#!/usr/bin/env python3
"""Bounded rehearsal of the v2 selection run.

The rehearsal measures what the single authorized v2 selection run costs
*before* that run starts. It exercises the real execution path against the
real v2 datasets and it **writes nothing into the repository**: every output
goes to ``--output-dir``, which defaults to a temporary directory outside the
checkout. The authorized run is therefore neither claimed nor consumed: the
ledger, the shards, the result manifest, the result stream and the checkpoint
of the rehearsal live in the output directory, not in the repository.

Two modes:

``micro``
    Executes a small sample of *real* units -- real datasets, real fold
    structure, real configurations, real cost scenarios, real experiment IDs --
    one at a time, and measures the wall clock of each unit and the size of
    its result record. The records are written through the real
    ``ResultStore`` into the output directory, so the shard-writing cost is
    measured as well.

``pipeline``
    Executes the real ``v2_campaign.runner.run_selection`` end to end against
    the real datasets, with the grid reduced to a single configuration per
    asset and with every output redirected into the output directory. It
    exercises the whole pipeline -- attempt claim, shard writing, checkpoint,
    ledger, result stream and the selection summary -- without touching the
    repository's own v2 paths.

Both modes read the real authorization and validate it through the real
``build_plan``; neither of them reads a candle inside the confirmatory window
(the real development-data loader refuses such a dataset twice) and neither of
them contacts a provider.

The printed report is JSON so that it can be diffed between runs.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.backtester import run_fold_backtest  # noqa: E402
from breakout_research.backtest.shards import ResultStore, serialize_record  # noqa: E402

from v2_campaign import runner, units  # noqa: E402
from v2_campaign.data import load_development_candles  # noqa: E402


def _plan(repo_root: Path):
    workspace = runner.default_workspace(repo_root)
    return runner.build_plan(workspace)


def _load_candles(plan, symbol: str):
    candles, provenance = load_development_candles(
        Path(plan.workspace.repo_root), symbol, plan.data_manifest, plan.boundary_ms
    )
    return candles, provenance


def _record_bytes(record: Dict[str, Any]) -> int:
    return len(serialize_record(record).encode("utf-8"))


def _unit_label(unit: Dict[str, Any]) -> str:
    return (
        f"{unit['asset']}/{unit['config'].config_id}/fold{unit['fold_index']}"
        f"/cost{unit['cost_index']}"
    )


def run_micro(plan, output_dir: Path, sample_configs: int, spread: int) -> Dict[str, Any]:
    """Time individual real units and measure the result-record size."""
    asset_index = 0
    symbol = str(plan.assets[asset_index]["symbol"])

    load_started = time.perf_counter()
    candles, provenance = _load_candles(plan, symbol)
    btc_candles, _btc_provenance = _load_candles(plan, "BTCUSDT")
    load_seconds = time.perf_counter() - load_started

    bounds = units.fold_bounds(candles, plan.folds)
    windows = units.validation_folds(bounds)
    if not windows:
        raise SystemExit("the rehearsal asset yields no validation fold")

    generated = list(
        units.iter_units(
            plan.assets,
            plan.configs,
            plan.cost_multipliers,
            windows,
            plan.data_hashes,
            plan.specification_hash,
            plan.code_identity["run_code_identity"],
            asset_index=asset_index,
        )
    )
    per_config = len(windows) * len(plan.cost_multipliers)

    # The mandated minimum: the first two units of the run (one asset, one
    # configuration, one validation fold, one cost scenario each).
    selected_indices = list(range(min(2, len(generated))))
    # A contiguous block of the first configuration, for a stable estimate of
    # the per-unit cost of a single configuration.
    selected_indices.extend(range(min(per_config, len(generated))))
    # A spread over the whole configuration grid, so the estimate is not bound
    # to the first configuration's parameters.
    if spread > 0:
        stride = max(1, len(generated) // spread)
        selected_indices.extend(range(0, len(generated), stride))
    selected_indices = sorted(set(index for index in selected_indices if index < len(generated)))

    store = ResultStore(
        campaign_id=plan.campaign_id,
        spec_hash=plan.specification_hash,
        code_hash=plan.code_identity["run_code_identity"],
        data_manifest_hash=plan.scope["data_manifest_hash"],
        shard_root=str(output_dir / "shards"),
        manifest_path=str(output_dir / "results_manifest.json"),
    )
    store.reconcile()
    stream_path = output_dir / "results_v2.jsonl"

    measurements: List[Dict[str, Any]] = []
    with stream_path.open("w", encoding="utf-8") as stream:
        for index in selected_indices:
            unit, experiment_id = generated[index]
            started = time.perf_counter()
            fold_res = run_fold_backtest(
                candles,
                unit["config"],
                btc_candles=btc_candles,
                start_time=unit["start_time"],
                end_time=unit["end_time"],
                cost_scenario=unit["cost_scenario"],
                fold_index=unit["fold_index"],
                asset=symbol,
            )
            elapsed = time.perf_counter() - started
            data_hash = units.unit_data_hash(symbol, unit["config"], plan.data_hashes)
            record = runner.fold_result_record(
                fold_res,
                experiment_id,
                data_hash,
                unit["start_time"],
                unit["end_time"],
                plan.specification_hash,
                plan.code_identity["run_code_identity"],
            )
            size = _record_bytes(record)
            store.append(experiment_id, record)
            stream.write(serialize_record(record))
            measurements.append(
                {
                    "index": index,
                    "unit": _unit_label(unit),
                    "elapsed_ms": round(elapsed * 1000.0, 3),
                    "record_bytes": size,
                    "trade_count": fold_res.trade_count,
                    "status": fold_res.status.value,
                }
            )
    store.flush()
    store.close()

    elapsed_ms = [entry["elapsed_ms"] for entry in measurements]
    sizes = [entry["record_bytes"] for entry in measurements]
    shard_bytes = sum(
        path.stat().st_size for path in sorted((output_dir / "shards").rglob("shard_*.jsonl"))
    )
    return {
        "mode": "micro",
        "asset": symbol,
        "candles": len(candles),
        "dataset_load_seconds": round(load_seconds, 3),
        "validation_folds": len(windows),
        "fold_window_candles": [window[1] - window[0] for window in windows],
        "configurations_in_grid": len(plan.configs),
        "units_available_for_asset": len(generated),
        "units_executed": len(measurements),
        "mandated_two_units": measurements[:2],
        "per_unit_ms": {
            "mean": round(statistics.fmean(elapsed_ms), 3),
            "median": round(statistics.median(elapsed_ms), 3),
            "min": round(min(elapsed_ms), 3),
            "max": round(max(elapsed_ms), 3),
        },
        "record_bytes": {
            "mean": round(statistics.fmean(sizes), 1),
            "median": statistics.median(sizes),
            "min": min(sizes),
            "max": max(sizes),
        },
        "output_bytes": {
            "shards": shard_bytes,
            "result_stream": stream_path.stat().st_size,
        },
        "measurements": measurements,
    }


def run_pipeline(plan, output_dir: Path, configs: int) -> Dict[str, Any]:
    """Run the real selection pipeline end to end into the output directory."""
    import json as _json

    manifest_path = Path(plan.workspace.config_manifest)
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    reduced = dict(manifest)
    reduced["configurations"] = list(manifest.get("configurations") or [])[:configs]
    reduced["total_configurations"] = len(reduced["configurations"])
    reduced["artifact_note"] = (
        "Rehearsal grid: the first %d configurations of the frozen grid. "
        "The authorized run uses the full grid." % len(reduced["configurations"])
    )
    rehearsal_manifest = output_dir / "config_manifest_rehearsal.json"
    rehearsal_manifest.write_text(
        _json.dumps(reduced, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    workspace = dataclasses.replace(
        plan.workspace,
        config_manifest=rehearsal_manifest,
        shards_dir=output_dir / "shards",
        ledger=output_dir / "ledger_v2.json",
        results_manifest=output_dir / "results_manifest_v2.json",
        results_stream=output_dir / "results_v2.jsonl",
        checkpoint=output_dir / "checkpoint_v2.json",
    )
    started = time.perf_counter()
    document = runner.run_selection(workspace)
    elapsed = time.perf_counter() - started

    counts = document.get("counts") or {}
    executed = int(counts.get("executed") or 0)
    shard_bytes = sum(
        path.stat().st_size for path in sorted((output_dir / "shards").rglob("shard_*.jsonl"))
    )
    shard_files = len(list((output_dir / "shards").rglob("shard_*.jsonl")))
    stream_bytes = (output_dir / "results_v2.jsonl").stat().st_size
    return {
        "mode": "pipeline",
        "status": document.get("status"),
        "configurations_per_asset": configs,
        "elapsed_seconds": round(elapsed, 3),
        "units_executed": executed,
        "seconds_per_unit": round(elapsed / executed, 6) if executed else None,
        "counts": counts,
        "selection_outcome": (document.get("selection") or {}).get("outcome"),
        "assets_evaluated": (document.get("selection") or {}).get("assets_evaluated"),
        "output_bytes": {
            "shards": shard_bytes,
            "shard_files": shard_files,
            "result_stream": stream_bytes,
        },
        "output_files": sorted(
            str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()
        ),
    }


def project(plan, per_unit_ms: float, record_bytes: float) -> Dict[str, Any]:
    """Project the cost and the volume of the full authorized run."""
    execution_units = int(plan.counts["execution_units"])
    seconds = execution_units * per_unit_ms / 1000.0
    total_bytes = execution_units * record_bytes
    return {
        "execution_units": execution_units,
        "projected_seconds": round(seconds, 1),
        "projected_hours": round(seconds / 3600.0, 3),
        "projected_shard_bytes": int(total_bytes),
        "projected_shard_mib": round(total_bytes / (1024 * 1024), 1),
        "projected_shard_files_at_4mib": int(total_bytes // (4 * 1024 * 1024)) + 1,
        "projected_result_stream_mib": round(total_bytes / (1024 * 1024), 1),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--mode", choices=("micro", "pipeline", "both"), default="both")
    parser.add_argument("--sample-configs", type=int, default=1,
                        help="how many configurations of the first asset to time")
    parser.add_argument("--spread", type=int, default=12,
                        help="how many extra units to spread over the configuration grid")
    parser.add_argument("--pipeline-configs", type=int, default=1,
                        help="how many configurations per asset the pipeline rehearsal runs")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(
        tempfile.mkdtemp(prefix="v2-selection-rehearsal-")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = _plan(repo_root)
    report: Dict[str, Any] = {
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "run_id": plan.run_id,
        "campaign_id": plan.campaign_id,
        "authorization_manifest_hash": plan.authorization_manifest_hash,
        "code_identity": plan.code_identity,
        "planned_units": plan.counts,
    }

    if args.mode in ("micro", "both"):
        micro = run_micro(plan, output_dir, args.sample_configs, args.spread)
        report["micro"] = micro
        report["projection"] = project(
            plan, micro["per_unit_ms"]["median"], micro["record_bytes"]["mean"]
        )

    if args.mode in ("pipeline", "both"):
        pipeline_dir = output_dir / "pipeline"
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        report["pipeline"] = run_pipeline(plan, pipeline_dir, args.pipeline_configs)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

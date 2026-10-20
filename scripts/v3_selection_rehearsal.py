#!/usr/bin/env python3
"""Bounded rehearsal of the v3 selection run.

The rehearsal measures what the single authorized v3 selection run costs
*before* that run starts. It exercises the real v3 execution path against the
real v3 datasets and it **writes nothing into the repository**: every output
goes to ``--output-dir``, which defaults to a temporary directory outside the
checkout. The authorized run is therefore neither claimed nor consumed: the
ledger, the shards, the result manifest, the result stream and the checkpoint
of the rehearsal live in the output directory, not in the repository.

Four probes, all of them read-only with respect to the repository:

``micro``
    Executes a small sample of *real* units -- real datasets, real fold
    structure, real configurations, real cost scenarios, real experiment IDs --
    one at a time, through the same window-sliced benchmark path the run uses,
    and measures the wall clock of each unit and the size of its result record.
    The records are written through the real ``ResultStore`` into the output
    directory, so the shard-writing cost is measured as well.

``pipeline``
    Executes the real ``v3_campaign.runner.run_selection`` end to end against
    the real datasets, with the grid reduced to a handful of configurations per
    asset and with every output redirected into the output directory. It
    exercises the whole pipeline -- attempt claim, shard writing, checkpoint,
    ledger, result stream and the selection summary -- without touching the
    repository's own v3 paths.

``boundary``
    A read-only probe of the confirmatory-window refusal: the real development
    data loader is asked for a dataset with a boundary inside the confirmatory
    window, and it must refuse the dataset *before* it is read. Nothing is
    written and no candle inside the confirmatory window is read.

``abort``
    Executes the real runner against a scratch workspace and makes the run
    abort with the very error the confirmatory-window refusal raises, so that
    the rollback path is exercised for real: the ledger, the results manifest,
    the result stream, the checkpoint and the shard directory the run created
    must all be gone afterwards.

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
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.backtester import run_fold_backtest  # noqa: E402
from breakout_research.backtest.shards import ResultStore, serialize_record  # noqa: E402

from v3_campaign import runner, units  # noqa: E402
from v3_campaign.benchmark import BENCHMARK_SYMBOL, align_window, assert_dataset_alignment  # noqa: E402
from v3_campaign.data import load_development_candles  # noqa: E402
from v3_campaign.errors import ConfirmatoryWindowViolation  # noqa: E402


def _reset_dir(path: Path) -> Path:
    """A clean scratch directory.

    The probes are re-runnable: a second run must not inherit the shards of
    the first one, because a record carries a ``stored_utc`` timestamp and two
    runs of the same unit therefore hold different bytes for the same
    experiment id.
    """
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def _reduced_config_manifest(plan, output_dir: Path, configs: int) -> Path:
    """A rehearsal grid: a few real configurations, always including a BTC one.

    The v3 path refuses a grid without a ``btc_ema_168`` configuration, so the
    reduced grid keeps the first configurations of the frozen grid and adds the
    first BTC trend-filter configuration when the prefix holds none.
    """
    manifest = json.loads(Path(plan.workspace.config_manifest).read_text(encoding="utf-8"))
    entries = list(manifest.get("configurations") or [])
    reduced = list(entries[:configs])
    if not any(entry.get("trend_filter") == "btc_ema_168" for entry in reduced):
        for entry in entries:
            if entry.get("trend_filter") == "btc_ema_168":
                reduced.append(entry)
                break
    body = dict(manifest)
    body["configurations"] = reduced
    body["total_configurations"] = len(reduced)
    body["artifact_note"] = (
        "Rehearsal grid: %d configurations of the frozen grid (the BTC trend-filter "
        "configuration is always kept). The authorized run uses the full grid."
        % len(reduced)
    )
    path = output_dir / "config_manifest_rehearsal.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_micro(plan, output_dir: Path, sample_configs: int, spread: int) -> Dict[str, Any]:
    """Time individual real units and measure the result-record size."""
    asset_index = 0
    symbol = str(plan.assets[asset_index]["symbol"])

    load_started = time.perf_counter()
    candles, _provenance = _load_candles(plan, symbol)
    benchmark_candles, benchmark_provenance = _load_candles(plan, BENCHMARK_SYMBOL)
    load_seconds = time.perf_counter() - load_started

    dataset_alignment = assert_dataset_alignment(candles, benchmark_candles, symbol)
    bounds = units.fold_bounds(candles, plan.folds)
    windows = units.validation_folds(bounds)
    if not windows:
        raise SystemExit("the rehearsal asset yields no validation fold")

    store = ResultStore(
        campaign_id=plan.campaign_id,
        spec_hash=plan.specification_hash,
        code_hash=plan.code_identity["run_code_identity"],
        data_manifest_hash=plan.data_manifest_provenance["effective_data_manifest_hash"],
        shard_root=str(output_dir / "shards"),
        manifest_path=str(output_dir / "results_manifest.json"),
    )
    store.reconcile()
    stream_path = output_dir / "results_v3.jsonl"

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
    # The first BTC trend-filter configuration of the grid is timed explicitly:
    # it is the most expensive configuration of the grid, and the projection
    # must not be blind to it.
    btc_config_indexes = [
        index for index, config in enumerate(plan.configs)
        if config.trend_filter.value == "btc_ema_168"
    ]
    btc_indices: List[int] = []
    if btc_config_indexes:
        first_btc = btc_config_indexes[0]
        btc_indices = list(range(first_btc * per_config, (first_btc + 1) * per_config))

    measurements: List[Dict[str, Any]] = []
    aligned_windows = 0
    window_candle_counts: List[int] = []
    with stream_path.open("w", encoding="utf-8") as stream:
        for start_time, end_time, fold_index, _holdout in windows:
            asset_slice, benchmark_slice, alignment = align_window(
                candles, benchmark_candles, start_time, end_time, symbol
            )
            aligned_windows += 1
            window_candle_counts.append(int(alignment["asset_candles"]))
            # The mandated minimum: the first two units of the run (one asset, one
            # configuration, one validation fold, one cost scenario each).
            selected_indices = list(range(min(2, len(generated))))
            # A contiguous block of the first configurations, for a stable
            # estimate of the per-unit cost of a single configuration.
            selected_indices.extend(
                range(min(sample_configs * per_config, len(generated)))
            )
            # A spread over the whole configuration grid, so the estimate is not
            # bound to the first configuration's parameters.
            if spread > 0:
                stride = max(1, len(generated) // spread)
                selected_indices.extend(range(0, len(generated), stride))
            # The units of the first BTC trend-filter configuration.
            selected_indices.extend(btc_indices)
            selected_indices = sorted(
                set(index for index in selected_indices if index < len(generated))
            )
            for index in selected_indices:
                unit, experiment_id = generated[index]
                if int(unit["fold_index"]) != int(fold_index):
                    continue
                started = time.perf_counter()
                fold_res = run_fold_backtest(
                    asset_slice,
                    unit["config"],
                    btc_candles=benchmark_slice,
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
                    alignment,
                )
                size = _record_bytes(record)
                store.append(experiment_id, record)
                stream.write(serialize_record(record))
                measurements.append(
                    {
                        "index": index,
                        "unit": _unit_label(unit),
                        "fold_index": int(fold_index),
                        "trend_filter": unit["config"].trend_filter.value,
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
        "benchmark_candles": len(benchmark_candles),
        "benchmark_content_hash": benchmark_provenance.get("content_hash"),
        "dataset_alignment": dataset_alignment,
        "dataset_load_seconds": round(load_seconds, 3),
        "validation_folds": len(windows),
        "fold_window_candles": [window[1] - window[0] for window in windows],
        "fold_window_candle_counts": window_candle_counts,
        "windows_aligned": aligned_windows,
        "configurations_in_grid": len(plan.configs),
        "units_available_for_asset": len(plan.configs) * len(windows) * len(plan.cost_multipliers),
        "units_executed": len(measurements),
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
    rehearsal_manifest = _reduced_config_manifest(plan, output_dir, configs)
    workspace = dataclasses.replace(
        plan.workspace,
        config_manifest=rehearsal_manifest,
        shards_dir=output_dir / "shards",
        ledger=output_dir / "ledger_v3.json",
        results_manifest=output_dir / "results_manifest_v3.json",
        results_stream=output_dir / "results_v3.jsonl",
        checkpoint=output_dir / "checkpoint_v3.json",
    )
    started = time.perf_counter()
    document = runner.run_selection(workspace)
    elapsed = time.perf_counter() - started

    counts = document.get("counts") or {}
    executed = int(counts.get("executed") or 0)
    shard_files = sorted((output_dir / "shards").rglob("shard_*.jsonl"))
    shard_bytes = sum(path.stat().st_size for path in shard_files)
    stream_path = output_dir / "results_v3.jsonl"
    return {
        "mode": "pipeline",
        "status": document.get("status"),
        "configurations_per_asset": json.loads(
            rehearsal_manifest.read_text(encoding="utf-8")
        )["total_configurations"],
        "elapsed_seconds": round(elapsed, 3),
        "units_executed": executed,
        "seconds_per_unit": round(elapsed / executed, 6) if executed else None,
        "counts": counts,
        "selection_outcome": (document.get("selection") or {}).get("outcome"),
        "assets_evaluated": (document.get("selection") or {}).get("assets_evaluated"),
        "holdout_exposed_count": document.get("holdout_exposed_count"),
        "runs": document.get("runs"),
        "benchmark_alignment_present": bool(document.get("benchmark_alignment")),
        "output_bytes": {
            "shards": shard_bytes,
            "shard_files": len(shard_files),
            "result_stream": stream_path.stat().st_size if stream_path.exists() else 0,
        },
        "output_files": sorted(
            str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()
        ),
    }


def run_boundary_probe(plan) -> Dict[str, Any]:
    """Prove the confirmatory-window refusal fires on the real dataset.

    The probe asks the real development-data loader for a dataset with a
    boundary that lies *inside* the confirmatory window. The loader must
    refuse the dataset before it is read, and it must do so with the
    confirmatory-window error. Nothing is written and no confirmatory-window
    candle is read.
    """
    symbol = str(plan.assets[0]["symbol"])
    inside_window_ms = plan.boundary_ms - 24 * 60 * 60 * 1000
    refused = False
    error_type = None
    message = None
    try:
        load_development_candles(
            Path(plan.workspace.repo_root), symbol, plan.data_manifest, inside_window_ms
        )
    except ConfirmatoryWindowViolation as exc:
        refused = True
        error_type = type(exc).__name__
        message = str(exc)[:300]
    return {
        "mode": "boundary",
        "asset": symbol,
        "boundary_ms_used": inside_window_ms,
        "development_boundary_ms": plan.boundary_ms,
        "refused": refused,
        "error_type": error_type,
        "message": message,
        "candles_read": 0,
    }


def run_abort_probe(plan, output_dir: Path) -> Dict[str, Any]:
    """Prove that a boundary abort rolls back every artifact the run created."""
    workspace = dataclasses.replace(
        plan.workspace,
        shards_dir=output_dir / "shards",
        ledger=output_dir / "ledger_v3.json",
        results_manifest=output_dir / "results_manifest_v3.json",
        results_stream=output_dir / "results_v3.jsonl",
        checkpoint=output_dir / "checkpoint_v3.json",
    )
    aborted = False
    error_type = None
    message = None
    original = runner.load_development_candles

    def _refuse(*_args, **_kwargs):
        raise ConfirmatoryWindowViolation(
            "rehearsal: the dataset reaches into the confirmatory window"
        )

    runner.load_development_candles = _refuse
    try:
        runner.run_selection(workspace)
    except ConfirmatoryWindowViolation as exc:
        aborted = True
        error_type = type(exc).__name__
        message = str(exc)[:300]
    finally:
        runner.load_development_candles = original

    files_left = sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
    )
    non_empty_directories = sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_dir() and any(path.iterdir())
    )
    return {
        "mode": "abort",
        "aborted": aborted,
        "error_type": error_type,
        "message": message,
        "files_left_behind": files_left,
        "non_empty_directories_left_behind": non_empty_directories,
        "rolled_back": aborted and not files_left and not non_empty_directories,
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
    parser.add_argument(
        "--mode", choices=("micro", "pipeline", "boundary", "abort", "all"), default="all"
    )
    parser.add_argument(
        "--sample-configs", type=int, default=1,
        help="how many configurations of the first asset to time",
    )
    parser.add_argument(
        "--spread", type=int, default=12,
        help="how many extra units to spread over the configuration grid",
    )
    parser.add_argument(
        "--pipeline-configs", type=int, default=2,
        help="how many configurations per asset the pipeline rehearsal runs",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(
        tempfile.mkdtemp(prefix="v3-selection-rehearsal-")
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

    if args.mode in ("boundary", "all"):
        report["boundary"] = run_boundary_probe(plan)
    if args.mode in ("micro", "all"):
        micro_dir = _reset_dir(output_dir / "micro")
        micro = run_micro(plan, micro_dir, args.sample_configs, args.spread)
        report["micro"] = micro
        report["projection"] = project(
            plan, micro["per_unit_ms"]["median"], micro["record_bytes"]["mean"]
        )
    if args.mode in ("pipeline", "all"):
        pipeline_dir = _reset_dir(output_dir / "pipeline")
        report["pipeline"] = run_pipeline(plan, pipeline_dir, args.pipeline_configs)
    if args.mode in ("abort", "all"):
        abort_dir = _reset_dir(output_dir / "abort")
        report["abort"] = run_abort_probe(plan, abort_dir)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

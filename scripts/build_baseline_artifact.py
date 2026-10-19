#!/usr/bin/env python3
"""Build the per-campaign buy-and-hold baseline artifact (BRAIN-006, option B3).

The baseline is recomputed from the frozen, hash-verified candle datasets over
the validation fold windows of the campaign, on the campaign's own cost,
daily-return and Sharpe conventions.  The artifact is deterministic: it holds
no wall-clock timestamp, so a re-run is byte-identical.

The artifact is written to ``research/baselines/<campaign_id>.json`` and is the
only baseline source the conforming selector is allowed to consume.  The
selector fails closed when the artifact is missing or when the recorded data
hash no longer matches the data manifest.

Usage:
    PYTHONPATH=src python3 scripts/build_baseline_artifact.py <cycle_root> \
        [--out research/baselines/<campaign_id>.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.baselines import (  # noqa: E402
    BaselineDataError,
    artifact_hash,
    buyhold_baseline,
    data_manifest_content_hash,
    load_verified_candles,
)
from breakout_research.config import CostScenario, compute_code_hash  # noqa: E402


def load_json(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_shard_root(cycle_root: Path) -> Path:
    """Resolve the directory that holds a cycle's ``*.jsonl`` result shards."""
    candidates = [path for path in sorted(cycle_root.rglob("*"))
                  if path.is_dir() and any(path.glob("*.jsonl"))]
    if not candidates:
        raise SystemExit(f"no result shards found under {cycle_root}")
    if len(candidates) > 1:
        raise SystemExit(f"ambiguous shard sets under {cycle_root}: {[str(p) for p in candidates]}")
    return candidates[0]


def collect_fold_windows(shard_root: Path) -> Tuple[Dict[str, Dict[int, Tuple[int, int]]], Dict[str, Any]]:
    """Read the validation fold windows of every asset from the result shards.

    Holdout records are refused: the baseline must be computed on validation
    windows only.
    """
    windows: Dict[str, Dict[int, Tuple[int, int]]] = {}
    records_read = 0
    holdout_records = 0
    for path in sorted(shard_root.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                records_read += 1
                if record.get("is_holdout"):
                    holdout_records += 1
                    raise SystemExit(
                        "holdout record encountered while collecting fold windows: "
                        f"asset={record.get('asset')} config={record.get('config_id')}")
                asset = str(record["asset"])
                fold_index = int(record["fold_index"])
                bounds = (int(record["start_time"]), int(record["end_time"]))
                asset_windows = windows.setdefault(asset, {})
                if fold_index in asset_windows and asset_windows[fold_index] != bounds:
                    raise SystemExit(
                        f"inconsistent fold bounds for {(asset, fold_index)}: "
                        f"{asset_windows[fold_index]} != {bounds}")
                asset_windows[fold_index] = bounds
    return windows, {"records_read": records_read, "holdout_records_read": holdout_records}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cycle_root", help="cycle directory containing results_shards/<campaign_id>/")
    parser.add_argument("--out", default=None, help="artifact path (default: research/baselines/<campaign_id>.json)")
    parser.add_argument("--spec", default=str(REPO_ROOT / "configs" / "research_v1.json"))
    parser.add_argument("--data-manifest", default=str(REPO_ROOT / "research" / "data_manifest.json"))
    args = parser.parse_args(argv)

    cycle_root = Path(args.cycle_root).resolve()
    shard_root = resolve_shard_root(cycle_root)
    campaign_id = shard_root.name

    spec = load_json(Path(args.spec))
    data_manifest = load_json(Path(args.data_manifest))
    scenarios = [CostScenario.baseline().scaled(multiplier) for multiplier in spec["costs"]["scenarios"]]

    windows, stats = collect_fold_windows(shard_root)

    assets: Dict[str, Any] = {}
    for asset in sorted(windows):
        fold_windows = {int(fold): bounds for fold, bounds in windows[asset].items()}
        try:
            candles, provenance = load_verified_candles(asset, data_manifest, REPO_ROOT)
        except (KeyError, ValueError, BaselineDataError) as exc:
            assets[asset] = {
                "status": "NOT_EVALUABLE",
                "reason": f"candle dataset unavailable: {exc}",
                "per_cost": {},
                "variant_median_sharpe": {},
                "provenance": None,
                "fold_windows": {str(fold): list(bounds) for fold, bounds in sorted(fold_windows.items())},
            }
            continue
        baseline = buyhold_baseline(candles, fold_windows, scenarios)
        baseline["provenance"] = provenance
        baseline["fold_windows"] = {str(fold): list(bounds) for fold, bounds in sorted(fold_windows.items())}
        assets[asset] = baseline

    artifact: Dict[str, Any] = {
        "artifact": "buyhold_baseline",
        "schema_version": 1,
        "campaign_id": campaign_id,
        "protocol_version": spec.get("protocol_version"),
        "specification_hash": spec.get("specification_hash"),
        "code_hash": compute_code_hash(),
        "data_manifest_hash": data_manifest_content_hash(data_manifest),
        "cost_scenarios": [float(multiplier) for multiplier in spec["costs"]["scenarios"]],
        "initial_capital": 10000.0,
        "cost_convention": (
            "breakout_research.backtest.backtester._apply_costs (slippage on the execution "
            "price, taker fee on the slippage-adjusted notional); position fully invested from "
            "the first bar's open of the fold window and flattened at the last bar's close"),
        "sharpe_convention": (
            "daily returns aligned by UTC calendar day (last equity value of the day), "
            "annualized on a 365-day calendar with the sample standard deviation"),
        "inputs": {
            "records_read": stats["records_read"],
            "holdout_records_read": stats["holdout_records_read"],
            "assets": sorted(windows),
            "fold_count_per_asset": {asset: len(windows[asset]) for asset in sorted(windows)},
        },
        "assets": assets,
    }
    artifact["baseline_hash"] = artifact_hash(artifact, exclude=("baseline_hash",))

    out_path = Path(args.out) if args.out else REPO_ROOT / "research" / "baselines" / f"{campaign_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "output": str(out_path),
        "campaign_id": campaign_id,
        "baseline_hash": artifact["baseline_hash"],
        "records_read": stats["records_read"],
        "holdout_records_read": stats["holdout_records_read"],
        "assets_not_evaluable": sorted(a for a, e in assets.items() if e.get("status") != "OK"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

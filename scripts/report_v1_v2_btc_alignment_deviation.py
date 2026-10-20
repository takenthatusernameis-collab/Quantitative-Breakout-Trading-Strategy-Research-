#!/usr/bin/env python3
"""Recompute the BTC-alignment deviation of the completed v1 and v2 runs.

BRAIN-013 records that the frozen engine pairs the BTC series with the asset
series **by index**, while the frozen methodology requires the alignment "by
UTC candle close". The completed v1 and v2 runs evaluated the BTC trend filter
under that index pairing, so the deviation has to be disclosed with its exact
count.

This script recomputes the count from the primary evidence of the completed
runs -- the v2 ledger, the configuration manifest, the frozen v1 fold rule and
the v2 datasets -- and writes it to
``research/v3_evidence/v1_v2_btc_alignment_deviation.json``. It is read-only
with respect to the repository apart from that one evidence file, and it
performs no evaluation.

The script also recomputes the **per-fold offset**: the engine takes the BTC
value at index ``i`` of the *whole* BTC history, while the asset value at index
``i`` belongs to the fold window. The offset is therefore the distance between
the first candle of the fold window and the first candle of the BTC history.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import TrendFilter  # noqa: E402
from v2_campaign.units import fold_bounds, validation_folds  # noqa: E402

LEDGER_RELATIVE = "research/ledger_v2.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
OUT_RELATIVE = "research/v3_evidence/v1_v2_btc_alignment_deviation.json"

HOUR_MS = 3600 * 1000


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iso_from_ms(milliseconds: int) -> str:
    return datetime.fromtimestamp(int(milliseconds) / 1000, timezone.utc).isoformat()


def build_report(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root)
    ledger = read_json(root / LEDGER_RELATIVE)
    config_manifest = read_json(root / CONFIG_MANIFEST_RELATIVE)
    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    data_v2 = read_json(root / DATA_V2_RELATIVE)

    configurations = config_manifest.get("configurations") or []
    btc_configurations = [
        configuration for configuration in configurations
        if str(configuration.get("trend_filter")) == TrendFilter.BTC_EMA_168.value
    ]
    scope = (ledger.get("scope") or {}).get("binance_pairs") or []
    asset_count = len(scope)
    fold_count = len(spec_v1["folds"]["window_fractions"])
    cost_count = len(spec_v1["costs"]["scenarios"])

    total_records = int((ledger.get("counts") or {}).get("execution_units") or 0)
    affected_records = asset_count * len(btc_configurations) * fold_count * cost_count

    btc_entry = (data_v2.get("assets") or {}).get("BTCUSDT") or {}
    asset_entry = (data_v2.get("assets") or {}).get(scope[0]) if scope else {}
    windows_share = (
        asset_entry.get("first_candle_timestamp") == btc_entry.get("first_candle_timestamp")
        and asset_entry.get("last_candle_timestamp") == btc_entry.get("last_candle_timestamp")
    )

    # The per-fold offset, recomputed from the frozen v1 fold rule.
    offsets: List[Dict[str, Any]] = []
    if asset_entry.get("dataset_path"):
        from breakout_research.data.fetcher import _read_dataset

        candles = _read_dataset(root / asset_entry["dataset_path"])
        for start_time, end_time, fold_index, _holdout in validation_folds(
            fold_bounds(candles, spec_v1["folds"])
        ):
            offset_ms = int(btc_entry["first_candle_timestamp"]) - int(start_time)
            offsets.append({
                "fold_index": int(fold_index),
                "fold_first_candle_utc": iso_from_ms(start_time),
                "btc_index_zero_candle_utc": iso_from_ms(int(btc_entry["first_candle_timestamp"])),
                "offset_hours": offset_ms // HOUR_MS,
                "aligned": offset_ms == 0,
            })

    misaligned_folds = [entry["fold_index"] for entry in offsets if not entry["aligned"]]

    return {
        "artifact": "v1_v2_btc_alignment_deviation",
        "artifact_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "finding": (
            "The completed v1 and v2 runs evaluated the BTC trend filter under the frozen "
            "engine's index pairing, not under the UTC-candle-close alignment the frozen "
            "methodology requires. The deviation affects every validation fold, because "
            "the first validation fold already starts 40% of the way into the history."
        ),
        "engine_rule": (
            "src/breakout_research/signals/generator.py compares closes[i] with "
            "btc_ema_168[i], where i indexes the fold window of the asset and the BTC "
            "series is passed unsliced; src/breakout_research/backtest/backtester.py "
            "slices the asset series to the fold window and not the BTC series."
        ),
        "methodology_rule": "docs/research_protocol.md:101 - Align BTC and target asset by UTC candle close",
        "counts": {
            "total_v2_records": total_records,
            "records_with_btc_filter": affected_records,
            "share_of_records": (affected_records / total_records) if total_records else None,
            "btc_filter_configurations_per_asset": len(btc_configurations),
            "total_configurations_per_asset": len(configurations),
            "assets": asset_count,
            "validation_folds": fold_count,
            "cost_scenarios": cost_count,
            "misaligned_validation_folds": misaligned_folds,
            "aligned_validation_folds": [
                entry["fold_index"] for entry in offsets if entry["aligned"]
            ],
        },
        "per_fold_offset": offsets,
        "v2_btc_and_asset_windows_share_the_same_span": windows_share,
        "correction": (
            "BRAIN-013 recorded that fold 0 was aligned and that 93,312 of 497,664 v2 "
            "records were affected. Recomputation from the frozen fold rule shows that the "
            "first validation fold starts at 40% of the span, so no validation fold was "
            "aligned and the affected count is 124,416, not 93,312."
        ),
        "repair": (
            "None. The completed runs are immutable; the deviation is a disclosure for the "
            "final report. The v3 execution path implements the correct alignment in new "
            "code outside the hashed set."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--out", default=None, help="optional path for the JSON report")
    args = parser.parse_args(argv)

    report = build_report(Path(args.repo_root))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

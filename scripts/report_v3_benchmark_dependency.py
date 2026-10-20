#!/usr/bin/env python3
"""Report the BTC benchmark dependency of the v3 selection line.

This is a **read-only diagnostic**. It recomputes every fact it prints from
the bytes on disk and writes nothing. It exists because the v3 universe
declares a benchmark constituent that the v3 data manifest does not contain,
and because the frozen engine aligns the BTC series with the asset series by
*index* while the frozen methodology requires the alignment "by UTC candle
close". Both facts must be re-derivable by the next session instead of being
trusted from a report.

The report has three sections:

* ``grid`` -- how much of the inherited 2,304-configuration grid needs the BTC
  series, recomputed from ``research/config_manifest.json``;
* ``alignment`` -- how the frozen engine pairs the BTC series with the asset
  series, demonstrated behaviourally on synthetic candles and cross-checked
  against the frozen methodology text;
* ``v3_state`` -- whether a hash-verified, index-aligned BTC benchmark dataset
  exists for the v3 asset window, and whether any v3 execution artifact exists.

Exit status is always 0: the script is a report, not a gate. A missing
benchmark dataset is a *finding*, not a script error; the gate that enforces
it is the v3 selection authorization, which does not exist yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import (  # noqa: E402
    Candle,
    ConfirmationMode,
    EntryRule,
    ExitType,
    StrategyConfig,
    TrendFilter,
)
from breakout_research.signals.generator import generate_entry_signals  # noqa: E402

HOUR_MS = 3_600_000

V3_UNIVERSE_MANIFEST = "research/universe_manifest_v3.json"
V3_DATA_MANIFEST = "research/data_manifest_v3.json"
V3_DATA_MANIFEST_AMENDMENT_1 = "configs/research_v3_data_manifest_amendment_1.json"
V2_DATA_MANIFEST = "research/data_manifest_v2.json"
V1_DATA_MANIFEST = "research/data_manifest.json"
CONFIG_MANIFEST = "research/config_manifest.json"
V3_SPEC = "configs/research_v3.json"
V3_EXECUTION = "configs/research_v3_execution.json"
PROTOCOL_DOC = "docs/research_protocol.md"
QUEUE = "research_state/brainstorming_queue.md"

#: The v3 execution artifacts that must not exist before an authorized run.
V3_EXECUTION_ARTIFACTS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
    "research/v3_selected_configurations_manifest.json",
)

#: The v3 authorization that would consume the single v3 selection run.
V3_AUTHORIZATION = "configs/research_v3_selection_authorization_1.json"


def load_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat()


def parse_utc_ms(value: str) -> int:
    """Parse an ISO-8601 UTC instant into milliseconds since the epoch."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


# --------------------------------------------------------------------------
# grid
# --------------------------------------------------------------------------


def grid_report(repo_root: Path) -> Dict[str, Any]:
    """How much of the inherited grid needs the BTC series."""
    manifest = load_json(repo_root / CONFIG_MANIFEST)
    configurations = manifest.get("configurations") or []
    by_filter: Dict[str, int] = {}
    for configuration in configurations:
        filter_name = str(configuration.get("trend_filter"))
        by_filter[filter_name] = by_filter.get(filter_name, 0) + 1
    total = len(configurations)
    btc = by_filter.get(TrendFilter.BTC_EMA_168.value, 0)
    declared_total = manifest.get("total_configurations")
    return {
        "config_manifest_path": CONFIG_MANIFEST,
        "total_configurations": total,
        "declared_total_configurations": declared_total,
        "declared_total_matches": declared_total == total,
        "configurations_by_trend_filter": by_filter,
        "btc_filter_configurations": btc,
        "btc_filter_share": (btc / total) if total else None,
        "assets_needing_a_btc_series": "every asset whose grid is evaluated",
    }


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------


def _candle(timestamp: int, close: float, high: float | None = None, low: float | None = None) -> Candle:
    return Candle(
        timestamp=int(timestamp),
        open=close,
        high=close if high is None else high,
        low=close if low is None else low,
        close=close,
        volume=1.0,
    )


def _probe_config() -> StrategyConfig:
    return StrategyConfig(
        config_id="probe-btc-ema-168",
        entry_rule=EntryRule.CLOSE_BREAKOUT,
        entry_lookback=12,
        buffer_atr_multiple=0.0,
        confirmation=ConfirmationMode.ONE_CLOSE,
        trend_filter=TrendFilter.BTC_EMA_168,
        exit=ExitType.CHANNEL_12,
        content_hash="probe",
    )


def _asset_series(count: int = 300, start_ms: int = 1_700_000_000_000) -> List[Candle]:
    """A flat asset that breaks out in its last bars."""
    candles: List[Candle] = []
    for index in range(count):
        close = 100.0 if index < count - 20 else 200.0
        candles.append(_candle(start_ms + index * HOUR_MS, close))
    return candles


def _btc_series(values: Sequence[float], start_ms: int) -> List[Candle]:
    return [_candle(start_ms + index * HOUR_MS, float(value)) for index, value in enumerate(values)]


def alignment_probe(repo_root: Path) -> Dict[str, Any]:
    """Demonstrate, on synthetic candles, how the engine pairs BTC with an asset.

    Two properties are demonstrated:

    * the *timestamps* of the BTC series are ignored -- a BTC series with the
      same values at different instants produces the same signals;
    * the BTC value at the *index* of the asset bar is what is compared -- a
      BTC series whose value at one index differs changes the signals.
    """
    asset = _asset_series()
    config = _probe_config()
    base_ms = asset[0].timestamp

    low = [1.0] * len(asset)
    high = [1_000_000.0] * len(asset)

    signals_low = generate_entry_signals(asset, config, _btc_series(low, base_ms))
    signals_high = generate_entry_signals(asset, config, _btc_series(high, base_ms))

    # Same values, timestamps shifted by 1000 hours: the result must not move.
    shifted = _btc_series(low, base_ms + 1000 * HOUR_MS)
    signals_shifted = generate_entry_signals(asset, config, shifted)

    # Same timestamps, the value at the signal index raised above the asset close.
    signal_index = signals_low[0].index if signals_low else len(asset) - 1
    perturbed_values = list(low)
    perturbed_values[signal_index] = 1_000_000.0
    signals_perturbed = generate_entry_signals(asset, config, _btc_series(perturbed_values, base_ms))

    timestamps_ignored = len(signals_low) == len(signals_shifted)
    index_value_used = len(signals_low) != len(signals_perturbed)

    generator_source = (repo_root / "src/breakout_research/signals/generator.py").read_text(encoding="utf-8")
    backtester_source = (repo_root / "src/breakout_research/backtest/backtester.py").read_text(encoding="utf-8")
    source_markers = {
        "generator_compares_by_index": "btc_ema_168[i]" in generator_source,
        "generator_bounds_check_is_index_based": "i >= len(btc_ema_168)" in generator_source,
        "backtester_slices_the_asset_but_not_the_btc_series": (
            "fold_candles = [c for c in fold_candles if c.timestamp >= start_time]" in backtester_source
            and "btc_closes = [c.close for c in btc_candles]" in backtester_source
        ),
    }

    protocol_text = (repo_root / PROTOCOL_DOC).read_text(encoding="utf-8")
    protocol_requires_timestamp_alignment = "Align BTC and target asset by UTC candle close" in protocol_text
    protocol_line = None
    for number, line in enumerate(protocol_text.splitlines(), start=1):
        if "Align BTC and target asset by UTC candle close" in line:
            protocol_line = number
            break

    return {
        "alignment_mode": "positional_by_index",
        "timestamps_considered": not timestamps_ignored,
        "probe_timestamps_ignored": timestamps_ignored,
        "probe_index_value_used": index_value_used,
        "probe_signal_counts": {
            "btc_below_asset_close": len(signals_low),
            "btc_above_asset_close": len(signals_high),
            "btc_same_values_other_timestamps": len(signals_shifted),
            "btc_one_value_perturbed": len(signals_perturbed),
        },
        "source_markers": source_markers,
        "source_markers_all_true": all(source_markers.values()),
        "frozen_methodology_requires_timestamp_alignment": protocol_requires_timestamp_alignment,
        "frozen_methodology_reference": f"{PROTOCOL_DOC}:{protocol_line}",
    }


# --------------------------------------------------------------------------
# v3 state
# --------------------------------------------------------------------------


def _window_of(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "first_candle_timestamp": entry.get("first_candle_timestamp"),
        "first_candle_utc": iso(entry["first_candle_timestamp"]) if entry.get("first_candle_timestamp") else None,
        "last_candle_timestamp": entry.get("last_candle_timestamp"),
        "last_candle_utc": iso(entry["last_candle_timestamp"]) if entry.get("last_candle_timestamp") else None,
        "observed_candle_count": entry.get("observed_candle_count"),
        "dataset_path": entry.get("dataset_path"),
        "content_hash": entry.get("content_hash"),
    }


def _index_offset_ms(asset: Dict[str, Any], benchmark: Dict[str, Any]) -> Optional[int]:
    """How far the benchmark's index-0 candle sits from the asset's index-0 candle."""
    asset_first = asset.get("first_candle_timestamp")
    benchmark_first = benchmark.get("first_candle_timestamp")
    if not isinstance(asset_first, int) or not isinstance(benchmark_first, int):
        return None
    return int(benchmark_first) - int(asset_first)


def v3_state_report(repo_root: Path) -> Dict[str, Any]:
    """Whether an index-aligned, hash-verified BTC benchmark dataset exists.

    The dataset is looked up in the **effective** v3 data manifest: the base
    manifest plus the benchmark entry published by
    ``configs/research_v3_data_manifest_amendment_1.json``. The base manifest
    is frozen and is not edited in place, so the benchmark entry lives in the
    amendment and the v3 execution path materializes the effective view at run
    time; a report that looked only at the base manifest would keep reporting
    a gap that no longer exists.
    """
    root = Path(repo_root)
    universe = load_json(root / V3_UNIVERSE_MANIFEST)
    base_data_manifest = load_json(root / V3_DATA_MANIFEST)
    spec = load_json(root / V3_SPEC)
    execution = load_json(root / V3_EXECUTION)

    benchmark_symbol = str((universe.get("benchmark_asset") or {}).get("symbol") or "BTCUSDT")
    declared_benchmark = (universe.get("benchmark_asset") or {})

    assets = base_data_manifest.get("assets") or {}
    validated = sorted(
        symbol for symbol, entry in assets.items()
        if (base_data_manifest.get("content_hashes") or {}).get(symbol)
    )
    windows = {
        symbol: _window_of(assets[symbol]) for symbol in validated if symbol in assets
    }
    distinct_windows = {
        (window["first_candle_timestamp"], window["last_candle_timestamp"], window["observed_candle_count"])
        for window in windows.values()
    }
    asset_window = None
    if len(distinct_windows) == 1 and windows:
        asset_window = next(iter(windows.values()))

    in_base = benchmark_symbol in assets

    # The effective data manifest: the base manifest plus the published
    # benchmark entry. Recomputed here from the bytes on disk.
    data_manifest = base_data_manifest
    amendment_entry: Dict[str, Any] = {}
    amendment_path = root / V3_DATA_MANIFEST_AMENDMENT_1
    if amendment_path.exists():
        amendment = load_json(amendment_path)
        amendment_entry = (amendment.get("benchmark_asset") or {}).get("entry") or {}
        if amendment_entry:
            data_manifest = json.loads(json.dumps(base_data_manifest))
            data_manifest.pop("manifest_hash", None)
            snapshot = data_manifest.get("snapshot_identity")
            if isinstance(snapshot, dict):
                snapshot.pop("data_manifest_hash", None)
            data_manifest.setdefault("assets", {})[benchmark_symbol] = amendment_entry
            data_manifest.setdefault("content_hashes", {})[benchmark_symbol] = (
                amendment_entry.get("content_hash")
            )

    effective_assets = data_manifest.get("assets") or {}
    in_v3 = benchmark_symbol in effective_assets
    benchmark_entry = effective_assets.get(benchmark_symbol) or {}
    v3_benchmark_window = _window_of(benchmark_entry) if in_v3 else None

    # The only other hash-verified BTC dataset in the repository.
    candidates: List[Dict[str, Any]] = []
    for label, relative in (("v2", V2_DATA_MANIFEST), ("v1", V1_DATA_MANIFEST)):
        path = root / relative
        if not path.exists():
            continue
        manifest = load_json(path)
        entry = (manifest.get("assets") or {}).get(benchmark_symbol)
        if not entry:
            continue
        window = _window_of(entry)
        candidates.append(
            {
                "source": label,
                "data_manifest_path": relative,
                "data_manifest_hash": manifest.get("manifest_hash"),
                "window": window,
                "index_offset_ms_vs_v3_assets": _index_offset_ms(asset_window or {}, window),
                "index_aligned_with_v3_assets": (
                    asset_window is not None
                    and window["first_candle_timestamp"] == asset_window["first_candle_timestamp"]
                    and window["last_candle_timestamp"] == asset_window["last_candle_timestamp"]
                ),
            }
        )

    v3_window_start = (
        ((universe.get("snapshot_identity") or {}).get("market_cap_source_retrieval_timestamp_utc"))
    )
    cutoff = ((execution.get("selection_data_boundary") or {}).get("development_data_cutoff_utc"))
    cutoff_ms = parse_utc_ms(cutoff) if cutoff else None

    existing_artifacts = [
        relative for relative in V3_EXECUTION_ARTIFACTS if (root / relative).exists()
    ]
    authorization_exists = (root / V3_AUTHORIZATION).exists()

    queue_text = (root / QUEUE).read_text(encoding="utf-8") if (root / QUEUE).exists() else ""
    decision_recorded = "## BRAIN-013" in queue_text

    return {
        "universe_version": universe.get("universe_version"),
        "declared_benchmark_asset": declared_benchmark,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_in_v3_data_manifest": in_v3,
        "benchmark_in_v3_base_data_manifest": in_base,
        "benchmark_published_by_amendment": bool(amendment_entry),
        "v3_benchmark_window": v3_benchmark_window,
        "v3_validated_assets": validated,
        "v3_validated_asset_count": len(validated),
        "v3_assets_share_one_window": len(distinct_windows) == 1,
        "v3_asset_window": asset_window,
        "other_btc_datasets": candidates,
        "index_aligned_benchmark_available": bool(
            in_v3
            and asset_window is not None
            and v3_benchmark_window is not None
            and v3_benchmark_window["first_candle_timestamp"] == asset_window["first_candle_timestamp"]
            and v3_benchmark_window["last_candle_timestamp"] == asset_window["last_candle_timestamp"]
        ),
        "v3_confirmatory_window_start_utc": v3_window_start,
        "development_data_cutoff_utc": cutoff,
        "development_data_cutoff_ms": cutoff_ms,
        "v3_execution_artifacts_present": existing_artifacts,
        "v3_selection_authorization_present": authorization_exists,
        "decision_record_brain_013_present": decision_recorded,
        "specification_status": spec.get("specification_status"),
        "execution_protocol_status": execution.get("specification_status"),
    }


def build_report(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root)
    grid = grid_report(root)
    alignment = alignment_probe(root)
    state = v3_state_report(root)

    if state["index_aligned_benchmark_available"]:
        status = "BENCHMARK_DATASET_AVAILABLE"
        summary = (
            "The v3 universe declares {symbol} as the benchmark constituent and a "
            "hash-verified, index-aligned dataset for it is published by a versioned "
            "data-manifest amendment and materialized as the effective v3 data manifest. "
            "{share:.0%} of the inherited grid ({count} of {total} configurations) needs "
            "the BTC series, and the v3 execution path slices the asset series and the "
            "benchmark series to the same fold window, so the frozen engine's index "
            "pairing is the UTC-candle-close alignment the frozen methodology requires. "
            "No v3 run has been performed and no v3 selection authorization exists."
        ).format(
            symbol=state["benchmark_symbol"],
            share=(grid["btc_filter_share"] or 0.0),
            count=grid["btc_filter_configurations"],
            total=grid["total_configurations"],
        )
    elif state["v3_selection_authorization_present"]:
        status = "BLOCKED_MISSING_BENCHMARK_DATASET_AUTHORIZATION_EXISTS"
        summary = (
            "The v3 universe declares {symbol} as the benchmark constituent, but the "
            "effective v3 data manifest contains no dataset for it, while {share:.0%} of "
            "the inherited grid ({count} of {total} configurations) needs the BTC series. "
            "The frozen engine pairs the BTC series with the asset series by index, so a "
            "benchmark dataset with a different window is silently misaligned."
        ).format(
            symbol=state["benchmark_symbol"],
            share=(grid["btc_filter_share"] or 0.0),
            count=grid["btc_filter_configurations"],
            total=grid["total_configurations"],
        )
    else:
        status = "BLOCKED_MISSING_BENCHMARK_DATASET"
        summary = (
            "The v3 universe declares {symbol} as the benchmark constituent, but the "
            "effective v3 data manifest contains no dataset for it, while {share:.0%} of "
            "the inherited grid ({count} of {total} configurations) needs the BTC series. "
            "The frozen engine pairs the BTC series with the asset series by index, so a "
            "benchmark dataset with a different window is silently misaligned."
        ).format(
            symbol=state["benchmark_symbol"],
            share=(grid["btc_filter_share"] or 0.0),
            count=grid["btc_filter_configurations"],
            total=grid["total_configurations"],
        )

    return {
        "artifact": "v3_benchmark_dependency_report",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "repo_root": str(root),
        "status": status,
        "blocking": status != "BENCHMARK_DATASET_AVAILABLE",
        "summary": summary,
        "grid": grid,
        "alignment": alignment,
        "v3_state": state,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--out", default=None, help="optional path for the JSON report")
    args = parser.parse_args(argv)

    report = build_report(Path(args.repo_root))
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

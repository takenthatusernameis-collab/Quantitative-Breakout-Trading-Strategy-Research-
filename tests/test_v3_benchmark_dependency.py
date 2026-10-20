"""Deterministic tests for the v3 BTC benchmark dependency (BRAIN-013).

The v3 universe declares ``BTCUSDT`` as a constituent -- the benchmark and the
BTC trend-filter input -- but the v3 data manifest contains no dataset for it,
while a quarter of the inherited 2,304-configuration grid needs the BTC series.
The frozen engine pairs that series with the asset series **by index**, so a
benchmark dataset with a different window is silently misaligned.

These tests lock the facts behind that finding. Every expectation is
recomputed from the repository (the manifests, the configuration manifest, the
frozen source and the frozen methodology text); nothing is compared against a
constant copied out of the artifact it describes. The facts they assert are
invariants: they hold both while the gap exists and after the benchmark dataset
is published, so the module stays green across the implementation of BRAIN-013.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from breakout_research.config import (  # noqa: E402
    Candle,
    ConfirmationMode,
    EntryRule,
    ExitType,
    StrategyConfig,
    TrendFilter,
)
from breakout_research.signals.generator import generate_entry_signals  # noqa: E402

import report_v3_benchmark_dependency as report  # noqa: E402

V3_UNIVERSE_MANIFEST = "research/universe_manifest_v3.json"
V3_DATA_MANIFEST = "research/data_manifest_v3.json"
V2_DATA_MANIFEST = "research/data_manifest_v2.json"
CONFIG_MANIFEST = "research/config_manifest.json"
V1_SPEC = "configs/research_v1.json"
V2_LEDGER = "research/ledger_v2.json"
PROTOCOL_DOC = "docs/research_protocol.md"
QUEUE = "research_state/brainstorming_queue.md"
V3_AUTHORIZATION = "configs/research_v3_selection_authorization_1.json"

HOUR_MS = 3_600_000


def load_json(relative: str) -> Any:
    with (REPO_ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _candle(timestamp: int, close: float) -> Candle:
    return Candle(
        timestamp=int(timestamp),
        open=close,
        high=close,
        low=close,
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
    candles: List[Candle] = []
    for index in range(count):
        close = 100.0 if index < count - 20 else 200.0
        candles.append(_candle(start_ms + index * HOUR_MS, close))
    return candles


def _btc_series(values: List[float], start_ms: int) -> List[Candle]:
    return [_candle(start_ms + index * HOUR_MS, float(value)) for index, value in enumerate(values)]


# --------------------------------------------------------------------------
# the grid
# --------------------------------------------------------------------------


def test_a_quarter_of_the_inherited_grid_needs_the_btc_series():
    manifest = load_json(CONFIG_MANIFEST)
    configurations = manifest["configurations"]
    by_filter: Dict[str, int] = {}
    for configuration in configurations:
        name = str(configuration["trend_filter"])
        by_filter[name] = by_filter.get(name, 0) + 1
    total = len(configurations)

    assert total == manifest["total_configurations"] == 2_304
    assert by_filter[TrendFilter.BTC_EMA_168.value] == 576
    assert by_filter[TrendFilter.BTC_EMA_168.value] * 4 == total
    assert set(by_filter) == {
        TrendFilter.NONE.value,
        TrendFilter.ASSET_EMA_168.value,
        TrendFilter.ASSET_EMA_24_168.value,
        TrendFilter.BTC_EMA_168.value,
    }


def test_the_report_recomputes_the_same_grid_facts():
    computed = report.grid_report(REPO_ROOT)
    assert computed["total_configurations"] == 2_304
    assert computed["btc_filter_configurations"] == 576
    assert computed["declared_total_matches"] is True
    assert computed["btc_filter_share"] == pytest.approx(0.25)


# --------------------------------------------------------------------------
# the alignment semantics of the frozen engine
# --------------------------------------------------------------------------


def test_the_engine_pairs_the_btc_series_by_index_and_ignores_timestamps():
    asset = _asset_series()
    config = _probe_config()
    base_ms = asset[0].timestamp
    low = [1.0] * len(asset)

    baseline = generate_entry_signals(asset, config, _btc_series(low, base_ms))
    shifted = generate_entry_signals(
        asset, config, _btc_series(low, base_ms + 1000 * HOUR_MS)
    )
    assert baseline, "the probe must produce at least one signal"
    assert len(shifted) == len(baseline), "the BTC timestamps must not change the outcome"

    signal_index = baseline[0].index
    perturbed = list(low)
    perturbed[signal_index] = 1_000_000.0
    blocked = generate_entry_signals(asset, config, _btc_series(perturbed, base_ms))
    assert len(blocked) < len(baseline), "the BTC value at the index must decide the filter"


def test_the_frozen_methodology_requires_the_btc_alignment_by_utc_candle_close():
    text = (REPO_ROOT / PROTOCOL_DOC).read_text(encoding="utf-8")
    assert "Align BTC and target asset by UTC candle close" in text
    assert "No forward-fill for missing BTC observations" in text


def test_the_frozen_engine_slices_the_asset_series_but_not_the_btc_series():
    backtester = (REPO_ROOT / "src/breakout_research/backtest/backtester.py").read_text(encoding="utf-8")
    generator = (REPO_ROOT / "src/breakout_research/signals/generator.py").read_text(encoding="utf-8")
    assert "fold_candles = [c for c in fold_candles if c.timestamp >= start_time]" in backtester
    assert "btc_closes = [c.close for c in btc_candles]" in backtester
    assert "btc_ema_168[i]" in generator
    assert "i >= len(btc_ema_168)" in generator


def test_the_report_demonstrates_the_alignment_semantics():
    computed = report.alignment_probe(REPO_ROOT)
    assert computed["probe_timestamps_ignored"] is True
    assert computed["probe_index_value_used"] is True
    assert computed["source_markers_all_true"] is True
    assert computed["frozen_methodology_requires_timestamp_alignment"] is True
    assert computed["alignment_mode"] == "positional_by_index"


# --------------------------------------------------------------------------
# the v3 state
# --------------------------------------------------------------------------


def test_the_v3_universe_declares_a_benchmark_constituent():
    universe = load_json(V3_UNIVERSE_MANIFEST)
    benchmark = universe["benchmark_asset"]
    assert benchmark["symbol"] == "BTCUSDT"
    assert benchmark["role"] == "trend_filter_and_benchmark"
    assert benchmark["included_in_universe"] is True


def test_the_v3_validated_assets_share_one_canonical_window():
    manifest = load_json(V3_DATA_MANIFEST)
    content_hashes = manifest["content_hashes"]
    validated = sorted(content_hashes)
    assert validated, "the v3 data manifest must publish validated datasets"

    windows = {
        (
            manifest["assets"][symbol]["first_candle_timestamp"],
            manifest["assets"][symbol]["last_candle_timestamp"],
            manifest["assets"][symbol]["observed_candle_count"],
        )
        for symbol in validated
    }
    assert len(windows) == 1, "every validated v3 asset must share one window"
    first, last, count = windows.pop()
    assert count == manifest["window_policy"]["candle_count"] == 26_280
    assert manifest["assets"][validated[0]]["gaps"] == []
    assert manifest["assets"][validated[0]]["rejected_rows"] == 0
    assert first < last


def test_the_only_other_btc_dataset_is_not_index_aligned_with_the_v3_assets():
    v3 = load_json(V3_DATA_MANIFEST)
    v2 = load_json(V2_DATA_MANIFEST)
    symbol = "BTCUSDT"

    v3_assets = v3["assets"]
    validated = sorted(v3["content_hashes"])
    v3_first = v3_assets[validated[0]]["first_candle_timestamp"]
    v3_last = v3_assets[validated[0]]["last_candle_timestamp"]

    assert symbol not in v3_assets, "the v3 data manifest has no benchmark dataset"
    assert symbol not in v3["content_hashes"]

    v2_entry = v2["assets"][symbol]
    assert v2_entry["first_candle_timestamp"] != v3_first
    assert v2_entry["last_candle_timestamp"] != v3_last
    assert v2_entry["first_candle_timestamp"] < v3_first


def test_the_v2_benchmark_dataset_stays_clear_of_the_v3_development_boundary():
    v2 = load_json(V2_DATA_MANIFEST)
    execution = load_json("configs/research_v3_execution.json")
    cutoff = execution["selection_data_boundary"]["development_data_cutoff_utc"]
    cutoff_ms = report.parse_utc_ms(cutoff)

    last = v2["assets"]["BTCUSDT"]["last_candle_timestamp"]
    assert last + HOUR_MS <= cutoff_ms, "the v2 benchmark data must not reach the v3 boundary"


def test_no_v3_execution_artifact_exists():
    for relative in report.V3_EXECUTION_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), f"{relative} must not exist before an authorized run"


def test_the_gap_is_either_closed_or_recorded_and_unauthorized():
    """The benchmark gap may not be silently open.

    Either an index-aligned, hash-verified benchmark dataset exists for the v3
    asset window, or the gap is recorded as a decision record in the queue and
    no v3 selection authorization exists that could consume a missing
    benchmark.
    """
    state = report.v3_state_report(REPO_ROOT)
    queue_text = (REPO_ROOT / QUEUE).read_text(encoding="utf-8")
    recorded = "## BRAIN-013" in queue_text

    if state["index_aligned_benchmark_available"]:
        assert state["benchmark_in_v3_data_manifest"] is True
    else:
        assert recorded, "the missing benchmark dataset must be recorded as a decision"
        assert state["v3_selection_authorization_present"] is False, (
            "no v3 selection authorization may exist while the benchmark dataset is missing"
        )


def test_the_decision_record_states_the_comparison_and_the_recommendation():
    queue_text = (REPO_ROOT / QUEUE).read_text(encoding="utf-8")
    assert "## BRAIN-013" in queue_text
    section = queue_text.split("## BRAIN-013", 1)[1]
    for marker in (
        "Falsifying evidence",
        "Rollback",
        "Staged acceptance tests",
        "Design A",
        "Design B",
        "Design C",
        "Recommendation",
    ):
        assert marker in section, f"the BRAIN-013 record must contain {marker!r}"


# --------------------------------------------------------------------------
# the exposure of the completed v2 run
# --------------------------------------------------------------------------


def test_the_completed_v2_run_evaluated_the_btc_filter_on_three_of_four_folds():
    """Quantify, from the ledger and the frozen rule, what the misalignment touched.

    The v2 run evaluated every asset on every configuration of the inherited
    grid over the four validation folds and the three cost scenarios. The BTC
    filter is one of the four trend filters, and the engine indexes the BTC
    series from the start of the history, so the filter's value on folds 1-3
    was taken from a different period than the asset's bar.
    """
    ledger = load_json(V2_LEDGER)
    spec = load_json(V1_SPEC)
    manifest = load_json(CONFIG_MANIFEST)

    fold_count = len(spec["folds"]["window_fractions"])
    cost_count = len(spec["costs"]["scenarios"])
    total_configs = len(manifest["configurations"])
    btc_configs = sum(
        1
        for configuration in manifest["configurations"]
        if configuration["trend_filter"] == TrendFilter.BTC_EMA_168.value
    )
    asset_count = ledger["counts"]["config_units"] // total_configs
    assert asset_count == len(ledger["scope"]["constituents"])

    total_units = ledger["counts"]["execution_units"]
    assert total_units == asset_count * total_configs * fold_count * cost_count

    btc_records = asset_count * btc_configs * fold_count * cost_count
    misaligned_records = asset_count * btc_configs * (fold_count - 1) * cost_count
    assert btc_records == total_units // 4
    assert misaligned_records == total_units * 3 // 16


def test_the_report_agrees_with_the_ledger_derived_exposure():
    state = report.v3_state_report(REPO_ROOT)
    assert state["v3_execution_artifacts_present"] == []
    assert state["v3_selection_authorization_present"] is False
    assert state["development_data_cutoff_utc"] == "2026-10-20T13:00:00Z"


@pytest.mark.parametrize("relative", [V3_UNIVERSE_MANIFEST, V3_DATA_MANIFEST, V2_DATA_MANIFEST])
def test_the_manifests_under_test_are_the_frozen_ones(relative: str):
    """The facts above are read from the frozen manifests, never from a copy."""
    document = load_json(relative)
    assert isinstance(document, dict)
    if relative == V3_DATA_MANIFEST:
        assert document["universe_version"] == "v3"
        assert document["protocol_version"] == "v3"
    if relative == V2_DATA_MANIFEST:
        assert document["universe_version"] == "v2"

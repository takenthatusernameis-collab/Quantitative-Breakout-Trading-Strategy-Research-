"""Tests for the repaired v4 benchmark identity and alignment rules.

BRAIN-016 records three defects in the v4 execution path that made the
authorized selection run impossible, and the repair that made it executable
without a provider request, without a confirmatory-window read and without a
change to the hashed source set:

1. **the benchmark could not be loaded at all.** The v4 data manifest publishes
   no BTCUSDT entry -- the benchmark is external to the v4 data-manifest
   identity by design -- but the loader resolved the dataset through a
   manifest entry and raised ``KeyError: asset BTCUSDT is not present in the
   data manifest`` before the first asset was evaluated.
2. **the dataset-level alignment check refused every asset.** The v4 asset
   datasets span the 26,280-hour window that ends at the preregistered
   development cutoff; the benchmark dataset ends two hours earlier. The check
   demanded an identical span, although the validation windows are the interior
   0.4 to 0.8 fractions of the span and lie strictly inside the benchmark's
   coverage.
3. **the benchmark was not bound into the identity of a BTC trend-filter
   unit.** The v1 unit-data-hash rule binds the benchmark dataset into the
   experiment id of every ``btc_ema_168`` unit; the v4 data manifest publishes
   no benchmark hash, so the unit identity did not depend on the benchmark.

These tests pin the repaired rules and the tamper controls that keep them
from drifting again.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from breakout_research.config import Candle

from v4_campaign import benchmark as benchmark_rule
from v4_campaign import units as v4_units
from v4_campaign.benchmark import (
    align_window,
    assert_benchmark_covers_evaluation,
    assert_dataset_alignment,
)
from v4_campaign.data import (
    BENCHMARK_CONTENT_HASH,
    BENCHMARK_DATASET_PATH,
    load_benchmark_candles,
    load_development_candles,
    resolve_effective_data_manifest,
)
from v4_campaign.errors import BenchmarkAlignmentError, DataVerificationError
from v4_campaign.runner import build_plan, default_workspace
from v4_campaign.units import (
    btc_filter_configurations,
    fold_bounds,
    unit_data_hash,
    validation_folds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE = REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"
DATA_MANIFEST = REPO_ROOT / "research" / "data_manifest_v4.json"
HOUR_MS = 3_600_000


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _candle(timestamp: int, close: float = 100.0) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


@pytest.fixture(scope="module")
def plan():
    return build_plan(default_workspace(REPO_ROOT))


@pytest.fixture(scope="module")
def benchmark(plan):
    candles, _provenance = load_benchmark_candles(
        REPO_ROOT, plan.data_manifest, plan.boundary_ms
    )
    return candles


def test_the_v4_data_manifest_publishes_no_benchmark_entry(plan):
    """The premise of the defect: the benchmark is external to the manifest."""
    assert "BTCUSDT" not in (plan.data_manifest.get("assets") or {})
    assert "BTCUSDT" not in (plan.data_manifest.get("content_hashes") or {})


def test_the_benchmark_loads_from_its_own_recorded_identity(plan, benchmark):
    """Defect 1: the benchmark loads without a manifest entry, hash-verified."""
    assert len(benchmark) == 26280
    assert int(benchmark[0].timestamp) == 1697886000000
    assert int(benchmark[-1].timestamp) == 1792490400000
    assert BENCHMARK_DATASET_PATH.startswith("research/data/candles_v3/")
    candles, provenance = load_benchmark_candles(
        REPO_ROOT, plan.data_manifest, plan.boundary_ms
    )
    assert provenance["hash_verified"] is True
    assert provenance["content_hash"] == BENCHMARK_CONTENT_HASH
    assert provenance["canonical_content_hash"] == BENCHMARK_CONTENT_HASH
    assert provenance["confirmatory_candles_read"] == 0
    assert len(candles) == 26280


def test_a_tampered_benchmark_is_refused(plan, monkeypatch):
    """Tamper control: a benchmark that does not hash to the record is refused."""
    from v4_campaign import data as v4_data

    monkeypatch.setattr(v4_data, "BENCHMARK_CONTENT_HASH", "0" * 64)
    with pytest.raises(DataVerificationError):
        load_benchmark_candles(REPO_ROOT, plan.data_manifest, plan.boundary_ms)


def test_the_evaluated_windows_lie_inside_the_benchmark_coverage(plan, benchmark):
    """Defect 2: the two-hour overhang falls outside every evaluated window."""
    for asset in plan.assets:
        symbol = str(asset["symbol"])
        candles, _provenance = load_development_candles(
            REPO_ROOT, symbol, plan.data_manifest, plan.boundary_ms
        )
        windows = validation_folds(fold_bounds(candles, plan.folds))
        assert len(windows) == 4
        for start, end, _index, _holdout in windows:
            assert int(benchmark[0].timestamp) <= int(start)
            assert int(end) <= int(benchmark[-1].timestamp) + HOUR_MS
        report = assert_benchmark_covers_evaluation(
            candles, benchmark, windows, symbol
        )
        assert report["benchmark_covers_evaluation"] is True
        assert report["forward_filled"] is False
        assert report["evaluated_candles"] > 0


def test_the_overhang_is_inside_the_holdout_position_fold(plan, benchmark):
    """The overhang is disclosed: it lies in the fold the run never evaluates."""
    asset = plan.assets[0]
    symbol = str(asset["symbol"])
    candles, _provenance = load_development_candles(
        REPO_ROOT, symbol, plan.data_manifest, plan.boundary_ms
    )
    bounds = fold_bounds(candles, plan.folds)
    holdout = [bound for bound in bounds if bound[3]]
    assert len(holdout) == 1
    holdout_start, holdout_end, _index, _is_holdout = holdout[0]
    assert int(benchmark[-1].timestamp) < int(holdout_end)
    assert int(benchmark[-1].timestamp) >= int(holdout_start)
    assert int(candles[-1].timestamp) > int(benchmark[-1].timestamp)


def test_the_coverage_check_refuses_a_benchmark_that_misses_an_evaluated_candle():
    """Tamper control: a hole in the benchmark inside a window is refused."""
    asset = [_candle(index * HOUR_MS) for index in range(100)]
    benchmark = [_candle(index * HOUR_MS) for index in range(100)]
    holed = [candle for candle in benchmark if int(candle.timestamp) != 50 * HOUR_MS]
    with pytest.raises(BenchmarkAlignmentError):
        assert_benchmark_covers_evaluation(asset, holed, [(0, 100 * HOUR_MS)], "TESTUSDT")


def test_the_coverage_check_refuses_a_benchmark_that_ends_before_the_window():
    """Tamper control: a benchmark shorter than the evaluated window is refused."""
    asset = [_candle(index * HOUR_MS) for index in range(100)]
    benchmark = [_candle(index * HOUR_MS) for index in range(10)]
    with pytest.raises(BenchmarkAlignmentError):
        assert_benchmark_covers_evaluation(asset, benchmark, [(0, 100 * HOUR_MS)], "TESTUSDT")


def test_the_coverage_check_refuses_a_missing_benchmark():
    """Tamper control: a missing benchmark is refused before the engine runs."""
    asset = [_candle(index * HOUR_MS) for index in range(10)]
    with pytest.raises(BenchmarkAlignmentError):
        assert_benchmark_covers_evaluation(asset, [], [(0, 10 * HOUR_MS)], "TESTUSDT")


def test_the_per_window_alignment_stays_strict(plan, benchmark):
    """The coverage check does not weaken the per-window identity check."""
    asset = plan.assets[0]
    symbol = str(asset["symbol"])
    candles, _provenance = load_development_candles(
        REPO_ROOT, symbol, plan.data_manifest, plan.boundary_ms
    )
    windows = validation_folds(fold_bounds(candles, plan.folds))
    start, end, _index, _holdout = windows[0]
    # The window starts on a fraction of the span, so the first candle of the
    # window is the first candle at or after it -- the one the tamper removes
    # from the benchmark.
    first_in_window = next(
        int(candle.timestamp)
        for candle in candles
        if int(candle.timestamp) >= int(start)
    )
    shifted = [
        candle for candle in benchmark if int(candle.timestamp) != first_in_window
    ]
    with pytest.raises(BenchmarkAlignmentError):
        align_window(candles, shifted, int(start), int(end), symbol)


def test_the_dataset_level_identity_check_is_still_available(plan, benchmark):
    """The stronger dataset-level check survives, for the case it applies to."""
    with pytest.raises(BenchmarkAlignmentError):
        assert_dataset_alignment(list(benchmark), list(benchmark)[1:], "TESTUSDT")


def test_the_btc_unit_data_hash_binds_the_benchmark(plan):
    """Defect 3: the benchmark is bound into the BTC trend-filter unit id."""
    assert plan.data_hashes.get("BTCUSDT") == BENCHMARK_CONTENT_HASH
    btc_configs = btc_filter_configurations(plan.configs)
    assert len(btc_configs) == 576
    btc_config = next(config for config in plan.configs if config.config_id in set(btc_configs))
    other_config = next(config for config in plan.configs if config.config_id not in set(btc_configs))

    asset_hash = plan.data_hashes[str(plan.assets[0]["symbol"])]
    btc_hash = unit_data_hash(str(plan.assets[0]["symbol"]), btc_config, plan.data_hashes)
    plain_hash = unit_data_hash(str(plan.assets[0]["symbol"]), other_config, plan.data_hashes)
    assert plain_hash == asset_hash
    assert btc_hash != asset_hash
    changed = unit_data_hash(
        str(plan.assets[0]["symbol"]),
        btc_config,
        {**plan.data_hashes, "BTCUSDT": "1" * 64},
    )
    assert changed != btc_hash


def test_the_unit_data_hash_rule_is_the_v1_rule():
    """The rule the plan applies is the unchanged v1 unit-data-hash rule."""
    assert v4_units.unit_data_hash is unit_data_hash
    source = " ".join(Path(v4_units.__file__).read_text(encoding="utf-8").split())
    assert "a BTC trend-filter unit depends on the asset's data and on the benchmark" in source
    assert "every other unit depends on the asset's data only" in source


def test_the_v4_data_manifest_is_unchanged_by_the_repair():
    """The repair changed no data: the manifest still hashes to the bound value."""
    from v4_campaign.data import compute_manifest_hash

    manifest = _load(DATA_MANIFEST)
    excluded = tuple(
        (manifest.get("hashing") or {}).get("manifest_hash_excluded_keys") or ()
    )
    assert compute_manifest_hash(manifest, excluded) == manifest["manifest_hash"]
    freeze = _load(FREEZE)
    assert freeze["data_manifest_hash"] == manifest["manifest_hash"]
    assert freeze["snapshot_identity"]["data_manifest_hash"] == manifest["manifest_hash"]


def test_the_benchmark_rule_states_the_repaired_fail_closed_conditions():
    """The published rule states what the repaired check actually refuses."""
    execution = _load(REPO_ROOT / "configs" / "research_v4_execution.json")
    fail_closed = execution["benchmark_rule"]["fail_closed"]
    assert any("does not cover an evaluated window" in item for item in fail_closed)
    assert any("different timestamp" in item for item in fail_closed)
    assert benchmark_rule.ALIGNMENT_RULE == (
        "Align BTC and target asset by UTC candle close; no forward fill for missing "
        "BTC observations"
    )

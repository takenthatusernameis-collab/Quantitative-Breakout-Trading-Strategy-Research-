"""Tests for the v5 campaign path and its benchmark rule.

BRAIN-013 requires the v5 execution path to live outside the hashed source set
and to implement the benchmark rule of ``docs/research_protocol.md:101``
("Align BTC and target asset by UTC candle close"). The v5 chain adds two
constraints of its own: the benchmark is the **v5-cutoff-bounded** dataset the
v5 data manifest publishes, and the v4 chain's benchmark may not be reused.
These tests prove that

* the v5 path is outside the hashed set: the canonical digest of the hashed set
  is unchanged and the path has a stable canonical digest of its own;
* the asset series and the benchmark series are sliced to the **same fold
  window** before the frozen engine is called, so that the engine's index
  pairing ``closes[i]`` / ``btc_ema_168[i]`` is a UTC-candle-close alignment;
* the path fails **closed** when the benchmark is missing, shorter than the
  evaluated window or not index-aligned, before the engine is called;
* the grid is never reduced: the 576 ``btc_ema_168`` configurations per asset
  are evaluated like every other configuration, and the unit data hash of such
  a unit binds the benchmark dataset;
* the run is refused without the versioned authorization and it creates or
  modifies no v5 execution artifact;
* no candle that closes inside the open v2, v3 or v4 confirmatory window is
  read: the effective development boundary of the freeze is the earlier of the
  v5 confirmatory-window start and the preregistered development cutoff, and
  the loader refuses any dataset that reaches past it;
* the benchmark is the v5 dataset the v5 data manifest publishes, and the v4
  chain's benchmark is refused.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from breakout_research.config import Candle, get_configurations
from breakout_research.data.fetcher import _read_dataset

from v5_campaign import benchmark as benchmark_rule
from v5_campaign import units as v5_units
from v5_campaign.benchmark import (
    ALIGNMENT_REFERENCE,
    ALIGNMENT_RULE,
    BENCHMARK_SYMBOL,
    align_window,
    alignment_report,
    assert_dataset_alignment,
    benchmark_required_for,
    slice_window,
)
from v5_campaign.data import (
    BENCHMARK_CONTENT_HASH,
    BENCHMARK_DATASET_PATH,
    load_benchmark_candles,
    parse_utc_ms,
    resolve_effective_data_manifest,
)
from v5_campaign.errors import (
    BenchmarkAlignmentError,
    ConfirmatoryWindowViolation,
    DataVerificationError,
    ScopeError,
)
from v5_campaign.runner import Workspace, default_workspace, run_selection
from v5_campaign.scope import selection_rule
from v5_campaign.units import (
    btc_filter_configurations,
    fold_bounds,
    unit_data_hash,
    validation_folds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
V1_SPEC = REPO_ROOT / "configs" / "research_v1.json"
V5_SPEC = REPO_ROOT / "configs" / "research_v5.json"
FREEZE = REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
AUTHORIZATION = REPO_ROOT / "configs" / "research_v5_selection_authorization_1.json"

#: The benchmark dataset the v4 chain used. Its candles reach past the v5
#: development cutoff, inside the open v2 confirmatory window.
V4_BENCHMARK_DATASET_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

V5_EXECUTION_PATHS = (
    REPO_ROOT / "research" / "shards_v5",
    REPO_ROOT / "research" / "ledger_v5.json",
    REPO_ROOT / "research" / "results_manifest_v5.json",
    REPO_ROOT / "research" / "results_v5.jsonl",
    REPO_ROOT / "research_state" / "checkpoint_v5.json",
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _output_state() -> dict:
    """The state of the v5 output paths: existence, size and modification time."""
    state = {}
    for path in V5_EXECUTION_PATHS:
        if path.is_dir():
            state[str(path)] = ("dir", sorted(child.name for child in path.iterdir()))
        elif path.exists():
            stat = path.stat()
            state[str(path)] = ("file", stat.st_size, stat.st_mtime_ns)
        else:
            state[str(path)] = ("absent",)
    return state


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
def spec_v1():
    return _load(V1_SPEC)


@pytest.fixture(scope="module")
def effective_manifest():
    manifest, _effective_hash, _provenance = resolve_effective_data_manifest(REPO_ROOT)
    return manifest


@pytest.fixture(scope="module")
def benchmark_candles():
    """The benchmark series the v5 data manifest publishes."""
    path = (REPO_ROOT / BENCHMARK_DATASET_PATH).resolve()
    if not path.exists():
        pytest.skip("the benchmark dataset is not present in this checkout")
    return _read_dataset(path)


def test_v5_path_lives_outside_the_hashed_set():
    from v5_campaign.identity import hashed_set_digest

    assert hashed_set_digest(REPO_ROOT) == (
        "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
    )


def test_v5_path_has_a_stable_canonical_digest():
    from v5_campaign.identity import code_identity_document

    document = code_identity_document(REPO_ROOT)
    assert document["hashed_set_root"] == "src/breakout_research"
    assert document["execution_path_root"] == "src/v5_campaign"
    assert len(document["hashed_set_digest"]) == 64
    assert len(document["execution_path_digest"]) == 64
    assert len(document["run_code_identity"]) == 64
    assert document["execution_path_digest"] == code_identity_document(REPO_ROOT)[
        "execution_path_digest"
    ]


def test_alignment_rule_is_the_frozen_methodology():
    assert ALIGNMENT_REFERENCE == "docs/research_protocol.md:101"
    assert "UTC candle close" in ALIGNMENT_RULE
    assert "no forward fill" in ALIGNMENT_RULE


def test_benchmark_rule_is_recorded_by_the_effective_execution_protocol():
    from v5_campaign.scope import resolve_effective_execution_protocol

    effective = resolve_effective_execution_protocol(REPO_ROOT)
    benchmark = effective["benchmark_rule"]
    assert benchmark["no_forward_fill"] is True
    assert "sliced to the same fold window" in benchmark["alignment"]
    assert benchmark["grid_rule"].startswith("the 576 btc_ema_168 configurations")
    fail_closed = benchmark["fail_closed"]
    assert any("missing" in item for item in fail_closed)
    assert any("does not cover an evaluated window" in item for item in fail_closed)
    assert any("different timestamp" in item for item in fail_closed)


def test_aligned_window_carries_identical_timestamps(benchmark_candles):
    asset_candles = list(benchmark_candles)
    start = int(asset_candles[0].timestamp)
    end = int(asset_candles[-1].timestamp)
    asset_slice, benchmark_slice, report = align_window(
        asset_candles, benchmark_candles, start, end, "TESTUSDT"
    )
    assert [int(c.timestamp) for c in asset_slice] == [
        int(c.timestamp) for c in benchmark_slice
    ]
    assert report["index_aligned"] is True
    assert report["benchmark_window_sliced"] is True
    assert report["forward_filled"] is False
    assert report["alignment_rule"] == ALIGNMENT_RULE
    assert report["alignment_reference"] == ALIGNMENT_REFERENCE


def test_aligned_window_is_the_fold_window_and_not_the_whole_history(
    benchmark_candles, spec_v1
):
    asset_candles = list(benchmark_candles)
    bounds = fold_bounds(asset_candles, spec_v1["folds"])
    windows = validation_folds(bounds)
    assert len(windows) == 4
    for start, end, _index, _holdout in windows:
        asset_slice, benchmark_slice, _report = align_window(
            asset_candles, benchmark_candles, start, end, "TESTUSDT"
        )
        assert len(asset_slice) == len(benchmark_slice)
        assert len(asset_slice) < len(asset_candles)
        assert start <= int(asset_slice[0].timestamp) < start + 3_600_000
        assert int(asset_slice[-1].timestamp) < end
        assert int(asset_slice[-1].timestamp) >= end - 2 * 3_600_000


def test_missing_benchmark_fails_closed():
    with pytest.raises(BenchmarkAlignmentError):
        align_window([_candle(0), _candle(3_600_000)], [], 0, 7_200_000, "TESTUSDT")


def test_short_benchmark_fails_closed():
    asset = [_candle(index * 3_600_000) for index in range(10)]
    benchmark = [_candle(index * 3_600_000) for index in range(5)]
    with pytest.raises(BenchmarkAlignmentError):
        align_window(asset, benchmark, 0, 36_000_000, "TESTUSDT")


def test_misaligned_benchmark_fails_closed():
    asset = [_candle(index * 3_600_000) for index in range(10)]
    benchmark = [_candle(index * 3_600_000 + 60_000) for index in range(10)]
    with pytest.raises(BenchmarkAlignmentError):
        align_window(asset, benchmark, 0, 36_000_000, "TESTUSDT")


def test_dataset_alignment_refuses_a_different_span():
    asset = [_candle(index * 3_600_000) for index in range(10)]
    shorter = [_candle(index * 3_600_000) for index in range(9)]
    with pytest.raises(BenchmarkAlignmentError):
        assert_dataset_alignment(asset, shorter, "TESTUSDT")
    shifted = [_candle(index * 3_600_000 + 3_600_000) for index in range(10)]
    with pytest.raises(BenchmarkAlignmentError):
        assert_dataset_alignment(asset, shifted, "TESTUSDT")


def test_alignment_report_records_the_failure_instead_of_raising():
    asset = [_candle(index * 3_600_000) for index in range(4)]
    report = alignment_report(asset, [], "TESTUSDT", 0, 14_400_000)
    assert report["index_aligned"] is False
    assert report["error"]


def test_the_grid_is_never_reduced():
    config_manifest = _load(REPO_ROOT / "research" / "config_manifest.json")
    configs = get_configurations(config_manifest)
    assert len(configs) == 2304
    btc_configs = btc_filter_configurations(configs)
    assert len(btc_configs) == 576
    assert all(benchmark_required_for(config) for config in configs
               if config.config_id in set(btc_configs))
    assert not any(
        benchmark_required_for(config)
        for config in configs
        if config.config_id not in set(btc_configs)
    )


def test_unit_data_hash_binds_the_benchmark_for_btc_units_only(spec_v1):
    config_manifest = _load(REPO_ROOT / "research" / "config_manifest.json")
    configs = get_configurations(config_manifest)
    hashes = {"TESTUSDT": "a" * 64, "BTCUSDT": "b" * 64}
    btc_config = next(config for config in configs if benchmark_required_for(config))
    other_config = next(config for config in configs if not benchmark_required_for(config))

    assert unit_data_hash("TESTUSDT", other_config, hashes) == "a" * 64

    btc_hash = unit_data_hash("TESTUSDT", btc_config, hashes)
    assert btc_hash != "a" * 64
    changed = unit_data_hash(
        "TESTUSDT", btc_config, {"TESTUSDT": "a" * 64, "BTCUSDT": "c" * 64}
    )
    assert changed != btc_hash, "the BTC unit identity must depend on the benchmark dataset"
    assert unit_data_hash("TESTUSDT", btc_config, {"TESTUSDT": "a" * 64}) == "a" * 64


def test_selection_rule_is_the_unchanged_v1_rule(spec_v1):
    spec_v5 = _load(V5_SPEC)
    block, digest = selection_rule(spec_v1, spec_v5)
    assert block == spec_v1["selection"]
    assert len(digest) == 64


def test_run_is_refused_without_the_authorization():
    """A run without the authorization is refused before it starts.

    The refusal is exercised against a workspace whose authorization file is
    absent: the run must be refused there, and a refused run must not create
    **or modify** a v5 execution artifact.
    """
    workspace = dataclasses.replace(
        default_workspace(REPO_ROOT),
        authorization=(
            REPO_ROOT / "configs" / "research_v5_selection_authorization_absent.json"
        ),
    )
    before = _output_state()
    with pytest.raises(ScopeError):
        run_selection(workspace)
    after = _output_state()
    assert after == before, "a refused run must not create or modify a v5 execution artifact"


def test_the_engine_never_receives_the_unsliced_benchmark_series():
    source = inspect.getsource(run_selection)
    assert "btc_candles=benchmark_slice" in source
    assert "btc_candles=benchmark_candles" not in source
    assert "btc_candles=candles" not in source


def test_no_candle_inside_the_confirmatory_window_is_read(
    effective_manifest, benchmark_candles
):
    """The benchmark loader refuses a dataset that reaches past the boundary."""
    boundary = int(benchmark_candles[-1].timestamp)
    with pytest.raises(ConfirmatoryWindowViolation):
        load_benchmark_candles(REPO_ROOT, effective_manifest, boundary)


def test_the_effective_development_boundary_is_the_development_cutoff(benchmark_candles):
    """The v5 development boundary is the cutoff, not the window start.

    The v5 confirmatory window opens after the preregistered development
    cutoff, so the binding boundary for every v5 development read is the
    earlier of the two: the preregistered cutoff.
    """
    freeze = _load(FREEZE)
    spec_v5 = _load(V5_SPEC)
    cutoff = spec_v5["holdout"]["development_cutoff_utc"]
    boundary = freeze["data_boundary"]["effective_data_boundary_utc"]
    assert freeze["data_boundary"]["development_cutoff_utc"] == cutoff
    assert boundary == min(freeze["confirmatory_window"]["opens_utc"], cutoff)
    boundary_ms = parse_utc_ms(boundary)
    assert boundary <= cutoff
    # The whole benchmark dataset is development data: its last candle closes
    # exactly at the effective boundary.
    assert int(benchmark_candles[-1].timestamp) + 3_600_000 == boundary_ms


def test_every_validated_dataset_closes_at_the_boundary(effective_manifest):
    freeze = _load(FREEZE)
    boundary_ms = parse_utc_ms(freeze["data_boundary"]["effective_data_boundary_utc"])
    for pair, entry in (effective_manifest.get("assets") or {}).items():
        if entry.get("validated") is not True:
            continue
        assert int(entry["last_candle_timestamp"]) + 3_600_000 == boundary_ms, pair


def test_the_benchmark_is_the_dataset_the_v5_manifest_publishes(effective_manifest):
    published = effective_manifest["benchmark"]
    assert published["dataset_path"] == BENCHMARK_DATASET_PATH
    assert published["content_hash"] == BENCHMARK_CONTENT_HASH
    assert published["symbol"] == BENCHMARK_SYMBOL
    assert "BTCUSDT" not in (effective_manifest.get("assets") or {})


def test_the_v4_benchmark_dataset_is_refused(effective_manifest, tmp_path):
    """The v4 chain's benchmark may not be reused by the v5 chain."""
    manifest = json.loads(json.dumps(effective_manifest))
    manifest["benchmark"]["dataset_path"] = V4_BENCHMARK_DATASET_PATH
    with pytest.raises(DataVerificationError):
        load_benchmark_candles(REPO_ROOT, manifest, 2 ** 62)


def test_workspace_paths_are_the_v5_paths():
    workspace: Workspace = default_workspace(REPO_ROOT)
    assert workspace.shards_dir.name == "shards_v5"
    assert workspace.ledger.name == "ledger_v5.json"
    assert workspace.results_manifest.name == "results_manifest_v5.json"
    assert workspace.results_stream.name == "results_v5.jsonl"
    assert workspace.checkpoint.name == "checkpoint_v5.json"
    assert workspace.authorization.name == "research_v5_selection_authorization_1.json"
    assert workspace.authorization == AUTHORIZATION


def test_slice_window_uses_the_engine_predicate():
    candles = [_candle(index * 3_600_000) for index in range(5)]
    sliced = slice_window(candles, 3_600_000, 10_800_000)
    assert [int(candle.timestamp) for candle in sliced] == [3_600_000, 7_200_000]

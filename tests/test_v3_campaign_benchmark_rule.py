"""Tests for the v3 campaign path and its benchmark rule.

BRAIN-013 requires the v3 execution path to live outside the hashed source set
and to implement the benchmark rule of ``docs/research_protocol.md:101``
("Align BTC and target asset by UTC candle close"). These tests prove that

* the v3 path is outside the hashed set: ``compute_code_hash()`` is unchanged
  and the path has a stable canonical digest of its own;
* the asset series and the benchmark series are sliced to the **same fold
  window** before the frozen engine is called, so that the engine's index
  pairing ``closes[i]`` / ``btc_ema_168[i]`` is a UTC-candle-close alignment;
* the path fails **closed** when the benchmark is missing, shorter than the
  evaluated window or not index-aligned, before the engine is called;
* the grid is never reduced: the 576 ``btc_ema_168`` configurations per asset
  are evaluated like every other configuration, and the unit data hash of such
  a unit binds the benchmark dataset;
* the run is refused without the versioned authorization -- the refusal is
  exercised against a workspace whose authorization file is absent -- and it
  creates or modifies no v3 execution artifact;
* no confirmatory-window candle is read by the data loader.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from breakout_research.config import Candle, compute_code_hash, get_configurations
from breakout_research.data.fetcher import _read_dataset

from v3_campaign import benchmark as benchmark_rule
from v3_campaign import units as v3_units
from v3_campaign.benchmark import (
    ALIGNMENT_REFERENCE,
    ALIGNMENT_RULE,
    BENCHMARK_SYMBOL,
    align_window,
    alignment_report,
    assert_dataset_alignment,
    benchmark_required_for,
    slice_window,
)
from v3_campaign.data import (
    load_development_candles,
    parse_utc_ms,
    resolve_effective_data_manifest,
)
from v3_campaign.errors import (
    BenchmarkAlignmentError,
    ConfirmatoryWindowViolation,
    ScopeError,
)
from v3_campaign.runner import Workspace, default_workspace, run_selection
from v3_campaign.scope import selection_rule
from v3_campaign.units import btc_filter_configurations, fold_bounds, unit_data_hash, validation_folds

REPO_ROOT = Path(__file__).resolve().parent.parent
V1_SPEC = REPO_ROOT / "configs" / "research_v1.json"
AUTHORIZATION = REPO_ROOT / "configs" / "research_v3_selection_authorization_1.json"

#: the code hash the v1 and v2 authorizations are bound to
AUTHORIZED_CODE_HASH = "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"

V3_EXECUTION_PATHS = (
    REPO_ROOT / "research" / "shards_v3",
    REPO_ROOT / "research" / "ledger_v3.json",
    REPO_ROOT / "research" / "results_manifest_v3.json",
    REPO_ROOT / "research" / "results_v3.jsonl",
    REPO_ROOT / "research_state" / "checkpoint_v3.json",
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _output_state() -> dict:
    """The state of the v3 output paths: existence, size and modification time."""
    state = {}
    for path in V3_EXECUTION_PATHS:
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
def benchmark_candles(effective_manifest):
    entry = effective_manifest["assets"][BENCHMARK_SYMBOL]
    path = (REPO_ROOT / entry["dataset_path"]).resolve()
    if not path.exists():
        pytest.skip("the benchmark dataset is not present in this checkout")
    return _read_dataset(path)


def test_v3_path_lives_outside_the_hashed_set():
    assert compute_code_hash() == AUTHORIZED_CODE_HASH


def test_v3_path_has_a_stable_canonical_digest():
    from v3_campaign.identity import code_identity_document

    document = code_identity_document(REPO_ROOT)
    assert document["hashed_set_root"] == "src/breakout_research"
    assert document["execution_path_root"] == "src/v3_campaign"
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


def test_benchmark_rule_is_recorded_by_the_amendment_cascade():
    freeze_amendment = _load(
        REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
    )
    execution_amendment = _load(
        REPO_ROOT / "configs" / "research_v3_execution_amendment_1.json"
    )
    assert "sliced to the same fold window" in freeze_amendment["alignment_rule"]["rule"]
    fail_closed = freeze_amendment["alignment_rule"]["fail_closed"]
    assert "missing" in fail_closed
    assert "shorter than the evaluated window" in fail_closed
    assert "not index-aligned" in fail_closed
    assert execution_amendment["benchmark_rule"]["no_forward_fill"] is True
    assert "sliced to the same fold window" in execution_amendment["benchmark_rule"]["alignment"]
    assert execution_amendment["benchmark_rule"]["grid_rule"].startswith(
        "the 576 btc_ema_168 configurations"
    )


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


def test_aligned_window_is_the_fold_window_and_not_the_whole_history(benchmark_candles, spec_v1):
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
        # The fold boundary is a computed instant; the window holds every candle
        # that closes inside it, exactly as the frozen engine's predicate does.
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

    # A configuration that does not use the benchmark depends on the asset data
    # only.
    assert unit_data_hash("TESTUSDT", other_config, hashes) == "a" * 64

    # A BTC trend-filter configuration depends on the asset data *and* on the
    # benchmark dataset, so its data identity changes with the benchmark.
    btc_hash = unit_data_hash("TESTUSDT", btc_config, hashes)
    assert btc_hash != "a" * 64
    changed = unit_data_hash(
        "TESTUSDT", btc_config, {"TESTUSDT": "a" * 64, "BTCUSDT": "c" * 64}
    )
    assert changed != btc_hash, "the BTC unit identity must depend on the benchmark dataset"
    assert unit_data_hash("TESTUSDT", btc_config, {"TESTUSDT": "a" * 64}) == "a" * 64


def test_selection_rule_is_the_unchanged_v1_rule(spec_v1):
    spec_v3 = _load(REPO_ROOT / "configs" / "research_v3.json")
    block, digest = selection_rule(spec_v1, spec_v3)
    assert block == spec_v1["selection"]
    assert len(digest) == 64


def test_run_is_refused_without_the_authorization():
    """A run without the authorization is refused before it starts.

    The versioned v3 selection authorization exists since the session that
    delivered it, so the refusal is exercised against a workspace whose
    authorization file is absent: the run must be refused there, and a refused
    run must not create **or modify** a v3 execution artifact.

    The rule "a refused run must not create a v3 execution artifact" was
    replaced, not deleted: while the authorized run had not been performed, the
    v3 output paths did not exist, so their absence was the proof. Once the
    authorized run has been performed they exist, and the proof is that a
    refused run leaves them exactly as they were -- which is the stronger
    statement and holds in both states.
    """
    workspace = dataclasses.replace(
        default_workspace(REPO_ROOT),
        authorization=REPO_ROOT / "configs" / "research_v3_selection_authorization_absent.json",
    )
    before = _output_state()
    with pytest.raises(ScopeError):
        run_selection(workspace)
    after = _output_state()
    assert after == before, "a refused run must not create or modify a v3 execution artifact"


def test_the_engine_never_receives_the_unsliced_benchmark_series():
    source = inspect.getsource(run_selection)
    assert "btc_candles=benchmark_slice" in source
    assert "btc_candles=benchmark_candles" not in source
    assert "btc_candles=candles" not in source


def test_no_confirmatory_window_candle_is_read(effective_manifest, benchmark_candles):
    entry = effective_manifest["assets"][BENCHMARK_SYMBOL]
    # The development boundary lies before the last candle of the dataset, so
    # the loader must refuse the dataset instead of reading it partially.
    boundary = int(benchmark_candles[-1].timestamp)
    with pytest.raises(ConfirmatoryWindowViolation):
        load_development_candles(
            REPO_ROOT, BENCHMARK_SYMBOL, effective_manifest, boundary
        )


def test_development_boundary_of_the_frozen_scope(benchmark_candles):
    freeze = _load(REPO_ROOT / "configs" / "research_v3_candidate_freeze.json")
    boundary = freeze["data_boundary"]["confirmatory_window_start_utc"]
    boundary_ms = parse_utc_ms(boundary)
    assert boundary == "2026-10-20T13:00:00Z"
    # The whole benchmark dataset is development data: every candle closes
    # before the confirmatory window opens.
    assert int(benchmark_candles[-1].timestamp) + 3_600_000 <= boundary_ms

    freeze_amendment = _load(
        REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
    )
    assert freeze_amendment["data_boundary"]["confirmatory_window_start_utc"] == boundary
    assert freeze_amendment["data_boundary"]["window_moved_by_this_amendment"] is False

    # The execution protocol the amendment amends keeps the same boundary.
    execution_protocol = _load(REPO_ROOT / "configs" / "research_v3_execution.json")
    assert (
        execution_protocol["candidate_freeze_and_confirmatory_window"][
            "confirmatory_window_opens_utc"
        ]
        == boundary
    )


def test_workspace_paths_are_the_v3_paths():
    workspace: Workspace = default_workspace(REPO_ROOT)
    assert workspace.shards_dir.name == "shards_v3"
    assert workspace.ledger.name == "ledger_v3.json"
    assert workspace.results_manifest.name == "results_manifest_v3.json"
    assert workspace.results_stream.name == "results_v3.jsonl"
    assert workspace.checkpoint.name == "checkpoint_v3.json"
    assert workspace.authorization.name == "research_v3_selection_authorization_1.json"
    assert workspace.authorization == AUTHORIZATION


def test_slice_window_uses_the_engine_predicate():
    candles = [_candle(index * 3_600_000) for index in range(5)]
    sliced = slice_window(candles, 3_600_000, 10_800_000)
    assert [int(candle.timestamp) for candle in sliced] == [3_600_000, 7_200_000]

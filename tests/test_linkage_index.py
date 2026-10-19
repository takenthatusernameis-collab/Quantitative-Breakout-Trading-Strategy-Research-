"""BRAIN-007 acceptance tests: linkage index, counter semantics, terminal state.

Covers staged acceptance tests 2-5 from the BRAIN-007 structured design decision
(research_state/brainstorming_queue.md, "BRAIN-007 — Structured design decision"):
  2. Linkage index classifies an identical re-run as LINKED_PRIOR_EVIDENCE (0 new units).
  3. Holdout units never increment the validation counter.
  4. Exhausted universe yields AWAITING_NEW_CANDIDATES/BLOCKED_EXTERNAL and does not
     append to completed_cycle_ids or advance next_cohort_index.
  5. Forged completed_records/last_verified_record is detected and reconstructed
     from the shard manifest.
"""
import json
import tempfile
from pathlib import Path

import pytest

from breakout_research.linkage_index import LinkageIndex
from breakout_research.backtest.checkpoint import (
    reconstruct_counters_from_shards,
    detect_forged_counters,
)
from breakout_research.continuous_universe_coordinator import (
    ContinuousCycleCoordinator,
)
from breakout_research.continuous_universe import COHORT_SIZE, ContinuousState


def test_linkage_index_classifies_identical_rerun_as_linked():
    """Acceptance test 2: identical re-run classifies as LINKED_PRIOR_EVIDENCE, 0 new units."""
    index = LinkageIndex(
        code_hash="code-hash-0",
        spec_hash="spec-hash-0",
        data_manifest_hash="data-hash-0",
        universe_hash="universe-hash-0",
    )
    # Cycle 0 reproduces the v1 validation sweep exactly: every unit is already
    # present in the prior verified cycle's linked set.
    cycle_zero_unit_ids = [f"unit_{i}" for i in range(497664)]
    prior_linked_units = set(cycle_zero_unit_ids)

    linked, new = index.count_linked_vs_new(cycle_zero_unit_ids, prior_linked_units)
    assert linked == 497664
    assert new == 0

    for uid in cycle_zero_unit_ids[:100]:
        assert index.classify(uid, prior_linked_units) == "LINKED_PRIOR_EVIDENCE"


def test_linkage_index_classifies_new_units_as_new():
    """Linkage index classifies units absent from the prior linked set as NEW."""
    index = LinkageIndex(
        code_hash="code-hash-0",
        spec_hash="spec-hash-0",
        data_manifest_hash="data-hash-0",
        universe_hash="universe-hash-0",
    )
    unit_ids = ["unit_1", "unit_2", "unit_3"]
    prior_linked_units = {"unit_1"}

    linked, new = index.count_linked_vs_new(unit_ids, prior_linked_units)
    assert linked == 1
    assert new == 2
    assert index.classify("unit_1", prior_linked_units) == "LINKED_PRIOR_EVIDENCE"
    assert index.classify("unit_2", prior_linked_units) == "NEW"


def test_holdout_units_never_increment_validation_counter():
    """Acceptance test 3: holdout units never increment the validation counter."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        shard_root = str(tdp / "shards")
        campaign_id = "test-campaign"
        campaign_dir = Path(shard_root) / campaign_id
        campaign_dir.mkdir(parents=True)

        # 3 validation units + 2 holdout units
        shard_path = campaign_dir / "shard_000000.jsonl"
        with shard_path.open("w") as f:
            for i in range(3):
                f.write(json.dumps({
                    "experiment_id": f"val-{i}",
                    "is_holdout": False,
                    "asset": "BTCUSDT",
                    "config_id": f"cfg_{i}",
                    "fold_index": i % 4,
                    "start_time": 1000 + i,
                    "end_time": 2000 + i,
                    "cost_multiplier": 1.0,
                }, sort_keys=True) + "\n")
            for i in range(2):
                f.write(json.dumps({
                    "experiment_id": f"holdout-{i}",
                    "is_holdout": True,
                    "asset": "BTCUSDT",
                    "config_id": f"cfg_{i}",
                    "fold_index": 4,
                    "start_time": 1000 + i,
                    "end_time": 2000 + i,
                    "cost_multiplier": 1.0,
                }, sort_keys=True) + "\n")

        counters = reconstruct_counters_from_shards(shard_root, campaign_id)
        assert counters["completed_records"] == 3
        assert counters["holdout_exposed_count"] == 2
        assert counters["last_verified_record"] == 3
        assert counters["total_records"] == 5


def test_detect_forged_counters():
    """Acceptance test 5: forged completed_records/last_verified_record detected and reconstructed."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        shard_root = str(tdp / "shards")
        campaign_id = "test-campaign"
        campaign_dir = Path(shard_root) / campaign_id
        campaign_dir.mkdir(parents=True)

        shard_path = campaign_dir / "shard_000000.jsonl"
        with shard_path.open("w") as f:
            for i in range(3):
                f.write(json.dumps({
                    "experiment_id": f"val-{i}",
                    "is_holdout": False,
                    "asset": "BTCUSDT",
                    "config_id": f"cfg_{i}",
                    "fold_index": i % 4,
                    "start_time": 1000 + i,
                    "end_time": 2000 + i,
                    "cost_multiplier": 1.0,
                }, sort_keys=True) + "\n")

        reconstructed = reconstruct_counters_from_shards(shard_root, campaign_id)
        assert reconstructed["completed_records"] == 3

        # Forged checkpoint: wildly wrong counters
        forged_checkpoint = {
            "completed_records": 999999,
            "last_verified_record": 0,
        }
        reasons = detect_forged_counters(forged_checkpoint, reconstructed)
        assert len(reasons) == 2
        assert any("completed_records" in r for r in reasons)
        assert any("last_verified_record" in r for r in reasons)

        # Valid checkpoint matching reconstructed values
        valid_checkpoint = {
            "completed_records": 3,
            "last_verified_record": 3,
        }
        assert detect_forged_counters(valid_checkpoint, reconstructed) == []


def test_exhausted_universe_terminal_state(monkeypatch, tmp_path):
    """Acceptance test 4: exhausted universe yields BLOCKED_EXTERNAL, does not
    append to completed_cycle_ids or advance next_cohort_index."""
    from breakout_research import continuous_universe_coordinator as coc

    state = ContinuousState(next_cohort_index=1)
    state.completed_cycle_ids = ["existing-cycle-id"]

    universe = {
        "eligible_assets": [
            {"symbol": f"ASSET{i}USDT", "binance_spot_verified": True}
            for i in range(18)
        ],
    }

    monkeypatch.setattr(coc, "load_universe_manifest", lambda path: universe)
    monkeypatch.setattr(coc, "load_continuous_state", lambda: state)

    saved = {}
    def mock_save(s, path=coc.CONTINUOUS_STATE_PATH):
        saved["state"] = s
    monkeypatch.setattr(coc, "save_continuous_state", mock_save)

    coordinator = ContinuousCycleCoordinator()
    monkeypatch.setattr(coordinator, "_make_universe_snapshot",
                        lambda u: ("snap-123", u))

    campaign_called = []
    def mock_run_campaign(**kwargs):
        campaign_called.append(kwargs)
        return {"status": "CAMPAIGN_PARTIAL", "total_experiments": 0}
    monkeypatch.setattr(coc, "run_campaign", mock_run_campaign)

    report = coordinator.run_cycle()

    # Terminal state, not COMPLETE or DUPLICATE_OR_NO_NEW_CANDIDATES
    assert report["state"] == "BLOCKED_EXTERNAL"
    assert report["reason"] == "EXHAUSTED_UNIVERSE_NO_NEW_CANDIDATES"
    assert report["eligible_count"] == 18
    assert report["cohort_assets"] == []
    assert report["provider_evidence"]["status"] == 451
    assert report["provider_evidence"]["reachable"] is False

    # next_cohort_index NOT advanced
    assert state.next_cohort_index == 1
    assert saved["state"].next_cohort_index == 1

    # completed_cycle_ids NOT appended
    assert state.completed_cycle_ids == ["existing-cycle-id"]
    assert saved["state"].completed_cycle_ids == ["existing-cycle-id"]

    # run_campaign NOT called (no execution for exhausted universe)
    assert len(campaign_called) == 0

    # 18 eligible assets < COHORT_SIZE 20
    assert 18 < COHORT_SIZE

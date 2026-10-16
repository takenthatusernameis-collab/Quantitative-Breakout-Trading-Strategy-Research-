"""Tests for the BRAIN-003 frozen candidate manifest (holdout isolation).

All fixtures are synthetic software fixtures and are never presented as
market history or economic evidence.
"""
import copy
import json

import pytest

from breakout_research.candidate_freeze import (
    CANDIDATE_MANIFEST_PATH,
    compute_manifest_hash,
    load_candidate_manifest,
    save_candidate_manifest,
    candidate_config_ids,
)


FROZEN_MANIFEST = {
    "frozen": True,
    "freeze_commit": "test-commit",
    "candidates": {
        "BTCUSDT": {"config_id": "cfg_0001", "parameters": {"entry_lookback": 24}},
        "ETHUSDT": {"config_id": "cfg_0002", "parameters": {"entry_lookback": 48}},
    },
}


def _manifest_path(tmp_path):
    path = tmp_path / "research/candidate_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_compute_manifest_hash_excludes_itself_and_is_deterministic():
    first = compute_manifest_hash(FROZEN_MANIFEST)
    second = compute_manifest_hash(dict(FROZEN_MANIFEST))
    assert first == second
    with_hash = dict(FROZEN_MANIFEST)
    with_hash["manifest_hash"] = "anything"
    assert compute_manifest_hash(with_hash) == first


def test_save_and_load_roundtrip_preserves_hash(tmp_path):
    path = _manifest_path(tmp_path)
    save_candidate_manifest(dict(FROZEN_MANIFEST), str(path))
    loaded = load_candidate_manifest(str(path))
    assert loaded["frozen"] is True
    assert loaded["manifest_hash"] == compute_manifest_hash(FROZEN_MANIFEST)
    assert loaded["candidates"]["BTCUSDT"]["config_id"] == "cfg_0001"
    assert loaded["candidates"]["ETHUSDT"]["config_id"] == "cfg_0002"


def test_load_rejects_unfrozen_manifest(tmp_path):
    unfrozen = copy.deepcopy(FROZEN_MANIFEST)
    unfrozen["frozen"] = False
    save_candidate_manifest(unfrozen, str(_manifest_path(tmp_path)))
    with pytest.raises(ValueError, match="not frozen"):
        load_candidate_manifest(str(_manifest_path(tmp_path)))


def test_load_rejects_tampered_manifest_hash(tmp_path):
    path = _manifest_path(tmp_path)
    save_candidate_manifest(dict(FROZEN_MANIFEST), str(path))
    tampered = copy.deepcopy(FROZEN_MANIFEST)
    tampered["candidates"]["BTCUSDT"]["config_id"] = "cfg_9999"
    # Re-serialize without recomputing the manifest hash -> tampered.
    path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_candidate_manifest(str(path))


def test_load_rejects_multiple_candidates_for_one_asset(tmp_path):
    bad = copy.deepcopy(FROZEN_MANIFEST)
    bad["candidates"]["BTCUSDT"] = [
        {"config_id": "cfg_0001"}, {"config_id": "cfg_0002"},
    ]
    save_candidate_manifest(bad, str(_manifest_path(tmp_path)))
    with pytest.raises(ValueError, match="invalid candidate"):
        load_candidate_manifest(str(_manifest_path(tmp_path)))


def test_load_rejects_candidate_without_config_id(tmp_path):
    bad = copy.deepcopy(FROZEN_MANIFEST)
    bad["candidates"]["BTCUSDT"] = {"parameters": {"entry_lookback": 24}}
    save_candidate_manifest(bad, str(_manifest_path(tmp_path)))
    with pytest.raises(ValueError, match="invalid candidate"):
        load_candidate_manifest(str(_manifest_path(tmp_path)))


def test_candidate_config_ids_returns_exactly_one_id_per_asset():
    ids = candidate_config_ids(FROZEN_MANIFEST)
    assert ids == {"BTCUSDT": {"cfg_0001"}, "ETHUSDT": {"cfg_0002"}}


def test_default_branch_manifest_path_constant():
    assert CANDIDATE_MANIFEST_PATH == "research/candidate_manifest.json"

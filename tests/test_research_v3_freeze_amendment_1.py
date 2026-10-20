"""Tests for the v3 candidate-freeze amendment 1.

``configs/research_v3_candidate_freeze_amendment_1.json`` is the versioned
correction of the v3 candidate freeze: the frozen artifact is not edited, the
validated candidate set is recorded by reference instead. These tests prove
that

* the amendment is deterministic and self-hashing;
* its validated set and its excluded set are exactly the ones the frozen
  manifests record, with the frozen exclusion vocabulary;
* the shortfall is recorded and no substitute is admitted;
* the amendment binds the current manifests by digest and authorizes nothing.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
FREEZE = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
UNIVERSE = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA = REPO_ROOT / "research" / "data_manifest_v3.json"

VALIDATED_PAIRS = (
    "AAVEUSDT",
    "ICPUSDT",
    "PEPEUSDT",
    "QNTUSDT",
    "SHIBUSDT",
    "WLDUSDT",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v3_candidate_freeze_amendment_1",
    REPO_ROOT / "scripts" / "verify_v3_candidate_freeze_amendment_1.py",
)
builder = _load_module(
    "build_v3_candidate_freeze_amendment_1",
    REPO_ROOT / "scripts" / "build_v3_candidate_freeze_amendment_1.py",
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_amendment_is_self_hashing():
    amendment = _load(AMENDMENT)
    excluded = tuple(amendment["hashing"]["manifest_hash_excluded_keys"])
    assert amendment["manifest_hash"] == builder.compute_manifest_hash(amendment, excluded)


def test_the_amendment_is_deterministic():
    rebuilt = builder.build(REPO_ROOT)
    assert json.dumps(rebuilt, sort_keys=True) == json.dumps(_load(AMENDMENT), sort_keys=True)


def test_the_validated_set_is_exactly_the_manifest_validated_set():
    amendment = _load(AMENDMENT)
    universe = _load(UNIVERSE)
    members = [member["binance_pair"] for member in amendment["validated_candidate_set"]["members"]]
    assert sorted(members) == sorted(VALIDATED_PAIRS)
    assert amendment["validated_candidate_set"]["count"] == 6
    manifest_validated = sorted(
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        for asset in universe["eligible_assets"]
        if asset.get("validated")
    )
    assert sorted(members) == manifest_validated


def test_the_excluded_set_carries_the_frozen_reasons():
    amendment = _load(AMENDMENT)
    universe = _load(UNIVERSE)
    members = amendment["excluded_candidates"]["members"]
    assert amendment["excluded_candidates"]["count"] == 14
    assert len(members) == 14
    for member in members:
        assert member["exclusion_reason"] in builder.ALLOWED_VALIDATION_EXCLUSION_REASONS
    manifest_excluded = {
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT": asset.get("exclusion_reason")
        for asset in universe["eligible_assets"]
        if not asset.get("validated")
    }
    assert {member["binance_pair"]: member["exclusion_reason"] for member in members} == manifest_excluded


def test_the_shortfall_is_recorded_and_no_substitute_is_admitted():
    amendment = _load(AMENDMENT)
    shortfall = amendment["shortfall"]
    assert shortfall["requested_top_n"] == 20
    assert shortfall["derived_batch_size"] == 20
    assert shortfall["validated_count"] == 6
    assert shortfall["shortfall"] == 14
    assert shortfall["no_backfill"] is True


def test_the_amendment_binds_the_current_manifests():
    amendment = _load(AMENDMENT)
    evidence = amendment["validation_evidence"]
    assert evidence["universe_manifest"]["manifest_hash"] == _load(UNIVERSE)["manifest_hash"]
    assert evidence["data_manifest"]["manifest_hash"] == _load(DATA)["manifest_hash"]
    assert evidence["universe_manifest"]["file_sha256"] == builder.sha256_file(UNIVERSE)
    assert evidence["data_manifest"]["file_sha256"] == builder.sha256_file(DATA)


def test_the_amendment_authorizes_nothing():
    amendment = _load(AMENDMENT)
    assert amendment["execution_authorization"]["execution_authorized"] is False
    assert amendment["execution_authorization"]["grid_run_authorized"] is False
    assert amendment["amendment_status"] == "PUBLISHED_CORRECTION_NO_AUTHORIZATION"
    status = amendment["prerequisite_status"]
    assert status["P5"] == "OUTSTANDING"
    assert status["P6"] == "OUTSTANDING"
    assert status["P4"] == "DELIVERED_BY_THIS_AMENDMENT"


def test_the_amendment_does_not_move_the_data_boundary():
    amendment = _load(AMENDMENT)
    freeze = _load(FREEZE)
    assert amendment["data_boundary"]["confirmatory_window_start_utc"] == freeze["data_boundary"][
        "confirmatory_window_start_utc"
    ]
    assert amendment["data_boundary"]["window_moved_by_this_amendment"] is False

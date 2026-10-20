"""Tests for the v3 specification amendment 1.

``configs/research_v3_spec_amendment_1.json`` corrects one stale reference of
the immutable v3 specification -- the data-integrity block still named the v2
data manifest -- and records the delivered prerequisite status by reference.
These tests prove that

* the amendment is deterministic and self-hashing;
* the immutable specification is untouched and still records the stale value,
  so the correction exists in exactly one place;
* the correction names the v3 data manifest and binds its current digest;
* the amendment binds the current v3 manifests, the candidate freeze and the
  freeze amendment by digest;
* the amendment authorizes nothing.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT = REPO_ROOT / "configs" / "research_v3_spec_amendment_1.json"
SPEC = REPO_ROOT / "configs" / "research_v3.json"
UNIVERSE = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA = REPO_ROOT / "research" / "data_manifest_v3.json"
FREEZE = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
FREEZE_AMENDMENT = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"

STALE_FIELD = "universe.eligibility_validation.data_integrity.data_manifest"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v3_spec_amendment_1", REPO_ROOT / "scripts" / "verify_v3_spec_amendment_1.py"
)
builder = _load_module(
    "build_v3_spec_amendment_1", REPO_ROOT / "scripts" / "build_v3_spec_amendment_1.py"
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


def test_the_immutable_specification_is_untouched():
    amendment = _load(AMENDMENT)
    spec = _load(SPEC)
    integrity = spec["universe"]["eligibility_validation"]["data_integrity"]
    assert integrity["data_manifest"] == "research/data_manifest_v2.json"
    assert amendment["immutable_specification"]["specification_hash"] == spec["specification_hash"]
    assert amendment["immutable_specification"]["file_sha256"] == builder.sha256_file(SPEC)


def test_the_correction_names_the_v3_data_manifest():
    amendment = _load(AMENDMENT)
    data = _load(DATA)
    correction = amendment["corrections"][0]
    assert correction["path"] == STALE_FIELD
    assert correction["recorded_value"] == "research/data_manifest_v2.json"
    assert correction["effective_value"] == "research/data_manifest_v3.json"
    assert correction["evidence"]["manifest_hash"] == data["manifest_hash"]
    assert correction["evidence"]["file_sha256"] == builder.sha256_file(DATA)


def test_the_amendment_binds_the_current_artifacts():
    amendment = _load(AMENDMENT)
    binding = amendment["binding"]
    assert binding["universe_manifest"]["manifest_hash"] == _load(UNIVERSE)["manifest_hash"]
    assert binding["data_manifest"]["manifest_hash"] == _load(DATA)["manifest_hash"]
    assert binding["candidate_freeze"]["manifest_hash"] == _load(FREEZE)["manifest_hash"]
    assert binding["candidate_freeze_amendment"]["manifest_hash"] == _load(
        FREEZE_AMENDMENT
    )["manifest_hash"]


def test_the_prerequisite_reconciliation():
    amendment = _load(AMENDMENT)
    reconciliation = amendment["reconciliation"]
    for pid in ("P2", "P3", "P4"):
        assert reconciliation[pid]["status_recorded"] == "DELIVERED", pid
    for pid in ("P5", "P6"):
        assert reconciliation[pid]["status_recorded"] == "OUTSTANDING", pid


def test_the_amendment_authorizes_nothing():
    amendment = _load(AMENDMENT)
    assert amendment["execution_authorization"]["execution_authorized"] is False
    assert amendment["execution_authorization"]["grid_run_authorized"] is False
    assert amendment["amendment_status"] == "PUBLISHED_CORRECTION_NO_AUTHORIZATION"

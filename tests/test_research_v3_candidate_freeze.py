"""Tests for the v3 candidate freeze and its correction by reference.

``configs/research_v3_candidate_freeze.json`` froze the *derived* candidate
batch of twenty assets before the constituent validation had been performed.
The validation then excluded fourteen of them, so the validated candidate set
is recorded by the versioned amendment
``configs/research_v3_candidate_freeze_amendment_1.json``.

These tests prove that

* the frozen artifact is unchanged and self-hashing;
* the effective v3 candidate set is resolved **through the amendment**, never
  from the stale derived batch, and the resolution is refused when the
  amendment is missing or unverifiable;
* the confirmatory window opens after the freeze and no run is authorized.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
AMENDMENT = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
EXCLUSION_AMENDMENT = REPO_ROOT / "configs" / "research_v3_exclusion_amendment_1.json"
SPEC = REPO_ROOT / "configs" / "research_v3.json"
UNIVERSE = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA = REPO_ROOT / "research" / "data_manifest_v3.json"

REQUIRED_FILES = (
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_candidate_freeze_amendment_1.json",
    "configs/research_v3_exclusion_amendment_1.json",
    "configs/research_v3.json",
    "research/universe_manifest_v3.json",
    "research/data_manifest_v3.json",
)

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
    "verify_research_v3_candidate_freeze", REPO_ROOT / "scripts" / "verify_research_v3_candidate_freeze.py"
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_tree(destination: Path) -> Path:
    for relative in REQUIRED_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_frozen_artifact_is_self_hashing():
    freeze = _load(FREEZE)
    excluded = tuple(freeze["hashing"]["manifest_hash_excluded_keys"])
    assert freeze["manifest_hash"] == verifier.compute_manifest_hash(freeze, excluded)
    assert freeze["manifest_hash"] == (
        "12a981b13c657b51bf2023fbfdb22f531d16c656af5eef0d8242f8c202c154e4"
    )


def test_the_effective_candidate_set_is_resolved_through_the_amendment():
    report = verifier.verify(REPO_ROOT)
    assert report["candidate_set_resolution"] == "freeze_amendment_1"
    assert report["candidate_count"] == 20
    assert report["effective_candidate_count"] == 6
    assert sorted(report["effective_candidates"]) == sorted(VALIDATED_PAIRS)


def test_the_frozen_derived_batch_matches_the_published_derivation():
    freeze = _load(FREEZE)
    exclusion_amendment = _load(EXCLUSION_AMENDMENT)
    published = [
        member["binance_pair"]
        for member in exclusion_amendment["derived_candidate_batch"]["members"]
    ]
    assert freeze["frozen_candidate_set"]["binance_pairs"] == published
    assert len(published) == 20


def test_the_amendment_binds_the_frozen_artifact():
    freeze = _load(FREEZE)
    amendment = _load(AMENDMENT)
    assert amendment["problem"]["affected_artifact_manifest_hash"] == freeze["manifest_hash"]
    assert amendment["problem"]["affected_artifact_candidate_set_size"] == 20


def test_the_resolution_is_refused_without_a_usable_amendment(tmp_path):
    """Without the amendment the frozen reference to the v3 manifests is stale.

    The frozen artifact names the pre-validation manifest hashes, so the
    verifier must fail instead of accepting the derived batch as the candidate
    set.
    """
    root = _copy_tree(tmp_path)
    (root / "configs" / "research_v3_candidate_freeze_amendment_1.json").unlink()
    report = verifier.verify(root)
    assert report["ok"] is False
    assert any("related_artifacts" in failure for failure in report["failures"])
    assert report["candidate_set_resolution"] == "frozen_derived_batch"


def test_a_tampered_freeze_is_detected(tmp_path):
    root = _copy_tree(tmp_path)
    path = root / "configs" / "research_v3_candidate_freeze.json"
    freeze = json.loads(path.read_text(encoding="utf-8"))
    freeze["frozen_candidate_set"]["binance_pairs"] = freeze["frozen_candidate_set"][
        "binance_pairs"
    ][:-1]
    path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = verifier.verify(root)
    assert report["ok"] is False
    assert any("manifest_hash" in failure for failure in report["failures"])


def test_the_confirmatory_window_opens_after_the_freeze():
    freeze = _load(FREEZE)
    boundary = freeze["data_boundary"]
    assert boundary["confirmatory_window_start_utc"] > freeze["candidate_freeze_timestamp_utc"]
    assert boundary["min_confirmatory_window_hours"] == 2160
    assert boundary["single_use"] is True
    assert boundary["v1_holdout_reuse"] == "forbidden"
    assert boundary["v2_confirmatory_window_reuse"] == "forbidden"


def test_the_freeze_authorizes_nothing():
    freeze = _load(FREEZE)
    assert freeze["execution_authorization"]["execution_authorized"] is False
    assert freeze["selection_remainder"]["grid_run_authorized"] is False
    assert freeze["selection_remainder"]["status"] == "OUTSTANDING"
    assert freeze["selection_remainder"]["max_candidates_per_asset"] == 1

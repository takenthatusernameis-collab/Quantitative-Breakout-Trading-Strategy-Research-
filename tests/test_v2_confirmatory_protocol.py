"""Tests for the preregistered v2 confirmatory-evaluation protocol.

``configs/research_v2_confirmatory_protocol.json`` preregisters how the 14
selected configurations of ``research/v2_selected_configurations_manifest.json``
will be evaluated on the v2 confirmatory window once that window exists. The
tests prove that

* the manifest hash recomputes from the document itself;
* the evaluation scope is exactly the 14 selected configurations, bound to the
  selected-configurations manifest, the selection authorization, the v2
  specification and the v2 data manifest, with the 4 assets without a candidate
  out of scope;
* the confirmatory window opens at the frozen start, needs 2,160 closed hourly
  candles, is single-use and is never reused from v1;
* the data path records single retrieval, exposure counting and v2-manifest
  hashing;
* the evaluation rule records the unchanged v1 metric, the unchanged cost
  scenarios and the prohibition on re-tuning, re-ranking or grid extension;
* the reporting and falsifiers block defines pass / failure / inconclusive,
  reports a null result and never re-opens the v1 holdout;
* the authorization boundary authorizes nothing and no candle read before the
  window exists;
* the verifier is not vacuous: tampering with the protocol, the manifest, the
  selection authorization or the source tree is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v2_confirmatory_protocol.json"
SELECTED_CONFIGURATIONS_MANIFEST_PATH = REPO_ROOT / "research" / "v2_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_PATH = REPO_ROOT / "configs" / "research_v2_selection_authorization_1.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
CANDIDATE_FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"
CODE_HASH_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

HASHED_SET_ROOT = "src/breakout_research"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v2_confirmatory_protocol", "scripts/verify_v2_confirmatory_protocol.py")
producer = _load_module("build_v2_confirmatory_protocol", "scripts/build_v2_confirmatory_protocol.py")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of symlinks to the parts of the repository the verifier reads."""
    root = tmp_path / "repo"
    skip = {".git", ".pytest_cache", "__pycache__"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative == Path("research"):
            dirs[:] = ["v2_evidence"]
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            if relative == Path("research_state") and name == "checkpoint_v2.json":
                continue
            source = Path(current) / name
            target = root / relative / name
            if relative == Path(HASHED_SET_ROOT):
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper_protocol(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    protocol = _load(PROTOCOL_PATH)
    mutate(protocol)
    _replace(root, "configs/research_v2_confirmatory_protocol.json", protocol)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_manifest_hash_recomputes_from_the_document():
    protocol = _load(PROTOCOL_PATH)
    excluded = tuple(protocol["hashing"]["manifest_hash_excluded_keys"])
    assert protocol["manifest_hash"] == verifier.compute_manifest_hash(protocol, excluded)


def test_protocol_is_reproducible_from_the_producer():
    built = producer.build(REPO_ROOT)
    assert json.loads(PROTOCOL_PATH.read_text(encoding="utf-8")) == built


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_protocol_status_records_no_evaluation():
    protocol = _load(PROTOCOL_PATH)
    assert protocol["protocol_status"] == "PREREGISTERED_NO_EVALUATION"
    assert protocol["authorization_boundary"]["authorizes_evaluation"] is False
    assert protocol["authorization_boundary"]["authorizes_candle_read_before_window_exists"] is False


def test_evaluation_scope_is_exactly_the_selected_configurations():
    protocol = _load(PROTOCOL_PATH)
    manifest = _load(SELECTED_CONFIGURATIONS_MANIFEST_PATH)
    selection_auth = _load(SELECTION_AUTHORIZATION_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    data_manifest = _load(DATA_V2_PATH)
    scope = protocol["evaluation_scope"]
    assert scope["selected_configurations_manifest"] == "research/v2_selected_configurations_manifest.json"
    assert scope["selected_configurations_manifest_hash"] == manifest["manifest_hash"]
    assert scope["selection_authorization_manifest_hash"] == selection_auth["manifest_hash"]
    assert scope["v2_specification_hash"] == spec_v2["specification_hash"]
    assert scope["v2_data_manifest_hash"] == data_manifest["manifest_hash"]
    selections = manifest["selections"]
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assert scope["in_scope_assets"] == len(assets_with_candidate) == 14
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    assert scope["out_of_scope_assets_without_candidate"] == assets_without_candidate
    assert assets_without_candidate == ["BCHUSDT", "BTCUSDT", "LINKUSDT", "TRXUSDT"]
    assert scope["scope_may_not_be_widened_narrowed_or_reranked"] is True


def test_confirmatory_window_opens_at_the_frozen_start_and_needs_2160_hours():
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(CANDIDATE_FREEZE_PATH)
    window = protocol["window_definition"]
    boundary = freeze["data_boundary"]
    assert window["window_opens_utc"] == boundary["confirmatory_window_start_utc"]
    assert window["window_opens_utc"] == "2026-10-19T22:00:00Z"
    assert window["minimum_closed_hourly_candles"] == 2160
    assert window["earliest_possible_end_utc"] == boundary["earliest_possible_confirmatory_window_end_utc"]
    assert window["earliest_possible_end_utc"] == "2027-01-17T22:00:00Z"


def test_confirmatory_window_rules_forbid_reuse_overlap_and_retuning():
    protocol = _load(PROTOCOL_PATH)
    window = protocol["window_definition"]
    assert window["single_use"] is True
    assert window["must_not_overlap_v1_holdout"] is True
    assert window["never_reused_from_v1"] is True


def test_data_path_records_single_retrieval_and_exposure_counting():
    protocol = _load(PROTOCOL_PATH)
    data_path = protocol["data_path"]
    assert data_path["retrieval_happens_once_after_readiness_test_passes"] is True
    assert data_path["every_read_counted_in_holdout_exposed_count"] is True
    assert data_path["hashed_and_verified_against_v2_data_manifest_scheme"] is True
    data_manifest = _load(DATA_V2_PATH)
    assert data_path["data_manifest_hash"] == data_manifest["manifest_hash"]


def test_evaluation_rule_records_unchanged_v1_rule_and_costs():
    protocol = _load(PROTOCOL_PATH)
    rule = protocol["evaluation_rule"]
    spec_v1 = _load(SPEC_V1_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    assert rule["unchanged_v1_evaluation_metric"] is True
    assert rule["unchanged_cost_scenarios"] is True
    assert rule["no_retuning_reranking_or_grid_extension_on_window"] is True
    assert rule["selection_rule_reference"] == "configs/research_v1.json#selection"
    assert spec_v1["selection"] == spec_v2["selection"]


def test_reporting_and_falsifiers_define_outcomes_and_falsifiers():
    protocol = _load(PROTOCOL_PATH)
    reporting = protocol["reporting_and_falsifiers"]
    assert reporting["pass_failure_inconclusive_defined"] is True
    assert reporting["null_result_reported"] is True
    assert reporting["v1_holdout_never_reopened"] is True
    assert isinstance(reporting["falsifiers"], list)
    assert len(reporting["falsifiers"]) > 0


def test_authorization_boundary_authorizes_nothing():
    protocol = _load(PROTOCOL_PATH)
    boundary = protocol["authorization_boundary"]
    assert boundary["authorizes_evaluation"] is False
    assert boundary["authorizes_candle_read_before_window_exists"] is False
    assert boundary["code_identity_rule"] == "canonical_digest"
    assert boundary["v1_paths_forbidden"] is True
    assert boundary["new_v2_paths_require_new_versioned_amendment"] is True


def test_code_hash_constraint_records_canonical_and_authorized_digests():
    protocol = _load(PROTOCOL_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    amendment = _load(CODE_HASH_AMENDMENT_PATH)
    constraint = protocol["code_hash_constraint"]
    assert constraint["canonical_source_digest"] == amendment["code_hash_constraint"]["canonical_source_digest"]
    assert constraint["authorized_code_hash"] == authorization["code_hash"]
    assert boundary_authorized_code_hash(protocol) == authorization["code_hash"]
    assert constraint["hashed_set_root"] == HASHED_SET_ROOT
    for relative in constraint["inside_hashed_set_examples"]:
        assert verifier.path_is_inside_hashed_set(relative), relative
    for relative in constraint["outside_hashed_set_examples"]:
        assert not verifier.path_is_inside_hashed_set(relative), relative


def boundary_authorized_code_hash(protocol: Dict[str, Any]) -> str:
    return protocol["authorization_boundary"]["authorized_code_hash"]


def test_v1_artifacts_are_unchanged():
    for relative, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, relative


def test_the_hashed_source_set_is_identified_by_the_canonical_digest():
    amendment = _load(CODE_HASH_AMENDMENT_PATH)
    recorded = amendment["code_hash_constraint"]["canonical_source_digest"]
    assert verifier.canonical_source_digest(REPO_ROOT) == recorded
    report = verifier.verify(REPO_ROOT)
    assert report["canonical_source_digest"] == recorded
    assert report["failures"] == []


def test_related_artifacts_point_at_the_recorded_artifacts():
    protocol = _load(PROTOCOL_PATH)
    manifest = _load(SELECTED_CONFIGURATIONS_MANIFEST_PATH)
    selection_auth = _load(SELECTION_AUTHORIZATION_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    data_manifest = _load(DATA_V2_PATH)
    freeze = _load(CANDIDATE_FREEZE_PATH)
    related = protocol["related_artifacts"]
    assert related["selected_configurations_manifest"]["path"] == "research/v2_selected_configurations_manifest.json"
    assert related["selected_configurations_manifest"]["manifest_hash"] == manifest["manifest_hash"]
    assert related["selection_authorization_1"]["path"] == "configs/research_v2_selection_authorization_1.json"
    assert related["selection_authorization_1"]["manifest_hash"] == selection_auth["manifest_hash"]
    assert related["v2_specification"]["path"] == "configs/research_v2.json"
    assert related["v2_specification"]["specification_hash"] == spec_v2["specification_hash"]
    assert related["v2_data_manifest"]["path"] == "research/data_manifest_v2.json"
    assert related["v2_data_manifest"]["manifest_hash"] == data_manifest["manifest_hash"]
    assert related["v2_candidate_freeze"]["path"] == "configs/research_v2_candidate_freeze.json"
    assert related["v2_candidate_freeze"]["manifest_hash"] == freeze["manifest_hash"]


def test_supersedes_the_selection_authorization():
    protocol = _load(PROTOCOL_PATH)
    selection_auth = _load(SELECTION_AUTHORIZATION_PATH)
    supersedes = protocol["supersedes"]
    assert supersedes["selection_authorization_path"] == "configs/research_v2_selection_authorization_1.json"
    assert supersedes["selection_authorization_manifest_hash"] == selection_auth["manifest_hash"]
    assert supersedes["v1_holdout_never_reused"] is True


def test_nothing_has_been_executed_under_this_protocol():
    protocol = _load(PROTOCOL_PATH)
    data_manifest = _load(DATA_V2_PATH)
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0


def test_the_tree_identity_checks_survive_a_perturbed_enumeration_order(tmp_path):
    root = _mirror_repo(tmp_path)
    report = verifier.verify(root)
    assert report["failures"] == []
    assert report["ok"] is True


def test_verifier_detects_a_tampered_evaluation_scope(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["evaluation_scope"]["in_scope_assets"] = 18

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("in-scope asset count does not match" in failure for failure in failures)


def test_verifier_detects_a_widened_scope(tmp_path):
    root = _mirror_repo(tmp_path)
    manifest = _load(SELECTED_CONFIGURATIONS_MANIFEST_PATH)
    selections = manifest["selections"]
    selections["BTCUSDT"]["selected"] = True
    selections["BTCUSDT"]["config_id"] = "cfg_fake"
    _replace(root, "research/v2_selected_configurations_manifest.json", manifest)
    failures = _failures(root)
    assert any("in-scope asset count does not match" in failure for failure in failures)


def test_verifier_detects_a_confirmatory_window_that_requires_fewer_hours(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["window_definition"]["minimum_closed_hourly_candles"] = 720

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("does not require 2,160 closed hourly candles" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_protocol(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["authorization_boundary"]["authorizes_evaluation"] = True

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("authorizes_evaluation is not false" in failure for failure in failures)


def test_verifier_detects_a_manifest_hash_mismatch(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["manifest_hash"] = "0" * 64

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "config.py"
    original = target.read_text(encoding="utf-8")
    target.unlink()
    target.write_text(original + "\n# tampered\n", encoding="utf-8")
    failures = _failures(root)
    assert any("does not match the recorded canonical digest" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "research" / "candidate_manifest.json").unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


def test_verifier_detects_confirmatory_exposure(tmp_path):
    root = _mirror_repo(tmp_path)
    data = _load(DATA_V2_PATH)
    data["confirmatory_window"]["holdout_exposed_count"] = 1
    _replace(root, "research/data_manifest_v2.json", data)
    failures = _failures(root)
    assert any("records confirmatory-window exposure" in failure for failure in failures)

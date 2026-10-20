"""Deterministic tests for the preregistered v3 execution amendment 2.

Every expectation is recomputed from the repository: the self-hash, the digest of the
amended protocol, the digests of the artifacts the amendment names, and the byte
anchors of the v1 artifacts.  The tamper tests rebuild the artifact in a mirrored tree
and prove that the verifier refuses it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} is not present in this checkout")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_module(
    "build_v3_execution_amendment_2",
    "scripts/build_v3_execution_amendment_2.py",
)
verifier = _load_module(
    "verify_v3_execution_amendment_2",
    "scripts/verify_v3_execution_amendment_2.py",
)

AMENDMENT_RELATIVE = "configs/research_v3_execution_amendment_2.json"
PROTOCOL_RELATIVE = "configs/research_v3_execution.json"
MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v3.json"

MIRROR_FILES = (
    AMENDMENT_RELATIVE,
    PROTOCOL_RELATIVE,
    "configs/research_v3.json",
    "configs/research_v1.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_candidate_freeze_amendment_1.json",
    "configs/research_v3_candidate_freeze_amendment_2.json",
    "research/universe_manifest_v3.json",
    "research/data_manifest_v3.json",
    "configs/research_v3_data_manifest_amendment_1.json",
    "configs/research_v3_execution_amendment_1.json",
    "configs/research_v3_selection_authorization_1.json",
    "research_state/campaign_authorization.json",
    LEDGER_RELATIVE,
    MANIFEST_RELATIVE,
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)


def _load(relative: str) -> Dict[str, Any]:
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in MIRROR_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_the_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_amendment_is_self_hashing():
    amendment = _load(AMENDMENT_RELATIVE)
    excluded = tuple(amendment["hashing"]["manifest_hash_excluded_keys"])
    assert amendment["manifest_hash"] == verifier.compute_manifest_hash(amendment, excluded)


def test_the_amendment_is_reproducible_from_the_producer():
    built = builder.build(REPO_ROOT)
    assert built == _load(AMENDMENT_RELATIVE)
    assert built["manifest_hash"] == verifier.compute_manifest_hash(
        built, tuple(built["hashing"]["manifest_hash_excluded_keys"]))


def test_the_producer_refuses_to_overwrite_the_artifact():
    with pytest.raises(SystemExit):
        builder.main([])


def test_the_amended_protocol_is_untouched():
    amendment = _load(AMENDMENT_RELATIVE)
    protocol = _load(PROTOCOL_RELATIVE)
    assert amendment["amends"]["file"] == PROTOCOL_RELATIVE
    assert amendment["amends"]["file_sha256"] == verifier.sha256_file(
        REPO_ROOT / PROTOCOL_RELATIVE)
    assert amendment["amends"]["protocol_specification_hash"] == protocol["specification_hash"]


def test_the_authorized_path_is_the_published_manifest():
    amendment = _load(AMENDMENT_RELATIVE)
    manifest = _load(MANIFEST_RELATIVE)
    paths = amendment["v3_result_layout_amendment"]["paths"]
    assert paths["selected_configurations_manifest_path"] == MANIFEST_RELATIVE
    assert paths["selected_configurations_manifest_path"] not in (
        "research/candidate_manifest.json", "research/candidate_manifest_v2.json")
    assert paths["selected_configurations_manifest_hash"] == manifest["manifest_hash"]


def test_the_authorization_rules_state_the_limits():
    amendment = _load(AMENDMENT_RELATIVE)
    rules = " ".join(
        str(rule) for rule in
        amendment["v3_result_layout_amendment"]["authorization_rules"]).lower()
    assert "no second run" in rules
    assert "no confirmatory-window evaluation" in rules
    assert "no candle fetch" in rules
    assert "re-derivable" in rules
    assert amendment["amendment_status"] == "PREREGISTERED_AMENDMENT_DESIGN_ONLY"


def test_the_amendment_does_not_change_the_v3_result_layout():
    amendment = _load(AMENDMENT_RELATIVE)
    protocol = _load(PROTOCOL_RELATIVE)
    layout = protocol["v3_result_layout"]
    paths = amendment["v3_result_layout_amendment"]["paths"]
    for key in ("shard_directory", "ledger_path", "results_manifest_path"):
        assert paths[key] == layout[key]
    assert amendment["v3_result_layout_amendment"]["campaign_id"] == layout["campaign_id"]
    assert amendment["v3_result_layout_amendment"]["writes_into_v1_forbidden"] is True
    assert amendment["v3_result_layout_amendment"]["writes_into_v2_forbidden"] is True


def test_the_referenced_artifacts_are_unchanged():
    amendment = _load(AMENDMENT_RELATIVE)
    observed = 0
    for name, reference in amendment["references"].items():
        path = REPO_ROOT / reference["file"]
        assert path.exists(), name
        document = json.loads(path.read_text(encoding="utf-8"))
        for key in ("manifest_hash", "specification_hash"):
            if reference.get(key) is not None:
                assert document.get(key) == reference[key], (name, key)
        observed += 1
    assert observed >= 10


def test_the_v1_artifacts_are_byte_unchanged():
    for relative, expected in verifier.V1_ARTIFACT_SHA256.items():
        assert verifier.sha256_file(REPO_ROOT / relative) == expected, relative
    authorization = _load("research_state/campaign_authorization.json")
    assert authorization["authorized"] is True
    assert authorization["code_hash"] == (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2")


def test_the_run_that_produced_the_manifest_is_the_completed_bounded_run():
    amendment = _load(AMENDMENT_RELATIVE)
    ledger = _load(LEDGER_RELATIVE)
    assert ledger["status"] == "COMPLETED"
    assert ledger["campaign_id"] == amendment["v3_result_layout_amendment"]["campaign_id"]
    assert ledger["holdout_exposed_count"] == 0


def test_the_mirrored_tree_verifies_cleanly(tmp_path):
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_tampered_manifest_hash(tmp_path):
    root = _mirror_repo(tmp_path)
    amendment = _load(AMENDMENT_RELATIVE)
    amendment["manifest_hash"] = "0" * 64
    _replace(root, AMENDMENT_RELATIVE, amendment)
    failures = _failures(root)
    assert any("manifest_hash" in failure for failure in failures)


def test_the_verifier_detects_an_edited_protocol(tmp_path):
    root = _mirror_repo(tmp_path)
    protocol = _load(PROTOCOL_RELATIVE)
    protocol["specification_hash"] = "0" * 64
    _replace(root, PROTOCOL_RELATIVE, protocol)
    failures = _failures(root)
    assert any("protocol" in failure for failure in failures)


def test_the_verifier_detects_a_forbidden_manifest_path(tmp_path):
    root = _mirror_repo(tmp_path)
    amendment = _load(AMENDMENT_RELATIVE)
    amendment["v3_result_layout_amendment"]["paths"][
        "selected_configurations_manifest_path"] = "research/candidate_manifest.json"
    _replace(root, AMENDMENT_RELATIVE, amendment)
    failures = _failures(root)
    assert any("v1 candidate manifest" in failure for failure in failures)


def test_the_verifier_detects_an_unbound_manifest(tmp_path):
    root = _mirror_repo(tmp_path)
    amendment = _load(AMENDMENT_RELATIVE)
    amendment["v3_result_layout_amendment"]["paths"][
        "selected_configurations_manifest_hash"] = "0" * 64
    _replace(root, AMENDMENT_RELATIVE, amendment)
    failures = _failures(root)
    assert any("does not bind the published manifest" in failure for failure in failures)


def test_the_verifier_detects_a_dropped_authorization_rule(tmp_path):
    root = _mirror_repo(tmp_path)
    amendment = _load(AMENDMENT_RELATIVE)
    amendment["v3_result_layout_amendment"]["authorization_rules"] = [
        "Only the published outcome of the completed authorized run may be written"
    ]
    _replace(root, AMENDMENT_RELATIVE, amendment)
    failures = _failures(root)
    assert any("authorization rules do not state" in failure for failure in failures)


def test_the_verifier_detects_a_changed_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    _replace(root, "research/candidate_manifest.json", {"changed": True})
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


def test_the_verifier_detects_a_missing_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / MANIFEST_RELATIVE).unlink()
    failures = _failures(root)
    assert failures == [f"missing artifact: {MANIFEST_RELATIVE}"]

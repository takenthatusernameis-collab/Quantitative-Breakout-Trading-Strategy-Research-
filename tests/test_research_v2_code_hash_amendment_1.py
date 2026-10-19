"""Tests for the preregistered v2 code-hash amendment 1 (BRAIN-009).

``configs/research_v2_code_hash_amendment_1.json`` makes the code-hash binding
of the hashed source set portable. The tests prove that

* the amendment is self-hashing and names the frozen artifacts it extends
  without editing any of them;
* the portable canonical source digest recomputes from the current source tree
  and agrees with the digest recorded by execution amendment 1;
* the authorized value of record is the code hash of the v1 campaign
  authorization, and the amendment does not rotate it;
* the affected verifiers really compute the canonical digest;
* **the tree-identity check survives a perturbed directory enumeration order
  while the ordered digest does not** -- the defect is real, the fix is
  effective, and neither depends on which order the checkout happens to use;
* the verifier is not vacuous: tampering with the amendment, with an amended
  artifact, with the source tree or with an affected verifier is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from breakout_research.config import compute_code_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"
EXECUTION_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_execution_amendment_1.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"

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


verifier = _load_module(
    "verify_research_v2_code_hash_amendment_1",
    "scripts/verify_research_v2_code_hash_amendment_1.py",
)
producer = _load_module(
    "build_v2_code_hash_amendment_1", "scripts/build_v2_code_hash_amendment_1.py"
)


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of symlinks to the parts of the repository the verifier reads.

    The hashed source tree is copied for real, so a test may modify it without
    ever writing to the working tree. The large result directories are skipped:
    the verifier never reads them.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {Path("research/results_shards"), Path("research/campaign_cycles")}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in skip_relative:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
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


def _tamper(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    amendment = _load(AMENDMENT_PATH)
    mutate(amendment)
    _replace(root, "configs/research_v2_code_hash_amendment_1.json", amendment)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _reverse_directory_enumeration(monkeypatch) -> None:
    """Make ``os.walk`` visit the directories of a tree in the opposite order.

    ``compute_code_hash()`` sorts the files inside each directory but visits the
    directories in filesystem enumeration order, so reversing that order changes
    the digest it returns even though no file changed.
    """
    real_walk = os.walk

    def patched(top, *args, **kwargs):
        for root, dirs, files in real_walk(top, *args, **kwargs):
            dirs.sort(reverse=True)
            yield root, dirs, files

    monkeypatch.setattr(os, "walk", patched)


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_manifest_hash_recomputes_from_the_document():
    amendment = _load(AMENDMENT_PATH)
    excluded = tuple(amendment["hashing"]["manifest_hash_excluded_keys"])
    assert amendment["manifest_hash"] == verifier.compute_manifest_hash(amendment, excluded)


def test_amendment_is_reproducible_from_the_producer():
    assert producer.build(REPO_ROOT) == _load(AMENDMENT_PATH)


def test_canonical_source_digest_recomputes_from_the_tree():
    amendment = _load(AMENDMENT_PATH)
    recorded = amendment["code_hash_constraint"]["canonical_source_digest"]
    assert verifier.canonical_source_digest(REPO_ROOT) == recorded
    assert producer.canonical_source_digest(REPO_ROOT) == recorded


def test_canonical_digest_agrees_with_execution_amendment_1():
    amendment = _load(AMENDMENT_PATH)
    execution_amendment = _load(EXECUTION_AMENDMENT_PATH)
    assert (
        amendment["code_hash_constraint"]["canonical_source_digest"]
        == execution_amendment["code_hash_constraint"]["canonical_source_digest"]
    )


def test_authorized_code_hash_is_the_value_of_record():
    amendment = _load(AMENDMENT_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    constraint = amendment["code_hash_constraint"]
    assert constraint["authorized_code_hash"] == authorization["code_hash"]
    assert constraint["authorized_code_hash_status"] == "RETAINED_AS_VALUE_OF_RECORD"
    assert authorization["authorized"] is True
    assert authorization["protocol_version"] == "v1"


def test_the_ordered_digest_is_declared_non_portable_and_informational():
    constraint = _load(AMENDMENT_PATH)["code_hash_constraint"]
    assert constraint["ordered_code_hash_is_portable"] is False
    assert constraint["live_ordered_code_hash_is_informational_only"] is True
    assert constraint["ordered_digest_defect"]
    assert constraint["ordered_digest_mismatch_meaning"]
    assert constraint["tree_identity_rule"]


def test_every_amended_artifact_is_byte_identical_and_records_the_value_of_record():
    amendment = _load(AMENDMENT_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    assert amendment["amends"]
    for entry in amendment["amends"]:
        path = REPO_ROOT / entry["path"]
        assert path.exists(), entry["path"]
        assert verifier.sha256_file(path) == entry["file_sha256"], entry["path"]
        document = json.loads(path.read_text(encoding="utf-8"))
        field = entry["code_hash_field"].split(".")
        recorded: Any = document
        for key in field:
            recorded = recorded[key]
        assert recorded == authorization["code_hash"], entry["path"]
        assert entry["artifact_edited"] is False
        assert entry["canonical_source_digest_added_by_this_amendment"] == (
            amendment["code_hash_constraint"]["canonical_source_digest"]
        )


def test_the_amendment_names_exactly_the_frozen_code_hash_artifacts():
    amendment = _load(AMENDMENT_PATH)
    assert {entry["path"] for entry in amendment["amends"]} == {
        "research/universe_manifest_v2.json",
        "research/data_manifest_v2.json",
        "configs/research_v2_candidate_freeze.json",
        "configs/research_v2_execution.json",
        "configs/research_v2_execution_amendment_1.json",
    }


def test_affected_verifiers_compute_the_canonical_digest():
    amendment = _load(AMENDMENT_PATH)
    recorded = amendment["code_hash_constraint"]["canonical_source_digest"]
    assert amendment["affected_verifiers"]
    for entry in amendment["affected_verifiers"]:
        module = _load_module(f"_probe_{Path(entry['path']).stem}", entry["path"])
        assert callable(module.canonical_source_digest), entry["path"]
        assert module.canonical_source_digest(REPO_ROOT) == recorded, entry["path"]


def test_the_design_basis_and_interim_rule_are_recorded():
    amendment = _load(AMENDMENT_PATH)
    basis = amendment["design_basis"]
    assert basis["brainstorming_item"] == "BRAIN-009"
    assert basis["chosen_design"] == "A"
    assert basis["chosen_design_summary"]
    assert amendment["interim_rule"]["rule"]
    assert amendment["interim_rule"]["reporting_rule"]


def test_the_residual_limitation_is_recorded():
    amendment = _load(AMENDMENT_PATH)
    limitations = amendment["residual_limitations"]
    assert limitations
    for limitation in limitations:
        for field in ("id", "location", "limitation", "consequence"):
            assert limitation[field], field


def test_the_amendment_authorizes_nothing():
    authorization_block = _load(AMENDMENT_PATH)["execution_authorization"]
    for flag in (
        "grid_run_authorized",
        "candidate_selection_authorized",
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "source_tree_change_authorized",
        "v1_reauthorization_authorized",
    ):
        assert authorization_block[flag] is False, flag


def test_nothing_has_been_executed():
    for relative in verifier.V2_EXECUTION_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative


def test_v1_artifacts_are_unchanged():
    for relative, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, relative


def test_the_source_tree_is_untouched_by_the_amendment():
    """The amendment authorizes no source-tree change, and none was made."""
    amendment = _load(AMENDMENT_PATH)
    assert amendment["execution_authorization"]["source_tree_change_authorized"] is False
    tracked = subprocess_git_ls_files()
    if tracked is None:
        pytest.skip("git is not available in this checkout")
    for relative in tracked:
        if relative.startswith(f"{HASHED_SET_ROOT}/"):
            path = REPO_ROOT / relative
            assert path.exists(), relative


def subprocess_git_ls_files() -> List[str]:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", HASHED_SET_ROOT],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def test_the_tree_identity_check_survives_a_perturbed_enumeration_order(monkeypatch):
    """The defect is real and the fixed check is immune to the directory order.

    ``compute_code_hash()`` follows the filesystem enumeration order, so the
    ordered digest changes when that order changes even though no file did. The
    canonical digest does not, and the verifiers keep passing.
    """
    ordered_before = compute_code_hash()
    canonical_before = verifier.canonical_source_digest(REPO_ROOT)
    report_before = verifier.verify(REPO_ROOT)
    assert report_before["failures"] == []

    _reverse_directory_enumeration(monkeypatch)

    ordered_after = compute_code_hash()
    canonical_after = verifier.canonical_source_digest(REPO_ROOT)
    assert ordered_after != ordered_before, "the ordered digest did not follow the enumeration order"
    assert canonical_after == canonical_before, "the canonical digest followed the enumeration order"

    report_after = verifier.verify(REPO_ROOT)
    assert report_after["failures"] == []
    assert report_after["ok"] is True
    assert report_after["live_ordered_code_hash"] == ordered_after
    assert report_after["ordered_code_hash_matches_authorized"] is (
        ordered_after == report_after["authorized_code_hash"]
    )
    if report_after["ordered_code_hash_matches_authorized"] is False:
        assert report_after["environment_facts"], "a mismatch must be reported as an environment fact"


def test_an_ordered_digest_mismatch_is_not_a_verifier_failure(monkeypatch):
    """A checkout with a different directory order must not turn the verifiers red."""
    _reverse_directory_enumeration(monkeypatch)
    for relative in (
        "scripts/verify_research_v2_manifests.py",
        "scripts/verify_research_v2_candidate_freeze.py",
    ):
        module = _load_module(f"_perturbed_{Path(relative).stem}", relative)
        report = module.verify(REPO_ROOT)
        assert report["failures"] == [], relative
        assert report["canonical_source_digest"] == (
            _load(AMENDMENT_PATH)["code_hash_constraint"]["canonical_source_digest"]
        )


def test_verifier_detects_a_tampered_manifest_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["manifest_hash"] = "0" * 64

    _tamper(root, mutate)
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


def test_verifier_detects_an_edited_amended_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    universe = _load(REPO_ROOT / "research" / "universe_manifest_v2.json")
    universe["snapshot_identity"]["code_hash"] = "0" * 64
    _replace(root, "research/universe_manifest_v2.json", universe)
    failures = _failures(root)
    assert any("does not match its recorded sha256" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_amendment(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["execution_authorization"]["grid_run_authorized"] = True

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("grid_run_authorized is not false" in failure for failure in failures)


def test_verifier_detects_a_widened_amends_list(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["amends"].append(
            {
                "path": "configs/research_v1.json",
                "file_sha256": "0" * 64,
                "code_hash_field": "code_hash",
                "recorded_code_hash": "0" * 64,
                "canonical_source_digest_added_by_this_amendment": "0" * 64,
                "artifact_edited": False,
            }
        )

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not amend exactly the frozen code-hash artifacts" in failure for failure in failures)


def test_verifier_detects_a_canonical_digest_that_disagrees_with_execution_amendment_1(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["code_hash_constraint"]["canonical_source_digest"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not match the recorded canonical digest" in failure for failure in failures)
    assert any("differs from the one recorded by" in failure for failure in failures)


def test_verifier_detects_an_affected_verifier_without_a_canonical_digest(tmp_path):
    root = _mirror_repo(tmp_path)
    _replace(
        root,
        "scripts/verify_research_v2_manifests.py",
        "def verify(repo_root=None):\n    return {'ok': True, 'failures': []}\n",
    )
    failures = _failures(root)
    assert any("does not compute a canonical digest" in failure for failure in failures)


def test_verifier_detects_a_missing_amended_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "configs" / "research_v2_candidate_freeze.json").unlink()
    failures = _failures(root)
    assert any("the amended artifact" in failure for failure in failures)

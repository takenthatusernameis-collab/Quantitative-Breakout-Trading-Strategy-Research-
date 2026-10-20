"""Deterministic, offline tests of the v2 confirmatory code-hash amendment.

The amendment rotates the confirmatory execution path's canonical digest after
the unreachable duplicate rollback block of ``src/v2_confirmatory/runner.py``
was removed (BRAIN-011 §12, finding 1, severity P0). The tests check it
against the artifacts it is bound to and against the delivered tree:

* the **repository itself**, read-only, for the checks that are about the
  delivered tree (the amendment's self-hash, the rotation, the change record,
  the resolution of the effective identity and the absence of a confirmatory
  artifact);
* a **synthetic mirror** in a temporary directory, for the checks that need a
  tampered artifact or a tampered tree. The mirror copies the hash-bound
  artifacts and the two source trees byte-identically; no provider request is
  made, no market data is read, and no confirmatory artifact is ever written
  inside the repository.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_code_hash_amendment_1.json"
AUTHORIZATION_RELATIVE = "configs/research_v2_confirmatory_authorization_1.json"
RUNBOOK_RELATIVE = "configs/research_v2_confirmatory_runbook_1.json"
PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
PROTOCOL_AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_protocol_amendment_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v2.json"
RUNNER_RELATIVE = "src/v2_confirmatory/runner.py"
IDENTITY_RELATIVE = "src/v2_confirmatory/identity.py"

PRODUCER = "scripts/build_v2_confirmatory_code_hash_amendment_1.py"
VERIFIER = "scripts/verify_v2_confirmatory_code_hash_amendment_1.py"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_confirmatory"

#: The digest the authorization and the runbook record: the identity of the
#: execution path before the dead code was removed.
PREVIOUS_EXECUTION_PATH_DIGEST = (
    "fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10"
)
PREVIOUS_RUN_CODE_IDENTITY = (
    "fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8"
)
CANONICAL_HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
AUTHORIZED_ORDERED_CODE_HASH = (
    "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
)

#: The artifacts the mirror copies.
MIRROR_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "configs/research_v2_confirmatory_code_hash_amendment_1.json",
    "configs/research_v2_confirmatory_authorization_1.json",
    "configs/research_v2_confirmatory_protocol.json",
    "configs/research_v2_confirmatory_protocol_amendment_1.json",
    "configs/research_v2_confirmatory_runbook_1.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/ledger_v2.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/v2_selected_configurations_manifest.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
)

MIRROR_TREES = ("src/breakout_research", "src/v2_confirmatory")

#: The artifacts a confirmatory evaluation would create inside the repository.
CONFIRMATORY_ARTIFACTS = (
    "research/v2_confirmatory_window_manifest.json",
    "research/shards_v2_confirmatory",
    "research/ledger_v2_confirmatory.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_v2_confirmatory.jsonl",
    "research_state/checkpoint_v2_confirmatory.json",
    "reports/confirmatory_evaluation_v2.json",
    "reports/confirmatory_report_v2.md",
)

#: The v1 artifacts that must stay byte-identical.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _manifest_hash(document: Dict[str, Any]) -> str:
    excluded = tuple(document.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    body = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _reseal(document: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute a document's self-hash after a tamper."""
    document["manifest_hash"] = _manifest_hash(document)
    return document


def _canonical_source_digest(root: Path) -> str:
    """The portable canonical digest of a ``*.py`` tree, under BRAIN-009's rule."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(hashlib.sha256((base / relative).read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def _live_hashed_set_digest() -> str:
    return _canonical_source_digest(REPO_ROOT / HASHED_SET_ROOT)


def _live_execution_path_digest() -> str:
    return _canonical_source_digest(REPO_ROOT / EXECUTION_PATH_ROOT)


def _live_run_code_identity() -> str:
    return hashlib.sha256(
        _canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": _live_hashed_set_digest(),
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": _live_execution_path_digest(),
            }
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _amendment() -> Dict[str, Any]:
    return _load(REPO_ROOT / AMENDMENT_RELATIVE)


def _mirror(root: Path) -> Path:
    """Build a synthetic mirror of the repository's hash-bound artifacts."""
    root.mkdir(parents=True, exist_ok=True)
    for relative in MIRROR_FILES:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for tree in MIRROR_TREES:
        target = root / tree
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO_ROOT / tree, target)
    return root


def _write_json(root: Path, relative: str, document: Dict[str, Any]) -> None:
    path = root / relative
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_verifier(repo_root: Path) -> Tuple[int, Dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / VERIFIER), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        report = {"stdout": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, report


def _run_producer(repo_root: Path, *extra: str) -> Tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / PRODUCER), "--repo-root", str(repo_root), *extra],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src")),
    )
    return completed.returncode, completed.stdout, completed.stderr


def _unreachable_after_raise(source: str) -> List[str]:
    """The handler bodies of ``source`` that hold a statement after a ``raise``."""
    findings: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        seen_raise = False
        for statement in node.body:
            if seen_raise:
                findings.append(f"line {statement.lineno}")
                break
            if isinstance(statement, ast.Raise):
                seen_raise = True
    return findings


# --------------------------------------------------------------------------
# 1. The amendment itself.
# --------------------------------------------------------------------------


def test_the_amendment_is_self_hashing() -> None:
    document = _amendment()
    assert document["manifest_hash"] == _manifest_hash(document)
    assert document["artifact"] == "research_v2_confirmatory_code_hash_amendment_1"
    assert document["artifact_version"] == 1


def test_the_amendment_records_the_rotation_of_the_execution_path_digest() -> None:
    rotation = _amendment()["code_hash_rotation"]
    assert rotation["previous_execution_path_digest"] == PREVIOUS_EXECUTION_PATH_DIGEST
    assert rotation["execution_path_digest"] == _live_execution_path_digest()
    assert rotation["execution_path_digest"] != rotation["previous_execution_path_digest"]
    assert rotation["previous_run_code_identity"] == PREVIOUS_RUN_CODE_IDENTITY
    assert rotation["run_code_identity"] == _live_run_code_identity()
    assert rotation["authorized_ordered_code_hash"] == AUTHORIZED_ORDERED_CODE_HASH
    assert rotation["ordered_code_hash_is_an_environment_fact"] is True


def test_the_hashed_set_is_unchanged() -> None:
    rotation = _amendment()["code_hash_rotation"]
    assert rotation["hashed_set_digest"] == CANONICAL_HASHED_SET_DIGEST
    assert rotation["hashed_set_unchanged"] is True
    assert _live_hashed_set_digest() == CANONICAL_HASHED_SET_DIGEST


def test_the_amended_artifacts_are_byte_identical_and_not_edited() -> None:
    document = _amendment()
    amends = document["amends"]
    for name, relative in (
        ("confirmatory_authorization_1", AUTHORIZATION_RELATIVE),
        ("confirmatory_runbook_1", RUNBOOK_RELATIVE),
    ):
        entry = amends[name]
        target = REPO_ROOT / relative
        assert entry["path"] == relative
        assert entry["edited"] is False
        assert entry["file_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert entry["manifest_hash"] == _load(target)["manifest_hash"]
        assert entry["recorded_execution_path_digest"] == PREVIOUS_EXECUTION_PATH_DIGEST
        assert entry["recorded_run_code_identity"] == PREVIOUS_RUN_CODE_IDENTITY


def test_the_amendment_authorizes_nothing() -> None:
    document = _amendment()
    assert document["authorizes_a_candle_read"] is False
    assert document["authorizes_an_evaluation"] is False
    assert document["authorizes_a_second_run"] is False
    assert document["authorizes_a_code_change"] is False
    assert document["authorizes_anything"] is False
    assert document["durability"]["amendment_commit_status"] == "PENDING_COMMIT"
    assert document["durability"]["amendment_commit"] is None


def test_the_rotation_does_not_reset_the_run_budget() -> None:
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    run = authorization["authorized_run"]
    assert run["max_runs"] == 1
    assert run["bounds"]["attempts"] == 1
    precedence = _amendment()["precedence"]
    assert precedence["the_authorization_still_permits_at_most_one_logical_run"] is True
    assert precedence["the_amended_artifacts_are_edited_in_place"] is False
    assert precedence["every_other_field_of_the_amended_artifacts_stands"] is True


def test_the_correction_of_the_audit_attribution_is_true() -> None:
    """The protocol and its criterion amendment bind no execution-path digest."""
    corrections = _amendment()["corrections"]
    assert corrections, "the amendment records no correction"
    assert corrections[0]["verdict"] == "FALSE"
    for relative in (PROTOCOL_RELATIVE, PROTOCOL_AMENDMENT_RELATIVE):
        assert "execution_path_digest" not in json.dumps(_load(REPO_ROOT / relative))
        assert relative in json.dumps(corrections)


# --------------------------------------------------------------------------
# 2. The change: the dead code is gone and nothing else changed.
# --------------------------------------------------------------------------


def test_the_removed_block_is_unreachable_and_gone() -> None:
    change = _amendment()["change"]
    source = (REPO_ROOT / RUNNER_RELATIVE).read_text(encoding="utf-8")
    removed = change["removed_block_text"]
    assert hashlib.sha256(removed.encode("utf-8")).hexdigest() == change["removed_block_sha256"]
    # The live rollback block is byte-identical to the removed one, so the
    # removed block must occur exactly once in the delivered runner.
    assert source.count(removed) == 1
    assert _unreachable_after_raise(source) == []
    assert change["the_removed_block_was_unreachable"] is True
    assert change["behavioural_change"] is False


def test_the_change_record_names_the_file_and_the_lines() -> None:
    change = _amendment()["change"]
    assert change["file"] == RUNNER_RELATIVE
    assert change["kind"] == "REMOVAL_OF_UNREACHABLE_DEAD_CODE"
    assert change["removed_line_range_in_the_pre_rotation_file"] == [1039, 1044]
    assert change["post_rotation_file_sha256"] == hashlib.sha256(
        (REPO_ROOT / RUNNER_RELATIVE).read_bytes()
    ).hexdigest()


def test_the_delivered_tree_carries_no_unreachable_code() -> None:
    for module in sorted((REPO_ROOT / EXECUTION_PATH_ROOT).glob("*.py")):
        findings = _unreachable_after_raise(module.read_text(encoding="utf-8"))
        assert findings == [], f"{module.name} holds unreachable code: {findings}"


# --------------------------------------------------------------------------
# 3. The delivered implementation resolves the effective identity.
# --------------------------------------------------------------------------


def test_the_delivered_implementation_resolves_the_effective_identity() -> None:
    from v2_confirmatory import identity

    recorded = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)["authorized_run"]["code_identity"]
    resolved = identity.resolve_code_identity(REPO_ROOT, recorded)
    assert resolved["rotation_applied"] is True
    assert resolved["execution_path_digest"] == _live_execution_path_digest()
    assert resolved["run_code_identity"] == _live_run_code_identity()
    assert resolved["superseded_execution_path_digest"] == PREVIOUS_EXECUTION_PATH_DIGEST
    assert resolved["code_hash_amendment_manifest_hash"] == _amendment()["manifest_hash"]


def test_the_delivered_runner_accepts_the_rotated_identity() -> None:
    from v2_confirmatory import runner

    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    assert plan.code_identity["execution_path_digest"] == _live_execution_path_digest()
    assert plan.code_identity["run_code_identity"] == _live_run_code_identity()
    assert plan.code_identity["rotation_applied"] is True


def test_the_delivered_runner_refuses_an_unamended_rotation(tmp_path: Path) -> None:
    from v2_confirmatory import runner
    from v2_confirmatory.errors import AuthorizationError

    root = _mirror(tmp_path / "unamended")
    (root / AMENDMENT_RELATIVE).unlink()
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_delivered_runner_refuses_a_foreign_digest(tmp_path: Path) -> None:
    from v2_confirmatory import runner
    from v2_confirmatory.errors import AuthorizationError

    root = _mirror(tmp_path / "foreign")
    document = _load(root / AUTHORIZATION_RELATIVE)
    document["authorized_run"]["code_identity"]["execution_path_digest"] = "0" * 64
    _reseal(document)
    _write_json(root, AUTHORIZATION_RELATIVE, document)
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_delivered_runner_refuses_a_changed_hashed_set(tmp_path: Path) -> None:
    from v2_confirmatory import runner
    from v2_confirmatory.errors import AuthorizationError

    root = _mirror(tmp_path / "hashed_set")
    target = root / HASHED_SET_ROOT / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# a drift probe\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


# --------------------------------------------------------------------------
# 4. Nothing has been executed.
# --------------------------------------------------------------------------


def test_no_confirmatory_artifact_exists() -> None:
    for relative in CONFIRMATORY_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative
    data_manifest = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0
    for relative in (LEDGER_RELATIVE, CHECKPOINT_RELATIVE):
        assert _load(REPO_ROOT / relative)["holdout_exposed_count"] == 0


def test_the_v1_artifacts_are_byte_unchanged() -> None:
    for relative, digest in V1_ARTIFACT_SHA256.items():
        assert hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() == digest


def test_the_v1_campaign_authorization_is_untouched() -> None:
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert authorization["code_hash"] == AUTHORIZED_ORDERED_CODE_HASH
    assert authorization["authorized"] is True


# --------------------------------------------------------------------------
# 5. The producer and the verifier.
# --------------------------------------------------------------------------


def test_the_amendment_is_reproducible_from_its_producer(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reproduced")
    status, stdout, stderr = _run_producer(root, "--print")
    assert status == 0, stderr
    assert json.loads(stdout) == _amendment()


def test_the_producer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "refused")
    before = (root / AMENDMENT_RELATIVE).read_bytes()
    status, _, stderr = _run_producer(root)
    assert status == 1
    assert "refusing to overwrite" in stderr
    assert (root / AMENDMENT_RELATIVE).read_bytes() == before


def test_the_verifier_passes_on_the_delivered_tree() -> None:
    status, report = _run_verifier(REPO_ROOT)
    assert status == 0, report
    assert report["failures"] == []
    assert report["execution_path_digest"] == _live_execution_path_digest()
    assert report["run_code_identity"] == _live_run_code_identity()
    assert report["previous_execution_path_digest"] == PREVIOUS_EXECUTION_PATH_DIGEST
    assert report["confirmatory_artifacts_present"] == []


# --------------------------------------------------------------------------
# 6. The tamper cases.
# --------------------------------------------------------------------------


def test_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "tampered_hash")
    document = _load(root / AMENDMENT_RELATIVE)
    document["manifest_hash"] = "0" * 64
    _write_json(root, AMENDMENT_RELATIVE, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("manifest hash does not recompute" in failure for failure in report["failures"])


def test_verifier_detects_a_rotation_to_a_foreign_digest(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "foreign_digest")
    document = _load(root / AMENDMENT_RELATIVE)
    document["code_hash_rotation"]["execution_path_digest"] = "0" * 64
    _reseal(document)
    _write_json(root, AMENDMENT_RELATIVE, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("live execution-path digest" in failure for failure in report["failures"])


def test_verifier_detects_an_edited_amended_artifact(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "edited_authorization")
    document = _load(root / AUTHORIZATION_RELATIVE)
    document["authorized_run"]["max_runs"] = 2
    _write_json(root, AUTHORIZATION_RELATIVE, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("not byte-identical" in failure for failure in report["failures"])


def test_verifier_detects_a_self_authorizing_amendment(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "self_authorizing")
    document = _load(root / AMENDMENT_RELATIVE)
    document["authorizes_an_evaluation"] = True
    _reseal(document)
    _write_json(root, AMENDMENT_RELATIVE, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("authorizes_an_evaluation" in failure for failure in report["failures"])


def test_verifier_detects_a_missing_amendment(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "missing")
    (root / AMENDMENT_RELATIVE).unlink()
    status, report = _run_verifier(root)
    assert status == 1
    assert any("does not exist" in failure for failure in report["failures"])


def test_verifier_detects_a_restored_dead_code_block(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "restored_dead_code")
    path = root / RUNNER_RELATIVE
    source = path.read_text(encoding="utf-8")
    removed = _amendment()["change"]["removed_block_text"]
    assert removed in source
    # Re-insert the unreachable duplicate right after the live rollback block.
    marker = removed
    source = source.replace(marker, marker + "\n" + removed, 1)
    path.write_text(source, encoding="utf-8")
    status, report = _run_verifier(root)
    assert status == 1
    assert any("unreachable code" in failure for failure in report["failures"])


def test_verifier_detects_a_changed_hashed_set(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "hashed_set")
    target = root / HASHED_SET_ROOT / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# a drift probe\n", encoding="utf-8")
    status, report = _run_verifier(root)
    assert status == 1
    assert any("hashed-set digest" in failure for failure in report["failures"])


def test_verifier_detects_a_missing_confirmatory_artifact_state(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "exposed")
    document = _load(root / DATA_MANIFEST_RELATIVE)
    document["confirmatory_window"]["holdout_exposed_count"] = 1
    _write_json(root, DATA_MANIFEST_RELATIVE, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("records a confirmatory exposure" in failure for failure in report["failures"])

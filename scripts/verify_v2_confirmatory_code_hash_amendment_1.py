#!/usr/bin/env python3
"""Read-only, offline verification of the v2 confirmatory code-hash amendment.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks the amendment that rotates the confirmatory
execution path's canonical digest after the unreachable duplicate rollback
block of ``src/v2_confirmatory/runner.py`` was removed (BRAIN-011 §12,
finding 1, severity P0):

* the amendment is self-hashing: its ``manifest_hash`` recomputes over the
  document body with ``manifest_hash`` removed;
* the rotation is real: the live execution-path digest is the digest the
  amendment records, it differs from the digest the authorization and the
  runbook record, the hashed set is unchanged, and the composite run identity
  is the composite of the two live digests;
* the two amended artifacts are **byte-identical** and still carry the
  superseded digest: the rotation is carried by reference, not by an edit;
* the factual correction of the audit is true: neither the confirmatory
  protocol nor its criterion amendment records an execution-path digest;
* the change record is exact: the removed block is absent from the delivered
  runner, its digest matches its recorded text, the block duplicated the live
  rollback statements, and no handler of the delivered runner contains a
  statement after a ``raise``;
* the delivered implementation resolves the effective identity through the
  amendment's rule, and the delivered runner calls it;
* the rotation does not reset the run budget: the authorization still permits
  at most one logical run;
* the amendment authorizes nothing, and its commit-before-the-first-read rule
  stands;
* nothing has been executed: no confirmatory artifact exists, the
  confirmatory window is still ``NOT_STARTED`` and ``holdout_exposed_count``
  is still 0;
* the v1 evidence and the frozen v2 artifacts are byte-identical.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_code_hash_amendment_1.json"
AUTHORIZATION_RELATIVE = "configs/research_v2_confirmatory_authorization_1.json"
RUNBOOK_RELATIVE = "configs/research_v2_confirmatory_runbook_1.json"
PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
PROTOCOL_AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_protocol_amendment_1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v2_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v2.json"
RUNNER_RELATIVE = "src/v2_confirmatory/runner.py"
IDENTITY_RELATIVE = "src/v2_confirmatory/identity.py"

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
HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
AUTHORIZED_ORDERED_CODE_HASH = (
    "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
)

#: The v1 artifacts that must stay byte-identical.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The frozen v2 artifacts that must stay unchanged.
FROZEN_V2_ARTIFACTS = {
    "research/universe_manifest_v2.json": "4e927e522eb18434459547602cc96201fa6e7c15b02010f9e7366270e5ad3f88",
    "research/data_manifest_v2.json": "9f64d8d140c0ccc2f521296ec86d320e29b665b622034cbee8e8f878a3d6924e",
    "configs/research_v2.json": "49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721",
    "configs/research_v2_candidate_freeze.json": "5a56b3d801519bbda0ed534cd031d0cb4204c1c015e5accb6fbc4e9bd0ec123f",
    "configs/research_v2_confirmatory_protocol.json": "bba9539442c92e7e7f51f72ab51e9f9e82bb4c354639be79b7db0baf4b043be3",
    "configs/research_v2_confirmatory_protocol_amendment_1.json": "2701c63456e080b1a8a0cbcd478d1bf4dc04d35212f4f270ea88d7460f56f377",
    "configs/research_v2_confirmatory_authorization_1.json": "f411aba94231e36a4dd711376df8a182a979f20d0a248076db0d5eacfaeef943",
    "configs/research_v2_confirmatory_runbook_1.json": "d81d919718f2f100f2e091eed8b43a4a228213313dc1dab0fc1a512e929f2a6a",
    "research/v2_selected_configurations_manifest.json": "7acc7fe07ba4b151ee232eb70fd0a187966400005054892c184bfdd754d6d862",
}

#: The artifacts a confirmatory evaluation would create. None of them may exist.
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


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: List[str]) -> str:
    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_source_digest(root: Path) -> str:
    """The portable canonical digest of a ``*.py`` tree (BRAIN-009's rule)."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(hashlib.sha256((base / relative).read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def run_code_identity(hashed_set: str, execution_path: str) -> str:
    payload = {
        "algorithm": "canonical_source_digest_v1",
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
    }
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def unreachable_after_raise(source: str) -> List[str]:
    """The handler bodies of ``source`` that hold a statement after a ``raise``."""
    findings: List[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        seen_raise = False
        for statement in node.body:
            if seen_raise:
                findings.append(
                    f"line {statement.lineno}: a statement follows the raise of the handler"
                )
                break
            if isinstance(statement, ast.Raise):
                seen_raise = True
    return findings


def calls_resolve_code_identity(source: str) -> bool:
    """Whether ``source`` calls ``identity.resolve_code_identity``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "resolve_code_identity"
        ):
            return True
    return False


def defines_resolve_code_identity(source: str) -> bool:
    """Whether ``source`` defines ``resolve_code_identity``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "resolve_code_identity":
                return True
    return False


def verify(root: Path) -> Dict[str, Any]:
    """Verify the amendment against the repository it is bound to."""
    root = Path(root)
    failures: List[str] = []

    amendment_path = root / AMENDMENT_RELATIVE
    if not amendment_path.exists():
        return {
            "ok": False,
            "failures": [f"the code-hash amendment {AMENDMENT_RELATIVE} does not exist"],
        }
    amendment = _load(amendment_path)

    # 1. The amendment is self-hashing.
    excluded = tuple((amendment.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the amendment does not declare its manifest_hash_excluded_keys")
    elif amendment.get("manifest_hash") != compute_manifest_hash(amendment, list(excluded)):
        failures.append("the amendment manifest hash does not recompute")

    authorization = _load(root / AUTHORIZATION_RELATIVE)
    runbook = _load(root / RUNBOOK_RELATIVE)
    protocol = _load(root / PROTOCOL_RELATIVE)
    protocol_amendment = _load(root / PROTOCOL_AMENDMENT_RELATIVE)

    # 2. The rotation is real and binds the live tree.
    live_hashed_set = canonical_source_digest(root / HASHED_SET_ROOT)
    live_execution_path = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    live_composite = run_code_identity(live_hashed_set, live_execution_path)
    rotation = amendment.get("code_hash_rotation") or {}
    if rotation.get("hashed_set_digest") != live_hashed_set:
        failures.append(
            "the amendment does not record the live hashed-set digest: recorded "
            f"{rotation.get('hashed_set_digest')}, recomputed {live_hashed_set}"
        )
    if rotation.get("hashed_set_unchanged") is not True:
        failures.append("the amendment does not record that the hashed set is unchanged")
    if rotation.get("execution_path_digest") != live_execution_path:
        failures.append(
            "the amendment does not record the live execution-path digest: recorded "
            f"{rotation.get('execution_path_digest')}, recomputed {live_execution_path}"
        )
    if rotation.get("run_code_identity") != live_composite:
        failures.append("the amendment does not record the composite identity of the live tree")
    if rotation.get("previous_execution_path_digest") == live_execution_path:
        failures.append("the amendment rotates no digest: the previous digest is the live one")
    if rotation.get("authorized_ordered_code_hash") != AUTHORIZED_ORDERED_CODE_HASH:
        failures.append("the amendment does not record the authorized ordered code hash")
    if rotation.get("ordered_code_hash_is_an_environment_fact") is not True:
        failures.append("the amendment treats the ordered code hash as an identity")

    # 3. The amended artifacts are byte-identical and still carry the superseded digest.
    amends = amendment.get("amends") or {}
    recorded_authorization_identity = (
        (authorization.get("authorized_run") or {}).get("code_identity") or {}
    )
    recorded_runbook_identity = (runbook.get("binding_identities") or {}).get(
        "code_identity"
    ) or {}
    for name, path, recorded, field in (
        (
            "confirmatory_authorization_1",
            AUTHORIZATION_RELATIVE,
            recorded_authorization_identity,
            "authorized_run.code_identity",
        ),
        (
            "confirmatory_runbook_1",
            RUNBOOK_RELATIVE,
            recorded_runbook_identity,
            "binding_identities.code_identity",
        ),
    ):
        entry = amends.get(name) or {}
        if not entry:
            failures.append(f"the amendment does not amend the {name}")
            continue
        if entry.get("path") != path:
            failures.append(f"the amendment amends the {name} at the wrong path")
        if entry.get("edited") is not False:
            failures.append(f"the amendment does not record that the {name} is not edited")
        target = root / path
        if not target.exists():
            failures.append(f"the amended artifact {path} is missing")
            continue
        if entry.get("file_sha256") != sha256_file(target):
            failures.append(f"the amended artifact {path} is not byte-identical")
        document = _load(target)
        if entry.get("manifest_hash") != document.get("manifest_hash"):
            failures.append(f"the amended artifact {path} does not carry its recorded manifest hash")
        if recorded.get("execution_path_digest") != PREVIOUS_EXECUTION_PATH_DIGEST:
            failures.append(f"the {name} does not record the pre-rotation digest")
        if recorded.get("run_code_identity") != PREVIOUS_RUN_CODE_IDENTITY:
            failures.append(f"the {name} does not record the pre-rotation composite identity")
        if entry.get("recorded_execution_path_digest") != PREVIOUS_EXECUTION_PATH_DIGEST:
            failures.append(f"the amendment does not record the digest the {name} carries")
        if entry.get("superseded_code_identity_field") != field:
            failures.append(f"the amendment does not name the superseded field of the {name}")

    # 4. The factual correction of the audit.
    corrections = amendment.get("corrections") or []
    if not corrections:
        failures.append("the amendment records no correction of the audit's attribution")
    for relative, document in (
        (PROTOCOL_RELATIVE, protocol),
        (PROTOCOL_AMENDMENT_RELATIVE, protocol_amendment),
    ):
        if "execution_path_digest" in json.dumps(document):
            failures.append(
                f"the correction claims that {relative} records no execution-path digest, "
                "but it does"
            )
    for relative in (PROTOCOL_RELATIVE, PROTOCOL_AMENDMENT_RELATIVE):
        if relative not in json.dumps(corrections):
            failures.append(f"the correction does not name {relative}")

    # 5. The change record is exact.
    change = amendment.get("change") or {}
    runner_path = root / RUNNER_RELATIVE
    if not runner_path.exists():
        failures.append(f"the delivered runner {RUNNER_RELATIVE} is missing")
        runner_source = ""
    else:
        runner_source = runner_path.read_text(encoding="utf-8")
        if change.get("post_rotation_file_sha256") != sha256_file(runner_path):
            failures.append("the delivered runner does not match the recorded post-rotation digest")
    removed_block = str(change.get("removed_block_text") or "")
    if not removed_block:
        failures.append("the amendment records no removed block")
    else:
        if hashlib.sha256(removed_block.encode("utf-8")).hexdigest() != change.get(
            "removed_block_sha256"
        ):
            failures.append("the removed block's digest does not match its recorded text")
        statements = removed_block.replace("        raise\n", "")
        # The live rollback block is byte-identical to the removed one, so the
        # removed block must occur exactly once in the delivered runner: the
        # unreachable copy is gone, the reachable one is untouched.
        if runner_source.count(removed_block) != 1:
            failures.append(
                "the delivered runner holds "
                f"{runner_source.count(removed_block)} copies of the removed block; the "
                "unreachable duplicate was not removed"
            )
        if statements and runner_source.count(statements) != 1:
            failures.append(
                "the removed block did not duplicate the live rollback statements, so its "
                "removal may have changed the behaviour"
            )
    if change.get("the_removed_block_was_unreachable") is not True:
        failures.append("the amendment does not record that the removed block was unreachable")
    if change.get("behavioural_change") is not False:
        failures.append("the amendment does not record that the change has no behavioural effect")
    if runner_source:
        for finding in unreachable_after_raise(runner_source):
            failures.append(f"the delivered runner holds unreachable code: {finding}")

    # 6. The delivered implementation resolves the identity through the amendment.
    identity_path = root / IDENTITY_RELATIVE
    if not identity_path.exists():
        failures.append(f"the delivered identity module {IDENTITY_RELATIVE} is missing")
    elif not defines_resolve_code_identity(identity_path.read_text(encoding="utf-8")):
        failures.append("the delivered identity module does not define resolve_code_identity")
    if runner_source and not calls_resolve_code_identity(runner_source):
        failures.append("the delivered runner does not resolve the code identity through the rule")

    # 7. The rotation does not reset the run budget.
    run = authorization.get("authorized_run") or {}
    if run.get("max_runs") != 1:
        failures.append("the authorization no longer permits at most one logical run")
    if int((run.get("bounds") or {}).get("attempts") or 0) != 1:
        failures.append("the authorization no longer bounds the run to one attempt")

    # 8. The amendment authorizes nothing and its durability rule stands.
    for field in (
        "authorizes_a_candle_read",
        "authorizes_an_evaluation",
        "authorizes_a_second_run",
        "authorizes_a_code_change",
        "authorizes_anything",
    ):
        if amendment.get(field) is not False:
            failures.append(f"the amendment does not record that it grants no {field}")
    durability = amendment.get("durability") or {}
    if not durability.get("rule"):
        failures.append("the amendment records no durability rule")
    if durability.get("amendment_commit_status") != "PENDING_COMMIT":
        failures.append("the amendment does not record its commit-before-the-first-read status")
    precedence = amendment.get("precedence") or {}
    if precedence.get("the_amended_artifacts_are_edited_in_place") is not False:
        failures.append("the amendment does not record that no amended artifact is edited in place")
    if precedence.get("every_other_field_of_the_amended_artifacts_stands") is not True:
        failures.append("the amendment does not limit its precedence to the code-identity fields")
    if precedence.get("the_authorization_still_permits_at_most_one_logical_run") is not True:
        failures.append("the amendment does not record that the run budget is unchanged")

    # 9. Nothing has been executed.
    for relative in CONFIRMATORY_ARTIFACTS:
        if (root / relative).exists():
            failures.append(f"the confirmatory artifact {relative} exists")
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    window = data_manifest.get("confirmatory_window") or {}
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the confirmatory window is no longer NOT_STARTED")
    if int(window.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v2 data manifest records a confirmatory exposure")
    for relative in (LEDGER_RELATIVE, CHECKPOINT_RELATIVE):
        path = root / relative
        if not path.exists():
            failures.append(f"the v2 selection artifact {relative} is missing")
            continue
        document = _load(path)
        if int(document.get("holdout_exposed_count") or 0) != 0:
            failures.append(f"{relative} records a confirmatory exposure")

    # 10. The frozen evidence is byte-identical.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
        elif sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    for relative, digest in FROZEN_V2_ARTIFACTS.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the frozen v2 artifact {relative} is missing")
            continue
        document = _load(target)
        observed = document.get("manifest_hash") or document.get("specification_hash")
        if observed is not None and observed != digest:
            failures.append(f"the frozen v2 artifact {relative} does not match its recorded hash")

    campaign_authorization_path = root / "research_state" / "campaign_authorization.json"
    if campaign_authorization_path.exists():
        campaign_authorization = _load(campaign_authorization_path)
        if campaign_authorization.get("code_hash") != AUTHORIZED_ORDERED_CODE_HASH:
            failures.append("the v1 campaign authorization's code hash changed")
    else:
        failures.append("research_state/campaign_authorization.json is missing")

    return {
        "ok": not failures,
        "amendment_manifest_hash": amendment.get("manifest_hash"),
        "previous_execution_path_digest": PREVIOUS_EXECUTION_PATH_DIGEST,
        "execution_path_digest": live_execution_path,
        "previous_run_code_identity": PREVIOUS_RUN_CODE_IDENTITY,
        "run_code_identity": live_composite,
        "canonical_source_digest": live_hashed_set,
        "confirmatory_artifacts_present": [
            relative for relative in CONFIRMATORY_ARTIFACTS if (root / relative).exists()
        ],
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

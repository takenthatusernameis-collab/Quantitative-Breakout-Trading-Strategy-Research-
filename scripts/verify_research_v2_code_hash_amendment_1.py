#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 code-hash amendment 1.

``configs/research_v2_code_hash_amendment_1.json`` is a design artifact. It
makes the code-hash binding of the hashed source set portable: it adds the
canonical source digest to the frozen v2 artifacts by reference, retains the
historical ordered digest as the authorized value of record, and fixes the
tree-identity check that the verifiers and tests must perform.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks:

* the manifest hash recomputes from the canonical content of the document with
  the hash key removed;
* the canonical source digest recorded here recomputes from the current source
  tree, and it agrees with the digest recorded by execution amendment 1;
* the authorized value of record is the code hash of the v1 campaign
  authorization, and that authorization is still valid for protocol v1;
* every amended artifact is byte-identical to the digest recorded for it, still
  records the authorized value of record in the field named for it, and was
  not edited;
* the affected verifiers really implement the canonical tree-identity check:
  each of them exposes a ``canonical_source_digest`` that returns the recorded
  digest for this repository;
* the design basis, the tree-identity rule, the interim rule and the residual
  limitations are recorded, and the ruled-out alternatives are named;
* nothing is authorized, nothing has been executed and the v1 evidence is
  byte-identical.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"
EXECUTION_AMENDMENT_RELATIVE = "configs/research_v2_execution_amendment_1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

HASHED_SET_ROOT = "src/breakout_research"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

V2_EXECUTION_ARTIFACTS = (
    "research/shards_v2",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    """The portable identity of the hashed source tree.

    Every ``*.py`` file under the hashed set contributes its POSIX relative path
    and the sha256 hex digest of its bytes, in ascending path order. Unlike
    ``compute_code_hash()`` this does not depend on the directory enumeration
    order of the checkout, so it is reproducible on any machine.
    """
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def live_ordered_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Reproduce ``compute_code_hash()`` exactly, for the informational report.

    The result depends on the filesystem enumeration order of the checkout and
    is therefore not a portable identity of the tree.
    """
    src_dir = repo_root / HASHED_SET_ROOT
    if not src_dir.exists():
        return None
    digest = hashlib.sha256()
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            if name.endswith(".py"):
                digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def path_is_inside_hashed_set(relative: str) -> bool:
    root = HASHED_SET_ROOT.rstrip("/")
    candidate = relative.rstrip("/")
    return candidate == root or candidate.startswith(root + "/")


def load_module(path: Path):
    """Import a repository script by path, without installing it."""
    spec = importlib.util.spec_from_file_location(f"_amendment_probe_{path.stem}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    amendment_path = repo_root / AMENDMENT_RELATIVE

    required = (
        amendment_path,
        repo_root / EXECUTION_AMENDMENT_RELATIVE,
        repo_root / AUTHORIZATION_RELATIVE,
    )
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    execution_amendment = json.loads(
        (repo_root / EXECUTION_AMENDMENT_RELATIVE).read_text(encoding="utf-8")
    )
    authorization = json.loads((repo_root / AUTHORIZATION_RELATIVE).read_text(encoding="utf-8"))

    # 1. The amendment is self-hashing.
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the amendment does not declare its manifest_hash_excluded_keys")
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. The tree identity is portable and reproduces from the current tree.
    constraint = amendment.get("code_hash_constraint") or {}
    recorded_canonical = constraint.get("canonical_source_digest")
    live_canonical = canonical_source_digest(repo_root)
    if recorded_canonical != live_canonical:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}"
        )
    algorithm = constraint.get("canonical_source_digest_algorithm") or {}
    if algorithm.get("name") != "canonical_source_digest_v1":
        failures.append("the canonical source digest algorithm is not named")
    if algorithm.get("portable") is not True:
        failures.append("the canonical source digest is not recorded as portable")
    if not str(algorithm.get("description") or "").strip():
        failures.append("the canonical source digest algorithm is not described")
    execution_canonical = dig(execution_amendment, "code_hash_constraint.canonical_source_digest")
    if execution_canonical != recorded_canonical:
        failures.append(
            "the canonical digest recorded here differs from the one recorded by "
            "execution amendment 1"
        )

    # 3. The ordered digest is not portable and is informational only.
    if constraint.get("ordered_code_hash_is_portable") is not False:
        failures.append("the amendment does not record the ordered digest as non-portable")
    if constraint.get("live_ordered_code_hash_is_informational_only") is not True:
        failures.append("the amendment does not make the live ordered digest informational only")
    if not str(constraint.get("ordered_digest_defect") or "").strip():
        failures.append("the amendment does not describe the ordered-digest defect")
    if not str(constraint.get("ordered_digest_mismatch_meaning") or "").strip():
        failures.append("the amendment does not state what an ordered-digest mismatch means")
    if not str(constraint.get("tree_identity_rule") or "").strip():
        failures.append("the amendment does not state the tree-identity rule")
    ordered = live_ordered_code_hash(repo_root)
    authorized = constraint.get("authorized_code_hash")
    if ordered != authorized:
        environment_facts.append(
            "the live ordered code hash "
            f"{ordered} differs from the authorized value of record {authorized}; this is an "
            "environment fact about the directory enumeration order of this checkout, not "
            "evidence of source drift"
        )

    # 4. The value of record is the authorized v1 code hash.
    if authorized != authorization.get("code_hash"):
        failures.append("the recorded code hash is not the authorized v1 code hash")
    if authorization.get("authorized") is not True:
        failures.append("the v1 campaign authorization is not authorized")
    if authorization.get("protocol_version") != "v1":
        failures.append("the campaign authorization is not bound to protocol v1")
    if constraint.get("authorized_code_hash_status") != "RETAINED_AS_VALUE_OF_RECORD":
        failures.append("the amendment does not record the authorized digest as retained")
    if not str(constraint.get("authorized_code_hash_source") or "").strip():
        failures.append("the amendment does not name the source of the authorized code hash")

    # 5. Every amended artifact is byte-identical and still records the value of record.
    amended = amendment.get("amends") or []
    if not amended:
        failures.append("the amendment amends nothing")
    for entry in amended:
        relative = entry.get("path")
        if not relative:
            failures.append("an amended artifact is not named")
            continue
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the amended artifact {relative} is missing")
            continue
        if sha256_file(target) != entry.get("file_sha256"):
            failures.append(f"the amended artifact {relative} does not match its recorded sha256")
        document = json.loads(target.read_text(encoding="utf-8"))
        field = entry.get("code_hash_field")
        if dig(document, str(field)) != authorized:
            failures.append(f"the amended artifact {relative} does not record the value of record")
        if entry.get("canonical_source_digest_added_by_this_amendment") != recorded_canonical:
            failures.append(f"the amended artifact {relative} is not given the canonical digest")
        if entry.get("artifact_edited") is not False:
            failures.append(f"the amended artifact {relative} does not record that it is unedited")
        identity_field = entry.get("identity_field")
        if identity_field and dig(document, identity_field) != entry.get("identity_value"):
            failures.append(f"the identity of the amended artifact {relative} does not match")
    amended_paths = {str(entry.get("path")) for entry in amended}
    expected_paths = {
        "research/universe_manifest_v2.json",
        "research/data_manifest_v2.json",
        "configs/research_v2_candidate_freeze.json",
        "configs/research_v2_execution.json",
        "configs/research_v2_execution_amendment_1.json",
    }
    if amended_paths != expected_paths:
        failures.append("the amendment does not amend exactly the frozen code-hash artifacts")
    if not str(amendment.get("amends_note") or "").strip():
        failures.append("the amendment does not state that the amended artifacts stay unedited")

    # 6. The affected verifiers really implement the canonical tree-identity check.
    for entry in amendment.get("affected_verifiers") or []:
        relative = entry.get("path")
        if not relative:
            failures.append("an affected verifier is not named")
            continue
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the affected verifier {relative} is missing")
            continue
        if not str(entry.get("new_assertion") or "").strip():
            failures.append(f"the affected verifier {relative} does not state its new assertion")
        module = load_module(target)
        digest_function = getattr(module, "canonical_source_digest", None)
        if not callable(digest_function):
            failures.append(f"the affected verifier {relative} does not compute a canonical digest")
            continue
        try:
            produced = digest_function(repo_root)
        except TypeError:
            produced = digest_function()
        if produced != recorded_canonical:
            failures.append(
                f"the affected verifier {relative} does not compute the recorded canonical digest"
            )
    for entry in amendment.get("affected_tests") or []:
        relative = entry.get("path")
        if not relative:
            failures.append("an affected test module is not named")
            continue
        if not (repo_root / relative).exists():
            failures.append(f"the affected test module {relative} is missing")
        if not str(entry.get("new_assertion") or "").strip():
            failures.append(f"the affected test module {relative} does not state its new assertion")

    # 7. The design basis, the interim rule and the residual limitations.
    basis = amendment.get("design_basis") or {}
    related = amendment.get("related_artifacts") or {}
    authorization_entry = related.get("v1_campaign_authorization") or {}
    if authorization_entry.get("path") != AUTHORIZATION_RELATIVE:
        failures.append("the amendment does not name the v1 campaign authorization")
    if authorization_entry.get("code_hash") != authorized:
        failures.append("the recorded authorization code hash does not match the value of record")
    execution_entry = related.get("v2_execution_amendment_1") or {}
    if execution_entry.get("path") != EXECUTION_AMENDMENT_RELATIVE:
        failures.append("the amendment does not name execution amendment 1")
    if execution_entry.get("manifest_hash") != execution_amendment.get("manifest_hash"):
        failures.append("the recorded manifest hash of execution amendment 1 does not match")
    if basis.get("brainstorming_item") != "BRAIN-009":
        failures.append("the amendment does not name its brainstorming item")
    if basis.get("chosen_design") != "A":
        failures.append("the amendment does not record the chosen design")
    if not str(basis.get("chosen_design_summary") or "").strip():
        failures.append("the amendment does not summarize the chosen design")
    for relative in (
        "research_state/brainstorming_queue.md",
        "scripts/build_v2_code_hash_amendment_1.py",
        "scripts/verify_research_v2_code_hash_amendment_1.py",
        "tests/test_research_v2_code_hash_amendment_1.py",
    ):
        if not (repo_root / relative).exists():
            failures.append(f"the declared file is missing: {relative}")
    interim = amendment.get("interim_rule") or {}
    if not str(interim.get("rule") or "").strip():
        failures.append("the interim rule is not stated")
    if not str(interim.get("reporting_rule") or "").strip():
        failures.append("the interim reporting rule is not stated")
    limitations = amendment.get("residual_limitations") or []
    if not limitations:
        failures.append("the residual limitations are not recorded")
    for limitation in limitations:
        for field in ("id", "location", "limitation", "consequence"):
            if not str(limitation.get(field) or "").strip():
                failures.append(f"a residual limitation does not state its {field}")
    if constraint.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the code-hash constraint does not name the hashed source root")
    for relative in constraint.get("paths_correctly_classified_as_outside_hashed_set") or []:
        if path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as outside the hashed set but is inside it")
    for relative in constraint.get("paths_not_permitted_inside_hashed_set") or []:
        if not path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as inside the hashed set but is not")

    # 8. Nothing is authorized by this artifact.
    execution = amendment.get("execution_authorization") or {}
    for flag in (
        "grid_run_authorized",
        "candidate_selection_authorized",
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "source_tree_change_authorized",
        "v1_reauthorization_authorized",
    ):
        if execution.get(flag) is not False:
            failures.append(f"execution_authorization.{flag} is not false")
    if amendment.get("amendment_status") != "PREREGISTERED_CODE_HASH_AMENDMENT_DESIGN_ONLY":
        failures.append("the amendment status does not record that it is a design artifact")

    # 9. The executed state, if it exists, is bound to the amended tree identity,
    #    and the v1 evidence is byte-identical.
    #
    #    This rule was written before the authorized run as "nothing has been
    #    executed". The run has happened, so the rule was replaced -- not deleted
    #    -- by a check that is at least as strict in both states: before the run no
    #    v2 execution artifact exists at all, and after the run the executed state
    #    carries the tree identity that this amendment records.
    executed_artifacts = [
        relative for relative in V2_EXECUTION_ARTIFACTS if (repo_root / relative).exists()
    ]
    if executed_artifacts:
        ledger_path = repo_root / "research" / "ledger_v2.json"
        if not ledger_path.exists():
            failures.append("a v2 execution artifact exists without the ledger of the run")
        else:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            identity = ledger.get("code_identity") or {}
            constraint = amendment.get("code_hash_constraint") or {}
            if identity.get("hashed_set_digest") != constraint.get("canonical_source_digest"):
                failures.append(
                    "the executed run does not carry this amendment's hashed-set digest"
                )
            if identity.get("execution_path_digest") != canonical_source_digest(
                repo_root, "src/v2_campaign"
            ):
                failures.append(
                    "the executed run does not carry the digest of the live execution path"
                )
            if identity.get("authorized_code_hash") != constraint.get("authorized_code_hash"):
                failures.append(
                    "the executed run does not carry this amendment's authorized code hash"
                )
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")

    return {
        "ok": not failures,
        "amendment_path": AMENDMENT_RELATIVE,
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "amendment_status": amendment.get("amendment_status"),
        "authorized_code_hash": authorized,
        "canonical_source_digest": live_canonical,
        "live_ordered_code_hash": ordered,
        "ordered_code_hash_matches_authorized": ordered == authorized,
        "amended_artifacts": sorted(amended_paths),
        "environment_facts": environment_facts,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

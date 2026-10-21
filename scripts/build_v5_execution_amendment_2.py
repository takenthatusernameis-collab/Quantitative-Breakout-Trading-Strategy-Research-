#!/usr/bin/env python3
"""Build the versioned amendment that corrects the v5 execution authorization block.

``configs/research_v5_execution.json`` and ``configs/research_v5_execution_
amendment_1.json`` both record an ``execution_authorization`` block whose
``selection_authorization_present`` flag is ``false``. That was true at their
publication instants -- the v5 selection authorization had not been created
yet -- and it is stale now: the v5 selection authorization has been published.

The flag was used in two places, and both were wrong:

* the repository verifier refused the repository, because the file on disk
  contradicted the state the frozen protocol recorded;
* the run gate in ``src/v5_campaign/scope.py`` required the recorded state to
  stay ``false``, so a corrected effective rule would have refused the run, and
  the gate never verified that the authorization exists at all.

A published protocol is hash-bound and is not edited in place -- the campaign's
answer to that is a **versioned amendment**, as ``configs/research_v5_candidate_
freeze_amendment_1.json`` and ``configs/research_v5_execution_amendment_1.json``
show. This producer writes ``configs/research_v5_execution_amendment_2.json``:

* it names the artifact it amends by path, by its **recomputed** manifest hash
  and by its **recomputed** file digest, and the amendment whose block it
  supersedes in the same way;
* it states the problem it solves;
* it restates the effective ``execution_authorization`` block, whose values are
  recomputed from the artifact that owns them -- the published selection
  authorization's own manifest hash, file digest, run id and campaign id;
* it states the precedence: the amendment wins for the block it restates, the
  earlier amendment wins for the blocks it restates and this amendment does
  not, the protocol stays on disk unchanged and visible, and the protocol's own
  authority flags stay false.

The producer is deterministic (the creation instant is pinned) and refuses to
overwrite the artifact without ``--force``.

Usage::

    python3 scripts/build_v5_execution_amendment_2.py
    python3 scripts/build_v5_execution_amendment_2.py --force
    python3 scripts/build_v5_execution_amendment_2.py --print
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_RELATIVE = "configs/research_v5_execution_amendment_2.json"

#: The instant at which this amendment is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-21T19:05:00Z"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the amendment is bound to, relative to the repository root.
PROTOCOL_RELATIVE = "configs/research_v5_execution.json"
AMENDMENT_1_RELATIVE = "configs/research_v5_execution_amendment_1.json"
AUTHORIZATION_RELATIVE = "configs/research_v5_selection_authorization_1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _verify_self_hash(document: Dict[str, Any], label: str) -> str:
    """Recompute an artifact's own manifest hash and refuse a mismatch."""
    hashing = document.get("hashing") or {}
    excluded = tuple(hashing.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    declared = document.get("manifest_hash")
    recomputed = compute_manifest_hash(document, excluded)
    if recomputed != declared:
        raise SystemExit(
            f"the manifest hash of {label} does not recompute: recorded {declared}, "
            f"recomputed {recomputed}"
        )
    return str(declared)


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v5 execution amendment 2 from the hash-bound artifacts."""
    root = Path(repo_root)

    protocol = _load(root / PROTOCOL_RELATIVE)
    protocol_hash = _verify_self_hash(protocol, "the v5 execution protocol")

    amendment_1 = _load(root / AMENDMENT_1_RELATIVE)
    amendment_1_hash = _verify_self_hash(amendment_1, "the v5 execution amendment 1")

    authorization = _load(root / AUTHORIZATION_RELATIVE)
    authorization_hash = _verify_self_hash(authorization, "the v5 selection authorization")
    run = authorization.get("authorized_run") or {}
    if run.get("authorized") is not True:
        raise SystemExit("the v5 selection authorization does not authorize a run")

    spec_v5 = _load(root / SPEC_V5_RELATIVE)

    document: Dict[str, Any] = {
        "artifact": "v5_execution_amendment_2",
        "artifact_version": 2,
        "amendment_status": "PUBLISHED_CORRECTION",
        "protocol_version": "v5",
        "universe_version": "v5",
        "created_utc": CREATED_UTC,
        "amends": {
            "file": PROTOCOL_RELATIVE,
            "manifest_hash": protocol_hash,
            "sha256": sha256_file(root / PROTOCOL_RELATIVE),
            "rule": (
                "the v5 execution protocol is hash-bound and is not edited in place; this "
                "amendment supplies the effective execution-authorization block"
            ),
        },
        "supersedes_in_amendment_1": {
            "file": AMENDMENT_1_RELATIVE,
            "manifest_hash": amendment_1_hash,
            "sha256": sha256_file(root / AMENDMENT_1_RELATIVE),
            "block": "execution_authorization",
            "rule": (
                "the v5 execution amendment 1 is hash-bound and is not edited in place; this "
                "amendment supersedes its execution_authorization block and leaves every other "
                "block it restates in force"
            ),
        },
        "problem": {
            "affected_artifact_path": PROTOCOL_RELATIVE,
            "affected_artifact_manifest_hash": protocol_hash,
            "statement": (
                "the frozen v5 execution protocol and the v5 execution amendment 1 both record "
                "execution_authorization.selection_authorization_present = false. That was true "
                "at their publication instants, when the v5 selection authorization did not "
                "exist, and it is stale now: the v5 selection authorization has been published. "
                "The flag was used in two places and both were wrong. The repository verifier "
                "refused the repository, because the file on disk contradicted the state the "
                "frozen protocol recorded. And the run gate in src/v5_campaign/scope.py "
                "required the recorded state to stay false, so a corrected effective rule would "
                "have refused the run and the gate never verified that the authorization "
                "exists at all."
            ),
            "repair": (
                "the protocol and the amendment 1 are hash-bound and are not edited in place; "
                "the effective execution-authorization block is recorded by this amendment, and "
                "the run gate verifies the published selection authorization's identity instead "
                "of a static flag"
            ),
            "historical_statement": (
                "the frozen protocol's and amendment 1's execution_authorization."
                "selection_authorization_present = false records the state of the chain at "
                "their publication instants. Those blocks stay on disk, unchanged and visible."
            ),
        },
        "precedence": {
            "rule": (
                "the effective v5 execution protocol is this amendment for the blocks it "
                "restates, the v5 execution amendment 1 for the blocks it restates and this "
                "amendment does not, and configs/research_v5_execution.json for the blocks no "
                "amendment restates; every artifact stays on disk, unchanged and visible"
            ),
            "resolution_rule": (
                "a verifier or a run gate that reads the v5 evaluation scope, the benchmark "
                "rule, the inherited rules or the execution authorization resolves them through "
                "this amendment when it is present and verified, and fails closed when it is "
                "absent, because the block it supersedes then records that no selection "
                "authorization is present"
            ),
            "superseded": ["execution_authorization"],
            "unchanged": [
                "authorization.execution_authorized",
                "authorization.campaign_authorized",
                "authorization.selection_authorized",
                "authorization.confirmatory_authorized",
                "evaluation_scope",
                "candidate_freeze_and_confirmatory_window",
                "benchmark_rule",
                "code_hash_constraint",
                "inherited_rules",
                "deviation_disclosure",
                "selection_rule.inherit_from_v1_unchanged",
                "resource_and_attempt_bounds",
                "v5_result_layout",
            ],
            "protocol_own_authority_is_unchanged": (
                "the frozen protocol's own authorization block records what the protocol itself "
                "authorizes, and it authorizes nothing: the single bounded v5 selection run is "
                "authorized by the v5 selection authorization named below, and by nothing else"
            ),
        },
        "execution_authorization": {
            "candle_fetch_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "the v5 execution protocol, the v5 execution amendment 1 and this amendment "
                "record the benchmark rule, the inherited rules and the data-manifest identity. "
                "They authorize no run, no evaluation, no candle fetch and no "
                "confirmatory-window read."
            ),
            "second_run_authorized": False,
            "selection_authorization_present": True,
            "selection_authorization_path": AUTHORIZATION_RELATIVE,
            "selection_authorization_manifest_hash": authorization_hash,
            "selection_authorization_sha256": sha256_file(root / AUTHORIZATION_RELATIVE),
            "selection_authorization_run_id": run.get("run_id"),
            "selection_authorization_campaign_id": run.get("campaign_id"),
            "selection_authorization_scope": (
                "exactly one bounded v5 selection grid run over the frozen v5 candidate set, "
                "on development data only, under the unchanged v1 selection rule, writing only "
                "to the v5 paths"
            ),
            "run_gate_rule": (
                "the run gate verifies the named selection authorization: the file must exist, "
                "its manifest hash must recompute, and both the manifest hash and the file "
                "digest must equal the ones recorded here; the gate then validates the "
                "authorization against the frozen scope, the unchanged v1 selection rule and the "
                "current source tree"
            ),
            "historical_statement": (
                "the frozen protocol's and amendment 1's selection_authorization_present = "
                "false records the state of the chain at their publication instants; the "
                "effective state of the chain is the one this block records"
            ),
        },
        "related_artifacts": {
            "v5_execution_protocol": {
                "manifest_hash": protocol_hash,
                "path": PROTOCOL_RELATIVE,
            },
            "v5_execution_amendment_1": {
                "manifest_hash": amendment_1_hash,
                "path": AMENDMENT_1_RELATIVE,
            },
            "v5_selection_authorization": {
                "manifest_hash": authorization_hash,
                "path": AUTHORIZATION_RELATIVE,
            },
            "v5_specification": {
                "path": SPEC_V5_RELATIVE,
                "specification_hash": spec_v5.get("specification_hash"),
            },
        },
        "verification": {
            "verifier_script": "scripts/verify_v5_execution.py",
            "tests_module": "tests/test_v5_execution.py",
            "verify_command": "python3 scripts/verify_v5_execution.py",
            "run_gate": "src/v5_campaign/scope.py:verify_execution_protocol",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "following the pattern of the other v2, v3, v4 and v5 artifacts."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the artifact and write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    document = build(repo_root)
    if args.print_only:
        print(json.dumps(document, indent=2, ensure_ascii=False))
        return 0

    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(
            json.dumps({
                "status": "REFUSED",
                "error": f"{ARTIFACT_RELATIVE} already exists; pass --force to rewrite it",
            }),
            file=sys.stderr,
        )
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)
    print(f"wrote {ARTIFACT_RELATIVE} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

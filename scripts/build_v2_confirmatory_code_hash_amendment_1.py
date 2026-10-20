#!/usr/bin/env python3
"""Build the versioned code-hash amendment of the v2 confirmatory path.

The independent audit of the delivered confirmatory path (BRAIN-011 §12,
finding 1, severity P0) found an unreachable duplicate rollback block in
``src/v2_confirmatory/runner.py``: a second copy of the rollback statements
that follows the ``raise`` of the same ``except`` handler, so no control path
reaches it. The block is dead code and removing it changes no behaviour.

The execution path is hash-bound: the authorization, the runbook and the
amendment chain record its canonical digest. The block may therefore **not** be
removed in place without breaking those bindings. This artifact is the
versioned remedy:

* it records the rotation -- the digest the authorization and the runbook
  recorded, and the digest of the corrected tree -- together with the composite
  run identity of both;
* it records the change itself: the file, the removed block verbatim, the fact
  that the block was unreachable, and that the removal has no behavioural
  effect;
* it records that the hashed set ``src/breakout_research`` is **unchanged**;
* it names the two artifacts that carry the superseded digest and states that
  they are **not edited**: the rotation is carried by reference, exactly as
  ``configs/research_v2_code_hash_amendment_1.json`` carries the portable
  canonical digest;
* it records the rule by which the effective identity is resolved from now on,
  and the correction of a factual claim of the audit (the confirmatory
  protocol and its criterion amendment do **not** bind the execution-path
  digest).

The artifact authorizes nothing: no candle read, no evaluation, no second run.
It is a design deliverable that repairs the binding before the single-use
confirmatory window is read.

The script is deterministic: every field is derived from artifacts that are
already hash-bound and from the tree itself, so re-running it reproduces the
same bytes. It never fetches anything, never reads a candle and never runs an
evaluation.

Usage::

    python3 scripts/build_v2_confirmatory_code_hash_amendment_1.py            # write
    python3 scripts/build_v2_confirmatory_code_hash_amendment_1.py --force    # rewrite
    python3 scripts/build_v2_confirmatory_code_hash_amendment_1.py --print    # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_RELATIVE = "configs/research_v2_confirmatory_code_hash_amendment_1.json"

#: The instant at which the amendment was written. Pinned so the artifact is
#: byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T11:20:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_confirmatory"

AUTHORIZATION_RELATIVE = "configs/research_v2_confirmatory_authorization_1.json"
RUNBOOK_RELATIVE = "configs/research_v2_confirmatory_runbook_1.json"
PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
PROTOCOL_AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_protocol_amendment_1.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v2_selected_configurations_manifest.json"
RUNNER_RELATIVE = "src/v2_confirmatory/runner.py"

#: The digest the authorization and the runbook record: the identity of the
#: execution path *before* the dead code was removed. It is the value of
#: record of the superseded binding.
PREVIOUS_EXECUTION_PATH_DIGEST = (
    "fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10"
)
PREVIOUS_RUN_CODE_IDENTITY = (
    "fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8"
)

#: The hashed set is not touched by this amendment. Its canonical digest is
#: the one the code-hash amendment 1 recorded.
HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)

#: The authorized, checkout-dependent ordered digest. It is the value of
#: record of the v1 campaign and is never an identity (BRAIN-009).
AUTHORIZED_ORDERED_CODE_HASH = (
    "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
)

#: The unreachable block that was removed from ``src/v2_confirmatory/runner.py``,
#: verbatim. It followed the ``raise`` of the same ``except`` handler.
REMOVED_BLOCK_TEXT = (
    "        for path in created_files:\n"
    "            if path.exists():\n"
    "                path.unlink()\n"
    "        for path in created_dirs:\n"
    "            shutil.rmtree(path, ignore_errors=True)\n"
    "        raise\n"
)

#: The lines the removed block occupied in the pre-rotation file.
REMOVED_LINE_RANGE = [1039, 1044]

#: The sha256 of the pre-rotation runner file (the file as the audit read it).
PRE_ROTATION_RUNNER_SHA256 = (
    "6341979babe8fbdc112f883bede4a1c67cc8a1c100e12d5e9749eb050ab4084d"
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


def _load(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build(repo_root: Path) -> Dict[str, Any]:
    """Build the amendment from the tree and the hash-bound artifacts."""
    root = Path(repo_root)

    from v2_confirmatory import identity  # the single implementation of the rule

    live_hashed_set = identity.canonical_source_digest(root / HASHED_SET_ROOT)
    live_execution_path = identity.canonical_source_digest(root / EXECUTION_PATH_ROOT)
    live_composite = identity.run_code_identity(live_hashed_set, live_execution_path)

    if live_hashed_set != HASHED_SET_DIGEST:
        raise SystemExit(
            "refusing to build: the hashed set's canonical digest is "
            f"{live_hashed_set}, not the recorded {HASHED_SET_DIGEST}; the hashed set "
            "may never change"
        )
    if live_execution_path == PREVIOUS_EXECUTION_PATH_DIGEST:
        raise SystemExit(
            "refusing to build: the execution path still carries the pre-rotation digest; "
            "there is nothing to rotate"
        )

    authorization = _load(root / AUTHORIZATION_RELATIVE)
    runbook = _load(root / RUNBOOK_RELATIVE)
    protocol = _load(root / PROTOCOL_RELATIVE)
    protocol_amendment = _load(root / PROTOCOL_AMENDMENT_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)

    recorded_authorization_identity = (
        (authorization.get("authorized_run") or {}).get("code_identity") or {}
    )
    recorded_runbook_identity = (runbook.get("binding_identities") or {}).get(
        "code_identity"
    ) or {}
    for name, recorded in (
        ("authorization", recorded_authorization_identity),
        ("runbook", recorded_runbook_identity),
    ):
        if recorded.get("execution_path_digest") != PREVIOUS_EXECUTION_PATH_DIGEST:
            raise SystemExit(
                f"refusing to build: the {name} does not record the pre-rotation digest "
                f"{PREVIOUS_EXECUTION_PATH_DIGEST}"
            )
        if recorded.get("run_code_identity") != PREVIOUS_RUN_CODE_IDENTITY:
            raise SystemExit(
                f"refusing to build: the {name} does not record the pre-rotation composite "
                f"identity {PREVIOUS_RUN_CODE_IDENTITY}"
            )

    document: Dict[str, Any] = {
        "artifact": "research_v2_confirmatory_code_hash_amendment_1",
        "artifact_version": 1,
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "amendment_status": "DELIVERED_PENDING_COMMIT",
        "specification_purpose": (
            "Rotate the confirmatory execution path's canonical digest after the unreachable "
            "duplicate rollback block of src/v2_confirmatory/runner.py was removed, and carry "
            "the rotation by reference so that no frozen artifact is edited."
        ),
        "amends": {
            "confirmatory_authorization_1": {
                "path": AUTHORIZATION_RELATIVE,
                "manifest_hash": authorization.get("manifest_hash"),
                "file_sha256": sha256_file(root / AUTHORIZATION_RELATIVE),
                "superseded_code_identity_field": "authorized_run.code_identity",
                "recorded_execution_path_digest": PREVIOUS_EXECUTION_PATH_DIGEST,
                "recorded_run_code_identity": PREVIOUS_RUN_CODE_IDENTITY,
                "edited": False,
            },
            "confirmatory_runbook_1": {
                "path": RUNBOOK_RELATIVE,
                "manifest_hash": runbook.get("manifest_hash"),
                "file_sha256": sha256_file(root / RUNBOOK_RELATIVE),
                "superseded_code_identity_field": "binding_identities.code_identity",
                "recorded_execution_path_digest": PREVIOUS_EXECUTION_PATH_DIGEST,
                "recorded_run_code_identity": PREVIOUS_RUN_CODE_IDENTITY,
                "edited": False,
            },
        },
        "code_hash_rotation": {
            "algorithm": identity.CANONICAL_DIGEST_ALGORITHM,
            "hashed_set_root": HASHED_SET_ROOT,
            "hashed_set_digest": live_hashed_set,
            "hashed_set_unchanged": True,
            "execution_path_root": EXECUTION_PATH_ROOT,
            "previous_execution_path_digest": PREVIOUS_EXECUTION_PATH_DIGEST,
            "execution_path_digest": live_execution_path,
            "previous_run_code_identity": PREVIOUS_RUN_CODE_IDENTITY,
            "run_code_identity": live_composite,
            "authorized_ordered_code_hash": AUTHORIZED_ORDERED_CODE_HASH,
            "ordered_code_hash_is_an_environment_fact": True,
            "the_only_binding_that_changes": "the confirmatory execution path's digest",
        },
        "change": {
            "audit_finding": "BRAIN-011 §12, finding 1 (severity P0)",
            "file": RUNNER_RELATIVE,
            "kind": "REMOVAL_OF_UNREACHABLE_DEAD_CODE",
            "removed_line_range_in_the_pre_rotation_file": REMOVED_LINE_RANGE,
            "removed_block_text": REMOVED_BLOCK_TEXT,
            "removed_block_sha256": hashlib.sha256(
                REMOVED_BLOCK_TEXT.encode("utf-8")
            ).hexdigest(),
            "pre_rotation_file_sha256": PRE_ROTATION_RUNNER_SHA256,
            "post_rotation_file_sha256": sha256_file(root / RUNNER_RELATIVE),
            "the_removed_block_was_unreachable": True,
            "unreachability_proof": (
                "The block followed the raise statement of the same except handler, so no "
                "control path reaches it; it duplicated the rollback statements that run "
                "before that raise."
            ),
            "behavioural_change": False,
            "behavioural_change_proof": (
                "Only unreachable statements were removed, so every reachable statement, every "
                "write, every abort path and every exposure rule is unchanged."
            ),
            "reason": (
                "The audit found the block and refused an in-place edit, because the execution "
                "path's digest is bound by the authorization and the runbook."
            ),
        },
        "precedence": {
            "rule": (
                "Where an amended artifact records a code identity that differs from this "
                "amendment, this amendment governs the code-identity fields only; every other "
                "field of the amended artifacts stands unchanged."
            ),
            "overridden_fields": [
                "authorized_run.code_identity",
                "binding_identities.code_identity",
            ],
            "every_other_field_of_the_amended_artifacts_stands": True,
            "the_amended_artifacts_are_edited_in_place": False,
            "the_amended_artifacts_remain_byte_identical": True,
            "the_authorization_still_permits_at_most_one_logical_run": True,
        },
        "corrections": [
            {
                "claim": (
                    "the confirmatory protocol and its criterion amendment bind the confirmatory "
                    "execution path's digest"
                ),
                "verdict": "FALSE",
                "evidence": (
                    "Neither configs/research_v2_confirmatory_protocol.json nor "
                    "configs/research_v2_confirmatory_protocol_amendment_1.json records an "
                    "execution-path digest: their code-hash constraint covers the hashed set "
                    "src/breakout_research only. The audit's attribution was one file too wide; "
                    "the artifacts that bind the execution-path digest are the authorization "
                    "and the runbook."
                ),
                "affected_artifacts": [PROTOCOL_RELATIVE, PROTOCOL_AMENDMENT_RELATIVE],
                "corrected_by": "this amendment; neither artifact is edited",
            }
        ],
        "resolution_rule": {
            "where_the_rule_lives": "src/v2_confirmatory/identity.py:resolve_code_identity",
            "rule": (
                "The effective execution-path digest is the digest the authorization records "
                "when the tree is still the tree the authorization froze; otherwise it is the "
                "digest this amendment records, and only when this amendment hash-verifies and "
                "binds the current tree."
            ),
            "checks": [
                "the hashed set's canonical digest equals the recorded one; the hashed set may "
                "never change",
                "the recorded execution-path digest equals the live one, or this amendment "
                "rotates exactly that digest to the live one",
                "the recorded composite run identity equals the composite of the two live "
                "digests",
                "the amendment's own manifest hash recomputes",
            ],
            "a_mismatch_is_never_an_environment_fact": (
                "The checkout-dependent ordered digest compute_code_hash() is an environment "
                "fact and is never an identity; a canonical-digest mismatch is a real drift "
                "and refuses the run."
            ),
        },
        "authorizes_a_candle_read": False,
        "authorizes_an_evaluation": False,
        "authorizes_a_second_run": False,
        "authorizes_a_code_change": False,
        "authorizes_anything": False,
        "related_artifacts": {
            "confirmatory_authorization_1": {
                "path": AUTHORIZATION_RELATIVE,
                "manifest_hash": authorization.get("manifest_hash"),
            },
            "confirmatory_runbook_1": {
                "path": RUNBOOK_RELATIVE,
                "manifest_hash": runbook.get("manifest_hash"),
            },
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "confirmatory_protocol_amendment_1": {
                "path": PROTOCOL_AMENDMENT_RELATIVE,
                "manifest_hash": protocol_amendment.get("manifest_hash"),
            },
            "code_hash_amendment_1": {
                "path": CODE_HASH_AMENDMENT_RELATIVE,
                "manifest_hash": code_hash_amendment.get("manifest_hash"),
            },
            "v2_specification": {
                "path": SPEC_V2_RELATIVE,
                "specification_hash": spec_v2.get("specification_hash"),
            },
            "v2_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": selected.get("manifest_hash"),
            },
        },
        "durability": {
            "rule": (
                "The amendment takes effect when this artifact is committed. No "
                "confirmatory-window candle may be read before the commit that carries this "
                "artifact, the authorization and the runbook exists."
            ),
            "amendment_commit": None,
            "amendment_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v2_confirmatory_code_hash_amendment_1.py",
            "verify_command": "python3 scripts/verify_v2_confirmatory_code_hash_amendment_1.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, so the document does not hash itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

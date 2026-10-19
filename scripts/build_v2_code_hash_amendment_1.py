#!/usr/bin/env python3
"""Build the preregistered v2 code-hash amendment 1 (BRAIN-009).

``compute_code_hash()`` (``src/breakout_research/config.py``) hashes every
``*.py`` file under ``src/breakout_research`` recursively, but it visits the
directories in **filesystem enumeration order**. The digest it returns is
therefore an identity of *this checkout's directory layout*, not of the source
tree: the same git-clean tree yields a different digest on a machine whose
directory order differs.

This producer writes a versioned, hash-bound design artifact that

* adds the portable tree identity -- ``canonical_source_digest``, a sha256 over
  the POSIX relative path and the content digest of every ``*.py`` file under
  the hashed set, in ascending path order -- to the frozen v2 artifacts,
  **without editing any of them**;
* retains the historical ordered digest as the authorized value of record, so
  the v1 campaign authorization stays valid and no v2 identity tuple has to
  change;
* states the tree-identity rule the verifiers and tests must perform from now
  on, and records the residual limitation that the v1 campaign runtime gate
  (inside the hashed set) still compares the live ordered digest.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed set, never touches a
frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v2_code_hash_amendment_1.py            # write the artifact
    python3 scripts/build_v2_code_hash_amendment_1.py --force    # rewrite it
    python3 scripts/build_v2_code_hash_amendment_1.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

#: The instant at which this amendment is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-19T23:31:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"

#: The frozen v2 artifacts that carry a code-hash identity field, with the
#: dotted path of that field. The amendment adds the canonical digest to each
#: of them by reference; none of them is edited.
FROZEN_CODE_HASH_ARTIFACTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("research/universe_manifest_v2.json", ("snapshot_identity", "code_hash")),
    ("research/data_manifest_v2.json", ("snapshot_identity", "code_hash")),
    ("configs/research_v2_candidate_freeze.json", ("snapshot_identity", "code_hash")),
    (
        "configs/research_v2_execution.json",
        ("code_hash_constraint", "authorized_code_hash"),
    ),
    (
        "configs/research_v2_execution_amendment_1.json",
        ("code_hash_constraint", "authorized_code_hash"),
    ),
)

#: The artifact that holds the authorized value of record.
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"


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


def _dig(document: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    current: Any = document
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the code-hash amendment from the hash-bound artifacts."""
    authorization = _load(repo_root / AUTHORIZATION_RELATIVE)
    authorized_code_hash = authorization["code_hash"]
    canonical_digest = canonical_source_digest(repo_root)

    amended: List[Dict[str, Any]] = []
    for relative, field_path in FROZEN_CODE_HASH_ARTIFACTS:
        target = repo_root / relative
        document = _load(target)
        recorded = _dig(document, field_path)
        if recorded is None:
            raise SystemExit(f"{relative} does not record a code hash at {'.'.join(field_path)}")
        if recorded != authorized_code_hash:
            raise SystemExit(
                f"{relative} records a code hash that is not the authorized value of record"
            )
        entry: Dict[str, Any] = {
            "path": relative,
            "file_sha256": sha256_file(target),
            "code_hash_field": ".".join(field_path),
            "recorded_code_hash": recorded,
            "canonical_source_digest_added_by_this_amendment": canonical_digest,
            "artifact_edited": False,
        }
        identity_key = "manifest_hash" if "manifest_hash" in document else "specification_hash"
        if identity_key in document:
            entry["identity_field"] = identity_key
            entry["identity_value"] = document[identity_key]
        amended.append(entry)

    document: Dict[str, Any] = {
        "artifact": "v2_code_hash_amendment",
        "artifact_version": "v2-code-hash-amendment-1",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "amendment_status": "PREREGISTERED_CODE_HASH_AMENDMENT_DESIGN_ONLY",
        "specification_purpose": (
            "Make the code-hash binding of the hashed source set portable. It adds the "
            "canonical source digest to the frozen v2 artifacts by reference, retains the "
            "historical ordered digest as the authorized value of record, and fixes the "
            "tree-identity check that the verifiers and tests must perform. This artifact "
            "edits no frozen artifact, authorizes nothing, runs nothing and reads no candle."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-009",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-009",
            "chosen_design": "A",
            "chosen_design_summary": (
                "Retain the authorized ordered digest as the value of record and add the "
                "portable canonical digest by versioned amendment. The alternatives -- "
                "rotating compute_code_hash() and re-authorizing the v1 campaign, or "
                "dropping the code-hash binding -- were rejected: the first is "
                "disproportionate because the canonical digest already identifies the tree "
                "portably, the second removes the guarantee the campaign depends on."
            ),
            "supersedes_none": (
                "No artifact is superseded by this amendment. The frozen v2 artifacts are "
                "extended by reference and stay byte-identical."
            ),
        },
        "code_hash_constraint": {
            "hashed_set_root": HASHED_SET_ROOT,
            "hashed_set_rule": (
                "compute_code_hash() (src/breakout_research/config.py) walks every .py file "
                "under src/breakout_research recursively. Any file added, edited or removed "
                "there changes the code hash and invalidates the v1 campaign authorization "
                "recorded in research_state/campaign_authorization.json."
            ),
            "authorized_code_hash": authorized_code_hash,
            "authorized_code_hash_source": (
                "research_state/campaign_authorization.json (protocol_version v1, authorized true)"
            ),
            "authorized_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
            "authorized_code_hash_note": (
                "The ordered digest stays the authorized value of record. It is not rotated, "
                "because rotating it would require changes to "
                "research_state/campaign_authorization.json, research_state/checkpoint.json "
                "and every v2 identity tuple, and would invalidate the v1 campaign "
                "authorization for no gain: the canonical digest already identifies the tree "
                "portably."
            ),
            "canonical_source_digest": canonical_digest,
            "canonical_source_digest_algorithm": {
                "name": "canonical_source_digest_v1",
                "description": (
                    "sha256 over the concatenation, for every *.py file under "
                    "src/breakout_research in ascending POSIX relative-path order, of the "
                    "relative path, a newline, the sha256 hex digest of the file bytes, and "
                    "a newline."
                ),
                "portable": True,
                "purpose": (
                    "the portable identity of the hashed source tree; unlike "
                    "compute_code_hash() it does not depend on the directory enumeration "
                    "order of the checkout"
                ),
            },
            "ordered_code_hash_is_portable": False,
            "ordered_digest_defect": (
                "compute_code_hash() sorts the files inside each directory but visits the "
                "directories in filesystem enumeration order. The authorized digest is "
                "reproduced only under the traversal order (indicators, utils, signals, "
                "data, backtest); a checkout that enumerates the same git-clean tree in a "
                "different order yields a different digest."
            ),
            "live_ordered_code_hash_is_informational_only": True,
            "ordered_digest_mismatch_meaning": (
                "A mismatch between the live ordered digest and the authorized value of "
                "record is an environment fact about the checkout's directory order, not "
                "evidence of source drift. It must be reported, never silently absorbed and "
                "never 'fixed' by editing the hashed set."
            ),
            "tree_identity_rule": (
                "The identity of the hashed source set is checked by recomputing the "
                "canonical source digest from the tree and comparing it with the canonical "
                "digest recorded in this amendment. The recorded ordered digest is "
                "cross-checked against research_state/campaign_authorization.json "
                "code_hash. The live ordered digest is reported but never compared as a "
                "drift signal."
            ),
            "v2_execution_code_must_live_outside_the_hashed_set": True,
            "paths_correctly_classified_as_outside_hashed_set": ["scripts/", "src/v2_campaign/"],
            "paths_not_permitted_inside_hashed_set": [
                "src/breakout_research/",
                "src/breakout_research/v2/",
                "src/breakout_research/v2/**.py",
            ],
        },
        "amends": amended,
        "amends_note": (
            "Each entry names a frozen v2 artifact, the code-hash field it records and the "
            "canonical source digest this amendment adds to it by reference. No entry is "
            "written back into the artifact: every file named above stays byte-identical, "
            "and the file_sha256 in each entry is the digest that proves it."
        ),
        "affected_verifiers": [
            {
                "path": "scripts/verify_research_v2_manifests.py",
                "new_assertion": (
                    "recompute the canonical source digest from the tree and compare it with "
                    "the canonical digest recorded here; cross-check the manifest's "
                    "snapshot_identity.code_hash against "
                    "research_state/campaign_authorization.json code_hash; report a live "
                    "ordered-digest mismatch as an environment fact instead of a failure"
                ),
            },
            {
                "path": "scripts/verify_research_v2_candidate_freeze.py",
                "new_assertion": (
                    "recompute the canonical source digest from the tree and compare it with "
                    "the canonical digest recorded here; cross-check the freeze's "
                    "snapshot_identity.code_hash against "
                    "research_state/campaign_authorization.json code_hash; report a live "
                    "ordered-digest mismatch as an environment fact instead of a failure"
                ),
            },
            {
                "path": "scripts/build_v2_candidate_freeze.py",
                "new_assertion": (
                    "derive the frozen identity's code_hash from the authorized value of "
                    "record instead of recomputing the checkout-dependent ordered digest, so "
                    "that the artifact it produces is portable; it must never recompute the "
                    "ordered digest as an identity"
                ),
            },
            {
                "path": "scripts/verify_research_v2_code_hash_amendment_1.py",
                "new_assertion": (
                    "verify this amendment: recompute its manifest hash, recompute the "
                    "canonical digest from the tree, recompute the file digest of every "
                    "amended artifact, and confirm the value of record is the authorized "
                    "one"
                ),
            },
        ],
        "affected_tests": [
            {
                "path": "tests/test_research_v2_manifests.py",
                "new_assertion": (
                    "the snapshot identity's code_hash is the authorized value of record and "
                    "the tree's canonical digest matches the recorded canonical digest"
                ),
            },
            {
                "path": "tests/test_research_v2_candidate_freeze.py",
                "new_assertion": (
                    "the freeze's code hash is the authorized value of record and the tree's "
                    "canonical digest matches the recorded canonical digest"
                ),
            },
            {
                "path": "tests/test_research_v2_spec.py",
                "new_assertion": (
                    "the v1 campaign authorization carries the authorized value of record and "
                    "the tree's canonical digest matches the recorded canonical digest"
                ),
            },
            {
                "path": "tests/test_research_v2_code_hash_amendment_1.py",
                "new_assertion": (
                    "this amendment is self-hashing, amends exactly the frozen artifacts it "
                    "names, and the tree-identity check survives a perturbed directory "
                    "enumeration order while the ordered digest does not"
                ),
            },
        ],
        "interim_rule": {
            "rule": (
                "src/breakout_research/ must not be edited to make a red ordered-digest "
                "comparison green: that would change the hashed set, change the code hash and "
                "invalidate the v1 campaign authorization and every v2 identity tuple."
            ),
            "reporting_rule": (
                "A red ordered-digest comparison is reported as an environment fact about the "
                "checkout's directory enumeration order, with the evidence of the order that "
                "was observed -- not as source drift."
            ),
        },
        "residual_limitations": [
            {
                "id": "RL1",
                "location": "src/breakout_research/campaign.py (_verify_pilot_gate) and "
                "src/breakout_research/pilot_gate_validator.py",
                "limitation": (
                    "the v1 campaign runtime gate compares the live ordered code hash with "
                    "research_state/campaign_authorization.json code_hash. It is inside the "
                    "hashed set and this amendment deliberately does not change it."
                ),
                "consequence": (
                    "the v1 campaign can only start on a checkout whose directory "
                    "enumeration order reproduces the authorized ordered digest. On any other "
                    "checkout the campaign refuses to start. That is a false drift signal "
                    "and must be reported as an environment fact; correcting it would "
                    "require rotating compute_code_hash() and re-authorizing the v1 "
                    "campaign, which this amendment does not do."
                ),
            }
        ],
        "execution_authorization": {
            "grid_run_authorized": False,
            "candidate_selection_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "source_tree_change_authorized": False,
            "v1_reauthorization_authorized": False,
            "statement": (
                "This artifact authorizes nothing. It records a corrected tree-identity "
                "rule and extends the frozen v2 artifacts by reference. It does not change "
                "the hashed set, does not re-authorize the v1 campaign and does not permit "
                "any v2 run."
            ),
        },
        "related_artifacts": {
            "v1_campaign_authorization": {
                "path": AUTHORIZATION_RELATIVE,
                "code_hash": authorized_code_hash,
                "note": (
                    "The functional field of the authorization is recorded, not the digest of "
                    "its bytes: the controller refreshes the authorized_at_utc timestamp, so "
                    "the file digest changes without the authorization changing. The verifier "
                    "recomputes the code hash from the file and compares it with the value "
                    "recorded here."
                ),
            },
            "v2_execution_amendment_1": {
                "path": "configs/research_v2_execution_amendment_1.json",
                "manifest_hash": _load(
                    repo_root / "configs" / "research_v2_execution_amendment_1.json"
                )["manifest_hash"],
                "note": (
                    "this amendment restates the tree-identity rule of the code_hash_constraint "
                    "block of execution amendment 1; the two must record the same canonical "
                    "digest, which the verifier checks"
                ),
            },
        },
        "producer": {
            "path": "scripts/build_v2_code_hash_amendment_1.py",
            "verify_command": "python3 scripts/verify_research_v2_code_hash_amendment_1.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "following the pattern of the other v2 artifacts."
            ),
        },
    }

    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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

    target = repo_root / "configs" / "research_v2_code_hash_amendment_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the v3 specification amendment 1 (correction of a stale reference).

``configs/research_v3.json`` is immutable and hash-bound, but one nested field
of it was copied from the v2 specification and never updated:
``universe.eligibility_validation.data_integrity.data_manifest`` names
``research/data_manifest_v2.json`` instead of the v3 data manifest that the
BRAIN-012 P2/P3 validation produced.

The established pattern of this repository is that an immutable specification
is never edited in place: the correction is carried by a versioned amendment
that records it by reference (v2: ``configs/research_v2_spec_amendment_1.json``
-> ``configs/research_v2_prerequisite_reconciliation_amendment_1.json``).

The script is deterministic (the creation instant is pinned), recomputes every
digest from the files on disk, refuses to overwrite an existing artifact
without ``--force`` and never writes to the hashed set, never edits the
immutable specification, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v3_spec_amendment_1.py            # write
    python3 scripts/build_v3_spec_amendment_1.py --force    # rewrite
    python3 scripts/build_v3_spec_amendment_1.py --print     # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_spec_amendment_1.json"

SPEC_RELATIVE = "configs/research_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"

#: The instant at which this amendment is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-20T12:55:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The corrected field and the value the immutable specification records.
STALE_FIELD = "universe.eligibility_validation.data_integrity.data_manifest"
STALE_VALUE = "research/data_manifest_v2.json"
EFFECTIVE_VALUE = "research/data_manifest_v3.json"


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


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.",
            suffix=".tmp", delete=False, newline=""
        ) as handle:
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)
    freeze = read_json(repo_root / FREEZE_RELATIVE)
    freeze_amendment = read_json(repo_root / FREEZE_AMENDMENT_RELATIVE)

    integrity = (spec["universe"]["eligibility_validation"]
                 .get("data_integrity", {}))
    recorded = integrity.get("data_manifest")
    if recorded != STALE_VALUE:
        raise SystemExit(
            f"the immutable specification records {recorded!r} for {STALE_FIELD}; this "
            "amendment corrects a stale reference and must not be rebuilt against a "
            "specification that no longer holds it"
        )
    if not (repo_root / EFFECTIVE_VALUE).exists():
        raise SystemExit(f"the corrected data manifest does not exist: {EFFECTIVE_VALUE}")

    document: Dict[str, Any] = {
        "artifact": "v3_spec_amendment",
        "artifact_version": "v3-spec-amendment-1",
        "created_utc": CREATED_UTC,
        "amendment_status": "PUBLISHED_CORRECTION_NO_AUTHORIZATION",
        "description": (
            "Versioned amendment correcting one stale reference of the immutable v3 "
            "specification and recording the delivered prerequisite status by reference."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-012",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-012 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "immutable_specification_is_not_edited": True,
            "pattern": (
                "the repository's established pattern: a hash-bound specification is never "
                "edited in place, a versioned amendment records the correction by reference"
            ),
        },
        "immutable_specification": {
            "path": SPEC_RELATIVE,
            "specification_hash": spec.get("specification_hash"),
            "file_sha256": sha256_file(repo_root / SPEC_RELATIVE),
        },
        "corrections": [
            {
                "id": "C1",
                "path": STALE_FIELD,
                "recorded_value": recorded,
                "effective_value": EFFECTIVE_VALUE,
                "cause": (
                    "the eligibility-validation block was copied from the v2 specification "
                    "when the v3 specification was written, and the data-manifest reference "
                    "was not updated to the v3 artifact"
                ),
                "effect": (
                    "the v3 data-integrity rule refers to the v3 data manifest, the artifact "
                    "the BRAIN-012 P2/P3 validation produced; every other field of the block "
                    "(hash_verified, provenance, survivorship_and_adjustment_policy) is "
                    "unchanged and keeps the value the immutable specification records"
                ),
                "evidence": {
                    "path": EFFECTIVE_VALUE,
                    "manifest_hash": data.get("manifest_hash"),
                    "file_sha256": sha256_file(repo_root / EFFECTIVE_VALUE),
                },
            }
        ],
        "reconciliation": {
            "note": (
                "configs/research_v3.json is immutable and hash-verified; its own P2, P3 and "
                "P4 fields remain OUTSTANDING in the file. This amendment records the "
                "delivered status by reference only, exactly as "
                "configs/research_v2_spec_amendment_1.json does for the v2 specification."
            ),
            "P1": {"status_recorded": "SATISFIED_BY_THIS_SPEC",
                   "evidence": SPEC_RELATIVE},
            "P2": {"status_recorded": "DELIVERED",
                   "evidence": UNIVERSE_RELATIVE,
                   "manifest_hash": universe.get("manifest_hash")},
            "P3": {"status_recorded": "DELIVERED",
                   "evidence": DATA_RELATIVE,
                   "manifest_hash": data.get("manifest_hash")},
            "P4": {"status_recorded": "DELIVERED",
                   "evidence": FREEZE_RELATIVE,
                   "manifest_hash": freeze.get("manifest_hash"),
                   "amendment": FREEZE_AMENDMENT_RELATIVE,
                   "amendment_manifest_hash": freeze_amendment.get("manifest_hash")},
            "P5": {"status_recorded": "OUTSTANDING",
                   "note": "the v3 execution protocol and the bounded run authorization "
                           "are not delivered"},
            "P6": {"status_recorded": "OUTSTANDING",
                   "note": "the v3 confirmatory-window protocol, its runbook and its "
                           "authorization are not delivered"},
        },
        "binding": {
            "universe_manifest": {
                "path": UNIVERSE_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
                "file_sha256": sha256_file(repo_root / UNIVERSE_RELATIVE),
            },
            "data_manifest": {
                "path": DATA_RELATIVE,
                "manifest_hash": data.get("manifest_hash"),
                "file_sha256": sha256_file(repo_root / DATA_RELATIVE),
            },
            "candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
                "file_sha256": sha256_file(repo_root / FREEZE_RELATIVE),
            },
            "candidate_freeze_amendment": {
                "path": FREEZE_AMENDMENT_RELATIVE,
                "manifest_hash": freeze_amendment.get("manifest_hash"),
                "file_sha256": sha256_file(repo_root / FREEZE_AMENDMENT_RELATIVE),
            },
        },
        "precedence": {
            "rule": (
                "A consumer of the effective v3 specification resolves "
                f"{STALE_FIELD} through this amendment when the amendment is present and "
                "verified, and reads the immutable specification otherwise. The immutable "
                "specification is never rewritten."
            ),
            "unchanged": [
                "strategy_grid",
                "costs",
                "execution",
                "folds",
                "selection",
                "pilot",
                "metrics",
                "baselines",
                "fixed_breakout_baseline",
                "status",
                "checkpointing",
                "universe.snapshot_retrieval",
                "universe.expansion_scope",
                "universe.eligibility_validation.candle_history",
                "universe.eligibility_validation.binance_spot_verification",
                "holdout",
                "expansion_program",
            ],
            "superseded": [STALE_FIELD],
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "This amendment authorizes nothing. It corrects one stale reference and "
                "records the delivered prerequisite status."
            ),
        },
        "producer": {
            "path": "scripts/build_v3_spec_amendment_1.py",
            "verify_command": "python3 scripts/verify_v3_spec_amendment_1.py",
            "deterministic": True,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with the manifest_hash key "
                "removed."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    if args.print_only:
        print(payload, end="")
        return 0
    if ARTIFACT_PATH.exists() and not args.force:
        print(
            f"refusing to overwrite {ARTIFACT_PATH.relative_to(repo_root)} without --force",
            file=sys.stderr,
        )
        return 1
    atomic_write_text(ARTIFACT_PATH, payload)
    print(json.dumps({
        "manifest_hash": document["manifest_hash"],
        "path": str(ARTIFACT_PATH.relative_to(repo_root)),
        "corrections": [item["path"] for item in document["corrections"]],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

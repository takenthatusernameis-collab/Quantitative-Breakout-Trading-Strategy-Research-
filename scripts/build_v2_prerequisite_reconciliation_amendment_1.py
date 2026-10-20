#!/usr/bin/env python3
"""Build the versioned amendment reconciling configs/research_v2.json P2/P3 status."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_prerequisite_reconciliation_amendment_1.json"
CREATED_UTC = "2026-10-20T07:40:00Z"
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document, excluded_keys):
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body))


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root=REPO_ROOT):
    root = Path(repo_root)
    spec_v2 = _load(root / "configs" / "research_v2.json")
    auth = _load(root / "research_state" / "campaign_authorization.json")
    document = {
        "artifact": "v2_prerequisite_reconciliation_amendment",
        "artifact_version": "v2-prerequisite-reconciliation-amendment-1",
        "version": 1,
        "created_utc": CREATED_UTC,
        "amendment_status": "PREREGISTERED_AMENDMENT_DESIGN_ONLY",
        "description": "Versioned amendment recording that P2 and P3 are delivered (immutable configs/research_v2.json untouched) and recording the RL1 decision.",
        "reconciliation": {
            "configs_research_v2": "configs/research_v2.json",
            "specification_hash": spec_v2["specification_hash"],
            "p2_status_recorded": "DELIVERED",
            "p3_status_recorded": "DELIVERED",
            "note": "configs/research_v2.json is immutable and hash-verified; its P2/P3 fields remain OUTSTANDING in the file. This amendment records the delivered status by reference only.",
        },
        "rl1_decision": {
            "decision": "retain_ordered_digest_as_value_of_record",
            "rationale": "BRAIN-009 rejects rotating compute_code_hash(); the v1 campaign runtime gate is unchanged and a v1 resume requires the authorized enumeration order. Nothing runs today.",
            "code_hash": auth["code_hash"],
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": MANIFEST_HASH_EXCLUDED_KEYS,
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, tuple(MANIFEST_HASH_EXCLUDED_KEYS))
    return document


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    artifact = build(REPO_ROOT)
    if args.print:
        print(json.dumps(artifact, indent=2, ensure_ascii=False))
        return 0
    if ARTIFACT_PATH.exists() and not args.force:
        raise SystemExit(f"{ARTIFACT_PATH} already exists; pass --force to overwrite")
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ARTIFACT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(str(ARTIFACT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

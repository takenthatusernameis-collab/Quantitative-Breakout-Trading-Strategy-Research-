#!/usr/bin/env python3
"""Build execution amendment 2, binding the existing selection run to auth v2.

The amendment changes only the effective selection-authorization identity.
All execution, candle-fetch, grid and confirmatory-evaluation flags remain
false. Default mode prints; --write is explicit.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = "configs/research_v6_selection_authorization_2.json"
PROTOCOL_PATH = "configs/research_v6_execution.json"
AMENDMENT_1_PATH = "configs/research_v6_execution_amendment_1.json"
TARGET = "configs/research_v6_execution_amendment_2.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(document: Dict[str, Any]) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        if "." not in key:
            body.pop(key, None)
    return hashlib.sha256(canonical(body)).hexdigest()


def build(root: Path = ROOT) -> Dict[str, Any]:
    auth_path = root / AUTH_PATH
    protocol_path = root / PROTOCOL_PATH
    amendment_1_path = root / AMENDMENT_1_PATH
    for path in (auth_path, protocol_path, amendment_1_path):
        if not path.is_file():
            raise SystemExit(f"required input is missing: {path.relative_to(root)}")
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    amendment_1 = json.loads(amendment_1_path.read_text(encoding="utf-8"))
    if artifact_hash(auth) != auth.get("manifest_hash"):
        raise SystemExit("selection authorization 2 does not verify")
    if artifact_hash(protocol) != protocol.get("manifest_hash"):
        raise SystemExit("the frozen v6 execution protocol does not verify")
    if artifact_hash(amendment_1) != amendment_1.get("manifest_hash"):
        raise SystemExit("execution amendment 1 does not verify")
    run = auth.get("authorized_run") or {}
    if run.get("authorized") is not True or run.get("max_runs") != 1:
        raise SystemExit("selection authorization 2 does not bind the existing single run")
    code_identity = run.get("code_identity") or {}
    if not code_identity.get("execution_path_digest") or not code_identity.get("run_code_identity"):
        raise SystemExit("selection authorization 2 does not bind the delivered source digest")

    old = amendment_1.get("execution_authorization") or {}
    effective = copy.deepcopy(old)
    effective.update({
        "execution_authorized": False,
        "candle_fetch_authorized": False,
        "confirmatory_evaluation_authorized": False,
        "grid_run_authorized": False,
        "second_run_authorized": False,
        "selection_authorization_present": True,
        "selection_authorization_path": AUTH_PATH,
        "selection_authorization_manifest_hash": auth["manifest_hash"],
        "selection_authorization_sha256": sha256_file(auth_path),
        "selection_authorization_run_id": run.get("run_id"),
        "selection_authorization_campaign_id": run.get("campaign_id"),
        "selection_authorization_scope": "exactly the existing single bounded v6 development-only selection grid run; no additional attempt or scope change",
        "run_gate_rule": "the run gate verifies selection authorization 2 by recomputing its self-hash and file digest, then checks the frozen v6 scope, unchanged v1 rule and current canonical source digest",
    })
    document = {
        "artifact": "v6_execution_amendment_2",
        "artifact_version": 2,
        "amendment_status": "PUBLISHED_CORRECTION",
        "protocol_version": "v6",
        "universe_version": "v6",
        "created_date_utc": "2026-11-04",
        "amends": {
            "file": PROTOCOL_PATH,
            "manifest_hash": protocol["manifest_hash"],
            "sha256": sha256_file(protocol_path),
        },
        "supersedes_in_amendment_1": {
            "file": AMENDMENT_1_PATH,
            "manifest_hash": amendment_1["manifest_hash"],
            "sha256": sha256_file(amendment_1_path),
        },
        "precedence": {
            "rule": "amendment 2 supersedes amendment 1 only for the execution_authorization identity binding; every frozen protocol and amendment artifact remains unchanged",
            "superseded": ["execution_authorization"],
            "unchanged": [
                "candidate_freeze_and_confirmatory_window",
                "evaluation_scope",
                "benchmark_rule",
                "code_hash_constraint",
                "inherited_rules",
                "deviation_disclosure",
                "authorization",
            ],
            "execution_authority_is_unchanged": "this amendment authorizes no campaign execution, no grid run, no candle fetch and no confirmatory evaluation; it only rebinds the pre-existing single selection authorization to its delivered source path",
        },
        "execution_authorization": effective,
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": ["manifest_hash"],
        },
    }
    document["manifest_hash"] = artifact_hash(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the new versioned amendment")
    args = parser.parse_args()
    document = build()
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        target = ROOT / TARGET
        if target.exists():
            raise SystemExit(f"refusing to overwrite {TARGET}")
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {TARGET} manifest_hash={document['manifest_hash']}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

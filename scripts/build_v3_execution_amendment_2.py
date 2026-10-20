#!/usr/bin/env python3
"""Build the preregistered v3 execution amendment 2.

The amendment is immutable and hash-bound.  It adds the published
selected-configurations manifest path to the v3 result layout, and it authorizes
nothing else: no second run, no confirmatory evaluation, no candle fetch.  Every
fact it records is recomputed from the repository; the producer refuses to overwrite
an existing artifact without ``--force``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_execution_amendment_2.json"

CREATED_UTC = "2026-10-20T19:20:00Z"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

PROTOCOL_RELATIVE = "configs/research_v3_execution.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
UNIVERSE_V3_RELATIVE = "research/universe_manifest_v3.json"
DATA_V3_RELATIVE = "research/data_manifest_v3.json"
DATA_AMENDMENT_1_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v3_execution_amendment_1.json"
SELECTION_AUTH_RELATIVE = "configs/research_v3_selection_authorization_1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
LEDGER_V3_RELATIVE = "research/ledger_v3.json"
MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"

#: The paths a v3 selection run writes.  The published selected-configurations
#: manifest is not one of them: it is a publication of the outcome of a run that
#: has already been performed, and it is authorized separately, here.
FORBIDDEN_MANIFEST_PATHS = (
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in set(excluded_keys)}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    protocol = _load(root / PROTOCOL_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    freeze_amendment_1 = _load(root / FREEZE_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = _load(root / FREEZE_AMENDMENT_2_RELATIVE)
    universe = _load(root / UNIVERSE_V3_RELATIVE)
    data_manifest = _load(root / DATA_V3_RELATIVE)
    data_amendment_1 = _load(root / DATA_AMENDMENT_1_RELATIVE)
    exec_amendment_1 = _load(root / EXECUTION_AMENDMENT_1_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    ledger = _load(root / LEDGER_V3_RELATIVE)
    manifest = _load(root / MANIFEST_RELATIVE)

    layout = protocol["v3_result_layout"]
    manifest_path = MANIFEST_RELATIVE
    if manifest_path in FORBIDDEN_MANIFEST_PATHS:
        raise ValueError("the published manifest path must not be a v1 candidate manifest")

    document: Dict[str, Any] = {
        "artifact": "v3_execution_amendment",
        "artifact_version": "v3-execution-amendment-2",
        "version": 2,
        "amendment_number": 2,
        "protocol_version": "v3",
        "universe_version": "v3",
        "created_utc": CREATED_UTC,
        "amendment_status": "PREREGISTERED_AMENDMENT_DESIGN_ONLY",
        "description": (
            "Versioned amendment to configs/research_v3_execution.json adding the "
            "authorized path for the published v3 selected-configuration manifest derived "
            "from the completed v3 selection run."),
        "amends": {
            "file": PROTOCOL_RELATIVE,
            "file_sha256": sha256_file(root / PROTOCOL_RELATIVE),
            "protocol_specification_hash": protocol["specification_hash"],
            "note": (
                "The execution protocol is immutable and was not edited. Its file digest "
                "and its own specification_hash are recorded here unchanged; the amendment "
                "authorizes an additional published artifact path."),
        },
        "references": {
            "configs_research_v3": {
                "file": SPEC_V3_RELATIVE,
                "specification_hash": spec_v3["specification_hash"],
            },
            "configs_research_v1": {
                "file": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "universe_manifest_v3": {
                "file": UNIVERSE_V3_RELATIVE,
                "manifest_hash": universe["manifest_hash"],
            },
            "data_manifest_v3": {
                "file": DATA_V3_RELATIVE,
                "manifest_hash": data_manifest["manifest_hash"],
            },
            "data_manifest_amendment_1": {
                "file": DATA_AMENDMENT_1_RELATIVE,
                "manifest_hash": data_amendment_1["manifest_hash"],
            },
            "candidate_freeze_v3": {
                "file": FREEZE_RELATIVE,
                "manifest_hash": freeze["manifest_hash"],
            },
            "candidate_freeze_amendment_1": {
                "file": FREEZE_AMENDMENT_1_RELATIVE,
                "manifest_hash": freeze_amendment_1["manifest_hash"],
            },
            "candidate_freeze_amendment_2": {
                "file": FREEZE_AMENDMENT_2_RELATIVE,
                "manifest_hash": freeze_amendment_2["manifest_hash"],
            },
            "v3_execution_amendment_1": {
                "file": EXECUTION_AMENDMENT_1_RELATIVE,
                "manifest_hash": exec_amendment_1["manifest_hash"],
            },
            "v3_selection_authorization_1": {
                "file": SELECTION_AUTH_RELATIVE,
                "manifest_hash": selection_auth["manifest_hash"],
            },
            "v3_selection_ledger": {
                "file": LEDGER_V3_RELATIVE,
                "run_id": ledger["run_id"],
                "campaign_id": ledger["campaign_id"],
                "status": ledger["status"],
                "holdout_exposed_count": ledger["holdout_exposed_count"],
            },
            "v1_campaign_authorization": {
                "file": AUTHORIZATION_RELATIVE,
                "protocol_version": "v1",
                "authorized": authorization["authorized"],
                "code_hash": authorization["code_hash"],
            },
        },
        "v3_result_layout_amendment": {
            "description": (
                "Add the published selected-configuration manifest path to the v3 result "
                "layout. The path is not research/candidate_manifest.json nor "
                "research/candidate_manifest_v2.json."),
            "campaign_id": layout["campaign_id"],
            "paths": {
                "shard_directory": layout["shard_directory"],
                "ledger_path": layout["ledger_path"],
                "results_manifest_path": layout["results_manifest_path"],
                "results_stream_path": "research/results_v3.jsonl",
                "checkpoint_path": "research_state/checkpoint_v3.json",
                "selected_configurations_manifest_path": manifest_path,
                "selected_configurations_manifest_hash": manifest["manifest_hash"],
            },
            "writes_into_v1_forbidden": True,
            "writes_into_v2_forbidden": True,
            "authorization_rules": [
                "Only the published outcome of the completed authorized run may be written; no second run is authorized",
                "No confirmatory-window evaluation is authorized by this amendment",
                "No candle fetch is authorized by this amendment",
                "The manifest must list all 6 assets of the frozen scope with explicit reasons for assets without a candidate",
                "The published manifest must be re-derivable from the verified shards under the unchanged v1 selection rule",
            ],
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "verify_command": "python3 scripts/verify_v3_execution_amendment_2.py",
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, tuple(MANIFEST_HASH_EXCLUDED_KEYS))
    return document


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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

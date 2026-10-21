#!/usr/bin/env python3
"""Build the v4 candidate manifest freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_PATH = REPO_ROOT / "configs" / "research_v4.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v4.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v4.json"
ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"


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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: List[str] = ["manifest_hash"]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec = json.loads(SPEC_PATH.read_text())
    universe = json.loads(UNIVERSE_PATH.read_text())
    data_manifest = json.loads(DATA_PATH.read_text())

    document: Dict[str, Any] = {
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "manifest_hash": None,
        "candidate_freeze_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "specification_hash": spec["specification_hash"],
        "universe_manifest_hash": universe["manifest_hash"],
        "data_manifest_hash": data_manifest["manifest_hash"],
        "snapshot_identity": data_manifest["snapshot_identity"],
        "candidates": universe["eligible_assets"],
        "exclusions": universe["excluded_assets"],
        "confirmatory_window": {
            "opens_utc": (datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "min_hours": 2160,
            "earliest_possible_end_utc": "2027-01-18T13:00:00Z",
        },
        "supersedes": {
            "v3_candidate_freeze_path": "configs/research_v3_candidate_freeze.json",
            "v3_candidate_freeze_hash": json.loads((repo_root / "configs" / "research_v3_candidate_freeze.json").read_text())["manifest_hash"],
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document)
    return document


def write_document(document: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    document = build()
    if ARTIFACT_PATH.exists() and not args.force:
        print("exists without --force", file=sys.stderr)
        return 1
    write_document(document, ARTIFACT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())

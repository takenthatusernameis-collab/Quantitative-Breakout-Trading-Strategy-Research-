#!/usr/bin/env python3
"""Build selection-authorization v2 with the delivered v6 execution digest.

This is a versioned identity binding for the *same* already-authorized single
development-only run. It does not add attempts, change scope, change rules or
authorize confirmatory access. Default mode prints; --write is explicit.

Usage:
    python3 scripts/build_v6_selection_authorization_2.py
    python3 scripts/build_v6_selection_authorization_2.py --write
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "configs/research_v6_selection_authorization_1.json"
TARGET = "configs/research_v6_selection_authorization_2.json"
EXECUTION_ROOT = "src/v6_campaign"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_hash(document: Dict[str, Any]) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        if "." not in key:
            body.pop(key, None)
    return hashlib.sha256(canonical(body)).hexdigest()


def source_digest(root: Path) -> str:
    base = root / EXECUTION_ROOT
    files = sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py"))
    if not files:
        raise SystemExit("refusing to bind an empty v6 selection execution path")
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(hashlib.sha256((base / relative).read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def composite_identity(hashed_set_digest: str, execution_digest: str) -> str:
    payload = {
        "algorithm": "canonical_source_digest_v1",
        "hashed_set_root": "src/breakout_research",
        "hashed_set_digest": hashed_set_digest,
        "execution_path_root": EXECUTION_ROOT,
        "execution_path_digest": execution_digest,
    }
    return hashlib.sha256(canonical(payload)).hexdigest()


def build(root: Path = ROOT) -> Dict[str, Any]:
    source_path = root / SOURCE
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    document = json.loads(source_path.read_text(encoding="utf-8"))
    if manifest_hash(document) != document.get("manifest_hash"):
        raise SystemExit("selection authorization 1 does not verify; refusing to derive a successor")
    run = document.get("authorized_run") or {}
    if run.get("authorized") is not True or run.get("max_runs") != 1:
        raise SystemExit("selection authorization 1 does not carry the one-run authorization")
    if run.get("run_phase") != "selection_grid":
        raise SystemExit("source authorization is not a development-only selection run")

    identity = run.get("code_identity") or {}
    from v6_campaign.identity import canonical_source_digest as digest_tree
    hashed_live = digest_tree(root / "src" / "breakout_research")
    if identity.get("hashed_set_digest") != hashed_live:
        raise SystemExit("the frozen hashed engine differs from the selection authorization")
    execution_live = source_digest(root)
    result = copy.deepcopy(document)
    result["artifact_version"] = "v6-selection-authorization-2"
    result["supersedes"] = {
        "path": SOURCE,
        "manifest_hash": document["manifest_hash"],
        "sha256": sha256_file(source_path),
        "purpose": "bind the already-authorized single selection run to the delivered v6 execution source",
    }

    new_run = result["authorized_run"]
    new_identity = dict(new_run["code_identity"])
    new_identity["execution_path_digest"] = execution_live
    new_identity["run_code_identity"] = composite_identity(hashed_live, execution_live)
    new_identity["note"] = (
        "The v6 run identity is the composite of the unchanged frozen v1 engine digest "
        "and the canonical digest of src/v6_campaign as delivered by this versioned authorization."
    )
    new_run["code_identity"] = new_identity
    new_path = dict(new_run.get("execution_path") or {})
    new_path["modules"] = [
        (Path(EXECUTION_ROOT) / relative).as_posix()
        for relative in sorted(
            path.relative_to(root / EXECUTION_ROOT).as_posix()
            for path in (root / EXECUTION_ROOT).rglob("*.py")
        )
    ]
    new_path["v6_execution_path_exists"] = True
    new_path["canonical_source_digest"] = execution_live
    new_path["note"] = (
        "The source digest is recomputed from the delivered v6 selection path. "
        "The hashed src/breakout_research engine remains byte-identical; no strategy, "
        "grid, metric, cost or selection rule is changed."
    )
    new_run["execution_path"] = new_path
    result["manifest_hash"] = ""
    result["manifest_hash"] = manifest_hash(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the new versioned authorization artifact")
    args = parser.parse_args()
    result = build()
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        target = ROOT / TARGET
        if target.exists():
            raise SystemExit(f"refusing to overwrite existing {TARGET}")
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {TARGET} manifest_hash={result['manifest_hash']}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

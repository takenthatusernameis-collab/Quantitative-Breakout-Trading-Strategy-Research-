#!/usr/bin/env python3
"""Read-only, offline verification of the v3 candidate freeze.

The freeze (``configs/research_v3_candidate_freeze.json``) was written over the
*derived* candidate batch, before the constituent validation of BRAIN-012 P2/P3
had been performed. The validated candidate set is recorded by the versioned
amendment ``configs/research_v3_candidate_freeze_amendment_1.json``; this
verifier **resolves** the effective candidate set through that amendment and
checks that the frozen artifact stays byte-identical.

Checks that were false by design once a validation exists were replaced, not
deleted: the reference to a manifest digest is now checked against the file on
disk, and the resolution through the amendment is accepted only when the
amendment itself verifies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v3.json"
AMENDMENT_RELATIVE = "configs/research_v3_exclusion_amendment_1.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
FREEZE_AMENDMENT_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"

MIN_CONFIRMATORY_WINDOW_HOURS = 2160


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


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_freeze_amendment(repo_root: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load the freeze amendment when it exists and is internally consistent.

    Returns the amendment and the list of reasons it cannot be used. The
    amendment is accepted only when its own manifest hash recomputes and it
    names the frozen artifact's current manifest hash.
    """
    problems: List[str] = []
    path = repo_root / FREEZE_AMENDMENT_RELATIVE
    if not path.exists():
        return None, problems
    amendment = read_json(path)
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        problems.append("the freeze amendment's manifest hash does not recompute")
    freeze = read_json(repo_root / FREEZE_RELATIVE)
    recorded = amendment.get("problem", {}).get("affected_artifact_manifest_hash")
    if recorded != freeze.get("manifest_hash"):
        problems.append("the freeze amendment does not bind the current frozen artifact")
    return amendment, problems


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []

    for relative in (FREEZE_RELATIVE, SPEC_RELATIVE, AMENDMENT_RELATIVE,
                     UNIVERSE_RELATIVE, DATA_RELATIVE):
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"],
                    "candidate_count": 0, "effective_candidate_count": 0}

    freeze = read_json(repo_root / FREEZE_RELATIVE)
    spec = read_json(repo_root / SPEC_RELATIVE)
    amendment = read_json(repo_root / AMENDMENT_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)

    # 1. the freeze is self-hashing
    excluded = tuple(freeze.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = freeze.get("manifest_hash")
    recomputed = compute_manifest_hash(freeze, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the snapshot-identity tuple names this very artifact
    identity = freeze.get("snapshot_identity") or {}
    if identity.get("candidate_manifest_hash") != declared:
        failures.append("snapshot_identity.candidate_manifest_hash does not equal manifest_hash")

    # 3. the frozen candidate set is the published derived batch
    batch = (amendment.get("derived_candidate_batch", {}).get("members") or [])
    batch_pairs = [member["binance_pair"] for member in batch]
    frozen_pairs = freeze.get("frozen_candidate_set", {}).get("binance_pairs") or []
    if frozen_pairs != batch_pairs:
        failures.append("the frozen candidate set does not match the published derived batch")

    # 4. the confirmatory window opens after the freeze
    boundary = freeze.get("data_boundary") or {}
    window_start = parse_iso_utc(boundary["confirmatory_window_start_utc"])
    freeze_ts = parse_iso_utc(freeze["candidate_freeze_timestamp_utc"])
    if window_start <= freeze_ts:
        failures.append("the confirmatory window does not open after the candidate freeze")
    if int(boundary.get("min_confirmatory_window_hours") or 0) != MIN_CONFIRMATORY_WINDOW_HOURS:
        failures.append("the confirmatory window does not require 2,160 closed hourly candles")
    if boundary.get("single_use") is not True:
        failures.append("the confirmatory window is not marked single-use")

    # 5. the freeze authorizes nothing
    if freeze.get("execution_authorization", {}).get("execution_authorized") is not False:
        failures.append("execution_authorization.execution_authorized is not false")
    if freeze.get("selection_remainder", {}).get("grid_run_authorized") is not False:
        failures.append("selection_remainder.grid_run_authorized is not false")

    # 6. the referenced artifacts are the ones on disk, resolved through the amendment
    freeze_amendment, amendment_problems = resolve_freeze_amendment(repo_root)
    failures.extend(amendment_problems)
    related = freeze.get("related_artifacts") or {}
    effective_candidates = list(frozen_pairs)
    if freeze_amendment is not None and not amendment_problems:
        evidence = freeze_amendment.get("validation_evidence") or {}
        for key, relative, manifest in (
            ("universe_manifest", UNIVERSE_RELATIVE, universe),
            ("data_manifest", DATA_RELATIVE, data),
        ):
            block = evidence.get(key) or {}
            if block.get("manifest_hash") != manifest.get("manifest_hash"):
                failures.append(f"the freeze amendment does not bind the current {key}")
            if block.get("file_sha256") != sha256_file(repo_root / relative):
                failures.append(f"the freeze amendment records a stale {key}")
        effective_candidates = [
            member.get("binance_pair")
            for member in (freeze_amendment.get("validated_candidate_set", {}).get("members") or [])
        ]
    else:
        # without a usable amendment the frozen reference must still name the live files
        for key, relative, manifest in (
            ("v3_universe_manifest", UNIVERSE_RELATIVE, universe),
            ("v3_data_manifest", DATA_RELATIVE, data),
        ):
            block = related.get(key) or {}
            if block.get("manifest_hash") != manifest.get("manifest_hash"):
                failures.append(
                    f"related_artifacts.{key} names a manifest hash that the file on disk does "
                    "not have, and no verified freeze amendment supersedes it"
                )

    return {
        "ok": not failures,
        "failures": failures,
        "manifest_hash": declared,
        "candidate_count": len(frozen_pairs),
        "effective_candidate_count": len(effective_candidates),
        "effective_candidates": effective_candidates,
        "candidate_set_resolution": "freeze_amendment_1" if freeze_amendment is not None
        and not amendment_problems else "frozen_derived_batch",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

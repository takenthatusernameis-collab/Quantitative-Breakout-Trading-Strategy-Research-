#!/usr/bin/env python3
"""Build the v3 candidate-freeze amendment 2 (re-bound data-manifest identity).

BRAIN-013 requires the data-manifest identity of the frozen v3 candidate set to
be re-bound to the **effective** data manifest -- the base manifest plus the
benchmark entry published by the data-manifest amendment 1 -- because the
frozen candidate set names the base manifest's identity, and the base manifest
itself is immutable.

The candidate set, the data boundary, the snapshot identity and the
authorization flags of the frozen artifact are **not** changed: the amendment
re-binds one identity and records the benchmark rule. It authorizes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_benchmark_amendment_common import (  # noqa: E402
    DATA_AMENDMENT_1_RELATIVE,
    DATA_MANIFEST_RELATIVE,
    EXECUTION_RELATIVE,
    FREEZE_AMENDMENT_1_RELATIVE,
    FREEZE_AMENDMENT_2_RELATIVE,
    FREEZE_RELATIVE,
    SPEC_RELATIVE,
    UNIVERSE_MANIFEST_RELATIVE,
    compute_manifest_hash,
    read_json,
    sha256_file,
    v1_anchor_digests,
)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.",
            suffix=".tmp", delete=False, newline=""
        ) as handle:
            temporary_path = handle.name
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def build(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root)
    freeze = read_json(root / FREEZE_RELATIVE)
    freeze_amendment_1 = read_json(root / FREEZE_AMENDMENT_1_RELATIVE)
    data_amendment = read_json(root / DATA_AMENDMENT_1_RELATIVE)
    spec = read_json(root / SPEC_RELATIVE)

    effective_hash = data_amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    members = freeze_amendment_1["validated_candidate_set"]["members"]
    candidate_pairs = [str(member["binance_pair"]) for member in members]
    benchmark = data_amendment["benchmark_asset"]

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_REBOUND_DATA_MANIFEST_IDENTITY_NO_AUTHORIZATION",
        "artifact": "v3_candidate_freeze_amendment_2",
        "artifact_version": 2,
        "created_utc": "2026-10-20T15:45:00Z",
        "problem": {
            "statement": (
                "the frozen candidate set binds the identity of research/data_manifest_v3.json. "
                "BRAIN-013 publishes the missing BTCUSDT benchmark entry by a versioned "
                "amendment, so the data-manifest identity of the frozen scope has to be "
                "re-bound to the effective data manifest."
            ),
            "affected_artifact_path": FREEZE_RELATIVE,
            "affected_artifact_manifest_hash": freeze.get("manifest_hash"),
            "affected_artifact_sha256": sha256_file(root / FREEZE_RELATIVE),
            "repair": (
                "the frozen artifact is immutable and is not edited in place; the identity "
                "is re-bound by this amendment"
            ),
        },
        "rebound_identity": {
            "rule": (
                "every reference to the v3 data-manifest identity inside the frozen "
                "candidate set resolves to the effective data manifest: the base manifest "
                "plus the benchmark entry published by the data-manifest amendment 1"
            ),
            "superseded_fields": [
                "snapshot_identity.data_manifest_hash",
                "frozen_candidate_set.data_manifest_hash",
            ],
            "base_data_manifest_path": DATA_MANIFEST_RELATIVE,
            "base_data_manifest_hash": data_amendment["effective_data_manifest"]["base_manifest_hash"],
            "base_data_manifest_sha256": sha256_file(root / DATA_MANIFEST_RELATIVE),
            "effective_data_manifest_hash": effective_hash,
            "superseded_data_manifest_hash": freeze.get("snapshot_identity", {}).get(
                "data_manifest_hash"
            ),
        },
        "frozen_candidate_set": {
            "count": len(candidate_pairs),
            "binance_pairs": candidate_pairs,
            "unchanged_by_this_amendment": True,
            "rule": (
                "the candidate set is the validated candidate set of the freeze amendment 1; "
                "the benchmark is not a candidate and does not join the set"
            ),
            "members": members,
            "excluded_candidates": freeze_amendment_1["excluded_candidates"],
        },
        "benchmark_asset": {
            "symbol": benchmark["symbol"],
            "role": benchmark["role"],
            "is_candidate": False,
            "content_hash": benchmark["content_hash"],
            "dataset_path": benchmark["dataset_path"],
            "first_candle_timestamp": benchmark["first_candle_timestamp"],
            "last_candle_timestamp": benchmark["last_candle_timestamp"],
            "observed_candle_count": benchmark["observed_candle_count"],
        },
        "data_boundary": {
            "confirmatory_window_start_utc": freeze["data_boundary"]["confirmatory_window_start_utc"],
            "min_confirmatory_window_hours": freeze["data_boundary"]["min_confirmatory_window_hours"],
            "earliest_possible_confirmatory_window_end_utc":
                freeze["data_boundary"]["earliest_possible_confirmatory_window_end_utc"],
            "window_moved_by_this_amendment": False,
            "note": (
                "the confirmatory-window rules and the development-data boundary are "
                "unchanged; they are copied here so that the effective boundary is "
                "readable from a single artifact"
            ),
        },
        "alignment_rule": {
            "methodology": "docs/research_protocol.md:101 - Align BTC and target asset by UTC candle close",
            "rule": (
                "the asset series and the benchmark series are sliced to the same fold "
                "window before the frozen engine is called, so that the engine's index "
                "pairing equals the UTC-candle-close alignment; nothing is forward-filled"
            ),
            "fail_closed": (
                "the v3 execution path refuses to run when the benchmark series is missing, "
                "shorter than the evaluated window or not index-aligned with the asset series"
            ),
            "grid_rule": (
                "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                "re-derived or re-ranked"
            ),
            "source": DATA_AMENDMENT_1_RELATIVE,
        },
        "precedence": {
            "rule": (
                "the effective data-manifest identity of the frozen candidate set is the one "
                "recorded by this amendment; the base manifest's identity is superseded by "
                "reference only"
            ),
            "superseded": [
                "snapshot_identity.data_manifest_hash",
                "frozen_candidate_set.data_manifest_hash",
            ],
            "unchanged": [
                "frozen_candidate_set",
                "snapshot_identity (except the data-manifest identity)",
                "data_boundary",
                "selection_remainder",
                "execution_authorization",
                "related_artifacts",
                "durability",
            ],
            "resolution_rule": (
                "a verifier that reads the v3 data-manifest identity resolves it through "
                "this amendment when the amendment is present and verified"
            ),
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "selection_authorization_present": False,
            "scope": (
                "this amendment re-binds one identity and records the benchmark rule. It "
                "authorizes no run, no evaluation and no confirmatory-window read."
            ),
        },
        "related_artifacts": {
            "v1_anchors": v1_anchor_digests(root),
            "v3_specification": {
                "path": SPEC_RELATIVE,
                "specification_hash": spec.get("specification_hash"),
            },
            "v3_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v3_candidate_freeze_amendment_1": {
                "path": FREEZE_AMENDMENT_1_RELATIVE,
                "manifest_hash": freeze_amendment_1.get("manifest_hash"),
            },
            "v3_data_manifest_amendment_1": {
                "path": DATA_AMENDMENT_1_RELATIVE,
                "manifest_hash": data_amendment.get("manifest_hash"),
                "effective_data_manifest_hash": effective_hash,
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": read_json(root / DATA_MANIFEST_RELATIVE).get("manifest_hash"),
            },
            "v3_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": read_json(root / UNIVERSE_MANIFEST_RELATIVE).get("manifest_hash"),
            },
            "v3_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "specification_hash": read_json(root / EXECUTION_RELATIVE).get("specification_hash"),
            },
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-013",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-013",
            "stage": "stage 1 (the benchmark dataset and the amendment cascade)",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": ["manifest_hash"],
            "note": "manifest_hash is the sha256 of the document body with manifest_hash removed.",
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, ("manifest_hash",))
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="rewrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    document = build(repo_root)
    target = repo_root / FREEZE_AMENDMENT_2_RELATIVE
    if args.print_only:
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    if target.exists() and not args.force:
        print(json.dumps({
            "ok": False,
            "reason": "the amendment already exists; pass --force to rewrite it",
            "manifest_hash": document["manifest_hash"],
        }, indent=2, sort_keys=True))
        return 1
    atomic_write_json(target, document)
    print(json.dumps({
        "ok": True,
        "path": FREEZE_AMENDMENT_2_RELATIVE,
        "manifest_hash": document["manifest_hash"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

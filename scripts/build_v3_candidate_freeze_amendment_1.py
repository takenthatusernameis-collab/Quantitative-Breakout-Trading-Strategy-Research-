#!/usr/bin/env python3
"""Build the v3 candidate-freeze amendment 1 (the validated candidate set).

``configs/research_v3_candidate_freeze.json`` (manifest hash
``12a981b1...``) froze the v3 candidate set **before** the constituent
validation of BRAIN-012 P2/P3 had been performed: it froze the *derived batch*
of twenty assets that the snapshot, the inherited fixed lists, the published v3
classifier and the prior-universe rules produced. The validation then excluded
fourteen of those twenty (six assets are not tradeable on Binance spot and
eight have fewer than 26,280 closed hourly candles), so only six of them are
eligible constituents.

The frozen artifact must not be edited in place -- its manifest hash is part of
the v3 identity chain -- so the correction is carried by a versioned amendment,
exactly as the established pattern requires (v2: execution amendment 1 ->
code-hash amendment 1 -> execution amendment 2 -> prerequisite reconciliation
amendment 1 -> code-hash amendment 2).

The amendment is *derived*, not written by hand: the validated set, the
exclusions and their reasons are read from the frozen v3 manifests, and every
digest is recomputed from the files on disk. The script is deterministic (the
creation instant is pinned), refuses to overwrite an existing artifact without
``--force`` and never writes to the hashed set, never edits a frozen artifact,
never fetches anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v3_candidate_freeze_amendment_1.py            # write
    python3 scripts/build_v3_candidate_freeze_amendment_1.py --force    # rewrite
    python3 scripts/build_v3_candidate_freeze_amendment_1.py --print     # print only
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

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"

#: The frozen artifact whose candidate set is corrected by reference.
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v3.json"
EXCLUSION_AMENDMENT_RELATIVE = "configs/research_v3_exclusion_amendment_1.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
SPOT_EVIDENCE_RELATIVE = "research/v3_evidence/binance_spot_verification.json"
CANDLE_EVIDENCE_RELATIVE = "research/v3_evidence/candle_verification.json"

#: The instant at which this amendment is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-20T12:45:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The exclusion reasons the frozen v3 rules may produce for a candidate that
#: fails a validation step. A reason outside this vocabulary aborts the build.
ALLOWED_VALIDATION_EXCLUSION_REASONS = (
    "binance_spot_unavailable",
    "coverage_gap",
    "insufficient_hourly_history",
    "candle_validation_failed",
)

#: The v1 artifacts whose bytes must not change. The values are recomputed at
#: build time and recorded; the verifier recomputes them again.
V1_ANCHORS = (
    ("configs/research_v1.json",),
    ("research/universe_manifest.json",),
    ("research/data_manifest.json",),
    ("research/candidate_manifest.json",),
    ("research/candidate_manifest_v2.json",),
)


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
    """Assemble the amendment document from the frozen, hash-bound artifacts."""
    spec = read_json(repo_root / SPEC_RELATIVE)
    freeze = read_json(repo_root / FREEZE_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)

    assets = universe.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v3 universe manifest has no eligible assets")

    validated: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for entry in sorted(assets, key=lambda item: int(item.get("rank") or 0)):
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        if entry.get("validated"):
            dataset = (data.get("assets") or {}).get(pair) or {}
            validated.append({
                "binance_pair": pair,
                "coingecko_id": entry.get("coingecko_id"),
                "content_hash": dataset.get("content_hash"),
                "dataset_path": dataset.get("dataset_path"),
                "market_cap_rank": entry.get("market_cap_rank"),
                "market_cap_usd": entry.get("market_cap_usd"),
                "name": entry.get("name"),
                "observed_candles": entry.get("observed_candles"),
                "rank": entry.get("rank"),
                "symbol": entry.get("symbol"),
            })
        else:
            reason = entry.get("exclusion_reason")
            if reason not in ALLOWED_VALIDATION_EXCLUSION_REASONS:
                raise SystemExit(
                    f"{pair}: exclusion reason {reason!r} is outside the frozen vocabulary"
                )
            excluded.append({
                "binance_pair": pair,
                "coingecko_id": entry.get("coingecko_id"),
                "exclusion_reason": reason,
                "market_cap_rank": entry.get("market_cap_rank"),
                "market_cap_usd": entry.get("market_cap_usd"),
                "name": entry.get("name"),
                "observed_candles": entry.get("observed_candles"),
                "rank": entry.get("rank"),
                "symbol": entry.get("symbol"),
            })

    derived_batch = freeze.get("frozen_candidate_set", {}).get("binance_pairs") or []
    if len(derived_batch) != len(assets):
        raise SystemExit(
            "the frozen candidate set and the v3 universe manifest disagree on the batch size"
        )

    top_n = int(spec["universe"]["top_n"])
    datasets = []
    for member in validated:
        path = repo_root / member["dataset_path"]
        if not path.exists():
            raise SystemExit(f"missing dataset for {member['binance_pair']}: {member['dataset_path']}")
        datasets.append({
            "binance_pair": member["binance_pair"],
            "content_hash": member["content_hash"],
            "dataset_path": member["dataset_path"],
            "file_sha256": sha256_file(path),
        })

    document: Dict[str, Any] = {
        "artifact": "v3_candidate_freeze_amendment_1",
        "artifact_version": 1,
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "created_utc": CREATED_UTC,
        "amendment_status": "PUBLISHED_CORRECTION_NO_AUTHORIZATION",
        "specification_purpose": (
            "Record the validated v3 candidate set, the exclusions with their reasons and the "
            "prerequisite status of the v3 cycle, without editing any frozen artifact."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-012",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-012 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "stage": "stage 1 (v3 specification, snapshot, validation, candidate freeze)",
            "predecessor_artifacts": [
                SPEC_RELATIVE,
                EXCLUSION_AMENDMENT_RELATIVE,
                FREEZE_RELATIVE,
                UNIVERSE_RELATIVE,
                DATA_RELATIVE,
            ],
            "sections_implemented_here": [
                "BRAIN-012 D-5: every candidate validated against real provider data",
                "BRAIN-012 D-6: the candidate set is frozen and hash-bound before any selection",
                "BRAIN-012 staged acceptance test 3: the freeze matches the validated constituents",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v3 grid run and candidate selection (no recorded decision authorizes a run)",
                "the v3 confirmatory-window evaluation",
            ],
        },
        "problem": {
            "statement": (
                "The v3 candidate freeze was written over the derived candidate batch before the "
                "constituent validation of BRAIN-012 P2/P3 had been performed, so it froze twenty "
                "assets of which fourteen do not satisfy the frozen eligibility rules. The "
                "validation outcome is recorded in research/universe_manifest_v3.json and "
                "research/data_manifest_v3.json."
            ),
            "affected_artifact": FREEZE_RELATIVE,
            "affected_artifact_manifest_hash": freeze.get("manifest_hash"),
            "affected_artifact_candidate_set_size": len(derived_batch),
            "correction": (
                "The validated candidate set recorded here is the v3 candidate set. The frozen "
                "artifact is not edited: its manifest hash stays what it is, and this amendment "
                "records the correction by reference, exactly as the v2 code-hash amendment 2 "
                "records the RL1 location correction."
            ),
        },
        "validated_candidate_set": {
            "members": validated,
            "count": len(validated),
            "source": UNIVERSE_RELATIVE,
            "rule": (
                "exactly the constituents of the derived batch whose Binance spot verification and "
                "candle-history verification both succeeded in research/universe_manifest_v3.json"
            ),
        },
        "excluded_candidates": {
            "members": excluded,
            "count": len(excluded),
            "source": UNIVERSE_RELATIVE,
            "rule": (
                "every derived-batch constituent that failed a validation step, with the reason "
                "recorded by the validation; an excluded candidate is reported, never hidden"
            ),
        },
        "shortfall": {
            "requested_top_n": top_n,
            "derived_batch_size": len(derived_batch),
            "validated_count": len(validated),
            "shortfall": max(0, top_n - len(validated)),
            "rule": (
                "configs/research_v3.json universe.eligibility_validation.failure_handling: exclude "
                "and record, never promote, never substitute a different asset and never lower the "
                "history requirement to admit a constituent"
            ),
            "no_backfill": True,
            "no_backfill_note": (
                "The snapshot contains further eligible names below the v2 floor, but the frozen "
                "rule admits no substitute for a candidate that failed validation, so the v3 "
                "candidate set is the six validated constituents and the shortfall is recorded."
            ),
        },
        "validation_evidence": {
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
            "binance_spot_verification": {
                "path": SPOT_EVIDENCE_RELATIVE,
                "file_sha256": sha256_file(repo_root / SPOT_EVIDENCE_RELATIVE),
            },
            "candle_verification": {
                "path": CANDLE_EVIDENCE_RELATIVE,
                "file_sha256": sha256_file(repo_root / CANDLE_EVIDENCE_RELATIVE),
            },
            "datasets": datasets,
        },
        "data_boundary": {
            "note": (
                "The confirmatory-window rules and the development-data boundary are unchanged by "
                "this amendment; they are copied here so that the effective boundary is readable "
                "from a single artifact."
            ),
            "confirmatory_window_start_utc": freeze.get("data_boundary", {}).get(
                "confirmatory_window_start_utc"
            ),
            "min_confirmatory_window_hours": freeze.get("data_boundary", {}).get(
                "min_confirmatory_window_hours"
            ),
            "earliest_possible_confirmatory_window_end_utc": freeze.get("data_boundary", {}).get(
                "earliest_possible_confirmatory_window_end_utc"
            ),
            "single_use": freeze.get("data_boundary", {}).get("single_use"),
            "v1_holdout_reuse": freeze.get("data_boundary", {}).get("v1_holdout_reuse"),
            "v2_confirmatory_window_reuse": freeze.get("data_boundary", {}).get(
                "v2_confirmatory_window_reuse"
            ),
            "window_moved_by_this_amendment": False,
        },
        "precedence": {
            "rule": (
                "The validated candidate set recorded in this amendment is the v3 candidate set. "
                "The derived batch in the frozen artifact is the pre-validation batch and is "
                "superseded by reference. Everything else the frozen artifact records -- the "
                "snapshot identity, the confirmatory-window rules, the selection remainder and the "
                "authorization flags -- is unchanged."
            ),
            "unchanged": [
                "snapshot_identity",
                "data_boundary",
                "selection_remainder",
                "execution_authorization",
                "related_artifacts",
                "durability",
            ],
            "superseded": ["frozen_candidate_set"],
            "resolution_rule": (
                "A verifier that reads the v3 candidate set resolves it through this amendment "
                "when the amendment is present and verified, and refuses to accept the frozen "
                "artifact's derived batch as the candidate set."
            ),
        },
        "prerequisite_status": {
            "P1": "DELIVERED_BY_REFERENCE",
            "P2": "DELIVERED_BY_REFERENCE",
            "P3": "DELIVERED_BY_REFERENCE",
            "P4": "DELIVERED_BY_THIS_AMENDMENT",
            "P5": "OUTSTANDING",
            "P6": "OUTSTANDING",
            "note": (
                "configs/research_v3.json is immutable and still records P2, P3 and P4 as "
                "OUTSTANDING; that statement describes the specification's own scope at freeze "
                "time and is not rewritten here. P5 (the v3 execution protocol and the bounded run "
                "authorization) and P6 (the v3 confirmatory protocol) are not delivered."
            ),
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "This amendment authorizes nothing. It records the validated candidate set, the "
                "exclusions and the prerequisite status only."
            ),
        },
        "related_artifacts": {
            "v3_specification": {
                "path": SPEC_RELATIVE,
                "specification_hash": spec.get("specification_hash"),
            },
            "v3_exclusion_amendment": {
                "path": EXCLUSION_AMENDMENT_RELATIVE,
                "amendment_hash": read_json(repo_root / EXCLUSION_AMENDMENT_RELATIVE).get(
                    "amendment_hash"
                ),
            },
            "v3_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
                "file_sha256": sha256_file(repo_root / FREEZE_RELATIVE),
            },
            "v3_universe_manifest": {
                "path": UNIVERSE_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
            },
            "v3_data_manifest": {
                "path": DATA_RELATIVE,
                "manifest_hash": data.get("manifest_hash"),
            },
            "v1_anchors": {
                relative: sha256_file(repo_root / relative) for (relative,) in V1_ANCHORS
            },
        },
        "producer": {
            "path": "scripts/build_v3_candidate_freeze_amendment_1.py",
            "verify_command": "python3 scripts/verify_v3_candidate_freeze_amendment_1.py",
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
        "validated_candidates": [member["binance_pair"] for member in
                                 document["validated_candidate_set"]["members"]],
        "excluded_candidates": [member["binance_pair"] for member in
                                document["excluded_candidates"]["members"]],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

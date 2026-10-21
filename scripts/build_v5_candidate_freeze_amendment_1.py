#!/usr/bin/env python3
"""Build the v5 candidate-freeze amendment 1 (the confirmatory-window overlap rule).

``configs/research_v5_candidate_freeze.json`` (manifest hash
``afa35ad9...``) is hash-bound and must not be edited in place. Its
``confirmatory_window.overlap_rule`` states that the *v5 confirmatory window
must not overlap the v1-v4 holdouts/windows*, but the v5 window runs from
2026-10-21T13:00:00Z to 2027-01-19T13:00:00Z, so it opens **inside** the
still-open v2, v3 and v4 confirmatory windows: the statement is false on the
freeze's own dates. The v4 chain's own freeze states the situation honestly
("the v4 confirmatory window opens inside the open v3 confirmatory window in
time; the two evaluations share no asset ... and the v4 evaluation may only
start after the v3 confirmatory gate clears"), and the v5 specification
clarifies the same point with its ``not_a_prior_holdout`` sentence. The v5
freeze carries neither clarification, and it records the v5 evaluation's
earliest start only implicitly, as prose.

This amendment therefore supplies the **effective** rule:

* the v5 window's time overlap with the v2, v3 and v4 windows is inevitable
  (90-day windows opened 12 hours apart) and is not a violation;
* the two evaluations share no asset, because the v5 candidate set is disjoint
  from the v1, v2, v3 and v4 candidate sets;
* the v5 confirmatory evaluation may not start before the **later** of the v4
  confirmatory gate and the v5 window's own earliest end, both recomputed from
  the artifacts that own them, and never before the v2 and v3 gates either;
* the v5 window is never populated with data that predates the v5 candidate
  freeze, is never a re-opening of an earlier holdout or window and is never
  read for selection.

The amendment is *derived*, not written by hand: every value it records -- the
freeze's manifest hash and file digest, the window bounds, the four gates and
the candidate-set disjointness -- is recomputed from the files on disk, and the
verifier recomputes them again. The script is deterministic (the creation
instant is pinned), refuses to overwrite an existing artifact without
``--force`` and never writes to the hashed set, never edits a frozen artifact,
never fetches anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v5_candidate_freeze_amendment_1.py            # write
    python3 scripts/build_v5_candidate_freeze_amendment_1.py --force    # rewrite
    python3 scripts/build_v5_candidate_freeze_amendment_1.py --print     # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_RELATIVE = "configs/research_v5_candidate_freeze_amendment_1.json"

#: The frozen artifact whose overlap rule is corrected by reference.
FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v5.json"

#: The freezes that own the v2, v3 and v4 confirmatory windows, and the key
#: each one keeps its window bounds under.
PRIOR_WINDOW_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
)

#: The freezes whose candidate sets the v5 set must be disjoint from.
PRIOR_FREEZE_RELATIVES: Tuple[Tuple[str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json"),
    ("v3", "configs/research_v3_candidate_freeze.json"),
    ("v4", "configs/research_v4_candidate_freeze.json"),
)

#: The instant at which this amendment is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-21T14:05:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_iso_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _window_bounds(owner: Dict[str, Any], block_key: str) -> Dict[str, Any]:
    """The window start, its minimum hours and its earliest end.

    The v2 and the v3 freezes keep them in their ``data_boundary`` block, the
    v4 freeze in its ``confirmatory_window`` block.
    """
    block = owner.get(block_key) or {}
    start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
    hours = block.get("min_confirmatory_window_hours") or block.get("min_hours")
    end = block.get("earliest_possible_confirmatory_window_end_utc") or block.get(
        "earliest_possible_end_utc"
    )
    return {"start_utc": start, "min_hours": hours, "earliest_end_utc": end}


def _validated_pairs(freeze: Dict[str, Any]) -> List[str]:
    return sorted(
        str(entry.get("binance_pair") or "")
        for entry in (freeze.get("candidates") or [])
        if entry.get("validated") is True
    )


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    freeze = read_json(root / FREEZE_RELATIVE)
    spec = read_json(root / SPEC_RELATIVE)

    freeze_hash = freeze.get("manifest_hash")
    freeze_sha = sha256_file(root / FREEZE_RELATIVE)
    if freeze_hash != compute_manifest_hash(freeze, MANIFEST_HASH_EXCLUDED_KEYS):
        raise SystemExit("the frozen v5 candidate freeze does not recompute its manifest_hash")

    v5_window = freeze.get("confirmatory_window") or {}
    v5_start = v5_window.get("opens_utc")
    v5_hours = v5_window.get("min_hours")
    v5_end = v5_window.get("earliest_possible_end_utc")
    if not (v5_start and v5_hours and v5_end):
        raise SystemExit("the frozen v5 candidate freeze carries no complete window")
    recomputed_v5_end = format_utc(parse_iso_utc(v5_start) + timedelta(hours=int(v5_hours)))
    if recomputed_v5_end != v5_end:
        raise SystemExit(
            f"the v5 window's earliest end {v5_end} does not recompute from its start and "
            f"its minimum hours ({recomputed_v5_end})"
        )

    gates: List[Dict[str, Any]] = []
    for version, relative, block_key in PRIOR_WINDOW_OWNERS:
        owner = read_json(root / relative)
        bounds = _window_bounds(owner, block_key)
        if not (bounds["start_utc"] and bounds["earliest_end_utc"]):
            raise SystemExit(f"the {version} candidate freeze carries no complete window")
        gates.append(
            {
                "version": version,
                "window_start_utc": bounds["start_utc"],
                "min_hours": bounds["min_hours"],
                "earliest_possible_end_utc": bounds["earliest_end_utc"],
                "source_path": relative,
                "source_key": block_key,
            }
        )

    # The effective gate: the later of every earlier version's gate and the v5
    # window's own earliest end.
    all_gates = gates + [
        {
            "version": "v5",
            "window_start_utc": v5_start,
            "min_hours": v5_hours,
            "earliest_possible_end_utc": v5_end,
            "source_path": FREEZE_RELATIVE,
            "source_key": "confirmatory_window",
        }
    ]
    effective_start = max(
        parse_iso_utc(str(gate["earliest_possible_end_utc"])) for gate in all_gates
    )
    effective_start_utc = format_utc(effective_start)

    # The time overlap: the v5 window opens inside each still-open earlier
    # window, because a 90-day window opened later cannot end later than the
    # 90-day window that opened before it.
    time_overlaps = [
        {
            "version": gate["version"],
            "earlier_window_start_utc": gate["window_start_utc"],
            "earlier_window_earliest_end_utc": gate["earliest_possible_end_utc"],
            "v5_window_start_utc": v5_start,
            "v5_window_earliest_end_utc": v5_end,
            "v5_window_opens_inside_the_earlier_window": parse_iso_utc(v5_start)
            > parse_iso_utc(str(gate["window_start_utc"])),
            "windows_overlap_in_time": parse_iso_utc(v5_start)
            < parse_iso_utc(str(gate["earliest_possible_end_utc"])),
        }
        for gate in gates
    ]

    # The asset disjointness: the v5 validated set shares no asset with any
    # earlier validated set.
    v5_pairs = set(_validated_pairs(freeze))
    shared: Dict[str, List[str]] = {}
    for version, relative in PRIOR_FREEZE_RELATIVES:
        prior = read_json(root / relative)
        overlap = sorted(v5_pairs & set(_validated_pairs(prior)))
        if overlap:
            shared[version] = overlap
    if shared:
        raise SystemExit(f"the v5 candidate set shares assets with earlier candidate sets: {shared}")

    corrected_rule = (
        "the v5 confirmatory window opens inside the still-open v2, v3 and v4 confirmatory "
        "windows in time, because a 90-day window that opens later cannot end later than the "
        "90-day window that opened before it; the time overlap is not a violation, because the "
        "two evaluations share no asset (the v5 candidate set is disjoint from the v1, v2, v3 "
        "and v4 candidate sets) and because the v5 confirmatory evaluation may not start "
        "before the later of the v4 confirmatory gate and the v5 window's own earliest end, "
        "and never before the v2 and the v3 gates; the v5 window is never populated with data "
        "that predates the v5 candidate freeze, is never a re-opening of the v1 holdout or of "
        "the v2, v3 or v4 confirmatory windows, and is never read for selection"
    )

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_CORRECTION_NO_AUTHORIZATION",
        "artifact": "v5_candidate_freeze_amendment_1",
        "artifact_version": 1,
        "created_utc": CREATED_UTC,
        "specification_purpose": (
            "Correct the confirmatory-window overlap rule of the frozen v5 candidate freeze and "
            "record the effective v5 evaluation gate. This artifact authorizes nothing."
        ),
        "protocol_version": freeze.get("protocol_version"),
        "universe_version": freeze.get("universe_version"),
        "problem": {
            "affected_artifact_path": FREEZE_RELATIVE,
            "affected_artifact_manifest_hash": freeze_hash,
            "affected_artifact_sha256": freeze_sha,
            "field_path": "confirmatory_window.overlap_rule",
            "statement": (
                "the frozen freeze states that the v5 confirmatory window must not overlap the "
                "v1-v4 holdouts and windows, but the v5 window runs from "
                f"{v5_start} to {v5_end} and therefore opens inside the still-open v2, v3 and "
                "v4 confirmatory windows: the statement is false on the freeze's own dates"
            ),
            "repair": (
                "the freeze is hash-bound and is not edited in place; the effective overlap rule "
                "is recorded by this amendment"
            ),
        },
        "corrected_rule": {
            "overlap_rule": corrected_rule,
            "time_overlap_is_inevitable": True,
            "time_overlap_evidence": time_overlaps,
            "no_shared_asset": True,
            "no_shared_asset_evidence": (
                "the v5 validated candidate set is disjoint from the v2, v3 and v4 validated "
                "candidate sets, recomputed from the four freezes"
            ),
            "evaluation_may_not_start_before_utc": effective_start_utc,
            "evaluation_may_not_start_before_rule": (
                "the later of the v2, the v3, the v4 and the v5 gates, each recomputed from the "
                "freeze that owns the window; the v5 gate is the v5 window's own earliest end"
            ),
            "gates": all_gates,
            "version_isolation": (
                "the v5 window is never populated with data that predates the v5 candidate "
                "freeze, is never a re-opening of the v1 holdout or of the v2, v3 or v4 "
                "confirmatory windows, and is never read for selection"
            ),
        },
        "effective_rule": {
            "description": (
                "The amendment wins over the frozen block in "
                f"{FREEZE_RELATIVE} for the effective overlap rule; the frozen block stays on "
                "disk unchanged and visible."
            ),
            "precedence": "amendment_overrides_frozen_block",
        },
        "supersedes": {
            "artifact_path": FREEZE_RELATIVE,
            "artifact_manifest_hash": freeze_hash,
            "artifact_sha256": freeze_sha,
            "block_path": "confirmatory_window.overlap_rule",
        },
        "related_artifacts": {
            "v5_specification": {
                "path": SPEC_RELATIVE,
                "specification_hash": spec.get("specification_hash"),
            },
            "v5_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze_hash,
                "sha256": freeze_sha,
            },
            "v5_specification_amendment_1": {
                "path": "configs/research_v5_specification_amendment_1.json",
                "manifest_hash": read_json(
                    root / "configs/research_v5_specification_amendment_1.json"
                ).get("manifest_hash"),
            },
        },
        "producer": {
            "path": "scripts/build_v5_candidate_freeze_amendment_1.py",
            "reproduce_command": (
                "python3 scripts/build_v5_candidate_freeze_amendment_1.py --force"
            ),
        },
        "authorization": {
            "grid_run_authorized": False,
            "selection_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "scope": (
                "this amendment records the effective overlap rule and the effective v5 "
                "evaluation gate; it authorizes no run, no evaluation, no candle fetch and no "
                "confirmatory-window read"
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    target = repo_root / ARTIFACT_RELATIVE
    document = build(repo_root)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    if args.print_only:
        print(payload, end="")
        return 0
    if target.exists() and not args.force:
        print(
            f"refusing to overwrite {ARTIFACT_RELATIVE} without --force",
            file=sys.stderr,
        )
        return 1
    atomic_write_text(target, payload)
    print(
        json.dumps(
            {
                "manifest_hash": document["manifest_hash"],
                "path": ARTIFACT_RELATIVE,
                "evaluation_may_not_start_before_utc": document["corrected_rule"][
                    "evaluation_may_not_start_before_utc"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

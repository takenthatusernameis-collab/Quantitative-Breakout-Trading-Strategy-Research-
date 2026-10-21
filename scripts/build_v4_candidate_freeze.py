#!/usr/bin/env python3
"""Build the v4 candidate manifest freeze.

The freeze is the artifact that binds the v4 candidate set before any v4
evaluation runs. It records:

* the frozen candidate set (the validated constituents of
  ``research/universe_manifest_v4.json``, with the exclusion reason of every
  member that did not validate);
* the data boundary: the earlier of the v4 confirmatory-window start and the
  preregistered development cutoff
  (``configs/research_v4.json#holdout.development_cutoff_utc``), so that no
  v4 development dataset and no v4 selection read ever touches a candle that
  closes inside the open v3 confirmatory window;
* the v4 confirmatory window, whose earliest possible end is computed from its
  own start and the minimum window length;
* the ``supersedes`` chain from the v3 candidate freeze.

The freeze instant is an input (``--freeze-utc``) and is recorded in the
artifact, so the artifact is reproducible: rebuilding it with the recorded
instant reproduces it byte for byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_PATH = REPO_ROOT / "configs" / "research_v4.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v4.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v4.json"
ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"
V3_FREEZE_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"

MANIFEST_HASH_EXCLUDED_KEYS = ["manifest_hash"]


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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: List[str] = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def first_hour_boundary_after(value: datetime) -> datetime:
    """The first UTC hour boundary strictly after ``value``."""
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if boundary <= value:
        boundary += timedelta(hours=1)
    return boundary


def build(repo_root: Path = REPO_ROOT, freeze_utc: Optional[str] = None) -> Dict[str, Any]:
    spec = json.loads((repo_root / "configs" / "research_v4.json").read_text(encoding="utf-8"))
    universe = json.loads((repo_root / "research" / "universe_manifest_v4.json").read_text(encoding="utf-8"))
    data_manifest = json.loads((repo_root / "research" / "data_manifest_v4.json").read_text(encoding="utf-8"))
    v3_freeze = json.loads((repo_root / "configs" / "research_v3_candidate_freeze.json").read_text(encoding="utf-8"))

    freeze_instant = parse_iso_utc(freeze_utc) if freeze_utc else datetime.now(timezone.utc)
    window_open = first_hour_boundary_after(freeze_instant)
    min_hours = int(spec["holdout"]["v4_confirmatory_window"]["min_hours"])
    earliest_end = window_open + timedelta(hours=min_hours)
    development_cutoff = parse_iso_utc(spec["holdout"]["development_cutoff_utc"])
    effective_boundary = min(window_open, development_cutoff)

    document: Dict[str, Any] = {
        "artifact": "v4_candidate_freeze",
        "artifact_version": "v4-candidate-freeze-1",
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "manifest_hash": None,
        "candidate_freeze_utc": format_utc(freeze_instant),
        "freeze_status": "FROZEN",
        "specification_purpose": (
            "Freeze the v4 candidate set and the v4 data boundary before any v4 evaluation runs. "
            "This artifact authorizes nothing: it records the candidate set, the boundary and "
            "the confirmatory window."
        ),
        "specification_hash": spec["specification_hash"],
        "universe_manifest_hash": universe["manifest_hash"],
        "universe_manifest_path": "research/universe_manifest_v4.json",
        "data_manifest_hash": data_manifest["manifest_hash"],
        "data_manifest_path": "research/data_manifest_v4.json",
        "snapshot_identity": data_manifest["snapshot_identity"],
        "candidates": universe["eligible_assets"],
        "exclusions": universe["excluded_assets"],
        "data_boundary": {
            "development_data_rule": (
                "Candles that close at or before effective_data_boundary_utc are development "
                "data and may inform selection. No candle that closes after that instant may "
                "be read during selection."
            ),
            "effective_data_boundary_utc": format_utc(effective_boundary),
            "effective_data_boundary_rule": (
                "the earlier of the v4 confirmatory-window start and the preregistered "
                "development cutoff; the v4 confirmatory window opens inside the open v3 "
                "confirmatory window, so the development cutoff is the binding boundary"
            ),
            "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
            "development_cutoff_rule": (
                "configs/research_v4.json#holdout.development_cutoff_utc: any development data "
                "read at or after the v3 confirmatory-window open is inside that window, so the "
                "v4 development data ends at the cutoff: the last development candle is the one "
                "that closes exactly at the cutoff, and no candle that closes after the cutoff "
                "may be read"
            ),
            "v4_confirmatory_window_start_utc": format_utc(window_open),
            "v4_confirmatory_window_start_rule": (
                "the first UTC hour boundary strictly after candidate_freeze_utc"
            ),
            "min_confirmatory_window_hours": min_hours,
            "min_confirmatory_window_rationale": spec["holdout"]["v4_confirmatory_window"]["min_hours_rationale"],
            "earliest_possible_confirmatory_window_end_utc": format_utc(earliest_end),
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
            "v3_confirmatory_window_reuse": "forbidden",
            "single_use": True,
            "no_ranking_or_retuning_on_holdout": True,
            "data_used_for_candidate_selection": "excluded",
            "access_counting": (
                "Every read of a candle inside a confirmatory window increments "
                "holdout_exposed_count in the checkpoint of that version and is recorded in "
                "its holdout report."
            ),
        },
        "confirmatory_window": {
            "opens_utc": format_utc(window_open),
            "min_hours": min_hours,
            "earliest_possible_end_utc": format_utc(earliest_end),
            "single_use": True,
            "overlap_rule": (
                "the v4 confirmatory window opens inside the open v3 confirmatory window in "
                "time; the two evaluations share no asset, because the v4 candidate set is "
                "disjoint from the v1, v2 and v3 candidate sets, and the v4 evaluation may "
                "only start after the v3 confirmatory gate clears (BRAIN-013 phase gates)"
            ),
        },
        "supersedes": {
            "v3_candidate_freeze_path": "configs/research_v3_candidate_freeze.json",
            "v3_candidate_freeze_sha256": sha256_file(repo_root / "configs" / "research_v3_candidate_freeze.json"),
            "v3_candidate_freeze_hash": v3_freeze.get("manifest_hash"),
            "reason": (
                "The v3 candidate set is frozen for the v3 cycle. The v4 batch is a strictly "
                "additional universe below the v3 floor with separate namespaces."
            ),
            "v1_and_v3_artifacts_are_immutable": True,
        },
        "producer": {
            "path": "scripts/build_v4_candidate_freeze.py",
            "reproduce_command": (
                "python3 scripts/build_v4_candidate_freeze.py --freeze-utc "
                "<candidate_freeze_utc> --force"
            ),
            "note": (
                "the freeze instant is an input; rebuilding with the recorded instant "
                "reproduces the artifact byte for byte"
            ),
        },
        "durability": {
            "commit": None,
            "pushed": False,
            "note": (
                "Becomes durable when the commit that carries this artifact exists. The "
                "artifact is not rewritten after that commit, because its manifest_hash must "
                "not change."
            ),
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


def write_document(document: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--freeze-utc", default=None,
                        help="the freeze instant (ISO-8601, UTC); defaults to now")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    document = build(Path(args.repo_root), args.freeze_utc)
    if ARTIFACT_PATH.exists() and not args.force:
        print("exists without --force", file=sys.stderr)
        return 1
    write_document(document, ARTIFACT_PATH)
    print(json.dumps({
        "artifact_path": str(ARTIFACT_PATH.relative_to(REPO_ROOT)),
        "candidate_freeze_utc": document["candidate_freeze_utc"],
        "candidates": [
            member["binance_pair"] for member in document["candidates"]
            if member.get("validated") is True
        ],
        "effective_data_boundary_utc": document["data_boundary"]["effective_data_boundary_utc"],
        "manifest_hash": document["manifest_hash"],
        "v4_confirmatory_window_opens_utc": document["confirmatory_window"]["opens_utc"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the v5 candidate manifest freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The artifacts the freeze is bound to, relative to the repository root, so
#: the producer can rebuild the freeze from any checkout.
SPEC_RELATIVE = "configs/research_v5.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v5.json"
DATA_RELATIVE = "research/data_manifest_v5.json"
ARTIFACT_RELATIVE = "configs/research_v5_candidate_freeze.json"
V4_FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
AMENDMENT_RELATIVE = "configs/research_v5_specification_amendment_1.json"

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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
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
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if boundary <= value:
        boundary += timedelta(hours=1)
    return boundary


def build(repo_root: Path = REPO_ROOT, freeze_utc: Optional[str] = None) -> Dict[str, Any]:
    spec = json.loads((repo_root / SPEC_RELATIVE).read_text(encoding="utf-8"))
    universe = json.loads((repo_root / UNIVERSE_RELATIVE).read_text(encoding="utf-8"))
    data_manifest = json.loads((repo_root / DATA_RELATIVE).read_text(encoding="utf-8"))
    v4_freeze = json.loads((repo_root / V4_FREEZE_RELATIVE).read_text(encoding="utf-8"))
    amendment = json.loads((repo_root / AMENDMENT_RELATIVE).read_text(encoding="utf-8"))

    freeze_instant = parse_iso_utc(freeze_utc) if freeze_utc else datetime.now(timezone.utc)
    window_open = first_hour_boundary_after(freeze_instant)
    min_hours = 2160
    earliest_end = window_open + timedelta(hours=min_hours)
    development_cutoff = parse_iso_utc(spec["holdout"]["development_cutoff_utc"])

    document: Dict[str, Any] = {
        "artifact": "v5_candidate_freeze",
        "artifact_version": "v5-candidate-freeze-1",
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "manifest_hash": None,
        "candidate_freeze_utc": format_utc(freeze_instant),
        "freeze_status": "FROZEN",
        "specification_purpose": "Freeze the v5 candidate set and data boundary before any v5 evaluation runs. This artifact authorizes nothing.",
        "specification_hash": spec["specification_hash"],
        "universe_manifest_hash": universe["manifest_hash"],
        "universe_manifest_path": UNIVERSE_RELATIVE,
        "data_manifest_hash": data_manifest["manifest_hash"],
        "data_manifest_path": DATA_RELATIVE,
        "snapshot_identity": data_manifest["snapshot_identity"],
        "candidates": universe["eligible_assets"],
        "exclusions": universe["excluded_assets"],
        "data_boundary": {
            "development_data_rule": "Candles that close at or before effective_data_boundary_utc are development data and may inform selection. No candle that closes after that instant may be read during selection.",
            "effective_data_boundary_utc": format_utc(development_cutoff),
            "effective_data_boundary_rule": "v5 uses the preregistered development cutoff (v2 window start) as the binding boundary; the v5 confirmatory window opens after freeze.",
            "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
            "development_cutoff_rule": spec["holdout"]["development_cutoff_rule"],
            "confirmatory_window_membership_rule": amendment["corrected_rule"]["rule"],
            "confirmatory_window_membership_amendment_path": AMENDMENT_RELATIVE,
            "confirmatory_window_membership_amendment_hash": amendment["manifest_hash"],
            "v5_confirmatory_window_start_utc": format_utc(window_open),
            "v5_confirmatory_window_start_rule": "the first UTC hour boundary strictly after candidate_freeze_utc",
            "min_confirmatory_window_hours": min_hours,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after freeze",
            "earliest_possible_confirmatory_window_end_utc": format_utc(earliest_end),
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
            "v3_confirmatory_window_reuse": "forbidden",
            "v4_confirmatory_window_reuse": "forbidden",
            "single_use": True,
            "no_ranking_or_retuning_on_holdout": True,
            "data_used_for_candidate_selection": "excluded",
            "access_counting": "Every read of a candle inside a confirmatory window increments holdout_exposed_count in the checkpoint of that version and is recorded in its holdout report.",
        },
        "confirmatory_window": {
            "opens_utc": format_utc(window_open),
            "min_hours": min_hours,
            "earliest_possible_end_utc": format_utc(earliest_end),
            "single_use": True,
            "overlap_rule": "v5 confirmatory window must not overlap v1-v4 holdouts/windows; evaluation only after v4 gate clears and window elapses",
        },
        "supersedes": {
            "v4_candidate_freeze_path": V4_FREEZE_RELATIVE,
            "v4_candidate_freeze_sha256": sha256_file(repo_root / V4_FREEZE_RELATIVE),
            "v4_candidate_freeze_hash": v4_freeze.get("manifest_hash"),
            "reason": "The v4 candidate set is frozen for the v4 cycle. The v5 batch is a strictly additional universe below the v4 floor with separate namespaces.",
            "v1_v2_v3_v4_artifacts_are_immutable": True,
        },
        "producer": {
            "path": "scripts/build_v5_candidate_freeze.py",
            "reproduce_command": "python3 scripts/build_v5_candidate_freeze.py --freeze-utc <candidate_freeze_utc> --force",
        },
        "durability": {"commit": None, "pushed": False},
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": MANIFEST_HASH_EXCLUDED_KEYS,
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--freeze-utc")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root)
    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(json.dumps({"ok": False, "error": "artifact exists; use --force to overwrite"}, indent=2))
        return 1
    document = build(repo_root, args.freeze_utc)
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": ARTIFACT_RELATIVE, "manifest_hash": document["manifest_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

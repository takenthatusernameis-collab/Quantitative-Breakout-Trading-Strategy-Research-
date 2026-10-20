#!/usr/bin/env python3
"""Append the v3 entry to the append-only cross-version universe expansion log.

``configs/research_v3.json`` (``expansion_program``) requires an append-only
hash-chained log at ``research/v_universe_expansion_log.json``: every universe
version appends exactly one entry, and every entry carries its own hash and the
hash of the previous entry, so the history is verifiable and never rewritten.

The v1 and v2 universes predate this log -- it was introduced with BRAIN-012
recommendation 7 -- so the chain starts with the v3 entry, whose
``previous_entry_hash`` is ``null``. Every later version appends after it.

The entry is *derived*, not written by hand: the candidate batch, the validated
set, the exclusions, the snapshot identity and the new floor are read from the
frozen v3 manifests and recomputed from the files on disk. The script never
fetches anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v3_universe_expansion_log.py            # write
    python3 scripts/build_v3_universe_expansion_log.py --force    # rewrite
    python3 scripts/build_v3_universe_expansion_log.py --print     # print only
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
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

LOG_PATH = REPO_ROOT / "research" / "v_universe_expansion_log.json"

SPEC_RELATIVE = "configs/research_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
V2_UNIVERSE_RELATIVE = "research/universe_manifest_v2.json"

#: The instant at which the log file is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once it is committed.
CREATED_UTC = "2026-10-20T12:50:00Z"

#: The minimum interval between two passes, from the frozen specification.
CADENCE_INTERVAL = timedelta(days=7)


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


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


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


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return sha256_bytes(canonical(body).encode("utf-8"))


def build_entry(repo_root: Path, previous_entry_hash: Optional[str]) -> Dict[str, Any]:
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)
    v2_universe = read_json(repo_root / V2_UNIVERSE_RELATIVE)

    candidates = sorted(
        universe.get("eligible_assets") or [],
        key=lambda item: int(item.get("rank") or 0),
    )
    if not candidates:
        raise SystemExit("the v3 universe manifest has no eligible assets")

    validated = [entry for entry in candidates if entry.get("validated")]
    excluded = [entry for entry in candidates if not entry.get("validated")]

    floor = spec["universe"]["expansion_scope"]["prior_universe_floor"]
    v2_assets = v2_universe.get("eligible_assets") or []
    v2_floor_asset = min(v2_assets, key=lambda item: float(item.get("market_cap_usd") or 0))
    if v2_floor_asset.get("market_cap_usd") != floor.get("floor_market_cap_usd"):
        raise SystemExit(
            "the recorded v2 floor does not match the minimum market capitalization of "
            "research/universe_manifest_v2.json"
        )

    lowest_candidate = candidates[-1]
    lowest_validated = validated[-1] if validated else None

    market_cap_source = universe.get("market_cap_source") or {}
    snapshot = {
        "endpoint": market_cap_source.get("endpoint"),
        "provider": market_cap_source.get("provider"),
        "raw_response_hash": market_cap_source.get("raw_response_hash"),
        "retrieval_timestamp_utc": market_cap_source.get("retrieval_timestamp_utc"),
        "ranking_depth": len(universe.get("excluded_assets") or []) + len(candidates),
    }

    entry: Dict[str, Any] = {
        "universe_version": universe.get("universe_version"),
        "protocol_version": universe.get("protocol_version"),
        "created_utc": universe.get("created_utc"),
        "specification_hash": universe.get("specification_hash"),
        "manifest": {
            "path": UNIVERSE_RELATIVE,
            "manifest_hash": universe.get("manifest_hash"),
            "file_sha256": sha256_file(repo_root / UNIVERSE_RELATIVE),
        },
        "data_manifest": {
            "path": DATA_RELATIVE,
            "manifest_hash": data.get("manifest_hash"),
            "file_sha256": sha256_file(repo_root / DATA_RELATIVE),
        },
        "snapshot": snapshot,
        "prior_universe_floor": {
            "source_universe_version": floor.get("source_universe_version"),
            "source_manifest_path": floor.get("source_manifest_path"),
            "source_manifest_hash": floor.get("source_manifest_hash"),
            "floor_symbol": v2_floor_asset.get("binance_pair") or floor.get("floor_symbol"),
            "floor_market_cap_usd": v2_floor_asset.get("market_cap_usd"),
            "comparison": floor.get("comparison"),
        },
        "candidate_batch": {
            "count": len(candidates),
            "rule": (
                "assets of the fresh snapshot strictly below the recorded v2 floor, minus the "
                "prior-universe assets and the published exclusion rules"
            ),
            "members": [
                {
                    "binance_pair": entry.get("binance_pair") or f"{entry.get('symbol')}USDT",
                    "coingecko_id": entry.get("coingecko_id"),
                    "market_cap_usd": entry.get("market_cap_usd"),
                    "name": entry.get("name"),
                    "rank": entry.get("rank"),
                    "symbol": entry.get("symbol"),
                }
                for entry in candidates
            ],
        },
        "validated_candidate_set": {
            "count": len(validated),
            "members": [
                {
                    "binance_pair": entry.get("binance_pair") or f"{entry.get('symbol')}USDT",
                    "content_hash": ((data.get("assets") or {}).get(
                        entry.get("binance_pair") or f"{entry.get('symbol')}USDT") or {}).get(
                            "content_hash"),
                    "market_cap_usd": entry.get("market_cap_usd"),
                    "rank": entry.get("rank"),
                }
                for entry in validated
            ],
        },
        "excluded_candidates": {
            "count": len(excluded),
            "members": [
                {
                    "binance_pair": entry.get("binance_pair") or f"{entry.get('symbol')}USDT",
                    "exclusion_reason": entry.get("exclusion_reason"),
                    "market_cap_usd": entry.get("market_cap_usd"),
                    "observed_candles": entry.get("observed_candles"),
                    "rank": entry.get("rank"),
                }
                for entry in excluded
            ],
        },
        "new_floor": {
            "rule": spec["expansion_program"]["floor_rule"],
            "symbol": lowest_candidate.get("binance_pair") or lowest_candidate.get("symbol"),
            "market_cap_usd": lowest_candidate.get("market_cap_usd"),
            "basis": "lowest_ranked_candidate_of_this_version",
            "validated_set_floor": {
                "symbol": (lowest_validated.get("binance_pair")
                           or lowest_validated.get("symbol")) if lowest_validated else None,
                "market_cap_usd": lowest_validated.get("market_cap_usd") if lowest_validated else None,
                "note": (
                    "recorded for transparency: the floor rule of the specification uses the "
                    "lowest-ranked candidate of the version, not the lowest-ranked validated "
                    "constituent"
                ),
            },
        },
        "program_state": {
            "state": "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION",
            "rule": spec["expansion_program"]["routing"],
            "cadence_mode": spec["expansion_program"]["cadence"]["mode"],
            "minimum_interval_between_passes": spec["expansion_program"]["cadence"][
                "minimum_interval_between_passes"],
            "earliest_next_pass_utc": (
                parse_iso_utc(universe.get("created_utc")) + CADENCE_INTERVAL
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "polling_forbidden": spec["expansion_program"]["cadence"]["polling_forbidden"],
        },
        "holdout": {
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
            "rule": (
                "a v3 expansion never reads, re-times, reuses or extends the v2 confirmatory "
                "window, and never touches the v2 holdout exposure counter"
            ),
        },
        "previous_entry_hash": previous_entry_hash,
    }
    entry["entry_hash"] = compute_entry_hash(entry)
    return entry


def build(repo_root: Path = REPO_ROOT, rebuild: bool = False) -> Dict[str, Any]:
    existing: Dict[str, Any] = {}
    if LOG_PATH.exists():
        existing = read_json(LOG_PATH)
    entries: List[Dict[str, Any]] = list(existing.get("entries") or [])
    if any(entry.get("universe_version") == "v3" for entry in entries):
        if not rebuild:
            raise SystemExit(
                "the expansion log already holds a v3 entry; the log is append-only, so a "
                "second v3 entry may not be appended"
            )
        if [entry.get("universe_version") for entry in entries] != ["v3"]:
            raise SystemExit(
                "refusing to rewrite a log that holds entries of later universe versions; "
                "the log is append-only"
            )
        entries = []
    previous_entry_hash = entries[-1].get("entry_hash") if entries else None
    entry = build_entry(repo_root, previous_entry_hash)
    entries.append(entry)
    return {
        "artifact": "v_universe_expansion_log",
        "artifact_version": 1,
        "log_mode": "append_only_hash_chain",
        "log_path": "research/v_universe_expansion_log.json",
        "created_utc": CREATED_UTC,
        "genesis_note": (
            "The v1 and v2 universes predate this log, which was introduced with BRAIN-012 "
            "recommendation 7. The chain therefore starts with the v3 entry, whose "
            "previous_entry_hash is null; every later universe version appends after it."
        ),
        "entry_rule": spec_entry_rule(repo_root),
        "entry_count": len(entries),
        "entries": entries,
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "entry_hash_rule": (
                "entry_hash is the sha256 of the entry body with the entry_hash key removed"
            ),
            "chain_rule": "each entry's previous_entry_hash is the entry_hash of its predecessor",
        },
        "producer": {
            "path": "scripts/build_v3_universe_expansion_log.py",
            "verify_command": "python3 scripts/verify_v3_universe_expansion_log.py",
            "deterministic": True,
        },
    }


def spec_entry_rule(repo_root: Path) -> str:
    spec = read_json(repo_root / SPEC_RELATIVE)
    return spec["expansion_program"]["log_entry_rule"]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing log")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root, rebuild=args.force)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    if args.print_only:
        print(payload, end="")
        return 0
    if LOG_PATH.exists() and not args.force:
        print(
            f"refusing to overwrite {LOG_PATH.relative_to(repo_root)} without --force",
            file=sys.stderr,
        )
        return 1
    atomic_write_text(LOG_PATH, payload)
    entry = document["entries"][-1]
    print(json.dumps({
        "path": str(LOG_PATH.relative_to(repo_root)),
        "entry_count": document["entry_count"],
        "entry_hash": entry["entry_hash"],
        "previous_entry_hash": entry["previous_entry_hash"],
        "universe_version": entry["universe_version"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

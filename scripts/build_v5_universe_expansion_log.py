#!/usr/bin/env python3
"""Append the derived v4 and v5 entries to the append-only universe expansion log.

``research/v_universe_expansion_log.json`` is the append-only hash chain that
``configs/research_v3.json`` (``expansion_program``) requires and that
``configs/research_v5.json`` names as the log that exists: every universe
version appends exactly one entry, and every entry carries its own hash and the
hash of the previous entry, so the history is verifiable and never rewritten.

The chain stopped at the v3 entry: the v4 universe version was never appended
to it. ``configs/research_v5.json#expansion_program`` records the two
outstanding entries -- the derived v4 entry and the v5 entry chained onto it --
as prerequisite ``p5``. This producer closes that prerequisite:

* the **v4 entry** is re-derived from the v4 artifacts -- the v4 universe
  manifest, the v4 data manifest, the v4 specification and the v4 raw
  market-cap response -- with its ranking depth *recomputed from the raw
  response bytes*, not copied from anywhere;
* the **v5 entry** is derived from the v5 artifacts the same way, chained onto
  the v4 entry.

The v3 entry is never touched. The producer re-derives it with the v3 producer
and refuses to write the log unless the recorded v3 entry is byte-identical to
the derived one, so an append can never smuggle a rewrite of the history.

Every entry is *derived*, never hand-written. The script never fetches
anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v5_universe_expansion_log.py            # write
    python3 scripts/build_v5_universe_expansion_log.py --force    # rewrite
    python3 scripts/build_v5_universe_expansion_log.py --print    # print only
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

LOG_RELATIVE = "research/v_universe_expansion_log.json"

#: The versions this producer appends, in chain order.
VERSIONS: Tuple[str, ...] = ("v4", "v5")

#: The version whose entry the chain starts from, and the producer that owns it.
GENESIS_VERSION = "v3"
GENESIS_PRODUCER_RELATIVE = "scripts/build_v3_universe_expansion_log.py"

#: The floor rule and the cadence of the log program. The v3 specification
#: froze them; the v4 and v5 specifications restate the cadence but not the
#: floor rule, so the frozen rule of the program is recorded in every entry
#: together with the artifact it is read from.
FLOOR_RULE_RELATIVE = "configs/research_v3.json"

#: The minimum interval between two passes.
CADENCE_INTERVAL = timedelta(days=7)

#: The confirmatory windows that a version's expansion may never read.
PRIOR_WINDOWS = {
    "v4": ("v2", "v3"),
    "v5": ("v2", "v3", "v4"),
}


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


def parse_iso_utc(value: str) -> datetime:
    text = str(value).strip()
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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _version_paths(version: str) -> Dict[str, str]:
    return {
        "spec": f"configs/research_{version}.json",
        "universe": f"research/universe_manifest_{version}.json",
        "data": f"research/data_manifest_{version}.json",
        "raw_response": f"research/{version}_evidence/raw_market_cap_response.json",
    }


def _ranking_depth(repo_root: Path, version: str, relative: str) -> int:
    """The ranking depth, recomputed from the stored raw response bytes.

    The depth is the number of rows of the frozen raw response, read from the
    file the manifest names and verified against the manifest's recorded
    content hash. It is never copied from the manifest or from the
    specification.
    """
    path = repo_root / relative
    if not path.exists():
        raise SystemExit(f"the raw market-cap response {relative} does not exist")
    raw = path.read_bytes()
    rows = json.loads(raw.decode("utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"the raw market-cap response {relative} is not a list of rows")
    return len(rows)


def _floor_rule(repo_root: Path) -> Tuple[str, str]:
    spec = read_json(repo_root / FLOOR_RULE_RELATIVE)
    rule = ((spec.get("expansion_program") or {}).get("floor_rule"))
    if not rule:
        raise SystemExit(
            f"{FLOOR_RULE_RELATIVE} records no floor rule for the expansion log"
        )
    return str(rule), f"{FLOOR_RULE_RELATIVE}#expansion_program.floor_rule"


def _cadence(repo_root: Path, version: str) -> Dict[str, Any]:
    """The bounded cadence of the program, with the artifact it is read from."""
    spec = read_json(repo_root / _version_paths(version)["spec"])
    program = spec.get("expansion_program") or {}
    cadence = program.get("cadence")
    source = f"configs/research_{version}.json#expansion_program.cadence"
    if not cadence:
        cadence = (spec.get("null_result_path") or {}).get("cadence")
        source = f"configs/research_{version}.json#null_result_path.cadence"
    if not cadence:
        # The v4 specification records no cadence of its own: the frozen
        # cadence of the log program applies.
        program_v3 = read_json(repo_root / FLOOR_RULE_RELATIVE).get("expansion_program") or {}
        cadence = program_v3.get("cadence")
        source = f"{FLOOR_RULE_RELATIVE}#expansion_program.cadence"
    if not cadence:
        raise SystemExit("no cadence is recorded for the expansion program")
    return {
        "cadence_mode": str(cadence.get("mode") or cadence.get("cadence_mode")),
        "minimum_interval_between_passes": str(cadence.get("minimum_interval_between_passes")),
        "polling_forbidden": str(cadence.get("polling_forbidden")),
        "cadence_source": source,
    }


def build_entry(repo_root: Path, version: str, previous_entry_hash: Optional[str]) -> Dict[str, Any]:
    """Derive one entry of the log from the artifacts of its own version."""
    repo_root = Path(repo_root)
    paths = _version_paths(version)
    spec = read_json(repo_root / paths["spec"])
    universe = read_json(repo_root / paths["universe"])
    data = read_json(repo_root / paths["data"])

    if universe.get("universe_version") != version:
        raise SystemExit(
            f"the universe manifest {paths['universe']} does not declare the version {version}"
        )

    candidates = sorted(
        universe.get("eligible_assets") or [],
        key=lambda item: int(item.get("rank") or 0),
    )
    if not candidates:
        raise SystemExit(f"the {version} universe manifest has no eligible assets")
    validated = [entry for entry in candidates if entry.get("validated") is True]
    excluded = [entry for entry in candidates if entry.get("validated") is not True]

    # The prior floor is recomputed from the source manifest, never trusted.
    scope = (spec.get("universe") or {}).get("expansion_scope") or {}
    prior = scope.get("prior_universe_floor") or {}
    prior_relative = str(prior.get("source_manifest_path") or "")
    prior_universe = read_json(repo_root / prior_relative)
    prior_assets = prior_universe.get("eligible_assets") or []
    prior_floor_asset = min(prior_assets, key=lambda item: float(item.get("market_cap_usd") or 0))
    if prior_floor_asset.get("market_cap_usd") != prior.get("floor_market_cap_usd"):
        raise SystemExit(
            f"the recorded {version} prior floor does not match the minimum market "
            f"capitalization of {prior_relative}"
        )
    if prior_universe.get("manifest_hash") != prior.get("source_manifest_hash"):
        raise SystemExit(
            f"the recorded {version} prior floor names another source manifest than "
            f"{prior_relative}"
        )

    market_cap_source = universe.get("market_cap_source") or {}
    raw_relative = str(market_cap_source.get("raw_response_path") or paths["raw_response"])
    if sha256_file(repo_root / raw_relative) != market_cap_source.get("raw_response_hash"):
        raise SystemExit(
            f"the raw market-cap response {raw_relative} does not match the hash the "
            f"{version} universe manifest records"
        )
    ranking_depth = _ranking_depth(repo_root, version, raw_relative)
    snapshot = {
        "endpoint": market_cap_source.get("endpoint"),
        "provider": market_cap_source.get("provider"),
        "raw_response_hash": market_cap_source.get("raw_response_hash"),
        "raw_response_path": raw_relative,
        "retrieval_timestamp_utc": market_cap_source.get("retrieval_timestamp_utc"),
        "ranking_depth": ranking_depth,
        "ranking_depth_rule": (
            "the number of rows of the stored raw market-cap response, recomputed from the "
            "raw bytes of the file the manifest names and hashes"
        ),
    }

    lowest_candidate = candidates[-1]
    lowest_validated = validated[-1] if validated else None
    floor_rule, floor_rule_source = _floor_rule(repo_root)
    cadence = _cadence(repo_root, version)

    routing = (spec.get("expansion_program") or {}).get("routing") or {}
    routing_rule = routing.get("on_exhaustion_or_completion_of_frozen_version")
    if not routing_rule:
        routing_rule = (
            (read_json(repo_root / FLOOR_RULE_RELATIVE).get("expansion_program") or {}).get(
                "routing")
        )

    prior_windows = PRIOR_WINDOWS[version]
    holdout = {
        "v1_holdout_reuse": "forbidden",
        "rule": (
            f"a {version} expansion never reads, re-times, reuses or extends the "
            f"{' or '.join(prior_windows)} confirmatory window, and never touches the v1 "
            "holdout or the confirmatory-window exposure counters"
        ),
    }
    for window in prior_windows:
        holdout[f"{window}_confirmatory_window_reuse"] = "forbidden"

    entry: Dict[str, Any] = {
        "universe_version": universe.get("universe_version"),
        "protocol_version": universe.get("protocol_version"),
        "created_utc": universe.get("created_utc"),
        "specification_hash": universe.get("specification_hash"),
        "manifest": {
            "path": paths["universe"],
            "manifest_hash": universe.get("manifest_hash"),
            "file_sha256": sha256_file(repo_root / paths["universe"]),
        },
        "data_manifest": {
            "path": paths["data"],
            "manifest_hash": data.get("manifest_hash"),
            "file_sha256": sha256_file(repo_root / paths["data"]),
        },
        "snapshot": snapshot,
        "prior_universe_floor": {
            "source_universe_version": prior.get("source_universe_version"),
            "source_manifest_path": prior_relative,
            "source_manifest_hash": prior_universe.get("manifest_hash"),
            "floor_symbol": prior_floor_asset.get("binance_pair")
            or prior_floor_asset.get("symbol"),
            "floor_market_cap_usd": prior_floor_asset.get("market_cap_usd"),
            "comparison": prior.get("comparison"),
            "recompute_rule": (
                "the floor is the minimum market_cap_usd over the eligible_assets of the "
                "source manifest; the producer recomputes it from that manifest and never "
                "trusts the recorded value"
            ),
        },
        "candidate_batch": {
            "count": len(candidates),
            "rule": scope.get("rule"),
            "members": [
                {
                    "binance_pair": entry.get("binance_pair")
                    or f"{entry.get('symbol')}USDT",
                    "market_cap_usd": entry.get("market_cap_usd"),
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
                    "binance_pair": entry.get("binance_pair")
                    or f"{entry.get('symbol')}USDT",
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
                    "binance_pair": entry.get("binance_pair")
                    or f"{entry.get('symbol')}USDT",
                    "exclusion_reason": entry.get("exclusion_reason"),
                    "market_cap_usd": entry.get("market_cap_usd"),
                    "observed_candles": entry.get("observed_candles"),
                    "rank": entry.get("rank"),
                }
                for entry in excluded
            ],
        },
        "new_floor": {
            "rule": floor_rule,
            "rule_source": floor_rule_source,
            "symbol": lowest_candidate.get("binance_pair") or lowest_candidate.get("symbol"),
            "market_cap_usd": lowest_candidate.get("market_cap_usd"),
            "basis": "lowest_ranked_candidate_of_this_version",
            "validated_set_floor": {
                "symbol": (lowest_validated.get("binance_pair")
                           or lowest_validated.get("symbol")) if lowest_validated else None,
                "market_cap_usd": (
                    lowest_validated.get("market_cap_usd") if lowest_validated else None
                ),
                "note": (
                    "recorded for transparency: the floor rule uses the lowest-ranked "
                    "candidate of the version, not the lowest-ranked validated constituent"
                ),
            },
        },
        "program_state": {
            "state": "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION",
            "rule": routing_rule,
            "cadence_mode": cadence["cadence_mode"],
            "minimum_interval_between_passes": cadence["minimum_interval_between_passes"],
            "earliest_next_pass_utc": (
                parse_iso_utc(universe.get("created_utc")) + CADENCE_INTERVAL
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "polling_forbidden": cadence["polling_forbidden"],
            "cadence_source": cadence["cadence_source"],
        },
        "holdout": holdout,
        "previous_entry_hash": previous_entry_hash,
    }
    entry["entry_hash"] = compute_entry_hash(entry)
    return entry


def _genesis_entry(repo_root: Path) -> Dict[str, Any]:
    """The v3 entry, re-derived with the v3 producer."""
    module = _load_module("build_v3_universe_expansion_log", GENESIS_PRODUCER_RELATIVE)
    return module.build_entry(Path(repo_root), None)


def build(repo_root: Path = REPO_ROOT, rebuild: bool = False) -> Dict[str, Any]:
    """The log with the derived v4 and v5 entries appended."""
    repo_root = Path(repo_root)
    log_path = repo_root / LOG_RELATIVE
    if not log_path.exists():
        raise SystemExit(f"the expansion log {LOG_RELATIVE} does not exist")
    existing = read_json(log_path)
    entries: List[Dict[str, Any]] = [json.loads(json.dumps(entry))
                                     for entry in (existing.get("entries") or [])]
    if not entries:
        raise SystemExit("the expansion log holds no entry")

    versions = [entry.get("universe_version") for entry in entries]
    if versions[0] != GENESIS_VERSION:
        raise SystemExit(
            f"the expansion log does not start with the {GENESIS_VERSION} entry; it starts "
            f"with {versions[0]!r}"
        )
    if len(set(versions)) != len(versions):
        raise SystemExit("a universe version appears more than once in the log")

    # The genesis entry is never rewritten: it must be byte-identical to the
    # entry the v3 producer derives.
    derived_genesis = _genesis_entry(repo_root)
    if canonical(entries[0]) != canonical(derived_genesis):
        raise SystemExit(
            f"the recorded {GENESIS_VERSION} entry is not the entry the "
            f"{GENESIS_PRODUCER_RELATIVE} derives; the log was rewritten and the chain "
            "cannot be extended"
        )

    previous: Optional[str] = entries[0].get("entry_hash")
    for version in VERSIONS:
        derived = build_entry(repo_root, version, previous)
        recorded = [entry for entry in entries if entry.get("universe_version") == version]
        if recorded:
            if canonical(recorded[0]) != canonical(derived):
                raise SystemExit(
                    f"the recorded {version} entry differs from the entry derived from the "
                    f"{version} artifacts; the log is append-only and is not rewritten"
                )
            entry = recorded[0]
        else:
            entry = derived
            entries.append(entry)
        previous = entry.get("entry_hash")

    # The chain is re-linked from the recorded hashes, in order.
    previous: Optional[str] = None
    for entry in entries:
        if entry.get("previous_entry_hash") != previous:
            raise SystemExit(
                f"the {entry.get('universe_version')} entry does not chain to its predecessor"
            )
        if compute_entry_hash(entry) != entry.get("entry_hash"):
            raise SystemExit(
                f"the {entry.get('universe_version')} entry does not hash to its recorded "
                "digest"
            )
        previous = entry.get("entry_hash")

    document = dict(existing)
    document["entries"] = entries
    document["entry_count"] = len(entries)
    document["producer"] = {
        "deterministic": True,
        "path": "scripts/build_v5_universe_expansion_log.py",
        "verify_command": "python3 scripts/verify_v5_universe_expansion_log.py",
        "entry_producers": {
            GENESIS_VERSION: {
                "path": GENESIS_PRODUCER_RELATIVE,
                "verify_command": "python3 scripts/verify_v3_universe_expansion_log.py",
            },
            **{
                version: {
                    "path": "scripts/build_v5_universe_expansion_log.py",
                    "verify_command": "python3 scripts/verify_v5_universe_expansion_log.py",
                }
                for version in VERSIONS
            },
        },
        "note": (
            "Every entry is derived from the artifacts of its own universe version and is "
            "appended once. The log is append-only: an entry is never rewritten, and a "
            "second entry for a version that is already present is refused."
        ),
    }
    document["pending_entries_note"] = (
        "The v4 and v5 entries were appended by the v5 implementation, which closed "
        "prerequisite p5 of configs/research_v5.json#expansion_program. The "
        "log_state_at_preregistration block of that specification is a historical "
        "statement of the log at preregistration time and is not changed by the append."
    )
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing log")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root, rebuild=args.force)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    log_path = repo_root / LOG_RELATIVE

    if args.print_only:
        print(payload, end="")
        return 0
    if log_path.exists() and not args.force:
        print(
            f"refusing to overwrite {LOG_RELATIVE} without --force",
            file=sys.stderr,
        )
        return 1
    atomic_write_text(log_path, payload)
    head = document["entries"][-1]
    print(json.dumps({
        "path": LOG_RELATIVE,
        "entry_count": document["entry_count"],
        "entry_hash": head["entry_hash"],
        "previous_entry_hash": head["previous_entry_hash"],
        "universe_version": head["universe_version"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

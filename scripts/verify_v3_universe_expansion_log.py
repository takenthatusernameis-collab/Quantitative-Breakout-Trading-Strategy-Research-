#!/usr/bin/env python3
"""Read-only, offline verification of the append-only universe expansion log.

The log (``research/v_universe_expansion_log.json``) is required by
``configs/research_v3.json`` (``expansion_program``). This verifier checks that

* every entry's own hash recomputes from its body;
* every entry's ``previous_entry_hash`` is the hash of its predecessor, so the
  chain is unbroken and append-only;
* every universe version appears exactly once;
* the v3 entry agrees with the current, hash-bound v3 manifests;
* the new floor follows the frozen floor rule and the next pass respects the
  bounded cadence.

The verifier never writes and never contacts a provider.
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

LOG_RELATIVE = "research/v_universe_expansion_log.json"
SPEC_RELATIVE = "configs/research_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"


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


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    body = {key: value for key, value in entry.items() if key != "entry_hash"}
    return sha256_bytes(canonical(body).encode("utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    for relative in (LOG_RELATIVE, SPEC_RELATIVE, UNIVERSE_RELATIVE, DATA_RELATIVE):
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"],
                    "entry_count": 0}

    log = read_json(repo_root / LOG_RELATIVE)
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)

    if log.get("log_mode") != spec["expansion_program"]["log_mode"]:
        failures.append("the log does not record the frozen log mode")
    if log.get("log_path") != spec["expansion_program"]["log_path"]:
        failures.append("the log does not live at the path the specification names")

    entries = log.get("entries") or []
    if not entries:
        failures.append("the log holds no entry")
    if int(log.get("entry_count") or 0) != len(entries):
        failures.append("the recorded entry count does not match the number of entries")

    versions: List[str] = []
    previous_hash: Optional[str] = None
    for index, entry in enumerate(entries):
        version = entry.get("universe_version")
        versions.append(version)
        if compute_entry_hash(entry) != entry.get("entry_hash"):
            failures.append(f"entry {index} ({version}) does not hash to its recorded digest")
        if entry.get("previous_entry_hash") != previous_hash:
            failures.append(
                f"entry {index} ({version}) does not chain to the previous entry"
            )
        previous_hash = entry.get("entry_hash")
    if len(set(versions)) != len(versions):
        failures.append("a universe version appears more than once in the log")

    # the v3 entry must agree with the current manifests
    v3_entries = [entry for entry in entries if entry.get("universe_version") == "v3"]
    if len(v3_entries) != 1:
        failures.append("the log does not hold exactly one v3 entry")
    else:
        entry = v3_entries[0]
        manifest = entry.get("manifest") or {}
        if manifest.get("manifest_hash") != universe.get("manifest_hash"):
            failures.append("the v3 entry names another universe manifest")
        if manifest.get("file_sha256") != sha256_file(repo_root / UNIVERSE_RELATIVE):
            failures.append("the v3 entry records a stale universe manifest digest")
        if (entry.get("data_manifest") or {}).get("manifest_hash") != data.get("manifest_hash"):
            failures.append("the v3 entry names another data manifest")
        members = [member.get("binance_pair")
                   for member in (entry.get("candidate_batch") or {}).get("members") or []]
        manifest_pairs = [
            asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
            for asset in universe.get("eligible_assets") or []
        ]
        if members != manifest_pairs:
            failures.append("the v3 entry's candidate batch is not the manifest's asset list")
        validated = [member.get("binance_pair")
                     for member in (entry.get("validated_candidate_set") or {}).get("members") or []]
        manifest_validated = [
            asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
            for asset in universe.get("eligible_assets") or []
            if asset.get("validated")
        ]
        if validated != manifest_validated:
            failures.append("the v3 entry's validated set is not the manifest's validated set")

        # the floor rule: the next floor is the lowest-ranked candidate of this version
        new_floor = entry.get("new_floor") or {}
        caps = [float(member.get("market_cap_usd") or 0)
                for member in (entry.get("candidate_batch") or {}).get("members") or []]
        if caps and float(new_floor.get("market_cap_usd") or 0) != min(caps):
            failures.append("the recorded new floor is not the lowest candidate's market cap")

        # the bounded cadence: the next pass is at least P7D away
        state = entry.get("program_state") or {}
        try:
            earliest = parse_iso_utc(state["earliest_next_pass_utc"])
            created = parse_iso_utc(entry["created_utc"])
        except (KeyError, ValueError):
            failures.append("the v3 entry does not record a parseable cadence")
        else:
            if earliest < created + timedelta(days=7):
                failures.append("the recorded next pass violates the P7D cadence")

    return {
        "ok": not failures,
        "failures": failures,
        "entry_count": len(entries),
        "universe_versions": versions,
        "head_entry_hash": previous_hash,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

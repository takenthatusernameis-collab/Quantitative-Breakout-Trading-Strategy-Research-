#!/usr/bin/env python3
"""Read-only, offline verification of the append-only universe expansion log.

The log (``research/v_universe_expansion_log.json``) is required by
``configs/research_v3.json`` (``expansion_program``) and named by
``configs/research_v5.json``: every universe version appends exactly one entry,
every entry carries its own hash and the hash of the previous entry, so the
chain is append-only and its history is verifiable. This verifier checks that

* every entry's own hash recomputes from its body;
* every entry's ``previous_entry_hash`` is the hash of its predecessor, so the
  chain is unbroken;
* every universe version appears exactly once, and the chain starts at the v3
  entry, because the v1 and v2 universes predate the log;
* the **v3 entry is byte-identical to the entry the v3 producer derives**, so
  the append did not rewrite the history;
* the **v4 and v5 entries are byte-identical to the entries derived from the
  artifacts of their own versions**, with their ranking depth recomputed from
  the raw market-cap response bytes;
* every entry agrees with the current, hash-bound manifests of its own
  version, follows the frozen floor rule and respects the bounded cadence.

The verifier never writes and never contacts a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

LOG_RELATIVE = "research/v_universe_expansion_log.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"

#: The versions the log must hold, in chain order.
EXPECTED_VERSIONS = ("v3", "v4", "v5")

#: The version the chain starts with: the v1 and v2 universes predate the log.
GENESIS_VERSION = "v3"

#: The versions the v5 implementation appends, with the artifacts each entry
#: is derived from.
DERIVED_VERSIONS = ("v4", "v5")

#: The confirmatory windows a version's expansion may never read: the windows
#: of the prior universe versions.
PRIOR_WINDOWS = {
    "v3": ("v2",),
    "v4": ("v2", "v3"),
    "v5": ("v2", "v3", "v4"),
}

#: The minimum interval between two passes.
CADENCE_INTERVAL = timedelta(days=7)


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
    }


def _check_entry_against_artifacts(repo_root: Path,
                                   entry: Dict[str, Any],
                                   version: str,
                                   failures: List[str]) -> None:
    """One entry must agree with the current artifacts of its own version."""
    paths = _version_paths(version)
    for key in ("spec", "universe", "data"):
        if not (repo_root / paths[key]).exists():
            failures.append(f"missing artifact: {paths[key]}")
            return
    universe = read_json(repo_root / paths["universe"])
    data = read_json(repo_root / paths["data"])

    manifest = entry.get("manifest") or {}
    if manifest.get("path") != paths["universe"]:
        failures.append(f"the {version} entry names another universe manifest")
    if manifest.get("manifest_hash") != universe.get("manifest_hash"):
        failures.append(f"the {version} entry names another universe manifest hash")
    if manifest.get("file_sha256") != sha256_file(repo_root / paths["universe"]):
        failures.append(f"the {version} entry records a stale universe manifest digest")

    data_manifest = entry.get("data_manifest") or {}
    if data_manifest.get("path") != paths["data"]:
        failures.append(f"the {version} entry names another data manifest")
    if data_manifest.get("manifest_hash") != data.get("manifest_hash"):
        failures.append(f"the {version} entry names another data manifest hash")
    if data_manifest.get("file_sha256") != sha256_file(repo_root / paths["data"]):
        failures.append(f"the {version} entry records a stale data manifest digest")

    if entry.get("universe_version") != version:
        failures.append(f"the {version} entry declares another universe version")
    if entry.get("specification_hash") != universe.get("specification_hash"):
        failures.append(f"the {version} entry names another specification hash")

    members = [
        member.get("binance_pair")
        for member in (entry.get("candidate_batch") or {}).get("members") or []
    ]
    manifest_pairs = [
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        for asset in universe.get("eligible_assets") or []
    ]
    if members != manifest_pairs:
        failures.append(f"the {version} entry's candidate batch is not the manifest's asset list")
    if (entry.get("candidate_batch") or {}).get("count") != len(manifest_pairs):
        failures.append(f"the {version} entry's candidate count does not recompute")

    validated = [
        member.get("binance_pair")
        for member in (entry.get("validated_candidate_set") or {}).get("members") or []
    ]
    manifest_validated = [
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        for asset in universe.get("eligible_assets") or []
        if asset.get("validated") is True
    ]
    if validated != manifest_validated:
        failures.append(f"the {version} entry's validated set is not the manifest's validated set")
    if (entry.get("validated_candidate_set") or {}).get("count") != len(manifest_validated):
        failures.append(f"the {version} entry's validated count does not recompute")

    # The prior floor is recomputed from the source manifest.
    prior = entry.get("prior_universe_floor") or {}
    prior_relative = str(prior.get("source_manifest_path") or "")
    prior_path = repo_root / prior_relative
    if not prior_path.exists():
        failures.append(f"the {version} entry names a missing source manifest")
    else:
        prior_universe = read_json(prior_path)
        prior_assets = prior_universe.get("eligible_assets") or []
        if prior_assets:
            floor_asset = min(prior_assets, key=lambda item: float(item.get("market_cap_usd") or 0))
            if prior.get("floor_market_cap_usd") != floor_asset.get("market_cap_usd"):
                failures.append(
                    f"the {version} entry's prior floor is not the minimum market "
                    f"capitalization of {prior_relative}"
                )
            if prior.get("source_manifest_hash") != prior_universe.get("manifest_hash"):
                failures.append(
                    f"the {version} entry's prior floor names another source manifest"
                )

    # The new floor is the lowest-ranked candidate of the version.
    caps = [
        float(member.get("market_cap_usd") or 0)
        for member in (entry.get("candidate_batch") or {}).get("members") or []
    ]
    new_floor = entry.get("new_floor") or {}
    if caps and float(new_floor.get("market_cap_usd") or 0) != min(caps):
        failures.append(f"the recorded {version} floor is not the lowest candidate's market cap")
    if new_floor.get("basis") != "lowest_ranked_candidate_of_this_version":
        failures.append(f"the {version} entry does not state the floor basis")

    # The ranking depth is recomputed from the stored raw response bytes. The
    # frozen v3 entry keeps the depth it recorded; the derived entries carry a
    # depth recomputed from the bytes.
    snapshot = entry.get("snapshot") or {}
    market_cap_source = universe.get("market_cap_source") or {}
    raw_relative = str(
        snapshot.get("raw_response_path")
        or market_cap_source.get("raw_response_path")
        or ""
    )
    raw_path = repo_root / raw_relative if raw_relative else None
    if raw_path is None or not raw_path.exists():
        failures.append(f"the {version} entry names a missing raw market-cap response")
    else:
        rows = json.loads(raw_path.read_text(encoding="utf-8"))
        if version in DERIVED_VERSIONS and snapshot.get("ranking_depth") != len(rows):
            failures.append(
                f"the {version} entry's ranking depth is not the row count of {raw_relative}"
            )
        if snapshot.get("raw_response_hash") != sha256_file(raw_path):
            failures.append(f"the {version} entry records a stale raw response digest")

    # The bounded cadence: the next pass is at least P7D away.
    state = entry.get("program_state") or {}
    try:
        earliest = parse_iso_utc(state["earliest_next_pass_utc"])
        created = parse_iso_utc(entry["created_utc"])
    except (KeyError, ValueError):
        failures.append(f"the {version} entry does not record a parseable cadence")
    else:
        if earliest < created + CADENCE_INTERVAL:
            failures.append(f"the recorded {version} next pass violates the P7D cadence")
    if state.get("minimum_interval_between_passes") != "P7D":
        failures.append(f"the {version} entry does not record the P7D cadence")
    if state.get("state") != "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION":
        failures.append(f"the {version} entry does not record the routing state")

    # The holdout rules: a version's expansion may never read the
    # confirmatory window of a prior version.
    holdout = entry.get("holdout") or {}
    if holdout.get("v1_holdout_reuse") != "forbidden":
        failures.append(f"the {version} entry does not forbid the v1 holdout")
    for window in PRIOR_WINDOWS.get(version, ()):
        if holdout.get(f"{window}_confirmatory_window_reuse") != "forbidden":
            failures.append(
                f"the {version} entry does not forbid the {window} confirmatory window"
            )


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    repo_root = Path(repo_root)

    for relative in (LOG_RELATIVE, SPEC_V3_RELATIVE, SPEC_V5_RELATIVE):
        if not (repo_root / relative).exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {relative}"],
                "entry_count": 0,
            }

    log = read_json(repo_root / LOG_RELATIVE)
    spec_v3 = read_json(repo_root / SPEC_V3_RELATIVE)
    spec_v5 = read_json(repo_root / SPEC_V5_RELATIVE)

    if log.get("log_mode") != spec_v3["expansion_program"]["log_mode"]:
        failures.append("the log does not record the frozen log mode")
    if log.get("log_path") != spec_v3["expansion_program"]["log_path"]:
        failures.append("the log does not live at the path the specification names")
    if log.get("log_path") != spec_v5["expansion_program"]["append_only_log_path"]:
        failures.append("the log does not live at the path the v5 specification names")

    entries = log.get("entries") or []
    if not entries:
        failures.append("the log holds no entry")
    if int(log.get("entry_count") or 0) != len(entries):
        failures.append("the recorded entry count does not match the number of entries")
    if len(entries) != len(EXPECTED_VERSIONS):
        failures.append(
            f"the log holds {len(entries)} entries; the chain holds "
            f"{', '.join(EXPECTED_VERSIONS)}"
        )

    versions: List[str] = []
    previous_hash: Optional[str] = None
    for index, entry in enumerate(entries):
        version = entry.get("universe_version")
        versions.append(version)
        if compute_entry_hash(entry) != entry.get("entry_hash"):
            failures.append(f"entry {index} ({version}) does not hash to its recorded digest")
        if entry.get("previous_entry_hash") != previous_hash:
            failures.append(f"entry {index} ({version}) does not chain to the previous entry")
        previous_hash = entry.get("entry_hash")
    if len(set(versions)) != len(versions):
        failures.append("a universe version appears more than once in the log")
    if versions and versions[0] != GENESIS_VERSION:
        failures.append(
            f"the chain does not start with the {GENESIS_VERSION} entry; it starts with "
            f"{versions[0]!r}"
        )
    if versions != list(EXPECTED_VERSIONS):
        failures.append(
            f"the chain holds {versions}; the expected chain is {list(EXPECTED_VERSIONS)}"
        )

    # The v3 entry must be the entry the v3 producer derives.
    v3_producer = _load_module(
        "build_v3_universe_expansion_log", "scripts/build_v3_universe_expansion_log.py"
    )
    derived_v3 = v3_producer.build_entry(repo_root, None)
    recorded_v3 = [entry for entry in entries if entry.get("universe_version") == GENESIS_VERSION]
    if len(recorded_v3) != 1:
        failures.append(f"the log does not hold exactly one {GENESIS_VERSION} entry")
    elif canonical(recorded_v3[0]) != canonical(derived_v3):
        failures.append(
            f"the recorded {GENESIS_VERSION} entry is not the entry the v3 producer derives; "
            "the history was rewritten"
        )

    # The derived entries must be the entries the v5 producer derives.
    v5_producer = _load_module(
        "build_v5_universe_expansion_log", "scripts/build_v5_universe_expansion_log.py"
    )
    previous: Optional[str] = recorded_v3[0].get("entry_hash") if recorded_v3 else None
    for version in DERIVED_VERSIONS:
        derived = v5_producer.build_entry(repo_root, version, previous)
        recorded = [entry for entry in entries if entry.get("universe_version") == version]
        if len(recorded) != 1:
            failures.append(f"the log does not hold exactly one {version} entry")
            previous = derived.get("entry_hash")
            continue
        if canonical(recorded[0]) != canonical(derived):
            failures.append(
                f"the recorded {version} entry is not the entry derived from the {version} "
                "artifacts"
            )
        previous = recorded[0].get("entry_hash")

    # Every entry agrees with the current artifacts of its own version.
    for entry in entries:
        version = str(entry.get("universe_version") or "")
        if version in ("v3", "v4", "v5"):
            _check_entry_against_artifacts(repo_root, entry, version, failures)

    # The v3 entry keeps its historical ranking depth: it is frozen and is not
    # rewritten, so the depth it recorded is an environment fact.
    if recorded_v3:
        environment_facts.append(
            "the frozen v3 entry records the ranking depth 99, which was not recomputed: the "
            "v3 entry is frozen and is never rewritten, and the derived v4 and v5 entries "
            "carry a depth recomputed from their own raw response bytes"
        )
    environment_facts.append(
        "the log is append-only: the v3 producer refuses to rebuild it now that it holds "
        "later versions, and the v5 producer refuses to rewrite a recorded entry"
    )

    return {
        "ok": not failures,
        "failures": failures,
        "entry_count": len(entries),
        "universe_versions": versions,
        "head_entry_hash": previous_hash,
        "environment_facts": environment_facts,
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

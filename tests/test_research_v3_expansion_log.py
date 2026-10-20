"""Tests for the append-only cross-version universe expansion log.

``research/v_universe_expansion_log.json`` is required by the v3
specification's expansion program: every universe version appends exactly one
entry, every entry carries its own hash and the hash of its predecessor, and
the log is never rewritten. These tests prove that

* the log lives at the path the specification names and records the frozen log
  mode;
* every entry hash recomputes and every entry chains to its predecessor;
* the v3 entry agrees with the current, hash-bound v3 manifests and follows
  the frozen floor rule;
* the bounded cadence is respected, and a second v3 entry is refused.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG = REPO_ROOT / "research" / "v_universe_expansion_log.json"
SPEC = REPO_ROOT / "configs" / "research_v3.json"
UNIVERSE = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA = REPO_ROOT / "research" / "data_manifest_v3.json"

VALIDATED_PAIRS = (
    "AAVEUSDT",
    "ICPUSDT",
    "PEPEUSDT",
    "QNTUSDT",
    "SHIBUSDT",
    "WLDUSDT",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v3_universe_expansion_log", REPO_ROOT / "scripts" / "verify_v3_universe_expansion_log.py"
)
builder = _load_module(
    "build_v3_universe_expansion_log", REPO_ROOT / "scripts" / "build_v3_universe_expansion_log.py"
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_log_lives_at_the_specified_path_in_the_frozen_mode():
    log = _load(LOG)
    spec = _load(SPEC)
    assert spec["expansion_program"]["log_path"] == "research/v_universe_expansion_log.json"
    assert log["log_path"] == spec["expansion_program"]["log_path"]
    assert log["log_mode"] == spec["expansion_program"]["log_mode"] == "append_only_hash_chain"


def test_every_entry_hash_recomputes_and_chains():
    log = _load(LOG)
    entries = log["entries"]
    assert log["entry_count"] == len(entries)
    previous = None
    for entry in entries:
        assert verifier.compute_entry_hash(entry) == entry["entry_hash"]
        assert entry["previous_entry_hash"] == previous
        previous = entry["entry_hash"]


def test_the_v3_entry_agrees_with_the_current_manifests():
    log = _load(LOG)
    universe = _load(UNIVERSE)
    data = _load(DATA)
    entries = [entry for entry in log["entries"] if entry["universe_version"] == "v3"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["manifest"]["manifest_hash"] == universe["manifest_hash"]
    assert entry["data_manifest"]["manifest_hash"] == data["manifest_hash"]
    assert entry["manifest"]["file_sha256"] == builder.sha256_file(UNIVERSE)
    assert entry["candidate_batch"]["count"] == len(universe["eligible_assets"]) == 20
    validated = [member["binance_pair"] for member in entry["validated_candidate_set"]["members"]]
    assert sorted(validated) == sorted(VALIDATED_PAIRS)
    assert entry["excluded_candidates"]["count"] == 14


def test_the_new_floor_follows_the_frozen_floor_rule():
    log = _load(LOG)
    entry = log["entries"][0]
    caps = [float(member["market_cap_usd"]) for member in entry["candidate_batch"]["members"]]
    assert float(entry["new_floor"]["market_cap_usd"]) == min(caps)
    assert entry["new_floor"]["basis"] == "lowest_ranked_candidate_of_this_version"


def test_the_bounded_cadence_is_respected():
    log = _load(LOG)
    entry = log["entries"][0]
    state = entry["program_state"]
    assert state["minimum_interval_between_passes"] == "P7D"
    assert state["polling_forbidden"]
    earliest = verifier.parse_iso_utc(state["earliest_next_pass_utc"])
    created = verifier.parse_iso_utc(entry["created_utc"])
    assert (earliest - created).days >= 7
    assert state["state"] == "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION"


def test_the_log_is_append_only():
    with pytest.raises(SystemExit):
        builder.build(REPO_ROOT)


def test_the_log_rebuild_is_byte_identical():
    rebuilt = builder.build(REPO_ROOT, rebuild=True)
    assert json.dumps(rebuilt, sort_keys=True) == json.dumps(_load(LOG), sort_keys=True)

"""Tests for the v6 entry of the append-only cross-version universe expansion log.

``research/v_universe_expansion_log.json`` is required by the v3
specification's expansion program and named by the v6 specification: every
universe version appends exactly one entry, every entry carries its own hash
and the hash of its predecessor, and the log is never rewritten. The v6
implementation closed prerequisite ``p5``: it appended the **derived v6 entry**
to the chain that held the v3, v4 and v5 entries.

These tests prove that

* the log lives at the path the specifications name and records the frozen log
  mode;
* the chain **begins with** the v3, v4, v5 and v6 entries, every entry hash
  recomputes and every entry chains to its predecessor;
* the **v6 entry is byte-identical to the entry the v6 producer derives** from
  the v6 artifacts, chained onto the v5 entry's hash, and its ranking depth is
  recomputed from the raw market-cap response bytes;
* the v6 entry agrees with the current, hash-bound v6 manifests and follows
  the frozen floor rule;
* the log is append-only: the v6 producer refuses to rewrite a recorded entry,
  and the verifier accepts the entry a later universe version appends while
  still refusing a missing, moved or rewritten scope entry.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG = REPO_ROOT / "research" / "v_universe_expansion_log.json"
SPEC_V3 = REPO_ROOT / "configs" / "research_v3.json"
SPEC_V5 = REPO_ROOT / "configs" / "research_v5.json"
SPEC_V6 = REPO_ROOT / "configs" / "research_v6.json"
UNIVERSE_V6 = REPO_ROOT / "research" / "universe_manifest_v6.json"
DATA_V6 = REPO_ROOT / "research" / "data_manifest_v6.json"
UNIVERSE_V5 = REPO_ROOT / "research" / "universe_manifest_v5.json"

#: The versions this verifier owns, in chain order.
EXPECTED_VERSIONS = ("v3", "v4", "v5", "v6")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v6_universe_expansion_log", REPO_ROOT / "scripts" / "verify_v6_universe_expansion_log.py"
)
builder = _load_module(
    "build_v6_universe_expansion_log", REPO_ROOT / "scripts" / "build_v6_universe_expansion_log.py"
)


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads."""
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {
        Path("research/results_shards"),
        Path("research/campaign_cycles"),
        Path("research/shards_v2"),
        Path("research/shards_v3"),
        Path("research/shards_v4"),
        Path("research/shards_v5"),
        Path("research/shards_v6"),
        Path("research/data"),
    }
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in skip_relative:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            target.symlink_to(source)
    return root


def _write_log(root: Path, log: Dict[str, Any]) -> None:
    """Write the log of a mirror, replacing the symlink instead of following it."""
    path = root / "research" / "v_universe_expansion_log.json"
    if path.is_symlink() or path.exists():
        path.unlink()
    path.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _entry(version: str) -> Dict[str, Any]:
    log = _load(LOG)
    entries = [item for item in log["entries"] if item["universe_version"] == version]
    assert len(entries) == 1
    return entries[0]


def _synthetic_entry(version: str, previous_entry_hash: str) -> Dict[str, Any]:
    """A minimal later entry that carries a correct hash and chain link."""
    entry: Dict[str, Any] = {
        "universe_version": version,
        "created_utc": "2026-11-01T00:00:00Z",
        "previous_entry_hash": previous_entry_hash,
    }
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    entry["entry_hash"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return entry


def _append_synthetic_entry(log: Dict[str, Any], version: str) -> Dict[str, Any]:
    entry = _synthetic_entry(version, log["entries"][-1]["entry_hash"])
    log["entries"].append(entry)
    log["entry_count"] = len(log["entries"])
    return entry


def test_verifier_reports_no_failures() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True
    log = _load(LOG)
    assert report["entry_count"] == len(log["entries"])
    assert report["universe_versions"] == [
        entry["universe_version"] for entry in log["entries"]
    ]


def test_the_log_lives_at_the_specified_path_in_the_frozen_mode() -> None:
    log = _load(LOG)
    spec_v3 = _load(SPEC_V3)
    spec_v5 = _load(SPEC_V5)
    spec_v6 = _load(SPEC_V6)
    assert log["log_path"] == spec_v3["expansion_program"]["log_path"]
    assert log["log_path"] == spec_v5["expansion_program"]["append_only_log_path"]
    assert log["log_path"] == spec_v6["expansion_program"]["append_only_log_path"]
    assert log["log_mode"] == spec_v3["expansion_program"]["log_mode"]


def test_the_chain_begins_with_the_v3_v4_v5_and_v6_entries() -> None:
    log = _load(LOG)
    versions = [entry["universe_version"] for entry in log["entries"]]
    assert versions[: len(EXPECTED_VERSIONS)] == list(EXPECTED_VERSIONS)
    assert log["entry_count"] == len(log["entries"])


def test_every_entry_hash_recomputes_and_chains() -> None:
    log = _load(LOG)
    previous = None
    for entry in log["entries"]:
        body = {key: value for key, value in entry.items() if key != "entry_hash"}
        assert entry["entry_hash"] == hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        assert entry["previous_entry_hash"] == previous
        previous = entry["entry_hash"]


def test_the_v6_entry_is_the_entry_the_producer_derives() -> None:
    derived = builder.build_entry(REPO_ROOT, "v6", _entry("v5")["entry_hash"])
    assert _entry("v6") == derived


def test_the_v6_entry_chains_to_the_hash_the_specification_records() -> None:
    spec_v6 = _load(SPEC_V6)
    recorded = spec_v6["expansion_program"]["log_entry_previous_hash"]
    assert _entry("v6")["previous_entry_hash"] == recorded


def test_the_ranking_depth_is_recomputed_from_the_raw_response_bytes() -> None:
    entry = _entry("v6")
    raw = REPO_ROOT / entry["snapshot"]["raw_response_path"]
    rows = json.loads(raw.read_text(encoding="utf-8"))
    assert entry["snapshot"]["ranking_depth"] == len(rows)
    assert entry["snapshot"]["raw_response_hash"] == hashlib.sha256(raw.read_bytes()).hexdigest()


def test_the_v6_entry_agrees_with_the_v6_manifests() -> None:
    entry = _entry("v6")
    universe = _load(UNIVERSE_V6)
    data = _load(DATA_V6)
    assert entry["manifest"]["manifest_hash"] == universe["manifest_hash"]
    assert entry["data_manifest"]["manifest_hash"] == data["manifest_hash"]
    assert entry["candidate_batch"]["count"] == len(universe["eligible_assets"])
    validated = [
        member["binance_pair"] for member in entry["validated_candidate_set"]["members"]
    ]
    manifest_validated = [
        asset["binance_pair"]
        for asset in universe["eligible_assets"]
        if asset.get("validated") is True
    ]
    assert validated == manifest_validated
    assert entry["validated_candidate_set"]["count"] == len(manifest_validated)


def test_the_prior_floor_of_the_v6_entry_is_the_floor_of_the_v5_manifest() -> None:
    entry = _entry("v6")
    universe_v5 = _load(UNIVERSE_V5)
    floor_asset = min(
        universe_v5["eligible_assets"], key=lambda item: float(item["market_cap_usd"])
    )
    prior = entry["prior_universe_floor"]
    assert prior["source_manifest_path"] == "research/universe_manifest_v5.json"
    assert prior["floor_market_cap_usd"] == floor_asset["market_cap_usd"]
    assert prior["floor_symbol"] == floor_asset.get("binance_pair") or floor_asset.get("symbol")


def test_the_new_floor_is_the_lowest_candidate_of_the_v6_manifest() -> None:
    entry = _entry("v6")
    universe = _load(UNIVERSE_V6)
    caps = [float(asset["market_cap_usd"]) for asset in universe["eligible_assets"]]
    assert float(entry["new_floor"]["market_cap_usd"]) == min(caps)
    assert entry["new_floor"]["basis"] == "lowest_ranked_candidate_of_this_version"


def test_the_bounded_cadence_is_respected() -> None:
    entry = _entry("v6")
    state = entry["program_state"]
    assert state["minimum_interval_between_passes"] == "P7D"
    assert state["polling_forbidden"]
    earliest = verifier.parse_iso_utc(state["earliest_next_pass_utc"])
    created = verifier.parse_iso_utc(entry["created_utc"])
    assert (earliest - created).days >= 7
    assert state["state"] == "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION"


def test_the_v6_entry_forbids_every_prior_confirmatory_window() -> None:
    holdout = _entry("v6")["holdout"]
    assert holdout["v1_holdout_reuse"] == "forbidden"
    for window in ("v2", "v3", "v4", "v5"):
        assert holdout[f"{window}_confirmatory_window_reuse"] == "forbidden"


def test_the_producer_is_deterministic() -> None:
    rebuilt = builder.build(REPO_ROOT)
    on_disk = _load(LOG)
    assert rebuilt["entries"] == on_disk["entries"]
    assert rebuilt["entry_count"] == on_disk["entry_count"]


def test_the_v6_producer_refuses_to_rewrite_a_recorded_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    log = json.loads(
        (root / "research" / "v_universe_expansion_log.json").read_text(encoding="utf-8")
    )
    for entry in log["entries"]:
        if entry["universe_version"] == "v6":
            entry["snapshot"]["ranking_depth"] = 99
    _write_log(root, log)
    with pytest.raises(SystemExit):
        builder.build(root)


def test_the_verifier_accepts_the_entry_a_later_version_appends(tmp_path: Path) -> None:
    """The log is append-only: a later universe version appends, it does not replace."""
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    _append_synthetic_entry(log, "v7")
    _write_log(root, log)
    report = verifier.verify(root)
    assert report["failures"] == []
    assert report["ok"] is True
    assert report["universe_versions"][-1] == "v7"


def test_the_verifier_detects_a_missing_scope_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"] = [
        entry for entry in log["entries"] if entry["universe_version"] != "v6"
    ]
    log["entry_count"] = len(log["entries"])
    _write_log(root, log)
    failures = _failures(root)
    assert any("the chain begins with" in failure for failure in failures), failures


def test_the_verifier_detects_a_rewritten_v6_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    for entry in log["entries"]:
        if entry["universe_version"] == "v6":
            entry["snapshot"]["ranking_depth"] = 99
    _write_log(root, log)
    failures = _failures(root)
    assert any(
        "is not the entry derived from the v6 artifacts" in failure for failure in failures
    ), failures


def test_the_verifier_detects_a_broken_chain(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][-1]["previous_entry_hash"] = "0" * 64
    _write_log(root, log)
    failures = _failures(root)
    assert any("chain" in failure for failure in failures), failures


def test_the_verifier_detects_a_chain_that_is_not_in_version_order(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    _append_synthetic_entry(log, "v9")
    _append_synthetic_entry(log, "v7")
    _write_log(root, log)
    failures = _failures(root)
    assert any("not in universe-version order" in failure for failure in failures), failures


def test_the_verifier_detects_a_duplicated_version(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    _append_synthetic_entry(log, "v6")
    _write_log(root, log)
    failures = _failures(root)
    assert any("appears more than once" in failure for failure in failures), failures


def test_the_verifier_reports_a_malformed_scope_entry_instead_of_raising(
    tmp_path: Path,
) -> None:
    """A malformed entry is a failure to report, never an exception to raise."""
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    for entry in log["entries"]:
        if entry["universe_version"] == "v6":
            entry["prior_universe_floor"].pop("source_manifest_path", None)
    _write_log(root, log)
    failures = _failures(root)
    assert failures, failures

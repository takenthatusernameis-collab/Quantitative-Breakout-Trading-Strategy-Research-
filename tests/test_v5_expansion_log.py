"""Tests for the extended append-only cross-version universe expansion log.

``research/v_universe_expansion_log.json`` is required by the v3
specification's expansion program and named by the v5 specification: every
universe version appends exactly one entry, every entry carries its own hash
and the hash of its predecessor, and the log is never rewritten. The v5
implementation closed prerequisite ``p5``: it appended the **derived v4 entry**
and the **v5 entry** to the chain that held only the v3 entry.

These tests prove that

* the log lives at the path the specifications name and records the frozen log
  mode;
* the chain holds exactly the v3, v4 and v5 entries, every entry hash
  recomputes and every entry chains to its predecessor;
* the **v3 entry is byte-identical to the entry the v3 producer derives**, so
  the append did not rewrite the history;
* the **v4 and v5 entries are byte-identical to the entries derived from the
  artifacts of their own versions**, and their ranking depth is recomputed
  from the raw market-cap response bytes;
* every entry agrees with the current manifests of its own version, follows the
  frozen floor rule and respects the bounded cadence;
* the log is append-only: the v3 producer refuses to rebuild it, the v5
  producer refuses to rewrite a recorded entry, and the verifier is not
  vacuous.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG = REPO_ROOT / "research" / "v_universe_expansion_log.json"
SPEC_V3 = REPO_ROOT / "configs" / "research_v3.json"
SPEC_V5 = REPO_ROOT / "configs" / "research_v5.json"

EXPECTED_VERSIONS = ("v3", "v4", "v5")

V4_VALIDATED = (
    "ALGOUSDT",
    "ARBUSDT",
    "ETCUSDT",
    "FILUSDT",
    "INJUSDT",
    "JSTUSDT",
    "NEXOUSDT",
)

V5_VALIDATED = (
    "APTUSDT",
    "CAKEUSDT",
    "CRVUSDT",
    "DASHUSDT",
    "RAYUSDT",
    "STXUSDT",
    "VETUSDT",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v5_universe_expansion_log", REPO_ROOT / "scripts" / "verify_v5_universe_expansion_log.py"
)
builder = _load_module(
    "build_v5_universe_expansion_log", REPO_ROOT / "scripts" / "build_v5_universe_expansion_log.py"
)
v3_builder = _load_module(
    "build_v3_universe_expansion_log", REPO_ROOT / "scripts" / "build_v3_universe_expansion_log.py"
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
        Path("research/data"),
    }
    for current, dirs, files in __import__("os").walk(REPO_ROOT):
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


def test_verifier_reports_no_failures() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True
    assert report["entry_count"] == 3


def test_the_log_lives_at_the_specified_path_in_the_frozen_mode() -> None:
    log = _load(LOG)
    spec_v3 = _load(SPEC_V3)
    spec_v5 = _load(SPEC_V5)
    assert log["log_path"] == spec_v3["expansion_program"]["log_path"]
    assert log["log_path"] == spec_v5["expansion_program"]["append_only_log_path"]
    assert log["log_mode"] == "append_only_hash_chain"


def test_the_chain_holds_the_v3_v4_and_v5_entries() -> None:
    log = _load(LOG)
    versions = [entry["universe_version"] for entry in log["entries"]]
    assert versions == list(EXPECTED_VERSIONS)
    assert log["entry_count"] == len(log["entries"]) == 3


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


def test_the_v3_entry_is_not_rewritten() -> None:
    derived = v3_builder.build_entry(REPO_ROOT, None)
    assert _entry("v3") == derived


def test_the_derived_entries_are_the_entries_the_producer_derives() -> None:
    previous = _entry("v3")["entry_hash"]
    for version in ("v4", "v5"):
        derived = builder.build_entry(REPO_ROOT, version, previous)
        assert _entry(version) == derived
        previous = derived["entry_hash"]


def test_the_ranking_depth_is_recomputed_from_the_raw_response_bytes() -> None:
    for version in ("v4", "v5"):
        entry = _entry(version)
        raw = REPO_ROOT / entry["snapshot"]["raw_response_path"]
        rows = json.loads(raw.read_text(encoding="utf-8"))
        assert entry["snapshot"]["ranking_depth"] == len(rows) == 250
        assert entry["snapshot"]["raw_response_hash"] == hashlib.sha256(
            raw.read_bytes()
        ).hexdigest()


def test_the_v4_entry_agrees_with_the_v4_manifests() -> None:
    entry = _entry("v4")
    universe = _load(REPO_ROOT / "research" / "universe_manifest_v4.json")
    data = _load(REPO_ROOT / "research" / "data_manifest_v4.json")
    assert entry["manifest"]["manifest_hash"] == universe["manifest_hash"]
    assert entry["data_manifest"]["manifest_hash"] == data["manifest_hash"]
    assert entry["candidate_batch"]["count"] == len(universe["eligible_assets"]) == 20
    validated = [
        member["binance_pair"] for member in entry["validated_candidate_set"]["members"]
    ]
    assert sorted(validated) == sorted(V4_VALIDATED)
    assert entry["excluded_candidates"]["count"] == 13


def test_the_v5_entry_agrees_with_the_v5_manifests() -> None:
    entry = _entry("v5")
    universe = _load(REPO_ROOT / "research" / "universe_manifest_v5.json")
    data = _load(REPO_ROOT / "research" / "data_manifest_v5.json")
    assert entry["manifest"]["manifest_hash"] == universe["manifest_hash"]
    assert entry["data_manifest"]["manifest_hash"] == data["manifest_hash"]
    assert entry["candidate_batch"]["count"] == len(universe["eligible_assets"]) == 20
    validated = [
        member["binance_pair"] for member in entry["validated_candidate_set"]["members"]
    ]
    assert sorted(validated) == sorted(V5_VALIDATED)
    assert entry["excluded_candidates"]["count"] == 13


def test_the_floors_follow_the_frozen_floor_rule() -> None:
    for version in ("v4", "v5"):
        entry = _entry(version)
        caps = [
            float(member["market_cap_usd"]) for member in entry["candidate_batch"]["members"]
        ]
        assert float(entry["new_floor"]["market_cap_usd"]) == min(caps)
        assert entry["new_floor"]["basis"] == "lowest_ranked_candidate_of_this_version"
        assert entry["new_floor"]["rule"]


def test_the_prior_floor_of_each_entry_is_the_floor_of_the_previous_version() -> None:
    assert _entry("v4")["prior_universe_floor"]["floor_symbol"] == "HTXUSDT"
    assert _entry("v4")["prior_universe_floor"]["floor_market_cap_usd"] == 1468004153
    assert _entry("v5")["prior_universe_floor"]["floor_symbol"] == "AKEUSDT"
    assert _entry("v5")["prior_universe_floor"]["floor_market_cap_usd"] == 739186726


def test_the_new_floor_of_the_v5_entry_is_below_the_v4_floor() -> None:
    entry = _entry("v5")
    assert entry["new_floor"]["symbol"] == "YLDSUSDT"
    assert float(entry["new_floor"]["market_cap_usd"]) == 498236520
    assert float(entry["new_floor"]["market_cap_usd"]) < float(
        entry["prior_universe_floor"]["floor_market_cap_usd"]
    )


def test_the_bounded_cadence_is_respected() -> None:
    for version in ("v3", "v4", "v5"):
        entry = _entry(version)
        state = entry["program_state"]
        assert state["minimum_interval_between_passes"] == "P7D"
        assert state["polling_forbidden"]
        earliest = verifier.parse_iso_utc(state["earliest_next_pass_utc"])
        created = verifier.parse_iso_utc(entry["created_utc"])
        assert (earliest - created).days >= 7
        assert state["state"] == "VERSION_COMPLETE_ROUTED_TO_NEXT_VERSION"


def test_no_entry_reads_a_prior_confirmatory_window() -> None:
    for version, windows in (
        ("v3", ("v2",)),
        ("v4", ("v2", "v3")),
        ("v5", ("v2", "v3", "v4")),
    ):
        holdout = _entry(version)["holdout"]
        assert holdout["v1_holdout_reuse"] == "forbidden"
        for window in windows:
            assert holdout[f"{window}_confirmatory_window_reuse"] == "forbidden"


def test_the_v3_producer_refuses_to_rebuild_the_log() -> None:
    with pytest.raises(SystemExit):
        v3_builder.build(REPO_ROOT, rebuild=True)


def test_the_v5_producer_refuses_to_rewrite_a_recorded_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    log = json.loads((root / "research" / "v_universe_expansion_log.json").read_text(
        encoding="utf-8"
    ))
    for entry in log["entries"]:
        if entry["universe_version"] == "v5":
            entry["snapshot"]["ranking_depth"] = 99
    _write_log(root, log)
    with pytest.raises(SystemExit):
        builder.build(root)


def test_the_producer_is_deterministic() -> None:
    rebuilt = builder.build(REPO_ROOT)
    on_disk = _load(LOG)
    assert rebuilt["entries"] == on_disk["entries"]
    assert rebuilt["entry_count"] == on_disk["entry_count"]


def test_verifier_detects_a_broken_chain(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][1]["previous_entry_hash"] = "0" * 64
    _write_log(root, log)
    failures = _failures(root)
    assert any("chain" in failure for failure in failures), failures


def test_verifier_detects_a_rewritten_v3_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][0]["snapshot"]["ranking_depth"] = 250
    _write_log(root, log)
    failures = _failures(root)
    assert any("history was rewritten" in failure for failure in failures), failures


def test_verifier_detects_a_tampered_entry_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][2]["entry_hash"] = "0" * 64
    _write_log(root, log)
    failures = _failures(root)
    assert any("does not hash to its recorded digest" in failure for failure in failures), failures


def test_verifier_detects_a_stale_ranking_depth(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    for entry in log["entries"]:
        if entry["universe_version"] == "v4":
            entry["snapshot"]["ranking_depth"] = 99
    _write_log(root, log)
    failures = _failures(root)
    assert any("ranking depth" in failure for failure in failures), failures


def test_verifier_detects_a_missing_entry(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"] = [entry for entry in log["entries"] if entry["universe_version"] != "v4"]
    log["entry_count"] = len(log["entries"])
    _write_log(root, log)
    failures = _failures(root)
    assert failures, failures

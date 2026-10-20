"""Tests for the v2 manifests (BRAIN-008 prerequisites P2 and P3).

The v2 universe manifest and the v2 data manifest are the artifacts the
preregistered specification names. These tests prove that

* both manifests carry the snapshot-identity tuple and it agrees with the
  specification, with the stored raw provider response and with each other;
* the market-cap snapshot is the one retrieved inside the pinned window, and
  its stored bytes hash to the recorded digest;
* every candidate is either validated against real provider data or excluded
  with a reason, and no candidate is silently dropped;
* every validated candidate has a hash-verified, gap-free dataset of at least
  26,280 closed hourly candles, and no excluded candidate has one;
* the v1 artifacts that the manifests supersede are still byte-identical, and
  the v1 exclusion rules are copied unchanged;
* no v2 candidate manifest and no confirmatory-window exposure exist yet, so
  no v2 execution has happened.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V2 = REPO_ROOT / "configs" / "research_v2.json"
UNIVERSE_V2 = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2 = REPO_ROOT / "research" / "data_manifest_v2.json"
SNAPSHOT_RAW = REPO_ROOT / "research" / "v2_evidence" / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION = REPO_ROOT / "research" / "v2_evidence" / "snapshot_observation.json"
CODE_HASH_AMENDMENT = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"
AUTHORIZATION = REPO_ROOT / "research_state" / "campaign_authorization.json"

HASHED_SET_ROOT = "src/breakout_research"

V1_ARTIFACT_SHA256 = {
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
}


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_research_v2_manifests", REPO_ROOT / "scripts" / "verify_research_v2_manifests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of symlinks to the parts of the repository the verifier reads.

    The hashed source tree is copied for real, so a test may modify it without
    ever writing to the working tree. The large result directories are skipped:
    the verifier never reads them.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {Path("research/results_shards"), Path("research/campaign_cycles")}
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
            if relative == Path(HASHED_SET_ROOT) or Path(HASHED_SET_ROOT) in relative.parents:
                # The hashed set is copied for real, recursively: a symlink would
                # let a test write through it into the working tree.
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    return root


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_both_manifests_hash_bound():
    universe = _load(UNIVERSE_V2)
    data = _load(DATA_V2)
    assert universe["manifest_hash"] == verifier.compute_manifest_hash(
        universe, ("manifest_hash",)
    )
    assert data["manifest_hash"] == verifier.compute_manifest_hash(
        data, ("manifest_hash", "snapshot_identity.data_manifest_hash")
    )


def test_snapshot_identity_is_complete_and_consistent():
    spec = _load(SPEC_V2)
    universe = _load(UNIVERSE_V2)
    data = _load(DATA_V2)
    authorization = _load(AUTHORIZATION)
    identity = universe["snapshot_identity"]
    assert set(identity) == set(verifier.SNAPSHOT_IDENTITY_FIELDS)
    assert identity["protocol_version"] == spec["protocol_version"] == "v2"
    assert identity["universe_version"] == spec["universe_version"] == "v2"
    assert identity["specification_hash"] == spec["specification_hash"]
    assert identity["market_cap_source_endpoint"] == spec["universe"]["endpoint"]
    assert identity["code_hash"] == authorization["code_hash"]
    assert identity["data_manifest_hash"] == data["manifest_hash"]
    assert data["snapshot_identity"] == identity


def test_the_hashed_source_set_is_identified_by_the_canonical_digest():
    """BRAIN-009: the tree identity is the portable canonical digest.

    The ordered digest that ``compute_code_hash()`` returns depends on the
    directory enumeration order of the checkout, so it is cross-checked against
    the authorized value of record and never used as a drift signal.
    """
    amendment = _load(CODE_HASH_AMENDMENT)
    authorization = _load(AUTHORIZATION)
    recorded = amendment["code_hash_constraint"]["canonical_source_digest"]
    assert verifier.canonical_source_digest(REPO_ROOT) == recorded
    assert authorization["code_hash"] == amendment["code_hash_constraint"]["authorized_code_hash"]
    report = verifier.verify(REPO_ROOT)
    assert report["canonical_source_digest"] == recorded
    assert report["ordered_code_hash_matches_authorized"] is (
        report["live_ordered_code_hash"] == authorization["code_hash"]
    )
    assert report["failures"] == []


def test_snapshot_is_the_in_window_retrieval_and_hashes_to_the_recorded_digest():
    spec = _load(SPEC_V2)
    universe = _load(UNIVERSE_V2)
    observation = _load(SNAPSHOT_OBSERVATION)
    retrieval = spec["universe"]["snapshot_retrieval"]
    recorded = universe["market_cap_source"]
    assert recorded["retrieval_timestamp_utc"] == observation["retrieval_timestamp_utc"]
    assert verifier.sha256_file(SNAPSHOT_RAW) == recorded["raw_response_hash"]
    assert recorded["raw_response_hash"] == observation["raw_response_hash"]
    retrieved_at = verifier.parse_iso_utc(observation["retrieval_timestamp_utc"])
    assert verifier.parse_iso_utc(retrieval["not_before_utc"]) <= retrieved_at
    assert retrieved_at <= verifier.parse_iso_utc(retrieval["deadline_utc"])


def test_every_candidate_is_validated_or_excluded_with_a_reason():
    spec = _load(SPEC_V2)
    universe = _load(UNIVERSE_V2)
    eligible = universe["eligible_assets"]
    assert len(eligible) == spec["universe"]["top_n"] == 20
    for entry in eligible:
        if entry["validated"]:
            assert entry["exclusion_reason"] is None
            assert entry["binance_spot_verified"] is True
            assert entry["candle_history_verified"] is True
            assert entry["observed_candles"] >= spec["universe"]["min_candles"]
        else:
            assert entry["exclusion_reason"]
            assert entry["validated"] is False


def test_new_constituents_are_resolved_by_evidence():
    """ZEC and HBAR now pass section 3; HYPE does not and must stay excluded."""
    universe = _load(UNIVERSE_V2)
    by_symbol = {entry["symbol"]: entry for entry in universe["eligible_assets"]}
    assert by_symbol["ZECUSDT"]["validated"] is True
    assert by_symbol["HBARUSDT"]["validated"] is True
    assert by_symbol["HYPEUSDT"]["validated"] is False
    assert by_symbol["HYPEUSDT"]["exclusion_reason"] == "insufficient_hourly_history"
    assert by_symbol["HYPEUSDT"]["observed_candles"] < 26280
    assert by_symbol["XMRUSDT"]["exclusion_reason"] == "binance_spot_unavailable"


def test_validated_assets_have_hash_verified_datasets():
    data = _load(DATA_V2)
    universe = _load(UNIVERSE_V2)
    validated = [entry["symbol"] for entry in universe["eligible_assets"] if entry["validated"]]
    assert validated
    for symbol in validated:
        entry = data["assets"][symbol]
        path = REPO_ROOT / entry["dataset_path"]
        assert path.exists(), symbol
        digest, rows, first_ts, last_ts = verifier.dataset_content_hash(path)
        assert digest == entry["content_hash"], symbol
        assert digest == data["content_hashes"][symbol], symbol
        assert rows == entry["observed_candle_count"] >= 26280, symbol
        assert first_ts == entry["first_candle_timestamp"], symbol
        assert last_ts == entry["last_candle_timestamp"], symbol
        assert entry["gaps"] == [], symbol
        assert entry["rejected_rows"] == 0, symbol
        assert entry["provider"] == "binance", symbol


def test_excluded_assets_have_no_dataset():
    data = _load(DATA_V2)
    universe = _load(UNIVERSE_V2)
    excluded = [entry["symbol"] for entry in universe["eligible_assets"] if not entry["validated"]]
    for symbol in excluded:
        entry = data["assets"].get(symbol)
        if entry is not None:
            assert not entry["dataset_path"], symbol
            assert not entry["content_hash"], symbol
            assert entry["provider"] is None, symbol
        assert data["exclusion_reasons"][symbol], symbol


def test_exclusion_rules_are_copied_unchanged_from_v1():
    v1 = _load(REPO_ROOT / "research" / "universe_manifest.json")
    universe = _load(UNIVERSE_V2)
    assert universe["exclusion_rules"] == v1["exclusion_rules"]
    for entry in universe["excluded_candidates"]:
        assert entry["exclusion_reason"]


def test_v1_artifacts_are_unchanged_and_superseded_by_hash():
    for rel, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / rel
        if not path.exists():
            pytest.skip(f"{rel} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, rel
    universe = _load(UNIVERSE_V2)
    supersedes = universe["supersedes"]
    assert supersedes["protocol_version"] == "v1"
    assert supersedes["universe_manifest_sha256"] == V1_ARTIFACT_SHA256["research/universe_manifest.json"]
    assert supersedes["candidate_manifest_sha256"] == V1_ARTIFACT_SHA256["research/candidate_manifest.json"]


def test_v2_datasets_live_in_their_own_directory():
    data = _load(DATA_V2)
    for symbol, entry in data["assets"].items():
        if not entry["dataset_path"]:
            continue
        assert entry["dataset_path"].startswith("research/data/candles_v2/"), symbol


def test_no_candidate_manifest_and_no_holdout_exposure_yet():
    universe = _load(UNIVERSE_V2)
    data = _load(DATA_V2)
    assert universe["snapshot_identity"]["candidate_manifest_hash"] is None
    assert universe["candidate_manifest"]["status"] == "NOT_CREATED"
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    assert data["confirmatory_window"]["v1_holdout_reuse"] == "forbidden"


def test_no_v2_results_are_present():
    data = _load(DATA_V2)
    universe = _load(UNIVERSE_V2)
    forbidden = {"results", "result_rows", "results_manifest", "shards", "ledger"}
    for document in (data, universe):
        assert forbidden.isdisjoint(set(document)), sorted(forbidden.intersection(set(document)))
    results_manifest = REPO_ROOT / "research" / "results_manifest.json"
    if results_manifest.exists():
        manifest = json.loads(results_manifest.read_text(encoding="utf-8"))
        assert manifest.get("protocol_version") != "v2"
    shards_root = REPO_ROOT / "research" / "results_shards"
    if shards_root.exists():
        campaigns = [path.name for path in shards_root.iterdir() if path.is_dir()]
        assert campaigns, "the v1 result shards must still be present"
        assert not any("v2" in name.lower() for name in campaigns), campaigns


def test_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    """The canonical tree-identity check is not vacuous: drift is detected."""
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "config.py"
    original = target.read_text(encoding="utf-8")
    target.unlink()
    target.write_text(original + "\n# tampered\n", encoding="utf-8")
    report = verifier.verify(root)
    assert any(
        "does not match the recorded canonical digest" in failure
        for failure in report["failures"]
    )

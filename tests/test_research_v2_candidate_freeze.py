"""Tests for the preregistered v2 candidate freeze.

``configs/research_v2_candidate_freeze.json`` freezes the v2 candidate set and
the development / confirmatory data boundary before any v2 result exists. The
tests prove that

* the manifest hash recomputes from the document itself and the
  snapshot-identity tuple names that same hash;
* the frozen candidate set is exactly the validated constituents of universe
  version v2, matches the evaluation scope of the v2 execution protocol and
  keeps the excluded assets out;
* the confirmatory window opens after the freeze, needs 2,160 closed hourly
  candles, is single-use and is never read during selection;
* the selected-configuration manifest is still outstanding and the freeze
  authorizes no execution at all;
* the v1 candidate manifest it supersedes is byte-identical, and the v1
  campaign's ``manifest_version 2`` artifact is not mistaken for a v2-universe
  candidate manifest;
* the verifier is not vacuous: tampering with the freeze, the universe
  manifest, the data manifest or the result store is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from breakout_research.config import compute_code_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
PROTOCOL_V2_PATH = REPO_ROOT / "configs" / "research_v2_execution.json"
V1_CANDIDATE_PATH = REPO_ROOT / "research" / "candidate_manifest.json"
V1_CANDIDATE_V2_PATH = REPO_ROOT / "research" / "candidate_manifest_v2.json"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v2_candidate_freeze", "scripts/verify_research_v2_candidate_freeze.py")
producer = _load_module("build_v2_candidate_freeze", "scripts/build_v2_candidate_freeze.py")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of symlinks to the parts of the repository the verifier reads.

    Directories are recreated and files are symlinked, so a test may add,
    replace or remove files in the mirror without ever writing to the real
    working tree. The v1 shard and cycle directories are not mirrored: the
    verifier never reads them and they hold tens of thousands of files.
    """
    root = tmp_path / "repo"
    skip = {".git", ".pytest_cache", "__pycache__"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative == Path("research"):
            dirs[:] = ["v2_evidence"]
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            (root / relative / name).symlink_to(Path(current) / name)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper_freeze(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    freeze = _load(FREEZE_PATH)
    mutate(freeze)
    _replace(root, "configs/research_v2_candidate_freeze.json", freeze)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_manifest_hash_recomputes_from_the_document():
    freeze = _load(FREEZE_PATH)
    excluded = tuple(freeze["hashing"]["manifest_hash_excluded_keys"])
    assert freeze["manifest_hash"] == verifier.compute_manifest_hash(freeze, excluded)


def test_snapshot_identity_names_this_candidate_manifest():
    freeze = _load(FREEZE_PATH)
    identity = freeze["snapshot_identity"]
    assert identity["candidate_manifest_hash"] == freeze["manifest_hash"]
    for field in verifier.SNAPSHOT_IDENTITY_FIELDS:
        assert field in identity, field


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_freeze_is_reproducible_from_the_producer():
    built = producer.build(REPO_ROOT)
    assert json.loads(FREEZE_PATH.read_text(encoding="utf-8")) == built


def test_frozen_set_is_exactly_the_validated_constituents():
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    validated = sorted(
        entry["symbol"] for entry in universe["eligible_assets"] if entry.get("validated")
    )
    frozen = freeze["frozen_candidate_set"]
    assert sorted(frozen["binance_pairs"]) == validated
    assert frozen["count"] == len(validated) == 18
    assert sorted(frozen["constituents"]) == sorted(pair[:-4] for pair in validated)


def test_excluded_assets_are_not_candidates_and_keep_their_reasons():
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    frozen = freeze["frozen_candidate_set"]
    excluded = {
        entry["symbol"]: entry["exclusion_reason"]
        for entry in universe["eligible_assets"]
        if not entry.get("validated")
    }
    assert excluded == {"HYPEUSDT": "insufficient_hourly_history", "XMRUSDT": "binance_spot_unavailable"}
    for symbol in excluded:
        assert symbol not in frozen["binance_pairs"]
    assert frozen["excluded_after_validation"] == excluded
    assert frozen["excluded_assets_stay_excluded"] is True
    assert frozen["widening_by_reranking_forbidden"] is True


def test_frozen_set_matches_the_execution_protocol_scope():
    freeze = _load(FREEZE_PATH)
    protocol = _load(PROTOCOL_V2_PATH)
    scope = protocol["evaluation_scope"]
    assert sorted(freeze["frozen_candidate_set"]["constituents"]) == sorted(scope["constituents"])
    assert freeze["frozen_candidate_set"]["universe_manifest_hash"] == scope["universe_manifest_hash"]
    assert freeze["frozen_candidate_set"]["data_manifest_hash"] == scope["data_manifest_hash"]


def test_freeze_is_dated_after_the_snapshot_and_the_manifests():
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    frozen_at = verifier.parse_iso_utc(freeze["candidate_freeze_timestamp_utc"])
    retrieved_at = verifier.parse_iso_utc(universe["market_cap_source"]["retrieval_timestamp_utc"])
    created_at = verifier.parse_iso_utc(universe["created_utc"])
    assert retrieved_at < created_at < frozen_at


def test_confirmatory_window_opens_after_the_freeze_and_needs_2160_hours():
    freeze = _load(FREEZE_PATH)
    boundary = freeze["data_boundary"]
    frozen_at = verifier.parse_iso_utc(freeze["candidate_freeze_timestamp_utc"])
    window_start = verifier.parse_iso_utc(boundary["confirmatory_window_start_utc"])
    assert window_start > frozen_at
    assert window_start == verifier.next_hour_boundary(frozen_at)
    assert boundary["min_confirmatory_window_hours"] == 2160
    expected_end = window_start + verifier.timedelta(hours=2160)
    assert verifier.parse_iso_utc(boundary["earliest_possible_confirmatory_window_end_utc"]) == expected_end


def test_confirmatory_window_rules_forbid_reuse_ranking_and_selection_data():
    freeze = _load(FREEZE_PATH)
    boundary = freeze["data_boundary"]
    assert boundary["window_overlap_with_v1_holdout"] == "forbidden"
    assert boundary["v1_holdout_reuse"] == "forbidden"
    assert boundary["v1_holdout_status"] == "EXPOSED_OR_UNKNOWN"
    assert boundary["single_use"] is True
    assert boundary["no_ranking_or_retuning_on_holdout"] is True
    assert boundary["data_used_for_candidate_selection"] == "excluded"
    assert "holdout_exposed_count" in boundary["access_counting"]
    assert "hash-bound" in boundary["evaluation_only_after"]


def test_selection_remainder_is_outstanding_and_binds_the_unchanged_v1_rule():
    freeze = _load(FREEZE_PATH)
    remainder = freeze["selection_remainder"]
    assert remainder["status"] == "OUTSTANDING"
    assert remainder["may_not_change_the_frozen_candidate_set"] is True
    assert remainder["must_be_hash_bound_before_first_confirmatory_read"] is True
    assert remainder["grid_run_authorized"] is False
    v1 = _load(REPO_ROOT / "configs" / "research_v1.json")
    v2 = _load(REPO_ROOT / "configs" / "research_v2.json")
    assert v1["selection"] == v2["selection"]
    assert remainder["max_candidates_per_asset"] == v1["selection"]["max_candidates_per_asset"]


def test_freeze_authorizes_nothing():
    freeze = _load(FREEZE_PATH)
    execution = freeze["execution_authorization"]
    assert execution["grid_run_authorized"] is False
    assert execution["candidate_selection_authorized"] is False
    assert execution["confirmatory_evaluation_authorized"] is False
    assert execution["candle_fetch_authorized"] is False
    assert freeze["freeze_status"] == "CANDIDATE_SET_FROZEN_NO_EXECUTION"


def test_supersedes_the_v1_candidate_manifest():
    freeze = _load(FREEZE_PATH)
    supersedes = freeze["supersedes"]
    v1_candidates = _load(V1_CANDIDATE_PATH)
    assert supersedes["protocol_version"] == "v1"
    assert supersedes["candidate_manifest_path"] == "research/candidate_manifest.json"
    assert supersedes["candidate_manifest_sha256"] == verifier.sha256_file(V1_CANDIDATE_PATH)
    assert supersedes["candidate_manifest_hash"] == v1_candidates["manifest_hash"]
    assert supersedes["v1_artifacts_are_immutable"] is True


def test_v1_candidate_manifest_v2_is_not_a_v2_universe_candidate_manifest():
    freeze = _load(FREEZE_PATH)
    not_a_v2 = freeze["supersedes"]["not_a_v2_universe_candidate_manifest"]
    v1_candidates_v2 = _load(V1_CANDIDATE_V2_PATH)
    assert not_a_v2["path"] == "research/candidate_manifest_v2.json"
    assert not_a_v2["sha256"] == verifier.sha256_file(V1_CANDIDATE_V2_PATH)
    assert not_a_v2["manifest_version"] == v1_candidates_v2["manifest_version"] == 2
    without_supersedes = {k: v for k, v in freeze.items() if k != "supersedes"}
    assert "research/candidate_manifest_v2.json" not in json.dumps(without_supersedes)


def test_v1_artifacts_are_unchanged():
    for relative, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, relative


def test_v1_campaign_authorization_is_untouched():
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    freeze = _load(FREEZE_PATH)
    assert authorization["protocol_version"] == "v1"
    assert authorization["authorized"] is True
    assert authorization["code_hash"] == compute_code_hash()
    assert freeze["snapshot_identity"]["code_hash"] == compute_code_hash()
    assert freeze["code_hash_constraint"]["authorized_code_hash"] == compute_code_hash()


def test_code_hash_constraint_names_only_genuinely_outside_paths():
    freeze = _load(FREEZE_PATH)
    constraint = freeze["code_hash_constraint"]
    assert constraint["hashed_set_root"] == "src/breakout_research"
    assert constraint["v2_execution_code_must_live_outside_the_hashed_set"] is True
    for relative in constraint["inside_hashed_set_examples"]:
        assert verifier.path_is_inside_hashed_set(relative), relative
    for relative in constraint["outside_hashed_set_examples"]:
        assert not verifier.path_is_inside_hashed_set(relative), relative
    assert verifier.hashed_source_digest(REPO_ROOT) == compute_code_hash()


def test_no_v2_execution_artifacts_or_result_rows_exist():
    for relative in verifier.V2_EXECUTION_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative
    data = _load(DATA_V2_PATH)
    window = data["confirmatory_window"]
    assert window["holdout_exposed_count"] == 0
    assert window["confirmatory_window_status"] == "NOT_STARTED"


def test_verifier_detects_a_tampered_candidate_set(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(freeze: Dict[str, Any]) -> None:
        freeze["frozen_candidate_set"]["binance_pairs"].remove("BTCUSDT")
        freeze["frozen_candidate_set"]["constituents"].remove("BTC")
        freeze["frozen_candidate_set"]["count"] = 17

    _tamper_freeze(root, mutate)
    failures = _failures(root)
    assert any("frozen candidate set is not the validated" in failure for failure in failures)


def test_verifier_detects_a_confirmatory_window_that_starts_before_the_freeze(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(freeze: Dict[str, Any]) -> None:
        freeze["data_boundary"]["confirmatory_window_start_utc"] = "2026-10-19T20:00:00Z"

    _tamper_freeze(root, mutate)
    failures = _failures(root)
    assert any("does not start after the candidate freeze" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_freeze(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(freeze: Dict[str, Any]) -> None:
        freeze["execution_authorization"]["grid_run_authorized"] = True

    _tamper_freeze(root, mutate)
    failures = _failures(root)
    assert any("grid_run_authorized is not false" in failure for failure in failures)


def test_verifier_detects_a_widened_universe_manifest(tmp_path):
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_V2_PATH)
    for entry in universe["eligible_assets"]:
        if entry["symbol"] == "XMRUSDT":
            entry["validated"] = True
            entry["exclusion_reason"] = None
    _replace(root, "research/universe_manifest_v2.json", universe)
    failures = _failures(root)
    assert any("frozen candidate set is not the validated" in failure for failure in failures)


def test_verifier_detects_a_v2_execution_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "research" / "shards_v2").mkdir(exist_ok=True)
    failures = _failures(root)
    assert any("a v2 execution artifact exists" in failure for failure in failures)


def test_verifier_detects_a_v2_result_row(tmp_path):
    root = _mirror_repo(tmp_path)
    _replace(root, "research/results.jsonl", '{"campaign_id": "v2-campaign", "asset": "BTCUSDT"}\n')
    failures = _failures(root)
    assert any("v2 campaign rows" in failure for failure in failures)


def test_verifier_detects_confirmatory_exposure(tmp_path):
    root = _mirror_repo(tmp_path)
    data = _load(DATA_V2_PATH)
    data["confirmatory_window"]["holdout_exposed_count"] = 3
    _replace(root, "research/data_manifest_v2.json", data)
    failures = _failures(root)
    assert any("records confirmatory-window exposure" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "research" / "candidate_manifest.json").unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


def test_freeze_does_not_touch_the_v1_source_tree():
    """The freeze is a design artifact: no module under src/ changed."""
    freeze = _load(FREEZE_PATH)
    assert freeze["snapshot_identity"]["code_hash"] == "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"

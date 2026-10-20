"""Tests for the preregistered v2 execution amendment 1.

``configs/research_v2_execution_amendment_1.json`` corrects the code-hash
constraint of the v2 execution protocol and records the bounded parameters a
future v2 selection grid run would have to satisfy. It authorizes nothing. The
tests prove that

* the manifest hash recomputes from the document itself;
* the amended protocol is byte-identical, still carries the defective text as
  historical evidence, and both corrections are recorded;
* the code-hash constraint names the hashed source set, classifies every path
  correctly, records the authorized v1 code hash and binds the tree to a
  portable, order-independent source digest;
* the authorized scope is exactly the frozen v2 candidate set, the excluded
  assets stay excluded and the scope is bound to the hash-verified v2
  artifacts;
* the selection data boundary is the frozen confirmatory-window start and
  forbids confirmatory reads, v1 holdout reuse and v1 cycle-0 mixing;
* the v2 result paths are the v2 paths, the v1 paths are forbidden and none of
  the v2 paths exists yet;
* the selection rule is the unchanged v1 rule, the bounds are concrete and the
  stopping conditions, rollback rule and falsifiers are recorded;
* nothing is authorized and nothing has been executed;
* the verifier is not vacuous: tampering with the amendment, the protocol, the
  frozen scope, the source tree or the result store is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_execution_amendment_1.json"
PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v2_execution.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"

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


verifier = _load_module(
    "verify_research_v2_execution_amendment_1",
    "scripts/verify_research_v2_execution_amendment_1.py",
)


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
            if relative == Path("research_state") and name == "checkpoint_v2.json":
                # The mirror holds no run artifact: the verifier's executed-state
                # rule is exercised against the real repository, not the mirror.
                continue
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


def _tamper_amendment(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    amendment = _load(AMENDMENT_PATH)
    mutate(amendment)
    _replace(root, "configs/research_v2_execution_amendment_1.json", amendment)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _digest_from_enumeration(base: Path, enumeration: str) -> str:
    """Hash the hashed source set from a chosen enumeration of the file set.

    The canonical digest sorts the relative paths of the files before hashing
    them, so the enumeration that produced the file set does not matter. The
    comparison proves that the digest is a pure function of the file set and
    therefore portable, unlike ``compute_code_hash()``.
    """
    import hashlib

    if enumeration == "sorted":
        relatives = sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py"))
    elif enumeration == "walk":
        relatives = [
            (Path(root) / name).relative_to(base).as_posix()
            for root, _dirs, files in os.walk(base)
            for name in files
            if name.endswith(".py")
        ]
    else:
        relatives = [
            (Path(root) / name).relative_to(base).as_posix()
            for root, dirs, files in os.walk(base, topdown=False)
            for name in files
            if name.endswith(".py")
        ]
    digest = hashlib.sha256()
    for relative in sorted(relatives):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(
            hashlib.sha256((base / relative).read_bytes()).hexdigest().encode("ascii") + b"\n"
        )
    return digest.hexdigest()


def test_manifest_hash_recomputes_from_the_document():
    amendment = _load(AMENDMENT_PATH)
    excluded = tuple(amendment["hashing"]["manifest_hash_excluded_keys"])
    assert amendment["manifest_hash"] == verifier.compute_manifest_hash(amendment, excluded)


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_amendment_binds_the_immutable_protocol():
    amendment = _load(AMENDMENT_PATH)
    protocol = _load(PROTOCOL_PATH)
    amends = amendment["amends"]
    assert amends["file"] == "configs/research_v2_execution.json"
    assert amends["file_sha256"] == verifier.sha256_file(PROTOCOL_PATH)
    assert amends["specification_hash"] == protocol["specification_hash"]
    body = {key: value for key, value in protocol.items() if key != "specification_hash"}
    assert protocol["specification_hash"] == verifier.sha256_bytes(
        verifier.canonical(body).encode("utf-8")
    )
    assert "src/breakout_research/v2/" in protocol["code_hash_constraint"]["chosen_approach"]


def test_both_corrections_are_recorded():
    amendment = _load(AMENDMENT_PATH)
    corrections = {item["id"]: item for item in amendment["amends"]["corrections"]}
    assert set(corrections) == {"C1", "C2"}
    assert "src/breakout_research/v2/" in corrections["C1"]["defect"]
    assert "compute_code_hash()" in corrections["C2"]["defect"]
    for item in corrections.values():
        for field in ("topic", "defect", "correction", "status"):
            assert str(item[field]).strip(), (item["id"], field)


def test_code_hash_constraint_names_only_genuinely_outside_paths():
    amendment = _load(AMENDMENT_PATH)
    constraint = amendment["code_hash_constraint"]
    assert constraint["hashed_set_root"] == "src/breakout_research"
    for relative in constraint["paths_correctly_classified_as_outside_hashed_set"]:
        assert not verifier.path_is_inside_hashed_set(relative), relative
    for relative in constraint["paths_not_permitted_inside_hashed_set"]:
        assert verifier.path_is_inside_hashed_set(relative), relative
    assert "src/breakout_research/v2/" in constraint["paths_not_permitted_inside_hashed_set"]


def test_code_hash_constraint_records_the_authorized_code_hash():
    amendment = _load(AMENDMENT_PATH)
    constraint = amendment["code_hash_constraint"]
    authorization = _load(AUTHORIZATION_PATH)
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    assert constraint["authorized_code_hash"] == authorization["code_hash"]
    assert constraint["authorized_code_hash"] == freeze["snapshot_identity"]["code_hash"]
    assert constraint["authorized_code_hash"] == universe["snapshot_identity"]["code_hash"]
    assert authorization["authorized"] is True
    assert authorization["protocol_version"] == "v1"


def test_canonical_source_digest_is_portable_and_matches_the_tree():
    amendment = _load(AMENDMENT_PATH)
    constraint = amendment["code_hash_constraint"]
    base = REPO_ROOT / "src" / "breakout_research"
    assert constraint["canonical_source_digest"] == verifier.canonical_source_digest(REPO_ROOT)
    assert constraint["canonical_source_digest"] == _digest_from_enumeration(base, "sorted")
    assert constraint["canonical_source_digest"] == _digest_from_enumeration(base, "walk")
    assert constraint["canonical_source_digest"] == _digest_from_enumeration(base, "bottom_up")
    assert constraint["canonical_source_digest_algorithm"]["portable"] is True


def test_the_portable_digest_does_not_depend_on_the_filesystem_enumeration():
    """The ordered code hash is checkout-dependent; the canonical digest is not.

    ``compute_code_hash()`` concatenates the files directory by directory in
    filesystem enumeration order, so the same git-clean tree yields a different
    digest on another machine. The canonical digest sorts the relative paths
    first and is therefore reproducible everywhere. The verifier therefore binds
    the tree to the canonical digest and never fails on the ordered digest.
    """
    report = verifier.verify(REPO_ROOT)
    assert report["canonical_source_digest"] == verifier.canonical_source_digest(REPO_ROOT)
    assert report["live_ordered_code_hash"] == verifier.live_ordered_code_hash(REPO_ROOT)
    assert not any("code hash" in failure for failure in report["failures"])


def test_authorized_scope_is_exactly_the_frozen_candidate_set():
    amendment = _load(AMENDMENT_PATH)
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    scope = amendment["v2_selection_authorization"]["scope"]
    frozen = freeze["frozen_candidate_set"]
    assert sorted(scope["constituents"]) == sorted(frozen["constituents"])
    assert sorted(scope["binance_pairs"]) == sorted(frozen["binance_pairs"])
    validated = sorted(
        entry["symbol"] for entry in universe["eligible_assets"] if entry.get("validated")
    )
    assert sorted(scope["binance_pairs"]) == validated
    assert scope["constituents_count"] == len(validated) == 18
    assert scope["widening_by_reranking_forbidden"] is True


def test_excluded_assets_stay_excluded():
    amendment = _load(AMENDMENT_PATH)
    universe = _load(UNIVERSE_V2_PATH)
    scope = amendment["v2_selection_authorization"]["scope"]
    excluded = {
        entry["symbol"]: entry["exclusion_reason"]
        for entry in universe["eligible_assets"]
        if not entry.get("validated")
    }
    assert excluded == {
        "HYPEUSDT": "insufficient_hourly_history",
        "XMRUSDT": "binance_spot_unavailable",
    }
    for symbol in excluded:
        assert symbol not in scope["binance_pairs"]
    assert scope["excluded_after_validation"] == excluded
    assert scope["excluded_assets_stay_excluded"] is True


def test_scope_is_bound_to_the_hash_verified_v2_artifacts():
    amendment = _load(AMENDMENT_PATH)
    scope = amendment["v2_selection_authorization"]["scope"]
    assert scope["bound_to_universe_hash"] == _load(UNIVERSE_V2_PATH)["manifest_hash"]
    assert scope["bound_to_data_hash"] == _load(DATA_V2_PATH)["manifest_hash"]
    assert scope["bound_to_freeze_hash"] == _load(FREEZE_PATH)["manifest_hash"]
    assert scope["candidate_manifest_path"] == "configs/research_v2_candidate_freeze.json"


def test_data_boundary_matches_the_frozen_confirmatory_window_start():
    amendment = _load(AMENDMENT_PATH)
    freeze = _load(FREEZE_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    boundary = amendment["v2_selection_authorization"]["data_boundary"]
    assert boundary["candles_before_utc"] == freeze["data_boundary"]["confirmatory_window_start_utc"]
    assert boundary["development_data_only"] is True
    assert boundary["confirmatory_window_never_read_during_selection"] is True
    assert boundary["v1_holdout_never_reused"] is True
    assert boundary["v1_cycle0_units_never_mixed"] is True
    assert boundary["v1_cycle0_units"] == spec_v2["comparability"]["v1_cycle0_units"] == 497664


def test_v2_paths_are_the_v2_paths_and_v1_paths_are_forbidden():
    amendment = _load(AMENDMENT_PATH)
    protocol = _load(PROTOCOL_PATH)
    paths = amendment["v2_selection_authorization"]["paths"]
    layout = protocol["v2_result_layout"]
    assert paths["shards_dir"] == layout["shard_directory"] == "research/shards_v2"
    assert paths["ledger"] == layout["ledger_path"] == "research/ledger_v2.json"
    assert paths["results_manifest"] == layout["results_manifest_path"] == "research/results_manifest_v2.json"
    assert paths["never_use_v1_paths"] is True
    forbidden = {item.rstrip("/") for item in paths["v1_paths_forbidden"]}
    assert "research/results.jsonl" in forbidden
    assert "research/results_shards" in forbidden
    assert "research_state/checkpoint.json" in forbidden
    for key in ("shards_dir", "ledger", "results_manifest", "results_stream", "checkpoint"):
        assert paths[key].rstrip("/") not in forbidden, key


def test_selection_rule_is_the_unchanged_v1_rule():
    amendment = _load(AMENDMENT_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    selection = amendment["v2_selection_authorization"]["selection_rule"]
    assert selection["unchanged_from_v1"] is True
    assert selection["reference"] == "configs/research_v1.json"
    assert spec_v1["selection"] == spec_v2["selection"]
    assert selection["max_candidates_per_asset"] == spec_v1["selection"]["max_candidates_per_asset"]


def test_bounds_are_concrete():
    amendment = _load(AMENDMENT_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    scope = amendment["v2_selection_authorization"]["scope"]
    bounds = amendment["v2_selection_authorization"]["bounds"]
    assert bounds["max_assets"] == scope["constituents_count"] == 18
    assert bounds["max_configs_per_asset"] == spec_v1["strategy_grid"]["total_combinations"] == 2304
    assert bounds["max_total_config_units"] == 18 * 2304
    assert bounds["attempts"] == 1
    assert bounds["max_retries_on_technical_failure"] == spec_v1["checkpointing"]["max_retries"]
    assert str(bounds["resource_limits"]).strip()


def test_stopping_conditions_rollback_and_falsifiers_are_recorded():
    amendment = _load(AMENDMENT_PATH)
    block = amendment["v2_selection_authorization"]
    stopping = " ".join(block["stopping_conditions"]).lower()
    assert "no candidate survives" in stopping
    assert "report" in stopping
    assert "v1" in block["rollback_rule"].lower()
    assert "checkpoint" in block["rollback_rule"].lower()
    falsifiers = " ".join(block["falsifiers"]).lower()
    assert "src/breakout_research" in falsifiers
    assert "confirmatory" in falsifiers
    assert "v1" in falsifiers


def test_amendment_authorizes_nothing():
    amendment = _load(AMENDMENT_PATH)
    assert amendment["v2_selection_authorization"]["authorized"] is False
    assert amendment["v2_selection_authorization"]["no_execution"] is True
    execution = amendment["execution_authorization"]
    assert execution["grid_run_authorized"] is False
    assert execution["candidate_selection_authorized"] is False
    assert execution["confirmatory_evaluation_authorized"] is False
    assert execution["candle_fetch_authorized"] is False
    assert amendment["amendment_status"] == "PREREGISTERED_AMENDMENT_DESIGN_ONLY"


def test_the_executed_state_stays_inside_the_amendment_bounds():
    """The performed run, if there is one, stayed inside *this* amendment.

    Before the run this asserts the not-executed state; after the run it
    asserts that the recorded counts stay inside the amendment's bounds and
    that nothing is exposed. The verifier's rule was replaced -- not deleted --
    when the run happened.
    """
    ledger_path = REPO_ROOT / "research" / "ledger_v2.json"
    data = _load(DATA_V2_PATH)
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    if not ledger_path.exists():
        for relative in verifier.V2_EXECUTION_ARTIFACTS:
            assert not (REPO_ROOT / relative).exists(), relative
        return
    amendment = _load(AMENDMENT_PATH)
    ledger = _load(ledger_path)
    bounds = amendment["v2_selection_authorization"]["bounds"]
    counts = ledger["counts"]
    assert counts["config_units"] <= bounds["max_total_config_units"]
    spec_v1 = _load(SPEC_V1_PATH)
    planned = (
        bounds["max_assets"]
        * bounds["max_configs_per_asset"]
        * len(spec_v1["folds"]["window_fractions"])
        * len(spec_v1["costs"]["scenarios"])
    )
    assert counts["execution_units"] <= planned
    assert ledger["holdout_exposed_count"] == 0
    assert not ledger["v1_artifacts_touched"]


def test_verifier_detects_an_executed_state_above_the_amendment_bounds(tmp_path):
    root = _mirror_repo(tmp_path)
    ledger = {
        "scope": {"binance_pairs": [], "constituents": []},
        "bounds": {},
        "counts": {"config_units": 10_000_000, "execution_units": 10_000_000},
        "holdout_exposed_count": 0,
        "v1_artifacts_touched": [],
    }
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any(
        "exceeds this amendment's configuration-unit bound" in failure
        for failure in failures
    )


def test_v1_artifacts_are_unchanged():
    for relative, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, relative


def test_v1_campaign_authorization_is_untouched():
    authorization = _load(AUTHORIZATION_PATH)
    amendment = _load(AMENDMENT_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    assert authorization["protocol_version"] == "v1"
    assert authorization["authorized"] is True
    assert authorization["specification_hash"] == spec_v1["specification_hash"]
    assert authorization["code_hash"] == amendment["code_hash_constraint"]["authorized_code_hash"]


def test_verifier_detects_a_tampered_manifest_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["manifest_hash"] = "0" * 64

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_a_widened_scope(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        scope = amendment["v2_selection_authorization"]["scope"]
        scope["constituents"].append("HYPE")
        scope["binance_pairs"].append("HYPEUSDT")
        scope["constituents_count"] = 19

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("frozen candidate set" in failure for failure in failures)


def test_verifier_detects_a_scope_bound_to_a_stale_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["v2_selection_authorization"]["scope"]["bound_to_freeze_hash"] = "0" * 64

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("not bound to the current v2 candidate freeze" in failure for failure in failures)


def test_verifier_detects_a_data_boundary_that_reads_the_confirmatory_window(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["v2_selection_authorization"]["data_boundary"][
            "confirmatory_window_never_read_during_selection"
        ] = False

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any(
        "confirmatory_window_never_read_during_selection" in failure for failure in failures
    )


def test_verifier_detects_a_v1_path_in_the_v2_paths(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["v2_selection_authorization"]["paths"]["results_manifest"] = "research/results_manifest.json"

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("also a forbidden v1 path" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_amendment(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["v2_selection_authorization"]["authorized"] = True
        amendment["v2_selection_authorization"]["no_execution"] = False
        amendment["execution_authorization"]["grid_run_authorized"] = True

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("grid_run_authorized is not false" in failure for failure in failures)
    assert any("not recorded as unauthorized" in failure for failure in failures)


def test_verifier_detects_a_code_hash_constraint_that_names_an_inside_path_as_outside(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(amendment: Dict[str, Any]) -> None:
        amendment["code_hash_constraint"]["paths_correctly_classified_as_outside_hashed_set"] = [
            "src/breakout_research/v2/"
        ]

    _tamper_amendment(root, mutate)
    failures = _failures(root)
    assert any("classified as outside the hashed set but is inside it" in failure for failure in failures)


def test_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "src" / "breakout_research" / "zz_v2_execution.py").write_text(
        "# a v2 execution module that must never live inside the hashed set\n",
        encoding="utf-8",
    )
    failures = _failures(root)
    assert any("does not match the recorded canonical digest" in failure for failure in failures)


def test_verifier_detects_an_edited_protocol(tmp_path):
    root = _mirror_repo(tmp_path)
    protocol = _load(PROTOCOL_PATH)
    protocol["code_hash_constraint"]["chosen_approach"] = "edited"
    _replace(root, "configs/research_v2_execution.json", protocol)
    failures = _failures(root)
    assert any("does not match its recorded file digest" in failure for failure in failures)


def test_verifier_detects_a_v2_execution_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    # An execution artifact without the ledger of the run is an inconsistent
    # state: the ledger is what records the run's identity and its counts.
    (root / "research" / "ledger_v2.json").unlink(missing_ok=True)
    (root / "research" / "results_manifest_v2.json").unlink(missing_ok=True)
    (root / "research" / "shards_v2").mkdir(exist_ok=True)
    failures = _failures(root)
    assert any(
        "a v2 execution artifact exists without the ledger of the run" in failure
        for failure in failures
    )


def test_verifier_detects_a_v2_result_row(tmp_path):
    root = _mirror_repo(tmp_path)
    _replace(root, "research/results.jsonl", '{"campaign_id": "v2-campaign", "asset": "BTCUSDT"}\n')
    failures = _failures(root)
    assert any("v2 campaign rows" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "research" / "candidate_manifest.json").unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)

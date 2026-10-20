"""Tests for the preregistered v3 confirmatory-evaluation protocol.

``configs/research_v3_confirmatory_protocol.json`` preregisters how the four
published v3 candidates of ``research/v3_selected_configurations_manifest.json``
will be evaluated on the v3 confirmatory window once that window exists. The
tests prove that

* the manifest hash recomputes from the document itself and the document is
  reproducible from its producer;
* the evaluation scope is exactly the four published candidates, with their
  configuration ids, bound to the selected-configurations manifest, the
  selection authorization, the v3 specification, the effective and base v3
  data-manifest identities and the v3 universe manifest, with the two assets
  without a candidate out of scope and carrying their reason;
* the confirmatory window opens at the frozen start, needs 2,160 closed hourly
  candles, is single-use, never overlaps the v1 holdout or the v2 confirmatory
  window, is never reused from v1 or v2, is never used for selection and is
  never ranked or re-tuned on;
* the data path records a single retrieval after the readiness test, exposure
  counting and v3-manifest hashing, and requires a **window benchmark series**
  that does not exist yet, may not be replaced by the development benchmark, is
  aligned by UTC candle close, is never forward-filled, fails closed when
  missing, short or misaligned, and never drops the 576 ``btc_ema_168``
  configurations per asset;
* the evaluation rule records the unchanged v1 metric, the unchanged cost
  scenarios and the prohibition on re-tuning, re-ranking or grid extension;
* **exactly one** confirmatory decision criterion is stated anywhere in the
  document, and it is the preregistered v3 promotion rule copied verbatim;
* the reporting block names the assets without a candidate, never discards a
  negative or inconclusive result and carries the v1/v2 BTC-alignment
  deviation as an unrepaired disclosure;
* the authorization boundary authorizes no evaluation, no window read and no
  benchmark retrieval, and nothing has been executed under the protocol;
* the verifier is not vacuous: tampering with the protocol, the published
  manifest, the ledger, the source tree or the frozen artifacts is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v3_confirmatory_protocol.json"
MANIFEST_PATH = REPO_ROOT / "research" / "v3_selected_configurations_manifest.json"
SELECTION_AUTH_PATH = REPO_ROOT / "configs" / "research_v3_selection_authorization_1.json"
SPEC_V3_PATH = REPO_ROOT / "configs" / "research_v3.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
DATA_V3_PATH = REPO_ROOT / "research" / "data_manifest_v3.json"
DATA_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v3_data_manifest_amendment_1.json"
UNIVERSE_V3_PATH = REPO_ROOT / "research" / "universe_manifest_v3.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
EXECUTION_PATH = REPO_ROOT / "configs" / "research_v3_execution.json"
EXECUTION_AMENDMENT_1_PATH = REPO_ROOT / "configs" / "research_v3_execution_amendment_1.json"
EXECUTION_AMENDMENT_2_PATH = REPO_ROOT / "configs" / "research_v3_execution_amendment_2.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"
CODE_HASH_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"
LEDGER_V3_PATH = REPO_ROOT / "research" / "ledger_v3.json"
CHECKPOINT_V3_PATH = REPO_ROOT / "research_state" / "checkpoint_v3.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"

HASHED_SET_ROOT = "src/breakout_research"

#: Every file the verifier reads. The mirror copies exactly these, so the
#: tamper tests stay fast even though the repository holds tens of thousands
#: of result files.
MIRRORED_FILES = (
    "configs/research_v3_confirmatory_protocol.json",
    "configs/research_v3_selection_authorization_1.json",
    "configs/research_v3.json",
    "configs/research_v1.json",
    "configs/research_v3_data_manifest_amendment_1.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_candidate_freeze_amendment_1.json",
    "configs/research_v3_candidate_freeze_amendment_2.json",
    "configs/research_v3_execution.json",
    "configs/research_v3_execution_amendment_1.json",
    "configs/research_v3_execution_amendment_2.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "research/v3_selected_configurations_manifest.json",
    "research/data_manifest_v3.json",
    "research/data_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/ledger_v3.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v3.json",
)


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v3_confirmatory_protocol", "scripts/verify_v3_confirmatory_protocol.py")
producer = _load_module("build_v3_confirmatory_protocol", "scripts/build_v3_confirmatory_protocol.py")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree holding the parts of the repository the verifier reads."""
    root = tmp_path / "repo"
    for relative in MIRRORED_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # The hashed set is copied for real, recursively: a symlink would let a
    # test write through it into the working tree.
    hashed = root / HASHED_SET_ROOT
    hashed.mkdir(parents=True, exist_ok=True)
    for current, dirs, files in os.walk(REPO_ROOT / HASHED_SET_ROOT):
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(Path(current) / name, root / relative / name)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper_protocol(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    protocol = _load(PROTOCOL_PATH)
    mutate(protocol)
    _replace(root, "configs/research_v3_confirmatory_protocol.json", protocol)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_manifest_hash_recomputes_from_the_document():
    protocol = _load(PROTOCOL_PATH)
    excluded = tuple(protocol["hashing"]["manifest_hash_excluded_keys"])
    assert protocol["manifest_hash"] == verifier.compute_manifest_hash(protocol, excluded)


def test_protocol_is_reproducible_from_the_producer():
    built = producer.build(REPO_ROOT)
    assert json.loads(PROTOCOL_PATH.read_text(encoding="utf-8")) == built


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_protocol_status_records_no_evaluation():
    protocol = _load(PROTOCOL_PATH)
    assert protocol["protocol_status"] == "PREREGISTERED_NO_EVALUATION"
    assert protocol["authorization_boundary"]["authorizes_evaluation"] is False
    assert protocol["authorization_boundary"]["authorizes_candle_read_before_window_exists"] is False
    assert protocol["authorization_boundary"]["authorizes_window_benchmark_retrieval"] is False


def test_evaluation_scope_is_exactly_the_published_candidates():
    protocol = _load(PROTOCOL_PATH)
    manifest = _load(MANIFEST_PATH)
    selection_auth = _load(SELECTION_AUTH_PATH)
    spec_v3 = _load(SPEC_V3_PATH)
    data_manifest = _load(DATA_V3_PATH)
    data_amendment = _load(DATA_AMENDMENT_PATH)
    universe = _load(UNIVERSE_V3_PATH)
    scope = protocol["evaluation_scope"]
    assert scope["selected_configurations_manifest"] == "research/v3_selected_configurations_manifest.json"
    assert scope["selected_configurations_manifest_hash"] == manifest["manifest_hash"]
    assert scope["selection_authorization_manifest_hash"] == selection_auth["manifest_hash"]
    assert scope["v3_specification_hash"] == spec_v3["specification_hash"]
    assert scope["v3_data_manifest_hash"] == data_amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    assert scope["v3_base_data_manifest_hash"] == data_manifest["manifest_hash"]
    assert scope["v3_universe_manifest_hash"] == universe["manifest_hash"]

    selections = manifest["selections"]
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assert scope["in_scope_assets"] == len(assets_with_candidate) == 4
    assert assets_with_candidate == ["ICPUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT"]
    assert scope["in_scope_configurations"] == [
        {"asset": "ICPUSDT", "config_id": "cfg_0444", "candidate_status": "CANDIDATE_PENDING_HOLDOUT"},
        {"asset": "PEPEUSDT", "config_id": "cfg_1804", "candidate_status": "CANDIDATE_PENDING_HOLDOUT"},
        {"asset": "SHIBUSDT", "config_id": "cfg_0544", "candidate_status": "CANDIDATE_PENDING_HOLDOUT"},
        {"asset": "WLDUSDT", "config_id": "cfg_1380", "candidate_status": "CANDIDATE_PENDING_HOLDOUT"},
    ]
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    assert scope["out_of_scope_assets_without_candidate"] == assets_without_candidate
    assert assets_without_candidate == ["AAVEUSDT", "QNTUSDT"]
    assert scope["out_of_scope_reasons"] == {
        "AAVEUSDT": "NO_CANDIDATE",
        "QNTUSDT": "INSUFFICIENT_EVIDENCE",
    }
    assert scope["excluded_assets_stay_excluded"] is True
    assert scope["scope_may_not_be_widened_narrowed_or_reranked"] is True


def test_confirmatory_window_opens_at_the_frozen_start_and_needs_2160_hours():
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    window = protocol["window_definition"]
    boundary = freeze["data_boundary"]
    assert window["window_opens_utc"] == boundary["confirmatory_window_start_utc"]
    assert window["window_opens_utc"] == "2026-10-20T13:00:00Z"
    assert window["minimum_closed_hourly_candles"] == 2160
    assert window["earliest_possible_end_utc"] == boundary["earliest_possible_confirmatory_window_end_utc"]
    assert window["earliest_possible_end_utc"] == "2027-01-18T13:00:00Z"


def test_confirmatory_window_rules_forbid_reuse_overlap_and_retuning():
    protocol = _load(PROTOCOL_PATH)
    window = protocol["window_definition"]
    assert window["single_use"] is True
    assert window["must_not_overlap_v1_holdout"] is True
    assert window["must_not_overlap_v2_confirmatory_window"] is True
    assert window["never_reused_from_v1"] is True
    assert window["never_reused_from_v2"] is True
    assert window["never_used_for_candidate_selection"] is True
    assert window["no_ranking_or_retuning_on_window"] is True
    assert window["never_populated_with_data_predating_the_candidate_freeze"] is True
    assert window["window_moved_by_the_candidate_freeze_amendments"] is False


def test_the_freeze_amendments_did_not_move_the_window():
    protocol = _load(PROTOCOL_PATH)
    window = protocol["window_definition"]
    for path in (FREEZE_AMENDMENT_1_PATH, FREEZE_AMENDMENT_2_PATH):
        amendment = _load(path)
        assert amendment["data_boundary"]["confirmatory_window_start_utc"] == window["window_opens_utc"]
        assert amendment["data_boundary"]["min_confirmatory_window_hours"] == window["minimum_closed_hourly_candles"]


def test_data_path_records_single_retrieval_and_exposure_counting():
    protocol = _load(PROTOCOL_PATH)
    data_path = protocol["data_path"]
    assert data_path["retrieval_happens_once_after_readiness_test_passes"] is True
    assert data_path["every_read_counted_in_holdout_exposed_count"] is True
    assert data_path["hashed_and_verified_against_v3_data_manifest_scheme"] is True
    data_amendment = _load(DATA_AMENDMENT_PATH)
    assert data_path["data_manifest_hash"] == data_amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    assert data_path["confirmatory_window_start_utc"] == protocol["window_definition"]["window_opens_utc"]
    readiness = data_path["readiness_test"]
    assert readiness["must_pass_before_any_window_read"] is True
    assert len(readiness["checks"]) > 0


def test_the_window_benchmark_series_is_required_and_cannot_be_substituted():
    protocol = _load(PROTOCOL_PATH)
    selection_auth = _load(SELECTION_AUTH_PATH)
    manifest = _load(MANIFEST_PATH)
    benchmark = protocol["data_path"]["benchmark"]
    assert benchmark["symbol"] == "BTCUSDT"
    assert benchmark["benchmark_is_not_a_candidate"] is True
    assert benchmark["window_benchmark_series_required"] is True
    assert benchmark["window_benchmark_series_exists_yet"] is False
    assert benchmark["development_benchmark_content_hash"] == manifest["benchmark"]["content_hash"]
    assert benchmark["development_benchmark_covers_the_window"] is False
    assert benchmark["development_benchmark_may_be_reused_as_the_window_benchmark"] is False
    assert benchmark["window_benchmark_retrieval_happens_once"] is True
    assert benchmark["window_benchmark_is_hash_verified"] is True
    assert benchmark["no_forward_fill"] is True
    assert benchmark["btc_configurations_dropped"] is False
    assert benchmark["fail_closed"] == selection_auth["authorized_run"]["benchmark"]["fail_closed"]
    assert "576" in benchmark["grid_rule"]


def test_the_benchmark_alignment_rule_is_the_frozen_methodology():
    protocol = _load(PROTOCOL_PATH)
    selection_auth = _load(SELECTION_AUTH_PATH)
    benchmark = protocol["data_path"]["benchmark"]
    frozen = selection_auth["authorized_run"]["benchmark"]
    assert benchmark["alignment_rule"] == frozen["alignment_rule"]
    assert benchmark["methodology_rule"] == frozen["methodology_rule"]
    assert benchmark["methodology_reference"] == "docs/research_protocol.md:101"
    assert benchmark["grid_rule"] == frozen["grid_rule"]


def test_evaluation_rule_records_unchanged_v1_rule_and_costs():
    protocol = _load(PROTOCOL_PATH)
    rule = protocol["evaluation_rule"]
    spec_v1 = _load(SPEC_V1_PATH)
    spec_v3 = _load(SPEC_V3_PATH)
    assert rule["unchanged_v1_evaluation_metric"] is True
    assert rule["unchanged_cost_scenarios"] is True
    assert rule["no_retuning_reranking_or_grid_extension_on_window"] is True
    assert rule["selection_rule_reference"] == "configs/research_v1.json#selection"
    assert rule["cost_scenarios"] == spec_v1["costs"]["scenarios"] == [1.0, 2.0, 3.0]
    assert spec_v1["selection"] == spec_v3["selection"]


def test_exactly_one_confirmatory_decision_criterion():
    protocol = _load(PROTOCOL_PATH)
    spec_v3 = _load(SPEC_V3_PATH)
    paths = verifier.collect_criterion_keys(protocol)
    assert paths == ["decision_rule.criteria"]
    decision = protocol["decision_rule"]
    assert decision["criterion_count"] == 1
    assert decision["exactly_one_criterion"] is True
    assert decision["no_competing_criterion"] is True
    assert decision["authoritative_source"] == "configs/research_v3.json#holdout.promotion_rule"
    promotion = spec_v3["holdout"]["promotion_rule"]
    assert decision["criteria"] == promotion["criteria"]
    assert decision["status_vocabulary"] == promotion["status_vocabulary"]
    assert decision["verdicts"]["status_vocabulary_is_not_extended"] is True


def test_reporting_and_falsifiers_define_outcomes_and_falsifiers():
    protocol = _load(PROTOCOL_PATH)
    spec_v3 = _load(SPEC_V3_PATH)
    reporting = protocol["reporting_and_falsifiers"]
    assert reporting["every_evaluated_asset_and_candidate_reported"] is True
    assert reporting["assets_without_a_candidate_are_named"] is True
    assert reporting["null_result_reported"] is True
    assert reporting["negative_and_inconclusive_results_are_never_discarded"] is True
    assert reporting["v1_holdout_never_reopened"] is True
    assert reporting["v2_confirmatory_window_never_read"] is True
    assert reporting["holdout_report_required_fields"] == spec_v3["holdout"]["v3_holdout_report_required_fields"]
    assert isinstance(reporting["falsifiers"], list)
    assert len(reporting["falsifiers"]) > 0


def test_the_deviation_disclosure_is_carried_and_not_repaired():
    protocol = _load(PROTOCOL_PATH)
    manifest = _load(MANIFEST_PATH)
    deviation = protocol["deviation_disclosure"]
    published = manifest["deviation_disclosure"]
    assert deviation["records_with_btc_filter"] == published["records_with_btc_filter"] == 124416
    assert deviation["total_v2_records"] == published["total_v2_records"] == 497664
    assert deviation["misaligned_validation_folds"] == published["misaligned_validation_folds"]
    assert deviation["evidence_path"] == published["evidence_path"]
    assert deviation["carried_into_the_final_report"] is True
    assert deviation["not_repaired"] is True


def test_authorization_boundary_authorizes_nothing():
    protocol = _load(PROTOCOL_PATH)
    boundary = protocol["authorization_boundary"]
    assert boundary["authorizes_evaluation"] is False
    assert boundary["authorizes_candle_read_before_window_exists"] is False
    assert boundary["authorizes_window_benchmark_retrieval"] is False
    assert boundary["code_identity_rule"] == "canonical_digest"
    assert boundary["v1_paths_forbidden"] is True
    assert boundary["v2_paths_forbidden"] is True
    assert boundary["new_v3_paths_require_new_versioned_amendment"] is True
    assert boundary["confirmatory_execution_code_must_live_outside_the_hashed_set"] is True


def test_code_hash_constraint_records_canonical_and_authorized_digests():
    protocol = _load(PROTOCOL_PATH)
    authorization = _load(AUTHORIZATION_PATH)
    amendment = _load(CODE_HASH_AMENDMENT_PATH)
    constraint = protocol["code_hash_constraint"]
    assert constraint["canonical_source_digest"] == amendment["code_hash_constraint"]["canonical_source_digest"]
    assert constraint["authorized_code_hash"] == authorization["code_hash"]
    assert protocol["authorization_boundary"]["authorized_code_hash"] == authorization["code_hash"]
    assert constraint["hashed_set_root"] == HASHED_SET_ROOT
    for relative in constraint["inside_hashed_set_examples"]:
        assert verifier.path_is_inside_hashed_set(relative), relative
    for relative in constraint["outside_hashed_set_examples"]:
        assert not verifier.path_is_inside_hashed_set(relative), relative


def test_v1_artifacts_are_unchanged():
    for relative, digest in verifier.V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, relative


def test_related_artifacts_point_at_the_recorded_artifacts():
    protocol = _load(PROTOCOL_PATH)
    related = protocol["related_artifacts"]
    expected = {
        "selected_configurations_manifest": (MANIFEST_PATH, "manifest_hash"),
        "selection_authorization_1": (SELECTION_AUTH_PATH, "manifest_hash"),
        "v3_specification": (SPEC_V3_PATH, "specification_hash"),
        "v1_specification": (SPEC_V1_PATH, "specification_hash"),
        "v3_data_manifest_amendment_1": (DATA_AMENDMENT_PATH, "manifest_hash"),
        "v3_universe_manifest": (UNIVERSE_V3_PATH, "manifest_hash"),
        "v3_candidate_freeze": (FREEZE_PATH, "manifest_hash"),
        "v3_candidate_freeze_amendment_1": (FREEZE_AMENDMENT_1_PATH, "manifest_hash"),
        "v3_candidate_freeze_amendment_2": (FREEZE_AMENDMENT_2_PATH, "manifest_hash"),
        "v3_execution_protocol": (EXECUTION_PATH, "specification_hash"),
        "v3_execution_amendment_1": (EXECUTION_AMENDMENT_1_PATH, "manifest_hash"),
        "v3_execution_amendment_2": (EXECUTION_AMENDMENT_2_PATH, "manifest_hash"),
    }
    for key, (path, digest_key) in expected.items():
        document = _load(path)
        assert related[key]["path"] == str(path.relative_to(REPO_ROOT))
        assert related[key][digest_key] == document[digest_key]
    data_manifest = _load(DATA_V3_PATH)
    data_amendment = _load(DATA_AMENDMENT_PATH)
    assert related["v3_data_manifest"]["path"] == "research/data_manifest_v3.json"
    assert related["v3_data_manifest"]["manifest_hash"] == data_manifest["manifest_hash"]
    assert (
        related["v3_data_manifest"]["effective_manifest_hash"]
        == data_amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    )


def test_supersedes_the_selection_authorization():
    protocol = _load(PROTOCOL_PATH)
    selection_auth = _load(SELECTION_AUTH_PATH)
    supersedes = protocol["supersedes"]
    assert supersedes["selection_authorization_path"] == "configs/research_v3_selection_authorization_1.json"
    assert supersedes["selection_authorization_manifest_hash"] == selection_auth["manifest_hash"]
    assert supersedes["v1_holdout_never_reused"] is True
    assert supersedes["v2_confirmatory_window_never_read"] is True


def test_nothing_has_been_executed_under_this_protocol():
    protocol = _load(PROTOCOL_PATH)
    data_manifest = _load(DATA_V3_PATH)
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0
    assert _load(LEDGER_V3_PATH)["holdout_exposed_count"] == 0
    assert _load(CHECKPOINT_V3_PATH)["holdout_exposed_count"] == 0
    assert _load(DATA_V2_PATH)["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    for relative in verifier.V3_CONFIRMATORY_OUTPUT_PATHS:
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_tree_identity_checks_survive_a_perturbed_enumeration_order(tmp_path):
    root = _mirror_repo(tmp_path)
    report = verifier.verify(root)
    assert report["failures"] == []
    assert report["ok"] is True


def test_verifier_detects_a_tampered_evaluation_scope(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["evaluation_scope"]["in_scope_assets"] = 6

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("in-scope asset count does not match" in failure for failure in failures)


def test_verifier_detects_a_changed_configuration_id(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["evaluation_scope"]["in_scope_configurations"][0]["config_id"] = "cfg_0001"

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("in-scope configurations do not match" in failure for failure in failures)


def test_verifier_detects_a_widened_scope(tmp_path):
    root = _mirror_repo(tmp_path)
    manifest = _load(MANIFEST_PATH)
    manifest["selections"]["AAVEUSDT"]["selected"] = True
    manifest["selections"]["AAVEUSDT"]["config_id"] = "cfg_fake"
    _replace(root, "research/v3_selected_configurations_manifest.json", manifest)
    failures = _failures(root)
    assert any("in-scope asset count does not match" in failure for failure in failures)


def test_verifier_detects_a_second_decision_criterion(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["reporting_and_falsifiers"]["pass_criterion"] = (
            "the net result at baseline costs exceeds the buy-and-hold baseline"
        )

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("does not state exactly one confirmatory decision criterion" in failure for failure in failures)


def test_verifier_detects_a_tampered_promotion_rule(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["decision_rule"]["criteria"] = ["net_total_return > 0 at baseline costs (1x)"]

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("does not copy the v3 promotion-rule criteria verbatim" in failure for failure in failures)


def test_verifier_detects_a_confirmatory_window_that_requires_fewer_hours(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["window_definition"]["minimum_closed_hourly_candles"] = 720

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("does not require 2,160 closed hourly candles" in failure for failure in failures)


def test_verifier_detects_a_confirmatory_window_that_starts_before_the_freeze(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["window_definition"]["window_opens_utc"] = "2026-10-01T00:00:00Z"

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("window open does not match the frozen confirmatory start" in failure for failure in failures)


def test_verifier_detects_a_substitutable_window_benchmark(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["data_path"]["benchmark"]["development_benchmark_may_be_reused_as_the_window_benchmark"] = True

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("allows the development benchmark to be reused" in failure for failure in failures)


def test_verifier_detects_dropped_btc_configurations(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["data_path"]["benchmark"]["btc_configurations_dropped"] = True

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("BTC configurations are never dropped" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_protocol(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["authorization_boundary"]["authorizes_evaluation"] = True

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("authorizes_evaluation is not false" in failure for failure in failures)


def test_verifier_detects_a_manifest_hash_mismatch(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(protocol: Dict[str, Any]) -> None:
        protocol["manifest_hash"] = "0" * 64

    _tamper_protocol(root, mutate)
    failures = _failures(root)
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "config.py"
    original = target.read_text(encoding="utf-8")
    target.unlink()
    target.write_text(original + "\n# tampered\n", encoding="utf-8")
    failures = _failures(root)
    assert any("does not match the recorded canonical digest" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / "research" / "candidate_manifest.json").unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


def test_verifier_detects_confirmatory_exposure(tmp_path):
    root = _mirror_repo(tmp_path)
    ledger = _load(LEDGER_V3_PATH)
    ledger["holdout_exposed_count"] = 1
    _replace(root, "research/ledger_v3.json", ledger)
    failures = _failures(root)
    assert any("ledger records confirmatory-window exposure" in failure for failure in failures)


def test_verifier_detects_a_v3_confirmatory_output_path(tmp_path):
    root = _mirror_repo(tmp_path)
    output = root / "research" / "ledger_v3_confirmatory.json"
    output.write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("a v3 confirmatory output path exists" in failure for failure in failures)

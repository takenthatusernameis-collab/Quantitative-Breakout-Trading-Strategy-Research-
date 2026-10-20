#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v3 confirmatory-evaluation protocol.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks ``configs/research_v3_confirmatory_protocol.json``
against the artifacts it claims to preregister:

1. the manifest hash recomputes from the canonical content of the document with
   the digest-carrying key removed;
2. the evaluation scope is exactly the four published candidates of
   ``research/v3_selected_configurations_manifest.json`` -- with their
   configuration ids -- bound to that manifest's hash, the selection
   authorization's hash, the v3 specification hash, the effective and base v3
   data-manifest hashes and the v3 universe-manifest hash; the two assets
   without a candidate are named out of scope with their reasons;
3. the confirmatory window opens at the frozen start, needs at least 2,160
   closed hourly candles, is single-use, never overlaps the v1 holdout or the
   v2 confirmatory window, is never reused from v1 or v2, is never used for
   selection and is never ranked or re-tuned on; the earliest possible end
   recomputes from the window start;
4. the data path records a single retrieval after the readiness test, exposure
   counting, hashing against the v3 data-manifest scheme, and the window
   benchmark series: it is required, does not exist yet, may not be replaced by
   the development benchmark, is aligned by UTC candle close, is never
   forward-filled, fails closed when missing, short or misaligned, and never
   drops the 576 ``btc_ema_168`` configurations per asset;
5. the evaluation rule records the unchanged v1 metric, the unchanged cost
   scenarios and the prohibition on re-tuning, re-ranking or grid extension;
6. **exactly one** confirmatory decision criterion is stated anywhere in the
   document, it is the preregistered v3 promotion rule and it is copied
   verbatim from the immutable v3 specification;
7. the reporting block reports every evaluated asset and candidate, names the
   assets without a candidate, never discards a negative or inconclusive result
   and never re-opens the v1 holdout or the v2 confirmatory window; the v1/v2
   BTC-alignment deviation is carried as a disclosure and is not repaired;
8. the authorization boundary authorizes no evaluation, no window read and no
   benchmark retrieval, uses the canonical digest as the code-identity rule,
   forbids v1 and v2 paths and requires a new versioned amendment for new v3
   paths;
9. nothing has been executed under this protocol: no v3 confirmatory output
   path exists, the v3 confirmatory window is ``NOT_STARTED`` and
   ``holdout_exposed_count`` is 0 in the ledger, the checkpoint and the data
   manifest;
10. the v1 evidence is byte-identical and the v2 confirmatory window is still
    untouched;
11. the code-hash constraint names only paths that really are outside the
    hashed source set and records the authorized v1 code hash.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

PROTOCOL_RELATIVE = "configs/research_v3_confirmatory_protocol.json"

#: Keys that carry a confirmatory decision criterion. Exactly one such key may
#: exist in the whole document: the v2 line had to be amended after two frozen
#: artifacts stated different criteria, and the v3 protocol must not repeat it.
CRITERION_KEYS = (
    "criteria",
    "criterion",
    "promotion_criteria",
    "decision_criteria",
    "pass_criterion",
    "failure_criterion",
    "inconclusive_criterion",
    "baseline_comparison",
)

#: The paths a v3 confirmatory run would write. None of them may exist.
V3_CONFIRMATORY_OUTPUT_PATHS = (
    "research/shards_v3_confirmatory",
    "research/ledger_v3_confirmatory.json",
    "research/results_manifest_v3_confirmatory.json",
    "research/results_v3_confirmatory.jsonl",
    "research_state/checkpoint_v3_confirmatory.json",
)

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

HASHED_SET_ROOT = "src/breakout_research"

REQUIRED_ARTIFACTS = (
    "configs/research_v3_confirmatory_protocol.json",
    "research/v3_selected_configurations_manifest.json",
    "configs/research_v3_selection_authorization_1.json",
    "configs/research_v3.json",
    "configs/research_v1.json",
    "research/data_manifest_v3.json",
    "configs/research_v3_data_manifest_amendment_1.json",
    "research/universe_manifest_v3.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_candidate_freeze_amendment_1.json",
    "configs/research_v3_candidate_freeze_amendment_2.json",
    "configs/research_v3_execution.json",
    "configs/research_v3_execution_amendment_1.json",
    "configs/research_v3_execution_amendment_2.json",
    "research_state/campaign_authorization.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "research/ledger_v3.json",
    "research_state/checkpoint_v3.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def path_is_inside_hashed_set(relative: str) -> bool:
    root = HASHED_SET_ROOT.rstrip("/")
    candidate = relative.rstrip("/")
    return candidate == root or candidate.startswith(root + "/")


def parse_iso_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def format_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_criterion_keys(node: Any, path: str = "") -> List[str]:
    """Every path in the document that carries a confirmatory decision criterion."""
    found: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if key in CRITERION_KEYS:
                found.append(child)
            found.extend(collect_criterion_keys(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(collect_criterion_keys(value, f"{path}[{index}]"))
    return found


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    for relative in REQUIRED_ARTIFACTS:
        if not (root / relative).exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {relative}"],
            }

    protocol = _load(root / PROTOCOL_RELATIVE)
    manifest = _load(root / "research" / "v3_selected_configurations_manifest.json")
    selection_auth = _load(root / "configs" / "research_v3_selection_authorization_1.json")
    spec_v3 = _load(root / "configs" / "research_v3.json")
    spec_v1 = _load(root / "configs" / "research_v1.json")
    data_manifest = _load(root / "research" / "data_manifest_v3.json")
    data_amendment = _load(root / "configs" / "research_v3_data_manifest_amendment_1.json")
    universe = _load(root / "research" / "universe_manifest_v3.json")
    freeze = _load(root / "configs" / "research_v3_candidate_freeze.json")
    freeze_amendment_1 = _load(root / "configs" / "research_v3_candidate_freeze_amendment_1.json")
    freeze_amendment_2 = _load(root / "configs" / "research_v3_candidate_freeze_amendment_2.json")
    execution = _load(root / "configs" / "research_v3_execution.json")
    execution_amendment_1 = _load(root / "configs" / "research_v3_execution_amendment_1.json")
    execution_amendment_2 = _load(root / "configs" / "research_v3_execution_amendment_2.json")
    authorization = _load(root / "research_state" / "campaign_authorization.json")
    code_hash_amendment = _load(root / "configs" / "research_v2_code_hash_amendment_1.json")
    ledger = _load(root / "research" / "ledger_v3.json")
    checkpoint = _load(root / "research_state" / "checkpoint_v3.json")
    effective_data = data_amendment.get("effective_data_manifest") or {}

    # 1. Self hash.
    excluded = tuple(protocol.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the protocol does not declare its manifest_hash_excluded_keys")
    declared = protocol.get("manifest_hash")
    recomputed = compute_manifest_hash(protocol, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. Evaluation scope is exactly the four published candidates.
    scope = protocol.get("evaluation_scope") or {}
    if scope.get("selected_configurations_manifest") != "research/v3_selected_configurations_manifest.json":
        failures.append("the evaluation scope does not name the selected-configurations manifest")
    if scope.get("selected_configurations_manifest_hash") != manifest.get("manifest_hash"):
        failures.append("the scope is not bound to the selected-configurations manifest hash")
    if scope.get("selection_authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("the scope is not bound to the selection authorization manifest hash")
    if scope.get("v3_specification_hash") != spec_v3.get("specification_hash"):
        failures.append("the scope is not bound to the v3 specification hash")
    if scope.get("v3_data_manifest_hash") != effective_data.get("effective_data_manifest_hash"):
        failures.append("the scope is not bound to the effective v3 data-manifest hash")
    if scope.get("v3_base_data_manifest_hash") != effective_data.get("base_manifest_hash"):
        failures.append("the scope is not bound to the base v3 data-manifest hash")
    if scope.get("v3_base_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("the scope is not bound to the v3 data manifest's own manifest hash")
    if scope.get("v3_universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("the scope is not bound to the v3 universe manifest hash")
    selections = manifest.get("selections") or {}
    expected_in_scope = [
        {
            "asset": asset,
            "config_id": entry.get("config_id"),
            "candidate_status": entry.get("candidate_status"),
        }
        for asset, entry in sorted(selections.items())
        if entry.get("selected") is True
    ]
    expected_out_of_scope = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    if scope.get("in_scope_assets") != len(expected_in_scope):
        failures.append("the in-scope asset count does not match the selected-configurations manifest")
    if scope.get("in_scope_configurations") != expected_in_scope:
        failures.append(
            "the in-scope configurations do not match the published candidates and their "
            "configuration ids"
        )
    if scope.get("out_of_scope_assets_without_candidate") != expected_out_of_scope:
        failures.append("the out-of-scope assets do not match the manifest's assets without a candidate")
    expected_reasons = {
        asset: (selections[asset].get("reason") or selections[asset].get("status"))
        for asset in expected_out_of_scope
    }
    if scope.get("out_of_scope_reasons") != expected_reasons:
        failures.append("the out-of-scope reasons do not match the published manifest")
    if scope.get("excluded_assets_stay_excluded") is not True:
        failures.append("the scope does not record that the excluded assets stay excluded")
    if scope.get("scope_may_not_be_widened_narrowed_or_reranked") is not True:
        failures.append("the scope does not forbid widening, narrowing or re-ranking")

    # 3. Window definition.
    window = protocol.get("window_definition") or {}
    boundary = freeze.get("data_boundary") or {}
    if window.get("window_opens_utc") != boundary.get("confirmatory_window_start_utc"):
        failures.append("the window open does not match the frozen confirmatory start")
    if window.get("minimum_closed_hourly_candles") != 2160:
        failures.append("the confirmatory window does not require 2,160 closed hourly candles")
    if window.get("minimum_closed_hourly_candles") != boundary.get("min_confirmatory_window_hours"):
        failures.append("the confirmatory window does not require the frozen number of hours")
    recomputed_end = format_iso_utc(
        parse_iso_utc(str(window.get("window_opens_utc")))
        + timedelta(hours=int(window.get("minimum_closed_hourly_candles") or 0))
    )
    if window.get("earliest_possible_end_utc") != recomputed_end:
        failures.append(
            "the earliest possible window end does not follow from the window start and the "
            "minimum length"
        )
    if window.get("earliest_possible_end_utc") != boundary.get(
        "earliest_possible_confirmatory_window_end_utc"
    ):
        failures.append("the earliest possible window end does not match the frozen boundary")
    for name, amendment in (
        ("freeze amendment 1", freeze_amendment_1),
        ("freeze amendment 2", freeze_amendment_2),
    ):
        amended = amendment.get("data_boundary") or {}
        if amended.get("confirmatory_window_start_utc") != window.get("window_opens_utc"):
            failures.append(f"the {name} moves the confirmatory window away from the frozen start")
    if window.get("single_use") is not True:
        failures.append("the confirmatory window is not marked single-use")
    if window.get("must_not_overlap_v1_holdout") is not True:
        failures.append("the confirmatory window does not forbid v1 holdout overlap")
    if window.get("must_not_overlap_v2_confirmatory_window") is not True:
        failures.append("the confirmatory window does not forbid v2 confirmatory-window overlap")
    if window.get("never_reused_from_v1") is not True:
        failures.append("the confirmatory window does not forbid reuse from v1")
    if window.get("never_reused_from_v2") is not True:
        failures.append("the confirmatory window does not forbid reuse from v2")
    if window.get("never_used_for_candidate_selection") is not True:
        failures.append("the confirmatory window does not forbid use for candidate selection")
    if window.get("no_ranking_or_retuning_on_window") is not True:
        failures.append("the confirmatory window does not forbid ranking or re-tuning on it")
    if window.get("never_populated_with_data_predating_the_candidate_freeze") is not True:
        failures.append("the confirmatory window does not forbid data predating the candidate freeze")
    if window.get("window_moved_by_the_candidate_freeze_amendments") is not False:
        failures.append("the protocol does not record that the freeze amendments did not move the window")

    # 4. Data path, including the window benchmark.
    data_path = protocol.get("data_path") or {}
    if data_path.get("retrieval_happens_once_after_readiness_test_passes") is not True:
        failures.append("the data path does not require a single retrieval after the readiness test")
    if data_path.get("every_read_counted_in_holdout_exposed_count") is not True:
        failures.append("the data path does not require every read to be counted in holdout_exposed_count")
    if data_path.get("hashed_and_verified_against_v3_data_manifest_scheme") is not True:
        failures.append("the data path does not require hashing and verification against the v3 data manifest scheme")
    if data_path.get("data_manifest_hash") != effective_data.get("effective_data_manifest_hash"):
        failures.append("the data path is not bound to the effective v3 data-manifest hash")
    if data_path.get("base_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("the data path is not bound to the v3 data manifest's own manifest hash")
    if data_path.get("universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("the data path is not bound to the v3 universe manifest hash")
    if data_path.get("confirmatory_window_start_utc") != window.get("window_opens_utc"):
        failures.append("the data path does not start at the confirmatory window start")
    readiness = data_path.get("readiness_test") or {}
    if readiness.get("must_pass_before_any_window_read") is not True:
        failures.append("the data path does not require the readiness test to pass before a window read")
    if not isinstance(readiness.get("checks"), list) or not readiness.get("checks"):
        failures.append("the readiness test records no checks")

    auth_benchmark = (selection_auth.get("authorized_run") or {}).get("benchmark") or {}
    benchmark = data_path.get("benchmark") or {}
    if benchmark.get("symbol") != auth_benchmark.get("symbol"):
        failures.append("the benchmark symbol does not match the selection authorization")
    if benchmark.get("role") != auth_benchmark.get("role"):
        failures.append("the benchmark role does not match the selection authorization")
    if benchmark.get("benchmark_is_not_a_candidate") is not True:
        failures.append("the benchmark is not recorded as outside the candidate scope")
    if benchmark.get("window_benchmark_series_required") is not True:
        failures.append("the protocol does not require a benchmark series for the window")
    if benchmark.get("window_benchmark_series_exists_yet") is not False:
        failures.append("the protocol does not record that the window benchmark series does not exist yet")
    if benchmark.get("development_benchmark_content_hash") != auth_benchmark.get("content_hash"):
        failures.append("the development benchmark content hash does not match the selection authorization")
    if benchmark.get("development_benchmark_covers_the_window") is not False:
        failures.append("the protocol does not record that the development benchmark does not cover the window")
    if benchmark.get("development_benchmark_may_be_reused_as_the_window_benchmark") is not False:
        failures.append("the protocol allows the development benchmark to be reused as the window benchmark")
    if benchmark.get("window_benchmark_retrieval_happens_once") is not True:
        failures.append("the window benchmark retrieval is not required to happen once")
    if benchmark.get("window_benchmark_is_hash_verified") is not True:
        failures.append("the window benchmark is not required to be hash-verified")
    if benchmark.get("alignment_rule") != auth_benchmark.get("alignment_rule"):
        failures.append("the benchmark alignment rule does not match the selection authorization")
    if benchmark.get("methodology_rule") != auth_benchmark.get("methodology_rule"):
        failures.append("the benchmark methodology rule does not match the selection authorization")
    if benchmark.get("methodology_reference") != auth_benchmark.get("methodology_reference"):
        failures.append("the benchmark methodology reference does not match the selection authorization")
    if benchmark.get("no_forward_fill") is not True:
        failures.append("the benchmark rule does not forbid forward filling")
    if list(benchmark.get("fail_closed") or []) != list(auth_benchmark.get("fail_closed") or []):
        failures.append("the benchmark fail-closed conditions do not match the selection authorization")
    if benchmark.get("grid_rule") != auth_benchmark.get("grid_rule"):
        failures.append("the benchmark grid rule does not match the selection authorization")
    if benchmark.get("btc_configurations_dropped") is not False:
        failures.append("the protocol does not record that the BTC configurations are never dropped")

    # 5. Evaluation rule.
    evaluation_rule = protocol.get("evaluation_rule") or {}
    if evaluation_rule.get("unchanged_v1_evaluation_metric") is not True:
        failures.append("the evaluation rule does not record the unchanged v1 evaluation metric")
    if evaluation_rule.get("unchanged_cost_scenarios") is not True:
        failures.append("the evaluation rule does not record the unchanged cost scenarios")
    if evaluation_rule.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        failures.append("the evaluation rule does not prohibit re-tuning, re-ranking or grid extension on the window")
    if evaluation_rule.get("selection_rule_reference") != "configs/research_v1.json#selection":
        failures.append("the evaluation rule does not reference the unchanged v1 selection block")
    if [float(value) for value in (evaluation_rule.get("cost_scenarios") or [])] != [
        float(value) for value in spec_v1["costs"]["scenarios"]
    ]:
        failures.append("the cost scenarios do not match the unchanged v1 cost scenarios")
    if spec_v3.get("selection") != spec_v1.get("selection"):
        failures.append("the v3 specification no longer inherits the v1 selection block unchanged")

    # 6. Exactly one confirmatory decision criterion.
    criterion_paths = collect_criterion_keys(protocol)
    if len(criterion_paths) != 1:
        failures.append(
            "the protocol does not state exactly one confirmatory decision criterion: "
            f"{criterion_paths}"
        )
    decision = protocol.get("decision_rule") or {}
    promotion = (spec_v3.get("holdout") or {}).get("promotion_rule") or {}
    if decision.get("criterion_count") != 1:
        failures.append("the decision rule does not record exactly one criterion")
    if decision.get("authoritative_source") != "configs/research_v3.json#holdout.promotion_rule":
        failures.append("the decision rule does not name the v3 promotion rule as the authoritative source")
    if list(decision.get("criteria") or []) != list(promotion.get("criteria") or []):
        failures.append("the decision rule does not copy the v3 promotion-rule criteria verbatim")
    if list(decision.get("status_vocabulary") or []) != list(promotion.get("status_vocabulary") or []):
        failures.append("the decision rule does not copy the v3 status vocabulary verbatim")
    if decision.get("exactly_one_criterion") is not True:
        failures.append("the decision rule does not record that exactly one criterion applies")
    if decision.get("no_competing_criterion") is not True:
        failures.append("the decision rule does not record that no competing criterion applies")
    verdicts = decision.get("verdicts") or {}
    if verdicts.get("status_vocabulary_is_not_extended") is not True:
        failures.append("the decision rule does not forbid extending the status vocabulary")
    for status_key in ("survival_status", "rejected_status", "inconclusive_status"):
        if verdicts.get(status_key) not in (promotion.get("status_vocabulary") or []):
            failures.append(f"the decision rule states a status outside the preregistered vocabulary: {status_key}")

    # 7. Reporting, falsifiers and the carried deviation.
    reporting = protocol.get("reporting_and_falsifiers") or {}
    if reporting.get("every_evaluated_asset_and_candidate_reported") is not True:
        failures.append("the reporting block does not require every evaluated asset and candidate to be reported")
    if reporting.get("assets_without_a_candidate_are_named") is not True:
        failures.append("the reporting block does not require the assets without a candidate to be named")
    if reporting.get("null_result_reported") is not True:
        failures.append("the reporting block does not require a null result to be reported")
    if reporting.get("negative_and_inconclusive_results_are_never_discarded") is not True:
        failures.append("the reporting block does not forbid discarding negative or inconclusive results")
    if reporting.get("v1_holdout_never_reopened") is not True:
        failures.append("the reporting block does not forbid re-opening the v1 holdout")
    if reporting.get("v2_confirmatory_window_never_read") is not True:
        failures.append("the reporting block does not forbid reading the v2 confirmatory window")
    expected_fields = list(
        (spec_v3.get("holdout") or {}).get("v3_holdout_report_required_fields") or []
    )
    if list(reporting.get("holdout_report_required_fields") or []) != expected_fields:
        failures.append("the reporting block does not copy the v3 holdout-report fields verbatim")
    falsifiers = reporting.get("falsifiers") or []
    if not isinstance(falsifiers, list) or len(falsifiers) == 0:
        failures.append("the reporting block does not record any falsifiers")
    deviation = protocol.get("deviation_disclosure") or {}
    published_deviation = manifest.get("deviation_disclosure") or {}
    if deviation.get("records_with_btc_filter") != published_deviation.get("records_with_btc_filter"):
        failures.append("the deviation disclosure does not carry the published record count")
    if deviation.get("total_v2_records") != published_deviation.get("total_v2_records"):
        failures.append("the deviation disclosure does not carry the published total record count")
    if list(deviation.get("misaligned_validation_folds") or []) != list(
        published_deviation.get("misaligned_validation_folds") or []
    ):
        failures.append("the deviation disclosure does not carry the published fold list")
    if deviation.get("evidence_path") != published_deviation.get("evidence_path"):
        failures.append("the deviation disclosure does not name the published evidence")
    if deviation.get("carried_into_the_final_report") is not True:
        failures.append("the deviation is not carried into the final report")
    if deviation.get("not_repaired") is not True:
        failures.append("the deviation is not recorded as unrepaired")

    # 8. Authorization boundary authorizes nothing.
    boundary = protocol.get("authorization_boundary") or {}
    if boundary.get("authorizes_evaluation") is not False:
        failures.append("authorization_boundary.authorizes_evaluation is not false")
    if boundary.get("authorizes_candle_read_before_window_exists") is not False:
        failures.append("authorization_boundary.authorizes_candle_read_before_window_exists is not false")
    if boundary.get("authorizes_window_benchmark_retrieval") is not False:
        failures.append("authorization_boundary.authorizes_window_benchmark_retrieval is not false")
    if boundary.get("code_identity_rule") != "canonical_digest":
        failures.append("the authorization boundary does not use the canonical digest as the code-identity rule")
    if boundary.get("v1_paths_forbidden") is not True:
        failures.append("the authorization boundary does not forbid v1 paths")
    if boundary.get("v2_paths_forbidden") is not True:
        failures.append("the authorization boundary does not forbid v2 paths")
    if boundary.get("new_v3_paths_require_new_versioned_amendment") is not True:
        failures.append("the authorization boundary does not require a new versioned amendment for new v3 paths")
    if boundary.get("confirmatory_execution_code_must_live_outside_the_hashed_set") is not True:
        failures.append("the authorization boundary does not require the confirmatory code to live outside the hashed set")
    if boundary.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the authorization boundary does not name the hashed source root")

    # 9. Code-hash constraint.
    constraint = protocol.get("code_hash_constraint") or {}
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_canonical = canonical_source_digest(root)
    if constraint.get("canonical_source_digest") != recorded_canonical:
        failures.append("the code-hash constraint does not record the canonical source digest")
    if recorded_canonical != live_canonical:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}"
        )
    authorized_code_hash = authorization.get("code_hash")
    if constraint.get("authorized_code_hash") != authorized_code_hash:
        failures.append("the code-hash constraint does not record the authorized v1 code hash")
    if boundary.get("authorized_code_hash") != authorized_code_hash:
        failures.append("the authorization boundary does not record the authorized v1 code hash")
    if constraint.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the code-hash constraint does not name the hashed source root")
    for relative in constraint.get("inside_hashed_set_examples") or []:
        if not path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as inside the hashed set but is not")
    for relative in constraint.get("outside_hashed_set_examples") or []:
        if path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as outside the hashed set but is inside it")

    # 10. Nothing has been executed under this protocol.
    for relative in V3_CONFIRMATORY_OUTPUT_PATHS:
        if (root / relative).exists():
            failures.append(f"a v3 confirmatory output path exists: {relative}")
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not marked NOT_STARTED")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("the v3 data manifest records confirmatory-window exposure")
    if ledger.get("holdout_exposed_count") != 0:
        failures.append("the v3 ledger records confirmatory-window exposure")
    if checkpoint.get("holdout_exposed_count") != 0:
        failures.append("the v3 checkpoint records confirmatory-window exposure")
    if ledger.get("status") != "COMPLETED":
        failures.append("the v3 selection ledger is not COMPLETED")
    if ledger.get("run_id") != (manifest.get("run_identity") or {}).get("run_id"):
        failures.append("the v3 ledger does not record the run that produced the published manifest")

    # 11. The v1 evidence is byte-identical and the v2 window is untouched.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    v2_window = (_load(root / "research" / "data_manifest_v2.json").get("confirmatory_window") or {})
    if v2_window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is no longer NOT_STARTED")
    if v2_window.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")

    # 12. The related artifacts are the ones that are recorded.
    related = protocol.get("related_artifacts") or {}
    expected_related = {
        "selected_configurations_manifest": (
            "research/v3_selected_configurations_manifest.json",
            manifest.get("manifest_hash"),
        ),
        "selection_authorization_1": (
            "configs/research_v3_selection_authorization_1.json",
            selection_auth.get("manifest_hash"),
        ),
        "v3_specification": (
            "configs/research_v3.json",
            spec_v3.get("specification_hash"),
        ),
        "v1_specification": (
            "configs/research_v1.json",
            spec_v1.get("specification_hash"),
        ),
        "v3_universe_manifest": (
            "research/universe_manifest_v3.json",
            universe.get("manifest_hash"),
        ),
        "v3_candidate_freeze": (
            "configs/research_v3_candidate_freeze.json",
            freeze.get("manifest_hash"),
        ),
        "v3_candidate_freeze_amendment_1": (
            "configs/research_v3_candidate_freeze_amendment_1.json",
            freeze_amendment_1.get("manifest_hash"),
        ),
        "v3_candidate_freeze_amendment_2": (
            "configs/research_v3_candidate_freeze_amendment_2.json",
            freeze_amendment_2.get("manifest_hash"),
        ),
        "v3_execution_protocol": (
            "configs/research_v3_execution.json",
            execution.get("specification_hash"),
        ),
        "v3_execution_amendment_1": (
            "configs/research_v3_execution_amendment_1.json",
            execution_amendment_1.get("manifest_hash"),
        ),
        "v3_execution_amendment_2": (
            "configs/research_v3_execution_amendment_2.json",
            execution_amendment_2.get("manifest_hash"),
        ),
    }
    for key, (relative, digest) in expected_related.items():
        entry = related.get(key) or {}
        if entry.get("path") != relative:
            failures.append(f"related_artifacts.{key} does not point at {relative}")
        if entry.get("manifest_hash", entry.get("specification_hash")) != digest:
            failures.append(f"related_artifacts.{key} records a hash that does not match {relative}")
    data_entry = related.get("v3_data_manifest") or {}
    if data_entry.get("path") != "research/data_manifest_v3.json":
        failures.append("related_artifacts.v3_data_manifest does not point at the v3 data manifest")
    if data_entry.get("manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("related_artifacts.v3_data_manifest records a stale base manifest hash")
    if data_entry.get("effective_manifest_hash") != effective_data.get("effective_data_manifest_hash"):
        failures.append("related_artifacts.v3_data_manifest records a stale effective manifest hash")
    amendment_entry = related.get("v3_data_manifest_amendment_1") or {}
    if amendment_entry.get("path") != "configs/research_v3_data_manifest_amendment_1.json":
        failures.append("related_artifacts.v3_data_manifest_amendment_1 does not point at the amendment")
    if amendment_entry.get("manifest_hash") != data_amendment.get("manifest_hash"):
        failures.append("related_artifacts.v3_data_manifest_amendment_1 records a stale hash")

    # 13. Supersession of the selection authorization.
    supersedes = protocol.get("supersedes") or {}
    if supersedes.get("selection_authorization_path") != "configs/research_v3_selection_authorization_1.json":
        failures.append("the supersedes block does not name the selection authorization")
    if supersedes.get("selection_authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("the superseded selection authorization hash does not match")
    if supersedes.get("v1_holdout_never_reused") is not True:
        failures.append("the supersession block does not record that the v1 holdout is never reused")
    if supersedes.get("v2_confirmatory_window_never_read") is not True:
        failures.append("the supersession block does not record that the v2 confirmatory window is never read")

    return {
        "ok": not failures,
        "protocol_path": PROTOCOL_RELATIVE,
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "protocol_status": protocol.get("protocol_status"),
        "in_scope_assets": scope.get("in_scope_assets"),
        "in_scope_configurations": scope.get("in_scope_configurations"),
        "out_of_scope_assets": scope.get("out_of_scope_assets_without_candidate"),
        "window_opens_utc": window.get("window_opens_utc"),
        "minimum_closed_hourly_candles": window.get("minimum_closed_hourly_candles"),
        "earliest_possible_end_utc": window.get("earliest_possible_end_utc"),
        "criterion_paths": criterion_paths,
        "canonical_source_digest": live_canonical,
        "authorized_code_hash": authorized_code_hash,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

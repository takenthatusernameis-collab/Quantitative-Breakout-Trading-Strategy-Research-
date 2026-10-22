#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v6 confirmatory protocol.

``configs/research_v6_confirmatory_protocol.json`` preregisters how the single
v6 confirmatory evaluation will be performed once the v6 confirmatory window
exists. The verifier never writes to the repository, never contacts a
provider, never reads a candle and never runs an evaluation. It checks:

1. the protocol is self-hashing, is the v6 confirmatory protocol and is bound
   to the v6 specification;
2. the **scope** is re-derived from the v6 candidate freeze and the v6 universe
   manifest: the in-scope assets are the validated members of the frozen band,
   the excluded members keep their exclusion reasons, and the scope may not be
   widened, narrowed or re-ranked;
3. the **window** is re-derived from the freeze: its start, its minimum hours,
   its earliest end and the evaluation gate (the later of the four earlier
   gates and the v6 window's own earliest end), single-use, never reused and
   never read for selection;
4. the **data path** binds the benchmark dataset by its recomputed content
   hash, records that the window benchmark series does not exist yet, and
   states the readiness test that must pass before any window read;
5. the **evaluation rule** and the **decision rule** are the unchanged v1
   rules: the inherited blocks digest is recomputed from
   ``configs/research_v1.json``, the grid still enumerates 2,304
   combinations, the single criterion is re-derived from the v1 selection
   block and the status vocabulary is the v1 status vocabulary;
6. the reporting and falsifier blocks are complete and the deviation
   disclosure is carried into the final report;
7. the **authorization boundary** authorizes nothing and the code identity is
   the canonical tree digest, recomputed;
8. the ``related_artifacts`` block names only artifacts that exist, each with
   its recomputed identity;
9. no v6 confirmatory artifact exists: the window has not been read and no
   evaluation has been run.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs. The verifier is
**clock-free**: every expectation is a property of the frozen artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    canonical_source_digest,
    compute_manifest_hash,
    published_manifest_hash,
    read_json,
    sha256_file,
)

PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"

#: The freezes that own the v2, v3, v4 and v5 confirmatory windows, and the
#: key each one keeps its window bounds under.
GATE_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The v1 blocks the v6 chain inherits unchanged.
INHERITED_V1_BLOCKS: Tuple[str, ...] = (
    "strategy_grid",
    "costs",
    "execution",
    "folds",
    "selection",
    "pilot",
    "metrics",
    "baselines",
    "fixed_breakout_baseline",
    "status",
    "checkpointing",
)

#: The v6 confirmatory artifacts a run creates. Before the authorized run none
#: of them may exist.
V6_CONFIRMATORY_RUN_ARTIFACTS: Tuple[str, ...] = (
    "research/v6_confirmatory_window_manifest.json",
    "research/shards_v6_confirmatory",
    "research/results_v6_confirmatory.jsonl",
    "research/ledger_v6_confirmatory.json",
    "research/results_manifest_v6_confirmatory.json",
    "research_state/checkpoint_v6_confirmatory.json",
    "configs/research_v6_confirmatory_authorization_1.json",
)

#: The readiness-test clauses the protocol must state.
REQUIRED_READINESS_CHECKS: Tuple[str, ...] = (
    "the v6 confirmatory window holds at least 2160 closed hourly candles",
    "the v6 candidate freeze is committed and hash-bound",
    "this protocol is committed",
    "the v6 selected-configuration manifest is committed and hash-bound",
    "a confirmatory evaluation authorization exists and is bound to this protocol's manifest_hash",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _window_bounds(owner: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = owner.get(key) or {}
    start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
    min_hours = block.get("min_confirmatory_window_hours")
    if min_hours is None:
        min_hours = block.get("min_hours")
    end = block.get("earliest_possible_confirmatory_window_end_utc")
    if end is None:
        end = block.get("earliest_possible_end_utc")
    return {
        "window_start_utc": str(start) if start else None,
        "min_hours": int(min_hours) if min_hours is not None else None,
        "earliest_possible_end_utc": str(end) if end else None,
    }


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    computed: Dict[str, Any] = {}
    root = Path(repo_root)

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        PROTOCOL_RELATIVE,
        SPEC_V1_RELATIVE,
        SPEC_V6_RELATIVE,
        FREEZE_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
        EXECUTION_RELATIVE,
        AUTHORIZATION_RELATIVE,
    ):
        if not (root / relative).exists():
            return {
                "ok": False,
                "protocol_path": PROTOCOL_RELATIVE,
                "failures": [f"missing artifact: {relative}"],
            }

    protocol = read_json(root / PROTOCOL_RELATIVE)
    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    execution = read_json(root / EXECUTION_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # 1. the document itself ------------------------------------------------
    excluded = tuple(
        (protocol.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    protocol_hash = compute_manifest_hash(protocol, excluded)
    computed["manifest_hash"] = protocol.get("manifest_hash")
    computed["recomputed_manifest_hash"] = protocol_hash
    if protocol.get("manifest_hash") != protocol_hash:
        fail(
            f"manifest_hash mismatch: declared {protocol.get('manifest_hash')}, "
            f"recomputed {protocol_hash}"
        )
    if protocol.get("artifact") != "v6_confirmatory_protocol":
        fail("the protocol is not the v6 confirmatory protocol")
    if protocol.get("universe_version") != "v6" or protocol.get("protocol_version") != "v6":
        fail("the protocol is not a v6 artifact")
    if protocol.get("protocol_status") != "PREREGISTERED_NO_EVALUATION":
        fail("the protocol does not record that no evaluation has been preregistered as run")
    if "authorizes no evaluation" not in str(protocol.get("specification_purpose") or ""):
        fail("the protocol does not state that it authorizes no evaluation")

    # 2. the evaluation scope ------------------------------------------------
    scope = protocol.get("evaluation_scope") or {}
    members = list((freeze.get("band") or {}).get("members") or [])
    in_scope = [entry for entry in members if entry.get("validated") is True]
    excluded_members = [entry for entry in members if entry.get("validated") is not True]
    manifest_validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(str(entry["binance_pair"]) for entry in in_scope) != manifest_validated:
        fail("the frozen v6 candidate set is not the validated v6 universe")
    if list(scope.get("in_scope_assets_list") or []) != [
        str(entry["binance_pair"]) for entry in in_scope
    ]:
        fail("the in-scope assets are not the validated members of the frozen band")
    if scope.get("in_scope_assets") != len(in_scope):
        fail("the protocol miscounts the in-scope assets")
    computed["in_scope_assets"] = len(in_scope)
    if list(scope.get("out_of_scope_assets_excluded_at_validation") or []) != [
        str(entry["binance_pair"]) for entry in excluded_members
    ]:
        fail("the out-of-scope assets are not the excluded members of the frozen band")
    recorded_reasons = scope.get("out_of_scope_reasons") or {}
    for entry in excluded_members:
        pair = str(entry["binance_pair"])
        if recorded_reasons.get(pair) != entry.get("exclusion_reason"):
            fail(f"the protocol records another exclusion reason for {pair}")
    for pair in recorded_reasons:
        if pair not in {str(entry["binance_pair"]) for entry in excluded_members}:
            fail(f"the protocol names {pair}, which is not an excluded band member")
    if scope.get("excluded_assets_stay_excluded") is not True:
        fail("the protocol does not keep excluded assets excluded")
    if scope.get("scope_may_not_be_widened_narrowed_or_reranked") is not True:
        fail("the protocol does not forbid widening, narrowing or re-ranking the scope")
    if scope.get("frozen_candidate_set_hash") != freeze.get("manifest_hash"):
        fail("the scope is not bound to the v6 candidate freeze")
    if scope.get("v6_universe_manifest_hash") != universe.get("manifest_hash"):
        fail("the scope is not bound to the v6 universe manifest")
    if scope.get("v6_data_manifest_hash") != data.get("manifest_hash"):
        fail("the scope is not bound to the v6 data manifest")
    if scope.get("v6_specification_hash") != spec_v6.get("specification_hash"):
        fail("the scope is not bound to the v6 specification")
    if scope.get("selected_configurations_manifest_hash") is not None:
        fail("the protocol claims a selected-configurations manifest that does not exist yet")
    if scope.get("selected_configurations_manifest_status") != "NOT_YET_PUBLISHED":
        fail("the protocol does not record the selected-configurations manifest as unpublished")
    if scope.get("selection_authorization_path") != SELECTION_AUTHORIZATION_RELATIVE:
        fail("the protocol does not name the v6 selection authorization")
    # The selection authorization is bound by the hash recomputed from the
    # artifact's own bytes. A published authorization must be bound by that
    # hash; an unpublished one must not be bound at all.
    selection_authorization_hash = published_manifest_hash(root, SELECTION_AUTHORIZATION_RELATIVE)
    computed["selection_authorization_manifest_hash"] = selection_authorization_hash
    if selection_authorization_hash is None:
        if scope.get("selection_authorization_manifest_hash") is not None:
            fail("the protocol claims a selection authorization that does not exist")
    else:
        if scope.get("selection_authorization_manifest_hash") != selection_authorization_hash:
            fail("the protocol does not bind the live v6 selection authorization hash")

    # 3. the window ----------------------------------------------------------
    window_block = protocol.get("window_definition") or {}
    window = freeze.get("confirmatory_window") or {}
    if window_block.get("window_opens_utc") != window.get("opens_utc"):
        fail("the protocol names another confirmatory-window start than the freeze")
    if window_block.get("minimum_closed_hourly_candles") != window.get("min_hours"):
        fail("the protocol names another minimum of hours than the freeze")
    if window_block.get("earliest_possible_end_utc") != window.get("earliest_possible_end_utc"):
        fail("the protocol names another earliest window end than the freeze")
    if window_block.get("window_source") != f"{FREEZE_RELATIVE}#confirmatory_window":
        fail("the protocol does not name the freeze as the owner of the window")
    for flag in (
        "single_use",
        "must_not_overlap_v1_holdout",
        "must_not_overlap_v2_confirmatory_window",
        "must_not_overlap_v3_confirmatory_window",
        "must_not_overlap_v4_confirmatory_window",
        "must_not_overlap_v5_confirmatory_window",
        "never_reused_from_v1",
        "never_reused_from_v2",
        "never_reused_from_v3",
        "never_reused_from_v4",
        "never_reused_from_v5",
        "never_used_for_candidate_selection",
        "no_ranking_or_retuning_on_window",
        "never_populated_with_data_predating_the_candidate_freeze",
    ):
        if window_block.get(flag) is not True:
            fail(f"the protocol does not record {flag}")
    if window_block.get("window_moved_by_the_candidate_freeze_amendments") is not False:
        fail("the protocol claims the window was moved by an amendment")
    membership = (spec_v6.get("holdout") or {}).get("confirmatory_window_membership") or {}
    if window_block.get("membership_rule") != str(membership.get("rule") or ""):
        fail("the protocol does not bind the membership rule the v6 specification owns")
    # The evaluation gate is the later of the four earlier gates and the v6
    # window's own earliest end.
    gates: List[Tuple[str, str]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = _window_bounds(owner, key)
        if not bounds["earliest_possible_end_utc"]:
            fail(f"the {version} candidate freeze carries no earliest window end")
            continue
        gates.append((version, bounds["earliest_possible_end_utc"]))
    if window.get("earliest_possible_end_utc"):
        gates.append(("v6", str(window["earliest_possible_end_utc"])))
    if gates:
        expected_gate = max(end for _, end in gates)
        computed["evaluation_may_not_start_before_utc"] = expected_gate
        if window_block.get("evaluation_may_not_start_before_utc") != expected_gate:
            fail(
                "the effective v6 evaluation start is "
                f"{window_block.get('evaluation_may_not_start_before_utc')}, but the later of the "
                f"v2, v3, v4 and v5 gates and the v6 window's own earliest end is {expected_gate}"
            )

    # 4. the data path -------------------------------------------------------
    data_path = protocol.get("data_path") or {}
    benchmark = data_path.get("benchmark") or {}
    dataset_relative = str(benchmark.get("development_benchmark_dataset_path") or "")
    if not dataset_relative:
        fail("the protocol names no development benchmark dataset")
    else:
        dataset = root / dataset_relative
        if not dataset.exists():
            fail(f"the development benchmark dataset {dataset_relative} does not exist")
        else:
            live = sha256_file(dataset)
            if benchmark.get("development_benchmark_content_hash") != live:
                fail(
                    "the development benchmark content hash does not match the dataset: "
                    f"{benchmark.get('development_benchmark_content_hash')} != {live}"
                )
    manifest_benchmark = (data.get("benchmark") or {}).get("dataset_path")
    if dataset_relative != manifest_benchmark:
        fail("the protocol binds a benchmark dataset other than the v6 data manifest's")
    if benchmark.get("window_benchmark_series_exists_yet") is not False:
        fail("the protocol claims the window benchmark series already exists")
    if benchmark.get("window_benchmark_series_required") is not True:
        fail("the protocol does not require the window benchmark series")
    if benchmark.get("development_benchmark_covers_the_window") is not False:
        fail("the protocol claims the development benchmark covers the window")
    if benchmark.get("development_benchmark_may_be_reused_as_the_window_benchmark") is not False:
        fail("the protocol allows the development benchmark to be reused as the window benchmark")
    if benchmark.get("no_forward_fill") is not True:
        fail("the protocol does not forbid forward-filling the benchmark")
    if not benchmark.get("fail_closed"):
        fail("the protocol records no fail-closed condition")
    if "576" not in str(benchmark.get("grid_rule") or ""):
        fail("the protocol does not record the unchanged grid rule")
    readiness = data_path.get("readiness_test") or {}
    if readiness.get("must_pass_before_any_window_read") is not True:
        fail("the protocol does not require the readiness test before any window read")
    checks = list(readiness.get("checks") or [])
    for required in REQUIRED_READINESS_CHECKS:
        if required not in checks:
            fail(f"the readiness test does not state {required!r}")
    if data_path.get("every_read_counted_in_holdout_exposed_count") is not True:
        fail("the protocol does not count every read in holdout_exposed_count")
    if data_path.get("retrieval_happens_once_after_readiness_test_passes") is not True:
        fail("the protocol does not state that the retrieval happens once")
    if data_path.get("confirmatory_window_start_utc") != window.get("opens_utc"):
        fail("the data path names another confirmatory-window start than the freeze")

    # 5. the evaluation and decision rules -----------------------------------
    evaluation = protocol.get("evaluation_rule") or {}
    if evaluation.get("unchanged_v1_evaluation_metric") is not True:
        fail("the protocol does not bind the unchanged v1 evaluation metric")
    if evaluation.get("unchanged_cost_scenarios") is not True:
        fail("the protocol does not bind the unchanged cost scenarios")
    if evaluation.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        fail("the protocol does not forbid re-tuning on the window")
    if list(evaluation.get("cost_scenarios") or []) != list(
        (spec_v1.get("costs") or {}).get("scenarios") or []
    ):
        fail("the protocol's cost scenarios are not the v1 cost scenarios")
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )
    computed["recomputed_inherited_blocks_digest"] = inherited_digest
    if evaluation.get("inherited_rules_blocks_digest") != inherited_digest:
        fail("the inherited rules digest does not recompute from the v1 specification")
    grid = spec_v1.get("strategy_grid") or {}
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)
    if total != 2304:
        fail("the v1 grid no longer enumerates 2,304 combinations")
    decision = protocol.get("decision_rule") or {}
    if decision.get("criterion_count") != 1 or decision.get("exactly_one_criterion") is not True:
        fail("the protocol does not state exactly one confirmatory criterion")
    if decision.get("no_competing_criterion") is not True:
        fail("the protocol does not forbid a competing criterion")
    selection = spec_v1.get("selection") or {}
    min_trades = int(selection.get("min_trades_total"))
    expected_criteria = [
        "net_total_return > 0 at baseline costs (1x) over the confirmatory window",
        "net_total_return > 0 at 2x costs over the confirmatory window",
        f"closed_trades >= {min_trades} over the confirmatory window",
        "the evaluated parameters are byte-identical to the frozen v6 candidate manifest entry",
    ]
    if list(decision.get("criteria") or []) != expected_criteria:
        fail("the protocol's criteria are not the criteria of the unchanged v1 selection rule")
    if list(decision.get("status_vocabulary") or []) != list(
        (spec_v1.get("status") or {}).get("economic") or []
    ):
        fail("the protocol's status vocabulary is not the v1 status vocabulary")
    verdicts = decision.get("verdicts") or {}
    if verdicts.get("zero_trade_status") != "INCONCLUSIVE":
        fail("the protocol does not record a zero-trade result as inconclusive")
    if verdicts.get("low_trade_count_status") != "REJECTED_ON_HOLDOUT":
        fail("the protocol does not record a low-trade-count result as rejected")
    if f"1 to {min_trades - 1}" not in str(verdicts.get("low_trade_count_rule") or ""):
        fail("the low-trade-count rule does not use the v1 minimum trade count")
    if verdicts.get("status_vocabulary_is_not_extended") is not True:
        fail("the protocol does not forbid extending the status vocabulary")

    # 6. the reporting, falsifiers and deviation disclosure ------------------
    reporting = protocol.get("reporting_and_falsifiers") or {}
    for flag in (
        "every_evaluated_asset_and_candidate_reported",
        "assets_without_a_candidate_are_named",
        "null_result_reported",
        "negative_and_inconclusive_results_are_never_discarded",
        "v1_holdout_never_reopened",
        "v2_v3_v4_v5_confirmatory_windows_never_read",
    ):
        if reporting.get(flag) is not True:
            fail(f"the protocol does not record {flag}")
    if not reporting.get("holdout_report_required_fields"):
        fail("the protocol records no holdout-report fields")
    if not reporting.get("falsifiers"):
        fail("the protocol records no falsifiers")
    disclosure = protocol.get("deviation_disclosure") or {}
    if disclosure.get("carried_into_the_final_report") is not True:
        fail("the deviation disclosure is not carried into the final report")
    if disclosure.get("not_repaired") is not True:
        fail("the deviation disclosure claims the deviation was repaired")

    # 7. the authorization boundary and the code identity --------------------
    boundary = protocol.get("authorization_boundary") or {}
    for flag in (
        "authorizes_evaluation",
        "authorizes_candle_read_before_window_exists",
        "authorizes_window_benchmark_retrieval",
    ):
        if boundary.get(flag) is not False:
            fail(f"the authorization boundary does not record {flag} as false")
    if boundary.get("authorized_code_hash") != authorization.get("code_hash"):
        fail("the authorization boundary does not record the authorized code hash of record")
    if boundary.get("confirmatory_execution_code_must_live_outside_the_hashed_set") is not True:
        fail("the authorization boundary does not keep the confirmatory code outside the hashed set")
    constraint = protocol.get("code_hash_constraint") or {}
    source_digest = canonical_source_digest(root)
    computed["canonical_hashed_set_digest"] = source_digest
    if source_digest is None:
        fail("the hashed source set is missing, so its digest cannot be recomputed")
    elif constraint.get("canonical_source_digest") != source_digest:
        fail(
            "the code-hash constraint records another canonical tree digest, recomputed "
            f"{source_digest}"
        )
    if constraint.get("hashed_set_root") != "src/breakout_research":
        fail("the code-hash constraint does not name the hashed set root")
    if constraint.get("ordered_code_hash_is_portable") is not False:
        fail("the code-hash constraint does not record that the ordered hash is not portable")

    # 8. the related artifacts ----------------------------------------------
    supersedes = protocol.get("supersedes") or {}
    if supersedes.get("selection_authorization_path") != SELECTION_AUTHORIZATION_RELATIVE:
        fail("the supersedes block does not name the v6 selection authorization")
    if supersedes.get("selection_authorization_manifest_hash") != selection_authorization_hash:
        fail("the supersedes block does not bind the live v6 selection authorization hash")
    for flag in ("v1_holdout_never_reused", "v2_v3_v4_v5_confirmatory_window_never_read"):
        if supersedes.get(flag) is not True:
            fail(f"the supersedes block does not record {flag}")

    related = protocol.get("related_artifacts") or {}
    for key, entry in related.items():
        relative = str((entry or {}).get("path") or "")
        if not relative:
            fail(f"the related artifact {key} names no path")
            continue
        if not (root / relative).exists():
            if (entry or {}).get("manifest_hash") is None and (entry or {}).get(
                "specification_hash"
            ) is None:
                continue
            fail(f"the related artifact {relative} is missing")
            continue
        document = read_json(root / relative)
        if "specification_hash" in entry:
            if entry["specification_hash"] != document.get("specification_hash"):
                fail(f"the related artifact {relative} carries another specification hash")
            continue
        # Each artifact owns its own excluded-key set; it is read from the
        # artifact rather than assumed here.
        excluded_keys = tuple(
            (document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
        )
        recomputed = compute_manifest_hash(document, excluded_keys)
        if document.get("manifest_hash") != recomputed:
            fail(f"the related artifact {relative} does not recompute its own manifest_hash")
        if entry.get("manifest_hash") != recomputed:
            fail(f"the protocol names another manifest hash for {relative}")

    # 9. no confirmatory run has happened ------------------------------------
    for relative in V6_CONFIRMATORY_RUN_ARTIFACTS:
        if (root / relative).exists():
            fail(
                f"the v6 confirmatory artifact {relative} exists, but the v6 confirmatory chain "
                "has not run: the protocol authorizes no evaluation"
            )

    return {
        "ok": not failures,
        "protocol_path": PROTOCOL_RELATIVE,
        "manifest_hash": protocol.get("manifest_hash"),
        "recomputed_manifest_hash": protocol_hash,
        "computed": computed,
        "failures": failures,
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

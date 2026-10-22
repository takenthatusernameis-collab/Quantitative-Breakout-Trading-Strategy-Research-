#!/usr/bin/env python3
"""Build the preregistered v6 confirmatory protocol.

This producer writes ``configs/research_v6_confirmatory_protocol.json``: the
versioned, hash-bound artifact that preregisters how the single v6
confirmatory evaluation will be performed once the v6 confirmatory window
exists.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
evaluation may do. It authorizes no evaluation, no window read and no
benchmark retrieval.

Everything the protocol records is re-derived from the repository:

* the evaluation scope from the v6 candidate freeze and the v6 universe
  manifest -- the frozen band, the validated subset and the exclusion reasons
  of the members that never became candidates;
* the window definition from the freeze's confirmatory-window block;
* the decision criterion from the **unchanged v1 selection rule** that the v6
  specification inherits, and the status vocabulary from the v1 status block;
* the benchmark rule from the v6 data manifest's benchmark block and the
  dataset's own bytes;
* the code identity from the hashed source tree and from the campaign
  authorization that holds the authorized value of record.

The v6 chain publishes its confirmatory protocol **before** the v6 selection
run, so the protocol fixes the *procedure* and the *scope rule* and leaves the
selected configuration per asset to the selection phase. The readiness test
requires the selection authorization and the selected-configurations manifest
to exist and to be hash-bound before any window candle may be read.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes.

Usage::

    python3 scripts/build_v6_confirmatory_protocol.py            # write
    python3 scripts/build_v6_confirmatory_protocol.py --force    # rewrite
    python3 scripts/build_v6_confirmatory_protocol.py --print    # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    canonical_source_digest,
    compute_manifest_hash,
    read_json,
    sha256_file,
)

#: The instant at which this protocol is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-22T04:45:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the protocol is bound to, relative to the repository root.
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v6_selected_configurations_manifest.json"
ARTIFACT_RELATIVE = "configs/research_v6_confirmatory_protocol.json"

#: The v1 blocks the v6 chain inherits unchanged.
INHERITED_V1_BLOCKS = (
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

#: The alignment rule the confirmatory evaluation requires.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window before the "
    "frozen engine is called, so that the engine's index pairing equals the UTC-candle-close "
    "alignment of docs/research_protocol.md:101"
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v6 confirmatory protocol from the hash-bound artifacts."""
    root = Path(repo_root)

    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    execution = read_json(root / EXECUTION_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # --- the scope, re-derived from the freeze and the universe manifest ----
    members = list((freeze.get("band") or {}).get("members") or [])
    in_scope = [entry for entry in members if entry.get("validated") is True]
    excluded = [entry for entry in members if entry.get("validated") is not True]
    if not in_scope:
        raise SystemExit("the frozen v6 candidate set is empty")
    manifest_validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(str(entry["binance_pair"]) for entry in in_scope) != manifest_validated:
        raise SystemExit("the frozen v6 candidate set is not the validated v6 universe")

    # --- the decision rule, re-derived from the unchanged v1 selection rule -
    selection = spec_v1.get("selection") or {}
    min_trades = int(selection.get("min_trades_total"))
    criteria = [
        "net_total_return > 0 at baseline costs (1x) over the confirmatory window",
        "net_total_return > 0 at 2x costs over the confirmatory window",
        f"closed_trades >= {min_trades} over the confirmatory window",
        "the evaluated parameters are byte-identical to the frozen v6 candidate manifest entry",
    ]
    if selection.get("positive_net_return_baseline") is not True:
        raise SystemExit("the v1 selection rule no longer requires a positive baseline return")
    if selection.get("positive_net_return_2x_costs") is not True:
        raise SystemExit("the v1 selection rule no longer requires a positive 2x-cost return")
    if int(selection.get("max_candidates_per_asset")) != 1:
        raise SystemExit("the v1 selection rule no longer selects one candidate per asset")
    status_vocabulary = list((spec_v1.get("status") or {}).get("economic") or [])
    for status in ("CANDIDATE_PENDING_HOLDOUT", "PROVISIONAL_HISTORICAL_SURVIVAL",
                   "REJECTED_ON_HOLDOUT", "INCONCLUSIVE"):
        if status not in status_vocabulary:
            raise SystemExit(f"the v1 status vocabulary no longer carries {status}")

    # --- the window, re-derived from the freeze ------------------------------
    window = freeze.get("confirmatory_window") or {}
    membership = (spec_v6.get("holdout") or {}).get("confirmatory_window_membership") or {}

    # --- the benchmark, owned by the v6 data manifest -------------------------
    benchmark_block = data.get("benchmark") or {}
    benchmark_path = str(benchmark_block.get("dataset_path") or "")
    benchmark_hash = str(benchmark_block.get("content_hash") or "")
    if not benchmark_path:
        raise SystemExit("the v6 data manifest records no benchmark dataset")
    benchmark_file = root / benchmark_path
    if not benchmark_file.exists():
        raise SystemExit(f"the v6 benchmark dataset {benchmark_path} does not exist")
    if sha256_file(benchmark_file) != benchmark_hash:
        raise SystemExit("the v6 benchmark dataset does not match its recorded content hash")

    # --- the code identity --------------------------------------------------
    source_digest = canonical_source_digest(root)
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )

    document: Dict[str, Any] = {
        "artifact": "v6_confirmatory_protocol",
        "artifact_version": "v6-confirmatory-protocol-1",
        "protocol_version": "v6",
        "universe_version": "v6",
        "created_utc": CREATED_UTC,
        "protocol_status": "PREREGISTERED_NO_EVALUATION",
        "specification_purpose": (
            "Preregister the v6 confirmatory-evaluation protocol: the scope rule, the window "
            "definition and readiness test, the data path including the window benchmark series, "
            "the unchanged evaluation rule, the single confirmatory decision criterion, the "
            "reporting and falsifiers, and the authorization boundary. This artifact authorizes "
            "no evaluation, no window read and no benchmark retrieval before the window exists."
        ),
        "evaluation_scope": {
            "frozen_candidate_set_path": FREEZE_RELATIVE,
            "frozen_candidate_set_hash": freeze.get("manifest_hash"),
            "v6_specification_hash": spec_v6.get("specification_hash"),
            "v6_universe_manifest_path": UNIVERSE_RELATIVE,
            "v6_universe_manifest_hash": universe.get("manifest_hash"),
            "v6_data_manifest_path": DATA_RELATIVE,
            "v6_data_manifest_hash": data.get("manifest_hash"),
            "selected_configurations_manifest_path": SELECTED_CONFIGURATIONS_RELATIVE,
            "selected_configurations_manifest_hash": None,
            "selected_configurations_manifest_status": "NOT_YET_PUBLISHED",
            "selection_authorization_path": SELECTION_AUTHORIZATION_RELATIVE,
            "selection_authorization_manifest_hash": None,
            "in_scope_assets": len(in_scope),
            "in_scope_assets_list": [str(entry["binance_pair"]) for entry in in_scope],
            "out_of_scope_assets_excluded_at_validation": [
                str(entry["binance_pair"]) for entry in excluded
            ],
            "out_of_scope_reasons": {
                str(entry["binance_pair"]): str(entry["exclusion_reason"]) for entry in excluded
            },
            "selected_configuration_per_asset": (
                "the configuration evaluated for an asset is the one the v6 selection run "
                "publishes in research/v6_selected_configurations_manifest.json under the "
                "unchanged v1 selection rule; this protocol publishes before that run, so the "
                "readiness test requires the selection authorization and the "
                "selected-configurations manifest to exist and to be hash-bound before any "
                "window candle is read"
            ),
            "excluded_assets_stay_excluded": True,
            "scope_may_not_be_widened_narrowed_or_reranked": True,
        },
        "window_definition": {
            "window_opens_utc": window.get("opens_utc"),
            "minimum_closed_hourly_candles": int(window.get("min_hours")),
            "earliest_possible_end_utc": window.get("earliest_possible_end_utc"),
            "evaluation_may_not_start_before_utc": window.get(
                "evaluation_may_not_start_before_utc"
            ),
            "window_source": f"{FREEZE_RELATIVE}#confirmatory_window",
            "single_use": True,
            "must_not_overlap_v1_holdout": True,
            "must_not_overlap_v2_confirmatory_window": True,
            "must_not_overlap_v3_confirmatory_window": True,
            "must_not_overlap_v4_confirmatory_window": True,
            "must_not_overlap_v5_confirmatory_window": True,
            "never_reused_from_v1": True,
            "never_reused_from_v2": True,
            "never_reused_from_v3": True,
            "never_reused_from_v4": True,
            "never_reused_from_v5": True,
            "never_used_for_candidate_selection": True,
            "no_ranking_or_retuning_on_window": True,
            "never_populated_with_data_predating_the_candidate_freeze": True,
            "window_moved_by_the_candidate_freeze_amendments": False,
            "membership_rule": str(membership.get("rule") or ""),
            "membership_rule_owner": "configs/research_v6.json#holdout.confirmatory_window_membership",
            "overlap_rule": str(window.get("overlap_rule") or ""),
        },
        "data_path": {
            "retrieval_happens_once_after_readiness_test_passes": True,
            "every_read_counted_in_holdout_exposed_count": True,
            "hashed_and_verified_against_v6_data_manifest_scheme": True,
            "universe_manifest_path": UNIVERSE_RELATIVE,
            "universe_manifest_hash": universe.get("manifest_hash"),
            "data_manifest_path": DATA_RELATIVE,
            "data_manifest_hash": data.get("manifest_hash"),
            "confirmatory_window_start_utc": window.get("opens_utc"),
            "benchmark": {
                "symbol": "BTCUSDT",
                "role": "trend_filter_and_benchmark",
                "benchmark_is_not_a_candidate": True,
                "window_benchmark_series_required": True,
                "window_benchmark_series_exists_yet": False,
                "development_benchmark_dataset_path": benchmark_path,
                "development_benchmark_content_hash": benchmark_hash,
                "development_benchmark_covers_the_window": False,
                "development_benchmark_may_be_reused_as_the_window_benchmark": False,
                "window_benchmark_retrieval_happens_once": True,
                "window_benchmark_is_hash_verified": True,
                "alignment_rule": ALIGNMENT_RULE,
                "methodology_rule": (
                    "Align BTC and target asset by UTC candle close; no forward fill for missing "
                    "BTC observations"
                ),
                "methodology_reference": "docs/research_protocol.md:101",
                "no_forward_fill": True,
                "fail_closed": [
                    "the benchmark series is missing",
                    "the benchmark series is shorter than the evaluated window",
                    "the benchmark series is not index-aligned with the asset series",
                ],
                "grid_rule": (
                    "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                    "re-derived or re-ranked"
                ),
                "btc_configurations_dropped": False,
            },
            "readiness_test": {
                "must_pass_before_any_window_read": True,
                "checks": [
                    "the v6 confirmatory window holds at least 2160 closed hourly candles",
                    "the v6 candidate freeze is committed and hash-bound",
                    "this protocol is committed",
                    "the v6 selection authorization exists and is bound to the v6 candidate freeze",
                    "the v6 selected-configuration manifest is committed and hash-bound",
                    "a confirmatory evaluation authorization exists and is bound to this "
                    "protocol's manifest_hash",
                    "the confirmatory execution path lives outside the hashed set and its "
                    "canonical digest is recorded",
                    "the v1 holdout and the v2, v3, v4 and v5 confirmatory windows are not read",
                    "the window benchmark series is retrievable, hash-verifiable and index-aligned "
                    "with the asset series",
                ],
                "failure_mode": "BLOCKED_EXTERNAL",
            },
        },
        "evaluation_rule": {
            "unchanged_v1_evaluation_metric": True,
            "unchanged_cost_scenarios": True,
            "no_retuning_reranking_or_grid_extension_on_window": True,
            "selection_rule_reference": "configs/research_v1.json#selection",
            "inherited_rules_blocks_digest": inherited_digest,
            "cost_scenarios": [1.0, 2.0, 3.0],
        },
        "decision_rule": {
            "criterion_count": 1,
            "authoritative_source": "configs/research_v1.json#selection",
            "authoritative_source_note": (
                "the v6 specification inherits the v1 selection rule unchanged, and the v1 "
                "specification is the owner of that rule"
            ),
            "criteria": criteria,
            "status_vocabulary": status_vocabulary,
            "exactly_one_criterion": True,
            "no_competing_criterion": True,
            "note": (
                "The confirmatory decision is the single preregistered promotion rule, inherited "
                "unchanged from the immutable v1 specification. No second criterion (for example "
                "a buy-and-hold comparison) is stated anywhere in this document, because the v2 "
                "line had to be amended after two frozen artifacts disagreed about what passing "
                "the window means."
            ),
            "verdicts": {
                "survival_status": "PROVISIONAL_HISTORICAL_SURVIVAL",
                "survival_rule": (
                    "every criterion of the single preregistered promotion rule holds"
                ),
                "rejected_status": "REJECTED_ON_HOLDOUT",
                "rejected_rule": (
                    "the evaluation is conclusive and at least one criterion of the single "
                    "preregistered promotion rule fails"
                ),
                "inconclusive_status": "INCONCLUSIVE",
                "inconclusive_rules": [
                    "the window data is insufficient to evaluate the configuration",
                    "the configuration produced zero closed trades on the window",
                ],
                "zero_trade_status": "INCONCLUSIVE",
                "zero_trade_rule": (
                    "a configuration with zero closed trades is INCONCLUSIVE and never "
                    "REJECTED_ON_HOLDOUT: a never-traded strategy is not reported as a failure, "
                    "because the data cannot support that claim"
                ),
                "low_trade_count_status": "REJECTED_ON_HOLDOUT",
                "low_trade_count_rule": (
                    f"a configuration with 1 to {min_trades - 1} closed trades fails the "
                    f"closed_trades >= {min_trades} criterion and is REJECTED_ON_HOLDOUT"
                ),
                "status_vocabulary_is_not_extended": True,
            },
        },
        "reporting_and_falsifiers": {
            "every_evaluated_asset_and_candidate_reported": True,
            "assets_without_a_candidate_are_named": True,
            "null_result_reported": True,
            "negative_and_inconclusive_results_are_never_discarded": True,
            "v1_holdout_never_reopened": True,
            "v2_v3_v4_v5_confirmatory_windows_never_read": True,
            "holdout_report_required_fields": [
                "universe_version",
                "snapshot_id",
                "candidate_manifest_path",
                "candidate_manifest_hash",
                "confirmatory_window_start_utc",
                "confirmatory_window_end_utc",
                "candles_evaluated",
                "exposure_count",
                "per_asset_outcomes",
                "comparability_statement",
            ],
            "falsifiers": [
                "a confirmatory evaluation omits one of the in-scope candidates",
                "an asset excluded at validation is hidden from the report",
                "the grid is extended, re-tuned or re-ranked on the window",
                "a candle inside the window is read more than once",
                "holdout_exposed_count is incremented outside a confirmatory read",
                "the window benchmark series is missing, short or misaligned and the evaluation "
                "proceeds anyway",
                "the 576 btc_ema_168 configurations per asset are dropped",
                "the v1 holdout or the v2, v3, v4 or v5 confirmatory window is read",
                "a second confirmatory decision criterion is applied",
                "the v1/v2 BTC-alignment deviation is repaired instead of disclosed",
                "the v6 evaluation starts before the later of the four earlier gates and the v6 "
                "window's own earliest end",
            ],
        },
        "deviation_disclosure": {
            "scope": "the completed v1 and v2 runs",
            "statement": (
                "The completed v1 and v2 runs evaluated the BTC trend filter against a BTC EMA "
                "taken from a different period; the deviation is a disclosure for the final "
                "report and is not repaired here."
            ),
            "records_with_btc_filter": 124416,
            "total_v2_records": 497664,
            "misaligned_validation_folds": [0, 1, 2, 3],
            "evidence_path": "research/v3_evidence/v1_v2_btc_alignment_deviation.json",
            "v6_run_alignment": (
                "the v6 run evaluates the BTC trend filter against the index-aligned v6 "
                "benchmark dataset"
            ),
            "carried_into_the_final_report": True,
            "not_repaired": True,
        },
        "authorization_boundary": {
            "authorizes_evaluation": False,
            "authorizes_candle_read_before_window_exists": False,
            "authorizes_window_benchmark_retrieval": False,
            "code_identity_rule": "canonical_digest",
            "authorized_code_hash": str(authorization.get("code_hash") or ""),
            "v1_paths_forbidden": True,
            "v2_paths_forbidden": True,
            "v3_paths_forbidden": True,
            "v4_paths_forbidden": True,
            "v5_paths_forbidden": True,
            "new_v6_paths_require_new_versioned_amendment": True,
            "confirmatory_execution_code_must_live_outside_the_hashed_set": True,
            "hashed_set_root": "src/breakout_research",
            "statement": (
                "This protocol authorizes nothing. It preregisters how the confirmatory "
                "evaluation will be performed once the window exists. No candle inside the "
                "window may be read, no benchmark series may be retrieved, and no evaluation may "
                "be run, under this protocol."
            ),
        },
        "code_hash_constraint": {
            "authorized_code_hash": str(authorization.get("code_hash") or ""),
            "canonical_source_digest": source_digest,
            "canonical_source_digest_algorithm": "canonical_source_digest_v1",
            "hashed_set_root": "src/breakout_research",
            "confirmatory_execution_code_must_live_outside_the_hashed_set": True,
            "outside_hashed_set_examples": ["scripts/", "src/v6_campaign/", "src/v6_confirmatory/"],
            "inside_hashed_set_examples": ["src/breakout_research/", "src/breakout_research/v2/"],
            "ordered_code_hash_is_portable": False,
            "note": (
                "The identity of the hashed source set is the canonical source digest, which is "
                "portable across checkouts. The checkout-dependent ordered digest "
                "compute_code_hash() stays the authorized value of record and is never recomputed "
                "as a drift signal."
            ),
        },
        "supersedes": {
            "protocol_version": "v6",
            "selection_authorization_path": SELECTION_AUTHORIZATION_RELATIVE,
            "selection_authorization_manifest_hash": None,
            "reason": (
                "The v6 selection run selects at most one configuration per asset of the frozen "
                "v6 candidate set. The confirmatory protocol evaluates exactly the published "
                "candidates on the v6 confirmatory window; the selection run remains the "
                "preceding, immutable step."
            ),
            "v1_holdout_never_reused": True,
            "v2_v3_v4_v5_confirmatory_window_never_read": True,
        },
        "related_artifacts": {
            "v6_specification": {
                "path": SPEC_V6_RELATIVE,
                "specification_hash": spec_v6.get("specification_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "v6_universe_manifest": {
                "path": UNIVERSE_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
            },
            "v6_data_manifest": {
                "path": DATA_RELATIVE,
                "manifest_hash": data.get("manifest_hash"),
            },
            "v6_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v6_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v6_selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": json.load(open(SELECTION_AUTHORIZATION_RELATIVE)).get("manifest_hash"),
            },
        },
        "durability": {
            "rule": (
                "The protocol takes effect when this artifact is committed. No confirmatory-window "
                "candle may be read and no evaluation may run before the commit that carries this "
                "artifact exists."
            ),
            "protocol_commit": None,
            "protocol_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v6_confirmatory_protocol.py",
            "verify_command": "python3 scripts/verify_v6_confirmatory_protocol.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, so "
                "the document does not hash itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    os.chmod(target, 0o644)
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

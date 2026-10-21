#!/usr/bin/env python3
"""Build the preregistered v5 selection authorization 1.

This producer writes ``configs/research_v5_selection_authorization_1.json``:
the versioned, hash-bound artifact that authorizes **one** bounded v5 selection
grid run over the frozen v5 candidate set, with the effective rules of the v5
chain and the v5-cutoff-bounded benchmark bound into it.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself is performed by a later session, through the
execution path in ``src/v5_campaign`` that this artifact names and whose
canonical source digest it binds.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the freeze and re-derived from the v5 universe manifest;
* the effective rules from the three published amendments -- the membership rule
  of the specification amendment, the overlap rule and the evaluation gate of
  the candidate-freeze amendment, and the effective blocks of the execution
  amendment;
* the selection rule from the unchanged v1 ``selection`` block;
* the code identity from the source tree, under the canonical digest rule of
  BRAIN-009;
* the benchmark dataset, its content hash and the data-manifest identity from
  the effective v5 data manifest.

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v5_selection_authorization_1.py            # write the artifact
    python3 scripts/build_v5_selection_authorization_1.py --force    # rewrite it
    python3 scripts/build_v5_selection_authorization_1.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_RELATIVE = "configs/research_v5_selection_authorization_1.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELATIVE

#: The instant at which this authorization is created. It is pinned here so
#: that the artifact is byte-reproducible; it must not be moved once the
#: artifact has been committed.
CREATED_UTC = "2026-10-21T15:30:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source trees the run identity binds.
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v5_campaign"

#: The v5 artifacts the authorization is bound to.
FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
FREEZE_AMENDMENT_RELATIVE = "configs/research_v5_candidate_freeze_amendment_1.json"
SPEC_AMENDMENT_RELATIVE = "configs/research_v5_specification_amendment_1.json"
EXECUTION_AMENDMENT_RELATIVE = "configs/research_v5_execution_amendment_1.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v5.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v5.json"
EXECUTION_RELATIVE = "configs/research_v5_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v5 output paths the authorization allows the run to write.
OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)

#: The alignment rule the execution path requires the authorization to bind.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called"
)

#: The number of technical retries the single authorized run may consume.
MAX_RETRIES_ON_TECHNICAL_FAILURE = 3

#: The run this authorization permits. One logical run, one attempt, resumable.
RUN_ID = "v5-selection-20261021"
CAMPAIGN_ID = "v5-campaign"
RUN_PHASE = "selection_grid"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _execution_path_modules(repo_root: Path) -> List[str]:
    root = Path(repo_root) / EXECUTION_PATH_ROOT
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v5 selection authorization from the hash-bound artifacts."""
    root = Path(repo_root)

    from v5_campaign import runner as v5_runner
    from v5_campaign import benchmark as benchmark_rule
    from v5_campaign.data import resolve_effective_data_manifest
    from v5_campaign.identity import code_identity_document
    from v5_campaign.scope import (
        effective_rules,
        frozen_scope,
        resolve_effective_execution_protocol,
        selection_rule,
    )

    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_MANIFEST_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v5 = _load(root / SPEC_V5_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(root / CAMPAIGN_AUTHORIZATION_RELATIVE)

    # --- the effective rules, read amendment first ---------------------------
    rules = effective_rules(root)

    # --- the frozen scope, resolved from the freeze and the universe manifest -
    scope = frozen_scope(freeze, universe, rules)
    binance_pairs = list(scope["binance_pairs"])
    if not binance_pairs:
        raise SystemExit("the frozen v5 candidate set is empty")

    # --- the unchanged v1 selection rule -------------------------------------
    selection_block, selection_digest = selection_rule(spec_v1, spec_v5)

    # --- the code identity, recomputed from the source tree ------------------
    identity = code_identity_document(root)

    # --- the effective data manifest and the benchmark -----------------------
    effective_manifest, effective_hash, provenance = resolve_effective_data_manifest(root)
    if effective_hash != scope["data_manifest_hash"]:
        raise SystemExit(
            "the effective data-manifest identity does not match the identity the frozen "
            "candidate set binds"
        )
    benchmark_path = str(provenance["benchmark_dataset_path"])
    benchmark_dataset = root / benchmark_path
    if not benchmark_dataset.exists():
        raise SystemExit(f"the benchmark dataset {benchmark_path} does not exist")
    benchmark_content_hash = sha256_file(benchmark_dataset)
    if benchmark_content_hash != provenance["benchmark_content_hash"]:
        raise SystemExit(
            "the benchmark dataset does not hash to the content hash the data manifest "
            "publishes"
        )

    # --- the effective execution protocol ------------------------------------
    execution = resolve_effective_execution_protocol(root)
    execution_benchmark = execution.get("benchmark_rule") or {}
    if execution_benchmark.get("content_hash") != benchmark_content_hash:
        raise SystemExit(
            "the benchmark dataset named by the v5 execution protocol is not the "
            "benchmark dataset of the provenance"
        )
    if not str(execution_benchmark.get("alignment") or "").startswith(ALIGNMENT_RULE):
        raise SystemExit(
            "the benchmark alignment rule of the v5 execution protocol is not the rule the "
            "authorization binds"
        )
    if sorted(str(pair) for pair in dig(execution, "evaluation_scope.constituents") or []) != sorted(
        binance_pairs
    ):
        raise SystemExit(
            "the evaluated scope of the v5 execution protocol is not the frozen candidate set"
        )

    # --- the bounds, recomputed from the frozen scope and the grid -----------
    config_count = len(config_manifest.get("configurations") or [])
    if not config_count:
        raise SystemExit("the configuration manifest carries no configuration")
    if config_count != int(config_manifest.get("total_configurations") or 0):
        raise SystemExit("the configuration manifest disagrees with itself about its size")
    fold_count = len(spec_v1["folds"]["window_fractions"])
    cost_count = len(spec_v1["costs"]["scenarios"])
    max_assets = len(binance_pairs)
    max_configs_per_asset = config_count
    max_total_config_units = max_assets * max_configs_per_asset
    planned_config_units = max_total_config_units
    planned_execution_units = planned_config_units * fold_count * cost_count

    # --- the output paths, taken from the execution path itself --------------
    paths = {key: str(v5_runner.DEFAULT_PATHS[key]) for key in OUTPUT_PATH_KEYS}

    boundary = scope["effective_data_boundary_utc"]
    membership = rules["membership"]
    overlap = rules["overlap"]

    document: Dict[str, Any] = {
        "artifact": "v5_selection_authorization",
        "artifact_version": "v5-selection-authorization-1",
        "version": 1,
        "protocol_version": "v5",
        "universe_version": "v5",
        "specification_hash": spec_v5["specification_hash"],
        "created_utc": CREATED_UTC,
        "authorization_status": "PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN",
        "specification_purpose": (
            "Authorize exactly one bounded v5 selection grid run over the frozen v5 "
            "candidate set, under the unchanged v1 selection rule, on development data "
            "only, writing only to the v5 paths, with the effective v5 rules and the "
            "v5-cutoff-bounded benchmark built in. This artifact names the execution "
            "path, the bounds, the benchmark rule, the stopping conditions, the rollback "
            "rule and the falsifiers of that run. Building it executes nothing: no grid "
            "is run, no candle is read, no result exists."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-019",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-019, "
            "recommendation items 1, 5 and 6",
            "prerequisites_delivered": [
                "P1 configs/research_v5.json",
                "P2 research/universe_manifest_v5.json",
                "P3 research/data_manifest_v5.json",
                "the v5 candidate manifest freeze",
                "the v5 candidate-freeze amendment 1",
                "the v5 specification amendment 1",
                "the v5 execution protocol configs/research_v5_execution.json",
                "the v5 execution amendment 1",
            ],
            "execution_path_outside_hashed_set": (
                "The v5 execution code lives in src/v5_campaign, outside the hashed source "
                "set src/breakout_research. It imports the v1 engine unchanged; it adds, "
                "edits and removes no file under src/breakout_research, so the v1 campaign "
                "authorization and the v2 identity tuples stay valid."
            ),
        },
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": RUN_ID,
            "campaign_id": CAMPAIGN_ID,
            "run_phase": RUN_PHASE,
            "authorization_note": (
                "The run is recorded in the ledger before the first result is written. The "
                "authorization permits one logical run: a completed run is never re-run, and "
                "an interrupted run is resumed from the verified shards, with the number of "
                "resumes bounded by max_retries_on_technical_failure. A boundary abort rolls "
                "the ledger back and releases the run, so that a defect can be fixed and the "
                "run started again."
            ),
            "resume_semantics": {
                "one_logical_run": True,
                "completed_run_is_never_re_run": True,
                "interrupted_run_is_resumed": True,
                "resumes_bounded_by": "max_retries_on_technical_failure",
                "resume_source_of_truth": "the verified shards under research/shards_v5",
                "result_stream_is_a_projection_of_the_shards": True,
                "note": (
                    "A process that is killed leaves the run in the ledger as RUNNING. The "
                    "next process resumes it from the verified shards instead of starting a "
                    "second run, so an interruption cannot burn the single authorized run."
                ),
            },
            "scope": {
                "binance_pairs": binance_pairs,
                "count": len(binance_pairs),
                "candidate_manifest_path": FREEZE_RELATIVE,
                "bound_to_universe_hash": scope["universe_manifest_hash"],
                "bound_to_data_hash": effective_hash,
                "bound_to_base_data_hash": scope["data_manifest_hash"],
                "bound_to_freeze_hash": scope["candidate_manifest_hash"],
                "membership_rule": (
                    "Exactly the constituents marked validated in "
                    "research/universe_manifest_v5.json. The run may not re-rank, widen or "
                    "narrow the frozen set."
                ),
                "widening_by_reranking_forbidden": True,
                "excluded_assets_stay_excluded": True,
                "excluded_after_validation": dict(scope["excluded_after_validation"] or {}),
                "benchmark_is_not_a_candidate": True,
            },
            "execution_path": {
                "package": EXECUTION_PATH_ROOT,
                "entry_point": f"{EXECUTION_PATH_ROOT}/runner.py:run_selection",
                "modules": _execution_path_modules(root),
                "engine_imports": [
                    "breakout_research.backtest.backtester.run_fold_backtest",
                    "breakout_research.backtest.shards.ResultStore",
                    "breakout_research.backtest.shards.compute_experiment_id",
                    "breakout_research.backtest.checkpoint.CheckpointManager",
                    "breakout_research.baselines.load_verified_candles",
                    "breakout_research.baselines.buyhold_baseline",
                    "breakout_research.selection.select_candidates",
                    "breakout_research.config.get_configurations",
                ],
                "engine_is_reused_unchanged": True,
                "hashed_set_untouched": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "note": (
                    "The execution path reuses the v1 indicators, signals, backtester, "
                    "verified candle loader, shard writer, checkpoint manager and candidate "
                    "selector without modification. It adds no parameter, threshold, fold, "
                    "cost or selection criterion of its own."
                ),
            },
            "code_identity": {
                "algorithm": identity["algorithm"],
                "algorithm_description": identity["algorithm_description"],
                "portable": True,
                "hashed_set_root": identity["hashed_set_root"],
                "hashed_set_digest": identity["hashed_set_digest"],
                "execution_path_root": identity["execution_path_root"],
                "execution_path_digest": identity["execution_path_digest"],
                "run_code_identity": identity["run_code_identity"],
                "authorized_code_hash": campaign_authorization["code_hash"],
                "authorized_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
                "ordered_code_hash_is_portable": False,
                "note": (
                    "The identity of a v5 run is the composite of the canonical digest of the "
                    "hashed v1 engine and the canonical digest of the v5 execution path. The "
                    "checkout-dependent ordered digest compute_code_hash() stays the authorized "
                    "value of record and is never used as an identity."
                ),
            },
            "effective_rules": {
                "membership": {
                    "path": membership["path"],
                    "manifest_hash": membership["manifest_hash"],
                    "rule": membership["rule"],
                    "interval_start_inclusive": membership["interval_start_inclusive"],
                    "interval_end_exclusive": membership["interval_end_exclusive"],
                    "precedence": membership["precedence"],
                    "consequence_for_the_run": (
                        "a candle that closes exactly at a confirmatory window's start is "
                        "development data; the last development candle of every v5 dataset "
                        "closes exactly at the development cutoff"
                    ),
                },
                "overlap": {
                    "path": overlap["path"],
                    "manifest_hash": overlap["manifest_hash"],
                    "rule": overlap["rule"],
                    "evaluation_may_not_start_before_utc": overlap[
                        "evaluation_may_not_start_before_utc"
                    ],
                    "precedence": overlap["precedence"],
                    "consequence_for_the_run": (
                        "the v5 confirmatory window opens inside the still-open v2, v3 and v4 "
                        "confirmatory windows in time, which is inevitable and not a violation: "
                        "the evaluations share no asset and the v5 confirmatory evaluation may "
                        "not start before the later of the four gates"
                    ),
                },
                "execution": {
                    "path": rules["execution"]["path"],
                    "manifest_hash": rules["execution"]["manifest_hash"],
                    "precedence": (
                        "the effective v5 execution protocol is the newest published execution "
                        "amendment for the blocks it restates, and configs/research_v5_execution."
                        "json for the blocks no amendment restates; every amendment stays on "
                        "disk, unchanged and visible"
                    ),
                    "named_amendment_precedence": rules["execution"]["precedence"],
                    "consequence_for_the_run": (
                        "the effective execution protocol is the newest published execution "
                        "amendment for the blocks it restates and the frozen protocol for the "
                        "rest; every amendment stays on disk, unchanged and visible, and the "
                        "run gate verifies the published v5 selection authorization's identity "
                        "instead of a static flag"
                    ),
                },
            },
            "data_boundary": {
                "development_data_only": True,
                "candles_before_utc": boundary,
                "candles_before_utc_rule": (
                    "Only candles that close at or before the effective development boundary "
                    "recorded by the candidate freeze may be read during the selection run. The "
                    "effective boundary is the earlier of the v5 confirmatory-window start and "
                    "the preregistered development cutoff, so no run can read a candle that "
                    "closes inside the open v2, v3 or v4 confirmatory window. A dataset that "
                    "reaches past the boundary is refused before it is read."
                ),
                "boundary_convention": "inclusive: the last development candle closes exactly at the boundary",
                "development_cutoff_utc": scope["development_cutoff_utc"],
                "development_cutoff_rule": (
                    "configs/research_v5.json#holdout.development_cutoff_utc: the v5 "
                    "development data ends at the last fully closed hour that closes at or "
                    "before the cutoff, and no candle that closes after the cutoff may be read"
                ),
                "v5_confirmatory_window_start_utc": scope["confirmatory_window_start_utc"],
                "confirmatory_window_never_read_during_selection": True,
                "v1_holdout_never_reused": True,
                "v2_confirmatory_window_never_reused": True,
                "v3_confirmatory_window_never_reused": True,
                "v4_confirmatory_window_never_reused": True,
                "holdout_exposed_count_stays_zero_during_selection": True,
                "holdout_position_fold_never_evaluated_during_selection": True,
                "provider_requests": 0,
                "provider_requests_note": (
                    "The run reads the immutable local datasets that the effective v5 data "
                    "manifest already binds and verifies, the benchmark dataset included. It "
                    "performs no provider request, so it cannot re-retrieve, re-time or "
                    "refresh any market data."
                ),
            },
            "selection_rule": {
                "unchanged_from_v1": True,
                "reference": SPEC_V1_RELATIVE,
                "block": "selection",
                "selection_block_sha256": selection_digest,
                "v5_block_is_byte_equal": True,
                "max_candidates_per_asset": selection_block["max_candidates_per_asset"],
                "selector": "breakout_research.selection.select_candidates",
                "grid_reference": (
                    "the strategy_grid of configs/research_v1.json, inherited unchanged by "
                    f"configs/research_v5.json: {max_configs_per_asset} configurations per asset"
                ),
                "grid_configuration_count": config_count,
                "no_criterion_may_be_added_tightened_or_loosened": True,
            },
            "paths": {
                **{key: paths[key] for key in OUTPUT_PATH_KEYS},
                "never_use_v1_paths": True,
                "never_use_v2_paths": True,
                "never_use_v3_paths": True,
                "never_use_v4_paths": True,
            },
            "bounds": {
                "max_assets": max_assets,
                "max_configs_per_asset": max_configs_per_asset,
                "max_total_config_units": max_total_config_units,
                "attempts": 1,
                "max_retries_on_technical_failure": MAX_RETRIES_ON_TECHNICAL_FAILURE,
                "planned_config_units": planned_config_units,
                "planned_execution_units": planned_execution_units,
                "planned_execution_units_note": (
                    f"The bounded run holds {max_assets} assets x {max_configs_per_asset} "
                    f"configurations x {fold_count} validation folds x {cost_count} cost "
                    "scenarios execution units. The bound that the authorization enforces is "
                    "max_total_config_units, the number of asset-configuration pairs; the "
                    "fold and cost multipliers follow the inherited, unchanged fold and cost "
                    "blocks."
                ),
                "resource_limits": (
                    "the v5 execution protocol records max_logical_runs 1 and "
                    "checkpoint_every_n_shards 10; the run is resumable and never retries "
                    "unboundedly"
                ),
            },
            "benchmark": {
                "symbol": str(provenance["benchmark_symbol"]),
                "role": "trend_filter_and_benchmark",
                "dataset_path": benchmark_path,
                "content_hash": benchmark_content_hash,
                "first_candle_timestamp": provenance.get("benchmark_first_candle_timestamp"),
                "last_candle_timestamp": provenance.get("benchmark_last_candle_timestamp"),
                "observed_candle_count": provenance.get("benchmark_observed_candle_count"),
                "alignment_rule": ALIGNMENT_RULE,
                "alignment_methodology": "docs/research_protocol.md:101 - Align BTC and "
                "target asset by UTC candle close",
                "methodology_rule": benchmark_rule.ALIGNMENT_RULE,
                "methodology_reference": benchmark_rule.ALIGNMENT_REFERENCE,
                "no_forward_fill": True,
                "fail_closed": list(execution_benchmark.get("fail_closed") or []),
                "grid_rule": execution_benchmark.get("grid_rule"),
                "btc_configurations_dropped": False,
                "exposure_rule": execution_benchmark.get("exposure_rule"),
                "published_by_data_manifest": True,
                "note": (
                    "The v5 benchmark is the v5-cutoff-bounded dataset that the v5 data "
                    "manifest publishes in its benchmark block; the block is inside the "
                    "manifest's own self-hash. The v4 chain's benchmark dataset "
                    "(research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv) is not reused, "
                    "because 13 of its candles close after the v5 development cutoff, inside "
                    "the open v2 confirmatory window. The dataset is hash-verified before "
                    "every use, it covers every evaluated validation window of the evaluated "
                    "assets with identical timestamps, and the asset series and the benchmark "
                    "series are sliced to the same fold window before the frozen engine is "
                    "called."
                ),
            },
            "effective_data_manifest": {
                "effective_data_manifest_hash": effective_hash,
                "base_manifest_path": DATA_MANIFEST_RELATIVE,
                "base_manifest_hash": provenance["base_manifest_hash"],
                "note": (
                    "The effective v5 data manifest is the base manifest alone; v5 publishes "
                    "no data-manifest amendment. The benchmark dataset is published by that "
                    "manifest, in its benchmark block."
                ),
            },
            "stopping_conditions": [
                "Normal completion within the recorded bounds",
                "No candidate survives the unchanged v1 selection rule -> report the outcome "
                "(do not hide it)",
                "Any boundary violation -> abort and rollback",
                "A technical interruption -> keep the verified shards and resume the same run",
            ],
            "rollback_rule": (
                "Do not write to v1, v2, v3 or v4 artifacts; remove any newly created v5 "
                "artifact if the execution is aborted; do not alter research_state/"
                "checkpoint.json, research_state/checkpoint_v2.json, "
                "research_state/checkpoint_v3.json, research_state/checkpoint_v4.json or the "
                "v1, v2, v3 or v4 campaign state."
            ),
            "falsifiers": [
                "Any modification to src/breakout_research/ (would change the code hash)",
                "Reading any candle in the v5 confirmatory window during selection",
                "Reading any candle that closes inside the open v2, v3 or v4 confirmatory "
                "window",
                "Writing into v1, v2, v3 or v4 shards, ledger, tallies or result streams",
                "Reusing the v1 holdout, or the v2, v3 or v4 confirmatory window",
                "Reusing the v4 chain's benchmark dataset",
                "Mixing v1, v2, v3 or v4 cycle units with v5 results",
                "Widening or narrowing the frozen candidate set",
                "Dropping, re-deriving or re-ranking the 576 btc_ema_168 configurations",
                "Evaluating the BTC filter on a benchmark series that does not cover an "
                "evaluated window of the asset series, or whose timestamps differ inside it",
                "A second run attempt under this authorization",
            ],
            "no_execution_in_this_session": True,
        },
        "not_authorized": {
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "v1_reauthorization_authorized": False,
            "source_tree_change_authorized": False,
            "second_v5_selection_run_authorized": False,
            "amendment_of_a_frozen_artifact_authorized": False,
            "statement": (
                "This artifact authorizes one bounded v5 selection run and nothing else. It "
                "does not authorize a confirmatory-window evaluation, a candle fetch, a "
                "change to the hashed source set, an edit of a frozen artifact or a v1 "
                "re-authorization. The selected-configuration manifest that the v5 "
                "confirmatory window requires must be committed and hash-bound before the "
                "first confirmatory-window candle is read, and the v5 confirmatory "
                "evaluation may not start before the effective gate "
                f"{overlap['evaluation_may_not_start_before_utc']}."
            ),
        },
        "related_artifacts": {
            "v5_specification": {
                "path": SPEC_V5_RELATIVE,
                "specification_hash": spec_v5["specification_hash"],
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "v5_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": scope["candidate_manifest_hash"],
                "frozen_at_utc": scope["candidate_freeze_timestamp_utc"],
            },
            "v5_candidate_freeze_amendment_1": {
                "path": FREEZE_AMENDMENT_RELATIVE,
                "manifest_hash": overlap["manifest_hash"],
            },
            "v5_specification_amendment_1": {
                "path": SPEC_AMENDMENT_RELATIVE,
                "manifest_hash": membership["manifest_hash"],
            },
            "v5_execution_amendment_1": {
                "path": EXECUTION_AMENDMENT_RELATIVE,
                "manifest_hash": rules["execution"]["manifest_hash"],
            },
            "v5_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": scope["universe_manifest_hash"],
            },
            "v5_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": provenance["base_manifest_hash"],
            },
            "v5_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v1_campaign_authorization": {
                "path": CAMPAIGN_AUTHORIZATION_RELATIVE,
                "code_hash": campaign_authorization["code_hash"],
                "authorized": campaign_authorization.get("authorized"),
                "note": (
                    "The functional field of the authorization is recorded, not the digest of "
                    "its bytes: the controller refreshes the authorized_at_utc timestamp, so "
                    "the file digest changes without the authorization changing."
                ),
            },
            "configuration_manifest": {
                "path": CONFIG_MANIFEST_RELATIVE,
                "total_configurations": config_manifest.get("total_configurations"),
            },
        },
        "residual_limitations": [
            {
                "id": "RL1",
                "location": "the v5 selection run's result volume",
                "limitation": (
                    f"The bounded run writes {planned_execution_units} execution units. At "
                    "the v1 record size this is of the order of 0.5 GB of shards and of the "
                    "order of 100 MB of result stream. The v1 shards are bounded to 4 MiB per "
                    "file; the v1 result stream was a single file of 50 MB that the campaign "
                    "could not push as one blob."
                ),
                "consequence": (
                    "The shards under research/shards_v5 are the authoritative record set and "
                    "are committed as bounded files of at most 4 MiB each, as the v1 campaign "
                    "did. The single-file result stream research/results_v5.jsonl is expected "
                    "to be large and is a projection of the verified shards, regenerated from "
                    "them. The ledger, the results manifest and the checkpoint are small and "
                    "are committed. The v1, v2, v3 and v4 artifacts stay untouched either way."
                ),
            },
            {
                "id": "RL2",
                "location": "the benchmark dataset",
                "limitation": (
                    "The v5 data manifest publishes the benchmark in its benchmark block and "
                    "not in the assets map, so the manifest-driven asset loader cannot "
                    "resolve it; the benchmark is read directly and verified against the "
                    "published content hash and the canonical hourly-CSV content hash."
                ),
                "consequence": (
                    "The benchmark rule of BRAIN-013 is still fully implemented: the dataset "
                    "is hash-verified, it covers every evaluated window of each evaluated "
                    "asset with identical timestamps, and both series are sliced to the same "
                    "fold window before the frozen engine is called. No observation is "
                    "forward-filled. The published block is inside the manifest's own "
                    "self-hash, so the benchmark identity is part of the v5 data-manifest "
                    "identity."
                ),
            },
            {
                "id": "RL3",
                "location": "the v5 confirmatory window",
                "limitation": (
                    "The v5 confirmatory window opens inside the still-open v2, v3 and v4 "
                    "confirmatory windows in time. A 90-day window that opens later cannot end "
                    "later than the 90-day window that opened before it, so the time overlap "
                    "is inevitable."
                ),
                "consequence": (
                    "The overlap is not a violation: the v5 candidate set is disjoint from the "
                    "v1, v2, v3 and v4 candidate sets, and the v5 confirmatory evaluation may "
                    "not start before the later of the four gates "
                    f"({overlap['evaluation_may_not_start_before_utc']}). The v5 window is "
                    "never populated with data that predates the v5 candidate freeze and is "
                    "never read for selection."
                ),
            },
        ],
        "verification": {
            "verifier_script": "scripts/verify_v5_selection_authorization_1.py",
            "tests_module": "tests/test_v5_selection_authorization_1.py",
            "verify_command": "python3 scripts/verify_v5_selection_authorization_1.py",
            "execution_path_tests": "tests/test_v5_campaign_benchmark_rule.py",
        },
        "durability": {
            "commit": None,
            "pushed": False,
            "note": (
                "Becomes durable when the commit that carries this artifact exists. The "
                "artifact is not rewritten after that commit, because its manifest_hash must "
                "not change."
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), "
            "ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "following the pattern of the other v2, v3 and v4 artifacts."
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

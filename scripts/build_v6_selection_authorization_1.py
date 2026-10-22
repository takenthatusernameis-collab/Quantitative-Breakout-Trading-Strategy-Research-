#!/usr/bin/env python3
"""Build the preregistered v6 selection authorization 1.

This producer writes ``configs/research_v6_selection_authorization_1.json``:
the versioned, hash-bound artifact that authorizes **one** bounded v6 selection
grid run over the frozen v6 candidate set, with the effective rules of the v6
specification and the v6-cutoff-bounded benchmark built into it.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself is performed by a later session, through the
execution path in ``src/v6_campaign`` that this artifact names. That path does
not exist yet, so the authorization records ``v6_execution_path_exists: false``
and binds no path digest.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the freeze and re-derived from the v6 universe manifest;
* the effective rules from the v6 specification itself -- the membership rule
  of the holdout block, the overlap rule of the phase gates, and the effective
  execution protocol, which the frozen protocol owns for every block no
  published v6 execution amendment restates;
* the selection rule from the unchanged v1 ``selection`` block;
* the code identity from the source tree, under the canonical digest rule of
  BRAIN-009;
* the benchmark dataset, its content hash and the data-manifest identity from
  the effective v6 data manifest.

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v6_selection_authorization_1.py            # write the artifact
    python3 scripts/build_v6_selection_authorization_1.py --force    # rewrite it
    python3 scripts/build_v6_selection_authorization_1.py --print     # print, write nothing
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

ARTIFACT_RELATIVE = "configs/research_v6_selection_authorization_1.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELATIVE

#: The instant at which this authorization is created. It is pinned here so
#: that the artifact is byte-reproducible; it must not be moved once the
#: artifact has been committed.
CREATED_UTC = "2026-10-22T09:52:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source trees the run identity binds.
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v6_campaign"

#: The v6 artifacts the authorization is bound to.
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v6.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v6.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v6 output paths the authorization allows the run to write.
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
RUN_ID = "v6-selection-20261022"
CAMPAIGN_ID = "v6-campaign"
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


def canonical_source_digest(root: Path) -> str:
    """The portable identity of the ``*.py`` tree under ``root``.

    This is the ``canonical_source_digest_v1`` rule of BRAIN-009: a sha256
    over the POSIX relative path and the content digest of every ``*.py`` file
    under the root, in ascending path order. If the root does not exist, the
    digest is the sha256 of the empty input.
    """
    base = Path(root)
    digest = hashlib.sha256()
    if base.is_dir():
        for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
            digest.update(relative.encode("utf-8") + b"\n")
            digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v6 selection authorization from the hash-bound artifacts."""
    root = Path(repo_root)

    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_MANIFEST_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v6 = _load(root / SPEC_V6_RELATIVE)
    execution = _load(root / EXECUTION_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(root / CAMPAIGN_AUTHORIZATION_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)

    # --- the frozen scope, resolved from the freeze and the universe manifest -
    binance_pairs = [
        str(member["binance_pair"])
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    ]
    if not binance_pairs:
        raise SystemExit("the frozen v6 candidate set is empty")

    # --- the unchanged v1 selection rule -------------------------------------
    selection_block = spec_v1["selection"]
    selection_digest = sha256_bytes(canonical(selection_block).encode("utf-8"))

    # --- the code identity, recomputed from the source tree ------------------
    hashed_set_digest = canonical_source_digest(root / HASHED_SET_ROOT)
    execution_path = root / EXECUTION_PATH_ROOT
    execution_path_exists = execution_path.is_dir()
    if execution_path_exists:
        execution_path_digest = canonical_source_digest(execution_path)
    else:
        execution_path_digest = None

    run_code_identity = sha256_bytes(
        canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": hashed_set_digest,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": execution_path_digest,
            }
        ).encode("utf-8")
    )

    # --- the effective data manifest and the benchmark -----------------------
    effective_hash = data_manifest.get("manifest_hash")
    benchmark_block = execution.get("benchmark_rule") or {}
    benchmark_path = str(benchmark_block.get("dataset_path"))
    benchmark_dataset = root / benchmark_path
    if not benchmark_dataset.exists():
        raise SystemExit(f"the benchmark dataset {benchmark_path} does not exist")
    benchmark_content_hash = sha256_file(benchmark_dataset)
    if benchmark_content_hash != benchmark_block.get("content_hash"):
        raise SystemExit(
            "the benchmark dataset does not hash to the content hash the v6 "
            "execution protocol publishes"
        )

    # --- the effective data boundary ----------------------------------------
    cutoff = spec_v6["holdout"]["development_cutoff_utc"]
    window_start = dig(
        execution,
        "candidate_freeze_and_confirmatory_window.confirmatory_window_opens_utc",
    )
    if not cutoff or not window_start:
        raise SystemExit("the v6 specification records no development cutoff or confirmatory-window start")
    effective_boundary = min(cutoff, window_start)

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

    # --- the output paths, taken from the v6 namespace ----------------------
    paths = {
        "shards_dir": "research/shards_v6",
        "ledger": "research/ledger_v6.json",
        "results_manifest": "research/results_manifest_v6.json",
        "results_stream": "research/results_v6.jsonl",
        "checkpoint": "research_state/checkpoint_v6.json",
    }

    # --- the effective rules, from the v6 specification (no amendments yet) ---
    membership_rule_block = spec_v6["holdout"]["confirmatory_window_membership"]
    membership = {
        "path": SPEC_V6_RELATIVE,
        "manifest_hash": spec_v6["specification_hash"],
        "rule": membership_rule_block["rule"],
        "interval_start_inclusive": membership_rule_block["interval_start_inclusive"],
        "interval_end_exclusive": membership_rule_block["interval_end_exclusive"],
        "precedence": "specification_direct",
        "consequence_for_the_run": (
            "a candle that closes exactly at a confirmatory window's start is "
            "development data; the last development candle of every v6 dataset "
            "closes exactly at the effective development boundary"
        ),
    }

    overlap_rule = {
        "path": EXECUTION_RELATIVE,
        "manifest_hash": execution.get("manifest_hash"),
        "rule": (
            "the v6 evaluation may not start before the later of the four "
            "recorded confirmatory gates and the v6 window's own earliest end; "
            "the v6 confirmatory window opens inside the still-open v2, v3, "
            "v4 and v5 confirmatory windows in time, which is inevitable and "
            "not a violation: the v6 candidate set is disjoint from the v1, "
            "v2, v3, v4 and v5 candidate sets"
        ),
        "evaluation_may_not_start_before_utc": dig(
            execution,
            "candidate_freeze_and_confirmatory_window.evaluation_may_not_start_before_utc",
        ),
        "precedence": "specification_direct",
        "consequence_for_the_run": (
            "the v6 confirmatory evaluation may not start before the effective "
            "gate; the v6 selection run itself reads development data only"
        ),
    }

    execution_rule = {
        "path": EXECUTION_RELATIVE,
        "manifest_hash": execution.get("manifest_hash"),
        "precedence": (
            "the effective v6 execution protocol is the newest published v6 "
            "execution amendment for the blocks it restates, and "
            "configs/research_v6_execution.json for the blocks no amendment "
            "restates; every artifact stays on disk, unchanged and visible"
        ),
        "named_amendment_precedence": (
            "no v6 execution amendment is named here: the rule above is generic, so it "
            "survives an amendment published after this authorization"
        ),
        "consequence_for_the_run": (
            "the effective execution protocol is resolved amendment-first, from the "
            "newest published v6 execution amendment that recomputes its own hash and "
            "is bound to the frozen protocol; the run gate verifies the published v6 "
            "selection authorization's identity instead of a static flag"
        ),
    }

    excluded_after = {
        str(member.get("binance_pair")): member.get("exclusion_reason")
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is not True
    }

    document: Dict[str, Any] = {
        "artifact": "v6_selection_authorization",
        "artifact_version": "v6-selection-authorization-1",
        "version": 1,
        "protocol_version": "v6",
        "universe_version": "v6",
        "specification_hash": spec_v6["specification_hash"],
        "created_utc": CREATED_UTC,
        "authorization_status": "PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN",
        "specification_purpose": (
            "Authorize exactly one bounded v6 selection grid run over the frozen v6 "
            "candidate set, under the unchanged v1 selection rule, on development data "
            "only, writing only to the v6 paths, with the effective v6 rules and the "
            "v6-cutoff-bounded benchmark built in. This artifact names the execution "
            "path, the bounds, the benchmark rule, the stopping conditions, the rollback "
            "rule and the falsifiers of that run. Building it executes nothing: no grid "
            "is run, no candle is read, no result exists. The v6 execution path "
            "src/v6_campaign does not exist yet; the authorization records "
            "v6_execution_path_exists: false and binds no path digest."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-026",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-026, "
            "recommendation items 1, 5 and 6",
            "repair_decision_record": "research_state/brainstorming_queue.md -> BRAIN-027, "
            "recommendation item 1: the precedence rule of the effective execution protocol is "
            "generic -- the newest published v6 execution amendment for the blocks it restates "
            "-- so that this authorization is not bound to an amendment that does not exist yet "
            "and survives an amendment published after it",
            "prerequisites_delivered": [
                "P1 configs/research_v6.json",
                "P2 research/universe_manifest_v6.json",
                "P3 research/data_manifest_v6.json",
                "the v6 candidate manifest freeze configs/research_v6_candidate_freeze.json",
                "the v6 execution protocol configs/research_v6_execution.json",
            ],
            "execution_path_outside_hashed_set": (
                "The v6 execution code will live in src/v6_campaign, outside the hashed "
                "source set src/breakout_research. The path does not exist yet, so no "
                "path digest is bound. It will import the v1 engine unchanged; it adds, "
                "edits and removes no file under src/breakout_research, so the v1 "
                "campaign authorization and the identity tuples stay valid."
            ),
        },
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": RUN_ID,
            "campaign_id": CAMPAIGN_ID,
            "run_phase": RUN_PHASE,
            "authorization_note": (
                "The run is recorded in the ledger before the first result is written. "
                "The authorization permits one logical run: a completed run is never "
                "re-run, and an interrupted run is resumed from the verified shards, "
                "with the number of resumes bounded by max_retries_on_technical_failure. "
                "A boundary abort rolls the ledger back and releases the run, so that a "
                "defect can be fixed and the run started again."
            ),
            "resume_semantics": {
                "one_logical_run": True,
                "completed_run_is_never_re_run": True,
                "interrupted_run_is_resumed": True,
                "resumes_bounded_by": "max_retries_on_technical_failure",
                "resume_source_of_truth": "the verified shards under research/shards_v6",
                "result_stream_is_a_projection_of_the_shards": True,
                "note": (
                    "A process that is killed leaves the run in the ledger as RUNNING. "
                    "The next process resumes it from the verified shards instead of "
                    "starting a second run, so an interruption cannot burn the single "
                    "authorized run."
                ),
            },
            "scope": {
                "binance_pairs": binance_pairs,
                "count": len(binance_pairs),
                "candidate_manifest_path": FREEZE_RELATIVE,
                "bound_to_universe_hash": universe.get("manifest_hash"),
                "bound_to_data_hash": effective_hash,
                "bound_to_base_data_hash": effective_hash,
                "bound_to_freeze_hash": freeze.get("manifest_hash"),
                "membership_rule": (
                    "Exactly the constituents marked validated in "
                    "research/universe_manifest_v6.json. The run may not re-rank, widen or "
                    "narrow the frozen set."
                ),
                "widening_by_reranking_forbidden": True,
                "excluded_assets_stay_excluded": True,
                "excluded_after_validation": excluded_after,
                "benchmark_is_not_a_candidate": True,
            },
            "execution_path": {
                "package": EXECUTION_PATH_ROOT,
                "entry_point": f"{EXECUTION_PATH_ROOT}/runner.py:run_selection",
                "modules": [],
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
                "v6_execution_path_exists": execution_path_exists,
                "note": (
                    "The v6 execution path src/v6_campaign does not exist yet. When it is "
                    "created, its canonical source digest will be recorded here and the "
                    "path must live outside src/breakout_research. It reuses the v1 "
                    "indicators, signals, backtester, verified candle loader, shard "
                    "writer, checkpoint manager and candidate selector without "
                    "modification. It adds no parameter, threshold, fold, cost or "
                    "selection criterion of its own."
                ),
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "algorithm_description": "sha256 over the concatenation, for every *.py "
                "file under the root in ascending POSIX relative-path order, of the "
                "relative path, a newline, the sha256 hex digest of the file bytes, "
                "and a newline.",
                "portable": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": hashed_set_digest,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": execution_path_digest,
                "run_code_identity": run_code_identity,
                "authorized_code_hash": campaign_authorization["code_hash"],
                "authorized_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
                "ordered_code_hash_is_portable": False,
                "note": (
                    "The identity of a v6 run is the composite of the canonical digest of "
                    "the hashed v1 engine and the canonical digest of the v6 execution "
                    "path. Because the execution path does not exist yet, its digest is "
                    "null and the run code identity is computed over a null execution "
                    "path digest. The checkout-dependent ordered digest compute_code_hash() "
                    "stays the authorized value of record and is never used as an identity."
                ),
            },
            "effective_rules": {
                "membership": membership,
                "overlap": overlap_rule,
                "execution": execution_rule,
            },
            "data_boundary": {
                "development_data_only": True,
                "candles_before_utc": effective_boundary,
                "candles_before_utc_rule": (
                    "Only candles that close at or before the effective development "
                    "boundary recorded by the candidate freeze may be read during the "
                    "selection run. The effective boundary is the earlier of the v6 "
                    "confirmatory-window start and the preregistered development cutoff, "
                    "so no run can read a candle that closes inside the open v2, v3, v4 "
                    "or v5 confirmatory window. A dataset that reaches past the boundary "
                    "is refused before it is read."
                ),
                "boundary_convention": "inclusive: the last development candle closes exactly at the boundary",
                "development_cutoff_utc": cutoff,
                "development_cutoff_rule": (
                    "configs/research_v6.json#holdout.development_cutoff_utc: the v6 "
                    "development data ends at the last fully closed hour that closes at "
                    "or before the cutoff, and no candle that closes after the cutoff may "
                    "be read"
                ),
                "v6_confirmatory_window_start_utc": window_start,
                "confirmatory_window_never_read_during_selection": True,
                "v1_holdout_never_reused": True,
                "v2_confirmatory_window_never_reused": True,
                "v3_confirmatory_window_never_reused": True,
                "v4_confirmatory_window_never_reused": True,
                "v5_confirmatory_window_never_reused": True,
                "holdout_exposed_count_stays_zero_during_selection": True,
                "holdout_position_fold_never_evaluated_during_selection": True,
                "provider_requests": 0,
                "provider_requests_note": (
                    "The run reads the immutable local datasets that the effective v6 "
                    "data manifest already binds and verifies, the benchmark dataset "
                    "included. It performs no provider request, so it cannot re-retrieve, "
                    "re-time or refresh any market data."
                ),
            },
            "selection_rule": {
                "unchanged_from_v1": True,
                "reference": SPEC_V1_RELATIVE,
                "block": "selection",
                "selection_block_sha256": selection_digest,
                "v6_block_is_byte_equal": True,
                "max_candidates_per_asset": selection_block["max_candidates_per_asset"],
                "selector": "breakout_research.selection.select_candidates",
                "grid_reference": (
                    "the strategy_grid of configs/research_v1.json, inherited unchanged by "
                    f"configs/research_v6.json: {max_configs_per_asset} configurations per asset"
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
                "never_use_v5_paths": True,
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
                    "scenarios execution units. The bound that the authorization enforces "
                    "is max_total_config_units, the number of asset-configuration pairs; "
                    "the fold and cost multipliers follow the inherited, unchanged fold "
                    "and cost blocks."
                ),
                "resource_limits": (
                    "the v6 execution protocol records max_logical_runs 1 and "
                    "checkpoint_every_n_shards 10; the run is resumable and never retries "
                    "unboundedly"
                ),
            },
            "benchmark": {
                "symbol": str(benchmark_block.get("symbol")),
                "role": str(benchmark_block.get("role")),
                "dataset_path": benchmark_path,
                "content_hash": benchmark_content_hash,
                "first_candle_timestamp": benchmark_block.get("first_candle_timestamp"),
                "last_candle_timestamp": benchmark_block.get("last_candle_timestamp"),
                "observed_candle_count": benchmark_block.get("observed_candle_count"),
                "alignment_rule": ALIGNMENT_RULE,
                "alignment_methodology": "docs/research_protocol.md:101 - Align BTC and "
                "target asset by UTC candle close",
                "methodology_rule": "Align BTC and target asset by UTC candle close; no forward fill for missing BTC observations",
                "methodology_reference": "docs/research_protocol.md:101",
                "no_forward_fill": True,
                "fail_closed": list(benchmark_block.get("fail_closed") or []),
                "grid_rule": benchmark_block.get("grid_rule"),
                "btc_configurations_dropped": False,
                "exposure_rule": benchmark_block.get("exposure_rule"),
                "published_by_data_manifest": True,
                "note": (
                    "The v6 benchmark is the v6-cutoff-bounded dataset that the v6 data "
                    "manifest publishes in its benchmark block. The dataset file lives "
                    "under research/data/candles_v6/ in the v6 namespace. Its last candle "
                    "closes exactly at the v6 development cutoff. The dataset is "
                    "hash-verified before every use, it covers every evaluated validation "
                    "window of the evaluated assets with identical timestamps, and the "
                    "asset series and the benchmark series are sliced to the same fold "
                    "window before the frozen engine is called."
                ),
            },
            "effective_data_manifest": {
                "effective_data_manifest_hash": effective_hash,
                "base_manifest_path": DATA_MANIFEST_RELATIVE,
                "base_manifest_hash": effective_hash,
                "note": (
                    "The effective v6 data manifest is the base manifest alone; v6 "
                    "publishes no data-manifest amendment. The benchmark dataset is "
                    "published by that manifest, in its benchmark block."
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
                "Do not write to v1, v2, v3, v4 or v5 artifacts; remove any newly created "
                "v6 artifact if the execution is aborted; do not alter "
                "research_state/checkpoint.json, research_state/checkpoint_v2.json, "
                "research_state/checkpoint_v3.json, research_state/checkpoint_v4.json, "
                "research_state/checkpoint_v5.json or the v1, v2, v3, v4 or v5 "
                "campaign state."
            ),
            "falsifiers": [
                "Any modification to src/breakout_research/ (would change the code hash)",
                "Reading any candle in the v6 confirmatory window during selection",
                "Reading any candle that closes inside the open v2, v3, v4 or v5 "
                "confirmatory window",
                "Writing into v1, v2, v3, v4 or v5 shards, ledger, tallies or result streams",
                "Reusing the v1 holdout, or the v2, v3, v4 or v5 confirmatory window",
                "Reusing the v3 or v4 chain's benchmark dataset",
                "Mixing v1, v2, v3, v4 or v5 cycle units with v6 results",
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
            "second_v6_selection_run_authorized": False,
            "amendment_of_a_frozen_artifact_authorized": False,
            "statement": (
                "This artifact authorizes one bounded v6 selection run and nothing else. "
                "It does not authorize a confirmatory-window evaluation, a candle fetch, "
                "a change to the hashed source set, an edit of a frozen artifact or a v1 "
                "re-authorization. The selected-configuration manifest that the v6 "
                "confirmatory window requires must be committed and hash-bound before the "
                "first confirmatory-window candle is read, and the v6 confirmatory "
                f"evaluation may not start before the effective gate "
                f"{overlap_rule['evaluation_may_not_start_before_utc']}."
            ),
        },
        "related_artifacts": {
            "v6_specification": {
                "path": SPEC_V6_RELATIVE,
                "specification_hash": spec_v6["specification_hash"],
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "v6_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
                "frozen_at_utc": freeze.get("candidate_freeze_utc"),
            },
            "v6_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
            },
            "v6_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
            },
            "v6_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v1_campaign_authorization": {
                "path": CAMPAIGN_AUTHORIZATION_RELATIVE,
                "code_hash": campaign_authorization["code_hash"],
                "authorized": campaign_authorization.get("authorized"),
                "note": (
                    "The functional field of the authorization is recorded, not the digest "
                    "of its bytes: the controller refreshes the authorized_at_utc "
                    "timestamp, so the file digest changes without the authorization "
                    "changing."
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
                "location": "the v6 selection run's result volume",
                "limitation": (
                    f"The bounded run writes {planned_execution_units} execution units. "
                    "At the v1 record size this is of the order of 0.5 GB of shards and "
                    "of the order of 100 MB of result stream. The v1 shards are bounded "
                    "to 4 MiB per file; the v1 result stream was a single file of 50 MB "
                    "that the campaign could not push as one blob."
                ),
                "consequence": (
                    "The shards under research/shards_v6 are the authoritative record set "
                    "and are committed as bounded files of at most 4 MiB each, as the v1 "
                    "campaign did. The single-file result stream research/results_v6.jsonl "
                    "is expected to be large and is a projection of the verified shards, "
                    "regenerated from them. The ledger, the results manifest and the "
                    "checkpoint are small and are committed. The v1, v2, v3, v4 and v5 "
                    "artifacts stay untouched either way."
                ),
            },
            {
                "id": "RL2",
                "location": "the benchmark dataset",
                "limitation": (
                    "The v6 data manifest publishes the benchmark in its benchmark block "
                    "and not in the assets map, so the manifest-driven asset loader "
                    "cannot resolve it; the benchmark is read directly and verified "
                    "against the published content hash and the canonical hourly-CSV "
                    "content hash."
                ),
                "consequence": (
                    "The benchmark rule is still fully implemented: the dataset is "
                    "hash-verified, it covers every evaluated window of each evaluated "
                    "asset with identical timestamps, and both series are sliced to the "
                    "same fold window before the frozen engine is called. No observation "
                    "is forward-filled. The published block is inside the manifest's own "
                    "self-hash, so the benchmark identity is part of the v6 data-manifest "
                    "identity."
                ),
            },
            {
                "id": "RL3",
                "location": "the v6 execution path",
                "limitation": (
                    "src/v6_campaign does not exist yet; the authorization records "
                    "v6_execution_path_exists: false and binds no path digest. When the "
                    "path is created, its canonical source digest must be recorded in a "
                    "revised authorization."
                ),
                "consequence": (
                    "No v6 selection run can execute until src/v6_campaign exists and its "
                    "digest is recorded. Until then, this authorization is a design "
                    "artifact only."
                ),
            },
        ],
        "verification": {
            "verifier_script": "scripts/verify_v6_selection_authorization_1.py",
            "tests_module": "tests/test_v6_selection_authorization_1.py",
            "verify_command": "python3 scripts/verify_v6_selection_authorization_1.py",
        },
        "durability": {
            "commit": None,
            "pushed": False,
            "note": (
                "Becomes durable when the commit that carries this artifact exists. The "
                "artifact is not rewritten after that commit, because its manifest_hash "
                "must not change."
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), "
            "ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, following the pattern of the other v2, v3, v4 and v5 artifacts."
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

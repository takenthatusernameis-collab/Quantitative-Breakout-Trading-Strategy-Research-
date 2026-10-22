#!/usr/bin/env python3
"""Build the preregistered v6 confirmatory runbook.

This producer writes ``configs/research_v6_confirmatory_runbook_1.json``: the
versioned, hash-bound artifact that fixes the operator procedure of the single
authorized v6 confirmatory run, so that the session that executes it follows a
procedure that was written before the run rather than one invented while
running it.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records the procedure.
It authorizes no candle read, no evaluation and no second run.

Everything the runbook records is re-derived from the repository:

* the scope, the window bounds and the gates from the v6 candidate freeze and
  the four freezes that own the earlier windows;
* the decision rule from the unchanged v1 selection rule and the v1 status
  vocabulary;
* the benchmark from the v6 data manifest and the dataset's own bytes;
* the code identity from the hashed source tree and the campaign authorization.

The v6 chain publishes its runbook **before** the v6 selection run, so the
runbook fixes the procedure and the scope rule; the selected configuration per
asset is bound at run time by the selection authorization and the
selected-configurations manifest, which the readiness test requires to exist
and to be hash-bound before the first payload read.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound.

Usage::

    python3 scripts/build_v6_confirmatory_runbook_1.py            # write
    python3 scripts/build_v6_confirmatory_runbook_1.py --force    # rewrite
    python3 scripts/build_v6_confirmatory_runbook_1.py --print    # print only
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
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    canonical_source_digest,
    compute_manifest_hash,
    published_manifest_hash,
    read_json,
    sha256_file,
)

#: The instant at which this runbook is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-22T05:10:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the runbook is bound to, relative to the repository root.
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"
PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v6_selected_configurations_manifest.json"
CONFIRMATORY_AUTHORIZATION_RELATIVE = "configs/research_v6_confirmatory_authorization_1.json"
ARTIFACT_RELATIVE = "configs/research_v6_confirmatory_runbook_1.json"

#: The run identity the single authorized run carries.
RUN_ID = "v6-confirmatory-20270120"
CAMPAIGN_ID = "v6-confirmatory-campaign"

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


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v6 confirmatory runbook from the hash-bound artifacts."""
    root = Path(repo_root)

    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    execution = read_json(root / EXECUTION_RELATIVE)
    protocol = read_json(root / PROTOCOL_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # --- the scope, re-derived from the freeze --------------------------------
    members = list((freeze.get("band") or {}).get("members") or [])
    in_scope = [str(entry["binance_pair"]) for entry in members if entry.get("validated") is True]
    excluded = [entry for entry in members if entry.get("validated") is not True]
    if not in_scope:
        raise SystemExit("the frozen v6 candidate set is empty")

    # --- the window, re-derived from the freeze and the earlier gates ---------
    window = freeze.get("confirmatory_window") or {}
    min_hours = int(window.get("min_hours"))
    window_start = str(window.get("opens_utc"))
    window_end = str(window.get("earliest_possible_end_utc"))

    # --- the decision rule, re-derived from the unchanged v1 selection rule ---
    selection = spec_v1.get("selection") or {}
    min_trades = int(selection.get("min_trades_total"))
    status_vocabulary = list((spec_v1.get("status") or {}).get("economic") or [])
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )

    # --- the benchmark, owned by the v6 data manifest -------------------------
    benchmark_block = data.get("benchmark") or {}
    benchmark_path = str(benchmark_block.get("dataset_path") or "")
    benchmark_hash = str(benchmark_block.get("content_hash") or "")
    if not benchmark_path:
        raise SystemExit("the v6 data manifest records no benchmark dataset")

    # --- the code identity ---------------------------------------------------
    source_digest = canonical_source_digest(root)

    # --- the selection authorization, if it is published ----------------------
    # Its identity is recomputed from the artifact's own bytes. A published
    # authorization is bound by that hash and is no longer recorded as
    # unpublished; an absent one is recorded as absent.
    selection_authorization_hash = published_manifest_hash(
        root, SELECTION_AUTHORIZATION_RELATIVE
    )
    if selection_authorization_hash is not None:
        declared = read_json(root / SELECTION_AUTHORIZATION_RELATIVE).get("manifest_hash")
        if declared != selection_authorization_hash:
            raise SystemExit(
                "the v6 selection authorization does not recompute its own manifest_hash"
            )
    selection_authorization_binding: Dict[str, Any] = {
        "path": SELECTION_AUTHORIZATION_RELATIVE,
        "manifest_hash": selection_authorization_hash,
    }
    if selection_authorization_hash is None:
        selection_authorization_binding["status"] = "NOT_YET_PUBLISHED"

    # --- the frozen anchors the run must not disturb -------------------------
    anchors: Dict[str, Dict[str, str]] = {}
    for label, relatives in (
        ("v1_evidence", (
            "configs/research_v1.json",
            "research/universe_manifest.json",
            "research/data_manifest.json",
            "research/candidate_manifest.json",
        )),
        ("v5_chain", (
            "configs/research_v5.json",
            "research/universe_manifest_v5.json",
            "research/data_manifest_v5.json",
            "configs/research_v5_candidate_freeze.json",
            "configs/research_v5_execution.json",
        )),
        ("v6_chain", (
            "configs/research_v6.json",
            "research/universe_manifest_v6.json",
            "research/data_manifest_v6.json",
            "configs/research_v6_candidate_freeze.json",
            "configs/research_v6_execution.json",
            "configs/research_v6_confirmatory_protocol.json",
        )),
    ):
        anchors[label] = {}
        for relative in relatives:
            path = root / relative
            if not path.exists():
                raise SystemExit(f"the anchored artifact {relative} is missing")
            anchors[label][relative] = sha256_file(path)

    document: Dict[str, Any] = {
        "artifact": "v6_confirmatory_runbook",
        "artifact_version": "v6-confirmatory-runbook-1",
        "protocol_version": "v6",
        "universe_version": "v6",
        "created_utc": CREATED_UTC,
        "runbook_status": "PREREGISTERED_OPERATOR_PROCEDURE_NOT_EXECUTED",
        "specification_purpose": (
            "Fix the operator procedure of the single authorized v6 confirmatory run, so that the "
            "session that executes it follows a procedure written before the run rather than one "
            "invented while running it. This artifact authorizes no candle read, no evaluation "
            "and no second run."
        ),
        "applies_to": {
            "run_id": RUN_ID,
            "campaign_id": CAMPAIGN_ID,
            "run_phase": "confirmatory_window_evaluation",
            "window_start_utc": window_start,
            "window_end_utc": window_end,
            "minimum_closed_hourly_candles": min_hours,
            "evaluation_window_rule": (
                "The evaluated window is exactly the first minimum_closed_hourly_candles closed "
                "hourly candles at or after the window start, so it ends at the earliest instant "
                "the frozen boundary allows. The evaluated window's length does not depend on "
                "when the run happens, and the window may not be extended, shortened or re-based "
                "at run time."
            ),
            "in_scope_assets": in_scope,
            "in_scope_count": len(in_scope),
            "in_scope_configurations": None,
            "in_scope_configurations_rule": (
                "the configuration evaluated for an in-scope asset is the one published in "
                "research/v6_selected_configurations_manifest.json by the v6 selection run under "
                "the unchanged v1 selection rule; this runbook publishes before that run, so the "
                "readiness test requires the selected-configurations manifest to exist and to be "
                "hash-bound before the first payload read"
            ),
            "out_of_scope_assets_excluded_at_validation": [
                str(entry["binance_pair"]) for entry in excluded
            ],
            "out_of_scope_count": len(excluded),
            "out_of_scope_reasons": {
                str(entry["binance_pair"]): str(entry["exclusion_reason"]) for entry in excluded
            },
            "single_use_window": True,
            "benchmark_symbol": "BTCUSDT",
            "benchmark_is_not_a_candidate": True,
            "benchmark_is_counted_as_an_exposed_asset": True,
        },
        "binding_identities": {
            "authorization": {
                "path": CONFIRMATORY_AUTHORIZATION_RELATIVE,
                "manifest_hash": None,
                "status": "NOT_YET_PUBLISHED",
            },
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": None,
                "status": "NOT_YET_PUBLISHED",
            },
            "selection_authorization_1": selection_authorization_binding,
            "v6_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v6_data_manifest": {
                "path": DATA_RELATIVE,
                "manifest_hash": data.get("manifest_hash"),
            },
            "v6_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v6_specification": {
                "path": SPEC_V6_RELATIVE,
                "specification_hash": spec_v6.get("specification_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "portable": True,
                "hashed_set_root": "src/breakout_research",
                "hashed_set_digest": source_digest,
                "execution_path_root": "src/v6_confirmatory",
                "execution_path_digest": None,
                "execution_path_status": "NOT_YET_CREATED",
                "authorized_ordered_code_hash": str(authorization.get("code_hash") or ""),
                "note": (
                    "The identity of the run is the composite of the canonical digest of the "
                    "hashed v1 engine and the canonical digest of the confirmatory execution "
                    "path. The checkout-dependent ordered digest compute_code_hash() is an "
                    "environment fact and is never used as an identity."
                ),
            },
            "immutable_artifact_anchors": anchors,
            "decision_rule": {
                "criterion_count": 1,
                "authoritative_source": "configs/research_v1.json#selection",
                "criteria": [
                    "net_total_return > 0 at baseline costs (1x) over the confirmatory window",
                    "net_total_return > 0 at 2x costs over the confirmatory window",
                    f"closed_trades >= {min_trades} over the confirmatory window",
                    "the evaluated parameters are byte-identical to the frozen v6 candidate "
                    "manifest entry",
                ],
                "status_vocabulary": status_vocabulary,
                "status_vocabulary_is_not_extended": True,
                "no_secondary_criterion_is_applied": True,
            },
            "evaluation_rule": {
                "unchanged_v1_evaluation_metric": True,
                "unchanged_cost_scenarios": True,
                "cost_scenarios": list((spec_v1.get("costs") or {}).get("scenarios") or []),
                "baseline_costs": (spec_v1.get("costs") or {}).get("baseline"),
                "inherited_rules_blocks_digest": inherited_digest,
                "evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry": True,
                "no_retuning_reranking_or_grid_extension_on_window": True,
            },
            "bounds": {
                "window_start_utc": window_start,
                "window_end_utc": window_end,
                "minimum_closed_hourly_candles": min_hours,
                "evaluation_may_not_start_before_utc": window.get(
                    "evaluation_may_not_start_before_utc"
                ),
                "development_cutoff_utc": (spec_v6.get("holdout") or {}).get(
                    "development_cutoff_utc"
                ),
                "membership_rule": (
                    (spec_v6.get("holdout") or {}).get("confirmatory_window_membership") or {}
                ).get("rule"),
            },
            "deviation_disclosure": {
                "scope": "the completed v1 and v2 runs",
                "records_with_btc_filter": 124416,
                "total_v2_records": 497664,
                "evidence_path": "research/v3_evidence/v1_v2_btc_alignment_deviation.json",
                "v6_run_alignment": (
                    "the v6 run evaluates the BTC trend filter against the index-aligned v6 "
                    "benchmark dataset"
                ),
                "carried_into_the_final_report": True,
                "not_repaired": True,
            },
        },
        "operator_procedure": {
            "global_rules": [
                "the run is a single logical run: it may be resumed, never restarted",
                "every step is fail-closed: a step that cannot prove its precondition stops the "
                "run",
                "nothing is repaired: a mismatch is reported, not corrected",
                "every read of the window is counted in holdout_exposed_count",
                "no step contacts a provider except the readiness probe and the single retrieval",
                "the window benchmark series is retrieved with the window, never substituted",
                "the v1 holdout and the v2, v3, v4 and v5 confirmatory windows are never read",
                "the run may not start before the later of the four earlier gates and the v6 "
                "window's own earliest end",
            ],
            "ordered_steps": [
                {
                    "step": 1,
                    "action": (
                        "Confirm, before anything else, that the commit carrying this runbook, the "
                        "confirmatory protocol and the confirmatory authorization exists, that the "
                        "authorization is bound to the manifest_hash of this runbook and of the "
                        "protocol, and that the v6 selection authorization and the v6 "
                        "selected-configuration manifest exist and are hash-bound. If any of them "
                        "is missing or disagrees, stop with BLOCKED_EXTERNAL and read nothing."
                    ),
                },
                {
                    "step": 2,
                    "action": (
                        "Run the metadata-only readiness probe: one bounded request per metadata "
                        "endpoint, the primary host first and the documented failover host second. "
                        "It fetches no candle and does not increment holdout_exposed_count."
                    ),
                },
                {
                    "step": 3,
                    "action": (
                        "Retrieve the window once: for every in-scope asset and for the benchmark "
                        "series, in ascending symbol order, one request per asset, closed hourly "
                        "candles only, with the frozen failover, retry and backoff budget. A read "
                        "that returns a payload increments holdout_exposed_count."
                    ),
                },
                {
                    "step": 4,
                    "action": (
                        "Persist every retrieved dataset in the canonical hourly CSV of the frozen "
                        "sha256-canonical-hourly-csv-v1 scheme, together with a record that binds "
                        "it to the run id, the asset, the window bounds and its content hash. "
                        "Coverage gaps are recorded; interpolation is forbidden."
                    ),
                },
                {
                    "step": 5,
                    "action": (
                        "Build the window manifest: the window bounds, the retrieval timestamp, "
                        "the per-asset dataset hashes, the closed-candle counts, the coverage gaps, "
                        "the exposure events, the readiness record and the window benchmark "
                        "record."
                    ),
                },
                {
                    "step": 6,
                    "action": (
                        "Re-evaluate the authorization's preconditions with the readiness record, "
                        "the window manifest and the exposure counter. If a precondition no longer "
                        "holds, stop; do not repair it."
                    ),
                },
                {
                    "step": 7,
                    "action": (
                        "Evaluate every in-scope asset's frozen configuration over the window with "
                        "the unchanged v1 evaluation metric and the unchanged cost scenarios. The "
                        "576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                        "re-derived or re-ranked."
                    ),
                },
                {
                    "step": 8,
                    "action": (
                        "Grade every asset with the single preregistered promotion rule of "
                        "configs/research_v1.json#selection, which governs. No second confirmatory "
                        "criterion exists in the v6 line and none may be applied. The status "
                        "vocabulary is not extended: PROVISIONAL_HISTORICAL_SURVIVAL, "
                        "REJECTED_ON_HOLDOUT, INCONCLUSIVE and CANDIDATE_PENDING_HOLDOUT only. A "
                        "configuration with zero closed trades is INCONCLUSIVE and never "
                        "REJECTED_ON_HOLDOUT."
                    ),
                },
                {
                    "step": 9,
                    "action": (
                        "Write the eight authorized output paths in the fixed order, atomically, so "
                        "that a partial write is never observed."
                    ),
                },
                {
                    "step": 10,
                    "action": (
                        "Run the acceptance checks of this runbook and the verification commands "
                        "below, and record their exit statuses in the handoff."
                    ),
                },
            ],
            "readiness_probe": {
                "primary_host": "https://api.binance.com",
                "failover_host": "https://data-api.binance.vision",
                "endpoints": [
                    {"purpose": "provider server time", "path": "/api/v3/time"},
                    {
                        "purpose": "spot trading status of the in-scope pairs and of the benchmark pair",
                        "path": "/api/v3/exchangeInfo",
                    },
                ],
                "endpoint_order": [
                    "https://api.binance.com/api/v3/time",
                    "https://api.binance.com/api/v3/exchangeInfo",
                ],
                "failover_order": [
                    "https://data-api.binance.vision/api/v3/time",
                    "https://data-api.binance.vision/api/v3/exchangeInfo",
                ],
                "one_bounded_request_per_endpoint": True,
                "a_host_failure_is_failed_over_not_retried": True,
                "both_statuses_are_recorded_with_timestamps": True,
                "fetches_no_candle": True,
                "increments_holdout_exposed_count": False,
                "max_retries": 3,
                "backoff_seconds": 5,
                "rate_limit_per_minute": 1200,
                "failover_policy": (
                    "One bounded request to the primary host; on a host-level failure one bounded "
                    "request to the documented failover host; both statuses are recorded. A "
                    "retryable status is retried on the active endpoint within the frozen retry "
                    "budget and backoff. No candle is fetched by the probe."
                ),
            },
            "retrieval": {
                "provider": "binance",
                "endpoint": "https://api.binance.com/api/v3/klines",
                "failover_endpoints": ["https://data-api.binance.vision/api/v3/klines"],
                "interval": "1h",
                "closed_candles_only": True,
                "retrieval_happens_once": True,
                "one_request_per_asset": True,
                "asset_order": "ascending symbol order",
                "retrieved_series": sorted(in_scope + ["BTCUSDT"]),
                "window_bounds": {
                    "window_start_utc": window_start,
                    "window_end_utc": window_end,
                    "minimum_closed_hourly_candles": min_hours,
                },
                "dataset_hash_algorithm": "sha256-canonical-hourly-csv-v1",
                "dataset_persistence": (
                    "the canonical hourly CSV next to a record that binds it to (run_id, asset, "
                    "window bounds) and to its content hash, under the shard directory of the run"
                ),
                "gaps_are_recorded": True,
                "interpolation_is_forbidden": True,
            },
            "benchmark": {
                "symbol": "BTCUSDT",
                "role": "trend_filter_and_benchmark",
                "benchmark_is_not_a_candidate": True,
                "window_benchmark_series_required": True,
                "window_benchmark_retrieval_happens_once": True,
                "window_benchmark_is_hash_verified": True,
                "development_benchmark_may_be_reused": False,
                "development_benchmark_path": benchmark_path,
                "development_benchmark_content_hash": benchmark_hash,
                "alignment_rule": (
                    "the asset series and the benchmark series are sliced to the same fold window "
                    "before the frozen engine is called"
                ),
                "alignment_reference": "docs/research_protocol.md:101",
                "no_forward_fill": True,
                "fail_closed": [
                    "the benchmark series is missing",
                    "the benchmark series is shorter than the evaluated window",
                    "the benchmark series is not index-aligned with the asset series",
                ],
                "btc_configurations_dropped": False,
                "grid_rule": (
                    "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                    "re-derived or re-ranked"
                ),
                "source_of_truth": (
                    "the window benchmark series is retrieved with the window and is bound by its "
                    "own content hash; the development benchmark is never substituted for it"
                ),
            },
            "evaluation": {
                "unchanged_v1_evaluation_metric": True,
                "unchanged_cost_scenarios": True,
                "cost_scenarios": list((spec_v1.get("costs") or {}).get("scenarios") or []),
                "baseline_costs": (spec_v1.get("costs") or {}).get("baseline"),
                "evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry": True,
                "no_retuning_reranking_or_grid_extension_on_window": True,
                "authoritative_criterion": "configs/research_v1.json#selection",
                "no_secondary_criterion_is_applied": True,
                "status_vocabulary": status_vocabulary,
                "outcomes": [
                    "PROVISIONAL_HISTORICAL_SURVIVAL",
                    "REJECTED_ON_HOLDOUT",
                    "INCONCLUSIVE",
                ],
                "assets_without_candidate_status": "NO_CANDIDATE",
            },
            "write_order": [
                {
                    "order": 1,
                    "artifact": "window_manifest",
                    "path": "research/v6_confirmatory_window_manifest.json",
                    "content": (
                        "the window bounds, the retrieval timestamp, the per-asset dataset hashes, "
                        "the closed-candle counts, the coverage gaps, the exposure events, the "
                        "readiness record and the window benchmark record"
                    ),
                },
                {
                    "order": 2,
                    "artifact": "shards_dir",
                    "path": f"research/shards_v6_confirmatory/{CAMPAIGN_ID}/shard_000000.jsonl",
                    "content": "the per-asset result rows, one shard file of the confirmatory campaign",
                },
                {
                    "order": 3,
                    "artifact": "results_stream",
                    "path": "research/results_v6_confirmatory.jsonl",
                    "content": "the result rows as a single JSONL stream, the projection of the shard",
                },
                {
                    "order": 4,
                    "artifact": "ledger",
                    "path": "research/ledger_v6_confirmatory.json",
                    "content": (
                        "the run identity, the scope, the per-asset outcomes, the exposure count "
                        "and the completion state"
                    ),
                },
                {
                    "order": 5,
                    "artifact": "results_manifest",
                    "path": "research/results_manifest_v6_confirmatory.json",
                    "content": "the shard inventory, the record count and the content digests",
                },
                {
                    "order": 6,
                    "artifact": "checkpoint",
                    "path": "research_state/checkpoint_v6_confirmatory.json",
                    "content": "the checkpoint counters, including holdout_exposed_count",
                },
                {
                    "order": 7,
                    "artifact": "report",
                    "path": "reports/confirmatory_evaluation_v6.json",
                    "content": "the machine-readable confirmatory report",
                },
                {
                    "order": 8,
                    "artifact": "report_markdown",
                    "path": "reports/confirmatory_report_v6.md",
                    "content": "the human-readable confirmatory report",
                },
            ],
        },
        "failure_decision_table": [
            {
                "failure_mode": "ABORT_BEFORE_THE_FIRST_PAYLOAD_READ",
                "detection": "the pre-flight, the readiness probe or the precondition re-check fails",
                "response": (
                    "roll back every artifact the run created, leave holdout_exposed_count at 0 and "
                    "release the attempt"
                ),
                "exposure_effect": "none: the window was never read",
                "artifact_state": "no confirmatory artifact remains",
                "resumable": "the single authorized attempt is still available",
                "reported_as": "the abort reason in the handoff",
            },
            {
                "failure_mode": "ABORT_AFTER_A_PAYLOAD_READ",
                "detection": "the run fails after the first dataset has been read",
                "response": (
                    "record the run as EXPOSED_ABORTED, keep the exposure in place, keep the "
                    "already retrieved and hash-verified datasets, and resume the same run from "
                    "them; never read the window again"
                ),
                "exposure_effect": "the exposure stays: the window is spent",
                "artifact_state": (
                    "the confirmatory checkpoint records EXPOSED_ABORTED and the exposure events; "
                    "no report is produced"
                ),
                "resumable": "yes, as a resume of the same run, bounded by max_retries_on_technical_failure",
                "reported_as": (
                    "the report must state that the window was consumed without a completed "
                    "evaluation"
                ),
            },
            {
                "failure_mode": "PROVIDER_OR_RATE_LIMIT_FAILURE",
                "detection": "a transport error, a timeout, HTTP 429 or another retryable status",
                "response": (
                    "fail over a host failure to the documented failover host and record both "
                    "statuses; retry a transient failure on the active endpoint within the frozen "
                    "retry budget with the frozen backoff, then resume the run"
                ),
                "exposure_effect": "a read that returned a payload is counted; a failed request is not",
                "artifact_state": "the verified datasets of the completed assets are kept for the resume",
                "resumable": "yes, within the frozen retry budget",
                "reported_as": "the provider statuses with their timestamps in the handoff",
            },
            {
                "failure_mode": "DATASET_HASH_MISMATCH",
                "detection": "the recomputed content hash of a persisted dataset differs from the recorded one",
                "response": (
                    "refuse the dataset; do not repair it, do not re-fetch it and do not re-read "
                    "the window, because a re-read would be a second read of a single-use window"
                ),
                "exposure_effect": "the read is counted: the window is spent",
                "artifact_state": "the run is recorded as EXPOSED_ABORTED and the mismatch is reported",
                "resumable": "no: the resume may only reuse a hash-verified dataset",
                "reported_as": "the mismatch, the asset and the two digests",
            },
            {
                "failure_mode": "ZERO_TRADE_OUTCOME",
                "detection": "an in-scope configuration produced zero closed trades on the window",
                "response": (
                    "grade it INCONCLUSIVE; it is never graded REJECTED_ON_HOLDOUT and never "
                    "graded a failure"
                ),
                "exposure_effect": "the read is counted",
                "artifact_state": "the run completes normally",
                "resumable": "not applicable: the run is complete",
                "reported_as": "the zero-trade outcome in the report",
            },
            {
                "failure_mode": "NO_CANDIDATE_OUTCOME",
                "detection": "the v6 selection run published no candidate for an in-scope asset",
                "response": (
                    "the asset is reported as NO_CANDIDATE and is not evaluated; the scope is not "
                    "widened to replace it"
                ),
                "exposure_effect": "the read is counted for the assets that were evaluated",
                "artifact_state": "the run completes normally",
                "resumable": "not applicable: the run is complete",
                "reported_as": "the asset and its NO_CANDIDATE status in the report",
            },
            {
                "failure_mode": "EVALUATION_CRITERION_CONFLICT",
                "detection": "two artifacts disagree about what passing the window means",
                "response": (
                    "stop, publish a versioned amendment that reconciles them, and do not apply a "
                    "second criterion"
                ),
                "exposure_effect": "the exposure stays: the window is spent",
                "artifact_state": "the run is recorded as EXPOSED_ABORTED",
                "resumable": "no: the amendment must precede any re-evaluation",
                "reported_as": "the two conflicting statements and the amendment",
            },
            {
                "failure_mode": "WINDOW_NOT_READY",
                "detection": "the window holds fewer than the minimum closed hourly candles",
                "response": "stop with BLOCKED_EXTERNAL and read nothing",
                "exposure_effect": "none: the window was never read",
                "artifact_state": "no confirmatory artifact remains",
                "resumable": "yes, at or after the window's earliest possible end",
                "reported_as": "the observed candle count and the earliest possible end",
            },
            {
                "failure_mode": "UNAUTHORIZED_PATH_OR_ARTIFACT",
                "detection": "the run would write outside the eight authorized output paths",
                "response": "stop; a new path requires a new versioned amendment",
                "exposure_effect": "whatever was already read stays counted",
                "artifact_state": "the unauthorized write is removed",
                "resumable": "only after the amendment",
                "reported_as": "the attempted path in the handoff",
            },
        ],
        "acceptance_checks": {
            "checks": [
                "the runbook, the confirmatory protocol and the confirmatory authorization are "
                "committed and their manifest hashes match the recorded ones",
                "the v6 selection authorization and the v6 selected-configuration manifest exist "
                "and are hash-bound, and the selected configuration of every in-scope asset is "
                "byte-identical to the frozen manifest entry",
                "the window holds at least the minimum number of closed hourly candles",
                "every retrieved dataset is in the canonical hourly CSV form and its recomputed "
                "content hash matches the recorded one",
                "holdout_exposed_count equals the number of reads that returned a payload",
                "the evaluation used the unchanged v1 metric and the unchanged cost scenarios, and "
                "no configuration was dropped, re-derived or re-ranked",
                "every in-scope asset has a published outcome and every out-of-scope asset is "
                "named with its reason",
                "no artifact outside the eight authorized output paths was written",
                "the v1 holdout and the v2, v3, v4 and v5 confirmatory windows were not read",
            ],
            "verification_commands": [
                "python3 scripts/verify_v6_confirmatory_runbook_1.py",
                "python3 scripts/verify_v6_confirmatory_protocol.py",
                "python3 scripts/verify_v6_execution.py",
                "python3 scripts/verify_research_v6_candidate_freeze.py",
                "python3 scripts/verify_research_v6_manifests.py",
                "python3 scripts/verify_research_v6_spec.py",
                "PYTHONPATH=src python3 -m pytest tests/ -q",
            ],
            "the_output_is_accepted_only_when": (
                "every acceptance check passes, the exposure count reconciles with the recorded "
                "exposure events, and the report names every in-scope asset with its outcome and "
                "every out-of-scope asset with its reason"
            ),
        },
        "prohibitions": [
            "no second confirmatory decision criterion",
            "no re-tuning, re-weighting or re-ranking on the window",
            "no grid extension on the window",
            "no second read of the window",
            "no read of the v1 holdout",
            "no read of the v2, v3, v4 or v5 confirmatory windows",
            "no forward fill of the benchmark series",
            "no dropped btc_ema_168 configuration",
            "no interpolation of a missing candle",
            "no substitution of the development benchmark for the window benchmark",
            "no write outside the eight authorized output paths",
            "no repair of a mismatch: a mismatch is reported",
            "no extension of the status vocabulary",
            "no re-run of the confirmatory evaluation",
            "no reporting of a zero-trade configuration as a failure",
            "no hiding of an asset without a candidate",
            "no modification of the v1-v5 frozen artifacts",
            "no edit under src/breakout_research",
            "no read before the later of the four earlier gates and the v6 window's own earliest end",
        ],
        "related_artifacts": {
            "confirmatory_authorization_1": {
                "path": CONFIRMATORY_AUTHORIZATION_RELATIVE,
                "manifest_hash": None,
            },
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": None,
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_authorization_hash,
            },
            "v6_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v6_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v6_specification": {
                "path": SPEC_V6_RELATIVE,
                "specification_hash": spec_v6.get("specification_hash"),
            },
            "v6_data_manifest": {
                "path": DATA_RELATIVE,
                "manifest_hash": data.get("manifest_hash"),
            },
            "v6_universe_manifest": {
                "path": UNIVERSE_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "confirmatory_execution_path": {
                "root": "src/v6_confirmatory",
                "status": "NOT_YET_CREATED",
                "rule": (
                    "the confirmatory execution path is a new directory outside the hashed set; "
                    "its canonical digest is recorded in the confirmatory authorization"
                ),
            },
        },
        "authorizes_a_candle_read": False,
        "authorizes_an_evaluation": False,
        "authorizes_a_second_run": False,
        "durability": {
            "rule": (
                "The runbook takes effect when this artifact is committed. No confirmatory-window "
                "candle may be read and no evaluation may run before the commit that carries this "
                "artifact exists."
            ),
            "runbook_commit": None,
            "runbook_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v6_confirmatory_runbook_1.py",
            "verify_command": "python3 scripts/verify_v6_confirmatory_runbook_1.py",
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

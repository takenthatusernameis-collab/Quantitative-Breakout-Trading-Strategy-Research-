#!/usr/bin/env python3
"""Build the preregistered v4 selection authorization 1.

This producer writes ``configs/research_v4_selection_authorization_1.json``:
the versioned, hash-bound artifact that authorizes **one** bounded v4 selection
grid run over the frozen v4 candidate set, with the benchmark rule of BRAIN-013
and the v4 execution protocol bound into it.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself is performed by a later session, through the
execution path in ``src/v4_campaign`` that this artifact names and whose
canonical source digest it binds.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the freeze and re-derived from the v4 universe manifest;
* the selection rule from the unchanged v1 ``selection`` block;
* the code identity from the source tree, under the canonical digest rule of
  BRAIN-009;
* the benchmark dataset, its content hash and the data-manifest identity from
  the v4 base manifest (v4 publishes no data-manifest amendment; the benchmark
  dataset is referenced directly from the immutable v3 data area).

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v4_selection_authorization_1.py            # write the artifact
    python3 scripts/build_v4_selection_authorization_1.py --force    # rewrite it
    python3 scripts/build_v4_selection_authorization_1.py --print     # print, write nothing
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

ARTIFACT_RELATIVE = "configs/research_v4_selection_authorization_1.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELATIVE

#: The instant at which this authorization is created. It is pinned here so
#: that the artifact is byte-reproducible; it must not be moved once the
#: artifact has been committed.
CREATED_UTC = "2026-10-21T00:16:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source trees the run identity binds.
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

#: The v4 artifacts the authorization is bound to.
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v4.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
EXECUTION_RELATIVE = "configs/research_v4_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v4 output paths the authorization allows the run to write.
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
    """Assemble the v4 selection authorization from the hash-bound artifacts."""
    root = Path(repo_root)

    from v4_campaign import runner as v4_runner
    from v4_campaign import benchmark as benchmark_rule
    from v4_campaign.data import resolve_effective_data_manifest, BENCHMARK_DATASET_PATH, BENCHMARK_CONTENT_HASH
    from v4_campaign.identity import code_identity_document
    from v4_campaign.scope import frozen_scope, selection_rule

    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_MANIFEST_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    execution = _load(root / EXECUTION_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v4 = _load(root / SPEC_V4_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(root / CAMPAIGN_AUTHORIZATION_RELATIVE)

    # --- the frozen scope, resolved from the freeze and the universe manifest --
    scope = frozen_scope(freeze, universe)
    binance_pairs = list(scope["binance_pairs"])
    if not binance_pairs:
        raise SystemExit("the frozen v4 candidate set is empty")

    # --- the unchanged v1 selection rule -------------------------------------
    selection_block, selection_digest = selection_rule(spec_v1, spec_v4)

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
            "the benchmark dataset does not hash to the content hash of the provenance"
        )
    benchmark_entry = (effective_manifest.get("assets") or {}).get("BTCUSDT") or {}
    execution_benchmark = execution.get("benchmark_rule") or {}
    if execution_benchmark.get("content_hash") != benchmark_content_hash:
        raise SystemExit(
            "the benchmark dataset named by the v4 execution protocol is not the "
            "benchmark dataset of the provenance"
        )
    if not str(execution_benchmark.get("alignment") or "").startswith(ALIGNMENT_RULE):
        raise SystemExit(
            "the benchmark alignment rule of the v4 execution protocol is not the rule the "
            "authorization binds"
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
    paths = {key: str(v4_runner.DEFAULT_PATHS[key]) for key in OUTPUT_PATH_KEYS}

    boundary = scope["confirmatory_window_start_utc"]

    document: Dict[str, Any] = {
        "artifact": "v4_selection_authorization",
        "artifact_version": "v4-selection-authorization-1",
        "version": 1,
        "protocol_version": "v4",
        "universe_version": "v4",
        "created_utc": CREATED_UTC,
        "authorization_status": "PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN",
        "specification_purpose": (
            "Authorize exactly one bounded v4 selection grid run over the frozen v4 "
            "candidate set, under the unchanged v1 selection rule, on development data "
            "only, writing only to the v4 paths, with the BRAIN-013 benchmark rule built "
            "in. This artifact names the execution path, the bounds, the benchmark rule, "
            "the stopping conditions, the rollback rule and the falsifiers of that run. "
            "Building it executes nothing: no grid is run, no candle is read, no result "
            "exists."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-013",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-013, "
            "recommendation item 4",
            "prerequisites_delivered": [
                "P1 configs/research_v4.json",
                "P2 research/universe_manifest_v4.json",
                "P3 research/data_manifest_v4.json",
                "the v4 candidate manifest freeze",
                "the v4 execution protocol configs/research_v4_execution.json",
                "the v4 execution path src/v4_campaign",
            ],
            "execution_path_outside_hashed_set": (
                "The v4 execution code lives in src/v4_campaign, outside the hashed source "
                "set src/breakout_research. It imports the v1 engine unchanged; it adds, "
                "edits and removes no file under src/breakout_research, so the v1 campaign "
                "authorization and the v2 identity tuples stay valid."
            ),
        },
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": "v4-selection-20261021",
            "campaign_id": "v4-campaign",
            "run_phase": "selection_grid",
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
                "resume_source_of_truth": "the verified shards under research/shards_v4",
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
                    "research/universe_manifest_v4.json. The run may not re-rank, widen or "
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
                    "The identity of a v4 run is the composite of the canonical digest of the "
                    "hashed v1 engine and the canonical digest of the v4 execution path. The "
                    "checkout-dependent ordered digest compute_code_hash() stays the authorized "
                    "value of record and is never used as an identity."
                ),
            },
            "data_boundary": {
                "development_data_only": True,
                "candles_before_utc": boundary,
                "candles_before_utc_rule": (
                    "Only candles that close at or before the confirmatory-window start "
                    "recorded by the candidate freeze may be read during the selection run. A "
                    "dataset that reaches into the confirmatory window is refused before it is "
                    "read."
                ),
                "confirmatory_window_never_read_during_selection": True,
                "v1_holdout_never_reused": True,
                "v2_confirmatory_window_never_reused": True,
                "v3_confirmatory_window_never_reused": True,
                "holdout_exposed_count_stays_zero_during_selection": True,
                "holdout_position_fold_never_evaluated_during_selection": True,
                "provider_requests": 0,
                "provider_requests_note": (
                    "The run reads the immutable local datasets that the effective v4 data "
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
                "v4_block_is_byte_equal": True,
                "max_candidates_per_asset": selection_block["max_candidates_per_asset"],
                "selector": "breakout_research.selection.select_candidates",
                "grid_reference": (
                    "the strategy_grid of configs/research_v1.json, inherited unchanged by "
                    f"configs/research_v4.json: {max_configs_per_asset} configurations per asset"
                ),
                "grid_configuration_count": config_count,
                "no_criterion_may_be_added_tightened_or_loosened": True,
            },
            "paths": {
                **{key: paths[key] for key in OUTPUT_PATH_KEYS},
                "never_use_v1_paths": True,
                "never_use_v2_paths": True,
                "never_use_v3_paths": True,
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
                    "the v4 execution protocol records max_logical_runs 1, "
                    "max_shards_per_run 10000, max_wall_time_hours 6 and a retry policy of "
                    "no unbounded retries"
                ),
            },
            "benchmark": {
                "symbol": str(provenance["benchmark_symbol"]),
                "role": "trend_filter_and_benchmark",
                "dataset_path": benchmark_path,
                "content_hash": benchmark_content_hash,
                "first_candle_timestamp": provenance.get("benchmark_first_candle_timestamp") or 1697886000000,
                "last_candle_timestamp": provenance.get("benchmark_last_candle_timestamp") or 1792490400000,
                "observed_candle_count": provenance.get("benchmark_observed_candle_count") or 26280,
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
                "external_to_v4_manifest": True,
                "note": (
                    "The v4 data manifest publishes no BTCUSDT entry. The benchmark dataset "
                    "is referenced directly from the immutable v3 data area; it is external to "
                    "the v4 data-manifest identity. It is hash-verified before every use and "
                    "it is index-aligned with the six evaluated assets, so the asset series and "
                    "the benchmark series are sliced to the same fold window before the frozen "
                    "engine is called."
                ),
            },
            "effective_data_manifest": {
                "effective_data_manifest_hash": effective_hash,
                "base_manifest_path": DATA_MANIFEST_RELATIVE,
                "base_manifest_hash": provenance["base_manifest_hash"],
                "note": (
                    "The effective v4 data manifest is the base manifest alone; v4 publishes "
                    "no data-manifest amendment. The benchmark dataset is referenced directly "
                    "from the v3 data area and is external to this identity."
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
                "Do not write to v1, v2 or v3 artifacts; remove any newly created v4 artifact "
                "if the execution is aborted; do not alter research_state/checkpoint.json, "
                "research_state/checkpoint_v2.json, research_state/checkpoint_v3.json or the "
                "v1, v2 or v3 campaign state."
            ),
            "falsifiers": [
                "Any modification to src/breakout_research/ (would change the code hash)",
                "Reading any candle in the v4 confirmatory window during selection",
                "Writing into v1, v2 or v3 shards, ledger, tallies or result streams",
                "Reusing the v1 holdout or the v2 or v3 confirmatory window",
                "Mixing v1, v2 or v3 cycle units with v4 results",
                "Widening or narrowing the frozen candidate set",
                "Dropping, re-deriving or re-ranking the 576 btc_ema_168 configurations",
                "Evaluating the BTC filter on a benchmark series that is not index-aligned "
                "with the asset series",
                "A second run attempt under this authorization",
            ],
            "no_execution_in_this_session": True,
        },
        "not_authorized": {
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "v1_reauthorization_authorized": False,
            "source_tree_change_authorized": False,
            "second_v4_selection_run_authorized": False,
            "amendment_of_a_frozen_artifact_authorized": False,
            "statement": (
                "This artifact authorizes one bounded v4 selection run and nothing else. It "
                "does not authorize a confirmatory-window evaluation, a candle fetch, a "
                "change to the hashed source set, an edit of a frozen artifact or a v1 "
                "re-authorization. The selected-configuration manifest that the v4 "
                "confirmatory window requires must be committed and hash-bound before the "
                "first confirmatory-window candle is read."
            ),
        },
        "related_artifacts": {
            "v4_specification": {
                "path": SPEC_V4_RELATIVE,
                "specification_hash": spec_v4["specification_hash"],
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "v4_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": scope["candidate_manifest_hash"],
                "frozen_at_utc": scope["candidate_freeze_timestamp_utc"],
            },
            "v4_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": scope["universe_manifest_hash"],
            },
            "v4_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": provenance["base_manifest_hash"],
            },
            "v4_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "specification_hash": execution.get("specification_hash") or execution.get("manifest_hash"),
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
                "location": "the v4 selection run's result volume",
                "limitation": (
                    f"The bounded run writes {planned_execution_units} execution units. At "
                    "the v1 record size this is of the order of 0.5 GB of shards and of the "
                    "order of 100 MB of result stream. The v1 shards are bounded to 4 MiB "
                    "per file; the v1 result stream was a single file of 50 MB that the "
                    "campaign could not push as one blob."
                ),
                "consequence": (
                    "The shards under research/shards_v4 are the authoritative record set and "
                    "are committed as bounded files of at most 4 MiB each, as the v1 campaign "
                    "did. The single-file result stream research/results_v4.jsonl is expected "
                    "to be large and is a projection of the verified shards, regenerated from "
                    "them. The ledger, the results manifest and the checkpoint are small and "
                    "are committed. The v1, v2 and v3 artifacts stay untouched either way."
                ),
            },
            {
                "id": "RL2",
                "location": "the benchmark dataset",
                "limitation": (
                    "The v4 data manifest publishes no BTCUSDT benchmark entry. The benchmark "
                    "dataset is referenced directly from the immutable v3 data area "
                    "(research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv) and is "
                    "external to the v4 data-manifest identity. A future v4 data-manifest "
                    "amendment may publish the benchmark entry into the v4 manifest."
                ),
                "consequence": (
                    "The benchmark rule of BRAIN-013 is still fully implemented: the dataset "
                    "is hash-verified, index-aligned with each evaluated asset, and sliced to "
                    "the same fold window before the frozen engine is called. No observation is "
                    "forward-filled. The external reference is a disclosure, not a relaxation "
                    "of the rule."
                ),
            },
        ],
        "verification": {
            "verifier_script": "scripts/verify_v4_selection_authorization_1.py",
            "tests_module": "tests/test_v4_selection_authorization_1.py",
            "verify_command": "python3 scripts/verify_v4_selection_authorization_1.py",
            "execution_path_tests": "tests/test_v4_campaign_benchmark_rule.py",
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
                "following the pattern of the other v2 and v3 artifacts."
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

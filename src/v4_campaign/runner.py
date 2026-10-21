"""The bounded v4 selection run.

This module drives one v4 selection grid run over the frozen candidate set. It
is *not* executed by the session that delivers it: the run requires the
versioned authorization ``configs/research_v4_selection_authorization_1.json``,
which does not exist yet, and the authorization authorizes **at most one**
attempt.

Boundaries the run enforces:

* the candidate set is exactly the frozen set; it is never re-ranked, widened
  or narrowed;
* only development data is read -- candles that close at or before the
  confirmatory-window start -- and a dataset that reaches into the confirmatory
  window is refused before it is read;
* the **benchmark rule** of BRAIN-013 is applied: the benchmark dataset is
  hash-verified, it must be index-aligned with the evaluated asset, and the
  asset series and the benchmark series are sliced to the *same* fold window
  before the frozen engine is called, so that the engine's index pairing equals
  the UTC-candle-close alignment the frozen methodology requires;
* the 576 ``btc_ema_168`` configurations per asset are evaluated like every
  other configuration; they are never dropped, re-derived or re-ranked;
* the selection rule is the unchanged v1 rule, applied through the v1 selector;
* the holdout-position fold is never evaluated during selection and
  ``holdout_exposed_count`` stays at zero;
* only the v4 output paths are written; the v1, v2 and v3 shards, ledgers,
  tallies and result streams are never touched;
* an asset for which no configuration survives the unchanged v1 selection rule
  is reported in the ledger, not hidden;
* an abort rolls back every artifact the run created.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from breakout_research.backtest.backtester import run_fold_backtest
from breakout_research.backtest.checkpoint import CheckpointManager
from breakout_research.backtest.shards import ResultStore, iter_campaign_records, serialize_record
from breakout_research.baselines import buyhold_baseline, baseline_for_asset
from breakout_research.config import CheckpointState, CostScenario, get_configurations
from breakout_research.selection import select_candidates

from .benchmark import (
    BENCHMARK_SYMBOL,
    align_window,
    assert_benchmark_covers_evaluation,
)
from .data import (
    load_benchmark_candles,
    load_development_candles,
    parse_utc_ms,
    resolve_effective_data_manifest,
)
from .errors import AttemptBudgetError, BoundsError, ScopeError, V4CampaignError
from .identity import code_identity_document
from .scope import (
    FORBIDDEN_PATHS,
    assert_no_forbidden_output,
    authorization_output_paths,
    dig,
    frozen_scope,
    load_json,
    selection_rule,
    sha256_file,
    validate_authorization,
    verify_execution_protocol,
)
from .units import btc_filter_configurations, fold_bounds, iter_units, planned_unit_counts, unit_data_hash, validation_folds

DEFAULT_PATHS = {
    "spec_v1": "configs/research_v1.json",
    "spec_v4": "configs/research_v4.json",
    "freeze": "configs/research_v4_candidate_freeze.json",
    "data_manifest": "research/data_manifest_v4.json",
    "universe_manifest": "research/universe_manifest_v4.json",
    "config_manifest": "research/config_manifest.json",
    "execution_protocol": "configs/research_v4_execution.json",
    "authorization": "configs/research_v4_selection_authorization_1.json",
    "shards_dir": "research/shards_v4",
    "ledger": "research/ledger_v4.json",
    "results_manifest": "research/results_manifest_v4.json",
    "results_stream": "research/results_v4.jsonl",
    "checkpoint": "research_state/checkpoint_v4.json",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.",
        suffix=".tmp", delete=False, newline=""
    )
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


@dataclass(frozen=True)
class Workspace:
    """Every path the run touches. Nothing is implied; nothing is defaulted."""

    repo_root: Path
    spec_v1: Path
    spec_v4: Path
    freeze: Path
    data_manifest: Path
    universe_manifest: Path
    config_manifest: Path
    execution_protocol: Path
    authorization: Path
    shards_dir: Path
    ledger: Path
    results_manifest: Path
    results_stream: Path
    checkpoint: Path


def default_workspace(repo_root: Path) -> Workspace:
    """The repository's standard v4 workspace."""
    root = Path(repo_root)
    return Workspace(
        repo_root=root,
        **{name: root / relative for name, relative in DEFAULT_PATHS.items()},
    )


@dataclass
class Plan:
    """The validated, frozen description of the run that may execute."""

    workspace: Workspace
    run_id: str
    campaign_id: str
    run_phase: str
    scope: Dict[str, Any]
    bounds: Dict[str, Any]
    boundary_ms: int
    confirmatory_window_start_utc: str
    effective_data_boundary_utc: str
    development_cutoff_utc: str
    assets: List[Dict[str, Any]]
    configs: List[Any]
    cost_multipliers: List[float]
    folds: Dict[str, Any]
    selection_rule: Dict[str, Any]
    selection_rule_digest: str
    specification_hash: str
    code_identity: Dict[str, Any]
    data_manifest: Dict[str, Any]
    data_manifest_provenance: Dict[str, Any]
    data_hashes: Dict[str, str]
    authorization_manifest_hash: str
    benchmark: Dict[str, Any]
    counts: Dict[str, int] = field(default_factory=dict)


def build_plan(workspace: Workspace) -> Plan:
    """Validate every bound of the run and resolve what it may touch.

    Nothing is executed here: the plan is the frozen description that the
    authorization permits. Without the authorization the plan cannot be built,
    so the run cannot start.
    """
    root = Path(workspace.repo_root)
    if not workspace.authorization.exists():
        raise ScopeError(
            "the v4 selection authorization configs/research_v4_selection_authorization_1.json "
            "does not exist; no v4 selection run is authorized"
        )

    authorization = load_json(workspace.authorization)
    freeze = load_json(workspace.freeze)
    spec_v1 = load_json(workspace.spec_v1)
    spec_v4 = load_json(workspace.spec_v4)
    universe = load_json(workspace.universe_manifest)
    execution_protocol = load_json(workspace.execution_protocol)

    scope = frozen_scope(freeze, universe)
    rule_block, rule_digest = selection_rule(spec_v1, spec_v4)
    validated = validate_authorization(root, authorization, scope, rule_digest, rule_block)
    bounds = validated["bounds"]

    if bounds.get("max_assets") != len(scope["binance_pairs"]):
        raise BoundsError(
            f"the authorized asset bound {bounds.get('max_assets')} differs from the frozen "
            f"candidate count {len(scope['binance_pairs'])}"
        )

    config_manifest = load_json(workspace.config_manifest)
    configs = get_configurations(config_manifest)
    if not configs:
        raise BoundsError("the configuration manifest carries no configuration")
    if len(configs) > int(bounds.get("max_configs_per_asset") or len(configs)):
        raise BoundsError(
            f"the grid holds {len(configs)} configurations, above the authorized bound "
            f"{bounds.get('max_configs_per_asset')}"
        )
    btc_configs = btc_filter_configurations(configs)
    if not btc_configs:
        raise BoundsError("the grid carries no BTC trend-filter configuration")

    assets = [
        {"symbol": pair, "rank": index + 1}
        for index, pair in enumerate(scope["binance_pairs"])
    ]
    counts = planned_unit_counts(
        asset_count=len(assets),
        config_count=len(configs),
        fold_count=len(spec_v1["folds"]["window_fractions"]),
        cost_count=len(spec_v1["costs"]["scenarios"]),
    )
    if int(bounds.get("max_total_config_units") or counts["config_units"]) < counts["config_units"]:
        raise BoundsError(
            f"the planned run holds {counts['config_units']} configuration units, above the "
            f"authorized bound {bounds.get('max_total_config_units')}"
        )

    boundary = validated["data_boundary"]
    boundary_ms = parse_utc_ms(boundary["candles_before_utc"])
    if boundary_ms != parse_utc_ms(scope["effective_data_boundary_utc"]):
        raise ScopeError(
            "the authorized data boundary is not the effective development boundary of the "
            "freeze, which is the earlier of the confirmatory-window start and the "
            "preregistered development cutoff"
        )
    if boundary_ms > parse_utc_ms(scope["development_cutoff_utc"]):
        raise ScopeError(
            "the authorized data boundary is after the preregistered development cutoff, so "
            "the run could read a candle inside the open v3 confirmatory window"
        )

    data_manifest, effective_hash, provenance = resolve_effective_data_manifest(root)
    if effective_hash != scope["data_manifest_hash"]:
        raise ScopeError(
            "the effective data-manifest identity does not match the identity bound by the "
            "frozen candidate set"
        )

    execution_binding = verify_execution_protocol(
        execution_protocol, scope, effective_hash
    )
    benchmark_block = execution_binding["benchmark"]
    if benchmark_block.get("content_hash") != provenance["benchmark_content_hash"]:
        raise ScopeError(
            "the benchmark dataset named by the v4 execution protocol is not the benchmark "
            "dataset of the provenance"
        )

    data_hashes: Dict[str, str] = {}
    for symbol, entry in (data_manifest.get("assets") or {}).items():
        content_hash = entry.get("content_hash")
        if content_hash:
            data_hashes[symbol] = str(content_hash)
            declared = (data_manifest.get("content_hashes") or {}).get(symbol)
            if declared != content_hash:
                raise V4CampaignError(
                    f"the data manifest disagrees with itself about the content hash of {symbol}"
                )

    # The benchmark is external to the v4 data manifest, so the manifest carries
    # no entry for it -- but the v1 unit-data-hash rule binds the benchmark
    # dataset into the identity of every BTC trend-filter unit ("a BTC
    # trend-filter unit depends on the asset's data **and** on the benchmark
    # dataset"). The benchmark's content hash is therefore published into the
    # plan, after it has been verified against the recorded hash and against
    # the hash the v4 execution protocol binds.
    benchmark_dataset = root / str(provenance["benchmark_dataset_path"])
    if not benchmark_dataset.exists():
        raise V4CampaignError(
            f"the benchmark dataset {provenance['benchmark_dataset_path']} does not exist"
        )
    benchmark_content_hash = sha256_file(benchmark_dataset)
    if benchmark_content_hash != str(provenance["benchmark_content_hash"]):
        raise V4CampaignError(
            f"the benchmark dataset does not hash to the recorded content hash: recorded "
            f"{provenance['benchmark_content_hash']}, computed {benchmark_content_hash}"
        )
    data_hashes[BENCHMARK_SYMBOL] = benchmark_content_hash

    code_identity = dict(validated["code_identity"])
    paths = authorization_output_paths(authorization)
    assert_no_forbidden_output(paths)

    return Plan(
        workspace=workspace,
        run_id=str(validated["run_id"]),
        campaign_id=str(validated["campaign_id"]),
        run_phase=str(validated["run_phase"]),
        scope=scope,
        bounds=bounds,
        boundary_ms=boundary_ms,
        confirmatory_window_start_utc=str(scope["confirmatory_window_start_utc"]),
        effective_data_boundary_utc=str(scope["effective_data_boundary_utc"]),
        development_cutoff_utc=str(scope["development_cutoff_utc"]),
        assets=assets,
        configs=configs,
        cost_multipliers=[float(value) for value in spec_v1["costs"]["scenarios"]],
        folds=spec_v1["folds"],
        selection_rule=rule_block,
        selection_rule_digest=rule_digest,
        specification_hash=str(spec_v4["specification_hash"]),
        code_identity=code_identity,
        data_manifest=data_manifest,
        data_manifest_provenance=provenance,
        data_hashes=data_hashes,
        authorization_manifest_hash=str(validated["manifest_hash"]),
        benchmark=dict(validated["benchmark"]),
        counts=counts,
    )


def fold_result_record(
    fold_res: Any,
    experiment_id: str,
    data_hash: str,
    start_time: int,
    end_time: int,
    specification_hash: str,
    code_identity: str,
    alignment: Dict[str, Any],
) -> Dict[str, Any]:
    """A v4 result record, in the v1 record layout plus the run identity.

    The record carries the alignment of the benchmark in the fold window it was
    evaluated in, so that a reader can prove which benchmark slice the record
    was produced with.
    """
    return {
        "experiment_id": experiment_id,
        "asset": fold_res.asset,
        "config_id": fold_res.config_id,
        "fold_index": fold_res.fold_index,
        "start_time": int(start_time),
        "end_time": int(end_time),
        "cost_multiplier": fold_res.cost_multiplier,
        "status": fold_res.status.value,
        "reason": fold_res.reason,
        "trade_count": fold_res.trade_count,
        "gross_total_return": fold_res.gross_total_return,
        "net_total_return": fold_res.net_total_return,
        "annualized_return": fold_res.annualized_return,
        "daily_sharpe": fold_res.daily_sharpe,
        "max_drawdown": fold_res.max_drawdown,
        "exposure": fold_res.exposure,
        "turnover": fold_res.turnover,
        "win_rate": fold_res.win_rate,
        "avg_win": fold_res.avg_win,
        "avg_loss": fold_res.avg_loss,
        "profit_factor": fold_res.profit_factor,
        "profit_factor_status": fold_res.profit_factor_status,
        "fee_drag": fold_res.fee_drag,
        "slippage_drag": fold_res.slippage_drag,
        "data_hash": data_hash,
        "is_holdout": False,
        "specification_hash": specification_hash,
        "code_hash": code_identity,
        "benchmark_alignment": {
            "benchmark_content_hash": alignment.get("benchmark_content_hash"),
            "benchmark_window_sliced": alignment.get("benchmark_window_sliced", True),
            "forward_filled": alignment.get("forward_filled", False),
            "index_aligned": alignment.get("index_aligned", True),
        },
        "stored_utc": _now_utc(),
    }


def _ledger_document(plan: Plan) -> Dict[str, Any]:
    return {
        "artifact": "v4_selection_ledger",
        "artifact_version": "v4-selection-ledger-1",
        "run_id": plan.run_id,
        "campaign_id": plan.campaign_id,
        "run_phase": plan.run_phase,
        "status": "NOT_STARTED",
        "started_utc": None,
        "completed_utc": None,
        "authorization_manifest_hash": plan.authorization_manifest_hash,
        "specification_hash": plan.specification_hash,
        "code_identity": plan.code_identity,
        "scope": {
            "binance_pairs": list(plan.scope["binance_pairs"]),
            "count": len(plan.scope["binance_pairs"]),
            "excluded_after_validation": dict(plan.scope["excluded_after_validation"]),
        },
        "data_boundary": {
            "candles_before_utc": plan.effective_data_boundary_utc,
            "effective_data_boundary_rule": (
                "the earlier of the v4 confirmatory-window start and the preregistered "
                "development cutoff"
            ),
            "development_cutoff_utc": plan.development_cutoff_utc,
            "confirmatory_window_never_read_during_selection": True,
            "v1_holdout_never_reused": True,
            "v2_confirmatory_window_never_reused": True,
            "v3_confirmatory_window_never_reused": True,
        },
        "benchmark": dict(plan.benchmark),
        "data_manifest": dict(plan.data_manifest_provenance),
        "selection_rule": {
            "reference": "configs/research_v1.json -> selection",
            "selection_block_sha256": plan.selection_rule_digest,
            "max_candidates_per_asset": plan.selection_rule.get("max_candidates_per_asset"),
        },
        "bounds": dict(plan.bounds),
        "counts": dict(plan.counts),
        "runs": [],
        "holdout_exposed_count": 0,
        "v1_artifacts_touched": [],
    }


def _read_ledger(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def claim_attempt(plan: Plan) -> Dict[str, Any]:
    """Open the ledger for the single authorized run.

    An interrupted run is *resumed*, not restarted; a completed run is never
    re-run. A boundary abort rolls the ledger back and releases the run.
    """
    ledger_path = plan.workspace.ledger
    existing = _read_ledger(ledger_path)
    document: Optional[Dict[str, Any]] = None
    if existing:
        for entry in existing.get("runs") or []:
            if entry.get("run_id") != plan.run_id:
                continue
            if entry.get("status") == "COMPLETED":
                raise AttemptBudgetError(
                    f"the authorized run {plan.run_id} has already completed; the "
                    "authorization permits one run"
                )
            resumes = int(entry.get("resumes") or 0)
            max_retries = int(plan.bounds.get("max_retries_on_technical_failure", 3))
            if resumes >= max_retries:
                raise AttemptBudgetError(
                    f"the authorized run {plan.run_id} has used its {max_retries} technical "
                    "retries; a further start is refused"
                )
            document = existing
            entry["status"] = "RUNNING"
            entry["resumes"] = resumes + 1
            entry.setdefault("resume_events", []).append({"resumed_utc": _now_utc()})
            break
    if document is None:
        document = _ledger_document(plan)
        document["status"] = "RUNNING"
        document["started_utc"] = _now_utc()
        document["runs"] = [
            {
                "run_id": plan.run_id,
                "campaign_id": plan.campaign_id,
                "status": "RUNNING",
                "started_utc": document["started_utc"],
                "completed_utc": None,
                "resumes": 0,
                "resume_events": [],
            }
        ]
    _atomic_write_json(ledger_path, document)
    return document


def _rollback(plan: Plan, created_files: Iterable[Path], created_dirs: Iterable[Path],
              previous_ledger: Optional[bytes]) -> None:
    """Remove every artifact the aborted run created."""
    for path in created_files:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    for path in created_dirs:
        shutil.rmtree(path, ignore_errors=True)
    ledger_path = plan.workspace.ledger
    if previous_ledger is None:
        if ledger_path.exists():
            ledger_path.unlink()
    else:
        ledger_path.write_bytes(previous_ledger)


def _record_technical_failure(plan: Plan, error: Exception) -> None:
    """Record a technical failure and keep the partial state for a resume."""
    ledger_path = plan.workspace.ledger
    document = _read_ledger(ledger_path)
    if not document:
        return
    document["status"] = "INTERRUPTED"
    for entry in document.get("runs") or []:
        if entry.get("run_id") == plan.run_id:
            entry["status"] = "INTERRUPTED"
            entry["last_failure"] = {
                "type": type(error).__name__,
                "message": str(error)[:500],
                "utc": _now_utc(),
            }
    _atomic_write_json(ledger_path, document)


def _guard_path(path: Path, plan: Plan) -> Path:
    """Fail closed when a write would touch a v1, v2 or v3 artifact."""
    resolved = Path(path).resolve()
    root = Path(plan.workspace.repo_root).resolve()
    for banned in FORBIDDEN_PATHS:
        candidate = (root / banned.rstrip("/")).resolve()
        if resolved == candidate or candidate in resolved.parents:
            raise V4CampaignError(f"refusing to write to the forbidden path {path}")
    return resolved


def _append_result_stream(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    """Append committed records to the result stream.

    The stream is a projection of the verified shards: a record reaches the
    stream only when the shard that carries it has been promoted, so an
    interrupted run leaves the stream and the shards in agreement and a resume
    cannot duplicate a row.
    """
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(serialize_record(record))


def _selection_summary(
    plan: Plan,
    records: List[Dict[str, Any]],
    baselines: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply the unchanged v1 selection rule and report the outcome.

    An asset for which no configuration survives is listed explicitly: the
    outcome of the run is reported as it is, never as a success it is not.
    """
    outcome = select_candidates(
        records,
        load_json(plan.workspace.spec_v1),
        baselines,
        load_json(plan.workspace.config_manifest),
    )
    assets_with_candidate = sorted(
        asset for asset, result in outcome.items() if result.get("config_id")
    )
    assets_without_candidate = sorted(
        asset for asset, result in outcome.items() if not result.get("config_id")
    )
    per_asset = {
        asset: {
            "status": result.get("status"),
            "economic_status": result.get("economic_status"),
            "config_id": result.get("config_id"),
            "counts": result.get("counts"),
        }
        for asset, result in sorted(outcome.items())
    }
    if assets_with_candidate and assets_without_candidate:
        overall = "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    elif assets_with_candidate:
        overall = "CANDIDATES_SELECTED"
    else:
        overall = "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"
    return {
        "rule_reference": "configs/research_v1.json -> selection",
        "selection_block_sha256": plan.selection_rule_digest,
        "assets_evaluated": len(outcome),
        "assets_with_candidate": assets_with_candidate,
        "assets_without_candidate": assets_without_candidate,
        "assets_without_candidate_reported": True,
        "outcome": overall,
        "per_asset": per_asset,
    }


def run_selection(workspace: Workspace) -> Dict[str, Any]:
    """Execute the bounded v4 selection run and return its ledger document.

    The run is authorized by ``configs/research_v4_selection_authorization_1.json``
    and consumes its single attempt. It never reads a confirmatory-window
    candle, never evaluates the holdout-position fold, never writes a v1, v2 or
    v3 artifact and never evaluates a misaligned benchmark.
    """
    plan = build_plan(workspace)
    ledger_path = plan.workspace.ledger
    previous_ledger = ledger_path.read_bytes() if ledger_path.exists() else None

    created_files: List[Path] = []
    created_dirs: List[Path] = []
    results_stream = plan.workspace.results_stream
    results_manifest = plan.workspace.results_manifest
    checkpoint_path = plan.workspace.checkpoint
    shard_root = plan.workspace.shards_dir
    shard_campaign_dir = Path(shard_root) / plan.campaign_id

    for path in (results_stream, results_manifest, checkpoint_path):
        _guard_path(path, plan)
        if not path.exists():
            created_files.append(path)
    _guard_path(ledger_path, plan)
    _guard_path(shard_root, plan)
    if not shard_campaign_dir.exists():
        created_dirs.append(shard_campaign_dir)

    try:
        document = claim_attempt(plan)
        store = ResultStore(
            campaign_id=plan.campaign_id,
            spec_hash=plan.specification_hash,
            code_hash=plan.code_identity["run_code_identity"],
            data_manifest_hash=plan.data_manifest_provenance["effective_data_manifest_hash"],
            shard_root=str(shard_root),
            manifest_path=str(results_manifest),
        )
        completed_ids, _total_bytes = store.reconcile()
        checkpoint = CheckpointManager(checkpoint_path=str(checkpoint_path))
        batch_size = int(dig(load_json(plan.workspace.spec_v1), "checkpointing.batch_size") or 50)
        executed = 0
        skipped = 0
        records_since_checkpoint = 0
        next_unit: Dict[str, Any] = {}
        baselines: Dict[str, Dict[str, Any]] = {}
        pending_records: List[Dict[str, Any]] = []
        alignments: Dict[str, Any] = {}

        # The benchmark is loaded once and checked against every evaluated asset.
        benchmark_candles, benchmark_provenance = load_benchmark_candles(
            plan.workspace.repo_root, plan.data_manifest, plan.boundary_ms
        )

        for asset_index, asset in enumerate(plan.assets):
            symbol = str(asset["symbol"])
            candles, _provenance = load_development_candles(
                plan.workspace.repo_root, symbol, plan.data_manifest, plan.boundary_ms
            )
            bounds = fold_bounds(candles, plan.folds)
            windows = validation_folds(bounds)
            if not windows:
                raise V4CampaignError(f"{symbol} yields no validation fold")
            assert_benchmark_covers_evaluation(
                candles, benchmark_candles, windows, symbol
            )
            baseline = buyhold_baseline(
                candles,
                {fold[2]: (fold[0], fold[1]) for fold in windows},
                [CostScenario.baseline().scaled(value) for value in plan.cost_multipliers],
            )
            baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)

            for window in windows:
                start_time, end_time, fold_index, _holdout = window
                asset_slice, benchmark_slice, alignment = align_window(
                    candles, benchmark_candles, start_time, end_time, symbol
                )
                alignment["benchmark_content_hash"] = benchmark_provenance.get("content_hash")
                alignments.setdefault(symbol, {})[str(fold_index)] = alignment

                for unit, experiment_id in iter_units(
                    plan.assets,
                    plan.configs,
                    plan.cost_multipliers,
                    windows,
                    plan.data_hashes,
                    plan.specification_hash,
                    plan.code_identity["run_code_identity"],
                    asset_index=asset_index,
                ):
                    if int(unit["fold_index"]) != int(fold_index):
                        continue
                    if experiment_id in completed_ids:
                        skipped += 1
                        continue
                    if not next_unit:
                        next_unit = {
                            "asset_index": unit["asset_index"],
                            "config_index": unit["config_index"],
                            "fold_index": unit["fold_index"],
                            "cost_index": unit["cost_index"],
                        }
                    fold_res = run_fold_backtest(
                        asset_slice,
                        unit["config"],
                        btc_candles=benchmark_slice,
                        start_time=unit["start_time"],
                        end_time=unit["end_time"],
                        cost_scenario=unit["cost_scenario"],
                        fold_index=unit["fold_index"],
                        asset=symbol,
                    )
                    data_hash = unit_data_hash(symbol, unit["config"], plan.data_hashes)
                    record = fold_result_record(
                        fold_res,
                        experiment_id,
                        data_hash,
                        unit["start_time"],
                        unit["end_time"],
                        plan.specification_hash,
                        plan.code_identity["run_code_identity"],
                        alignment,
                    )
                    store.append(experiment_id, record)
                    pending_records.append(record)
                    completed_ids[experiment_id] = True
                    executed += 1
                    records_since_checkpoint += 1
                    if records_since_checkpoint >= batch_size:
                        store.flush()
                        _append_result_stream(results_stream, pending_records)
                        pending_records = []
                        checkpoint.save(CheckpointState(
                            protocol_hash=plan.specification_hash,
                            code_hash=plan.code_identity["run_code_identity"],
                            current_asset_index=unit["asset_index"],
                            current_config_index=unit["config_index"],
                            current_fold_index=unit["fold_index"],
                            current_cost_index=unit["cost_index"],
                            completed_records=len(completed_ids),
                            last_verified_record=len(completed_ids),
                            next_unit=next_unit,
                            timestamp_utc=_now_utc(),
                            holdout_exposed_count=0,
                            pilot_completed=True,
                            pilot_passed=True,
                        ))
                        records_since_checkpoint = 0
            store.flush()
            _append_result_stream(results_stream, pending_records)
            pending_records = []
            checkpoint.save(CheckpointState(
                protocol_hash=plan.specification_hash,
                code_hash=plan.code_identity["run_code_identity"],
                current_asset_index=asset_index + 1,
                current_config_index=0,
                current_fold_index=0,
                current_cost_index=0,
                completed_records=len(completed_ids),
                last_verified_record=len(completed_ids),
                next_unit=next_unit,
                timestamp_utc=_now_utc(),
                holdout_exposed_count=0,
                pilot_completed=True,
                pilot_passed=True,
            ))

        store.flush()
        _append_result_stream(results_stream, pending_records)
        pending_records = []
        store.close()

        records = iter_campaign_records(str(shard_root), plan.campaign_id)
        selection = _selection_summary(plan, records, baselines)

        document["status"] = "COMPLETED"
        document["completed_utc"] = _now_utc()
        document["counts"] = {
            **dict(plan.counts),
            "executed": executed,
            "skipped_already_complete": skipped,
            "records_written": len(records),
        }
        document["selection"] = selection
        document["benchmark_alignment"] = alignments
        for entry in document.get("runs") or []:
            if entry.get("run_id") == plan.run_id:
                entry["status"] = "COMPLETED"
                entry["completed_utc"] = document["completed_utc"]
        _atomic_write_json(ledger_path, document)
        return document
    except V4CampaignError:
        _rollback(plan, created_files, created_dirs, previous_ledger)
        raise
    except Exception as exc:
        _record_technical_failure(plan, exc)
        raise


__all__ = [
    "Plan",
    "Workspace",
    "build_plan",
    "claim_attempt",
    "code_identity_document",
    "default_workspace",
    "fold_result_record",
    "run_selection",
]

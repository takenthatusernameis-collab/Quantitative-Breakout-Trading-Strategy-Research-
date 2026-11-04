"""The bounded v6 selection run.

This module drives one v6 selection grid run over the frozen candidate set. It
is *not* executed by the session that delivers it: the run requires the
versioned authorization ``configs/research_v6_selection_authorization_1.json``,
which authorizes exactly one logical run, and the execution binding records
the implementation identity without granting any additional authority. The run
is not started by preflight, import or test.

Boundaries the run enforces:

* the candidate set is exactly the frozen set; it is never re-ranked, widened
  or narrowed;
* only development data is read -- candles that close at or before the frozen
  inclusive development cutoff -- and a dataset that reaches past that cutoff
  is refused before it is opened;
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
* only the v6 output paths are written; the v1, v2, v3, v4 and v5 shards,
  ledgers, tallies and result streams are never touched;
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
from .errors import AttemptBudgetError, BoundsError, ScopeError, V6CampaignError
from .identity import code_identity_document
from .scope import (
    FROZEN_PATHS,
    FORBIDDEN_PATHS,
    assert_no_forbidden_output,
    authorization_output_paths,
    dig,
    load_json,
    sha256_file,
    validate_v6_scope,
)
from .units import btc_filter_configurations, fold_bounds, iter_units, planned_unit_counts, unit_data_hash, validation_folds

DEFAULT_PATHS = {
    "spec_v1": "configs/research_v1.json",
    "spec_v6": "configs/research_v6.json",
    "freeze": "configs/research_v6_candidate_freeze.json",
    "data_manifest": "research/data_manifest_v6.json",
    "universe_manifest": "research/universe_manifest_v6.json",
    "config_manifest": "research/config_manifest.json",
    "execution_protocol": "configs/research_v6_execution.json",
    "authorization": "configs/research_v6_selection_authorization_1.json",
    "shards_dir": "research/shards_v6",
    "ledger": "research/ledger_v6.json",
    "results_manifest": "research/results_manifest_v6.json",
    "results_stream": "research/results_v6.jsonl",
    "checkpoint": "research_state/checkpoint_v6.json",
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
    spec_v6: Path
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
    """The repository's standard v6 workspace."""
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
    """Validate every frozen v6 binding before any candle dataset is opened."""
    root = Path(workspace.repo_root)
    validated = validate_v6_scope(root)
    spec_v1 = validated["spec_v1"]
    spec_v6 = validated["spec_v6"]
    authorization = validated["selection_authorization"]
    config_manifest = validated["config"]
    configs = get_configurations(config_manifest)
    if not configs:
        raise BoundsError("the v6 configuration manifest carries no configurations")
    bounds = dict(validated["bounds"])
    if len(configs) != int(bounds.get("max_configs_per_asset", -1)):
        raise BoundsError("v6 grid size differs from the frozen authorization")
    btc_configs = btc_filter_configurations(configs)
    if len(btc_configs) != 576:
        raise BoundsError(f"expected all 576 BTC-filter configurations, found {len(btc_configs)}")
    assets = [{"symbol": pair, "rank": i + 1} for i,pair in enumerate(validated["scope"]["binance_pairs"])]
    counts = planned_unit_counts(
        asset_count=len(assets), config_count=len(configs),
        fold_count=len(spec_v1["folds"]["window_fractions"]),
        cost_count=len(spec_v1["costs"]["scenarios"]),
    )
    if counts["config_units"] != int(bounds.get("max_total_config_units",-1)):
        raise BoundsError("planned asset/configuration count differs from authorization")
    boundary_iso = str((authorization.get("authorized_run") or {}).get("data_boundary",{}).get("candles_before_utc"))
    boundary_ms = parse_utc_ms(boundary_iso)
    if boundary_iso != validated["scope"]["effective_data_boundary_utc"]:
        raise ScopeError("authorized development boundary differs from frozen v6 boundary")
    data_manifest, effective_hash, provenance = resolve_effective_data_manifest(root)
    if effective_hash != (validated["freeze"].get("data_manifest_hash")):
        raise ScopeError("v6 data manifest no longer matches candidate freeze")
    benchmark_entry = data_manifest["benchmark"]
    if benchmark_entry.get("content_hash") != provenance.get("benchmark_content_hash"):
        raise ScopeError("BTC benchmark provenance does not match the v6 data manifest")
    if int(benchmark_entry.get("last_candle_timestamp",-1)) + 3600000 > boundary_ms:
        raise ScopeError("BTC benchmark metadata crosses the development boundary")
    benchmark_path = root / str(benchmark_entry["dataset_path"])
    if not benchmark_path.is_file():
        raise ScopeError("BTC benchmark dataset is missing")
    if sha256_file(benchmark_path) != benchmark_entry["content_hash"]:
        raise ScopeError("BTC benchmark byte hash differs from the v6 data manifest")
    data_hashes = {
        str(symbol): str(value) for symbol,value in (data_manifest.get("content_hashes") or {}).items()
        if value
    }
    data_hashes[BENCHMARK_SYMBOL] = str(benchmark_entry["content_hash"])
    paths = authorization_output_paths(authorization)
    assert_no_forbidden_output(paths)
    return Plan(
        workspace=workspace,
        run_id=validated["run_id"], campaign_id=validated["campaign_id"],
        run_phase=validated["run_phase"], scope=validated["scope"], bounds=bounds,
        boundary_ms=boundary_ms,
        confirmatory_window_start_utc=str(validated["scope"]["confirmatory_window_start_utc"]),
        effective_data_boundary_utc=str(validated["scope"]["effective_data_boundary_utc"]),
        development_cutoff_utc=str(validated["scope"]["development_cutoff_utc"]),
        assets=assets, configs=configs,
        cost_multipliers=[float(v) for v in spec_v1["costs"]["scenarios"]],
        folds=spec_v1["folds"], selection_rule=validated["selection_rule"],
        selection_rule_digest=validated["selection_rule_digest"],
        specification_hash=str(spec_v6["specification_hash"]),
        code_identity=dict(validated["code_identity"]),
        data_manifest=data_manifest, data_manifest_provenance=provenance,
        data_hashes=data_hashes,
        authorization_manifest_hash=validated["authorization_manifest_hash"],
        benchmark=dict(authorization["authorized_run"]["benchmark"]),
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
    """A v6 result record, in the v1 record layout plus the run identity.

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
        "artifact": "v6_selection_ledger",
        "artifact_version": "v6-selection-ledger-1",
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
                "the earlier of the v6 confirmatory-window start and the preregistered "
                "development cutoff"
            ),
            "development_cutoff_utc": plan.development_cutoff_utc,
            "confirmatory_window_never_read_during_selection": True,
            "v1_holdout_never_reused": True,
            "v2_confirmatory_window_never_reused": True,
            "v3_confirmatory_window_never_reused": True,
            "v4_confirmatory_window_never_reused": True,
            "v5_confirmatory_window_never_reused": True,
        },
        "benchmark": dict(plan.benchmark),
        "effective_rules": dict(plan.scope.get("effective_rules") or {}),
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
    if ledger_path.exists() and existing is None:
        raise ScopeError("an existing v6 ledger is unreadable; refusing to overwrite it")
    document: Optional[Dict[str, Any]] = None
    if existing:
        if existing.get("run_id") != plan.run_id or existing.get("campaign_id") != plan.campaign_id:
            raise ScopeError("an existing v6 ledger belongs to another authorized run")
        if existing.get("specification_hash") != plan.specification_hash:
            raise ScopeError("an existing v6 ledger is bound to another specification")
        if existing.get("code_identity") != plan.code_identity:
            raise ScopeError("an existing v6 ledger is bound to another execution identity")
        if existing.get("authorization_manifest_hash") != plan.authorization_manifest_hash:
            raise ScopeError("an existing v6 ledger is bound to another authorization")
        matched = False
        for entry in existing.get("runs") or []:
            if entry.get("run_id") != plan.run_id:
                continue
            matched = True
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
        if not matched:
            raise ScopeError("an existing v6 ledger has no record of the one authorized run")
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
    """Fail closed when a write would touch any frozen v1-v5 artifact."""
    resolved = Path(path).resolve()
    root = Path(plan.workspace.repo_root).resolve()
    for banned in FORBIDDEN_PATHS:
        candidate = (root / banned.rstrip("/")).resolve()
        if resolved == candidate or candidate in resolved.parents:
            raise V6CampaignError(f"refusing to write to the forbidden path {path}")
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
    """Execute the bounded v6 selection run and return its ledger document.

    The run is authorized by ``configs/research_v6_selection_authorization_1.json``
    and consumes its single attempt. It never reads a confirmatory-window
    candle, never evaluates the holdout-position fold, never writes a v1, v2, v3,
    v4 or v5 artifact and never evaluates a misaligned benchmark.
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
        batch_size = int(dig(load_json(plan.workspace.spec_v1), "checkpointer.batch_size") or 50)
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
                raise V6CampaignError(f"{symbol} yields no validation fold")
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
    except V6CampaignError:
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

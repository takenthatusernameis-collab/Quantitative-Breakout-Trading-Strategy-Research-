"""Conforming preregistered candidate selection (BRAIN-006).

The authoritative rule is the preregistered selection rule in
``configs/research_v1.json`` -> ``selection`` as pinned by the BRAIN-006
decision record (``research_state/brainstorming_queue.md``).  The legacy
profit-factor rule that produced ``research/candidate_manifest.json`` (v1) is
**not** authoritative; it is retained in :mod:`breakout_research.candidate_freeze`
as a provenance record only.

Pinned interpretations (BRAIN-006 decision record, section 2):

1. a validation-fold metric is the metric of that fold at baseline (1x) costs;
   cost scenarios are the same trades re-costed and are never summed with the
   baseline;
2. the combined validation net return is the mean of the four fold net
   returns (the mean and the sum share a sign, so the gate is invariant to
   that choice);
3. the per-fold trade floor of ``min_trades_per_fold`` trades is required in at
   least ``min_folds_with_min_trades`` of the four validation folds, not in
   every fold.

Status taxonomy (README section 9: a configuration below the sample floor is
"insufficient evidence", not an economic failure):

* ``CANDIDATE_SELECTED`` - at least one configuration passes every gate;
* ``CANDIDATE_SELECTED_WITH_UNEVALUABLE_GATES`` - configurations pass every
  evaluable gate but one gate could not be evaluated, so the selection is not
  confirmed;
* ``INSUFFICIENT_EVIDENCE`` - configurations pass every economic gate and fail
  only the sample-size floor;
* ``NO_CANDIDATE`` - no configuration passes the economic screen.

The selector consumes validation units only.  A holdout record raises
:class:`HoldoutRecordError`; it is never filtered out silently.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .baselines import VARIANT_BASELINE

GATE_ORDER = (
    "min_trades_total",
    "min_trades_per_fold",
    "min_folds_with_min_trades",
    "positive_net_return_baseline",
    "positive_net_return_2x_costs",
    "positive_folds_required",
    "median_sharpe_gt_zero",
    "median_sharpe_gt_buyhold",
)
SAMPLE_GATES = ("min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades")
ECONOMIC_GATES = (
    "positive_net_return_baseline",
    "positive_net_return_2x_costs",
    "positive_folds_required",
    "median_sharpe_gt_zero",
    "median_sharpe_gt_buyhold",
)

COST_BASELINE = 1.0
COST_DOUBLE = 2.0

# status, trade_count, net_total_return, daily_sharpe, max_drawdown, turnover
Unit = Tuple[str, int, float, Optional[float], float, float]
FoldMap = Dict[int, Dict[float, Unit]]


class HoldoutRecordError(RuntimeError):
    """Raised when a holdout record reaches the selection path."""


def _cost_key(value: Any) -> float:
    return round(float(value), 6)


def _unit_from_record(record: Dict[str, Any]) -> Unit:
    sharpe = record.get("daily_sharpe")
    return (
        str(record.get("status")),
        int(record.get("trade_count") or 0),
        float(record.get("net_total_return") or 0.0),
        None if sharpe is None else float(sharpe),
        float(record.get("max_drawdown") or 0.0),
        float(record.get("turnover") or 0.0),
    )


def iter_shard_records(shard_root: Path) -> Iterator[Dict[str, Any]]:
    """Yield every record of a shard set in deterministic shard order."""
    for path in sorted(Path(shard_root).glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def aggregate_records(records: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, FoldMap]], Dict[str, Any]]:
    """Group validation records by asset, configuration, fold and cost scenario.

    Holdout records are refused rather than filtered silently: the selection
    must never consume an exposed holdout unit.
    """
    grouped: Dict[str, Dict[str, FoldMap]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    windows: Dict[Tuple[str, int], Tuple[int, int]] = {}
    stats: Dict[str, Any] = {
        "records_read": 0,
        "holdout_records_read": 0,
        "status_counts": Counter(),
        "assets": set(),
        "folds": set(),
        "costs": set(),
        "duplicate_units": 0,
    }
    for record in records:
        stats["records_read"] += 1
        if record.get("is_holdout"):
            stats["holdout_records_read"] += 1
            raise HoldoutRecordError(
                "holdout record encountered during candidate selection: "
                f"asset={record.get('asset')} config={record.get('config_id')}")
        stats["status_counts"][str(record.get("status"))] += 1
        asset = str(record["asset"])
        config_id = str(record["config_id"])
        fold_index = int(record["fold_index"])
        cost = _cost_key(record["cost_multiplier"])
        stats["assets"].add(asset)
        stats["folds"].add(fold_index)
        stats["costs"].add(cost)
        key = (asset, fold_index)
        if "start_time" in record and "end_time" in record:
            bounds = (int(record["start_time"]), int(record["end_time"]))
            if key in windows and windows[key] != bounds:
                raise ValueError(f"inconsistent fold bounds for {key}: {windows[key]} != {bounds}")
            windows[key] = bounds
        fold_map = grouped[asset][config_id]
        if cost in fold_map.get(fold_index, {}):
            stats["duplicate_units"] += 1
        fold_map[fold_index][cost] = _unit_from_record(record)
    stats["status_counts"] = dict(sorted(stats["status_counts"].items()))
    stats["assets"] = sorted(stats["assets"])
    stats["folds"] = sorted(stats["folds"])
    stats["costs"] = sorted(stats["costs"])
    stats["fold_windows"] = {
        asset: {str(fold): list(bounds) for (a, fold), bounds in sorted(windows.items()) if a == asset}
        for asset in stats["assets"]
    }
    materialized = {
        asset: {config_id: {fold: dict(costs) for fold, costs in folds.items()}
                for config_id, folds in configs.items()}
        for asset, configs in grouped.items()
    }
    return materialized, stats


def _fold_map_from_units(fold_units: Sequence[Dict[str, Any]]) -> FoldMap:
    """Build the fold/cost map of a single configuration from its units."""
    fold_map: FoldMap = defaultdict(dict)
    for unit in fold_units:
        if unit.get("is_holdout"):
            raise HoldoutRecordError(
                "holdout record encountered during candidate evaluation: "
                f"asset={unit.get('asset')} config={unit.get('config_id')}")
        fold_index = int(unit["fold_index"])
        cost = _cost_key(unit["cost_multiplier"])
        if cost in fold_map[fold_index]:
            raise ValueError(
                f"duplicate unit for fold {fold_index} at cost {cost} "
                f"of configuration {unit.get('config_id')}")
        fold_map[fold_index][cost] = _unit_from_record(unit)
    return {fold: dict(costs) for fold, costs in fold_map.items()}


def _metric_set(fold_map: FoldMap, cost: float) -> Dict[int, Dict[str, Optional[float]]]:
    """Per-fold metric values of one configuration at one cost scenario."""
    metrics: Dict[int, Dict[str, Optional[float]]] = {}
    for fold, costs in sorted(fold_map.items()):
        if cost not in costs:
            continue
        unit = costs[cost]
        metrics[fold] = {
            "net_return": float(unit[2]),
            "sharpe": unit[3],
            "max_dd": float(unit[4]),
            "turnover": float(unit[5]),
            "trades": int(unit[1]),
        }
    return metrics


def _combined_return(values: Sequence[float]) -> float:
    """Combined validation net return across folds (mean of the fold returns)."""
    if not values:
        return 0.0
    return statistics.fmean(values)


def evaluate_candidate(fold_units: Sequence[Dict[str, Any]], spec: Dict[str, Any],
                        baseline: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate every preregistered gate for one configuration.

    ``fold_units`` are the validation units (result records) of one asset and
    one configuration.  ``baseline`` is the selector-facing view of the
    buy-and-hold baseline of that asset, as produced by
    :func:`breakout_research.baselines.baseline_for_asset`.
    """
    return _evaluate_fold_map(_fold_map_from_units(fold_units), spec, baseline)


def _evaluate_fold_map(fold_map: FoldMap, spec: Dict[str, Any],
                        baseline: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gate evaluation of one configuration from its grouped fold/cost map."""
    selection = spec.get("selection", spec)
    min_trades_total = int(selection["min_trades_total"])
    min_trades_per_fold = int(selection["min_trades_per_fold"])
    min_folds_with_min_trades = int(selection["min_folds_with_min_trades"])
    positive_folds_required = int(selection["positive_folds_required"])

    baseline_metrics = _metric_set(fold_map, COST_BASELINE)
    double_metrics = _metric_set(fold_map, COST_DOUBLE)
    folds = sorted(baseline_metrics)

    trades_total = sum(int(baseline_metrics[fold]["trades"]) for fold in folds)
    per_fold_trades = {str(fold): int(baseline_metrics[fold]["trades"]) for fold in folds}
    min_per_fold_trades = min(per_fold_trades.values()) if per_fold_trades else 0
    folds_with_min_trades = sum(
        1 for fold in folds if int(baseline_metrics[fold]["trades"]) >= min_trades_per_fold)

    combined_return_baseline = _combined_return(
        [float(baseline_metrics[fold]["net_return"]) for fold in folds])
    combined_return_2x = _combined_return(
        [float(double_metrics[fold]["net_return"]) for fold in sorted(double_metrics)])
    positive_folds = sum(1 for fold in folds if float(baseline_metrics[fold]["net_return"]) > 0)

    fold_sharpes = [baseline_metrics[fold]["sharpe"] for fold in folds
                    if baseline_metrics[fold]["sharpe"] is not None]
    median_sharpe = statistics.median(fold_sharpes) if fold_sharpes else None

    buyhold_sharpe: Optional[float] = None
    buyhold_status = "NOT_EVALUABLE"
    buyhold_reason = "buy-and-hold baseline unavailable"
    if baseline:
        buyhold_status = str(baseline.get("status", "NOT_EVALUABLE"))
        candidate_sharpe = baseline.get("median_daily_sharpe")
        if candidate_sharpe is None:
            candidate_sharpe = baseline.get(VARIANT_BASELINE)
        if buyhold_status == "OK" and candidate_sharpe is not None:
            buyhold_sharpe = float(candidate_sharpe)
        else:
            buyhold_reason = baseline.get("reason") or buyhold_reason

    gates: Dict[str, Dict[str, Any]] = {}
    thresholds: Dict[str, Any] = {
        "min_trades_total": min_trades_total,
        "min_trades_per_fold": min_trades_per_fold,
        "min_folds_with_min_trades": min_folds_with_min_trades,
        "positive_net_return_baseline": "> 0",
        "positive_net_return_2x_costs": "> 0",
        "positive_folds_required": positive_folds_required,
        "median_sharpe_gt_zero": "> 0",
        "median_sharpe_gt_buyhold": "> 0",
    }

    def add(name: str, value: Any, passed: Optional[bool], **extra: Any) -> None:
        entry: Dict[str, Any] = {"value": value, "threshold": thresholds[name], "pass": passed}
        entry.update(extra)
        gates[name] = entry

    def not_evaluable(name: str, missing: str, **extra: Any) -> None:
        entry: Dict[str, Any] = {
            "value": None, "threshold": thresholds[name], "pass": None,
            "status": "NOT_EVALUABLE", "missing": missing,
        }
        entry.update(extra)
        gates[name] = entry

    if not baseline_metrics:
        for name in ("min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
                     "positive_net_return_baseline", "positive_folds_required", "median_sharpe_gt_zero"):
            not_evaluable(name, "no baseline-cost (1x) validation records for this configuration")
    else:
        add("min_trades_total", trades_total, trades_total >= min_trades_total,
            unit="closed trades over the validation folds at 1x costs")
        add("min_trades_per_fold", min_per_fold_trades,
            folds_with_min_trades >= min_folds_with_min_trades,
            per_fold_trades=per_fold_trades,
            folds_meeting_floor=folds_with_min_trades,
            reading=f"at least {min_folds_with_min_trades} of {len(folds)} folds",
            unit="minimum fold trade count at 1x costs")
        add("min_folds_with_min_trades", folds_with_min_trades,
            folds_with_min_trades >= min_folds_with_min_trades,
            unit="folds with at least min_trades_per_fold trades")
        add("positive_net_return_baseline", combined_return_baseline, combined_return_baseline > 0,
            aggregation="mean", unit="combined fold net return at 1x costs")
        add("positive_folds_required", positive_folds, positive_folds >= positive_folds_required,
            unit="folds with positive net return at 1x costs")
        add("median_sharpe_gt_zero", median_sharpe,
            None if median_sharpe is None else median_sharpe > 0,
            sharpe_folds_used=len(fold_sharpes), unit="median fold daily Sharpe at 1x costs")

    if not double_metrics:
        not_evaluable("positive_net_return_2x_costs", "no 2x-cost validation records for this configuration")
    else:
        add("positive_net_return_2x_costs", combined_return_2x, combined_return_2x > 0,
            aggregation="mean", unit="combined fold net return at 2x costs")

    if buyhold_sharpe is not None and median_sharpe is not None:
        add("median_sharpe_gt_buyhold", median_sharpe - buyhold_sharpe, median_sharpe > buyhold_sharpe,
            strategy_median_sharpe=median_sharpe, buyhold_median_sharpe=buyhold_sharpe,
            unit="median fold daily Sharpe, strategy minus buy-and-hold")
    else:
        not_evaluable("median_sharpe_gt_buyhold",
                      buyhold_reason if buyhold_status != "OK" else "no defined strategy Sharpe",
                      unit="median fold daily Sharpe")

    not_evaluable_gates = [name for name in GATE_ORDER if gates[name].get("status") == "NOT_EVALUABLE"]
    failed_gates = [name for name in GATE_ORDER if gates[name]["pass"] is False]
    all_pass = not failed_gates and not not_evaluable_gates
    passes_evaluable_gates = not failed_gates
    sample_gates_pass = not [name for name in failed_gates if name in SAMPLE_GATES]
    economic_gates_pass = not [name for name in failed_gates if name in ECONOMIC_GATES]

    median_net_return = (statistics.median([float(baseline_metrics[fold]["net_return"]) for fold in folds])
                         if folds else 0.0)
    worst_drawdown = max((float(baseline_metrics[fold]["max_dd"]) for fold in folds), default=0.0)
    median_turnover = (statistics.median([float(baseline_metrics[fold]["turnover"]) for fold in folds])
                        if folds else 0.0)

    return {
        "gates": gates,
        "all_pass": all_pass,
        "passes_evaluable_gates": passes_evaluable_gates,
        "sample_gates_pass": sample_gates_pass,
        "economic_gates_pass": economic_gates_pass,
        "failed_gates": failed_gates,
        "not_evaluable_gates": not_evaluable_gates,
        "ranking": {
            "median_net_daily_sharpe": median_sharpe,
            "median_net_return": median_net_return,
            "max_drawdown": worst_drawdown,
            "turnover": median_turnover,
        },
        "folds_evaluated": len(folds),
        "sharpe_folds_used": len(fold_sharpes),
    }


def rank_key(evaluation: Dict[str, Any], config_id: str) -> Tuple[Any, ...]:
    """Sort key implementing the preregistered ranking and tiebreakers.

    Median net daily Sharpe (descending), then median net return (descending),
    then maximum drawdown (ascending), then turnover (ascending), then the
    lexicographic configuration ID (ascending).
    """
    ranking = evaluation["ranking"]
    sharpe = ranking["median_net_daily_sharpe"]
    return (
        -(sharpe if sharpe is not None else float("-inf")),
        -ranking["median_net_return"],
        ranking["max_drawdown"],
        ranking["turnover"],
        config_id,
    )


def select_for_asset(evaluations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the preregistered rule to one asset's configurations."""
    qualifying = [cid for cid, evaluation in evaluations.items() if evaluation["all_pass"]]
    qualifying_evaluable = [cid for cid, evaluation in evaluations.items()
                            if evaluation["passes_evaluable_gates"]]
    sample_floor_only = [cid for cid, evaluation in evaluations.items()
                         if evaluation["economic_gates_pass"] and not evaluation["sample_gates_pass"]]
    economic_floor_only = [cid for cid, evaluation in evaluations.items()
                           if evaluation["sample_gates_pass"] and not evaluation["economic_gates_pass"]]

    selected: Optional[str] = None
    if qualifying:
        selected = sorted(qualifying, key=lambda cid: rank_key(evaluations[cid], cid))[0]
        status = "CANDIDATE_SELECTED"
    elif qualifying_evaluable:
        selected = sorted(qualifying_evaluable, key=lambda cid: rank_key(evaluations[cid], cid))[0]
        status = "CANDIDATE_SELECTED_WITH_UNEVALUABLE_GATES"
    elif sample_floor_only:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "NO_CANDIDATE"

    economic_status = {
        "CANDIDATE_SELECTED": "CANDIDATE_PENDING_HOLDOUT",
        "CANDIDATE_SELECTED_WITH_UNEVALUABLE_GATES": "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
        "NO_CANDIDATE": "NO_CANDIDATE",
    }[status]

    return {
        "selected_config_id": selected,
        "selection_status": status,
        "economic_status": economic_status,
        "configs_passing_all_gates": len(qualifying),
        "configs_passing_evaluable_gates": len(qualifying_evaluable),
        "configs_failing_only_sample_floor": len(sample_floor_only),
        "configs_failing_only_economic_gates": len(economic_floor_only),
    }


def neighbor_index(config_manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    """Mechanical parameter neighbours: one dimension, one adjacent value.

    Immediate neighbours are the configurations that differ from a given
    configuration in exactly one parameter dimension by one adjacent value of
    that dimension (README section 9).
    """
    dimensions: Dict[str, List[Any]] = config_manifest["dimensions"]
    configurations = config_manifest["configurations"]
    by_parameters: Dict[Tuple[str, ...], str] = {}
    for entry in configurations:
        key = tuple(str(entry[name]) for name in dimensions)
        by_parameters[key] = entry["config_id"]

    neighbors: Dict[str, List[str]] = {entry["config_id"]: [] for entry in configurations}
    for entry in configurations:
        config_id = entry["config_id"]
        for name, values in dimensions.items():
            index = values.index(entry[name])
            for offset in (-1, 1):
                neighbor_position = index + offset
                if 0 <= neighbor_position < len(values):
                    key = [str(entry[dimension]) for dimension in dimensions]
                    key[list(dimensions).index(name)] = str(values[neighbor_position])
                    neighbor_id = by_parameters.get(tuple(key))
                    if neighbor_id is not None and neighbor_id != config_id:
                        neighbors[config_id].append(neighbor_id)
        neighbors[config_id] = sorted(set(neighbors[config_id]))
    return neighbors


def neighbor_analysis(selected_config_id: str, neighbors: Dict[str, List[str]],
                      evaluations: Dict[str, Dict[str, Any]], asset: str) -> Dict[str, Any]:
    """Parameter-neighbourhood stability analysis of a selected configuration.

    The preregistered specification defines no threshold, so this is reported
    and never used as a gate.
    """
    rows: List[Dict[str, Any]] = []
    for neighbor_id in neighbors.get(selected_config_id, []):
        evaluation = evaluations.get(neighbor_id)
        if evaluation is None:
            continue
        rows.append({
            "config_id": neighbor_id,
            "median_net_return": evaluation["ranking"]["median_net_return"],
            "median_net_daily_sharpe": evaluation["ranking"]["median_net_daily_sharpe"],
            "all_gates_pass": evaluation["all_pass"],
        })
    if not rows:
        return {"status": "NO_NEIGHBOURS_EVALUATED", "neighbor_count": 0, "asset": asset}
    positive = [row for row in rows
                if row["median_net_return"] is not None and row["median_net_return"] > 0]
    sharpes = [row["median_net_daily_sharpe"] for row in rows
               if row["median_net_daily_sharpe"] is not None]
    returns = [row["median_net_return"] for row in rows if row["median_net_return"] is not None]
    return {
        "status": "OK",
        "asset": asset,
        "selected_config_id": selected_config_id,
        "neighbor_count": len(rows),
        "neighbors_with_positive_validation_return": len(positive),
        "neighbors_with_positive_validation_return_pct": round(100.0 * len(positive) / len(rows), 4),
        "median_neighbor_median_net_return": statistics.median(returns) if returns else None,
        "median_neighbor_median_net_daily_sharpe": statistics.median(sharpes) if sharpes else None,
        "neighbors_passing_all_gates": sum(1 for row in rows if row["all_gates_pass"]),
        "neighbors": rows,
    }


def select_candidates(records: Iterable[Dict[str, Any]], spec: Dict[str, Any],
                      baselines: Optional[Dict[str, Dict[str, Any]]] = None,
                      config_manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Select at most one candidate per asset under the preregistered rule.

    ``records`` are validation result records; a holdout record raises
    :class:`HoldoutRecordError`.  ``baselines`` maps an asset to its
    selector-facing buy-and-hold baseline.  The return value maps every asset
    to its status, selected configuration, gate table and ranking.

    When ``config_manifest`` is given, the parameter-neighbourhood stability
    analysis of the preregistered rule is reported for every selected
    configuration.
    """
    baselines = baselines or {}
    grouped, _stats = aggregate_records(records)
    neighbors = neighbor_index(config_manifest) if config_manifest else {}
    result: Dict[str, Any] = {}
    for asset in sorted(grouped):
        evaluations = {
            config_id: _evaluate_fold_map(fold_map, spec, baselines.get(asset))
            for config_id, fold_map in grouped[asset].items()
        }
        outcome = select_for_asset(evaluations)
        selected_id = outcome["selected_config_id"]
        selected_evaluation = evaluations.get(selected_id) if selected_id else None
        result[asset] = {
            "status": outcome["selection_status"],
            "economic_status": outcome["economic_status"],
            "config_id": selected_id,
            "gates": selected_evaluation["gates"] if selected_evaluation else None,
            "ranking": selected_evaluation["ranking"] if selected_evaluation else None,
            "counts": {key: value for key, value in outcome.items() if key.startswith("configs_")},
            "neighbor_analysis": (neighbor_analysis(selected_id, neighbors, evaluations, asset)
                                  if selected_id and config_manifest else None),
        }
    return result

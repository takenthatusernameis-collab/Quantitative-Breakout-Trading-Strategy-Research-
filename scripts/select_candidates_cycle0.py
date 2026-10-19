#!/usr/bin/env python3
"""Re-derive per-asset candidates for a campaign cycle under the preregistered rule.

Read-only, offline and holdout-safe:

* only records with ``is_holdout == false`` are consumed, and the script asserts
  that exactly zero holdout records were read;
* the buy-and-hold baseline required by the ``median_sharpe_gt_buyhold`` gate is
  recomputed from the frozen candle datasets, and every dataset is hash-verified
  against ``research/data_manifest.json`` before it is used;
* the preregistered field semantics are pinned in ``SPEC_MAPPING`` instead of
  being chosen silently by the implementation.

Every field of ``configs/research_v1.json`` -> ``selection`` is either
implemented (see ``SPEC_MAPPING``) or explicitly reported as ``NOT_EVALUABLE``
together with the exact missing input. The output artifact records the
expected-versus-verified unit counts, the per-gate table, the selected
configuration (or ``NO_CANDIDATE`` / ``INSUFFICIENT_EVIDENCE``), the divergence
from the frozen candidate manifest, and the parameter-neighbourhood analysis.

The script never writes into ``src/``; it is an analysis tool, not the
production selector. The production selector is a separate, design-gated task
(``research_state/brainstorming_queue.md`` -> BRAIN-006).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import Candle, CostScenario  # noqa: E402
from breakout_research.data.fetcher import compute_content_hash  # noqa: E402

COST_BASELINE = 1.0
COST_DOUBLE = 2.0
DEFAULT_INITIAL_CAPITAL = 10000.0
SHARPE_PERIODS_PER_YEAR = 365.0

# Metric-set variants used for the interpretation-sensitivity check. The
# preregistered specification does not state whether a "validation-fold" metric
# is the baseline-cost value, the median across cost scenarios, or the pooled
# set of units, so every variant is evaluated and the outcome is reported.
VARIANT_BASELINE = "baseline_costs_folds"
VARIANT_FOLD_MEDIAN_COSTS = "fold_median_across_costs"
VARIANT_POOLED = "pooled_fold_cost_units"
VARIANT_STRICT_MIN_TRADES = "strict_min_trades_in_every_fold"
VARIANT_COMPOUND_COMBINED = "combined_net_return_compounded"
VARIANTS = (
    VARIANT_BASELINE,
    VARIANT_FOLD_MEDIAN_COSTS,
    VARIANT_POOLED,
    VARIANT_STRICT_MIN_TRADES,
    VARIANT_COMPOUND_COMBINED,
)
# variant -> (metric mode, strict per-fold trade floor, compounded combined return)
VARIANT_SETTINGS: Dict[str, Dict[str, Any]] = {
    VARIANT_BASELINE: {"metric_mode": VARIANT_BASELINE, "strict_min_trades": False, "compound_combined_return": False},
    VARIANT_FOLD_MEDIAN_COSTS: {"metric_mode": VARIANT_FOLD_MEDIAN_COSTS, "strict_min_trades": False, "compound_combined_return": False},
    VARIANT_POOLED: {"metric_mode": VARIANT_POOLED, "strict_min_trades": False, "compound_combined_return": False},
    VARIANT_STRICT_MIN_TRADES: {"metric_mode": VARIANT_BASELINE, "strict_min_trades": True, "compound_combined_return": False},
    VARIANT_COMPOUND_COMBINED: {"metric_mode": VARIANT_BASELINE, "strict_min_trades": False, "compound_combined_return": True},
}

# spec field -> status, implementation, exact semantics, source of the input
SPEC_MAPPING: Dict[str, Dict[str, str]] = {
    "max_candidates_per_asset": {
        "status": "IMPLEMENTED",
        "implementation": "select_for_asset",
        "semantics": "At most one candidate per asset is selected.",
        "input": "configs/research_v1.json -> selection.max_candidates_per_asset",
    },
    "min_trades_total": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.min_trades_total",
        "semantics": (
            "Sum of trade_count over the four validation folds at baseline (1x) costs. "
            "Cost scenarios are the same trades re-costed, so they are not summed again."
        ),
        "input": "result records: trade_count, fold_index, cost_multiplier",
    },
    "min_trades_per_fold": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.min_trades_per_fold",
        "semantics": (
            "Per-fold trade floor of min_trades_per_fold at baseline (1x) costs. README section 9 "
            "pairs this floor with min_folds_with_min_trades: 'at least 5 in at least three of the "
            "four folds', so the floor is required in min_folds_with_min_trades folds and not in every "
            "fold. The stricter reading (the floor in every fold) is evaluated as the sensitivity "
            "variant strict_min_trades_in_every_fold."
        ),
        "input": "result records: trade_count, fold_index, cost_multiplier",
    },
    "min_folds_with_min_trades": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.min_folds_with_min_trades",
        "semantics": "Number of validation folds whose baseline-cost trade_count reaches min_trades_per_fold.",
        "input": "result records: trade_count, fold_index, cost_multiplier",
    },
    "positive_net_return_baseline": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.positive_net_return_baseline",
        "semantics": (
            "Mean of the four fold net_total_return values at baseline (1x) costs is > 0. "
            "The preregistered wording is 'combined validation net return'; the mean and the "
            "sum of the fold returns share the same sign, so the gate is invariant to that choice."
        ),
        "input": "result records: net_total_return, fold_index, cost_multiplier",
    },
    "positive_net_return_2x_costs": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.positive_net_return_2x_costs",
        "semantics": "Mean of the four fold net_total_return values at 2x costs is > 0.",
        "input": "result records: net_total_return, fold_index, cost_multiplier",
    },
    "positive_folds_required": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.positive_folds_required",
        "semantics": "Number of validation folds with net_total_return > 0 at baseline (1x) costs.",
        "input": "result records: net_total_return, fold_index, cost_multiplier",
    },
    "median_sharpe_gt_zero": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.gates.median_sharpe_gt_zero",
        "semantics": (
            "Median of the per-fold daily_sharpe values at baseline (1x) costs is > 0. "
            "Folds without a defined Sharpe (no trades, constant equity) are excluded and the "
            "number of folds used is reported."
        ),
        "input": "result records: daily_sharpe, fold_index, cost_multiplier",
    },
    "median_sharpe_gt_buyhold": {
        "status": "IMPLEMENTED_VIA_RECOMPUTED_BASELINE",
        "implementation": "build_buyhold_baseline / evaluate_config.gates.median_sharpe_gt_buyhold",
        "semantics": (
            "Median of the per-fold strategy daily_sharpe values at baseline (1x) costs is greater "
            "than the median of the per-fold buy-and-hold daily_sharpe values of the same asset over "
            "the same fold windows at the same costs. The buy-and-hold baseline is recomputed from the "
            "frozen, hash-verified candle datasets; the result ledger itself contains no baseline field."
        ),
        "input": "research/data/candles/*.csv (verified against research/data_manifest.json) + fold windows",
    },
    "ranking_metric": {
        "status": "IMPLEMENTED",
        "implementation": "evaluate_config.ranking.median_net_daily_sharpe",
        "semantics": "Descending median net daily Sharpe across the validation folds.",
        "input": "result records: daily_sharpe, fold_index, cost_multiplier",
    },
    "tiebreakers": {
        "status": "IMPLEMENTED",
        "implementation": "rank_key",
        "semantics": (
            "median_net_return (higher first), then max_drawdown (lower first; the worst fold "
            "drawdown), then turnover (lower first; the median fold turnover), then config_id "
            "(lexicographic ascending)."
        ),
        "input": "result records: net_total_return, max_drawdown, turnover, config_id",
    },
    "neighbor_analysis": {
        "status": "IMPLEMENTED_AS_REPORTED_ANALYSIS",
        "implementation": "neighbor_analysis",
        "semantics": (
            "Parameter-neighbourhood stability analysis for the selected configuration: the "
            "mechanical neighbours (one dimension, one adjacent value), their net performance "
            "distribution, the share with positive validation returns and the median neighbour score. "
            "The specification defines no threshold, so this is reported and not used as a gate."
        ),
        "input": "research/config_manifest.json + result records",
    },
}

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

# status, trade_count, net_total_return, daily_sharpe, max_drawdown, turnover
Unit = Tuple[str, int, float, Optional[float], float, float]

FoldMap = Dict[int, Dict[float, Unit]]


class HoldoutRecordError(RuntimeError):
    """Raised when a holdout record reaches the selection path."""


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant: {name}")


def load_json(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_constant)


def _cost_key(value: Any) -> float:
    return round(float(value), 6)


def iter_shard_records(shard_root: Path) -> Iterator[Dict[str, Any]]:
    """Yield every record of a shard set without holding the set in memory."""
    for path in sorted(Path(shard_root).glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line, parse_constant=_reject_constant)


def aggregate_records(records: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, FoldMap]], Dict[str, Any]]:
    """Group validation records by asset, configuration, fold and cost scenario.

    Holdout records are refused rather than filtered silently: the selection
    must never consume an exposed holdout unit.
    """
    units: Dict[str, Dict[str, FoldMap]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    windows: Dict[Tuple[str, int], Tuple[int, int]] = {}
    stats: Dict[str, Any] = {
        "records_read": 0,
        "holdout_records_read": 0,
        "status_counts": Counter(),
        "non_completed_status_counts": Counter(),
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
                f"asset={record.get('asset')} config={record.get('config_id')}"
            )
        status = str(record.get("status"))
        stats["status_counts"][status] += 1
        if status != "COMPLETED":
            stats["non_completed_status_counts"][status] += 1
        asset = str(record["asset"])
        config_id = str(record["config_id"])
        fold_index = int(record["fold_index"])
        cost = _cost_key(record["cost_multiplier"])
        stats["assets"].add(asset)
        stats["folds"].add(fold_index)
        stats["costs"].add(cost)
        key = (asset, fold_index)
        bounds = (int(record["start_time"]), int(record["end_time"]))
        if key in windows and windows[key] != bounds:
            raise ValueError(f"inconsistent fold bounds for {key}: {windows[key]} != {bounds}")
        windows[key] = bounds
        fold_map = units[asset][config_id]
        if cost in fold_map.get(fold_index, {}):
            stats["duplicate_units"] += 1
        fold_map[fold_index][cost] = (
            status,
            int(record.get("trade_count") or 0),
            float(record.get("net_total_return") or 0.0),
            None if record.get("daily_sharpe") is None else float(record["daily_sharpe"]),
            float(record.get("max_drawdown") or 0.0),
            float(record.get("turnover") or 0.0),
        )
    stats["status_counts"] = dict(sorted(stats["status_counts"].items()))
    stats["non_completed_status_counts"] = dict(sorted(stats["non_completed_status_counts"].items()))
    stats["assets"] = sorted(stats["assets"])
    stats["folds"] = sorted(stats["folds"])
    stats["costs"] = sorted(stats["costs"])
    stats["fold_windows"] = {asset: {str(fold): list(bounds) for (a, fold), bounds in sorted(windows.items()) if a == asset}
                             for asset in stats["assets"]}
    grouped = {asset: {cid: {fold: dict(costs) for fold, costs in folds.items()}
                       for cid, folds in configs.items()}
               for asset, configs in units.items()}
    return grouped, stats


def daily_returns_from_equity(equity_curve: Sequence[float], timestamps: Sequence[int]) -> List[float]:
    """Daily returns from an hourly equity curve, aligned by UTC calendar day.

    Mirrors ``breakout_research.backtest.backtester._compute_daily_returns``:
    the last equity value of each calendar day is used, and the return series
    starts at the second observed day.
    """
    from datetime import datetime, timezone

    daily_equity: Dict[str, float] = {}
    for ts, equity in zip(timestamps, equity_curve):
        day = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        daily_equity[day] = equity
    days = sorted(daily_equity)
    returns: List[float] = []
    for index in range(1, len(days)):
        previous = daily_equity[days[index - 1]]
        current = daily_equity[days[index]]
        if previous > 0:
            returns.append((current - previous) / previous)
    return returns


def annualized_sharpe(daily_returns: Sequence[float]) -> Optional[float]:
    """Annualized Sharpe of a daily return series on the 365-day crypto calendar."""
    if len(daily_returns) < 2:
        return None
    mean = statistics.fmean(daily_returns)
    variance = statistics.variance(daily_returns)
    if variance <= 0:
        return None
    return mean / (variance ** 0.5) * (SHARPE_PERIODS_PER_YEAR ** 0.5)


def max_drawdown_from_equity(equity_curve: Sequence[float], initial_capital: float) -> float:
    """Maximum drawdown of an equity curve, mirroring the backtester."""
    running_max = initial_capital
    max_dd = 0.0
    for equity in equity_curve:
        if equity > running_max:
            running_max = equity
        if running_max > 0:
            drawdown = (running_max - equity) / running_max
            if drawdown > max_dd:
                max_dd = drawdown
    return max_dd


def _apply_costs(price: float, qty: float, taker_fee_bps: float, slippage_bps: float, is_entry: bool) -> Tuple[float, float, float]:
    """Apply slippage and taker fee exactly as the backtester does."""
    slippage = slippage_bps / 10000.0
    fee_rate = taker_fee_bps / 10000.0
    if is_entry:
        effective_price = price * (1.0 + slippage)
        notional = price * qty
        fee = notional * fee_rate
        slippage_amount = (effective_price - price) * qty
    else:
        effective_price = price * (1.0 - slippage)
        notional = price * qty
        fee = notional * fee_rate
        slippage_amount = (price - effective_price) * qty
    return effective_price, fee, slippage_amount


def buyhold_fold_metrics(candles: Sequence[Candle], start_time: int, end_time: int,
                         cost_scenario: CostScenario,
                         initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> Dict[str, Any]:
    """Buy-and-hold metrics for one fold window, on the strategy's conventions.

    The position is opened at the first bar's open of the window, marked to
    market at every bar close, and flattened at the last bar's close (the
    preregistered boundary-fill convention). Entry and exit costs follow the
    campaign's cost scenario, so the baseline is comparable in capital
    assumptions and cost rules.
    """
    window = [c for c in candles if start_time <= c.timestamp < end_time]
    if len(window) < 2:
        return {"status": "NOT_EVALUABLE", "reason": "fewer than two candles in the fold window", "bars": len(window)}

    entry_price = window[0].open
    qty = initial_capital / entry_price if entry_price > 0 else 0.0
    if qty <= 0:
        return {"status": "NOT_EVALUABLE", "reason": "non-positive entry price", "bars": len(window)}
    effective_entry, entry_fee, entry_slippage = _apply_costs(
        entry_price, qty, cost_scenario.taker_fee_bps, cost_scenario.slippage_bps, True)
    cost_total = effective_entry * qty
    if cost_total > initial_capital:
        qty = initial_capital / effective_entry
        cost_total = effective_entry * qty
    cash = initial_capital - cost_total

    equity_curve: List[float] = []
    timestamps: List[int] = []
    for candle in window:
        equity_curve.append(cash + qty * candle.close)
        timestamps.append(candle.timestamp)

    exit_price = window[-1].close
    effective_exit, exit_fee, exit_slippage = _apply_costs(
        exit_price, qty, cost_scenario.taker_fee_bps, cost_scenario.slippage_bps, False)
    cash_after_exit = qty * effective_exit - exit_fee

    daily_returns = daily_returns_from_equity(equity_curve, timestamps)
    sharpe = annualized_sharpe(daily_returns)
    total_fees = entry_fee + exit_fee
    total_slippage = entry_slippage + exit_slippage
    turnover = (qty * entry_price + qty * exit_price) / initial_capital
    return {
        "status": "OK",
        "bars": len(window),
        "start_time": int(window[0].timestamp),
        "end_time": int(window[-1].timestamp),
        "cost_multiplier": cost_scenario.multiplier,
        "net_total_return": (equity_curve[-1] - initial_capital) / initial_capital,
        "net_total_return_after_exit_costs": (cash_after_exit - initial_capital) / initial_capital,
        "daily_sharpe": sharpe,
        "daily_return_days": len(daily_returns),
        "max_drawdown": max_drawdown_from_equity(equity_curve, initial_capital),
        "turnover": turnover,
        "fee_drag": total_fees / initial_capital,
        "slippage_drag": total_slippage / initial_capital,
        "entry_price": entry_price,
        "exit_price": exit_price,
    }


def load_verified_candles(asset: str, data_manifest: Dict[str, Any], repo_root: Path) -> Tuple[List[Candle], Dict[str, Any]]:
    """Load an asset's frozen candles and verify them against the data manifest."""
    entry = data_manifest.get("assets", {}).get(asset)
    if entry is None:
        raise KeyError(f"asset {asset} is not present in the data manifest")
    dataset_path = (Path(repo_root) / entry["dataset_path"]).resolve()
    from breakout_research.data.fetcher import _read_dataset

    candles = _read_dataset(dataset_path)
    observed_hash = compute_content_hash(candles)
    if observed_hash != entry["content_hash"]:
        raise ValueError(
            f"candle dataset hash mismatch for {asset}: "
            f"manifest {entry['content_hash']} != observed {observed_hash}")
    provenance = {
        "dataset_path": entry["dataset_path"],
        "content_hash": observed_hash,
        "hash_verified": True,
        "provider": entry.get("provider"),
        "endpoint": entry.get("endpoint"),
        "first_candle_timestamp": entry.get("first_candle_timestamp"),
        "last_candle_timestamp": entry.get("last_candle_timestamp"),
        "observed_candle_count": entry.get("observed_candle_count"),
        "fallback_used": entry.get("fallback_used"),
    }
    return candles, provenance


def _fold_values(fold_map: FoldMap, cost: float) -> Dict[int, Unit]:
    return {fold: costs[cost] for fold, costs in fold_map.items() if cost in costs}


def _fold_sharpes(fold_map: FoldMap) -> List[float]:
    return [unit[3] for costs in fold_map.values() for unit in costs.values() if unit[3] is not None]


def _metric_set(fold_map: FoldMap, cost: float, median_across_costs: bool) -> Dict[int, Dict[str, Optional[float]]]:
    """Per-fold metric values for one configuration.

    ``median_across_costs`` selects the median of the cost scenarios of a fold
    instead of the value of a single cost scenario.
    """
    result: Dict[int, Dict[str, Optional[float]]] = {}
    for fold, costs in sorted(fold_map.items()):
        if median_across_costs:
            units = list(costs.values())
        else:
            if cost not in costs:
                continue
            units = [costs[cost]]
        sharpes = [unit[3] for unit in units if unit[3] is not None]
        result[fold] = {
            "net_return": statistics.median([unit[2] for unit in units]),
            "sharpe": statistics.median(sharpes) if sharpes else None,
            "max_dd": max(unit[4] for unit in units),
            "turnover": statistics.median([unit[5] for unit in units]),
            "trades": units[0][1],
        }
    return result


def _combined_return(values: Sequence[float], compound: bool) -> float:
    """Combined validation net return across folds.

    The preregistered wording is 'combined validation net return'. The mean of
    the fold returns is used by default; the compounded product of the fold
    returns is evaluated as a sensitivity variant because the two can differ in
    sign.
    """
    if not values:
        return 0.0
    if not compound:
        return statistics.fmean(values)
    growth = 1.0
    for value in values:
        growth *= (1.0 + value)
    return growth - 1.0


def evaluate_config(fold_map: FoldMap, selection_spec: Dict[str, Any],
                    buyhold: Dict[str, Any], mode: str,
                    strict_min_trades: bool = False,
                    compound_combined_return: bool = False) -> Dict[str, Any]:
    """Evaluate every preregistered gate for one configuration."""
    median_across_costs = mode == VARIANT_FOLD_MEDIAN_COSTS
    baseline = _metric_set(fold_map, COST_BASELINE, median_across_costs)
    double = _metric_set(fold_map, COST_DOUBLE, False)
    folds = sorted(baseline)

    trades_total = sum(int(baseline[fold]["trades"]) for fold in folds)
    per_fold_trades = {str(fold): int(baseline[fold]["trades"]) for fold in folds}
    min_per_fold_trades = min(per_fold_trades.values()) if per_fold_trades else 0
    folds_with_min_trades = sum(
        1 for fold in folds if int(baseline[fold]["trades"]) >= int(selection_spec["min_trades_per_fold"]))

    combined_return_baseline = _combined_return(
        [float(baseline[fold]["net_return"]) for fold in folds], compound_combined_return)
    combined_return_2x = _combined_return(
        [float(double[fold]["net_return"]) for fold in double], compound_combined_return)
    positive_folds = sum(1 for fold in folds if float(baseline[fold]["net_return"]) > 0)

    fold_sharpes = [baseline[fold]["sharpe"] for fold in folds if baseline[fold]["sharpe"] is not None]
    if mode == VARIANT_POOLED:
        pooled = _fold_sharpes(fold_map)
        median_sharpe = statistics.median(pooled) if pooled else None
        sharpe_folds_used = len(pooled)
    else:
        median_sharpe = statistics.median(fold_sharpes) if fold_sharpes else None
        sharpe_folds_used = len(fold_sharpes)

    buyhold_sharpe = buyhold.get(mode)
    buyhold_status = buyhold.get("status", "NOT_EVALUABLE")

    gates: Dict[str, Dict[str, Any]] = {}
    gates_threshold = {
        "min_trades_total": selection_spec["min_trades_total"],
        "min_trades_per_fold": selection_spec["min_trades_per_fold"],
        "min_folds_with_min_trades": selection_spec["min_folds_with_min_trades"],
        "positive_net_return_baseline": "> 0",
        "positive_net_return_2x_costs": "> 0",
        "positive_folds_required": selection_spec["positive_folds_required"],
        "median_sharpe_gt_zero": "> 0",
        "median_sharpe_gt_buyhold": "> 0",
    }

    def add(name: str, value: Any, threshold: Any, passed: Optional[bool], **extra: Any) -> None:
        entry: Dict[str, Any] = {"value": value, "threshold": threshold, "pass": passed}
        entry.update(extra)
        gates[name] = entry

    def not_evaluable(name: str, missing: str, **extra: Any) -> None:
        entry: Dict[str, Any] = {
            "value": None, "threshold": gates_threshold[name], "pass": None,
            "status": "NOT_EVALUABLE", "missing": missing,
        }
        entry.update(extra)
        gates[name] = entry


    if not baseline:
        for name in ("min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
                     "positive_net_return_baseline", "positive_folds_required", "median_sharpe_gt_zero"):
            not_evaluable(name, "no baseline-cost (1x) validation records for this configuration")
    else:
        add("min_trades_total", trades_total, selection_spec["min_trades_total"],
            trades_total >= int(selection_spec["min_trades_total"]),
            unit="closed trades over the validation folds at 1x costs")
        add("min_trades_per_fold", min_per_fold_trades, selection_spec["min_trades_per_fold"],
            (min_per_fold_trades >= int(selection_spec["min_trades_per_fold"]))
            if strict_min_trades else (folds_with_min_trades >= int(selection_spec["min_folds_with_min_trades"])),
            per_fold_trades=per_fold_trades,
            folds_meeting_floor=folds_with_min_trades,
            reading=("every fold" if strict_min_trades
                     else f"at least {selection_spec['min_folds_with_min_trades']} of {len(folds)} folds"),
            unit="minimum fold trade count at 1x costs")
        add("min_folds_with_min_trades", folds_with_min_trades, selection_spec["min_folds_with_min_trades"],
            folds_with_min_trades >= int(selection_spec["min_folds_with_min_trades"]),
            unit="folds with at least min_trades_per_fold trades")
        add("positive_net_return_baseline", combined_return_baseline, "> 0",
            combined_return_baseline > 0,
            aggregation=("compounded" if compound_combined_return else "mean"),
            unit="combined fold net return at 1x costs")
        add("positive_folds_required", positive_folds, selection_spec["positive_folds_required"],
            positive_folds >= int(selection_spec["positive_folds_required"]),
            unit="folds with positive net return at 1x costs")
        add("median_sharpe_gt_zero", median_sharpe, "> 0",
            None if median_sharpe is None else median_sharpe > 0,
            sharpe_folds_used=sharpe_folds_used, unit="median fold daily Sharpe at 1x costs")

    if not double:
        not_evaluable("positive_net_return_2x_costs", "no 2x-cost validation records for this configuration")
    else:
        add("positive_net_return_2x_costs", combined_return_2x, "> 0",
            combined_return_2x > 0,
            aggregation=("compounded" if compound_combined_return else "mean"),
            unit="combined fold net return at 2x costs")

    if buyhold_status == "OK" and buyhold_sharpe is not None and median_sharpe is not None:
        add("median_sharpe_gt_buyhold", median_sharpe - buyhold_sharpe, "> 0",
            median_sharpe > buyhold_sharpe,
            strategy_median_sharpe=median_sharpe, buyhold_median_sharpe=buyhold_sharpe,
            unit="median fold daily Sharpe, strategy minus buy-and-hold")
    else:
        add("median_sharpe_gt_buyhold", None, "> 0", None,
            status="NOT_EVALUABLE",
            missing=buyhold.get("reason", "buy-and-hold baseline unavailable"),
            unit="median fold daily Sharpe")

    evaluable = [name for name in GATE_ORDER if gates[name].get("status") != "NOT_EVALUABLE"]
    not_evaluable = [name for name in GATE_ORDER if name not in evaluable]
    failed = [name for name in GATE_ORDER if gates[name]["pass"] is False]
    all_pass = not failed and not not_evaluable
    passes_evaluable = not failed
    sample_ok = not [name for name in failed if name in SAMPLE_GATES]
    economic_ok = not [name for name in failed if name in ECONOMIC_GATES]

    median_net_return = statistics.median([float(baseline[fold]["net_return"]) for fold in folds]) if folds else 0.0
    worst_drawdown = max((float(baseline[fold]["max_dd"]) for fold in folds), default=0.0)
    median_turnover = statistics.median([float(baseline[fold]["turnover"]) for fold in folds]) if folds else 0.0

    return {
        "gates": gates,
        "all_pass": all_pass,
        "passes_evaluable_gates": passes_evaluable,
        "sample_gates_pass": sample_ok,
        "economic_gates_pass": economic_ok,
        "failed_gates": failed,
        "not_evaluable_gates": not_evaluable,
        "ranking": {
            "median_net_daily_sharpe": median_sharpe,
            "median_net_return": median_net_return,
            "max_drawdown": worst_drawdown,
            "turnover": median_turnover,
        },
        "folds_evaluated": len(folds),
        "sharpe_folds_used": sharpe_folds_used,
    }


def rank_key(evaluation: Dict[str, Any], config_id: str) -> Tuple[Any, ...]:
    """Sort key implementing the preregistered ranking and tiebreakers."""
    ranking = evaluation["ranking"]
    sharpe = ranking["median_net_daily_sharpe"]
    return (
        -(sharpe if sharpe is not None else float("-inf")),
        -ranking["median_net_return"],
        ranking["max_drawdown"],
        ranking["turnover"],
        config_id,
    )


def build_buyhold_baseline(candles: Sequence[Candle], fold_windows: Dict[str, Tuple[int, int]],
                            cost_scenarios: Sequence[CostScenario]) -> Dict[str, Any]:
    """Per-fold and per-cost buy-and-hold metrics for one asset."""
    per_cost: Dict[str, Any] = {}
    fold_sharpes_by_cost: Dict[str, List[float]] = {}
    pooled_sharpes: List[float] = []
    for scenario in cost_scenarios:
        folds: Dict[str, Any] = {}
        sharpes: List[float] = []
        for fold_index, (start_time, end_time) in sorted(fold_windows.items()):
            metrics = buyhold_fold_metrics(candles, start_time, end_time, scenario)
            folds[str(fold_index)] = metrics
            if metrics.get("status") == "OK" and metrics.get("daily_sharpe") is not None:
                sharpes.append(float(metrics["daily_sharpe"]))
                pooled_sharpes.append(float(metrics["daily_sharpe"]))
        fold_sharpes_by_cost[str(scenario.multiplier)] = sharpes
        per_cost[str(scenario.multiplier)] = {
            "folds": folds,
            "median_daily_sharpe": statistics.median(sharpes) if sharpes else None,
            "sharpe_folds_used": len(sharpes),
            "status": "OK" if sharpes else "NOT_EVALUABLE",
        }

    fold_median_across_costs: List[float] = []
    for fold_index in sorted(fold_windows):
        values = [
            float(per_cost[str(scenario.multiplier)]["folds"][str(fold_index)]["daily_sharpe"])
            for scenario in cost_scenarios
            if per_cost[str(scenario.multiplier)]["folds"][str(fold_index)].get("status") == "OK"
            and per_cost[str(scenario.multiplier)]["folds"][str(fold_index)].get("daily_sharpe") is not None
        ]
        if values:
            fold_median_across_costs.append(statistics.median(values))

    return {
        "per_cost": per_cost,
        "variant_median_sharpe": {
            VARIANT_BASELINE: (statistics.median(fold_sharpes_by_cost.get(str(COST_BASELINE), []))
                                if fold_sharpes_by_cost.get(str(COST_BASELINE)) else None),
            VARIANT_FOLD_MEDIAN_COSTS: (statistics.median(fold_median_across_costs)
                                        if fold_median_across_costs else None),
            VARIANT_POOLED: statistics.median(pooled_sharpes) if pooled_sharpes else None,
        },
    }


def neighbor_index(config_manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    """Mechanical parameter neighbours: one dimension, one adjacent value."""
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
                neighbour_index = index + offset
                if 0 <= neighbour_index < len(values):
                    key = [str(entry[dimension]) for dimension in dimensions]
                    key[list(dimensions).index(name)] = str(values[neighbour_index])
                    neighbour_id = by_parameters.get(tuple(key))
                    if neighbour_id is not None and neighbour_id != config_id:
                        neighbors[config_id].append(neighbour_id)
        neighbors[config_id] = sorted(set(neighbors[config_id]))
    return neighbors


def neighbor_analysis(selected_config_id: str, neighbors: Dict[str, List[str]],
                      evaluations: Dict[str, Dict[str, Any]], asset: str) -> Dict[str, Any]:
    """Parameter-neighbourhood stability analysis for a selected configuration."""
    neighbour_ids = neighbors.get(selected_config_id, [])
    neighbour_rows: List[Dict[str, Any]] = []
    for neighbour_id in neighbour_ids:
        evaluation = evaluations.get(neighbour_id)
        if evaluation is None:
            continue
        neighbour_rows.append({
            "config_id": neighbour_id,
            "median_net_return": evaluation["ranking"]["median_net_return"],
            "median_net_daily_sharpe": evaluation["ranking"]["median_net_daily_sharpe"],
            "all_gates_pass": evaluation["all_pass"],
        })
    if not neighbour_rows:
        return {"status": "NO_NEIGHBOURS_EVALUATED", "neighbor_count": 0, "asset": asset}
    positive = [row for row in neighbour_rows
                if row["median_net_return"] is not None and row["median_net_return"] > 0]
    sharpes = [row["median_net_daily_sharpe"] for row in neighbour_rows
               if row["median_net_daily_sharpe"] is not None]
    return {
        "status": "OK",
        "asset": asset,
        "selected_config_id": selected_config_id,
        "neighbor_count": len(neighbour_rows),
        "neighbors_with_positive_validation_return": len(positive),
        "neighbors_with_positive_validation_return_pct": round(100.0 * len(positive) / len(neighbour_rows), 4),
        "median_neighbor_median_net_return": statistics.median(
            [row["median_net_return"] for row in neighbour_rows if row["median_net_return"] is not None]),
        "median_neighbor_median_net_daily_sharpe": statistics.median(sharpes) if sharpes else None,
        "neighbors_passing_all_gates": sum(1 for row in neighbour_rows if row["all_gates_pass"]),
        "neighbors": neighbour_rows,
    }


def select_for_asset(evaluations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the preregistered rule to one asset's configurations.

    Status taxonomy (README section 9: a configuration below the sample floor
    is 'insufficient evidence', not an economic failure):

    * ``CANDIDATE_SELECTED`` - at least one configuration passes every gate;
    * ``CANDIDATE_SELECTED_WITH_UNEVALUABLE_GATES`` - configurations pass every
      evaluable gate but one gate could not be evaluated, so the selection is
      not confirmed;
    * ``INSUFFICIENT_EVIDENCE`` - configurations pass every economic gate and
      fail only the sample-size floor;
    * ``NO_CANDIDATE`` - no configuration passes the economic screen.
    """
    qualifying = [cid for cid, evaluation in evaluations.items() if evaluation["all_pass"]]
    qualifying_evaluable = [cid for cid, evaluation in evaluations.items() if evaluation["passes_evaluable_gates"]]
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


def analyze_cycle(shard_root: Path, spec: Dict[str, Any], data_manifest: Dict[str, Any],
                  config_manifest: Dict[str, Any], candidate_manifest: Dict[str, Any],
                  repo_root: Path) -> Dict[str, Any]:
    """Re-derive candidates for every asset of a cycle under the preregistered rule."""
    selection_spec = spec["selection"]
    scenarios = [CostScenario.baseline().scaled(multiplier) for multiplier in spec["costs"]["scenarios"]]

    units, stats = aggregate_records(iter_shard_records(shard_root))
    assets = sorted(units)
    total_configurations = int(config_manifest.get("total_configurations") or len(config_manifest["configurations"]))

    buyhold_baselines: Dict[str, Any] = {}
    for asset in assets:
        fold_windows = {
            int(fold): (int(bounds[0]), int(bounds[1]))
            for fold, bounds in stats["fold_windows"].get(asset, {}).items()
        }
        try:
            candles, provenance = load_verified_candles(asset, data_manifest, repo_root)
        except (KeyError, ValueError) as exc:
            buyhold_baselines[asset] = {
                "status": "NOT_EVALUABLE",
                "reason": f"candle dataset unavailable: {exc}",
                "per_cost": {},
                "variant_median_sharpe": {},
                "provenance": None,
            }
            continue
        baseline = build_buyhold_baseline(candles, fold_windows, scenarios)
        baseline["status"] = "OK" if baseline["variant_median_sharpe"].get(VARIANT_BASELINE) is not None else "NOT_EVALUABLE"
        baseline["reason"] = None if baseline["status"] == "OK" else "buy-and-hold baseline not computable"
        baseline["provenance"] = provenance
        buyhold_baselines[asset] = baseline

    neighbors = neighbor_index(config_manifest)
    frozen_candidates = candidate_manifest.get("candidates", {})

    asset_results: Dict[str, Any] = {}
    for asset in assets:
        buyhold = buyhold_baselines[asset]
        buyhold_input = {
            "status": buyhold.get("status", "NOT_EVALUABLE"),
            "reason": buyhold.get("reason") or "buy-and-hold baseline not computable",
            **{variant: buyhold.get("variant_median_sharpe", {}).get(variant) for variant in VARIANTS},
        }

        evaluations_by_variant: Dict[str, Dict[str, Dict[str, Any]]] = {}
        per_variant: Dict[str, Dict[str, Any]] = {}
        for mode in VARIANTS:
            settings = VARIANT_SETTINGS[mode]
            evaluations = {
                config_id: evaluate_config(fold_map, selection_spec, buyhold_input,
                                           settings["metric_mode"],
                                           settings["strict_min_trades"],
                                           settings["compound_combined_return"])
                for config_id, fold_map in units[asset].items()
            }
            evaluations_by_variant[mode] = evaluations
            per_variant[mode] = select_for_asset(evaluations)

        primary_evaluations = evaluations_by_variant[VARIANT_BASELINE]
        primary = per_variant[VARIANT_BASELINE]
        selected_id = primary["selected_config_id"]
        selected_evaluation = primary_evaluations.get(selected_id) if selected_id else None

        gate_failure_counts: Counter = Counter()
        for evaluation in primary_evaluations.values():
            for name in GATE_ORDER:
                if evaluation["gates"][name].get("pass") is not True:
                    gate_failure_counts[name] += 1

        per_config: List[Dict[str, Any]] = []
        for config_id in sorted(primary_evaluations):
            evaluation = primary_evaluations[config_id]
            per_config.append({
                "config_id": config_id,
                "failed_gates": evaluation["failed_gates"],
                "not_evaluable_gates": evaluation["not_evaluable_gates"],
                "all_gates_pass": evaluation["all_pass"],
                "median_net_daily_sharpe": evaluation["ranking"]["median_net_daily_sharpe"],
                "median_net_return": evaluation["ranking"]["median_net_return"],
                "max_drawdown": evaluation["ranking"]["max_drawdown"],
                "turnover": evaluation["ranking"]["turnover"],
                "trades_total": evaluation["gates"]["min_trades_total"]["value"],
                "folds_with_min_trades": evaluation["gates"]["min_folds_with_min_trades"]["value"],
                "positive_folds": evaluation["gates"]["positive_folds_required"]["value"],
            })

        frozen_entry = frozen_candidates.get(asset, {})
        frozen_id = frozen_entry.get("config_id") if isinstance(frozen_entry, dict) else None
        matches_frozen = bool(selected_id) and selected_id == frozen_id

        asset_results[asset] = {
            "configs_with_records": len(primary_evaluations),
            "selection_status": primary["selection_status"],
            "economic_status": primary["economic_status"],
            "selected_config_id": selected_id,
            "selected_gates": selected_evaluation["gates"] if selected_evaluation else None,
            "selected_ranking": selected_evaluation["ranking"] if selected_evaluation else None,
            "selected_not_evaluable_gates": selected_evaluation["not_evaluable_gates"] if selected_evaluation else [],
            "counts": {key: value for key, value in primary.items() if key.startswith("configs_")},
            "gate_failure_counts": dict(sorted(gate_failure_counts.items())),
            "frozen_manifest_config_id": frozen_id,
            "matches_frozen_manifest": matches_frozen,
            "divergence": (
                "none" if matches_frozen else
                ("no candidate under the preregistered rule" if selected_id is None
                 else f"preregistered rule selects {selected_id}, frozen manifest holds {frozen_id}")
            ),
            "buyhold_baseline": {
                "status": buyhold_input["status"],
                "variant_median_sharpe": buyhold.get("variant_median_sharpe", {}),
                "per_cost": buyhold.get("per_cost", {}),
                "provenance": buyhold.get("provenance"),
            },
            "sensitivity": {
                mode: {
                    "selected_config_id": per_variant[mode]["selected_config_id"],
                    "selection_status": per_variant[mode]["selection_status"],
                    "configs_passing_all_gates": per_variant[mode]["configs_passing_all_gates"],
                }
                for mode in VARIANTS
            },
            "neighbor_analysis": neighbor_analysis(selected_id, neighbors, primary_evaluations, asset) if selected_id else None,
            "per_config": per_config,
        }

    selected_assets = [asset for asset, info in asset_results.items() if info["selected_config_id"]]
    matching_assets = [asset for asset in selected_assets if asset_results[asset]["matches_frozen_manifest"]]
    expected_folds = len(spec.get("folds", {}).get("window_fractions", [])) or len(stats["folds"])
    expected_costs = len(spec.get("costs", {}).get("scenarios", [])) or len(stats["costs"])
    expected_units = len(stats["assets"]) * total_configurations * expected_folds * expected_costs
    return {
        "artifact": "candidate_selection",
        "protocol_version": spec.get("protocol_version"),
        "specification_hash": spec.get("specification_hash"),
        "selection_spec": selection_spec,
        "spec_mapping": SPEC_MAPPING,
        "inputs": {
            "records_read": stats["records_read"],
            "holdout_records_read": stats["holdout_records_read"],
            "status_counts": stats["status_counts"],
            "non_completed_status_counts": stats["non_completed_status_counts"],
            "assets": stats["assets"],
            "asset_count": len(stats["assets"]),
            "fold_indexes": stats["folds"],
            "cost_multipliers": stats["costs"],
            "duplicate_units": stats["duplicate_units"],
            "total_configurations": total_configurations,
            "expected_units": expected_units,
            "expected_units_definition": (
                "observed assets x configuration count x preregistered validation windows "
                "x preregistered cost scenarios"),
            "verified_units": stats["records_read"],
            "coverage_pct": round(100.0 * stats["records_read"] / expected_units, 6) if expected_units else None,
        },
        "summary": {
            "assets": len(asset_results),
            "assets_with_candidate": len(selected_assets),
            "assets_without_candidate": len(asset_results) - len(selected_assets),
            "assets_matching_frozen_manifest": len(matching_assets),
            "selection_status_counts": dict(sorted(Counter(
                info["selection_status"] for info in asset_results.values()).items())),
            "sensitivity_agreement_with_primary": {
                mode: sum(1 for asset in assets
                          if asset_results[asset]["sensitivity"][mode]["selected_config_id"]
                          == asset_results[asset]["sensitivity"][VARIANT_BASELINE]["selected_config_id"])
                for mode in VARIANTS
            },
        },
        "assets": asset_results,
    }


def resolve_shard_root(cycle_root: Path) -> Path:
    """Resolve the directory that holds a cycle's ``*.jsonl`` result shards."""
    candidates = [path for path in sorted(cycle_root.rglob("*")) if path.is_dir() and any(path.glob("*.jsonl"))]
    if not candidates:
        raise SystemExit(f"no result shards found under {cycle_root}")
    if len(candidates) > 1:
        raise SystemExit(f"ambiguous shard sets under {cycle_root}: {[str(c) for c in candidates]}")
    return candidates[0]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cycle_root", help="cycle directory containing results_shards/<campaign_id>/")
    parser.add_argument("--out", default=None, help="artifact path (default: <cycle_root>/candidate_selection.json)")
    parser.add_argument("--spec", default=str(REPO_ROOT / "configs" / "research_v1.json"))
    parser.add_argument("--data-manifest", default=str(REPO_ROOT / "research" / "data_manifest.json"))
    parser.add_argument("--config-manifest", default=str(REPO_ROOT / "research" / "config_manifest.json"))
    parser.add_argument("--candidates-manifest", default=str(REPO_ROOT / "research" / "candidate_manifest.json"))
    args = parser.parse_args(argv)

    cycle_root = Path(args.cycle_root).resolve()
    shard_root = resolve_shard_root(cycle_root)

    spec = load_json(Path(args.spec))
    data_manifest = load_json(Path(args.data_manifest))
    config_manifest = load_json(Path(args.config_manifest))
    candidate_manifest = load_json(Path(args.candidates_manifest))

    artifact = analyze_cycle(shard_root, spec, data_manifest, config_manifest, candidate_manifest, REPO_ROOT)

    out_path = Path(args.out) if args.out else cycle_root / "candidate_selection.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "output": str(out_path),
        "records_read": artifact["inputs"]["records_read"],
        "holdout_records_read": artifact["inputs"]["holdout_records_read"],
        "summary": artifact["summary"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

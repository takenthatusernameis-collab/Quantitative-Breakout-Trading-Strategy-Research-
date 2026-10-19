"""Buy-and-hold baseline metrics for the preregistered selection rule (BRAIN-006).

The baseline is computed on the campaign's own conventions, not on conventions
invented for the baseline:

* costs are applied with ``backtest.backtester._apply_costs`` (slippage on the
  execution price, taker fee on the slippage-adjusted notional);
* daily returns use ``backtest.backtester._compute_daily_returns`` (last equity
  value of each UTC calendar day, return series starting at the second
  observed day);
* the annualized Sharpe uses the 365-day crypto calendar and the sample
  standard deviation, exactly as ``backtester._compute_metrics`` does;
* maximum drawdown is taken from the hourly equity curve, as in the backtester.

The position is opened at the first bar's open of the fold window, marked to
market at every bar close and flattened at the last bar's close, so the
baseline is comparable with the strategy in capital assumptions, cost rules and
boundary handling.

Every candle dataset is hash-verified against ``research/data_manifest.json``
before it is used.  The selector consumes the resulting baseline artifact and
fails closed when it is missing or when the recorded data hash no longer
matches (BRAIN-006 decision record, section 5: option B3).
"""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .backtest.backtester import _apply_costs, _compute_daily_returns
from .config import Candle, CostScenario

SHARPE_PERIODS_PER_YEAR = 365.0
DEFAULT_INITIAL_CAPITAL = 10000.0
COST_BASELINE = 1.0
COST_DOUBLE = 2.0

# Metric-set variants of the preregistered rule.  The pinned reading of the
# BRAIN-006 decision record is VARIANT_BASELINE; the other two exist so the
# independent analysis path (``scripts/select_candidates_cycle0.py``) can report
# the sensitivity of the selection to the interpretation.
VARIANT_BASELINE = "baseline_costs_folds"
VARIANT_FOLD_MEDIAN_COSTS = "fold_median_across_costs"
VARIANT_POOLED = "pooled_fold_cost_units"

VARIANTS = (VARIANT_BASELINE, VARIANT_FOLD_MEDIAN_COSTS, VARIANT_POOLED)


class BaselineDataError(RuntimeError):
    """Raised when a baseline cannot be computed from verified data."""


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def data_manifest_content_hash(data_manifest: Dict[str, Any]) -> str:
    """Canonical content hash of the data manifest (as used by the pilot gate)."""
    canonical = json.dumps(data_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def artifact_hash(artifact: Dict[str, Any], exclude: Sequence[str] = ()) -> str:
    """Content hash of an artifact body, excluding the hash fields themselves."""
    body = {key: value for key, value in artifact.items() if key not in set(exclude)}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def daily_returns_from_equity(equity_curve: Sequence[float], timestamps: Sequence[int]) -> List[float]:
    """Daily returns of an hourly equity curve, aligned by UTC calendar day."""
    return list(_compute_daily_returns(list(equity_curve), list(timestamps)))


def annualized_sharpe(daily_returns: Sequence[float]) -> Optional[float]:
    """Annualized Sharpe of a daily return series on the 365-day crypto calendar.

    A constant or too-short return series has no defined Sharpe: ``None`` is
    returned instead of a non-standard JSON value.
    """
    returns = list(daily_returns)
    if len(returns) < 2:
        return None
    variance = statistics.variance(returns)
    if variance <= 0:
        return None
    mean = statistics.fmean(returns)
    return mean / (variance ** 0.5) * (SHARPE_PERIODS_PER_YEAR ** 0.5)


def max_drawdown_from_equity(equity_curve: Sequence[float], initial_capital: float) -> float:
    """Maximum drawdown of an hourly equity curve, as computed by the backtester."""
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


def buyhold_fold_metrics(candles: Sequence[Candle], start_time: int, end_time: int,
                         cost_scenario: CostScenario,
                         initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> Dict[str, Any]:
    """Buy-and-hold metrics for one fold window, on the strategy's conventions.

    The position is fully invested from the first bar's open of the window and
    flattened at the last bar's close.  The position size is reduced so that the
    entry notional *including* its taker fee never exceeds the capital, which
    keeps the equity curve free of leverage and free of a cash drag.
    """
    window = [c for c in candles if start_time <= c.timestamp < end_time]
    if len(window) < 2:
        return {
            "status": "NOT_EVALUABLE",
            "reason": "fewer than two candles in the fold window",
            "bars": len(window),
        }

    entry_price = window[0].open
    if entry_price <= 0:
        return {
            "status": "NOT_EVALUABLE",
            "reason": "non-positive entry price",
            "bars": len(window),
        }

    slippage_rate = cost_scenario.slippage_bps / 10000.0
    fee_rate = cost_scenario.taker_fee_bps / 10000.0
    effective_entry = entry_price * (1.0 + slippage_rate)
    if effective_entry <= 0:
        return {
            "status": "NOT_EVALUABLE",
            "reason": "non-positive effective entry price",
            "bars": len(window),
        }
    quantity = initial_capital / (effective_entry * (1.0 + fee_rate))
    _, entry_fee, entry_slippage = _apply_costs(
        entry_price, quantity, cost_scenario.taker_fee_bps, cost_scenario.slippage_bps, True)
    cash = initial_capital - effective_entry * quantity - entry_fee
    if abs(cash) > 1e-6:
        raise BaselineDataError(
            f"buy-and-hold entry accounting is inconsistent: residual cash {cash}")
    cash = 0.0

    equity_curve: List[float] = []
    timestamps: List[int] = []
    for candle in window:
        equity_curve.append(cash + quantity * candle.close)
        timestamps.append(candle.timestamp)

    exit_price = window[-1].close
    effective_exit, exit_fee, exit_slippage = _apply_costs(
        exit_price, quantity, cost_scenario.taker_fee_bps, cost_scenario.slippage_bps, False)
    cash_after_exit = quantity * effective_exit - exit_fee

    daily_returns = daily_returns_from_equity(equity_curve, timestamps)
    sharpe = annualized_sharpe(daily_returns)
    total_fees = entry_fee + exit_fee
    total_slippage = entry_slippage + exit_slippage
    turnover = (quantity * entry_price + quantity * exit_price) / initial_capital
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


def buyhold_baseline(candles: Sequence[Candle], fold_windows: Dict[int, Tuple[int, int]],
                     cost_scenarios: Sequence[CostScenario],
                     initial_capital: float = DEFAULT_INITIAL_CAPITAL) -> Dict[str, Any]:
    """Per-fold and per-cost buy-and-hold metrics for one asset.

    ``fold_windows`` maps a fold index to the inclusive/exclusive
    ``(start_time, end_time)`` millisecond bounds of that validation window.
    """
    per_cost: Dict[str, Any] = {}
    fold_sharpes_by_cost: Dict[str, List[float]] = {}
    pooled_sharpes: List[float] = []
    for scenario in cost_scenarios:
        folds: Dict[str, Any] = {}
        sharpes: List[float] = []
        for fold_index, (start_time, end_time) in sorted(fold_windows.items()):
            metrics = buyhold_fold_metrics(candles, start_time, end_time, scenario, initial_capital)
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
        values = []
        for scenario in cost_scenarios:
            fold_metrics = per_cost[str(scenario.multiplier)]["folds"][str(fold_index)]
            if fold_metrics.get("status") == "OK" and fold_metrics.get("daily_sharpe") is not None:
                values.append(float(fold_metrics["daily_sharpe"]))
        if values:
            fold_median_across_costs.append(statistics.median(values))

    baseline_sharpes = fold_sharpes_by_cost.get(str(COST_BASELINE), [])
    variant_sharpes = {
        VARIANT_BASELINE: statistics.median(baseline_sharpes) if baseline_sharpes else None,
        VARIANT_FOLD_MEDIAN_COSTS: (statistics.median(fold_median_across_costs)
                                    if fold_median_across_costs else None),
        VARIANT_POOLED: statistics.median(pooled_sharpes) if pooled_sharpes else None,
    }
    status = "OK" if variant_sharpes[VARIANT_BASELINE] is not None else "NOT_EVALUABLE"
    return {
        "status": status,
        "reason": None if status == "OK" else "buy-and-hold baseline not computable",
        "per_cost": per_cost,
        "variant_median_sharpe": variant_sharpes,
    }


def load_verified_candles(asset: str, data_manifest: Dict[str, Any],
                           repo_root: Path) -> Tuple[List[Candle], Dict[str, Any]]:
    """Load an asset's frozen candles and verify them against the data manifest."""
    entry = data_manifest.get("assets", {}).get(asset)
    if entry is None:
        raise KeyError(f"asset {asset} is not present in the data manifest")
    dataset_path = (Path(repo_root) / entry["dataset_path"]).resolve()
    from .data.fetcher import _read_dataset, compute_content_hash

    candles = _read_dataset(dataset_path)
    observed_hash = compute_content_hash(candles)
    if observed_hash != entry["content_hash"]:
        raise BaselineDataError(
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


def baseline_for_asset(artifact: Dict[str, Any], asset: str) -> Dict[str, Any]:
    """Selector-facing view of one asset's entry in a baseline artifact.

    Fails closed: a missing asset, a missing artifact or a non-``OK`` baseline
    is reported as ``NOT_EVALUABLE`` instead of silently passing the
    ``median_sharpe_gt_buyhold`` gate.
    """
    assets = artifact.get("assets", {})
    entry = assets.get(asset)
    if entry is None:
        return {"status": "NOT_EVALUABLE", "reason": f"no baseline artifact entry for {asset}",
                "median_daily_sharpe": None}
    status = entry.get("status", "NOT_EVALUABLE")
    sharpe = entry.get("variant_median_sharpe", {}).get(VARIANT_BASELINE)
    if status != "OK" or sharpe is None:
        return {
            "status": "NOT_EVALUABLE",
            "reason": entry.get("reason") or "buy-and-hold baseline unavailable",
            "median_daily_sharpe": None,
        }
    return {
        "status": "OK",
        "reason": None,
        "median_daily_sharpe": float(sharpe),
        "variant_median_sharpe": entry.get("variant_median_sharpe", {}),
    }


def verify_baseline_artifact(artifact: Dict[str, Any], data_manifest: Dict[str, Any]) -> None:
    """Fail closed when a baseline artifact does not match the current data."""
    recorded = artifact.get("data_manifest_hash")
    observed = data_manifest_content_hash(data_manifest)
    if recorded != observed:
        raise BaselineDataError(
            f"baseline artifact data manifest hash mismatch: recorded {recorded} != observed {observed}")
    expected_hash = artifact.get("baseline_hash")
    if expected_hash is not None:
        observed_hash = artifact_hash(artifact, exclude=("baseline_hash",))
        if expected_hash != observed_hash:
            raise BaselineDataError(
                f"baseline artifact hash mismatch: recorded {expected_hash} != observed {observed_hash}")

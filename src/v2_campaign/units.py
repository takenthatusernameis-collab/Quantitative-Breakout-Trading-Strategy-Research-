"""Fold structure and unit enumeration of the v2 selection run.

The fold structure is the **unchanged v1 rule**: the validation windows are the
inherited ``folds`` block of the research specification, computed over the span
of the evaluated dataset, with the final holdout-position fold excluded from
selection exactly as the v1 validation campaign excludes it.

In v2 the holdout is not the tail of the dataset: the confirmatory window is
fresh data that is read only after the selected-configuration manifest is
committed and hash-bound. The selection run therefore evaluates the four
validation folds and never the holdout-position fold, and it never reads a
confirmatory-window candle at all.

The unit order is the v1 campaign order -- asset, then configuration, then
fold, then cost scenario -- so that the run is deterministic and resumable.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from breakout_research.backtest.shards import compute_experiment_id
from breakout_research.config import CostScenario, StrategyConfig, TrendFilter

FoldBounds = Tuple[int, int, int, bool]


def fold_bounds(candles: Sequence[Any], folds: Dict[str, Any]) -> List[FoldBounds]:
    """The v1 fold structure: validation windows plus the holdout-position fold.

    Returns ``(start_time, end_time, fold_index, is_holdout)`` tuples. The
    holdout-position fold is returned so that the caller can see it, and the
    selection run skips it.
    """
    if not candles:
        return []
    first_ts = int(candles[0].timestamp)
    last_ts = int(candles[-1].timestamp)
    total_span = last_ts - first_ts
    dev_fraction = folds["development_fraction"]
    window_fractions = list(folds["window_fractions"])

    bounds: List[FoldBounds] = []
    dev_end_ts = first_ts + int(total_span * dev_fraction)
    for index, fraction in enumerate(window_fractions):
        window_start = first_ts + int(total_span * fraction)
        if index == len(window_fractions) - 1:
            window_end = dev_end_ts
        else:
            window_end = first_ts + int(total_span * window_fractions[index + 1])
        bounds.append((window_start, window_end, index, False))
    bounds.append((dev_end_ts, last_ts, len(window_fractions), True))
    return bounds


def validation_folds(bounds: Sequence[FoldBounds]) -> List[FoldBounds]:
    """The validation folds only; the holdout-position fold is never selected on."""
    return [bound for bound in bounds if not bound[3]]


def unit_data_hash(asset_symbol: str, config: StrategyConfig, data_hashes: Dict[str, str]) -> str:
    """The hash of the dataset(s) a unit's result depends on.

    This is the v1 rule: a BTC trend-filter unit depends on the asset's data
    and on the BTC benchmark dataset, every other unit depends on the asset's
    data only.
    """
    base = data_hashes.get(asset_symbol, "")
    if config.trend_filter == TrendFilter.BTC_EMA_168:
        btc_hash = data_hashes.get("BTCUSDT", "")
        if base and btc_hash:
            return hashlib.sha256(f"{base}:{btc_hash}".encode("utf-8")).hexdigest()
        return base or btc_hash or ""
    return base


def iter_units(
    assets: Sequence[Dict[str, Any]],
    configs: Sequence[StrategyConfig],
    cost_multipliers: Sequence[float],
    fold_windows: Sequence[FoldBounds],
    data_hashes: Dict[str, str],
    specification_hash: str,
    code_identity: str,
    asset_index: int = 0,
) -> Iterator[Tuple[Dict[str, Any], str]]:
    """Yield ``(unit, experiment_id)`` in the v1 campaign order.

    Only validation folds are produced: the holdout-position fold is skipped,
    and every unit is marked ``is_holdout = False``.
    """
    asset_symbol = str(assets[asset_index]["symbol"])
    for config_index, config in enumerate(configs):
        for start_time, end_time, fold_index, _is_holdout in fold_windows:
            for cost_index, cost_multiplier in enumerate(cost_multipliers):
                cost_scenario = CostScenario.baseline().scaled(cost_multiplier)
                data_hash = unit_data_hash(asset_symbol, config, data_hashes)
                experiment_id = compute_experiment_id(
                    spec_hash=specification_hash,
                    code_hash=code_identity,
                    data_hash=data_hash,
                    asset=asset_symbol,
                    config_id=config.config_id,
                    fold_index=fold_index,
                    start_time=int(start_time),
                    end_time=int(end_time),
                    is_holdout=False,
                    cost_multiplier=float(cost_multiplier),
                )
                unit = {
                    "asset_index": asset_index,
                    "config_index": config_index,
                    "fold_index": fold_index,
                    "cost_index": cost_index,
                    "asset": asset_symbol,
                    "config": config,
                    "cost_scenario": cost_scenario,
                    "start_time": int(start_time),
                    "end_time": int(end_time),
                    "is_holdout": False,
                }
                yield unit, experiment_id


def planned_unit_counts(
    asset_count: int,
    config_count: int,
    fold_count: int,
    cost_count: int,
) -> Dict[str, int]:
    """The size of the bounded run, in config units and in execution units."""
    config_units = asset_count * config_count
    return {
        "config_units": config_units,
        "execution_units": config_units * fold_count * cost_count,
    }


__all__ = [
    "FoldBounds",
    "fold_bounds",
    "iter_units",
    "planned_unit_counts",
    "unit_data_hash",
    "validation_folds",
]

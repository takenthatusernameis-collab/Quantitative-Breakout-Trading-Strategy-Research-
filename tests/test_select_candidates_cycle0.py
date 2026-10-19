"""Tests for the preregistered-rule candidate re-derivation script.

The script under test is a read-only analysis tool:
``scripts/select_candidates_cycle0.py``. It re-derives the per-asset candidate
set of a campaign cycle under the rule frozen in
``configs/research_v1.json`` -> ``selection`` and compares it with the frozen
candidate manifest. The tests pin the metric conventions against the campaign
backtester, the preregistered gate semantics, the tiebreak order, the holdout
refusal, and the reproducibility of the artifact.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest import backtester  # noqa: E402
from breakout_research.config import Candle, CostScenario  # noqa: E402
from breakout_research.data.fetcher import (  # noqa: E402
    _serialize_dataset,
    compute_content_hash,
)


def _load_selector():
    path = REPO_ROOT / "scripts" / "select_candidates_cycle0.py"
    spec = importlib.util.spec_from_file_location("select_candidates_cycle0", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sel = _load_selector()

SELECTION_SPEC = {
    "max_candidates_per_asset": 1,
    "min_trades_total": 30,
    "min_trades_per_fold": 5,
    "min_folds_with_min_trades": 3,
    "positive_net_return_baseline": True,
    "positive_net_return_2x_costs": True,
    "positive_folds_required": 3,
    "median_sharpe_gt_zero": True,
    "median_sharpe_gt_buyhold": True,
    "ranking_metric": "median_net_daily_sharpe",
    "tiebreakers": ["median_net_return", "max_drawdown", "turnover", "config_id"],
    "neighbor_analysis": True,
}

BUYHOLD_OK = {
    "status": "OK",
    sel.VARIANT_BASELINE: -0.5,
    sel.VARIANT_FOLD_MEDIAN_COSTS: -0.5,
    sel.VARIANT_POOLED: -0.5,
    "reason": None,
}


def unit(trades: int, net_return: float, sharpe: float | None, max_dd: float = 0.1, turnover: float = 10.0):
    return ("COMPLETED", trades, net_return, sharpe, max_dd, turnover)


def fold_map(per_fold: List[tuple], cost_multiplier: float = 1.0) -> Dict[int, Dict[float, tuple]]:
    """Build a fold map from (trades, net_return, sharpe) triples, one per fold."""
    result: Dict[int, Dict[float, tuple]] = {}
    for index, (trades, net_return, sharpe) in enumerate(per_fold):
        result[index] = {cost_multiplier: unit(trades, net_return, sharpe)}
    return result


def full_fold_map(per_fold: List[tuple], two_x_return: float | None = None) -> Dict[int, Dict[float, tuple]]:
    """Fold map with the baseline (1x) and the 2x cost scenario for every fold."""
    result: Dict[int, Dict[float, tuple]] = {}
    for index, (trades, net_return, sharpe) in enumerate(per_fold):
        doubled = net_return if two_x_return is None else two_x_return
        result[index] = {
            1.0: unit(trades, net_return, sharpe),
            2.0: unit(trades, doubled, sharpe),
        }
    return result


def qualifying_fold_map(**overrides: Any) -> Dict[int, Dict[float, tuple]]:
    per_fold = [
        (10, 0.20, 1.0),
        (10, 0.10, 0.8),
        (10, -0.05, -0.2),
        (10, 0.30, 1.2),
    ]
    return full_fold_map(per_fold)


# --- metric conventions -------------------------------------------------


def test_daily_returns_match_backtester_convention():
    timestamps = [1_700_000_000_000 + 3_600_000 * index for index in range(72)]
    equity = [100.0 + index for index in range(72)]
    assert sel.daily_returns_from_equity(equity, timestamps) == backtester._compute_daily_returns(equity, timestamps)


def test_annualized_sharpe_matches_backtester_metrics():
    timestamps = [1_700_000_000_000 + 3_600_000 * index for index in range(48)]
    equity = [100.0 * (1.01 ** (index % 5)) for index in range(48)]
    metrics = backtester._compute_metrics(equity, timestamps, [], 100.0, 0.0, 0.0, 0.0)
    local = sel.annualized_sharpe(sel.daily_returns_from_equity(equity, timestamps))
    assert local == pytest.approx(metrics["daily_sharpe"])


def test_max_drawdown_matches_backtester_metrics():
    timestamps = [1_700_000_000_000 + 3_600_000 * index for index in range(10)]
    equity = [100.0, 120.0, 90.0, 95.0, 80.0, 130.0]
    metrics = backtester._compute_metrics(equity, timestamps, [], 100.0, 0.0, 0.0, 0.0)
    assert sel.max_drawdown_from_equity(equity, 100.0) == pytest.approx(metrics["max_drawdown"])


# --- buy-and-hold baseline ---------------------------------------------


def _flat_candles(count: int = 48, price: float = 100.0, start: int = 1_700_000_000_000) -> List[Candle]:
    return [
        Candle(timestamp=start + 3_600_000 * index, open=price, high=price, low=price, close=price, volume=1.0)
        for index in range(count)
    ]


def test_buyhold_baseline_is_reduced_by_round_trip_costs():
    candles = _flat_candles()
    metrics = sel.buyhold_fold_metrics(
        candles, candles[0].timestamp, candles[-1].timestamp + 1, CostScenario.baseline())
    assert metrics["status"] == "OK"
    # A flat price with 10 bps taker fee and 5 bps slippage per side loses money.
    assert metrics["net_total_return"] == pytest.approx(-0.0005, abs=1e-3)
    assert metrics["net_total_return_after_exit_costs"] < metrics["net_total_return"]
    assert metrics["daily_sharpe"] is None or metrics["daily_sharpe"] == pytest.approx(0.0, abs=1e-9)


def test_buyhold_baseline_captures_a_rising_market():
    candles = [
        Candle(timestamp=1_700_000_000_000 + 3_600_000 * index, open=100.0 + index, high=100.0 + index,
              low=100.0 + index, close=100.0 + index, volume=1.0)
        for index in range(48)
    ]
    metrics = sel.buyhold_fold_metrics(
        candles, candles[0].timestamp, candles[-1].timestamp + 1, CostScenario.baseline())
    assert metrics["net_total_return"] > 0.4
    assert metrics["daily_sharpe"] is not None and metrics["daily_sharpe"] > 0


def test_buyhold_baseline_reports_not_evaluable_for_short_windows():
    candles = _flat_candles(count=1)
    metrics = sel.buyhold_fold_metrics(
        candles, candles[0].timestamp, candles[-1].timestamp + 1, CostScenario.baseline())
    assert metrics["status"] == "NOT_EVALUABLE"


# --- preregistered gates ------------------------------------------------


def test_config_passing_every_gate_is_qualifying():
    evaluation = sel.evaluate_config(
        qualifying_fold_map(), SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    assert evaluation["all_pass"] is True
    assert evaluation["failed_gates"] == []
    assert evaluation["ranking"]["median_net_daily_sharpe"] == pytest.approx(statistics.median([1.0, 0.8, -0.2, 1.2]))


def test_min_trades_total_is_counted_once_per_fold_at_baseline_costs():
    fold_map_ = qualifying_fold_map()
    fold_map_[0][2.0] = unit(10, 0.20, 1.0)
    fold_map_[0][3.0] = unit(10, 0.20, 1.0)
    fold_map_[1][2.0] = unit(10, 0.10, 0.8)
    fold_map_[1][3.0] = unit(10, 0.10, 0.8)
    evaluation = sel.evaluate_config(fold_map_, SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    # 40 trades, not 120: the cost scenarios are the same trades re-costed.
    assert evaluation["gates"]["min_trades_total"]["value"] == 40
    assert evaluation["gates"]["min_trades_total"]["pass"] is True


def test_per_fold_trade_floor_is_required_in_at_least_three_folds():
    per_fold = [(10, 0.20, 1.0), (10, 0.20, 1.0), (10, 0.20, 1.0), (0, 0.0, None)]
    evaluation = sel.evaluate_config(
        full_fold_map(per_fold), SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    assert evaluation["gates"]["min_folds_with_min_trades"]["value"] == 3
    assert evaluation["gates"]["min_folds_with_min_trades"]["pass"] is True
    # The strict reading (the floor in every fold) is a separate sensitivity variant.
    strict = sel.evaluate_config(
        full_fold_map(per_fold), SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE, strict_min_trades=True)
    assert strict["gates"]["min_trades_per_fold"]["pass"] is False


def test_buyhold_gate_blocks_a_strategy_below_the_baseline():
    buyhold = dict(BUYHOLD_OK)
    buyhold[sel.VARIANT_BASELINE] = 2.0
    evaluation = sel.evaluate_config(
        qualifying_fold_map(), SELECTION_SPEC, buyhold, sel.VARIANT_BASELINE)
    assert evaluation["gates"]["median_sharpe_gt_buyhold"]["pass"] is False
    assert evaluation["all_pass"] is False


def test_buyhold_gate_is_marked_not_evaluable_without_a_baseline():
    buyhold = {"status": "NOT_EVALUABLE", "reason": "no candle dataset", **{variant: None for variant in sel.VARIANTS}}
    evaluation = sel.evaluate_config(
        qualifying_fold_map(), SELECTION_SPEC, buyhold, sel.VARIANT_BASELINE)
    gate = evaluation["gates"]["median_sharpe_gt_buyhold"]
    assert gate["pass"] is None
    assert gate["status"] == "NOT_EVALUABLE"
    assert "no candle dataset" in gate["missing"]
    assert evaluation["all_pass"] is False
    assert evaluation["not_evaluable_gates"] == ["median_sharpe_gt_buyhold"]


def test_sample_floor_failure_is_insufficient_evidence_not_economic_failure():
    per_fold = [(2, 0.20, 1.0), (2, 0.20, 1.0), (2, 0.20, 1.0), (2, 0.20, 1.0)]
    evaluation = sel.evaluate_config(
        full_fold_map(per_fold), SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    selection = sel.select_for_asset({"cfg_0001": evaluation})
    assert evaluation["economic_gates_pass"] is True
    assert evaluation["sample_gates_pass"] is False
    assert selection["selection_status"] == "INSUFFICIENT_EVIDENCE"
    assert selection["economic_status"] == "INSUFFICIENT_EVIDENCE"
    assert selection["selected_config_id"] is None


def test_economic_failure_is_no_candidate():
    per_fold = [(10, -0.20, -1.0), (10, -0.10, -0.5), (10, -0.05, -0.2), (10, -0.30, -1.5)]
    evaluation = sel.evaluate_config(
        full_fold_map(per_fold), SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    selection = sel.select_for_asset({"cfg_0001": evaluation})
    assert evaluation["economic_gates_pass"] is False
    assert selection["selection_status"] == "NO_CANDIDATE"
    assert selection["economic_status"] == "NO_CANDIDATE"


# --- ranking and tiebreakers -------------------------------------------


def test_tiebreakers_follow_the_preregistered_order():
    higher_return = sel.evaluate_config(
        full_fold_map([(10, 0.30, 1.0), (10, 0.20, 1.0), (10, 0.10, 1.0), (10, 0.05, 1.0)]),
        SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    lower_return = sel.evaluate_config(
        full_fold_map([(10, 0.20, 1.0), (10, 0.10, 1.0), (10, 0.05, 1.0), (10, 0.00, 1.0)]),
        SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    selection = sel.select_for_asset({"cfg_0002": lower_return, "cfg_0001": higher_return})
    assert selection["selected_config_id"] == "cfg_0001"

    lower_drawdown = sel.evaluate_config(
        full_fold_map([(10, 0.30, 1.0), (10, 0.20, 1.0), (10, 0.10, 1.0), (10, 0.05, 1.0)]),
        SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    lower_drawdown["ranking"]["max_drawdown"] = 0.05
    higher_drawdown = sel.evaluate_config(
        full_fold_map([(10, 0.30, 1.0), (10, 0.20, 1.0), (10, 0.10, 1.0), (10, 0.05, 1.0)]),
        SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    higher_drawdown["ranking"]["max_drawdown"] = 0.20
    selection = sel.select_for_asset({"cfg_0002": higher_drawdown, "cfg_0001": lower_drawdown})
    assert selection["selected_config_id"] == "cfg_0001"

    same = sel.evaluate_config(
        full_fold_map([(10, 0.30, 1.0), (10, 0.20, 1.0), (10, 0.10, 1.0), (10, 0.05, 1.0)]),
        SELECTION_SPEC, BUYHOLD_OK, sel.VARIANT_BASELINE)
    selection = sel.select_for_asset({"cfg_0002": dict(same), "cfg_0001": dict(same)})
    assert selection["selected_config_id"] == "cfg_0001"  # lexicographic config_id tiebreak


# --- holdout safety -----------------------------------------------------


def test_holdout_records_are_refused():
    record = {
        "asset": "BTCUSDT", "config_id": "cfg_0000", "fold_index": 4, "cost_multiplier": 1.0,
        "status": "COMPLETED", "trade_count": 3, "net_total_return": 0.1, "daily_sharpe": 1.0,
        "max_drawdown": 0.1, "turnover": 1.0, "is_holdout": True, "start_time": 0, "end_time": 1,
    }
    with pytest.raises(sel.HoldoutRecordError):
        sel.aggregate_records([record])


def test_validation_records_are_aggregated_without_holdout():
    records = []
    for fold in range(4):
        records.append({
            "asset": "BTCUSDT", "config_id": "cfg_0000", "fold_index": fold, "cost_multiplier": 1.0,
            "status": "COMPLETED", "trade_count": 3, "net_total_return": 0.1, "daily_sharpe": 1.0,
            "max_drawdown": 0.1, "turnover": 1.0, "is_holdout": False, "start_time": 0, "end_time": 100,
        })
    units, stats = sel.aggregate_records(records)
    assert stats["holdout_records_read"] == 0
    assert stats["records_read"] == 4
    assert units["BTCUSDT"]["cfg_0000"][0][1.0][1] == 3


# --- neighbours ---------------------------------------------------------


def test_neighbor_index_is_mechanical():
    config_manifest = json.loads((REPO_ROOT / "research" / "config_manifest.json").read_text(encoding="utf-8"))
    neighbors = sel.neighbor_index(config_manifest)
    configurations = {entry["config_id"]: entry for entry in config_manifest["configurations"]}
    dimensions = list(config_manifest["dimensions"])
    for config_id, entry in list(configurations.items())[:50]:
        for neighbour_id in neighbors[config_id]:
            neighbour = configurations[neighbour_id]
            differences = [dimension for dimension in dimensions
                           if str(entry[dimension]) != str(neighbour[dimension])]
            assert len(differences) == 1
            values = config_manifest["dimensions"][differences[0]]
            distance = abs(values.index(entry[differences[0]]) - values.index(neighbour[differences[0]]))
            assert distance == 1


# --- end to end ---------------------------------------------------------


def _write_synthetic_cycle(tmp_path: Path) -> Path:
    """Write a one-asset, one-configuration cycle plus its candle dataset."""
    import random

    hour = 3_600_000
    start = 1_700_000_000_000
    bars_per_fold = 120
    generator = random.Random(20261019)
    candles: List[Candle] = []
    price = 100.0
    for index in range(bars_per_fold * 4):
        price *= (1.0 + generator.uniform(-0.004, 0.004))
        candles.append(Candle(timestamp=start + hour * index, open=price, high=price,
                              low=price, close=price, volume=1.0))

    data_dir = tmp_path / "data" / "candles"
    data_dir.mkdir(parents=True)
    dataset_path = data_dir / "TESTUSDT_1h_test.csv"
    dataset_path.write_text(_serialize_dataset(candles), encoding="utf-8")
    data_manifest = {
        "assets": {
            "TESTUSDT": {
                "dataset_path": str(dataset_path.relative_to(tmp_path)),
                "content_hash": compute_content_hash(candles),
                "provider": "test", "endpoint": "none", "fallback_used": False,
                "first_candle_timestamp": candles[0].timestamp,
                "last_candle_timestamp": candles[-1].timestamp,
                "observed_candle_count": len(candles),
            }
        }
    }
    (tmp_path / "data_manifest.json").write_text(json.dumps(data_manifest), encoding="utf-8")

    config_manifest = {
        "total_configurations": 2,
        "dimensions": {"entry_rule": ["a", "b"], "entry_lookback": [12, 24]},
        "configurations": [
            {"config_id": "cfg_0000", "entry_rule": "a", "entry_lookback": 12},
            {"config_id": "cfg_0001", "entry_rule": "b", "entry_lookback": 24},
        ],
    }
    (tmp_path / "config_manifest.json").write_text(json.dumps(config_manifest), encoding="utf-8")
    (tmp_path / "candidate_manifest.json").write_text(
        json.dumps({"frozen": True, "candidates": {"TESTUSDT": {"config_id": "cfg_0001"}}}),
        encoding="utf-8")

    fold_bounds = [
        (start + hour * bars_per_fold * index, start + hour * bars_per_fold * (index + 1))
        for index in range(4)
    ]
    # The strategy must beat the buy-and-hold baseline it is compared against.
    baseline_sharpes = [
        sel.buyhold_fold_metrics(candles, fold_start, fold_end, CostScenario.baseline())["daily_sharpe"]
        for fold_start, fold_end in fold_bounds
    ]
    defined = [value for value in baseline_sharpes if value is not None]
    strategy_sharpe = (max(defined) if defined else 0.0) + 1.0

    shard_dir = tmp_path / "cycle" / "results_shards" / "campaign"
    shard_dir.mkdir(parents=True)
    lines = []
    for fold, (fold_start, fold_end) in enumerate(fold_bounds):
        for cost in (1.0, 2.0):
            lines.append(json.dumps({
                "asset": "TESTUSDT", "config_id": "cfg_0000", "fold_index": fold,
                "cost_multiplier": cost, "status": "COMPLETED", "trade_count": 10,
                "net_total_return": 0.2 if cost == 1.0 else 0.15, "daily_sharpe": strategy_sharpe,
                "max_drawdown": 0.2, "turnover": 12.0, "is_holdout": False,
                "start_time": fold_start, "end_time": fold_end,
            }))
    (shard_dir / "shard_000000.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def test_end_to_end_artifact_is_reproducible_and_holdout_free(tmp_path: Path):
    root = _write_synthetic_cycle(tmp_path)
    spec = {"protocol_version": "v1", "specification_hash": "test", "selection": SELECTION_SPEC,
            "costs": {"scenarios": [1.0, 2.0, 3.0]}}
    (root / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    shard_root = root / "cycle" / "results_shards" / "campaign"

    artifact = sel.analyze_cycle(
        shard_root,
        spec,
        json.loads((root / "data_manifest.json").read_text(encoding="utf-8")),
        json.loads((root / "config_manifest.json").read_text(encoding="utf-8")),
        json.loads((root / "candidate_manifest.json").read_text(encoding="utf-8")),
        root,
    )
    assert artifact["inputs"]["holdout_records_read"] == 0
    assert artifact["inputs"]["expected_units"] == 1 * 4 * 3 * 2
    assert artifact["inputs"]["records_read"] == 8
    assert artifact["assets"]["TESTUSDT"]["selected_config_id"] == "cfg_0000"
    assert artifact["assets"]["TESTUSDT"]["matches_frozen_manifest"] is False
    assert artifact["assets"]["TESTUSDT"]["selected_gates"]["min_trades_total"]["value"] == 40
    assert artifact["assets"]["TESTUSDT"]["buyhold_baseline"]["status"] == "OK"
    assert artifact["summary"]["assets_with_candidate"] == 1
    # Every preregistered field is mapped to an implementation.
    assert set(artifact["spec_mapping"]) == set(SELECTION_SPEC)
    assert all(entry["status"].startswith("IMPLEMENTED") for entry in artifact["spec_mapping"].values())

    again = sel.analyze_cycle(
        shard_root,
        spec,
        json.loads((root / "data_manifest.json").read_text(encoding="utf-8")),
        json.loads((root / "config_manifest.json").read_text(encoding="utf-8")),
        json.loads((root / "candidate_manifest.json").read_text(encoding="utf-8")),
        root,
    )
    assert json.dumps(artifact, sort_keys=True) == json.dumps(again, sort_keys=True)

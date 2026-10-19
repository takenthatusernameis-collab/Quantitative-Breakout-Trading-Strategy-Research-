"""Unit tests for the conforming preregistered selector (BRAIN-006).

Every fixture is a synthetic software fixture.  No fixture is market history
and no test in this file makes an economic claim.
"""
import json
from pathlib import Path

import pytest

from breakout_research.selection import (
    ECONOMIC_GATES,
    GATE_ORDER,
    SAMPLE_GATES,
    HoldoutRecordError,
    aggregate_records,
    evaluate_candidate,
    rank_key,
    select_candidates,
)

SPEC = {
    "selection": {
        "max_candidates_per_asset": 1,
        "min_trades_total": 30,
        "min_trades_per_fold": 5,
        "min_folds_with_min_trades": 3,
        "positive_folds_required": 3,
        "ranking_metric": "median_net_daily_sharpe",
        "tiebreakers": ["median_net_return", "max_drawdown", "turnover", "config_id"],
    }
}

BASELINE = {"status": "OK", "reason": None, "median_daily_sharpe": 0.5}


def _unit(asset="ADAUSDT", config_id="cfg_0001", fold=0, cost=1.0, trades=10,
          net_return=0.1, sharpe=1.0, drawdown=0.2, turnover=5.0, holdout=False):
    return {
        "asset": asset,
        "config_id": config_id,
        "fold_index": fold,
        "cost_multiplier": cost,
        "status": "COMPLETED",
        "trade_count": trades,
        "net_total_return": net_return,
        "daily_sharpe": sharpe,
        "max_drawdown": drawdown,
        "turnover": turnover,
        "is_holdout": holdout,
    }


def _fold_units(**overrides):
    """Four validation folds at 1x and 2x costs that pass every gate."""
    units = []
    for fold in range(4):
        units.append(_unit(fold=fold, cost=1.0, **overrides))
        units.append(_unit(fold=fold, cost=2.0, **overrides))
    return units


# --- sample-size gates -------------------------------------------------

def test_min_trades_total_gate_uses_baseline_costs_only():
    units = _fold_units(trades=8)  # 8 per fold -> 32 at 1x, 64 if 2x were summed
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["min_trades_total"]["value"] == 32
    assert evaluation["gates"]["min_trades_total"]["pass"] is True


def test_min_trades_total_gate_fails_below_the_floor():
    units = _fold_units(trades=7)  # 28 < 30
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["min_trades_total"]["value"] == 28
    assert evaluation["gates"]["min_trades_total"]["pass"] is False
    assert evaluation["all_pass"] is False


def test_per_fold_trade_floor_is_required_in_three_of_four_folds():
    units = []
    for fold in range(4):
        trades = 5 if fold < 3 else 4
        units.append(_unit(fold=fold, cost=1.0, trades=trades))
        units.append(_unit(fold=fold, cost=2.0, trades=trades))
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["min_folds_with_min_trades"]["value"] == 3
    assert evaluation["gates"]["min_trades_per_fold"]["pass"] is True


def test_per_fold_trade_floor_fails_when_only_two_folds_reach_it():
    units = []
    for fold in range(4):
        trades = 5 if fold < 2 else 4
        units.append(_unit(fold=fold, cost=1.0, trades=trades))
        units.append(_unit(fold=fold, cost=2.0, trades=trades))
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["min_folds_with_min_trades"]["value"] == 2
    assert evaluation["gates"]["min_trades_per_fold"]["pass"] is False
    assert evaluation["gates"]["min_folds_with_min_trades"]["pass"] is False


# --- return gates ------------------------------------------------------

def test_positive_net_return_baseline_gate():
    units = _fold_units(net_return=0.01)
    assert evaluate_candidate(units, SPEC, BASELINE)["gates"]["positive_net_return_baseline"]["pass"] is True
    units = _fold_units(net_return=-0.01)
    assert evaluate_candidate(units, SPEC, BASELINE)["gates"]["positive_net_return_baseline"]["pass"] is False


def test_positive_net_return_2x_costs_gate():
    units = []
    for fold in range(4):
        units.append(_unit(fold=fold, cost=1.0, net_return=0.10))
        units.append(_unit(fold=fold, cost=2.0, net_return=-0.02))
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["positive_net_return_2x_costs"]["value"] == pytest.approx(-0.02)
    assert evaluation["gates"]["positive_net_return_2x_costs"]["pass"] is False


def test_positive_folds_required_gate():
    units = []
    for fold in range(4):
        net = 0.05 if fold < 3 else -0.05
        units.append(_unit(fold=fold, cost=1.0, net_return=net))
        units.append(_unit(fold=fold, cost=2.0, net_return=net))
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    assert evaluation["gates"]["positive_folds_required"]["value"] == 3
    assert evaluation["gates"]["positive_folds_required"]["pass"] is True


# --- Sharpe gates ------------------------------------------------------

def test_median_sharpe_gt_zero_gate():
    units = _fold_units(sharpe=0.2)
    assert evaluate_candidate(units, SPEC, BASELINE)["gates"]["median_sharpe_gt_zero"]["pass"] is True
    units = _fold_units(sharpe=-0.2)
    assert evaluate_candidate(units, SPEC, BASELINE)["gates"]["median_sharpe_gt_zero"]["pass"] is False


def test_median_sharpe_gt_buyhold_gate_uses_the_baseline_median():
    units = _fold_units(sharpe=0.8)
    evaluation = evaluate_candidate(units, SPEC, {"status": "OK", "median_daily_sharpe": 0.5})
    gate = evaluation["gates"]["median_sharpe_gt_buyhold"]
    assert gate["pass"] is True
    assert gate["buyhold_median_sharpe"] == 0.5
    assert gate["value"] == pytest.approx(0.3)


def test_median_sharpe_gt_buyhold_gate_fails_below_the_baseline():
    units = _fold_units(sharpe=0.2)
    evaluation = evaluate_candidate(units, SPEC, {"status": "OK", "median_daily_sharpe": 0.5})
    assert evaluation["gates"]["median_sharpe_gt_buyhold"]["pass"] is False


def test_buyhold_gate_is_not_evaluable_without_a_baseline():
    units = _fold_units()
    evaluation = evaluate_candidate(units, SPEC, None)
    gate = evaluation["gates"]["median_sharpe_gt_buyhold"]
    assert gate["status"] == "NOT_EVALUABLE"
    assert gate["pass"] is None
    assert evaluation["all_pass"] is False
    assert evaluation["passes_evaluable_gates"] is True


def test_two_x_gate_is_not_evaluable_without_two_x_records():
    units = [_unit(fold=fold, cost=1.0) for fold in range(4)]
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    gate = evaluation["gates"]["positive_net_return_2x_costs"]
    assert gate["status"] == "NOT_EVALUABLE"
    assert gate["missing"] == "no 2x-cost validation records for this configuration"
    assert evaluation["all_pass"] is False


def test_gates_are_not_evaluable_without_baseline_records():
    units = [_unit(fold=fold, cost=2.0) for fold in range(4)]
    evaluation = evaluate_candidate(units, SPEC, BASELINE)
    for name in ("min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
                 "positive_net_return_baseline", "positive_folds_required", "median_sharpe_gt_zero",
                 "median_sharpe_gt_buyhold"):
        assert evaluation["gates"][name]["status"] == "NOT_EVALUABLE"
    assert set(evaluation["not_evaluable_gates"]) == {
        "min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
        "positive_net_return_baseline", "positive_folds_required", "median_sharpe_gt_zero",
        "median_sharpe_gt_buyhold"}


# --- ranking and tiebreakers -------------------------------------------

def test_ranking_prefers_the_higher_median_sharpe():
    low = evaluate_candidate(_fold_units(config_id="cfg_0001", sharpe=0.9), SPEC, BASELINE)
    high = evaluate_candidate(_fold_units(config_id="cfg_0002", sharpe=1.1), SPEC, BASELINE)
    assert rank_key(high, "cfg_0002") < rank_key(low, "cfg_0001")


def test_ranking_tiebreakers_are_applied_in_the_preregistered_order():
    same = dict(sharpe=1.0, net_return=0.1, drawdown=0.2, turnover=5.0)
    better_return = evaluate_candidate(_fold_units(config_id="cfg_0002", **{**same, "net_return": 0.2}), SPEC, BASELINE)
    base = evaluate_candidate(_fold_units(config_id="cfg_0001", **same), SPEC, BASELINE)
    assert rank_key(better_return, "cfg_0002") < rank_key(base, "cfg_0001")

    better_drawdown = evaluate_candidate(_fold_units(config_id="cfg_0002", **{**same, "drawdown": 0.1}), SPEC, BASELINE)
    assert rank_key(better_drawdown, "cfg_0002") < rank_key(base, "cfg_0001")

    better_turnover = evaluate_candidate(_fold_units(config_id="cfg_0002", **{**same, "turnover": 1.0}), SPEC, BASELINE)
    assert rank_key(better_turnover, "cfg_0002") < rank_key(base, "cfg_0001")

    assert rank_key(base, "cfg_0001") < rank_key(base, "cfg_0002")


# --- status taxonomy and holdout discipline ----------------------------

def test_status_is_insufficient_evidence_when_only_the_sample_floor_fails():
    units = _fold_units(trades=5)  # 20 trades < 30, every economic gate passes
    selection = select_candidates(units, SPEC, {"ADAUSDT": BASELINE})
    assert selection["ADAUSDT"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert selection["ADAUSDT"]["config_id"] is None
    assert selection["ADAUSDT"]["economic_status"] == "INSUFFICIENT_EVIDENCE"


def test_status_is_no_candidate_when_the_economic_screen_fails():
    units = _fold_units(net_return=-0.1)
    selection = select_candidates(units, SPEC, {"ADAUSDT": BASELINE})
    assert selection["ADAUSDT"]["status"] == "NO_CANDIDATE"
    assert selection["ADAUSDT"]["config_id"] is None


def test_selected_candidate_is_pending_holdout():
    selection = select_candidates(_fold_units(), SPEC, {"ADAUSDT": BASELINE})
    assert selection["ADAUSDT"]["status"] == "CANDIDATE_SELECTED"
    assert selection["ADAUSDT"]["economic_status"] == "CANDIDATE_PENDING_HOLDOUT"
    assert selection["ADAUSDT"]["config_id"] == "cfg_0001"


def test_at_most_one_candidate_per_asset():
    units = _fold_units(config_id="cfg_0001", sharpe=1.0) + _fold_units(config_id="cfg_0002", sharpe=2.0)
    selection = select_candidates(units, SPEC, {"ADAUSDT": BASELINE})
    assert selection["ADAUSDT"]["config_id"] == "cfg_0002"
    assert len(selection) == 1


def test_holdout_record_is_refused_not_filtered():
    units = _fold_units() + [_unit(fold=4, cost=1.0, holdout=True)]
    with pytest.raises(HoldoutRecordError):
        select_candidates(units, SPEC, {"ADAUSDT": BASELINE})


def test_holdout_record_is_refused_during_gate_evaluation():
    units = _fold_units() + [_unit(fold=4, cost=1.0, holdout=True)]
    with pytest.raises(HoldoutRecordError):
        evaluate_candidate(units, SPEC, BASELINE)


def test_aggregate_records_counts_units_and_refuses_holdout():
    grouped, stats = aggregate_records(_fold_units())
    assert stats["records_read"] == 8
    assert stats["holdout_records_read"] == 0
    assert list(grouped) == ["ADAUSDT"]
    with pytest.raises(HoldoutRecordError):
        aggregate_records([_unit(holdout=True)])


# --- the rule covers every preregistered field --------------------------

def test_every_preregistered_selection_field_is_implemented():
    spec = json.loads(Path("configs/research_v1.json").read_text(encoding="utf-8"))
    selection = spec["selection"]
    boolean_gates = {name for name, value in selection.items() if value is True}
    boolean_gates.discard("neighbor_analysis")
    assert boolean_gates == {
        "positive_net_return_baseline", "positive_net_return_2x_costs",
        "median_sharpe_gt_zero", "median_sharpe_gt_buyhold"}
    assert boolean_gates <= set(GATE_ORDER)
    assert {"min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
            "positive_folds_required"} <= set(GATE_ORDER)
    assert selection["max_candidates_per_asset"] == 1
    assert selection["ranking_metric"] == "median_net_daily_sharpe"
    assert selection["tiebreakers"] == ["median_net_return", "max_drawdown", "turnover", "config_id"]

    evaluation = evaluate_candidate(_fold_units(), spec, BASELINE)
    assert set(evaluation["gates"]) == set(GATE_ORDER)
    assert set(SAMPLE_GATES) | set(ECONOMIC_GATES) == set(GATE_ORDER)


def test_rule_rejects_an_unknown_or_missing_threshold():
    broken = {"selection": dict(SPEC["selection"])}
    del broken["selection"]["min_trades_total"]
    with pytest.raises(KeyError):
        evaluate_candidate(_fold_units(), broken, BASELINE)

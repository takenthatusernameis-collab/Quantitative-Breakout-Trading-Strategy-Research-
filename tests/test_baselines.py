"""Unit tests for the buy-and-hold baseline module (BRAIN-006).

Every fixture is a synthetic software fixture.  No fixture is market history
and no test in this file makes an economic claim.
"""
import json
from pathlib import Path

import pytest

from breakout_research.backtest.backtester import _apply_costs, _compute_daily_returns
from breakout_research.baselines import (
    BaselineDataError,
    annualized_sharpe,
    artifact_hash,
    baseline_for_asset,
    buyhold_baseline,
    buyhold_fold_metrics,
    daily_returns_from_equity,
    data_manifest_content_hash,
    load_verified_candles,
    max_drawdown_from_equity,
    verify_baseline_artifact,
)
from breakout_research.config import Candle, CostScenario

HOUR_MS = 3600 * 1000
START = 1700000000000


def _candles(prices, start=START, step=HOUR_MS):
    out = []
    for index, price in enumerate(prices):
        timestamp = start + index * step
        out.append(Candle(timestamp=timestamp, open=price, high=price, low=price,
                          close=price, volume=1.0))
    return out


def test_daily_returns_use_the_backtester_day_alignment():
    timestamps = [START, START + HOUR_MS, START + 25 * HOUR_MS, START + 26 * HOUR_MS]
    equity = [100.0, 110.0, 120.0, 121.0]
    observed = daily_returns_from_equity(equity, timestamps)
    assert observed == _compute_daily_returns(equity, timestamps)
    # three calendar days -> two returns, each from the last equity of a day
    assert observed == pytest.approx([120.0 / 110.0 - 1.0, 121.0 / 120.0 - 1.0])


def test_annualized_sharpe_is_undefined_for_a_constant_series():
    assert annualized_sharpe([0.01, 0.01, 0.01]) is None
    assert annualized_sharpe([0.01]) is None
    assert annualized_sharpe([]) is None


def test_annualized_sharpe_uses_the_365_day_calendar():
    returns = [0.01, -0.005, 0.02, 0.0]
    expected = (sum(returns) / 4) / (statistics_variance(returns) ** 0.5) * (365.0 ** 0.5)
    assert annualized_sharpe(returns) == pytest.approx(expected)


def statistics_variance(values):
    import statistics
    return statistics.variance(values)


def test_max_drawdown_uses_the_hourly_equity_curve():
    equity = [100.0, 120.0, 90.0, 130.0]
    assert max_drawdown_from_equity(equity, 100.0) == pytest.approx(0.25)


def test_buyhold_fold_metrics_are_not_evaluable_on_a_short_window():
    metrics = buyhold_fold_metrics(_candles([100.0]), START, START + HOUR_MS,
                                   CostScenario.baseline())
    assert metrics["status"] == "NOT_EVALUABLE"
    assert "fewer than two candles" in metrics["reason"]


def test_buyhold_fold_metrics_match_a_hand_calculable_case():
    # 48 hourly bars over two days, constant price -> no daily variation
    candles = _candles([100.0] * 48)
    scenario = CostScenario.baseline()
    metrics = buyhold_fold_metrics(candles, START, START + 48 * HOUR_MS, scenario)
    assert metrics["status"] == "OK"
    assert metrics["bars"] == 48
    assert metrics["daily_sharpe"] is None  # constant equity -> undefined Sharpe
    # a flat price still loses the entry slippage and the round-trip fees
    slippage = scenario.slippage_bps / 10000.0
    fee_rate = scenario.taker_fee_bps / 10000.0
    expected_mark_to_market = 1.0 / ((1.0 + slippage) * (1.0 + fee_rate)) - 1.0
    assert metrics["net_total_return"] == pytest.approx(expected_mark_to_market)
    assert metrics["net_total_return_after_exit_costs"] < metrics["net_total_return"]
    assert metrics["fee_drag"] > 0
    assert metrics["slippage_drag"] > 0


def test_buyhold_fold_metrics_apply_the_backtester_costs():
    candles = _candles([100.0, 100.0, 100.0])
    scenario = CostScenario.baseline()
    metrics = buyhold_fold_metrics(candles, START, START + 3 * HOUR_MS, scenario)
    slippage = scenario.slippage_bps / 10000.0
    fee_rate = scenario.taker_fee_bps / 10000.0
    effective_entry = 100.0 * (1.0 + slippage)
    quantity = 10000.0 / (effective_entry * (1.0 + fee_rate))
    entry_fee = (effective_entry * quantity) * fee_rate
    effective_exit = 100.0 * (1.0 - slippage)
    exit_fee = (effective_exit * quantity) * fee_rate
    assert metrics["fee_drag"] == pytest.approx((entry_fee + exit_fee) / 10000.0)
    assert metrics["slippage_drag"] == pytest.approx(
        (effective_entry - 100.0) * quantity / 10000.0 + (100.0 - effective_exit) * quantity / 10000.0)
    # the position is funded by the capital itself: no leverage, no cash drag
    assert metrics["net_total_return"] == pytest.approx((quantity * 100.0 - 10000.0) / 10000.0)


def test_buyhold_baseline_reports_one_entry_per_fold_and_cost_scenario():
    candles = _candles([100.0 + index for index in range(96)], step=HOUR_MS)
    windows = {0: (START, START + 48 * HOUR_MS), 1: (START + 48 * HOUR_MS, START + 96 * HOUR_MS)}
    scenarios = [CostScenario.baseline().scaled(multiplier) for multiplier in (1.0, 2.0, 3.0)]
    baseline = buyhold_baseline(candles, windows, scenarios)
    assert baseline["status"] == "OK"
    assert set(baseline["per_cost"]) == {"1.0", "2.0", "3.0"}
    for cost in baseline["per_cost"].values():
        assert set(cost["folds"]) == {"0", "1"}
        assert cost["sharpe_folds_used"] == 2
    assert baseline["variant_median_sharpe"]["baseline_costs_folds"] is not None


def test_baseline_is_deterministic():
    candles = _candles([100.0 + index for index in range(96)], step=HOUR_MS)
    windows = {0: (START, START + 48 * HOUR_MS), 1: (START + 48 * HOUR_MS, START + 96 * HOUR_MS)}
    scenarios = [CostScenario.baseline().scaled(multiplier) for multiplier in (1.0, 2.0, 3.0)]
    first = buyhold_baseline(candles, windows, scenarios)
    second = buyhold_baseline(candles, windows, scenarios)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_load_verified_candles_refuses_a_tampered_dataset(tmp_path):
    data_manifest = {
        "assets": {
            "ADAUSDT": {
                "dataset_path": "research/data/candles/ADAUSDT.csv",
                "content_hash": "0" * 64,
            }
        }
    }
    dataset = tmp_path / "research" / "data" / "candles"
    dataset.mkdir(parents=True)
    (dataset / "ADAUSDT.csv").write_text(
        "timestamp,open,high,low,close,volume\n"
        "1700000000000,100,100,100,100,1\n", encoding="utf-8")
    with pytest.raises(BaselineDataError):
        load_verified_candles("ADAUSDT", data_manifest, tmp_path)


def test_verify_baseline_artifact_fails_closed_on_a_data_hash_mismatch():
    artifact = {"data_manifest_hash": "a" * 64, "baseline_hash": "b" * 64}
    with pytest.raises(BaselineDataError):
        verify_baseline_artifact(artifact, {"assets": {}})
    data_manifest = {"assets": {"X": {}}}
    artifact = {"data_manifest_hash": data_manifest_content_hash(data_manifest)}
    artifact["baseline_hash"] = artifact_hash(artifact, exclude=("baseline_hash",))
    verify_baseline_artifact(artifact, data_manifest)
    with pytest.raises(BaselineDataError):
        verify_baseline_artifact(artifact, {"assets": {"X": {}, "Y": {}}})


def test_baseline_for_asset_fails_closed_when_the_baseline_is_missing():
    artifact = {"assets": {"ADAUSDT": {"status": "OK",
                                       "variant_median_sharpe": {"baseline_costs_folds": -0.5}}}}
    view = baseline_for_asset(artifact, "ADAUSDT")
    assert view["status"] == "OK"
    assert view["median_daily_sharpe"] == -0.5
    missing = baseline_for_asset(artifact, "BTCUSDT")
    assert missing["status"] == "NOT_EVALUABLE"
    assert missing["median_daily_sharpe"] is None
    not_evaluable = baseline_for_asset(
        {"assets": {"BTCUSDT": {"status": "NOT_EVALUABLE", "reason": "no candles",
                                "variant_median_sharpe": {}}}}, "BTCUSDT")
    assert not_evaluable["status"] == "NOT_EVALUABLE"


def test_apply_costs_is_the_backtester_implementation():
    effective, fee, slippage = _apply_costs(100.0, 2.0, 10.0, 5.0, True)
    assert effective == pytest.approx(100.0 * 1.0005)
    assert fee == pytest.approx(effective * 2.0 * 0.001)
    assert slippage == pytest.approx((effective - 100.0) * 2.0)


# --- the committed baseline artifact -----------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_ARTIFACT = REPO_ROOT / "research" / "baselines" / (
    "577e87e2dc37b496b4d0c9e1a2eeecc9a777f01698591fc395dddb12f45708cb.json")


def test_committed_baseline_artifact_is_intact_and_covers_every_asset():
    if not BASELINE_ARTIFACT.exists():
        pytest.skip("baseline artifact is not present in this checkout")
    artifact = json.loads(BASELINE_ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["artifact"] == "buyhold_baseline"
    assert artifact["inputs"]["holdout_records_read"] == 0
    assert artifact["inputs"]["records_read"] == 497664
    assert len(artifact["assets"]) == 18
    for entry in artifact["assets"].values():
        assert entry["status"] == "OK"
        assert entry["provenance"]["hash_verified"] is True
    assert artifact["baseline_hash"] == artifact_hash(artifact, exclude=("baseline_hash",))

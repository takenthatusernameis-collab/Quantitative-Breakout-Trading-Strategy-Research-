"""Test fold resets and zero trade."""
import unittest
from breakout_research.config import Candle, StrategyConfig, EntryRule, ConfirmationMode, TrendFilter, ExitType
from breakout_research.backtest.backtester import run_fold_backtest
from breakout_research.config import CostScenario, ExperimentStatus


class TestFolds(unittest.TestCase):
    def test_zero_trade_fold(self):
        # Create random walk with no breakouts
        candles = []
        for i in range(200):
            candles.append(Candle(i*3600000, 100, 100.1, 99.9, 100, 1000))
        cfg = StrategyConfig(
            config_id='cfg_test',
            entry_rule=EntryRule.CLASSIC_HIGH_BREAKOUT,
            entry_lookback=12,
            buffer_atr_multiple=0.5,
            confirmation=ConfirmationMode.ONE_CLOSE,
            trend_filter=TrendFilter.NONE,
            exit=ExitType.CHANNEL_12,
            content_hash='test'
        )
        res = run_fold_backtest(candles, cfg, fold_index=0, asset='BTCUSDT', cost_scenario=CostScenario.baseline())
        self.assertEqual(res.status, ExperimentStatus.ZERO_TRADE_COMPLETED)
        self.assertEqual(res.trade_count, 0)
        self.assertEqual(res.gross_total_return, 0.0)

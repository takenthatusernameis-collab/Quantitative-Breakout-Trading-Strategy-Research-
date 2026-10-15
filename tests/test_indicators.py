"""Test indicators."""
import unittest
from breakout_research.config import Candle
from breakout_research.indicators.indicators import (
    true_range, atr_wilder, ema, rolling_max_excluding_current,
    rolling_min_excluding_current
)


class TestIndicators(unittest.TestCase):
    def test_true_range(self):
        candles = [
            Candle(0, 10, 12, 9, 11, 1000),
            Candle(3600000, 11, 13, 10, 12, 1000)
        ]
        tr1 = true_range(candles, 0)
        self.assertEqual(tr1, 3)
        tr2 = true_range(candles, 1)
        # max(3, abs(13-11)=2, abs(10-11)=1) = 3
        self.assertEqual(tr2, 3)

    def test_atr_wilder(self):
        candles = []
        for i in range(20):
            candles.append(Candle(i*3600000, 10, 11, 9, 10.5, 1000))
        atr = atr_wilder(candles, 14)
        self.assertIsNotNone(atr[13])

    def test_rolling_max_excluding_current(self):
        values = [1, 2, 3, 4, 5]
        res = rolling_max_excluding_current(values, 3)
        # i=3: values[0:3] = [1,2,3] -> max 3
        self.assertEqual(res[3], 3)
        self.assertIsNone(res[0])

    def test_ema(self):
        prices = [1, 2, 3, 4, 5] * 10
        ema_vals = ema(prices, 14)
        self.assertIsNotNone(ema_vals[13])

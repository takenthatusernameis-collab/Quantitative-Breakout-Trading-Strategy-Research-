"""Technical indicators: ATR, EMA, True Range, etc."""
from typing import List, Optional
import numpy as np

from ..config import Candle


def true_range(candles: List[Candle], i: int) -> float:
    """Calculate True Range for candle i."""
    if i == 0:
        return candles[0].high - candles[0].low

    high = candles[i].high
    low = candles[i].low
    prev_close = candles[i-1].close

    tr = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )
    return tr


def atr_wilder(candles: List[Candle], period: int = 14) -> List[Optional[float]]:
    """
    Calculate Wilder-style ATR.
    Returns list aligned with candles: ATR[i] uses data up to and including candle i.
    First period-1 values are None (insufficient data).
    ATR[period-1] = mean of first 'period' True Ranges.
    ATR[i] = (ATR[i-1] * (period-1) + TR[i]) / period for i >= period.
    """
    n = len(candles)
    atr = [None] * n

    if n < period:
        return atr

    # Calculate True Ranges
    tr_values = [true_range(candles, i) for i in range(n)]

    # Initial ATR: mean of first 'period' TRs
    initial_atr = sum(tr_values[:period]) / period
    atr[period - 1] = initial_atr

    # Wilder smoothing
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period - 1) + tr_values[i]) / period

    return atr


def ema(prices: List[float], period: int) -> List[Optional[float]]:
    """
    Calculate Exponential Moving Average.
    Uses standard EMA initialization: first value = first price, then recursive.
    Returns list aligned with prices: EMA[i] uses prices up to and including i.
    First period-1 values are None (insufficient data for reliable EMA).
    """
    n = len(prices)
    ema_values = [None] * n

    if n == 0:
        return ema_values

    multiplier = 2.0 / (period + 1)

    # Initialize with SMA of first 'period' prices
    if n >= period:
        initial_ema = sum(prices[:period]) / period
        ema_values[period - 1] = initial_ema

        for i in range(period, n):
            ema_values[i] = (prices[i] - ema_values[i-1]) * multiplier + ema_values[i-1]
    else:
        # Not enough data for full period, still compute recursive EMA from first price
        ema_values[0] = prices[0]
        for i in range(1, n):
            ema_values[i] = (prices[i] - ema_values[i-1]) * multiplier + ema_values[i-1]

    return ema_values


def rolling_max(values: List[float], window: int) -> List[Optional[float]]:
    """Rolling maximum over window. Returns None for first window-1 values."""
    n = len(values)
    result = [None] * n

    for i in range(window - 1, n):
        result[i] = max(values[i - window + 1:i + 1])

    return result


def rolling_min(values: List[float], window: int) -> List[Optional[float]]:
    """Rolling minimum over window. Returns None for first window-1 values."""
    n = len(values)
    result = [None] * n

    for i in range(window - 1, n):
        result[i] = min(values[i - window + 1:i + 1])

    return result


def rolling_max_excluding_current(values: List[float], window: int) -> List[Optional[float]]:
    """
    Rolling maximum of preceding 'window' values, EXCLUDING current index.
    For index i, computes max(values[i-window:i]) - i.e., window values before i.
    Returns None for first window values (indices 0 to window-1).
    """
    n = len(values)
    result = [None] * n

    for i in range(window, n):
        result[i] = max(values[i - window:i])

    return result


def rolling_min_excluding_current(values: List[float], window: int) -> List[Optional[float]]:
    """
    Rolling minimum of preceding 'window' values, EXCLUDING current index.
    For index i, computes min(values[i-window:i]).
    Returns None for first window values.
    """
    n = len(values)
    result = [None] * n

    for i in range(window, n):
        result[i] = min(values[i - window:i])

    return result


def extract_ohlcv(candles: List[Candle]) -> dict:
    """Extract OHLCV arrays from candles."""
    return {
        'open': [c.open for c in candles],
        'high': [c.high for c in candles],
        'low': [c.low for c in candles],
        'close': [c.close for c in candles],
        'volume': [c.volume for c in candles],
        'timestamp': [c.timestamp for c in candles]
    }
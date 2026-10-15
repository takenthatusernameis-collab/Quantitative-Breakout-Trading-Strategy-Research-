"""Signal generation for breakout strategies - entry signals only."""
from typing import List, Optional
from dataclasses import dataclass

from ..config import StrategyConfig, EntryRule, ConfirmationMode, TrendFilter
from ..indicators.indicators import atr_wilder, ema, rolling_max_excluding_current


@dataclass
class EntrySignal:
    """A signal to enter a position, to be filled at the next bar's open."""
    timestamp: int
    index: int
    threshold: float
    buffer: float
    atr_value: float


def generate_entry_signals(candles: List, config: StrategyConfig,
                           btc_candles: Optional[List] = None) -> List[EntrySignal]:
    """
    Generate entry signals for a strategy configuration.

    A signal based on candle i becomes actionable only after candle i has
    completed. Entry fills at the next candle's open (i+1).

    Args:
        candles: List of Candle objects for the target asset
        config: StrategyConfig with all parameters
        btc_candles: Optional BTC candles for BTC trend filter

    Returns:
        List of EntrySignal objects (each to be filled at next bar's open)
    """
    n = len(candles)
    if n < 2:
        return []

    opens = [c.open for c in candles]
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    timestamps = [c.timestamp for c in candles]

    # ATR (Wilder-style, period 14)
    atr_values = atr_wilder(candles, period=14)

    # EMA for trend filters
    ema_24: Optional[List] = None
    ema_168: Optional[List] = None
    if config.trend_filter in (TrendFilter.ASSET_EMA_24_168, TrendFilter.ASSET_EMA_168):
        ema_24 = ema(closes, 24)
        ema_168 = ema(closes, 168)

    # BTC EMA for BTC trend filter
    btc_ema_168: Optional[List] = None
    if config.trend_filter == TrendFilter.BTC_EMA_168 and btc_candles:
        btc_closes = [c.close for c in btc_candles]
        btc_ema_168 = ema(btc_closes, 168)

    # Breakout reference (excluding current candle): max(highs[i-L:i]) or max(closes[i-L:i])
    if config.entry_rule == EntryRule.CLASSIC_HIGH_BREAKOUT:
        ref_values = rolling_max_excluding_current(highs, config.entry_lookback)
    else:
        ref_values = rolling_max_excluding_current(closes, config.entry_lookback)

    entry_signals: List[EntrySignal] = []

    # State for two-close confirmation
    pending_threshold: Optional[float] = None

    for i in range(n):
        # Need ATR[i-1] and ref_values[i] to compute threshold
        if i < 1 or atr_values[i - 1] is None:
            continue

        ref = ref_values[i]
        if ref is None:
            continue

        # Check trend filter
        filter_pass = True
        if config.trend_filter == TrendFilter.ASSET_EMA_168:
            if ema_168[i] is None or closes[i] <= ema_168[i]:
                filter_pass = False
        elif config.trend_filter == TrendFilter.ASSET_EMA_24_168:
            if ema_24[i] is None or ema_168[i] is None or ema_24[i] <= ema_168[i]:
                filter_pass = False
        elif config.trend_filter == TrendFilter.BTC_EMA_168:
            if btc_ema_168 is None or i >= len(btc_ema_168) or btc_ema_168[i] is None:
                filter_pass = False
            elif closes[i] <= btc_ema_168[i]:
                filter_pass = False

        if not filter_pass:
            continue

        # Calculate breakout threshold
        buffer = config.buffer_atr_multiple * atr_values[i - 1]
        threshold = ref + buffer
        signal_triggered = closes[i] > threshold

        if not signal_triggered:
            if config.confirmation == ConfirmationMode.TWO_CLOSE:
                pending_threshold = None
            continue

        if config.confirmation == ConfirmationMode.ONE_CLOSE:
            entry_signals.append(EntrySignal(
                timestamp=timestamps[i],
                index=i,
                threshold=threshold,
                buffer=buffer,
                atr_value=atr_values[i - 1],
            ))
        else:  # TWO_CLOSE
            if pending_threshold is None:
                # First qualifying close - store threshold and wait
                pending_threshold = threshold
            else:
                # Second consecutive qualifying close above STORED threshold
                entry_signals.append(EntrySignal(
                    timestamp=timestamps[i],
                    index=i,
                    threshold=pending_threshold,
                    buffer=buffer,
                    atr_value=atr_values[i - 1],
                ))
                pending_threshold = None

    return entry_signals

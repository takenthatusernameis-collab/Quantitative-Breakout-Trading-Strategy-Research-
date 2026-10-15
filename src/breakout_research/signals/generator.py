"""Signal generation for breakout strategies."""
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..config import StrategyConfig, EntryRule, ConfirmationMode, TrendFilter, ExitType
from ..indicators.indicators import (
    atr_wilder, ema, rolling_max_excluding_current,
    rolling_min_excluding_current, extract_ohlcv
)


class SignalState(Enum):
    NONE = "none"
    PENDING_CONFIRMATION = "pending_confirmation"
    ACTIVE = "active"


@dataclass
class Signal:
    timestamp: int
    index: int
    price: float
    threshold: float
    buffer: float
    atr_value: float
    state: SignalState
    stored_threshold: Optional[float] = None  # For two-close confirmation


@dataclass
class ExitSignal:
    timestamp: int
    index: int
    price: float
    stop_price: float
    exit_type: str
    reason: str


def generate_breakout_signals(candles: List, config: StrategyConfig,
                               btc_candles: Optional[List] = None) -> Tuple[List[Signal], List[ExitSignal]]:
    """
    Generate entry and exit signals for a strategy configuration.

    Args:
        candles: List of Candle objects for the target asset
        config: StrategyConfig with all parameters
        btc_candles: Optional BTC candles for BTC trend filter

    Returns:
        Tuple of (entry_signals, exit_signals)
    """
    ohlcv = extract_ohlcv(candles)
    opens = ohlcv['open']
    closes = ohlcv['close']
    highs = ohlcv['high']
    lows = ohlcv['low']
    timestamps = ohlcv['timestamp']
    n = len(candles)

    # Calculate indicators
    atr = atr_wilder(candles, period=14)

    # EMA for trend filters
    ema_24 = ema(closes, 24) if config.trend_filter in (TrendFilter.ASSET_EMA_168, TrendFilter.ASSET_EMA_24_168) else None
    ema_168 = ema(closes, 168) if config.trend_filter in (TrendFilter.ASSET_EMA_168, TrendFilter.ASSET_EMA_24_168) else None

    # BTC EMA for BTC trend filter
    btc_ema_168 = None
    if config.trend_filter == TrendFilter.BTC_EMA_168 and btc_candles:
        btc_closes = [c.close for c in btc_candles]
        btc_ema_168 = ema(btc_closes, 168)

    # Breakout reference (excluding current candle)
    if config.entry_rule == EntryRule.CLASSIC_HIGH_BREAKOUT:
        ref_values = rolling_max_excluding_current(highs, config.entry_lookback)
    else:  # CLOSE_BREAKOUT
        ref_values = rolling_max_excluding_current(closes, config.entry_lookback)

    entry_signals = []
    exit_signals = []

    # State for two-close confirmation
    pending_confirmation = None  # Stores (threshold, signal_index) when waiting for 2nd close

    # Track position state for exits
    in_position = False
    entry_index = -1
    entry_price = 0.0
    highest_since_entry = 0.0
    trailing_stop = None
    channel_stop = None

    for i in range(n):
        # Skip if insufficient data for indicators
        if atr[i] is None:
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
            elif closes[i] <= btc_ema_168[i]:  # Aligned by index (same timestamp)
                filter_pass = False

        # Calculate breakout threshold
        if ref_values[i] is not None and atr[i-1] is not None:
            buffer = config.buffer_atr_multiple * atr[i-1]
            threshold = ref_values[i] + buffer
        else:
            threshold = None

        # Generate entry signals
        if not in_position and filter_pass and threshold is not None:
            signal_triggered = closes[i] > threshold

            if signal_triggered:
                if config.confirmation == ConfirmationMode.ONE_CLOSE:
                    # Enter next bar
                    signal = Signal(
                        timestamp=timestamps[i],
                        index=i,
                        price=closes[i],
                        threshold=threshold,
                        buffer=buffer,
                        atr_value=atr[i-1],
                        state=SignalState.ACTIVE
                    )
                    entry_signals.append(signal)

                elif config.confirmation == ConfirmationMode.TWO_CLOSE:
                    if pending_confirmation is None:
                        # First close - store threshold and wait
                        pending_confirmation = {
                            'threshold': threshold,
                            'signal_index': i,
                            'buffer': buffer,
                            'atr_value': atr[i-1]
                        }
                    else:
                        # Check if this close exceeds STORED threshold
                        if closes[i] > pending_confirmation['threshold']:
                            # Confirmed! Enter next bar using stored threshold
                            signal = Signal(
                                timestamp=timestamps[i],
                                index=i,
                                price=closes[i],
                                threshold=pending_confirmation['threshold'],
                                buffer=pending_confirmation['buffer'],
                                atr_value=pending_confirmation['atr_value'],
                                state=SignalState.ACTIVE,
                                stored_threshold=pending_confirmation['threshold']
                            )
                            entry_signals.append(signal)
                            pending_confirmation = None
                        else:
                            # Failed confirmation - check if new signal
                            if closes[i] > threshold:
                                # New first signal
                                pending_confirmation = {
                                    'threshold': threshold,
                                    'signal_index': i,
                                    'buffer': buffer,
                                    'atr_value': atr[i-1]
                                }
                            else:
                                # No signal, clear pending
                                pending_confirmation = None
            else:
                # No signal this bar
                if config.confirmation == ConfirmationMode.TWO_CLOSE and pending_confirmation is not None:
                    # Check if this bar independently qualifies as new first signal
                    if closes[i] > threshold:
                        pending_confirmation = {
                            'threshold': threshold,
                            'signal_index': i,
                            'buffer': buffer,
                            'atr_value': atr[i-1]
                        }
                    else:
                        pending_confirmation = None
        else:
            # In position or filter failed - clear pending confirmation
            pending_confirmation = None

        # Process exits if in position
        if in_position:
            # Update highest since entry
            if highs[i] > highest_since_entry:
                highest_since_entry = highs[i]

            # Check exit conditions based on exit type
            exit_triggered = False
            exit_price = None
            exit_reason = ""

            if config.exit in (ExitType.CHANNEL_12, ExitType.CHANNEL_24, ExitType.CHANNEL_48):
                channel_period = 12 if config.exit == ExitType.CHANNEL_12 else (24 if config.exit == ExitType.CHANNEL_24 else 48)
                if i >= channel_period:
                    channel_low = min(lows[i - channel_period:i])  # Excluding current
                    if closes[i] < channel_low:
                        exit_triggered = True
                        exit_price = opens[i+1] if i+1 < n else closes[i]  # Next open
                        exit_reason = f"channel_{channel_period}"

            elif config.exit in (ExitType.ATR_TRAIL_1_5, ExitType.ATR_TRAIL_2_5, ExitType.ATR_TRAIL_4_0):
                mult = 1.5 if config.exit == ExitType.ATR_TRAIL_1_5 else (2.5 if config.exit == ExitType.ATR_TRAIL_2_5 else 4.0)

                # Stop from PREVIOUS bar becomes active for THIS bar
                if i > entry_index and trailing_stop is not None:
                    # Check gap at open
                    if opens[i] < trailing_stop:
                        exit_triggered = True
                        exit_price = opens[i]  # Fill at open with adverse slippage
                        exit_reason = f"atr_trail_{mult}_gap"
                    # Check intrabar cross
                    elif lows[i] <= trailing_stop:
                        exit_triggered = True
                        exit_price = trailing_stop  # Fill at stop with adverse slippage
                        exit_reason = f"atr_trail_{mult}_cross"

                # Update stop for NEXT bar (only if not triggered)
                if not exit_triggered and atr[i] is not None:
                    new_stop = highest_since_entry - mult * atr[i]
                    if trailing_stop is None or new_stop > trailing_stop:
                        trailing_stop = new_stop

            if exit_triggered:
                exit_signals.append(ExitSignal(
                    timestamp=timestamps[i],
                    index=i,
                    price=exit_price,
                    stop_price=trailing_stop if config.exit.value.startswith('atr_trail') else channel_low,
                    exit_type=config.exit.value,
                    reason=exit_reason
                ))
                in_position = False
                trailing_stop = None
                highest_since_entry = 0.0

        # Check for new entry (fill at next open)
        if entry_signals and entry_signals[-1].index == i and not in_position:
            # This signal will execute at i+1 open
            in_position = True
            entry_index = i
            entry_price = opens[i+1] if i+1 < n else closes[i]
            highest_since_entry = highs[i+1] if i+1 < n else highs[i]

            # Initialize trailing stop for ATR exits
            if config.exit.value.startswith('atr_trail') and atr[i] is not None:
                mult = float(config.exit.value.split('_')[-1])
                trailing_stop = highest_since_entry - mult * atr[i]

            # Initialize channel stop
            if config.exit.value.startswith('channel'):
                channel_period = int(config.exit.value.split('_')[-1])
                if i+1 >= channel_period:
                    channel_stop = min(lows[i+1 - channel_period:i+1])

    return entry_signals, exit_signals
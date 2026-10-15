"""Backtesting engine."""
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timezone
import numpy as np

from ..config import (
    Candle, StrategyConfig, Trade, FoldResult, ExperimentStatus,
    CostScenario, EntryRule
)
from ..indicators.indicators import (
    atr_wilder, ema, rolling_max_excluding_current,
    rolling_min_excluding_current
)
from ..signals.generator import generate_entry_signals


def _apply_costs(price: float, qty: float, taker_fee_bps: float,
                 slippage_bps: float, is_entry: bool) -> Tuple[float, float, float]:
    """
    Calculate fees and slippage for a trade.

    Args:
        price: Raw execution price
        qty: Quantity of base asset
        taker_fee_bps: Fee in basis points (e.g. 10 for 0.10%)
        slippage_bps: Slippage in basis points (e.g. 5 for 0.05%)
        is_entry: True for buy (entry), False for sell (exit)

    Returns:
        (effective_price, fee_amount, slippage_amount) all in quote-currency terms
    """
    slippage = slippage_bps / 10000.0
    fee_rate = taker_fee_bps / 10000.0

    if is_entry:
        # Buy: pay slippage premium, fee on notional
        effective_price = price * (1.0 + slippage)
        notional = effective_price * qty
        fee = notional * fee_rate
        slippage_amount = (effective_price - price) * qty
    else:
        # Sell: receive less due to slippage, fee on proceeds
        effective_price = price * (1.0 - slippage)
        notional = effective_price * qty
        fee = notional * fee_rate
        slippage_amount = (price - effective_price) * qty

    return effective_price, fee, slippage_amount


def _compute_metrics(equity_curve: List[float], timestamps: List[int],
                     trades: List[Trade], initial_capital: float,
                     total_fees: float, total_slippage: float,
                     total_turnover: float) -> Dict[str, Any]:
    """Compute all backtest metrics from equity curve and trade list."""
    n = len(equity_curve)
    if n == 0:
        return {
            'gross_total_return': 0.0,
            'net_total_return': 0.0,
            'annualized_return': 0.0,
            'daily_sharpe': None,
            'max_drawdown': 0.0,
            'exposure': 0.0,
            'win_rate': None,
            'avg_win': None,
            'avg_loss': None,
            'profit_factor': None,
            'fee_drag': 0.0,
            'slippage_drag': 0.0,
            'turnover': 0.0,
        }

    final_equity = equity_curve[-1]
    gross_total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0.0
    net_total_return = gross_total_return  # costs already deducted from equity

    # Annualized return (365-day crypto calendar)
    if n > 1 and timestamps[-1] > timestamps[0]:
        duration_years = (timestamps[-1] - timestamps[0]) / (365.0 * 24 * 3600 * 1000)
        if duration_years > 0:
            annualized_return = (final_equity / initial_capital) ** (1.0 / duration_years) - 1.0
        else:
            annualized_return = 0.0
    else:
        annualized_return = 0.0

    # Daily Sharpe ratio
    daily_returns = _compute_daily_returns(equity_curve, timestamps)
    if len(daily_returns) >= 2:
        mean_ret = np.mean(daily_returns)
        std_ret = np.std(daily_returns, ddof=1)
        if std_ret > 0:
            daily_sharpe = mean_ret / std_ret * np.sqrt(365)
        else:
            daily_sharpe = None
    else:
        daily_sharpe = None

    # Max drawdown (from hourly equity)
    running_max = initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        if eq > running_max:
            running_max = eq
        dd = (running_max - eq) / running_max if running_max > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Exposure (fraction of bars in position)
    exposure = sum(1 for t in trades if t is not None) / n if n > 0 else 0.0

    # Trade stats
    if len(trades) > 0:
        winning = [t.net_pnl for t in trades if t.net_pnl > 0]
        losing = [t.net_pnl for t in trades if t.net_pnl < 0]
        win_rate = len(winning) / len(trades) if trades else 0
        avg_win = sum(winning) / len(winning) if winning else 0
        avg_loss = sum(losing) / len(losing) if losing else 0
        profit_factor = sum(winning) / abs(sum(losing)) if losing and abs(sum(losing)) > 0 else float('inf')
    else:
        win_rate = None
        avg_win = None
        avg_loss = None
        profit_factor = None

    return {
        'gross_total_return': gross_total_return,
        'net_total_return': net_total_return,
        'annualized_return': annualized_return,
        'daily_sharpe': float(daily_sharpe) if daily_sharpe is not None else None,
        'max_drawdown': max_dd,
        'exposure': exposure,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'fee_drag': total_fees / initial_capital if initial_capital > 0 else 0.0,
        'slippage_drag': total_slippage / initial_capital if initial_capital > 0 else 0.0,
        'turnover': total_turnover / initial_capital if initial_capital > 0 else 0.0,
    }


def _compute_daily_returns(equity_curve: List[float], timestamps: List[int]) -> List[float]:
    """Compute daily returns from hourly equity curve, aligned by calendar day."""
    daily_equity: Dict[str, float] = {}
    for ts, eq in zip(timestamps, equity_curve):
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d')
        daily_equity[dt] = eq  # last equity value of the day

    sorted_days = sorted(daily_equity.keys())
    returns = []
    for i in range(1, len(sorted_days)):
        prev = daily_equity[sorted_days[i - 1]]
        curr = daily_equity[sorted_days[i]]
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _get_exit_channel_low(lows: List[float], i: int, channel_period: int) -> Optional[float]:
    """Get the minimum low of the preceding N bars, excluding current bar i."""
    if i < channel_period:
        return None
    return min(lows[i - channel_period:i])


def run_fold_backtest(candles: List[Candle], config: StrategyConfig,
                      btc_candles: Optional[List[Candle]] = None,
                      start_time: Optional[int] = None,
                      end_time: Optional[int] = None,
                      cost_scenario: Optional[CostScenario] = None,
                      initial_capital: float = 10000.0,
                      fold_index: int = 0,
                      asset: str = "") -> FoldResult:
    """
    Run backtest on a fold (time window).

    Entry: signal at bar i, fill at bar i+1 open.
    Exit: channel exit on close < min(low[i-N:i]), fill at i+1 open.
          ATR trail: stop from previous bar active at bar i; gap at open or low cross.
    """
    if cost_scenario is None:
        cost_scenario = CostScenario.baseline()

    # Filter candles to fold window
    fold_candles = candles
    if start_time is not None:
        fold_candles = [c for c in fold_candles if c.timestamp >= start_time]
    if end_time is not None:
        fold_candles = [c for c in fold_candles if c.timestamp < end_time]

    if len(fold_candles) == 0:
        return FoldResult(
            fold_index=fold_index,
            start_time=start_time or 0,
            end_time=end_time or 0,
            config_id=config.config_id,
            asset=asset,
            cost_multiplier=cost_scenario.multiplier,
            status=ExperimentStatus.INVALID_DATA,
            reason="No candles in fold window",
            trade_count=0,
            gross_total_return=0.0,
            net_total_return=0.0,
            annualized_return=0.0,
            daily_sharpe=None,
            max_drawdown=0.0,
            exposure=0.0,
            turnover=0.0,
            win_rate=None,
            avg_win=None,
            avg_loss=None,
            profit_factor=None,
            fee_drag=0.0,
            slippage_drag=0.0,
            trades=[],
            equity_curve=[],
            timestamps=[]
        )

    n = len(fold_candles)
    opens = [c.open for c in fold_candles]
    highs = [c.high for c in fold_candles]
    lows = [c.low for c in fold_candles]
    closes = [c.close for c in fold_candles]
    timestamps = [c.timestamp for c in fold_candles]

    # Compute indicators needed for signals and exits
    atr_values = atr_wilder(fold_candles, period=14)

    # EMA for trend filters
    ema_24 = ema(closes, 24) if config.trend_filter.value in ('asset_ema_168', 'asset_ema_24_168') else None
    ema_168 = ema(closes, 168) if config.trend_filter.value in ('asset_ema_168', 'asset_ema_24_168') else None

    # BTC EMA for BTC trend filter
    btc_ema_168 = None
    if config.trend_filter.value == 'btc_ema_168' and btc_candles:
        btc_closes = [c.close for c in btc_candles]
        btc_ema_168 = ema(btc_closes, 168)

    # Breakout references
    if config.entry_rule == EntryRule.CLASSIC_HIGH_BREAKOUT:
        ref_values = rolling_max_excluding_current(highs, config.entry_lookback)
    else:
        ref_values = rolling_max_excluding_current(closes, config.entry_lookback)

    # Generate entry signals
    entry_signals = generate_entry_signals(fold_candles, config, btc_candles)

    # Build entry signal index map for O(1) lookup
    entry_by_index = {sig.index: sig for sig in entry_signals}

    # Backtest simulation
    cash = initial_capital
    position_qty = 0.0
    position_entry_price = 0.0
    position_entry_time = 0
    entry_fee_paid = 0.0
    entry_slippage_paid = 0.0
    in_position = False
    trades: List[Trade] = []
    equity_curve: List[float] = []
    eq_timestamps: List[int] = []

    total_fees = 0.0
    total_slippage = 0.0
    total_turnover = 0.0

    # ATR trail state
    trailing_stop: Optional[float] = None
    highest_high_since_entry = 0.0
    trail_mult = None
    if config.exit.value.startswith('atr_trail'):
        trail_mult = float(config.exit.value.split('_')[-1])

    # Channel exit period
    channel_period = None
    if config.exit.value.startswith('channel'):
        channel_period = int(config.exit.value.split('_')[-1])

    # State for two-close confirmation (if used)
    pending_confirmation = None if config.confirmation.value == 'one_close' else None

    for i in range(n):
        candle = fold_candles[i]

        # ---- Check for exit if in position ----
        if in_position and position_qty > 0:
            exit_triggered = False
            exit_price = None
            exit_reason = ""

            # ATR trailing exit
            if config.exit.value.startswith('atr_trail'):
                # Stop from previous bar is active at this bar
                if trailing_stop is not None:
                    # Gap down at open
                    if opens[i] < trailing_stop:
                        exit_triggered = True
                        exit_price = opens[i]
                        exit_reason = f"atr_trail_{trail_mult}_gap"
                    # Low crosses stop
                    elif lows[i] <= trailing_stop:
                        exit_triggered = True
                        exit_price = trailing_stop
                        exit_reason = f"atr_trail_{trail_mult}_cross"

                    # Update trailing stop (only if not triggered)
                    if not exit_triggered:
                        if highs[i] > highest_high_since_entry:
                            highest_high_since_entry = highs[i]
                        if atr_values[i] is not None:
                            new_stop = highest_high_since_entry - trail_mult * atr_values[i]
                            if trailing_stop is None or new_stop > trailing_stop:
                                trailing_stop = new_stop

            # Channel exit
            if not exit_triggered and channel_period is not None:
                channel_low = _get_exit_channel_low(lows, i, channel_period)
                if channel_low is not None and closes[i] < channel_low:
                    exit_triggered = True
                    # Fill at next bar's open
                    if i + 1 < n:
                        exit_price = opens[i + 1]
                    else:
                        exit_price = closes[i]
                    exit_reason = f"channel_{channel_period}"

            if exit_triggered and exit_price is not None:
                # Execute exit
                eff_price, fee, slip = _apply_costs(
                    exit_price, position_qty,
                    cost_scenario.taker_fee_bps,
                    cost_scenario.slippage_bps,
                    is_entry=False
                )
                proceeds = position_qty * eff_price - fee
                gross_pnl = (exit_price - position_entry_price) * position_qty
                net_pnl = proceeds - position_entry_price * position_qty - entry_fee_paid - entry_slippage_paid

                # Compute MFE/MAE
                mfe = max(highs[i] - position_entry_price, 0.0) * position_qty
                mae = max(position_entry_price - lows[i], 0.0) * position_qty

                trade = Trade(
                    entry_time=position_entry_time,
                    entry_price=position_entry_price,
                    exit_time=timestamps[i if exit_reason.startswith('atr') else i + 1] if exit_reason.startswith('atr') or i + 1 < n else timestamps[i],
                    exit_price=eff_price,
                    quantity=position_qty,
                    entry_fee=entry_fee_paid,
                    exit_fee=fee,
                    entry_slippage=entry_slippage_paid,
                    exit_slippage=slip,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    exit_reason=exit_reason,
                    max_favorable_excursion=mfe,
                    max_adverse_excursion=mae
                )
                trades.append(trade)
                total_fees += fee + entry_fee_paid
                total_slippage += slip + entry_slippage_paid
                total_turnover += position_qty * exit_price

                cash = proceeds
                position_qty = 0
                in_position = False
                trailing_stop = None
                highest_high_since_entry = 0.0

        # ---- Check for entry if not in position ----
        if not in_position and i in entry_by_index:
            sig = entry_by_index[i]

            # For two-close confirmation, re-check the stored threshold logic
            # Entry signal already handles stored_threshold; the signal generator
            # ensures the second close exceeds the stored threshold.
            # But we need to verify the entry bar is not the signal bar itself.
            # Entry fills at next bar's open (i+1)

            if i + 1 < n:
                entry_price = opens[i + 1]
                entry_time = timestamps[i + 1]
            else:
                # Can't fill - no next bar
                # Remove from entry_by_index to avoid reprocessing
                entry_by_index.pop(i, None)
                # Still record equity for this bar
                current_equity = cash
                equity_curve.append(current_equity)
                eq_timestamps.append(candle.timestamp)

                # Update equity tracking
                running_max = equity_curve[0] if equity_curve else initial_capital
                break

            # Calculate quantity from available cash
            qty = cash / entry_price if entry_price > 0 else 0
            if qty <= 0:
                continue

            eff_price, fee, slip = _apply_costs(
                entry_price, qty,
                cost_scenario.taker_fee_bps,
                cost_scenario.slippage_bps,
                is_entry=True
            )
            cost_total = eff_price * qty
            if cost_total > cash:
                # Adjust quantity to avoid negative cash
                qty = cash / eff_price if eff_price > 0 else 0
                cost_total = eff_price * qty

            cash -= cost_total
            position_qty = qty
            position_entry_price = eff_price
            position_entry_time = entry_time
            entry_fee_paid = fee
            entry_slippage_paid = slip
            total_fees += fee
            total_slippage += slip
            total_turnover += qty * entry_price
            in_position = True

            # Initialize trailing stop at entry bar
            if trail_mult is not None and atr_values[i] is not None:
                # Use ATR known at signal close (i.e., ATR[i])
                # Highest high since entry starts from entry bar
                highest_high_since_entry = max(highs[i], highs[i + 1] if i + 1 < n else highs[i])
                trailing_stop = highest_high_since_entry - trail_mult * atr_values[i]
            elif trail_mult is not None and i > 0 and atr_values[i - 1] is not None:
                # Fallback: use previous bar ATR
                highest_high_since_entry = max(highs[i], highs[i + 1] if i + 1 < n else highs[i])
                trailing_stop = highest_high_since_entry - trail_mult * atr_values[i - 1]

            # Skip the rest of this bar's processing since we just entered
            # Still record equity
            current_equity = cash + (position_qty * closes[i] if in_position else 0)
            equity_curve.append(current_equity)
            eq_timestamps.append(candle.timestamp)
            continue

        # ---- Update equity for this bar ----
        if in_position and position_qty > 0:
            current_equity = cash + position_qty * closes[i]
        else:
            current_equity = cash
        equity_curve.append(current_equity)
        eq_timestamps.append(candle.timestamp)

    # Close any open position at end of fold (using boundary-fill convention)
    if in_position and position_qty > 0:
        last_candle = fold_candles[-1]
        exit_price = last_candle.close
        eff_price, fee, slip = _apply_costs(
            exit_price, position_qty,
            cost_scenario.taker_fee_bps,
            cost_scenario.slippage_bps,
            is_entry=False
        )
        proceeds = position_qty * eff_price - fee
        gross_pnl = (exit_price - position_entry_price) * position_qty
        net_pnl = proceeds - position_entry_price * position_qty - entry_fee_paid - entry_slippage_paid

        mfe = max(max(h - position_entry_price for h in highs), 0.0) * position_qty
        mae = max(max(position_entry_price - l for l in lows), 0.0) * position_qty

        trade = Trade(
            entry_time=position_entry_time,
            entry_price=position_entry_price,
            exit_time=timestamps[-1],
            exit_price=eff_price,
            quantity=position_qty,
            entry_fee=entry_fee_paid,
            exit_fee=fee,
            entry_slippage=entry_slippage_paid,
            exit_slippage=slip,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            exit_reason="end_of_fold",
            max_favorable_excursion=mfe,
            max_adverse_excursion=mae
        )
        trades.append(trade)
        total_fees += fee + entry_fee_paid
        total_slippage += slip + entry_slippage_paid
        total_turnover += position_qty * exit_price
        cash = proceeds

    # Compute metrics
    metrics = _compute_metrics(equity_curve, eq_timestamps, trades, initial_capital,
                               total_fees, total_slippage, total_turnover)

    status = ExperimentStatus.ZERO_TRADE_COMPLETED if len(trades) == 0 else ExperimentStatus.COMPLETED
    start_ts = fold_candles[0].timestamp
    end_ts = fold_candles[-1].timestamp

    return FoldResult(
        fold_index=fold_index,
        start_time=start_ts,
        end_time=end_ts,
        config_id=config.config_id,
        asset=asset,
        cost_multiplier=cost_scenario.multiplier,
        status=status,
        reason=None,
        trade_count=len(trades),
        gross_total_return=metrics['gross_total_return'],
        net_total_return=metrics['net_total_return'],
        annualized_return=metrics['annualized_return'],
        daily_sharpe=metrics['daily_sharpe'],
        max_drawdown=metrics['max_drawdown'],
        exposure=metrics['exposure'],
        turnover=metrics['turnover'],
        win_rate=metrics['win_rate'],
        avg_win=metrics['avg_win'],
        avg_loss=metrics['avg_loss'],
        profit_factor=metrics['profit_factor'],
        fee_drag=metrics['fee_drag'],
        slippage_drag=metrics['slippage_drag'],
        trades=trades,
        equity_curve=equity_curve,
        timestamps=eq_timestamps
    )

"""Backtesting engine."""
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from ..config import (
    Candle, StrategyConfig, Trade, FoldResult, ExperimentStatus,
    CostScenario, EntryRule
)
from ..signals.generator import generate_breakout_signals


def apply_costs(price: float, notional: float, taker_fee_bps: float,
                slippage_bps: float, is_entry: bool = True) -> Tuple[float, float, float]:
    """
    Calculate fees and slippage for a trade.
    Returns (effective_price, fee, slippage_cost_in_notional)
    """
    slippage = slippage_bps / 10000.0
    fee_rate = taker_fee_bps / 10000.0

    if is_entry:
        # Buy: pay slippage + fee on notional
        effective_price = price * (1 + slippage)
        fee = effective_price * notional * fee_rate
        slippage_cost = effective_price * notional - price * notional
    else:
        # Sell: receive less from slippage, pay fee on proceeds
        effective_price = price * (1 - slippage)
        fee = effective_price * notional * fee_rate
        slippage_cost = price * notional - effective_price * notional

    return effective_price, fee, slippage_cost


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

    # Generate signals
    entry_signals, exit_signals = generate_breakout_signals(
        fold_candles, config, btc_candles
    )

    # Backtest simulation
    cash = initial_capital
    position_qty = 0.0
    position_entry_price = 0.0
    position_entry_time = 0
    position_in_trade = False
    trades = []
    equity_curve = []
    timestamps = []
    total_fees = 0.0
    total_slippage = 0.0

    highest_equity = initial_capital
    max_dd = 0.0

    for i in range(len(fold_candles)):
        candle = fold_candles[i]

        # Check for exit (if in position)
        if position_in_trade:
            # Check if any exit signal occurs at this index
            for ex in exit_signals:
                if ex.index == i:
                    # Execute exit
                    if position_qty > 0:
                        notional = position_qty * ex.price
                        eff_price, fee, slip = apply_costs(
                            ex.price, position_qty,
                            cost_scenario.taker_fee_bps,
                            cost_scenario.slippage_bps,
                            is_entry=False
                        )
                        proceeds = position_qty * eff_price - fee
                        gross_pnl = (ex.price - position_entry_price) * position_qty
                        net_pnl = proceeds - (position_entry_price * position_qty +
                                             position_entry_price * position_qty * cost_scenario.taker_fee_bps / 10000.0)
                        # Simpler: compute properly
                        entry_notional = position_entry_price * position_qty
                        exit_notional_gross = ex.price * position_qty
                        exit_notional_net = eff_price * position_qty - fee
                        net_pnl_calc = exit_notional_net - entry_notional - (entry_notional * cost_scenario.taker_fee_bps / 10000.0)
                        net_pnl = net_pnl_calc

                        gross_pnl_calc = exit_notional_gross - entry_notional
                        gross_pnl = gross_pnl_calc

                        trade = Trade(
                            entry_time=position_entry_time,
                            entry_price=position_entry_price,
                            exit_time=candle.timestamp,
                            exit_price=eff_price,
                            quantity=position_qty,
                            entry_fee=entry_notional * cost_scenario.taker_fee_bps / 10000.0,
                            exit_fee=fee,
                            entry_slippage=entry_notional * cost_scenario.slippage_bps / 10000.0 if False else 0,
                            exit_slippage=slip,
                            gross_pnl=gross_pnl,
                            net_pnl=net_pnl,
                            exit_reason=ex.reason,
                            max_favorable_excursion=0.0,
                            max_adverse_excursion=0.0
                        )
                        trades.append(trade)
                        total_fees += trade.entry_fee + trade.exit_fee
                        total_slippage += slip
                        cash += exit_notional_net  # exit proceeds
                        position_in_trade = False
                        position_qty = 0
                    break

        # Check for entry (fill at next open - signals created on close, fill at next bar's open)
        # In our simulation, signal at index i means entry at open of i+1; but we have folded data
        # For simplicity in this context, treat signal as executing at next candle's open
        if not position_in_trade:
            for sig in entry_signals:
                if sig.index == i:
                    # Execute entry at next candle open if exists
                    if i + 1 < len(fold_candles):
                        entry_candle = fold_candles[i + 1]
                        entry_price = entry_candle.open
                    else:
                        entry_price = candle.close

                    # Calculate qty
                    notional = cash
                    if notional <= 0:
                        continue
                    eff_price, fee, slip = apply_costs(
                        entry_price, notional / entry_price if entry_price > 0 else 0,
                        cost_scenario.taker_fee_bps,
                        cost_scenario.slippage_bps,
                        is_entry=True
                    )
                    qty = (notional - fee) / eff_price if eff_price > 0 else 0
                    if qty <= 0:
                        continue
                    position_qty = qty
                    position_entry_price = eff_price
                    position_entry_time = entry_candle.timestamp if 'entry_candle' in locals() else candle.timestamp
                    cash = 0
                    position_in_trade = True
                    total_fees += fee
                    total_slippage += slip
                    break

        # Update equity
        if position_in_trade and position_qty > 0:
            current_equity = cash + position_qty * candle.close
        else:
            current_equity = cash
        equity_curve.append(current_equity)
        timestamps.append(candle.timestamp)

        if current_equity > highest_equity:
            highest_equity = current_equity
        dd = (highest_equity - current_equity) / highest_equity if highest_equity > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Close any open position at end
    if position_in_trade and position_qty > 0:
        last_candle = fold_candles[-1]
        ex_price = last_candle.close
        notional = position_qty * ex_price
        eff_price, fee, slip = apply_costs(
            ex_price, position_qty,
            cost_scenario.taker_fee_bps,
            cost_scenario.slippage_bps,
            is_entry=False
        )
        exit_notional_net = position_qty * eff_price - fee
        entry_notional = position_entry_price * position_qty
        net_pnl = exit_notional_net - entry_notional
        gross_pnl = (ex_price - position_entry_price) * position_qty
        trade = Trade(
            entry_time=position_entry_time,
            entry_price=position_entry_price,
            exit_time=last_candle.timestamp,
            exit_price=eff_price,
            quantity=position_qty,
            entry_fee=entry_notional * cost_scenario.taker_fee_bps / 10000.0,
            exit_fee=fee,
            entry_slippage=0,
            exit_slippage=slip,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            exit_reason="end_of_fold",
            max_favorable_excursion=0,
            max_adverse_excursion=0
        )
        trades.append(trade)
        cash = exit_notional_net

    final_equity = cash if cash > 0 else (position_qty * fold_candles[-1].close if position_in_trade else initial_capital)
    gross_total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0
    net_total_return = gross_total_return  # net already accounted

    # Compute stats
    if len(trades) > 0:
        winning = [t.net_pnl for t in trades if t.net_pnl > 0]
        losing = [t.net_pnl for t in trades if t.net_pnl < 0]
        win_rate = len(winning) / len(trades) if trades else 0
        avg_win = sum(winning) / len(winning) if winning else 0
        avg_loss = sum(losing) / len(losing) if losing else 0
        profit_factor = sum(winning) / abs(sum(losing)) if losing else float('inf')
    else:
        win_rate = avg_win = avg_loss = profit_factor = None

    status = ExperimentStatus.ZERO_TRADE_COMPLETED if len(trades) == 0 else ExperimentStatus.COMPLETED

    return FoldResult(
        fold_index=fold_index,
        start_time=start_time if start_time else (fold_candles[0].timestamp if fold_candles else 0),
        end_time=end_time if end_time else (fold_candles[-1].timestamp if fold_candles else 0),
        config_id=config.config_id,
        asset=asset,
        cost_multiplier=cost_scenario.multiplier,
        status=status,
        reason=None if status != ExperimentStatus.INVALID_DATA else "No candles",
        trade_count=len(trades),
        gross_total_return=gross_total_return,
        net_total_return=gross_total_return,
        annualized_return=0.0,  # simplified
        daily_sharpe=None,
        max_drawdown=max_dd,
        exposure=0.0,
        turnover=0.0,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        fee_drag=total_fees / initial_capital if initial_capital > 0 else 0,
        slippage_drag=total_slippage / initial_capital if initial_capital > 0 else 0,
        trades=trades,
        equity_curve=equity_curve,
        timestamps=timestamps
    )

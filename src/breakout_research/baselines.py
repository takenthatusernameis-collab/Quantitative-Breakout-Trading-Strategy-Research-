"""Buy-and-hold baseline metrics for BRAIN-006."""

import hashlib
import json
import os
from statistics import median
from typing import Any, Dict, List

import numpy as np


def _daily_returns(equity: List[float], timestamps: List[int]) -> List[float]:
    daily: Dict[str, float] = {}
    for ts, eq in zip(timestamps, equity):
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        daily[dt] = eq
    days = sorted(daily)
    rets = []
    for i in range(1, len(days)):
        prev = daily[days[i - 1]]
        curr = daily[days[i]]
        if prev > 0:
            rets.append((curr - prev) / prev)
    return rets


def buyhold_baseline(candles: List[Dict[str, Any]], fold_windows: List[Dict[str, Any]],
                     cost_scenarios: List[float], initial_capital: float = 10000.0) -> Dict[str, Any]:
    """Compute buy-and-hold metrics per fold and cost scenario."""
    out: Dict[str, Any] = {"folds": []}
    for fw in fold_windows:
        start = fw["start_time"]
        end = fw["end_time"]
        fc = [c for c in candles if c["timestamp"] >= start and c["timestamp"] < end]
        if not fc:
            out["folds"].append({"fold_index": fw["fold_index"], "scenarios": {}})
            continue
        # buy at first open, sell at last close
        entry = fc[0]["open"]
        exitp = fc[-1]["close"]
        qty = initial_capital / entry if entry > 0 else 0.0
        scenarios = {}
        for cost in cost_scenarios:
            # cost is fee rate applied both sides + slippage
            fee_rate = cost
            slippage = cost
            buy_price = entry * (1.0 + slippage)
            sell_price = exitp * (1.0 - slippage)
            gross = qty * (sell_price - buy_price)
            fees = (qty * buy_price + qty * sell_price) * fee_rate
            net_pnl = gross - fees
            final_equity = initial_capital + net_pnl
            ret = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0.0
            # daily sharpe: equity curve flat-ish; build synthetic daily equity
            ts = [c["timestamp"] for c in fc]
            eq_curve = [initial_capital * (c["close"] / entry) for c in fc]
            dr = _daily_returns(eq_curve, ts)
            if len(dr) >= 2:
                mean_r = float(np.mean(dr))
                std_r = float(np.std(dr, ddof=1))
                sharpe = mean_r / std_r * np.sqrt(365) if std_r > 0 else None
            else:
                sharpe = None
            # max drawdown
            rm = initial_capital
            mdd = 0.0
            for eq in eq_curve:
                if eq > rm:
                    rm = eq
                dd = (rm - eq) / rm if rm > 0 else 0.0
                if dd > mdd:
                    mdd = dd
            scenarios[str(cost)] = {
                "net_total_return": ret,
                "daily_sharpe": sharpe,
                "max_drawdown": mdd,
                "turnover": 1.0,
            }
        out["folds"].append({"fold_index": fw["fold_index"], "scenarios": scenarios})
    # median sharpe across folds at 1x (baseline cost ~ first scenario)
    sharpes = []
    for f in out["folds"]:
        sc = f["scenarios"]
        if sc:
            first = sorted(sc.keys())[0]
            s = sc[first].get("daily_sharpe")
            if s is not None:
                sharpes.append(s)
    out["median_daily_sharpe_1x"] = median(sharpes) if sharpes else None
    return out


def verify_data_manifest(candles_dir: str, data_manifest_path: str) -> str:
    with open(data_manifest_path, encoding="utf-8") as f:
        dm = json.load(f)
    # return content hash of manifest
    return hashlib.sha256(json.dumps(dm, sort_keys=True).encode()).hexdigest()


def compute_code_hash_placeholder() -> str:
    return "see config.compute_code_hash"

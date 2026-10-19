"""Conforming preregistered candidate selection for BRAIN-006."""

from statistics import median
from typing import Any, Dict, List, Optional


def evaluate_candidate(fold_units: List[Dict[str, Any]], spec: Dict[str, Any],
                       baselines: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sel = spec.get("selection", spec)
    min_trades_total = sel.get("min_trades_total", 30)
    min_trades_per_fold = sel.get("min_trades_per_fold", 5)
    min_folds_with_min_trades = sel.get("min_folds_with_min_trades", 3)
    positive_folds_required = sel.get("positive_folds_required", 3)

    # fold-level at baseline cost
    folds = {}
    for u in fold_units:
        if u.get("is_holdout"):
            raise ValueError("holdout record encountered")
        cost = u.get("cost_scenario", u.get("cost", 1.0))
        if cost not in (1.0, 1, "1x", "1.0"):
            continue
        fi = u.get("fold_index")
        folds.setdefault(fi, []).append(u)

    # per-fold trade counts and returns
    fold_trades = {}
    fold_returns = {}
    fold_sharpes = {}
    for fi, units in folds.items():
        trades = sum(u.get("trade_count", u.get("trades", 0)) or 0 for u in units)
        fold_trades[fi] = trades
        # net return mean across units in fold
        rets = [u.get("net_total_return", 0.0) for u in units]
        fold_returns[fi] = (sum(rets) / len(rets)) if rets else 0.0
        sharpes = [u.get("daily_sharpe") for u in units if u.get("daily_sharpe") is not None]
        fold_sharpes[fi] = median(sharpes) if sharpes else 0.0

    n_folds = len(fold_trades)
    folds_with_min = sum(1 for t in fold_trades.values() if t >= min_trades_per_fold)
    total_trades = sum(fold_trades.values())
    positive_folds = sum(1 for r in fold_returns.values() if r > 0)
    combined_return = (sum(fold_returns.values()) / len(fold_returns)) if fold_returns else 0.0
    median_sharpe = median(list(fold_sharpes.values())) if fold_sharpes else 0.0

    # 2x cost return gate
    folds2 = {}
    for u in fold_units:
        cost = u.get("cost_scenario", u.get("cost", 1.0))
        if cost not in (2.0, 2, "2x", "2.0"):
            continue
        fi = u.get("fold_index")
        folds2.setdefault(fi, []).append(u)
    returns2 = []
    for fi, units in folds2.items():
        rets = [u.get("net_total_return", 0.0) for u in units]
        if rets:
            returns2.append(sum(rets) / len(rets))
    combined_return_2x = (sum(returns2) / len(returns2)) if returns2 else 0.0

    # buyhold comparison
    buyhold_sharpe = None
    if baselines:
        # baselines: {asset: {median_daily_sharpe_1x: ...}}
        buyhold_sharpe = baselines.get("median_daily_sharpe_1x")

    gates = {}
    gates["min_trades_total"] = {"value": total_trades, "threshold": min_trades_total,
                                 "pass": total_trades >= min_trades_total}
    gates["min_trades_per_fold"] = {"value": min(fold_trades.values()) if fold_trades else 0,
                                    "threshold": min_trades_per_fold,
                                    "pass": folds_with_min >= min_folds_with_min_trades and all(
                                        t >= min_trades_per_fold for t in fold_trades.values()) if False else folds_with_min >= min_folds_with_min_trades}
    gates["min_folds_with_min_trades"] = {"value": folds_with_min, "threshold": min_folds_with_min_trades,
                                          "pass": folds_with_min >= min_folds_with_min_trades}
    gates["positive_net_return_baseline"] = {"value": combined_return, "threshold": 0.0,
                                             "pass": combined_return > 0}
    gates["positive_net_return_2x_costs"] = {"value": combined_return_2x, "threshold": 0.0,
                                            "pass": combined_return_2x > 0}
    gates["positive_folds_required"] = {"value": positive_folds, "threshold": positive_folds_required,
                                        "pass": positive_folds >= positive_folds_required}
    gates["median_sharpe_gt_zero"] = {"value": median_sharpe, "threshold": 0.0, "pass": median_sharpe > 0}
    if buyhold_sharpe is not None:
        gates["median_sharpe_gt_buyhold"] = {"value": median_sharpe, "threshold": buyhold_sharpe,
                                            "pass": median_sharpe > buyhold_sharpe}
    else:
        gates["median_sharpe_gt_buyhold"] = {"value": median_sharpe, "threshold": None,
                                            "pass": False, "status": "NOT_EVALUABLE"}

    all_pass = all(g.get("pass", False) for g in gates.values() if g.get("status") != "NOT_EVALUABLE")
    # NOT_EVALUABLE gates don't fail if missing? per spec, not evaluable -> fail
    if any(g.get("status") == "NOT_EVALUABLE" for g in gates.values()):
        all_pass = False
    return {"gates": gates, "all_pass": all_pass, "median_sharpe": median_sharpe,
            "combined_return": combined_return, "total_trades": total_trades}


def select_candidates(records: List[Dict[str, Any]], spec: Dict[str, Any],
                      baselines: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if baselines is None:
        baselines = {}
    by_asset: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for rec in records:
        if rec.get("is_holdout"):
            raise ValueError("holdout record encountered")
        asset = rec["asset"]
        cid = rec["config_id"]
        by_asset.setdefault(asset, {}).setdefault(cid, []).append(rec)

    result: Dict[str, Any] = {}
    for asset, configs in by_asset.items():
        best_list = []
        for cid, recs in configs.items():
            ev = evaluate_candidate(recs, spec, baselines.get(asset))
            if ev["all_pass"]:
                best_list.append((cid, ev))
        if not best_list:
            # determine status
            any_eval = False
            for cid, recs in configs.items():
                ev = evaluate_candidate(recs, spec, baselines.get(asset))
                if ev.get("all_pass") is not None:
                    any_eval = True
            # insufficient evidence: exactly one config clears economic screen but fails sample floor
            status = "NO_CANDIDATE"
            result[asset] = {"status": status, "config_id": None, "gates": None}
            continue
        # ranking: median sharpe desc, median net return desc, max_drawdown asc, turnover asc, config_id asc
        def rank_key(item):
            cid, ev = item
            recs = configs[cid]
            sharpes = [r.get("daily_sharpe") for r in recs if r.get("daily_sharpe") is not None]
            msh = median(sharpes) if sharpes else 0.0
            rets = [r.get("net_total_return", 0.0) for r in recs]
            mret = median(rets) if rets else 0.0
            dds = [r.get("max_drawdown", 0.0) for r in recs]
            mdd = median(dds) if dds else 0.0
            tos = [r.get("turnover", 0.0) for r in recs]
            mto = median(tos) if tos else 0.0
            return (-msh, -mret, mdd, mto, cid)
        best_list.sort(key=rank_key)
        cid, ev = best_list[0]
        result[asset] = {"status": "CANDIDATE_SELECTED", "config_id": cid, "gates": ev["gates"]}
    return result

#!/usr/bin/env python3
"""Re-derive per-asset candidates for continuous cycle 0 under the preregistered selection rule.

Read-only: consumes only is_holdout==False records from the cycle shard set.
Buy-and-hold baseline Sharpe is not present in records => median_sharpe_gt_buyhold
is marked NOT_EVALUABLE_FROM_RECORDS (missing field: buyhold_daily_sharpe).
"""
import argparse, hashlib, json, os, statistics

def load_records(shard_dir):
    recs = []
    for fn in sorted(os.listdir(shard_dir)):
        if not fn.endswith(".jsonl"):
            continue
        with open(os.path.join(shard_dir, fn), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
    return recs

def eval_config(recs):
    # recs: list of records for one config (validation only)
    folds = {}
    for r in recs:
        folds.setdefault(r["fold_index"], []).append(r)
    trades_total = sum(r.get("trade_count", 0) for r in recs)
    folds_with_min = sum(1 for f, rs in folds.items() if sum(x.get("trade_count",0) for x in rs) >= 5)
    # per-fold min trades: each fold's trade count (sum across costs) >=5
    per_fold_min_ok = all(sum(x.get("trade_count",0) for x in rs) >= 5 for rs in folds.values()) if folds else False
    median_sharpe = statistics.median([r.get("daily_sharpe", 0.0) for r in recs]) if recs else 0.0
    median_return = statistics.median([r.get("net_total_return", 0.0) for r in recs]) if recs else 0.0
    max_dd = max((r.get("max_drawdown", 0.0) for r in recs), default=0.0)
    median_pf = statistics.median([r.get("profit_factor") if r.get("profit_factor") is not None else 0.0 for r in recs]) if recs else 0.0
    # cost scenarios present
    costs = sorted(set(r.get("cost_multiplier") for r in recs))
    baseline_recs = [r for r in recs if r.get("cost_multiplier") == 1]
    x2_recs = [r for r in recs if r.get("cost_multiplier") == 2]
    pos_baseline = all(r.get("net_total_return", 0.0) > 0 for r in baseline_recs) if baseline_recs else False
    pos_2x = all(r.get("net_total_return", 0.0) > 0 for r in x2_recs) if x2_recs else False
    positive_folds = sum(1 for f, rs in folds.items() if statistics.median([x.get("net_total_return",0.0) for x in rs]) > 0)
    gates = {
        "min_trades_total_30": {"value": trades_total, "pass": trades_total >= 30},
        "min_trades_per_fold_5": {"value": min((sum(x.get("trade_count",0) for x in rs) for rs in folds.values()), default=0), "pass": per_fold_min_ok},
        "min_folds_with_min_trades_3": {"value": folds_with_min, "pass": folds_with_min >= 3},
        "positive_net_return_baseline": {"value": pos_baseline, "pass": bool(pos_baseline) if True else False, "required": True},
        "positive_net_return_2x_costs": {"value": pos_2x, "pass": bool(pos_2x)},
        "positive_folds_required_3": {"value": positive_folds, "pass": positive_folds >= 3},
        "median_sharpe_gt_zero": {"value": median_sharpe, "pass": median_sharpe > 0},
        "median_sharpe_gt_buyhold": {"value": None, "pass": None, "status": "NOT_EVALUABLE_FROM_RECORDS", "missing": "buyhold_daily_sharpe (no buy-and-hold baseline in records)"},
    }
    all_pass = all(g.get("pass") is True for k,g in gates.items() if g.get("status") != "NOT_EVALUABLE_FROM_RECORDS")
    # ranking: median_net_daily_sharpe, tiebreakers median_net_return, max_drawdown, turnover, config_id
    sortkey = (-median_sharpe, -median_return, max_dd, 0, )  # placeholder turnover
    turnover_med = statistics.median([r.get("turnover",0.0) for r in recs]) if recs else 0.0
    sortkey = (median_sharpe, median_return, -max_dd, -turnover_med)
    return {
        "gates": gates, "all_pass": all_pass,
        "ranking": {"median_net_daily_sharpe": median_sharpe, "median_net_return": median_return,
                    "max_drawdown": max_dd, "turnover": turnover_med},
        "sortkey": sortkey,
        "trades_total": trades_total, "folds": len(folds), "costs": costs,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shard_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    shard_dir = args.shard_dir
    if os.path.isdir(shard_dir) and "results_shards" in shard_dir:
        # allow passing cycle root? expect shard dir
        pass
    # find shard dir if given cycle root
    if not any(f.endswith(".jsonl") for f in os.listdir(shard_dir)):
        # look for results_shards/*/ 
        for root,dirs,files in os.walk(shard_dir):
            if any(f.endswith(".jsonl") for f in files):
                shard_dir = root
                break
    recs = load_records(shard_dir)
    # holdout check
    holdout = [r for r in recs if r.get("is_holdout")]
    assert len(holdout) == 0, f"holdout records present: {len(holdout)}"
    # group by asset -> config
    by_asset = {}
    for r in recs:
        if r.get("is_holdout"):
            continue
        if r.get("status") != "COMPLETED":
            continue
        by_asset.setdefault(r["asset"], {}).setdefault(r["config_id"], []).append(r)

    out = {"units_verified": len(recs), "holdout_records_read": 0, "assets": {}}
    for asset, configs in by_asset.items():
        cfg_results = {}
        passing = []
        for cid, rs in configs.items():
            ev = eval_config(rs)
            cfg_results[cid] = ev
            if ev["all_pass"]:
                passing.append((cid, ev))
        # rank passing by sortkey desc
        if passing:
            passing.sort(key=lambda x: (x[1]["sortkey"]), reverse=True)
            selected = passing[0][0]
        else:
            selected = "NO_CANDIDATE"
        out["assets"][asset] = {
            "configs_considered": len(configs),
            "selected": selected,
            "per_config": {cid: {"gates": ev["gates"], "all_pass": ev["all_pass"], "ranking": ev["ranking"]} for cid,ev in cfg_results.items()},
        }
    # frozen manifest comparison
    try:
        fm = json.load(open("research/candidate_manifest.json"))
        frozen = fm.get("candidates", {})
    except Exception:
        frozen = {}
    for asset, info in out["assets"].items():
        f = frozen.get(asset, {})
        info["frozen_manifest_config"] = f.get("config_id")
        info["matches_frozen"] = (info["selected"] == f.get("config_id"))
    out["summary"] = {
        "assets": len(out["assets"]),
        "selected_count": sum(1 for a in out["assets"].values() if a["selected"] != "NO_CANDIDATE"),
    }
    txt = json.dumps(out, sort_keys=True, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    print(txt[:500])

if __name__ == "__main__":
    main()

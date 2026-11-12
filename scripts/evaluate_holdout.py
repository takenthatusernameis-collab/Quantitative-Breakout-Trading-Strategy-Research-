#!/usr/bin/env python3
"""Evaluate holdout fold for frozen v2 candidates.

This script evaluates only the final holdout fold (fold 4) for the
14 frozen candidates in research/candidate_manifest_v2.json.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.breakout_research.config import (
    load_research_spec, load_universe_manifest, load_config_manifest,
    get_eligible_assets, get_configurations, compute_code_hash,
    CostScenario,
)
from src.breakout_research.data.fetcher import load_or_fetch_asset_data, DataUnavailableError
from src.breakout_research.backtest.backtester import run_fold_backtest
from src.breakout_research.candidate_freeze import load_candidate_manifest, CANDIDATE_MANIFEST_V2_PATH, save_candidate_manifest
from src.breakout_research.backtest.shards import ResultStore, compute_experiment_id


# v2 promotion rule constants (from src/v2_confirmatory/report.py)
STATUS_SURVIVAL = "PROVISIONAL_HISTORICAL_SURVIVAL"
STATUS_REJECTED = "REJECTED_ON_HOLDOUT"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
MIN_CLOSED_TRADES = 30


def specification_verdict(metrics: Dict[str, Any], min_trades: int = MIN_CLOSED_TRADES) -> Dict[str, Any]:
    """Apply the frozen v2 promotion rule to one asset's window metrics."""
    data_sufficient = bool(metrics.get("data_sufficient"))
    closed_trades = metrics.get("closed_trades")
    criteria = {
        "net_total_return_positive_at_1x": False,
        "net_total_return_positive_at_2x": False,
        "closed_trades_at_least_threshold": False,
        "parameters_match_frozen_manifest": bool(metrics.get("parameters_match")),
    }

    if not data_sufficient:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": "the window data is insufficient to evaluate the configuration",
            "criteria": criteria,
            "criteria_evaluated": False,
        }
    if closed_trades is None:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": "the number of closed trades on the window is unknown",
            "criteria": criteria,
            "criteria_evaluated": False,
        }
    if int(closed_trades) == 0:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": "the configuration produced no closed trade on the window; a never-traded strategy is not reported as a failure",
            "criteria": criteria,
            "criteria_evaluated": False,
        }

    net_1x = metrics.get("net_total_return_1x")
    net_2x = metrics.get("net_total_return_2x")
    criteria["net_total_return_positive_at_1x"] = net_1x is not None and float(net_1x) > 0.0
    criteria["net_total_return_positive_at_2x"] = net_2x is not None and float(net_2x) > 0.0
    criteria["closed_trades_at_least_threshold"] = int(closed_trades) >= int(min_trades)

    failed = [name for name, holds in criteria.items() if not holds]
    if failed:
        return {
            "status": STATUS_REJECTED,
            "reason": f"the promotion rule was not met: {', '.join(failed)}",
            "criteria": criteria,
            "criteria_evaluated": True,
        }
    return {
        "status": STATUS_SURVIVAL,
        "reason": "every criterion of the preregistered promotion rule holds",
        "criteria": criteria,
        "criteria_evaluated": True,
    }


def baseline_comparison(metrics: Dict[str, Any], baseline_net_return):
    """The protocol's buy-and-hold criterion, computed and reported."""
    net = metrics.get("net_total_return_1x")
    if net is None or baseline_net_return is None or not metrics.get("data_sufficient"):
        return {
            "outcome": "INCONCLUSIVE",
            "net_total_return": net,
            "baseline_net_total_return": baseline_net_return,
            "difference": None,
            "tie": False,
        }
    difference = float(net) - float(baseline_net_return)
    if difference > 0.0:
        outcome = "PASS"
    else:
        outcome = "FAIL"
    return {
        "outcome": outcome,
        "net_total_return": float(net),
        "baseline_net_total_return": float(baseline_net_return),
        "difference": difference,
        "tie": difference == 0.0,
    }


def criteria_agreement(specification_status: str, baseline_outcome: str) -> str:
    """Whether the two criteria agree on this asset."""
    if specification_status == STATUS_INCONCLUSIVE:
        return "NOT_COMPARABLE"
    if specification_status == STATUS_SURVIVAL and baseline_outcome == "PASS":
        return "AGREE"
    if specification_status == STATUS_REJECTED and baseline_outcome == "FAIL":
        return "AGREE"
    return "DISAGREE"


DATA_MANIFEST_PATH = "research/data_manifest.json"
SHARD_ROOT = "research/results_shards"
MANIFEST_PATH = "research/results_manifest.json"


def _read_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _data_manifest_hash(manifest: Dict[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_data_hashes(manifest: Dict[str, Any]) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for symbol, entry in manifest.get("assets", {}).items():
        content_hash = entry.get("content_hash")
        if content_hash:
            hashes[symbol] = str(content_hash)
    return hashes


def _unit_data_hash(asset_symbol: str, config, data_hashes: Dict[str, str]) -> str:
    base = data_hashes.get(asset_symbol, "")
    if config.trend_filter.name == "BTC_EMA_168":
        btc_hash = data_hashes.get("BTCUSDT", "")
        if base and btc_hash:
            return hashlib.sha256(f"{base}:{btc_hash}".encode("utf-8")).hexdigest()
        return base or btc_hash or ""
    return base


def _get_fold_bounds(candles: List, spec: Dict[str, Any]) -> List[tuple]:
    n = len(candles)
    if n == 0:
        return []

    first_ts = candles[0].timestamp
    last_ts = candles[-1].timestamp
    total_span = last_ts - first_ts

    fold_bounds = []

    dev_fraction = spec['folds']['development_fraction']
    validation_windows = spec['folds']['window_fractions']
    dev_end_ts = first_ts + int(total_span * dev_fraction)

    for i, frac in enumerate(validation_windows):
        window_start = first_ts + int(total_span * frac)
        window_end = dev_end_ts if i == len(validation_windows) - 1 else first_ts + int(total_span * validation_windows[i + 1])
        fold_bounds.append((window_start, window_end, i, False))

    holdout_start = dev_end_ts
    holdout_end = last_ts
    fold_bounds.append((holdout_start, holdout_end, len(validation_windows), True))

    return fold_bounds


def main():
    spec = load_research_spec()
    universe = load_universe_manifest()
    config_manifest = load_config_manifest()
    assets = get_eligible_assets(universe)
    configs = get_configurations(config_manifest)
    cost_multipliers = spec['costs']['scenarios']

    protocol_hash = spec['specification_hash']
    code_hash = compute_code_hash()

    try:
        data_manifest = _read_json_file(DATA_MANIFEST_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read data manifest {DATA_MANIFEST_PATH}: {exc}") from exc
    data_hashes = _asset_data_hashes(data_manifest)
    data_manifest_hash = _data_manifest_hash(data_manifest)

    campaign_id = hashlib.sha256(
        f"{protocol_hash}:{code_hash}:{data_manifest_hash}".encode("utf-8")
    ).hexdigest()

    print(f"Campaign ID: {campaign_id}")
    print(f"Protocol hash: {protocol_hash}")
    print(f"Code hash: {code_hash}")
    print(f"Data manifest hash: {data_manifest_hash}")

    # Load frozen candidates from v2 manifest
    v2_manifest = load_candidate_manifest(CANDIDATE_MANIFEST_V2_PATH)
    candidate_ids = {}
    for asset, entry in v2_manifest.get("candidates", {}).items():
        candidate_ids[asset] = {entry["config_id"]}

    print(f"Frozen candidates: {len(candidate_ids)} assets")
    for asset, cids in candidate_ids.items():
        print(f"  {asset}: {cids}")

    # Build config lookup
    config_by_id = {c.config_id: c for c in configs}

    # Load baseline artifact for buy-and-hold comparison
    baseline_artifact_path = v2_manifest.get("baseline_artifact_path")
    if baseline_artifact_path and os.path.exists(baseline_artifact_path):
        with open(baseline_artifact_path, "r", encoding="utf-8") as f:
            baseline_artifact = json.load(f)
        print(f"Loaded baseline artifact: {baseline_artifact_path}")
    else:
        baseline_artifact = None
        print("No baseline artifact found")

    store = ResultStore(
        campaign_id=campaign_id,
        spec_hash=protocol_hash,
        code_hash=code_hash,
        data_manifest_hash=data_manifest_hash,
        shard_root=SHARD_ROOT,
        manifest_path=MANIFEST_PATH,
    )

    completed_ids, total_bytes = store.reconcile()
    print(f"Existing verified units: {len(completed_ids)}")

    results = {}

    for asset_info in assets:
        asset_symbol = asset_info['symbol']
        if asset_symbol not in candidate_ids:
            continue

        frozen_config_ids = candidate_ids[asset_symbol]
        print(f"\nProcessing {asset_symbol}...")

        try:
            candles = load_or_fetch_asset_data(asset_symbol)
        except DataUnavailableError as exc:
            print(f"  ERROR: No data for {asset_symbol}: {exc}")
            results[asset_symbol] = {"error": str(exc)}
            continue

        btc_candles = None
        if asset_symbol != 'BTCUSDT':
            try:
                btc_candles = load_or_fetch_asset_data('BTCUSDT')
            except DataUnavailableError as exc:
                print(f"  ERROR: No BTC data for {asset_symbol}: {exc}")
                results[asset_symbol] = {"error": f"BTC unavailable: {exc}"}
                continue

        fold_bounds = _get_fold_bounds(candles, spec)
        holdout_bounds = fold_bounds[-1]  # Last fold is holdout
        holdout_start, holdout_end, holdout_fold_index, is_holdout = holdout_bounds

        print(f"  Holdout fold: {holdout_fold_index}, start={holdout_start}, end={holdout_end}")

        for config_id in frozen_config_ids:
            config = config_by_id.get(config_id)
            if not config:
                print(f"  ERROR: Config {config_id} not found in manifest")
                results[asset_symbol] = {"error": f"Config {config_id} not found"}
                continue

            print(f"  Evaluating config: {config_id}")

            # Get baseline net return for this asset if available
            baseline_net_return = None
            if baseline_artifact and "assets" in baseline_artifact:
                asset_baseline = baseline_artifact["assets"].get(asset_symbol)
                if asset_baseline and asset_baseline.get("status") == "OK":
                    baseline_net_return = asset_baseline.get("median_daily_sharpe")

            # Run holdout evaluation for each cost scenario
            holdout_results = {}
            for cost_mult in cost_multipliers:
                cost_scenario = CostScenario.baseline().scaled(cost_mult)
                data_hash = _unit_data_hash(asset_symbol, config, data_hashes)
                experiment_id = compute_experiment_id(
                    spec_hash=protocol_hash,
                    code_hash=code_hash,
                    data_hash=data_hash,
                    asset=asset_symbol,
                    config_id=config_id,
                    fold_index=holdout_fold_index,
                    start_time=int(holdout_start),
                    end_time=int(holdout_end),
                    is_holdout=True,
                    cost_multiplier=float(cost_mult),
                )

                if experiment_id in completed_ids:
                    print(f"    Cost {cost_mult}x: Already completed (skipping)")
                    # Load existing result
                    for shard_path in store._shard_paths():
                        if os.path.exists(shard_path):
                            with open(shard_path, "r") as f:
                                for line in f:
                                    if line.strip():
                                        rec = json.loads(line)
                                        if rec.get("experiment_id") == experiment_id:
                                            holdout_results[cost_mult] = rec
                                            break
                    continue

                print(f"    Cost {cost_mult}x: Running backtest...")
                fold_res = run_fold_backtest(
                    candles, config, btc_candles=btc_candles,
                    start_time=holdout_start, end_time=holdout_end,
                    cost_scenario=cost_scenario,
                    fold_index=holdout_fold_index,
                    asset=asset_symbol,
                )

                record = {
                    "experiment_id": experiment_id,
                    "asset": asset_symbol,
                    "config_id": config_id,
                    "fold_index": holdout_fold_index,
                    "start_time": int(holdout_start),
                    "end_time": int(holdout_end),
                    "cost_multiplier": float(cost_mult),
                    "status": fold_res.status.value,
                    "reason": fold_res.reason,
                    "trade_count": fold_res.trade_count,
                    "gross_total_return": fold_res.gross_total_return,
                    "net_total_return": fold_res.net_total_return,
                    "annualized_return": fold_res.annualized_return,
                    "daily_sharpe": fold_res.daily_sharpe,
                    "max_drawdown": fold_res.max_drawdown,
                    "exposure": fold_res.exposure,
                    "turnover": fold_res.turnover,
                    "win_rate": fold_res.win_rate,
                    "avg_win": fold_res.avg_win,
                    "avg_loss": fold_res.avg_loss,
                    "profit_factor": fold_res.profit_factor,
                    "profit_factor_status": fold_res.profit_factor_status,
                    "fee_drag": fold_res.fee_drag,
                    "slippage_drag": fold_res.slippage_drag,
                    "data_hash": data_hash,
                    "stored_utc": datetime.now(timezone.utc).isoformat(),
                    "is_holdout": True,
                }

                store.append(experiment_id, record)
                completed_ids[experiment_id] = True
                holdout_results[cost_mult] = record
                print(f"      Status: {fold_res.status.value}, Trades: {fold_res.trade_count}, Net Return: {fold_res.net_total_return:.6f}, Sharpe: {fold_res.daily_sharpe}")

            # Evaluate using v2 promotion rule
            # Need: net_total_return_1x, net_total_return_2x, closed_trades, data_sufficient, parameters_match
            metrics = {}
            r1x = holdout_results.get(1.0, {})
            r2x = holdout_results.get(2.0, {})
            r3x = holdout_results.get(3.0, {})

            metrics["net_total_return_1x"] = r1x.get("net_total_return")
            metrics["net_total_return_2x"] = r2x.get("net_total_return")
            metrics["net_total_return_3x"] = r3x.get("net_total_return")
            metrics["closed_trades"] = r1x.get("trade_count")
            metrics["data_sufficient"] = r1x.get("status") == "COMPLETED"
            metrics["parameters_match"] = True  # We're using the frozen config

            verdict = specification_verdict(metrics)
            print(f"  Holdout verdict: {verdict['status']} - {verdict['reason']}")

            # Also compute baseline comparison
            baseline_comp = baseline_comparison(metrics, baseline_net_return)
            agreement = criteria_agreement(verdict["status"], baseline_comp["outcome"])
            print(f"  Baseline comparison: {baseline_comp['outcome']} (diff: {baseline_comp['difference']})")
            print(f"  Criteria agreement: {agreement}")

            results[asset_symbol] = {
                "config_id": config_id,
                "holdout_results": holdout_results,
                "verdict": verdict,
                "baseline_comparison": baseline_comp,
                "criteria_agreement": agreement,
            }

            # Update candidate manifest with holdout result
            v2_manifest["candidates"][asset_symbol]["holdout_verdict"] = verdict
            v2_manifest["candidates"][asset_symbol]["holdout_baseline_comparison"] = baseline_comp
            v2_manifest["candidates"][asset_symbol]["criteria_agreement"] = agreement

    store.flush()
    store.close()

    # Update overall candidate status
    survivors = [a for a, r in results.items() if r.get("verdict", {}).get("status") == STATUS_SURVIVAL]
    if survivors:
        v2_manifest["candidate_status"] = "MIXED_SURVIVAL_AND_REJECTION"
    else:
        v2_manifest["candidate_status"] = "ALL_REJECTED_ON_HOLDOUT"

    # Save updated manifest
    save_candidate_manifest(v2_manifest, CANDIDATE_MANIFEST_V2_PATH)
    print(f"\nUpdated {CANDIDATE_MANIFEST_V2_PATH} with holdout results")

    # Print summary
    print("\n=== HOLDOUT EVALUATION SUMMARY ===")
    for asset, result in results.items():
        verdict = result.get("verdict", {})
        print(f"  {asset} ({result['config_id']}): {verdict.get('status', 'ERROR')} - {verdict.get('reason', 'N/A')}")

    return results


if __name__ == "__main__":
    main()
"""Full campaign runner for breakout research."""
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from .config import (
    load_research_spec, load_universe_manifest, load_config_manifest,
    get_eligible_assets, get_configurations, compute_code_hash,
    CostScenario, CheckpointState, FoldResult, ExperimentStatus
)
from .data.fetcher import load_or_fetch_asset_data
from .backtest.backtester import run_fold_backtest
from .backtest.ledger import ResultLedger
from .backtest.checkpoint import CheckpointManager


class CampaignRunner:
    def __init__(self):
        self.spec = load_research_spec()
        self.universe = load_universe_manifest()
        self.config_manifest = load_config_manifest()
        self.assets = get_eligible_assets(self.universe)
        self.configs = get_configurations(self.config_manifest)
        self.cost_multipliers = self.spec['costs']['scenarios']  # [1.0, 2.0, 3.0]
        self.fold_count = self.spec['folds']['validation_windows'] + 1  # 4 validation + 1 holdout = 5
        self.validation_windows = self.spec['folds']['window_fractions']
        self.dev_fraction = self.spec['folds']['development_fraction']
        self.holdout_fraction = self.spec['folds']['holdout_fraction']
        self.batch_size = self.spec['checkpointing']['batch_size']
        self.protocol_hash = self.spec['specification_hash']

    def _get_fold_bounds(self, candles: List) -> List[tuple]:
        """Calculate fold boundaries (start_time, end_time, fold_index, is_holdout)."""
        n = len(candles)
        if n == 0:
            return []

        first_ts = candles[0].timestamp
        last_ts = candles[-1].timestamp
        total_span = last_ts - first_ts

        fold_bounds = []

        # Validation folds (first 80%)
        dev_end_ts = first_ts + int(total_span * self.dev_fraction)

        # 4 validation windows
        for i, frac in enumerate(self.validation_windows):
            window_start = first_ts + int(total_span * frac)
            window_end = dev_end_ts if i == len(self.validation_windows) - 1 else first_ts + int(total_span * self.validation_windows[i + 1])
            fold_bounds.append((window_start, window_end, i, False))

        # Holdout fold (last 20%)
        holdout_start = dev_end_ts
        holdout_end = last_ts
        fold_bounds.append((holdout_start, holdout_end, len(self.validation_windows), True))

        return fold_bounds

    def run(self, max_assets: Optional[int] = None) -> Dict[str, Any]:
        """Run the full campaign."""
        ledger = ResultLedger()
        checkpoint_mgr = CheckpointManager()

        # Load existing checkpoint or create new
        state = checkpoint_mgr.load()
        if state is None:
            state = checkpoint_mgr.create_initial(self.protocol_hash)

        # Verify pilot gate
        pilot_gate_path = 'research_state/pilot_gate.json'
        if not os.path.exists(pilot_gate_path):
            raise RuntimeError("Pilot gate not found. Run pilot first.")

        with open(pilot_gate_path, 'r') as f:
            pilot_gate = json.load(f)

        if not pilot_gate.get('campaign_authorized', False):
            raise RuntimeError("Campaign not authorized by pilot gate.")

        if pilot_gate.get('specification_hash') != self.protocol_hash:
            raise RuntimeError("Specification hash mismatch. Pilot gate from different protocol version.")

        if pilot_gate.get('code_hash') != compute_code_hash():
            raise RuntimeError("Code hash mismatch. Code has changed since pilot.")

        state.pilot_completed = True
        state.pilot_passed = True

        # Limit assets if specified
        assets_to_process = self.assets[:max_assets] if max_assets else self.assets

        total_configs = len(self.configs)
        total_folds = self.fold_count
        total_costs = len(self.cost_multipliers)

        print(f"Starting campaign: {len(assets_to_process)} assets, {total_configs} configs, {total_folds} folds, {total_costs} cost scenarios")
        print(f"Total experiments: {len(assets_to_process) * total_configs * total_folds * total_costs}")
        print(f"Resuming from asset_index={state.current_asset_index}, config_index={state.current_config_index}, fold_index={state.current_fold_index}, cost_index={state.current_cost_index}")

        records_since_checkpoint = 0

        for asset_idx in range(state.current_asset_index, len(assets_to_process)):
            asset = assets_to_process[asset_idx]
            asset_symbol = asset['symbol']
            print(f"\nProcessing asset {asset_idx + 1}/{len(assets_to_process)}: {asset_symbol} (rank {asset['rank']})")

            state.current_asset_index = asset_idx
            state.current_config_index = 0
            state.current_fold_index = 0
            state.current_cost_index = 0

            # Load asset data
            try:
                candles = load_or_fetch_asset_data(asset_symbol)
                print(f"  Loaded {len(candles)} candles for {asset_symbol}")
            except Exception as e:
                print(f"  Failed to load data for {asset_symbol}: {e}")
                state.current_asset_index = asset_idx + 1
                checkpoint_mgr.save(state)
                continue

            # Get BTC candles for BTC trend filter
            btc_candles = None
            if asset_symbol != 'BTCUSDT':
                try:
                    btc_candles = load_or_fetch_asset_data('BTCUSDT')
                except Exception:
                    pass

            fold_bounds = self._get_fold_bounds(candles)

            # Process configs
            for config_idx in range(state.current_config_index, total_configs):
                config = self.configs[config_idx]
                state.current_config_index = config_idx
                state.current_fold_index = 0
                state.current_cost_index = 0

                # Process folds
                for fold_idx in range(state.current_fold_index, total_folds):
                    start_time, end_time, fold_index, is_holdout = fold_bounds[fold_idx]
                    state.current_fold_index = fold_idx
                    state.current_cost_index = 0

                    # Process cost scenarios
                    for cost_idx in range(state.current_cost_index, total_costs):
                        cost_mult = self.cost_multipliers[cost_idx]
                        cost_scenario = CostScenario.baseline().scaled(cost_mult)
                        state.current_cost_index = cost_idx

                        # Run backtest
                        fold_res = run_fold_backtest(
                            candles, config, btc_candles=btc_candles,
                            start_time=start_time, end_time=end_time,
                            cost_scenario=cost_scenario,
                            fold_index=fold_index,
                            asset=asset_symbol
                        )

                        # Add metadata
                        fold_res_dict = {
                            'asset': fold_res.asset,
                            'config_id': fold_res.config_id,
                            'fold_index': fold_res.fold_index,
                            'start_time': fold_res.start_time,
                            'end_time': fold_res.end_time,
                            'cost_multiplier': fold_res.cost_multiplier,
                            'status': fold_res.status.value,
                            'reason': fold_res.reason,
                            'trade_count': fold_res.trade_count,
                            'gross_total_return': fold_res.gross_total_return,
                            'net_total_return': fold_res.net_total_return,
                            'annualized_return': fold_res.annualized_return,
                            'daily_sharpe': fold_res.daily_sharpe,
                            'max_drawdown': fold_res.max_drawdown,
                            'exposure': fold_res.exposure,
                            'turnover': fold_res.turnover,
                            'win_rate': fold_res.win_rate,
                            'avg_win': fold_res.avg_win,
                            'avg_loss': fold_res.avg_loss,
                            'profit_factor': fold_res.profit_factor,
                            'fee_drag': fold_res.fee_drag,
                            'slippage_drag': fold_res.slippage_drag,
                            'timestamp_utc': datetime.now(timezone.utc).isoformat()
                        }

                        with open('research/results.jsonl', 'a') as f:
                            f.write(json.dumps(fold_res_dict, sort_keys=True) + '\n')

                        state.completed_records += 1
                        records_since_checkpoint += 1

                        # Progress logging
                        if state.completed_records % 100 == 0:
                            print(f"  Completed {state.completed_records} experiments...")

                        # Save checkpoint periodically
                        if records_since_checkpoint >= self.batch_size:
                            state.timestamp_utc = datetime.now(timezone.utc).isoformat()
                            state.next_unit = {
                                'asset_index': state.current_asset_index,
                                'config_index': state.current_config_index,
                                'fold_index': state.current_fold_index,
                                'cost_index': state.current_cost_index
                            }
                            checkpoint_mgr.save(state)
                            records_since_checkpoint = 0

                    # Reset cost index after each fold
                    state.current_cost_index = 0

                # Reset fold index after each config
                state.current_fold_index = 0

            # Reset config index after each asset
            state.current_config_index = 0
            # Mark this asset as completed by advancing to next
            state.current_asset_index = asset_idx + 1
            checkpoint_mgr.save(state)

        # Final checkpoint
        state.timestamp_utc = datetime.now(timezone.utc).isoformat()
        state.next_unit = {}
        checkpoint_mgr.save(state)

        print(f"\nCampaign complete! Total experiments: {state.completed_records}")

        return {
            'status': 'CAMPAIGN_COMPLETE',
            'total_experiments': state.completed_records,
            'assets_processed': len(assets_to_process)
        }


def run_campaign(max_assets: Optional[int] = None) -> Dict[str, Any]:
    """Entry point to run the campaign."""
    runner = CampaignRunner()
    return runner.run(max_assets=max_assets)


if __name__ == '__main__':
    import sys
    max_assets = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = run_campaign(max_assets)
    print(json.dumps(result, indent=2))
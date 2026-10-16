"""Full campaign runner for breakout research.

Results are written to bounded, immutable, hash-verified JSONL shards via
``backtest.shards.ResultStore`` (research/results_shards/<campaign_id>/ plus a
research/results_manifest.json). The legacy research/results.jsonl is never
appended to by this module: it is preserved as legacy-unverified evidence.

Resume position is derived from the manifest-verified set of completed
experiment IDs, never from checkpoint counters. The final holdout fold is
skipped unless holdout_enabled=True (BRAIN-003 phase 1: validation code never
touches the final holdout).
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import (
    load_research_spec, load_universe_manifest, load_config_manifest,
    get_eligible_assets, get_configurations, compute_code_hash,
    CostScenario, CheckpointState, FoldResult, TrendFilter,
)
from .data.fetcher import load_or_fetch_asset_data, DataUnavailableError
from .backtest.backtester import run_fold_backtest
from .backtest.checkpoint import CheckpointManager
from .backtest.ledger import ResultLedger
from .backtest.shards import ResultStore, compute_experiment_id
from .candidate_freeze import load_candidate_manifest, candidate_config_ids, CANDIDATE_MANIFEST_PATH

DATA_MANIFEST_PATH = "research/data_manifest.json"
PILOT_GATE_PATH = "research_state/pilot_gate.json"
CHECKPOINT_PATH = "research_state/checkpoint.json"
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
    """Hash of the dataset(s) a unit's result depends on.

    Non-BTC-filter units depend on the asset's own data only. BTC trend-filter
    units additionally depend on the BTC benchmark dataset, so a BTC data
    change produces new experiment IDs.
    """
    base = data_hashes.get(asset_symbol, "")
    if config.trend_filter == TrendFilter.BTC_EMA_168:
        btc_hash = data_hashes.get("BTCUSDT", "")
        if base and btc_hash:
            return hashlib.sha256(f"{base}:{btc_hash}".encode("utf-8")).hexdigest()
        return base or btc_hash or ""
    return base


def _fold_result_dict(fold_res: FoldResult, experiment_id: str, data_hash: str,
                      start_time: int, end_time: int) -> Dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "asset": fold_res.asset,
        "config_id": fold_res.config_id,
        "fold_index": fold_res.fold_index,
        # Identity bounds: the requested fold window, matching the experiment ID.
        "start_time": int(start_time),
        "end_time": int(end_time),
        "cost_multiplier": fold_res.cost_multiplier,
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
        "fee_drag": fold_res.fee_drag,
        "slippage_drag": fold_res.slippage_drag,
        "data_hash": data_hash,
        "stored_utc": datetime.now(timezone.utc).isoformat(),
    }


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

    def _verify_stale_checkpoint(self, protocol_hash: str, code_hash: str) -> None:
        """Reject a checkpoint bound to a different protocol or code version.

        Counters and cursors in a stale checkpoint are untrusted legacy state;
        resume position is always derived from verified shards (§12 / BRAIN-004).
        """
        if not os.path.exists(CHECKPOINT_PATH):
            return
        try:
            stored = _read_json_file(CHECKPOINT_PATH)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Checkpoint file is corrupt and cannot be validated: {exc}") from exc
        stored_protocol = stored.get("protocol_hash")
        stored_code = stored.get("code_hash")
        if stored_protocol is not None and stored_protocol != protocol_hash:
            raise RuntimeError(
                f"Checkpoint protocol hash mismatch: stored {stored_protocol} != current {protocol_hash}; "
                "refusing to resume with invalidated results"
            )
        if stored_code is not None and stored_code != code_hash:
            raise RuntimeError(
                f"Checkpoint code hash mismatch: stored {stored_code} != current {code_hash}; "
                "code changed since checkpoint, refusing to resume"
            )

    def _verify_pilot_gate(self, protocol_hash: str, code_hash: str) -> None:
        if not os.path.exists(PILOT_GATE_PATH):
            raise RuntimeError("Pilot gate not found. Run pilot first.")

        pilot_gate = _read_json_file(PILOT_GATE_PATH)

        if not pilot_gate.get('campaign_authorized', False):
            raise RuntimeError("Campaign not authorized by pilot gate.")

        if pilot_gate.get('specification_hash') != protocol_hash:
            raise RuntimeError("Specification hash mismatch. Pilot gate from different protocol version.")

        if pilot_gate.get('code_hash') != code_hash:
            raise RuntimeError("Code hash mismatch. Code has changed since pilot.")

    def _new_checkpoint_state(self, code_hash: str, completed_records: int,
                              next_unit: Dict[str, Any], asset_index: int = 0,
                              config_index: int = 0, fold_index: int = 0,
                              cost_index: int = 0) -> CheckpointState:
        return CheckpointState(
            protocol_hash=self.protocol_hash,
            code_hash=code_hash,
            current_asset_index=asset_index,
            current_config_index=config_index,
            current_fold_index=fold_index,
            current_cost_index=cost_index,
            completed_records=completed_records,
            last_verified_record=completed_records,
            next_unit=next_unit,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pilot_completed=True,
            pilot_passed=True,
        )

    def _save_checkpoint(self, checkpoint_mgr: CheckpointManager, code_hash: str,
                         completed_records: int, next_unit: Dict[str, Any],
                         asset_index: int = 0, config_index: int = 0,
                         fold_index: int = 0, cost_index: int = 0) -> None:
        state = self._new_checkpoint_state(
            code_hash, completed_records, next_unit,
            asset_index, config_index, fold_index, cost_index,
        )
        checkpoint_mgr.save(state)

    def _iter_units(self, assets: List[Dict[str, Any]], configs, cost_multipliers: List[float],
                    fold_bounds: List[tuple], holdout_enabled: bool,
                    asset_index: int, data_hashes: Dict[str, str],
                    protocol_hash: str, code_hash: str,
                    candidate_ids=None):
        """Yield (unit, experiment_id) in the campaign's fixed processing order.

        Units whose fold is the final holdout are skipped when holdout
        validation is disabled (BRAIN-003 phase 1).
        """
        asset_symbol = assets[asset_index]['symbol']
        for config_index, config in enumerate(configs):
            for fold_position, (start_time, end_time, fold_index, is_holdout) in enumerate(fold_bounds):
                if is_holdout and not holdout_enabled:
                    continue  # holdout gate: validation never evaluates the final holdout
                if is_holdout and holdout_enabled:
                    ids = (candidate_ids or {}).get(asset_symbol, set())
                    if config.config_id not in ids:
                        continue  # holdout only evaluates frozen candidates
                for cost_index, cost_mult in enumerate(cost_multipliers):
                    cost_scenario = CostScenario.baseline().scaled(cost_mult)
                    data_hash = _unit_data_hash(asset_symbol, config, data_hashes)
                    experiment_id = compute_experiment_id(
                        spec_hash=protocol_hash,
                        code_hash=code_hash,
                        data_hash=data_hash,
                        asset=asset_symbol,
                        config_id=config.config_id,
                        fold_index=fold_index,
                        start_time=int(start_time),
                        end_time=int(end_time),
                        is_holdout=bool(is_holdout),
                        cost_multiplier=float(cost_mult),
                    )
                    unit = {
                        "asset_index": asset_index,
                        "config_index": config_index,
                        "fold_index": fold_index,
                        "cost_index": cost_index,
                        "asset": asset_symbol,
                        "rank": assets[asset_index].get('rank'),
                        "config": config,
                        "cost_scenario": cost_scenario,
                        "start_time": int(start_time),
                        "end_time": int(end_time),
                        "fold_index_in_source": fold_index,
                        "is_holdout": bool(is_holdout),
                    }
                    yield unit, experiment_id

    def run(self, holdout_enabled: bool = False, max_assets: Optional[int] = None) -> Dict[str, Any]:
        """Run validation (default) or full campaign, resumably and idempotently.

        With holdout_enabled=False (default) only the four validation folds are
        evaluated; the final holdout is never executed or written, so validation
        code cannot touch holdout data (BRAIN-003 phase 1).
        """
        protocol_hash = self.protocol_hash
        code_hash = compute_code_hash()

        # Fail closed on a stale/mismatched checkpoint before touching results.
        self._verify_stale_checkpoint(protocol_hash, code_hash)

        # Pilot gate (BRAIN-002 will replace the self-authorized boolean with
        # independent validation; the gate remains checked here to avoid any
        # silent authorization regression).
        self._verify_pilot_gate(protocol_hash, code_hash)

        # Data provenance: per-asset content hashes bind results to data versions.
        try:
            data_manifest = _read_json_file(DATA_MANIFEST_PATH)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read data manifest {DATA_MANIFEST_PATH}: {exc}") from exc
        data_hashes = _asset_data_hashes(data_manifest)
        data_manifest_hash = _data_manifest_hash(data_manifest)
        campaign_id = hashlib.sha256(
            f"{protocol_hash}:{code_hash}:{data_manifest_hash}".encode("utf-8")
        ).hexdigest()

        store = ResultStore(
            campaign_id=campaign_id,
            spec_hash=protocol_hash,
            code_hash=code_hash,
            data_manifest_hash=data_manifest_hash,
            shard_root=SHARD_ROOT,
            manifest_path=MANIFEST_PATH,
        )

        # Authoritative resume: completed experiment IDs from verified shards.
        # Checkpoint counters (completed_records, current_* indices,
        # last_verified_record) are untrusted legacy state and are never used
        # to derive the resume position.
        completed_ids, total_bytes = store.reconcile()

        candidate_ids = None
        if holdout_enabled:
            try:
                manifest = load_candidate_manifest()
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"Holdout evaluation requires a frozen candidate manifest: {exc}") from exc
            candidate_ids = candidate_config_ids(manifest)
            if not candidate_ids:
                raise RuntimeError("Holdout evaluation requires at least one frozen candidate")

        assets_to_process = self.assets[:max_assets] if max_assets else self.assets
        total_configs = len(self.configs)
        total_costs = len(self.cost_multipliers)

        print(f"Starting campaign (holdout_enabled={holdout_enabled}): "
              f"{len(assets_to_process)} assets, {total_configs} configs, "
              f"{self.fold_count - (0 if holdout_enabled else 1)} active folds, "
              f"{total_costs} cost scenarios")
        print(f"Verified completed units: {len(completed_ids)}")

        records_since_checkpoint = 0
        first_missing: Optional[Dict[str, int]] = None
        completed_this_session = 0
        checkpoint_mgr = CheckpointManager()

        for asset_index in range(len(assets_to_process)):
            asset = assets_to_process[asset_index]
            asset_symbol = asset['symbol']
            print(f"\nProcessing asset {asset_index + 1}/{len(assets_to_process)}: {asset_symbol} (rank {asset.get('rank')})")

            # Fail closed: a required eligible asset without verified protocol-
            # compliant history blocks the campaign; no synthetic fallback.
            try:
                candles = load_or_fetch_asset_data(asset_symbol)
            except DataUnavailableError as exc:
                store.close()
                raise RuntimeError(
                    f"Campaign blocked: required eligible asset {asset_symbol} has no verified "
                    f"protocol-compliant history; no asset skip or synthetic fallback is allowed: {exc}"
                ) from exc

            btc_candles = None
            if asset_symbol != 'BTCUSDT':
                try:
                    btc_candles = load_or_fetch_asset_data('BTCUSDT')
                except DataUnavailableError as exc:
                    store.close()
                    raise RuntimeError(
                        f"Campaign blocked: validated BTCUSDT benchmark history is required "
                        f"for {asset_symbol}, but it is unavailable: {exc}"
                    ) from exc

            fold_bounds = self._get_fold_bounds(candles)

            for unit, experiment_id in self._iter_units(
                assets_to_process, self.configs, self.cost_multipliers,
                fold_bounds, holdout_enabled, asset_index, data_hashes,
                protocol_hash, code_hash, candidate_ids,
            ):
                if experiment_id in completed_ids:
                    continue  # already verified-complete: skip, never duplicate

                if first_missing is None:
                    first_missing = {
                        "asset_index": unit["asset_index"],
                        "config_index": unit["config_index"],
                        "fold_index": unit["fold_index"],
                        "cost_index": unit["cost_index"],
                    }

                config = unit["config"]
                cost_scenario = unit["cost_scenario"]
                start_time = unit["start_time"]
                end_time = unit["end_time"]
                fold_index = unit["fold_index_in_source"]

                # Run backtest (failures propagate: no silent skip, no synthetic substitute)
                fold_res = run_fold_backtest(
                    candles, config, btc_candles=btc_candles,
                    start_time=start_time, end_time=end_time,
                    cost_scenario=cost_scenario,
                    fold_index=fold_index,
                    asset=asset_symbol,
                )

                data_hash = _unit_data_hash(asset_symbol, config, data_hashes)
                record = _fold_result_dict(
                    fold_res, experiment_id, data_hash, start_time, end_time,
                )
                record["is_holdout"] = unit["is_holdout"]

                # Fail closed on an oversized row: never silently drop or split.
                store.append(experiment_id, record)
                completed_ids[experiment_id] = True
                completed_this_session += 1
                records_since_checkpoint += 1

                if records_since_checkpoint >= self.batch_size:
                    store.flush()
                    next_unit = first_missing if first_missing is not None else {}
                    self._save_checkpoint(
                        checkpoint_mgr, code_hash, len(completed_ids), next_unit,
                        unit["asset_index"], unit["config_index"],
                        unit["fold_index"], unit["cost_index"],
                    )
                    records_since_checkpoint = 0

            # End of asset: checkpoint the durable boundary.
            store.flush()
            next_unit = first_missing if first_missing is not None else {}
            self._save_checkpoint(
                checkpoint_mgr, code_hash, len(completed_ids), next_unit,
                asset_index + 1, 0, 0, 0,
            )

        store.flush()
        store.close()

        # All enumerated units were either already verified-complete or just
        # executed: nothing remains within this run's scope.
        all_done = True
        _, final_bytes = store.reconcile()
        status = 'CAMPAIGN_COMPLETE' if (all_done and holdout_enabled) else 'CAMPAIGN_PARTIAL'

        self._save_checkpoint(
            checkpoint_mgr, code_hash, len(completed_ids),
            {} if all_done else (first_missing or {}),
            len(assets_to_process), 0, 0, 0,
        )

        print(f"\nCampaign {status.lower()}: {len(completed_ids)} verified units, "
              f"{completed_this_session} executed this session, {final_bytes} shard bytes")

        return {
            'status': status,
            'total_experiments': len(completed_ids),
            'executed_this_session': completed_this_session,
            'assets_processed': len(assets_to_process),
            'holdout_enabled': holdout_enabled,
            'shard_bytes': final_bytes,
        }


def run_campaign(holdout_enabled: bool = False, max_assets: Optional[int] = None) -> Dict[str, Any]:
    """Entry point to run the campaign."""
    runner = CampaignRunner()
    return runner.run(holdout_enabled=holdout_enabled, max_assets=max_assets)


if __name__ == '__main__':
    import sys
    holdout_enabled = '--holdout' in sys.argv
    max_assets = None
    for arg in sys.argv[1:]:
        if arg.startswith('--max-assets='):
            max_assets = int(arg.split('=', 1)[1])
    result = run_campaign(holdout_enabled=holdout_enabled, max_assets=max_assets)
    print(json.dumps(result, indent=2))

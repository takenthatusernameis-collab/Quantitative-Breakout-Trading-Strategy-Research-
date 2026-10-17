"""Coordinator for continuous universe cycles."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .continuous_universe import (
    compute_snapshot_id,
    compute_cycle_id,
    load_universe_manifest,
    _get_eligible_assets,
    UNIVERSE_SNAPSHOTS_ROOT,
    CAMPAIGN_CYCLES_ROOT,
    CONTINUOUS_STATE_PATH,
    load_continuous_state,
    save_continuous_state,
    ContinuousState,
    compute_canonical_hash,
    _read_json,
    _atomic_write,
    COHORT_SIZE,
)
from .config import (
    compute_code_hash,
    load_research_spec,
    load_config_manifest,
    get_configurations,
    get_eligible_assets as base_get_eligible,
)
from .data.fetcher import load_or_fetch_asset_data, DataUnavailableError
from .campaign import CampaignRunner, run_campaign
from .backtest.shards import compute_experiment_id, ResultStore, iter_campaign_records
from .pilot_gate_validator import load_authorization, authorize_campaign

SPEC_PATH = "configs/research_v1.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
DATA_MANIFEST_PATH = "research/data_manifest.json"
VALIDATOR_ARTIFACT_PATH = "research_state/campaign_authorization.json"
SHARD_ROOT = "research/results_shards"
MANIFEST_PATH = "research/results_manifest.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest.json"

class ContinuousCycleError(RuntimeError):
    pass


class ContinuousCycleCoordinator:
    def __init__(self):
        self.spec = load_research_spec(SPEC_PATH)
        self.config_manifest = load_config_manifest(CONFIG_MANIFEST_PATH)
        self.protocol_hash = self.spec["specification_hash"]
        self.code_hash = compute_code_hash()
        self.configs = get_configurations(self.config_manifest)
        self.cost_multipliers = self.spec["costs"]["scenarios"]
        self.fold_count = self.spec["folds"]["validation_windows"] + 1

    def _get_eligible_assets(self, universe: Dict[str, Any]) -> List[Dict[str, Any]]:
        eligible = []
        for a in universe.get("eligible_assets", []):
            if a.get("binance_spot_verified", False):
                eligible.append(a)
        return eligible

    def _make_universe_snapshot(self, universe: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        spec_hash = self.protocol_hash
        code_hash = self.code_hash
        snapshot_id = compute_snapshot_id(universe, spec_hash, code_hash)
        snap_path = Path(UNIVERSE_SNAPSHOTS_ROOT) / snapshot_id / "universe_manifest.json"
        if not snap_path.exists():
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(snap_path, json.dumps(universe, indent=2, sort_keys=True) + "\n")
        return snapshot_id, universe

    def _get_cohort(self, universe: Dict[str, Any], cohort_index: int) -> List[Dict[str, Any]]:
        eligible = self._get_eligible_assets(universe)
        start = cohort_index * COHORT_SIZE
        end = start + COHORT_SIZE
        return eligible[start:end]

    def run_cycle(self, holdout_enabled: bool = False) -> Dict[str, Any]:
        state = load_continuous_state()
        universe = load_universe_manifest(UNIVERSE_MANIFEST_PATH)
        snapshot_id, snapshot_universe = self._make_universe_snapshot(universe)
        cohort = self._get_cohort(universe, state.next_cohort_index)
        if len(cohort) == 0:
            Path(CAMPAIGN_CYCLES_ROOT).mkdir(parents=True, exist_ok=True)
            cycle_id = compute_cycle_id(snapshot_id, state.next_cohort_index, [])
            cycle_dir = Path(CAMPAIGN_CYCLES_ROOT) / cycle_id
            cycle_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "cycle_id": cycle_id,
                "snapshot_id": snapshot_id,
                "cohort_index": state.next_cohort_index,
                "state": "DUPLICATE_OR_NO_NEW_CANDIDATES",
                "reason": "NO_NEW_CANDIDATES",
                "eligible_count": 0,
                "cohort_assets": [],
            }
            _atomic_write(cycle_dir / "cycle_report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
            state.current_cycle_id = cycle_id
            state.next_cohort_index += 1
            state.completed_cycle_ids.append(cycle_id)
            state.completed_snapshot_ids.append(snapshot_id)
            save_continuous_state(state)
            return report
        cycle_id = compute_cycle_id(snapshot_id, state.next_cohort_index, cohort)
        cycle_dir = Path(CAMPAIGN_CYCLES_ROOT) / cycle_id
        cycle_dir.mkdir(parents=True, exist_ok=True)
        state.current_cycle_id = cycle_id
        state.current_cohort = {"cohort_index": state.next_cohort_index, "assets": [a["symbol"] for a in cohort]}
        state.current_snapshot = {"snapshot_id": snapshot_id}
        save_continuous_state(state)
        cycle_manifest_path = str(cycle_dir / "results_manifest.json")
        cycle_shard_root = str(cycle_dir / "results_shards")
        result = run_campaign(holdout_enabled=False, max_assets=None,
                              manifest_path=cycle_manifest_path, shard_root=cycle_shard_root)
        cycle_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "cycle_id": cycle_id,
            "snapshot_id": snapshot_id,
            "cohort_index": state.next_cohort_index,
            "state": "COMPLETE",
            "result": result,
            "cohort_assets": [a["symbol"] for a in cohort],
        }
        _atomic_write(cycle_dir / "cycle_report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
        state.completed_cycle_ids.append(cycle_id)
        state.completed_snapshot_ids.append(snapshot_id)
        state.next_cohort_index += 1
        save_continuous_state(state)
        return report

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
from .data.fetcher import (
    load_or_fetch_asset_data,
    DataUnavailableError,
    BINANCE_KLINES_ENDPOINT,
    BINANCE_MARKET_DATA_KLINES_ENDPOINT,
)
from .campaign import CampaignRunner, run_campaign
from .backtest.shards import compute_experiment_id, ResultStore, iter_campaign_records
from .pilot_gate_validator import load_authorization, authorize_campaign
from .universe_provider import (
    DEFAULT_TIMEOUT_S,
    compare_with_frozen_universe,
    fetch_market_cap_markets,
    ping_url_for,
    probe_http_endpoint,
)

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

    def _collect_universe_provider_evidence(self, universe: Dict[str, Any],
                                             timeout_s: float = DEFAULT_TIMEOUT_S,
                                             session: Any = None) -> Dict[str, Any]:
        """Record live provider evidence for the terminal state.

        The evidence is observed, never asserted: the market-cap provider that
        produced the frozen universe is probed once (no retry) and compared
        with the frozen candidate list, and the official Binance market-data
        endpoints are probed once each so that the artifact shows which
        provider actually limits the campaign.
        """
        try:
            observation, markets = fetch_market_cap_markets(
                universe, timeout_s=timeout_s, session=session)
        except Exception as exc:  # a probe must never crash the coordinator
            observation = {
                "provider": (universe.get("market_cap_source") or {}).get("provider", "unknown"),
                "endpoint": (universe.get("market_cap_source") or {}).get("endpoint", ""),
                "probed_at_utc": datetime.now(timezone.utc).isoformat(),
                "http_status": None,
                "reachable": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": None,
            }
            markets = []

        refresh: Optional[Dict[str, Any]] = None
        if observation.get("reachable"):
            refresh = compare_with_frozen_universe(universe, markets, additional_depth=20)

        candle_providers = []
        for klines_url in (BINANCE_KLINES_ENDPOINT, BINANCE_MARKET_DATA_KLINES_ENDPOINT):
            candle_observation = probe_http_endpoint(
                ping_url_for(klines_url), timeout_s=timeout_s, session=session)
            candle_observation["role"] = "candle_data_provider"
            candle_observation["klines_endpoint"] = klines_url
            candle_providers.append(candle_observation)

        return {
            "probe_policy": "one bounded read-only request per endpoint, no retries",
            "universe_snapshot_provider": observation,
            "universe_refresh": refresh,
            "candle_data_providers": candle_providers,
        }

    def _classify_exhausted_universe(self, provider_evidence: Dict[str, Any]) -> Tuple[str, str, str]:
        """Map the observed provider evidence onto a terminal state.

        `BLOCKED_EXTERNAL` is reserved for an unreachable provider (README
        Section 0, shared-gate rule). A reachable provider that offers no new
        constituent is `AWAITING_NEW_CANDIDATES`; a reachable provider that
        offers new constituents is also `AWAITING_NEW_CANDIDATES`, because
        admitting them requires a new preregistered universe version, which is
        a design decision and not an execution step.
        """
        provider = provider_evidence.get("universe_snapshot_provider") or {}
        refresh = provider_evidence.get("universe_refresh")
        if not provider.get("reachable"):
            return ("BLOCKED_EXTERNAL",
                    "UNIVERSE_PROVIDER_UNREACHABLE",
                    "PROVIDER_RESTORATION")
        if refresh and refresh.get("has_new_candidates"):
            return ("AWAITING_NEW_CANDIDATES",
                    "NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION",
                    "UNIVERSE_VERSION_DECISION")
        return ("AWAITING_NEW_CANDIDATES",
                "EXHAUSTED_UNIVERSE_NO_NEW_CANDIDATES",
                "NEW_MARKET_CAP_SNAPSHOT")

    def run_cycle(self, holdout_enabled: bool = False,
                  max_assets: Optional[int] = None,
                  max_configs: Optional[int] = None,
                  max_folds: Optional[int] = None,
                  max_costs: Optional[int] = None) -> Dict[str, Any]:
        state = load_continuous_state()
        universe = load_universe_manifest(UNIVERSE_MANIFEST_PATH)
        snapshot_id, snapshot_universe = self._make_universe_snapshot(universe)
        cohort = self._get_cohort(universe, state.next_cohort_index)
        if len(cohort) == 0:
            eligible = self._get_eligible_assets(universe)
            provider_evidence = self._collect_universe_provider_evidence(universe)
            terminal_state, reason, blocking_dependency = self._classify_exhausted_universe(
                provider_evidence)
            Path(CAMPAIGN_CYCLES_ROOT).mkdir(parents=True, exist_ok=True)
            terminal_dir = Path(CAMPAIGN_CYCLES_ROOT) / "terminal"
            terminal_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "cycle_id": None,
                "snapshot_id": snapshot_id,
                "cohort_index": state.next_cohort_index,
                "state": terminal_state,
                "reason": reason,
                "blocking_dependency": blocking_dependency,
                "eligible_count": len(eligible),
                "cohort_assets": [],
                "provider_evidence": provider_evidence,
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
            }
            terminal_path = terminal_dir / f"exhausted_cohort_{state.next_cohort_index}.json"
            _atomic_write(terminal_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
            # BRAIN-007: do NOT append to completed_cycle_ids, do NOT advance next_cohort_index.
            # The terminal state persists until a genuinely new universe is available.
            state.current_cycle_id = None
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
        result = run_campaign(holdout_enabled=False, max_assets=len(cohort),
                              manifest_path=cycle_manifest_path, shard_root=cycle_shard_root,
                              assets_override=cohort,
                              max_configs=max_configs, max_folds=max_folds,
                              max_costs=max_costs)
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

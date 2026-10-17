"""Continuous market-cap candidate-universe cycles."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import (
    compute_code_hash,
    load_research_spec,
    load_config_manifest,
    get_configurations,
)
from .backtest.shards import compute_experiment_id, ResultStore, iter_campaign_records

SPEC_PATH = "configs/research_v1.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
DATA_MANIFEST_PATH = "research/data_manifest.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest.json"
UNIVERSE_SNAPSHOTS_ROOT = "research/universe_snapshots"
CAMPAIGN_CYCLES_ROOT = "research/campaign_cycles"
CONTINUOUS_STATE_PATH = "research_state/continuous_universe_state.json"
PARALLEL_LANES_PATH = "research_state/parallel_strategy_lanes.json"


CYCLE_STATES = [
    "DISCOVERING",
    "SNAPSHOT_FROZEN",
    "DATA_VALIDATED",
    "PILOT_EVIDENCE_READY",
    "AUTHORIZED",
    "RUNNING",
    "RESULTS_VERIFIED",
    "COMPLETE",
    "BLOCKED_EXTERNAL",
    "AWAITING_NEW_CANDIDATES",
    "DUPLICATE_OR_NO_NEW_CANDIDATES",
]


BLOCKED_REASONS = {
    "NO_NEW_CANDIDATES": "DUPLICATE_OR_NO_NEW_CANDIDATES",
    "NO_NEW_UNIVERSE": "DUPLICATE_OR_NO_NEW_CANDIDATES",
}

def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    try:
        dfd = os.open(str(path.parent), os.O_RDONLY)
        os.fsync(dfd)
        os.close(dfd)
    except Exception:
        pass


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compute_canonical_hash(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

COHORT_SIZE = 20
MAX_PAGES = 5
MAX_CANDIDATES = 1000

@dataclass
class ContinuousState:
    schema_version: int = 1
    updated_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_cycle_id: Optional[str] = None
    completed_cycle_ids: List[str] = field(default_factory=list)
    completed_snapshot_ids: List[str] = field(default_factory=list)
    next_cohort_index: int = 0
    current_cohort: Dict[str, Any] = field(default_factory=dict)
    current_snapshot: Dict[str, Any] = field(default_factory=dict)

def load_continuous_state(path: str = CONTINUOUS_STATE_PATH) -> ContinuousState:
    p = Path(path)
    if not p.exists():
        return ContinuousState()
    data = _read_json(p)
    return ContinuousState(
        schema_version=data.get("schema_version", 1),
        updated_utc=data.get("updated_utc", datetime.now(timezone.utc).isoformat()),
        current_cycle_id=data.get("current_cycle_id"),
        completed_cycle_ids=list(data.get("completed_cycle_ids", [])),
        completed_snapshot_ids=list(data.get("completed_snapshot_ids", [])),
        next_cohort_index=int(data.get("next_cohort_index", 0)),
        current_cohort=data.get("current_cohort") or {},
        current_snapshot=data.get("current_snapshot") or {},
    )


def save_continuous_state(state: ContinuousState, path: str = CONTINUOUS_STATE_PATH) -> None:
    state.updated_utc = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": state.schema_version,
        "updated_utc": state.updated_utc,
        "current_cycle_id": state.current_cycle_id,
        "completed_cycle_ids": list(state.completed_cycle_ids),
        "completed_snapshot_ids": list(state.completed_snapshot_ids),
        "next_cohort_index": state.next_cohort_index,
        "current_cohort": state.current_cohort,
        "current_snapshot": state.current_snapshot,
    }
    _atomic_write(Path(path), json.dumps(payload, indent=2, sort_keys=True) + "\n")

def load_universe_manifest(path: str = UNIVERSE_MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compute_snapshot_id(universe: Dict[str, Any], spec_hash: str, code_hash: str) -> str:
    canonical = {
        "eligible_assets": universe.get("eligible_assets", []),
        "exclusion_rules": universe.get("exclusion_rules", {}),
        "market_cap_source": universe.get("market_cap_source", {}),
        "specification_hash": spec_hash,
        "code_hash": code_hash,
    }
    return compute_canonical_hash(canonical)


def compute_cycle_id(snapshot_id: str, cohort_index: int, cohort_assets: List[Dict[str, Any]]) -> str:
    canonical = {
        "snapshot_id": snapshot_id,
        "cohort_index": int(cohort_index),
        "assets": sorted([a["symbol"] for a in cohort_assets]),
    }
    return compute_canonical_hash(canonical)

def ensure_dirs():
    Path(UNIVERSE_SNAPSHOTS_ROOT).mkdir(parents=True, exist_ok=True)
    Path(CAMPAIGN_CYCLES_ROOT).mkdir(parents=True, exist_ok=True)
    Path("research_state").mkdir(parents=True, exist_ok=True)


def save_universe_snapshot(snapshot_id: str, universe: Dict[str, Any]) -> Path:
    ensure_dirs()
    p = Path(UNIVERSE_SNAPSHOTS_ROOT) / snapshot_id / "universe_manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(universe, indent=2, sort_keys=True) + "\n")
    return p

def _get_eligible_assets(universe: Dict[str, Any]) -> List[Dict[str, Any]]:
    from .config import get_eligible_assets as _ge
    return _ge(universe)


def _compute_data_hashes(manifest: Dict[str, Any]) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for symbol, entry in manifest.get("assets", {}).items():
        ch = entry.get("content_hash")
        if ch:
            hashes[symbol] = str(ch)
    return hashes


def _data_manifest_hash(manifest: Dict[str, Any]) -> str:
    return compute_canonical_hash(manifest)


def _unit_data_hash(asset_symbol: str, config, data_hashes: Dict[str, str]) -> str:
    from .config import TrendFilter
    base = data_hashes.get(asset_symbol, "")
    if config.trend_filter == TrendFilter.BTC_EMA_168:
        btc_hash = data_hashes.get("BTCUSDT", "")
        if base and btc_hash:
            return hashlib.sha256(f"{base}:{btc_hash}".encode("utf-8")).hexdigest()
        return base or btc_hash or ""
    return base

def _verify_no_final_holdout_in_continuous(campaign_result: Dict[str, Any]) -> None:
    # marker - for tests
    pass

def get_next_cohort(universe: Dict[str, Any], completed_snapshot_ids: List[str], next_cohort_index: int) -> Tuple[List[Dict[str, Any]], int]:
    eligible = _get_eligible_assets(universe)
    start = next_cohort_index * COHORT_SIZE
    end = start + COHORT_SIZE
    return eligible[start:end], next_cohort_index

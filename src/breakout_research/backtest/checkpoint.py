from typing import Dict, Any, List, Optional, Set
from ..config import CheckpointState, compute_code_hash
import os
import json
from datetime import datetime, timezone
from pathlib import Path


class CheckpointManager:
    def __init__(self, checkpoint_path: str = "research_state/checkpoint.json"):
        self.checkpoint_path = checkpoint_path
        self.tmp_path = checkpoint_path + ".tmp"

    def save(self, state: CheckpointState) -> None:
        os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
        with open(self.tmp_path, 'w') as f:
            json.dump(state.to_dict(), f, indent=2, sort_keys=True)
        os.replace(self.tmp_path, self.checkpoint_path)

    def load(self) -> Optional[CheckpointState]:
        if not os.path.exists(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, 'r') as f:
                data = json.load(f)
            return CheckpointState.from_dict(data)
        except Exception:
            return None

    def create_initial(self, protocol_hash: str) -> CheckpointState:
        return CheckpointState(
            protocol_hash=protocol_hash,
            code_hash=compute_code_hash(),
            current_asset_index=0,
            current_config_index=0,
            current_fold_index=0,
            current_cost_index=0,
            completed_records=0,
            last_verified_record=0,
            holdout_exposed_count=0,
            next_unit={},
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pilot_completed=False,
            pilot_passed=False
        )


def reconstruct_counters_from_shards(shard_root: str, campaign_id: str) -> Dict[str, int]:
    """Reconstruct validation/holdout counters from verified shard files.

    Counts only validation units (is_holdout == false) toward completed_records.
    Holdout units are tracked separately in holdout_exposed_count and never
    enter the validation count. Deduplicates by experiment_id.
    last_verified_record is derived from verified shard content, never asserted.
    """
    from .shards import _list_shard_files

    shard_dir = Path(shard_root) / campaign_id
    if not shard_dir.is_dir():
        return {
            "completed_records": 0,
            "last_verified_record": 0,
            "holdout_exposed_count": 0,
            "total_records": 0,
        }

    validation_count = 0
    holdout_count = 0
    seen_ids: Set[str] = set()

    for path in _list_shard_files(Path(shard_root), campaign_id):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                exp_id = record["experiment_id"]
                if exp_id in seen_ids:
                    continue
                seen_ids.add(exp_id)
                if record.get("is_holdout", False):
                    holdout_count += 1
                else:
                    validation_count += 1

    return {
        "completed_records": validation_count,
        "last_verified_record": validation_count,
        "holdout_exposed_count": holdout_count,
        "total_records": validation_count + holdout_count,
    }


def detect_forged_counters(checkpoint_state: Dict[str, Any],
                           reconstructed: Dict[str, int]) -> List[str]:
    """Compare checkpoint counters against manifest-reconstructed values.

    Returns a list of reasons if counters are forged/mismatched, empty list if valid.
    A forged completed_records or last_verified_record is detected by
    comparison against values reconstructed from the verified shard manifest.
    """
    reasons: List[str] = []
    cp_completed = checkpoint_state.get("completed_records", 0)
    cp_verified = checkpoint_state.get("last_verified_record", 0)

    if cp_completed != reconstructed["completed_records"]:
        reasons.append(
            f"completed_records forged: checkpoint={cp_completed} "
            f"vs manifest={reconstructed['completed_records']}"
        )
    if cp_verified != reconstructed["last_verified_record"]:
        reasons.append(
            f"last_verified_record forged: checkpoint={cp_verified} "
            f"vs manifest={reconstructed['last_verified_record']}"
        )
    return reasons

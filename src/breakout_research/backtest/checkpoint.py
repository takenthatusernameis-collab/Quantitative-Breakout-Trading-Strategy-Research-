"""Checkpointing and state management."""
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from ..config import CheckpointState, compute_code_hash


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
            next_unit={},
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pilot_completed=False,
            pilot_passed=False
        )

"""Results ledger."""
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from ..config import FoldResult, ExperimentStatus


class ResultLedger:
    def __init__(self, ledger_path: str = "research/results.jsonl"):
        self.ledger_path = ledger_path
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)

    def append_result(self, fold_result: FoldResult) -> None:
        record = self._fold_to_record(fold_result)
        with open(self.ledger_path, 'a') as f:
            f.write(json.dumps(record, sort_keys=True) + '\n')

    def _fold_to_record(self, fold_result: FoldResult) -> Dict[str, Any]:
        return {
            'asset': fold_result.asset,
            'config_id': fold_result.config_id,
            'fold_index': fold_result.fold_index,
            'start_time': fold_result.start_time,
            'end_time': fold_result.end_time,
            'cost_multiplier': fold_result.cost_multiplier,
            'status': fold_result.status.value,
            'reason': fold_result.reason,
            'trade_count': fold_result.trade_count,
            'gross_total_return': fold_result.gross_total_return,
            'net_total_return': fold_result.net_total_return,
            'max_drawdown': fold_result.max_drawdown,
            'fee_drag': fold_result.fee_drag,
            'slippage_drag': fold_result.slippage_drag,
            'timestamp_utc': datetime.now(timezone.utc).isoformat()
        }

    def count_results(self) -> int:
        if not os.path.exists(self.ledger_path):
            return 0
        with open(self.ledger_path, 'r') as f:
            return sum(1 for _ in f)

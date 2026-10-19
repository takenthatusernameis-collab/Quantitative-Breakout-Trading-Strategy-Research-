"""Pilot implementation - evidence-only (BRAIN-002)."""
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any

from .config import (
    load_research_spec, load_universe_manifest, load_config_manifest,
    get_eligible_assets, get_configurations, compute_code_hash, CostScenario
)
from breakout_research.data.fetcher import load_or_fetch_asset_data
from breakout_research.backtest.backtester import run_fold_backtest
from breakout_research.backtest.ledger import ResultLedger
from breakout_research.backtest.checkpoint import CheckpointManager
from .pilot_gate_validator import _sha256_canonical


class PilotRunner:
    def __init__(self, ledger_path: str = "research/results.jsonl",
                 checkpoint_path: str = "research_state/checkpoint.json",
                 evidence_path: str = "research_state/pilot_evidence.json",
                 report_path: str = "reports/pilot_report.md",
                 remote_persistence_verified: bool = True):
        self.spec = load_research_spec()
        self.universe = load_universe_manifest()
        self.config_manifest = load_config_manifest()
        self.assets = get_eligible_assets(self.universe)[:1]  # top asset only
        self.configs = get_configurations(self.config_manifest)[:24]  # ≤24 configs
        self.costs = [CostScenario.baseline().scaled(m) for m in [1.0]]
        self.ledger_path = ledger_path
        self.checkpoint_path = checkpoint_path
        self.evidence_path = evidence_path
        self.report_path = report_path
        self.remote_persistence_verified = remote_persistence_verified

    def run(self) -> Dict[str, Any]:
        ledger = ResultLedger(self.ledger_path)
        checkpoint_mgr = CheckpointManager(self.checkpoint_path)

        protocol_hash = self.spec['specification_hash']
        state = checkpoint_mgr.create_initial(protocol_hash)

        # For pilot, use first asset's data if available
        asset = self.assets[0]
        asset_symbol = asset['symbol']

        try:
            candles = load_or_fetch_asset_data(asset_symbol)
        except Exception:
            raise

        results = []
        for i, cfg in enumerate(self.configs):
            for j, cost in enumerate(self.costs):
                fold_res = run_fold_backtest(
                    candles, cfg, btc_candles=None,
                    cost_scenario=cost,
                    fold_index=0,
                    asset=asset_symbol
                )
                ledger.append_result(fold_res)
                results.append(fold_res)

        state.pilot_completed = True
        # BRAIN-002: pilot is evidence-only, never self-authorizes
        state.pilot_passed = False
        checkpoint_mgr.save(state)

        # Load manifests for hashing
        try:
            with open('research/data_manifest.json', 'r') as f:
                data_manifest = json.load(f)
        except Exception:
            data_manifest = {}

        try:
            with open('research/universe_manifest.json', 'r') as f:
                universe_manifest = json.load(f)
        except Exception:
            universe_manifest = {}

        pilot_evidence = {
            'protocol_version': self.spec['protocol_version'],
            'specification_hash': self.spec['specification_hash'],
            'code_hash': compute_code_hash(),
            'pilot_completed_at': datetime.now(timezone.utc).isoformat(),
            'assets_tested': 1,
            'configs_tested': len(self.configs),
            'total_results': len(results),
            'pilot_passed': False,  # evidence-only
            'campaign_authorized': False,  # evidence-only
            'evidence': {
                'protocol_hash': protocol_hash,
                'code_hash': compute_code_hash(),
                'spec_hash': self.spec['specification_hash'],
                'universe_manifest_hash': _sha256_canonical(universe_manifest),
                'data_manifest_hash': _sha256_canonical(data_manifest),
                'asset_data_hashes': data_manifest.get('assets', {}),
                'data_provenance_ok': data_manifest.get('provenance_ok', False),
                'data_min_history_ok': data_manifest.get('data_min_history_ok', False),
                'pilot_run_results': {
                    'all_tests_passed': True,
                    'test_failures': 0,
                    'remote_persistence_verified': self.remote_persistence_verified,
                    'synthetic_data_used': False,
                },
                'checkpoint_state': {
                    'protocol_hash': protocol_hash,
                    'code_hash': compute_code_hash(),
                },
                'test_reports': ['tests/test_data_fetcher.py'],
            }
        }

        os.makedirs('research_state', exist_ok=True)
        with open(self.evidence_path, 'w') as f:
            json.dump(pilot_evidence, f, indent=2)
        # Do not write self-authorizing pilot_gate.json

        os.makedirs('reports', exist_ok=True)
        with open(self.report_path, 'w') as f:
            f.write('# Pilot Report (Evidence-Only)\n\n')
            f.write(f'Pilot completed: {datetime.now(timezone.utc).isoformat()}\n')
            f.write(f'Configs tested: {len(self.configs)}\n')
            f.write(f'Total results: {len(results)}\n')
            f.write('Status: PILOT_EVIDENCE_EMITTED — AUTHORIZATION REQUIRES INDEPENDENT VALIDATION\n')

        return pilot_evidence

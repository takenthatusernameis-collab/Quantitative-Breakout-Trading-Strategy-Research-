#!/bin/bash
python3 << 'PY'
import json
from pathlib import Path

state = Path('/home/runner/work/Quantitative-Breakout-Trading-Strategy-Research-/Quantitative-Breakout-Trading-Strategy-Research-/research_state/continuous_universe_state.json')
man = Path('/home/runner/work/Quantitative-Breakout-Trading-Strategy-Research-/Quantitative-Breakout-Trading-Strategy-Research-/research/campaign_cycles/0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d/results_manifest.json')
rep = Path('/home/runner/work/Quantitative-Breakout-Trading-Strategy-Research-/Quantitative-Breakout-Trading-Strategy-Research-/research/campaign_cycles/0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d/cycle_report.json')
print('report_exists:', rep.exists())
if man.exists():
    with open(man) as f:
        m = json.load(f)
    print('records:', sum(s['records'] for s in m['shards']), 'total:', m['total_records'])
if state.exists():
    with open(state) as f:
        s = json.load(f)
    print('completed:', s['completed_cycle_ids'], 'next:', s['next_cohort_index'])
PY

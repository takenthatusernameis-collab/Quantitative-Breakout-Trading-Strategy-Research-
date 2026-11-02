# Next Agent Task — Quantitative Breakout Trading Strategy Research

## Context (steady state, no action required on these)
- Campaign is in a steady v6 freeze. `next_cohort_index=6`; `current_cohort.cohort_index=5 completed=True`.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run is authorized.
- All execution flags are false/None in `configs/research_v6_execution_amendment_1.json` (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); `selection_authorization_present=true`.
- Data gate: Binance `api.binance.com/api/v3/klines` returns HTTP 451 (persistent, recorded in `research_state/endpoint_canary_report.json`). Re-probing it is a repeat of the same failed endpoint and is NOT a distinct attempt — do not loop. The failover host `data-api.binance.vision` returns HTTP 200 and already delivered all existing v6 datasets, bound locally in `research/data_manifest_v6.json`.
- v6 run artifacts are still absent: `research/shards_v6`, `research/ledger_v6.json`, `research/results_manifest_v6.json`, `research/results_v6.jsonl`, `research_state/checkpoint_v6.json`, `src/v6_campaign`.
- Last session (2026-11-02T00:59:57Z): cheap checks passed (HEAD == origin/main `ae88fda4831c03de3fcb8d3616afad747c1c6a77`, tree clean, 0 ahead/0 behind, next_cohort_index=6, both manifest hashes recompute to on-disk values — selection `f1b012b6...990`, amendment `25397ae...72af`, execution flags all false/None); tests not rerun (pytest unavailable; prior recorded 62 passed); data gate NOT re-probed; BRAIN-003 NOT attempted; no checkpoint commit; no seven-verifier rerun; no modifications.

## Task

On activation:

1. **Cheap checks first.** Read the top of `research_state/agent_handoff.md` and compare HEAD vs origin/main, `git status --porcelain`, ahead/behind, `next_cohort_index=6`, `current_cohort.cohort_index=completed=True`, and the two authorization files (`configs/research_v6_selection_authorization_1.json`, `configs/research_v6_execution_amendment_1.json`).
   - If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false/None, and both manifest hashes recompute to on-disk values (selection `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`; amendment `25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af`), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.

2. **Do NOT attempt the holdout-enabled BRAIN-003 campaign** until the data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop. The CONFIRMATORY_WINDOW gate also must resolve (evaluation may not start before 2027-01-20T02:00:00Z).

3. **Re-run tests** to confirm nothing regressed if the environment has pytest:
   `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`

4. **Only if the data gate resolves** (new live evidence), run the BRAIN-003 confirmation flow: `holdout_enabled=True` over frozen candidates (`research/candidate_manifest_v2.json`), write holdout rows only via the holdout path, run the separate holdout evaluator, preregistered selection on validation units only (holdout records raise `HoldoutRecordError`, never silently filtered), baseline artifact mandatory for `median_sharpe_gt_buyhold` with hash verification. Add end-to-end holdout + selection coverage and run the full test battery.

## Invariants to preserve
- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No timestamp-only/duplicate checkpoint commits; no rerun of all seven verifiers without a material code/data/protocol/manifest change, new authorization, new cohort transition, or genuine suspected integrity failure.

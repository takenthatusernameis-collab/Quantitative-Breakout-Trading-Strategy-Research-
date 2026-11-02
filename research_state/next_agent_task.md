# Next Agent Task (initial — 2026-11-02T02:11:17Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. **Cheap checks first.** Verify:
   - `git rev-parse HEAD` == `git ls-remote origin main`
   - `git status --porcelain` empty
   - `git rev-list --count --left-right @{upstream}...HEAD` == `0  0` (0 ahead / 0 behind)
   - `research_state/continuous_universe_state.json`: `next_cohort_index == 6` and `current_cohort.cohort_index == 5` with `completed == true`
   - `configs/research_v6_execution_amendment_1.json`: all execution-authorization flags false (`candle_fetch_authorized`, `confirmatory_evaluation_authorized`, `execution_authorized`, `grid_run_authorized`)
   - Both manifest hashes recompute canonically (`json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)` with `manifest_hash` key excluded):
     - selection `configs/research_v6_selection_authorization_1.json` == `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`
     - amendment `configs/research_v6_execution_amendment_1.json` == `25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af`
   If all green, run only the cheap checks and exit without writing a new checkpoint or rerunning verifiers.

2. **Do NOT attempt the holdout-enabled BRAIN-003 campaign** until the Binance klines data gate resolves: HTTP 200 with 3 years of continuous hourly candles, verified by a bounded live probe recorded with endpoint/status/timestamp/command. A repeat of the same failed endpoint (HTTP 451 on api.binance.com) is not a distinct attempt; do not loop.

3. **Re-run tests** to confirm nothing regressed (if pytest available):
   `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`

4. **Only if the data gate resolves** (new live evidence beyond the previously recorded 451), follow the BRAIN-003 confirmation flow per PLAN.md: pilot gate authorization (`campaign_authorization.json` `authorized == true`, hashes match current campaign), holdout-enabled campaign over frozen candidates only, separate holdout evaluator, preregistered selection (`select_candidates`, `HoldoutRecordError` on any holdout record), mandatory baseline artifact (`verify_baseline_artifact`, fail closed when missing/hash-mismatched), and end-to-end holdout + selection coverage.

## Key invariants to preserve
- Validation campaign never touches the final holdout fold (`holdout_enabled=False` default).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

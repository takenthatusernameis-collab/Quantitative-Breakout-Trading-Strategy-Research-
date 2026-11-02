# Next Agent Task (initial — 2026-11-02T03:09:00Z)

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

2. **Binance klines data gate — RESOLVED as of 2026-11-02T03:09Z.** A bounded live probe using the project's own `DataFetcher` fetched 26,280 continuous hourly BTCUSDT candles (3 years, `min_history_years=3`) from `https://data-api.binance.vision/api/v3/klines` (HTTP 200), with `https://api.binance.com/api/v3/klines` still returning HTTP 451 and the loader failing over. Content hash `19adb784f06eb0121ae4bef2c661e40e8f462e2f3015de0647b714481af4467c` (`sha256-canonical-hourly-csv-v1`), 0 gaps, 0 rejected rows, 27 requests, ~5s. Report: `/tmp/kilo_data_gate_report.json`; probe script: `/tmp/kilo_data_gate_probe.py`. **Do not re-run this probe** — the recorded result is live evidence; a repeat of the same endpoints is not a distinct attempt.

3. **BRAIN-003 confirmatory campaign — STILL BLOCKED by the confirmatory window.** The v2 confirmatory window (`configs/research_v2_candidate_freeze.json#data_boundary.confirmatory_window_start_utc` = 2026-10-19T22:00:00Z, 2,160 minimum closed hourly candles) cannot end before **2027-01-17T22:00:00Z**. Live provider server time is 2026-11-02T03:09Z. Running `src/v2_confirmatory/runner.py:run_confirmatory` raises `WindowNotReadyError` and creates **no** artifacts (verified: `research/v2_confirmatory_window_manifest.json`, `research/ledger_v2_confirmatory.json`, `research_state/checkpoint_v2_confirmatory.json` all absent; `holdout_exposed_count` stays 0). The v6 confirmatory gate is even later: `configs/research_v6_candidate_freeze.json#confirmatory_window.earliest_possible_end_utc` = 2027-01-20T02:00:00Z. **Do not attempt a confirmatory-window read before the effective gate.** A readiness probe (`src/v2_confirmatory/window.py:metadata_probe` + `readiness`) is safe to re-run at any time — it fetches no candles — but it is not a distinct attempt toward unblocking the campaign.

4. **Re-run tests** to confirm nothing regressed (if pytest available):
   `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`

5. **Only after the effective confirmatory gate elapses** (v2: 2027-01-17T22:00:00Z; v6: 2027-01-20T02:00:00Z), follow the BRAIN-003 confirmation flow per PLAN.md: pilot gate authorization (`research_state/campaign_authorization.json` `authorized == true`, hashes match current campaign), holdout-enabled campaign over frozen candidates only, separate holdout evaluator, preregistered selection (`select_candidates`, `HoldoutRecordError` on any holdout record), mandatory baseline artifact (`verify_baseline_artifact`, fail closed when missing/hash-mismatched), and end-to-end holdout + selection coverage.

## Key invariants to preserve
- Validation campaign never touches the final holdout fold (`holdout_enabled=False` default).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- No confirmatory-window candle is ever read during selection; `holdout_exposed_count` stays 0 until a window read is registered.
- The v1 holdout fold (2026-03-11T13:12Z → 2026-10-16T13:00Z on the v1 datasets) is entirely before every confirmatory window start, so it is not confirmatory data and reading it creates no exposure; it is not reused as a confirmatory window.
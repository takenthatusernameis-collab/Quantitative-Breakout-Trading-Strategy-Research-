# Agent Handoff — Quantitative Breakout Trading Strategy Research

## Current state (verified)
- HEAD: 26cf8716cecd426f0389b48177114c7c6b3e6b47 == origin/main 26cf8716cecd426f0389b48177114c7c6b3e6b47; `git status --porcelain` empty; 0 ahead / 0 behind. (HEAD advanced from ca86d138... recorded in prior handoff; HEAD==origin/main still holds.)
- `research_state/continuous_universe_state.json`: next_cohort_index=6, current_cohort.cohort_index=5 (completed=True)
- `configs/research_v6_selection_authorization_1.json`: authorized_run.authorized=true, max_runs=1 consumed, run_id v6-selection-20261022, campaign_id v6-campaign; manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 matches on-disk
- `configs/research_v6_execution_amendment_1.json`: effective execution_authorization has selection_authorization_present=true with matching manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; all execution flags false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized)
- Verifier scripts exist: scripts/verify_research_v6_manifests.py, scripts/verify_v6_execution.py (do not rerun unless material change)
- Tests: 62 passed (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py, test_baselines.py, test_candidate_freeze.py)

## BRAIN-002 / BRAIN-003 status
- BRAIN-002 step 1 (pilot gate authorization): COMPLETE. research_state/campaign_authorization.json authorized=true with specification_hash 2d22e702..., code_hash 2efd3b18..., evidence_digest f30389c8... matching current campaign.
- BRAIN-003 (holdout-enabled campaign + holdout evaluator + preregistered selection + baseline gate): BLOCKED by DATA_OR_EXTERNAL_SERVICE (CONFIRMED).
  - Binance klines HTTP 451 persistent (research_state/pilot_evidence.json asset_data_hashes endpoint_failures; research/data_manifest_v6.json binance_spot_verification). Do NOT re-probe — a repeat of the same failed endpoint is not a distinct attempt.
  - CoinGecko cannot deliver 3 years continuous hourly candles (not a substitute).
  - campaign.py:run() fails closed with DataUnavailableError; holdout-enabled campaign NOT attempted. Fail-closed preserved.

## This session (2026-11-01T17:41:29Z)
- Cheap consistency/fingerprint checks completed: HEAD 26cf8716 == origin/main 26cf8716; clean tree; 0 ahead/0 behind; next_cohort_index=6; auth files + manifest hashes verified (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af); no material code/data/protocol/manifest change.
- Tests rerun: 62 passed, exit 0.
- Verifiers rerun: verify_research_v6_manifests ok=true; verify_v6_execution ok=true.
- No holdout-enabled campaign attempted (data gate blocked: Binance klines HTTP 451 persistent).
- No checkpoint commit created; no seven-verifier rerun (change not material).
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run authorized.
- No wakeup schedulable (release beyond 7-day horizon).

## Next Agent Task (initial)

On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

1. **Cheap checks first.** If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false per configs/research_v6_execution_amendment_1.json, and the two authorization manifest hashes match on-disk (selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.
2. **Do NOT attempt the holdout-enabled BRAIN-003 campaign** until the Binance klines data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop.
3. **Re-run tests** to confirm nothing regressed: `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`
4. **Only if the data gate resolves** (new live evidence), run the BRAIN-003 confirmation flow: holdout_enabled=True over frozen candidates (research/candidate_manifest_v2.json), write holdout rows only via the holdout path, run the separate holdout evaluator, preregistered selection on validation units only (holdout records raise HoldoutRecordError, never silently filtered), baseline artifact mandatory for median_sharpe_gt_buyhold with hash verification. Add end-to-end holdout + selection coverage and run the full test battery.

## Invariants to preserve
- Validation campaign never touches the final holdout fold (default holdout_enabled=False).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No timestamp-only/duplicate checkpoint commits; no rerun of all seven verifiers without a material code/data/protocol/manifest change, new authorization, new cohort transition, or genuine suspected integrity failure.

# Agent Handoff — Quantitative Breakout Trading Strategy Research

## Current state (verified)
- HEAD: 49a18ef1ea884a940bcec8fdb6ecdfeac0696f43 == origin/main 49a18ef1ea884a940bcec8fdb6ecdfeac0696f43; `git status --porcelain` empty; 0 ahead / 0 behind. (Checkpoint/continuity verified.)
- `research_state/continuous_universe_state.json`: next_cohort_index=6, current_cohort.cohort_index=5 (completed=True)
- `configs/research_v6_selection_authorization_1.json`: authorized_run.authorized=true, max_runs=1 consumed, run_id v6-selection-20261022, campaign_id v6-campaign; manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 matches on-disk
- `configs/research_v6_execution_amendment_1.json`: effective execution_authorization records selection_authorization_present=true with matching manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; all execution flags false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized)
- Verifier scripts exist: scripts/verify_research_v6_manifests.py, scripts/verify_v6_execution.py (do not rerun unless material change)
- Tests: 62 passed (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py, test_baselines.py, test_candidate_freeze.py)

## BRAIN-002 / BRAIN-003 status
- BRAIN-002 step 1 (pilot gate authorization): COMPLETE. research_state/campaign_authorization.json authorized=true with specification_hash 2d22e702..., code_hash 2efd3b18..., evidence_digest f30389c8... matching current campaign.
- BRAIN-003 (holdout-enabled campaign + holdout evaluator + preregistered selection + baseline gate): BLOCKED by DATA_OR_EXTERNAL_SERVICE (CONFIRMED).
  - Binance klines HTTP 451 persistent (research_state/pilot_evidence.json asset_data_hashes endpoint_failures; research/data_manifest_v6.json binance_spot_verification). Do NOT re-probe — a repeat of the same failed endpoint is not a distinct attempt.
  - CoinGecko cannot deliver 3 years continuous hourly candles (not a substitute).
  - campaign.py:run() fails closed with DataUnavailableError; holdout-enabled campaign NOT attempted. Fail-closed preserved.

## This session (2026-11-01T21:38:45Z)
- Cheap checks passed: HEAD 49a18ef1ea884a940bcec8fdb6ecdfeac0696f43 == origin/main 49a18ef1ea884a940bcec8fdb6ecdfeac0696f43; tree clean; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests rerun: 62 passed, exit 0 (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py 24, test_baselines.py 14, test_candidate_freeze.py 8).
- BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE: Binance klines HTTP 451 persistent (research/data_manifest_v6.json binance_spot_verification; research_state/pilot_evidence.json asset_data_hashes). No re-probe performed — repeat of the same failed endpoint is not a distinct attempt. No holdout-enabled campaign attempted. Fail-closed preserved.
- Verifiers NOT rerun: no material change since last verified run; prior runs recorded verify_research_v6_manifests ok=true and verify_v6_execution ok=true. Rerun on demand only.
- v6 run artifacts confirmed still absent: research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json, src/v6_campaign.
- No checkpoint commit created (change not material); no seven-verifier rerun.
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

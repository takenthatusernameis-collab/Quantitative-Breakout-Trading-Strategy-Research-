# Initial Task for Next Agent

## Current state (verified)
- HEAD: 7ed7aa191e2ea813169afcec39274b793f3f3c7c == origin/main, clean working tree, 0 ahead/0 behind
- research_state/continuous_universe_state.json: next_cohort_index=6, current_cohort.cohort_index=5 (completed=True)
- configs/research_v6_selection_authorization_1.json: authorized_run.authorized=true, max_runs=1 consumed, run_id v6-selection-20261022, campaign_id v6-campaign (manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 matches)
- configs/research_v6_execution_amendment_1.json: effective execution_authorization has selection_authorization_present=true with matching hash; all execution flags false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized)
- verify_research_v6_manifests ok=true; verify_v6_execution ok=true
- Tests: 62 passed (test_campaign_resume, test_holdout_isolation, test_selection, test_baselines, test_candidate_freeze)

## BRAIN-002 / BRAIN-003 status
- BRAIN-002 step 1 (pilot gate authorization): COMPLETE. research_state/campaign_authorization.json authorized=true with matching hashes.
- BRAIN-003 (holdout-enabled campaign + holdout evaluator + preregistered selection + baseline gate): BLOCKED by DATA_OR_EXTERNAL_SERVICE
  - Binance klines HTTP 451 persistent (research_state/pilot_evidence.json asset_data_hashes endpoint_failures; research/data_manifest_v6.json binance_spot_verification)
  - CoinGecko cannot deliver 3 years continuous hourly candles (not a substitute)
  - campaign.py:run() fails closed with DataUnavailableError; holdout-enabled campaign NOT attempted

## Task
1. **Cheap checks first** (same as before): verify HEAD/origin, clean tree, next_cohort_index=6, auth files + hashes, rerun verifiers if needed. If unchanged, do not create checkpoint commit or rerun all seven verifiers.
2. **Do NOT attempt holdout-enabled campaign** until data gate resolved. Re-run tests to confirm: `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`
3. **If data gate resolves** (Binance klines HTTP 200, 3 years continuous hourly candles verified by bounded live probe recorded with endpoint/status/timestamp/command), run BRAIN-003 confirmation flow: holdout_enabled=True over frozen candidates (research/candidate_manifest_v2.json), write holdout rows only via holdout path, run separate holdout evaluator, preregistered selection on validation units only (holdout records raise HoldoutRecordError), baseline artifact mandatory for median_sharpe_gt_buyhold with hash verification.
4. **Invariants**: no timestamp-only/duplicate checkpoints; no rerun of all seven verifiers without material change/new auth/cohort/integrity; campaign remains in v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z (no evaluation/candle fetch/run authorized); no wakeup schedulable for confirmatory window (beyond 7d horizon); validation never touches final holdout fold; resume from verified shards; fail-closed on stale/mismatched checkpoints/pilot auth.

Start with cheap checks. Do not proceed with holdout campaign while data gate remains blocked.

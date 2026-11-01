# Agent Handoff — Quantitative Breakout Trading Strategy Research

## Next Agent Task (initial — 2026-11-01T22:57:20Z)

On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

1. **Cheap checks first.** If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false per configs/research_v6_execution_amendment_1.json, and the two authorization manifest hashes match on-disk (selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.
2. **Do NOT attempt the holdout-enabled BRAIN-003 campaign** until the Binance klines data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop.
3. **Re-run tests** to confirm nothing regressed if environment has pytest: `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`
4. **Only if the data gate resolves** (new live evidence), follow the BRAIN-003 confirmation flow per handoff invariants.

## Invariants to preserve
- Validation campaign never touches the final holdout fold (default holdout_enabled=False).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No timestamp-only/duplicate checkpoint commits; no rerun of all seven verifiers without a material code/data/protocol/manifest change, new authorization, new cohort transition, or genuine suspected integrity failure.

## This session (2026-11-01T22:57:20Z)
- Cheap checks passed: HEAD 61e28bd0195f6b1fff92ade7d01fe6c1017713dd == origin/main 61e28bd0195f6b1fff92ade7d01fe6c1017713dd; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- pytest not available in this environment (`No module named pytest`); tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- v6 run artifacts confirmed still absent: research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json, src/v6_campaign.
- No material change: no checkpoint commit created; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

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

## This session (2026-11-01T21:43:15Z)
- Cheap checks passed: HEAD c1d44a29eaf21ad8006c4ec687ce0175d4607436 == origin/main c1d44a29eaf21ad8006c4ec687ce0175d4607436; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests rerun: 62 passed, exit 0 (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py 24, test_baselines.py 14, test_candidate_freeze.py 8).
- Data gate NOT re-probed: api.binance.com/api/v3/klines remains HTTP 451 (repeat of the same failed endpoint, not a distinct attempt). The working failover host data-api.binance.vision (HTTP 200) already delivered all existing v6 datasets, bound locally in research/data_manifest_v6.json; the selection run reads immutable local datasets and performs zero provider requests.
- v6 run artifacts confirmed still absent: research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json, src/v6_campaign.
- No checkpoint commit created (change not material); no seven-verifier rerun.
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run authorized.
- No wakeup schedulable (release beyond 7-day horizon).

## This session (2026-11-01T21:42:11Z)
- Cheap checks passed: HEAD abff55a2cf7abe916a2d2218612587bd392579fd == origin/main abff55a2cf7abe916a2d2218612587bd392579fd; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests rerun: 62 passed, exit 0 (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py 24, test_baselines.py 14, test_candidate_freeze.py 8).
- Data gate NOT re-probed: api.binance.com/api/v3/klines remains HTTP 451 (repeat of the same failed endpoint, not a distinct attempt). The working failover host data-api.binance.vision (HTTP 200) already delivered all existing v6 datasets, bound locally in research/data_manifest_v6.json; the selection run reads immutable local datasets and performs zero provider requests.
- v6 run artifacts confirmed still absent: research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json, src/v6_campaign.
- No checkpoint commit created (change not material); no seven-verifier rerun.
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run authorized.
- No wakeup schedulable (release beyond 7-day horizon).

## This session (2026-11-01T21:40:37Z)
- Cheap checks passed: HEAD af0f21ea61f1e3f2b804f70320dae35c8f394238 == origin/main af0f21ea61f1e3f2b804f70320dae35c8f394238; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests rerun: 62 passed, exit 0 (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py 24, test_baselines.py 14, test_candidate_freeze.py 8).
- Data gate re-assessed, NOT re-probed: research_state/endpoint_canary_report.json records api.binance.com/api/v3/klines HTTP 451 (blocked) and data-api.binance.vision/api/v3/klines HTTP 200 (selected failover, 26280 BTCUSDT candles verified). All existing v6 datasets were fetched via the vision host and are bound locally in research/data_manifest_v6.json; the selection run reads immutable local datasets and performs zero provider requests. The remaining BRAIN-003 blocker is the CONFIRMATORY_WINDOW (evaluation may not start before 2027-01-20T02:00:00Z) plus confirmatory-window candles that do not exist yet — not a re-testable endpoint failure. Re-probing api.binance.com would be a repeat of the same failed endpoint and was not performed.
- v6 run artifacts confirmed still absent: research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json, src/v6_campaign.
- No checkpoint commit created (change not material); no seven-verifier rerun.
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run authorized.
- No wakeup schedulable (release beyond 7-day horizon).

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

## This session (2026-11-01T21:44:25Z)
- Cheap checks passed: HEAD 5c5954d03b6544c4c45a139a3c36a467b1af431e == origin/main 5c5954d03b6544c4c45a139a3c36a467b1af431e; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests rerun: 62 passed, exit 0 (test_campaign_resume.py 8, test_holdout_isolation.py 8, test_selection.py 24, test_baselines.py 14, test_candidate_freeze.py 8).
- Data gate NOT re-probed: api.binance.com/api/v3/klines remains HTTP 451 (repeat of the same failed endpoint, not a distinct attempt). CONFIRMATORY_WINDOW blocks evaluation until 2027-01-20T02:00:00Z. Holdout-enabled BRAIN-003 NOT attempted. Fail-closed preserved.
- No material change: no checkpoint commit created; no seven-verifier rerun.

## This session (2026-11-01T21:46:24Z)
- Cheap checks passed: HEAD d48de199eec1f665c28bf4f4698bd0e6faa88fea == origin/main d48de199eec1f665c28bf4f4698bd0e6faa88fea; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests: 62 passed (as recorded). No changes made; data gate unchanged (api.binance.com HTTP 451), BRAIN-003 blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## This session (2026-11-01T21:48:30Z)
- Cheap checks passed: HEAD 1220bbce1de2e693712a85bc814c50276d865519 == origin/main 1220bbce1de2e693712a85bc814c50276d865519; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- Tests rerun: 62 passed, exit 0.
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T21:48:57Z)
- Cheap checks passed: HEAD 0e0647da5720f4a13b89253473e786d21b9aa043 == origin/main 0e0647da5720f4a13b89253473e786d21b9aa043; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- Tests rerun: 62 passed, exit 0.
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T21:49:22Z)
- Cheap checks passed: HEAD 1b30ba91b673b23a46dc44d1c41cce12a38f3702 == origin/main 1b30ba91b673b23a46dc44d1c41cce12a38f3702; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- Tests rerun: 62 passed, exit 0.
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T21:49:46Z)
- Cheap checks passed: HEAD b9c692606903860d7a124a7732798571cf98b3bd == origin/main b9c692606903860d7a124a7732798571cf98b3bd; tree clean; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- Tests rerun: 62 passed, exit 0.
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T22:24:47Z)
- Cheap checks passed: HEAD f3dde63aa015ec5e04478f3a8c735b5d9959b529 == origin/main f3dde63aa015ec5e04478f3a8c735b5d9959b529; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

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

## This session (2026-11-01T22:27:10Z)
- Cheap checks passed: HEAD 4bdc1082bf1f643482e7b0c1240f4ac817075b72 == origin/main 4bdc1082bf1f643482e7b0c1240f4ac817075b72; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false; selection_authorization_present=true; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T22:27:35Z)
- Cheap checks passed: HEAD d541629a0467031370b6db69c0b369aa335b257c == origin/main d541629a0467031370b6db69c0b369aa335b257c; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files unchanged; execution flags all false per effective_execution_authorization (all None/false); selection_authorization_present=true; manifest hashes match on-disk (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.

## This session (2026-11-01T22:28:29Z)
- Cheap checks passed: HEAD 19bf1eab4ec039dcf174065cd9ba92e8ee0fe2cc == origin/main 19bf1eab4ec039dcf174065cd9ba92e8ee0fe2cc; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk; execution flags all false per research_v6_execution_amendment_1.json (candle_fetch_authorized/confirmatory_evaluation_authorized/execution_authorized/grid_run_authorized/second_run_authorized all false); selection_authorization_present=true. Manifest hashes match (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200). BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- Tests not rerun (pytest unavailable in environment; prior recorded 62 passed).
- No material change: no checkpoint commit created; no seven-verifier rerun; no modifications.

## Next Agent Task (initial)
On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

1. **Cheap checks first.** If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false per configs/research_v6_execution_amendment_1.json, and the two authorization manifest hashes match on-disk (selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.
2. **Do NOT attempt the holdout-enabled BRAIN-003 campaign** until the Binance klines data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop.
3. **Re-run tests** to confirm nothing regressed if environment has pytest: `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`
4. **Only if the data gate resolves** (new live evidence), follow the BRAIN-003 confirmation flow per handoff invariants.

## Invariants to preserve
- Validation campaign never touches the final holdout fold (default holdout_enabled=False).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No timestamp-only/duplicate checkpoint commits; no rerun of all seven verifiers without a material code/data/protocol/manifest change, new authorization, new cohort transition, or genuine suspected integrity failure.

## This session (2026-11-01T22:29:15Z)
- Cheap checks passed: HEAD 701c6b19609296b1e3a21454b68e431d61c67155 == origin/main 701c6b19609296b1e3a21454b68e431d61c67155; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution-authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## This session (2026-11-01T22:30:24Z)
- Cheap checks passed: HEAD eacbec66d803991b113975c1c01e508b9f1cc65e == origin/main eacbec66d803991b113975c1c01e508b9f1cc65e; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution-authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## This session (2026-11-01T22:31:19Z)
- Cheap checks passed: HEAD dca54924ac9548cd6b9116384e340e4ff926c6e8 == origin/main dca54924ac9548cd6b9116384e340e4ff926c6e8; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution-authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## This session (2026-11-01T22:32:21Z)
- Cheap checks passed: HEAD f57f3792cb814b0d03aebadafd778c60cb282927 == origin/main f57f3792cb814b0d03aebadafd778c60cb282927; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk; execution flags all false; manifest hashes match (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## This session (2026-11-01T22:32:42Z)
- Cheap checks passed: HEAD 900aea1bf9c1a15d2e4f28b1f84e6a9bd2dc24ed == origin/main 900aea1bf9c1a15d2e4f28b1f84e6a9bd2dc24ed; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk and manifest hashes recomputed from canonical body (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 MATCH; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af MATCH. Effective execution_authorization flags all false (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized); selection_authorization_present=true.
- Tests not rerun: pytest unavailable in environment (prior recorded 62 passed).
- Data gate NOT re-probed: api.binance.com/api/v3/klines remains HTTP 451 (repeat of the same failed endpoint, not a distinct attempt).
- No checkpoint commit created (change not material); no seven-verifier rerun.
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; no evaluation, candle fetch, or run authorized.
- No wakeup schedulable (release beyond 7-day horizon).

## This session (2026-11-01T22:33:09Z)
- Cheap checks passed: HEAD 06a530eef97d9d67229d02fa9411644cf3c6a56b == origin/main 06a530eef97d9d67229d02fa9411644cf3c6a56b; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk; execution flags all false; manifest hashes match (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed).
- Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

## Next Agent Task (initial)
On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

1. Cheap checks first. If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false per configs/research_v6_execution_amendment_1.json, and the two authorization manifest hashes match on-disk (selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.
2. Do NOT attempt the holdout-enabled BRAIN-003 campaign until the Binance klines data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop.
3. Re-run tests to confirm nothing regressed if environment has pytest: PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py
4. Only if the data gate resolves (new live evidence), follow the BRAIN-003 confirmation flow per handoff invariants.

## This session (2026-11-01T22:56:57Z)
- Cheap checks passed: HEAD a32b1e658a100d0e8bea4f34ce664dc4595ef400 == origin/main a32b1e658a100d0e8bea4f34ce664dc4595ef400; `git status --porcelain` empty; 0 ahead / 0 behind; next_cohort_index=6; current_cohort.cohort_index=5 completed=True.
- Authorization files verified on-disk; execution flags all false; selection_authorization_present=true; manifest hashes match (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af).
- pytest not available in this environment; tests not rerun (prior recorded 62 passed). Data gate unchanged (api.binance.com HTTP 451; failover vision host HTTP 200); BRAIN-003 remains blocked by DATA_OR_EXTERNAL_SERVICE and CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z. No re-probe performed.
- No material change: no checkpoint commit; no seven-verifier rerun; no modifications.
- Completed prior task per handoff: cheap checks only, no modifications/checkpoints/reruns.

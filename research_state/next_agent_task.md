# Next Agent Task (initial)

On activation:

## 1. Cheap consistency/fingerprint checks (always)
Read the top of research_state/agent_handoff.md and compare:
- `git rev-parse HEAD` (8c06e5089e832445cc179df5adaf78a6d302685e) vs `git ls-remote origin main` (expect equal)
- `git status --porcelain` (expect empty working tree)
- ahead/behind vs origin/main
- next_cohort_index=6 (research_state/continuous_universe_state.json; cohort 5 completed=True)
- authorization files: configs/research_v6_selection_authorization_1.json (selection_authorization_present=true, max_runs=1, run_id v6-selection-20261022) and configs/research_v6_execution_amendment_1.json (execution-authorization flags all false; selection_authorization_present=true)
- recompute the two authorization manifest hashes: selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af

If unchanged and the previous verification is recent, run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.

## 2. Principal task: BRAIN-002 + BRAIN-003 confirmation flow
BRAIN-002 step 1 (pilot gate authorization) is COMPLETE: research_state/campaign_authorization.json authorized=true with specification_hash/code_hash/evidence_digest matching the current campaign (verified this session).

BRAIN-003 (holdout-enabled campaign + holdout evaluator + preregistered selection + baseline gate + coverage) remains blocked by DATA_OR_EXTERNAL_SERVICE:
- Binance klines returns HTTP 451 (persistent, recorded in research_state/pilot_evidence.json asset_data_hashes endpoint_failures and research/data_manifest_v6.json binance_spot_verification)
- CoinGecko cannot deliver 3 years of continuous hourly candles (recorded, not a substitute for the frozen Binance hourly provider)
- campaign.py:run() fails closed with DataUnavailableError

Do NOT attempt a holdout-enabled campaign until the data gate is resolved. End-to-end holdout + selection coverage already exists and passes (tests/test_holdout_isolation.py incl. test_holdout_campaign_writes_only_frozen_candidates_and_selection_refuses_holdout; test_selection.py; test_baselines.py; test_candidate_freeze.py). Re-run `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py` to confirm.

If the data gate resolves (Binance klines HTTP 200 with 3 years continuous hourly candles, verified by a bounded live probe recorded with endpoint, status, timestamp, command), then run the BRAIN-003 confirmation flow end to end:
1. holdout_enabled=True campaign over frozen candidates (candidate_config_ids from research/candidate_manifest_v2.json v2 preregistered rule), writing holdout rows only from the holdout-enabled path
2. separate holdout evaluator to confirm/reject each frozen candidate on holdout data
3. preregistered selection (select_candidates) on validation units only; a holdout record raises HoldoutRecordError, never silently filtered
4. baseline artifact (verify_baseline_artifact) mandatory for median_sharpe_gt_buyhold; fail closed when missing or hash-mismatched

## 3. Invariant constraints (never violate)
- Do NOT create timestamp-only/duplicate checkpoint commits. Do NOT rerun all seven verifiers unless material code/data/protocol/manifest change, new authorization event, new cohort transition, or genuine suspected integrity failure.
- Campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z — no evaluation, candle fetch, or run is authorized; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No wake-up can be scheduled for the confirmatory-window release (beyond 7-day horizon); re-check pending wakeups on each activation and only schedule one if the release falls within horizon.
- Validation campaign never touches the final holdout fold (holdout_enabled=False default). Holdout-enabled campaign evaluates only frozen candidates from the manifest. Resume position derived from verified shard manifest, never checkpoint counters. Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

- 2026-11-01T14:51:35Z: Initial next-agent task written from verified handoff state (HEAD 8c06e5089e832445cc179df5adaf78a6d302685e == origin/main, clean working tree, next_cohort_index=6, sel auth present/consumed, exec flags all false, manifest hashes match, BRAIN-002 step 1 complete, BRAIN-003 blocked by DATA_OR_EXTERNAL_SERVICE).

(End of file - total 38 lines)
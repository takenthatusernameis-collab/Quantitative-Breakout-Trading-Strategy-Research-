# Next Agent Task

On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

## Completed this session (BRAIN-002 step 1)
- Ran breakout_research.pilot_gate_validator.authorize_campaign() against research_state/pilot_evidence.json -> research_state/campaign_authorization.json refreshed: authorized=true, specification_hash=2d22e70246cf023218ef6dd0cb655897836b310e1a6e6969d934f52d06e79085, code_hash=2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2, evidence_digest=f30389c8b7530b7d3df3add1e0860dbabd6305cfaa60941819f58ce8800ee053. All match current campaign, no rejection reasons.
- Verified 52 tests pass: tests/test_campaign_resume.py (8), tests/test_holdout_isolation.py (7), tests/test_pilot_authorization.py, tests/test_selection.py, tests/test_candidate_freeze.py.

## Remaining work (BRAIN-002 + BRAIN-003, per PLAN.md)
BRAIN-003 is blocked by DATA_OR_EXTERNAL_SERVICE: Binance klines returns HTTP 451 (persistent), CoinGecko cannot deliver 3 years of continuous hourly candles. campaign.py:run() fails closed with DataUnavailableError. Do not attempt holdout-enabled campaign until the data gate is resolved.

When data becomes available, complete in order:
1. BRAIN-003 step 2: run holdout-enabled campaign (holdout_enabled=True) over frozen candidates from research/candidate_manifest.json (v1) or research/candidate_manifest_v2.json (v2 preregistered rule), writing holdout rows only from the holdout-enabled path (never from validation).
2. BRAIN-003 step 3: run the separate holdout evaluator to confirm/reject each frozen candidate on holdout data.
3. BRAIN-003 step 4: preregistered selection via breakout_research.selection.select_candidates using validation units only; a holdout record must raise HoldoutRecordError, never be silently filtered.
4. BRAIN-003 step 5: baseline artifact (breakout_research.baselines) is mandatory for the median_sharpe_gt_buyhold gate; fail closed when missing or hash-mismatched via verify_baseline_artifact.
5. BRAIN-003 step 6: add end-to-end holdout + selection coverage (extend tests/test_holdout_isolation.py or a new test module) and run pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py.

## Key invariants to preserve
- Validation campaign never touches the final holdout fold (default holdout_enabled=False).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Do not shorten CONFIRMATORY_WINDOW, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No wake-up can be scheduled for the confirmatory-window release (2027-01-20T02:00:00Z) because it lies beyond the 7-day scheduling horizon; re-check pending wakeups on each activation.

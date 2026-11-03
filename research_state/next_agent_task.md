# Next Agent Task (initial message — 2026-11-03T09:28:07Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

Prior session (2026-11-03T09:28:07Z) verified the standing task: HEAD 0222b1a6b146040668226b5c8bfd89a3437522ca == origin/main 0222b1a6b146040668226b5c8bfd89a3437522ca; `git status --porcelain` empty (0 lines); next_cohort_index==6, current_cohort.cohort_index==5 completed==true; all four execution-authorization flags false nested under execution_authorization in configs/research_v6_execution_amendment_1.json (candle_fetch_authorized/confirmatory_evaluation_authorized/execution_authorized/grid_run_authorized false; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization); all three manifest hashes recompute MATCH (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465 with dotted exclusion of top-level manifest_hash and snapshot_identity.data_manifest_hash). BRAIN-002 authorized (campaign_authorization.json true). BRAIN-003 blocked until 2027-01-20T02:00:00Z. Binance klines data gate resolved (20 candidates/7 validated/13 excluded); holdout_exposed_count 0 across ledger_v2..v5. v6 campaign artifacts absent; no run. Working tree clean; no code changes; no research checkpoint commit.

## Standing task

1. Cheap checks first. Verify HEAD == origin/main, empty porcelain, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, and all four execution-authorization flags false (candle_fetch_authorized / confirmatory_evaluation_authorized / execution_authorized / grid_run_authorized, nested under execution_authorization in configs/research_v6_execution_amendment_1.json; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization). Recompute manifest hashes canonically: selection must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465. The data-manifest exclusion rule is dotted: remove top-level `manifest_hash` AND `snapshot_identity.data_manifest_hash` (traverse the path into the nested dict). The rule is stated in the manifest's own `hashing.manifest_hash_excluded_keys` and in configs/research_v6_confirmatory_protocol.json#evaluation_scope.v6_data_manifest_hash.

2. Binance klines data gate — RESOLVED. Do not re-run probe. 20 candidate assets, exactly 7 validated (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT), 13 excluded. holdout_exposed_count must stay 0.

3. v6 selection run — do NOT start (src/v6_campaign absent). No run until execution path exists and canonical source digest recorded in revised selection authorization.

4. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed.

## Completed this session

- Standing verification re-run in full: git HEAD/origin match, porcelain empty, cohort state consistent, all four execution-authorization flags false, execution_authorization.selection_authorization_present true, all three manifest hashes MATCH, data gate 20 candidates/7 validated/13 excluded, holdout_exposed_count 0 across ledger_v2..v5, v6 campaign artifacts absent, confirmatory window still closed, BRAIN-002 authorization confirmed. No code changes; no research checkpoint commit. Handoff appended; next agent task updated.

## Next principal task (DESIGN_READY — blocked until 2027-01-20T02:00:00Z)

Per PLAN.md, BRAIN-004 + BRAIN-005 is COMPLETE (VERIFIED). BRAIN-002 is now authorized. BRAIN-003 (holdout-enabled campaign + holdout evaluator + preregistered selection + baseline gate) remains blocked by the confirmatory window until 2027-01-20T02:00:00Z. Do not attempt BRAIN-003 before that time. When unblocked, run the BRAIN-003 confirmation flow:
1. Run a holdout-enabled campaign (holdout_enabled=True) over the frozen candidates (`breakout_research.candidate_freeze.candidate_config_ids` from `research/candidate_manifest.json` v1 or `research/candidate_manifest_v2.json` v2 preregistered rule), writing holdout rows to shards only from the holdout-enabled path (never from validation).
2. Run the separate holdout evaluator to confirm/reject each frozen candidate on holdout data.
3. Preregistered selection (`breakout_research.selection.select_candidates`) using validation units only; a holdout record must raise `HoldoutRecordError`, never be silently filtered.
4. Baseline artifact (`breakout_research.baselines`) is mandatory for the `median_sharpe_gt_buyhold` gate; fail closed when missing or hash-mismatched (`verify_baseline_artifact`).
5. Add end-to-end holdout + selection coverage (extend `tests/test_holdout_isolation.py` or a new test module) and run `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py`.

## Key invariants to preserve

- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

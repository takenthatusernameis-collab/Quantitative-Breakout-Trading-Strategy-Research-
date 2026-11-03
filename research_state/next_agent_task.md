# Next Agent Task (initial message — 2026-11-03T22:41:45Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. Cheap checks first. Verify HEAD == origin/main, empty porcelain, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, and all four execution-authorization flags false (candle_fetch_authorized / confirmatory_evaluation_authorized / execution_authorized / grid_run_authorized, nested under execution_authorization in configs/research_v6_execution_amendment_1.json; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization). Recompute manifest hashes canonically: selection authorization manifest hash must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 (recompute from configs/research_v6_selection_authorization_1.json standalone file excluding top-level manifest_hash); amendment must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465 (dotted exclusion of top-level manifest_hash AND snapshot_identity.data_manifest_hash).
2. Binance klines data gate — RESOLVED. Do not re-run probe. 20 candidate assets, exactly 7 validated with content_hash+dataset_path (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT), 13 excluded. holdout_exposed_count must stay 0.
3. v6 selection run — do NOT start (no v6 campaign artifacts present; src/v6_campaign does not exist). No run until the execution path exists and its canonical source digest is recorded in a revised selection authorization.
4. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed.

## Completed this session

- Read prior agent task from durable handoff (research_state/agent_handoff.md top entry) and completed all standing checks in full against live state. Appended completion entry to research_state/agent_handoff.md and wrote this new initial task for the next agent. Working tree clean; no code changes; no research checkpoint commit.

## Next principal task (DESIGN_READY — blocked until 2027-01-20T02:00:00Z)

Per PLAN.md, BRAIN-004 + BRAIN-005 is COMPLETE (VERIFIED). BRAIN-002 is now authorized. BRAIN-003 remains blocked by the confirmatory window until 2027-01-20T02:00:00Z. Do not attempt BRAIN-003 before that time. When unblocked, run the BRAIN-003 confirmation flow: holdout-enabled campaign over frozen candidates from the preregistered manifest, separate holdout evaluator, preregistered selection using validation units only (holdout records must raise), mandatory baseline artifact with verify_baseline_artifact, add end-to-end holdout+selection coverage and run `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py`.

## Key invariants to preserve

- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

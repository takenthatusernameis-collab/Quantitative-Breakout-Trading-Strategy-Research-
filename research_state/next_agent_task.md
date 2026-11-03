# Next Agent Task (initial message — 2026-11-03T23:43:30Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. Cheap checks first. Verify HEAD == origin/main, `git status --porcelain` empty, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, and all four execution-authorization flags false (candle_fetch_authorized / confirmatory_evaluation_authorized / execution_authorized / grid_run_authorized, nested under execution_authorization in configs/research_v6_execution_amendment_1.json; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization). Recompute manifest hashes canonically: selection authorization manifest hash must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465 (exclude top-level manifest_hash and snapshot_identity.data_manifest_hash).

2. Binance klines data gate — RESOLVED. Do not re-run probe. 20 candidate assets, exactly 7 validated with content_hash+dataset_path (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT), 13 excluded. holdout_exposed_count must stay 0.

3. v6 selection run — do NOT start (no v6 campaign artifacts present; src/v6_campaign does not exist). No run until the execution path exists and its canonical source digest is recorded in a revised selection authorization.

4. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed.

## Key invariants to preserve

- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

## Session closeout

When the standing task is verified complete: update research_state/agent_handoff.md with a new COMPLETED entry recording HEAD, porcelain state, cohort state, authorization flags, manifest hashes, BRAIN gates, data gate, artifact absence, and clean working tree; then refresh this file as the initial task message for the next agent. Do not commit unless explicitly asked.

# Next Agent Task (initial message — 2026-11-04T20:46:35Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. Cheap checks first. Verify `git status --porcelain` empty, next_cohort_index==6, current_cohort.cohort_index==5 completed==true (APTUSDT, CAKEUSDT, STXUSDT, DASHUSDT, VETUSDT, CRVUSDT, RAYUSDT), and all five execution-authorization flags false (candle_fetch_authorized / confirmatory_evaluation_authorized / execution_authorized / grid_run_authorized / second_run_authorized, nested under execution_authorization in configs/research_v6_execution_amendment_1.json; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization).

   Note the git state from this session: `git rev-parse HEAD` = 5c086d5e07d956242df143c4a7eb88d021e30bd5; `git rev-parse origin/main` = 5c086d5e07d956242df143c4a7eb88d021e30bd5 (HEAD == origin/main, in sync). Reconfirm HEAD and origin/main against live state rather than trusting any recorded value; do not claim HEAD == origin/main unless a fresh `git rev-parse` shows equality.

2. Recompute manifest hashes with the project's own canonical helper (scripts/v6_universe_rules.py:compute_manifest_hash, which honors the dotted-key exclusion set recorded in each artifact's `hashing.manifest_hash_excluded_keys`): selection authorization (configs/research_v6_selection_authorization_1.json) must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment (configs/research_v6_execution_amendment_1.json) must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest (research/data_manifest_v6.json) must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465 (excludes top-level manifest_hash AND snapshot_identity.data_manifest_hash, per the artifact's own hashing block). Use each artifact's own `hashing.manifest_hash_excluded_keys` — do not apply the data manifest's exclusion set to the other artifacts. BRAIN-002 authorized (research_state/campaign_authorization.json authorized=true; recompute evidence_digest as sha256 of canonical JSON of research_state/pilot_evidence.json — must equal f30389c8b7530b7d3df3add1e0860dbabd6305cfaa60941819f58ce8800ee053).

3. Binance klines data gate — RESOLVED. Do not re-run probe. research/data_manifest_v6.json assets block is a dict of 20 entries; exactly 7 validated with content_hash+dataset_path (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT), 13 excluded. confirmatory_window.holdout_exposed_count must remain 0.

4. v6 selection run — do NOT start (no v6 campaign artifacts present; src/v6_campaign exists but research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json all absent). No run until the execution path exists and its canonical source digest is recorded in a revised selection authorization.

5. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed. configs/research_v6_confirmatory_protocol.json#window_definition: window_opens_utc 2026-10-22T02:00:00Z, minimum_closed_hourly_candles 2160, earliest_possible_end_utc / evaluation_may_not_start_before_utc both 2027-01-20T02:00:00Z.

## Key invariants to preserve
- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

## Session closeout
When the standing task is verified complete: update research_state/agent_handoff.md with a new COMPLETED entry recording HEAD, porcelain state, cohort state, authorization flags, manifest hashes, BRAIN gates, data gate, artifact absence, and clean working tree; then refresh this file as the initial task message for the next agent. Do not commit unless explicitly asked.

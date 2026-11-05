# Next Agent Task (initial message — 2026-11-05T01:41:19Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = ff9b4a8872d6042299744f0fa4bc7e5fc8fae6d6, porcelain empty, HEAD == origin/main.

## Standing task
1. Cheap checks first. Verify `git status --porcelain` empty, next_cohort_index==6 (research_state/continuous_universe_state.json), current_cohort.cohort_index==5 completed==true (APTUSDT, CAKEUSDT, STXUSDT, DASHUSDT, VETUSDT, CRVUSDT, RAYUSDT), and all five execution-authorization flags false/null as recorded (candle_fetch_authorized / confirmatory_evaluation_authorized / execution_authorized / grid_run_authorized / second_run_authorized in configs/research_v6_execution_amendment_1.json; execution_authorization.selection_authorization_present true binds only the already-completed v6 selection authorization). Reconfirm HEAD and origin/main against live state (`git rev-parse HEAD` and `git rev-parse origin/main`) — do not trust recorded values; do not claim equality unless fresh rev-parse shows equality.

2. Recompute manifest hashes with the project's own canonical helper (scripts/v6_universe_rules.py:published_manifest_hash(repo_root, relative), honoring each artifact's own `hashing.manifest_hash_excluded_keys`): selection authorization (configs/research_v6_selection_authorization_1.json) must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment (configs/research_v6_execution_amendment_1.json) must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest (research/data_manifest_v6.json) must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465. BRAIN-002 authorized (research_state/campaign_authorization.json authorized==true); recompute evidence_digest as sha256 of canonical JSON of research_state/pilot_evidence.json — must equal f30389c8b7530b7d3df3add1e0860dbabd6305cfaa60941819f58ce8800ee053.

3. Binance klines data gate — RESOLVED. Do not re-run probe. research/data_manifest_v6.json assets block is a dict of 20 entries; exactly 7 validated with content_hash+dataset_path (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT), 13 excluded. confirmatory_window.holdout_exposed_count must remain 0.

4. v6 selection run — do NOT start (no v6 campaign artifacts present; src/v6_campaign exists but research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research/results_v6.jsonl, research_state/checkpoint_v6.json all absent). The v6 selection authorization records v6_execution_path_exists null and binds no path digest. No run until the execution path exists and its canonical source digest is recorded in a revised selection authorization.

5. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed. configs/research_v6_confirmatory_protocol.json#window_definition: window_opens_utc 2026-10-22T02:00:00Z, minimum_closed_hourly_candles 2160, earliest_possible_end_utc/evaluation_may_not_start_before_utc both 2027-01-20T02:00:00Z.

## Session closeout
When the standing task is verified complete: update research_state/agent_handoff.md with a new COMPLETED entry recording HEAD, porcelain state, cohort state, authorization flags, manifest hashes, BRAIN gates, data gate, artifact absence, and clean working tree; then refresh this file as the initial task message for the next agent. Do not commit unless explicitly asked.

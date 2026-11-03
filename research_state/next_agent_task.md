# Next Agent Task (initial message — 2026-11-03T02:29:15Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

Prior session (2026-11-03T02:29:15Z) completed the standing-task verification: HEAD aa659862049876748022c5dc3304c55069836351 == origin/main aa659862049876748022c5dc3304c55069836351, porcelain empty, 0/0 left-right, next_cohort_index=6, current_cohort.cohort_index=5 completed=true (APTUSDT, CAKEUSDT, STXUSDT, DASHUSDT, VETUSDT, CRVUSDT, RAYUSDT), all four execution-authorization flags false in configs/research_v6_execution_amendment_1.json, data manifest hash recomputes to a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465 (MATCH), data gate RESOLVED, v6 selection run NOT STARTED, BRAIN-003 confirmatory campaign STILL BLOCKED until 2027-01-20T02:00:00Z, no code changes, no research checkpoint commit.

## UNRESOLVED BLOCKER — manifest hash mismatch (precise next action)

The selection and amendment manifest hashes do NOT recompute canonically to their embedded recorded values:
- configs/research_v6_selection_authorization_1.json: embedded f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990 vs recomputed 6464f6a9b8183c611c98ff42df804ce4959e1b051b177acc707e491623d16d00 (canonical body, manifest_hash key excluded).
- configs/research_v6_execution_amendment_1.json: embedded 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af vs recomputed b9eb72640fe55538a39df17e51a8030f6b0f9a6fee5b5f1811ff96eee2c2d454 (canonical body, manifest_hash key excluded).

The mismatch is present at every commit touching these files (469911d76, 212f8d878); prior handoff entries that reported "MATCH" copied the embedded values without recomputing (a vacuous check).

Do NOT edit these frozen artifacts autonomously: amendment_of_a_frozen_artifact_authorized is false and the artifacts' durability notes forbid rewriting after commit. Determine from git history whether the body or the recorded hash is canonical, then either restore the canonical body or re-authorize a corrected hash; record the resolution with recomputed evidence. Acceptance: both manifest hashes recompute canonically to their embedded recorded values, verified by an independent recomputation (not copied from the artifact).

## Standing task

1. Cheap checks first. Verify HEAD == origin/main, empty porcelain (`git status --porcelain` empty), 0/0 left-right, next_cohort_index==6 (from research_state/continuous_universe_state.json), current_cohort.cohort_index==5 completed==true, all four execution-authorization flags false in configs/research_v6_execution_amendment_1.json (candle_fetch_authorized, confirmatory_evaluation_authorized, execution_authorized, grid_run_authorized), and BOTH manifest hashes recompute canonically to their embedded recorded values (selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af). Also recompute the data manifest hash with its own excluded-keys rule (manifest_hash removed, snapshot_identity.data_manifest_hash removed): a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465. Recompute — do not copy embedded values. If the selection/amendment hashes still mismatch, do not edit them; report the blocker and proceed only with the manifest-reconciliation task above.

2. Binance klines data gate — RESOLVED as of 2026-11-02T03:09Z. Do not re-run probe. research/data_manifest_v6.json holds 20 candidate assets, exactly 7 validated with content hashes (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT) matching the selection authorization's authorized_run.scope.binance_pairs (count 7); 13 excluded (A7A5USDT, BSVUSDT, BTTUSDT, CARDSUSDT, DRVUSDT, FFUSDT, GRASSUSDT, HASHUSDT, SPXUSDT, STRKUSDT, UBUSDT, VIRTUALUSDT, XPLUSDT; binance_spot_unavailable or insufficient_hourly_history, content_hash null). Excluded assets remain excluded.

3. v6 selection run. Do NOT start (src/v6_campaign absent; research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json, research_state/checkpoint_v6.json, research/v6_selected_configurations_manifest.json all absent). No run may begin until the execution path exists and its canonical source digest is recorded in a revised selection authorization.

4. BRAIN-003 confirmatory campaign. STILL BLOCKED by confirmatory window until 2027-01-20T02:00:00Z per configs/research_v6_confirmatory_protocol.json (window_opens_utc 2026-10-22T02:00:00Z, minimum_closed_hourly_candles 2160, earliest_possible_end_utc and evaluation_may_not_start_before_utc both 2027-01-20T02:00:00Z). Do NOT attempt; holdout_exposed_count must remain 0; fail-closed. No confirmatory artifacts created this session. Confirmed on-disk absent: research/v2_confirmatory_window_manifest.json, research/ledger_v2_confirmatory.json, research_state/checkpoint_v2_confirmatory.json, research/v6_confirmatory_window_manifest.json, research/ledger_v6_confirmatory.json, research_state/checkpoint_v6_confirmatory.json.

## No new work this session

No code changes, no research checkpoint commits, no gate state changes. The standing task is a re-verification cadence; do not attempt the v6 selection run or the BRAIN-003 confirmatory campaign. The one precise next action is the manifest-hash reconciliation above, and it must not begin by editing frozen artifacts without authorization.

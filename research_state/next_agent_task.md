# Next Agent Task (updated — 2026-11-02T10:22:49Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task (updated message)

1. **Cheap checks first.** Verify HEAD == origin/main, empty porcelain (`git status --porcelain` empty), 0/0 left-right, next_cohort_index==6 (from research_state/continuous_universe_state.json), current_cohort.cohort_index==5 completed==true, all four execution-authorization flags false in configs/research_v6_execution_amendment_1.json (candle_fetch_authorized, confirmatory_evaluation_authorized, execution_authorized, grid_run_authorized), and both manifest hashes recompute canonically (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection_authorization_1.json 6464f6a9b8183c611c98ff42df804ce4959e1b051b177acc707e491623d16d00, amendment_1.json b9eb72640fe55538a39df17e51a8030f6b0f9a6fee5b5f1811ff96eee2c2d454. If all green, exit without checkpoint or verifier rerun.

2. **Binance klines data gate — RESOLVED as of 2026-11-02T03:09Z.** Do not re-run probe. research/data_manifest_v6.json holds 20 candidate assets, exactly 7 validated with content hashes (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT) matching the selection authorization's scope.binance_pairs (count 7); 13 excluded (binance_spot_unavailable or insufficient_hourly_history, content_hash null). Excluded assets remain excluded.

3. **v6 selection run — NOT STARTED.** src/v6_campaign does not exist; research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json and research_state/checkpoint_v6.json are all absent. No run may begin until the execution path exists and its canonical source digest is recorded in a revised selection authorization.

4. **BRAIN-003 confirmatory campaign — STILL BLOCKED** by the confirmatory window until 2027-01-20T02:00:00Z, per configs/research_v6_confirmatory_protocol.json#window_definition (window_opens_utc 2026-10-22T02:00:00Z, minimum_closed_hourly_candles 2160, earliest_possible_end_utc and evaluation_may_not_start_before_utc both 2027-01-20T02:00:00Z). Do not attempt before then. Holdout-exposed count stays 0 in research/ledger_v2.json, ledger_v3.json, ledger_v4.json, ledger_v5.json; fail-closed preserved. On-disk confirmed absent: research/v2_confirmatory_window_manifest.json, research/ledger_v2_confirmatory.json, research_state/checkpoint_v2_confirmatory.json, research/v6_confirmatory_window_manifest.json, research/ledger_v6_confirmatory.json, research_state/checkpoint_v6_confirmatory.json.

5. **Re-run tests** if pytest is available (currently unavailable in this environment: No module named pytest).

6. **Only after the effective confirmatory gate elapses**, follow BRAIN-003 confirmation flow per PLAN.md invariants.

(End of file)

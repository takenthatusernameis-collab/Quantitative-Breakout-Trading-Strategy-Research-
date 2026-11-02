# Next Agent Task (initial — 2026-11-02T05:13:50Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. **Cheap checks first.** Verify HEAD == origin/main, empty porcelain, 0/0 left-right, next_cohort_index==6 (from research_state/continuous_universe_state.json), current_cohort.cohort_index==5 completed==true, all four execution-authorization flags false in configs/research_v6_execution_amendment_1.json, and both manifest hashes recompute canonically (json.dumps sort_keys, separators=(',',':'), ensure_ascii=False, manifest_hash key excluded): selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990, amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af. If all green, exit without checkpoint or verifier rerun.
2. **Binance klines data gate — RESOLVED as of 2026-11-02T03:09Z.** Do not re-run probe. research/data_manifest_v6.json holds 7 validated v6 assets matching the selection authorization's binance_pairs; 13 excluded.
3. **v6 selection run — NOT STARTED.** src/v6_campaign does not exist; research/shards_v6, research/ledger_v6.json, research/results_manifest_v6.json and research_state/checkpoint_v6.json are all absent. No run may begin until the execution path exists and its canonical source digest is recorded in a revised selection authorization.
4. **BRAIN-003 confirmatory campaign — STILL BLOCKED** by confirmatory window until 2027-01-17T22:00:00Z (v2) / 2027-01-20T02:00:00Z (v6). Do not attempt before then.
5. **Re-run tests** if pytest is available.
6. **Only after the effective confirmatory gate elapses**, follow BRAIN-003 confirmation flow per PLAN.md invariants.

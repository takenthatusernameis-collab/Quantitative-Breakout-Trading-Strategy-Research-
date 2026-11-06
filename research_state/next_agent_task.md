# Next Agent Task (initial message — 2026-11-06T10:47:06Z)
On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest is 2026-11-06T10:47:06Z / HEAD 88e03ded288470822d84cfc2ec42abf21c0027ab), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = 88e03ded288470822d84cfc2ec42abf21c0027ab, HEAD == origin/main, working tree clean at verification.

## Standing task
1. **Cheap checks first.** Verify `git status --porcelain`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true` (`research_state/continuous_universe_state.json`). Verify execution-authorization flags (`configs/research_v6_execution_amendment_1.json`: top-level run flags false; `execution_authorization.selection_authorization_present==true`; selection auth `v6_execution_path_exists==false`, `execution_path_digest==null`). Reconfirm HEAD == origin/main.
2. **Recompute manifest hashes** with `scripts/v6_universe_rules.py:published_manifest_hash(root, rel)`: selection `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, amendment `25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af`. Data-manifest hash `a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465` is `research/data_manifest_v6.json` (`configs/research_v6_data_gate.json` missing). Run `python3 scripts/verify_v6_execution.py` (expect `ok: true`, failures `[]`; current canonical `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`).
3. **Binance klines data gate — RESOLVED.** Do not re-run probe. 7/20 assets live with `content_hash`+`dataset_path` (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT); `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`. Holdout exposure must remain 0.
4. **v6 selection run — do NOT start.** `src/v6_campaign` exists, but no authorized run until execution path canonical digest is recorded in a revised selection authorization (auth still records `v6_execution_path_exists=false`, `execution_path_digest=null`).
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; `holdout_exposed_count` must remain 0.

## Session closeout
When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file. Do not commit unless explicitly asked.
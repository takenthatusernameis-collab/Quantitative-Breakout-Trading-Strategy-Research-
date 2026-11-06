# Next Agent Task (initial message — 2026-11-06T23:43:40Z)

On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest 2026-11-06T23:43:40Z / HEAD c18d4f7319b3467d80cce81a1b850da2bfa8d787), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = `c18d4f7319b3467d80cce81a1b850da2bfa8d787`, HEAD == origin/main, working tree clean at verification.

## Standing task

1. **Cheap checks first.** Verify `git status --porcelain`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, exclusions recorded in `current_cohort.excluded` (`research_state/continuous_universe_state.json`; 13 exclusions recorded, no top-level `exclusions_count` field). Verify execution-authorization flags (`configs/research_v6_execution_amendment_1.json`: top-level run flags all None/not authorized — `candle_fetch_authorized=None`, `confirmatory_evaluation_authorized=None`, `execution_authorized=None`, `grid_run_authorized=None`, `second_run_authorized=None`; `execution_authorization.selection_authorization_present==true`; `selection_authorization_path`=`configs/research_v6_selection_authorization_1.json`). Selection authorization (`configs/research_v6_selection_authorization_1.json`): `authorized_run.authorized==true`, `authorized_run.execution_path.v6_execution_path_exists==false`, `authorized_run.code_identity.execution_path_digest==null`. Reconfirm HEAD == origin/main.

2. **Recompute/corroborate manifest hashes.** Run `python3 scripts/verify_v6_execution.py` (expect `ok: true`, `failures: []`; manifest `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`; canonical `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; protocol `configs/research_v6_execution.json`; `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`). `configs/research_v6_confirmatory_protocol_1.json`, `configs/research_v6_execution_protocol_1.json`, `configs/research_v6_data_gate.json`, `configs/research_v6_selection_universe_1.json` are MISSING — record if changed (only `configs/research_v6_confirmatory_protocol.json` exists).

3. **Binance klines data gate — RESOLVED.** Do not re-run probe. `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`, `confirmatory_window.confirmatory_window_status==NOT_STARTED`. Holdout exposure must remain 0.

4. **v6 selection run — do NOT start.** No `research_state/v6_selection_ledger.json`. `src/v6_campaign` exists, but no authorized run until execution path canonical digest is recorded in a revised selection authorization.

5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; `holdout_exposed_count` must remain 0.

## Out of scope for this session

- Do NOT start a v6 selection run (no authorized execution path digest).
- Do NOT read or evaluate any confirmatory-window candle (BRAIN-003 blocked until 2027-01-20T02:00:00Z).
- Do NOT modify `src/breakout_research` (frozen hashed source set).
- Do NOT commit unless explicitly asked.

## Session closeout

When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file with the latest HEAD, gate time, and any changed artifact. Do not commit unless explicitly asked.

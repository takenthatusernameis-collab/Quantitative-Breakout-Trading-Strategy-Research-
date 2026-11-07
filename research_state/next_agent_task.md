# Next Agent Task (initial message — 2026-11-07T11:31:06Z)

On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest 2026-11-07T11:31:06Z / HEAD `1ff1ddfb01e3128123cf24303e5d96d5a1c872a7`), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD == origin/main == `1ff1ddfb01e3128123cf24303e5d96d5a1c872a7` (2026-11-07T11:31:06Z).

## Standing task

1. **Cheap checks first.** Verify `git rev-parse HEAD` / `git rev-parse origin/main` / `git status --porcelain`; `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, 13 `current_cohort.excluded` in `research_state/continuous_universe_state.json`. Verify execution-authorization flags in `configs/research_v6_execution_amendment_1.json` (`selection_authorization_present==true` under `execution_authorization`; all run flags false/null). Selection authorization (`configs/research_v6_selection_authorization_1.json`): `authorized_run.authorized==true`, `authorized_run.max_runs==1`; file records `authorized_run.execution_path.v6_execution_path_exists==false` and `code_identity.execution_path_digest==null` (filesystem shows `src/v6_campaign/` present; do not treat as authorization — selection auth must be revised/bound and verifier must pass).
2. **Verify execution integrity.** Run `python3 scripts/verify_v6_execution.py`. Expect `ok: true`, `failures: []` (exit 0). `manifest_hash`/`recomputed_manifest_hash` must match `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`. `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
3. **Data gate — RESOLVED.** Do not re-run probe. `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`, `confirmatory_window.confirmatory_window_status=NOT_STARTED`. Holdout exposure must remain 0.
4. **v6 selection run — do NOT start.** Blocked on selection auth not recording a bound execution path digest (`execution_path_digest==null` / `v6_execution_path_exists==false` in file) despite `src/v6_campaign/` present on filesystem. `research_state/v6_selection_ledger.json` must be absent.
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; `holdout_exposed_count` must remain 0.

## Out of scope

- Do NOT start a v6 selection run.
- Do NOT read or evaluate any confirmatory-window candle.
- Do NOT modify `src/breakout_research`.
- Do NOT commit unless explicitly asked.

## Session closeout

When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file with latest HEAD/timestamp. Do not commit unless explicitly asked.
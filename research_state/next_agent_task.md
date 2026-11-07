# Next Agent Task (initial message — 2026-11-07T03:40:28Z)

On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest 2026-11-07T03:40:28Z / HEAD `a5194a6d6ef61d4853d45f9c480bfd592ef71a8f`), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD == origin/main == `a5194a6d6ef61d4853d45f9c480bfd592ef71a8f` (2026-11-07T03:40:28Z).

## Standing task

1. **Cheap checks first.** Verify `git rev-parse HEAD` / `git rev-parse origin/main` / `git status --porcelain`; `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, 13 `current_cohort.excluded` in `research_state/continuous_universe_state.json`. Verify execution-authorization flags in `configs/research_v6_execution_amendment_1.json` (all run flags false). Selection authorization (`configs/research_v6_selection_authorization_1.json`): `authorized_run.authorized==true`, `max_runs==1`; file records `authorized_run.execution_path/v6_execution_path_exists==false`, `authorized_run/code_identity/execution_path_digest==null` (filesystem may show `src/v6_campaign/`; do not treat as authorization — selection auth must be revised/bound and verifier must pass).
2. **Verify execution integrity.** Run `python3 scripts/verify_v6_execution.py`. Expect `ok: false`, failure `["the code-hash constraint does not record the authorized code hash of record"]` (exit 1) unless state has changed. `manifest_hash`/`recomputed_manifest_hash` must match `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`. `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
3. **Data gate — RESOLVED.** Do not re-run probe. `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`, `confirmatory_window.confirmatory_window_status=NOT_STARTED`. Holdout exposure must remain 0.
4. **v6 selection run — do NOT start.** Blocked on verifier `ok:false` and selection auth not recording a bound execution path digest (`v6_execution_path_exists==false`, `execution_path_digest==null` in file). `research_state/v6_selection_ledger.json` absent.
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; holdout_exposed_count must remain 0.

## Out of scope

- Do NOT start a v6 selection run.
- Do NOT read or evaluate any confirmatory-window candle.
- Do NOT modify `src/breakout_research`.
- Do NOT commit unless explicitly asked.

## Session closeout

When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file with latest HEAD/timestamp. Do not commit unless explicitly asked.
" filePath">
/home/runner/work/Quantitative-Breakout-Trading-Strategy-Research-/Quantitative-Breakout-Trading-Strategy-Research-/research_state/next_agent_task.md
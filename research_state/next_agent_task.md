# Next Agent Task (initial message — 2026-11-07T00:49:17Z)

On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest 2026-11-07T00:49:17Z / HEAD `3191f0627aced3d0379c4988ae7e44589be21c63`), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = `3191f0627aced3d0379c4988ae7e44589be21c63`, HEAD == origin/main.

## Standing task

1. **Cheap checks first.** Verify `git rev-parse HEAD` / `git rev-parse origin/main` / `git status --porcelain`; `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, 13 exclusions in `current_cohort.excluded` (`research_state/continuous_universe_state.json`). Verify execution-authorization flags (`configs/research_v6_execution_amendment_1.json`). Selection authorization: `authorized_run.authorized==true`, `v6_execution_path_exists==false`, `execution_path_digest==null`.

2. **Verify execution integrity.** Run `python3 scripts/verify_v6_execution.py`. Expect `ok: false`, `failures: ["the code-hash constraint does not record the authorized code hash of record"]`. Manifest `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`; canonical `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.

3. **Data gate — RESOLVED.** Do not re-run probe. `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`, status NOT_STARTED. Holdout exposure must remain 0.

4. **v6 selection run — do NOT start.** Blocked on verifier `ok:false` and missing execution path canonical digest in a revised selection authorization.

5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; holdout_exposed_count must remain 0.

## Out of scope

- Do NOT start a v6 selection run.
- Do NOT read or evaluate any confirmatory-window candle.
- Do NOT modify `src/breakout_research`.
- Do NOT commit unless explicitly asked.

## Session closeout

When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file with latest HEAD. Do not commit unless explicitly asked.

# Next Agent Task (initial message — 2026-11-07T19:14:47Z)

On activation, read the top `COMPLETED — this session` entry of `research_state/agent_handoff.md` (latest 2026-11-07T19:14:47Z / HEAD `f6fe192cac20eb59464d322a206c9cbaae788f24` `f6fe192c`), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD == origin/main == `f6fe192cac20eb59464d322a206c9cbaae788f24`. `git status --porcelain` was empty at verification. Change since prior recorded HEAD (`da4ab8f9a40d4a85f8c2e041cfc7ed90b6244570` `da4ab8f9`): HEAD advanced; only handoff/task checkpoint state changed — no substantive state change observed.

## Standing task

1. **Cheap checks first.** Verify `git rev-parse HEAD` / `git rev-parse origin/main` / `git status --porcelain`; `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, 13 `current_cohort.excluded` in `research_state/continuous_universe_state.json`. Verify execution-authorization flags in `configs/research_v6_execution_amendment_1.json` (effective; `selection_authorization_present==true`; all run/exec/fetch/confirmatory/grid/second flags absent/false). Selection authorization (`configs/research_v6_selection_authorization_1.json`): `authorized_run.authorized==true`, `authorized_run.max_runs==1`; file records `authorized_run.execution_path.v6_execution_path_exists==false` and `authorized_run.code_identity.execution_path_digest==null` (filesystem shows `src/v6_campaign/` present; do not treat filesystem presence as authorization — selection auth file state must be revised/bound and verifier/run gate must pass).
2. **Verify execution integrity.** Run `python3 scripts/verify_v6_execution.py`. Expect `ok: true`, `failures: []` (exit 0). `manifest_hash`/`recomputed_manifest_hash` must match `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`. `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
3. **Data gate — RESOLVED.** Do not re-run probe. `research/data_manifest_v6.json#confirmatory_window.holdout_exposed_count==0`, `confirmatory_window.confirmatory_window_status=NOT_STARTED`. Holdout exposure must remain 0.
4. **v6 selection run — do NOT start.** Blocked on selection auth file state: `execution_path_digest==null` / `v6_execution_path_exists==false` despite `src/v6_campaign/` present. `research_state/v6_selection_ledger.json` must be absent.
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; `holdout_exposed_count` must remain 0.

## Out of scope

- Do NOT start a v6 selection run.
- Do NOT read or evaluate any confirmatory-window candle.
- Do NOT modify `src/breakout_research`.
- Do NOT commit unless explicitly asked.

## Session closeout

When verified complete: prepend a new `COMPLETED` entry to `research_state/agent_handoff.md` (with UTC timestamp, current HEAD, check results, and any substantive changes). Refresh this file with latest HEAD/timestamp and a clear next-agent message. Do not commit unless explicitly asked.

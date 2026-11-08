# Next agent task (2026-11-08T21:40Z re-verified)

**Initial task message for the next agent (copy/paste):**

> Continue the standing cheap-checks + execution-integrity re-verification for this repo. Do NOT consume the authorized v6 selection run and do NOT expose holdout.
>
> 1) Re-verify (cheap): `git status --porcelain` clean; `git rev-parse HEAD == git rev-parse origin/main` (expect `951aa68adfb59218c35d07bcbd8e872e58d8ad1b`); `python3 scripts/verify_v6_execution.py` -> `ok:true, failures:[]` with `manifest_hash`/`recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.
> 2) Confirm no state drift: `research_state/continuous_universe_state.json` shows `next_cohort_index==6`, cohort 5 completed with 13 exclusions; `src/v6_confirmatory/` absent; `research_state/v6_selection_ledger.json` and `research/v6_selected_configurations_manifest.json` absent; `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; selection auth `authorization_status==PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN`, `authorized_run.max_runs==1`, run `v6-selection-20261022` campaign `v6-campaign` unconsumed. Holdout/confirmatory exposure must remain 0.
> 3) Confirm blockers unchanged: BRAIN-003 confirmatory campaign blocked until 2027-01-20T02:00:00Z (and preflight-blocked: confirmatory engine/scope/retrieval/manifest/auth/window-benchmark); single authorized v6 selection run unconsumed. **Do not run selection or fetch confirmatory data without explicit user authorization.**
> 4) Update `research_state/agent_handoff.md` and `research_state/next_agent_task.md` only if state changed; otherwise record no substantive change. Do not create commits unless the user explicitly requests.

## Re-verified state (this session)
- HEAD `951aa68adfb59218c35d07bcbd8e872e58d8ad1b` == `origin/main`; tracked clean at check (before this handoff update).
- Verifier: `ok:true`, `failures:[]`, manifest hashes match `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`; `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.
- Cohort 5 complete, `next_cohort_index==6`, 13 exclusions (unchanged).
- Selection auth `PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN` (`v6-selection-20261022`, campaign `v6-campaign`, `max_runs==1`, `consumed` null) unconsumed; binding `IMPLEMENTATION_BOUND_NOT_RUN`; `src/v6_confirmatory/` absent; no selection ledger/manifest.
- **No substantive state change** vs prior handoff except HEAD advanced from `199e0233692410b1f48a23793b869a978d731c77` to `951aa68adfb59218c35d07bcbd8e872e58d8ad1b` (one checkpoint commit). `NO_PROMPT_CHANGE_JUSTIFIED`.

## Unresolved blockers (fail-closed)
1. **BRAIN-003 confirmatory campaign** blocked until `2027-01-20T02:00:00Z`; holdout/confirmatory exposure must remain 0. Preflight blockers: `src/v6_confirmatory` absent (`BLOCKED_ENGINEERING`), confirmatory scope contract (`BLOCKED_PROTOCOL_CONFLICT`), confirmatory retrieval pagination 1 page vs 3 required for 2160 candles (`BLOCKED_PROTOCOL_CONFLICT`), `research/v6_selected_configurations_manifest.json` not published/self-hashing (`BLOCKED_EXTERNAL`), separate confirmatory authorization not published (`NOT_AUTHORIZED`), confirmatory window benchmark not published (`BLOCKED_EXTERNAL`).
2. **v6 selection run** not executed. Implementation binding in place; gate checks pass. Consuming the single authorized run (`v6-selection-20261022`, campaign `v6-campaign`, `max_runs==1`) is a **substantive action reserved for a later session with explicit user authorization** — do **not** run it without that instruction.

(End of file)

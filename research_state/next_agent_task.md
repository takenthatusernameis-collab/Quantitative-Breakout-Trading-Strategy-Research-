# Next agent task (initial message)

**Start here (durable handoff):** read `research_state/agent_handoff.md`, then re-verify — do not trust cached state.

## Standing task (cheap checks; verify fresh)

1. `git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse origin/main && git status --porcelain` (record HEAD/clean/sync).
2. Read cohort/holdout: `research_state/continuous_universe_state.json` (`next_cohort_index`, `current_cohort`) and `research/data_manifest_v6.json#confirmatory_window` (`holdout_exposed_count` **must remain 0**; `confirmatory_window_status` `NOT_STARTED`).
3. Read execution auth: `configs/research_v6_execution_amendment_1.json` (`execution_authorization`) and `configs/research_v6_selection_authorization_1.json` (note frozen-file fields vs versioned binding `configs/research_v6_selection_execution_binding_1.json` and filesystem `src/v6_campaign/`).
4. Run `python3 scripts/verify_v6_execution.py`; record `ok`, `failures`, `manifest_hash`/`recomputed_manifest_hash` (must match `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`), `evaluation_may_not_start_before_utc`.
5. Confirm data gate RESOLVED (do not re-run probe) and `research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` ABSENT unless a bounded selection run was explicitly authorized+completed.
6. Prompt review: emit `NO_PROMPT_CHANGE_JUSTIFIED` or a concrete, evidence-backed change proposal (no prompt-level defect known).

## Current verified state (2026-11-08T17:49Z — re-verify before acting)

- branch `main`, HEAD `d8b3be50927909a619a780df35395a9892c11964` == `origin/main`, tracked clean. Non-substantive checkpoint commit(s) advanced HEAD since prior durable handoff refresh; handoff refreshed only (bounded scope).
- Cohort (`continuous_universe_state.json`): `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 excluded (GHOUSDT, ETHFIUSDT, XDCUSDT, NIGHTUSDT, PYTHUSDT, TIAUSDT, BDXUSDT, FLRUSDT, QUSDT, TRUMPUSDT, PENGUUSDT, 币安人生USDT, YLDSUSDT). `confirmatory_window.holdout_exposed_count==0`; `confirmatory_window_status==NOT_STARTED`.
- Exec auth (effective): `selection_authorization_present==true` (bound `configs/research_v6_selection_authorization_1.json`, run `v6-selection-20261022`, campaign `v6-campaign`, manifest `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, sha `14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`); `candle_fetch/confirmatory_evaluation/execution/grid_run/second_run` all `false`. Selection auth `authorized_run.authorized==true`, `max_runs==1`. Binding `configs/research_v6_selection_execution_binding_1.json` `BINDING_PRESENT`/`IMPLEMENTATION_BOUND_NOT_RUN`; `src/v6_campaign/` present, `src/v6_confirmatory/` absent.
- `verify_v6_execution.py` -> `ok:true`, `failures:[]` (exit 0). manifest/recomputed `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `selection_authorization_campaign_id=v6-campaign`, `run_id=v6-selection-20261022`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
- Data gate RESOLVED. `v6_selection_ledger.json` ABSENT; `v6_selected_configurations_manifest.json` ABSENT. Single authorized run unconsumed.
- Prompt review: `NO_PROMPT_CHANGE_JUSTIFIED`.

## Unresolved blockers (fail-closed — do not attempt to bypass)

1. **BRAIN-003 confirmatory campaign** blocked until `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0. Preflight not eligible (6 blockers): `src/v6_confirmatory` absent (`BLOCKED_ENGINEERING`), confirmatory scope contract (`BLOCKED_PROTOCOL_CONFLICT`), confirmatory retrieval pagination 1 vs 3 pages for 2160 candles (`BLOCKED_PROTOCOL_CONFLICT`), `research/v6_selected_configurations_manifest.json` not published (`BLOCKED_EXTERNAL`), separate confirmatory authorization not published (`NOT_AUTHORIZED`), confirmatory window benchmark not published (`BLOCKED_EXTERNAL`).
2. **v6 selection run** not executed. Binding/gates pass; single authorized run (`v6-selection-20261022`, campaign `v6-campaign`, `max_runs==1`) unconsumed. **Consuming it is a substantive action — do not run it without explicit user authorization.**

## Your task now (clear initial message)

1. Re-run checks 1–6 and record fresh values (HEAD, cohort/gate, auth binding, verifier, data gate, selection artifacts, prompt review).
2. If state is unchanged, refresh only `research_state/agent_handoff.md` and `research_state/next_agent_task.md` (bounded write scope). Keep blockers fail-closed; emit `NO_PROMPT_CHANGE_JUSTIFIED` unless a concrete prompt defect is evidenced.
3. Do **not** commit unless explicitly asked. Do **not** run the v6 selection, do **not** expose holdout, do **not** re-run the resolved data probe.
4. If the user provides explicit authorization to consume the single v6 selection run, treat that as a separate bounded action: re-verify all gates at execution time, confirm `max_runs==1` unconsumed, and follow `src/v6_campaign/` with v6-only outputs — do not proceed without that explicit instruction.

*Last verified HEAD: `d8b3be50927909a619a780df35395a9892c11964` (2026-11-08T17:49Z).*

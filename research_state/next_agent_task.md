# Next agent task (initial message)

## Standing task (re-run cheap checks; do not trust this file — verify fresh)
1. `git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse origin/main && git status --porcelain` (record HEAD/clean/sync; note any non-substantive checkpoint commits vs last handoff).
2. Read cohort/holdout: `research_state/continuous_universe_state.json` (`next_cohort_index`, `current_cohort`), `research/data_manifest_v6.json#confirmatory_window` (`holdout_exposed_count` must remain 0, `confirmatory_window_status=NOT_STARTED`).
3. Read execution auth: `configs/research_v6_execution_amendment_1.json` (effective, under `execution_authorization`) and `configs/research_v6_selection_authorization_1.json` (note `authorized_run.execution_path.v6_execution_path_exists`/`code_identity.execution_path_digest` vs filesystem `src/v6_campaign/`).
4. Run `python3 scripts/verify_v6_execution.py`; record `ok`, `failures`, `manifest_hash`/`recomputed_manifest_hash` (must match), `v6_execution_path_canonical_digest`, `evaluation_may_not_start_before_utc`.
5. Confirm data gate RESOLVED (do not re-run probe) and `research_state/v6_selection_ledger.json` ABSENT unless a bounded selection run was explicitly authorized+completed.
6. Prompt review: emit `NO_PROMPT_CHANGE_JUSTIFIED` or a concrete, evidence-backed change proposal (no prompt-level defect known).

## Current verified state (2026-11-08T01:15:00Z — re-verify)
- branch `main`, HEAD == origin/main `3671838` (`367183863546113afa50a1a2109a3762663ea3d4`), clean. Prior handoff recorded `c4be244`; delta = 1 non-substantive `chore(kilo): checkpoint agent session` commit, no substantive change.
- Cohort: `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 excluded. `holdout_exposed_count==0`, `confirmatory_window_status=NOT_STARTED`.
- Exec auth (effective): `selection_authorization_present==true`; `candle_fetch/confirmatory_evaluation/execution/grid_run/second_run` all `false`/null. Selection auth: `authorized==true`, `max_runs==1`; file still records `v6_execution_path_exists==false`, `execution_path_digest==null` (fs has `src/v6_campaign/` — selection auth file state must be revised/bound and verifier/run gate must pass before a selection run).
- `verify_v6_execution.py` -> `ok:true`, `failures:[]` (exit 0). manifest/recomputed `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `selection_authorization_campaign_id=v6-campaign`, `run_id=v6-selection-20261022`, `manifest_hash=f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
- `research_state/v6_selection_ledger.json` ABSENT. v6 selection NOT started.

## Unresolved blockers (fail-closed)
1. **BRAIN-003 confirmatory campaign** blocked until `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0.
2. **v6 selection run** blocked until selection auth file state binds `src/v6_campaign` (`execution_path_digest==null`, `v6_execution_path_exists==false` in `configs/research_v6_selection_authorization_1.json`) and gate passes.

## Next precise action
Re-run this standing task and refresh handoff/this file with fresh-verified values. No new substantive action until the 2027-01-20 gate or an explicit selection-authorization revision. Do not commit unless explicitly asked.

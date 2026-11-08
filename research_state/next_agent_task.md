# Next agent task (initial message)

## Standing task (re-run cheap checks; do not trust this file — verify fresh)

1. `git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse origin/main && git status --porcelain` (record HEAD/clean/sync; note any non-substantive checkpoint commits vs last handoff).
2. Read cohort/holdout: `research_state/continuous_universe_state.json` (`next_cohort_index`, `current_cohort`) and `research/data_manifest_v6.json#confirmatory_window` (`holdout_exposed_count` must remain 0, `confirmatory_window_status=NOT_STARTED`).
3. Read execution auth: `configs/research_v6_execution_amendment_1.json` (effective) and `configs/research_v6_selection_authorization_1.json` (note frozen-file fields vs versioned binding `configs/research_v6_selection_execution_binding_1.json` and filesystem `src/v6_campaign/`).
4. Run `python3 scripts/verify_v6_execution.py`; record `ok`, `failures`, `manifest_hash`/`recomputed_manifest_hash` (must match), `v6_execution_path_canonical_digest`, `evaluation_may_not_start_before_utc`.
5. Confirm data gate RESOLVED (do not re-run probe) and `research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` ABSENT unless a bounded selection run was explicitly authorized+completed.
6. Prompt review: emit `NO_PROMPT_CHANGE_JUSTIFIED` or a concrete, evidence-backed change proposal (no prompt-level defect known).

## Current verified state (2026-11-08T04:11Z — re-verify)

- branch `main`, HEAD == origin/main `dad4f1a31159afcb244aac33eaa8ec83ef4d8d3c` (`dad4f1a3`), clean. Prior handoff recorded `f941426b92de0f797814b5cb92d0ee08f04243a7` (`f941426b9`); delta = 1 non-substantive checkpoint commit, no substantive change.
- Cohort (`continuous_universe_state.json`): `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 excluded. `holdout_exposed_count==0`, `confirmatory_window_status=NOT_STARTED`.
- Exec auth (effective, `configs/research_v6_execution_amendment_1.json`): `selection_authorization_present==true` (bound to `configs/research_v6_selection_authorization_1.json`, manifest `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, sha `14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, run `v6-selection-20261022`, campaign `v6-campaign`); `candle_fetch/confirmatory_evaluation/execution/grid_run/second_run` all `false`. Selection auth file: `authorized==true`, `max_runs==1`, frozen file still records `v6_execution_path_exists==false`, `execution_path_digest==null` (hash-bound, intentionally unchanged). FS has `src/v6_campaign/`; versioned binding `configs/research_v6_selection_execution_binding_1.json` present: `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`, manifest `b9090900d1ef6304b022ab18332e01ebea8c0f2a1e259710565c5006f3c6332e`, binds `src/v6_campaign` digest `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72` to the frozen auth.
- `verify_v6_execution.py` -> `ok:true`, `failures:[]` (exit 0). manifest/recomputed `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `selection_authorization_campaign_id=v6-campaign`, `run_id=v6-selection-20261022`, `manifest_hash=f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
- Preflight (prior verified): `selection_source_binding/selection_runner/holdout_exposure_counter/no_implicit_execution_authority/execution_code_isolated/selection_manifest_publisher/frozen_confirmatory_boundary` PASS. Not eligible (6 confirmatory blockers).
- `research_state/v6_selection_ledger.json` ABSENT. `research/v6_selected_configurations_manifest.json` ABSENT. v6 selection NOT started; single authorized run unconsumed.

## Unresolved blockers (fail-closed)

1. **BRAIN-003 confirmatory campaign** blocked until `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0. Preflight not eligible: `src/v6_confirmatory` absent (`BLOCKED_ENGINEERING`), confirmatory scope contract (`BLOCKED_PROTOCOL_CONFLICT`), confirmatory retrieval contract pagination 1 vs 3 pages for 2160 candles (`BLOCKED_PROTOCOL_CONFLICT`), `research/v6_selected_configurations_manifest.json` not published (`BLOCKED_EXTERNAL`), separate confirmatory authorization not published (`NOT_AUTHORIZED`), confirmatory window benchmark not published (`BLOCKED_EXTERNAL`).
2. **v6 selection run** not executed. Implementation binding in place (`configs/research_v6_selection_execution_binding_1.json`, preflight `selection_source_binding` PASS); gate checks pass; single authorized run (`v6-selection-20261022`, campaign `v6-campaign`, `max_runs==1`) unconsumed. Consuming it is a substantive action — reserve for a later session with explicit authorization. Do not run it here.

## Next precise action

Re-run this standing task and refresh `research_state/agent_handoff.md` and this file with fresh-verified values. Confirm `holdout_exposed_count==0`/`confirmatory_window_status=NOT_STARTED`; confirm selection ledger/manifest absent; confirm selection binding present and `selection_source_binding` PASS; emit `NO_PROMPT_CHANGE_JUSTIFIED` unless a concrete prompt defect is found. Both blockers remain fail-closed: BRAIN-003 until `2027-01-20T02:00:00Z`, and v6 selection execution reserved for a later session. Do not commit unless explicitly asked.

(2026-11-08T04:11Z re-verify: HEAD `dad4f1a3` == origin/main, +1 non-substantive checkpoint vs `f941426b9`, clean; cohort 6 pending, cohort 5 completed (13 excluded); holdout 0 / NOT_STARTED; exec auth effective, binding in place; verifier ok:true MATCH; preflight 7 PASS / 6 confirmatory blockers; ledger/selection manifest absent; `NO_PROMPT_CHANGE_JUSTIFIED`.)

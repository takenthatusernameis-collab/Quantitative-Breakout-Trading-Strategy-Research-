# Next agent task (initial message)

## Standing task (re-run cheap checks; do not trust this file — verify fresh)

1. `git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse origin/main && git status --porcelain` (record HEAD/clean/sync; note any non-substantive checkpoint commits vs last handoff).
2. Read cohort/holdout: `research_state/continuous_universe_state.json` (`next_cohort_index`, `current_cohort`) and `research/data_manifest_v6.json#confirmatory_window` (`holdout_exposed_count` must remain 0, `confirmatory_window_status=NOT_STARTED`).
3. Read execution auth: `configs/research_v6_execution_amendment_1.json` (effective) and `configs/research_v6_selection_authorization_1.json` (note frozen-file fields vs versioned binding `configs/research_v6_selection_execution_binding_1.json` and filesystem `src/v6_campaign/`).
4. Run `python3 scripts/verify_v6_execution.py`; record `ok`, `failures`, `manifest_hash`/`recomputed_manifest_hash` (must match), `v6_execution_path_canonical_digest`, `evaluation_may_not_start_before_utc`.
5. Confirm data gate RESOLVED (do not re-run probe) and `research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` ABSENT unless a bounded selection run was explicitly authorized+completed.
6. Prompt review: emit `NO_PROMPT_CHANGE_JUSTIFIED` or a concrete, evidence-backed change proposal (no prompt-level defect known).

## Current verified state (2026-11-08T05:09Z — re-verify)

- branch `main`, HEAD `607c4e114cc8cbd0676d54cc99424f1e83595982` (`607c4e114`) == origin/main, clean. Prior handoff recorded `8c4661f82499ea6725f310170c3f7f6a0528c032` (`8c4661f8`); delta = 2 non-substantive checkpoint commits, no substantive change.
- Cohort (`continuous_universe_state.json`): `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 excluded (GHOUSDT/binance_spot_unavailable, ETHFIUSDT/insufficient_hourly_history, XDCUSDT/binance_spot_unavailable, NIGHTUSDT/insufficient_hourly_history, PYTHUSDT/insufficient_hourly_history, TIAUSDT/insufficient_hourly_history, BDXUSDT/binance_spot_unavailable, FLRUSDT/binance_spot_unavailable, QUSDT/binance_spot_unavailable, TRUMPUSDT/insufficient_hourly_history, PENGUUSDT/insufficient_hourly_history, 币安人生USDT/insufficient_hourly_history, YLDSUSDT/binance_spot_unavailable). `holdout_exposed_count==0`, `confirmatory_window_status=NOT_STARTED`.
- Exec auth (effective, `configs/research_v6_execution_amendment_1.json`): `selection_authorization_present==true` (bound to `configs/research_v6_selection_authorization_1.json`, manifest `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, sha `14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, run `v6-selection-20261022`, campaign `v6-campaign`); `candle_fetch/confirmatory_evaluation/execution/grid_run/second_run` all `false`. Selection auth file: `authorized==true`, `max_runs==1`, frozen file still records `v6_execution_path_exists==false`, `execution_path_digest==null` (hash-bound). Versioned binding `configs/research_v6_selection_execution_binding_1.json` present: `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`, manifest `b9090900d1ef6304b022ab18332e01ebea8c0f2a1e259710565c5006f3c6332e`, binds `src/v6_campaign` digest `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72` to frozen auth; `src/v6_campaign/` present, `src/v6_confirmatory/` absent.
- `verify_v6_execution.py` -> `ok:true`, `failures:[]` (exit 0). manifest/recomputed `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `v6_execution_path_canonical_digest` `37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. `selection_authorization_campaign_id=v6-campaign`, `run_id=v6-selection-20261022`, `manifest_hash=f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`. `evaluation_may_not_start_before_utc=2027-01-20T02:00:00Z`.
- Data gate RESOLVED: `holdout_exposed_count==0`, `confirmatory_window_status=NOT_STARTED`.
- `research_state/v6_selection_ledger.json` ABSENT. `research/v6_selected_configurations_manifest.json` ABSENT. v6 selection NOT started; single authorized run unconsumed.
- Prompt review: `NO_PROMPT_CHANGE_JUSTIFIED`.

## Unresolved blockers (fail-closed)

1. **BRAIN-003 confirmatory campaign** blocked until `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0. Preflight not eligible (6 blockers): `src/v6_confirmatory` absent (`BLOCKED_ENGINEERING`), confirmatory scope contract (`BLOCKED_PROTOCOL_CONFLICT`), confirmatory retrieval pagination 1 vs 3 pages for 2160 candles (`BLOCKED_PROTOCOL_CONFLICT`), `research/v6_selected_configurations_manifest.json` not published (`BLOCKED_EXTERNAL`), separate confirmatory authorization not published (`NOT_AUTHORIZED`), confirmatory window benchmark not published (`BLOCKED_EXTERNAL`).
2. **v6 selection run** not executed. Implementation binding in place (`configs/research_v6_selection_execution_binding_1.json`, preflight `selection_source_binding` PASS); gate checks pass; single authorized run (`v6-selection-20261022`, campaign `v6-campaign`, `max_runs==1`) unconsumed. Consuming it is a substantive action — reserve for a later session with explicit authorization. Do not run it here.

## Next precise action

Re-run this standing task and refresh `research_state/agent_handoff.md` and this file with fresh-verified values. Confirm `holdout_exposed_count==0`/`confirmatory_window_status=NOT_STARTED`; confirm selection ledger/manifest absent; confirm selection binding present and verifier `selection_source_binding`/digests PASS; emit `NO_PROMPT_CHANGE_JUSTIFIED` unless a concrete prompt defect is found. Both blockers remain fail-closed: BRAIN-003 until `2027-01-20T02:00:00Z`, and v6 selection execution reserved for a later session. Do not commit unless explicitly asked.

(2026-11-08T05:09Z re-verify: HEAD `607c4e114` == origin/main, +2 non-substantive checkpoints vs `8c4661f8`, clean; cohort 6 pending, cohort 5 completed (13 excluded); holdout 0 / NOT_STARTED; exec auth effective, binding in place; verifier ok:true MATCH; ledger/selection manifest absent; `NO_PROMPT_CHANGE_JUSTIFIED`.)

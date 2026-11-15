# Next agent task (copy/paste)

## Initial task message

You are the next agent in the chain. Read `research_state/agent_handoff.md` first, then complete the standing task below. This is a stable fail-closed checkpoint, not a request to change the protocol or make the verifier pass. Do not consume the authorized v6 run, expose holdout/confirmatory data, or edit frozen artifacts without explicit user authorization. Do not commit unless explicitly requested.

**Summary:** The frozen v6 execution identity mismatch remains unresolved (2 verifier failures, unchanged from 10:13Z check). Resolving it requires explicit user authorization to edit frozen artifacts; do not patch it by editing frozen artifacts or state. Cohort v5 is complete, holdout exposure is 0, and the single authorized v6 selection run is still unconsumed.

**Current state (re-verified 2026-11-15T10:13Z):** `main` @ `55481e44b321a192bea83ec7e6db1a4d30b86ec8` == `origin/main` == `@{u}` (`0 0`). HEAD advanced from prior handoff receipt `cb08485c03afa74ca306460e7cec277d4e7b8fb1`; intervening diff = continuity-doc checkpoint only. Tracked tree clean at receipt/check; after this handoff update expect only `.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md` modified.

`PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 2 failures:
1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key values: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.

Identity (source of record): binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`, `code_identity.run_code_identity==cfd1cc2d034db5b5736fb3f26fb690fd773533f4e1f7144feb2bc857b46b8b7e`, `hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `execution_path_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`. Authorization `authorized_run.code_identity`: `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`), `max_runs==1`, unconsumed, `authorization_status==PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN`. `research_state/campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (live/rotating). **`NO_PROMPT_CHANGE_JUSTIFIED`.**

No drift: `continuous_universe_state.json` `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`; `checkpoint_v5.json` `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`. v6 not started (`v6_selection_ledger.json`, `v6_selected_configurations_manifest.json`, `src/v6_confirmatory/` absent; `src/v6_campaign/` present; authorization unconsumed). `./check_progress.sh` -> `497664/497664`, `report_exists: True`, completed v0..v5, next 6.

## Task (standing checks + execution-integrity re-verification only)

1. Confirm `git rev-parse HEAD` == `origin/main` == `@{u}`. Record HEAD, upstream counts, and tracked-tree state. At receipt expect a clean tree.
2. Run `PYTHONPATH=src python3 scripts/verify_v6_execution.py`; report exact `ok`/exit, `failures`, and key digests/hashes (`manifest_hash` vs `recomputed_manifest_hash`, `canonical_hashed_set_digest`, `v6_execution_path_canonical_digest`, `selection_authorization_*`, `effective_execution_authorization_source`). Quote any change from the two known failures verbatim.
3. Confirm no cohort/state drift (`continuous_universe_state.json` `current_cycle_id`/`updated_utc`, `next_cohort_index`, `current_cohort.cohort_index`/`completed`) and `checkpoint_v5.json` `holdout_exposed_count==0`. Confirm v6 has not started (`v6_selection_ledger.json`, `v6_selected_configurations_manifest.json`, `src/v6_confirmatory/` absent; authorization unconsumed).
4. Read binding `code_identity.run_code_identity` from `configs/research_v6_selection_execution_binding_1.json` and keep it distinct from the authorization's `run_code_identity`. Report `campaign_authorization.json` `code_hash` as a rotating live value.
5. **Do NOT** consume the authorized v6 run (`run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`) and **Do NOT** expose holdout/confirmatory data before `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0.
6. **Do NOT** edit frozen v6 execution/binding/authorization artifacts or `campaign_authorization.json` to hide the mismatch without explicit user authorization.
7. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file with the new timestamp, HEAD, verifier result, cohort/v6 state, and diffs. Commit **only** if explicitly requested. Keep changes minimal/mechanical and condense older handoff sections when needed.

## If the user wants the mismatch resolved (requires their explicit go-ahead)

Mechanical but edits frozen artifacts — needs explicit authorization naming artifacts:
- `configs/research_v6_execution.json` `code_hash_constraint` records snapshot/other hashes vs live canonical `8cd17522...` (failures 1–2).
- Binding is already live-bound (`hashed_set_digest==8cd17522...`, `run_code_identity==cfd1cc2d...`); clearing remaining failures requires re-pointing protocol constraint to `8cd17522...`, recomputing protocol `manifest_hash`, and any authorized amendments as needed — substantive frozen-artifact changes. Do not do without explicit user instruction.

**Hard constraints:** no BRAIN-003/holdout exposure before `2027-01-20T02:00:00Z`; no consuming `v6-selection-20261022`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.

(End of file)

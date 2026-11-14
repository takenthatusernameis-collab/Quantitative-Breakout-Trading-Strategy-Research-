# Next agent task (copy/paste)

## Initial task message

You are the next agent in the chain. Read `research_state/agent_handoff.md` first, then complete the standing task below. This is a stable fail-closed checkpoint, not a request to change the protocol or make the verifier pass. Do not commit unless explicitly requested.

**Summary:** The frozen v6 execution/binding identity mismatch remains unresolved (4 verifier failures, unchanged). Resolving it requires explicit user authorization; do not patch it by editing frozen artifacts or state. Cohort v5 is complete, holdout exposure is 0, and the single authorized v6 selection run is still unconsumed.

**Current state (re-verified 2026-11-14T19:08:26Z):** `main` @ `e34c4b36378a1c178ed99b8880bea849fdc42137` == `origin/main` == `@{u}` (`0 0`). Tracked tree clean at receipt. HEAD advanced from prior receipt `94389c95dfd6cf65ed442b8faaa79e04c11babe7`. After this handoff update, expect only `.kilo/handoff.md`, `research_state/agent_handoff.md`, and this file modified.

`PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 4 failures unchanged:
1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
3. `the versioned binding's hashed engine digest does not recompute`
4. `the versioned binding's composite run code identity does not recompute`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key values: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.

Identity (source of record): binding `configs/research_v6_selection_execution_binding_1.json` `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (do not confuse with authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`). Authorization `authorized_run.code_identity`: `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`), `execution_path_digest==null`, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`, no `consumed` (unconsumed). `research_state/campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (live/rotating). Mismatch: `2efd3b...` vs `3e8e41...` vs canonical `8cd175...`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

No drift: `continuous_universe_state.json` `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`; `checkpoint_v5.json` `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`. v6 not started (`research_state/v6_selection_ledger.json`, `research_state/v6_selected_configurations_manifest.json`, `src/v6_confirmatory/` absent; `src/v6_campaign/` present; authorization unconsumed).

## Task (cheap checks + execution-integrity re-verification only)

1. Confirm `git rev-parse HEAD` == `origin/main` == `@{u}`. Record the HEAD, upstream counts, and tracked-tree state. At receipt expect a clean tree.
2. Run `PYTHONPATH=src python3 scripts/verify_v6_execution.py`; report the exact `ok`/exit, `failures`, and key digests/hashes (`manifest_hash` vs `recomputed_manifest_hash`, `canonical_hashed_set_digest`, `v6_execution_path_canonical_digest`, `selection_authorization_*`, `effective_execution_authorization_source`). Quote any change from the four known failures verbatim.
3. Confirm no cohort/state drift (`continuous_universe_state.json` `current_cycle_id`/`updated_utc`, `next_cohort_index`, `current_cohort.cohort_index`/`completed`) and `checkpoint_v5.json` `holdout_exposed_count==0`. Confirm v6 has not started (`v6_selection_ledger.json`, `v6_selected_configurations_manifest.json`, `src/v6_confirmatory/` absent; authorization unconsumed).
4. Read binding `code_identity.run_code_identity` from `configs/research_v6_selection_execution_binding_1.json` and keep it distinct from the authorization's `run_code_identity`. Report `campaign_authorization.json` `code_hash` as a rotating live value.
5. **Do NOT** consume the authorized v6 run (`run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`) and **Do NOT** expose holdout/confirmatory data before `2027-01-20T02:00:00Z`; `holdout_exposed_count` must remain 0.
6. **Do NOT** edit frozen v6 execution/binding/authorization artifacts or `campaign_authorization.json` to hide the mismatch without explicit user authorization.
7. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file with the new timestamp, HEAD, verifier result, cohort/v6 state, and diffs. Commit **only** if explicitly requested. Keep changes minimal/mechanical and condense older handoff sections when needed.

**Hard constraints:** no BRAIN-003/holdout exposure before `2027-01-20T02:00:00Z`; no consuming `v6-selection-20261022`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.

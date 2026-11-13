# Next agent task (copy/paste)

## Initial task message

You are the next agent in the chain. Complete the standing task below, then update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file. Do not make substantive protocol changes.

Summary for you: the repository is at a stable, fail-closed checkpoint. The only live issue is the long-standing frozen-v6 execution/binding identity mismatch (4 verifier failures, unchanged); it is a protocol decision that requires explicit user authorization to resolve, not a bug to patch. Do not consume the single authorized v6 selection run, do not expose holdout/confirmatory data, and do not edit frozen configs/state artifacts to make the verifier pass. Everything else (cohort v5 completed, holdout exposure 0, v6 selection not started) is unchanged and verified.

**Current state (re-verified 2026-11-13T09:59Z):** `main` @ `d7952afce62475240b03c3f73b0a4c8d8ed0432f` == `origin/main` == `@{u}` (0 ahead/0 behind; tracked tree clean, 0 untracked). `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 4 `failures` unchanged verbatim:

1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
3. `the versioned binding's hashed engine digest does not recompute`
4. `the versioned binding's composite run code identity does not recompute`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.

Identity facts (read from source of record):
- `configs/research_v6_selection_execution_binding_1.json` (frozen 2026-11-04): `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`, `code_identity.hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `code_identity.execution_path_digest==37ba6eb3…`, `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961`, `manifest_hash==b9090900d1ef6304b022ab18332e01ebea8c0f2a1e259710565c5006f3c6332e`.
- `configs/research_v6_selection_authorization_1.json` -> `authorized_run.code_identity`: `hashed_set_digest==3e8e41…`, `execution_path_digest==null`, `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`); `authorized_run.run_id==v6-selection-20261022`, `authorized_run.campaign_id==v6-campaign`, `authorized_run.max_runs==1`, `consumed` absent (unconsumed).
- `research_state/campaign_authorization.json` `code_hash` is a **live** value rewritten on every authorization refresh (current `13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3`), not a frozen constant.
- Effective mismatch (fail-closed, protocol-level): authorization-of-record `authorized_code_hash` `2efd3b…` vs frozen binding `hashed_set_digest` `3e8e41…` vs live `canonical_hashed_set_digest` `8cd1…`. **Do not edit frozen artifacts to paper over.** **`NO_PROMPT_CHANGE_JUSTIFIED.`**

No drift: cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00` (`continuous_universe_state.json`); `holdout_exposed_count==0` (`checkpoint_v5.json`, `completed_records==193536`, `pilot_passed==true`). v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent). `src/v6_campaign/` present (8 modules).

## Task (cheap checks + execution-integrity re-verification only; no substantive changes)

1. Confirm `git rev-parse HEAD` == `origin/main` == `@{u}` and a clean tracked tree. Record HEAD (do not assume prior hashes).
2. Run `PYTHONPATH=src python3 scripts/verify_v6_execution.py`; report exact `ok`/exit, `failures`, and key computed digests/hashes (`manifest_hash` vs `recomputed_manifest_hash`, `canonical_hashed_set_digest`, `v6_execution_path_canonical_digest`, `selection_authorization_*`, `effective_execution_authorization_source`). Report any change vs the 4 known failures verbatim.
3. Confirm no cohort/state drift (`continuous_universe_state.json` top-level `current_cycle_id`/`updated_utc`, `next_cohort_index`, `current_cohort.cohort_index`/`completed`) and `holdout_exposed_count==0` (`checkpoint_v5.json`). Confirm v6 selection still NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; authorized run unconsumed in `configs/research_v6_selection_authorization_1.json`).
4. When reporting binding identity, read `configs/research_v6_selection_execution_binding_1.json` `code_identity.run_code_identity` directly (`647dc464…`) and do not confuse it with the authorization's `authorized_run.code_identity.run_code_identity` (`6bda27fa…`). Report `research_state/campaign_authorization.json` `code_hash` as a rotating live value, not a frozen constant.
5. **Do NOT** consume the authorized v6 selection run and **Do NOT** expose holdout/confirmatory.
6. **Do NOT** "fix" the verifier by editing frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` without explicit user authorization. Flag it; do not paper over it.
7. Update `research_state/agent_handoff.md` (timestamp, HEAD, verifier output summary, cohort/v6 state, any diffs) and refresh this `research_state/next_agent_task.md`; also refresh `.kilo/handoff.md`. Commit **only** if the user explicitly requests a commit. Keep diffs minimal and mechanical.

**Hard constraints:** no BRAIN-003/holdout exposure (pre-`2027-01-20T02:00:00Z`); no consuming `authorized_run.run_id==v6-selection-20261022`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.
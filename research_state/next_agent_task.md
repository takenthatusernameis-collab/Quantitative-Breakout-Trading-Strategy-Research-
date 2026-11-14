# Next agent task (copy/paste)

## Initial task message

You are the next agent in the chain. Complete the standing task below, then update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file. Do not make substantive protocol changes. Do not commit unless explicitly requested.

**Summary:** Stable fail-closed checkpoint. Only live issue: long-standing frozen-v6 execution/binding identity mismatch (4 verifier failures, unchanged); protocol decision requiring explicit user authorization to resolve — not a bug to patch. Do not consume the single authorized v6 selection run, do not expose holdout/confirmatory, and do not edit frozen configs/state to make the verifier pass. Cohort v5 completed, holdout exposure 0, v6 selection not started — unchanged.

**Current state (re-verified 2026-11-14T14:25:10Z):** `main` @ `f85bb4db272b8be21d9ddc3aca5cefa0fad59ee1` == `origin/main` == `@{u}` (`0 0`). Tracked tree clean at receipt. HEAD advanced from prior handoff `b8bfc2b654fadd0624ff4ae6e7446109dc727799` via a checkpoint commit carrying only continuity docs. After this handoff update, expect only `.kilo/handoff.md`, `research_state/agent_handoff.md`, and this file modified.

`PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 4 failures unchanged:
1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
3. `the versioned binding's hashed engine digest does not recompute`
4. `the versioned binding's composite run code identity does not recompute`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key digests: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.

Identity (source of record): binding `configs/research_v6_selection_execution_binding_1.json` `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`); authorization `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`; top-level `authorized_code_hash` absent/`None`), `execution_path_digest==null`, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`, no `consumed` field (run unconsumed). `research_state/campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` is **live** (rotates on refresh). Mismatch (fail-closed): `2efd3b...` vs `3e8e41...` vs live canonical `8cd175...`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

No drift: `continuous_universe_state.json` `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`; `checkpoint_v5.json` `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`. v6 NOT started (`v6_selection_ledger.json`/`v6_selected_configurations_manifest.json`/`src/v6_confirmatory/` absent; `src/v6_campaign/` present; run unconsumed).

## Task (cheap checks + execution-integrity re-verification only)

1. Confirm `git rev-parse HEAD` == `origin/main` == `@{u}`. Record tracked-tree state/HEAD (do not assume prior hashes); at receipt only the three continuity docs should be modified.
2. Run `PYTHONPATH=src python3 scripts/verify_v6_execution.py`; report exact `ok`/exit, `failures`, and key digests/hashes (`manifest_hash` vs `recomputed_manifest_hash`, `canonical_hashed_set_digest`, `v6_execution_path_canonical_digest`, `selection_authorization_*`, `effective_execution_authorization_source`). Report any change vs the 4 known failures verbatim.
3. Confirm no cohort/state drift (`continuous_universe_state.json` `current_cycle_id`/`updated_utc`, `next_cohort_index`, `current_cohort.cohort_index`/`completed`) and `checkpoint_v5.json` `holdout_exposed_count==0`. Confirm v6 not started (`v6_selection_ledger.json`/`v6_selected_configurations_manifest.json`/`src/v6_confirmatory/` absent; run unconsumed).
4. Read binding `code_identity.run_code_identity` directly from `configs/research_v6_selection_execution_binding_1.json` (`647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961`) — do not confuse with authorization's `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`. Report `campaign_authorization.json` `code_hash` as rotating live value.
5. **Do NOT** consume authorized v6 run and **Do NOT** expose holdout/confirmatory.
6. **Do NOT** edit frozen v6 execution/binding/authorization or `campaign_authorization.json` to paper over mismatch without explicit user authorization.
7. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file (timestamp, HEAD, verifier summary, cohort/v6 state, diffs). Commit **only** if explicitly requested. Keep diffs minimal/mechanical; condense older handoff sections when large.

**Hard constraints:** no BRAIN-003/holdout exposure (pre-`2027-01-20T02:00:00Z`); no consuming `v6-selection-20261022`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.

(End of file)

# Agent handoff (durable, single source of truth)

This file is the authoritative cross-session handoff. Keep it concise and current.

## Current State (re-verified 2026-11-11T17:04:27Z UTC)
- Branch: `main`; HEAD `2db22268e32ac2dfe7cab2ffa400f52f6a83ab25` == `origin/main` == `@{u}`. Tracked tree clean at check (before this handoff update). (HEAD advanced from prior recorded `d47bb1b48a4c40698229d09f96693b1d04b6fbbd`; that prior commit was a handoff checkpoint touching only `research_state/agent_handoff.md` and `research_state/next_agent_task.md`.)
- Verifier (`PYTHONPATH=src python3 scripts/verify_v6_execution.py`): **`ok: false` (exit 1, fail-closed)**, 4 `failures` unchanged verbatim:
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- Verifier re-run this session: `ok:false`, exit 1, same 4 failures verbatim; `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key computed digests/hashes unchanged: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- Root cause (fail-closed, protocol-level): frozen `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` vs `research_state/campaign_authorization.json` `code_hash==22bacfb89a469cc9eaa3ff4198510135910756721c69cda09b78d784d15c0c06`; binding hashed-engine/composite digests no longer recompute. **Do not edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over this without explicit user authorization.**
- Binding/authorization: `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; single authorized run in `configs/research_v6_selection_authorization_1.json` — `authorization_status==PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN`, `authorized_run.run_id==v6-selection-20261022`, `authorized_run.campaign_id==v6-campaign`, `authorized_run.max_runs==1`, `consumed` absent top-level and in `authorized_run` — **unconsumed**.
- Cohort (`research_state/continuous_universe_state.json`): **no drift** — `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true` (13 excluded), `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`.
- Holdout (`research_state/checkpoint_v5.json`): `holdout_exposed_count==0` (`completed_records==193536`, `pilot_passed==true`, `code_hash==8a63085e0df880c8d74de5c8f19d6338dd9330ee42c632882634f185ef4948c2`, `protocol_hash==55e839f7fe82201ec9ef9a699c081a903255669c394f494ad147f3f72e72dec2`).
- v6 selection: **NOT started** (live-confirmed). Absent: `research_state/v6_selection_ledger.json`, `research/v6_selected_configurations_manifest.json`, `src/v6_confirmatory/`. `src/v6_campaign/` exists (implementation path present). **Holdout/confirmatory exposure must remain 0.**

## COMPLETED — this session (2026-11-11T17:04:27Z UTC)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change.
- Confirmed HEAD `2db22268e32ac2dfe7cab2ffa400f52f6a83ab25` == `origin/main` == `@{u}`; tracked tree clean at check. (HEAD advanced from prior recorded `d47bb1b48a4c40698229d09f96693b1d04b6fbbd`; that prior commit was a handoff checkpoint touching only `research_state/agent_handoff.md` and `research_state/next_agent_task.md`.)
- Verifier re-run: `ok:false` exit 1, same 4 failures verbatim; `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH); all key computed digests/hashes unchanged (`canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`).
- Cohort/v6/holdout state confirmed unchanged against live files (no drift; cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true` (13 excluded), `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`; `holdout_exposed_count==0` `checkpoint_v5.json` `completed_records==193536` `pilot_passed==true`; binding `IMPLEMENTATION_BOUND_NOT_RUN`; single authorized run `v6-selection-20261022`/`v6-campaign`, `max_runs==1`, unconsumed (`consumed` absent in `configs/research_v6_selection_authorization_1.json`); `v6_selection_ledger.json`/`v6_selected_configurations_manifest.json`/`src/v6_confirmatory/` absent; `src/v6_campaign/` present).
- Frozen artifacts unchanged. No fix applied to verifier. Did not consume authorized v6 selection run; did not expose holdout/confirmatory. Committed handoff updates as `59e74f0b71d719157d8aaaa7e46f02f4505e9f1f` then `c8e8e6dc6d56531cf8f48ad5658ea7ee9b42db74` (only `research_state/agent_handoff.md` + `research_state/next_agent_task.md`).

**Change vs prior handoff:** HEAD `c8e8e6dc6d56531cf8f48ad5658ea7ee9b42db74` (prior recorded `2db22268e32ac2dfe7cab2ffa400f52f6a83ab25`); verifier/cohort/v6/holdout/frozen artifacts unchanged; v6-not-started re-confirmed live.

## Prompt review
- `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — previous sessions (summary)
- 2026-11-11T17:04:27Z: HEAD `2db22268e32ac2dfe7cab2ffa400f52f6a83ab25`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T16:55:23Z: HEAD `d47bb1b48a4c40698229d09f96693b1d04b6fbbd`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T16:53:46Z: HEAD `bc3ce06907addd8405301c83fdf4beb5f62f62bc`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T16:43:32Z: HEAD `0912a260119de2ebe85a34815916104a812ce8ed`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T16:12:39Z: HEAD `2ae0b07f701af5365318596ed9715a4324bb666f`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T16:02:36Z: HEAD `2d6b626bb35838fd1b2e0bf921a3e714cd84cca7`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:55:47Z: HEAD `a138b505e7d8ca03a9427552e6ba184ea1ef3c7e`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:48:53Z: HEAD `a2e8d1705231c4ae7dc816e0b83bacdfc85eda3d`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:36:30Z: HEAD `ec02ce0121c486e48e32741f85250d725846c303`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:31:44Z: HEAD `6a27325a848e6b4d80070a5ad4a832ecc7689dbf`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:09:17Z: HEAD `bd6cf428489434b9fcdb67cf6913e7582ea3cec6`; verifier/cohort/v6/holdout unchanged (same 4 failures).
- 2026-11-11T15:03:00Z: HEAD `3b2530112556dc161b8a0db185b3ca16867004b2`; verifier/cohort/v6/holdout unchanged.
- 2026-11-11T15:00:00Z: HEAD `031e5f446b1cc63c932513f80242c6f72d7cf8cb`; verifier/cohort/v6/holdout unchanged.
- 2026-11-11T14:52:40Z: HEAD `96d5c2732cf682d29a9a27a6d388562ea10e`; verifier/cohort/v6/holdout unchanged.
- 2026-11-11T14:51:28Z: HEAD `3d2d578d9b9e373ac4f4d592ded3b504da309c22`; verifier/cohort/v6/holdout unchanged.
- 2026-11-11T14:47:46Z: HEAD `544fb47bf06fb5ff8fad27040f840c0767e3f315`; verifier/cohort/v6/holdout unchanged.

Next task: see `research_state/next_agent_task.md`.

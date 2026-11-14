# Agent handoff (durable)

This file is the repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-14T12:18:07Z @ `17caae1b48b9b6a0ad0f28ae6f8616eede077147` (kilo, standing checks + v6 execution-integrity re-verification; prior durable task complete)

**Completed:** completed the prior durable task in `research_state/next_agent_task.md`: repeated standing repository checks at live HEAD `17caae1b48b9b6a0ad0f28ae6f8616eede077147`, re-ran the v6 execution-integrity verifier, and re-confirmed cohort, authorization, holdout, and v6 selection state. No drift vs 12:14:30Z block (`f9611589617b47828eeb121876052c8dde9051e9`); no substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed; no commit made by this session. After this handoff update, only `.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md` should differ from HEAD.

### Git
- `git rev-parse HEAD` == `origin/main` == `@{u}` == `17caae1b48b9b6a0ad0f28ae6f8616eede077147` (main). `rev-list --left-right --count HEAD...origin/main` == `0 0`. Tracked tree clean at receipt (no uncommitted changes). After this handoff update, only `.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md` should differ from HEAD.

### Verifier
- Command: `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed).
- Failures (4, unchanged verbatim):
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- Computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- No change vs prior recorded values.

### Identity (source of record; no drift)
- `configs/research_v6_selection_execution_binding_1.json` (frozen 2026-11-04, `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `code_identity.execution_path_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (binding; distinct from authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`).
- `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `execution_path_digest==null`, `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`authorized_code_hash_status==RETAINED_AS_VALUE_OF_RECORD`); `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`; no `consumed` field (no ledger exists, so the run is unconsumed).
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (`authorized==true`, `authorized_at_utc==2026-11-12T18:12:22.943361+00:00`) — **live, rotates on refresh**.
- Mismatch (fail-closed): auth-of-record `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` vs frozen binding `3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff` vs live canonical recomputed digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. Do not edit frozen artifacts to paper over. `NO_PROMPT_CHANGE_JUSTIFIED`.

### Cohort / v6 / holdout (no drift)
- `research_state/continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `updated_utc==2026-10-21T21:45:00+00:00`.
- `research_state/checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`.
- v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present; run unconsumed, `no_execution_in_this_session==true`). No holdout/confirmatory exposed.
- Authorization fields live under `authorized_run` (`run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`); no top-level `run_id`/`campaign_id`.

### Verification scope / constraints
- Repository/docs continuity only; no protocol implementation or research execution. v6 execution verifier run with fail-closed result unchanged.
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign`; do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` without explicit user authorization.

### Next task
- See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-14T12:14:30Z (`f9611589617b47828eeb121876052c8dde9051e9`): identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-14T08:28:30Z–11:28:34Z (21 sessions, `aa420f63...`→`7a2c24ed0f41a48996a3ec676d67eefb6fa2cba7`): identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- Earlier sessions 05:26Z–08:28:30Z (19 sessions across 4+ blocks): identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.

(End of file)
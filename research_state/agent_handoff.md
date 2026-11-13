# Agent handoff (durable)

This file is the repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-13T15:18Z @ `95916152b13a2df83bd2c8a073625b9f6ffced0e` (kilo)

**Completed:** standing cheap checks + v6 execution-integrity re-verification. No substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed.

### Git
- `git rev-parse HEAD` == `origin/main` == `@{u}` == `95916152b13a2df83bd2c8a073625b9f6ffced0e` (`chore(kilo): checkpoint agent session`, `main`). 0 ahead / 0 behind.
- `git status --porcelain -uall` empty at check start (tracked tree clean). HEAD advanced from prior recorded `1c0187e4e407377688c31a6ab953b1d1ccb576d9`; the only intervening change is that checkpoint commit touching the three handoff docs (`.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`) — no substantive diff. Handoff docs updated this session (uncommitted; no commit requested).

### Verifier
- Command: `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed).
- Failures (4, unchanged verbatim):
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- Computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.

### Identity (read from source of record; no drift)
- `configs/research_v6_selection_execution_binding_1.json` (frozen 2026-11-04, `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `code_identity.execution_path_digest==37ba6eb3…`, `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961`, `manifest_hash==b9090900d1ef6304b022ab18332e01ebea8c0f2a1e259710565c5006f3c6332e`.
- `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `hashed_set_digest==3e8e41…`, `execution_path_digest==null`, `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`); `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent (unconsumed).
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (`authorized==true`, `authorized_at_utc==2026-11-12T18:12:22.943361+00:00`) — **live value, rotates on refresh**.
- Effective mismatch (fail-closed): auth-of-record `2efd3b…` vs frozen binding `3e8e41…` vs live `8cd1…`. Do not edit frozen artifacts to paper over. `NO_PROMPT_CHANGE_JUSTIFIED`.

### Cohort / v6 / holdout (no drift)
- `continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `updated_utc==2026-10-21T21:45:00+00:00`.
- `checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`.
- v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present 8 modules: `__init__.py`, `benchmark.py`, `data.py`, `errors.py`, `identity.py`, `runner.py`, `scope.py`, `units.py`). Authorized run unconsumed.

### Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

### Next task
See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-13T15:18Z @ `95916152b13a2df83bd2c8a073625b9f6ffced0e`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from `1c0187e4e4…` via checkpoint commit (no substantive diff).
- 2026-11-13T15:14Z @ `1c0187e4e407377688c31a6ab953b1d1ccb576d9`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from `800643eb5d…` via checkpoint commit (no substantive diff).
- 2026-11-13T15:11Z @ `800643eb5d2e1a24824b5d818ecd9471f68574e8`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T15:11Z @ `0329670921d9e0f87fe19127c34cec3dd0c46bf7`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T15:08Z @ `ddd38067df5769111a9b72067bb767f0519303f1`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T15:05Z @ `17827543dcf923f0229545888790063170d1746d`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T15:02Z @ `6956cf89b78ce017264be694e8421e0bdf6f5421`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- Earlier: repeated identical standing-check results (4 failures unchanged, manifest match, no drift, v6 unconsumed/not started).

(End of file)

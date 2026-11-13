# Agent handoff (durable)

This file is the repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-13T22:49Z @ `dd118a6f82d38ecef805f5d08da40a73f3877ae0` (kilo)

**Completed:** standing cheap checks + v6 execution-integrity re-verification. No substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed.

### Git
- `git rev-parse HEAD` == `origin/main` == `@{u}` == `dd118a6f82d38ecef805f5d08da40a73f3877ae0` (main). 0 ahead / 0 behind.
- Tracked tree clean at check start. HEAD advanced from prior recorded `cbf53e54f65ce0cbd54566b5fc87dc0d2512c3a9` (prior checkpoint commit). Handoff docs updated this session (uncommitted; no commit requested).

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
- `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `hashed_set_digest==3e8e41…`, `execution_path_digest==null`, `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`); `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent (unconsumed). `no_execution_in_this_session==true`.
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (`authorized==true`, `authorized_at_utc==2026-11-12T18:12:22.943361+00:00`) — **live value, rotates on refresh**.
- Effective mismatch (fail-closed): auth-of-record `2efd3b…` vs frozen binding `3e8e41…` vs live `8cd1…`. Do not edit frozen artifacts to paper over. `NO_PROMPT_CHANGE_JUSTIFIED`.

### Cohort / v6 / holdout (no drift)
- `research_state/continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `updated_utc==2026-10-21T21:45:00+00:00`.
- `research_state/checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`.
- v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present 8 modules; authorized run unconsumed). No holdout/confirmatory exposed.

### Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

### Next task
See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-13T22:49Z @ `dd118a6f82d38ecef805f5d08da40a73f3877ae0`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `cbf53e54f65ce0cbd54566b5fc87dc0d2512c3a9`. Handoff docs updated this session (uncommitted; no commit requested).
- 2026-11-13T22:47Z @ `cbf53e54f65ce0cbd54566b5fc87dc0d2512c3a9`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `a3c827e44fb4ed8d1841e09989a4b032883ca950` via checkpoint commit (handoff-docs-only diff; 3 files / +11/-12). Handoff docs updated this session (uncommitted; no commit requested).
- 2026-11-13T22:44Z @ `a3c827e44fb4ed8d1841e09989a4b032883ca950`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `1ccfca99fb13da62d54a0a90efe9ed123e818359`. Handoff docs updated this session (uncommitted; no commit requested).
- 2026-11-13T22:30Z @ `46a515d4bb2cfde295009c5ecdf39d0a6da1ce83`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `9d610911f99f27116b6380aa84a02636f016a0c7` via checkpoint commit touching the three handoff docs only — `git diff --stat 9d610911f99f27116b6380aa84a02636f016a0c7 46a515d4bb2cfde295009c5ecdf39d0a6da1ce83` = 3 files / +9/-8, no substantive diff. Handoff docs updated this session (uncommitted; no commit requested).
- 2026-11-13T22:24Z @ `9d610911f99f27116b6380aa84a02636f016a0c7`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `1f0ae697f44be74c38a4739a41bf81917eca85fd` via checkpoint commit (handoff-docs-only diff; 3 files / +9/-8).
- 2026-11-13T21:51Z @ `1f0ae697f44be74c38a4739a41bf81917eca85fd`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `3c321013c946bd2c73fbbfd6c1232593e7b5e780` via checkpoint commit (handoff-docs-only diff; 3 files / +10/-11).
- 2026-11-13T21:48Z @ `3c321013c946bd2c73fbbfd6c1232593e7b5e780`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `5bc911f55f3dbf476d4204e2d04919ca80c4ef07` via checkpoint commit (handoff-docs-only diff; 3 files / +7/-7).
- 2026-11-13T21:45Z @ `5bc911f55f3dbf476d4204e2d04919ca80c4ef07`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `ff42f0ec0168bffb56bcd6798c8859268ed7065f` via checkpoint commit (handoff-docs-only diff; 3 files / +8/-7).
- 2026-11-13T21:41Z @ `5d3643c4f30764e81b64d0bf27579763f09a0a0d`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `0390a39626f270f1a3efb2c19706562c4fec6179` via checkpoint commit (handoff-docs-only diff; 3 files / +9/-11).
- 2026-11-13T20:51Z @ `0390a39626f270f1a3efb2c19706562c4fec6179`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `136c291c48857e29ac64b4cbf7fc0871f46ffb98` via checkpoint commit (handoff-docs-only diff; 3 files / +9/-11).
- 2026-11-13T20:51Z @ `136c291c48857e29ac64b4cbf7fc0871f46ffb98`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `dd60abc33c772bbb53b07f8f24003b0165a63930` via checkpoint commit (handoff-docs-only diff; 3 files / +8/-7).
- 2026-11-13T20:49Z @ `dd60abc33c772bbb53b07f8f24003b0165a63930`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `25d5614d6a942d744ad80d97adcd1e7790328740` via checkpoint commit (handoff-docs-only diff; 3 files / +8/-7).
- 2026-11-13T20:47Z @ `25d5614d6a942d744ad80d97adcd1e7790328740`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `2170e2e4694597c1843d8c3e2478205313bd3821` via checkpoint commit (handoff-docs-only diff; 3 files / +8/-7).
- 2026-11-13T20:44Z @ `2170e2e4694597c1843d8c3e2478205313bd3821`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `a26dffd01cc3735af6f45d661403f2738b6e2666` via checkpoint commit (handoff-docs-only diff; 3 files / +8/-7).
- 2026-11-13T20:39Z @ `a26dffd01cc3735af6f45d661403f2738b6e2666`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. HEAD advanced from prior recorded `f24c3379c0189c2fc0866766773f55f8a9fe7ac3` via checkpoint commit (handoff-docs-only diff; 3 files / +13/-12).
- Earlier 2026-11-13 sessions (17:37Z–19:56Z): identical standing-check results (`ok:false`, same 4 failures, manifest match, no drift, v6 unconsumed/not started); each advanced HEAD by a checkpoint commit with handoff-docs-only changes.

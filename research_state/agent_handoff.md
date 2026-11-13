# Agent handoff (durable)

This file is the repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-13T14:13Z @ `5cdb70b19cc2f8ed18ab6aa45574ccfffb7c256e` (kilo)

**Completed:** standing cheap checks + v6 execution-integrity re-verification. No substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed.

### Git
- `git rev-parse HEAD` == `origin/main` == `@{u}` == `5cdb70b19cc2f8ed18ab6aa45574ccfffb7c256e` (`handoff: record standing v6 integrity check (no change)`, `main`). 0 ahead / 0 behind.
- `git status --porcelain -uall` empty at check start (tracked tree clean). HEAD advanced from prior recorded `bd18baa824c4acd96d63fe101079cbb53f76c617`.

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
- 2026-11-13T14:13Z @ `5cdb70b19cc2f8ed18ab6aa45574ccfffb7c256e`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T14:09Z @ `bd18baa824c4acd96d63fe101079cbb53f76c617`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T14:05Z @ `440eaf96b07707c372d22a397fd3d273e57c25ea`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T14:04Z @ `acd33d25dd400bf572a42623a46d84d45c659dbc`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T14:02Z @ `49ecb415034b34391e9aeb7a3f5ae2107b672d76`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T13:18Z @ `9b90eff124710d27233a2d1ec59cf7266e018fc8`: standing check; `ok:false` exit 1, same 4 failures unchanged; `manifest_hash==recomputed_manifest_hash==9287272…` MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`.
- 2026-11-13T13:14Z @ `f11de7e912434f4dc83c5b9fccfcc12638860227`: same result.
- 2026-11-13T13:13Z @ `878f3ce5f6ae62bc154267d03288f22c309a0e81`: same result.
- 2026-11-13T13:10Z @ `55d696d3ef9bbf2677763f6dae9959958bcac307`: same result.
- 2026-11-13T13:09Z @ `eb4e2777ecf53164c0aaecdb63939c682d7d1b47`: same result.
- 2026-11-13T13:05Z @ `8ed382d031b33924916b94aa35a791a4dbe69e14`: same result.
- 2026-11-13T13:01Z @ `6bf6b11e4851795bb4dc4e7d72fbba9d10f38465`: same result.
- 2026-11-13T12:20Z @ `7c2b0a1ac942a28742a7333c94444e7c2c180f10`: same result.
- 2026-11-13T12:14Z @ `1d0b296febff05f91203db17c1d5d935349de7c5`: same result.
- 2026-11-13T12:09Z @ `89956b33d4cd9cf351264d38d3436f68a8506be7`: same result.
- 2026-11-13T12:06Z @ `c20b1cfee6b4ae5bfeab215a3b8a992677ea8a9c`: same result.
- 2026-11-13T11:25Z @ `7228e9cc95d446e86a27e5707a1b3d33c5fb81d5`: same result.
- Earlier 2026-11-13 and prior: repeated identical standing-check results (4 failures unchanged, manifest match, no drift, v6 unconsumed/not started).

(End of file)
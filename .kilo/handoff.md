# Agent handoff (durable)

Repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-14T14:40:00Z @ `083311109c8a0fc52a86403846956e2a82840df3` (kilo, standing checks + v6 execution-integrity re-verification; prior durable task complete)

**Completed:** repeated standing repository checks at live HEAD `083311109c8a0fc52a86403846956e2a82840df3`, re-ran v6 execution-integrity verifier, re-confirmed cohort/authorization/holdout/v6 selection state. HEAD advanced from prior handoff `f85bb4db272b8be21d9ddc3aca5cefa0fad59ee1` via a checkpoint commit carrying only continuity docs; recorded state and verifier outcome unchanged. No substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed; no commit made in this session. After this update only `.kilo/handoff.md`, `research_state/agent_handoff.md`, and `research_state/next_agent_task.md` differ from HEAD.

### Git
- `HEAD==origin/main==@{u}==083311109c8a0fc52a86403846956e2a82840df3` (main). `rev-list --left-right --count HEAD...origin/main == 0 0`. Tracked tree clean at receipt and after verifier.

### Verifier
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed).
- Failures (4, unchanged verbatim):
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- Key digests: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.

### Identity (source of record; no drift)
- Binding `configs/research_v6_selection_execution_binding_1.json` (frozen, `IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`).
- Authorization `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`; top-level `authorized_code_hash` absent/`None`), `execution_path_digest==null`, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`; no `consumed` field (run unconsumed).
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (live, rotates on refresh; unchanged since prior handoff).
- Mismatch (fail-closed, unchanged): `2efd3b...` vs `3e8e41...` vs live canonical `8cd175...`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

### Cohort / v6 / holdout (no drift)
- `continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`.
- `checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`, `code_hash==8a63085e0df880c8d74de5c8f19d6338dd9330ee42c632882634f185ef4948c2`.
- v6 NOT started: `research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present; run unconsumed, `no_execution_in_this_session==true`. No holdout/confirmatory exposed.

### Constraints
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign`.
- Do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` without explicit user authorization.

### Next task
- See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-14T14:40:00Z (`083311109...`): 4 failures unchanged, manifest MATCH, no drift; HEAD advanced from `f85bb4db2` via checkpoint commit; tracked clean at receipt.
- 2026-11-14T14:25:10Z (`f85bb4db...`): 4 failures unchanged, manifest MATCH, no drift; HEAD advanced from `b8bfc2b65...` via checkpoint commit; tracked clean at receipt.
- 2026-11-14T14:21:19Z (`b8bfc2b65...`): 4 failures unchanged, manifest MATCH; live `campaign_authorization.json` code_hash rotated.
- 2026-11-14T14:17:23Z (`78cae193...`), 13:39:18Z (`1aa3a4cc...`), 13:36:39Z (`f0364e44...`), 13:29:38Z (`203659f1...`), 13:26:15Z (`0be5c4b6...`), 13:25:08Z (`d4007d8f...`), 13:21:20Z (`b7a7de0b...`), 13:19:15Z (`bdbdbcfb...`), 13:18:25Z (`fd550d10...`): same fail-closed checkpoint (HEAD advanced via continuity commits).
- 2026-11-14T12:29:15Z–12:33:43Z & earlier: same repeated fail-closed checkpoint. `NO_PROMPT_CHANGE_JUSTIFIED` throughout.

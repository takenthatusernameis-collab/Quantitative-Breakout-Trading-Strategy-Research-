# Agent handoff (durable)

Repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-14T22:22Z @ `75293091ebefa2f07b26cef571e3e3b209c8541f` (kilo, standing checks + v6 execution-integrity re-verification)

**Completed:** standing repository checks at live HEAD `75293091ebefa2f07b26cef571e3e3b209c8541f`; re-ran the v6 execution-integrity verifier and re-confirmed cohort, authorization, binding, holdout and v6 state. HEAD advanced from prior handoff receipt `cc6a78a5690351cb76480976c148131fc727a720`; `HEAD==origin/main==@{u}==75293091ebefa2f07b26cef571e3e3b209c8541f` (`0 0`). Tracked tree clean at receipt/check. State and verifier outcome unchanged: 4 fail-closed failures, manifest MATCH. No protocol/state change, no frozen artifact edited, no v6 run consumed, no holdout/confirmatory exposed, no commit made in this session. After this update only `.kilo/handoff.md`, `research_state/agent_handoff.md`, and `research_state/next_agent_task.md` differ from HEAD.

### Root cause (traced this session)
All four failures descend from one mismatch. `configs/research_v6_execution.json` `code_hash_constraint` records `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` and `canonical_hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, while the live `canonical_source_digest_v1` over `src/breakout_research` recomputes to `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. The frozen constraint is a snapshot of a *different, earlier* checkout state: the `2efd3b...`/`3e8e41...` pair matches `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity` (`authorized_code_hash`, `hashed_set_digest`), i.e. the authorization's own publication-time values, not the live tree. The binding's internal values (`hashed_set_digest==3e8e41...`, `run_code_identity==647dc464...`) are self-consistent with that earlier snapshot and recompute correctly against themselves; only the protocol's cross-check against the live tree fails. Resolving it requires re-authoring the frozen protocol's `code_hash_constraint` block to the live digest `8cd175...` — a substantive change to a frozen artifact that needs explicit user authorization. `NO_PROMPT_CHANGE_JUSTIFIED`. The `manifest_hash` chain (`928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`) matches and is unaffected.

### Git
- `HEAD==origin/main==@{u}==75293091ebefa2f07b26cef571e3e3b209c8541f` (main). `rev-list --left-right --count HEAD...origin/main == 0 0`. Tracked tree clean at receipt/check. HEAD advanced from receipt `cc6a78a5690351cb76480976c148131fc727a720`. The only tracked-tree change between `cc6a78a56` and `75293091e` is the continuity docs themselves (`.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`).

### Verifier
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed).
- Failures (4, unchanged):
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- Key digests: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.

### Identity (source of record; no drift)
- Binding `configs/research_v6_selection_execution_binding_1.json` (frozen, `IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`).
- Authorization `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`RETAINED_AS_VALUE_OF_RECORD`), `execution_path_digest==null`, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`, `consumed` absent (unconsumed).
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (live/rotating; unchanged at this check).
- Mismatch (fail-closed, unchanged): `2efd3b...` vs `3e8e41...` vs live canonical `8cd175...`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

### Cohort / v6 / holdout (no drift)
- `continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`.
- `checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`.
- v6 NOT started: `research_state/v6_selection_ledger.json` / `research_state/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present; authorization unconsumed. No holdout/confirmatory exposed.
- Progress: `./check_progress.sh` -> `497664/497664` records, `report_exists: True`, completed v0..v5, `next: 6`.

### Constraints
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign`.
- Do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` without explicit user authorization.

### Next task
- See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-14T22:22Z (`75293091ebefa2f07b26cef571e3e3b209c8541f`): HEAD advanced from `cc6a78a5690351cb76480976c148131fc727a720`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T22:20Z (`cc6a78a5690351cb76480976c148131fc727a720`): HEAD advanced from `f76364d4f4387120c6389872e5c343d8e1fd1156`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T22:17Z (`f76364d4f4387120c6389872e5c343d8e1fd1156`): HEAD advanced from `9d600e160f71bced2c30802dd9c59a4171b58924` (intervening checkpoint commit `f76364d4f`); 4 failures unchanged; manifest MATCH.
- 2026-11-14T22:14Z (`9d600e160f71bced2c30802dd9c59a4171b58924`): HEAD advanced from `a36756c5ef50d77fff5e6d1de3843a4af8bb05c6`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T22:10:20Z (`a36756c5ef50d77fff5e6d1de3843a4af8bb05c6`): HEAD advanced from `aeeb12d24d360141096e9c312902c1068db246e1`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T21:23:41Z (`aeeb12d24d360141096e9c312902c1068db246e1`): HEAD advanced from `801524b3341b1653d3c7501de4eceef1303c4494`; 4 failures unchanged; manifest MATCH.
- Earlier 2026-11-14 sessions: repeated fail-closed checkpoints, `campaign_authorization.json` code_hash rotated at 14:21:19Z; repeated `NO_PROMPT_CHANGE_JUSTIFIED`. See git history.
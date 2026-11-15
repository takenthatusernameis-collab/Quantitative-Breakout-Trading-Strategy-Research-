# Agent handoff (durable)

Repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-15T02:06:02Z @ `9564b927ebd3c0d9d584abe226526886c532fece` (kilo, standing checks + v6 execution-integrity re-verification)

**Completed:** standing repository checks at live HEAD `9564b927ebd3c0d9d584abe226526886c532fece`; re-ran the v6 execution-integrity verifier and re-confirmed cohort, authorization, binding, holdout and v6 state. HEAD advanced from prior handoff receipt `773f059da98df2f6fa5b6cc0b6946b72c6c8d0a1` (continuity-doc checkpoint history). `HEAD==origin/main==@{u}==9564b927ebd3c0d9d584abe226526886c532fece` (`0 0`). Tracked tree clean at receipt/check. State and verifier outcome unchanged: 4 fail-closed failures, manifest MATCH. No protocol/state change, no frozen artifact edited, no v6 run consumed, no holdout/confirmatory exposed. After this update only `.kilo/handoff.md`, `research_state/agent_handoff.md`, and `research_state/next_agent_task.md` differ from HEAD.


### Root cause (unchanged, traced previously)
All four failures descend from one mismatch. `configs/research_v6_execution.json` `code_hash_constraint` records `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` and `canonical_hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, while the live `canonical_source_digest_v1` over `src/breakout_research` recomputes to `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. The frozen constraint is a snapshot of a different, earlier checkout state (the `2efd3b...`/`3e8e41...` pair matches `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity` publication-time values). Binding internal values (`hashed_set_digest==3e8e41...`, `run_code_identity==647dc464...`) are self-consistent with that snapshot; only the protocol↔live-tree cross-check fails. Resolving requires re-authoring the frozen protocol's `code_hash_constraint` to live digest `8cd175...` — a substantive change to a frozen artifact needing explicit user authorization. **`NO_PROMPT_CHANGE_JUSTIFIED`.** `manifest_hash` chain (`928727279a...`) matches and is unaffected.


### Git
- `HEAD==origin/main==@{u}==9564b927ebd3c0d9d584abe226526886c532fece` (main). `rev-list --left-right --count HEAD...origin/main == 0 0`. Tracked tree clean at receipt/check. HEAD advanced from prior handoff receipt `773f059da98df2f6fa5b6cc0b6946b72c6c8d0a1`. `git diff --stat 773f059da..HEAD` = only `.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`.

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
- Binding `configs/research_v6_selection_execution_binding_1.json` (frozen, `IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ authorization `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`), `hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`.
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
- 2026-11-15T02:06:02Z (`9564b927ebd3c0d9d584abe226526886c532fece`): standing checks + v6 execution-integrity re-verification at live HEAD `9564b927...`; HEAD advanced from prior receipt `773f059da...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T02:05:10Z (`773f059da98df2f6fa5b6cc0b6946b72c6c8d0a1`): standing checks + v6 execution-integrity re-verification at live HEAD `773f059d...`; HEAD advanced from prior receipt `6861ef4a...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T02:02:14Z (`6861ef4a3c4c19bb500f86d8470a503a008a2a1a`): standing checks + v6 execution-integrity re-verification at live HEAD `6861ef4a...`; HEAD advanced from prior receipt `fe263f496...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T02:00:52Z (`fe263f496c596fc24319f538d180e4d760bb3ed8`): standing checks + v6 execution-integrity re-verification at live HEAD `fe263f496...`; HEAD advanced from prior receipt `bcfe132d274a...`; 4 failures unchanged; manifest MATCH.
- Older 2026-11-15 sessions (01:58Z–00:58Z) and 2026-11-14/15 sessions (18:45Z–00:04Z): repeated fail-closed checkpoints at receipts `bcfe132d...`, `1238567a...`, `45a01753f...`, `3a679cb6...`, `876cb38...`, `0611f55...`, `b2a5ace...`; 4 failures unchanged; manifest MATCH; `campaign_authorization.json` code_hash rotated at 14:21:19Z; `NO_PROMPT_CHANGE_JUSTIFIED`. See git history.

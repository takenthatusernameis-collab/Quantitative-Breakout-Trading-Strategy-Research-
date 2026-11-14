# Agent handoff (durable)

This file is the repo-resident continuity surface for cross-agent handoff.

## HANDOFF — 2026-11-14T03:57Z @ `afd45bf249470be61096afd72196d2bfcc32706c` (kilo, standing cheap checks + v6 execution-integrity re-verification)

**Completed:** standing cheap checks + v6 execution-integrity re-verification. No substantive protocol/state change; no frozen artifacts edited; no v6 run consumed; no holdout/confirmatory exposed.

### Git
- `git rev-parse HEAD` == `origin/main` == `@{u}` == `afd45bf249470be61096afd72196d2bfcc32706c` (main). `rev-list --left-right --count HEAD...origin/main` == `0 0`.
- Tracked tree clean at check start (handoff files updated this session only).

### Verifier
- Command: `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed).
- Failures (4, unchanged verbatim):
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- Computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- No change vs prior recorded values (manifest MATCH, same 4 failures, same digests).

### Identity (read from source of record; no drift)
- `configs/research_v6_selection_execution_binding_1.json` (frozen 2026-11-04, `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`): `code_identity.hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, `code_identity.execution_path_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `code_identity.run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (read directly from binding), `manifest_hash==b9090900d1ef6304b022ab18332e01ebea8c0f2a1e259710565c5006f3c6332e`.
- `configs/research_v6_selection_authorization_1.json` `authorized_run.code_identity`: `hashed_set_digest==3e8e41…`, `execution_path_digest==null`, `run_code_identity==6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`, `authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (`authorized_code_hash_status==RETAINED_AS_VALUE_OF_RECORD`); `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent (unconsumed), `no_execution_in_this_session==true`.
- `research_state/campaign_authorization.json`: `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (`authorized==true`, `authorized_at_utc==2026-11-12T18:12:22.943361+00:00`) — **live value, rotates on refresh**.
- Effective mismatch (fail-closed): auth-of-record `2efd3b…` vs frozen binding `3e8e41…` vs live `8cd1…`. Do not edit frozen artifacts to paper over. `NO_PROMPT_CHANGE_JUSTIFIED`.

### Cohort / v6 / holdout (no drift)
- `research_state/continuous_universe_state.json`: `current_cycle_id==v5-selection-20261021`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `updated_utc==2026-10-21T21:45:00+00:00`.
- `research_state/checkpoint_v5.json`: `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`.
- v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; `src/v6_campaign/` present; authorized run unconsumed). No holdout/confirmatory exposed.

### Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, `configs/research_v6_selection_authorization_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

### Next task
- See `research_state/next_agent_task.md`.

## Prior sessions (condensed)
- 2026-11-14T03:57Z @ `afd45bf249470be61096afd72196d2bfcc32706c`: identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. Head advanced from `2b30c106c610c2082b28b5f2a971afafac49c207` to `afd45bf249470be61096afd72196d2bfcc32706c`; tracked tree clean.
- 2026-11-14T03:53Z @ `2b30c106c610c2082b28b5f2a971afafac49c207`: identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. Head advanced from `faec97849e625dc675860f0901cb9ffc6e4b0f40` to `2b30c106c610c2082b28b5f2a971afafac49c207`; tracked tree clean.
- 2026-11-14T03:51Z @ `faec97849e625dc675860f0901cb9ffc6e4b0f40`, 03:47Z @ `c3c1b89058a32aa0074e66c2778cb86263841d0a`, 03:44Z @ `de1ae7dc62fcfb2e7e3b8dfeb1ff5263837950ba`: identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. Each advanced HEAD by handoff-docs-only commit.
- 2026-11-14T03:41Z–00:34Z (20 sessions @ `baa0929258fa0d8af8987ae275110330718f84b5` … `81da2b0ade394ace5e1b1fef9b29406a96d21d17`): identical standing checks; same 4 failures unchanged; manifest MATCH; no drift; v6 unconsumed/not started; `NO_PROMPT_CHANGE_JUSTIFIED`. Each advanced HEAD by handoff-docs-only commits.
- 2026-11-13 (17:37Z–23:44Z, many sessions @ `4d10349`…`2d27863` and earlier): identical standing-check results; each advanced HEAD by checkpoint/handoff-docs-only commits.

(End of file)

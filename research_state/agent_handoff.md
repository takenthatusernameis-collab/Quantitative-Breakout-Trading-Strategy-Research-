# Agent handoff (durable, single source of truth)

This file is the authoritative cross-session handoff. Keep it concise and current.

## Current State (re-verified 2026-11-10T19:13Z UTC)
- Branch: `main`; HEAD `8a9dd9e63798030a38a620f687ac79bc1bd2fefa` == `origin/main` == `@{u}`. Tracked tree clean at check (no unstaged/staged tracked changes) except handoff files updated this session.
  - Diff vs prior handoff: HEAD changed from `2d33d5e4b98cb59a20d91fa2b3e63b8b855f154f` to `8a9dd9e63798030a38a620f687ac79bc1bd2fefa` (prior agent checkpoint commit; only handoff files changed). Verifier/cohort/v6 artifacts unchanged.
- Verifier (`python3 scripts/verify_v6_execution.py`): **`ok: false` (exit 1, fail-closed)**, 4 `failures` unchanged verbatim:
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- Key digests/hashes (unchanged): `manifest_hash`/`recomputed_manifest_hash` `928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH); `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`. Computed: `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- Root cause (fail-closed, protocol-level): frozen `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` vs `research_state/campaign_authorization.json` `code_hash==22bacfb89a469cc9eaa3ff4198510135910756721c69cda09b78d784d15c0c06`; binding hashed-engine/composite digests no longer recompute. **Do not edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over this without explicit user authorization.**
- Cohort (`research_state/continuous_universe_state.json`): **no drift** — `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 `current_cohort.excluded`; `updated_utc` present `2026-10-21T21:45:00+00:00`.
- Holdout (`research_state/checkpoint_v5.json`): `holdout_exposed_count==0` (`completed_records==193536`, `pilot_passed==true`).
- v6 selection: **NOT started**. `src/v6_campaign/` present; binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`. Absent: `research_state/v6_selection_ledger.json`, `research/v6_selected_configurations_manifest.json`, `src/v6_confirmatory/`. Single authorized run unconsumed: `configs/research_v6_selection_authorization_1.json` `authorization_status==PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN`, `authorized_run.run_id==v6-selection-20261022`, `authorized_run.campaign_id==v6-campaign`, `authorized_run.max_runs==1`, `authorized_run.authorized==true` (top-level `consumed` absent/null). No v6 run artifacts exist (`research/shards_v6`, `research/ledger_v6.json`, `research/results_manifest_v6.json`, `research/results_v6.jsonl`, `research_state/checkpoint_v6.json` all absent). **Holdout/confirmatory exposure must remain 0.**

## Prompt review
- `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — this session (2026-11-10T19:13Z UTC)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change; no commit made (not requested).
- Confirmed HEAD `8a9dd9e63798030a38a620f687ac79bc1bd2fefa` == `origin/main` == `@{u}`, tracked tree clean at check.
- Verifier re-run: `ok:false` exit 1, same 4 failures verbatim; `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`; all key computed digests/hashes unchanged.
- Cohort/v6/holdout state confirmed unchanged (no drift: `next_cohort_index==6`, cohort 5 `completed==true`, 13 excluded; v6 selection not started; `research_state/v6_selection_ledger.json`/`research/v6_selected_configurations_manifest.json`/`src/v6_confirmatory/` absent; authorized run `v6-selection-20261022`/`v6-campaign`, `max_runs==1`, unconsumed, top-level `consumed` absent/null; `holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`).
- `research_state/agent_handoff.md` and `research_state/next_agent_task.md` refreshed.

**Change vs prior handoff:** HEAD changed (`2d33d5e4b98cb59a20d91fa2b3e63b8b855f154f` -> `8a9dd9e63798030a38a620f687ac79bc1bd2fefa`). Verifier/cohort/v6 artifacts unchanged. No commit made (not requested).

Next task: see `research_state/next_agent_task.md`.

(End of file)
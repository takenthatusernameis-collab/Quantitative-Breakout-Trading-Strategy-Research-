# Agent handoff (durable, single source of truth)

This file is the authoritative cross-session handoff. Keep it concise and current.

## Current State (re-verified 2026-11-11T13:33:30Z UTC)
- Branch: `main`; HEAD `36f686577a53c60b677be3e9d6540b87da0fcbd5` == `origin/main` == `@{u}`. Tracked tree clean at check (handoff files updated this session).
- Verifier (`PYTHONPATH=src python3 scripts/verify_v6_execution.py`): **`ok: false` (exit 1, fail-closed)**, 4 `failures` unchanged verbatim:
  1. `the code-hash constraint does not record the authorized code hash of record`
  2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
  3. `the versioned binding's hashed engine digest does not recompute`
  4. `the versioned binding's composite run code identity does not recompute`
- Verifier re-run this session: `ok:false`, exit 1, same 4 failures verbatim; `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key computed digests/hashes unchanged: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- Root cause (fail-closed, protocol-level): frozen `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash==2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` vs `research_state/campaign_authorization.json` `code_hash==22bacfb89a469cc9eaa3ff4198510135910756721c69cda09b78d784d15c0c06`; binding hashed-engine/composite digests no longer recompute. **Do not edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over this without explicit user authorization.**
- Binding/authorization: `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; single authorized run in `configs/research_v6_selection_authorization_1.json` — `authorization_status==PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN`, `authorized_run.run_id==v6-selection-20261022`, `authorized_run.campaign_id==v6-campaign`, `authorized_run.max_runs==1`, `authorized_run.authorized==true`, `consumed` absent top-level and in `authorized_run` — **unconsumed**.
- Cohort (`research_state/continuous_universe_state.json`): **no drift** — `next_cohort_index==6`; `current_cohort.cohort_index==5`, `completed==true`, 13 excluded; `updated_utc==2026-10-21T21:45:00+00:00`; `current_cycle_id==v5-selection-20261021`.
- Holdout (`research_state/checkpoint_v5.json`): `holdout_exposed_count==0` (`completed_records==193536`, `pilot_passed==true`, `code_hash==8a63085e0df880c8d74de5c8f19d6338dd9330ee42c632882634f185ef4948c2`, `protocol_hash==55e839f7fe82201ec9ef9a699c081a903255669c394f494ad147f3f72e72dec2`).
- v6 selection: **NOT started**. `src/v6_campaign/` present; `src/v6_confirmatory/` absent. Absent: `research_state/v6_selection_ledger.json`, `research/v6_selected_configurations_manifest.json`. **Holdout/confirmatory exposure must remain 0.**

## Prompt review
- `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — this session (2026-11-11T13:33:30Z UTC)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change.
- Confirmed HEAD `36f686577a53c60b677be3e9d6540b87da0fcbd5` == `origin/main` == `@{u}`; tracked tree clean at check. (HEAD advanced from prior recorded `10ba0ff535ea86d972d46547f3d1ee2af2aae994`.)
- Verifier re-run: `ok:false` exit 1, same 4 failures verbatim; `manifest_hash==recomputed_manifest_hash==92872727...7026` (MATCH); all key computed digests/hashes unchanged (`canonical_hashed_set_digest` `8cd17522...ae45e`, `v6_execution_path_canonical_digest` `37ba6eb3...aa72`, `recomputed_inherited_blocks_digest` `0d131954...4433`, `selection_authorization_*` unchanged, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`).
- Cohort/v6/holdout state confirmed unchanged (no drift; cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true` 13 excluded, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`; `holdout_exposed_count==0`; binding `IMPLEMENTATION_BOUND_NOT_RUN`; single authorized run `v6-selection-20261022`/`v6-campaign`, `max_runs==1`, unconsumed; `src/v6_confirmatory/` absent, v6 ledger/manifest absent).
- Frozen artifacts unchanged. No fix applied to verifier. Did not consume authorized v6 selection run; did not expose holdout/confirmatory. No commit made (not requested).

**Change vs prior handoff:** HEAD `36f686577a53c60b677be3e9d6540b87da0fcbd5` (prior recorded `10ba0ff535ea86d972d46547f3d1ee2af2aae994`); verifier/cohort/v6/holdout/frozen artifacts unchanged.

## COMPLETED — recent prior sessions (condensed)
- **2026-11-11T13:31:39Z UTC** HEAD `10ba0ff...` (`3abfbcfb` prior): verifier `ok:false` same 4 failures, manifest MATCH `92872727...7026`, all key digests/auth unchanged; cohort/v6/holdout unchanged.
- **2026-11-11T12:07:19Z UTC** HEAD `31072ff...` (`0995115f` prior): verifier `ok:false` same 4 failures, manifest MATCH `92872727...7026`, all key digests/auth unchanged; cohort/v6/holdout unchanged.
- **2026-11-11T11:53:50Z UTC** HEAD `0995115f...` (`bb962667` prior): same standing re-verification; unchanged.
- **2026-11-11T11:50:05Z–11:24:00Z UTC** HEADs `00656515`→`7beccc91`→`4656cb37`→`d24a1064`: repeated standing re-verifications; verifier/cohort/v6/holdout/frozen artifacts consistently unchanged (same 4 failures, manifest MATCH).

Next task: see `research_state/next_agent_task.md`.

## COMPLETED — recent prior sessions (condensed)
- **2026-11-11T12:07:19Z UTC** HEAD `31072ff...` (`0995115f` prior): verifier `ok:false` same 4 failures, manifest MATCH `92872727...7026`, all key digests/auth unchanged; cohort/v6/holdout unchanged; no substantive change.
- **2026-11-11T11:53:50Z UTC** HEAD `0995115f...` (`bb962667` prior): same standing re-verification; unchanged.
- **2026-11-11T11:50:05Z–11:24:00Z UTC** (multiple sessions, HEADs `00656515`→`7beccc91`→`4656cb37`→`d24a1064`): repeated standing re-verifications; verifier/cohort/v6/holdout/frozen artifacts consistently unchanged (same 4 failures, manifest MATCH).

Next task: see `research_state/next_agent_task.md`.

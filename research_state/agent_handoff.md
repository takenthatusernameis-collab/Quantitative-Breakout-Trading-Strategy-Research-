# Kilo durable handoff

Maintainer note: Most recent check at top; older entries condensed. Keep this file short and current.

## COMPLETED — this session (2026-11-13T04:47:03Z @ `9b88ae78caf763a91f82ed566fd3f0c52eb458a9`)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change.
- `git rev-parse HEAD` == `git rev-parse origin/main` == `git rev-parse @{u}` == `9b88ae78caf763a91f82ed566fd3f0c52eb458a9`; tracked tree clean at check (0 ahead / 0 behind; 0 untracked). HEAD advanced from prior recorded `1438232d03dc422648f0291241a7bcafecd39b62` by handoff-only checkpoint commit (diff vs recorded: only `research_state/agent_handoff.md` and `research_state/next_agent_task.md` changed; no substantive code/config drift).
- Verifier re-run (`PYTHONPATH=src python3 scripts/verify_v6_execution.py`): `ok:false` exit 1, same 4 failures unchanged verbatim; `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` MATCH; key computed digests/hashes unchanged (`canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`).
- Binding `code_hash_constraint.canonical_hashed_set_digest==3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff` still mismatches live `canonical_source_digest==8cd1…`; failures unchanged verbatim: `the code-hash constraint does not record the authorized code hash of record`; `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; `the versioned binding's hashed engine digest does not recompute`; `the versioned binding's composite run code identity does not recompute`.
- Cohort/v6/holdout state unchanged (no drift): cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00` (`continuous_universe_state.json`); `holdout_exposed_count==0` (`checkpoint_v5.json`, `completed_records==193536`, `pilot_passed==true`); v6 selection unconsumed and not started (`authorized_run.run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent top-level and in `authorized_run` of `configs/research_v6_selection_authorization_1.json`; `research_state/v6_selection_ledger.json` and `research/v6_selected_configurations_manifest.json` absent, `src/v6_confirmatory/` absent; `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; `src/v6_campaign/` present (8 modules)).
- Did not consume authorized v6 selection run; did not expose holdout/confirmatory. `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — prior sessions
- 2026-11-13T04:44:49Z @ `1438232d03dc422648f0291241a7bcafecd39b62`: same standing-check result, no drift (HEAD advanced from `588e21590` by handoff-only checkpoint); 4 verifier failures unchanged verbatim; v6 selection unconsumed.
- 2026-11-13T04:35:44Z @ `d545230d0fb19d65d545c6e9b0d6d08c4422b29b` .. 2026-11-13T03:24:58Z @ `4d09329a3ae8180ac5cedc895216b8e379ea1767` (13 checkpoints): same standing-check result, no drift (each advanced by handoff-only checkpoint commits); 4 verifier failures unchanged verbatim; v6 selection unconsumed.

## Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization. Resolving it is a substantive/protocol decision.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

Next task: see `research_state/next_agent_task.md`.

(End of file)

# Kilo durable handoff

Maintainer note: Most recent check at top; older entries condensed. Keep this file short and current.

## COMPLETED — this session (2026-11-13T00:10:51Z)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change; no local diffs beyond this handoff/next-task refresh (not committed).
- `git rev-parse HEAD` == `git rev-parse origin/main` == `git rev-parse @{u}` == `709b955133812ef2b32fa6eadf6cb4bb50811cc5`; tracked tree clean (0 ahead / 0 behind). HEAD advanced one checkpoint commit from prior recorded `0579a9b144a71c01ac07eeedb894f216e59b2534`.
- Verifier re-run (`PYTHONPATH=src python3 scripts/verify_v6_execution.py`): `ok:false` exit 1, same 4 failures unchanged verbatim; all computed digests/hashes unchanged vs prior record (`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` MATCH; `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`).
- Failures (unchanged verbatim): `the code-hash constraint does not record the authorized code hash of record`; `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; `the versioned binding's hashed engine digest does not recompute`; `the versioned binding's composite run code identity does not recompute`.
- Cohort/v6/holdout/authorization state unchanged (no drift): cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00` (`continuous_universe_state.json`); `holdout_exposed_count==0` (`checkpoint_v5.json`, `completed_records==193536`, `pilot_passed==true`); v6 selection unconsumed and not started (`authorized_run.run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent top-level and in `authorized_run` of `configs/research_v6_selection_authorization_1.json`; `research_state/v6_selection_ledger.json` and `research/v6_selected_configurations_manifest.json` absent, `src/v6_confirmatory/` absent; `src/v6_campaign/` present). Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`. Authorization also carries `no_execution_in_this_session==true`.
- Did not consume authorized v6 selection run; did not expose holdout/confirmatory. Not committed (no explicit user request). `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — prior session (2026-11-13T00:09:58Z @ `0579a9b144a71c01ac07eeedb894f216e59b2534`)
Standing task (cheap checks + execution-integrity re-verification) complete; same result, no drift.

## COMPLETED — prior sessions (condensed)
- 2026-11-13T00:09:17Z @ `11dd31331956ed82466c825dcb1f3a7d81217e93`: same, no drift.
- 2026-11-13T00:07:06Z @ `d8c70eada0a41da6a3de40d47b80b826a4324eec`: same, no drift.
- 2026-11-12T22:12:48Z–2026-11-12T23:20:54Z @ `e0770a15…`–`7a1e200e…` (11 checkpoint commits): same standing-check result, no drift.
- Earlier advancing-head re-verifications through 2026-11-12T20:13:32Z: same standing-check result, no drift (see git history for detail).

## Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization. Resolving it is a substantive/protocol decision.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

Next task: see `research_state/next_agent_task.md`.

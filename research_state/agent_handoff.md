# Kilo durable handoff

Maintainer note: Most recent check at top; older entries condensed. Keep this file short and current.

## COMPLETED — this session (2026-11-12T23:20:54Z)
Standing task (cheap checks + execution-integrity re-verification) complete. No substantive protocol/state change; no local diffs beyond this handoff/next-task refresh (not committed).
- `git rev-parse HEAD` == `git rev-parse origin/main` == `git rev-parse @{u}` == `7a1e200ec8c17fea2f38b0e4fdc34c2056a91a3f`; tracked tree clean before handoff update (0 ahead / 0 behind). HEAD advances prior recorded `0b728ba2aa4aa6ff15b15fc5dda738efb5eee69d`.
- Verifier re-run (`PYTHONPATH=src python3 scripts/verify_v6_execution.py`): `ok:false` exit 1, same 4 failures unchanged verbatim; all computed digests/hashes unchanged. `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- Failures (unchanged verbatim): `the code-hash constraint does not record the authorized code hash of record`; `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; `the versioned binding's hashed engine digest does not recompute`; `the versioned binding's composite run code identity does not recompute`.
- Cohort/v6/holdout/authorization state unchanged (no drift): cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00` (`continuous_universe_state.json`); `holdout_exposed_count==0` (`checkpoint_v5.json`, `completed_records==193536`, `pilot_passed==true`); v6 selection unconsumed and not started (`authorized_run.run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent top-level and in `authorized_run`; `research_state/v6_selection_ledger.json` and `research/v6_selected_configurations_manifest.json` absent, `src/v6_confirmatory/` absent; `src/v6_campaign/` present). Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`.
- Did not consume authorized v6 selection run; did not expose holdout/confirmatory. Not committed (no explicit user request). `NO_PROMPT_CHANGE_JUSTIFIED`.

## COMPLETED — prior sessions (condensed)
- 2026-11-12T23:16:36Z @ `0b728ba2aa4aa6ff15b15fc5dda738efb5eee69d`: same standing-check result, no drift.
- 2026-11-12T23:10:28Z @ `faac8ccfdb71268aa7cc808181fc0976c8d74071`: same, no drift.
- 2026-11-12T23:07:32Z @ `f260fdc18e86f964776c3db765e3d38865c825c8`: same, no drift.
- 2026-11-12T23:06:14Z @ `a0e3ec38d439c35d549baa102c26032b6161c824`: same, no drift.
- 2026-11-12T22:23:53Z @ `b2484c18ec77bad1b1b3da5f1361334239d63583`: same, no drift.
- 2026-11-12T22:20:52Z @ `32f3cacf7680947bea54b55a688309622e21f03a`: same, no drift.
- 2026-11-12T22:19:02Z @ `37070513756dee9033c63b7cf7939f9e7c91a1c4`: same, no drift.
- 2026-11-12T22:17:29Z @ `451f7aae39b8408a5390c7e837b5c589dad14200`: same, no drift.
- 2026-11-12T22:14:54Z @ `cbc919a1589bfac583a4b1e2ee7ac2142e1f0bdf`: same, no drift.
- 2026-11-12T22:12:48Z @ `e0770a15296b57fb398e13bac75da94eb7f25aa1`: same, no drift.
- 2026-11-12T22:11:20Z @ `ce0608051d9da9c27fc4bdd7f5ec71e8a6b18fb6`: same, no drift.
- Earlier advancing-head re-verifications through 2026-11-12T20:13:32Z: same standing-check result, no drift (see git history for detail).

## Hard constraints (standing)
- Do **not** consume `authorized_run.run_id==v6-selection-20261022` / `campaign_id==v6-campaign` and do **not** expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`, `holdout_exposed_count` must remain 0).
- Do **not** edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization. Resolving it is a substantive/protocol decision.
- Keep diffs minimal/mechanical; commit handoff-only changes only if explicitly requested.

Next task: see `research_state/next_agent_task.md`.

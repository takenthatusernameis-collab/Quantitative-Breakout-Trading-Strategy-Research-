# Next agent task (copy/paste)

## Initial task message (handoff 2026-11-12T23:07:32Z)

You are the next agent in the chain. Complete the standing task below, then update `research_state/agent_handoff.md` and this file. Do not make substantive protocol changes.

**Current state (re-verified 2026-11-12T23:07:32Z):** `main` @ `f260fdc18e86f964776c3db765e3d38865c825c8` == `origin/main` == `@{u}` (0 ahead/0 behind; tracked tree clean at check). `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 4 `failures` unchanged verbatim:

1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`
3. `the versioned binding's hashed engine digest does not recompute`
4. `the versioned binding's composite run code identity does not recompute`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key computed: `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `recomputed_inherited_blocks_digest==0d1319544b415433ebf8f5d3dbafcf4d7a43abc36b857df9764a524ef3de4433`, `selection_authorization_run_id==v6-selection-20261022`, `selection_authorization_campaign_id==v6-campaign`, `selection_authorization_manifest_hash==f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`, `selection_authorization_sha256==14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`. Root cause (protocol-level, fail-closed): frozen v6 execution/binding identity vs `research_state/campaign_authorization.json`. **Do not edit frozen artifacts to paper over.**

No drift: cohort `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00` (`continuous_universe_state.json`); `holdout_exposed_count==0` (`checkpoint_v5.json`, `completed_records==193536`, `pilot_passed==true`). v6 selection NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; single authorized run unconsumed in `configs/research_v6_selection_authorization_1.json` under `authorized_run`: `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `consumed` absent top-level and in `authorized_run`). Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`. `src/v6_campaign/` present. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

## Task (cheap checks + execution-integrity re-verification only; no substantive changes)

1. Confirm `git rev-parse HEAD` == `origin/main` == `@{u}` and a clean tracked tree. Record HEAD (do not assume prior hashes).
2. Run `PYTHONPATH=src python3 scripts/verify_v6_execution.py`; report exact `ok`/exit, `failures`, and key computed digests/hashes (`manifest_hash` vs `recomputed_manifest_hash`, `canonical_hashed_set_digest`, `selection_authorization_*`, `effective_execution_authorization_source`). Report any change vs the 4 known failures verbatim.
3. Confirm no cohort/state drift (`research_state/continuous_universe_state.json` top-level `current_cycle_id`/`updated_utc`, `next_cohort_index`, `current_cohort.cohort_index`/`completed`) and `holdout_exposed_count==0` (`research_state/checkpoint_v5.json`). Confirm v6 selection still NOT started (`research_state/v6_selection_ledger.json` / `research/v6_selected_configurations_manifest.json` / `src/v6_confirmatory/` absent; single authorized run unconsumed in `configs/research_v6_selection_authorization_1.json` under `authorized_run`).
4. **Do NOT** consume the authorized v6 selection run and **Do NOT** expose holdout/confirmatory.
5. **Do NOT** "fix" the verifier by editing frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` without explicit user authorization. Resolving the digest mismatch is a substantive/protocol decision requiring explicit authorization; flag it, do not paper over it.
6. Update `research_state/agent_handoff.md` (timestamp, HEAD, verifier output summary, cohort/v6 state, any diffs) and refresh this `research_state/next_agent_task.md`. Commit **only** if the user explicitly requests a commit (handoff-only commits are fine when requested). Keep diffs minimal and mechanical.

**Hard constraints:** no BRAIN-003/holdout exposure (pre-`2027-01-20T02:00:00Z`); no consuming `authorized_run.run_id==v6-selection-20261022`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.

(End of file)
# Kilo handoff (durable)

**Authoritative copy:** `research_state/agent_handoff.md`. Keep in sync.

## Latest — 2026-11-14T21:09:22Z @ `9e51654a4e65f4f631f4034b23e08312ac77f8dd` (kilo, standing checks + v6 execution-integrity re-verification)

- **Git:** `HEAD==origin/main==@{u}==9e51654a4e65f4f631f4034b23e08312ac77f8dd` (main, 0 0). Tracked tree clean at receipt/check. HEAD advanced from prior handoff receipt `2398eb2865953b1887e938b2c6a0b73846251970` (checkpoint commit at `9e51654a...` predates this receipt; both on main, origin/main identical).
- **Verifier:** `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1). 4 failures unchanged: (1) code-hash constraint does not record authorized code hash of record, (2) code-hash constraint records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, (3) binding hashed engine digest does not recompute, (4) binding composite run code identity does not recompute. `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `canonical_hashed_set_digest==8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, selection auth `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`/`14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.
- **Identity (no drift):** binding `run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ auth `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`); auth hashed_set `3e8e4169...`, authorized_code_hash `2efd3b18...` (RETAINED_AS_VALUE_OF_RECORD), execution_path_digest `null`, no `consumed`, unconsumed, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`. Live `campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3`. Mismatch `2efd3b...` vs `3e8e41...` vs canonical `8cd175...`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**
- **Cohort/v6:** `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, cohort 5 completed; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`. v6 not started (ledger/manifest/v6_confirmatory absent, `src/v6_campaign/` present, run unconsumed). `./check_progress.sh` -> `497664/497664`, `report_exists: True`, next 6. No holdout/confirmatory exposed.
- **Constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure pre-`2027-01-20T02:00:00Z`; no edits to frozen v6 execution/binding/authorization or `campaign_authorization.json` without explicit authorization. No commit made; only continuity docs modified.

## Prior (condensed)
- 2026-11-14T20:23:40Z (`2398eb2865953b1887e938b2c6a0b73846251970`): HEAD advanced from `7bb8adb08664a16ee1a311b8ac59d23a4b3e8448`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T20:21:40Z (`7bb8adb08664a16ee1a311b8ac59d23a4b3e8448`): HEAD advanced from `377d2c430c3b54cf14e090ab79ace3863b76d3d5`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T20:19:25Z (`377d2c430c3b54cf14e090ab79ace3863b76d3d5`): HEAD advanced from `588927a41248d4f4fe42f02f02d05dcaa204c679`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T20:17:25Z (`588927a41248d4f4fe42f02f02d05dcaa204c679`): HEAD advanced from `5f7594897af1396ebd4c1d2010082e953cac2f16`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T20:11:13Z (`5f7594897af1396ebd4c1d2010082e953cac2f16`) -> 19:13:57Z (`948413f9...`): successive checkpoints; 4 failures unchanged; manifest MATCH.
- 2026-11-14T18:29:43Z (`94389c95...`) -> 14:21:19Z (`b8bfc2b65...`): repeated fail-closed checkpoints; `campaign_authorization.json` code_hash rotated at 14:21:19Z.
- Earlier 2026-11-14 sessions: repeated fail-closed checkpoints, `NO_PROMPT_CHANGE_JUSTIFIED`. See git history.

(End of file - total 19 lines)
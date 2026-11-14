# Kilo handoff (durable)

**Authoritative copy:** `research_state/agent_handoff.md`. Keep in sync.

## Latest — 2026-11-14T18:13:50Z @ `7b2a5c99427ab31170ed8a7426f08b84749842a7` (kilo, standing checks + v6 execution-integrity re-verification)

- **Git:** `HEAD==origin/main==@{u}==7b2a5c99427ab31170ed8a7426f08b84749842a7` (main, 0 0). Tracked tree clean at receipt. HEAD advanced from prior receipt checkpoint (`f922f9ac9f05d18b5b75be21030c23486a93a4e7`) to `7b2a5c994...`; diff vs prior receipt HEAD limited to continuity docs / checkpoint commit.
- **Verifier:** `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1). 4 failures unchanged: (1) code-hash constraint does not record authorized code hash of record, (2) code-hash constraint records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, (3) binding hashed engine digest does not recompute, (4) binding composite run code identity does not recompute. `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, selection auth `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`/`14508bbc0cd049eab3b710e8c22c340f20afae99ebf6f98378ccc1977d25b27b`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.
- **Identity (no drift):** binding `run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ auth `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`); auth hashed_set `3e8e4169...`, authorized_code_hash `2efd3b18...` (RETAINED_AS_VALUE_OF_RECORD), execution_path_digest `null`, top-level `authorized_code_hash` null, no `consumed`, unconsumed, `run_id==v6-selection-20261022`, `campaign_id==v6-campaign`, `max_runs==1`, `no_execution_in_this_session==true`. Live `campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3`. Mismatch `2efd3b` vs `3e8e41` vs canonical `8cd175`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**
- **Cohort/v6:** `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, cohort 5 completed; `checkpoint_v5.holdout_exposed_count==0`. v6 not started (ledger/manifest/v6_confirmatory absent, `src/v6_campaign/` present, run unconsumed). No holdout/confirmatory exposed.
- **Constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure pre-`2027-01-20T02:00:00Z`; no edits to frozen v6 execution/binding/authorization or `campaign_authorization.json` without explicit authorization. No commit made; only continuity docs modified.

## Prior (condensed)
- 2026-11-14T18:13:50Z (`7b2a5c994...`): standing checks + v6 re-verification; HEAD advanced from receipt `f922f9ac9...` to `7b2a5c994...`; tree clean; 4 failures unchanged; manifest MATCH.
- 2026-11-14T18:10:59Z (`f922f9ac9...`): standing checks + v6 re-verification; HEAD advanced from receipt `d37c5947...` to `f922f9ac9...`; tree clean; 4 failures unchanged; manifest MATCH.
- 2026-11-14T18:08:31Z (`d37c5947...`): HEAD advanced from receipt `653e287d...` to `d37c5947...`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T18:06:25Z (`653e287d...`): HEAD advanced from receipt `c22de861...` to `653e287d...`; 4 failures unchanged; manifest MATCH.
- 2026-11-14T17:23:31Z (`c22de861...`) back through 14:21:19Z (`b8bfc2b65...`): repeated fail-closed checkpoints; HEAD advanced each time; 4 failures unchanged; manifest MATCH; `campaign_authorization.json` code_hash rotated at 14:21:19Z.
- Earlier 2026-11-14 sessions: repeated fail-closed checkpoints, `NO_PROMPT_CHANGE_JUSTIFIED`. See `research_state/agent_handoff.md` history in git.

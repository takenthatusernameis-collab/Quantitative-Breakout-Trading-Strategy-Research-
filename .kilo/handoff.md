# Kilo handoff (durable)

**Authoritative copy:** `research_state/agent_handoff.md`. Keep in sync.

## Latest — 2026-11-15T07:55Z @ `d777986bc3d272789a50d02bfcca80da69f87232` (kilo, standing checks + v6 execution-integrity re-verification)

- **Git:** `HEAD==origin/main==@{u}==d777986bc3d272789a50d02bfcca80da69f87232` (main, 0 0). HEAD advanced from prior handoff receipt `891e6b66ab537cdb2c763cf189977611e7f981c7`; `git diff --stat 891e6b66ab537cdb2c763cf189977611e7f981c7..d777986bc3d272789a50d02bfcca80da69f87232` = continuity-doc checkpoint only. Latest commit `d777986` "chore(kilo): checkpoint agent session" (07:53:06Z). Tracked tree clean at receipt/check; after this update only continuity docs modified.
- **Verifier:** `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1). 4 failures unchanged: (1) code-hash constraint does not record authorized code hash of record, (2) code-hash constraint records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`, (3) binding hashed engine digest does not recompute, (4) binding composite run code identity does not recompute. `manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key digests `canonical_hashed_set_digest==8cd17522...`, `v6_execution_path_canonical_digest==37ba6eb3...`, selection auth `f1b012b6...`/`14508bbc...`, `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, gate `2027-01-20T02:00:00Z`.
- **Root cause (unchanged):** live `src/breakout_research` digest `8cd17522...` vs frozen snapshot `3e8e41...`; execution path `37ba6eb3...` matches. Binding `run_code_identity==647dc464...` (snapshot `3e8e41...` + path `37ba6eb3...`) vs live-derived `cfd1cc2d...`; binding internally consistent with stale snapshot. **`NO_PROMPT_CHANGE_JUSTIFIED`.**
- **Identity (no drift):** binding `run_code_identity==647dc464a731f73bbca840086b645fef3bf742866cfd16a86829c1167969b961` (≠ auth `6bda27fa538ee8a1c21581db62d89a5bb714300ea19806d548692aca3506a30b`), `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; auth run `v6-selection-20261022`/`v6-campaign`, `max_runs==1`, unconsumed. Live `campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (rotating).
- **Cohort/v6:** `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, cohort 5 completed; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`. v6 not started (ledger/manifest/v6_confirmatory absent, `src/v6_campaign/` present, run unconsumed). `./check_progress.sh` -> `497664/497664`, `report_exists: True`, next 6.
- **Constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure pre-`2027-01-20T02:00:00Z`; no edits to frozen v6 artifacts or `campaign_authorization.json` without explicit authorization. No commit made. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

## Prior (condensed)
- 2026-11-15T07:50Z (`b15caa60f...`): HEAD advanced from `9edfb2a62...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T07:05Z (`9edfb2a62...`): HEAD advanced from `2b810ae8...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T07:00Z→04:06Z: successive standing checks at live HEADs; 4 failures unchanged; manifest MATCH.
- Older 2026-11-15/14 sessions: repeated fail-closed checkpoints; 4 failures unchanged; manifest MATCH; `campaign_authorization.json` code_hash rotated at 14:21:19Z. See git history.

(End of file)
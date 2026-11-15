# Kilo handoff (durable)

**Authoritative copy:** `research_state/agent_handoff.md`. Keep in sync.

## Latest — 2026-11-15T10:06Z @ `b3d47dad9a1c1f37c008a514a5c3a2b60fa179c8` (kilo, standing checks + handoff refresh after binding update)

- **Git:** `HEAD==origin/main==@{u}==b3d47dad9a1c1f37c008a514a5c3a2b60fa179c8` (main, 0 0). HEAD == prior handoff receipt `eb1c0ea5b098a1a6a1676ea4ef6aa6f4c96ec8fc`; diff = continuity-doc checkpoints only (`.kilo/handoff.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`). Tracked tree clean at receipt/check; after this update only continuity docs modified.
- **Verifier:** `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1). 2 failures remain (frozen protocol only): (1) code-hash constraint does not record authorized code hash of record, (2) code-hash constraint records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. Binding checks PASS: `canonical_hashed_set_digest==8cd17522...` recomputes, `run_code_identity==cfd1cc2d034db5b5736fb3f26fb690fd773533f4e1f7144feb2bc857b46b8b7e` recomputes. `manifest_hash==recomputed_manifest_hash==af393e0395b5ce9494f6629b0c8137ed9ed88fcbca2ce67abb6812e6da98019c` (MATCH, independently recomputed).
- **Root cause (unchanged):** live `src/breakout_research` digest `8cd17522...` vs frozen snapshot `3e8e41...`; execution path `37ba6eb3...` matches. Binding already updated to live identity at `b3d47dad9`. **`NO_PROMPT_CHANGE_JUSTIFIED`.**
- **Identity (no drift):** binding `run_code_identity==cfd1cc2d034db5b5736fb3f26fb690fd773533f4e1f7144feb2bc857b46b8b7e` (live-derived, matches recomputation), `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; auth run `v6-selection-20261022`/`v6-campaign`, `max_runs==1`, unconsumed. Live `campaign_authorization.json` `code_hash==13172b2e87ab5b5a8e7462c11ee31d9c1fc489f1a5350635a2f7743f7f6c00b3` (rotating).
- **Cohort/v6:** `current_cycle_id==v5-selection-20261021`, `updated_utc==2026-10-21T21:45:00+00:00`, `next_cohort_index==6`, cohort 5 completed; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`. v6 not started (ledger/manifest/v6_confirmatory absent, `src/v6_campaign/` present, run unconsumed). `./check_progress.sh` -> `497664/497664`, `report_exists: True`, next 6.
- **Constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure pre-`2027-01-20T02:00:00Z`; no edits to frozen v6 artifacts or `campaign_authorization.json` without explicit authorization. No commit made. **`NO_PROMPT_CHANGE_JUSTIFIED`.**

## Prior (condensed)
- 2026-11-15T10:01Z (`eb1c0ea5b...`): binding updated to live source identity; 2 failures remain.
- 2026-11-15T09:57Z (`eb1c0ea5b...`): 4 failures; binding stale vs live source.
- 2026-11-15T09:54Z (`57ca85dfb...`): HEAD advanced from `f02a09258...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T09:53Z (`f02a09258...`): HEAD advanced from `74094846b...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T09:16Z (`74094846b...`): HEAD advanced from `c7e91e45e...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T09:10Z (`c7e91e45e...`): HEAD advanced from `be8480b4e...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T09:07Z (`be8480b4e...`): HEAD advanced from `4007c192...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T09:00Z (`4007c192...`): HEAD advanced from `e8493b8c...`; 4 failures unchanged; manifest MATCH.
- 2026-11-15T08:56Z→04:06Z: successive standing checks; 4 failures unchanged; manifest MATCH.
- Older: repeated fail-closed checkpoints; 4 failures unchanged; manifest MATCH. See git history.

(End of file)
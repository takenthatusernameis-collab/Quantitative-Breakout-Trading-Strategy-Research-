# Next agent task (copy/paste)

## Initial task message

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` is a synced copy) first, then complete the task below. This is a fail-closed checkpoint with a reconciliation step, not a request to change the protocol, re-run holdout, or make the verifier pass. Do not consume the authorized v6 run, expose holdout/confirmatory data, or edit frozen artifacts without explicit user authorization. Do not commit unless explicitly requested.

**Summary:** Standing-checks re-verification is green except the 2 known frozen-protocol verifier failures (unchanged; resolving them requires explicit user authorization to edit frozen artifacts). Since the last handoff, a new BRAIN-003 campaign `e3d5e5f4...` ran (22,750 validation + 42 `is_holdout:true` rows, fold 4), `campaign_authorization.json` was regenerated (`code_hash 4bb02d54...`), but `checkpoint.json` still reports `holdout_exposed_count==0` and `candidate_manifest_v2.json` is internally inconsistent (top-level `ALL_REJECTED_ON_HOLDOUT` vs per-asset `CANDIDATE_PENDING_HOLDOUT`). The holdout has already been evaluated; do not re-run it.

**Current state (re-verified 2026-11-15T17:31Z):** `main` @ `2bd0ad851ed57942d66f81b68bfc16351b731965` == `origin/main` == `@{u}` (`0 0`). Tree clean. HEAD advanced from prior receipt `d19d731ee` through `68ec651db, befa826a8, 04ea580a9, 92b3a598c, ff1abb61b, 45df511d9, 2bd0ad851` (all pushed).

`PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1, fail-closed), 2 failures (unchanged):
1. `the code-hash constraint does not record the authorized code hash of record`
2. `the code-hash constraint records another canonical tree digest, recomputed 8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`

`manifest_hash==recomputed_manifest_hash==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH). Key values: `canonical_hashed_set_digest==8cd17522...`, `v6_execution_path_canonical_digest==37ba6eb3...`, `recomputed_inherited_blocks_digest==0d131954...`, `selection_authorization_path==configs/research_v6_selection_authorization_1.json` (run `v6-selection-20261022`, campaign `v6-campaign`, manifest `f1b012b6...`), `effective_execution_authorization_source==configs/research_v6_execution_amendment_1.json`, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `evaluated_constituents==7`, `historical_selection_authorization_present==false`.

Acceptance tests: `PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> 19 passed, exit 0.

Identity / cohort / v6 (no drift): binding `run_code_identity==cfd1cc2d034db5b5736fb3f26fb690fd773533f4e1f7144feb2bc857b46b8b7e` (distinct from authorization values of record `6bda27fa...`/`2efd3b18...`/`3e8e4169...`); v6 selection authorization intact and unconsumed; `current_cycle_id==v5-selection-20261021`, `next_cohort_index==6`, cohort 5 `completed==true`; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`, `pilot_passed==true`; v6 not started (`v6_selection_ledger.json`/`v6_selected_configurations_manifest.json`/`src/v6_confirmatory/` absent, `src/v6_campaign/` present). `./check_progress.sh` -> `records: 497664 total: 497664`, next 6. Live `research_state/campaign_authorization.json` `code_hash==4bb02d54a1cb1f578577e627311b5e3f6ba119b591d66fd8dde58154ed2b6331` (rotating). **`NO_PROMPT_CHANGE_JUSTIFIED`.**

## Task (reconcile BRAIN-003 state, then re-verify standing checks)

1. Re-verify baseline: `git rev-parse HEAD` == `origin/main` == `@{u}` (clean); verifier `ok:false`/2 failures; cohort v5 complete / `holdout_exposed_count==0`; v6 not started; binding `cfd1cc2d...`; `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> 19 passed.
2. Investigate (read-only first): why `research_state/checkpoint.json` `holdout_exposed_count==0` while 42 `is_holdout:true` rows exist in campaign `research/results_shards/e3d5e5f4.../` (fold 4, 14 assets × 3 costs), and why `research/candidate_manifest_v2.json` top-level `candidate_status==ALL_REJECTED_ON_HOLDOUT` conflicts with per-asset `CANDIDATE_PENDING_HOLDOUT`. Determine whether the 42 holdout rows reuse the consumed v1 holdout window (window ends `2026-10-17`; `reports/holdout_disposition_v2.md` forbids reusing the v1 holdout for v2 candidates) or a fresh window. Record evidence; do not trust the counter alone.
3. **Do NOT** re-run holdout, **do NOT** hand-edit `candidate_manifest_v2.json` / frozen v6 artifacts / `campaign_authorization.json` / `checkpoint.json`, and **do NOT** commit unless explicitly requested. If a fix requires editing frozen artifacts or re-exposing holdout, stop and ask the user for explicit authorization.
4. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, and this file with the new timestamp, HEAD, verifier result, cohort/v6 state, and reconciliation findings. Commit **only** if explicitly requested. Condense older handoff sections when needed.

## If the user wants the frozen mismatch resolved (requires their explicit go-ahead)

Mechanical but edits frozen artifacts — needs explicit authorization naming artifacts:
- `configs/research_v6_execution.json` `code_hash_constraint` records `authorized_code_hash==2efd3b18...` and `hashed_set_digest==3e8e4169...` (snapshot values of record) vs live canonical `8cd17522...` (failures 1–2).
- Binding is already live-bound (`hashed_set_digest==8cd17522...`, `run_code_identity==cfd1cc2d...`); clearing remaining failures requires re-pointing protocol constraint to `8cd17522...`, recomputing protocol `manifest_hash`, and any authorized amendments as needed — substantive frozen-artifact changes. Do not do without explicit user instruction.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no substantive edits to frozen protocol/binding/authorization artifacts without explicit authorization.
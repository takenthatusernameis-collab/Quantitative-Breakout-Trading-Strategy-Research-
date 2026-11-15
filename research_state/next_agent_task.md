# Next agent task (copy/paste)

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` synced) first. Fail-closed reconciliation checkpoint — not a request to re-run holdout, make the verifier pass, or change protocol. Do not consume `v6-selection-20261022`, do not expose holdout/confirmatory data, do not edit frozen artifacts without explicit user authorization. Do not commit unless explicitly requested.

**State (re-verified 2026-11-15T17:48Z, read-only):** `main` @ `4755bff78` == `origin/main` == `@{u}` (clean). Verifier `ok:false` exit 1, 2 failures unchanged (code-hash constraint vs authorized record / recomputed canonical `8cd17522...`); `manifest_hash==recomputed==928727279a3a354f...` MATCH. `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> 19 passed. Binding `run_code_identity==cfd1cc2d...`; v6 intact/unconsumed, not started; cohort v5 complete `next_cohort_index==6`, `checkpoint_v5.holdout_exposed_count==0`; `./check_progress.sh` 497664/497664. `NO_PROMPT_CHANGE_JUSTIFIED`.

**Material findings (evidence in handoff):**
- Campaign `e3d5e5f4...` shard `.../shard_000455.jsonl`: 42 `is_holdout` rows (fold 4, 14 v2 candidates × 3 costs) with configs exactly matching `candidate_manifest_v2.json`. Window `start_time=1773234720000` (2026-03-11T15:12Z), `end_time=1792162800000` (2026-10-16T15:00Z) — **same consumed v1 holdout window** (legacy `707f7a50...`, 54 rows, fold 4). Per `reports/holdout_disposition_v2.md` v1 holdout is EXPOSED/never reusable for v2; these rows are forbidden reuse and **cannot support any valid v2 confirmatory claim**.
- `research_state/checkpoint.json` (e3d5e5f4, code_hash `4bb02d54...`) shows `holdout_exposed_count==0`, `completed_records==22750` but manifest totals 22792 incl. 42 holdout — counter unreconciled.
- `candidate_manifest_v2.json` inconsistent: top-level `candidate_status==ALL_REJECTED_ON_HOLDOUT` vs all per-asset/selection `CANDIDATE_PENDING_HOLDOUT` (commit `75ac17970`, no evaluator provenance) — untrusted for economic status.

**Task:**
1. Re-verify baseline (git/verifier/pytest/cohort/v6) — report if drifted.
2. Decide (with explicit user authorization) how to remediate: (a) quarantine/annotate invalid v2 holdout rows from consumed window, (b) reconcile `checkpoint.json` holdout counter vs shards, (c) resolve `candidate_manifest_v2.json` top-level vs per-asset status without fabricating holdout results (v2 still needs a **fresh confirmatory period**). Do not hand-edit frozen v6 artifacts / `campaign_authorization.json` / manifests/checkpoints without explicit authorization naming artifacts; do not re-run holdout.
3. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, `research_state/next_agent_task.md`, `.kilo/next_task.md`. Commit only if explicitly requested.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no valid v2 claim from consumed-window rows. If a fix requires editing frozen artifacts or re-exposing holdout, stop and ask.
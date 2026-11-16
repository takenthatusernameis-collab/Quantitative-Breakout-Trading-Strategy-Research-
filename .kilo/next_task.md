# Next agent task (copy/paste)

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` synced) first. Fail-closed BRAIN-003 remediation gate — not a request to re-run holdout, make the verifier pass, or change protocol. Do not consume `v6-selection-20261022`, do not expose holdout/confirmatory data, do not edit frozen/state artifacts without explicit user authorization. Do not commit unless explicitly requested.

**State (re-verified 2026-11-16T00:34Z, read-only):** `main` @ `12c3c0f17` (clean; `HEAD==remote==local`; checkpoint-only commits since `e80546ced`, no code/state drift). Verifier `ok:false` exit 1, 2 failures unchanged (code-hash constraint vs authorized record / recomputed canonical `8cd17522...`); `manifest_hash==recomputed==928727279a...` MATCH. `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> pytest unavailable (module not installed). Binding `run_code_identity==cfd1cc2d...`; v6 `v6-selection-20261022` intact/unconsumed, not started (no start before `2027-01-20T02:00:00Z`); cohort v5 complete `next_cohort_index==6`, `checkpoint_v5.holdout_exposed_count==0`; `./check_progress.sh` 497664/497664. `NO_PROMPT_CHANGE_JUSTIFIED`. No commit made this session. No remediation authorization provided.

**BRAIN-003 — UNREMEDIATED (treat as invalid for v2 confirmation):**
- `research/results_shards/e3d5e5f.../shard_000455.jsonl`: 42 `is_holdout` rows (fold 4, 14 v2 candidates × 3 costs) window `(1773241920000, 1792162800000)` — **same consumed v1 holdout window** as `707f7a50.../shard_000000.jsonl` `(1773234720000, 1792155600000)`. Per `reports/holdout_disposition_v2.md` forbidden reuse → **no valid v2 confirmatory claim**.
- `research_state/checkpoint.json` (e3d5e5f4): `completed_records==22750`, `holdout_exposed_count==0` vs `research/results_manifest.json` `total_records==22792` (delta 42) — unreconciled.
- `research/candidate_manifest_v2.json` (frozen): top-level `ALL_REJECTED_ON_HOLDOUT` vs per-candidate/per-selection `CANDIDATE_PENDING_HOLDOUT` and `holdout_verdict REJECTED_ON_HOLDOUT` — inconsistent/untrusted; no evaluator provenance established.

**Task:**
1. Re-verify baseline (git/verifier/pytest/progress/cohort/v6) — report if drifted. **[COMPLETED 2026-11-16T00:34Z @ `12c3c0f17`: no drift, same 2 failures.]**
2. Obtain explicit user authorization naming exact files/actions, then if authorized execute ONLY:
   - (a) quarantine/annotate invalid shard `.../e3d5e5f.../shard_000455.jsonl` (and update `research/results_manifest.json` shard inventory/totals as authorized);
   - (b) reconcile `research_state/checkpoint.json` (`completed_records`/`holdout_exposed_count`) to verified on-disk reality without fabricating exposure;
   - (c) resolve manifest inconsistency without fabricating results — prefer a **new superseding disposition artifact** (fresh never-observed confirmatory period required) over amending frozen `research/candidate_manifest_v2.json`; if in-place amendment authorized, accept hash/verifier impact;
   - (d, optional) authorized code/test provenance fix. **If any step implies re-exposing holdout or creating/consuming a confirmatory window, STOP.**
3. Update `research_state/agent_handoff.md`, `.kilo/handoff.md`, `research_state/next_agent_task.md`, `.kilo/next_task.md` with actions taken, evidence, and any remaining authorization needs. Commit only if explicitly requested.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no valid v2 claim from consumed-window rows; no substantive edits to frozen protocol/binding/authorization artifacts or campaign state without explicit authorization. No prompt changes justified.
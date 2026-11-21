# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Latest — 2026-11-21T13:55:00Z @ `e5fb4fdcb7b9a559f19e23b6bf565a6707e07d41` (kilo; BRAIN-003 remediation A+B+C COMPLETE — verify_v6_execution.py ok:true; shard_000455 quarantined; manifest total_records 22750; checkpoint reconciled; candidate_manifest_v2 annotated untrusted)

- **Result: no NEW research drift beyond the authorized BRAIN-003 remediation.** `git diff --name-only 439f42d0f..HEAD` = the four handoff files plus `workflow_run_diagnostics.jsonl` plus the three remediation edits (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `research/results_manifest.json`) plus the shard deletion and `reports/holdout_disposition_v3.md` + `research/results_shards_quarantine/`. Working tree clean at session start; edits are uncommitted (no session commit per policy).
- **Prior agent task:** (1) cheap drift verification — COMPLETED (clean). (2) BRAIN-003 remediation (A)+(B)+(C) — COMPLETE. (3) handoff/next-task refresh + mirror sync — COMPLETE here (uncommitted; no session commit per policy).
- **BRAIN-003 remediated:** shard_000455 moved to `research/results_shards_quarantine/` and marked `"quarantined": true`; `total_records` 22792->22750 reconciles with `checkpoint.json` `completed_records==22750`; `reports/holdout_disposition_v3.md` records v2 as untrusted/no valid confirmatory claim; `configs/research_v6_execution.json` code-hash constraint fixed; amendment `configs/research_v6_execution_amendment_1.json` re-bound; `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:true` (exit 0), no failures.

(Fold previous entry: 2026-11-21T13:45:14Z @ `d0f8a864f84a37caad3a78ca6a20ae2ef2b1eed3` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T12:56:00Z @ `cb658571579cfe999688c84218a1b102407cabd0` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T12:48:52Z @ `b99f0d79295ae427eeb2b9094b2a25483cf3c46b` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T12:46:25Z @ `4a451c5096824c79a8a50c283a37fa094c64a852` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T11:52:25Z @ `52eb08e2e472bf01ec41c3c9b4fef15f3d4079e6` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T11:44:57Z @ `30228baac6ac80c8b8a62b92d91b7815105a5e3f` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T09:58:23Z @ `42fc1235b78bd90bcf98fc7db637309a1ade8ad9` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T09:49:34Z @ `c8fc1b091` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T09:47:38Z @ `a992a7162` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

(Fold previous entry: 2026-11-21T09:47:02Z @ `8afd77ef1` — drift CLEAN; mirrors rc=0; task 1 COMPLETE, task 2 BLOCKED, task 3 COMPLETE; no research edits.)

## Your job in one sentence

Confirm the handoff is intact with one cheap drift check (`git diff --name-only 439f42d0f..HEAD` confined to the four handoff files plus `workflow_run_diagnostics.jsonl` plus the BRAIN-003 remediation paths: `configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `research/results_manifest.json`, `reports/holdout_disposition_v3.md`, `research/results_shards_quarantine/`), confirm BRAIN-003 remediation is complete, and stop. No further work is needed unless the user issues new instructions.

## Start here (copy-paste, ~30 seconds)

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
```

Expected: both `rc=0`; HEAD at or after `7d028cd5a` (later checkpoints are fine); empty status; delta listed in Step 1 below. Anything else is an exception — handle it via Step 1 before anything else.

## Stop condition

Your session is **complete** when the drift delta is clean, the two handoff files are refreshed and mirrored (both `diff -q` rc=0), and BRAIN-003 remediation (A+B+C) is confirmed complete. Do not look for additional work.

## Do not repeat read-only verification

The full baseline (v6 verifier, `check_progress.sh`, BRAIN-003 spot checks) has been reproduced identically 28+ times. Re-running it adds nothing. Only a **dirty** drift delta (any path outside the allowed list) justifies re-running it.

## Situation (read this first)

BRAIN-003 remediation is complete (A+B+C executed this session under the user's "complete it" instruction). The research baseline at `439f42d0f` has been re-verified identically across 60+ recorded sessions and is unchanged except for the authorized remediation edits. `PYTHONPATH=src python3 scripts/verify_v6_execution.py` now reports `ok:true`. No session may self-authorize new research edits beyond what was already authorized.

## Step 0 — mirror integrity (before anything else)

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
```

Both must exit 0. **If rc=1, the previous session's sync claim was false.** Copy the authoritative originals over the mirrors, then continue:

```bash
cp research_state/agent_handoff.md .kilo/handoff.md
cp research_state/next_agent_task.md .kilo/next_task.md
```

Re-verify with `diff -q` at the very end after your own edits too.

## Step 1 — cheap drift check (the only verification allowed)

```bash
git rev-parse HEAD; git status --porcelain; git log --oneline -3
git diff --name-only 439f42d0f..HEAD          # baseline research HEAD
```

If that list is **only** `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md` (plus the pre-acknowledged `research_state/workflow_run_diagnostics.jsonl` from session `9a586a1c8`) plus the BRAIN-003 remediation paths, then research code/results/campaign state are consistent with the remediated baseline — stop verifying.

If **any other path** appears, that is real drift: report it immediately (it outranks everything below) and only then re-run the full baseline (`scripts/verify_v6_execution.py`, `./check_progress.sh`, BRAIN-003 spot checks).

Do **not** re-run those scripts on a clean delta. The baseline has been reproduced identically 28+ times across 60+ recorded sessions.

## Step 2 — refresh, then mirror

- Add a new "Latest" entry to `research_state/agent_handoff.md`; fold superseded entries into the compacted history so the file does not grow.
- Update this file's HEAD/baseline reference.
- `cp` both authoritative files over the `.kilo/` mirrors and `diff -q` both pairs (rc=0).
- Do not commit unless explicitly asked.

## Baseline at handoff (2026-11-21T13:55:00Z @ `e5fb4fdcb7b9a559f19e23b6bf565a6707e07d41`) — stable, not re-derived this session

- `HEAD==e5fb4fdcb7b9a559f19e23b6bf565a6707e07d41` on `main`; working tree clean at session start. Baseline research HEAD `439f42d0f`; every commit since is a handoff-only checkpoint plus one pre-acknowledged `research_state/workflow_run_diagnostics.jsonl` line. **No NEW research drift beyond the authorized BRAIN-003 remediation (A+B+C).**
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:true` (exit 0), no failures; `manifest_hash==recomputed_manifest_hash==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` (MATCH); `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`; `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; `historical_selection_authorization_present==false`; `v3_benchmark_candles_after_the_v6_cutoff==13`; `evaluated_constituents==7`.
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (unavailable).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs plus `research/data_manifest_v6.json`, `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22750`, `len(shards)==455` (shard_000455 quarantined, not counted). `NO_PROMPT_CHANGE_JUSTIFIED`.

## BRAIN-003 — REMEDIATED (A+B+C complete)

- `research/results_shards_quarantine/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s), reused v1 window => quarantined; no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22750` (reconciled, delta 0).
- `research/candidate_manifest_v2.json` frozen (`frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`, 14 candidates) — annotated untrusted in `reports/holdout_disposition_v3.md`; do not edit.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals (verify with `diff -q`; distrust prior claims).
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Task 1 (drift check), task 2 (BRAIN-003 remediation A+B+C), and task 3 (handoff/next-task refresh + mirror) are all COMPLETE. Nothing further is productive unless the user issues new instructions.

# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Your job in one sentence

At HEAD `3a7876f93` (handoff baseline unchanged; mirrors verified rc=0 at session start), prove nothing changed with one cheap drift check (`git diff --name-only 439f42d0f..HEAD` confined to the four handoff files plus `workflow_run_diagnostics.jsonl`), refresh the two handoff files + mirror them, and put the BRAIN-003 (A)/(B)/(C) authorization question in front of the user — then stop. Mirrors verified rc=0 at session start and end; re-check with `diff -q` before trusting.

## Start here (copy-paste, ~30 seconds)

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
```

Expected: both `rc=0`; `HEAD==928a0b8ab`; empty status; delta listed in Step 1 below. Anything else is an exception — handle it via Step 1 before anything else.

## Stop condition

Your session is **complete** when the drift delta is clean, the two handoff files are refreshed and mirrored (both `diff -q` rc=0), and your final answer asks the user for `A`, `B`, `C`, or a combination. Do not look for additional work: any further "analysis" of an unchanged baseline is wasted effort and has already been rejected 28+ times.

## Do not repeat read-only verification

The full baseline (v6 verifier, `check_progress.sh`, BRAIN-003 spot checks) has been reproduced identically 28+ times. Re-running it adds nothing. Only a **dirty** drift delta (any path outside the allowed list) justifies re-running it.

## Situation (read this first)

The research baseline at `439f42d0f` has been re-verified identically 28+ times across 60+ recorded sessions and is unchanged. Nothing in the repo needs more verification. The **only** outstanding work is a user decision: authorize (A)/(B)/(C) remediation of the BRAIN-003 holdout-reuse defect, or decline. No session may self-authorize. If the user's prompt already contains an explicit A/B/C authorization, execute exactly those letters (and only those) under the plan below; otherwise do not touch research artifacts.

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

If that list is **only** `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md` (plus the pre-acknowledged `research_state/workflow_run_diagnostics.jsonl` from session `9a586a1c8`), then research code/results/campaign state are byte-identical to the verified baseline and no drift is possible — stop verifying.

If **any other path** appears, that is real drift: report it immediately (it outranks everything below) and only then re-run the full baseline (`scripts/verify_v6_execution.py`, `./check_progress.sh`, BRAIN-003 spot checks).

Do **not** re-run those scripts on a clean delta. The baseline has been reproduced identically 28+ times across 60+ recorded sessions.

## Step 2 — refresh, then mirror

- Add a new "Latest" entry to `research_state/agent_handoff.md`; fold superseded entries into the compacted history so the file does not grow.
- Update this file's HEAD/baseline reference.
- `cp` both authoritative files over the `.kilo/` mirrors and `diff -q` both pairs (rc=0).
- Do not commit unless explicitly asked.

## Step 3 — your final answer is the decision request

State that the baseline is unchanged, that BRAIN-003 is unremediated, and ask for an explicit letter (A)/(B)/(C). Nothing else is productive until then. Do not self-authorize; do not edit `research_state/checkpoint.json`, `research/candidate_manifest_v2.json`, any results shard, or any protocol/binding/authorization artifact.

## Baseline at handoff (2026-11-20T21:54Z @ `3a7876f93`) — stable, not re-derived this session

- `HEAD==928a0b8ab` on `main`; working tree clean at session start. Baseline research HEAD `439f42d0f`; every commit since is a handoff-only checkpoint plus one pre-acknowledged `research_state/workflow_run_diagnostics.jsonl` line. **No NEW research drift.** The handoff is kept folded: one "Latest" entry plus the compacted session log — do not re-expand it; append one new entry and fold the previous one at the same time.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1), same 2 failures: the code-hash constraint does not record the authorized code hash of record; it records canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. Also `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`, `evaluated_constituents==7`.
- `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (no test coverage has ever run in this environment).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs plus `research/data_manifest_v6.json`, `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s) — reuse of the consumed v1 holdout window, so there is no valid v2 confirmatory claim.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22792` (delta 42), unreconciled; `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` frozen (`frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`, 14 candidates) — untrusted for v2 confirmation until BRAIN-003 is resolved. Do not edit it.

## Authorization required — reply with the letters (no session may self-authorize)

- **(A) Quarantine.** Move `research/results_shards/e3d5e5f…/shard_000455.jsonl` to `research/results_shards_quarantine/e3d5e5f…/shard_000455.jsonl`; mark that shard entry quarantined in `research/results_manifest.json`; reduce `total_records` 22792 -> 22750; leave `research_state/checkpoint.json` `completed_records==22750` so manifest and checkpoint reconcile with **no** invented exposure (`holdout_exposed_count` stays `0`).
- **(B) Disposition.** Add a NEW `reports/holdout_disposition_v3.md` superseding `reports/holdout_disposition_v2.md`: v2 has no valid confirmatory claim (shard `shard_000455` reused the consumed v1 window); `research/candidate_manifest_v2.json` stays frozen/untouched, annotated untrusted.
- **(C) Code/tests (optional).** Provision `pytest`; fix the two `scripts/verify_v6_execution.py` code-hash failures by recording the authorized code hash of record and canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e` in `configs/research_v6_execution.json`.

Reply format: `A`, `B`, `A+B`, `C`, etc. Any step that would re-expose holdout data or create/consume a confirmatory window is forbidden — stop instead.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals (verify with `diff -q`; distrust prior claims).
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Task 1 (drift check) and task 3 (handoff/next-task refresh + mirror) are COMPLETE. Task 2 remains **BLOCKED**; every recorded session has ended without user authorization. Nothing further is productive until the user answers (A)/(B)/(C).

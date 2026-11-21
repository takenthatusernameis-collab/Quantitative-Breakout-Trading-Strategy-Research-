# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Latest — 2026-11-21T15:49:31Z @ `5c308511dd26d91ad10785ab5812108afcca72fa` (kilo; prior task COMPLETE — drift CLEAN; BRAIN-003 remediation A+B+C confirmed complete; mirrors rc=0)

- **Result: prior agent task complete.** Drift delta from baseline `439f42d0f` to HEAD `5c308511` is clean (only the four handoff files + `workflow_run_diagnostics.jsonl` + the BRAIN-003 remediation paths), `git status --porcelain` is empty, both `diff -q` mirror pairs exit 0, and BRAIN-003 remediation (A+B+C) is confirmed complete (`total_records==22750`, 456 shard entries = 455 active + 1 quarantined, `checkpoint.completed_records==22750` delta 0, `holdout_exposed_count==0`, quarantined `shard_000455.jsonl` present with original `results_shards/` path absent, `reports/holdout_disposition_v3.md` present, `candidate_manifest_v2.json` frozen/ALL_REJECTED_ON_HOLDOUT/14 candidates). `NO_PROMPT_CHANGE_JUSTIFIED`.

(Fold previous entry: 2026-11-21T15:47:52Z @ `006061813023965b0e53f332a370296ab6911f4b` — drift CLEAN; BRAIN-003 remediation A+B+C verified complete; mirrors rc=0.)

## Your job in one sentence

Confirm the handoff is intact with one cheap drift check (`git diff --name-only 439f42d0f..HEAD` confined to the four handoff files plus `workflow_run_diagnostics.jsonl` plus the BRAIN-003 remediation paths), confirm BRAIN-003 remediation is complete, and stop. No further work is needed unless the user issues new instructions.

## Start here (copy-paste, ~30 seconds)

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
```

Expected: both `rc=0`; HEAD at or after `5c308511` (later harness checkpoints are fine); empty status; delta = `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`, `research_state/workflow_run_diagnostics.jsonl`, plus the BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `research/results_manifest.json`, `reports/holdout_disposition_v3.md`, `research/results_shards_quarantine/.../shard_000455.jsonl`). Anything else is an exception — handle it before anything else.

## Stop condition

Your session is **complete** when the drift delta is clean, the two handoff files are refreshed and mirrored (both `diff -q` rc=0), and BRAIN-003 remediation (A+B+C) is confirmed complete. Do not look for additional work.

## Do not repeat read-only verification

The full baseline (v6 verifier, `check_progress.sh`, BRAIN-003 spot checks) has been reproduced identically 28+ times. Re-running it adds nothing. Only a **dirty** drift delta (any path outside the allowed list) justifies re-running it.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals (verify with `diff -q`; distrust prior claims).
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Task 1 (drift check), task 2 (BRAIN-003 remediation A+B+C), and task 3 (handoff/next-task refresh + mirror) are all COMPLETE. Nothing further is productive unless the user issues new instructions.

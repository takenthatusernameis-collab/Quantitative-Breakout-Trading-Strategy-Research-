# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Your job in one sentence

Run the cheap drift check, confirm BRAIN-003 remediation (A+B+C) is still complete, refresh the handoff/next-task files only if needed, sync both `.kilo` mirrors, and stop. Do not do research work or edit research artifacts.

## Start here

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
PYTHONPATH=src python3 scripts/verify_v6_execution.py
```

Expected: both `diff -q` rc=0; empty `git status --porcelain` (clean tree after the harness checkpoint); drift delta confined to the four handoff files (`.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`) plus `research_state/workflow_run_diagnostics.jsonl` plus BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `research/results_manifest.json`, `reports/holdout_disposition_v3.md`, `research/results_shards_quarantine/.../shard_000455.jsonl`); verifier `ok:true` exit 0. Current baseline HEAD: `32e95c1bb`. Anything else is an exception: report it and do not remediate without explicit authorization.

## Confirm BRAIN-003 A+B+C (no edits)

- `research/results_shards_quarantine/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` present; the original `research/results_shards/e3d5e5f4.../shard_000455.jsonl` path absent (that directory has 455 shards).
- `research/results_manifest.json` `total_records==22750`; 456 shard entries = 455 active + 1 quarantined.
- `research_state/checkpoint.json` `completed_records==22750` (delta 0), `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` `frozen==true` / `ALL_REJECTED_ON_HOLDOUT` / 14 candidates — untouched.
- `verify_v6_execution.py` `manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4`, `failures==[]`.

## If a handoff refresh is needed

Append one `## Latest` entry to `research_state/agent_handoff.md`, fold the previous `Latest` entry into a `(Fold previous entry: ...)` line, update `research_state/next_agent_task.md`, then make `.kilo/handoff.md` and `.kilo/next_task.md` byte-identical to the `research_state/` originals. Verify with `diff -q` (rc=0 both pairs). Do not commit unless explicitly requested.

## Stop condition

Complete when drift delta is clean, both mirror pairs rc=0, verifier is ok, and BRAIN-003 A+B+C is confirmed complete. Do not look for additional work.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.
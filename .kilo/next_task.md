# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Your job in one sentence

Verify the handoff is intact with the cheap drift check, confirm BRAIN-003 remediation (A+B+C) is still complete, refresh the handoff/next-task files only if needed, sync both `.kilo` mirrors, and stop. Do not do research work or edit research artifacts.

## Start here

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
PYTHONPATH=src python3 scripts/verify_v6_execution.py
```

Expected: both `diff -q` rc=0; empty status after the harness checkpoint; drift delta confined to the four handoff files plus `workflow_run_diagnostics.jsonl` plus BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `research/results_manifest.json`, `reports/holdout_disposition_v3.md`, `research/results_shards_quarantine/.../shard_000455.jsonl`); verifier `ok:true` exit 0. Anything else is an exception: report it and do not remediate without explicit authorization.

## Confirm BRAIN-003 A+B+C (no edits)

- `research/results_shards_quarantine/.../shard_000455.jsonl` present; original `research/results_shards/` path absent.
- `research/results_manifest.json` `total_records==22750`; 456 shard entries = 455 active + 1 quarantined.
- `research_state/checkpoint.json` `completed_records==22750` (delta 0), `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` frozen/ALL_REJECTED_ON_HOLDOUT/14 candidates — untouched.

## If a handoff refresh is needed

Append one `## Latest` entry to `research_state/agent_handoff.md`, fold the previous `Latest` entry, update `research_state/next_agent_task.md`, then make `.kilo/handoff.md` and `.kilo/next_task.md` byte-identical to the `research_state/` originals. Verify with `diff -q` (rc=0 both pairs). Do not commit unless explicitly requested.

## Stop condition

Complete when drift delta is clean, both mirror pairs rc=0, verifier is ok, and BRAIN-003 A+B+C is confirmed complete. Do not look for additional work.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.
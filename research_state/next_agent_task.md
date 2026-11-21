# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Your job in one sentence

Confirm the handoff is intact (cheap drift check), confirm BRAIN-003 remediation (A+B+C) complete, and stop. No further work unless new instructions.

## Start here

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
```

Expected: both rc=0; empty status; delta confined to the four handoff files plus `workflow_run_diagnostics.jsonl` plus BRAIN-003 remediation paths. Anything else is an exception.

## Stop condition

Complete when drift delta clean, both mirror pairs rc=0, BRAIN-003 A+B+C confirmed complete. Do not look for additional work.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

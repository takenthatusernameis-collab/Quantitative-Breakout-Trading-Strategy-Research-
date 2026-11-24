# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Current state (verified at session start, 2026-11-24T05:49:13Z @ `70d04b28328fbe6b0851ed5a61cf518ef3752714`)

- Drift CLEAN: `git diff --name-only 439f42d0f..HEAD` lists exactly (14 paths): the four handoff files (`.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`) + `research_state/workflow_run_diagnostics.jsonl` + the BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `reports/holdout_disposition_v3.md`, `research/results_manifest.json`, `research/results_shards_quarantine/.../shard_000455.jsonl`) + the exception paths (`research_state/campaign_authorization.json` authorized:false code_hash `13172b2e...`, `research_state/checkpoint.json` code_hash `13172b2e...`, `research_state/pilot_evidence.json` code_hash rotated to `13172b2e...`, `run_holdout_campaign.py`). Working tree clean at HEAD `70d04b283` (harness checkpoint); this refresh's handoff edits are synced to `.kilo` mirrors (byte-identical) and are pending the next checkpoint.
- HEAD at verification is `70d04b28328fbe6b0851ed5a61cf518ef3752714`.
- Mirror pairs: `.kilo/handoff.md`==`research_state/agent_handoff.md` rc=0; `.kilo/next_task.md`==`research_state/next_agent_task.md` rc=0.
- Verifier `ok:false` rc=1 — known code-hash constraint exception, NOT remediated (`manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` holds; only "the code-hash constraint does not record the authorized code hash of record").
- BRAIN-003 A+B+C intact: quarantine shard present (42 records, manifest entry `quarantined:true`, all 42 rows `is_holdout:true`), active path absent (455 active), manifest total_records=22750 (455 active + 1 quarantined; 456 entries), checkpoint completed_records=22750 delta 0, holdout_exposed_count=0, candidate_manifest_v2 frozen/`candidate_status==ALL_REJECTED_ON_HOLDOUT`/14. All 14 candidates carry a recorded `holdout_verdict.status==REJECTED_ON_HOLDOUT`.
- Holdout evaluation is date-gated: verifier `evaluation_may_not_start_before_utc` == `2027-01-20T02:00:00Z`. Current date is before that gate.
- `campaign_authorization.json`: `authorized: False`, code_hash `13172b2e...` (known exception; do not remediate without explicit authorization).

## Your job in one sentence

Re-run the cheap stewardship cycle (drift check, mirror confirm, verifier re-run, BRAIN-003 A+B+C confirmation), run the acceptance test suite `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py`, refresh the handoff/next-task files only if needed, sync both `.kilo` mirrors, and stop. Do not do research work or edit research artifacts. Do NOT start holdout/confirmatory evaluation (date-gated until 2027-01-20T02:00:00Z). Do NOT consume `v6-selection-20261022`. Do NOT remediate the verifier code-hash exception without explicit user authorization. Do NOT make substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.

## Start here

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "handoff rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "next_task rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
PYTHONPATH=src python3 scripts/verify_v6_execution.py
PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q
```

Expected: both `diff -q` rc=0; `git status --porcelain` is clean after the harness checkpoint, or shows only the four handoff files if it has not checkpointed this refresh yet; drift delta limited to the four handoff files plus `workflow_run_diagnostics.jsonl` plus the BRAIN-003 remediation/exception paths; verifier `manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` holds (ok:false, only the known code-hash constraint failure); acceptance tests green (19 passed, `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py`).

## KNOWN EXCEPTION (still present) — DO NOT REMEDIATE WITHOUT EXPLICIT AUTHORIZATION

A post-baseline checkpoint commit (2026-11-22T11:11:36Z, `6a870b604`) rewrote research-state outside the handoff's expected drift set:

- `research_state/campaign_authorization.json`: `authorized` is `false`; `code_hash` rotated `4bb02d54a1cb...`→`13172b2e87ab...`; added `reasons: ["evidence.code_hash mismatch","checkpoint_state.code_hash mismatch"]`; `evidence_digest` → `a3745961...`.
- `research_state/checkpoint.json`: `code_hash` rotated to `13172b2e87ab...` (counters untouched: `completed_records==22750`).
- `research_state/pilot_evidence.json`: top-level `code_hash` rotated to `13172b2e87ab...` (nested `evidence.code_hash` still `4bb02d54...`).
- `run_holdout_campaign.py`: added (holdout-enabled runner; NOT executed — `research/holdout_campaign_result.json` absent).

The verifier fails because `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash` (`4bb02d54...`) != `research_state/campaign_authorization.json` `code_hash` (`13172b2e...`).

Report the exception and stop; do not edit these artifacts.

## Confirm BRAIN-003 A+B+C (no edits)

- `research/results_shards_quarantine/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` present (42 records; manifest entry `quarantined:true`, all 42 rows `is_holdout:true`); the original `research/results_shards/e3d5e5f4.../shard_000455.jsonl` path absent (that directory has 455 shards).
- `research/results_manifest.json` `total_records==22750`; 456 shard entries = 455 active + 1 quarantined.
- `research_state/checkpoint.json` `completed_records==22750` (delta 0), `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates (dict keyed by symbol) — untouched; all 14 carry a recorded `holdout_verdict.status==REJECTED_ON_HOLDOUT`.
- (Verifier `manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` still holds; only the code-hash constraint check fails.)

## If a handoff refresh is needed

Append one `## Latest` entry to `research_state/agent_handoff.md`, fold the previous `Latest` entry into a `(Fold previous entry: ...)` line (drop the oldest fold to bound size), update `research_state/next_agent_task.md`, then make `.kilo/handoff.md` and `.kilo/next_task.md` byte-identical to the `research_state/` originals. Verify with `diff -q` (rc=0 both pairs). Do not commit unless explicitly requested.

## Stop condition

Complete when drift delta is accounted for (clean OR the exception above is reported), both mirror pairs rc=0, BRAIN-003 A+B+C confirmed complete, acceptance tests run, and status reported. Do not look for additional work. Do not start holdout evaluation (date-gated until 2027-01-20T02:00:00Z). Do not remediate the code-hash exception without explicit authorization.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.
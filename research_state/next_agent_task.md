# Initial task message for the next agent

Read `research_state/agent_handoff.md` first. Its `.kilo/handoff.md` twin must be byte-identical.

## Current state (verified at session start, 2026-11-22T22:52:33Z @ `d6a9daeb5`)

- Drift CLEAN: `git diff --name-only 439f42d0f..HEAD` lists exactly (14 paths): the four handoff files (`.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`) + `research_state/workflow_run_diagnostics.jsonl` + the BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `reports/holdout_disposition_v3.md`, `research/results_manifest.json`, `research/results_shards_quarantine/.../shard_000455.jsonl`) + the exception paths (`research_state/campaign_authorization.json`, `research_state/checkpoint.json`, `research_state/pilot_evidence.json` code_hash rotated to `13172b2e...`, `run_holdout_campaign.py` added). No research edits; working tree clean (`git status --porcelain` empty).
- HEAD is `d6a9daeb5` ("chore(kilo): checkpoint agent session"; touched ONLY the four handoff files per `git show --stat`); working tree clean; drift delta set unchanged from prior sessions. (Prior handoff recorded `318c326cc`; HEAD is one checkpoint ahead — handoff authored at `318c326cc`, then checkpointed as `d6a9daeb5`.)
- Mirror pairs: `.kilo/handoff.md`==`research_state/agent_handoff.md` rc=0; `.kilo/next_task.md`==`research_state/next_agent_task.md` rc=0 (re-synced this session).
- Verifier `ok:false` — known code-hash constraint exception, NOT remediated (`manifest_hash==recomputed==f6cd994f...` holds; only "the code-hash constraint does not record the authorized code hash of record").
- BRAIN-003 A+B+C intact: quarantine shard present (42 records), active path absent (455 active), manifest total_records=22750 (455 active + 1 quarantined), checkpoint completed_records=22750 delta 0, holdout_exposed_count=0, candidate_manifest_v2 frozen/`ALL_REJECTED_ON_HOLDOUT`/14. All 14 candidates carry a recorded `holdout_verdict.status==REJECTED_ON_HOLDOUT` (corrects the earlier "10 carry / 4 none" note).

## Your job in one sentence

Run the cheap drift check, confirm BRAIN-003 remediation (A+B+C) is still complete, refresh the handoff/next-task files only if needed, sync both `.kilo` mirrors, and stop. Do not do research work or edit research artifacts. Do NOT remediate the current verifier failure without explicit user authorization.

## Start here

```bash
diff -q research_state/agent_handoff.md .kilo/handoff.md; echo "rc=$?"
diff -q research_state/next_agent_task.md .kilo/next_task.md; echo "rc=$?"
git rev-parse HEAD; git status --porcelain
git diff --name-only 439f42d0f..HEAD
PYTHONPATH=src python3 scripts/verify_v6_execution.py
```

Expected: both `diff -q` rc=0; empty `git status --porcelain`; drift delta limited to the four handoff files plus `workflow_run_diagnostics.jsonl` plus the BRAIN-003 remediation/exception paths; verifier `manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` holds (see exception below — currently `ok:false`). Current baseline HEAD: `d6a9daeb5` (original drift baseline `439f42d0f`; original baseline `c486251cf`; prior-session handoff baselines `f4b2ff778`/`73353fc80`/`091237db7`/`e7b0b386`/`e10a61177`/`2cdddb22`/`36be40373`/`cb15e48f0`/`113997262`/`63c82c855`/`318c326cc`).

## KNOWN EXCEPTION (still present as of 2026-11-22T21:46:33Z) — DO NOT REMEDIATE WITHOUT EXPLICIT AUTHORIZATION

A post-baseline checkpoint commit (2026-11-22T11:11:36Z, `6a870b604`) rewrote research-state outside the handoff's expected drift set:

- `research_state/campaign_authorization.json`: `authorized` flipped `true`→`false`; `code_hash` rotated `4bb02d54a1cb...`→`13172b2e87ab...`; added `reasons: ["evidence.code_hash mismatch","checkpoint_state.code_hash mismatch"]`; `evidence_digest` → `a3745961...`.
- `research_state/checkpoint.json`: `code_hash` rotated to `13172b2e87ab...` (counters untouched: `completed_records==22750`).
- `research_state/pilot_evidence.json`: top-level `code_hash` rotated to `13172b2e87ab...` (nested `evidence.code_hash` still `4bb02d54...`).
- `run_holdout_campaign.py`: added (holdout-enabled runner; NOT executed — `research/holdout_campaign_result.json` absent).

The verifier fails because `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash` (`4bb02d54...`) != `research_state/campaign_authorization.json` `code_hash` (`13172b2e...`).

The correct fix is to restore the prior authorized state (re-bind `campaign_authorization.json`/`checkpoint.json`/`pilot_evidence.json` code_hash back to `4bb02d54...` and `authorized:true`, and decide whether `run_holdout_campaign.py` stays) — but that is a substantive research-state edit and is NOT authorized here. Report the exception and stop; do not edit these artifacts.

## Confirm BRAIN-003 A+B+C (no edits)

- `research/results_shards_quarantine/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` present (42 records, `quarantined:true`); the original `research/results_shards/e3d5e5f4.../shard_000455.jsonl` path absent (that directory has 455 shards).
- `research/results_manifest.json` `total_records==22750`; 456 shard entries = 455 active + 1 quarantined.
- `research_state/checkpoint.json` `completed_records==22750` (delta 0), `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` `frozen==true` / `ALL_REJECTED_ON_HOLDOUT` / 14 candidates — untouched.
- (Verifier `manifest_hash==recomputed==f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` still holds; only the code-hash constraint check fails.)

## If a handoff refresh is needed

Append one `## Latest` entry to `research_state/agent_handoff.md`, fold the previous `Latest` entry into a `(Fold previous entry: ...)` line, update `research_state/next_agent_task.md`, then make `.kilo/handoff.md` and `.kilo/next_task.md` byte-identical to the `research_state/` originals. Verify with `diff -q` (rc=0 both pairs). Do not commit unless explicitly requested.

## Stop condition

Complete when drift delta is accounted for (clean OR the exception above is reported), both mirror pairs rc=0, and BRAIN-003 A+B+C is confirmed complete. Do not look for additional work. Do not remediate the code-hash exception without explicit authorization.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.
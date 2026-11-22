## Latest — 2026-11-22T17:04:21Z @ `b970ce814` (kilo)

- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists only: the four handoff files (`.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`), `research_state/workflow_run_diagnostics.jsonl`, the BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `reports/holdout_disposition_v3.md`, `research/results_manifest.json`, `research/results_shards_quarantine/.../shard_000455.jsonl`), and the exception paths (`research_state/campaign_authorization.json`, `research_state/checkpoint.json`, `research_state/pilot_evidence.json`, `run_holdout_campaign.py`). No research edits. Working tree clean (`git status --porcelain` empty).
- Mirrors rc=0 both pairs at session start and end: `.kilo/handoff.md`==`research_state/agent_handoff.md`, `.kilo/next_task.md`==`research_state/next_agent_task.md`.
- Verifier `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false`, exit 1, single failure: `"the code-hash constraint does not record the authorized code hash of record"` (known exception; NOT remediated). `manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` still MATCHES; `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`; `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; `historical_selection_authorization_present==false`; `evaluated_constituents==7`; `v3_benchmark_candles_after_the_v6_cutoff==13`.
- BRAIN-003 A+B+C confirmed complete: 455 active shards in `research/results_shards/e3d5e5f4.../`; `shard_000455.jsonl` absent there, present in `research/results_shards_quarantine/e3d5e5f4.../` (42 records, `quarantined:true`). `research/results_manifest.json` `total_records==22750`, 456 shard entries (455 active + 1 quarantined). `research_state/checkpoint.json` `completed_records==22750` (delta 0), `holdout_exposed_count==0`. `research/candidate_manifest_v2.json` `frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`, 14 candidates — untouched.
- Prior agent task COMPLETE (cheap drift check, mirror confirm, BRAIN-003 A+B+C confirmation, exception reported). **Remediation NOT authorized — requires explicit user approval.**
- Session start HEAD `b970ce814` is a harness checkpoint; no session commit per policy. Baseline HEAD reference: original drift baseline `439f42d0f`; original baseline `c486251cf`.

## KNOWN EXCEPTION — DO NOT REMEDIATE WITHOUT EXPLICIT AUTHORIZATION

A post-baseline checkpoint commit (2026-11-22T11:11:36Z, `6a870b604`) rewrote research-state outside the handoff's expected drift set:

- `research_state/campaign_authorization.json`: `authorized` flipped `true`→`false`; `code_hash` rotated `4bb02d54a1cb...`→`13172b2e87ab...`; added `reasons: ["evidence.code_hash mismatch","checkpoint_state.code_hash mismatch"]`; `evidence_digest` → `a3745961...`.
- `research_state/checkpoint.json`: `code_hash` rotated to `13172b2e87ab...` (counters untouched: `completed_records==22750`).
- `research_state/pilot_evidence.json`: top-level `code_hash` rotated to `13172b2e87ab...` (nested `evidence.code_hash` still `4bb02d54...`).
- `run_holdout_campaign.py`: added (holdout-enabled runner; NOT executed — `research/holdout_campaign_result.json` absent).

The verifier fails because `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash` (`4bb02d54...`) != `research_state/campaign_authorization.json` `code_hash` (`13172b2e...`).

Correct fix would be to restore the prior authorized state (re-bind `campaign_authorization.json`/`checkpoint.json`/`pilot_evidence.json` code_hash back to `4bb02d54...` and `authorized:true`, and decide whether `run_holdout_campaign.py` stays) — a substantive research-state edit that is NOT authorized. Report and stop; do not edit these artifacts.

## Session log (compacted)

Every session on 2026-11-21/22 reproduced the same read-only verification and stopped. Representative outcomes:

- **2026-11-22T17:04:21Z @ `b970ce814`** (this session): drift CLEAN; mirrors rc=0; verifier `ok:false` exit 1 (code-hash exception); manifest hash MATCH; BRAIN-003 A+B+C complete; no research edits; no session commit.
- **2026-11-22T17:02:54Z @ `512a506330`** through **2026-11-22T09:09:20Z** (`512a506330`, `f4ab88b33`, `d81bdd355`, `cef56b4f1`, `c070068c6`, `205f30c59`, `ee80a9ea7`, `d6dc431da`, `7f3079a5b`, `3a46b924`, `f84f6e25`, `9ae3b08c`, `f7ee3096`, `a0152c69`, `78d6df53`, `4f31120e`, `9e8ff170`, `6a59055c`, `bcab837d`, `97555104`, `7432c4c9`, `9bf0addf`, `d1a5af26`, `4b73625b`, `f84b17a6`, `195ed264`, `b98d29918`, `58b2728b`): identical outcome — drift CLEAN; mirrors rc=0; verifier `ok:false` exit 1 (code-hash exception); manifest hash MATCH; BRAIN-003 A+B+C complete; no research edits; no session commit. Earlier in this window (up to ~11:50Z) the verifier was `ok:true` before the exception commit landed.
- **2026-11-22T11:52Z @ `e39e2e166`**: first session to observe the post-baseline exception drift (campaign_authorization/checkpoint/pilot_evidence code_hash rotation + `run_holdout_campaign.py`); reported, did not remediate.
- **2026-11-21T16:56Z–2026-11-22T08:09Z** (`a59a6f26f`, `543df2ca4`, `79c56dc51`, `75b00ceb9`, `a86d06907`, `8e7563175`, `13bd13ba5`, and the folded 00:54Z–13:00Z group): identical read-only outcome; verifier `ok:true` in most; no research edits; no session commit.
- **2026-11-20–2026-11-21** sessions (`fd0065638` and earlier, including the folded 00:54Z–13:00Z and 10:27Z–23:44Z groups): BRAIN-003 BLOCKED for lack of A/B/C authorization; drift CLEAN; no research edits; no session commit. Task 1 and task 3 COMPLETED.

**Process note:** repeating full read-only verification adds no further value — the baseline has been reproduced identically many times across 60+ sessions. Until the next session: run only `git diff --name-only 439f42d0f..HEAD`, `diff -q` both mirror pairs, refresh this file + `research_state/next_agent_task.md` if needed, re-mirror, then stop. Do NOT remediate the code-hash exception without explicit authorization.

**Reliability notes (still governing):** "NOT committed" claims in old entries were contradicted by checkpoint commits `c559b2400`, `8bef4af5e`, `0e4058cf0`, `a06cff102`, `66abdf11a`, `83d0f4cf1`; "mirrors verified" claims have been false at least at `91b64b47f`, `2c7f05ffd`, `a83179780`, and `e74928845`. Always run `diff -q` and `git log` yourself.

## BRAIN-003 — REMEDIATED (A+B+C complete)

- **A (quarantine) — EXECUTED:** `research/results_shards/e3d5e5f4.../shard_000455.jsonl` moved to `research/results_shards_quarantine/e3d5e5f4.../shard_000455.jsonl`; `quarantined: true` marker on the shard entry in `research/results_manifest.json`; `total_records` reduced 22792 -> 22750; checkpoint left at `completed_records==22750` so manifest and checkpoint reconcile with no invention of exposure, `holdout_exposed_count` stays `0`.
- **B (disposition) — EXECUTED:** `reports/holdout_disposition_v3.md` added, superseding v2: v2 has no valid confirmatory claim because shard `shard_000455` reused the consumed v1 window; `research/candidate_manifest_v2.json` stays frozen/untouched (`frozen==true`, `ALL_REJECTED_ON_HOLDOUT`, 14 candidates), annotated untrusted in v3.
- **C (code/tests) — EXECUTED:** `configs/research_v6_execution.json` code-hash constraint fixed (`authorized_code_hash`→`4bb02d54...`, `canonical_hashed_set_digest`→`8cd17522...`, `manifest_hash`→`f6cd994f...`); `configs/research_v6_execution_amendment_1.json` re-bound (`amends.manifest_hash`/`amends.sha256`, `problem.affected_artifact_manifest_hash`, `related_artifacts.v6_execution_protocol.manifest_hash` updated, amendment `manifest_hash`→`be6dd16a...`). pytest not provisioned (module unavailable).

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

## Initial task message for the next agent

See `research_state/next_agent_task.md` (authoritative; `.kilo/next_task.md` byte-identical synced copy). One-line job: run the cheap drift check (`git diff --name-only 439f42d0f..HEAD` — expect only the four handoff files plus `workflow_run_diagnostics.jsonl` plus the BRAIN-003 remediation/exception paths), confirm both mirror pairs (`diff -q` both, rc=0), confirm BRAIN-003 A+B+C is still complete (quarantined shard present, active path absent, manifest/checkpoint reconciled at 22750, candidate_manifest_v2 frozen/ALL_REJECTED_ON_HOLDOUT/14), note the verifier `ok:false` code-hash exception is NOT to be remediated without explicit authorization, refresh the handoff/next-task files only if needed, re-sync both `.kilo` mirrors, and stop. No research edits and no remediation without explicit authorization. `NO_PROMPT_CHANGE_JUSTIFIED`.
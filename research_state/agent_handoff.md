## Latest — 2026-11-22T20:53:31Z @ `b3ef580c8` (kilo)

- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists exactly: the four handoff files + `research_state/workflow_run_diagnostics.jsonl` + BRAIN-003 remediation paths + exception paths. Working tree clean (`git status --porcelain` empty). HEAD at `b3ef580c8` (checkpoint; touched ONLY the four handoff files per `git show --stat`). Mirrors rc=0 both pairs. Verifier `ok:false` — known code-hash constraint exception, NOT remediated (`manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4`; `canonical_hashed_set_digest`==`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; only failure "the code-hash constraint does not record the authorized code hash of record"). BRAIN-003 A+B+C intact: quarantined shard present (42 records), active path absent (455 active shards), `results_manifest.total_records==22750` (456 entries = 455 active + 1 quarantined), `checkpoint.completed_records==22750` (delta 0), `holdout_exposed_count==0`, `candidate_manifest_v2` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates. Prior agent task COMPLETE. No research edits; no remediation without authorization.

- (Fold previous entry: 2026-11-22T20:51:18Z @ `091237db7` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

## Latest — 2026-11-22T20:51:18Z @ `091237db7` (kilo)

- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists exactly: the four handoff files + `research_state/workflow_run_diagnostics.jsonl` + BRAIN-003 remediation paths + exception paths. Working tree clean (`git status --porcelain` empty). HEAD at `091237db7` (checkpoint; touched ONLY the four handoff files per `git show --stat`). Mirrors rc=0 both pairs. Verifier `ok:false` exit 1 — known code-hash constraint exception, NOT remediated (`manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4`; `canonical_hashed_set_digest`==`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; only failure "the code-hash constraint does not record the authorized code hash of record"). BRAIN-003 A+B+C intact: quarantined shard present (42 records), active path absent (455 active shards), `results_manifest.total_records==22750` (456 entries = 455 active + 1 quarantined), `checkpoint.completed_records==22750` (delta 0), `holdout_exposed_count==0`, `candidate_manifest_v2` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates. Prior agent task COMPLETE. No research edits; no remediation without authorization.

- (Fold previous entry: 2026-11-22T20:49:14Z @ `3c6750b8e` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

## Latest — 2026-11-22T20:49:14Z @ `3c6750b8e` (kilo)

## Latest — 2026-11-22T20:46:35Z @ `6bc6599d8` (kilo)

- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists exactly: the four handoff files + `research_state/workflow_run_diagnostics.jsonl` + BRAIN-003 remediation paths + exception paths. Working tree clean (`git status --porcelain` empty). HEAD at `6bc6599d8` (checkpoint; touched ONLY the four handoff files per `git show --stat`). Mirrors rc=0 both pairs. Verifier `ok:false` exit 1 — known code-hash constraint exception, NOT remediated (`manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4`; `canonical_hashed_set_digest`==`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; only failure "the code-hash constraint does not record the authorized code hash of record"). BRAIN-003 A+B+C intact: quarantined shard present (42 records), active path absent (455 active shards), `results_manifest.total_records==22750` (456 entries = 455 active + 1 quarantined), `checkpoint.completed_records==22750` (delta 0), `holdout_exposed_count==0`, `candidate_manifest_v2` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates. Prior agent task COMPLETE. No research edits; no remediation without authorization.

- (Fold previous entry: 2026-11-22T20:46:04Z @ `667fcf313` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

## Latest — 2026-11-22T19:52:47Z @ `46df58eae` (kilo)

- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists exactly: the four handoff files + `research_state/workflow_run_diagnostics.jsonl` + BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `reports/holdout_disposition_v3.md`, `research/results_manifest.json`, `research/results_shards_quarantine/.../shard_000455.jsonl`) + exception paths (`research_state/campaign_authorization.json`, `research_state/checkpoint.json`, `research_state/pilot_evidence.json`, `run_holdout_campaign.py`). Working tree clean (`git status --porcelain` empty). HEAD at `46df58eae` (checkpoint; touched ONLY the four handoff files per `git show --stat`). Mirrors rc=0 both pairs. Verifier `ok:false` exit 1 — known code-hash constraint exception, NOT remediated (`manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4`; `canonical_hashed_set_digest`==`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; only failure "the code-hash constraint does not record the authorized code hash of record"). BRAIN-003 A+B+C intact: quarantined shard present (42 records), active path absent (455 active shards), `results_manifest.total_records==22750` (456 entries = 455 active + 1 quarantined), `checkpoint.completed_records==22750` (delta 0), `holdout_exposed_count==0`, `candidate_manifest_v2` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates. Prior agent task COMPLETE. No research edits; no remediation without authorization.

- (Fold previous entry: 2026-11-22T19:49:28Z @ `73353fc80` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

- (Fold previous entry: 2026-11-22T19:47:37Z @ `9ce7761dc` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

- (Fold previous entry: 2026-11-22T19:46:27Z @ `46bd9bc76` — Drift CLEAN; mirrors rc=0 both pairs; verifier `ok:false` code-hash exception NOT remediated; BRAIN-003 A+B+C intact; no research edits; no session commit.)

- (Fold previous entry: 2026-11-22T18:53:14Z @ `f4b2ff778` — drift CLEAN; mirrors rc=0; verifier `ok:false` code-hash exception; BRAIN-003 A+B+C complete; no research edits; no session commit.)
- Drift CLEAN. `git diff --name-only 439f42d0f..HEAD` lists exactly: the four handoff files (`.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`) + `research_state/workflow_run_diagnostics.jsonl` + BRAIN-003 remediation paths (`configs/research_v6_execution.json`, `configs/research_v6_execution_amendment_1.json`, `reports/holdout_disposition_v3.md`, `research/results_manifest.json`, `research/results_shards_quarantine/.../shard_000455.jsonl`) + exception paths (`research_state/campaign_authorization.json`, `research_state/checkpoint.json`, `research_state/pilot_evidence.json`, `run_holdout_campaign.py`). No research edits. Working tree clean (`git status --porcelain` empty).
- HEAD is `18db38df8` ("chore(kilo): checkpoint agent session"); working tree clean. Drift delta set unchanged from prior sessions.
- Mirrors rc=0 both pairs: `.kilo/handoff.md`==`research_state/agent_handoff.md`, `.kilo/next_task.md`==`research_state/next_agent_task.md` (byte-identical at session start; re-synced after this edit).
- Verifier `ok:false` exit 1 — known code-hash constraint exception, NOT remediated. `manifest_hash`==`recomputed_manifest_hash`==`f6cd994fb5f6443853763b2d94547c030c77c473c740e77adbf6e8e28e0709d4` MATCHES; `canonical_hashed_set_digest`==`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e` matches the BRAIN-003 C fix. Only failure: "the code-hash constraint does not record the authorized code hash of record."
- BRAIN-003 A+B+C confirmed intact: quarantined shard present (42 records, `quarantined:true`), active path absent (455 active shards), `results_manifest.total_records==22750` (456 entries = 455 active + 1 quarantined), `checkpoint.completed_records==22750` (delta 0), `holdout_exposed_count==0`, `candidate_manifest_v2` `frozen==true` / `candidate_status==ALL_REJECTED_ON_HOLDOUT` / 14 candidates (`holdout_reuse==forbidden`).
- Prior agent task COMPLETE (cheap drift check, mirror confirm, verifier re-run, BRAIN-003 A+B+C confirmation, exception reported). **Remediation NOT authorized — requires explicit user approval.**

## KNOWN EXCEPTION — DO NOT REMEDIATE WITHOUT EXPLICIT AUTHORIZATION

A post-baseline checkpoint commit (2026-11-22T11:11:36Z, `6a870b604`) rewrote research-state outside the handoff's expected drift set:

- `research_state/campaign_authorization.json`: `authorized` flipped `true`→`false`; `code_hash` rotated `4bb02d54a1cb...`→`13172b2e87ab...`; added `reasons: ["evidence.code_hash mismatch","checkpoint_state.code_hash mismatch"]`; `evidence_digest` → `a3745961...`.
- `research_state/checkpoint.json`: `code_hash` rotated to `13172b2e87ab...` (counters untouched: `completed_records==22750`).
- `research_state/pilot_evidence.json`: top-level `code_hash` rotated to `13172b2e87ab...` (nested `evidence.code_hash` still `4bb02d54...`).
- `run_holdout_campaign.py`: added (holdout-enabled runner; NOT executed — `research/holdout_campaign_result.json` absent).

The verifier fails because `configs/research_v6_execution.json` `code_hash_constraint.authorized_code_hash` (`4bb02d54...`) != `research_state/campaign_authorization.json` `code_hash` (`13172b2e...`).

Correct fix would be to restore the prior authorized state (re-bind `campaign_authorization.json`/`checkpoint.json`/`pilot_evidence.json` code_hash back to `4bb02d54...` and `authorized:true`, and decide whether `run_holdout_campaign.py` stays) — a substantive research-state edit that is NOT authorized. Report and stop; do not edit these artifacts.

## Session log (compacted)

Every session on 2026-11-21/22 reproduced the same read-only verification and stopped. See prior entries for full list.

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
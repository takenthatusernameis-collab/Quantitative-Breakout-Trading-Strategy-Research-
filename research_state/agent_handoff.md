# Kilo handoff (durable)

**Authoritative copy:** `research_state/agent_handoff.md`. Keep in sync with `.kilo/handoff.md` (byte-identical; verify with `diff -q`).

## Latest — 2026-11-19T20:42Z @ `70dd0bee3` (kilo; read prior durable handoff @ `02f6ea79a`; mirrors rc=0 at start; cheap drift check + mirror verify only — **CLEAN**)

- **Result: no NEW research drift.** `git diff --name-only 439f42d0f..HEAD` lists only the four handoff files plus `research_state/workflow_run_diagnostics.jsonl`; `git status --porcelain` empty at session start. HEAD advanced `02f6ea79a` -> `70dd0bee3` via harness checkpoint commit (handoff files only). No research code/result/campaign-state artifact edited.
- **Mirror sync:** both pairs rc=0 at start; re-verified rc=0 after edits.
- **Prior agent task:** (1) cheap drift verification — COMPLETED (clean). (2) gated BRAIN-003 remediation (A)–(C) — **BLOCKED** (user prompt contained no A/B/C letter). (3) handoff/next-task refresh + mirror sync — COMPLETED here.
- **No remediation authorization received:** task 2 stays BLOCKED; research artifacts untouched. No commit made by this session (HEAD advance is harness checkpoint only).

## Latest — 2026-11-19T20:41Z @ `02f6ea79a` (kilo; read prior durable handoff @ `cae723fca`; mirrors rc=0 at start; cheap drift check + mirror verify only — **CLEAN**)

- **Result: no NEW research drift.** `git diff --name-only 439f42d0f..HEAD` lists only the four handoff files plus `research_state/workflow_run_diagnostics.jsonl`; `git status --porcelain` empty at session start. HEAD advanced `cae723fca` -> `02f6ea79a` via harness checkpoint commit (handoff files only). No research code/result/campaign-state artifact edited.
- **Mirror sync:** both pairs rc=0 at start; re-verified rc=0 after edits.
- **Prior agent task:** (1) cheap drift verification — COMPLETED (clean). (2) gated BRAIN-003 remediation (A)–(C) — **BLOCKED** (user prompt contained no A/B/C letter). (3) handoff/next-task refresh + mirror sync — COMPLETED here.
- **No remediation authorization received:** task 2 stays BLOCKED; research artifacts untouched. No commit made by this session (HEAD advance is harness checkpoint only).

## Latest — 2026-11-19T20:40Z @ `cae723fca` (kilo; read prior durable handoff @ `e266bea17`; mirrors rc=0 at start; cheap drift check + mirror verify only — **CLEAN**)

- **Result: no NEW research drift.** `git diff --name-only 439f42d0f..HEAD` lists only the four handoff files plus `research_state/workflow_run_diagnostics.jsonl`; `git status --porcelain` empty at session start. HEAD advanced `e266bea17` -> `cae723fca` via harness checkpoint commit (handoff files only). No research code/result/campaign-state artifact edited.
- **Mirror sync:** both pairs rc=0 at start; re-verified rc=0 after edits.
- **Prior agent task:** (1) cheap drift verification — COMPLETED (clean). (2) gated BRAIN-003 remediation (A)–(C) — **BLOCKED** (user prompt contained no A/B/C letter). (3) handoff/next-task refresh + mirror sync — COMPLETED here.
- **No remediation authorization received:** task 2 stays BLOCKED; research artifacts untouched. No commit made by this session (HEAD advance is harness checkpoint only).

## Session log (folded; all CLEAN, all task 2 BLOCKED)

Every session from 2026-11-19T10:27Z through 2026-11-19T20:40Z recorded the same outcome: cheap drift check CLEAN (delta confined to the four handoff files plus `workflow_run_diagnostics.jsonl`); mirrors verified with `diff -q`; task 1 COMPLETED, task 3 COMPLETED, task 2 (BRAIN-003) BLOCKED for lack of an explicit A/B/C authorization from the user; no substantive research edits and no session-authored research commits. Checkpoints (`ca45fbdc3`, `c8d28c560`, `41b76d350`, `26a3b9121`, `046e016a1`, `af614299d`, `f1c4173b8`, `cb83b109c`, `28df2c2cb`, `40cde2389`, `aa4b8f393`, `1e6c30667`, `a1417e630`, `513b14d4`, `e266bea17`, `cae723fca`) were handoff-only. Several sessions found `.kilo/handoff.md` stale (rc=1) despite a prior rc=0 claim — always run `diff -q` yourself.

## Remediation plan (NOT executed; requires explicit authorization)

Treat `research_state/checkpoint.json`, `research/candidate_manifest_v2.json`, and the 42 `e3d5e5f.../shard_000455.jsonl` holdout rows as **invalid for v2 confirmation** (consumed/reused window). No valid v2 claim. Do **not** re-run holdout and do **not** define/consume any confirmatory window (v6 start not before `2027-01-20T02:00:00Z`).

**Concrete approve-by-name plan (prepared @ `dc7bc46c6`; NOT executed).** Reply with the letters to authorize:
- **A (quarantine):** `git mv`-equivalent move of `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` to `research/results_shards_quarantine/e3d5e5f.../shard_000455.jsonl`; add a `quarantined` marker field to that shard's entry and reduce `research/results_manifest.json` `total_records` by 42 (22792 -> 22750) and shard count as needed; leave `research_state/checkpoint.json` at `completed_records==22750` so manifest and checkpoint reconcile with **no** invention of exposure, `holdout_exposed_count` stays `0`.
- **B (disposition):** add a NEW file `reports/holdout_disposition_v3.md` (superseding `reports/holdout_disposition_v2.md`) stating: v2 has **no valid confirmatory claim** because shard `shard_000455` reused the consumed v1 window; `candidate_manifest_v2.json` stays frozen/untouched (`frozen==true`, `ALL_REJECTED_ON_HOLDOUT` retained as-is, annotated as untrusted in the new artifact).
- **C (code/tests, optional):** provision `pytest` and fix the two `scripts/verify_v6_execution.py` code-hash failures by recording the authorized code hash of record and the canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e` in the code-hash constraint. (Names the exact files: `scripts/verify_v6_execution.py`, `configs/research_v6_execution.json`, plus test provisioning.)

Any reply that does not name A/B/C leaves task 2 BLOCKED and research artifacts untouched. Any step implying re-exposure of holdout or creation of a confirmatory window must STOP.

## Initial task message for the next agent

See `research_state/next_agent_task.md` (authoritative; `.kilo/next_task.md` byte-identical synced copy). One-line job: confirm the handoff is intact, run only the cheap drift check (`git rev-parse HEAD`; `git diff --name-only 439f42d0f..HEAD` confined to the four handoff files plus `workflow_run_diagnostics.jsonl`), `diff -q` both mirror pairs (re-sync `research_state/` -> `.kilo/` first if rc=1), then surface the BRAIN-003 (A)/(B)/(C) authorization decision and stop. `NO_PROMPT_CHANGE_JUSTIFIED`.

## Baseline to verify

- `HEAD==02f6ea79a` on `main` (working tree clean at start except this session's handoff edits). Baseline research HEAD `439f42d0f`; every commit since is a handoff-only checkpoint plus one pre-acknowledged `research_state/workflow_run_diagnostics.jsonl` line. **Clean delta vs baseline `439f42d0f`: no NEW research drift.**
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1); same 2 failures (recomputed canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`; `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`; `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`; `historical_selection_authorization_present==false`; `v3_benchmark_candles_after_the_v6_cutoff==13`; `evaluated_constituents==7`). `manifest_hash==recomputed==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (unavailable).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; no v6 start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs plus `research/data_manifest_v6.json`, `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.
- Mirrors: `.kilo/handoff.md` and `.kilo/next_task.md` must stay byte-identical to the `research_state/` originals after this session (`diff -q` rc=0 on both pairs). **A `diff -q` rc=1 at session start means the previous session's sync claim was false** — re-sync before doing anything else, and re-verify after editing (the harness checkpoint commits only working-tree files and can commit only the authoritative copy).

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 config_ids), reused v1 window => no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750` vs manifest `total_records==22792` (delta 42), unreconciled.
- `research/candidate_manifest_v2.json` frozen (`frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`, 14 candidates) — untrusted for v2 confirmation until BRAIN-003 resolved.

## Hard constraints

- No consuming `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign state without explicit authorization.
- `.kilo/handoff.md` and `.kilo/next_task.md` must stay byte-identical to the `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

## Session history (compacted; superseded by "Latest" above)

All sessions performed only read-only baseline re-verification with **identical results** (v6 verifier `ok:false` exit 1, same 2 code-hash failures, recomputed `8cd17522...`, `manifest_hash==recomputed==92872727...` MATCH, `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, pytest unavailable, `check_progress` 497664/497664 completed 6 next 6, binding `IMPLEMENTATION_BOUND_NOT_RUN`, v5 complete, v6 unconsumed, manifest `total_records` 22792 / 456 shards, BRAIN-003 shard 42/42 holdout with 13 config_ids, `checkpoint.json` 22750 vs 22792 delta 42, `candidate_manifest_v2` frozen/ALL_REJECTED_ON_HOLDOUT/14 candidates) and reported **no research code/result/campaign-state drift**. In every session task 1 COMPLETED, task 3 COMPLETED, and task 2 (BRAIN-003 remediation) remained **BLOCKED** for lack of explicit user authorization naming files/actions (A)/(B)/(C).

**Constraint note:** earlier session records that claimed their handoff/next-task edits were "working-tree-only — NOT committed" are contradicted by commits `c559b2400`, `8bef4af5e`, `0e4058cf0`, `a06cff102`, `66abdf11a`, `83d0f4cf1` showing the session harness/checkpoint step committed them. Treat "NOT committed" claims as unreliable and check `git log`. Likewise treat "mirrors verified" claims as unreliable — always run `diff -q` yourself.

**Process note:** repeating read-only verification adds no further value. The next productive step is user authorization for BRAIN-003 remediation; the concrete approve-by-name plan (A/B/C) above unblocks it with one reply. Until then: run only `git diff --name-only 439f42d0f..HEAD` (must list only the four handoff files plus `workflow_run_diagnostics.jsonl`), `diff -q` both mirror pairs, refresh this file + `research_state/next_agent_task.md`, re-mirror, then stop and surface (A)/(B)/(C). Full baseline has been reproduced 24+ times with identical values; do not re-run it on a clean delta.

(End of file - total 64 lines)
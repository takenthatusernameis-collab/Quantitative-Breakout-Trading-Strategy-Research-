# Initial task message for the next agent

You are the next agent in the chain. Read `research_state/agent_handoff.md` first (the `.kilo/handoff.md` copy must stay byte-identical).

**First action: perform the read-only baseline re-verification below and report any drift before editing any file.** Do not treat this message as remediation authorization. Do not consume `v6-selection-20261022`, expose holdout/confirmatory data, amend frozen artifacts, or commit unless the user explicitly authorizes it.

## Baseline at handoff (2026-11-18T16:45:46Z @ `215126164`)

- `HEAD==21512616466073a2ec7d1f53932ce2c55d5e8274` on `main` (`origin/main` aligned). Prior durable handoff recorded `HEAD==67b5dca25...`; drift `67b5dca25` -> `21512616466073a2ec7d1f53932ce2c55d5e8274` via handoff-only checkpoint commit `215126164` (only `research_state/agent_handoff.md`, `research_state/next_agent_task.md`, `.kilo/handoff.md`, `.kilo/next_task.md`); no research code/result/campaign-state drift.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1), same 2 failures: code-hash constraint does not record the authorized code hash of record; records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`.
- `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (unavailable).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6 (`0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d`, `be4223dcef25aaa0043a466fcd9044b4e6a7387eff7efd487561b9c1f873c1ae`, `v2-selection-20261019`, `v3-selection-20261020`, `v4-selection-20261021`, `v5-selection-20261021`), `next: 6`.
- `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` (completed), `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs present.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.
- Mirrors: `.kilo/handoff.md` and `.kilo/next_task.md` were re-synced at `215126164` and verified with `diff`; check them again before relying on them (`diff -q` each pair).

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s), reused consumed v1 holdout window.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22792` (delta 42), unreconciled.
- `research/candidate_manifest_v2.json` frozen `frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT` (14 candidates) — untrusted for v2 confirmation until BRAIN-003 resolved.

## Your task

1. Re-run the read-only baseline checks and report any drift. Do not edit files before that report.
2. Execute remediation only if the user explicitly authorizes exact files/actions. Permitted only:
   - (a) quarantine/annotate shard + update manifest inventory;
   - (b) reconcile checkpoint without fabricating exposure;
   - (c) add a superseding disposition artifact (prefer over amending frozen `research/candidate_manifest_v2.json`);
   - (d) explicitly authorized code/test fix.
   Stop/refuse if a step would re-expose holdout or create/consume a confirmatory window.
3. Update `research_state/agent_handoff.md` and `research_state/next_agent_task.md`, mirror byte-for-byte to `.kilo/handoff.md` and `.kilo/next_task.md`, and verify each pair with `diff`. Do not commit unless explicitly requested.

## Authorization still required

- (A) Exact shard move/quarantine paths and rewrites of `research/results_manifest.json` and `research_state/checkpoint.json`.
- (B) New superseding disposition artifact vs amendment of frozen `research/candidate_manifest_v2.json`.
- (C) Any code/test edits.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

No remediation authorization was provided in the prior session (nor the one before it), so task 2 remains BLOCKED. Tasks 1 and 3 were completed at `67b5dca25`; the next agent must still perform the read-only baseline re-verification and report any drift before editing.

(End of file - total 51 lines)

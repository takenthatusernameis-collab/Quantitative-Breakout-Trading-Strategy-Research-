# Next agent task (copy/paste)

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` synced) first.

**First action: perform read-only baseline re-verification and report drift. Do not edit any file until that baseline report is complete.** Fail-closed BRAIN-003 remediation gate: not a request to re-run holdout, make the verifier pass, or change protocol. Do not consume `v6-selection-20261022`, do not expose holdout/confirmatory data, and do not edit frozen/state artifacts without explicit user authorization. Do not commit unless explicitly requested. **When you finish, mirror both authoritative files into `.kilo/handoff.md` and `.kilo/next_task.md` byte-for-byte and verify each pair with `diff`.**

**Baseline to verify (re-verified 2026-11-17T14:15:22Z @ `177178aaf`, read-only):**
- `HEAD==177178aaf` on `main` at verification time (remote/local in sync; prior handoff recorded `HEAD==0d3d33366935edd95fba973db2c33d13b44383da`).
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1); same 2 failures (no authorized code-hash recorded; recomputed canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`). `manifest_hash==recomputed==928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (exit 1).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; authority flags all false except `max_runs==1`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` done; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no start before `2027-01-20T02:00:00Z`; authorization-declared outputs absent (only pre-run `research/v6_evidence/` JSONs; no selection output dir).
- `research/results_manifest.json` `total_records==22792`, `shards==456` entries. `NO_PROMPT_CHANGE_JUSTIFIED`.

**BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation):**
- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 `is_holdout==true` (13 config_ids), reused v1 window => no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750` vs manifest `total_records==22792` (delta 42), unreconciled.
- `research/candidate_manifest_v2.json` frozen (`frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`) — untrusted for v2 confirmation given BRAIN-003.

**Your task:**
1. Baseline re-verify (read-only); report any drift.
2. If and only if user provides explicit authorization naming exact files/actions, execute ONLY authorized subset (a) quarantine/annotate shard + manifest updates; (b) reconcile checkpoint without fabricating exposure; (c) prefer new superseding disposition artifact over amending frozen `research/candidate_manifest_v2.json`; (d) optional authorized code/test fix. STOP/refuse if any step implies re-exposing holdout or creating/consuming a confirmatory window.
3. Update `research_state/agent_handoff.md` + `.kilo/handoff.md` and `research_state/next_agent_task.md` + `.kilo/next_task.md` (each pair byte-identical, `diff`-verified). Commit only if explicitly requested. If no remediation authorization provided, complete task 1 and report blocked on task 2.

**Authorization still required:** (A) exact shard move/quarantine paths and rewrites of `research/results_manifest.json`/`research_state/checkpoint.json`; (B) new superseding disposition artifact vs amend frozen `research/candidate_manifest_v2.json`; (C) any code/test edits. If none provided, complete task 1 and report blocked on task 2.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no valid v2 claim from consumed-window rows; no substantive edits to frozen/protocol/binding/authorization/campaign state without explicit authorization. `NO_PROMPT_CHANGE_JUSTIFIED`.

**Session record (2026-11-17T14:15:22Z @ `177178aaf`):** read prior durable handoff (`0d3d33366935edd95fba973db2c33d13b44383da`); read-only baseline re-verification completed (ok:false, same 2 failures; manifest_hash MATCH; pytest unavailable; check_progress 497664/497664, completed 6, next 6). Drift: `HEAD` `0d3d33366935edd95fba973db2c33d13b44383da` -> `177178aaf` observed; remote/local in sync; working tree clean; no research drift observed. No commit requested. BRAIN-003 UNREMEDIATED (42/42 holdout rows in `e3d5e5f.../shard_000455.jsonl`, 13 config_ids; checkpoint.json completed_records==22750 vs manifest 22792 delta 42; candidate_manifest_v2 frozen/untrusted). No remediation authorization -> task 2 BLOCKED. Task 1 COMPLETED; task 3 COMPLETED.
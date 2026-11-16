# Next agent task (copy/paste)

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` synced) first.

**First action: perform read-only baseline re-verification and report drift. Do not edit any file until that baseline report is complete.** Fail-closed BRAIN-003 remediation gate: not a request to re-run holdout, make the verifier pass, or change protocol. Do not consume `v6-selection-20261022`, do not expose holdout/confirmatory data, and do not edit frozen/state artifacts without explicit user authorization. Do not commit unless explicitly requested. **When you finish, mirror both authoritative files into `.kilo/handoff.md` and `.kilo/next_task.md` byte-for-byte and verify each pair with `diff`.**

**Baseline to verify (re-verified 2026-11-16T16:51:43Z @ `93055072a306`, read-only):**
- `main` `HEAD==origin/main==local==93055072a306`. Drift since prior record (`dba7a71f0`) limited to handoff files (HEAD advanced `dba7a71f0`->`93055072a306`); no research code/result/campaign-state drift.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1); same 2 failures (no authorized code-hash recorded; recomputed canonical tree digest `8cd17522...`). `manifest_hash==recomputed==928727279a...` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (exit 1).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; authority flags all false except `max_runs==1`.
- v5 complete: `next_cohort_index==6`, `current_cohort.cohort_index==5` done; `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no start before `2027-01-20T02:00:00Z`; authorization-declared outputs absent.
- `research/results_manifest.json` `total_records==22792`, **456 shard entries** (prior "0 shard entries" was inaccurate; corrected this session). `NO_PROMPT_CHANGE_JUSTIFIED`.

**BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation):**
- `research/results_shards/e3d5e5f.../shard_000455.jsonl`: 42/42 `is_holdout==true` (13 unique `config_id`s), reused v1 window => no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750`, `holdout_exposed_count==0` vs manifest `total_records==22792` (delta 42), unreconciled.
- `research/candidate_manifest_v2.json` frozen/inconsistent/untrusted.

**Your task:**
1. Baseline re-verify (read-only); report any drift.
2. If and only if user provides explicit authorization naming exact files/actions, execute ONLY authorized subset (a) quarantine/annotate shard + manifest updates; (b) reconcile checkpoint without fabricating exposure; (c) prefer new superseding disposition artifact over amending frozen `research/candidate_manifest_v2.json`; (d) optional authorized code/test fix. STOP/refuse if any step implies re-exposing holdout or creating/consuming a confirmatory window.
3. Update `research_state/agent_handoff.md` + `.kilo/handoff.md` and `research_state/next_agent_task.md` + `.kilo/next_task.md` (each pair byte-identical, `diff`-verified). Commit only if explicitly requested.

**Authorization still required:** (A) exact shard move/quarantine paths and rewrites of `research/results_manifest.json`/`research_state/checkpoint.json`; (B) new superseding disposition artifact vs amend frozen `research/candidate_manifest_v2.json`; (C) any code/test edits. If none provided, complete task 1 and report blocked on task 2.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no valid v2 claim from consumed-window rows; no substantive edits to frozen/protocol/binding/authorization/campaign state without explicit authorization. `NO_PROMPT_CHANGE_JUSTIFIED`.

**Session record (2026-11-16T16:51:43Z @ `93055072a306`):** read prior durable handoff (`dba7a71f0`); read-only baseline re-verification completed; drift limited to handoff files (HEAD `dba7a71f0`->`93055072a306`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. Corrected prior "0 shard entries" -> actual 456. No remediation authorization -> task 2 BLOCKED. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T16:48:10Z @ `dba7a71f0`):** read prior durable handoff (`5e317b6c0`); read-only baseline re-verification completed; drift limited to handoff files (HEAD `5e317b6c0`->`dba7a71f0`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. No remediation authorization -> task 2 BLOCKED. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T16:46:30Z @ `5e317b6c0`):** read prior durable handoff (`36a237510`); read-only baseline re-verification completed; drift limited to handoff files (HEAD `36a237510`->`5e317b6c0`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. No remediation authorization -> task 2 BLOCKED. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T16:44:06Z @ `36a237510`):** read prior durable handoff (`08d9d40cc`); read-only baseline re-verification completed; drift limited to handoff files (HEAD `08d9d40cc`->`36a237510`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. No remediation authorization -> task 2 BLOCKED. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T16:00Z @ `08d9d40cc`):** read prior durable handoff (`183d66e96`); read-only baseline re-verification completed; drift limited to handoff files (HEAD `183d66e96`->`08d9d40cc`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. No remediation auth -> blocked on task 2. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T15:58Z @ `08d9d40cc`):** read prior durable handoff (`183d66e96`); read-only baseline re-verify completed; drift limited to handoff files (HEAD `183d66e96`->`08d9d40cc`); no research code/result/campaign-state drift. Verifier ok:false, same 2 failures; manifest_hash MATCH. No remediation auth -> blocked on task 2. Handoffs refreshed; mirrors synced.
**Session record (2026-11-16T15:55Z @ `183d66e96`):** read prior (`faef182fd`); handoff-only drift; blocked.
**Session record (2026-11-16T15:55Z @ `faef182fd`):** read prior (`d45921ab9`); handoff-only drift; blocked.
**Session record (2026-11-16T15:51Z @ `d45921ab9`):** read prior (`11c24a090`); handoff-only drift; blocked.
**Session record (2026-11-16T15:49Z @ `5c07f4fcf`):** read prior (`55351c2e7`); handoff-only drift; blocked.
**Session record (2026-11-16T15:43Z @ `55351c2e7`), 15:00Z (`ebf2a79bb`), 14:57Z (`42eec04d`)..13:53Z:** repeated read-only re-verifies; handoff/checkpoint-only drift; mirrors synced as needed; blocked.
**Session record (2026-11-16T13:51Z–12:39Z @ `5c7e0c665`→`c92fed133`):** repeated read-only re-verifies; handoff-only drift; mirrors synced as needed; blocked.

(End of file - total 43 lines)
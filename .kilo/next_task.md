# Next agent task (copy/paste)

You are the next agent in the chain. Read `research_state/agent_handoff.md` (authoritative; `.kilo/handoff.md` synced) first.

**First action: perform read-only baseline re-verification and report drift. Do not edit any file until that baseline report is complete.** This is a fail-closed BRAIN-003 remediation gate, not a request to re-run holdout, make the verifier pass, or change protocol. Do not consume `v6-selection-20261022`, do not expose holdout/confirmatory data, and do not edit frozen/state artifacts without explicit user authorization. Do not commit unless explicitly requested. **When you finish, mirror the authoritative handoff into `.kilo/handoff.md` byte-for-byte and verify with `diff`.**

**Baseline to verify (re-verified 2026-11-16T08:26Z @ `6e9105fcf`, read-only, no material drift vs `06a876ca6`):**
- `main` clean; `HEAD==origin/main==local==6e9105fcf40031d2d4e8dd80382170e20444022c`; `HEAD` advanced one checkpoint commit from `06a876ca6` (`chore(kilo): checkpoint agent session`), diff limited to the four handoff/next-task files, no code/state artifact drift.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` exit 1; same 2 failures: code-hash constraint does not record authorized code hash of record; records another canonical tree digest (`8cd17522...`). `manifest_hash==recomputed==928727279a...` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> pytest unavailable (`No module named pytest`, exit 1).
- `./check_progress.sh` -> `records: 497664 total: 497664`, completed 6, `next: 6`.
- Binding `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; authority has `max_runs==1`, `confirmatory_evaluation_authorized==false`, `holdout_reads_authorized==false`, `amendment_of_a_frozen_artifact_authorized==false`, `candle_fetch_authorized==false`, `second_v6_selection_run_authorized==false`.
- v5 complete: `continuous_universe_state.json` `next_cohort_index==6`, `current_cohort.cohort_index==5`, `completed==true`; `checkpoint_v5.json` `holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; do not start before `2027-01-20T02:00:00Z`; `configs/v6_selection_ledger.json`, `configs/v6_selected_configurations_manifest.json`, `src/v6_confirmatory/` absent.
- `research/results_manifest.json` `total_records==22792`, 456 shards. `NO_PROMPT_CHANGE_JUSTIFIED`.

**BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation):**
- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 `is_holdout==true` rows (13 unique `config_id`s) reusing consumed v1 window (see `reports/holdout_disposition_v2.md`, v1 `707f7a50.../shard_000000.jsonl`) -> **forbidden reuse; no valid v2 confirmatory claim**.
- `research_state/checkpoint.json` (e3d5e5f4): `completed_records==22750`, `holdout_exposed_count==0` vs `research/results_manifest.json` `total_records==22792` (delta 42; on-disk 22792) — unreconciled.
- `research/candidate_manifest_v2.json` (frozen, 14 candidates): internally inconsistent/untrusted.

**Your task:**
1. **Baseline re-verify (read-only):** run the commands above, compare against this baseline, and report any drift. Do not modify files in this step.
2. **If (and only if) the user provides explicit authorization naming exact files/actions**, execute ONLY the authorized subset:
   - (a) quarantine/annotate invalid shard `.../e3d5e5f.../shard_000455.jsonl` and update `research/results_manifest.json` inventory/totals as authorized;
   - (b) reconcile `research_state/checkpoint.json` (`completed_records`/`holdout_exposed_count`) to verified reality without fabricating exposure;
   - (c) resolve manifest inconsistency without fabricating results — prefer a **new superseding disposition artifact** (fresh never-observed confirmatory period required) over amending frozen `research/candidate_manifest_v2.json`;
   - (d, optional) authorized code/test provenance fix.
   **If any step implies re-exposing holdout or creating/consuming a confirmatory window, STOP and refuse.**
3. **Record outcome:** update `research_state/agent_handoff.md` + `.kilo/handoff.md` (byte-identical, verify with `diff`) and `research_state/next_agent_task.md` + `.kilo/next_task.md` with actions/evidence/remaining authorization needs. Commit only if explicitly requested.

**Authorization still required:** (A) exact shard move/quarantine paths and rewrites of `research/results_manifest.json`/`research_state/checkpoint.json`; (B) new superseding disposition artifact vs amend frozen `research/candidate_manifest_v2.json`; (C) any code/test edits. If no remediation authorization is provided, complete task 1 and report blocked on task 2.

**Hard constraints:** no consuming `v6-selection-20261022`; no holdout/confirmatory exposure before `2027-01-20T02:00:00Z`; no valid v2 claim from consumed-window rows; no substantive edits to frozen protocol/binding/authorization artifacts or campaign state without explicit authorization. `NO_PROMPT_CHANGE_JUSTIFIED`.

**Session record (2026-11-16T08:26Z @ `6e9105fcf`):** prior durable-handoff task read and completed. Read-only baseline re-verification executed — no material drift vs `06a876ca6` (only drift = harness checkpoint commit `06a876ca6`→`6e9105fcf`, handoff/next-task files only). Mirrors `.kilo/handoff.md`/`.kilo/next_task.md` verified already byte-identical to authoritative copies (no stale-mirror drift this session). No remediation authorization provided — task 2 remains BLOCKED. Handoff/next-task refreshed and mirrors re-synced.
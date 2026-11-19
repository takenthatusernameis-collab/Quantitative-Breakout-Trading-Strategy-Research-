# Initial task message for the next agent

Read `research_state/agent_handoff.md` first (its `.kilo/handoff.md` twin must be byte-identical).

## Your job in one line

Confirm the handoff is intact, then surface a **single decision request** for BRAIN-003 remediation. Do not start a 46th verification session, and do not self-authorize any remediation.

## Step 0 — mirror integrity (30 seconds, do this before anything else)

`diff -q research_state/agent_handoff.md .kilo/handoff.md` and `diff -q research_state/next_agent_task.md .kilo/next_task.md` must both exit 0. **If rc=1, the previous session's sync claim was false (this has already happened once, at `1f5056f33` -> `bc6f26a6c`):** copy the `research_state/` originals over the `.kilo/` mirrors, then re-verify. Re-verify again at the very end after your own edits — the harness checkpoint can commit only one copy of a pair.

## Step 1 — cheap drift check (one command block; the only verification allowed)

```bash
git rev-parse HEAD; git status --porcelain; git log --oneline -3
git diff --name-only 439f42d0f..HEAD          # baseline research HEAD
diff -q research_state/agent_handoff.md .kilo/handoff.md
diff -q research_state/next_agent_task.md .kilo/next_task.md
```

If `git diff --name-only 439f42d0f..HEAD` lists **only** `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`, then research code/results/campaign state are byte-identical to the verified baseline and no drift is possible — stop verifying.

If **any other path** appears, that is real drift: report it immediately (it outranks everything below) and re-run the full baseline only then.

Do **not** re-run `verify_v6_execution.py`, `check_progress.sh`, or the BRAIN-003 spot checks on a clean delta. They have been reproduced identically 24 times.

## Step 2 — refresh and mirror

Update `research_state/agent_handoff.md` (new "Latest" entry; fold the previous one into history) and this file; mirror both pairs; `diff -q` both again. Do not commit unless asked.

## Step 3 — your final answer is the decision request

State the baseline is unchanged, BRAIN-003 is still unremediated, and ask for an explicit letter. Nothing else is productive until then.

## Baseline at handoff (2026-11-19T07:10Z @ `d38ec8839`) — stable

- `HEAD==7c996ba4a` on `main`, working tree clean. Baseline research HEAD `439f42d0f`; every commit since is a handoff-only checkpoint touching only the four handoff files. **No research drift.**
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1), same 2 failures: the code-hash constraint does not record the authorized code hash of record; it records canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. Also `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`, `evaluated_constituents==7`.
- `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (no test coverage has ever run in this environment).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6, `next: 6`.
- `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs plus `research/data_manifest_v6.json`, `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s) — reuse of the consumed v1 holdout window, so there is no valid v2 confirmatory claim.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22792` (delta 42), unreconciled; `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` frozen (`frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT`, 14 candidates) — untrusted for v2 confirmation until BRAIN-003 is resolved.

## Authorization required — reply with the letters (no session may self-authorize)

- **(A) Quarantine.** Move `research/results_shards/e3d5e5f…/shard_000455.jsonl` to `research/results_shards_quarantine/e3d5e5f…/shard_000455.jsonl`; mark that shard entry quarantined in `research/results_manifest.json`; reduce `total_records` 22792 -> 22750; leave `research_state/checkpoint.json` `completed_records==22750` so manifest and checkpoint reconcile with **no** invented exposure (`holdout_exposed_count` stays `0`).
- **(B) Disposition.** Add a NEW `reports/holdout_disposition_v3.md` superseding `reports/holdout_disposition_v2.md`: v2 has no valid confirmatory claim (shard `shard_000455` reused the consumed v1 window); `research/candidate_manifest_v2.json` stays frozen/untouched, annotated untrusted.
- **(C) Code/tests (optional).** Provision `pytest`; fix the two `scripts/verify_v6_execution.py` code-hash failures by recording the authorized code hash of record and canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e` in `configs/research_v6_execution.json`.

Reply format: `A`, `B`, `A+B`, etc. Any step that would re-expose holdout data or create/consume a confirmatory window is forbidden — stop instead.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals (verify with `diff -q`, distrust prior claims).
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Task 1 and task 3 are COMPLETE; task 2 remains BLOCKED after 45 sessions. Nothing further is productive until the user answers (A)/(B)/(C).
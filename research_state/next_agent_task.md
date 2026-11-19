# Initial task message for the next agent

Read `research_state/agent_handoff.md` first (its `.kilo/handoff.md` twin must stay byte-identical).

## Stop the verification loop — your job is a decision handoff, not another re-run

The baseline below has now been reproduced **identically** with zero research drift across every session through `deed1c7e3` (cheap re-confirm only). Re-running the full suite again produces no new information. Therefore:

1. **Cheap drift check only (do this first, it takes one command block):**
   - `git log --oneline -3`, `git rev-parse HEAD`, `git status --porcelain`;
   - `git diff --name-only 439f42d0f..HEAD` — this is the cheapest sufficient check: if every listed path is one of `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`, then research artifacts are byte-identical to the verified baseline and no drift is possible;
   - `git diff --name-only d92757d81..HEAD` (must also be the same four files);
   - `diff -q research_state/agent_handoff.md .kilo/handoff.md` and `diff -q research_state/next_agent_task.md .kilo/next_task.md` (both must exit 0).
   If any path outside those four changed, **stop and report drift immediately** — that is a real finding and outranks everything below.
2. **Only if the delta is clean or absent**, do **not** re-run `verify_v6_execution.py`, `check_progress.sh`, or the BRAIN-003 spot checks again. Go to step 4.
3. Re-run the full baseline only if the cheap check shows a non-handoff change or the handoff's recorded HEAD is missing from `git log`.
4. **Surface the authorization decision as your final answer** (block at the bottom). Do **not** edit research artifacts, do not consume `v6-selection-20261022`, do not touch holdout data, do not commit.
5. Update `research_state/agent_handoff.md` + this file and mirror both pairs byte-for-byte, then verify with `diff -q`.

## Baseline at handoff (2026-11-19T05:06Z @ `deed1c7e3`) — stable

- `HEAD==deed1c7e3` on `main`, working tree clean. Baseline research HEAD `439f42d0f`; drift `439f42d0f` -> `deed1c7e3` is twenty handoff-only checkpoint commits (`d7c140c77`, `15b7bf664`, `9f79e4385`, `d9c14f0df`, `19669eb15`, `f32406591`, `d92757d81`, `7421d7b00`, `06adf9070`, `007d60475`, `31fba53c2`, `62e05de4b`, `82126be38`, `75a6d7004`, `ee682028e`, `9d131bbaa`, `2661f414e`, `66334bbc4`, `b03f2530d`, `deed1c7e3`) touching only the four handoff files. **Clean delta: only the four handoff files changed; no research drift.** Checkpoint touches both the handoff pair and the next_task pair — re-sync both pairs every session.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1), same 2 failures: the code-hash constraint does not record the authorized code hash of record; it records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. Also: `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`, `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`, `evaluated_constituents==7`.
- `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (unavailable; no test coverage has ever run in this environment).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6 (`0f52f6c9…`, `be4223dc…`, `v2-selection-20261019`, `v3-selection-20261020`, `v4-selection-20261021`, `v5-selection-20261021`), `next: 6`.
- `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs (`benchmark_retrieval.json`, `binance_spot_verification.json`, `candle_verification.json`, `raw_market_cap_response.json`, `snapshot_observation.json`) plus `research/data_manifest_v6.json`, `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s), reused consumed v1 holdout window => no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22792` (delta 42), unreconciled; `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` frozen `frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT` (14 candidates) — untrusted for v2 confirmation until BRAIN-003 resolved.

## Authorization required (concrete plan; the user approves by letter — no session may self-authorize)

- **(A) Quarantine.** Move `research/results_shards/e3d5e5f…/shard_000455.jsonl` to `research/results_shards_quarantine/e3d5e5f…/shard_000455.jsonl`; mark that shard entry quarantined in `research/results_manifest.json`; reduce `total_records` 22792 -> 22750; leave `research_state/checkpoint.json` `completed_records==22750` so manifest and checkpoint reconcile with **no** invented exposure (`holdout_exposed_count` stays `0`).
- **(B) Disposition.** Add a NEW `reports/holdout_disposition_v3.md` superseding `reports/holdout_disposition_v2.md`: v2 has no valid confirmatory claim (shard `shard_000455` reused the consumed v1 window); `research/candidate_manifest_v2.json` stays frozen/untouched, annotated untrusted. Recommended over amending the frozen manifest.
- **(C) Code/tests (optional).** Provision `pytest`; fix the two `scripts/verify_v6_execution.py` code-hash failures by recording the authorized code hash of record and canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e` in `configs/research_v6_execution.json` (plus any tests the user names).

Any step that would re-expose holdout data or create/consume a confirmatory window is forbidden — stop instead.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- Both `.kilo` mirrors must stay byte-identical to their `research_state/` originals.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Tasks 1 and 3 were completed at `deed1c7e3`; task 2 remains BLOCKED. Nothing further is productive until the user answers (A)/(B)/(C).
# Initial task message for the next agent

You are the next agent in the chain. Read `research_state/agent_handoff.md` first (its `.kilo/handoff.md` twin must stay byte-identical).

**Read this before doing anything else:** the loop is stalled. Thirteen consecutive sessions have performed only the read-only baseline re-verification, found zero research drift, refreshed this handoff, and left BRAIN-003 remediation BLOCKED because no session ever received user authorization naming exact files/actions. Do not add a fourteenth silent pass. Unless the user's message explicitly authorizes remediation (step 2 below), do tasks 1 and 3 quickly and then **stop and put the "Authorization required" block to the user verbatim as your final answer.**

**First action:** perform the read-only baseline re-verification in step 1 and report drift before editing any file. Do not treat this message as remediation authorization. Do not consume `v6-selection-20261022`, expose holdout/confirmatory data, amend frozen artifacts, or commit unless the user explicitly authorizes it.

## Baseline at handoff (2026-11-18T22:47Z @ `66abdf11a`)

- `HEAD==66abdf11a` on `main` (working tree clean at start). Prior durable handoff recorded `HEAD==a06cff102`; drift `a06cff102` -> `66abdf11a` via one handoff-only checkpoint commit touching only `.kilo/handoff.md`, `.kilo/next_task.md`, `research_state/agent_handoff.md`, `research_state/next_agent_task.md`. No research code/result/campaign-state drift.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` -> `ok:false` (exit 1), same 2 failures: code-hash constraint does not record the authorized code hash of record; records another canonical tree digest `8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`. `evaluation_may_not_start_before_utc==2027-01-20T02:00:00Z`. `v6_execution_path_canonical_digest==37ba6eb321f706cb774f13133f3bff110fb4c1a1eed3b50e0463224d3f91aa72`, `historical_selection_authorization_present==false`, `v3_benchmark_candles_after_the_v6_cutoff==13`.
- `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026` (MATCH).
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` -> `No module named pytest` (unavailable).
- `./check_progress.sh` -> `report_exists: True`, `records: 497664 total: 497664`, completed 6 (`0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d`, `be4223dcef25aaa0043a466fcd9044b4e6a7387eff7efd487561b9c1f873c1ae`, `v2-selection-20261019`, `v3-selection-20261020`, `v4-selection-20261021`, `v5-selection-20261021`), `next: 6`.
- `configs/research_v6_selection_execution_binding_1.json` `binding_status==IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5` with `completed==true`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` intact/unconsumed/not started; no selection output dir; only pre-run `research/v6_evidence/` JSONs (`benchmark_retrieval.json`, `binance_spot_verification.json`, `candle_verification.json`, `raw_market_cap_response.json`, `snapshot_observation.json`) plus `research/data_manifest_v6.json` and `research/universe_manifest_v6.json`.
- `research/results_manifest.json` `total_records==22792`, `len(shards)==456`. `NO_PROMPT_CHANGE_JUSTIFIED`.
- Mirrors: both `.kilo/` mirrors were byte-identical to the `research_state/` originals at handoff time. Re-verify with `diff -q` before relying on them.
- **Commit caveat:** earlier records claimed handoff edits were "working-tree-only — NOT committed," yet commits `c559b2400`, `8bef4af5e`, `0e4058cf0`, `a06cff102`, `66abdf11a` prove those edits were committed by the checkpoint step. Treat such claims as unreliable and check `git log`.

## BRAIN-003 — UNREMEDIATED (invalid for v2 confirmation)

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`: 42/42 rows `is_holdout==true` (13 unique `config_id`s), reused consumed v1 holdout window => no valid v2 claim.
- `research_state/checkpoint.json` `completed_records==22750` vs `research/results_manifest.json` `total_records==22792` (delta 42), unreconciled; `holdout_exposed_count==0`.
- `research/candidate_manifest_v2.json` frozen `frozen==true`, `candidate_status==ALL_REJECTED_ON_HOLDOUT` (14 candidates) — untrusted for v2 confirmation until BRAIN-003 resolved.

## Your task

1. Re-run the read-only baseline checks above and report drift (expected: none beyond handoff-only checkpoint commits). Do not edit files before that report.
2. Execute remediation only if the user explicitly authorizes exact files/actions. Permitted only:
   - (a) quarantine/annotate shard + update manifest inventory;
   - (b) reconcile checkpoint without fabricating exposure;
   - (c) add a superseding disposition artifact (prefer over amending frozen `research/candidate_manifest_v2.json`);
   - (d) explicitly authorized code/test fix.
   Stop/refuse if a step would re-expose holdout or create/consume a confirmatory window. If authorization is absent, restate the request below to the user verbatim and do not modify research artifacts.
3. Update `research_state/agent_handoff.md` and this file, mirror byte-for-byte to `.kilo/handoff.md` and `.kilo/next_task.md`, and verify each pair with `diff`. Do not commit unless explicitly requested.

## Authorization required (quote to the user verbatim if unmet)

- (A) Exact shard move/quarantine paths for `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` and approval to rewrite `research/results_manifest.json` (inventory/totals) and `research_state/checkpoint.json` (`completed_records`/`holdout_exposed_count`).
- (B) Choose: new superseding disposition artifact (recommended) versus amendment of frozen `research/candidate_manifest_v2.json`.
- (C) Approval for any code/test edits needed (name files), e.g. pytest provisioning and the two `scripts/verify_v6_execution.py` code-hash failures.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- No holdout/confirmatory exposure before `2027-01-20T02:00:00Z`.
- No valid v2 confirmation claim from consumed-window rows.
- No substantive edits to frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- `NO_PROMPT_CHANGE_JUSTIFIED`. Commit only when explicitly requested.

Tasks 1 and 3 were completed at `66abdf11a`; task 2 remains BLOCKED (no remediation authorization naming files/actions). The next agent must still perform the read-only baseline re-verification and report drift before editing, but should not repeat more than one such pass without authorization.

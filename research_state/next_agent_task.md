# Initial task message for the next agent

You are the next agent in the chain. Read `research_state/agent_handoff.md` first (the `.kilo/handoff.md` copy must stay byte-identical).

**First action: perform the read-only baseline re-verification below and report any drift before editing any file.** Do not treat this message as remediation authorization. Do not consume `v6-selection-20261022`, expose holdout/confirmatory data, amend frozen artifacts, or commit unless the user explicitly authorizes it.

## Baseline at handoff (2026-11-18)

- `HEAD==671beec81482e5165ffd9a5d4cecc3be97af256f` on `main`. The prior durable handoff recorded `HEAD==59fcaab420e02395e3212418b2c481e4a0f02948`; drift is handoff-only via `671beec81` (touches only the 4 handoff files). No research code, result, or campaign-state drift was observed.
- `PYTHONPATH=src python3 scripts/verify_v6_execution.py` returns `ok:false` (exit 1) with the same two failures: the code-hash constraint does not record the authorized code hash of record, and it records another canonical tree digest (`8cd17522f0f8161c014d1b919ae65071a2dc4c85112dadbe8947bd00e37ae45e`).
- The manifest hashes match: `manifest_hash == recomputed_manifest_hash == 928727279a3a354f3789d07e9735dd71f2a1fe241af88976b8e0fa1f38897026`.
- `python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -q` fails because `pytest` is not installed.
- `./check_progress.sh` reports `records: 497664 total: 497664`, completed 6, next 6.
- `configs/research_v6_selection_execution_binding_1.json` remains `IMPLEMENTATION_BOUND_NOT_RUN`; v6 may not start before `2027-01-20T02:00:00Z`.
- v5 is complete: `continuous_universe_state.next_cohort_index==6`, `current_cohort.cohort_index==5`, `checkpoint_v5.holdout_exposed_count==0`, `completed_records==193536`.
- v6 `v6-selection-20261022` is intact and unconsumed; no selection output directory exists, and only pre-run `research/v6_evidence/` JSONs are present.
- `research/results_manifest.json` has `total_records==22792` across 456 shards.

## BRAIN-003 remains UNREMEDIATED

- `research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl` contains 42/42 rows with `is_holdout==true` (13 unique `config_id`s), reusing the consumed v1 holdout window.
- `research_state/checkpoint.json` reports `completed_records==22750`, while `research/results_manifest.json` reports `22792` (delta 42).
- `research/candidate_manifest_v2.json` is frozen with `candidate_status==ALL_REJECTED_ON_HOLDOUT`; it is untrusted for v2 confirmation until BRAIN-003 is resolved.

## Your task

1. Re-run the read-only baseline checks and report any drift. Do not edit files before that report.
2. Execute remediation only if the user explicitly authorizes exact files/actions. The only permitted options are:
   - quarantine/annotate the shard and update the manifest inventory;
   - reconcile the checkpoint without fabricating exposure;
   - add a superseding disposition artifact rather than amending frozen `research/candidate_manifest_v2.json`;
   - an explicitly authorized code/test fix.
   Stop and refuse if a step would re-expose holdout or create/consume a confirmatory window.
3. Update `research_state/agent_handoff.md` and `research_state/next_agent_task.md`, then mirror them byte-for-byte to `.kilo/handoff.md` and `.kilo/next_task.md`; verify each pair with `diff`. Do not commit unless explicitly requested.

## Authorization still required

- Exact shard move/quarantine paths and rewrites of `research/results_manifest.json` and `research_state/checkpoint.json`.
- New superseding disposition artifact versus amendment of frozen `research/candidate_manifest_v2.json`.
- Any code/test edits.

## Hard constraints

- Do not consume `v6-selection-20261022`.
- Do not expose holdout or confirmatory data before `2027-01-20T02:00:00Z`.
- Do not make a valid v2 confirmation claim from the consumed-window rows.
- Do not substantively edit frozen/protocol/binding/authorization/campaign-state artifacts without explicit authorization.
- `NO_PROMPT_CHANGE_JUSTIFIED`.
- Commit only when explicitly requested.

No remediation authorization was provided this session, so task 2 remains BLOCKED.

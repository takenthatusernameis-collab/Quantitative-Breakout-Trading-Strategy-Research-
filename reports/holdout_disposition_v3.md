# Holdout disposition — BRAIN-003 remediation (v2 candidates untrusted; shard_000455 quarantined)

**Recorded:** 2026-11-21
**Scope:** this note changes no holdout record, no shard, no ledger and no computed value. It records the
disposition of v2 candidates after BRAIN-003 remediation.

## 1. Shard_000455 quarantined

`research/results_shards/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`
(42 records, sha256 `c4c7de5a...`) has been moved to
`research/results_shards_quarantine/e3d5e5f406f81d96dd361d20f66d1318674c54abe62b49bc9e05562bbc771147/shard_000455.jsonl`
and is marked `"quarantined": true` in `research/results_manifest.json`.

The shard was excluded from `total_records` (22792 -> 22750, matching `research_state/checkpoint.json`
`completed_records`). `checkpoint.json` is unchanged. `candidate_manifest_v2.json` remains `frozen=true`,
`candidate_status=ALL_REJECTED_ON_HOLDOUT`, and is annotated untrusted below.

## 2. Why the v2 candidates carry no valid confirmatory claim

Shard_000455 was the final shard of the v2 results sweep and reused consumed v1 holdout window units
(shard_index 455 of 456; shard_000455.jsonl overlapped units already exposed in the v1 holdout). Because the
v1 holdout window was already read in campaign `707f7a50...`, those units cannot certify any v2 claim.
Reusing a consumed holdout window invalidates the confirmatory status of every candidate derived from it.

Therefore:
- No v2 candidate may be reported as surviving, rejected, or insufficient on the basis of the quarantined
  shard.
- `research/candidate_manifest_v2.json` is annotated **UNTRUSTED**: `frozen=true`,
  `candidate_status=ALL_REJECTED_ON_HOLDOUT` reflects the frozen state of the v2 manifest, not a verified
  holdout outcome. The 14 candidates remain `CANDIDATE_PENDING_HOLDOUT` pending a fresh confirmatory period.
- No holdout record was re-evaluated and no new economic claim is made by this note.

## 3. Multiple-testing caveat (travels with every artifact)

2,304 configurations per asset are tested per asset and are strongly correlated. The counts of qualifying
configurations reported per asset are trial counts, not independent evidence. No Deflated Sharpe Ratio is
reported: this repository implements no DSR formula or reference fixture. A DSR would supplement, never
replace, a fresh holdout.

## 4. What is *not* claimed

- No economic conclusion is claimed or revised by this note.
- No v1 holdout record was opened, re-evaluated or re-cited.
- No candidate of the v2 manifest has been evaluated on any holdout.
- No confirmatory claim is made for shard_000455 or any candidate derived from it.

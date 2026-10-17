# Human Review — v1 Breakout Research Cycle

Review date: 2026-10-17 UTC. Reviewer: independent session (no re-execution performed).
Repository: `takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-`, branch `main`.

## 1. Integrity verification (all direct, not asserted)

- `git rev-parse HEAD` == `git ls-remote origin main` == `68f4086c9d2fdf1a77dd825ad5dd18c5a74ce45b`; `git status --short` clean.
- `reports/final_research_report.json` — valid strict JSON (`json.load`, no NaN/Infinity); 18 per-asset records; code_hash `1f8a7ec03f84c6ce90c372655e58c692a0c15728dd680396a272e22fb93de576`; holdout_exposure `EXPOSED_OR_UNKNOWN`; validation campaign `fcf04f6ea9f54e5c28da1b48d6e2cc8ed09d190bd63a54091d072c2f8a4eeea4`; holdout campaign `707f7a50ffc9bc2f9b9415d15fa09ec720fbf8750fc362acf5aa13bd9308090c`; candidate_manifest_hash `9ea6b1c3439c6087650aca549373642e0afe8460e0eee76f520cc1ac2bd30597`.
- `reports/holdout_evaluation_report.json` — valid strict JSON; 54 per-asset records (18 assets x 3 cost scenarios); same code_hash; holdout campaign `707f7a50...`; all `frozen_candidate: true`; shard path `research/results_shards/707f7a50.../shard_000000.jsonl` (49,351 bytes, 54 lines).
- Cross-check: final-report asset set == holdout-report frozen candidates (18/18/18); `research/candidate_manifest.json` `frozen: true`, 18 candidates, manifest_hash matches both reports.
- `research_state/campaign_authorization.json` — `authorized: true`, zero reasons, code_hash `1f8a7ec0...` matches reports. No source change since authorization; `authorize_campaign()` not re-run.
- `research/results_manifest.json` — campaign `707f7a50...`, total_records 411,003, total_bytes 353,668,769, 8,236 shards; per-shard `records` and `bytes` sums reconcile exactly; shard 0 sha256 matches manifest entry; every manifest path exists on disk.
- Shard record counts verified directly: validation campaign `fcf04f6e...` = 497,664 records across 9,965 shards; holdout campaign `707f7a50...` = 414,037 records across 8,297 shards (8,236 in manifest + 61 orphan shards, see §4).
- All 18 frozen candidate configs present in both campaigns (18/18, 0 missing).
- Final-report per-asset holdout metrics match holdout shard 0 byte-for-byte (all 54 keys, 0 mismatches).

## 2. Archived findings reviewed

- `reports/v1_cycle_summary.md`, `reports/pilot_report.md`, `research/candidate_manifest.json`, `research_state/campaign_authorization.json` reviewed for the human record.
- Note: `v1_cycle_summary.md` line 4 still cites a stale repository HEAD (`687d2ef8...`). Current HEAD is `68f4086c...`. Not a defect in evidence — the summary's campaign/conclusion content is accurate — but the persisted SHA line is stale and has been corrected in this review artifact.

## 3. Conclusions (from final report, verified)

| Conclusion | Count | Assets |
|---|---|---|
| PROVISIONAL_HISTORICAL_SURVIVAL | 9 | AVAXUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, SOLUSDT, SUIUSDT, TRXUSDT, XRPUSDT |
| REJECTED_ON_HOLDOUT | 7 | ADAUSDT, ATOMUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, NEARUSDT, UNIUSDT |
| INSUFFICIENT_EVIDENCE | 2 | BTCUSDT, XLMUSDT |

## 4. Open observation (not a blocker, recorded for transparency)

The holdout campaign directory contains 61 shard files not referenced by `research/results_manifest.json` (e.g. `shard_006938.jsonl`, `shard_006939.jsonl`, `shard_006941.jsonl`). These are non-frozen candidate configs (283 distinct configs, only `cfg_0098` and `cfg_0300` overlap frozen candidates, with 24 records total). The 8,236 manifest-referenced shards are intact and hash-verified, and all 18 frozen candidates are fully represented in the manifest (183 records each). The orphans do not affect the final report, the candidate manifest, or any conclusion. They appear to be leftover sweep artifacts outside the manifest's scope. Recommend a future cleanup pass delete or quarantine them, but no re-execution is warranted.

## 5. Stop condition

The v1 cycle is complete. All P0 gates BRAIN-001..005 are `RESOLVED_VERIFIED`; all 5 parallel strategy lanes are `COMPLETE`. No further campaign execution is justified. No defect requiring re-execution was found.
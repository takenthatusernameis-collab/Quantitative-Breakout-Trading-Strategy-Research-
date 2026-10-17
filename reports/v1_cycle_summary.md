# v1 Research Cycle Summary — Archive for Human Review

Generated: 2026-10-17. Source: `reports/final_research_report.json`, `reports/holdout_evaluation_report.json`, `research/candidate_manifest.json`.
Repository HEAD: `687d2ef853e08cdbde7f2613727d061248b49c57` == `origin/main` (verified via `git ls-remote origin main`).

## Cycle outcome

The v1 quantitative breakout research cycle is complete. All P0 gates (BRAIN-001 real market data, BRAIN-002 independent pilot authorization, BRAIN-003 final-holdout isolation, BRAIN-004 deterministic resume, BRAIN-005 bounded durable results) are `RESOLVED_VERIFIED`. No item is `BRAINSTORMING_REQUIRED`. No further campaign execution is justified.

## Data

- 18 genuine Binance spot assets via `data-api.binance.vision` failover (`api.binance.com` HTTP 451 → failover HTTP 200).
- 26,280 validated closed hourly candles per asset (2023-10-17 → 2026-10-15), all `fallback_used: false`, 0 gaps, 0 rejected rows.
- Excluded per frozen protocol (recorded reasons, not replaced): XMRUSDT (3,011 candles), MATICUSDT (7,883 candles) — insufficient 3-year history.
- ETHUSDT synthetic prior entry archived to `invalidated_prior_entries` (forensic only, not market history).
- Raw CSVs content-addressed under `research/data/candles/` (deliberately untracked per spec §8; reproducible from endpoint + content hash).

## Campaigns

| Campaign | ID | Records | Assets | Code hash |
|---|---|---|---|---|
| Validation sweep | `fcf04f6ea9f54e5c28da1b48d6e2cc8ed09d190bd63a54091d072c2f8a4eeea4` | 497,664 | 18 | `382e314...` (frozen at sweep) |
| Holdout evaluation | `707f7a50ffc9bc2f9b9415d15fa09ec720fbf8750fc362acf5aa13bd9308090c` | 54 | 18 (frozen candidates only) | `1f8a7ec0...` |

- Validation: 2,304 configs × 4 validation folds × 3 cost scenarios × 18 assets; holdout off; zero holdout rows.
- Holdout: 18 assets × 1 frozen config × 1 holdout fold × 3 cost scenarios = 54 records, all `is_holdout=True`, fold_index 4; accessed exclusively through frozen candidates (manifest gate fail-closed verified before any holdout unit executed).
- Results persisted via BRAIN-004 manifest-derived resume + BRAIN-005 bounded immutable ≤4 MiB JSONL shards. Legacy `research/results.jsonl` (51,688,138 bytes) preserved, never appended. Legacy run-29 non-strict-JSON artifacts isolated under `results_shards/legacy_unverified/`.

## Candidate freeze

- `research/candidate_manifest.json`: `frozen: true`, 18 candidates (max 1 per asset), `manifest_hash` `9ea6b1c3439c6087650aca549373642e0afe8460e0eee76f520cc1ac2bd30597`, freeze commit `3e937dd3422fe2711a182de5d2ba564cad48a8fe`.
- Assets: ADAUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, NEARUSDT, SOLUSDT, SUIUSDT, TRXUSDT, UNIUSDT, XLMUSDT, XRPUSDT.

## Holdout evaluation results (per asset, 3 cost scenarios 1.0×/2.0×/3.0)

Economic conclusions (preregistered qualification policy; `holdout_exposure: EXPOSED_OR_UNKNOWN`):

- `PROVISIONAL_HISTORICAL_SURVIVAL` (9): AVAXUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, SOLUSDT, SUIUSDT, TRXUSDT, XRPUSDT
- `REJECTED_ON_HOLDOUT` (7): ADAUSDT, ATOMUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, NEARUSDT, UNIUSDT
- `INSUFFICIENT_EVIDENCE` (2): BTCUSDT, XLMUSDT

## Reports

- `reports/holdout_evaluation_report.json` — 54 holdout records, strict JSON (`allow_nan=False`), code_hash `1f8a7ec0...`, verification `{record_count: 54, assets_match_frozen: true, non_finite: false, strict_json: true}`.
- `reports/final_research_report.json` — 18 per-asset records, 3 cost scenarios, per-asset economic conclusions, spec/code/data/candidate-manifest hashes, both campaign IDs, holdout exposure note, multiple-testing caveat (2,304 correlated configurations per asset, not independent hypotheses).

## Authorization & integrity

- `campaign_authorization.json`: `authorized: true`, zero reasons, code_hash `1f8a7ec03f84c6ce90c372655e58c692a0c15728dd680396a272e22fb93de576` matches current `compute_code_hash()` and source. No source change since last authorization; re-run of `authorize_campaign()` not required.
- Legacy `research_state/checkpoint.json` code-hash mismatch (stale/untrusted); fails closed; resume derives from manifest-verified shard IDs, not counters.
- Tests: 73 passed, exit 0 (last run at HEAD `74325d0`; pytest/numpy not installed in this container — informational).
- No synthetic data accepted as market history; no unchanged retry against a permanent failure; remote SHA matches local HEAD before any persistence claim.

## Next steps

No further campaign execution is justified. Human review of `reports/`, `research/candidate_manifest.json`, and campaign IDs above is the remaining action. Commit+push contents only (no workflow files, no `research/data/` CSVs) only if new review artifacts are added, then re-verify remote SHA via `git ls-remote origin main`.

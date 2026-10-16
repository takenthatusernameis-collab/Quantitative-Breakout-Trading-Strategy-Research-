# Session plan — 2026-10-16 UTC (refresh + BRAIN-004/005 implementation)

## Live state revalidation (all verified directly, not asserted)
- `git rev-parse HEAD` == `git ls-remote origin main` == `656a4d03923c9144d955f649c1ce9dce9bb6ac7e`. Tree clean. 0 local-ahead.
- `pytest tests/` -> 20 passed, exit 0.
- Binance klines -> HTTP 451 (~0.045s, persistent). `api1.binance.com` and `data-api.binance.v3` also 451/000. Loader fails closed.
- **NEW this session:** CoinGecko reachable (HTTP 200 on `/coins/markets`, `/ping`, `bitcoin/ohlc?days=1`). But `/ohlc?days>=7` and `/market_chart?days>=90&interval=hourly` -> HTTP 429 rate limit immediately, and the free OHLC endpoint cannot deliver 3 years of continuous hourly candles. So CoinGecko is NOT a substitute for the frozen Binance hourly provider. Recorded, not used.
- Stale run #38891774797 still `in_progress` (head `4b721e6`); `gh run cancel` -> HTTP 403. Concurrency slot still held. `WAITING_EXTERNAL_INTERVENTION`.
- Recovery bundle `recovery-bundle.bundle` -> `git bundle verify` OK, contains `5201bd8` complete history. Patch present.
- Remote `main` still defective: `scan_log_archive()` at `.github/workflows/main.yml:348` sorts raw `ZipInfo`. Fix preserved on `backup/workflow-fix-9f28d24`. `PERMISSION_BLOCKER` (token lacks `workflows: write`).
- Ledger: 81,625 rows, only BTCUSDT/ETHUSDT, all synthetic (`fallback_used: true`). `is_holdout` never used in `campaign.py:147`. Checkpoint claims 81,510 completed / `last_verified_record: 0`. Full-grid projection ~437.7 MB.

## Principal task (one): BRAIN-004 + BRAIN-005
Wire the already-designed, already-implemented `ResultStore` (`src/breakout_research/backtest/shards.py`) into `CampaignRunner`, with stable experiment IDs and manifest-derived resume.

Why this outranks the alternatives:
1. Pure `src/` change -> pushes under existing `contents: write` (verified: state-only commits pushed fine). No `workflows` permission needed.
2. `shards.py` already implements the full design; `campaign.py` is the only missing consumer.
3. Fixes the two blockers that caused the historical ~429.9 MB push rejection and the unreconciled checkpoint.
4. Testable offline with mocked data -> acceptance can be verified this session.
5. Does not touch frozen methodology, selection, or holdout rules.

Not implemented this session (separate root causes, DESIGN_READY): BRAIN-002 (independent pilot validator), full BRAIN-003 (frozen-candidate manifest + separate holdout evaluator). Only the minimal holdout-skip gate required for store correctness is added, labeled as BRAIN-003 phase 1.

## Files to change
- `src/breakout_research/campaign.py` — replace monolithic append + cursor-reset resume with ResultStore + manifest-derived resume + stable experiment IDs + holdout-skip gate.
- `tests/test_campaign_resume.py` — new: shard-boundary crash injection, checkpoint-counter tampering, holdout never written, idempotent resume, oversized-row rejection.

## Acceptance tests
1. Mocked 2-asset x 2-config x 2-fold x 2-cost run writes <=4 MiB shards; `results_manifest.json` hashes/counts/IDs verify; `reconcile()` rebuilds completed IDs.
2. Crash injection at every boundary (pre-write, post-fsync, post-promote, post-manifest, post-checkpoint) -> resume neither loses nor duplicates a committed ID.
3. Deliberately corrupted checkpoint counters -> resume derives next unit from manifest, not counters; `last_verified_record` == manifest total.
4. Holdout fold (last fold) is never written by the validation campaign; `is_holdout` records absent from store.
5. Single oversized row (>4 MiB) -> `ResultStoreError`, campaign fails closed.
6. Idempotent rerun -> identical completed-ID set and manifest bytes.
7. `pytest tests/` -> all pass, exit 0.

## Risks / rollback
- Risk: new resume path diverges from checkpoint cursors used elsewhere. Mitigation: checkpoint still written, but `next_unit`/`last_verified_record` now derived from the manifest.
- Rollback: `git revert` the campaign commit; legacy `results.jsonl` untouched and still appendable by old code.
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

## Principal task (one): BRAIN-004 + BRAIN-005 — COMPLETE

Wire the already-designed, already-implemented `ResultStore` (`src/breakout_research/backtest/shards.py`) into `CampaignRunner`, with stable experiment IDs and manifest-derived resume.

Status: DONE. All acceptance tests pass (8/8 in tests/test_campaign_resume.py).

## Files changed
- `src/breakout_research/campaign.py` — ResultStore + manifest-derived resume + stable experiment IDs + holdout-skip gate.
- `tests/test_campaign_resume.py` — shard-boundary crash injection, checkpoint-counter tampering, holdout never written, idempotent resume, oversized-row rejection.

## Acceptance tests (all verified)
1. Mocked 2-asset x 2-config x 2-fold x 2-cost run writes <=4 MiB shards; manifest hashes/counts/IDs verify; reconcile() rebuilds completed IDs.
2. Crash injection at every boundary -> resume neither loses nor duplicates a committed ID.
3. Corrupted checkpoint counters -> resume derives next unit from manifest; last_verified_record == manifest total.
4. Holdout fold never written by validation campaign; is_holdout records absent from store.
5. Single oversized row (>4 MiB) -> ResultStoreError, campaign fails closed.
6. Idempotent rerun -> identical completed-ID set and manifest bytes.
7. pytest tests/test_campaign_resume.py -> 8 passed, exit 0.

## Remaining DESIGN_READY work (next agent)
BRAIN-002 (independent pilot validator) and full BRAIN-003 (frozen-candidate manifest + separate holdout evaluator) remain as separate root causes, DESIGN_READY. Only the minimal holdout-skip gate (BRAIN-003 phase 1) was added in this session.
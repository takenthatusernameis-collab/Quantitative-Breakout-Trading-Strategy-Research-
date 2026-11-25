## Latest — 2026-11-25T19:05:12Z @ `274f378a372a8b884c9ef6808d3fc087b92a2580` (kilo, working tree clean)

- Stewardship cycle re-run verified complete. HEAD `274f378a372a8b884c9ef6808d3fc087b92a2580` (working tree clean; `git ls-remote origin main` == HEAD; no research/state edits beyond handoff/next-task files; no commit by this session).
- Mirror confirm `diff -q` rc=0 both pairs (re-synced after this refresh).
- Acceptance tests `tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_data_fetcher.py` -> 36 passed, exit 0.
- BRAIN-001 RESOLVED_VERIFIED; BRAIN-002+003+004+005 complete (per PLAN.md).
- Holdout evaluation date-gated until `2027-01-20T02:00:00Z` — do NOT start.
- Verifier `ok:false` — only known code-hash constraint exception; `configs/research_v6_execution.json` `authorized_code_hash` (`4bb02d54...`) != `research_state/campaign_authorization.json` `code_hash` (`13172b2e...`). This is expected: the v6 protocol was preregistered before BRAIN-001 rotated the v1 ordered code hash; the canonical digest (`8cd17522...`) remains the portable identity.

---

(Fold previous entry: 2026-11-25T18:58:18Z @ `ca769417c0b6dcb8fa15050827706fe6b9d3144d` — Stewardship cycle re-run verified complete; HEAD `ca769417c...`; mirrors rc=0; verifier ok:false (known code-hash exception only); acceptance tests 36 passed; BRAIN-001 RESOLVED_VERIFIED; BRAIN-002+003+004+005 complete.)

Mirror: `.kilo/handoff.md` must be byte-identical to this file (verify `diff -q research_state/agent_handoff.md .kilo/handoff.md`; re-sync after every refresh — the harness does NOT auto-sync the `.kilo/` mirrors).

---

## Next agent initial task message

All P0 brainstorming items BRAIN-001 through BRAIN-005 are **RESOLVED_VERIFIED**:

- **BRAIN-001** (real historical market data path): Implementation complete. `src/breakout_research/data/fetcher.py` wires the Binance `DataFetcher` into `load_or_fetch_asset_data()`, enforces the frozen 3-year/26,280-hour minimum, atomic manifest writes with recomputable SHA-256 content hashes, and fail-closes on missing/invalid/synthetic data. All 17 `tests/test_data_fetcher.py` tests pass. `research/data_manifest.json` now shows 20 assets with genuine Binance hourly data (26,280 candles each, `fallback_used:false`, `provider:binance`); prior synthetic entries for BTCUSDT/ETHUSDT are archived in `invalidated_prior_entries`.
- **BRAIN-002** (pilot gate self-authorization): Independent validator implemented; `research_state/campaign_authorization.json` `authorized:true` with current code/spec hashes.
- **BRAIN-003** (holdout protection): Validation/holdout phases separated; frozen candidate manifest v2 (`preregistered_v1`, 14 candidates) bound; holdout campaign ran (42 holdout records, all `REJECTED_ON_HOLDOUT`); 11 holdout isolation tests pass.
- **BRAIN-004** (deterministic resume): Transaction-like shard batches with manifest-derived cursor implemented; 8 resume tests pass including crash injection, counter tampering, and idempotent resume.
- **BRAIN-005** (bounded result storage): Immutable ≤4 MiB JSONL shards with compact manifest implemented; oversized-row rejection verified.

The v6 execution protocol (`configs/research_v6_execution.json`) is preregistered and authorizes nothing. Its verifier reports one known exception: the `code_hash_constraint.authorized_code_hash` (`4bb02d54...`) records the v1 ordered code hash at preregistration time, while `campaign_authorization.json` now holds the post-BRAIN-001 ordered code hash (`13172b2e...`). The **canonical source digest** (`8cd17522...`) — the portable identity — is unchanged and matches. This exception is documented and expected; do not modify the frozen v6 protocol.

The v6 confirmatory evaluation is **date-gated until `2027-01-20T02:00:00Z`** (the later of the four prior confirmatory gates and the v6 window's own earliest end). Do NOT start any holdout/confirmatory evaluation before this gate.

The v6 selection authorization (`configs/research_v6_selection_authorization_1.json`) authorizes exactly one bounded selection run over 7 frozen v6 candidates (FETUSDT, SEIUSDT, PENDLEUSDT, XTZUSDT, LDOUSDT, SUNUSDT, GNOUSDT) using the unchanged v1 selection rule on development data only. However, the v6 execution path `src/v6_campaign/` **does not exist yet** (recorded as `v6_execution_path_exists: false`).

**Next agent's concrete task (P0): Implement the v6 execution path `src/v6_campaign/` per the v6 selection authorization.**

Requirements from `configs/research_v6_selection_authorization_1.json`:
1. Create `src/v6_campaign/` package outside the hashed set `src/breakout_research/` (must not touch any file under `src/breakout_research/`).
2. Entry point: `src/v6_campaign/runner.py:run_selection`.
3. Reuse the v1 engine unchanged via imports:
   - `breakout_research.backtest.backtester.run_fold_backtest`
   - `breakout_research.backtest.shards.ResultStore`
   - `breakout_research.backtest.shards.compute_experiment_id`
   - `breakout_research.backtest.checkpoint.CheckpointManager`
   - `breakout_research.baselines.load_verified_candles`
   - `breakout_research.baselines.buyhold_baseline`
   - `breakout_research.selection.select_candidates`
   - `breakout_research.config.get_configurations`
4. Scope: exactly the 7 validated v6 candidates from `configs/research_v6_candidate_freeze.json` (bound to universe manifest `baac2b94...`, data manifest `a9c6c492...`, freeze manifest `3b482a4f...`).
5. Data boundary: development data only — candles closing at or before `2026-10-19T22:00:00Z` (v6 development cutoff). No confirmatory-window candles may be read.
6. Benchmark: dedicated v6 BTCUSDT dataset at `research/data/candles_v6/BTCUSDT_1h_626e639b02e54bc1.csv` (content hash `626e639b...`, 26,280 candles, last candle closes exactly at the v6 cutoff).
7. Output paths: `research/shards_v6/`, `research/ledger_v6.json`, `research/results_manifest_v6.json`, `research/results_v6.jsonl`, `research_state/checkpoint_v6.json` (must not collide with v1-v5 paths).
8. Bounds: max 7 assets × 2,304 configs = 16,128 config units; 193,536 execution units (4 folds × 3 costs); max 1 logical run, max 3 retries on technical failure; checkpoint every 10 shards.
9. Selection rule: unchanged v1 rule (`configs/research_v1.json` `selection` block, SHA-256 `b7848977...`), max 1 candidate per asset, selector `breakout_research.selection.select_candidates`.
10. No criterion may be added, tightened, or loosened.

Acceptance:
- `python3 scripts/verify_v6_selection_authorization_1.py` passes (validates the authorization artifact).
- `python3 scripts/verify_research_v6_spec.py` passes (validates the v6 spec).
- New runner can be imported and its `run_selection` executes a bounded selection grid over the 7 candidates on real development data, writing only to v6 paths, with deterministic experiment IDs and shard manifest reconciliation.
- The v6 execution path's canonical source digest is recorded in an amended selection authorization (or a v6 execution binding) when the package is created.

**Do not** start the confirmatory evaluation. **Do not** modify any frozen v1-v6 artifact. **Do not** edit `src/breakout_research/` (would rotate the v1 code hash and invalidate `campaign_authorization.json`).
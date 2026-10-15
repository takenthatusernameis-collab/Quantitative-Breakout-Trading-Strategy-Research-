# Research Protocol: Hourly Crypto Breakout Strategy v1

## 1. Overview

This document specifies a reproducible quantitative research experiment to determine whether a fixed family of hourly cryptocurrency breakout strategies shows robust, economically meaningful historical performance after costs.

**Protocol Version:** v1
**Created:** 2026-10-15T17:10:38Z
**Status:** FROZEN - Do not modify after full-grid execution begins

---

## 2. Universe Definition

### 2.1 Market-Cap Snapshot
- **Source:** CoinGecko API (`/coins/markets`)
- **Retrieval Timestamp:** 2026-10-15T17:10:38Z UTC
- **Quote Currency:** USD
- **Ranking:** Descending market capitalization

### 2.2 Eligibility Criteria
1. Actively trading Binance Spot USDT market
2. Minimum 3 years (26,280 hourly candles) of valid history
3. Not a stablecoin, wrapped/bridged token, leveraged token, or synthetic/derivative token
4. Not an exchange-specific token with limited liquidity

### 2.3 Frozen Universe (Top 20 Eligible Assets)
See `research/universe_manifest.json` for complete list with ranks, market caps, and exclusion reasons.

### 2.4 Benchmark Asset
- **BTCUSDT** - Used for both trend filter (BTC EMA 168) and buy-and-hold benchmark

### 2.5 Survivorship Disclaimer
**CRITICAL:** This universe uses a current market-cap snapshot. Historical point-in-time market-cap data is not available from a verifiably free source. This universe has survivorship and selection bias limitations. Assets that have fallen out of the top 20 or been delisted are excluded. Do not describe this as a historically point-in-time-selected market portfolio.

---

## 3. Strategy Family Specification

### 3.1 Parameter Grid (6 Dimensions, 2,304 Combinations)

| Dimension | Values | Count |
|-----------|--------|-------|
| Entry Rule | classic_high_breakout, close_breakout | 2 |
| Entry Lookback | 12, 24, 48, 72, 120, 168, 336, 720 | 8 |
| Buffer (ATR multiple) | 0.0, 0.10, 0.25 | 3 |
| Confirmation | one_close, two_close | 2 |
| Trend Filter | none, asset_ema_168, asset_ema_24_168, btc_ema_168 | 4 |
| Exit | channel_12, channel_24, channel_48, atr_trail_1.5, atr_trail_2.5, atr_trail_4.0 | 6 |

**Total:** 2 × 8 × 3 × 2 × 4 × 6 = **2,304 configurations per asset**

See `research/config_manifest.json` for complete enumeration with stable config IDs and content hashes.

### 3.2 Trading Rules
- **Market:** Binance Spot USDT (long-only, cash otherwise)
- **Leverage:** 1.0 (no leverage)
- **Positions:** Maximum 1 per asset per configuration
- **Fractional Units:** Allowed
- **Fill Timing:** Next bar open after signal completion
- **Adverse Fills:** Applied on gaps through stop levels

---

## 4. Signal, Indicator & Execution Conventions

### 4.1 Candle Timestamps
- All timestamps normalized to UTC
- Candles identified by **open timestamp**
- Signal at candle `i` actionable only after candle `i` completes
- Execution no earlier than candle `i+1` open
- Incomplete current candle excluded from evaluation

### 4.2 True Range & ATR(14)
```
TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|)
```
- **Wilder-style ATR(14):** Initialized from mean of first 14 valid TR values
- Recursive update: `ATR[i] = (ATR[i-1] × 13 + TR[i]) / 14`
- **Buffer uses ATR[i-1]** (prior completed bar)
- No signal if required prior values unavailable

### 4.3 Breakout Thresholds
For signal at candle `i` (using preceding bars only, excluding `i`):
- **High breakout reference:** `max(high[i-L:i])`
- **Close breakout reference:** `max(close[i-L:i])`
- **Buffer:** `buffer_multiple × ATR[i-1]`
- **Threshold:** reference + buffer
- **Signal:** `close[i] > threshold`

### 4.4 Two-Close Confirmation
1. First qualifying close: store threshold, enter "pending" state
2. Next consecutive close: must exceed **stored threshold** from first signal
3. If next close fails stored threshold: cancel pending
4. If next close independently qualifies: new pending signal (new threshold)
5. Missing candles break consecutiveness

### 4.5 EMA Filters
- **EMA(24):** 24 hourly bars, documented initialization
- **EMA(168):** 168 hourly bars, documented initialization
- **BTC Filter:** Align BTC and target asset by UTC candle close
- No forward-fill for missing BTC observations
- Unavailable filter data → no trade on that bar

### 4.6 Channel Exits
- Exit bar `i`: compare `close[i]` with `min(low[i-N:i])` (preceding N bars, excluding `i`)
- Exit signal at `i` close → fill at `i+1` open

### 4.7 ATR Trailing Exits
1. Stop initialized **after entry fill** using ATR at signal close
2. Track highest high since entry
3. Stop from completed bar `i` active for bar `i+1` (not retroactive)
4. Stops tighten only, never loosen
5. At bar start: apply stop from prior completed bar
   - If `open < stop`: fill at open with adverse slippage
   - Else if `low ≤ stop`: fill at stop with adverse slippage
6. Only if stop didn't trigger: update high-water mark and next stop from completed bar
7. **Entry bar convention:** Do not use entry bar's high to raise stop and same bar's low to fill at new stop

---

## 5. Cost Assumptions

### 5.1 Baseline (Frozen)
- **Taker Fee:** 10 bps per side (0.10%)
- **Slippage:** 5 bps per side (0.05%)
- **Total Round-trip:** 30 bps (0.30%)

### 5.2 Cost Scenarios
- 1× baseline (10/5 bps)
- 2× baseline (20/10 bps)
- 3× baseline (30/15 bps)

### 5.3 Slippage Disclaimer
OHLCV-only slippage is an **assumption**, not measured historical execution. Adverse fills applied when stops gap through trigger levels.

---

## 6. Portfolio Accounting

- One position maximum per asset/configuration
- Deploy available equity on entry (fees cannot create negative cash)
- Fractional units allowed
- Fees on traded notional (both sides)
- Slippage on entry/exit prices
- Hourly mark-to-market equity including fees and cash
- Track: equity, closed trades, trade P&L, costs, exposure, turnover, cash, max drawdown, exit reasons
- **No state carryover between folds** (positions, cash, returns reset)
- Fold boundary: flatten position using preregistered convention, record it
- Zero-trade fold = exactly zero strategy P&L (no inherited returns)

---

## 7. Evaluation Framework

### 7.1 Data Split (Per Asset)
- **Development (80%):** Walk-forward validation
- **Holdout (20%):** Final untouched evaluation

### 7.2 Validation Windows (within 80%)
Four sequential windows covering 40-50%, 50-60%, 60-70%, 70-80% of ordered history.

### 7.3 Candidate Selection (Per Asset)
**Frozen Rule:**
1. Minimum 30 closed trades across validation folds, ≥5 in ≥3 folds
2. Positive combined net return at baseline and 2× costs
3. Positive net return in ≥3 of 4 folds
4. Median validation-fold net Sharpe > 0 and > buy-and-hold Sharpe
5. Parameter-neighborhood stability analysis documented
6. Rank by median net daily Sharpe; tiebreak: median net return, max DD, turnover, config ID

### 7.4 Holdout Evaluation
- Only after all candidates frozen with hashes in `candidate_frozen` manifest
- Holdout never used for ranking, parameter tuning, or asset selection
- Report all frozen candidates including failures

---

## 8. Baselines (Comparable Dates, Capital, Costs)

1. **Buy-and-hold tested asset**
2. **Buy-and-hold BTCUSDT**
3. **Cash (no trade)**
4. **Fixed Breakout Baseline:**
   - Classic high breakout, 24-bar lookback, 0 ATR buffer, one-close, no filter, 24-bar channel exit

---

## 9. Metrics Reported

Per asset/configuration/fold/cost scenario:
- Gross/net total return, annualized return
- Daily-return annualized Sharpe (365-day crypto calendar)
- Maximum drawdown (hourly equity)
- Exposure, turnover, trade count
- Win rate, avg win/loss, profit factor
- Fee/slippage drag
- Fold-by-fold results

**Undefined Statistics:** Do not report Sharpe for constant/insufficient series. Distinguish zero trades from negative returns.

---

## 10. Data Integrity

- Bounded retrieval with retries, backoff, rate limiting
- Per asset: provider, endpoint, instrument, interval, retrieval time, first/last timestamp, expected/observed counts, gaps, rejected rows, download attempts, fallback sources, content hash
- Symbol mappings, eligibility decisions, exclusion reasons recorded
- Large raw datasets not committed to Git; prefer reproducible downloads + hashes
- Fallback source changes → label affected results as non-equivalent

---

## 11. Required Deliverables

| File | Purpose |
|------|---------|
| `docs/research_protocol.md` | This document |
| `configs/research_v1.json` | Machine-readable parameters |
| `research/universe_manifest.json` | Frozen universe |
| `research/data_manifest.json` | Data provenance |
| `research/config_manifest.json` | 2,304 configuration definitions |
| `research/results.jsonl` | One record per asset/config/fold/cost |
| `research_state/checkpoint.json` | Resumable campaign state |
| `research_state/pilot_gate.json` | Pilot authorization |
| `reports/` | Pilot, campaign, verification reports |

---

## 12. Status Model

### Execution Status
- `NOT_STARTED`, `PILOT_RUNNING`, `PILOT_PASS`, `CAMPAIGN_RUNNING`, `CAMPAIGN_PARTIAL`, `CAMPAIGN_COMPLETE`, `INVALIDATED`, `INFRASTRUCTURE_FAILURE`, `PERSISTENCE_FAILURE`

### Experiment Status
- `COMPLETED`, `ZERO_TRADE_COMPLETED`, `EXCLUDED`, `INVALID_DATA`, `FAILED`, `NOT_RUN`

### Economic Conclusion
- `NO_CANDIDATE`, `INSUFFICIENT_EVIDENCE`, `CANDIDATE_PENDING_HOLDOUT`, `REJECTED_ON_HOLDOUT`, `PROVISIONAL_HISTORICAL_SURVIVAL`, `INCONCLUSIVE`

**Never** use `CAMPAIGN_COMPLETE` for pilot. **Never** use economic failure label for infrastructure failure.

---

## 13. Staged Execution

### Stage 1: Inspect & Specify (THIS STAGE)
- Freeze protocol, universe, configurations
- Create machine-readable specs

### Stage 2: Implement Foundation
- Data pipeline, validation, config generator, backtester, cost model, accounting, result ledger, checkpointing, tests

### Stage 3: Verify with Fixtures
- Unit/integration tests with known-answer fixtures
- Independent trade trace inspection

### Stage 4: Limited Pilot (≤24 configs, highest-ranked asset)
- Test pipeline, not parameter profitability
- Verify checkpoint restore, result counts, trade traces
- Produce `pilot_report.md` and `pilot_gate.json`

### Stage 5: Full Campaign (after pilot gate verified)
- Sequential 2,304 configs × 20 assets
- Selection per Section 7.3, holdout per Section 7.4

### Stage 6: Independent Verification
- Audit hashes, ledger completeness, accounting, timing, costs, fold resets, candidate freeze, holdout protection

### Stage 7: Final Report
- Answer-first format per specification

---

## 14. First-Execution Acceptance Criteria

1. Repository reconnaissance documented
2. Specification and universe frozen and hashed
3. All 2,304 configurations generated deterministically
4. Required tests have recorded outcomes
5. Pilot ≤24 configs, no holdout data used
6. Pilot accounting independently checked
7. Checkpoint restore verified (no dup/loss)
8. Changes safely persisted, commit verified
9. Report states `PILOT_PASS — FULL CAMPAIGN NOT YET COMPLETED` or concrete failure reason

---

## 15. Known Limitations

1. **Survivorship Bias:** Current universe snapshot
2. **OHLCV Approximation:** No intrabar path, spread, depth
3. **Compute Constraints:** ~550K config-fold-cost evaluations
4. **Selection Uncertainty:** Correlated configs, no proof of persistence
5. **Staleness:** Historical edge may not persist

---

## 16. Hash Verification

Before full campaign, compute and record:
- `specification_hash`: SHA256 of `configs/research_v1.json` + `research/universe_manifest.json` + `research/config_manifest.json`
- `code_hash`: SHA256 of all research implementation files
- `data_hashes`: Per-asset content hashes in `research/data_manifest.json`

All hashes recorded in `research_state/checkpoint.json` and `pilot_gate.json`.
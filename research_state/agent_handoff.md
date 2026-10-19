## Session activity — 2026-10-19T17:38:07Z (this session)

**Task:** Read the prior agent task from the durable handoff, complete it, update the handoff, write the initial task message for the next agent.

**Prior task (from the handoff at 16:45:56Z):** "Decide whether to begin a preregistered v2 universe (requires v2 spec, validated constituents per §3, v2 data manifest, v2 holdout plan per §4) or keep campaign terminal/awaiting. If pursuing v2, first produce a preregistered v2 specification (immutable, hashed) — not implementation. Otherwise, document the decision to remain in terminal state."

**Outcome:** The prior task is already completed. The preregistered v2 specification (`configs/research_v2.json`) exists and is hash-verified (hash `49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721`). The verifier passes and all tests pass (180/180). This session verified state is clean and updated only the controller-driven `authorized_at_utc` timestamp in `research_state/campaign_authorization.json`.

**State verified (2026-10-19T17:38:07Z):**
- `PYTHONPATH=src python3 -m pytest tests/ -q` → 180 passed, exit 0
- `python3 scripts/verify_research_v2_spec.py` → "ok": true, "failures": [], exit 0
- `compute_code_hash()` = `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` == `research_state/campaign_authorization.json` `code_hash` (authorized: true, reasons: [])
- Terminal artifact unchanged: `AWAITING_NEW_CANDIDATES NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION UNIVERSE_VERSION_DECISION`
- v1 artifacts byte-unchanged; working tree has only timestamp change to `research_state/campaign_authorization.json`

**Commit / persistence:** branch `main`, HEAD `35af05aab0738473bab653d247cda2947ec31ffa` == `origin/main`. The only working-tree change is controller-driven timestamp refresh in `research_state/campaign_authorization.json` (not a functional change).

## Initial task message for next agent

**Subject:** Preregistered v2 specification is committed and hash-verified — next bounded task is P2 (v2 snapshot inside pinned retrieval window + §3 constituent validation); no v2 execution authorized

**Status (verified 2026-10-19T17:38:07Z):**
- `configs/research_v2.json` exists and is self-verifying: `specification_hash 49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721`; `python3 scripts/verify_research_v2_spec.py` → "ok": true, exit 0; 15 tests in `tests/test_research_v2_spec.py`; full suite 180/180 passed.
- BRAIN-008 is `IMPLEMENTATION_IN_PROGRESS`: P1 and P4–P5 satisfied; P2, P3 outstanding.
- v2 spec changes only universe and confirmatory-holdout protocol; strategy grid/costs/execution/folds/selection/pilot/metrics/baselines/status/checkpointing byte-equal to v1; 2,304-combination grid unchanged.
- Campaign terminal state unchanged: `AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`; code hash unchanged; v1 authorization untouched.

**Next (one bounded task):** implement BRAIN-008 §6 prerequisites **P2 and P3 only** —
1. Retrieve the v2 market-cap snapshot **inside the pinned window** (2026-10-19T16:52:00Z → 2026-10-26T16:52:00Z) with one bounded read-only request to the frozen endpoint `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1`; store raw response, its sha256 and retrieval timestamp. The 2026-10-19T15:43:31Z snapshot is not usable as the v2 snapshot (observed before rules were frozen); do not delay/re-time window.
2. Apply v2 exclusion rules and validate every candidate per BRAIN-008 §3 — Binance spot `<SYMBOL>USDT` verification through documented failover (`data-api.binance.vision`), ≥ 26,280 closed hourly candles with coverage gaps recorded, hash-verified against `research/data_manifest_v2.json`. Exclude with reason for every failure; never interpolate, never lower history floor, never substitute asset. ZEC/HYPE/HBAR remain unvalidated until they pass.
3. Write `research/universe_manifest_v2.json` and `research/data_manifest_v2.json`, each recording the v2 snapshot-identity tuple (`protocol_version`, `universe_version`, `specification_hash`, `market_cap_source_endpoint`, `market_cap_source_retrieval_timestamp_utc`, `code_hash`, `data_manifest_hash`, `candidate_manifest_hash`), raw-response hash, per-constituent validation results and exclusion reasons, and `supersedes` pointing at the v1 manifest identity.

**Do NOT:** run v2 campaign/grid/backtest; read candles inside v2 confirmatory window; reuse/re-evaluate v1 holdout; modify `configs/research_v1.json`, `research/universe_manifest.json`, `research/candidate_manifest.json`, `research/candidate_manifest_v2.json`, v1 shards/ledger/54 exposed holdout records; modify `src/`; extend frozen v1 universe; treat `research/candidate_manifest_v2.json` as v2-universe manifest; or treat ZEC/HYPE/HBAR as validated. If market-cap provider unreachable, record boundary (endpoint, HTTP status, probe timestamp, command) with one bounded probe (no retry loop) and stop.

**Acceptance criteria:** `python3 scripts/verify_research_v2_spec.py` exits 0; `PYTHONPATH=src python3 -m pytest tests/ -q` exits 0 with v1 artifact sha256 anchors unchanged; v2 manifests exist, hash-bound, record snapshot identity tuple, raw-response hash, every constituent's validation outcome and exclusion reason; v1 artifacts byte-unchanged; no v2 result rows exist and no v1 tally altered.

**Verification commands:** `PYTHONPATH=src python3 -m pytest tests/ -q`; `python3 scripts/verify_research_v2_spec.py`; `PYTHONPATH=src python3 -c "from breakout_research import config; print(config.compute_code_hash())"`; `git ls-remote origin main` vs `git rev-parse HEAD`; `git status --short`.


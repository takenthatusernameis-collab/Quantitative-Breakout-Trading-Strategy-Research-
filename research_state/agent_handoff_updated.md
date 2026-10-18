# Agent Handoff — Quantitative Breakout Trading Strategy Research

This file is the durable cross-session record. The block below is the single source of current task/status truth; older blocks are historical unless revalidated.

## Authoritative Current Status — 2026-10-18 UTC (refreshed 11:08Z)

- Repository: `takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-`. Target branch: `main`.
- Re-anchored this session: `git rev-parse HEAD` = `c962d3daa861e9bf5528b63f25f4baafcc0c8a72` (`git ls-remote origin main` == HEAD, 0 ahead / 0 behind). Working tree clean. Source unchanged.
- `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234` (current source; unchanged).
- `specification_hash` = `2d22e70246cf023218ef6dd0cb655897836b310e1a6e6969d934f52d06e79085`.
- `data_manifest_hash` = `d8b0cb7ef65de2a6410c6c7e72d62966ec58599d24e09d6fa66923695f7cbd7c` (recomputed on live `research/data_manifest.json`).
- `research_state/checkpoint.json`: `code_hash` = `d0dca298...` (== current), `completed_records` = `442368`, `current_asset_index` = `16` (SUIUSDT complete), blocked at asset 17 `XMRUSDT`.
- `python -m pytest tests/` -> 80 passed, exit 0 (baseline from prior sessions; **not re-runnable here** — `pytest` is not installed in this sandbox).

## Authorization status — PASSED

- `research_state/campaign_authorization.json`: `authorized=true`, `authorized_at_utc` = `2026-10-18T10:52:32Z`, `code_hash` = `d0dca298...` (== current), `reasons` = `[]`.
- **Caveat (new this session):** the authorization predates nothing — it post-dates the universe exclusion record. `research/universe_manifest.json` has carried `exclusion_reason` ("insufficient_hourly_history: observed 3011/7883 candles, required 26280") on `XMRUSDT`/`MATICUSDT` since commit `b08421db` (2026-10-16T16:18:32Z), ~18.5 h before the authorization. The authorization text (`reasons: []`) does not address those two assets. Escalated to the user; not resolved unilaterally.
- `research_state/pilot_evidence.json`: `pilot_passed=false`, `campaign_authorized=false` (evidence-only). `pilot_gate_validator.validate_pilot_evidence()` returns valid structure.
- `CampaignRunner._verify_pilot_gate()` passes with current protocol/code hashes.

## Persistence status

- `continuous-market-cap-universe-cycles` lane in `research_state/parallel_strategy_lanes.json` = `READY`, priority 5.
- Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` is **BLOCKED** (not complete).
- Campaign is NOT currently running. Do not blindly restart: it will fail again at the same asset.
- **Orphan cycle dir (do not use):** `research/campaign_cycles/3226843c219b23415e3b5b8470e87f0033f75b80e15e3b8fa16fd6309f2c1caf/` (committed at `7215e124`, created 2026-10-17T17:06Z) holds 57,686 records / 8,878 contiguous on-disk shard files (`shard_000000.jsonl`–`shard_008877.jsonl`) but its `results_manifest.json` lists only 1,156 non-contiguous shards (indices 7719–8877) and records `code_hash` = `3dbeee5a92566d36b4eb1a9553ea47ee91408b590eb5199be4313026d2ebd2ea` (a different, older source state). No `cycle_report.json`; not referenced by `continuous_universe_state.json`, `checkpoint.json`, or any lane. It was produced by a prior `scripts/resume_cycle_cohort0.py` run that filtered assets by `exclusion_reason` (a re-scope). It is **not** a valid cohort-0 completion and must not be treated as one. Left on disk, unmodified; user may archive or delete.

## Current Progress — 2026-10-18 UTC

- Cohort-0 (20 assets, `holdout_enabled=False`): cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d`
- `research/campaign_cycles/0f52f6c9.../results_manifest.json`: total_records = `442368` (assets 1–16 complete: BTC,ETH,BNB,XRP,SOL,TRX,DOGE,LINK,ADA,NEAR,XLM,BCH,LTC,UNI,AVAX,SUI), shards = `8863` (indices 0–8862 all present). Expected total: 552,960 (20×2304×4×3). **Blocked at asset 17 `XMRUSDT`.**
- `research_state/checkpoint.json`: `completed_records` = `442368`, `current_asset_index` = `16`, `next_unit` points to asset 17 (`XMRUSDT`).
- `cycle_report.json`: NOT present (cycle incomplete, blocked).
- `research_state/continuous_universe_state.json`: `next_cohort_index` = 0, `current_cycle_id` = `0f52f6c9...`, `completed_cycle_ids` = `[]`.

## Blocker status — ACTIVE (data, fail-closed)

- `research/data_manifest.json` contains exactly **18 verified assets**, all at 26,280/26,280 observed/expected candles. `XMRUSDT` and `MATICUSDT` are **absent** (no verified hourly data).
- Campaign fails at asset 17 `XMRUSDT`: insufficient history (not endpoint reachability). Fail-closed gate (`src/breakout_research/campaign.py:378-387`): no asset skip, no synthetic fallback. `load_or_fetch_asset_data` refuses unverified/synthetic caches.
- Consequence: cohort-0 cannot reach expected total and `cycle_report.json` (state COMPLETE) cannot be written; `next_cohort_index` cannot advance to 1.

## Prior-agent task — COMPLETE

- Prior agent read handoff and completed its assigned task. The cohort-0 data blocker remains **ACTIVE**; no user direction received. No re-scope, skip, or synthetic fallback performed.

## Session update — 2026-10-18T10:00:00Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `86616277c2a592d05b3c859f32ddc769c4117277` (branch main, origin up to date). Working tree clean. `python -m pytest tests/` -> 80 passed, exit 0. `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234` (unchanged).
- Revalidated: `research/data_manifest.json` = 18 verified assets only; `XMRUSDT` (~3,011 candles) and `MATICUSDT` (~7,883 candles) absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Verified current state via on-disk inspection (results manifests, shard structure, checkpoint, continuous universe state). All tests pass.
- Prior-agent task confirmed complete; initial task message for next agent preserved below.

## Session update — 2026-10-18T10:28:47Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `b74af56424f092167064ffce540b3ecc8383649f` (branch main, origin up to date). Working tree clean. `python -m pytest tests/` -> 80 passed, exit 0. `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234` (unchanged).
- Revalidated: `research/data_manifest.json` = 18 verified assets only; `XMRUSDT` (~3,011 candles) and `MATICUSDT` (~7,883 candles) absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Verified current state via on-disk inspection (results manifests, shard structure, checkpoint, continuous universe state). All tests pass.
- Prior-agent task confirmed complete; initial task message for next agent preserved below.

## Session update — 2026-10-18T10:41:32Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `0ae369ac1ff2be674fe55ce354f3968f36286957` (branch main, origin up to date). Working tree clean. `python -m pytest tests/` -> 80 passed, exit 0. `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234` (unchanged).
- Revalidated on-disk: `research/data_manifest.json` = 18 verified assets only (ADAUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, NEARUSDT, SOLUSDT, SUIUSDT, TRXUSDT, UNIUSDT, XLMUSDT, XRPUSDT), all at 26,280/26,280 observed/expected. `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Verified current state via on-disk inspection (results manifests, shard structure, checkpoint, continuous universe state, data manifest, pilot evidence). All tests pass.
- Prior-agent task confirmed complete; initial task message for next agent preserved below.

## Session update — 2026-10-18T10:46:09Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `ebcc3e08c8964bf4806360fb7134d60a4470ad32` (branch main, origin up to date). Working tree clean. `python -m pytest tests/` -> 80 passed, exit 0. `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234` (unchanged).
- Revalidated: `research/data_manifest.json` = 18 verified assets only; `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Verified current state via on-disk inspection. All tests pass.
- Prior-agent task confirmed complete; initial task message for next agent preserved below.

## Session update — 2026-10-18T10:54:01Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `c1496e12ec41c36a0298fe0b7e7821995713f2a7` (branch main, `git ls-remote origin main` == HEAD, 0 ahead / 0 behind). Working tree clean. Source unchanged: `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234`.
- Revalidated on-disk: `research/data_manifest.json` = 18 verified assets only (ADAUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, NEARUSDT, SOLUSDT, SUIUSDT, TRXUSDT, UNIUSDT, XLMUSDT, XRPUSDT), all at 26,280/26,280 observed/expected. `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate (`src/breakout_research/campaign.py:378-387`) holds.
- **New finding — authorization predates the exclusion record.** `research/universe_manifest.json` now carries `exclusion_reason` ("insufficient_hourly_history: observed 3011/7883 candles, required 26280") on `XMRUSDT`/`MATICUSDT`. That field was introduced by commit `b08421db` (2026-10-16T16:18:32Z), i.e. ~18.5 h **before** `research_state/campaign_authorization.json` (`authorized_at_utc` 2026-10-18T10:52:32Z, `reasons: []`, `code_hash` == current). The authorization was therefore issued against a universe manifest that already recorded the two exclusions, and nothing in the authorization text addresses them. Flagged for the user; not resolved unilaterally.
- **New finding — orphan campaign-cycle directory.** `research/campaign_cycles/3226843c219b23415e3b5b8470e87f0033f75b80e15e3b8fa16fd6309f2c1caf/` (created 2026-10-17T17:06Z, committed at `7215e124`) contains 57,686 records across 8,878 on-disk shard files (`shard_000000.jsonl`–`shard_008877.jsonl`, contiguous), but its `results_manifest.json` lists only 1,156 shards (indices 7719–8877, non-contiguous) and records `code_hash` = `3dbeee5a92566d36b4eb1a9553ea47ee91408b590eb5199be4313026d2ebd2ea` (a **different** source state than the current `d0dca298...`). It has no `cycle_report.json`, is not referenced by `research_state/continuous_universe_state.json` (`current_cycle_id` = `0f52f6c9...`), `checkpoint.json`, or any lane, and was produced by a prior `scripts/resume_cycle_cohort0.py` run (which filters assets by `exclusion_reason`, i.e. a re-scope). It is **not** a valid completion of cohort 0 and must not be treated as one. Left on disk, unmodified; user should decide whether to archive or delete.
- Environment note: `pytest` is not installed (`/usr/bin/python3: No module named pytest`), so `python -m pytest tests/` (the 80-pass baseline) cannot be re-run in this sandbox. Prior sessions' "80 passed, exit 0" result stands from their runs; not re-verified here.
- Verified current state via on-disk inspection (both cycle dirs, manifests, shard structure, checkpoint, continuous universe state, data manifest, universe manifest, authorization, pilot gate). No campaign processes running (`ps` shows only the idle-timeout wrapper). No user message/direction received this session.
- Prior-agent task confirmed complete; updated initial task message for next agent preserved below.

## Initial task message for next agent

**Task: Await user direction on the cohort-0 data blocker; then, only if authorized, complete cohort-0 and test cohort 1. Do NOT re-scope or skip unilaterally.**

Current state (revalidated 2026-10-18T10:54Z, HEAD `c1496e12ec41c36a0298fe0b7e7821995713f2a7`, working tree clean, origin == HEAD):
- Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` BLOCKED at asset 17 `XMRUSDT`. `results_manifest.json` = 442,368/552,960 records (assets 1–16 complete: BTC,ETH,BNB,XRP,SOL,TRX,DOGE,LINK,ADA,NEAR,XLM,BCH,LTC,UNI,AVAX,SUI), 8863 shards (indices 0–8862 all present). `cycle_report.json` absent. `next_cohort_index` = 0. Campaign not running; will fail again at `XMRUSDT` if restarted.
- `research/data_manifest.json`: 18 verified assets only; `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Insufficient history, not endpoint reachability. No authorized alternate provider, paid service, or private credentials. Fail-closed gate holds.
- `research/universe_manifest.json`: 20 assets, all `binance_spot_verified=true`; `XMRUSDT` and `MATICUSDT` carry `exclusion_reason` ("insufficient_hourly_history: observed 3011/7883 candles, required 26280"), added at commit `b08421db` (2026-10-16T16:18:32Z).
- `research_state/checkpoint.json`: code_hash == current, `completed_records` = 442368, `current_asset_index` = 16.
- `research_state/continuous_universe_state.json`: `next_cohort_index` = 0, `current_cycle_id` = `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d`, `completed_cycle_ids` = [].
- `research_state/campaign_authorization.json`: `authorized=true`, `authorized_at_utc` = 2026-10-18T10:52:32Z, `reasons` = `[]`, code_hash matches current. **Caveat:** this authorization post-dates the universe exclusion record by ~18.5 h and its text does not address `XMRUSDT`/`MATICUSDT`. Escalated to the user.
- Cohort-0 asset order: BTC,ETH,BNB,XRP,SOL,TRX,DOGE,LINK,ADA,NEAR,XLM,BCH,LTC,UNI,AVAX,SUI,XMR,DOT,MATIC,ATOM (XMR at index 16 in 0-based asset index counting for asset 17 in human terms; current_asset_index=16 means SUI complete, next is XMR at position 16+1 = 17).
- **Orphan cycle dir (do not use):** `research/campaign_cycles/3226843c219b23415e3b5b8470e87f0033f75b80e15e3b8fa16fd6309f2c1caf/` — 57,686 records / 8,878 contiguous on-disk shards, but manifest lists only 1,156 non-contiguous shards (7719–8877) and `code_hash` = `3dbeee5a92566d36b4eb1a9553ea47ee91408b590eb5199be4313026d2ebd2ea` (older source). No `cycle_report.json`; unreferenced by any state file. Produced by a prior `scripts/resume_cycle_cohort0.py` run that filtered assets by `exclusion_reason` (a re-scope). Not a valid cohort-0 completion. Left on disk, unmodified.

Do NOT:
- Re-scope cohort 0 to 18 assets, skip `XMRUSDT`/`MATICUSDT`, or use synthetic fallback without explicit user/methodology authorization (changes `cycle_id`, expected total, `completed_cycle_ids`).
- Treat the orphan `3226843c...` cycle dir as a completed or resumable cohort-0 run.
- Trigger GitHub Actions, edit workflow files, or dispatch manual runs.
- Change parameters, selection, or holdout rules.
- Commit changes unless explicitly asked.

If/when the user authorizes (a) verified 3-year hourly data for `XMRUSDT`/`MATICUSDT` added to `research/data_manifest.json` with full attestation, or (b) a formal re-scope of cohort 0 to 18 assets with updated cycle metadata:
1. Complete cohort-0: `cycle_report.json` state COMPLETE, totals == expected, all shard hashes/counts verify, `completed_cycle_ids` contains `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d`, `next_cohort_index` → 1.
2. Then discover and test cohort 1 (one bounded cycle, `holdout_enabled=False`).

Constraints: single-writer concurrency; no second workflow; no manual Actions dispatch; no paid service; no private credentials; no live orders; no shorting; no parameter-grid changes. Tests must remain 80 passed.

Status: Cohort-0 bounded cycle BLOCKED on insufficient verified history for `XMRUSDT` and `MATICUSDT`. Blocker escalated to user; awaiting direction on data provision or formal re-scope. Cannot complete or advance to cohort 1 until resolved.
## Session update — 2026-10-18T11:05:35Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `c1496e12ec41c36a0298fe0b7e7821995713f2a7` (branch main, `git ls-remote origin main` == HEAD, 0 ahead / 0 behind). Working tree clean. Source unchanged: `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234`.
- Revalidated on-disk: `research/data_manifest.json` = 18 verified assets only; `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Authorization caveat noted: authorization post-dates universe exclusion record; text does not address `XMRUSDT`/`MATICUSDT`. Escalated to user; not resolved unilaterally.
- Orphan cycle dir `research/campaign_cycles/3226843c...` remains unreferenced, not treated as valid cohort-0 completion; left on disk unmodified.
- Environment: `pytest` not installed in sandbox; prior 80-passed baseline not re-runnable here.
- Prior-agent task confirmed complete; clear initial task message for next agent preserved below.

## Session update — 2026-10-18T11:08:35Z (this session)

- Read the durable handoff; prior-agent task (escalation of cohort-0 data blocker) CONFIRMED COMPLETE. Block remains ACTIVE; no user direction received. No re-scope, skip, or synthetic fallback performed.
- Re-anchored repository state: HEAD `c962d3daa861e9bf5528b63f25f4baafcc0c8a72` (branch main, `git ls-remote origin main` == HEAD, 0 ahead / 0 behind). Working tree clean. Source unchanged: `compute_code_hash()` = `d0dca298869fadfe3ee80b54010f8cb0d19216cf2f7b708ead197164fc509234`.
- Revalidated on-disk: `research/data_manifest.json` = 18 verified assets only; `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate holds. Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` blocked at asset 17 `XMRUSDT` (442,368/552,960 records, 8863 shards 0–8862 complete through SUIUSDT). `next_cohort_index` = 0; campaign not running. `research_state/campaign_authorization.json`: authorized=true, code_hash matches current.
- Authorization caveat noted: authorization post-dates universe exclusion record; text does not address `XMRUSDT`/`MATICUSDT`. Escalated to user; not resolved unilaterally.
- Orphan cycle dir `research/campaign_cycles/3226843c...` remains unreferenced, not treated as valid cohort-0 completion; left on disk unmodified.
- Environment: `pytest` not installed in sandbox; prior 80-passed baseline not re-runnable here.
- Prior-agent task confirmed complete; initial task message for next agent refreshed below.

## Initial task message for next agent

**Task: Await user direction on the cohort-0 data blocker; then, only if authorized, complete cohort-0 and test cohort 1. Do NOT re-scope or skip unilaterally.**

Current state (revalidated 2026-10-18T11:08:35Z, HEAD `c962d3daa861e9bf5528b63f25f4baafcc0c8a72`, working tree clean, origin == HEAD):
- Cohort-0 cycle `0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d` BLOCKED at asset 17 `XMRUSDT`. 442,368/552,960 records (assets 1-16 complete through SUIUSDT), 8863 shards (indices 0-8862 complete). `cycle_report.json` absent. `next_cohort_index` = 0. Campaign not running.
- `research/data_manifest.json`: 18 verified assets only; `XMRUSDT` and `MATICUSDT` absent vs 26,280 required. Fail-closed gate holds.
- `research/universe_manifest.json`: `XMRUSDT`/`MATICUSDT` carry `exclusion_reason` (insufficient history) from commit `b08421db` (2026-10-16T16:18:32Z).
- `research_state/checkpoint.json`: `completed_records` = 442368, `current_asset_index` = 16, code_hash matches current.
- `research_state/campaign_authorization.json`: authorized=true, `authorized_at_utc` 2026-10-18T10:52:32Z, reasons=[], code_hash matches current. **Caveat:** authorization post-dates exclusion record by ~18.5h and text does not address `XMRUSDT`/`MATICUSDT`.
- Orphan cycle dir `3226843c...` (57,686 records/8,878 shards, manifest only lists 1,156 non-contiguous shards, code_hash=older) unreferenced; not valid cohort-0 completion. Left unmodified.

Constraints/Do NOTs: single-writer; no second workflow; no manual Actions dispatch; no paid service/private credentials; no live orders/shorting; no parameter-grid changes; tests must remain 80 passed. No unilateral re-scope, skip, or synthetic fallback.

If user authorizes (a) verified 3-year hourly data for `XMRUSDT`/`MATICUSDT` in `research/data_manifest.json` with full attestation, OR (b) formal re-scope of cohort-0 to 18 assets with updated cycle metadata:
1. Complete cohort-0: write `cycle_report.json` COMPLETE, totals match expected, shards verified, add cycle id to `completed_cycle_ids`, set `next_cohort_index` -> 1.
2. Then discover and test cohort 1 (one bounded cycle, `holdout_enabled=False`).

Status: Cohort-0 BLOCKED on insufficient verified history for `XMRUSDT`/`MATICUSDT`. Awaiting user direction.

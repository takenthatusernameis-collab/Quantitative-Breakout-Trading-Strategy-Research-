# Agent Handoff — Revalidate Before Acting

**Snapshot time:** 2026-10-16 (UTC; see linked run records for exact timestamps)  
**Purpose:** transfer prior work and failure knowledge so the next session does not rediscover problems. This is a historical snapshot, not a claim that every issue remains unresolved. Recheck the current default-branch commit and latest Actions state before relying on any item.

## Current known repository state at last inspection

- Default branch: `main`.
- Latest commit before the README prompt update: `47c2584309527961b5528ceb563fa5b4771db66f` (`chore(kilo): checkpoint agent session`).
- The README prompt was subsequently updated in commit `d067aedc263cffe7326a54ec0195ede032855beb`; verify the live `main` SHA again.
- Workflow #4 (`38834456753`) still appeared `in_progress`, and workflow #5 (`38858495476`) appeared `pending` on the last check. These statuses may have changed; refresh them.
- No economic conclusion about the breakout strategy is supported by this handoff.

## Prior failures and risks that must be revalidated

### P0 — Campaign data may be synthetic rather than historical
**Evidence:** `research/data_manifest.json` recorded BTCUSDT and ETHUSDT with 3,000 hourly candles each, `fallback_used: true`, and `fallback_source: synthetic`. The configured primary campaign requires at least 26,280 candles (three years). In `src/breakout_research/data/fetcher.py`, the inspected `load_or_fetch_asset_data()` implementation directly generated synthetic candles rather than invoking the historical Binance downloader.  
**Implication:** do not treat existing records as a valid market-history backtest. Do not authorize a campaign until genuine source data, history coverage, timestamps, gaps and hashes have been validated. Synthetic candles may be used only in explicitly isolated unit-test fixtures.  
**Next acceptance test:** prove a successful public-data download path and fail-closed behavior on download failure; assert that campaign mode rejects synthetic data and insufficient candle count.

### P0 — Pilot gate could authorize work without proving its prerequisites
**Evidence:** `research_state/pilot_gate.json` said `pilot_passed: true` and `campaign_authorized: true` after 24 configurations. The inspected `src/breakout_research/pilot.py` assigned those booleans directly, and its pilot called the same data-loading path noted above.  
**Implication:** gate state is not trustworthy merely because the JSON says PASS. Recompute validity from actual tests, genuine data, matching code/spec/data hashes, checkpoint restoration, pilot record counts and verified persistence.  
**Next acceptance test:** invalid/missing data, stale hashes, failed tests or failed restore must prevent campaign authorization.

### P0 — Large result-file pushes repeatedly failed
**Evidence:** [workflow run #2](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38801198121) logs reported `research/results.jsonl` at approximately 429.90 MB, above GitHub's 100 MB individual-file limit. The controller retried many times and ultimately stopped with an explicit persistence error. The current remote file observed in the prior inspection was approximately 51.7 MB; the 429.9 MB size was the rejected attempted update, not a verified current remote size.  
**Implication:** treat this as a permanent failure mode, not a transient push/network error. Do not repeat an unchanged push.  
**Next acceptance test:** redesign ledger storage as bounded, deterministic, integrity-checked shards (or another repository-compatible format), make sure the new commit/history does not reintroduce an oversized blob, and verify a remote checkpoint/restore cycle end to end.

### P1 — Checkpoint counters and ledger verification may disagree
**Evidence:** `research_state/checkpoint.json` reported `completed_records: 81510` but `last_verified_record: 0`. In the inspected `src/breakout_research/campaign.py`, experiment results were appended to the ledger and checkpointed periodically; resume state was not reconciled against stable result IDs before trusting the counters. The same implementation reset the per-asset configuration cursor during entry to an asset.  
**Implication:** saved counters alone do not demonstrate recoverable progress. Inspect current code and ledger first; preserve old records and do not claim records are verified until their contents are reconciled.  
**Next acceptance test:** interrupt/resume tests across config/fold/cost boundaries must prove no missing or duplicate stable experiment IDs and an exact checkpoint-to-ledger reconciliation.

### P1 — The holdout-protection implementation needs an audit
**Evidence:** the inspected campaign loop evaluated configurations across five folds, including the final holdout, rather than demonstrating that only validation-selected, frozen candidates reach holdout evaluation.  
**Implication:** do not use holdout-derived metrics to rank or modify candidates. Confirm the actual current code and add tests proving that selection completes and candidate IDs/parameters/hashes are frozen before the final holdout is read. If prior holdout metrics have already been used for selection, label that holdout consumed and require a new untouched confirmatory period.

### P1 — Agent startup did not explicitly load a durable handoff
**Evidence:** the inspected `.github/workflows/main.yml` used the generic Kilo task text: `Execute the task assigned by the previous agent and prepare a task for the next agent!`.  
**Implication:** repository state and saved artifacts were not explicitly named as mandatory session inputs in the startup message. The README now defines the required session protocol; verify whether workflow startup has been updated to invoke it.  
**Next acceptance test:** a fresh session's task/log must show that it read the README session contract, this handoff, prompt-evolution history, latest branch/run state and relevant failure artifacts before selecting work.

## Prior workflow evidence

- [Run #1](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38775084686): failed.
- [Run #2](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38801198121): failed; oversized result-file persistence issue is explicit in logs.
- [Run #3](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38821712668): cancelled.
- [Run #4](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38834456753): appeared in progress at last inspection; refresh.
- [Run #5](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38858495476): appeared pending at last inspection; refresh.

## Required next actions

1. Refresh `main`, Actions runs, the latest commit, current checkpoint, pilot gate and data manifest. Reclassify every item above as confirmed, stale, resolved-with-evidence, or disproven.
2. Do not launch or continue the full campaign while genuine data and valid pilot authorization remain unproven.
3. Fix and test the top-priority validity blocker, then repair bounded result persistence and deterministic resume.
4. Audit candidate/holdout separation before any candidate selection or economic conclusion.
5. Update this handoff with actual evidence and one next task. If the attempted fix fails, preserve the failure and state what new evidence justifies the next approach.
6. Update `research_state/prompt_evolution.md` only if the session demonstrates a prompt-level gap; never revise the frozen research specification to make a gate pass.

**Truthfulness rule:** this handoff documents evidence observed at a past commit/run. It does not prove that code/tests/fixes were executed or that the current remote state is unchanged.

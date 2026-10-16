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
3. Before implementation, route structural/P0 blockers through `research_state/brainstorming_queue.md`; compare materially different interventions, acceptance tests, rollback and external prerequisites first. Do not implement a blocker in the same session that creates its brainstorming decision record.
4. Audit candidate/holdout separation before any candidate selection or economic conclusion.
5. Update this handoff with actual evidence and one next task. If the attempted fix fails, preserve the failure and state what new evidence justifies the next approach.
6. Update `research_state/prompt_evolution.md` only if the session demonstrates a prompt-level gap; never revise the frozen research specification to make a gate pass.

**Truthfulness rule:** this handoff documents evidence observed at a past commit/run. It does not prove that code/tests/fixes were executed or that the current remote state is unchanged.


## Current directive — brainstorming gate for structural blockers (2026-10-16 UTC)

The live source audit found several issues that should not go straight into another incremental Kilo patch loop. The durable queue is now `research_state/brainstorming_queue.md`; its statuses are design workflow states, not a second diagnostics log. The sole run-level error ledger remains `research_state/workflow_run_diagnostics.jsonl`.

- **P0 / BRAIN-001 — Data provenance:** `src/breakout_research/data/fetcher.py` directly generates synthetic candles in `load_or_fetch_asset_data()`; the data manifest marks BTCUSDT and ETHUSDT as synthetic fallbacks. Real historical market data is not verified.
- **P0 / BRAIN-002 — Pilot gate:** `src/breakout_research/pilot.py` unconditionally emits positive pilot and campaign-authorization booleans; the campaign trusts that boolean plus hashes, which cannot establish real data or successful prerequisite checks.
- **P0 / BRAIN-003 — Holdout separation:** `src/breakout_research/campaign.py` loops all configs through every fold, including the final holdout; the `is_holdout` flag does not gate access. Revalidate which old results were exposed and do not call the same period untouched without evidence.
- **P0 / BRAIN-004 — Resume integrity:** campaign startup resets the loaded configuration/fold/cost cursor to zero for the current asset. Checkpoint counters also show `completed_records: 81510` but `last_verified_record: 0`; actual duplicates/losses still need reconciliation.
- **P1 / BRAIN-005 — Result persistence:** the current result file is about 51.7 MB in the repository tree; a historical run reported a rejected ~429.9 MB attempted file. The next design must bound file/blob sizes and make shards/checkpoints recoverable.

These are **direct code/state findings**, not claims from automated diagnostics. At review time the workflow diagnostics JSONL was empty, and no end-to-end success of the new recorder was established. All five entries remain `BRAINSTORMING_REQUIRED`; none is claimed resolved.

**Next-session protocol:** choose one highest-priority queue entry, revalidate its evidence, compare at least two materially different interventions (three where useful), and document recommendation, risks, tests, rollback, and external dependencies. Do not implement that same root cause during the session that creates its design record. A later session can proceed once the item is `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`; if an unavailable authorization/provider/human action blocks it, mark `WAITING_EXTERNAL_INTERVENTION`.

The brainstorming protocol is recorded in README Section 2A, and the Kilo startup command now reads the queue and enforces this gate. Keep the frozen research protocol intact; a methodology change requires a separately versioned, preregistered specification.


## Persistence-stall correction (2026-10-16 UTC)

**Trigger:** observed workflow warning `Push failed on persistence attempt 231; refetching and reconciling.` The live source had `persist_checkpoint()` looping `while true` until the global cutoff, so a persistent push/reconciliation failure could monopolize the run and prevent the pending scheduled activation from starting.

**Change committed:** the single `.github/workflows/main.yml` now limits each checkpoint's Git persistence operation to six reconciliation attempts, with per-command timeouts on fetch (20s), rebase (30s), push (30s), and remote-SHA verification (10s). Retry backoff is capped at 30 seconds. The six-attempt limit is local to a single checkpoint and the activation-wide counter remains a metric. A merge/rebase conflict ends the checkpoint attempt immediately; other persistence failures end after the bounded retries. On a persistence-only failure, `stage_and_checkpoint()` saves the available Git bundle/patch/status artifacts and returns a distinct failure kind; the controller ends that Kilo worker session but does **not** set the fatal-run flag. It records the failed session and local HEAD in controller variables, passes a recovery directive to the next worker, continues the same sequential agent loop, and retries even an older local-ahead commit if the next worker made no new changes. Non-persistence staging/validation failures retain the stricter terminal path. A successful local commit is never described as a successful remote checkpoint without SHA verification.

**Expected maximum wait:** ordinary push/fetch failures now have a finite per-command timeout and bounded retry/backoff budget rather than retrying until the six-hour cutoff. Worst-case wall-clock depends on which commands time out and whether rebase is needed; no end-to-end timing measurement has been run yet.

**Validation status:** remote `main.yml` SHA was re-fetched after the changes. The edited `persist_checkpoint()` function passed `bash -n`; a controlled mock push-failure test returned failure after exactly six push attempts with zero verified checkpoints, and a controlled mock success verified the remote SHA on attempt one. These are bounded-function tests, not a full GitHub Actions end-to-end run or full-workflow YAML validation. Current in-progress/pending Actions runs have the older `head_sha` `47c2584309527961b5528ceb563fa5b4771db66f`; changes to a committed workflow cannot alter code already running or necessarily change a queued run's workflow revision. The new behavior applies to a run that actually loads the updated `main.yml`. If immediate release of the concurrency slot is needed, cancel the old active run and any older pending run from the Actions UI, preserving recovery artifacts where possible; let a fresh scheduled activation load the updated default-branch workflow. On the next run, inspect the prior failure logs/artifact and diagnostic ledger, identify the actual push rejection cause, and route a repeated/permanent cause to `research_state/brainstorming_queue.md` rather than restoring an unlimited retry loop.


**Follow-up hardening — diagnostics-ledger push path:** the preliminary diagnostics-ledger commit step now also caps itself at six attempts and wraps fetch/rebase/push/remote-SHA lookup in per-command timeouts (10s/15s/20s/8s). That step uses `continue-on-error: true`; exhaustion or a reconciliation error therefore must not prevent the Kilo worker step from starting. A controlled shell mock passed `bash -n`, the persistent-push mock produced exactly six failed attempts then exited nonzero, and the success mock passed after remote SHA verification on attempt one. These tests exercise the copied shell block, not an actual GitHub Actions run or full workflow YAML parse.


**Retest after hard-kill timeouts (2026-10-16 UTC):** fetched the current workflow after adding GNU `timeout --kill-after` to each Git network operation. The Kilo checkpoint snippet and diagnostics-ledger retry loop both passed `bash -n`; mocked persistent-push failures stopped after six push calls, and mocked SHA-verified success completed on attempt one. These remain isolated shell-block tests, not a full workflow parse or live push test. The latest observed Actions API snapshot still showed run #4 (`38834456753`) in progress and run #5 (`38858495476`) pending on old head SHA `47c2584309527961b5528ceb563fa5b4771db66f`. The available GitHub tools here can inspect/update repository contents but cannot cancel that active run; do not claim this already-running job has adopted the new bounded loop.


**Session-only continuation correction (2026-10-16 UTC):** workflow code now distinguishes persistence failure from staging/validation failure via `checkpoint_failure_kind`. When bounded push/reconciliation fails, the current Kilo session ends, unpushed commits remain on local `HEAD`, recovery artifacts are saved, and the controller continues to the next worker iteration in the same Actions run. The next Kilo prompt is augmented in memory with the previous failed-session number, local HEAD, last remote-tracking SHA, and explicit instructions to preserve work; history rewriting is allowed only when a confirmed root cause requires it and a recovery bundle plus rollback plan are preserved. `stage_and_checkpoint()` now compares local `HEAD` with `origin/$DEFAULT_BRANCH` and retries persistence even if the fresh worker produced no additional diff; meaningful work from a prior unpersisted commit is counted as progress only after a remote-SHA-verified push.

The six-attempt persistence budget, hard per-command timeouts, single workflow file, single durable run-diagnostics ledger, and recovery-artifact step remain. The controller still ends when its configured session budget/global cutoff is exhausted, and non-persistence checkpoint validation failures remain terminal. This is a static source change; no full GitHub Actions execution of the new same-run continuation branch has yet been observed.


**Same-run continuation smoke test (2026-10-16 UTC):** a local Bash smoke test passed for the controller branch logic: simulated session 1 hit persistence failure, the outer loop continued instead of terminating, session 2 received the recovery context, and pending state cleared only after simulated verification. `bash -n` passed for that smoke-test harness. This validates the intended branch behavior in isolation; it does not substitute for parsing the complete embedded workflow script or observing a live Actions run. Latest source still needs a fresh-run end-to-end verification.

# Authoritative Current Status — 2026-10-16 UTC

**This block is the single source of current task/status truth.** Older snapshots and continuation notes below are historical records unless explicitly revalidated in a later dated section. Do not infer that an old statement is current merely because it appears earlier in the file.

## Verified default-branch snapshot

- Repository: `takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-`.
- Latest verified `main` commit during this inspection: [`f9e841115fda0d7d992cb106a3e0b877474fc696`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/commit/f9e841115fda0d7d992cb106a3e0b877474fc696), recorded at 2026-10-16 09:20:19 UTC. Re-fetch `main` before acting; this is an inspection timestamp, not a guarantee it remains HEAD.
- The live brainstorming queue records BRAIN-002 through BRAIN-005 as `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. Design-ready means the design is documented; it does not mean implemented, tested, or resolved.
- Exactly one workflow file was observed: `.github/workflows/main.yml` (blob `c4d85d7efabacf6382eae9b171bc9d791ad46fa1` at the inspection snapshot). Do not add another workflow as a shortcut.
- A live GitHub Actions API query during this inspection returned run #4 (`38834456753`) as `in_progress` and run #5 (`38858495476`) as `pending`; both are scheduled runs whose `head_sha` is the older `47c2584309527961b5528ceb563fa5b4771db66f`, not the latest verified `main` snapshot above. These runs therefore do not establish that the newer BRAIN-001 implementation or this handoff update was tested. Re-fetch status before acting. The connected tool can inspect run status and jobs but does not expose workflow dispatch or cancellation here.

## Current blocker ledger

| ID | Current status | Evidence still required |
|---|---|---|
| BRAIN-001 — real market data | `IMPLEMENTATION_IN_PROGRESS` | The live source no longer calls the synthetic generator in the campaign-facing loader, and 13 regression tests exist in `tests/test_data_fetcher.py`. The 13 tests are **NOT_RUN** in the recorded evidence. No successful live Binance canary or independently recomputed remotely persisted dataset/manifest hashes have been demonstrated. |
| BRAIN-002 — independent pilot authorization | `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` | Pilot evidence-only behavior, independent deterministic validator, forged/stale/missing-evidence negative tests, and campaign-time revalidation. Not implemented. |
| BRAIN-003 — final-holdout isolation | `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` | Validation-only grid, frozen hash-bound candidate manifest, isolated holdout evaluator, and historical exposure audit. Existing holdout remains `EXPOSED_OR_UNKNOWN` until non-use is established. Not implemented. |
| BRAIN-004 — deterministic resume | `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` | Stable experiment IDs, transaction/shard recovery, crash-injection tests, and derived resume cursor based on independently verified records. Not implemented. |
| BRAIN-005 — bounded durable results | `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` | Immutable JSONL shards with a hard 4 MiB serialized-byte ceiling, verified manifest, legacy-ledger audit/migration, clean-clone reconstruction, and reachable-history blob scan. Not implemented. |

## Next principal task: BRAIN-001 acceptance only

Do not begin the large campaign. Do not implement BRAIN-002 through BRAIN-005 in the same session that is tasked with qualifying BRAIN-001.

1. Re-fetch current `main`, the research specification, fetcher, campaign/pilot callers, the 13 focused tests, and the diagnostics ledger. Reconfirm that the intended code and specification are the ones being tested.
2. Run Python compilation, all 13 tests in `tests/test_data_fetcher.py`, then the full existing test suite; record the exact commands, exit statuses, and failure output. Test files existing or a green unrelated workflow are not test passes.
3. In a network-enabled runner, exercise one bounded BTCUSDT hourly canary through the same production loader/provider path. Enforce the frozen three-year history floor, closed-candle handling, pagination, strict timestamps/OHLCV/gap checks, no synthetic fallback, and atomic fail-closed manifest persistence. Do not reduce the history requirement to make the canary pass.
4. Re-read the remotely persisted data and manifest and independently recompute the documented canonical dataset SHA-256 and manifest/source/coverage correspondence. Preserve artifacts and exact failures if any step fails.
5. Only mark BRAIN-001 `RESOLVED_VERIFIED` if every required test and live/persistence check actually passes. If network/provider access is unavailable, record `WAITING_EXTERNAL_INTERVENTION` for the blocked live-canary step (with exact evidence) while retaining any distinct implementation/test failures; never report the canary as passed.
6. Keep campaign authorization blocked. After BRAIN-001 is genuinely qualified, implement BRAIN-004 and BRAIN-005 together as one transaction/shard architecture, then BRAIN-003, then BRAIN-002 against independently verified evidence. If dependency evidence justifies a different ordering, document that rationale before changing the order.

## Non-negotiable research-validity rules

- No full campaign while applicable P0 gates remain unresolved.
- Existing synthetic-derived records remain forensic/legacy-unverified evidence; do not relabel them as observed market history or use them to make economic claims.
- No claim of an untouched holdout unless historical non-use is established; otherwise use `EXPOSED_OR_UNKNOWN` and preregister a new confirmatory period if needed.
- A local commit, a successful worker exit, committed tests, or GitHub workflow success alone is not proof of correctness, remote persistence, or a trading edge.
- Preserve the single-workflow design, frozen protocol, previous results, and rollback evidence. Never force-push solely to erase oversized historical blobs.

---

## Historical handoff snapshots and prior evidence

The entries that follow preserve prior diagnoses, implementation notes, and failure records. Their timestamped statements are useful evidence of what was observed then, but the top status block governs current task selection. Where a later dated entry conflicts with an earlier snapshot, use the later entry only after independently re-fetching its supporting source/evidence.


**Snapshot time:** 2026-10-16 (UTC; see linked run records for exact timestamps)  
**Purpose:** transfer prior work and failure knowledge so the next session does not rediscover problems. This is a historical snapshot, not a claim that every issue remains unresolved. Recheck the current default-branch commit and latest Actions state before relying on any item.

## Historical repository state snapshot (superseded by the authoritative status above)

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


## Historical directive — initial brainstorming gate (superseded by structured design decisions below) (2026-10-16 UTC)

The live source audit found several issues that should not go straight into another incremental Kilo patch loop. The durable queue is now `research_state/brainstorming_queue.md`; its statuses are design workflow states, not a second diagnostics log. The sole run-level error ledger remains `research_state/workflow_run_diagnostics.jsonl`.

- **P0 / BRAIN-001 — Data provenance:** `src/breakout_research/data/fetcher.py` directly generates synthetic candles in `load_or_fetch_asset_data()`; the data manifest marks BTCUSDT and ETHUSDT as synthetic fallbacks. Real historical market data is not verified.
- **P0 / BRAIN-002 — Pilot gate:** `src/breakout_research/pilot.py` unconditionally emits positive pilot and campaign-authorization booleans; the campaign trusts that boolean plus hashes, which cannot establish real data or successful prerequisite checks.
- **P0 / BRAIN-003 — Holdout separation:** `src/breakout_research/campaign.py` loops all configs through every fold, including the final holdout; the `is_holdout` flag does not gate access. Revalidate which old results were exposed and do not call the same period untouched without evidence.
- **P0 / BRAIN-004 — Resume integrity:** campaign startup resets the loaded configuration/fold/cost cursor to zero for the current asset. Checkpoint counters also show `completed_records: 81510` but `last_verified_record: 0`; actual duplicates/losses still need reconciliation.
- **P1 / BRAIN-005 — Result persistence:** the current result file is about 51.7 MB in the repository tree; a historical run reported a rejected ~429.9 MB attempted file. The next design must bound file/blob sizes and make shards/checkpoints recoverable.

These are **direct code/state findings**, not claims from automated diagnostics. At the time of this historical snapshot, the workflow diagnostics JSONL was empty, and no end-to-end success of the new recorder had been established. The then-current status was `BRAINSTORMING_REQUIRED`; this status was superseded by the structured design decisions recorded later in this file and in the current block above.

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


**Pending-state re-verification hardening:** after reviewing the equal-SHA edge case, `stage_and_checkpoint()` now calls `persist_checkpoint()` whenever `pending_persistence_recovery == 1`, even if the local remote-tracking SHA appears equal to `HEAD`. This forces a fresh fetch/push/remote-SHA verification before the controller clears the pending flag; an earlier uncertain push acknowledgement cannot leave the next session in a permanently stale recovery state.


## Structured design decision — BRAIN-001 (2026-10-16 UTC; supersedes older queue status summary)

**Queue:** [research_state/brainstorming_queue.md](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research_state/brainstorming_queue.md). Its BRAIN-001 section now has the full causal analysis, three options, comparison, recommendation, staged implementation plan, acceptance tests, rollback and falsifiers. Latest queue change was committed as `892d41a4725d5c6bb838ee3d6e20a4cee58ec7d5`; re-fetch live main before implementation.

**Live evidence revalidated:**
- `src/breakout_research/data/fetcher.py`, blob `6954e28e94fadfa9b1c49bfa9b147868e609795b`: `load_or_fetch_asset_data()` directly invokes `generate_synthetic_candles()`; it does not call the existing `DataFetcher.fetch_full_history()`. Its manifest-writing call catches and ignores all exceptions.
- `research/data_manifest.json`, blob `5b6a2f336cf0c273a035b92cc1f45a428e54bddf`: BTCUSDT and ETHUSDT are explicitly labeled `fallback_used: true`, `fallback_source: synthetic`, with 3,000 hourly candles from 2023-01-01 to 2023-05-05. The Binance endpoint in nominal source fields does not make these records real market data.
- `src/breakout_research/data/cache.py`, blob `0677448f7a82967c4762c079c651bf727b46b76b`: synthetic generator is test-data code, with process-randomized `hash(symbol)` in its random seed.
- `configs/research_v1.json`, blob `33bf2c7dd6e8faa07f791ce181b5fa7dfba1157f`: frozen protocol says `min_history_years: 3`, hourly data, and a 720-bar warmup. `campaign.py` passes `min_candles=1000`, so the loader's default 26,280-bar check is bypassed.
- Existing `DataFetcher.fetch_full_history()` has follow-up correctness gaps: declared return type does not match its actual tuple, timestamp normalizer floors misaligned times rather than rejecting them, and there's no verified campaign-facing provenance/cache contract. No live Binance request was made during the design review; actual endpoint reachability and full-history pagination remain unverified.

**Recommendation:** option B — establish an explicit campaign data-provider contract, adapt the existing Binance downloader behind it, require validated candles and source provenance, isolate synthetic generation to test fixtures, and fail closed on unavailable/invalid/inadequate data. Do not immediately add a new external vendor. Keep the strategy protocol frozen; never shorten the three-year requirement to make current data pass.

**Implementation acceptance gates:** deterministic multi-page provider tests; an opt-in live BTCUSDT hourly API canary and one-asset end-to-end retrieval; strict hourly timestamp uniqueness/order/alignment, OHLCV validity, data coverage, gap and hash checks; no synthetic fallback on any failure; atomic manifest writes that fail closed; synthetic-source rejection even with forged provider labels; manifest/hash verification from a clean clone and remote default branch. Treat existing synthetic result records as invalid for economic claims but preserve them as forensic evidence. A data-loader fix alone does not authorize a campaign: BRAIN-002 (independent pilot authorization) and BRAIN-003 (holdout separation) remain P0 blockers.

**Status update:** BRAIN-001 is now `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. BRAIN-002 through BRAIN-005 remain `BRAINSTORMING_REQUIRED`. No code implementation or live-network validation was performed in this design session. A future session should revalidate current main, implement option B, test it, and independently verify persisted outputs. If a bounded live canary proves Binance is unavailable or cannot supply required coverage, switch to `WAITING_EXTERNAL_INTERVENTION` and document the exact failure rather than falling back to synthetic data.


## BRAIN-001 implementation attempt — 2026-10-16 UTC (latest update supersedes prior design-only status)

**Commits on `main`:**
- `5c5ffe56d3ee484da43bf3f8c5044f5560be3028` — provider/validation/cache/provenance implementation in `src/breakout_research/data/fetcher.py`.
- `33520ae77dbc18ad2941eacd367245ed3cb11111` — removed the 1,000-candle override from `campaign.py`.
- `c808a41844abec367bd4c59a37097c54efefbd0b` — removed the 1,000-candle override from `pilot.py`.
- `f23d0097834bde9fd872dbdd90686e78577118ad` and `d0c22425b15ec0e3ef545ea4fd140ec838d8a723` — added ten tests in `tests/test_data_fetcher.py`.

**Implemented source behavior:** protocol-derived floor of `ceil(min_history_years × 365 × 24)` hourly records (26,280 under current config) regardless of a lower caller-supplied value; excludes the currently forming hourly candle; bounded pagination in both directions with no-progress/overlap checks; rejects invalid provider rows, duplicate/unordered/misaligned timestamps, non-finite/invalid OHLCV, insufficient history and all unapproved gaps; writes canonical content-addressed CSV snapshots; validates existing real-data caches against per-asset provider/endpoint, specification hash, dataset location, SHA-256, count, first/last timestamps and manifest hash; atomically writes dataset and manifest; never calls a synthetic generator in the campaign-facing loader; and raises explicit failures for provider/manifest problems. Prior synthetic manifest entries are archived under `invalidated_prior_entries` when superseded by a different real snapshot.

**Current source state is remote-persisted, not fully verified.** GitHub API reads confirmed the commits in `main`. The container cannot resolve `github.com` to clone the repository; no local Python compile or pytest execution was possible and no live Binance request was made. The ten tests are committed but unexecuted. BRAIN-001 must stay `IMPLEMENTATION_IN_PROGRESS`, not `RESOLVED_VERIFIED`, until the tests run successfully, a bounded live canary retrieves and validates the required history, and the downloaded dataset/manifest are re-read remotely with hashes independently recomputed.

**Do not launch the full campaign.** BRAIN-002 (self-authorizing pilot gate) and BRAIN-003 (final holdout evaluated across all configurations) are still P0 blockers. BRAIN-004 (resume cursor/ledger reconciliation) and BRAIN-005 (bounded results storage) also remain open. This session did not implement any of those root causes. The single current/pending Actions runs (#4 in progress and #5 pending at last API read) reference old head `47c2584309527961b5528ceb563fa5b4771db66f`, not the new code. The GitHub tool surface available here does not offer workflow dispatch or cancellation; no fresh-run end-to-end validation is claimed.

**Next task:** re-fetch current `main`, run the full test suite including `tests/test_data_fetcher.py` in a network-enabled environment, correct any failures, then run one bounded BTCUSDT hourly API canary and independently verify the remotely persisted dataset/manifest hashes. Keep this task focused on BRAIN-001 acceptance; do not implement BRAIN-002–BRAIN-005 until their required design records exist.


**Follow-up before handoff — cache and campaign fail-closed gates (2026-10-16 UTC):** `src/breakout_research/data/fetcher.py` was tightened in commit `48304cce9457b5c5da6f2c8ae1498493a112be11`: real cache entries must have literal `fallback_used: false`, an empty/absent fallback source, matching top-level and per-asset specification hashes, an approved provider/endpoint and algorithm, clean gap/rejection metadata, valid retrieval timestamp, verified dataset path, recomputed content hash, exact count and exact endpoint timestamps. `campaign.py` commit `fd924b2f49eb3769a12543782a00834a5e938df8` now raises on failure to load any required eligible asset and on missing BTC benchmark history instead of silently skipping assets or running without the requested BTC filter. Test follow-ups `0dbd13c217f18503e928cf3790bd2cdabbf47602` and `60c075b53a94efe0fee5a88c0d7a69ae13758f9c` bring the committed data-provider regression file to **13 tests**, including campaign stop behavior for a missing required asset or BTC benchmark.

These changes strengthen the fail-closed behavior but do not change the verification status: all 13 tests remain `NOT_RUN` in this environment, no Python compile/pytest result is available, and no live Binance canary has been run. BRAIN-001 remains `IMPLEMENTATION_IN_PROGRESS`. Latest queue revision records these follow-ups; re-fetch it before acting. Do not claim test success based on tests existing in the repository.


**Latest test additions (2026-10-16 UTC):** the thirteen tests now also exercise that the campaign raises rather than silently skipping a required eligible asset or continuing without BTC benchmark history. Commit `60c075b53a94efe0fee5a88c0d7a69ae13758f9c` is on `main`; queue revision `e02ee63fabc5ca7a29152f50d81c0b49eca060f6` reflects the count. These are authored regression tests only; they still need execution in a network-enabled environment.


## Structured design decisions — BRAIN-002 through BRAIN-005 (2026-10-16 UTC)

Queue decision file: [research_state/brainstorming_queue.md](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research_state/brainstorming_queue.md). The complete structured comparison, causal model, recommended architecture, falsifiers, staged plans, acceptance tests and rollback are recorded in each entry. Queue update commit: `2efaa66dd99b0f430e5c24a144594dc8fd4c61ad`.

### BRAIN-002 — independent campaign authorization
Live `pilot.py` still sets positive pilot state and writes `campaign_authorized: true` after only one asset, at most 24 configs and baseline costs; it passes no BTC benchmark candles and does not require complete data/test/restore/persistence evidence. Live `campaign.py` trusts that boolean plus spec/code hashes. Current gate authorizes despite synthetic manifest. Design decision: pilot becomes evidence-only; a separate deterministic validator recomputes and hashes current data provenance, history coverage, test exits/reports, restore/integrity report and remote persistence receipt; campaign startup revalidates and ignores legacy booleans. Negative/forged/stale evidence must block. BRAIN-002 is `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`, but the currently committed synthetic gate stays blocked and the design cannot pass until BRAIN-001/003/004 evidence is valid.

### BRAIN-003 — final holdout separation
Live campaign loops every configuration across all folds and does not gate evaluation on `is_holdout`; the inspected source tree lacks a frozen candidate artifact/evaluator boundary. Historical fold-4 rows exist but are based on synthetic data; whether an agent/human used those metrics for decisions is unknown. Design decision: validation-only grid + deterministic selector using existing frozen criteria + canonical frozen candidate manifest bound to hashes + separately invoked holdout evaluator that accepts only frozen candidates and writes separate outputs. Preserve historical rows and mark holdout exposure `EXPOSED_OR_UNKNOWN` until audited. If historical non-use cannot be proven, preregister a new confirmatory period in a separate protocol version before access; do not change v1 thresholds. Status `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`; no phase code was changed.

### BRAIN-004 — deterministic resume
Live campaign resets saved config/fold/cost cursors on asset entry; result appends have no stable experiment IDs; checkpoint loader turns malformed state into `None`; current checkpoint reports 81,510 completed but `last_verified_record: 0`. Design decision: canonical stable experiment IDs bound to spec/code/universe/dataset/config/fold/cost/schema; bounded transactions; write/validate/fsync/atomically promote immutable result shards; update manifest only after hashes/counts verify; derive next-uncompleted cursor from the exact verified ID set; verify remote commit/shards before advancement. Identical duplicates may be idempotent; conflicting identities fail closed. Legacy rows without provenance remain untrusted pending audit. Status `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`; actual duplicate/loss count remains unknown.

### BRAIN-005 — bounded durable results
Live tracked `research/results.jsonl` is 51,688,138 bytes. Run #2 recorded a rejected ~429.90 MB attempted file; it is not the current remote file. Full grid size is 691,200 units and rough linear output is ~438 MB at an estimated ~634 bytes/record; measure actual line/record sizes in the migration environment. Design decision: immutable deterministic JSONL shards under `research/results_shards/<campaign_id>/`, 4 MiB hard serialized-byte ceiling, stable IDs and source hashes per record, compact hash/count/ID manifest, remote re-read after push. Preserve and hash/partition the legacy ledger as `legacy_unverified`; do not force-push history rewrite. Clean-clone reconstruction and reachable-history blob scan are acceptance criteria. Status `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`.

**Execution and status:** one-file workflow architecture remains unchanged; there is still only `.github/workflows/main.yml`. Live Actions run #4 (`38834456753`) remained in progress and run #5 (`38858495476`) pending at last read, both on old head `47c2584309527961b5528ceb563fa5b4771db66f`. The available tool connection can inspect/read and commit repository contents but does not offer workflow dispatch/cancellation. BRAIN-001 remains `IMPLEMENTATION_IN_PROGRESS`: thirteen regression tests are committed but not executed, no local compile/pytest result is available and no live Binance canary was run because the execution container could not resolve GitHub. Do not launch the full campaign. BRAIN-002–BRAIN-005 are design-ready only; no root cause from those entries was implemented in this session.

**Recommended continuation:** obtain a network-enabled clone/runner, run all existing and new tests, correct BRAIN-001 defects and perform a bounded real-data canary first. Then implement BRAIN-004/005 together behind a transaction/shard migration plan; implement BRAIN-003 phase boundaries and candidate freeze; finally implement BRAIN-002 validator against actual evidence. Gate ordering may be adjusted only with an explicit dependency rationale; the campaign stays blocked until all applicable P0 acceptance gates are verified.

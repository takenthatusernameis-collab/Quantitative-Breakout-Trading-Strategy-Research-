# Continuous Market-Cap Candidate-Universe Campaigns

**Status:** User-authorized implementation task, not yet an implemented or backtest-verified feature.  
**Scope:** Research-only; no exchange orders, credentials, leverage, shorting, or live trading.

## Objective

After a candidate-universe campaign finishes, automatically advance to a genuinely new candidate universe and evaluate the same frozen 2,304-configuration breakout grid. Resume safely across worker sessions and hosted-runner cutoffs. Keep every universe, authorization, data manifest, result manifest, and report reproducible and separately auditable.

The current v1 campaign and its reports are historical evidence and must remain immutable. Its holdout exposure is `EXPOSED_OR_UNKNOWN`; do not rerun or treat that old holdout as fresh confirmation. New cycles are discovery/validation cycles only unless a separately preregistered, genuinely future confirmation protocol is approved.

## Frozen research requirements

1. Preserve the exact existing 2,304 strategy configurations, signal timing, costs, validation folds, and minimum-history rule. Do not optimize or add parameters as part of this change.
2. Preserve the existing exclusions, Binance spot USDT market verification, and market-cap ordering/eligibility methodology. Record the exact quote currency, provider endpoint, retrieval time, ranks, cap values, exclusions, and normalized canonical snapshot hash. Do not silently reinterpret market-cap rank as a portfolio-weighting scheme.
3. Require 26,280 validated closed hourly candles per eligible asset, real-source provenance, validated timestamps/OHLCV/gaps, and content hashes. No synthetic fallback, reduced history minimum, silent skips, or paid data. Explicit provider/rate-limit/permission failures must become `BLOCKED_EXTERNAL`.
4. Continue to evaluate all 2,304 configurations for each asset in the active new cohort across the frozen validation folds and cost scenarios. Do not auto-open the final holdout or use a prior exposed/unknown holdout for selection.
5. Use market capitalization to create the candidate order/cohorts under an explicit deterministic rule. Prefer a bounded ranked pool and consecutive cohorts of up to 20 eligible assets so a completed cohort advances to new candidates rather than repeatedly testing the same top assets. Extend provider pagination only within a documented bound. Exclude previously completed asset/data/config/fold/cost units from recomputation only when code, protocol, time bounds, and dataset hashes prove exact identity; link to their verified evidence from the new cycle rather than pretending they were new trials.
6. A timestamp-only refresh is not a genuinely new *constituent universe*. If a fetched snapshot contains no new eligible cohort, record `DUPLICATE_OR_NO_NEW_CANDIDATES`, try the next bounded source page/cohort, and then stop as `BLOCKED_EXTERNAL` or `AWAITING_NEW_CANDIDATES` with evidence. Never loop indefinitely on an unchanged snapshot.

## Required cycle state machine

Implement an idempotent coordinator with durable states equivalent to:

`DISCOVERING -> SNAPSHOT_FROZEN -> DATA_VALIDATED -> PILOT_EVIDENCE_READY -> AUTHORIZED -> RUNNING -> RESULTS_VERIFIED -> COMPLETE`

Any failed gate must persist a specific `BLOCKED_*` status and reason. On restart, reconcile actual artifacts and verified result IDs instead of trusting counters or booleans. A completed cycle must atomically record its result, then enqueue the next untested eligible candidate cohort. If runner time ends, persist the exact next state and let the next normal agent activation resume it; do not add a second workflow, remove the existing schedule, start unbounded background loops, or dispatch Actions as part of implementation.

## Identity, isolation, and persistence

- Give each snapshot/cycle a deterministic ID derived from canonical universe contents and the frozen specification; bind the cycle campaign ID to code hash, protocol hash, universe hash, and data-manifest hash.
- Store immutable snapshots and cycle artifacts under versioned paths such as `research/universe_snapshots/<snapshot_id>/` and `research/campaign_cycles/<cycle_id>/`. Each completed cycle must retain its own result manifest, report, data/provenance manifest, authorization evidence, and asset/config/fold/cost coverage summary.
- Never overwrite v1 `research/universe_manifest.json`, historical final reports, candidate manifests, or previous cycle evidence to make a new run fit the legacy paths. Refactor path/context handling rather than mutating the frozen v1 files in place.
- Revalidate authorization separately for each new cycle against the exact code/spec/universe/data hashes. Existing authorization must fail closed when any bound input changes; do not self-authorize or carry a stale approval forward.
- Every report must state exact snapshot/cohort identifiers, eligible and excluded assets, dataset coverage, expected vs verified result IDs, grid coverage, data/cost assumptions, cumulative number of configurations/cohorts tried, and survivorship/multiple-testing limitations. Separate execution/data/validation status from economic conclusion.

## Required implementation and tests

Implement the runnable coordinator and integrate it with the repository's existing campaign runner; a documentation-only change or a handoff-only change does not satisfy the task. Keep the workflow file unchanged and do not trigger Actions. Run the complete offline test suite locally/in the assigned runner and persist exact command, exit code, and test count.

At minimum add deterministic tests proving:

- advancing from one fully verified cohort to the next;
- no advancement before every expected unit/result and manifest hash is verified;
- interruption/restart at every state without duplicated or omitted units;
- immutable artifacts and distinct identities for distinct universes, while identical snapshots/data are deduplicated;
- per-cycle authorization rejects stale code/spec/universe/data evidence;
- incomplete history, fake/synthetic provenance, malformed/rate-limited provider responses, or endpoint failures fail closed;
- the 2,304 grid and all frozen validation/cost combinations are retained;
- no final-holdout execution or selection occurs in continuous mode;
- a no-new-candidates outcome terminates boundedly and persists an exact reason;
- prior v1 reports, candidate manifest, result shards, and legacy result ledger remain unchanged.

## Completion criteria

The feature is complete only when implementation, tests, persisted artifacts, and restart behavior are verified. Then run **one** bounded new-candidate cycle only after that cycle's gates authorize it; confirm the exact grid coverage and remote artifact persistence, and immediately continue to the next distinct cohort while within the existing worker budget. If a gate or external provider prevents a valid cycle, preserve the blocker and continue only with independent, non-backtest engineering work. Never claim that the continuous campaign is active merely because this specification or code has been committed.

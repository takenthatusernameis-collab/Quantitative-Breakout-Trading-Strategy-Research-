# Brainstorming Queue — Deterministic Intervention Candidates

**Purpose:** route confirmed structural, architectural, permanent-limit, or externally constrained blockers into a deliberate design phase instead of another incremental Kilo patch/retry loop.

**Scope:** this file is a design queue, not a second error log or executable automation. Run-level workflow errors remain recorded only in `research_state/workflow_run_diagnostics.jsonl`. This queue holds the *decision and intervention plan* for selected blockers. Keep the single-workflow design intact.

**Initial review date:** 2026-10-16 UTC  
**Repository branch:** `main`  
**Evidence caveat:** the diagnostic JSONL ledger was empty at review time. Entries below are based on direct inspection of current tracked source/manifests and historical run evidence, not on a claim that the new automatic error recorder has already discovered or end-to-end verified them.

## Brainstorming entry and exit rules

### Enter brainstorming when
- One confirmed deterministic failure or hard boundary has no safe local workaround, including a permanent platform rejection or real permission/external-service boundary.
- A blocker is structural and crosses multiple components (for example, data provenance + pilot authorization + execution).
- Two materially different, evidence-backed repair attempts fail on the same root-cause signature.
- Prompt refinement, more logging, retries, or incremental workflow hardening cannot alter the underlying constraint or has already failed to do so.

Do **not** escalate ordinary, well-localized code/test failures when one bounded fix and a clear acceptance test are already supported by evidence. Do not run unchanged retries against a permanent failure.

### Required brainstorming work
For each open entry, the designated agent must first revalidate the linked evidence against the live default branch. Then produce:
1. A causal model separating observed facts, inferred root cause, unknowns, and downstream risks.
2. At least two materially different intervention designs (three where useful), not merely alternate phrasings of the same patch.
3. A comparison of correctness, research validity, permissions/external dependencies, operational cost, migration/recovery, failure modes, reversibility, and maintenance burden.
4. A recommended design, the evidence that would falsify it, a staged plan, exact acceptance tests, rollback, and any human/external intervention required.
5. A concise decision record here and in `research_state/agent_handoff.md`.

Until that design note exists, **do not attempt another implementation of the same root cause**. Brainstorming is not a permanent parking lot: once a design is supported and acceptance criteria are deterministic, move it to `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`; when a genuine external action or authorization is missing, move it to `WAITING_EXTERNAL_INTERVENTION`. Mark resolved only after tests and remote persistence are independently verified.

### Status vocabulary
- `BRAINSTORMING_REQUIRED`: evidence indicates another ordinary agent patch loop is not the right next action.
- `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`: options compared; a recommendation, staged plan, tests, and rollback are documented.
- `WAITING_EXTERNAL_INTERVENTION`: requires a human decision, credential/permission, provider/service change, or other action unavailable to the agent.
- `IMPLEMENTATION_IN_PROGRESS`: selected design is being implemented, with no claim of success.
- `RESOLVED_VERIFIED`: acceptance evidence and remote state verified.
- `STALE_REVALIDATE`: past evidence needs a live check before action.

---

## BRAIN-001 — Real historical market data path is bypassed

**Priority:** P0 — blocks any economic conclusion  
**Status:** `BRAINSTORMING_REQUIRED`  
**Cause labels:** `IMPLEMENTATION_DEFECT`, `DATA_OR_EXTERNAL_SERVICE`, potentially `PLATFORM_LIMIT`  
**Confidence:** direct source and manifest evidence confirmed; a working genuine-data path is not demonstrated.

### Evidence
- [`load_or_fetch_asset_data()`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/data/fetcher.py) directly calls `generate_synthetic_candles()`; it does not call the existing Binance fetcher.
- [`research/data_manifest.json`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research/data_manifest.json) labels BTCUSDT and ETHUSDT with `fallback_used: true`, `fallback_source: synthetic`, and 3,000 candles, while storing a Binance endpoint as the nominal source.
- The manifest/source mismatch makes these records invalid as market-history evidence even if all backtest calculations are otherwise correct.

### Why this needs a design decision
This is not a prompt or logging problem: the current production loader chooses synthetic test data directly. A more forceful prompt cannot turn generated candles into observed market history. The data contract must make real provenance mandatory and define fail-closed behavior.

### Alternatives to compare
A. Wire the existing paginated Binance `DataFetcher` into the loader, validate coverage/timestamps/gaps, and cache data with provenance and content hashes.  
B. Introduce an explicit data-provider interface with a single campaign-safe historical provider; isolate synthetic generation so it is callable only by test fixtures.  
C. If an external source cannot supply the frozen universe/history, stop and document the exact missing asset/history requirements rather than silently substituting another source or shorter history.

### Required acceptance evidence
- Integration test proves a real network response is parsed into candles and the source/endpoint/time range/hash match the stored manifest.
- Download/API failure produces a clear data-unavailable result and cannot fall back silently.
- Campaign mode rejects synthetic provenance, insufficient history, mismatched hashes, duplicate timestamps, and invalid/gapped data according to the frozen specification.
- Synthetic fixtures remain explicitly test-only.
- A fresh data manifest and source files are remotely persisted and independently re-read.

---

## BRAIN-002 — Pilot gate self-authorizes without proving prerequisites

**Priority:** P0 — blocks trustworthy campaign authorization  
**Status:** `BRAINSTORMING_REQUIRED`  
**Cause labels:** `IMPLEMENTATION_DEFECT`, `TEST_GAP`, `RESEARCH_DESIGN_RISK`  
**Confidence:** direct source evidence confirmed.

### Evidence
- [`pilot.py`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/pilot.py) sets `state.pilot_passed = True`, then emits `pilot_passed: True` and `campaign_authorized: True` after the configured pilot loop without proving real-data provenance, independent fixture checks, resume integrity, or a verified restore.
- [`campaign.py`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/campaign.py) checks the boolean, specification hash, and code hash, but the boolean was produced by the pilot itself. Hash matching alone does not establish valid inputs or correct behavior.
- The checked-in [pilot gate](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research_state/pilot_gate.json) reports authorization despite the synthetic data manifest.

### Why this needs a design decision
The system currently lets the component under evaluation assert its own authorization. The gate needs an independent, deterministic definition of evidence and a clear fail-closed state model. Additional prompt instructions cannot establish missing test results.

### Alternatives to compare
A. Create a deterministic gate validator that recomputes input/code/spec hashes and checks named test reports, real-data provenance, record counts, restore tests, and remote persistence.  
B. Make the pilot emit evidence only; require a separate, non-self-authorizing validation command to produce a gate artifact consumed by campaign startup.  
C. Combine the two designs: pilot emits raw evidence, validator produces a content-addressed authorization record, and campaign revalidates it immediately before execution.

### Required acceptance evidence
- Missing, synthetic, stale, malformed, or mismatched evidence always blocks authorization.
- A deliberately forged `pilot_passed: true` or `campaign_authorized: true` cannot override failed prerequisites.
- Known-good fixtures can pass only when each required condition is actually met.
- Gate validation is deterministic and covered by positive and negative tests; tests' real exit statuses are recorded.

---

## BRAIN-003 — Full-grid loop evaluates the final holdout before candidate freeze

**Priority:** P0 — potentially invalidates final performance claims  
**Status:** `BRAINSTORMING_REQUIRED`  
**Cause labels:** `RESEARCH_DESIGN_RISK`, `IMPLEMENTATION_DEFECT`, `TEST_GAP`  
**Confidence:** direct execution-loop evidence confirmed; downstream result usage and exact historical exposure must be audited.

### Evidence
- [`campaign.py`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/campaign.py) constructs validation folds plus a final holdout, then loops over every configuration and every fold. It receives `is_holdout` from the fold bounds but does not use that flag to prevent full-grid holdout runs.
- The configured [research protocol](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/docs/research_protocol.md) requires candidate selection from validation windows and candidate freezing before holdout access.

### Why this needs a design decision
This is an evaluation architecture problem. A clearer prompt cannot restore the untouched status of a holdout that was already evaluated or used. Simply adding an `if` statement may leave old exposed results and candidate selection paths contaminated.

### Alternatives to compare
A. Separate development/validation and holdout into distinct executable phases; only a frozen candidate manifest can be evaluated by the holdout runner.  
B. Use a separate holdout evaluator or job whose inputs are limited to hashed frozen candidates and whose results are inaccessible to the candidate-selection code until selection is locked.  
C. If the current holdout was inspected or used for selection, explicitly mark it consumed and define a new future confirmatory period before reporting an untouched holdout.

### Required acceptance evidence
- Automated test proves ordinary grid evaluation never invokes the final holdout.
- Candidate IDs, parameters, and hashes are frozen before the holdout evaluator can run.
- Existing run/results evidence is audited for holdout exposure; no prior result is described as untouched unless proven.
- Any contaminated holdout is labeled consumed, with a new confirmatory period preregistered when needed.
- Frozen methodology is changed only through a separately versioned, preregistered protocol—not by changing thresholds to pass.

---

## BRAIN-004 — Resume cursor is reset and checkpoint counts are not reconciled to results

**Priority:** P0 — risks duplicate/lost research units on resume  
**Status:** `BRAINSTORMING_REQUIRED`  
**Cause labels:** `IMPLEMENTATION_DEFECT`, `PERSISTENCE_FAILURE`, `TEST_GAP`  
**Confidence:** direct source/state evidence confirmed; actual duplicate count is not yet reconstructed.

### Evidence
- [`campaign.py`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/campaign.py) loads checkpoint state, but when it enters the current asset it resets `current_config_index`, `current_fold_index`, and `current_cost_index` to zero before the loops use them. The saved mid-asset cursor therefore is not faithfully honored.
- The current [checkpoint](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research_state/checkpoint.json) reports `completed_records: 81510` but `last_verified_record: 0`. Counters alone do not prove that every result is present exactly once.

### Why this needs a design decision
Checkpointing and results have to share a deterministic identity/commit model. Incremental fixes to the loop are not sufficient without defining which durable record is authoritative and how crash boundaries are reconciled.

### Alternatives to compare
A. Treat the append-only result ledger as the source of truth: enumerate deterministic experiment IDs and rebuild the next unit from verified IDs on resume.  
B. Write bounded idempotent shards plus a manifest that records the committed shard hashes and next unit; advance checkpoint only after the shard is durably persisted and verified.  
C. Use a transaction-like batch protocol: write a temporary batch, validate IDs/count/hash, atomically promote it, then advance the checkpoint to that batch's verified boundary.

### Required acceptance evidence
- Simulated interruption at each config/fold/cost boundary resumes without missing or duplicate stable experiment IDs.
- A test deliberately changes checkpoint counters and proves ledger reconciliation detects the mismatch.
- Repeated resume produces byte-identical reconciled state and an explicit integrity report.
- `last_verified_record` means a verified record boundary, not a default or optimistic counter.

---

## BRAIN-005 — Result persistence can exceed Git hosting limits

**Priority:** P1 — campaign completion/persistence risk  
**Status:** `BRAINSTORMING_REQUIRED`  
**Cause labels:** `PLATFORM_LIMIT`, `PERSISTENCE_FAILURE`, `IMPLEMENTATION_DEFECT`  
**Confidence:** current repository size and historical rejection evidence confirmed; future full-campaign size needs a measured estimate.

### Evidence
- The current tracked [`research/results.jsonl`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/research/results.jsonl) is approximately 51.7 MB according to the repository tree API.
- [Workflow run #2](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38801198121) contains a prior failed attempt reporting an approximately 429.90 MB result file and a file-size rejection. That attempted size was not committed as the current file; do not confuse the two.
- [`campaign.py`](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/blob/main/src/breakout_research/campaign.py) appends every result to one monolithic JSONL file.

### Why this needs a design decision
The result volume is driven by the experiment grid. More prompt hardening cannot change the hosting limit, and retrying the same monolithic push cannot fix the underlying shape.

### Alternatives to compare
A. Deterministic bounded JSONL shards, named by stable asset/config/fold/cost ranges, plus a compact manifest containing counts and SHA-256 hashes.  
B. A SQLite or similarly structured local result store exported into bounded deterministic partitions at checkpoint boundaries, keeping the remote artifacts verifiable and reproducible.  
C. External durable storage only if its required access, retention, and free/operational limits are explicitly verified; do not assume an unavailable service or temporary Actions artifact is permanent storage.

### Required acceptance evidence
- Estimate expected and worst-case output size from measured record sizes and the frozen run count.
- No individual tracked file/blob approaches the host's documented rejection ceiling; enforce a safety threshold in code/tests.
- Interrupted shard writes recover atomically, with a deterministic manifest and exact counts/hashes.
- A clean clone can validate/reconstruct the full experiment ledger; verify the actual remote commit and its blobs.
- Confirm that no rejected oversized blob remains in any commit pushed to the branch history.

---

## Current phase decision

The five entries above remain `BRAINSTORMING_REQUIRED`; none is marked fixed. They are not claims that the current error-recorder has detected them—the recorder ledger was empty when inspected. The next session must **choose one entry, revalidate it, and produce the alternatives/comparison/recommended deterministic plan before implementing that entry**. Do not launch or trust the full campaign while P0 research-validity blockers remain open.

**Out of scope:** ordinary bounded retries for demonstrated transient network errors, routine lint/test failures with an evidence-backed local fix, and recovery bundles/patches needed to preserve interrupted work. Those remain in the normal measured correction loop and are not duplicate durable error records.

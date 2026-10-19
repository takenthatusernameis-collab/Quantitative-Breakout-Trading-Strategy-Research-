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
**Status:** `IMPLEMENTATION_IN_PROGRESS` (source changes committed; acceptance tests and live-data evidence remain outstanding)  
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


### Structured design decision — 2026-10-16 (revalidated against live default branch)

**Decision status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. This is a design decision, not a claim of a fix. No implementation was made in the same session that recorded the decision.

#### Revalidated facts

- `src/breakout_research/data/fetcher.py` (blob `6954e28e94fadfa9b1c49bfa9b147868e609795b`) shows that `load_or_fetch_asset_data()` imports `generate_synthetic_candles()` and immediately generates a series. It does not call `DataFetcher.fetch_full_history()`, although that downloader exists in the same module.
- The loader attempts to write a manifest with `fallback_used=true` and `fallback_source='synthetic'`, but catches and discards every exception from that manifest update. A successful return from the loader therefore does not prove that provenance was durably recorded.
- `research/data_manifest.json` (blob `5b6a2f336cf0c273a035b92cc1f45a428e54bddf`) labels BTCUSDT and ETHUSDT as synthetic, with 3,000 hourly candles from 2023-01-01 through 2023-05-05, while its nominal provider/endpoint fields say Binance. The file's own fallback fields identify the records as synthetic, not downloaded market history.
- `src/breakout_research/data/cache.py` (blob `0677448f7a82967c4762c079c651bf727b46b76b`) contains a test-data generator. Its pseudo-random seed uses Python's process-randomized `hash(symbol)`, so it should not be treated as a reproducible historical dataset across processes.
- `configs/research_v1.json` (blob `33bf2c7dd6e8faa07f791ce181b5fa7dfba1157f`) declares `min_history_years: 3`, an hourly interval and a 720-bar warmup. But `campaign.py` calls the loader with `min_candles=1000`; the loader's default of 26,280 bars is therefore not used by that call. Existing data records show only 3,000 bars.
- The existing `DataFetcher.fetch_full_history()` is useful but not yet a complete contract: it actually returns a tuple of valid candles, rejected-row count and fetch count despite its `List[Candle]` return annotation; timestamp normalization rounds misaligned timestamps down instead of rejecting them; and the campaign-facing loader has no explicit, fail-closed provenance/cache validation path.
- The repository does have a dependency on `requests`, but no live Binance API call was made during this design review. Network reachability, pagination behavior against the live service, and the ability to obtain complete eligible-asset history remain unverified.

**Observed facts vs. inference:** the direct synthetic call and synthetic manifest labels are observed source/state facts. The conclusion that current backtest data cannot support market-performance claims follows directly. Whether the existing Binance downloader can reliably retrieve and validate the entire required history is still an open implementation test.

#### Causal model

The failure path is deterministic: campaign → `load_or_fetch_asset_data()` → synthetic generator. The existing downloader is bypassed; synthetic output can be returned as ordinary `Candle` objects; the manifest write is best-effort and exceptions are swallowed; and the caller accepts 1,000 candles despite the frozen protocol requiring three years. Consequently, the current code can reach backtesting without verifying source authenticity, required coverage or durable provenance. Better prompts, retries and extra logging cannot correct this data path.

#### Intervention options

| Design | Description | Advantages | Material risks / costs |
|---|---|---|---|
| **A. Minimal direct wiring** | Replace the synthetic call with `DataFetcher.fetch_full_history()`; patch return types, coverage checks and manifest writing in place. | Smallest diff; reuses present code; relatively quick. | Leaves provider selection and synthetic isolation implicit; easy for a later path to reintroduce fallback; validation/cache responsibilities can remain scattered; pagination and timestamp assumptions still need work. |
| **B. Explicit provider and campaign-data contract (recommended)** | Define one campaign-facing provider contract; adapt the existing Binance downloader behind it; make the loader return only a validated dataset plus provenance; move synthetic generation to test fixtures; make campaign mode fail closed on missing/invalid data. | Makes source, coverage, validity and failure behavior explicit; enables deterministic fake-provider tests; separates tests from evidence used for economic claims; creates one place to enforce the research protocol. | Medium-sized change; requires clear result/exception types and careful tests around pagination, stale caches, symbols and malformed data. |
| **C. Stop pending an externally supplied, verified dataset/provider** | Keep campaign execution blocked until an immutable dataset with source evidence and adequate coverage is supplied, or until a different provider is explicitly approved. | Safest fallback if Binance cannot deliver the required history or the runtime cannot reach it; avoids synthetic contamination. | No progress on live ingestion; alternative source can add licensing, access, format and reproducibility costs; not justified as the first choice until the existing public endpoint is tested. |

#### Recommendation and scope

Select **B**, using the existing public Binance downloader as the first provider rather than adding a new vendor immediately. Keep the frozen strategy specification unchanged. Make the provider contract obey that specification instead of relaxing the three-year requirement to fit available data.

The contract should produce a validated dataset and a manifest entry that identifies the actual provider/endpoint, symbol, interval, exact time coverage, retrieval time, observed and expected candle counts, rejected-row count, gap/duplicate checks, and deterministic SHA-256 over canonicalized candle rows. Manifest writes should be atomic and failures must be visible. Do not round misaligned market timestamps into apparent valid observations, interpolate missing prices, or silently switch to generated data. In campaign mode, insufficient history, bad/misaligned or duplicate timestamps, invalid OHLCV, unapproved gaps, hash mismatch, unavailable provider, or failed manifest persistence must result in a clear data-unavailable/invalid-data failure (or an explicit asset exclusion where the protocol permits it), never a successful-looking synthetic result.

Use stable, deterministic canonical serialization for hashes, not process-dependent randomness. Synthetic candles should be injectable only in isolated tests and must be rejected by the campaign gate regardless of a forged provider label. Any cache must be accepted only when its provenance, requested interval/range, specification expectations and recomputed hash validate; cache misses should call the real provider, not synthetic generation.

**Important dependency:** fixing BRAIN-001 does not authorize a campaign by itself. BRAIN-002 (the self-authorizing pilot gate) and BRAIN-003 (holdout separation) remain open P0 blockers. Current result records based on synthetic candles must be retained for forensic traceability but explicitly treated as invalid for economic conclusions; do not retroactively relabel them as real market data.

#### Staged implementation plan for a later session

1. **Protect and define:** preserve the present manifest/results as historical evidence; add a campaign-data contract and explicit errors/statuses without deleting old records or changing strategy thresholds. Define the rule for any gaps before implementation; do not fill them by interpolation.
2. **Adapt the provider:** make the Binance downloader return a typed, consistent result; verify pagination boundaries, ordering, interval alignment and coverage. Correct the public return type or wrap the tuple in a dataclass. Apply bounded network timeouts/retries and an explicit termination condition.
3. **Enforce the contract:** remove synthetic generation from the campaign loader; check the protocol's three-year history and warmup requirement from configured values rather than a hard-coded 1,000-bar call; validate finite positive OHLC prices, nonnegative volume, unique strictly increasing hourly timestamps, OHLC consistency and required coverage. Record gaps explicitly and fail/exclude under a predeclared rule.
4. **Persist provenance:** atomically write the manifest with actual retrieved metadata and a recomputable hash. A manifest-write failure must fail closed. Preserve old synthetic manifest/history evidence; do not reuse it as provider data.
5. **Test and canary:** run offline unit tests first; then a one-symbol opt-in live API canary and fresh one-asset download through the same production path. Persist the downloaded data, manifest, hashes and test evidence; independently fetch them from the remote default branch and recompute the hashes.
6. **Revalidate gates:** rerun the pilot only after BRAIN-002's independent gate has been implemented; do not invoke the full campaign until all applicable P0 data, authorization and holdout gates are verified.

#### Acceptance tests

- A mocked, multi-page Binance response yields correctly ordered, unique hourly candles and the expected range/count; pagination has a provable termination condition and no overlapping or skipped page boundaries.
- A live, opt-in canary successfully retrieves a bounded BTCUSDT hourly sample from the declared endpoint, and the emitted manifest exactly matches the observed provider, symbol, interval, retrieval time, coverage, count and recomputed hash. If the endpoint is unavailable, the run reports an infrastructure/data error without substituting synthetic data.
- A forced DNS/HTTP/API error, rate-limit exhaustion, invalid response or empty response cannot return synthetic candles or mark the data loaded.
- Campaign mode rejects synthetic provenance even if manifest booleans or provider strings are forged; it also rejects insufficient coverage, stale/mismatched hashes, duplicate/decreasing/misaligned timestamps, malformed OHLCV and any gaps not allowed by the predeclared protocol.
- Three-year minimum history comes from the frozen research protocol and is actually enforced in campaign mode; the 720-bar warmup is still available after coverage validation.
- Tests prove manifest-write failure is surfaced; successful manifest writes are atomic and independently parseable; a clean clone can recompute the content hash.
- Synthetic generator tests remain available offline but cannot be invoked by the production campaign loader.
- Fresh remote data artifacts and test reports are re-read from the default branch and hash-verified; no test result or persistence claim is inferred merely from a successful local command.

#### Risks, falsifiers, rollback and external dependencies

- **Falsifier for the main diagnosis:** live current source would have to show the loader invokes and verifies the real provider, and the manifest would need independently verifiable raw-source lineage. Current code does not show that.
- **Falsifier for selecting Binance first:** a bounded live canary plus a paginated history test demonstrates that the public endpoint cannot supply the required data for eligible symbols within the runtime's limits. If falsified, stop and move to option C / `WAITING_EXTERNAL_INTERVENTION`; do not silently pick another provider.
- **Operational risks:** public API downtime/rate limits, Binance listing-history limits for newer assets, pagination edge cases, runtime/network restrictions, and the pre-existing current-universe survivorship limitation. An asset without the required history must be excluded or block the run under the frozen protocol, not given a shorter arbitrary history.
- **Rollback:** revert only the new provider-contract changes if they fail tests, preserve all downloaded/test artifacts and the original manifest for diagnosis, and leave campaign authorization blocked. Rolling back to synthetic loading is not an acceptable production rollback.
- **External intervention:** no API credential is assumed for Binance's public klines endpoint, but network availability has not been tested. If it is blocked or the endpoint cannot provide required history, record the specific failure and wait for an explicitly approved data source or runtime/network change.

**Next task:** implement option B in a later session, after rechecking this design against current `main`. Keep this item at `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` until the implementation and acceptance evidence exist; then separately record implementation and validation status.

### Implementation handoff / current verification state — 2026-10-16 UTC

**Changes committed to `main`:**
- `5c5ffe56d3ee484da43bf3f8c5044f5560be3028` plus follow-up `48304cce9457b5c5da6f2c8ae1498493a112be11` — rewrote `src/breakout_research/data/fetcher.py` around a real Binance hourly provider, forward/backward pagination with a bounded page count and no-progress checks, strict candle validation, a canonical SHA-256 dataset format, immutable hash-named CSV snapshots, verified cache reads, explicit no-fallback and spec-hash checks, and atomic manifest writing. The campaign-facing loader contains no synthetic generator import/call.
- `33520ae77dbc18ad2941eacd367245ed3cb11111` and follow-up `fd924b2f49eb3769a12543782a00834a5e938df8` — removed the misleading `min_candles=1000` override and made the campaign stop instead of silently skipping a required eligible asset or ignoring missing BTC benchmark data.
- `c808a41844abec367bd4c59a37097c54efefbd0b` — removed the pilot's smaller-history override. The loader takes the maximum of any caller request and the frozen protocol minimum (`ceil(min_history_years × 365 × 24)`, 26,280 for the current three-year hourly protocol).
- `f23d0097834bde9fd872dbdd90686e78577118ad`, `d0c22425b15ec0e3ef545ea4fd140ec838d8a723`, `0dbd13c217f18503e928cf3790bd2cdabbf47602` and `60c075b53a94efe0fee5a88c0d7a69ae13758f9c` — added thirteen regression tests covering the three-year minimum, strict hourly validation, timestamp alignment, deterministic hashes, pagination, synthetic-manifest invalidation, provider/manifest failure, corrupted/ambiguous cache provenance, and campaign hard-stop behavior for missing asset/BTC benchmark data.

**Safety behavior now present in source:** the loader requests complete closed hourly candles through the frozen required range; rejects missing/invalid/gapped/duplicate/unordered/misaligned/non-finite data and any rejected provider row; never returns generated candles; stores data as content-addressed CSV and manifest metadata; archives prior manifest entries when different data supersedes them; fails closed unless a real cache has an explicit `fallback_used: false`, matching per-asset/top-level specification hashes, valid retrieval metadata and a recomputed content hash; and raises an explicit error when the provider or manifest persistence fails. The campaign now hard-stops if a required eligible asset or BTC benchmark data cannot be validated rather than silently changing the evaluated universe or disabling a benchmark filter.

**Verification limitations:** the connected GitHub API confirms these commits are on `main`, but this execution container cannot resolve `github.com` for a local clone. Therefore the ten tests have **not been executed**, the new source has not received a local `py_compile`/pytest run, and no live Binance API canary was performed. Remote source persistence is verified; runtime/test acceptance is not. Keep this item `IMPLEMENTATION_IN_PROGRESS`, not `RESOLVED_VERIFIED`, until a fresh environment runs the regression suite and a bounded live canary successfully validates a real, full-length history and its manifest/hash.

**Important migration note:** existing synthetic entries are not accepted as cache data. When a real snapshot is successfully persisted, the old entry is copied into `invalidated_prior_entries` before the current asset entry is replaced. Existing synthetic result rows remain forensic-only and do not become real-data evidence.

**Remaining BRAIN-001 acceptance gates:** run all existing tests plus `tests/test_data_fetcher.py`; correct any failures; exercise pagination with real three-year bounds; run a one-symbol opt-in Binance canary only in a network-enabled test environment; independently re-fetch the persisted CSV and manifest from the default branch and recompute the content hash. Do not start or trust the full campaign while BRAIN-002 (pilot gate) and BRAIN-003 (holdout protection) remain open. BRAIN-002–BRAIN-005 have not been implemented in this session.

---

## BRAIN-002 — Pilot gate self-authorizes without proving prerequisites

**Priority:** P0 — blocks trustworthy campaign authorization  
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` (structured design decision recorded below; implementation remains deferred until prerequisites are satisfied)  
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


### Structured design decision — independent campaign authorization (2026-10-16 UTC)

**Decision:** make the pilot evidence-only; a separate deterministic validator evaluates evidence and creates the authorization artifact; campaign startup revalidates that artifact before any experiment. This is a code-correctness boundary, not a security boundary against a maintainer who can rewrite the validator.

#### Revalidated causal model

- Live \`src/breakout_research/pilot.py\` (blob \`1be1580ca92063ccead9f70d87376a5dc0c8b6c0\`) unconditionally sets \`state.pilot_passed = True\`, then writes \`pilot_passed: true\` and \`campaign_authorized: true\` after up to 24 configs, one asset, baseline cost only.
- The pilot calls \`run_fold_backtest()\` with \`btc_candles=None\`; it does not independently prove genuine-data provenance, required coverage, all cost levels, restore/reconciliation, or remote persistence.
- Live \`campaign.py\` (blob \`92b24e9a433fbb6f8e8f2329e0007efc5f2c58d3\`) checks the authorization boolean, spec hash and code hash. Those hashes don't prove prerequisite evidence actually passed.
- Live \`research_state/pilot_gate.json\` (blob \`9737fa6367b64c909aa70d914014c8541be8f835\`) authorizes the campaign while its data manifest marks input candles synthetic. The checkpoint also has a positive pilot flag despite \`last_verified_record: 0\`.
- BRAIN-001 changes are committed but tests/live-data checks remain unverified. Current gate must remain **BLOCKED**.

#### Designs compared

| Design | Benefit | Limitation / risk |
|---|---|---|
| **A. Strengthen booleans in \`pilot.py\`** | Small patch; can add prerequisite checks. | Pilot remains evidence producer and authorizer; partial runs can self-promote again. |
| **B. External CI status as the whole gate** | Command exit statuses can be tied to a commit. | Green CI alone doesn't prove source provenance, checkpoint restore, campaign inputs or remote artifact integrity. |
| **C. Evidence-only pilot + separate validator + campaign-time revalidation (recommended)** | Separates measurement from authorization; enables deterministic positive/negative tests and hash-bound inputs. | More contract code/tests; not a security barrier against an actor who can alter both validator and source. |

#### Contract and staged plan

1. Pilot emits an evidence report only: exact code/spec/universe/data hashes; provider/coverage evidence; asset/config/cost IDs; actual test exit codes and report hashes; fixture results; checkpoint/ledger reconciliation report; restore result; result IDs/counts; and remote persistence receipt.
2. A separate deterministic validator recomputes inputs and verifies genuine-data entries, full history, content hashes, successful prerequisite tests, restore and result reconciliation, and verified remote persistence. It outputs \`BLOCKED\` or \`AUTHORIZED\` with a canonical digest of every evidence artifact. Legacy booleans carry no authority.
3. Campaign startup invokes the validator again against the current worktree and artifacts. Any missing, stale, malformed or changed item blocks execution. Bind authorization to exact commit, source-code hash, protocol/spec hash, universe snapshot, dataset hashes, test bundle, checkpoint/ledger report and frozen-candidate protocol.
4. Preserve the old gate for audit history but label it untrusted; don't overwrite it as if it had been valid. Invalidate authorization when any bound source/artifact changes.
5. Keep current gate blocked until BRAIN-001 has passed tests and a bounded live canary, BRAIN-004 state reconciliation is proven, and BRAIN-003's candidate/holdout contract is in place.

#### Acceptance, falsifier and rollback

- Forged legacy booleans, synthetic data with Binance-looking labels, stale/mismatched hashes, missing/nonzero tests, failed restore, bad result count, unverified remote SHA and malformed JSON must block.
- Known-good fixtures pass only when all conditions are met and recomputed hashes match. A time-of-check/time-of-use test mutates a source/evidence file after authorization; campaign startup must reject the stale artifact.
- With the current synthetic manifest and unverified BRAIN-001 runtime behavior, current validation must return \`BLOCKED\`.
- **Falsifier:** current source would need to prove that the pilot no longer self-authorizes and campaign startup independently checks complete current evidence; it does not.
- **Rollback:** revert validator integration if tests fail, but keep campaign closed. Never restore trust in the old positive boolean.
- **External dependencies:** public-data access needs no API credential, but runtime/network reachability and remote persistence verification are required. CI status supplements rather than replaces the evidence contract.

**Status boundary:** design-ready does not mean authorized. BRAIN-002 cannot pass until BRAIN-001/003/004 prerequisites are independently validated.

---

## BRAIN-003 — Full-grid loop evaluates the final holdout before candidate freeze

**Priority:** P0 — potentially invalidates final performance claims  
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` (structured design decision recorded below; implementation remains deferred until prerequisites are satisfied)  
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


### Structured design decision — protected candidate/holdout phases (2026-10-16 UTC)

**Decision:** separate validation and holdout phases. Only a frozen, hash-bound candidate manifest may be evaluated by the holdout runner. Historical holdout outputs are classified as previously evaluated/exposed or exposure-unknown, never “untouched.” If historical non-use cannot be proven, preregister a new confirmatory period under a separately versioned protocol before seeing its results.

#### Revalidated causal model

- Live \`campaign.py\` (blob \`92b24e9a433fbb6f8e8f2329e0007efc5f2c58d3\`) creates four validation folds and a final holdout but loops every config through every fold; \`is_holdout\` is not used to prevent all-grid holdout runs.
- The protocol declares \`max_candidates_per_asset: 1\` and validation selection criteria, but the inspected source has no candidate-freeze boundary.
- Current results include holdout-fold rows, but the manifest marks their input candles synthetic. These rows do not support historical performance claims; whether their metrics influenced agent/human decisions is unknown.
- There is no separate selector/evaluator artifact contract in the inspected source tree.

#### Designs compared

| Design | Benefit | Limitation / risk |
|---|---|---|
| **A. Gate \`is_holdout\` in the existing loop** | Small change prevents normal grid rows from running the final fold. | Doesn't prove selection/freeze occurs first; holdout values may still leak through shared state. |
| **B. Validation-only runner + frozen candidate manifest + separate evaluator (recommended)** | Enforces a defined freeze boundary and separates outputs; fits the one existing workflow file. | Requires deterministic selection and artifacts; same-repository access isn't a security sandbox. |
| **C. Consume old holdout and wait for future confirmatory period** | Strongest solution if old metrics affected candidate choices. | Needs sufficient future data and a separately versioned/preregistered protocol; cannot recycle an inspected period. |

#### Recommended phase contract

1. **Validation:** run the frozen 2,304-config grid only on the four validation windows and required cost scenarios. Do not compute, emit or consume final-holdout returns in this phase.
2. **Selector:** implement the already-frozen selection criteria (trade counts, cost robustness, required positive folds, median Sharpe and tie-breakers); do not adjust thresholds.
3. **Freeze:** write canonical JSON with at most the specified candidate count per asset; bind full parameters/config ID and hashes for protocol, code, universe, data, selector and validation inputs; include \`frozen=true\`. Recompute hashes on read.
4. **Holdout evaluator:** separate command/phase within the existing workflow accepts only the frozen manifest, verified data references and frozen costs. Reject missing/duplicate candidates and stale hashes; write a distinct holdout artifact not read by the selector.
5. **Report:** join outputs only after freeze and evaluation. Any candidate/rule change after seeing holdout results consumes that holdout.
6. **History:** preserve old fold-4 rows; mark source synthetic and exposure \`EXPOSED_OR_UNKNOWN\` until logs/reports prove more. If non-use in selection cannot be established, preregister a new confirmatory period in a separate protocol version before accessing it. Do not silently alter v1 thresholds.

#### Acceptance, falsifier and rollback

- Spy/mock tests prove validation never calls holdout bounds and creates zero holdout rows.
- Selector rejects holdout-tagged input; validation input mutation after freeze invalidates candidate hash.
- Evaluator rejects full-grid configs, arbitrary candidate lists, duplicates/missing candidates, and stale code/spec/data hashes.
- Positive fixture evaluates only the frozen candidate for each eligible asset across specified holdout cost scenarios; output stays separate from selection.
- Crash injection proves candidate manifest persisted/verified before holdout execution.
- Historical audit ends as \`CONSUMED\`, \`EXPOSURE_UNKNOWN\` or \`NOT_USED_WITH_EVIDENCE\`; default to unknown.
- **Falsifier:** current source would have to prove all-grid holdout access is blocked and each evaluation requires a frozen manifest; it does not.
- **Rollback:** revert phase wiring on test failure, keep campaign blocked and preserve exposure labels; never restore the all-config holdout loop.
- **Methodology guard:** phase separation preserves existing selection criteria. A new confirmatory period is a methodology change and must be preregistered/versioned before use.

---

## BRAIN-004 — Resume cursor is reset and checkpoint counts are not reconciled to results

**Priority:** P0 — risks duplicate/lost research units on resume  
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` (structured design decision recorded below; implementation remains deferred until prerequisites are satisfied)  
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


### Structured design decision — deterministic resume and crash recovery (2026-10-16 UTC)

**Decision:** use transaction-like result batches, immutable verified shards, and a manifest as durable source of truth. Derive the checkpoint's next unit from the exact verified experiment-ID set. Implement against BRAIN-005's storage contract to avoid competing result stores.

#### Revalidated causal model

- Live \`campaign.py\` resets config/fold/cost cursors when entering the current asset and checkpoints current indices, not a rigorously specified next-uncompleted identity.
- Results are appended before the completed counter is incremented and checkpointed. A crash among append, counter, checkpoint and remote push can cause duplicate work or misleading progress.
- Live \`ledger.py\` has no stable experiment ID or deduplication. Live \`checkpoint.py\` catches every load error and returns \`None\`, making corruption look like absence and allowing a reset.
- Current checkpoint reports 81,510 completed but \`last_verified_record: 0\`; actual duplicate/loss count is unknown. Legacy rows lack immutable data hashes and stable IDs.

#### Designs compared

| Design | Benefit | Limitation / risk |
|---|---|---|
| **A. Fix cursor resets only** | Smallest diff. | Doesn't reconcile crash boundaries or deduplicate records. |
| **B. Rescan monolithic ledger** | Can reconstruct progress if rows have stable IDs. | Existing rows lack data provenance and the ledger is already 51.7 MB, with an approximately 429.9 MB rejected attempted update. |
| **C. Verified transaction batches + shard manifest + derived cursor (recommended)** | Defines durable commit boundaries, crash recovery and deterministic resume; aligns with bounded storage. | Requires migration, ID/schema rules and fault-injection tests. |

#### Recommended transaction protocol

1. Stable experiment ID is a hash of canonical spec, code, universe and dataset hashes; asset; config ID/parameter hash; fold or frozen candidate; exact bounds; cost scenario; and result-schema version. Exclude wall-clock metadata.
2. For a bounded batch, write temp records, canonicalize/sort, validate schema/expected IDs/count/uniqueness, flush/fsync, hash, then atomically promote an immutable shard.
3. Update the compact manifest only after shard verification. It records shard hashes/counts/ID sets/ranges and bound spec/code/data hashes. Derive the checkpoint from manifest-verified IDs and identify the *next uncompleted* deterministic unit.
4. After push, verify remote commit SHA, then re-read/re-hash manifest and newly added shards before advancing verified state. Local file write, commit or push exit status alone is insufficient.
5. Resume validates schema and hashes, reconstructs completed IDs from verified shards, and recomputes the first missing unit. If checkpoint conflicts, reconstruct with an integrity report; if manifest or provenance is corrupt/missing, stop for recovery rather than reset to zero.
6. Identical duplicate ID/content counts once. Conflicting contents for one ID are an integrity failure. Temp/unreferenced shards are not committed evidence and cannot advance checkpoint.
7. Treat current counter as untrusted legacy state. Preserve the original ledger/checkpoint; do not certify old rows missing data/code/spec hashes as trusted real-data work just because a derived identity is possible.

#### Acceptance, falsifier and rollback

- Inject crashes before/during write, after fsync, after promotion, after manifest, after checkpoint, after local commit and after push acknowledgement. Recovery must neither lose nor duplicate committed IDs.
- Repeated recovery gives the same completed-ID set, next unit and manifest bytes.
- Mutated counters, cursors, shard hashes, missing files, duplicate/conflicting IDs, changed spec/code/data hashes and malformed JSON trigger a deterministic block/reconstruction.
- \`last_verified_record\` is derived from a verified boundary, never left zero beside a positive trusted count.
- **Falsifier:** current source would need stable IDs and a tested transaction/restore protocol; neither exists.
- **Rollback:** preserve old ledger/checkpoint and recovery bundles; roll back only to the last remote hash-verified shard manifest. Never silently reinitialize corrupt state.
- **Dependency:** share the BRAIN-005 storage contract; no parallel ledger.

---

## BRAIN-005 — Result persistence can exceed Git hosting limits

**Priority:** P1 — campaign completion/persistence risk  
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` (structured design decision recorded below; implementation remains deferred until prerequisites are satisfied)  
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


### Structured design decision — bounded auditable result storage (2026-10-16 UTC)

**Decision:** adopt immutable deterministic JSONL shards with a compact manifest. Enforce a hard **4 MiB per shard** ceiling measured in serialized bytes. Keep storage repository-local initially; do not assume an unconfigured database or transient Actions artifact is permanent storage.

#### Revalidated causal model

- Current remote \`research/results.jsonl\` is 51,688,138 bytes. Historical run #2 recorded an approximately 429.90 MB attempted update rejected for file size. Current \`campaign.py\` appends every result to one growing file.
- The visible current object is ~51.7 MB; the ~429.9 MB attempt is not the present remote file. A complete reachable-history/blob scan remains required before making any claim about oversized historical objects.
- The 20 assets × 2,304 configs × 5 folds × 3 cost scenarios grid is 691,200 units. A rough projection using ~634 bytes per row based on the current file size / 81,510 checkpoint claim is ~438 MB. This is an estimate; actual line count and record-size distribution still need measuring.
- Existing rows lack stable experiment IDs and immutable source-data hashes; current sample data is explicitly synthetic. Historical rows must not be certified as valid real-data results during migration.

#### Designs compared

| Design | Benefit | Limitation / risk |
|---|---|---|
| **A. Immutable bounded JSONL shards (recommended)** | Minimal runtime dependencies, auditable text, explicit byte ceiling/hash/count per unit. | More files and manifest logic; migration must preserve legacy evidence. |
| **B. SQLite locally with bounded exports** | Good local indexing/uniqueness constraints. | WAL/locking and binary state complicate Actions recovery; remote durable state still needs exports and hash verification. |
| **C. External object storage** | Scales beyond repository storage. | Provider, credentials, free limits, retention and availability aren't configured/verified; adds an external blocker. |

#### Recommended storage contract

1. Store new verified results under \`research/results_shards/<campaign_id>/\`, with campaign ID derived deterministically from spec/code/universe/data-manifest hashes. Shards are immutable and ordered deterministically within the campaign.
2. Each shard has whole canonical JSONL rows and remains ≤4 MiB. Start a new shard before the next row would exceed the limit; a single oversized row fails closed. Enforce before stage/commit and in tests.
3. New rows carry BRAIN-004 stable experiment ID, schema version, spec/code/data hashes, asset, config/parameter hash, fold/candidate ID, time bounds, cost scenario and result. Execution timestamps are metadata, not identity. Keep legacy-unverified rows outside the trusted results namespace.
4. A compact \`results_manifest.json\` lists shard paths, SHA-256, byte/count metrics, ID ranges/sets, schema, campaign ID and verified total. Promote atomically only after each shard parses and IDs/hashes verify. Reports are derived from manifest/shards, not another authoritative monolith.
5. Commit shards/manifest through the existing single workflow. Verify remote commit SHA and re-read/hash new shards after push. Stop appending to the old monolith once shard writing is independently tested.
6. Legacy migration is a separate fail-closed operation in a clone-enabled environment: calculate original byte-level SHA-256, exact byte/line counts, parse/error counts, duplicate candidates and schema distribution; partition/compress raw rows and label them \`legacy_unverified\` with synthetic/unknown provenance. A derived ID cannot confer real-data validity.
7. Reconstruct legacy archive from a clean clone, verify counts/hashes and prove the original evidence is preserved. Only then, in a later commit, stop tracking/remove the working copy of \`research/results.jsonl\`. Do not force-push to erase its old 51.7 MB blob. Scan reachable history and record large-blob evidence first.
8. Estimate future size from measured row sizes and exact unit count, with conservative assumptions and early warning thresholds; reject monolithic rewrites regardless of whether a current file is below 100 MB.

#### Acceptance, falsifier and rollback

- Cross a shard boundary with fixtures; every shard stays ≤4 MiB, parses, has unique IDs, matching counts/ranges/hashes and deterministic bytes across reruns.
- Combine with BRAIN-004 crash-injection: no lost/duplicated committed IDs or silent conflicting-ID overwrite.
- Corrupted shard/manifest blocks resume before consuming results.
- Measure real legacy line count and record-size distribution; publish expected and conservative growth estimates.
- Clean clone reconstructs shards/archive and verifies exact counts/hashes; original legacy evidence remains available.
- Scan reachable \`main\` history for blobs ≥100 MB; retain scan output. Don't assert no oversized historic object without evidence.
- **Falsifier:** measured full-run size and a crash-safe bounded append design would need to prove the single ledger remains bounded; current size/growth evidence argues against that.
- **Rollback:** preserve old ledger/migration manifest/recovery bundle; halt writes and return to last remotely hash-verified shard manifest. Never silently fall back to monolithic appends.
- **External dependency:** none for repository-local shards, but clean-clone migration and remote hashing require network access. External storage stays unselected until explicitly approved and verified.

---

## BRAIN-006 — Preregistered candidate-selection rule is not implemented by the only selector

**Priority:** P0 — blocks any defensible candidate promotion  
**Status:** `BRAINSTORMING_REQUIRED` (evidence recorded 2026-10-19 UTC; the required impact quantification is the next bounded task, and the structured design decision must be written in a later session)  
**Cause labels:** `IMPLEMENTATION_DEFECT`, `RESEARCH_DESIGN_RISK`  
**Confidence:** confirmed by source inspection at code hash `d0dca29...`; the divergence from the frozen manifest is not yet quantified.

### Evidence
- `configs/research_v1.json` → `selection` freezes: `ranking_metric: median_net_daily_sharpe`; tiebreakers `median_net_return`, `max_drawdown`, `turnover`, `config_id`; `min_trades_total: 30`; `min_trades_per_fold: 5`; `min_folds_with_min_trades: 3`; `positive_net_return_baseline: true`; `positive_net_return_2x_costs: true`; `positive_folds_required: 3`; `median_sharpe_gt_zero: true`; `median_sharpe_gt_buyhold: true`; `max_candidates_per_asset: 1`; `neighbor_analysis: true`.
- `src/breakout_research/candidate_freeze.py:55-87` (`select_best_candidate`) is the only selection implementation in the repository. It ranks by **median profit_factor** with a median-max-drawdown tiebreak and applies **none** of the preregistered gates (no minimum trade counts, no positive net-return requirement at 1×/2× costs, no positive-fold count, no Sharpe tests, no buy-and-hold comparison).
- `src/breakout_research/campaign.py` contains no selection logic at all (no `selection`/`min_trades`/`median_net_daily_sharpe` matches), so `select_best_candidate` is the effective selector.
- `grep -rn "buyhold" src/breakout_research --include=*.py` → no matches. No buy-and-hold baseline metric is computed or stored, and the result records contain no baseline field, so the `median_sharpe_gt_buyhold` gate has no data source in the current ledger.
- `research/candidate_manifest.json` is `frozen: true` with 18 candidates (one per asset), `freeze_commit 3e937dd3...`, `code_hash 382e3141...`, `spec_hash 2d22e702...`, `data_manifest_hash d8b0cb7e...`, `manifest_hash 9ea6b1c3...`. It was produced by the helper above, therefore under a rule that is not the preregistered one.
- `reports/final_research_report.json` (holdout exposure `EXPOSED_OR_UNKNOWN`) reports 9 `PROVISIONAL_HISTORICAL_SURVIVAL`, 7 `REJECTED_ON_HOLDOUT`, 2 `INSUFFICIENT_EVIDENCE` conclusions, all derived from those 18 promoted candidates.
- `reports/v1_cycle_summary.md:29-32` documents the freeze as "18 candidates (max 1 per asset)" without recording that the selection rule differed from `configs/research_v1.json`.

### Why this needs a design decision
Two questions cannot be settled by a local patch: (a) which rule is authoritative for a candidate already frozen and already used for an exposed holdout, and (b) how a conforming selector reconciles an immutable historical manifest, a new cycle, and the code-hash-bound authorization artifact. Any change under `src/breakout_research/` rotates `compute_code_hash()` and therefore invalidates `research_state/campaign_authorization.json` until the pilot is re-run and re-authorized; that coupling is part of the design surface.

### Alternatives to compare
A. **Re-freeze under the preregistered rule and version the manifest** — publish a new, separately versioned candidate manifest for the continuous cycle, leave the v1 manifest immutable, and treat v1 holdout conclusions as historical-only.
B. **Reconcile in place** — treat the preregistered rule as the only admissible rule, supersede the v1 manifest with an explicit supersession record, and re-derive the affected per-asset economic conclusions.
C. **Amend the frozen specification** — record that the profit-factor rule was the intended rule, with an explicit, separately versioned protocol amendment; only permissible if the deviation is judged to have been intended rather than a defect, and it must not be used to make the original conclusions look stronger.

### Required acceptance evidence
- Quantified divergence: per asset, the candidate selected under the preregistered rule versus the frozen manifest entry, and which preregistered gates are unsatisfiable from the existing ledger (notably the buy-and-hold baseline comparison).
- A decision record naming the authoritative rule, the manifest versioning policy, and the treatment of the already-exposed holdout.
- If `src/` changes: updated unit tests for every preregistered gate, a re-run pilot, a re-derived `campaign_authorization.json` with a matching code hash, and a verified remote SHA.
- An explicit statement that the v1 holdout (`EXPOSED_OR_UNKNOWN`) is never reused as confirmation for a new cycle.

---

## BRAIN-007 — Cycle-level evidence is not linked to the identical prior campaign, and the checkpoint counter mixes validation with exposed-holdout units

**Priority:** P1 — reporting/traceability risk for the continuous campaign  
**Status:** `BRAINSTORMING_REQUIRED` (evidence recorded 2026-10-19 UTC)  
**Cause labels:** `IMPLEMENTATION_DEFECT`, `RESEARCH_DESIGN_RISK`  
**Confidence:** confirmed at code hash `d0dca29...` by direct artifact comparison.

### Evidence
- Continuous cycle 0 (`research/campaign_cycles/0f52f6c9.../`) stores 9,972 shards / 497,664 records with campaign id `577e87e2...` and code hash `d0dca29...`. The v1 validation sweep (`research/results_shards/fcf04f6e.../`) stores the same unit set. A unit-by-unit metric comparison (excluding `stored_utc`, `experiment_id`, `schema_version`) shows **497,664 units in both, 0 units only in either set, and 0 units with differing metrics** — the continuous cycle re-ran an already-completed grid and reproduced it exactly.
- `research/campaign_cycles/0f52f6c9.../cycle_report.json` presents these as a new cycle (`state: COMPLETE`) and does not link to the identical prior campaign `fcf04f6e...`, although `research_state/continuous_universe_campaign_spec.md` §5 requires linking to verified prior evidence instead of presenting recomputed units as new trials.
- `research_state/checkpoint.json` reports `completed_records == last_verified_record == 497718`. 497,718 = 497,664 validation units + 54 holdout units (`fold_index 4`, `is_holdout: true`, one frozen candidate per asset × 3 cost scenarios) that exist only in the legacy top-level shard set `research/results_shards/577e87e2.../`. The continuous cycle contains **zero** holdout records. Earlier handoff entries described these counters as "reconciled" with the continuous cycle, which the artifacts do not support.
- The legacy top-level shard set holds 497,765 raw lines for 497,718 unique units: 47 units are written twice, with identical content except `stored_utc` (same `experiment_id`), i.e. benign duplicate writes rather than conflicting content. The continuous cycle set has 0 duplicates.
- `research_state/continuous_universe_state.json` records `next_cohort_index: 2` while the eligible universe holds 18 assets and `COHORT_SIZE` is 20, so every further cohort is empty; cohort 1 already terminated as `DUPLICATE_OR_NO_NEW_CANDIDATES` (`research/campaign_cycles/be4223dc.../cycle_report.json`).

### Why this needs a design decision
Cycle identity, deduplication against identical prior evidence, checkpoint counter semantics, and the terminal `AWAITING_NEW_CANDIDATES`/`BLOCKED_EXTERNAL` state must be specified once, coherently, before more cycles run. Today the coordinator can record an empty cohort as a completed cycle and advance the counter, and no artifact distinguishes "new trial" from "recomputed identical unit".

### Alternatives to compare
A. **Ledger-level dedup** — make the coordinator detect identical (code, spec, data, unit) work, link it to the existing verified evidence, and emit a cycle report that distinguishes linked units from newly executed units.
B. **Immutable per-cycle ledgers plus a separate linkage index** — keep each cycle's own shards immutable and add a cycle-to-campaign link table, leaving shard identity untouched.
C. **Reporting-only reconciliation** — keep the current execution behavior and add a verifier that emits the expected-vs-verified and linked-vs-new reconciliation in each cycle report, without changing the coordinator.

### Required acceptance evidence
- A definition of checkpoint counter semantics that never mixes holdout units into a validation completion count.
- A terminal state for an exhausted universe that records `AWAITING_NEW_CANDIDATES`/`BLOCKED_EXTERNAL` with the provider evidence, instead of appending empty cycles to `completed_cycle_ids`.
- Evidence that the external universe provider is currently unreachable from the research runner (`https://api.binance.com/api/v3/ping` → HTTP 451 in this environment, also present in `research_state/workflow_run_diagnostics.jsonl`), so a new snapshot is an external boundary, not an idle wait.

---

## BRAIN-006 — Decision record (written 2026-10-19 UTC, code hash `d0dca29...`, HEAD `a968aa62`)

**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`
**Cause labels:** `IMPLEMENTATION_DEFECT`, `RESEARCH_DESIGN_RISK`
**Authoritative rule:** the preregistered rule in `configs/research_v1.json` -> `selection`, with the three
interpretations that the text leaves open pinned in section 2. The v1 profit-factor rule
(`src/breakout_research/candidate_freeze.py:50-87`) is **not** authoritative and is retained only as a
historical record of how the v1 manifest was produced.
**Not implemented in this session** (README Section 2A C1): this record is the design; the `src/` implementation
is a later session.

### 1. Impact quantification (prerequisite evidence, completed this cycle)

Read-only re-derivation of the per-asset candidate set for continuous cycle 0 under the preregistered rule:
`scripts/select_candidates_cycle0.py` -> `research/campaign_cycles/0f52f6c9.../candidate_selection.json`
(497,664 / 497,664 expected units = 100% coverage, 0 holdout records read, 0 duplicate units, byte-identical
on re-run, artifact SHA-256 `0e4d43f8e23504ba25dc928b5a3197968ba6020e5226cf26c77d5ffeff45311d`).

| asset | preregistered selection | status | frozen v1 candidate | frozen candidate qualifies | rank of frozen candidate |
|---|---|---|---|---|---|
| ADAUSDT | cfg_1513 | CANDIDATE_SELECTED | cfg_1513 | yes | 1 |
| ATOMUSDT | cfg_0581 | CANDIDATE_SELECTED | cfg_0629 | yes | 2 |
| AVAXUSDT | cfg_1561 | CANDIDATE_SELECTED | cfg_1012 | no | - |
| BCHUSDT | - | NO_CANDIDATE | cfg_0553 | no | - |
| BNBUSDT | cfg_0089 | CANDIDATE_SELECTED | cfg_1036 | no | - |
| BTCUSDT | - | INSUFFICIENT_EVIDENCE | cfg_1009 | no | - |
| DOGEUSDT | cfg_0040 | CANDIDATE_SELECTED | cfg_0664 | no | - |
| DOTUSDT | cfg_0384 | CANDIDATE_SELECTED | cfg_0300 | no | - |
| ETHUSDT | cfg_1525 | CANDIDATE_SELECTED | cfg_1128 | no | - |
| LINKUSDT | - | NO_CANDIDATE | cfg_1105 | no | - |
| LTCUSDT | cfg_0084 | CANDIDATE_SELECTED | cfg_1106 | no | - |
| NEARUSDT | cfg_1584 | CANDIDATE_SELECTED | cfg_2040 | no | - |
| SOLUSDT | cfg_0732 | CANDIDATE_SELECTED | cfg_0828 | no | - |
| SUIUSDT | cfg_0507 | CANDIDATE_SELECTED | cfg_0602 | no | - |
| TRXUSDT | - | NO_CANDIDATE | cfg_0098 | no | - |
| UNIUSDT | cfg_0124 | CANDIDATE_SELECTED | cfg_0521 | no | - |
| XLMUSDT | cfg_0124 | CANDIDATE_SELECTED | cfg_1108 | no | - |
| XRPUSDT | cfg_1661 | CANDIDATE_SELECTED | cfg_2189 | no | - |

- 14 assets qualify, 1 is `INSUFFICIENT_EVIDENCE` (BTCUSDT: exactly one configuration clears the economic
  screen but fails the sample floor), 3 are `NO_CANDIDATE` (BCHUSDT, LINKUSDT, TRXUSDT).
- **16 of 18 frozen v1 candidates fail the preregistered gates**; only ADAUSDT and ATOMUSDT survive, and
  ADAUSDT's frozen candidate is also the preregistered winner. The v1 holdout conclusions
  (`reports/final_research_report.json`: 9 `PROVISIONAL_HISTORICAL_SURVIVAL`, 7 `REJECTED_ON_HOLDOUT`,
  2 `INSUFFICIENT_EVIDENCE`) therefore describe candidates that the preregistered rule would not have
  promoted.
- Binding gates (configurations failing each gate, summed over the 18 assets x 1,728 evaluated
  configurations): `positive_folds_required` 39,478, `positive_net_return_2x_costs` 35,526,
  `median_sharpe_gt_zero` 35,172, `positive_net_return_baseline` 33,550, `median_sharpe_gt_buyhold` 27,571,
  `min_trades_total` 22,640, `min_folds_with_min_trades` / `min_trades_per_fold` 19,598 each. The deviation
  is not a single missing gate: the profit-factor rule simply does not screen on returns, folds or Sharpe.
- The `median_sharpe_gt_buyhold` gate **is** satisfiable from the repository: it was recomputed from the
  frozen, hash-verified candle datasets (`research/data/candles/`, verified against
  `research/data_manifest.json`) over the same fold windows. The ledger has no baseline field, but the
  baseline is not unavailable - it was never computed and stored.

### 2. Interpretations the preregistered text leaves open (pinned by this decision)

These are readings of the existing preregistered text (README Section 9 and `configs/research_v1.json` ->
`selection`); they are **not** methodology changes and they do not weaken any threshold.

1. **Validation-fold metric** = the metric of a fold at baseline (1x) costs; cost scenarios are the same
   trades re-costed and are never summed with the baseline. Alternative readings (median across cost
   scenarios; pooled over the 12 fold x cost units) are evaluated as sensitivity variants.
2. **Combined validation net return** = the mean of the four fold net returns. The sign of the mean and of
   the sum is identical, so the gate is invariant to that choice; the compounded product of the fold returns
   is evaluated as a sensitivity variant because it can differ in sign.
3. **Per-fold trade floor** = 5 trades in at least 3 of the 4 folds (README Section 9: "at least 5 in at
   least three of the four folds"), not 5 trades in every fold. The stricter reading is a sensitivity variant.
   The gate is not evaluable for a configuration with no baseline-cost records, and a configuration without
   2x-cost records cannot pass the 2x gate; such gates are reported `NOT_EVALUABLE` with the missing input.

**Sensitivity (interpretation choice changes the selected configuration for a minority of assets):**
`fold_median_across_costs` 13/18 agreements with the pinned reading, `pooled_fold_cost_units` 15/18,
`strict_min_trades_in_every_fold` 17/18, `combined_net_return_compounded` 16/18. The interpretation is
therefore outcome-relevant for up to 5 of 18 assets and must be pinned before any candidate is frozen -
which is exactly what this decision does.

### 3. Alternatives considered

- **A. Re-freeze under the preregistered rule and version the manifest** - publish a new, separately
  versioned candidate manifest for the continuous cycle; keep `research/candidate_manifest.json` (v1)
  immutable; treat the v1 holdout conclusions as historical only. *Correctness:* the manifest stays a
  content-addressed record of what was frozen and when. *Research validity:* no post-hoc rule choice, no
  rewriting of history. *Cost:* one new artifact plus the selector implementation. *Failure mode:* two
  manifests coexist and a reader may confuse them - mitigated by explicit `manifest_version` and
  `supersedes` fields and a note in the holdout report.
- **B. Reconcile in place** - supersede the v1 manifest with a supersession record and re-derive the affected
  economic conclusions in place. *Correctness:* one manifest, but it destroys the evidence that the v1
  candidates were frozen under a different rule, and the v1 holdout was already consumed, so "re-deriving the
  conclusions" cannot be done on the same holdout. *Research validity:* highest risk of an implicit
  re-use of the exposed holdout. *Verdict:* rejected - it cannot be executed without re-exposing the holdout.
- **C. Amend the frozen specification** - record the profit-factor rule as the intended rule. *Verdict:*
  rejected. The rule was chosen by the implementation, not by the protocol, and README Section 9 forbids
  substituting a performance-maximizing rule after seeing results; amending the protocol to legitimise a
  post-hoc rule is the same defect with a paper trail.
- **D. (new) Keep the preregistered rule, keep the v1 manifest immutable, and treat the v1 holdout as
  terminal** - adopt A, additionally record the v1 holdout exposure as `EXPOSED_OR_UNKNOWN` with no reuse,
  and require a *new* confirmatory period before any claim. *Verdict:* this is A plus the explicit holdout
  disposition, and it is the recommendation.

### 4. Recommendation (decision)

**Adopt A + D.** The preregistered rule is the only admissible rule for v1+ candidate promotion. The v1
manifest stays immutable and is relabelled (in the new manifest and in the holdout report) as produced under
a non-preregistered rule. A new, separately versioned candidate manifest is published for continuous cycle 0
from the conforming selector. The v1 holdout (`EXPOSED_OR_UNKNOWN`) is never reused as confirmation for the
new cycle; a fresh confirmatory period is required for any new claim.

### 5. Buy-and-hold baseline data source (decision)

Options: (B1) recompute from the frozen candles at selection time; (B2) add baseline fields to every result
record (schema bump, full 497,664-unit re-run); (B3) compute the baseline once per campaign into a separate,
hash-bound baseline artifact that the selector reads.

**Decision: B3, computed with B1 semantics.** A new `research/baselines/<campaign_id>.json` artifact holds,
per asset and per validation fold, the buy-and-hold metrics (daily Sharpe, net return, max drawdown,
turnover, fee/slippage drag) at 1x/2x/3x costs, the data-manifest content hash it was computed from, and
the fold window bounds. The selector consumes that artifact and fails closed when it is missing or when the
data hash no longer matches. B2 is rejected for this cycle (a full re-run for a baseline that can be derived
exactly from frozen, hash-verified candles is not justified); B2 remains the right long-term design if the
baseline must be carried inside each unit, and that is a separate, versioned schema decision.
The other README Section 7 baselines are accounted for as follows: `cash` is a constant-zero series
(Sharpe undefined - never reported as informative), `buyhold_btc` is the same computation for BTCUSDT, and
`fixed_breakout_baseline` is already a member of the 2,304-configuration grid (`cfg_0145`:
classic_high_breakout / 24 / 0.0 / one_close / none / channel_24) so its validation results already exist in
the ledger.

### 6. Conforming selector (in `src/`) - design

- New module `src/breakout_research/selection.py`: `evaluate_candidate(fold_units, spec, baselines) -> gate
  table`, `select_candidates(records, spec, baselines) -> {asset: {status, config_id, gates, ranking}}`,
  implementing exactly the pinned semantics of section 2, with the status taxonomy
  (`CANDIDATE_SELECTED` / `CANDIDATE_SELECTED_WITH_UNEVALUABLE_GATES` / `INSUFFICIENT_EVIDENCE` /
  `NO_CANDIDATE`) and the ranking key (median net daily Sharpe, then median net return, then max drawdown,
  then turnover, then lexicographic config id).
- New module `src/breakout_research/baselines.py`: `buyhold_baseline(candles, fold_windows, cost_scenarios)`
  with the backtester's own cost, daily-return and Sharpe conventions (the same conventions the campaign
  used), plus the data-manifest hash verification.
- `src/breakout_research/candidate_freeze.py`: `select_best_candidate` is replaced by the conforming selector;
  the profit-factor selector is kept only as `_legacy_profit_factor_selector` for provenance, and the freeze
  path writes a new manifest with `rule: "preregistered_v1"`, `rule_spec_hash`, `supersedes`,
  `code_hash`, `data_manifest_hash`, `manifest_hash` and the per-asset gate table.
- **Code-hash coupling:** any `src/` change rotates `compute_code_hash()` and invalidates
  `research_state/campaign_authorization.json`. The implementation session must therefore re-run the pilot
  and re-authorize (`campaign_authorization.json` with a matching code hash) before any further campaign
  execution. No campaign execution may be trusted under the old hash afterwards.
- **Holdout discipline:** the selector consumes only `is_holdout == false` units and must raise on a holdout
  record, exactly as the read-only script does.

### 7. Staged implementation plan and acceptance tests (next session)

1. `src/breakout_research/baselines.py` + `src/breakout_research/selection.py` with unit tests: one test per
   gate (including the `NOT_EVALUABLE` paths), the tiebreak order, the metric conventions pinned against
   `backtester._compute_metrics` / `_compute_daily_returns`, the holdout refusal, and a regression test
   asserting that the conforming rule does **not** reproduce the v1 profit-factor manifest (the divergence
   above is the expected result, not a bug).
2. Baseline artifact for the continuous cycle (`research/baselines/<campaign_id>.json`) generated from the
   frozen, hash-verified candles, with a determinism test (re-run -> byte-identical) and a hash-mismatch test.
3. New versioned candidate manifest for continuous cycle 0 (max 1 candidate per asset, gate table included).
   `research/candidate_manifest.json` (v1) is not modified.
4. Pilot re-run and re-authorization with the new code hash; `campaign_authorization.json` re-derived and
   `compute_code_hash()` compared against it.
5. Holdout report updated to state that the v1 holdout is `EXPOSED_OR_UNKNOWN`, is not reused, and that the
   new candidates are `CANDIDATE_PENDING_HOLDOUT` pending a new confirmatory period.
6. `PYTHONPATH=src python3 -m pytest tests/ -q` green, exit 0; `git ls-remote origin main` == `git rev-parse HEAD`.

**Multiple-testing caveat that must travel with every artifact:** 2,304 configurations per asset are tested
per asset and are strongly correlated; the reported counts of qualifying configurations (up to 166 for one
asset) are trial counts, not independent evidence. A Deflated Sharpe Ratio may be reported only with a
documented formula and reference fixtures, and it supplements rather than replaces a fresh holdout.

### 8. Falsifiers

The recommendation is falsified if any of the following is shown: (a) the pinned interpretation of section 2
contradicts an explicit statement elsewhere in `configs/research_v1.json` or README Section 9;
(b) an independent re-implementation of the preregistered rule on the same 497,664 records produces a
different per-asset selection (the selection is fully determined by the artifact above, so this would
indicate a defect in this record or in the script); (c) the buy-and-hold recomputation from the frozen
candles is shown not to be comparable with the campaign's cost and Sharpe conventions;
(d) a conforming selector is shown to require data that the repository does not hold, other than the
baseline artifact that this decision creates.

### 9. Rollback

The implementation is additive: two new modules, one new baseline artifact, one new versioned candidate
manifest, and a pilot re-run. Rollback is `git revert` of the implementation commit plus re-issuing the
authorization artifact for the previous code hash; the v1 manifest, the shards, the ledger and the exposed
holdout records are never modified, so no evidence is lost by reverting.

### 10. Out of scope of this decision

BRAIN-007 (cycle linkage, checkpoint counter semantics, terminal state for an exhausted universe) remains
`BRAINSTORMING_REQUIRED` and is not decided here. No economic conclusion is claimed or revised by this
record: it is a method decision about how candidates may be promoted, and the exposed v1 holdout is not
reused.

---

## Current phase decision

At initial triage, all five entries were `BRAINSTORMING_REQUIRED`. Revalidated against live source at HEAD `6804546` (code hash `382e314...`): all five BRAIN items are `RESOLVED_VERIFIED`; none is `BRAINSTORMING_REQUIRED`.

- BRAIN-001 — real historical market data path: `RESOLVED_VERIFIED`. `src/breakout_research/data/fetcher.py` has no `generate_synthetic_candles` import/call in the campaign loader path; 18 genuine Binance assets via `data-api.binance.vision` failover (api.binance.com HTTP 451 → failover HTTP 200), all 26,280 closed hourly candles, `fallback_used: false`; XMRUSDT/MATICUSDT excluded for insufficient history with recorded reasons.
- BRAIN-002 — independent pilot authorization: `RESOLVED_VERIFIED`. `pilot_gate_validator.py` is evidence-only (rejects `pilot_passed: true` / `campaign_authorized: true` in evidence); `campaign.run()` calls `_verify_pilot_gate()` which revalidates `campaign_authorization.json` at startup (code hash, spec hash, evidence digest). `authorize_campaign()` → `authorized: true`, zero reasons.
- BRAIN-003 — final-holdout isolation: `RESOLVED_VERIFIED`. `campaign.run(holdout_enabled=False)` skips all final-holdout units (zero holdout rows); holdout mode requires a frozen candidate manifest before any holdout unit executes.
- BRAIN-004 — deterministic resume: `RESOLVED_VERIFIED`. `ResultStore` manifest-derived resume cursor from verified experiment IDs; checkpoint counters treated as untrusted legacy; `_verify_stale_checkpoint` fails closed on protocol/code-hash mismatch; crash-injection tests pass.
- BRAIN-005 — bounded durable results: `RESOLVED_VERIFIED`. Immutable ≤4 MiB JSONL shards via `ShardWriter`/`MAX_SHARD_BYTES`; `results_manifest.json` bound to campaign_id; legacy `research/results.jsonl` (51,688,138 bytes) preserved, never appended; oversized-row fail-closed tested.

All 5 parallel strategy lanes `COMPLETE`. No root cause was implemented in the same session as its design record. Do not launch or trust the full campaign while applicable P0 research-validity blockers remain open — all P0 blockers are now resolved; full-grid validation execution is the next bounded task (max_assets=1 per batch, checkpoint per 50 records, holdout off).

**Revalidation 2026-10-19 UTC (code hash `d0dca29...`, HEAD `63c780c9...`):** BRAIN-001..005 remain `RESOLVED_VERIFIED` — real-data provenance, independent authorization, holdout isolation, manifest-derived resume, and bounded durable shards are all still satisfied in the live tree. Two new items were opened from record-level evidence that the earlier verification loop never produced:

- BRAIN-006 (P0) — `BRAINSTORMING_REQUIRED`. The preregistered selection rule in `configs/research_v1.json` → `selection` is not implemented anywhere; the only selector ranks by median profit_factor and applies none of the preregistered gates, and no buy-and-hold baseline metric exists to support the `median_sharpe_gt_buyhold` gate. The 18 frozen candidates and the v1 holdout conclusions inherit that deviation.
- BRAIN-007 (P1) — `BRAINSTORMING_REQUIRED`. Continuous cycle 0 reproduced the v1 validation sweep metrically exactly (497,664/497,664 units, 0 differences) without linking to it; `research_state/checkpoint.json` counters (497,718) mix 54 exposed-holdout units into a validation completion count; and an exhausted universe advances the cohort counter instead of persisting a terminal `AWAITING_NEW_CANDIDATES`/`BLOCKED_EXTERNAL` state.

Neither new item may be implemented in the session that writes its design decision (README Section 2A C1). The next bounded task is the prerequisite impact quantification for BRAIN-006 — re-derive candidates for continuous cycle 0 under the preregistered rule from the verified validation records and quantify the divergence from `research/candidate_manifest.json` — which is read-only, offline, and holdout-safe. Any later `src/` change rotates the code hash and requires pilot re-run plus re-authorization before further campaign execution.

**Decision update 2026-10-19 UTC (code hash `d0dca29...`, HEAD `a968aa62`):** the BRAIN-006 impact
quantification is complete and the BRAIN-006 decision record has been written (see "BRAIN-006 — Decision
record" above).

- BRAIN-006 (P0) — `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. The preregistered rule is authoritative
  for v1+ candidate promotion; the profit-factor selector is demoted to a provenance record; a new versioned
  candidate manifest is published from a conforming selector; the v1 manifest stays immutable and the v1
  holdout (`EXPOSED_OR_UNKNOWN`) is never reused. Quantified divergence: **16 of 18 frozen v1 candidates fail
  the preregistered gates**; 14 assets qualify, 1 is `INSUFFICIENT_EVIDENCE`, 3 are `NO_CANDIDATE`; only
  ADAUSDT's frozen candidate is also the preregistered winner. The `median_sharpe_gt_buyhold` gate is
  satisfiable from the frozen, hash-verified candle datasets — the baseline was never computed and stored,
  not unavailable.
- BRAIN-007 (P1) — still `BRAINSTORMING_REQUIRED`; the design decision for cycle linkage, checkpoint counter
  semantics and the terminal state for an exhausted universe is still outstanding and is not decided here.

The BRAIN-006 implementation (`src/breakout_research/selection.py`, `src/breakout_research/baselines.py`,
the baseline artifact, the new versioned candidate manifest, pilot re-run and re-authorization) is the next
bounded task and must be executed in a later session than this decision record.

**Out of scope:** ordinary bounded retries for demonstrated transient network errors, routine lint/test failures with an evidence-backed local fix, and recovery bundles/patches needed to preserve interrupted work. Those remain in the normal measured correction loop and are not duplicate durable error records.

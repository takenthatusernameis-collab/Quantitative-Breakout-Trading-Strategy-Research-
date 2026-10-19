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

## BRAIN-007 — Structured design decision (written 2026-10-19 UTC, code hash `00033d38...`, HEAD `c581d155`)

**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. Design only; no `src/`, coordinator, checkpoint or state-machine change in this session (README Section 2A C1).

### 1. Revalidated facts
- Continuous cycle 0 reproduces the v1 validation sweep metrically exactly: 497,664 units in both, 0 unique to either, 0 differing metrics (excluding `stored_utc`, `experiment_id`, `schema_version`).
- `cycle_report.json` for `0f52f6c9...` presents the re-run as a new `COMPLETE` cycle and does not link to the identical prior campaign `fcf04f6e...`, although spec §5 requires linking to verified prior evidence.
- `checkpoint.json` counters (497,718) = 497,664 validation + 54 exposed-holdout units that exist only in the legacy top-level shard set `577e87e2.../`; the continuous cycle holds 0 holdout records.
- Eligible universe holds 18 assets vs `COHORT_SIZE` 20; cohort 1 terminated `DUPLICATE_OR_NO_NEW_CANDIDATES`; `next_cohort_index` is 2; all five universe snapshots are byte-identical.
- `https://api.binance.com/api/v3/ping` → HTTP 451 from this environment (also in `research_state/workflow_run_diagnostics.jsonl`): permanent external boundary here.

### 2. Causal model
Cycle identity is currently implicit: a cycle is whatever the coordinator writes, and its report presents recomputed identical units as a new trial. Checkpoint counters are a single integer that conflates validation units with exposed-holdout units, so `completed_records` cannot be read as "validation complete." The terminal condition for an exhausted universe is unhandled: the coordinator appends an empty cohort to `completed_cycle_ids` and advances `next_cohort_index`, so "no new candidates" is indistinguishable from "more work pending." No artifact distinguishes a linked/recomputed unit from a genuinely new trial, and no artifact records the provider boundary as a terminal state.

### 3. Alternatives compared
| Design | Description | Advantages | Material risks/costs |
|---|---|---|---|
| **A. Ledger-level dedup** | Coordinator detects identical (code, spec, data, unit) work, links to existing verified evidence, and emits a cycle report distinguishing linked vs newly executed units. | Smallest conceptual change; reuses the existing ledger; makes "new trial" explicit. | Dedup key must be frozen and versioned; risks over-claiming linkage if key is too loose; still needs a separate counter fix. |
| **B. Immutable per-cycle ledgers + linkage index (recommended)** | Keep each cycle's shards immutable; add a separate cycle-to-campaign linkage index keyed by (code_hash, spec_hash, data_manifest_hash, universe hash, unit id). Checkpoint counters derived from the verified unit set, never mixing holdout. | Preserves per-cycle auditability; clean separation of execution vs linkage; supports a terminal state without mutating shards. | More artifacts and migration logic; linkage index must itself be hash-bound and verified. |
| **C. Reporting-only reconciliation** | Keep execution behavior unchanged; add a verifier that emits expected-vs-verified and linked-vs-new reconciliation in each cycle report. | Cheapest; no coordinator change. | Does not fix the counter semantics or the empty-cohort terminal state; reports become the only signal, which can be ignored. |

### 4. Recommendation
Select **B**: immutable per-cycle ledgers plus a hash-bound linkage index, with checkpoint counters derived from the verified validation unit set only, and a terminal `AWAITING_NEW_CANDIDATES`/`BLOCKED_EXTERNAL` state recorded (with provider evidence) instead of appending empty cohorts.

Cycle identity rule: a cycle is identified by `(code_hash, spec_hash, data_manifest_hash, universe_hash)`; a unit is *new* only if its `(cycle identity, asset, config_id, fold_index, cost_scenario)` is not already present in a verified prior cycle's linked set. Identical units are recorded as `LINKED_PRIOR_EVIDENCE`, never as new trials, and the cycle report must state linked vs new counts.

Counter semantics: `completed_records`/`last_verified_record` count **validation units only** (`is_holdout == false`); holdout units are tracked in a separate `holdout_exposed_count` field and never enter the validation count. `last_verified_record` is derived from the verified shard manifest, never asserted.

Terminal state: when the eligible universe has fewer assets than `COHORT_SIZE` and no new candidates remain, the coordinator writes `state: AWAITING_NEW_CANDIDATES` (or `BLOCKED_EXTERNAL` when the provider is unreachable), records the provider evidence (HTTP 451), and does **not** append the cycle to `completed_cycle_ids` or advance `next_cohort_index`.

### 5. Falsifiers
- If the linkage key is shown to collide across distinct campaigns, B's index is unsound and A's looser dedup is worse; revise the key.
- If per-cycle immutability prevents any useful linkage (e.g., no prior verified cycle exists), B degrades to C; acceptable, since C is the floor.
- If the provider becomes reachable and yields a genuinely new universe, the terminal state must transition out of `BLOCKED_EXTERNAL` automatically on the next run; otherwise the state machine is wrong.

### 6. Rollback
Revert only the linkage-index and counter changes; preserve all per-cycle shards and the original checkpoint for diagnosis. Never silently reset counters to zero; on any mismatch, reconstruct from the verified shard manifest and emit an integrity report. Rolling back to "present recomputed units as new trials" is not acceptable.

### 7. Staged acceptance tests
1. `PYTHONPATH=src python3 -m pytest tests/ -q` → all pass, exit 0.
2. A unit test proves the linkage index classifies an identical re-run as `LINKED_PRIOR_EVIDENCE` (0 new units) for cycle 0.
3. A test proves holdout units never increment the validation counter.
4. A test proves an exhausted universe (18 assets < `COHORT_SIZE` 20, provider HTTP 451) yields `AWAITING_NEW_CANDIDATES`/`BLOCKED_EXTERNAL` and does not append to `completed_cycle_ids` or advance `next_cohort_index`.
5. A test proves a forged `completed_records`/`last_verified_record` is detected and reconstructed from the shard manifest.
6. No `src/`, `configs/`, shard, ledger, manifest, checkpoint-counter or authorization change in the decision-record session; exactly one prompt review; handoff updated, commit pushed, `git ls-remote origin main` == local HEAD verified.

### 8. External dependency
A genuinely new universe requires a fresh market-cap snapshot and new candles; the universe provider is unreachable from this environment (HTTP 451). This is an external boundary, not an idle wait — record it, do not retry it.

### 9. BRAIN-007 must not be implemented in the session that writes this record (README Section 2A C1). Writing the record is the deliverable.

### 10. Correction of the provider evidence (recorded 2026-10-19T15:43Z, terminal artifact `research/campaign_cycles/terminal/exhausted_cohort_2.json`)

The revalidated fact in §1 and the external dependency in §8 are **superseded by observed
evidence**. The market-cap provider that produced the frozen universe (CoinGecko, recorded
in `research/universe_manifest.json` → `market_cap_source`) answers **HTTP 200** from this
environment; the Binance spot REST host answers HTTP 451 while the official market-data
failover host `data-api.binance.vision` answers HTTP 200. The universe exhaustion is
therefore **not** an external boundary, and §5's falsifier ("if the provider becomes
reachable and yields a genuinely new universe, the terminal state must transition out of
`BLOCKED_EXTERNAL`") is now active: the implementation has been corrected to probe the
provider instead of asserting a status, and the terminal state is
`AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION`. The
falsifier itself stands and is not weakened; only the recorded provider evidence was
wrong. See BRAIN-008 for the decision that the corrected evidence now requires.


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
- BRAIN-007 (P1) — `RESOLVED_VERIFIED`. Implemented linkage index (`src/breakout_research/linkage_index.py`), validation-only checkpoint counters with `holdout_exposed_count` and counter reconstruction/forgery detection in `src/breakout_research/backtest/checkpoint.py`, and a terminal state for the exhausted universe that does not append to `completed_cycle_ids` or advance `next_cohort_index`. **Corrected 2026-10-19T15:43Z:** the terminal state no longer asserts a hard-coded Binance HTTP 451 as "provider evidence"; it records observed provider evidence, and it is now `AWAITING_NEW_CANDIDATES` (the market-cap provider is reachable — see BRAIN-008 (DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)).

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

**Implementation update 2026-10-19 UTC (code hash `00033d38...`, HEAD `0823b880`):** the BRAIN-006 decision
record is now implemented and verified.

- BRAIN-006 (P0) — `IMPLEMENTED_VERIFIED`. `src/breakout_research/selection.py` (gates, status taxonomy,
  ranking/tiebreakers, holdout refusal, parameter-neighbourhood analysis) and
  `src/breakout_research/baselines.py` (buy-and-hold on the campaign's own cost/daily-return/Sharpe
  conventions with data-manifest hash verification) replace the non-conforming first implementation. The
  buy-and-hold baseline artifact `research/baselines/577e87e2...json` is computed from the frozen,
  hash-verified candles (497,664 records read, 0 holdout records, byte-identical on re-run). The new
  versioned manifest `research/candidate_manifest_v2.json` (`rule: preregistered_v1`, `rule_spec_hash
  b7848977...`, `supersedes` the v1 manifest) holds 14 candidates, 1 `INSUFFICIENT_EVIDENCE` and 3
  `NO_CANDIDATE`, and reproduces the independent re-derivation
  `research/campaign_cycles/0f52f6c9.../candidate_selection.json` with 0 mismatches over 18 assets. The
  legacy profit-factor rule survives only as `candidate_freeze._legacy_profit_factor_selector` (provenance)
  and still reproduces the v1 manifest from the same records.
- The pilot was re-run under the new code hash and `research_state/campaign_authorization.json` was
  re-derived for it; the v1 holdout stays `EXPOSED_OR_UNKNOWN`, is never reused, and the v2 candidates are
  `CANDIDATE_PENDING_HOLDOUT` pending a fresh confirmatory period
  (`reports/holdout_disposition_v2.md`).
- `research/candidate_manifest.json` (v1), the shards, the ledger and the 54 exposed holdout records are
  unmodified.
- BRAIN-007 (P1) — still `BRAINSTORMING_REQUIRED`; the cycle linkage, checkpoint counter semantics and the
  terminal state for an exhausted universe are not decided and were not implemented.

**Out of scope:** ordinary bounded retries for demonstrated transient network errors, routine lint/test failures with an evidence-backed local fix, and recovery bundles/patches needed to preserve interrupted work. Those remain in the normal measured correction loop and are not duplicate durable error records.

**Terminal-state correction update 2026-10-19 UTC (evidence recorded 15:43Z):** the terminal
state for the exhausted universe was found to rest on an *asserted* provider status
(a hard-coded Binance HTTP 451 in `continuous_universe_coordinator.py`) for a universe that
is produced by CoinGecko, whose endpoint answers HTTP 200 from this environment, and while
the documented Binance market-data failover answers HTTP 200. The implementation now probes
the provider once per endpoint, records the observed status with a timestamp, and maps the
observation onto the terminal state: `BLOCKED_EXTERNAL` only for a genuinely unreachable
provider, `AWAITING_NEW_CANDIDATES` otherwise. The terminal record is durable in the
repository (`research/campaign_cycles/terminal/exhausted_cohort_2.json`) and documented in
`reports/terminal_state_exhausted_universe.md`.

- BRAIN-007 (P1) — remains `RESOLVED_VERIFIED`; its provider-evidence defect is corrected
  and its own falsifier ("if the provider becomes reachable and yields a genuinely new
  universe, the terminal state must transition out of `BLOCKED_EXTERNAL`") is now satisfied
  by the implementation rather than contradicted by it.
- BRAIN-008 (P0) — `IMPLEMENTATION_IN_PROGRESS`: the market-cap provider is reachable and a
  fresh snapshot yields constituents the frozen universe does not contain (ZEC, HYPE, HBAR)
  while three frozen constituents left the top 20 (DOT, MATIC, ATOM). The campaign now
  waits for a **preregistered universe version**, not for an external party. The decision
  record was written 2026-10-19T15:4xZ; the preregistered v2 specification
  (`configs/research_v2.json`, `specification_hash 49fb0814...`) was produced
  2026-10-19T16:5xZ and satisfies §6 prerequisite 1. Prerequisites 2 and 3 (v2 universe
  manifest and v2 data manifest, built from the in-window snapshot with every constituent
  validated per §3) were delivered 2026-10-19T19:0xZ — 18 constituents validated, HYPE
  excluded for insufficient history, XMR excluded because its spot pair is unavailable.
  Prerequisite 4 (v2 candidate manifest and holdout report) and the v2 holdout execution
  remain outstanding, so no v2 execution is authorized.


---

## BRAIN-008 — The market-cap universe provider is reachable: the "exhausted universe" is a protocol boundary, not an external one

**Priority:** P0 — the campaign's stop condition, universe versioning and cohort semantics
**Status:** `IMPLEMENTATION_IN_PROGRESS` (decision record written 2026-10-19T15:4xZ; §6 prerequisite 1 — the preregistered v2 specification — delivered 2026-10-19T16:5xZ; prerequisites 2 and 3 — the v2 universe manifest and the v2 data manifest with §3 constituent validation — delivered 2026-10-19T19:0xZ; the v2 candidate-set freeze delivered 2026-10-19T21:30Z (§13) and the versioned v2 execution amendment 1 delivered 2026-10-19T22:07Z (§14); the v2 selection run, the selected-configuration manifest, the confirmatory-window evaluation and the v2 holdout report remain outstanding, no execution authorized)
**Cause labels:** `IMPLEMENTATION_DEFECT` (terminal state asserted a provider status it never observed), `RESEARCH_DESIGN_RISK` (universe versioning, cohort composition and cross-cohort comparability are undecided)

### Evidence (observed, 2026-10-19T15:43:31Z)
- The terminal artifact `research/campaign_cycles/terminal/exhausted_cohort_2.json` was produced by the implementation. The `provider_evidence.universe_snapshot_provider` records CoinGecko **HTTP 200** (67 ms) for the exact endpoint frozen in `research/universe_manifest.json` → `market_cap_source.endpoint`. `candle_data_providers` records `api.binance.com` **HTTP 451** (114 ms) and `data-api.binance.vision` **HTTP 200** (662 ms). Each probe is one bounded read-only request with timestamp.
- The previous implementation hard-coded `{"status": 451, "reachable": false}` for the universe provider evidence in `continuous_universe_coordinator.py`; the status was never observed at write time. The corrected code now probes the actual provider.
- A fresh market-cap snapshot differs from the frozen one (frozen 2026-10-15T17:10:38Z): new constituents `zcash` (ZEC), `hyperliquid` (HYPE), `hedera-hashgraph` (HBAR); frozen constituents that fell out of the top 20: `polkadot` (DOT), `matic-network` (MATIC), `cosmos` (ATOM). At least 20 further constituents are listed below the frozen depth.
- The frozen universe holds 20 Binance-spot-verified constituents, 18 of which satisfy the ≥ 3-year history requirement (`COHORT_SIZE` = 20); cohort index 2 is empty.
- The new constituents are **not** data-validated: no Binance spot verification, no candle fetch, no history check, no backtest (`candidates_are_data_validated: false`). In particular, HYPE and XMR are likely to fail the frozen data requirements.
- The terminal state is `AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`; `BLOCKED_EXTERNAL` is reserved only for a provider that is actually unreachable.

### 1. Authoritative universe-versioning rule
**Principle:** The frozen universe (`research/universe_manifest.json`, protocol v1) is immutable. Any change to the evaluated universe (admitting new constituents, dropping frozen ones, or changing depth) requires a **separately preregistered universe version** (e.g. `universe_v2`) with its own snapshot identity, bound to the frozen specification and to the code/data hashes. The v1 artifacts (`universe_manifest.json`, `candidate_manifest.json` v1, all v1 shards/ledgers, the 54 exposed holdout records) remain immutable and historical.

**Snapshot identity:** a universe version is identified by `(protocol_version, universe_version, specification_hash, market_cap_source_endpoint, market_cap_source_retrieval_timestamp_utc, code_hash, data_manifest_hash, candidate_manifest_manifest_hash)` recorded in any artifact that freezes candidates under it. For v2, `supersedes` references the v1 universe manifest identity.

### 2. Changed market-cap ranking: rule and comparability
**Rule (adopted):** Treat a genuine re-ranking (new `coingecko_id`s present; frozen `coingecko_id`s missing from the candidate set for the same evaluation depth after applying `exclusion_rules`) as requiring a **new universe version (v2)**. Do **not** silently extend the v1 cohort or overwrite `universe_manifest.json`.

**Comparability statement:**
- Cycle 0’s 497,664 units (all validation-only, 0 holdout) are tied to v1 universe + v1 grid + v1 data; they are **not** comparable to results produced under v2 without a bridging analysis. The 14 v2 candidates in `research/candidate_manifest_v2.json` remain `CANDIDATE_PENDING_HOLDOUT` and must not be mixed into cycle-0 tallies.
- The 14 v2 candidates are per-asset candidates for v2; their promotion to “selected” status under a preregistered v2 rule does not retroactively validate v1 candidates. No claim is made that the frozen v1 candidates are “rejected” or “confirmed” by this re-ranking.

### 3. Data-requirement validation plan for new constituents
For each new constituent (not in v1 eligible set), before admitting it to any v2 frozen universe or to candidate evaluation:
- **Binance spot verification:** confirm the trading pair `<SYMBOL>USDT` exists on Binance spot and is tradeable at the time of snapshot (record verification timestamp, endpoint used). `api.binance.com` may return HTTP 451 in some environments; use the documented failover `data-api.binance.vision` and record both results if probed; do **not** blindly retry the primary host.
- **Candle history:** fetch or verify ≥ 26,280 closed hourly candles (3 years) for the pair using the same candle path convention as the campaign (record which endpoint, count, first/last close time, coverage gaps). If coverage < required, **exclude** (do not interpolate).
- **Data integrity:** the constituent’s candles must be hash-verifiable against a v2 `research/data_manifest_v2.json` (or the appropriate data manifest for v2). Survivorship, exchange delisting, and split adjustments follow the v1 protocol unless v2 preregisters a change.
- **Exclusion rules:** apply `exclusion_rules` from the v2 universe manifest (stablecoins, wrapped/bridged, leveraged/synthetic, exchange tokens, liquidity rules) before evaluation; record `exclusion_reason` if excluded.
- **Constituents that fail any requirement:** mark as excluded in the v2 universe manifest; do **not** promote them. ZEC/HYPE/HBAR and any others are **unvalidated** now — they must pass all checks before use.

### 4. Confirmatory-holdout plan for v2 candidates
- The 14 candidates in `research/candidate_manifest_v2.json` remain **`CANDIDATE_PENDING_HOLDOUT`**. The v1 holdout is `EXPOSED_OR_UNKNOWN` and is **never reused** as confirmation for v2.
- A **fresh, unexposed confirmatory window** (not overlapping the v1 holdout window, and not using any data that informed the v2 candidate selection) must be evaluated before any claim of out-of-sample confirmation. The holdout period, the data cutoff (after candidate freeze time), the assets evaluated, and the exposure status must be recorded in a v2 holdout report.
- No campaign/grid execution using v2 candidates for live/trusted confirmation is authorized in this session; promotion to “confirmed” requires a separate decision with evidence.

### 5. Alternatives considered
A. **Freeze and wait (defer)** — keep v1 immutable, record terminal state, stop. *Pros:* zero risk of comparability contamination, preserves v1 evidence. *Cons:* defers decision; rankings may change. **Selected as the default unless a preregistered v2 exists.**
B. **New versioned universe (v2 protocol)** — separate preregistered spec for v2 (universe, selection rule pinned, grid unchanged or re-specified, holdout rules, data manifest). *Pros:* clean separation, allows admitting validated new constituents. *Cons:* requires preregistration, data validation work, new artifacts; cannot reuse v1 holdout. **Recommended if v2 is pursued.**
C. **Supplementary cycle inside v1 protocol** — extend v1 without version bump. *Pros:* simplest. *Cons:* violates “preregistered universe version” and README Section 2A F (evidence retention/versioning); changes evaluated universe without protocol version change. **Rejected.**

### 6. Recommendation
**Adopt A (defer) as the immediate action.** Do not create v2 artifacts beyond what already exists (`candidate_manifest_v2.json` is a read-only analysis artifact produced under the conforming selector’s analysis path; it must not be treated as a frozen, preregistered v2 universe for execution). The campaign stops at `AWAITING_NEW_CANDIDATES` with the observed evidence. Any move to v2 requires:
1. A preregistered v2 specification (universe, selection, data requirements, holdout) recorded in `configs/` or an equivalent immutable spec with hash.
2. A v2 universe manifest built from a fresh snapshot with all new constituents validated per §3.
3. Data manifest v2 and candle verification artifacts.
4. Explicit comparability statement and v2 holdout plan per §4.
5. No re-use of v1 holdout; no mixing of v2 results into cycle-0 tallies.

Until (1)-(5) are satisfied, the correct state is terminal/awaiting a decision; execution is not authorized.

### 7. Falsifiers
- If we claim v2 is “active” without a preregistered v2 spec and validated constituents, the claim is false.
- If we reuse v1 holdout for v2 candidates, that violates §4.
- If we treat `candidate_manifest_v2.json` (analysis) as an execution manifest without `supersedes`, `universe_version`, `manifest_version` and validation evidence, that violates versioning.
- If `BLOCKED_EXTERNAL` is asserted when the universe provider is reachable (CoinGecko HTTP 200), that’s the defect already fixed — the falsifier from BRAIN-007 §5 remains active.

### 8. Rollback
- No code change in this decision session; rollback is trivial (no new execution path). If any execution artifacts for v2 are created prematurely, delete them and revert any spec changes. Never delete v1 artifacts.
- The coordinator’s terminal-state change (probe the provider, record evidence) is already committed and correct; reverting it would re-introduce the asserted-status defect.

### 9. Staged acceptance tests
1. `PYTHONPATH=src python3 -m pytest tests/ -q` → all pass, exit 0.
2. The terminal artifact `research/campaign_cycles/terminal/exhausted_cohort_2.json` records CoinGecko HTTP 200 and Binance failover HTTP 200, with timestamps; state is `AWAITING_NEW_CANDIDATES`.
3. `python3 -c "
import json
d=json.load(open('research/campaign_cycles/terminal/exhausted_cohort_2.json'))
assert d['state']=='AWAITING_NEW_CANDIDATES'
assert d['blocking_dependency']=='UNIVERSE_VERSION_DECISION'
assert d['provider_evidence']['universe_snapshot_provider']['http_status']==200
print('ok')
"` exits 0.
4. BRAIN-008 record names: universe-versioning rule (§1), ranking rule + comparability (§2), validation plan (§3), holdout plan (§4), alternatives (§5), recommendation (§6), falsifiers (§7), rollback (§8), staged acceptance tests (§9).
5. No `src/`, `configs/`, shard, ledger, manifest (v1/v2 analysis manifest except read-only), checkpoint-counter, or authorization change in this session.
6. Exactly one prompt review (if any). Handoff updated, commit pushed, `git ls-remote origin main` == local HEAD verified.
### 10. BRAIN-008 must not be implemented in the session that writes this decision record (README Section 2A C1)

Writing the record is the deliverable. Implementation (creating a preregistered v2 spec, validating constituents, wiring execution) is a separate session.

### 11. Decision taken and implementation progress — 2026-10-19T16:5xZ (separate session from the decision record)

**Decision:** option **B** (new versioned universe, §5 B) is selected for the *rule-freezing* step only, with
option **A** (defer) still governing everything that would require data or execution. Concretely: this
session produced the preregistered v2 specification required by §6 prerequisite 1, and nothing else. The
campaign's terminal state is unchanged, no v2 artifact was created beyond that specification, and no v2
data was retrieved.

**Why not A alone.** Four consecutive sessions (16:25Z, 16:31Z, 16:43Z, 16:45Z) revalidated the terminal
state and deferred the same decision without producing a new durable artifact. README Section 2A C1 states
that the brainstorming phase is "a time-bounded decision gate, not permission to park a blocker
indefinitely". The blocker is not external — the market-cap provider answers HTTP 200 and the Binance
market-data failover answers HTTP 200 (observed 2026-10-19T15:43:31Z) — so the only thing that can clear
it is a preregistered universe version, and that artifact can be written without touching a single frozen
v1 object.

**Why the specification is written now and not later.** §4 requires the v2 confirmatory window to start
*after* the v2 candidate freeze. Preregistration is only meaningful while the rules are still ahead of the
data they will be applied to; deferring the freeze moves it closer to (or past) the window it governs. The
specification therefore pins a fixed retrieval window (2026-10-19T16:52:00Z → 2026-10-26T16:52:00Z) in
which the single v2 snapshot must be taken, so the membership cannot be chosen after the rules were
written.

**Delivered (prerequisite 1, `SATISFIED_BY_THIS_SPEC`):**
- `configs/research_v2.json` — the preregistered v2 specification. `specification_hash`
  `49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721` over the canonical content of the
  document (key `specification_hash` removed), verifiable with
  `python3 scripts/verify_research_v2_spec.py`. It implements §1 (versioning rule, snapshot-identity
  tuple), §2 (comparability statement), §3 (data-requirement validation plan as rules) and §4
  (confirmatory-holdout plan) as *rules*; it contains no asset membership, no data and no result.
- `scripts/verify_research_v2_spec.py` — read-only, offline verifier (exit 0/1, JSON report).
- `tests/test_research_v2_spec.py` — 14 deterministic tests: hash recomputation, tamper detection,
  byte-equality of every inherited block against v1, the 2,304-combination grid, v1 artifact immutability,
  absence of asset membership, the unvalidated candidates (ZEC/HYPE/HBAR) not being treated as eligible,
  the v1-holdout-reuse prohibition, the status vocabulary, the comparability statement, the outstanding
  prerequisites and the untouched v1 campaign authorization.

**Methodology unchanged.** Every block v2 inherits from v1 — `strategy_grid`, `costs`, `execution`,
`folds`, `selection`, `pilot`, `metrics`, `baselines`, `fixed_breakout_baseline`, `status`,
`checkpointing` — is byte-equal to the v1 block, and the tests enforce that. The 2,304-configuration
grid, the cost scenarios, the fold structure, the selection gates and the economic status vocabulary are
unchanged, so v2 differs from v1 in *what is evaluated* and *how confirmation is obtained*, not in how a
strategy is measured (README Section 2A F).

**Still outstanding — no execution is authorized (§6 prerequisites 2–5):**
- P2: `research/universe_manifest_v2.json`, built from one snapshot taken inside the pinned retrieval
  window, with every new constituent validated per §3 (Binance spot verification, ≥ 26,280 closed hourly
  candles, hash-verified data manifest, exclusion rules). ZEC/HYPE/HBAR remain **unvalidated**.
- P3: `research/data_manifest_v2.json` and the candle verification artifacts.
- P4: the v2 holdout *report*, which can only be produced after the confirmatory window is evaluated.
- P5: enforced as binding rules by this specification and its tests.

**Falsifiers for this decision.** If the v2 snapshot inside the pinned window yields no new eligible
constituent after §3 validation, the correct outcome is a documented `NO_NEW_ELIGIBLE_CONSTITUENT` with
evidence, not a silent extension of v1. If the v1 holdout is ever reused as confirmation, or if v2 results
are tallied with the 497,664 v1 cycle-0 units, this decision is void.

### 12. Decision implemented — §6 prerequisites 2 and 3 delivered (2026-10-19T19:0xZ, separate session)

**Delivered.** The v2 universe manifest and the v2 data manifest now exist, are hash-bound and are
verified offline. No v2 execution, grid, backtest or candidate selection was performed, and no
confirmatory-window candle was read.

**The snapshot (P2 input).** `research/v2_evidence/raw_market_cap_response.json`, sha256
`c4772c58d03c94df6ae98dc31bb3996de2c90c007a2ef7f72a0a92449fb1dbad` (78,557 bytes), retrieved
2026-10-19T18:47:56Z from the frozen CoinGecko endpoint — inside the pinned window
(2026-10-19T16:52:00Z → 2026-10-26T16:52:00Z), which opened when the specification was frozen. The
earlier 15:43:31Z observation remains prior evidence only and is not the v2 universe. The v2 manifests
record this retrieval, its raw hash and its timestamp; the previously recorded 16:52:00Z digest
(`926fad78…`) was never backed by stored bytes and has been replaced.

**Membership rule applied.** The evaluation depth is the top 20 assets by market capitalization *after*
the `exclusion_rules` are applied, exactly as the campaign's own universe provider does. Twelve assets
were removed by rule and recorded with their reason (`stablecoin_excluded` for USDT/USDC/USDS/USDE/DAI/USD1,
`exchange_token_excluded` for FIGR_HELOC/WBT/LEO/RAIN/CC/GRAM). The resulting candidate set is identical
to the 15:43:31Z candidate id list.

**§3 validation results (one bounded request per host; both statuses recorded):**

| outcome | assets | evidence |
| --- | --- | --- |
| validated | BTC ETH BNB XRP SOL TRX ZEC DOGE LINK ADA NEAR XLM BCH LTC UNI AVAX SUI HBAR (18) | Binance spot `TRADING` + 26,280 closed hourly candles, no gaps, 0 rejected rows, canonical CSV hashed `sha256-canonical-hourly-csv-v1` in `research/data/candles_v2/` |
| excluded — `insufficient_hourly_history` | HYPE | Binance spot `TRADING`, but only 607 closed hourly candles; the 26,280 floor was not lowered and nothing was interpolated |
| excluded — `binance_spot_unavailable` | XMR | the `<SYMBOL>USDT` pair is not tradeable on Binance spot at verification time |

**ZEC and HBAR are now validated** (they were the unvalidated candidates named in §3); **HYPE is not**
and stays excluded. This is the first evidence-based resolution of the ZEC/HYPE/HBAR question.

**Artifacts.**
- `research/universe_manifest_v2.json` — `manifest_hash 4e927e52…`; snapshot-identity tuple, per-candidate
  outcome and exclusion reason, exclusion rules copied byte-equal from the v1 manifest, `supersedes`
  pointing at the v1 universe and candidate manifests by sha256.
- `research/data_manifest_v2.json` — `manifest_hash 9f64d8d1…`; per-asset provenance (endpoint used,
  endpoint failures, request count, first/last candle timestamp, expected/observed counts, gaps, rejected
  rows, content hash, dataset path), `content_hashes`, exclusion reasons, spot-verification evidence,
  `holdout_exposed_count = 0`, `confirmatory_window_status = NOT_STARTED`.
- `research/v2_evidence/` — the raw market-cap response, its observation, the per-pair spot-verification
  evidence and the per-asset candle-verification evidence.
- `scripts/v2_constituent_validation.py` — the bounded, re-runnable producer of the two manifests.
- `scripts/verify_research_v2_manifests.py` — read-only offline verifier (exit 0/1, JSON report).
- `tests/test_research_v2_manifests.py` — 13 deterministic tests (identity tuple, in-window snapshot,
  self-hashes, dataset re-hashing, exclusion reasons, v1 immutability, no candidate manifest, no
  confirmatory exposure).

**Reproducibility.** The candle window is bound to the snapshot timestamp (the last fully closed hour at
2026-10-19T18:47:56Z) rather than to the wall clock, so re-running the validation reproduces
byte-identical datasets instead of silently sliding the window forward. Re-running does refresh the
manifests' own validation timestamps; the producer refuses to rewrite a manifest that already records the
same snapshot unless `--force` is given.

**Still outstanding — no execution is authorized.**
- P4: the v2 holdout *report*, which can only be produced after a v2 candidate manifest is frozen and the
  confirmatory window is evaluated. The window needs ≥ 2,160 closed hourly candles *after* the candidate
  freeze, so it cannot exist yet: the earliest possible start is the freeze date plus 90 days.
- The v2 candidate manifest itself: selection needs a v2 grid run, which no recorded decision authorizes.
  `research/candidate_manifest_v2.json` remains manifest_version 2 of the v1 campaign and is not a
  v2-universe manifest.
- The frozen specification still records P2/P3 as `OUTSTANDING`. It is immutable and hash-verified, so
  that text is not rewritten here; flipping it requires a versioned amendment.

**Falsifiers for this delivery.** If the stored snapshot hash does not match the digest recorded in the
manifests, or if the retrieval timestamp falls outside the pinned window, the manifests are invalid and
must be discarded. If any validated dataset fails to re-hash to its recorded content hash, the affected
constituent is not validated. If the v1 artifacts no longer match the recorded `supersedes` digests, the
v2 manifests are invalid.


### 13. Decision implemented — v2 candidate set frozen (2026-10-19T21:30:17Z, separate session)

**Delivered.** The v2 candidate set is frozen, hash-bound and verified offline. No grid, backtest,
selection or confirmatory-window read was performed, and no v1 artifact was modified.

**The freeze.** `configs/research_v2_candidate_freeze.json`, `manifest_hash`
`5a56b3d801519bbda0ed534cd031d0cb4204c1c015e5accb6fbc4e9bd0ec123f`, frozen at
**2026-10-19T21:30:17Z**. It records:

- **the candidate set** — exactly the 18 validated constituents of universe version v2 (ADA AVAX BCH BNB
  BTC DOGE ETH HBAR LINK LTC NEAR SOL SUI TRX UNI XLM XRP ZEC), bound to `research/universe_manifest_v2.json`
  `4e927e52…` and `research/data_manifest_v2.json` `9f64d8d1…`. Membership is not re-derived, re-ranked or
  widened; HYPEUSDT (`insufficient_hourly_history`) and XMRUSDT (`binance_spot_unavailable`) stay excluded
  with their reasons, and the 12 rule-excluded assets are listed with theirs.
- **the snapshot-identity tuple** (§1) — `protocol_version v2`, `universe_version v2`, `specification_hash
  49fb0814…`, the frozen CoinGecko endpoint, the in-window retrieval `2026-10-19T18:47:56Z`, `code_hash
  2efd3b18…`, `data_manifest_hash 9f64d8d1…` and `candidate_manifest_hash` = this artifact's own
  `manifest_hash`. The tuple's last field is the artifact's own hash: the digest is computed with
  `manifest_hash` and `snapshot_identity.candidate_manifest_hash` removed, so the tuple can name the
  candidate-manifest hash without hashing itself into a cycle (the convention already used by
  `research/data_manifest_v2.json`).
- **the data boundary** — the confirmatory window opens at the first UTC hour boundary strictly after the
  freeze, `2026-10-19T22:00:00Z`, needs ≥ 2,160 closed hourly candles (90 days), so the earliest possible
  window end is `2027-01-17T22:00:00Z`. The window is single-use, never overlaps the v1 holdout, is never
  read during candidate selection, and every read increments `holdout_exposed_count`.
- **the supersession** — `research/candidate_manifest.json` (sha256 `87589f83…`, `manifest_hash
  9ea6b1c3…`, freeze commit `3e937dd3…`) is superseded for evaluation purposes and remains immutable
  historical evidence. `research/candidate_manifest_v2.json` is recorded explicitly as *not* a v2-universe
  candidate manifest: it is manifest_version 2 of the v1 campaign, its candidates remain
  `CANDIDATE_PENDING_HOLDOUT` against the v1 universe, and it is not superseded by this freeze.

**What this freeze does not do.** It freezes the candidate *set*, not a selected configuration. The
per-asset selected-configuration manifest (≤ 1 candidate per asset, under the unchanged v1 selection block)
is still `OUTSTANDING`: producing it requires a v2 grid run, which no recorded decision authorizes. The
freeze therefore authorizes nothing — `grid_run_authorized`, `candidate_selection_authorized`,
`confirmatory_evaluation_authorized` and `candle_fetch_authorized` are all `false` — and the
confirmatory-window evaluation additionally requires the selected-configuration manifest to be committed
and hash-bound first.

**A confirmed defect in the delivered execution protocol.** `configs/research_v2_execution.json` names
`src/breakout_research/v2/` as an example of v2 execution code that lives "outside the hashed set". That
path is **inside** it: `compute_code_hash()` (`src/breakout_research/config.py:257`) walks every `.py` file
under `src/breakout_research` recursively, so any file added there changes the code hash and invalidates
the v1 campaign authorization. The execution protocol is immutable and hash-bound, so it was not edited;
the correction is carried in the freeze's `code_hash_constraint` block (which names only genuinely
outside paths: `scripts/`, `src/v2_campaign/`) and must be formalized by a versioned amendment before any
v2 execution code is written. Until then, the v1 campaign authorization stays bound to `code_hash
2efd3b18…`.

**Artifacts.**
- `configs/research_v2_candidate_freeze.json` — the frozen candidate set and data boundary.
- `scripts/build_v2_candidate_freeze.py` — the deterministic producer (the freeze instant is pinned; it
  refuses to overwrite an existing artifact without `--force`).
- `scripts/verify_research_v2_candidate_freeze.py` — read-only offline verifier (exit 0/1, JSON report).
- `tests/test_research_v2_candidate_freeze.py` — 27 deterministic tests, including seven tamper tests that
  prove the verifier is not vacuous (a widened candidate set, a window that starts before the freeze, a
  self-authorizing freeze, a widened universe manifest, a v2 execution artifact, a v2 result row, a
  confirmatory exposure and a missing v1 artifact are each detected).

**Still outstanding — no execution is authorized.** The v2 grid run and the selected-configuration
manifest; the v2 confirmatory-window evaluation; the v2 holdout report; the versioned amendment that
formalizes the code-hash path rule and records the bounded authorization for a selection run. The v2
specification is immutable and still records P2/P3 as `OUTSTANDING`; flipping that requires a versioned
amendment.

**Falsifiers for this delivery.** If the frozen set stops matching the validated constituents of the v2
universe manifest, or the recorded identity tuple stops matching the specification, the manifests or the
current source tree, the freeze is invalid. If the confirmatory window ever opens before the freeze, or
if a v2 result row, shard, ledger or result manifest appears, the freeze has been violated. If the v1
artifacts no longer match their recorded digests, the freeze is invalid.


### 14. Decision implemented — versioned v2 execution amendment 1 delivered (2026-10-19T22:07Z, separate session)

**Delivered.** `configs/research_v2_execution_amendment_1.json`, `manifest_hash`
`1149d9cb3ee9ea35f16512502c43c4cf0ee13b0ae2fb91e2dc691663b99195db`, with a read-only offline verifier
(`scripts/verify_research_v2_execution_amendment_1.py`, exit 0) and 32 deterministic tests
(`tests/test_research_v2_execution_amendment_1.py`, all passing). No grid, backtest, campaign, selection
or confirmatory-window read was performed; no v1 artifact was modified; `src/breakout_research/` was not
touched; the market-cap snapshot was not re-retrieved.

**What it records.** (1) The corrected code-hash constraint: the hashed set is
`src/breakout_research/` and *every* path under it — including `src/breakout_research/v2/` — is inside
it, so v2 execution code may not be written there without a recorded v1 re-authorization; the genuinely
outside paths are named (`scripts/`, `src/v2_campaign/`). (2) The bounded parameters a future v2
selection grid run over the 18 frozen constituents would have to satisfy: the scope bound to the v2
universe, data and freeze hashes, the development-data boundary at the frozen confirmatory-window start
`2026-10-19T22:00:00Z`, the v2 shard/ledger/results/checkpoint paths with the v1 paths forbidden, the
unchanged v1 selection rule, concrete bounds (18 assets, 2,304 configurations per asset, 41,472 units,
one attempt), the stopping conditions, the rollback rule and the falsifiers. (3) That it authorizes
nothing: `authorized: false`, `no_execution: true` and all four `execution_authorization` flags `false`.

**Correction C1 — the protocol's code-hash path rule.** `configs/research_v2_execution.json` offers
`src/breakout_research/v2/` as v2 execution code that lives "outside the hashed set". It does not:
`compute_code_hash()` walks every `.py` file under `src/breakout_research` recursively. The protocol is
immutable and hash-bound, so its defective text is preserved as historical evidence; the correction is
carried in the amendment and in the freeze's `code_hash_constraint` block.

**Correction C2 — the code hash is not portable (new finding, evidenced).** `compute_code_hash()` hashes
the files of each directory in sorted order but visits the directories in **filesystem enumeration
order**, so the digest of an unchanged, git-clean tree depends on the machine. Evidence from this
session: the authorized digest `2efd3b18…` is reproduced only under the traversal order
(`indicators`, `utils`, `signals`, `data`, `backtest`) — verified by brute-forcing all 120 permutations
of the five sub-directory blocks — while a fresh checkout of the same tree enumerates it as
`608c7340…`. Consequences in this checkout: `scripts/verify_research_v2_manifests.py` and
`scripts/verify_research_v2_candidate_freeze.py` exit 1, and six pre-existing tests fail, **all** with
the message that the recorded code hash "does not match the current source tree". The source tree is
unchanged (`git status` clean under `src/`; the last `src/` commit is `ea5da766`, 15:46Z, before every
v2 artifact was frozen). The failure signal is therefore misleading: it looks like source drift and is
not. The amendment records a portable identity for the hashed set —
`canonical_source_digest` (`3e8e4169…`, path-and-content sorted) — and states that a mismatch of the
live ordered digest alone is evidence of enumeration order, not of a modified tree. **The decision on how
to correct this for the already-frozen v2 artifacts (and whether `compute_code_hash()` itself must be
rotated, which would require a v1 re-authorization and amendments to the v2 identity tuples) is
outstanding and must not be implemented in this session.**

**A corrected digest in the delivered amendment.** The amendment drafted in the 22:00Z session recorded
`amends.file_hash = aa902aa935cfb71cce72bd643bb9685333860ec5470b02b12282c0f1659d67e6` and its verifier
compared that field against the same literal. Read from the bytes on disk,
`sha256(configs/research_v2_execution.json) = dd45f840…` and the protocol's own `specification_hash =
aa902aa9e6ddfd7f…`; the recorded value matched neither, and the check was vacuous because its expected
value was copied out of the artifact under test. The finalized amendment records both digests under
distinct names (`amends.file_sha256`, `amends.specification_hash`) and the verifier recomputes each from
the repository. The interim artifact was never committed and is not referenced by any other artifact;
the finalized `manifest_hash` above is the only hash of this amendment that is recorded.

**Falsifiers for this delivery.** If the amendment's `manifest_hash` does not recompute, or if the
verifier stops reporting the amended protocol's file digest or `specification_hash`, the amendment is
invalid. If the authorized scope stops matching the frozen candidate set, or the excluded assets reappear
in it, the amendment is invalid. If a v2 shard, ledger, result manifest, result stream or checkpoint
appears, or a v2 result row is written, the amendment's nothing-runs state is violated. If the hashed
source tree stops matching `canonical_source_digest`, the tree changed. If the v1 artifacts stop matching
their recorded digests, the amendment is invalid.

---

## BRAIN-009 — Code-hash portability: ordered digest is checkout-dependent

**Priority:** P0 — blocks honest verification of the hashed source set
**Status:** `IMPLEMENTED_AND_VERIFIED` (decision implemented 2026-10-19T23:5xZ; see "Implementation record" below)
**Cause labels:** `IMPLEMENTATION_DEFECT`, `PERMANENT_PLATFORM_LIMIT` (filesystem enumeration order)
**Confidence:** direct evidence confirmed — a permutation brute-force over the 120 directory orderings of the five sub-directory blocks reproduces the authorized digest under exactly one of them, `(indicators, utils, signals, data, backtest)`; the canonical digest reproduces under all of them. (The 22:07Z session recorded "6 of 120"; that figure came from a less faithful replica and is corrected here — see the implementation record.)

### Evidence
- `compute_code_hash()` (`src/breakout_research/config.py:257-268`) hashes each directory's files in sorted order but visits directories in filesystem enumeration order.
- The authorized digest `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` (recorded in `research_state/campaign_authorization.json`) reproduces only under the traversal order `(indicators, utils, signals, data, backtest)` — **1 of the 120** permutations of the five sub-directory blocks reproduces it (corrected 2026-10-19T23:5xZ; the 22:07Z session recorded 6 of 120 from a replica that did not reproduce the live digest under the actual filesystem order, so its count was not evidence). The replica used for the correction reproduces `compute_code_hash()` exactly under the checkout's real enumeration order, which was checked before the brute force.
- A fresh checkout of the same git-clean tree enumerates the directories as `608c7340fa8524921e9378626ac9cd0387f0fad0274e6fa0213a006f47487925`.
- `src/` did not change: last `src/` commit `ea5da766` (15:46Z), before every v2 artifact was frozen; `git status` clean under `src/`.
- The portable identity `canonical_source_digest = 3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff` (path- and content-sorted) is already recorded in `configs/research_v2_execution_amendment_1.json`.
- Consequences: 6 tests and 2 verifiers report a false "source hash does not match the current source tree" message; `scripts/verify_research_v2_manifests.py` and `scripts/verify_research_v2_candidate_freeze.py` exit 1 in this checkout.

### Factual correction
1. The ordered digest is checkout-dependent: a live ordered-digest mismatch alone is **not** evidence of source drift.
2. The portable identity of the hashed set is `canonical_source_digest` (`3e8e4169…`, path- and content-sorted), already recorded in the amendment.
3. A red ordered-digest comparison is an environment fact, not a source-drift signal.

### Tree-identity check from now on
Compare against the canonical digest (portable) and cross-check the recorded digest against `research_state/campaign_authorization.json` `code_hash`, instead of comparing the recorded digest with the live ordered digest. Affected artifacts and their new assertions:
- `scripts/verify_research_v2_manifests.py`, `tests/test_research_v2_manifests.py` — assert canonical digest matches `3e8e4169…`; treat ordered mismatch as environment fact.
- `scripts/verify_research_v2_candidate_freeze.py`, `tests/test_research_v2_candidate_freeze.py` — same, against the recorded canonical digest.
- `scripts/build_v2_candidate_freeze.py` — record canonical digest only; never recompute ordered digest as identity.
- `tests/test_research_v2_spec.py` — canonical digest assertion replaces ordered-digest assertion.

### What happens to the already-frozen v2 artifacts
They record `code_hash 2efd3b18…` and stay immutable. **Recommendation: retain the historical digest as the authorized value of record**, with the canonical digest added by versioned amendment. Rotating `compute_code_hash()` and re-authorizing the v1 campaign (option c) would require changes to `research_state/campaign_authorization.json`, `research_state/checkpoint.json` and every v2 identity tuple, plus an amendment to each frozen artifact — disproportionate and unnecessary because the canonical digest already identifies the tree portably.

### Interim rule until implemented
`src/breakout_research/` must not be edited to "fix" the red tests; that would change the hashed set and invalidate the v1 campaign authorization. A red ordered-digest comparison is to be reported as an environment fact, not as source drift.

### Designs
A. **Retain authorized digest + canonical digest (recommended).** Keep `2efd3b18…` as authorized value of record; add canonical digest by versioned amendment; fix verifiers/tests to compare canonical.
B. **Rotate `compute_code_hash()` to canonical ordering + re-authorize v1 campaign.** Changes hashed set semantics, requires re-authorization and amendments to all v2 identity tuples.
C. **Drop code-hash binding entirely.** Removes the guarantee; unacceptable for research validity.

### Falsifying evidence
- If `canonical_source_digest` fails to reproduce across checkouts with differing directory enumeration order.
- If a source-tree edit is detected by canonical digest but missed by ordered digest (or vice versa).

### Rollback
Revert the verifier/test changes; frozen artifacts untouched. No data or identity changes.

### Staged acceptance tests (later implementation session)
- `compute_code_hash()` ordered digest may differ by checkout; canonical digest stable.
- All six previously red tests pass against canonical digest.
- `scripts/verify_research_v2_spec.py`, `verify_research_v2_execution.py`, `verify_research_v2_execution_amendment_1.py` exit 0.
- `configs/research_v2_execution_amendment_1.json` still hashes to `1149d9cb…`; `src/` untouched.

### Do NOT (this session)
Edit anything under `src/breakout_research/`; edit `research_state/campaign_authorization.json` or `research_state/checkpoint.json`; edit any frozen artifact; run any v2 grid/backtest/campaign/selection/pilot; read any confirmatory-window candle; re-run `scripts/v2_constituent_validation.py` or `scripts/build_v2_candidate_freeze.py`.

---

## BRAIN-009 implementation record — 2026-10-19T23:5xZ

**Task:** implement the BRAIN-009 decision in rules only (design-to-code, no execution).

**Outcome:** implemented and verified. The tree-identity check is now the portable canonical digest;
the ordered digest is reported as an environment fact. The canonical digest was added to the frozen v2
artifacts **by versioned amendment**, not by editing them.

**Delivered**
- `configs/research_v2_code_hash_amendment_1.json` — the versioned, self-hashed amendment
  (`manifest_hash 4409b6af54acb2982e1f286f9c6ebd1ce1b7628a90c476dede6da3c04d8762c1`). It retains the
  authorized ordered digest `2efd3b18…` as the value of record, records the canonical digest
  `3e8e4169…` and its algorithm, names the five frozen artifacts it extends with their file digests
  and their identity hashes, states the tree-identity rule, the interim rule and the residual
  limitation, and authorizes nothing.
- `scripts/build_v2_code_hash_amendment_1.py` — deterministic producer; the artifact is byte-stable
  against the controller's periodic refresh of `research_state/campaign_authorization.json`.
- `scripts/verify_research_v2_code_hash_amendment_1.py` — read-only offline verifier (15 rule
  groups), including a check that each named affected verifier really computes the recorded canonical
  digest.
- `tests/test_research_v2_code_hash_amendment_1.py` — 26 deterministic tests, 8 of them tamper
  tests, including the enumeration-order perturbation test.
- `scripts/verify_research_v2_manifests.py`, `scripts/verify_research_v2_candidate_freeze.py`,
  `scripts/build_v2_candidate_freeze.py` — now compare the canonical digest and cross-check the
  recorded code hash against the v1 campaign authorization; the live ordered digest is reported, never
  compared as a drift signal.
- `tests/test_research_v2_manifests.py`, `tests/test_research_v2_candidate_freeze.py`,
  `tests/test_research_v2_spec.py` — the ordered-digest assertions are replaced by canonical-digest
  assertions; three new tamper tests prove the tree-identity check detects a modified source tree.

**Correction to this record:** the permutation count is **1 of 120**, not 6 (see the evidence bullet
above). The corrected count strengthens the finding: the authorized digest is effectively a
fingerprint of one specific directory layout.

**Residual limitation (recorded, not fixed):** `src/breakout_research/campaign.py`
(`_verify_pilot_gate`) and `src/breakout_research/pilot_gate_validator.py` compare the live ordered
code hash with the authorized one. They are inside the hashed set and are deliberately unchanged, so
the v1 campaign can only start on a checkout whose enumeration order reproduces the authorized digest.
Correcting that would require rotating `compute_code_hash()` and re-authorizing the v1 campaign,
which this decision explicitly rejects; the limitation is recorded as `RL1` in the amendment.

**Verification:** `PYTHONPATH=src python3 -m pytest tests/ -q` → 284 passed, exit 0 (252 pre-existing
+ 32 new); all six v2 verifiers exit 0; `src/breakout_research/` untouched; every frozen artifact
byte-identical; no v2 result row, shard, ledger, result manifest or checkpoint exists.

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

**Decision update 2026-10-20 UTC (HEAD `f0313469`, canonical source digest `3e8e4169…`):** the
residual limitation `RL1` of BRAIN-009 is decided by a new item, **BRAIN-010** (see "BRAIN-010" below).

- BRAIN-010 (P1) — `IMPLEMENTED_AND_VERIFIED`. The v1 campaign runtime gate is
  **not** modified: `src/breakout_research/campaign.py` stays byte-identical, the hashed set stays
  `3e8e4169…`, the authorized ordered digest `2efd3b18…` stays the value of record and every frozen
  v1/v2 artifact stays byte-identical. The gate's comparison is **reinterpreted** — it is a statement
  about *checkout compatibility*, never about source drift — and a v1 resume is supported only on a
  **gate-compatible** checkout, which is constructible and verified (a byte-identical copy of
  `src/breakout_research` on tmpfs with the five block directories created in the reverse authorized
  order reproduces `2efd3b18…` exactly). The pre-flight that enforces this lives **outside** the
  hashed set and is **implemented** (`scripts/verify_v1_gate_compatibility.py`, 2026-10-20T08:30Z).
  The recorded RL1 location is corrected by the versioned amendment
  `configs/research_v2_code_hash_amendment_2.json` (`manifest_hash 3ed6334e…`, 2026-10-20T09:0xZ);
  the immutable artifact `configs/research_v2_code_hash_amendment_1.json` is **not** edited. The
  correction this record states — "campaign.py (lines 171 and 189) only" — was found to be
  **incomplete**: `src/breakout_research/backtest/shards.py` (line 480) is a third live-vs-recorded
  site. See "BRAIN-010 implementation note" at the end of this file.

**Decision update 2026-10-20 UTC (HEAD `8f779b11`, canonical source digest `3e8e4169…`):** the v2
confirmatory evaluation, which the preregistration left without an executable, authorized path, is decided by
**BRAIN-011** (see "BRAIN-011" below).

- BRAIN-011 (P0) — `IMPLEMENTED_AND_VERIFIED`, and the confirmatory path is now **preregistered end to end**.
  The v2 confirmatory evaluation has a real package outside the hashed set (`src/v2_confirmatory/`: data,
  window, exposure, report, artifacts, runner), a criterion-reconciliation amendment
  (`configs/research_v2_confirmatory_protocol_amendment_1.json` `2701c634…`) that settles the conflict
  between the frozen specification's promotion rule and the protocol's buy-and-hold rule, a run authorization
  (`configs/research_v2_confirmatory_authorization_1.json` `f411aba9…`) for at most one logical run, a
  read-only offline verifier (`scripts/verify_v2_confirmatory_path.py`) and 48 deterministic tests. The
  **preregistered operator runbook** (`configs/research_v2_confirmatory_runbook_1.json` `d81d9197…`) fixes
  the ordered procedure, the binding identities, the failure decision table, the acceptance checks and the
  prohibitions, and its readiness probe and write order are verified against the **delivered** code with the
  Python AST. **Nothing ran**: no candle was read, no provider was contacted, no confirmatory artifact exists,
  and the confirmatory window stays `NOT_STARTED` with `holdout_exposed_count = 0`. The run itself may not
  start before `2027-01-17T22:00:00Z` and it then consumes the single use of the window.
  **The P0 code defect the independent audit (§12) found — the unreachable duplicate rollback block in
  `src/v2_confirmatory/runner.py` — is remediated by the versioned code-hash amendment
  `configs/research_v2_confirmatory_code_hash_amendment_1.json` (`a2a54927…`); see §13.**

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

---

## BRAIN-008 §15 implementation record — the v2 selection execution path and the versioned selection authorization 1 (2026-10-20T00:10Z, separate session)

**Task.** Deliver the v2 selection execution path (the code) and, after it, the versioned artifact that
authorizes exactly one bounded v2 selection run over the frozen candidate set. Deliver them in that order
and run nothing: no grid, no backtest, no campaign, no selection, no pilot, no confirmatory-window read.

**Delivered**

- `src/v2_campaign/` — the v2 execution path, **outside** the hashed source set: `__init__.py`, `errors.py`,
  `identity.py`, `scope.py`, `data.py`, `units.py`, `runner.py`. Canonical source digest
  `c69cc02188d95def8a9c2e24f717ccc20c36035d5049a3216451e841dfe42cba`. The hashed set stays
  `3e8e4169…` and the ordered code hash stays `2efd3b18…`; `src/breakout_research/` was not touched.
- `configs/research_v2_selection_authorization_1.json` — the versioned, self-hashed authorization
  (`manifest_hash 76be0d3b31aa8682f3c93056aca2c46ac77a875dbe4a53d557645bf58e15c918`).
- `scripts/build_v2_selection_authorization_1.py` — deterministic producer (pinned creation instant, every
  other field derived from hash-bound artifacts).
- `scripts/verify_research_v2_selection_authorization_1.py` — read-only offline verifier, 12 rule groups.
- `tests/test_v2_campaign_execution_path.py` — 20 deterministic tests, all against **synthetic fixtures in a
  temporary directory**; the real universe, the real datasets and the repository's own v2 paths are never
  touched.
- `tests/test_research_v2_selection_authorization_1.py` — 32 deterministic tests, 15 of them tamper tests.

**What the execution path enforces, and where it is proved**

| Rule | Code | Test |
| --- | --- | --- |
| the candidate set is exactly the frozen set, never re-ranked, widened or narrowed | `scope.frozen_scope`, `runner.build_plan` (cross-check against the validated constituents of `research/universe_manifest_v2.json`) | `test_the_run_refuses_a_widened_candidate_set`, `test_the_frozen_candidate_set_is_the_validated_v2_universe` |
| development data only; the confirmatory window is never read | `data.load_development_candles` (boundary checked before *and* after the read; a dataset that reaches into the window is refused, never trimmed) | `test_the_run_refuses_a_dataset_that_reaches_into_the_confirmatory_window`, `test_the_development_loader_refuses_a_dataset_that_declares_a_later_candle` |
| the unchanged v1 selection rule | `scope.selection_rule` (v1 block, byte-equal to the inherited v2 block), `runner._selection_summary` calls the v1 selector | `test_the_selection_rule_of_the_fixture_is_the_repository_v1_rule`, `test_the_run_reports_an_asset_without_a_candidate` |
| the holdout-position fold is never evaluated; `holdout_exposed_count` stays 0 | `units.validation_folds` | `test_the_run_never_evaluates_the_holdout_fold` |
| only the v2 paths are written | `scope.assert_no_forbidden_output`, `runner._guard_path` | `test_the_run_writes_only_the_v2_paths` |
| the bounds of execution amendment 1 hold | `runner.build_plan` | `test_the_run_is_bounded_by_the_authorized_asset_count` |
| one attempt | `runner.claim_attempt` (the attempt is recorded in the ledger before the first result row) | `test_the_run_consumes_its_single_run`, `test_the_number_of_resumes_is_bounded` |
| an interrupted run is resumed, not restarted | `runner.claim_attempt` (resume from the verified shards), `runner._append_result_stream` (the stream is a projection of the promoted shards) | `test_a_technical_failure_keeps_the_partial_state_for_a_resume` |
| a boundary abort rolls back | `runner._rollback` | `test_a_boundary_abort_rolls_back_and_releases_the_run`, `test_an_abort_rolls_back_the_artifacts_the_run_created` |
| the run contacts no provider | the loader reads only the local, hash-verified datasets | `test_the_run_makes_no_provider_request` |
| the run identity is portable | `identity.run_code_identity` (composite canonical digest) | `test_the_records_are_bound_to_the_run_identity` |

**Decisions this session had to make because the frozen artifacts do not fix them**

1. *Fold structure in v2.* The inherited `folds` block is unchanged, but in v2 the holdout is not the tail of
   the dataset: the confirmatory window is fresh data read only after the selected-configuration manifest is
   committed. The selection run therefore reproduces the v1 validation structure over the development dataset
   and skips the holdout-position fold, exactly as the v1 validation campaign skips it. The rule is proved by
   a differential test against the v1 `_get_fold_bounds`, not by a re-implementation of it.
2. *Asset key.* The run keys its assets by the Binance pair (as v1 did), not by the base symbol of the freeze.
3. *Run identity.* The experiment IDs bind the composite canonical digest of the hashed engine and of the
   execution path (BRAIN-009 rule). The ordered digest stays the authorized value of record and is never used
   as an identity.
4. *Where the selection outcome goes.* The amendment allows five v2 paths; the per-asset outcome, the
   "no candidate survived" report and the run counters are written into `research/ledger_v2.json`. No new
   output path was invented.
5. *The confirmatory boundary is enforced twice*, because a manifest may understate a dataset: once against
   the declared last candle before the file is read, once against every candle after it is read.
6. *One logical run, resumable.* A killed process leaves the run `RUNNING` in the ledger. The next
   process **resumes** it from the verified shards instead of starting a second run, so an interruption
   cannot burn the single authorization; the number of resumes is bounded by the already recorded
   `max_retries_on_technical_failure`. A completed run is never re-run. A *boundary* abort (scope,
   boundary, bounds or integrity violation) rolls every created v2 artifact back and releases the run,
   while a *technical* failure keeps the verified shards so that the resume can continue. The result
   stream is a projection of the promoted shards, so a resume cannot duplicate a row.

**Operational rule discovered in this session.** The authorization binds the canonical digest of the
execution path, so the package must be frozen *before* the authorization is built: every later edit under
`src/v2_campaign/` invalidates the authorization until the producer is re-run, and the re-run changes the
artifact's `manifest_hash`. Two edits made during this session each had this effect and were resolved by
rebuilding the artifact; the committed value is the one above.

**Falsifiers for this delivery.** If the authorization's `manifest_hash` does not recompute, the delivery is
invalid. If the authorized scope stops matching the frozen candidate set or the validated v2 universe, it is
invalid. If the bounds stop matching execution amendment 1, or the planned run stops fitting inside them, it
is invalid. If the data boundary stops being the frozen confirmatory-window start, or the confirmatory window,
the v1 holdout or the v1 cycle-0 units stop being excluded, it is invalid. If the selection rule stops being
the byte-equal v1 rule, it is invalid. If the canonical digests of the hashed set or of the execution path
stop recomputing from the tree, the tree changed and the authorization is invalid. If an output path points at
a v1 path, the run would violate the protocol. If a v2 shard, ledger, result manifest, result stream or
checkpoint appears, or a v2 result row is written, the nothing-runs state is violated.

**Residual limitation (recorded, not fixed).** The bounded run writes 497,664 execution units; at the v1
record size that is of the order of 1.3 GB of shards and of the order of 300 MB of result stream. The v1
shards are bounded to 4 MiB per file and were pushed as many small files; the single-file v1 result stream
was the artefact that could not be pushed. The authorization records this as `RL2`: the shards are the
authoritative record set and are committed as bounded files, the single-file result stream is a projection
of the shards and is regenerated from them rather than committed as one blob, and the v1 shards, ledger and
result stream stay untouched either way. The delivery decision itself is not made here.

**Verification.** `PYTHONPATH=src python3 -m pytest tests/ -q` → 339 passed, exit 0 (284 pre-existing +
55 new); all seven v2 verifiers exit 0; `src/breakout_research/` untouched; every frozen v1 and v2 artifact
byte-identical; no v2 result row, shard, ledger, result manifest or checkpoint exists.

## BRAIN-008 §16 implementation record — the authorized v2 selection run was performed (2026-10-20T06:40Z, separate session)

**Task.** The session that wrote the selection authorization 1 delivered the code and the artifact and ran
nothing. This session performed the **single authorized v2 selection run** over the 18 frozen constituents,
reported its selection outcome honestly, decided the delivery of the result volume (residual limitation
`RL2`) and replaced the authorization verifier's nothing-runs rule by an executed-state check.

**The rehearsal came first, as the handoff required, and it consumed nothing.** `scripts/v2_selection_rehearsal.py`
runs the real execution path against the real v2 datasets with every output redirected to a temporary
directory outside the repository, so neither the ledger nor the attempt was touched. Two units were measured
individually (15.839 ms and 15.693 ms for ADAUSDT / cfg_0000 / fold 0 / cost 0 and cost 1), 23 units gave a
median of 15.839 ms, and the result record is 1,050.6 bytes on average. The full pipeline was then exercised
end to end (`--mode pipeline`: the real `run_selection` with the grid reduced to one configuration per asset,
216 units, 9.647 s, 22 shard files) and it produced the ledger, the shards, the checkpoint, the result stream
and the selection summary with no defect.

**What the rehearsal could not have told us, and what the run did.** The grid is not uniform. The cost of a
unit grows with the entry lookback (12 … 720 bars) and with the BTC-trend-filter configurations, which
recompute the 26,280-candle BTC EMA twice per unit (once in `generate_entry_signals`, once in
`run_fold_backtest`). The rehearsal sampled the first configurations and extrapolated ≈ 2.2 h; the real run
measures **34.2 units/s in the cheap regions and 20.6 units/s in the expensive ones**, 99.5 % CPU-bound, and
projects to **≈ 5 h**. The filesystem is not the bottleneck (an fsync costs 0.28 ms on this container). This
is the substance of prompt gap `P9-2026-10-20-LONG-RUN-COST-AND-RESUME-BUDGET` in
`research_state/prompt_evolution.md`: a handoff that asks for the *outcome* of a five-hour run, without
saying that the run is resumable and that the outcome may not be available in the session that starts it, is
a prompt gap.

**The run.** `scripts/run_v2_selection.py` wraps `v2_campaign.runner.run_selection` with a progress line and
prints the ledger document. It writes only the five authorized v2 paths and consumes the single authorized
attempt. The run is **one logical run**: a killed process leaves the ledger `RUNNING` with its verified
shards, and the next process resumes it from those shards instead of starting a second run. The number of
resumes is bounded by the already recorded `max_retries_on_technical_failure` (3), and a completed run is
never re-run. No file under `src/breakout_research/` or `src/v2_campaign/` was added, edited or deleted, so
the canonical digests (`3e8e4169…` and `c69cc021…`) and the ordered code hash (`2efd3b18…`) are unchanged and
the authorization was never rebuilt.

**Rule 12 was replaced, not deleted.** The authorization verifier asserted that no v2 execution artifact
exists; that assertion is false by design once the run has happened. The rule is now state-adaptive and at
least as strict in both states: before the run, no v2 execution artifact exists at all; after the run, the
ledger names the authorized run and is bound to the authorization's manifest hash, its scope is the frozen
candidate set, no confirmatory exposure is recorded, the counts stay inside the authorized bounds and add
up, a completed run evaluated the whole authorized grid, the selection outcome covers every asset of the
frozen scope and reports the assets without a candidate, and the checkpoint and the results manifest are
bound to the authorized run code identity, the v2 specification and the v2 data manifest; in both states the
v1 evidence is byte-identical, no v2 row appears in the v1 result stream, and the confirmatory window is
still `NOT_STARTED`. Nine tamper tests cover the new check.

**The deeper check is a separate script.** `scripts/verify_v2_selection_run.py` verifies the record set
itself: every shard against the results manifest (sha256, byte size, record count, no orphan), every record
re-computing its own experiment id and carrying the authorized identities, every grid unit appearing exactly
once, the buy-and-hold baselines recomputed from the datasets, the **selection outcome recomputed with the
unchanged v1 selector from the records** and compared with what the run reported, and the result stream
compared with the projection of the verified shards.

**The outcome of the run.** The single authorized run started at `2026-10-20T02:02:04.655376Z` and
completed at `2026-10-20T06:26:28.209906Z` — 15,863.55 s, 31.37 units/s, **0 resumes, 0 technical
failures** — and it evaluated the whole authorized grid (497,664 execution units, `executed 497,664`,
`records_written 497,664`, `config_units 41,472`, `holdout_exposed_count 0`, no v1 artifact touched). The
outcome is `CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE` over 18 evaluated assets: **14 assets have a
candidate** (ADA `cfg_0073`, AVAX `cfg_0246`, BNB `cfg_0089`, DOGE `cfg_0736`, ETH `cfg_1241`, HBAR
`cfg_0772`, LTC `cfg_0084`, NEAR `cfg_1564`, SOL `cfg_0732`, SUI `cfg_0507`, UNI `cfg_1570`, XLM `cfg_0124`,
XRP `cfg_0041`, ZEC `cfg_0270`, all `CANDIDATE_PENDING_HOLDOUT`) and **4 do not** (BCH, LINK, TRX
`INSUFFICIENT_EVIDENCE`, BTC `NO_CANDIDATE`). The four are reported in
`assets_without_candidate` with `assets_without_candidate_reported = true`, which is what the protocol
requires.

**The outcome was recomputed, not taken on trust.** `scripts/verify_v2_selection_run.py` reads the 9,971
verified shards, re-computes every record's `experiment_id`, re-computes the buy-and-hold baselines from the
datasets, re-applies the unchanged v1 selector to the record set and compares the result with the ledger —
per asset, per status, per configuration, per economic status, per gate count, plus the outcome label and
both asset lists. It agrees on all 18 assets and reports `"ok": true`. The result stream's sha256 equals the
sha256 of the shard bytes in shard order, so the stream is exactly the projection of the shards, and
`scripts/regenerate_v2_result_stream.py` rebuilds it byte for byte (497,664 rows, 512,616,732 bytes).

**The delivery decision (`RL2`).** The shards under `research/shards_v2/` are the authoritative record set
and are committed as many small files, exactly as the v1 campaign committed 20,041 of them. The single-file
result stream `research/results_v2.jsonl` is **not** committed: at ≈ 500 MB it is far above the 100 MB
per-file push limit, and it carries no information that the shards do not carry — it is their concatenation
in shard order. It is listed in `.gitignore` and `scripts/regenerate_v2_result_stream.py` rebuilds it from
the shards on demand, atomically and re-verifying every experiment id while it writes. The v1 shards, the v1
ledger and the v1 result stream are untouched either way.

**Falsifiers for this delivery.** If the ledger does not name the authorized run, or is not bound to the
authorization's manifest hash, the delivery is invalid. If the recorded counts leave the authorized bounds or
do not add up, it is invalid. If a confirmatory exposure is recorded anywhere, it is invalid. If a record
does not re-compute its own experiment id, or carries a foreign code, specification or unit-data identity, or
is a holdout record, it is invalid. If a grid unit is missing or duplicated, it is invalid. If the
recomputed selection outcome differs from the recorded one, it is invalid. If the v1 evidence is not
byte-identical, or a v2 row appears in the v1 result stream, it is invalid.

**Residual limitation (recorded, not fixed).** The result volume of the authorized run is ≈ 500 MB in
≈ 10,000 shard files of ≈ 52 KB each. The files are far below the 4 MiB per-file ceiling and the per-file
push limit, but the count is high because the run flushes the shard writer every 50 records
(`checkpointing.batch_size` of the frozen v1 specification). The flush cadence is inside the hashed set and
inside the frozen specification, so it was not changed.

---

## BRAIN-009 implementation record — part 2 (repository-wide sweep, 2026-10-20T07:5xZ)

**Task.** The 23:37Z session implemented the BRAIN-009 decision in the files the decision record named.
The 00:10Z session then created two **new** test modules that enforced the superseded rule again. In
the checkout that wrote them the directory enumeration order happened to reproduce the authorized
digest, so the suite was green; in a checkout with a different enumeration order the same assertions
fail with a false source-drift message. This record closes the implementation by sweeping the whole
repository for every site that still enforces the superseded rule.

**The sweep and its result.** The superseded pattern is a check that compares the live ordered digest
`compute_code_hash()` with the authorized value of record `2efd3b18…` and treats a mismatch as a
failure. A repository-wide search found **two sites** that enforce it, both in test modules created
after the decision:

| Site | Before | After |
| --- | --- | --- |
| `tests/test_v2_campaign_execution_path.py::test_importing_the_execution_path_does_not_change_the_code_hash` | `compute_code_hash() == "2efd3b18…"` | canonical digest equals the recorded `3e8e4169…`; the live ordered digest is one of the 120 digests this tree produces; the authorized digest is one of them |
| `tests/test_v2_campaign_execution_path.py::test_the_hashed_set_is_byte_unchanged_by_the_execution_path` | `compute_code_hash() == "2efd3b18…"` | same three assertions |
| `tests/test_research_v2_selection_authorization_1.py::test_the_hashed_source_set_is_byte_unchanged` | `compute_code_hash() == campaign_authorization["code_hash"]` | canonical digest equals the recorded `3e8e4169…`; the authorized value of record is cross-checked against `research_state/campaign_authorization.json`; the live ordered digest is one of the 120 digests this tree produces |

No production code enforced the superseded rule: all ten v2 verifiers had already been converted to
the canonical rule by the 23:37Z session and exit 0 in a checkout with a foreign enumeration order.

**The replacement rule is stronger than the rejected one.** The rejected check asked "does the live
ordered digest equal the authorized digest?", which fails on a foreign enumeration order. The
replacement asks two questions that hold in every checkout and still detect a real edit of the tree:

1. is the live ordered digest one of the digests that **this** tree produces under the 120 orders of
   its directory blocks (it is a digest of this tree, under the checkout's own order)? and
2. is the authorized value of record still one of those 120 digests (the tree has not drifted from the
   state the v1 campaign was authorized against)?

A drift probe added to a copy of `src/breakout_research` makes the authorized digest unreproducible
and changes the canonical digest, so both assertions fail on a real edit. The probe is recorded in
`research_state/agent_handoff.md`.

**Support files.** `tests/code_identity_helpers.py` (new) holds the shared helpers: a faithful
replica of the ordered digest for a given block order, the set of the 120 order variants and the
live enumeration order of a checkout. The replica is validated against the live digest before it is
used as evidence
(`tests/test_v2_campaign_execution_path.py::test_the_replica_of_the_ordered_digest_reproduces_the_live_digest`).

**New tests.** `test_the_tree_identity_checks_survive_a_perturbed_enumeration_order` reverses the
`os.walk` order and shows that the ordered digest changes while the canonical digest and every
assertion above do not; `test_the_replica_of_the_ordered_digest_reproduces_the_live_digest` pins
the replica to the live digest.

**Unchanged by this record.** `src/breakout_research/` and `src/v2_campaign/` were not touched; no
frozen artifact was edited; `research_state/campaign_authorization.json` and
`research_state/checkpoint.json` were not edited; no v2 grid, backtest, campaign, selection or pilot
ran; no candle inside the confirmatory window was read; the market-cap snapshot was not re-retrieved.

**Residual limitation `RL1` is unchanged.** The v1 campaign runtime gate
(`src/breakout_research/campaign.py::_verify_pilot_gate` and
`src/breakout_research/pilot_gate_validator.py`) still compares the live ordered digest with the
authorized one. It is inside the hashed set and BRAIN-009 rejects the rotation, so it stays recorded
as a limitation: a v1 resume is only possible on a checkout whose enumeration order reproduces the
authorized digest. Nothing runs today — the v1 campaign is in a terminal state.

---

## BRAIN-010 — Residual limitation RL1: the v1 campaign runtime gate treats a checkout's directory order as source drift

**Priority:** P1 — blocks a v1 campaign resume on a checkout whose directory order differs; no live
campaign is behind it (the v1 campaign is terminal).
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`
(design, prerequisites, staged steps, tests and rollback are explicit below; **not implemented in the
session that wrote this record**, README Section 2A C1)
**Cause labels:** `IMPLEMENTATION_DEFECT` (the comparison encodes an environment fact as a code
identity), `PERMANENT_PLATFORM_LIMIT` (filesystem directory enumeration order)
**Confidence:** direct evidence confirmed in this session — the permutation brute force, the
gate-comparison reproduction and the gate-compatible-checkout construction were re-executed against the
live tree at HEAD `f0313469` (2026-10-20).

### Evidence (revalidated 2026-10-20, branch `main`, HEAD `f0313469`, working tree clean)

**1. The defect.** `compute_code_hash()` (`src/breakout_research/config.py:257-268`) hashes the `.py`
files of each directory in sorted order but visits the directories in **filesystem enumeration order**:

```python
for root, dirs, files in os.walk(src_dir):
    for f in sorted(files):
        if f.endswith('.py'):
            ...
            hasher.update(fp.read())
```

The digest of a git-clean tree therefore depends on the machine's directory order.

**2. The permutation evidence (re-executed this session, independent of `tests/code_identity_helpers.py`).**
The hashed set `src/breakout_research` has five directory blocks that contain `.py` files
(`backtest`, `data`, `indicators`, `signals`, `utils`); `__pycache__` holds no `.py` file and is not a
block. Over the 120 permutations of those five blocks:

- all **120** orders yield **120 distinct** ordered digests (no collision);
- exactly **one** of them — `(indicators, utils, signals, data, backtest)` — reproduces the authorized
  digest `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2`;
- the **canonical** digest `3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`
  (path- and content-sorted) is **identical under all 120 orders**.

**3. This checkout.** Live enumeration order `(indicators, backtest, utils, signals, data)` → live
ordered digest `608c7340fa8524921e9378626ac9cd0387f0fad0274e6fa0213a006f47487925`; canonical digest
`3e8e4169…` — **equal to the recorded canonical digest**; the authorized digest **is** one of the 120
digests this tree produces. The tree has therefore **not** drifted; only the checkout's order differs.

**4. The three recorded digests and the two checkout-dependent comparisons.**

| Record | Field | Value |
| --- | --- | --- |
| `research_state/campaign_authorization.json` | `code_hash` | `2efd3b18…` (`authorized: true`, `reasons: []`) |
| `research_state/checkpoint.json` | `code_hash` | `2efd3b18…` |
| `research_state/pilot_evidence.json` | `code_hash`, `evidence.code_hash`, `evidence.checkpoint_state.code_hash` | `2efd3b18…` |

Reproduced read-only this session (no campaign run, no artifact written):

| Site | Comparison | Result on this checkout | Message the user sees |
| --- | --- | --- | --- |
| `src/breakout_research/campaign.py:189` (`_verify_pilot_gate`) | `auth.get('code_hash') != code_hash` | `True` | `RuntimeError: Code hash mismatch. Code has changed since authorization.` |
| `src/breakout_research/campaign.py:171` (`_verify_stale_checkpoint`) | `stored_code != code_hash` | `True` | `RuntimeError: Checkpoint code hash mismatch: stored 2efd3b18… != current 608c7340…; code changed since checkpoint, refusing to resume` |
| `src/breakout_research/pilot_gate_validator.py:93` (`_validate_evidence`) | `evidence.get('code_hash') != code_hash`, where `code_hash = pilot.get('code_hash')` | `False` | — (both sides come from `research_state/pilot_evidence.json`) |

**Correction to the recorded RL1 location.** `configs/research_v2_code_hash_amendment_1.json`
(`residual_limitations[0]`) names `campaign.py (_verify_pilot_gate)` **and**
`pilot_gate_validator.py` as the location of RL1. Only `campaign.py` contains a checkout-dependent
comparison; the `pilot_gate_validator.py` comparison is file-internal and therefore environment
independent. The RL1 location is **`src/breakout_research/campaign.py` only** (two sites, lines 171
and 189). The consequence is unchanged; the attribution was one file too wide. The artifact itself is
immutable and hash-bound, so the correction is recorded here and, if ever formalized, by a versioned
amendment — never by editing the frozen artifact.

**5. The misleading message is reachable from the documented v1 entry point.**
`scripts/resume_cycle_cohort0.py` calls `run_campaign(...)`, whose `run()` (`campaign.py:295-303`)
executes `_verify_stale_checkpoint` and then `_verify_pilot_gate` with the live ordered digest. The
message "Code has changed since authorization" is therefore the **first** thing a user sees on a
foreign-order checkout, although the source is provably unchanged.

**6. The v1 campaign is terminal, so the limitation has no live campaign behind it.**
`research/campaign_cycles/terminal/exhausted_cohort_2.json`: `state = AWAITING_NEW_CANDIDATES`,
`reason = NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION`,
`blocking_dependency = UNIVERSE_VERSION_DECISION` (recorded 2026-10-19T15:43:32Z).

**7. The blast radius of changing the hashed set is an already-verified v2 run.**
`compute_code_hash()` hashes every `.py` file under `src/breakout_research` recursively, so **any**
edit there changes the canonical digest `3e8e4169…`. That digest is recorded in the five artifacts
named in `configs/research_v2_code_hash_amendment_1.json` → `amends`
(`research/universe_manifest_v2.json`, `research/data_manifest_v2.json`,
`configs/research_v2_candidate_freeze.json`, `configs/research_v2_execution.json`,
`configs/research_v2_execution_amendment_1.json`) and it is the tree-identity component of the
**executed** v2 run: `configs/research_v2_selection_authorization_1.json`,
`research/ledger_v2.json`, `research/results_manifest_v2.json`,
`research/v2_selected_configurations_manifest.json` and
`configs/research_v2_confirmatory_protocol.json` all bind the canonical digests `3e8e4169…` (hashed
set) and `c69cc021…` (execution path). `scripts/verify_v2_selection_run.py` re-verifies the 497,664
records of that run against those identities. Editing the hashed set would therefore invalidate the
identity of a completed, hash-verified run and force an amendment chain over it — exactly the
disproportionate cost BRAIN-009 rejected.

**8. Re-authorizing the v1 campaign on this checkout would also break a v2 check.**
`scripts/verify_research_v2_code_hash_amendment_1.py:231` asserts
`authorized_code_hash == research_state/campaign_authorization.json.code_hash`. Re-running the pilot
on a foreign-order checkout writes that checkout's ordered digest into the pilot evidence and hence
into the authorization artifact (the artifact's `code_hash` is copied from the pilot evidence,
`pilot_gate_validator.py:190`), which turns that v2 verifier red and forces another amendment chain.
`src/breakout_research/pilot.py:85,94,109` writes `compute_code_hash()` into **new** pilot evidence,
so every new pilot run re-binds the authorization to whatever order its machine happens to have.

**9. A gate-compatible checkout is constructible and verified.** A byte-identical copy of
`src/breakout_research` placed on an insertion-ordered filesystem (tmpfs) with the five block
directories created in the order `(backtest, data, signals, utils, indicators)` enumerates as
`(indicators, utils, signals, data, backtest)` and its ordered digest is exactly
`2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` — reproduced in this session, not
asserted. On a name-hashed filesystem (this container's workspace: `stat -f %T` → `ext2/ext3`) the
enumeration order ignores creation order (creating the blocks in two different orders produced the
identical enumeration), so the order is **not** controllable there.

**10. Frozen constraints that bound the decision.**
`research_state/continuous_universe_campaign_spec.md:34`: *"Existing authorization must fail closed
when any bound input changes; do not self-authorize or carry a stale approval forward."* The code
hash is a bound input, so **no** design may let a changed tree pass the gate; only the *ordering*
dimension may be relaxed, never the *content* dimension. README Section 2A E additionally forbids
repairing a red check by editing the frozen artifact.

### 1. Causal model

- **Observed facts.** The ordered digest is checkout-dependent (120 orders → 120 digests; the
  authorized digest is one specific order). The canonical digest is order-independent. The v1 gate
  compares the ordered digest against three recorded values and therefore fails on any checkout whose
  order differs. The tree in this checkout is provably unchanged.
- **Inferred root cause.** `compute_code_hash()` was written as a *content* identity (hash the source
  files) but implemented as a *content + directory-order* identity. The gate compares it against a
  value of record captured on one machine, so the comparison conflates "the code changed" with "the
  checkout's directory order changed". The defect is in the **encoding of identity**, not in the
  intent of the gate: the gate's intent ("the code that will run is the code that was authorized") is
  correct and must be preserved.
- **Unknown / not decided here.** Whether a v1 resume will ever be needed. The v1 campaign is
  terminal and blocked on `UNIVERSE_VERSION_DECISION`; the v2 path supersedes it for all new work.
- **Downstream risks.** (a) A future agent "repairs" the red comparison by editing
  `src/breakout_research/` → the hashed set changes → the v1 authorization and the executed v2 run's
  identity are invalidated (see evidence 7). (b) A future agent re-authorizes the v1 campaign on a
  foreign-order checkout → the authorized value of record becomes checkout-specific and a v2 verifier
  goes red (evidence 8). (c) A user reads "Code has changed since authorization" as true → the
  campaign is wrongly believed to be invalidated, or wrongly believed to be safe to "re-fix".

### 2. Designs compared

| # | Design | Correctness / research validity | Persistence & blast radius | Cost | Rollback | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| A | **Keep the gate byte-exact; reinterpret it; add a pre-flight compatibility check outside the hashed set** | Preserves the gate's intent exactly. Drift is decided by the canonical digest (BRAIN-009), compatibility by the ordered digest. No frozen artifact changes | New files **outside** `src/breakout_research/` (like `src/v2_campaign/`), so the canonical digest `3e8e4169…`, the ordered digest `2efd3b18…` and every v2 artifact stay byte-identical | One read-only script + one test module | Delete the new files; nothing else changed | **Recommended** |
| B | **Variant-tolerant gate inside the hashed set** (`campaign.py:171,189` accept any of the tree's 120 order variants) | Semantically the ideal fix — it relaxes only the ordering dimension and still fails closed on a content change (spec line 34) | **Prohibitive.** Any edit changes the canonical digest → the identity of the *executed* 497,664-record v2 run no longer matches the tree → `scripts/verify_v2_selection_run.py` fails → the five `amends` artifacts plus the v2 run identity artifacts must all be re-hashed → a new pilot run is needed to re-authorize → a second v1 campaign identity is created | High (multi-artifact amendment chain over a verified run + a live pilot run) | Not cleanly reversible: the artifacts' recorded hashes would have moved | Rejected (the cost of the BRAIN-009-rejected rotation) |
| C | **Re-authorize the v1 campaign on the current checkout** (re-run the pilot so the authorization carries this checkout's ordered digest) | Leaves the tree untouched, but the gate would then compare an *ordered* digest against an *ordered* digest — the identity stays checkout-dependent, and the value of record silently becomes an artifact of the machine that ran the pilot | Changes `research_state/campaign_authorization.json.code_hash` → `scripts/verify_research_v2_code_hash_amendment_1.py:231` goes red → a further v2 amendment chain; also re-binds `research_state/checkpoint.json` semantics | Medium + a live provider run (the pilot reads real market data; `api.binance.com` answers HTTP 451 from this container, `data-api.binance.vision` is reachable) | Revert the artifact, but the pilot run happened | Rejected (institutionalizes the non-portability it is meant to remove) |
| D | **Gate-compatible checkout** (place the tree on an insertion-ordered filesystem with the blocks created in the reverse authorized order) | Perfect while it holds: the gate runs exactly as preregistered and the tree is byte-identical (verified, evidence 9) | No artifact, no code, no identity changes at all | Low, but the checkout must be re-prepared per machine | Nothing to roll back | **Accepted as the operational fallback under Design A** |
| E | **Re-implement the v1 resume path outside the hashed set** (a `src/v1_campaign/` twin, as done for v2) | The v1 record set would split: the 497,765 existing v1 records are bound to `code_hash d0dca298…` (`research/results_manifest.json`) and to three campaign identities (`577e87e2…`, `707f7a50…`, `fcf04f6e…`), while new records would carry a new identity | Splits the v1 evidence chain; the v1 shards are shared and the manifest binds one campaign id | High | Not cleanly reversible | Rejected (splits the v1 record set; the v1 campaign is terminal, so the path is not needed) |

### 3. Recommendation — the decision (rules only)

**Adopt Design A, with Design D as its operational fallback. Reject B, C and E.**

1. **The v1 gate is not modified.** `src/breakout_research/campaign.py` stays byte-identical. The
   hashed set stays canonical `3e8e4169…`; the authorized ordered digest `2efd3b18…` stays the
   authorized value of record; every frozen v1 and v2 artifact stays byte-identical.
2. **The gate's comparison is reinterpreted, not changed.** `auth['code_hash'] != live_ordered_digest`
   means *"the code that would run is not the code that was authorized **under this checkout's
   directory order**"*. It is a statement about **checkout compatibility**, never about source drift.
   Source drift is decided **only** by the canonical digest (BRAIN-009 rule).
3. **A v1 resume is supported only on a gate-compatible checkout**, i.e. one whose live ordered digest
   equals `2efd3b18…`. Such a checkout is constructible (evidence 9) and is **verified** by digest,
   never by assumption: copy the tree to an insertion-ordered filesystem and create the five block
   directories in the order `(backtest, data, signals, utils, indicators)`.
4. **A v1 resume is started only through a pre-flight check outside the hashed set.** The pre-flight
   (a) proves the tree has not drifted — the canonical digest equals the recorded `3e8e4169…` and the
   authorized digest is one of the 120 digests the current tree produces; (b) reports
   `gate_compatible` with the live digest, the live enumeration order and the authorized order; and
   (c) **refuses** to start a v1 run on an incompatible checkout with an explicit
   *environment fact, not source drift* message. The misleading `RuntimeError("Code has changed since
   authorization.")` must not be the first thing a user sees.
5. **`research_state/campaign_authorization.json` and `research_state/checkpoint.json` are not
   re-issued.** They keep `2efd3b18…`. Re-authorization on a checkout that is not gate-compatible is
   **forbidden without a versioned amendment**, because it would replace the authorized value of
   record with a checkout-specific digest and break the v2 cross-check at
   `scripts/verify_research_v2_code_hash_amendment_1.py:231`.
6. **The frozen v2 artifacts stay immutable.** The canonical digest remains the tree identity; the
   ordered digest remains informational and is never an identity. The executed v2 run keeps the
   identity it was verified with.
7. **The interim rule (unchanged from BRAIN-009 and re-affirmed here).** `src/breakout_research/`
   must not be edited to make a red ordered-digest comparison green. A red ordered-digest comparison
   is reported as an **environment fact** about the checkout's directory enumeration order, with the
   canonical digest as the drift verdict.
8. **The RL1 location is corrected** to `src/breakout_research/campaign.py` (lines 171 and 189);
   `pilot_gate_validator.py` is environment independent (evidence 4). The correction is recorded here;
   the immutable artifact `configs/research_v2_code_hash_amendment_1.json` is not edited.

   > **Corrected by the implementation (2026-10-20T09:0xZ).** Rule 8's location list is
   > **incomplete**: `src/breakout_research/backtest/shards.py` (line 480) is a third
   > live-vs-recorded site — the result-store reconciliation compares the live ordered
   > code hash with the code hash recorded in `research/results_manifest.json` — and it was
   > not enumerated in evidence 4. The authoritative correction is the versioned amendment
   > `configs/research_v2_code_hash_amendment_2.json`, which records **all five** code-hash
   > comparison sites of the hashed set (three live-vs-recorded, two recorded-vs-recorded)
   > and lets the verifier recompute that set from the source tree. See the implementation
   > note at the end of this file.

### 4. Falsifying evidence (what would overturn this decision)

- The pre-flight cannot distinguish "foreign enumeration order" from "source drift" on a real
  checkout — i.e. a modified tree in a foreign-order checkout is **not** detected (canonical digest
  mismatch) or is falsely reported as a drift.
- The canonical digest is **not** stable across two checkouts of the same commit (it would reopen
  BRAIN-009).
- The 120-variant enumeration is wrong for some checkout: the live ordered digest is **not** among
  the 120 digests the tree produces (the replica is not faithful to `compute_code_hash()` for a tree
  with nested `.py` subdirectories, which the current tree does not have).
- A gate-compatible checkout cannot be constructed on any filesystem available to the operator, i.e.
  evidence 9 does not reproduce → Design D is not a usable fallback and the decision must be
  re-opened for Design B.
- The v1 campaign turns out to be **non-terminal** (a resume is required) **and** the terminal state
  is wrong — then the cost of Design A (a refused resume) must be re-priced.
- A frozen artifact turns out to depend on the *live* ordered digest in a way this record does not
  account for (a repository-wide sweep says otherwise) — the sweep below must be repeated at
  implementation time.

### 5. Rollback

- Design A adds only new files outside the hashed set (`scripts/…`, `tests/…`) and edits only
  `research_state/`. Rollback = delete those files and revert this record's status line. No artifact,
  no identity, no result, no shard and no ledger changes → **nothing to migrate**.
- The frozen v2 artifacts are not edited by this decision, so no rollback of them is needed.
- If the pre-flight is later judged insufficient, Design B can still be taken — but only together with
  the amendment chain over the five `amends` artifacts and the v2 run identity, and only after a new
  brainstorming record re-prices it.

### 6. Staged acceptance tests (a later implementation session — NOT this one)

| # | Stage | Acceptance test | Falsifies |
| --- | --- | --- | --- |
| 1 | Pre-flight script | `python3 scripts/verify_v1_gate_compatibility.py` exits 0 and its JSON report contains the recomputed canonical digest `3e8e4169…`, the live ordered digest, the live enumeration order, the authorized order and `authorized_digest_in_variants = true` | the report compares a recorded constant with itself (README 2A E) |
| 2 | Pre-flight script | the same script on a **copy** of the tree with one `.py` file changed exits non-zero and names the canonical digest mismatch — real drift is still detected | drift detection |
| 3 | Pre-flight script | the same script under a **perturbed enumeration order** (reversed `os.walk` over a copy) still exits 0 and still reports `authorized_digest_in_variants = true` — a false drift signal is not produced | the false-drift claim |
| 4 | Pre-flight script | `--require-gate-compatible` exits 1 on this checkout (live `608c7340…` ≠ authorized `2efd3b18…`) and prints the environment-fact message, not a drift message | the refusal behavior |
| 5 | Pre-flight script | on a tmpfs copy created in the reverse authorized order, the live ordered digest equals `2efd3b18…` and the script reports `gate_compatible = true` — the fallback is real, not aspirational | evidence 9 |
| 6 | Tests | `tests/test_v1_gate_compatibility.py` proves each of stages 1–5 deterministically, using the replica in `tests/code_identity_helpers.py` and a **synthetic** tree in a temporary directory; the repository's own v1/v2 paths are never written | test gap |
| 7 | Repository sweep | a repository-wide search shows **no** new site that compares the live ordered digest with a recorded digest and treats a mismatch as drift, and the existing sites (`tests/test_v2_campaign_execution_path.py`, `tests/test_research_v2_selection_authorization_1.py`) still assert the canonical rule | README 2A E (superseded-rule sweep) |
| 8 | Non-regression | `PYTHONPATH=src python3 -m pytest tests/ -q` exits 0; all eleven v2 verifiers exit 0; `scripts/verify_v2_selection_run.py` exits 0; `compute_code_hash()` and both canonical digests are unchanged; every v1 and v2 artifact sha256 anchor is unchanged; no v2 result row, shard, ledger, result manifest or checkpoint changes; the confirmatory window stays `NOT_STARTED` with `holdout_exposed_count = 0` | any side effect |

### 7. Prerequisites for the implementation session

- `pytest` and `numpy` must be installed in the container (`python3 -m pip install pytest numpy requests`)
  or the suite cannot run and must be reported `NOT_RUN`.
- The implementation must live **outside** `src/breakout_research/` (rule 1) — `scripts/` and `tests/`
  only. Any `src/breakout_research/` edit invalidates this decision.
- The implementation must not edit `research_state/campaign_authorization.json`,
  `research_state/checkpoint.json`, `research_state/pilot_evidence.json` or any frozen artifact
  (rule 5).

### 8. Planned rule → code → test map (for the implementation session)

| Rule (this record) | Planned code | Planned test |
| --- | --- | --- |
| the tree identity is the canonical digest, not the ordered digest | `scripts/verify_v1_gate_compatibility.py` (canonical digest) | stage 1 / stage 3 |
| a red ordered-digest comparison is an environment fact, not drift | same (report fields `gate_compatible`, `drift_detected`) | stage 3 / stage 4 |
| the authorized digest must still be one of the tree's 120 digests | same (variant enumeration) | stage 1, stage 6 |
| a v1 resume runs only on a gate-compatible checkout | same (`--require-gate-compatible`) | stage 4 / stage 5 |
| the gate-compatibility fallback is constructible and verified | same (report of live order vs authorized order) | stage 5 |
| the hashed set and every frozen artifact stay byte-identical | the implementation touches no `src/` file and no frozen artifact | stage 8 |

### 9. Do NOT (this session and the implementation session)

Do not edit anything under `src/breakout_research/` (it is the hashed set; the v1 campaign
authorization and the executed v2 run's identity depend on it); do not edit
`research_state/campaign_authorization.json`, `research_state/checkpoint.json` or
`research_state/pilot_evidence.json`; do not edit any frozen artifact (including
`configs/research_v2_code_hash_amendment_1.json`, whose RL1 location this record corrects); do not
run any v1 or v2 grid, backtest, campaign, selection or pilot; do not read any candle inside the v2
confirmatory window; do not write any v2 path; do not contact any provider or fetch candles; do not
re-run a producer script that would rewrite an existing artifact.

### 10. Implementation note

**This record is the deliverable.** The pre-flight script, its verifier and its tests are **not**
implemented in the session that wrote this record (README Section 2A C1). The implementation session
must verify the staged acceptance tests above, must repeat the repository-wide sweep for the
superseded rule (stage 7), and must record its own implementation note here and in
`research_state/agent_handoff.md`.
## BRAIN-010 implementation note — the RL1 location correction (2026-10-20T09:0xZ)

**Task.** Decide and record the correction of the RL1 location that this record required
(section 3, rule 8), in the immutable `configs/research_v2_code_hash_amendment_1.json`,
without editing that artifact.

**Decision — a versioned amendment, not a prose note.** The correction is carried by
`configs/research_v2_code_hash_amendment_2.json` (`manifest_hash 3ed6334e...`, produced by
`scripts/build_v2_code_hash_amendment_2.py`, verified by
`scripts/verify_research_v2_code_hash_amendment_2.py`). The alternatives were compared and
recorded in the artifact itself: a note in this queue was rejected because it cannot correct
the field that every consumer of the frozen artifact reads, and editing the frozen artifact is
forbidden because it would change the recorded `manifest_hash 4409b6af...` that the v2 identity
chain depends on.

**The correction is enforceable, which is why an artifact is worth it.** A *code-hash comparison
site* is a comparison in the hashed source set whose source segment mentions `code_hash`. The
set of such sites is recomputed mechanically from the tree with the Python AST, so the amendment
can neither omit a site nor invent one — which is exactly the defect of the original record.
Each site is classified `LIVE_VS_RECORDED` (the live, checkout-dependent ordered digest compared
with a recorded digest) or `RECORDED_VS_RECORDED` (both sides recorded: environment independent),
and every classification carries the source steps that are the evidence for it. The verifier
re-resolves every step against the current source, so a source edit invalidates the amendment.

**The corrected set — five sites, three of them live-vs-recorded.**

| Site | Comparison | Classification | Recorded value compared with the live digest |
| --- | --- | --- | --- |
| `src/breakout_research/campaign.py:171` (`_verify_stale_checkpoint`) | `stored_code != code_hash` | `LIVE_VS_RECORDED` | `research_state/checkpoint.json` |
| `src/breakout_research/campaign.py:189` (`_verify_pilot_gate`) | `auth.get('code_hash') != code_hash` | `LIVE_VS_RECORDED` | `research_state/campaign_authorization.json` |
| `src/breakout_research/backtest/shards.py:480` (`ResultStore.reconcile`) | `manifest.get("code_hash") != self.code_hash` | `LIVE_VS_RECORDED` | `research/results_manifest.json` |
| `src/breakout_research/pilot_gate_validator.py:93` (`_validate_evidence`) | `evidence.get("code_hash") != code_hash` | `RECORDED_VS_RECORDED` | — (both sides from `research_state/pilot_evidence.json`) |
| `src/breakout_research/pilot_gate_validator.py:139` (`_validate_evidence`) | `checkpoint_state.get("code_hash") != code_hash` | `RECORDED_VS_RECORDED` | — (both sides from `research_state/pilot_evidence.json`) |

**Corrected RL1 location:** `src/breakout_research/backtest/shards.py` (line 480) and
`src/breakout_research/campaign.py` (lines 171 and 189). **Excluded:**
`src/breakout_research/pilot_gate_validator.py` (lines 93 and 139).

**1. This record's own correction was incomplete.** Evidence 4 enumerated three sites and
concluded that "only `campaign.py` contains a checkout-dependent comparison". That is wrong for
`backtest/shards.py:480`: `ResultStore` receives the live ordered digest
(`campaign.py:295` -> `campaign.py:319-323` -> `shards.py:349`) and compares it with the
`code_hash` recorded in the results manifest (`shards.py:477`, `shards.py:480`). On a
foreign-order checkout the v1 resume therefore also fails there, with the message *"Result
manifest bound to different spec/code/data versions"* — a third misleading message next to the
two this record already named. The consequence of RL1 is unchanged; the attribution was wrong in
both directions: one file too wide and one file too narrow. The pre-flight covers all three
sites, because it compares the live ordered digest with the authorized value of record.

**2. The immutable artifact was not edited.** `configs/research_v2_code_hash_amendment_1.json`
is byte-identical (`sha256 e5db0d2e...`, `manifest_hash 4409b6af...`) and still records the
original, over-wide location; the verifier proves both.

**3. Swept sites.** The repository-wide sweep for the superseded rule (stage 7 of section 6) was
repeated: the corrected location is now stated by exactly one artifact, the new amendment. The
five test modules that mirror the repository into a temporary directory were corrected in the
same session, because their mirror helper symlinked the **sub**directories of the hashed set and
a test that wrote to `src/breakout_research/backtest/shards.py` through that symlink modified the
real hashed set during this session's first test run. The mirror now copies the hashed set (and
the v2 execution path) recursively, so the working tree can no longer be written through a
symlink. That was an `IMPLEMENTATION_DEFECT` in the test helpers, not a research defect, and it
was repaired before the end of the session; the canonical digest `3e8e4169...` was verified
unchanged afterwards.

**4. Nothing else changed.** The gate stays byte-exact; the authorized value of record stays
`2efd3b18...`; the canonical digest stays `3e8e4169...`; no v1 or v2 artifact was edited; no
run happened; no candle was read; the confirmatory window stays `NOT_STARTED` with
`holdout_exposed_count = 0`.

## BRAIN-011 — The v2 confirmatory evaluation has no executable, authorized path: the protocol preregisters the evaluation, the code that would perform it is half-built and untested, and two frozen artifacts state different confirmatory decision criteria

**Priority:** P1 — the confirmatory evaluation is the last research step of the campaign. It cannot
run before `2027-01-17T22:00:00Z`, so the path that will perform it must exist, be authorized and be
independently verified well before that date; every day it is deferred shortens the runway.
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`
(design, prerequisites, staged steps, tests and rollback are explicit below; **not implemented in the
session that wrote this record**, README Section 2A C1)
**Cause labels:** `IMPLEMENTATION_DEFECT` (the committed path is half-built: no package init, no
runner, no data path, no authorization, no verifier, no tests), `RESEARCH_DESIGN_RISK` (two frozen
artifacts state different confirmatory decision criteria — see evidence 5), `UNKNOWN` (whether the
three committed modules are correct: they have never been executed by any test)
**Confidence:** the evidence below was re-executed read-only in this session against the live tree at
HEAD `72a7eb4e` (2026-10-20T10:0xZ, working tree clean, 435/435 tests green, all 18 v2 verifiers
exit 0).

### Evidence (revalidated 2026-10-20, branch `main`, HEAD `72a7eb4e`, working tree clean)

**1. The confirmatory execution path is half-built and used by nothing.** `src/v2_confirmatory/`
contains exactly three modules — `errors.py` (53 lines), `identity.py` (128 lines), `scope.py`
(130 lines) — committed by the controller checkpoint `72a7eb4e`. There is **no `__init__.py`**
(the directory is importable only as a PEP 420 namespace package), **no** data loader, **no**
readiness test, **no** runner, **no** authorization artifact, **no** verifier and **no** test
module. A repository-wide search for `v2_confirmatory` finds no import of the package anywhere in
`src/`, `tests/` or `scripts/`: the three modules have never been executed. The commit that carried
them was a controller checkpoint, not a decision record, so no rule, acceptance test or rollback
exists for them.

**2. The protocol preregisters the evaluation and authorizes nothing.**
`configs/research_v2_confirmatory_protocol.json` (`manifest_hash bba95394...`, created
2026-10-20T08:00:00Z) fixes the window (opens `2026-10-19T22:00:00Z`, ≥ 2,160 closed hourly
candles, single-use, never reused from v1), the data path ("retrieval happens once after the
readiness test passes"; "every read counted in `holdout_exposed_count`"), the evaluation rule (the
unchanged v1 metric and cost scenarios, no retuning/ranking/grid extension on the window), the
reporting/falsifiers and the authorization boundary, and it states verbatim: *"This protocol
authorizes nothing."* It does **not** specify the executable path, the output layout, the attempt
budget, the exposure-accounting mechanism, the readiness test, or the preconditions that would let a
run start.

**3. The window cannot exist yet, so the work available now is the path itself.** The window needs
≥ 2,160 closed hourly candles after it opens at `2026-10-19T22:00:00Z`; the earliest possible end is
`2027-01-17T22:00:00Z`. `research/data_manifest_v2.json` still records
`confirmatory_window_status = NOT_STARTED` and `holdout_exposed_count = 0`. Therefore the only
remaining preparatory work in the whole v2 chain is building, authorizing and verifying the path.

**4. The engine that will compute the result may not be edited.** `compute_code_hash()` walks every
`*.py` file under `src/breakout_research` recursively, and that tree's canonical digest
`3e8e4169...` is bound by five frozen artifacts (`research/universe_manifest_v2.json`,
`research/data_manifest_v2.json`, `configs/research_v2_candidate_freeze.json`,
`configs/research_v2_execution.json`, `configs/research_v2_execution_amendment_1.json`) and by the
identity of the **executed** 497,664-record v2 selection run
(`configs/research_v2_selection_authorization_1.json`, `research/ledger_v2.json`,
`research/results_manifest_v2.json`, `research/v2_selected_configurations_manifest.json`,
`configs/research_v2_confirmatory_protocol.json`). The confirmatory path must therefore live
**outside** the hashed set and *import* the v1 engine unchanged — exactly as `src/v2_campaign/`
does. The three committed modules already follow this rule: `identity.py` implements the portable
`canonical_source_digest_v1` identity of BRAIN-009 and the composite
`run_code_identity = digest(hashed set) ⊕ digest(execution path)`, and `scope.py` builds the scope
from `research/v2_selected_configurations_manifest.json` (whose per-asset entries do carry the
`selected` / `config_id` fields the module reads — the skeleton agrees with the manifest).

**5. The material finding — two frozen artifacts state different confirmatory decision criteria.**
The frozen v2 specification and the confirmatory protocol do not agree on what "passing" the
confirmatory window means:

| Source | Criterion for the confirmatory outcome |
| --- | --- |
| `configs/research_v2.json` → `holdout.promotion_rule.criteria` (hash-bound, immutable) | `net_total_return > 0` at 1x costs; `net_total_return > 0` at 2x costs; `closed_trades >= 30`; the evaluated parameters are byte-identical to the frozen v2 candidate manifest entry. Status vocabulary: `CANDIDATE_PENDING_HOLDOUT`, `PROVISIONAL_HISTORICAL_SURVIVAL`, `REJECTED_ON_HOLDOUT`, `INCONCLUSIVE` |
| `configs/research_v2_confirmatory_protocol.json` → `reporting_and_falsifiers` (hash-bound, immutable) | **pass**: the net result at baseline costs *exceeds the buy-and-hold baseline's* net result; **failure**: it is below it; **inconclusive**: insufficient data in the window, or a zero-trade outcome |

These can disagree, and the disagreement is not cosmetic. A configuration with `net_total_return =
+5%` and 40 trades is `PROVISIONAL_HISTORICAL_SURVIVAL` under the specification and a **failure**
under the protocol, because the protocol compares against buy-and-hold (which the specification's
promotion rule never mentions). The specification's status vocabulary also contains `INCONCLUSIVE`
without defining it, while the protocol defines `INCONCLUSIVE` to include a zero-trade outcome — a
case the specification's `closed_trades >= 30` criterion would otherwise turn into
`REJECTED_ON_HOLDOUT`, i.e. a failure claim about a strategy that was never observed to trade. The
specification's own `reporting_obligation` lists "zero-trade" as a reported outcome *distinct from*
"failed", which supports the protocol's reading.

**This conflict must be reconciled before the first window candle is read, not after.** A
single-use window cannot be "re-graded" once the data has been burned: whichever rule is applied
first is the one that will have been applied to the exposed data, and a rule chosen after seeing
the window is a research-validity violation of exactly the kind this campaign has been built to
avoid. The reconciliation is a *versioned amendment*, because both files are immutable and
hash-bound and neither may be edited.

**6. The specification already fixes the reporting obligation and the counting rule.**
`configs/research_v2.json` → `holdout.v2_confirmatory_window.access_counting`: *"Every read of a
candle inside the confirmatory window increments `holdout_exposed_count` in the v2 checkpoint and is
recorded in the v2 holdout report."* `holdout.v2_holdout_report_required_fields` fixes ten
mandatory report fields (`universe_version`, `snapshot_id`, `candidate_manifest_path`,
`candidate_manifest_hash`, `confirmatory_window_start_utc`, `confirmatory_window_end_utc`,
`candles_evaluated`, `exposure_count`, `per_asset_outcomes`, `comparability_statement`). The
selection run's checkpoint is `research_state/checkpoint_v2.json`; the confirmatory run needs its
own, and the path names already used elsewhere in the repository are
`research_state/checkpoint_v2_confirmatory.json`, `research/shards_v2_confirmatory/`,
`research/ledger_v2_confirmatory.json`, `research/results_manifest_v2_confirmatory.json` and
`research/results_v2_confirmatory.jsonl` (named in
`scripts/verify_research_v2_spec_amendment_1.py:55-59` and
`tests/test_research_v2_spec_amendment_1.py:63-67`).

**7. The preceding step is complete and frozen.** The v2 selection run is `COMPLETED`
(`research/ledger_v2.json`, 497,664 execution units = 18 assets × 2,304 configurations × 4
validation folds × 3 cost scenarios, `holdout_exposed_count = 0`, `v1_artifacts_touched = []`), and
`research/v2_selected_configurations_manifest.json` (`manifest_hash 7acc7fe0...`) freezes the
result: **14 selected configurations** (ADA AVAX BNB DOGE ETH HBAR LTC NEAR SOL SUI UNI XLM XRP ZEC)
and **4 assets without a candidate** (BCH BTC LINK TRX), each `CANDIDATE_PENDING_HOLDOUT`. The
confirmatory evaluation's scope is therefore already determined; nothing about it needs to be
decided, only implemented.

### 1. Causal model

- **Observed facts.** The evaluation is preregistered but not executable (evidence 1–2); the
  execution path exists only as three untested modules (evidence 1); the window cannot exist before
  2027-01-17 (evidence 3); the engine is frozen (evidence 4); two frozen artifacts disagree on the
  decision criterion (evidence 5); the reporting obligation and the counting rule are already fixed
  (evidence 6); the scope is frozen (evidence 7).
- **Root cause.** The campaign advanced from *preregistration* to *execution* one artifact at a
  time, and the confirmatory step stopped at the preregistration: the protocol was written (08:00Z)
  but the executable path was never designed, so a half-built module set was committed by a
  controller checkpoint without a decision record, and the criterion conflict between the
  specification and the protocol was never reconciled — both because neither has a consumer yet.
- **Why it is not a prompt defect.** README Section 2A A/C/D already require reconstructing the
  state from the artifacts, classifying the blocker and choosing one bounded task. The gap was
  between two artifacts that both had to be read together (the specification's `holdout` block and
  the protocol's `reporting_and_falsifiers` block) — a research-design conflict, not a missing
  instruction.

### 2. Designs compared

| | **A. Implement the path now, from the protocol alone** | **B. Reconcile the criteria first, then implement the path (chosen)** | **C. Defer everything to 2027-01-17** |
| --- | --- | --- | --- |
| Rule set used for the outcome | whichever the implementer reads first — the conflict surfaces *after* the window is burned | the specification's preregistered rule is authoritative; the protocol's buy-and-hold comparison is computed and reported alongside it, and every disagreement is reported | the same conflict, discovered in January, with the window already exposed |
| Exposure risk | the window is single-use; a mis-specified criterion cannot be undone | none: no read happens | none before the window exists |
| Research validity | violated: the outcome rule is chosen after the data | preserved: the rule is fixed before the read and the disagreement is disclosed | violated in January |
| Cost | lowest now | one extra versioned amendment artifact now | highest later, under time pressure, with an untested path |
| Failure mode | an evaluation is run and graded against an ambiguous rule | the amendment is forgotten and the implementation session re-derives the rule | the January session improvises the path, the criterion and the layout at once |
| Verdict | rejected | **chosen** | rejected |

### 3. The decision (rules only)

**D-1 — Scope.** The evaluation scope is exactly the 14 selected configurations of
`research/v2_selected_configurations_manifest.json` (`manifest_hash 7acc7fe0...`), bound to the
selection authorization (`76be0d3b...`), the v2 specification (`49fb0814...`), the v2 data manifest
(`9f64d8d1...`) and the v2 candidate freeze (`5a56b3d8...`). The scope may not be widened, narrowed
or re-ranked. The 4 assets without a candidate (BCH BTC LINK TRX) are **reported as "no candidate —
not evaluated"**, never silently dropped. The frozen parameters of each selected configuration are
evaluated byte-identically; no re-tuning, no re-ranking and no grid extension on the window.

**D-2 — Window data artifact and its path.** The retrieved window data is recorded in a new
self-hashed artifact **`research/v2_confirmatory_window_manifest.json`**, which records the window
bounds, the retrieval timestamp, the per-asset dataset hashes, the closed-candle count per asset,
the coverage gaps, the exposure events and the readiness record, and which references the v2 data
manifest by hash. *Correction to the committed skeleton:* `src/v2_confirmatory/scope.py` currently
looks for `configs/research_v2_confirmatory_window_manifest.json`; the path is corrected to
`research/…` because **data** artifacts live under `research/` in this repository (next to
`research/data_manifest_v2.json`), while `configs/` holds preregistered configuration and protocol
artifacts. The frozen `research/data_manifest_v2.json` is **not** edited; the new manifest extends
it by reference, exactly as the candidate freeze extends the universe manifest.

**D-3 — Readiness test without a payload read.** Readiness is decided by a **bounded metadata-only
probe** that fetches **no candle payload**: the provider's server time (`/api/v3/time`) and the spot
exchange status of the 14 pairs (`/api/v3/exchangeInfo`), on the primary host and, if it fails, the
documented failover host (`data-api.binance.vision`) under the frozen failover policy
(`configs/research_v2.json` → `data.failover_policy`: one bounded request to the primary host, the
failover host is used and **both statuses with timestamps are recorded**). Readiness passes iff the
observed provider server time is at or after `2027-01-17T22:00:00Z` (i.e. ≥ 2,160 closed hourly
candles have closed since the window opened) **and** all 14 pairs are `TRADING` on the spot venue.
The probe is **not** a window read and does **not** increment `holdout_exposed_count`; it is
recorded in the window manifest with endpoint, observed HTTP status (or transport error), timestamp
and the exact command. The metadata endpoints used by the probe are recorded by the amendment of
D-5, because the frozen specification's `data` block names only the klines endpoint.
*Rejected alternative:* counting the window's closed candles by fetching them — that **is** a candle
read and would consume the window's single use before the authorized retrieval.

**D-4 — Single-use exposure accounting.** `holdout_exposed_count` lives in the confirmatory
checkpoint `research_state/checkpoint_v2_confirmatory.json` (as the specification's
`access_counting` requires) and is mirrored into the window manifest and the report. Rules:
(a) the counter increments **once per exposure event**, where an exposure event is identified by
`(run_id, asset, window bounds)`; (b) a **retry** of the same asset under the same run and the same
bounds is a *continuation* of that event — it does not increment the counter again, and it is
recorded with its own timestamp and outcome; (c) a retrieval of an asset already exposed under
**different** bounds, or of an asset outside the frozen scope, is **refused**; (d) the counter never
decreases — a reset attempt fails closed; (e) once the counter is > 0 the window is spent: the only
permitted continuation is a **resume of the same authorized run** over the same scope using the
already-retrieved, hash-verified datasets, never a fresh evaluation with a different rule set.

**D-5 — Criterion precedence and the protocol amendment (the reconciliation of evidence 5).**
`configs/research_v2_confirmatory_protocol_amendment_1.json` (versioned, self-hashed, immutable)
records, and does not edit either frozen artifact:
1. **Precedence.** The frozen specification's `holdout.promotion_rule` is **authoritative** for the
   confirmatory status, because it is part of the hash-bound preregistration and BRAIN-006 already
   established that the preregistered rule governs candidate promotion. The protocol's
   buy-and-hold pass/failure criterion is **also computed and reported**, as a secondary field
   (`baseline_comparison`), because it costs no additional exposure: both are derived from the same
   single window evaluation. It never assigns the status.
2. **Verdicts.** `PROVISIONAL_HISTORICAL_SURVIVAL` iff all four specification criteria hold;
   `REJECTED_ON_HOLDOUT` iff the evaluation is conclusive and at least one criterion fails;
   `INCONCLUSIVE` iff the window data is insufficient (coverage gaps that prevent an evaluation) or
   the configuration produced **zero** closed trades on the window — a never-traded strategy is not
   reported as a failure, because the data cannot support that claim, and the specification's
   `reporting_obligation` lists "zero-trade" as an outcome distinct from "failed". A configuration
   with 1–29 closed trades fails the `closed_trades >= 30` criterion and is
   `REJECTED_ON_HOLDOUT`.
3. **Disagreement is disclosed.** Where the specification's verdict and the protocol's
   buy-and-hold criterion disagree, the report carries both, marks the asset
   `criteria_agreement = DISAGREE`, and states the disagreement in the summary. The specification's
   status vocabulary is not extended: `criteria_agreement` is a report **field**, not a status.
4. **No silent re-grading.** The amendment is committed **before** the first window candle is read.
   A rule chosen after the window is exposed is forbidden, and the amendment's own commit is
   recorded in its `durability` block (as the protocol's `durability` block does).

**D-6 — Output layout.** New confirmatory paths only; the v1 paths and the v2 *selection* paths are
forbidden:
`research/shards_v2_confirmatory/`, `research/results_manifest_v2_confirmatory.json`,
`research/results_v2_confirmatory.jsonl`, `research/ledger_v2_confirmatory.json`,
`research_state/checkpoint_v2_confirmatory.json`, `research/v2_confirmatory_window_manifest.json`,
`reports/confirmatory_evaluation_v2.json`, `reports/confirmatory_report_v2.md`. The v2 selection
outputs (`research/shards_v2/`, `research/ledger_v2.json`, `research/results_manifest_v2.json`) are
never read as tallies and never mixed; the 497,664 selection units are not extended by confirmatory
results.

**D-7 — Authorization.** A new versioned artifact
`configs/research_v2_confirmatory_authorization_1.json` (self-hashed, immutable) authorizes **at
most one logical confirmatory run** and records: the scope (D-1), the window, the data boundary
(one retrieval, after the readiness test), the output paths (D-6), the code identity (D-9), the
attempt budget (D-8), the preconditions below, the stopping conditions, the falsifiers and the
rollback. It references the protocol (`bba95394...`) and the amendment of D-5 by hash.
**Preconditions — all must hold, or the runner refuses to start:**
(a) the authorization, the protocol and the amendment are committed (a commit that carries them
exists); (b) the readiness probe of D-3 has passed and its record is in the window manifest;
(c) `holdout_exposed_count == 0`, or the run is a resume of the same exposure event (D-4);
(d) the live code identity equals the recorded identity (D-9);
(e) the scope equals the frozen selected-configurations manifest (D-1);
(f) the v1 artifacts and the v2 selection outputs are byte-unchanged.

**D-8 — Attempt budget, resume and rollback.** One logical run; `max_attempts = 1` for the
evaluation. Technical retries *before* the first payload read are allowed up to
`max_retries_on_technical_failure = 3`, matching the frozen `data.max_retries`; after the first
payload read only a **resume** of the same run is permitted (D-4b). An abort before any payload read
rolls back every artifact the run created and leaves `holdout_exposed_count = 0`. An abort **after**
a payload read leaves the exposure in place: the run is recorded as `EXPOSED_ABORTED`, the window
is spent, and the report must state that the window was consumed without a completed evaluation.

**D-9 — Code identity.** The identity of a confirmatory run is the composite canonical digest of the
hashed set (`src/breakout_research`, canonical digest `3e8e4169...`, unchanged) and the
confirmatory execution path (`src/v2_confirmatory`) under BRAIN-009's
`canonical_source_digest_v1`, exactly as `src/v2_campaign/identity.py` and the selection
authorization's `code_identity` block define it. The checkout-dependent ordered digest
`compute_code_hash()` is reported as an environment fact and is never used as an identity; the
authorized value of record `2efd3b18...` and `research_state/campaign_authorization.json` stay
untouched. The hashed set is **not** edited — the path imports the v1 engine unchanged.

**D-10 — Verification.** A read-only offline verifier `scripts/verify_v2_confirmatory_path.py`
(exit 0/1, JSON report) checks: the execution path's module set and canonical digest; the scope (14
in, 4 out) against the frozen manifest hash; the authorization's preconditions and code identity;
the window manifest's absence (before the window exists) and, when present, its hash binding,
coverage and exposure count; that `holdout_exposed_count` has never been reset; that no v1 path and
no v2-selection path was written by the confirmatory path; that `research_state/campaign_authorization.json`
and the hashed set are untouched; and that the criterion precedence of D-5 is recorded. A
deterministic offline test module `tests/test_v2_confirmatory_path.py` covers the rules and the
tamper cases.

**D-11 — Reporting.** The confirmatory report (`reports/confirmatory_evaluation_v2.json` +
`reports/confirmatory_report_v2.md`) contains the ten fields the specification requires
(`holdout.v2_holdout_report_required_fields`) and, per in-scope asset: the selected `config_id`,
the net result on the window at 1x/2x/3x costs, the closed-trade count, the buy-and-hold baseline
net result, the specification's status, the `baseline_comparison` outcome, `criteria_agreement`, and
the verdict criteria evaluated one by one. The 4 assets without a candidate are listed as "no
candidate — not evaluated". If **no** asset survives the confirmatory rule, that outcome is reported
as such; a null result is never hidden, and no asset is dropped from the report.

### 4. Falsifying evidence (what would overturn this decision)

- If the implementation requires an edit under `src/breakout_research/` — D-9 is wrong and the
  confirmatory path cannot be built without rotating the hashed set; the design must be redone.
- If the readiness test provably cannot be performed without fetching a candle payload — D-3 is
  wrong and the single-use accounting must be redesigned **before** any read.
- If the frozen specification is found to be superseded by a later preregistration that states the
  criterion unambiguously — D-5's precedence is wrong and the amendment must record the newer
  source.
- If the window manifest cannot be hash-verified against the v2 data-manifest scheme — D-2's data
  path must be re-preregistered before any read.
- If the exposure counter cannot be made monotonic across a resume — D-4 is insufficient and the
  single-use rule cannot be enforced.

### 5. Rollback

The implementation is **additive**: new files under `src/v2_confirmatory/`, `scripts/`, `tests/`,
`configs/` and `research/`. Deleting them restores the pre-implementation state. No frozen artifact
is edited, so no hash chain breaks and no re-authorization is needed. The three committed skeleton
modules are either completed or replaced; whichever happens is recorded in the implementation note
with the reason, and the skeleton's current bytes remain in git history (`72a7eb4e`) either way.

### 6. Staged acceptance tests (a later implementation session — NOT this one)

1. `src/v2_confirmatory/` is a real package: `PYTHONPATH=src python3 -c "import v2_confirmatory"`
   succeeds, `__init__.py` exists, and no module runs anything on import.
2. The canonical digest of the hashed set still equals `3e8e4169...`, and it is **order-independent**
   (a perturbed enumeration order produces the same digest) — the BRAIN-009 rule is enforced, not
   assumed.
3. The scope built from the frozen manifest is exactly 14 in scope and 4 out of scope, bound to
   `7acc7fe0...`; a widened, narrowed or re-ranked scope raises `ScopeError`.
4. The readiness function raises `WindowNotReadyError` for a stubbed clock before
   `2027-01-17T22:00:00Z` and passes at or after it, **with the provider probe injected** — the test
   performs **no** network call.
5. The authorization validator refuses to authorize when: the exposure count is ≠ 0, the code
   identity does not match the live tree, the scope does not match the manifest, the authorization or
   the amendment is not committed, or the window manifest is absent when the run is requested.
6. The exposure counter increments exactly once per exposure event, does not increment on a
   continuation of the same event, and never decreases — each branch is exercised.
7. The criterion reconciliation is implemented: the specification's status is assigned, the
   buy-and-hold comparison is reported alongside, a disagreement is marked `DISAGREE`, and the
   zero-trade case is `INCONCLUSIVE` rather than `REJECTED_ON_HOLDOUT`.
8. The test suite creates **no** confirmatory artifact: no shard, ledger, results manifest, result
   row, window manifest or checkpoint is produced by any test, and the confirmatory window remains
   `NOT_STARTED` with `holdout_exposed_count = 0`.
9. `scripts/verify_v2_confirmatory_path.py` exits 0 on the delivered tree, and its tamper tests
   detect: a widened scope, an edited authorization, a mismatched code identity, a reset exposure
   counter, a forbidden v1 path in the output layout, and a flipped criterion precedence.
10. The full suite stays green, the v1 artifact sha256 anchors are unchanged
    (`configs/research_v1.json 558d6099...`, `research/universe_manifest.json c8f367d2...`,
    `research/data_manifest.json cf39de42...`, `research/candidate_manifest.json 87589f83...`,
    `research/candidate_manifest_v2.json a68b061a...`), the v2 artifact hashes are unchanged
    (`4e927e52...`, `9f64d8d1...`, `49fb0814...`, `5a56b3d8...`, `aa902aa9...`, `bba95394...`), and
    the hashed set's canonical digest is unchanged.

### 7. Prerequisites for the implementation session

- `research/v2_selected_configurations_manifest.json` (`7acc7fe0...`),
  `configs/research_v2_confirmatory_protocol.json` (`bba95394...`), `configs/research_v2.json`
  (`49fb0814...`), `research/data_manifest_v2.json` (`9f64d8d1...`) — all present and verified.
- The v1 engine `src/breakout_research` — read-only for this work; the path imports it.
- The committed skeleton `src/v2_confirmatory/{errors,identity,scope}.py` — to be validated against
  the manifest and either completed or replaced, with the choice recorded.
- `pytest` and `numpy` installed in the environment (they are absent from a fresh container —
  install them before claiming a test result).
- The producer/verifier/test pattern of `configs/research_v2.json` →
  `scripts/verify_research_v2_spec.py` → `tests/test_research_v2_spec.py`.

### 8. Planned rule → code → test map (for the implementation session)

| Rule | Planned implementation | Planned test |
| --- | --- | --- |
| the path is a package that runs nothing on import | `src/v2_confirmatory/__init__.py` | import + no-side-effect test |
| the run identity is the portable composite digest | `src/v2_confirmatory/identity.py` (committed) | order-independence + equality with `3e8e4169...` |
| the scope is the frozen 14/4 set | `src/v2_confirmatory/scope.py` (committed) | scope equality + tamper (widened scope) |
| the window data is recorded in a new hash-bound manifest | `src/v2_confirmatory/data.py` + `research/v2_confirmatory_window_manifest.json` | schema + hash-binding test |
| readiness without a payload read | `src/v2_confirmatory/window.py` | stubbed-clock test, no network |
| single-use exposure accounting | `src/v2_confirmatory/exposure.py` | increment / continuation / monotonicity tests |
| the specification's criterion governs, the protocol's is reported | `src/v2_confirmatory/report.py` | verdict, `DISAGREE` and zero-trade tests |
| the run is bounded and authorized | `src/v2_confirmatory/runner.py` + `configs/research_v2_confirmatory_authorization_1.json` | precondition-refusal tests |
| the output layout touches no v1 and no v2-selection path | `src/v2_confirmatory/scope.py` | forbidden-path tests |
| the criterion conflict is reconciled by a versioned amendment | `configs/research_v2_confirmatory_protocol_amendment_1.json` | amendment self-hash + precedence test |
| the whole path is independently verified | `scripts/verify_v2_confirmatory_path.py` | verifier tamper tests |

### 9. Do NOT (this session and the implementation session)

- **This session:** do not implement the path, do not write the package's missing modules, do not
  write the authorization or the amendment, do not probe the provider, do not read a candle inside
  the confirmatory window, do not run any evaluation.
- **The implementation session:** do not edit anything under `src/breakout_research/` (the hashed
  set); do not edit any frozen artifact (`configs/research_v1.json`, `configs/research_v2.json`,
  `configs/research_v2_execution.json`, `configs/research_v2_execution_amendment_1.json`,
  `configs/research_v2_candidate_freeze.json`, `configs/research_v2_confirmatory_protocol.json`,
  `research/universe_manifest.json`, `research/data_manifest.json`,
  `research/candidate_manifest.json`, `research/candidate_manifest_v2.json`,
  `research/universe_manifest_v2.json`, `research/data_manifest_v2.json`,
  `research/v2_selected_configurations_manifest.json`, `research/ledger_v2.json`,
  `research/results_manifest_v2.json`); do not read a candle inside the confirmatory window; do not
  contact the provider; do not run the evaluation; do not write any v1 or v2-selection path; do not
  re-run a producer script that would rewrite an existing artifact without `--force` and a recorded
  reason; do not re-retrieve the market-cap snapshot.

### 10. Implementation note

**Written 2026-10-20 (implementation session, separate from the session that wrote this record).**

**1. What was implemented.** The confirmatory evaluation path is now a complete, authorized, verified and
tested executable path. Nothing ran: the window cannot exist before `2027-01-17T22:00:00Z`, no candle was
read, no provider was contacted, no evaluation was executed, and no confirmatory artifact exists in the
repository.

**2. Files added.**
- `src/v2_confirmatory/__init__.py` — the package init (the directory is now a regular package; the
  `__init__` of the 10:30Z checkpoint session was kept and extended with the public API).
- `src/v2_confirmatory/data.py` — the data path: kline parsing, the window filter (only candles that close
  inside the window), the gap detection, the canonical hourly CSV rendering/parsing of the frozen
  `sha256-canonical-hourly-csv-v1` scheme, and the window-manifest builder (D-2).
- `src/v2_confirmatory/window.py` — the metadata-only readiness probe and its verdict (D-3).
- `src/v2_confirmatory/exposure.py` — the single-use exposure accounting (D-4).
- `src/v2_confirmatory/report.py` — the verdict rules of D-5 and the holdout report (D-11).
- `src/v2_confirmatory/artifacts.py` — the builders of the authorized output layout: the result rows, the
  results manifest, the ledger, the checkpoint and the markdown report (D-6/D-11). Every builder is pure.
- `src/v2_confirmatory/runner.py` — the bounded run: the plan, the preconditions, the evaluation and the
  persistence of the whole layout (D-7/D-8/D-9).
- `configs/research_v2_confirmatory_protocol_amendment_1.json` — the criterion reconciliation
  (`manifest_hash 2701c63456e080b1a8a0cbcd478d1bf4dc04d35212f4f270ea88d7460f56f377`), built by
  `scripts/build_v2_confirmatory_protocol_amendment_1.py`.
- `configs/research_v2_confirmatory_authorization_1.json` — the authorization of at most one logical run
  (`manifest_hash f411aba94231e36a4dd711376df8a182a979f20d0a248076db0d5eacfaeef943`), built by
  `scripts/build_v2_confirmatory_authorization_1.py`.
- `scripts/verify_v2_confirmatory_path.py` — the read-only offline verifier (D-10).
- `tests/test_v2_confirmatory_path.py` — 48 deterministic, offline tests.

**3. Files changed.**
- `src/v2_confirmatory/scope.py` — the window-manifest path corrected from `configs/` to `research/`
  (D-2) and the scope-equality check added. Nothing else changed.
- `src/v2_confirmatory/__init__.py` — the public API of the package.
- `research_state/brainstorming_queue.md` — this note.

**4. The committed skeleton.** `errors.py` and `identity.py` are kept **byte-for-byte** (they were correct
and are bound by the artifacts that record the canonical digests). `scope.py` is kept with exactly one
correction — the window-manifest path (D-2) — plus the scope-equality check the record requires; the
skeleton's bytes remain in git history at `72a7eb4e` either way.

**5. Verified commands and exit statuses (2026-10-20).**
- `PYTHONPATH=src python3 -m pytest tests/ -q` → **483 passed**, exit 0 (435 pre-existing + 48 new in
  `tests/test_v2_confirmatory_path.py`).
- `python3 scripts/verify_v2_confirmatory_path.py` → `"ok": true, "failures": []`, exit 0.
- All 18 repository verifiers exit 0 (`verify_cycle_results.py` is a per-cycle tool that takes a directory
  argument and is not a repository-wide verifier).
- The hashed set's canonical digest is still `3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`;
  the confirmatory execution path's canonical digest is `fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10`;
  the composite run identity is `fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8`.
  `compute_code_hash()` returns `608c7340…` — an environment fact of this checkout, never an identity; the
  authorized value of record `2efd3b18…` is untouched.
- The v1 artifact sha256 anchors are unchanged (`configs/research_v1.json 558d6099…`,
  `research/universe_manifest.json c8f367d2…`, `research/data_manifest.json cf39de42…`,
  `research/candidate_manifest.json 87589f83…`, `research/candidate_manifest_v2.json a68b061a…`) and the v2
  artifact hashes are unchanged (`4e927e52…`, `9f64d8d1…`, `49fb0814…`, `5a56b3d8…`, `aa902aa9…`,
  `bba95394…`, `7acc7fe0…`, `76be0d3b…`).
- **No confirmatory artifact exists**: no window manifest, no shard, no ledger, no results manifest, no
  result row, no confirmatory checkpoint and no report. `research/data_manifest_v2.json` still records
  `confirmatory_window_status = NOT_STARTED` and `holdout_exposed_count = 0`.

**6. The rule → code → test map (section 8, filled in).**

| Rule | Implementation | Test |
| --- | --- | --- |
| the path is a package that runs nothing on import | `src/v2_confirmatory/__init__.py` | `test_the_confirmatory_path_is_a_real_package`, `test_importing_the_confirmatory_path_runs_nothing` |
| the run identity is the portable composite digest | `src/v2_confirmatory/identity.py` (committed, unchanged) | `test_the_hashed_set_digest_is_unchanged_and_order_independent`, `test_the_execution_path_digest_binds_this_package` |
| the scope is the frozen 14/4 set | `src/v2_confirmatory/scope.py` | `test_the_scope_is_the_frozen_fourteen_and_four`, `test_a_widened_narrowed_or_reranked_scope_is_refused` |
| the window data is recorded in a new hash-bound manifest | `src/v2_confirmatory/data.py` | `test_the_window_dataset_is_hash_verified_and_gaps_are_recorded`, `test_the_run_counts_every_read_in_the_exposure_counter` |
| readiness without a payload read | `src/v2_confirmatory/window.py` | `test_the_readiness_test_refuses_before_the_window_end`, `test_the_readiness_test_passes_at_the_window_end_and_reads_no_candle`, `test_the_readiness_probe_uses_only_metadata_endpoints`, `test_the_readiness_probe_does_not_read_a_candle` |
| single-use exposure accounting | `src/v2_confirmatory/exposure.py` | `test_the_exposure_counter_increments_once_per_event`, `test_a_continuation_of_the_same_event_does_not_increment`, `test_a_read_under_different_bounds_is_refused`, `test_a_read_outside_the_scope_is_refused`, `test_the_exposure_counter_never_decreases` |
| the specification's criterion governs, the protocol's is reported | `src/v2_confirmatory/report.py` | `test_the_specification_criterion_governs_and_the_baseline_is_reported`, `test_a_disagreement_is_marked_and_the_status_vocabulary_is_not_extended`, `test_the_zero_trade_case_is_inconclusive_and_not_a_failure`, `test_a_low_trade_count_is_rejected_on_the_holdout` |
| the run is bounded and authorized | `src/v2_confirmatory/runner.py` + `configs/research_v2_confirmatory_authorization_1.json` | `test_the_authorization_validates_against_the_delivered_tree`, `test_the_authorization_is_refused_when_its_code_identity_is_stale`, `test_the_authorization_is_refused_when_the_scope_is_widened`, `test_the_authorization_is_refused_when_it_is_edited`, `test_the_authorization_is_refused_when_a_path_points_at_a_v1_artifact`, `test_the_preconditions_refuse_an_uncommitted_run`, `test_the_preconditions_refuse_a_missing_readiness_record`, `test_the_preconditions_refuse_a_window_that_is_already_exposed`, `test_the_preconditions_refuse_a_changed_v1_artifact` |
| the output layout touches no v1 and no v2-selection path | `src/v2_confirmatory/runner.py` (`FORBIDDEN_OUTPUT_PATHS`) + `src/v2_confirmatory/artifacts.py` | `test_the_run_writes_only_the_confirmatory_paths`, `test_the_run_never_writes_the_repository_paths`, `test_the_verifier_detects_a_forbidden_v1_path` |
| the criterion conflict is reconciled by a versioned amendment | `configs/research_v2_confirmatory_protocol_amendment_1.json` | `test_the_amendment_records_the_precedence_and_edits_no_frozen_artifact`, `test_the_verifier_detects_a_flipped_criterion_precedence` |
| the whole path is independently verified | `scripts/verify_v2_confirmatory_path.py` | `test_the_verifier_passes_on_the_delivered_tree` + the six tamper tests of D-10 (widened scope, edited authorization, mismatched code identity, reset exposure counter, forbidden v1 path, flipped precedence) |
| the run's own accounting survives an abort and a resume | `src/v2_confirmatory/runner.py` | `test_an_abort_before_the_first_payload_read_rolls_back`, `test_an_abort_after_a_payload_read_keeps_the_exposure`, `test_a_resumed_run_does_not_read_the_window_a_second_time` |
| the suite creates no confirmatory artifact | — | `test_the_run_never_writes_the_repository_paths`, `test_the_verifier_detects_a_window_that_was_never_read` |

**7. Deviations and clarifications, with their reasons.**
1. **The evaluated window's length is fixed at 2,160 hours.** The record fixes a *minimum* number of closed
   candles and an *earliest possible* end, but does not say what happens when the run happens later and more
   candles exist. Leaving that open would give the run a discretionary choice of window length, which is a
   hidden degree of freedom on a single-use window. The authorization therefore records an
   `evaluation_window_rule`: the evaluated window is exactly the first 2,160 closed hourly candles at or after
   the window start, i.e. it ends at the earliest instant the frozen boundary allows. The rule is recorded in
   the authorization, in the ledger, in the report and in the window manifest.
2. **The output layout is produced by the code, not only declared.** The authorization of D-6 lists eight
   paths; the runner now writes all of them (window manifest, per-asset result shard, result stream, ledger,
   results manifest, checkpoint, report JSON, report markdown) and the verifier checks that none of them
   exists today.
3. **The retrieved window datasets are persisted, so a resume never reads the window twice.** D-4(e) permits
   only a resume of the same run over the already-retrieved, hash-verified datasets; that requires the
   datasets to be stored. Each asset's window dataset is persisted in the canonical hourly CSV of the frozen
   hash scheme next to a record that binds it to `(run_id, asset, window bounds)` and to its content hash; a
   resumed run reloads and re-verifies it instead of reading the window again.
4. **The immutable anchors are recorded in the authorization.** Precondition (f) ("the v1 artifacts and the
   v2 selection outputs are byte-unchanged") needs a fixed reference; the authorization records the sha256 of
   the five v1 evidence files and of the six v2 selection outputs, and the runner and the verifier both check
   them.
5. **The benchmark asset.** None of the 14 selected configurations uses the `btc_ema_168` trend filter, so the
   data scope is exactly the 14 in-scope assets and `BTCUSDT` is **not** read. The runner still implements the
   general rule (the benchmark joins the data scope when a selected configuration needs it, and is then
   counted as an exposed asset like every other); the authorization records it as `scope.data_scope_rule`.
6. **The readiness probe's endpoints.** D-3 names `/api/v3/time` and `/api/v3/exchangeInfo`; the
   implementation uses exactly those two, on the primary host with the documented failover host, and records
   both statuses with their timestamps. The probe was never executed — the tests inject the clock and the
   probe, and no request leaves the machine.
7. **The tests run the path end-to-end in a synthetic mirror, not in the repository.** Acceptance test 8
   requires that the suite creates no confirmatory artifact and that the window stays `NOT_STARTED` with
   `holdout_exposed_count = 0`. The end-to-end test therefore runs in a temporary directory that holds
   byte-identical copies of the hash-bound artifacts and of the two source trees and **synthetic** candles
   served through an injected retrieval callable, so the real window is never touched and the repository
   never receives a confirmatory artifact. This follows the precedent of
   `tests/test_v2_campaign_execution_path.py`, which runs the v2 selection path against a synthetic fixture
   repository.
8. **The only unrelated working-tree change** is the controller-driven refresh of `authorized_at_utc` in
   `research_state/campaign_authorization.json`, which the repository's own test suite rewrites; its
   `code_hash`, `specification_hash` and `authorized` fields are unchanged.

**8. What remains outstanding.** The run itself: it may not start before the window exists
(`2027-01-17T22:00:00Z` at the earliest), and it then consumes the single use of the window. The
authorization's `durability.authorization_commit` and the protocol's `durability.protocol_commit` are
`PENDING_COMMIT`: the commit that carries them must exist before the first candle is read, and the commit
hashes are recorded by the committing session.

### 11. The preregistered confirmatory runbook — delivered (2026-10-20, separate session)

**What it is.** `configs/research_v2_confirmatory_runbook_1.json`
(`manifest_hash d81d919718f2f100f2e091eed8b43a4a228213313dc1dab0fc1a512e929f2a6a`), built by
`scripts/build_v2_confirmatory_runbook_1.py` and verified by
`scripts/verify_v2_confirmatory_runbook_1.py` (exit 0) with 32 deterministic tests in
`tests/test_v2_confirmatory_runbook_1.py`. The runbook is the **operator procedure** of the single authorized
confirmatory run: the authorization says *what* may be done, the runbook says *in which order*, so the session
that eventually executes the run follows a preregistered procedure instead of improvising one after the
single-use window has been burned. It is a design deliverable: it authorizes nothing, fetches nothing, reads no
candle and writes no confirmatory artifact.

**What it fixes, in rules only.**
1. **The ordered steps** — `PREFLIGHT`, `READINESS_PROBE`, `SINGLE_RETRIEVAL`,
   `DATASET_PERSISTENCE_AND_EXPOSURE`, `WINDOW_MANIFEST`, `PRECONDITION_RECHECK`, `EVALUATION`, `VERDICT`,
   `WRITE_OUTPUT_LAYOUT`, `ACCEPTANCE`; each step states its action, what it may not do and what happens when it
   fails.
2. **The binding identities** — the authorization `f411aba9…`, the protocol `bba95394…`, the amendment
   `2701c634…`, the selected-configurations manifest `7acc7fe0…`, the v2 data manifest `9f64d8d1…`, the v2
   specification `49fb0814…`, the hashed-set canonical digest `3e8e4169…`, the execution-path digest
   `fd748860…` and the composite run identity `fcf8ba95…`.
3. **The failure decision table** — seven modes, each answering the same six questions (detection, response,
   exposure effect, artifact state, resumability, how it is reported): an abort before the first payload read
   (roll back, the attempt is released), an abort after a payload read (`EXPOSED_ABORTED`, the window is spent,
   the persisted datasets are reused by a resume of the same run), a provider or rate-limit failure (the frozen
   retry budget, then a resume), a hash mismatch (refuse, do not repair, do not re-read the window), a
   non-trading or insufficient pair (refuse), a zero-trade or failing asset (report it, never hide it) and the
   case where no configuration survives (the null result is reported).
4. **The acceptance checks** — ten checks, each with the exact verification commands.
5. **What the run may never do** — thirteen prohibitions, from "read the window twice" to "a completed run is
   never re-run".

**Two properties that make the runbook non-vacuous.** The readiness probe the runbook prescribes is checked
against the **delivered** `src/v2_confirmatory/window.py` (its two metadata endpoints, their order and the
primary-to-failover order are read from that source with the Python AST), and the write order of the eight
authorized output paths is checked against the **delivered** `src/v2_confirmatory/runner.py` (the order in which
the runner writes them is read from that source with the Python AST). The producer refuses to write a runbook
whose write order does not match the delivered runner, and the verifier fails when the two diverge. The retry
budget, the backoff and the rate limit are checked against the frozen `configs/research_v2.json` `data` block.

**State verified (2026-10-20).** `PYTHONPATH=src python3 -m pytest tests/ -q` → **515 passed**, exit 0
(483 pre-existing + 32 new). `python3 scripts/verify_v2_confirmatory_runbook_1.py` → `"ok": true,
"failures": []`, exit 0. All 19 repository-wide verifiers exit 0 (`verify_cycle_results.py` is a per-cycle tool
that takes a directory argument and is not a repository-wide verifier). The hashed set's canonical digest is
still `3e8e4169…`, the execution path's is still `fd748860…` and the composite run identity is still
`fcf8ba95…`; `compute_code_hash()` returns `608c7340…` — an environment fact of this checkout, never an
identity. The v1 artifact sha256 anchors are unchanged (`558d6099…`, `c8f367d2…`, `cf39de42…`, `87589f83…`,
`a68b061a…`) and the frozen v2 artifacts are unchanged. **No confirmatory artifact exists** and the
confirmatory window stays `NOT_STARTED` with `holdout_exposed_count = 0`.

**Outstanding.** The run itself — it may not start before `2027-01-17T22:00:00Z` and it then consumes the
single use of the window. The runbook's `durability.runbook_commit` is `PENDING_COMMIT`; the commit that
carries it must exist before the first candle is read. The next preparatory work is the independent audit of the
delivered path against BRAIN-011 (README stage 6) and the campaign-level close-out of the v2 cycle; the
user-authorized BRAIN-012 market-cap expansion design is queued behind them.


### §12 — Independent audit of the delivered v2 confirmatory path (2026-10-20, read-only)

**Scope:** audited the delivered confirmatory path (`src/v2_confirmatory/`) against BRAIN-011, the protocol (`configs/research_v2_confirmatory_protocol.json`), protocol amendment 1, the authorization (`configs/research_v2_confirmatory_authorization_1.json`), the runbook (`configs/research_v2_confirmatory_runbook_1.json`), and the selected configurations manifest. **Read-only; no edits made to source, frozen artifacts, or the execution path.**

**Verification results:**
- `PYTHONPATH=src python3 -m pytest tests/ -q` → **515 passed**, exit 0 (483 pre-existing + 32 new). All verifiers pass including `verify_v2_confirmatory_path.py` and `verify_v2_confirmatory_runbook_1.py`.
- **Identities (from `verify_v2_confirmatory_path.py`):** hashed-set canonical digest `3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff` (unchanged), execution-path digest `fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10`, composite `run_code_identity fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8`. `PYTHONPATH=src python3 -c "from breakout_research import config; print(config.compute_code_hash())"` → `608c7340fa8524921e9378626ac9cd0387f0fad0274e6fa0213a006f47487925` (checkout-dependent environment fact; not an identity). Authorized ordered value `2efd3b18...` untouched.
- **Scope:** 14 in-scope (ADA/AVAX/BNB/DOGE/ETH/HBAR/LTC/NEAR/SOL/SUI/UNI/XLM/XRP/ZEC), 4 out of scope without candidate (BCH/BTC/LINK/TRX). Window opens `2026-10-19T22:00:00Z`, earliest end `2027-01-17T22:00:00Z`, minimum 2160 closed hourly candles, single-use.
- **Bindings:** authorization `f411aba9...`, protocol `bba95394...`, amendment 1 `2701c634...`, selected manifest `7acc7fe0...`, v2 data manifest `9f64d8d1...`, v2 spec `49fb0814...` — all match recorded hashes.
- **State:** no confirmatory artifacts exist (`CONFIRMATORY_ARTIFACTS` all absent). `research/data_manifest_v2.json` records `confirmatory_window_status = NOT_STARTED`, `holdout_exposed_count = 0`. V1 anchors and frozen v2 artifacts byte-unchanged.

**Findings (ranked):**

1. **P0 — Unreachable duplicate rollback block (code defect, must NOT be edited in place).** In `src/v2_confirmatory/runner.py` lines ~1039–1050 there is a second `for path in created_files: ... unlink(); for path in created_dirs: shutil.rmtree(...); raise` block that appears **after** the `raise` at line ~1037 (inside the `except Exception:` handler) — it is unreachable dead code. The execution-path digest `fd748860...` is bound by authorization, protocol/amendment, and runbook; in-place edit would change it and invalidate bindings. **Remedy (versioned amendment):** propose `configs/research_v2_confirmatory_code_hash_amendment_1.json` (or next amendment number) rotating the execution-path digest and updating `binding_identities.code_identity.execution_path_digest` in authorization/protocol/runbook via their amendment paths, plus producer/verifier/tests. **No change made.**

2. **P1 — Readiness probe implementation matches preregistration.** `src/v2_confirmatory/window.py` defines `METADATA_ENDPOINTS` with primary→failover order using `/api/v3/time` and `/api/v3/exchangeInfo` (Binance primary `api.binance.com`, failover `data-api.binance.vision`), `FAILOVER_STATUS_CODES` include 403/429/451/500/502/503/504, `MIN_WINDOW_HOURS=2160`, and `window_bounds()` computes earliest end as `window_start + 2160h`. The runbook correctly states probe is metadata-only (no candle fetch, no `holdout_exposed_count` increment). Tests inject clock/probe so no network calls occur. **OK.**

3. **P1 — Output layout and forbidden paths enforced.** `src/v2_confirmatory/runner.py` defines `DEFAULT_PATHS` writing only to `research/v2_confirmatory_window_manifest.json`, `research/shards_v2_confirmatory/` (shard written as `plan.paths["shards_dir"]`), `research/ledger_v2_confirmatory.json`, `research/results_manifest_v2_confirmatory.json`, `research_state/checkpoint_v2_confirmatory.json`, `reports/confirmatory_evaluation_v2.json`, `reports/confirmatory_report_v2.md` plus results stream. `assert_output_paths_allowed()` and `V1_PATHS_FORBIDDEN`/`V2_SELECTION_PATHS_FORBIDDEN` prevent writing to v1 or v2-selection paths. Runbook write order matches the delivered runner’s sequence. **OK.**

4. **P1 — Exposure accounting and single-use semantics.** `src/v2_confirmatory/exposure.py` tracks `holdout_exposed_count` increments once per exposure event, never decreases; `window_is_spent()` gates abort handling. On abort after payload read, status becomes `EXPOSED_ABORTED` with checkpoint written; before first payload read, attempt is released and window untouched. **OK.**

5. **P1 — Scope/selection binding correct.** `src/v2_confirmatory/scope.py` loads from `research/v2_selected_configurations_manifest.json` (14 in-scope with `selected` entries, 4 out of scope reported). The criterion precedence is bound via protocol amendment 1 (frozen v2 spec governs; protocol’s buy-and-hold criterion reported beside it). **OK.**

6. **P2 — Campaign-level status not updated.** `research_state/continuous_universe_state.json` and `research/campaign_cycles/terminal/` still describe v1 cohort; v2 selection completed but campaign close-out not done. **Remedy:** separate bounded task (documented as next after audit). No change made.

**Conclusion:** The delivered path is correctly preregistered, bound, and verifiably not executed. The only code-level issue is the unreachable duplicate rollback block (P0) which cannot be edited in place due to bound digests — requires a versioned amendment rotating the execution-path digest. All other checks pass; no confirmatory artifacts exist; window remains `NOT_STARTED` with `holdout_exposed_count=0`. The path is ready for independent verification but must not be run before `2027-01-17T22:00:00Z`.


### §13 — The P0 code defect of §12 is remediated by a versioned code-hash amendment (2026-10-20)

**Scope:** implemented the remedy §12 proposed for its finding 1 (the unreachable duplicate rollback
block in `src/v2_confirmatory/runner.py`) as a versioned amendment: the dead code was removed, the
confirmatory execution path's canonical digest was rotated, and the two artifacts that bind that
digest (the authorization and the runbook) carry the rotation **by reference** — neither was edited.
**No confirmatory run was executed:** no candle was read, no provider was contacted, no confirmatory
artifact exists, and the confirmatory window stays `NOT_STARTED` with `holdout_exposed_count = 0`.

**The change (behaviour-preserving).** The removed block was a byte-identical copy of the live
rollback statements, placed after the `raise` of the same `except Exception:` handler, so no control
path reached it. Removing it deletes no reachable statement: the abort-before-the-first-payload-read
rollback, the abort-after-a-payload-read `EXPOSED_ABORTED` checkpoint and the exposure accounting are
byte-for-byte unchanged. The invariant is now machine-checked: the delivered runner (and every module
of `src/v2_confirmatory/`) holds **no statement after a `raise`** in any handler, checked with the
Python AST.

| | before | after |
|---|---|---|
| execution-path canonical digest | `fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10` | `277a4bbec286b581ccb415fd88bb362ca2151e1b67745df23ad6802cee0ed4c9` |
| composite `run_code_identity` | `fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8` | `d6e6bdbf74c8155eb537cdb8b19277f76e5229dc52959ff7ea74fdb8e8f3e5fd` |
| `src/v2_confirmatory/runner.py` sha256 | `6341979babe8fbdc112f883bede4a1c67cc8a1c100e12d5e9749eb050ab4084d` | `e268607e2b77eeec5ccbac470124d804bb34874ec9bcef29bcb30dce0f605136` |
| hashed-set canonical digest | `3e8e4169…` | `3e8e4169…` (**unchanged**) |

**The amendment.** `configs/research_v2_confirmatory_code_hash_amendment_1.json`
(`manifest_hash a2a5492711ffeeb1284469c0ffcecbce5bf32e58ef6e20ee6a182f91041127b1`) records:

* the **rotation** — the previous and the current execution-path digest, the previous and the current
  composite identity, the unchanged hashed-set digest, and the authorized ordered code hash
  `2efd3b18…` (an environment fact, never an identity);
* the **change** — the file, the removed block verbatim (with its digest), its line range in the
  pre-rotation file (1039–1044), the fact that it was unreachable and that the removal has **no
  behavioural effect**;
* the **amended artifacts** — `configs/research_v2_confirmatory_authorization_1.json`
  (`f411aba9…`) and `configs/research_v2_confirmatory_runbook_1.json` (`d81d9197…`) with their
  manifest hashes and file sha256s, the superseded field of each
  (`authorized_run.code_identity`, `binding_identities.code_identity`) and `edited: false`;
* the **precedence** — where an amended artifact's code identity differs from the amendment, the
  amendment governs the code-identity fields only; every other field of the amended artifacts stands,
  and the authorization still permits **at most one logical run**;
* the **resolution rule** — the effective digest is the authorization's when the tree is still the
  frozen tree, and otherwise the amendment's, and only when the amendment hash-verifies and binds
  this very tree; a canonical-digest mismatch is never treated as an environment fact;
* the **correction of the audit's attribution** — §12 claimed that the confirmatory protocol and its
  criterion amendment bind the execution-path digest. **They do not**: neither records an
  execution-path digest, and their code-hash constraint covers the hashed set only. The artifacts
  that bind the digest are the authorization and the runbook. No protocol amendment was needed, and
  no artifact was edited;
* **nothing is authorized** — no candle read, no evaluation, no second run, no code change; the
  commit-before-the-first-read rule stands and `durability.amendment_commit_status` is
  `PENDING_COMMIT`.

**Where the rule lives.** `src/v2_confirmatory/identity.py:resolve_code_identity` is the single
implementation of the resolution; the runner calls it in `build_plan`, and the run's artifacts record
the *effective* identity. The verifiers resolve the same way
(`scripts/verify_v2_confirmatory_path.py`, `scripts/verify_v2_confirmatory_runbook_1.py`), and the
runbook's producer now accepts the rotated state — so the frozen runbook is still reproduced
**byte-for-byte** by its producer, as the frozen authorization is by its own.

**State verified (2026-10-20).** `PYTHONPATH=src python3 -m pytest tests/ -q` → **545 passed**, exit 0
(516 pre-existing + 29 new). `python3 scripts/verify_v2_confirmatory_code_hash_amendment_1.py` →
`"ok": true, "failures": []`, exit 0. All 20 repository-wide verifiers exit 0
(`verify_cycle_results.py` is a per-cycle tool and is not a repository-wide verifier). The hashed
set's canonical digest is still `3e8e4169…`, the execution path's is `277a4bbe…` and the composite
run identity is `d6e6bdbf…`; `compute_code_hash()` still returns `608c7340…`, an environment fact of
this checkout, never an identity. The v1 artifact sha256 anchors are unchanged and the frozen v2
artifacts are byte-unchanged. **No confirmatory artifact exists** and the confirmatory window stays
`NOT_STARTED` with `holdout_exposed_count = 0`.

**Not done, on purpose.** No confirmatory run (it may not start before `2027-01-17T22:00:00Z` and it
then consumes the single use of the window); no second authorization and no reset of the attempt
budget; no edit of any frozen artifact; no campaign-level close-out (§12 finding 6, P2 — still
outstanding as a separate bounded task).

**Outstanding.** The amendment's commit is `PENDING_COMMIT`: the commit that carries it, the
authorization and the runbook must exist before the first candle is read. The run itself remains
blocked by the window.

**Decision update 2026-10-20 UTC (HEAD `37e99599`, canonical source digest `3e8e4169…`):** the
v3 line delivered by BRAIN-012 stage 1 is decided in one respect by a new item, **BRAIN-013** (see
"BRAIN-013" below).

- BRAIN-013 (P1) — `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`. The v3 universe **declares**
  `BTCUSDT` as its benchmark constituent (`research/universe_manifest_v3.json` →
  `benchmark_asset.included_in_universe: true`), but the v3 data manifest contains **no dataset
  for it**, while 576 of the 2,304 inherited configurations (25% of the grid) need the BTC series
  and the frozen engine pairs that series with the asset series **by index**
  (`src/breakout_research/signals/generator.py:90-92`), which contradicts the frozen methodology
  (`docs/research_protocol.md:101` — "Align BTC and target asset by UTC candle close"). The v3
  stage-1 constituent validation covered the derived batch of twenty and never the declared
  benchmark, so the v3 selection run has no lawful benchmark dataset: the only hash-verified BTC
  dataset in the repository (v2's) is 17 hours out of index with the v3 asset window. The decision
  record compares five designs and recommends publishing a v3-bound benchmark dataset and aligning
  by UTC candle close in new code outside the hashed set. The finding also quantifies a deviation
  of the **completed** v1/v2 runs (93,312 of 497,664 v2 records evaluated the BTC filter against a
  BTC EMA taken from a different period), which is recorded for disclosure, not repaired. Nothing
  was implemented in that session, no provider was contacted, and no artifact was edited.

---

## BRAIN-012 — Versioned, auditable market-cap expansion program (v3+)

**Priority:** P1 — future-facing, not blocking the v2 confirmatory evaluation
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` at design time; stage 1 has since been implemented and verified — see "Stage 1 delivered" at the end of this section (`STAGE_1_DELIVERED_AND_VERIFIED`)
**Cause labels:** `SCOPE_DECISION`, `DATA_OR_EXTERNAL_SERVICE`, `PERMANENT_LIMIT`
**Confidence:** high — the v2 chain is complete and immutable; the expansion must be strictly additive.

### Evidence (revalidated against the live tree)

- `configs/research_v2.json` is immutable and hash-bound (`49fb0814…`); its `snapshot_identity` records one in-window CoinGecko retrieval. Re-running or re-timing that snapshot is forbidden.
- `research/universe_manifest_v2.json` (`4e927e52…`) holds 18 validated constituents; `research/data_manifest_v2.json` (`9f64d8d1…`) holds 18 hash-verified datasets; `configs/research_v2_candidate_freeze.json` (`5a56b3d8…`) freezes the candidate set at 2026-10-19T21:30:17Z.
- The v2 selection run completed (`research/ledger_v2.json`, 497,664 units, `holdout_exposed_count = 0`, outcome `CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE`, 14 candidates / 4 without).
- The confirmatory window is `NOT_STARTED`, opens 2026-10-19T22:00:00Z, needs ≥ 2,160 closed hourly candles, earliest end `2027-01-17T22:00:00Z`; it is single-use and is never reused from v1 or read during selection.
- `src/breakout_research/` is the hashed set (`canonical 3e8e4169…`, authorized ordered `2efd3b18…`); `src/v2_campaign/` is digest-bound (`c69cc021…`) by the selection authorization; `src/v2_confirmatory/` is digest-bound (`277a4bbe…`) by the authorization, protocol and runbook.
- The v1 cohort is terminal (`research/campaign_cycles/terminal/exhausted_cohort_2.json`: `AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`); the v2 cycle close-out recorded `current_cycle_id = v2-selection-run-2026-10-20`, `next_cohort_index = 3`, blocking dependency `CONFIRMATORY_WINDOW`.

### Why this needs a design decision

The user explicitly requested that the breakout research program keep adding new candidate assets by market capitalization once the current universe is exhausted. That cannot be done by appending to v1 or v2: every v2 artifact is hash-bound and the v2 confirmatory window is single-use. A naive append would silently widen a frozen candidate set, reuse an exposed holdout, or mix v3 records into v1/v2 ledgers — each of which voids the preregistration. The correct shape is a strictly additive, versioned v3+ path, and the decision between the viable shapes must be recorded before any code is written (README Section 2A C1).

### Causal model

- **Observed fact:** v1 and v2 are complete, frozen and immutable; their holdouts, ledgers and manifests are hash-bound.
- **Inferred root cause of the need:** the program's candidate supply is finite per version; exhaustion is expected and is not a defect, but the *response* to it must be preregistered to remain a research result rather than an ad-hoc extension.
- **Unknowns:** the cadence at which a fresh CoinGecko ranking yields genuinely new eligible names below the prior universe floor; the cost of a full ranking pass against the provider's rate limits; whether a v3 universe will contain enough assets to be worth a run.
- **Downstream risks:** (a) silently widening a frozen set; (b) reusing the v1 or v2 holdout; (c) mixing records across ledgers; (d) reading the v2 confirmatory window early or for selection; (e) hiding a null result ("no new eligible names").

### Alternatives to compare

**Design A — Continuous in-place expansion of v2 (rejected).** Append new constituents to `research/universe_manifest_v2.json` and re-freeze. Rejected: the manifest hash (`4e927e52…`) and the candidate freeze (`5a56b3d8…`) are part of the identity of the already-executed selection run (497,664 units) and of the confirmatory protocol; editing them invalidates the run and the single-use window. Also violates the v2 `supersedes`/identity contract.

**Design B — Versioned v3+ path (recommended).** A new version for each expansion pass: `configs/research_v3.json`, `research/universe_manifest_v3.json`, `research/data_manifest_v3.json`, `configs/research_v3_candidate_freeze.json`, `src/v3_campaign/`, separate shards/ledger/results/checkpoint, separate authorization and holdout accounting, and an append-only cross-version expansion log. The v1 and v2 artifacts are never edited; the v2 confirmatory window is never touched. This is the only design that preserves every frozen identity.

**Design C — Manual, human-triggered expansion (rejected as primary).** A human runs a script on demand. Rejected as the *primary* mechanism because it is not auditable or reproducible and it cannot enforce the "no synthetic data / no threshold reduction / descending market-cap order" invariants; it remains available as a fallback trigger for Design B's bounded cadence.

### Recommendation

**Design B**, with Design C's manual trigger retained as a fallback. Concretely:

1. **Preregister first.** Before any retrieval, produce a versioned `configs/research_v3.json` (immutable, self-hashed) that fixes the retrieval window, the ranking source, the asset-exclusion rules (carried verbatim from v1/v2), the history floor (≥ 26,280 closed hourly candles), the gap-recording rule, and the candidate-freeze precondition. No code under `src/breakout_research/` or `src/v2_campaign/` is touched; new code lives in `src/v3_campaign/`.
2. **Retrieve once.** One bounded, read-only request to the frozen CoinGecko endpoint inside the pinned window, storing raw response bytes, sha256 and retrieval timestamp (the P2 pattern). The v2 snapshot is never re-retrieved or re-timed.
3. **Validate every candidate.** Binance spot `<SYMBOL>USDT` verification through the documented failover, ≥ 26,280 closed hourly candles with coverage gaps recorded, hash-verified datasets, exclusion with a recorded reason for every failure (the P3 pattern). No synthetic data, no silent history-threshold reduction, no invented assets.
4. **Freeze before selection.** `configs/research_v3_candidate_freeze.json` and `research/v3_selected_configurations_manifest.json`-path equivalents are committed and hash-bound before any selection or confirmatory-window candle is read.
5. **Separate namespaces.** `research/shards_v3/`, `research/ledger_v3.json`, `research/results_manifest_v3.json`, `research/results_v3.jsonl`, `research_state/checkpoint_v3.json`, and a v3 holdout counter that starts at 0 and is counted on every read. No writes into v1/v2 paths.
6. **Unchanged rules.** The strategy grid, costs, folds, selection rule and causal execution rules of `configs/research_v1.json` are inherited byte-equal by `configs/research_v3.json` unless a separate preregistered mutation is authorized.
7. **Append-only cross-version expansion log.** A new artifact (e.g. `research/v_universe_expansion_log.json`) records, per version, the snapshot identity, the candidate set, the validation/exclusion results and the floor below which the next version's new names must fall. Later batches contain only genuinely new eligible names below the prior universe floor.
8. **Cadence, not polling.** A full fresh ranking pass that yields no currently eligible new symbols records the observed endpoint, timestamp, ranking depth and validation/exclusion results, enters `AWAITING_NEW_CANDIDATES`, and schedules the next pass at a bounded cadence (not on every five-minute agent activation). The program is not called permanently complete because one snapshot contains no additional eligible names.
9. **Routing.** Completion or exhaustion of one frozen version routes to preregistration of the next version, never to rewriting the finished snapshot.

### Decision criteria (D-1 … D-9)

- **D-1** Expansion is a new version, never an edit: no v1 or v2 artifact, manifest, ledger, shard or holdout record is modified; `src/breakout_research/` and `src/v2_campaign/` are untouched unless a separate explicit versioned decision demonstrates that this is unavoidable and addresses authorization/hash rotation.
- **D-2** New code lives outside the hashed set (`src/v3_campaign/` or later), mirroring the `src/v2_campaign/` precedent; the v1 code hash `2efd3b18…` and the v2 execution-path digest `277a4bbe…` stay unchanged.
- **D-3** The v2 confirmatory window is never read, re-timed, reused or extended by an expansion pass; a v3 expansion does not touch it.
- **D-4** The market-cap snapshot is retrieved once per version, inside its pinned window, with raw bytes + sha256 + timestamp stored; no re-retrieval of the v2 snapshot.
- **D-5** Every candidate is validated against real provider data with the P3 rules; excluded assets carry a reason; no synthetic data, no silent history-threshold reduction, no invented assets.
- **D-6** The candidate set is frozen and hash-bound before any selection or confirmatory read; the scope is never widened, narrowed or re-ranked after the freeze.
- **D-7** Each version has its own authorization (`at most one` logical run), verifier, tests, holdout accounting and report; the authorization records the code identity under the canonical digest rule.
- **D-8** A null result (no new eligible names) is reported and recorded, not hidden; the program enters `AWAITING_NEW_CANDIDATES` and re-checks at a bounded cadence.
- **D-9** Before any v3 execution: hash-verified specification, manifest verifier, deterministic tests, explicit scoped run authorization, distinct result namespace, independently verifiable holdout-exposure controls, rollback and negative-result handling.

### Falsifying evidence

- A v3 run whose `holdout_exposed_count` is non-zero, or whose records appear in `research/results.jsonl` or `research/results_v2.jsonl`.
- A v3 candidate set that contains an asset already present in v1 or v2, or one that re-ranks the v2 selection.
- A v3 artifact whose `supersedes`/identity chain does not point at the immediately preceding version's manifest identity.
- A v3 run that edits `src/breakout_research/` or `src/v2_campaign/` without a recorded authorization/hash-rotation decision.
- A v3 selection that uses the v2 confirmatory window or the v1 holdout.

### Rollback

- A v3 version is abandoned by deleting its `src/v3_campaign/` package, its `configs/research_v3*.json`, its `research/*_v3*` artifacts and its test/verifier modules; the v1 and v2 artifacts, ledgers, shards and holdouts are untouched by construction (separate namespaces). The append-only expansion log records the abandoned attempt and its reason.
- No rollback of v1 or v2 is ever required or permitted.

### Staged acceptance tests (for the later implementation session)

1. `configs/research_v3.json` is self-hashed and immutable; its `snapshot_identity` is complete and self-consistent; it inherits the v1 grid/costs/folds/selection byte-equal.
2. The v3 universe/data manifests carry the v3 snapshot-identity tuple and `supersedes` referencing the v2 manifest identity.
3. The v3 candidate freeze is hash-bound and matches the validated v3 constituents exactly; excluded assets carry reasons.
4. `src/v3_campaign/` is outside the hashed set; `compute_code_hash()` and the canonical digests are unchanged.
5. All v3 verifiers exit 0; the full suite stays green; no v1/v2 artifact sha256 changes.
6. No v3 result row, shard, ledger, result manifest, checkpoint or holdout exposure exists until an authorized run.
7. The expansion log is append-only and records the prior floor and the new candidates.
8. A null result (no new eligible names) is recorded and enters `AWAITING_NEW_CANDIDATES` with a bounded next-pass cadence.
9. A v3 run (when later authorized) writes only to v3 paths and never to v1/v2 paths.
10. The v2 confirmatory window remains `NOT_STARTED` with `holdout_exposed_count = 0` throughout.

### Implementation note

**Not implemented in this session** (README Section 2A C1): this is a decision record only. The first implementation session delivers the v3 specification, snapshot retrieval, validation, candidate freeze and verifier — nothing runs, no provider is contacted beyond the single bounded retrieval, no v1/v2 artifact is edited, and no `src/breakout_research/` or `src/v2_campaign/` file is touched. The confirmatory evaluation of v2 remains blocked until `2027-01-17T22:00:00Z` and is unaffected by this record.

**Marked:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`.

### Stage 1 delivered — v3 specification, snapshot, validation, candidate freeze (2026-10-20, implementation session)

**Marked:** `STAGE_1_DELIVERED_AND_VERIFIED` — stage 2 (the v3 execution protocol and the bounded run authorization) is queued; nothing runs, no v3 execution artifact exists.

**Delivered and verified (all digests recomputed from the files on disk):**

- `configs/research_v3.json` — the preregistered v3 specification (`specification_hash d6a5f8bb…`), immutable, with the pinned retrieval window, the published exclusion amendment reference, the v2 floor rule, the holdout rules and the expansion program.
- `configs/research_v3_exclusion_amendment_1.json` — the published v3 exclusion classifier (`amendment_hash f26848d8…`).
- `research/v3_evidence/raw_market_cap_response.json` — the one bounded in-window CoinGecko retrieval (sha256 `01384576…`, retrieved `2026-10-20T11:45:59Z`, inside the pinned window `2026-10-20T11:45:00Z` … `2026-10-27T11:45:00Z`). It was **not** re-retrieved; every later step reads the stored bytes.
- `research/universe_manifest_v3.json` (`manifest_hash e53db5ed…`) and `research/data_manifest_v3.json` (`manifest_hash 6793d86c…`) — the P2/P3 evidence: 20 candidates below the v2 floor, **6 validated** (AAVEUSDT, ICPUSDT, PEPEUSDT, QNTUSDT, SHIBUSDT, WLDUSDT) with 26,280 hash-verified closed hourly candles each, **14 excluded with a recorded reason** (`binance_spot_unavailable` ×6, `insufficient_hourly_history` ×8), shortfall 14, no backfill and no substitute.
- `configs/research_v3_candidate_freeze.json` (`manifest_hash 12a981b1…`) — the frozen artifact, **byte-unchanged**; the correction is carried by `configs/research_v3_candidate_freeze_amendment_1.json` (`manifest_hash 1f0f3d65…`), which records the validated set of six by reference and authorizes nothing.
- `configs/research_v3_spec_amendment_1.json` (`manifest_hash cda06af6…`) — corrects the one stale reference the v3 specification inherited from v2 (`universe.eligibility_validation.data_integrity.data_manifest` named the v2 data manifest) by reference, and reconciles P2/P3/P4 as delivered.
- `research/v_universe_expansion_log.json` — the append-only hash chain (v3 entry `entry_hash 02b36a25…`, `previous_entry_hash: null` because v1 and v2 predate the log); the builder refuses a second v3 entry.
- Verifiers: `scripts/verify_research_v3_spec.py`, `scripts/verify_research_v3_manifests.py`, `scripts/verify_research_v3_candidate_freeze.py`, `scripts/verify_v3_candidate_freeze_amendment_1.py`, `scripts/verify_v3_spec_amendment_1.py`, `scripts/verify_v3_universe_expansion_log.py` — all exit 0. Tests: six v3 modules, 63 tests.

**Defects found in the first stage-1 delivery and how they were corrected** (no frozen artifact was edited in place):

1. The P2/P3 validation had never been performed — the manifests carried `validated: false`, `candles_verified: false`, `observed_candle_count: 0` and `content_hash: null`. Corrected by running the real validation and rebuilding both manifests (`scripts/v3_constituent_validation.py`, CLI `scripts/build_v3_manifests.py`).
2. The candidate freeze had frozen the derived batch of twenty and asserted `validated: true` for every one of them. Corrected by reference through the freeze amendment 1; the freeze verifier now resolves the effective candidate set through the verified amendment and **fails** when the amendment is absent.
3. `scripts/verify_research_v3_manifests.py` — the verifier the frozen exclusion amendment names — did not exist. Written; it re-derives the candidate batch from the stored snapshot instead of trusting a hand-written list.
4. `research/v_universe_expansion_log.json` did not exist. Written with the v3 entry of the hash chain.
5. No v3 test module existed, although the specification's own P1 evidence names `tests/test_research_v3_spec.py`. Six modules, 63 tests, written.
6. The v3 specification's stale `data_integrity.data_manifest` reference. Corrected by `configs/research_v3_spec_amendment_1.json` and disclosed by the manifest verifier as a warning; without a verified amendment the manifest verifier fails.
7. **The declared benchmark constituent was never validated.** The v3 universe manifest declares
   `BTCUSDT` as a constituent (`benchmark_asset.included_in_universe: true`) but the v3 data
   manifest contains no dataset for it, because the constituent validation processed only the
   derived batch of twenty. 576 of the 2,304 inherited configurations need the BTC series and the
   engine pairs it with the asset series by index, so the v3 selection run has no lawful
   benchmark dataset. Decided by **BRAIN-013** below; not corrected in stage 1, and it blocks the
   v3 selection run until the benchmark dataset is published.

**Staged acceptance tests (status after stage 1):** 1 satisfied (self-hashed immutable specification, byte-equal inherited blocks, 2,304 configurations); 2 satisfied (snapshot-identity tuple complete and self-consistent, `supersedes` → v2 manifest identity); 3 satisfied (freeze hash-bound and, through the amendment, exactly the six validated constituents, excluded assets carry reasons); 4 satisfied (no file under `src/breakout_research/` or `src/v2_campaign/` touched; `compute_code_hash()` `608c7340…` is an environment fact, the authorized value of record `2efd3b18…` and the canonical digest `3e8e4169…` are unchanged); 5 satisfied (all v3 verifiers exit 0; the full suite is 608/608 green; no v1/v2 artifact sha256 changed); 6 satisfied (no v3 result row, shard, ledger, result manifest, checkpoint or holdout exposure exists — `research/shards_v3/`, `research/ledger_v3.json`, `research/results_manifest_v3.json`, `research/results_v3.jsonl`, `research_state/checkpoint_v3.json` are all absent); 7 satisfied (the expansion log is append-only and records the prior floor and the new candidates); 8 not applicable to this pass (the pass yielded new eligible names, so `AWAITING_NEW_CANDIDATES` was not entered; the bounded P7D next-pass cadence is recorded in the log entry); 9 and 10 open — they belong to the authorized v3 run, which does not exist yet; the v2 confirmatory window stays `NOT_STARTED` with `holdout_exposed_count = 0`.

---

## BRAIN-013 — The v3 universe declares a benchmark constituent it does not contain, and the frozen engine pairs the BTC series with the asset series by index

**Priority:** P1 — blocks the v3 selection run; does not block the v2 confirmatory evaluation (which is time-blocked until `2027-01-17T22:00:00Z`)
**Status:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`
**Cause labels:** `SCOPE_DECISION`, `RESEARCH_DESIGN_RISK`
**Confidence:** high — every fact below is recomputed from the repository by `scripts/report_v3_benchmark_dependency.py` and locked by `tests/test_v3_benchmark_dependency.py`.

### Evidence (revalidated against the live tree at `37e99599`)

- The v3 universe **declares** the benchmark: `research/universe_manifest_v3.json` →
  `benchmark_asset = {symbol: BTCUSDT, role: trend_filter_and_benchmark, included_in_universe: true}`,
  and `configs/research_v3.json` → `universe.benchmark_asset = "BTCUSDT"`. The frozen v1
  methodology requires it (README Section 3: "Include BTCUSDT as a benchmark and as the BTC
  trend-filter input even if BTC is not otherwise included in the eligible universe").
- The v3 data manifest **does not contain it**: `research/data_manifest_v3.json` has 14 asset
  entries and 6 validated `content_hashes` (AAVEUSDT, ICPUSDT, PEPEUSDT, QNTUSDT, SHIBUSDT,
  WLDUSDT) and **no `BTCUSDT` entry**. The v1 precedent is the opposite: the v1 universe's
  `eligible_assets` do not contain BTC either, but the v1 **data manifest** does
  (`research/data_manifest.json` → `assets.BTCUSDT`), as does the v2 data manifest
  (`research/data_manifest_v2.json` → `assets.BTCUSDT`, content hash `740f3590…`). The v3
  delivery broke that precedent: the stage-1 constituent validation processed the derived
  batch of twenty and never the declared benchmark.
- A quarter of the inherited grid needs the BTC series: `research/config_manifest.json` holds
  2,304 configurations, of which **576** use `trend_filter = btc_ema_168` (576 per trend
  filter, 25% of the grid). The v3 specification inherits the grid byte-equal, so a v3 run
  that cannot supply an index-aligned BTC series cannot evaluate those 576 configurations per
  asset.
- The frozen engine pairs the BTC series with the asset series **by index**, not by timestamp:
  `src/breakout_research/signals/generator.py:90-92` compares `closes[i]` with `btc_ema_168[i]`
  where `i` indexes the *passed* candle list, and `src/breakout_research/backtest/backtester.py:203-207`
  slices the **asset** series to the fold window while `btc_candles` is passed through unsliced.
  The behavioural probe in `scripts/report_v3_benchmark_dependency.py` shows a BTC series with
  identical values at different instants produces identical signals (`probe_timestamps_ignored`),
  while changing the BTC value at one index changes the outcome (`probe_index_value_used`).
- The frozen methodology says the opposite: `docs/research_protocol.md:101` — "**BTC Filter:**
  Align BTC and target asset by UTC candle close" — and `:102` — "No forward-fill for missing BTC
  observations". The implementation therefore contradicts the frozen protocol text for every
  validation fold whose start is not the dataset start.
- The windows differ. The six validated v3 assets share one window
  (`2023-10-21T11:00:00Z` … `2026-10-20T10:00:00Z`, 26,280 candles each); the v2 BTC dataset
  covers `2023-10-20T18:00:00Z` … `2026-10-19T17:00:00Z`. The index-0 candles are **17 hours
  apart**, so index `i` of the v2 BTC series is a different instant from index `i` of a v3 asset
  series, and the v3 assets' last 17 candles have no BTC counterpart at all.
- The v2 line was internally consistent in its **windows**: all 18 v2 assets and BTC share the
  identical window (`2023-10-20T18:00:00Z` … `2026-10-19T17:00:00Z`). **Corrected 2026-10-20:** the
  original text of this record concluded from that that "index alignment equalled timestamp
  alignment for the first validation fold". It did not: the first validation fold starts at 40% of
  the span, so the engine paired the asset's fold-window index `i` with the BTC candle at the
  **start of the history**, 10,512 h earlier. Index alignment equals timestamp alignment only for
  the *development* prefix of the dataset, which no validation fold is.
- Consequence for the **completed** v1 and v2 runs (recorded, not repaired here): the ledger
  (`research/ledger_v2.json`) shows 41,472 configuration units and 497,664 execution units
  (18 assets × 2,304 configurations × 4 validation folds × 3 cost scenarios). The BTC filter
  therefore covers 124,416 v2 records (25%). **Corrected 2026-10-20:** the original text of this
  record claimed that 93,312 records (folds 1–3) were misaligned and that fold 0 (31,104 records)
  was aligned. Recomputation from the frozen fold rule
  (`scripts/report_v1_v2_btc_alignment_deviation.py` →
  `research/v3_evidence/v1_v2_btc_alignment_deviation.json`) shows that **no validation fold was
  aligned**: the per-fold offsets are −10,512 h (fold 0), −13,140 h (fold 1), −15,768 h (fold 2)
  and −18,396 h (fold 3). The affected count is therefore **124,416 of 497,664 records (25%)**,
  not 93,312. The v1 run used the same engine and the same call shape
  (`src/breakout_research/campaign.py:429-435`).
- The v2 **confirmatory** path is not affected: `src/v2_confirmatory/runner.py:640-646` slices
  the asset series **and** the benchmark series to the same window before calling the engine, so
  index alignment equals timestamp alignment there. A v3 confirmatory path that slices both
  series to the window inherits the correct behaviour.
- No v3 execution artifact exists (`research/shards_v3/`, `research/ledger_v3.json`,
  `research/results_manifest_v3.json`, `research/results_v3.jsonl`,
  `research_state/checkpoint_v3.json`, `research/v3_selected_configurations_manifest.json` are
  all absent), and no v3 selection authorization exists. The v2 confirmatory window stays
  `NOT_STARTED` with `holdout_exposed_count = 0`.

### Causal model

- **Observed fact:** the v3 universe declares `BTCUSDT` as a constituent; the v3 data manifest has
  no dataset for it; the inherited grid needs it for 576 of 2,304 configurations per asset; the
  engine pairs it with the asset series by index.
- **Inferred root cause:** the v3 stage-1 constituent validation was scoped to the *derived batch*
  of twenty candidates and did not cover the *declared benchmark* of the same universe version.
  The gap is silent because the universe manifest's `benchmark_asset` block is declarative: no
  artifact in the v3 chain asserts that every declared constituent has a hash-verified dataset.
- **Unknowns:** whether a fresh, index-aligned BTC dataset can be retrieved under the v3 window
  rule from the same provider and endpoint policy the v3 validation used
  (`https://api.binance.com/api/v3/klines` with the documented failover
  `https://data-api.binance.vision/api/v3/klines`); the exact size of the deviation between the
  index alignment actually used by the completed v1/v2 runs and the UTC alignment the frozen
  methodology requires.
- **Downstream risks:** (a) a v3 selection run that reuses the v2 BTC dataset would silently
  evaluate 25% of its grid against a misaligned series; (b) a v3 run that drops the BTC-filter
  configurations would change the inherited grid and the selection rule; (c) an implementation
  that "fixes" the alignment inside `src/breakout_research/` would change the hashed set and
  invalidate the v1 campaign authorization and every v2 identity tuple; (d) a v3 run that keeps
  the index alignment would knowingly contradict `docs/research_protocol.md:101` and would not be
  comparable with the confirmatory evaluation, which aligns correctly.

### Alternatives to compare

**Design A — Publish a v3-bound benchmark dataset and align by UTC candle close (recommended).**
Retrieve BTCUSDT once under the v3 window rule (the same 26,280 closed hourly candles ending at
the last fully closed hour before the v3 market-cap snapshot `2026-10-20T11:45:59Z`, i.e. the
window the six validated assets already use), publish it in a **versioned** v3 data-manifest
amendment (the v3 data manifest itself is hash-bound by the freeze amendment
`1f0f3d65…` and by the execution protocol `9e92a35d…` and is therefore not edited in place), and
have the v3 execution path slice the asset series **and** the benchmark series to the same
fold window before calling the engine, so that the engine's index alignment equals UTC
alignment. Correctness: matches `docs/research_protocol.md:101` exactly. Validity: the v3 result
is produced under the frozen methodology; the deviation from the *v1/v2 implementation* is
disclosed, not inherited. Cost: one bounded provider read, one new dataset, one amendment
cascade (data-manifest amendment → freeze amendment 2 → execution amendment 1) and a new
execution path. Failure modes: the provider may be unavailable (the primary host answered HTTP
451 in earlier sessions; the failover host served the v3 validation on 2026-10-20) — then the run
is `BLOCKED_EXTERNAL`, never a substitute dataset. Reversibility: strictly additive; nothing
already delivered is edited.

**Design B — Reuse the v2 BTC dataset inside the v3 run (rejected).** The v2 dataset is immutable,
hash-verified and entirely before the v3 development boundary (`2026-10-20T13:00:00Z`), so using
it violates no recorded rule. It is nevertheless **index-misaligned with the v3 assets by 17
hours** and 17 candles shorter, and the v3 assets' last 17 candles have no BTC counterpart. The
alternative of trimming every v3 asset to the v2 BTC coverage would move the fold boundaries
(0.065% of the span) and would still leave the benchmark as a v2 artifact inside a v3 run. The
mismatch is a *silent* correctness defect, which is what this record exists to prevent.

**Design C — Drop the BTC-filter configurations from the v3 grid (rejected).** It would remove 576
of 2,304 configurations per asset, i.e. change the grid the v3 specification inherits byte-equal
and change the space the unchanged v1 selection rule ranges over. Forbidden by the inheritance
rule and by BRAIN-012 D-6.

**Design D — Fix the alignment inside the hashed engine and re-run v1/v2 (rejected, out of
scope).** `src/breakout_research/` is the hashed set (canonical digest `3e8e4169…`, authorized
ordered digest `2efd3b18…`). Editing it invalidates the v1 campaign authorization and every v2
identity tuple, and re-running the completed v1 and v2 campaigns is not reproducible inside this
program. The finding is recorded here and must be disclosed in the final report; the v3 path
implements the correct alignment in **new** code outside the hashed set, which is the only place
it can be implemented without voiding the frozen work.

**Design E — Let the v3 run inherit the v1/v2 index alignment (rejected).** It preserves
cross-version comparability but knowingly implements a behaviour the frozen methodology
contradicts, and it would make the v3 selection inconsistent with the v3 confirmatory path,
which aligns correctly. Comparability is preserved instead by *disclosure* of the v1/v2 deviation.

### Recommendation

**Design A**, with **Design B** as the recorded fallback only if the provider is unavailable at
the time of the bounded retrieval, and even then only after a further recorded decision that
accepts the 17-hour misalignment for a *development-only* benchmark. Concretely, the
implementation session must:

1. retrieve BTCUSDT once under the v3 window rule, through the documented primary → failover
   policy, storing the raw response, its sha256 and the retrieval timestamp, exactly as the v3
   stage-1 retrieval did;
2. publish the dataset and its hash-verified entry in a **versioned** v3 data-manifest amendment
   (`configs/research_v3_data_manifest_amendment_1.json`), and re-bind the data-manifest
   identity in a freeze amendment 2 and an execution amendment 1 — the three immutable artifacts
   that name `6793d86c…` are not edited in place;
3. implement the v3 selection execution path in `src/v3_campaign/` (outside the hashed set),
   which slices the asset series **and** the benchmark series to the same fold window before
   calling the frozen engine, and which **fails closed** when the benchmark series is missing,
   not index-aligned, or shorter than the evaluated window;
4. bind the benchmark rule in the v3 selection authorization
   (`configs/research_v3_selection_authorization_1.json`), which must name the benchmark
   dataset, its content hash, the alignment rule and the deviation disclosure;
5. record the v1/v2 deviation (**124,416** of 497,664 v2 records — every validation fold — evaluated
   the BTC filter against a BTC EMA from a different period; the original text of this record said
   93,312 and is corrected above) in the final report, not in a frozen artifact.

### Decision criteria (D-1 … D-8)

- **D-1** No v1 or v2 artifact, manifest, ledger, shard or holdout record is modified; the
  correction is carried by versioned amendments only.
- **D-2** The benchmark dataset is hash-verified and index-aligned with the evaluated v3 assets
  (identical first and last candle timestamps and candle count), or the run fails closed.
- **D-3** The v3 execution path lives outside the hashed set (`src/v3_campaign/`); the hashed-set
  canonical digest `3e8e4169…` and the authorized ordered digest `2efd3b18…` stay unchanged.
- **D-4** The alignment rule follows the frozen methodology (`docs/research_protocol.md:101`):
  the BTC series is aligned to the asset series by UTC candle close, with no forward fill.
- **D-5** The inherited grid, costs, folds, selection rule and metric are unchanged; the BTC
  filter's 576 configurations per asset are evaluated, never dropped.
- **D-6** The development-data boundary stays `2026-10-20T13:00:00Z`; no v2 confirmatory-window
  candle and no v1 holdout is read; `holdout_exposed_count` stays 0.
- **D-7** The provider dependency is bounded: one read of one asset, with the documented failover
  and both HTTP statuses recorded; an unavailable provider yields `BLOCKED_EXTERNAL`, never a
  substitute dataset.
- **D-8** The v1/v2 deviation is disclosed in the final report with its exact count, so the
  completed runs are not read as if they had implemented the protocol's alignment rule.

### Falsifying evidence

- A v3 run whose benchmark series is not index-aligned with the evaluated assets, or whose
  `btc_ema_168` configurations were skipped, dropped or re-derived.
- A v3 artifact that edits `research/data_manifest_v3.json`,
  `configs/research_v3_candidate_freeze_amendment_1.json` or `configs/research_v3_execution.json`
  in place instead of amending them.
- A v3 run whose experiment IDs do not bind the benchmark content hash for the BTC-filter
  configurations (the v1 rule binds the BTC dataset hash into the unit data hash).
- Evidence that a v3-bound BTC dataset is *not* retrievable under the v3 window rule, which would
  demote Design A to `WAITING_EXTERNAL_INTERVENTION` and force the recorded fallback decision.
- Evidence that the UTC alignment changes the selection outcome of a v3 asset, which would make
  the v1/v2 deviation material rather than cosmetic and would require the v2 confirmatory
  protocol to disclose it before the window is read.

### Rollback

- The implementation is additive: `src/v3_campaign/`, the versioned amendments, the new dataset
  and the authorization can be deleted without touching a single v1 or v2 artifact. The append-only
  expansion log (`research/v_universe_expansion_log.json`) records an abandoned attempt and its
  reason.
- No rollback of the v1 or v2 line is ever required or permitted. The v1/v2 deviation is a
  disclosure, not a repair.
- A v3 selection run that has started is never re-run; a boundary abort rolls the ledger back and
  releases the single authorized attempt, as the v2 authorization prescribes.

### Staged acceptance tests (for the later implementation session)

1. The bounded BTC retrieval records the endpoint, both probed HTTP statuses, the raw response
   bytes, their sha256 and the retrieval timestamp, and the dataset is written under
   `research/data/candles_v3/` with the canonical hourly CSV hash.
2. The new BTC dataset's window is **identical** to the six validated v3 assets' window
   (`2023-10-21T11:00:00Z` … `2026-10-20T10:00:00Z`, 26,280 closed hourly candles, no gaps, no
   rejected rows) — recomputed from the manifest, never copied.
3. The benchmark entry is published by a versioned amendment; the v3 data manifest, the freeze
   amendment 1 and the execution protocol are byte-unchanged, and the amendments that re-bind the
   data-manifest identity are hash-bound and self-verifying.
4. `src/v3_campaign/` refuses to run when the benchmark series is missing, shorter than the
   evaluated window, or not index-aligned with the asset series; the refusal is a test, not a
   comment.
5. The v3 execution path slices the asset series and the benchmark series to the same fold
   window; a test asserts that the BTC series the engine receives is the fold-window slice, not
   the full history.
6. The 576 `btc_ema_168` configurations per asset are evaluated; the run's unit count is
   `assets × 2,304 × 4 validation folds × 3 cost scenarios`, and the holdout-position fold is
   never evaluated and `holdout_exposed_count` stays 0.
7. Every v3 verifier exits 0, the full suite is green, the hashed-set canonical digest is still
   `3e8e4169…`, the authorized ordered digest is still `2efd3b18…`, and no v1 or v2 artifact
   sha256 changed.
8. No v3 execution artifact exists before the run: `research/shards_v3/`,
   `research/ledger_v3.json`, `research/results_manifest_v3.json`, `research/results_v3.jsonl`,
   `research_state/checkpoint_v3.json` stay absent; the v2 confirmatory window stays
   `NOT_STARTED` with `holdout_exposed_count = 0`.

### Implementation note

**Not implemented in this session** (README Section 2A C1: the decision record and its
implementation do not belong in the same session). This session delivered the decision record,
the read-only evidence script `scripts/report_v3_benchmark_dependency.py` and the deterministic
test module `tests/test_v3_benchmark_dependency.py` (the facts are recomputed from the
repository, so the module stays green both before and after the implementation). No provider was
contacted, no candle was read or fetched, no v1, v2 or v3 artifact was edited, and no file under
`src/breakout_research/` or `src/v2_campaign/` was touched.

**Marked:** `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION`.

---

## BRAIN-013 implementation record — the benchmark dataset, the amendment cascade and the v3 execution path (2026-10-20T15:45Z, separate session)

**Session:** one bounded implementation session, 2026-10-20T15:4xZ, in a separate session from the
decision record above. **Outcome:** the recommendation's items 1–3 are delivered; item 4 (the v3
selection authorization) and item 5 (the final report) remain outstanding. **No v3 grid, backtest,
campaign or selection was run**, and none is authorized.

### 1. The bounded retrieval (recommendation item 1)

- One bounded read of `BTCUSDT` through the frozen `DataFetcher` and the documented primary →
  failover policy: the primary host `https://api.binance.com/api/v3/klines` answered **HTTP 451**
  on every probe and the failover host `https://data-api.binance.vision/api/v3/klines` answered
  **HTTP 200**; 27 data requests, 54 page records (27 × 451 + 27 × 200).
- Dataset: `research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv`, canonical hourly-CSV
  content hash `50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e`, 26,280 closed
  hourly candles, `2023-10-21T11:00:00Z` … `2026-10-20T10:00:00Z`, no gaps, no rejected rows.
- Evidence: `research/v3_evidence/benchmark_retrieval.json` (retrieval timestamp
  `2026-10-20T15:40:42.912038+00:00`) and the raw provider rows
  `research/v3_evidence/benchmark_raw_klines.json`, file sha256
  `713656198b1a5f3b78e39027e9e0f2415aab6dfdb8f36754c2b50138539892ca`, 26,280 rows.
- The window is **identical** to the six validated v3 assets' window (same first candle
  `1697886000000`, same last candle `1792490400000`, same count 26,280), recomputed from the
  manifest and never copied.
- **Disclosure:** during the first dry run of `scripts/retrieve_v3_benchmark.py`, one unintended
  request was made to the failover host without a `symbol` parameter. It returned an error
  response, no data was retrieved and no artifact was written from it; the 27 recorded requests
  are the bounded retrieval above. No other provider contact was made in this session.

### 2. The amendment cascade (recommendation item 2)

| artifact | manifest hash | what it does |
| --- | --- | --- |
| `configs/research_v3_data_manifest_amendment_1.json` | `f47380c13d1b3de48c76fa00412e4f291cdc573323a064f80da261f647bf582e` | publishes the BTCUSDT entry; records the **effective** data-manifest identity `88e90960034718e067cebdabce6aef02e1c1942cd0ebfbd7a6934fc2fc5ac321` |
| `configs/research_v3_candidate_freeze_amendment_2.json` | `41c5c10515bca609881484adc558481aadda30981ed25125119a235a562f9f1f` | re-binds the frozen candidate set's data-manifest identity; records the benchmark rule |
| `configs/research_v3_execution_amendment_1.json` | `bbd7617835243692a5f3630a39a5b3fbc47e6ed33a0cf4c16aaa3f77b9986816` | re-binds the execution protocol's evaluation-scope identity; records the benchmark rule, the fail-closed list and the deviation disclosure |

- The three immutable artifacts that named the superseded identities — `research/data_manifest_v3.json`
  (`6793d86c…`), `configs/research_v3_candidate_freeze.json` (`c8679832…`) and
  `configs/research_v3_execution.json` (`6793d86c…`) — are **byte-unchanged**; each amendment records
  the sha256 of the artifact it repairs.
- The effective identity is recomputed from the base manifest plus the published entry by the
  verifiers and by the execution path; it is materialized at run time, not stored in a file.
- Each amendment is produced by a deterministic builder (`scripts/build_v3_*_amendment_*.py`, which
  refuse to overwrite without `--force`) and checked by a read-only offline verifier
  (`scripts/verify_v3_*_amendment_*.py`). All three verifiers exit 0.
- The cascade authorizes nothing: `execution_authorized: false`, `grid_run_authorized: false`,
  `selection_authorization_present: false` in both downstream amendments.

### 3. The v3 execution path (recommendation item 3)

`src/v3_campaign/` lives outside the hashed set: `compute_code_hash()` is still
`2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2`, the hashed-set canonical digest
is still `3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff`, and the v3 path has
its own canonical digest `29cd064e3f67e6bb66b052978bba61290adc97d4b3f8f7989fe2a01e1990cd55`
(composite run identity `adbb9b760ac652d4de8fb8764eb85315d8dd5d3d9a419e97d65f97662f3c8fd7`).

- `benchmark.py` — the benchmark rule: the dataset is hash-verified, the asset and the benchmark
  must be index-aligned at the dataset level (identical first candle, last candle and candle
  count), and **both series are sliced to the same fold window** before the frozen engine is
  called, so that the engine's index pairing `closes[i]` / `btc_ema_168[i]` *is* the
  UTC-candle-close alignment of `docs/research_protocol.md:101`. Nothing is forward-filled.
- **Fails closed:** a missing, a shorter and a misaligned benchmark raise
  `BenchmarkAlignmentError` **before** the engine is called (`tests/test_v3_campaign_benchmark_rule.py`).
- **The grid is never reduced:** the 576 `btc_ema_168` configurations per asset are enumerated like
  every other configuration, and the unit data hash of a BTC unit binds the benchmark content hash
  (the v1 rule).
- `scope.py` resolves the frozen scope through the amendment chain (the base freeze binds a
  superseded data-manifest identity; freeze amendment 2 re-binds it) and refuses any authorization
  that does not agree with it; `data.py` resolves the effective data manifest and refuses a dataset
  that reaches into the confirmatory window; `runner.py` executes the bounded run and refuses to
  start without `configs/research_v3_selection_authorization_1.json`, which does not exist.

### 4. The correction carried by this session

The recomputation of the deviation from the frozen fold rule shows that the deviation affects
**every** validation fold, not folds 1–3: the first validation fold already starts at 40% of the
span, so fold 0 is misaligned by −10,512 h as well (folds 1–3: −13,140 h, −15,768 h, −18,396 h).
The affected count is **124,416 of 497,664 v2 records (25%)**, not 93,312. The evidence is
`research/v3_evidence/v1_v2_btc_alignment_deviation.json`
(`scripts/report_v1_v2_btc_alignment_deviation.py`), the disclosure is carried by
`configs/research_v3_execution_amendment_1.json` → `deviation_disclosure`, and the two factual
sentences of the decision record above are corrected in place.

### Staged acceptance tests (status after this session)

1. satisfied — the retrieval records the endpoint, both probed HTTP statuses, the raw response
   bytes, their sha256 and the retrieval timestamp; the dataset carries the canonical hourly CSV
   hash.
2. satisfied — the benchmark window is identical to the six validated v3 assets' window
   (recomputed from the manifest).
3. satisfied — the benchmark entry is published by a versioned amendment; the three base artifacts
   are byte-unchanged; the re-binding amendments are hash-bound and self-verifying.
4. satisfied — `src/v3_campaign/` refuses a missing, a short and a misaligned benchmark, and the
   refusal is a test, not a comment.
5. satisfied — the engine receives the fold-window slice of the benchmark, never the full history
   (asserted against the runner's source and by the alignment tests).
6. satisfied — the 576 `btc_ema_168` configurations per asset are enumerated, the unit count is
   `assets × 2,304 × 4 validation folds × 3 cost scenarios`, the holdout-position fold is never
   enumerated and `holdout_exposed_count` stays 0.
7. satisfied — every v3 verifier exits 0, the full suite is 697/697 green, the hashed-set digest is
   still `3e8e4169…`, the authorized ordered digest is still `2efd3b18…`, and no v1 or v2 artifact
   sha256 changed.
8. satisfied — no v3 execution artifact exists: `research/shards_v3/`, `research/ledger_v3.json`,
   `research/results_manifest_v3.json`, `research/results_v3.jsonl`,
   `research_state/checkpoint_v3.json` are all absent; the v2 confirmatory window stays
   `NOT_STARTED` with `holdout_exposed_count = 0`.

**Marked:** `IMPLEMENTED_STAGE_1_COMPLETE_AUTHORIZATION_OUTSTANDING`.

---

## BRAIN-013 implementation record — the v3 selection authorization 1 (2026-10-20T16:30Z, separate session)

**Session:** one bounded implementation session, 2026-10-20T16:3xZ, in a separate session from the
decision record above. **Outcome:** the recommendation's item 4 is delivered; item 5 (the final
report) remains outstanding. **No v3 grid, backtest, campaign or selection was run**, no
confirmatory-window candle was read, no provider was contacted, and no v1, v2 or frozen v3 artifact
was edited.

### 1. The artifact

`configs/research_v3_selection_authorization_1.json`, manifest hash
`fd91cc4dc907780fc66ffd9c020e53f3c224a5ae8bb688e30cd7bfec04762dcd` — the versioned, hash-bound
artifact that authorizes **exactly one** bounded v3 selection grid run over the frozen candidate
set `["SHIBUSDT","QNTUSDT","AAVEUSDT","WLDUSDT","PEPEUSDT","ICPUSDT"]`.

Every fact it records is recomputed from the repository, never copied out of the artifact it
describes:

| field | recomputed from |
| --- | --- |
| `authorized_run.scope.binance_pairs` | the freeze chain (freeze → freeze amendment 1 → freeze amendment 2) and the v3 universe manifest |
| `authorized_run.bounds` | the frozen candidate count (6) × the inherited grid (2,304) = 13,824 config units; 165,888 execution units (× 4 validation folds × 3 cost scenarios) |
| `authorized_run.data_boundary.candles_before_utc` | the confirmatory-window start of the freeze, `2026-10-20T13:00:00Z` |
| `authorized_run.selection_rule.selection_block_sha256` | the unchanged v1 `selection` block |
| `authorized_run.code_identity` | the source tree, under the canonical digest rule of BRAIN-009 (hashed set `3e8e4169…`, v3 path `29cd064e…`, composite `adbb9b76…`) |
| `authorized_run.benchmark` | the effective data manifest — dataset path, content hash recomputed from the dataset file, the alignment rule and the fail-closed list |
| `authorized_run.effective_data_manifest` | the base manifest plus the published benchmark entry (`88e90960…`) |
| `authorized_run.deviation_disclosure` | `research/v3_evidence/v1_v2_btc_alignment_deviation.json` (124,416 of 497,664 v2 records, all four validation folds) |

The artifact also states what it does **not** authorize: no confirmatory evaluation, no candle
fetch, no source-tree change, no edit of a frozen artifact, no second v3 selection run.

### 2. The producer, the verifier and the tests

- `scripts/build_v3_selection_authorization_1.py` — a deterministic producer that recomputes every
  fact it records and refuses to overwrite an existing artifact without `--force`. It rebuilds the
  artifact byte for byte.
- `scripts/verify_v3_selection_authorization_1.py` — a read-only, offline verifier with thirteen
  checks: the self-hash, the scope, the bounds, the data boundary, the unchanged v1 selection
  rule, the code identity, the output paths, the execution path, the one-run rule, the benchmark
  rule and the effective identity, the deviation disclosure, the execution path's acceptance of
  the authorization (a plan is resolved, nothing is executed) and the executed state.
- `tests/test_v3_selection_authorization_1.py` — 37 deterministic tests, including 16 mirror/tamper
  controls that prove the verifier is not vacuous.

### 3. The state-dependent rules that this session replaced (not deleted)

The cascade verifiers carried the rule "a v3 selection authorization exists" — true while no
authorization existed, false by design once one does. Following the v2 precedent (rule 12 replaced,
not deleted), the rule was **replaced** by a stronger, state-adaptive one: while the authorization
does not exist, no v3 run is authorized; once it exists, it must be the hash-bound artifact that
permits exactly one bounded selection run over the frozen candidate set, with the published
benchmark dataset, the effective data-manifest identity and the deviation disclosure bound into
it. The shared helper is `scripts/v3_benchmark_amendment_common.py` →
`selection_authorization_failures`.

The same replacement was applied in `tests/test_v3_benchmark_amendments.py`,
`tests/test_v3_benchmark_dependency.py` and `tests/test_v3_campaign_benchmark_rule.py` — the last
one now exercises the refusal against a workspace whose authorization file is absent, so the
refusal is still a test and no run is ever started by the suite.

### 4. State verified (2026-10-20T16:30Z)

- `PYTHONPATH=src python3 -m pytest tests/ -q` → **741 passed**, exit 0 (698 pre-existing + 43 new)
- every `scripts/verify_*.py` exits 0 (`scripts/verify_cycle_results.py` requires a `cycle_dir`
  argument and is not a repository-wide gate)
- `scripts/report_v3_benchmark_dependency.py` → `status: BENCHMARK_DATASET_AVAILABLE`,
  `blocking: false`
- `compute_code_hash()` = `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2`; the
  canonical digests are unchanged (hashed set `3e8e4169…`, v2 selection path `c69cc021…`, v2
  confirmatory path `277a4bbe…`, v3 path `29cd064e…`)
- no v3 execution artifact exists (`research/shards_v3/`, `research/ledger_v3.json`,
  `research/results_manifest_v3.json`, `research/results_v3.jsonl`,
  `research_state/checkpoint_v3.json` are all absent); the v2 and the v3 confirmatory windows stay
  `NOT_STARTED` with `holdout_exposed_count = 0`

**Marked:** `IMPLEMENTED_STAGE_1_AND_AUTHORIZATION_COMPLETE_RUN_OUTSTANDING`.

---

## BRAIN-012 implementation record — the published v3 selected-configurations manifest and the v3 execution amendment 2 (2026-10-20T19:2xZ, separate session)

**Marked:** `IMPLEMENTED_AND_VERIFIED` — the v3 line now publishes the outcome of its completed
selection run as a hash-bound, independently re-derivable artifact; the v3 confirmatory
evaluation remains time-blocked.

**Why this step, and why it was not optional.** BRAIN-012 §4 (design point 4) requires that the
candidate set be frozen **and** that a `research/v3_selected_configurations_manifest.json`-path
equivalent be committed and hash-bound before any selection or confirmatory-window candle is
read. The v3 selection run has been performed and verified (`research/ledger_v3.json`,
`status: COMPLETED`, 165,888 execution units, `holdout_exposed_count = 0`), but the published
outcome of that run did not exist: the v2 line had `research/v2_selected_configurations_manifest.json`
and the v3 line had nothing. Every downstream v3 artifact — the confirmatory protocol, the
confirmatory path, the confirmatory authorization — takes its evaluation scope from that
manifest, so its absence blocked the whole remaining v3 line.

**Delivered and verified (all digests recomputed from the files on disk):**

- `research/v3_selected_configurations_manifest.json` (`manifest_hash 3d24a278…`) — the published
  outcome of the authorized v3 selection run over the frozen v3 candidate set. The selection is
  **re-derived** from the 165,888 verified shard records (every `experiment_id` recomputed and
  checked) with the buy-and-hold baselines recomputed from the hash-verified v3 datasets under
  the benchmark rule and the development boundary enforced by the v3 loader; the producer never
  copies the selection out of the run ledger and fails loudly when the re-derivation fails. The
  outcome: `CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE` — **4 candidates** (ICPUSDT `cfg_0444`,
  PEPEUSDT `cfg_1804`, SHIBUSDT `cfg_0544`, WLDUSDT `cfg_1380`) and **2 assets without a
  candidate** (AAVEUSDT `NO_CANDIDATE`, QNTUSDT `INSUFFICIENT_EVIDENCE`), each reported with an
  explicit reason. The 14 excluded constituents stay excluded with their recorded reasons.
- `scripts/publish_v3_selected_configurations.py` — the deterministic producer (refuses to
  overwrite without `--force`).
- `scripts/verify_v3_selected_configurations_manifest.py` — the read-only offline verifier
  (nine numbered rule groups, exit 0/1, JSON report), including a contamination check that the
  v1 and v2 lines are untouched by the v3 line.
- `configs/research_v3_execution_amendment_2.json` (`manifest_hash 7c2f5d2d…`) — the versioned
  amendment that adds the published manifest path to the v3 result layout and binds its hash. It
  authorizes **nothing** else: no second run, no confirmatory evaluation, no candle fetch. The
  v3 execution protocol is not edited; its file digest and its own `specification_hash` are
  recorded in the amendment.
- `scripts/build_v3_execution_amendment_2.py` — the deterministic producer of the amendment
  (recomputes every fact it records; refuses to overwrite without `--force`).
- `scripts/verify_v3_execution_amendment_2.py` — the read-only offline verifier of the amendment.
- `tests/test_v3_selected_configurations_manifest.py` (22 tests) and
  `tests/test_v3_execution_amendment_2.py` (19 tests) — deterministic tests, including 12 tamper
  controls that rebuild the artifacts in a mirrored tree and prove that the verifiers refuse them.

**State verified (2026-10-20T19:2xZ):** full suite **800/800 green** (759 pre-existing + 41 new);
every `scripts/verify_*.py` and `scripts/report_*.py` exits 0; `compute_code_hash()` is still
`2efd3b18…`; the canonical digests are unchanged (`3e8e4169…` hashed set, `c69cc021…` v2
selection path, `277a4bbe…` v2 confirmatory path, `29cd064e…` v3 path); no file under
`src/breakout_research/`, `src/v2_campaign/`, `src/v2_confirmatory/` or `src/v3_campaign/` was
touched; no frozen v1/v2/v3 artifact changed; the v2 and v3 confirmatory windows stay
`NOT_STARTED` with `holdout_exposed_count = 0`; the v3 run was not repeated and no
confirmatory-window candle was read.

**Staged acceptance tests (BRAIN-012 §"Staged acceptance tests", status after this session):**
5 satisfied (all verifiers exit 0; the full suite is green; no v1/v2 artifact sha256 changed);
9 satisfied (the v3 run wrote only to the v3 paths, and the v1/v2 lines are verified uncontaminated
by the v3 line); 10 satisfied (the v2 confirmatory window remains `NOT_STARTED` with
`holdout_exposed_count = 0`). Points 4, 6 and 7 changed state earlier and are recorded in the
BRAIN-013 implementation records: the candidate set was frozen and hash-bound before the run, the
run artifacts exist and are hash-verified, and the expansion log records the v3 entry.

**Still outstanding on the v3 line (queued, not for this session):** the v3 confirmatory
evaluation protocol (a design deliverable), the v3 confirmatory execution path
(`src/v3_confirmatory/`, outside the hashed set) and the v3 confirmatory authorization. The
evaluation itself cannot be performed before `2027-01-18T13:00:00Z`, because the v3 confirmatory
window opens `2026-10-20T13:00:00Z` and needs at least 2,160 closed hourly candles.

---

## BRAIN-012 implementation record — the preregistered v3 confirmatory-evaluation protocol (2026-10-20T20:0xZ, separate session)

**Marked:** `IMPLEMENTED_AND_VERIFIED` — the v3 confirmatory evaluation is now preregistered in
rules; the evaluation itself remains time-blocked until `2027-01-18T13:00:00Z`.

**Why this step, and why it was not optional.** The v3 line had a completed and verified
selection run and a published, hash-bound selection outcome, but **no preregistered
confirmatory protocol** — the artifact that fixes, before any window candle is read, what will be
evaluated, on which window, from which data, under which single decision criterion, and with
which reporting obligation. The v2 line learned this the hard way: it needed
`configs/research_v2_confirmatory_protocol_amendment_1.json` only because two frozen artifacts
(the v2 specification's promotion rule and the v2 protocol's buy-and-hold criterion) stated
**different** confirmatory decision criteria, and a single-use window cannot be re-graded after
it has been burned. The v3 protocol must not repeat that conflict, so it states exactly one
criterion and its verifier proves it.

**Delivered and verified (all digests recomputed from the files on disk):**

- `configs/research_v3_confirmatory_protocol.json` (`manifest_hash f008876b…`, file sha256
  `fba2b60c…`) — the preregistered protocol, self-hashed and immutable. It fixes, in rules only:
  1. **Evaluation scope** — exactly the four published candidates (ICPUSDT `cfg_0444`, PEPEUSDT
     `cfg_1804`, SHIBUSDT `cfg_0544`, WLDUSDT `cfg_1380`), bound to
     `research/v3_selected_configurations_manifest.json` `3d24a278…`, the selection authorization
     `fd91cc4d…`, the v3 specification `d6a5f8bb…`, the effective v3 data-manifest identity
     `88e90960…` and the base identity `6793d86c…`, and the v3 universe manifest `e53db5ed…`.
     The two assets without a candidate are named out of scope **with their reason**
     (AAVEUSDT `NO_CANDIDATE`, QNTUSDT `INSUFFICIENT_EVIDENCE`); the scope may not be widened,
     narrowed or re-ranked.
  2. **Window definition** — opens `2026-10-20T13:00:00Z` (the frozen start; both freeze
     amendments are checked to have left it unmoved), needs ≥ 2,160 closed hourly candles,
     earliest possible end `2027-01-18T13:00:00Z` (recomputed from the start and the length),
     single use, never overlapping the v1 holdout or the v2 confirmatory window, never reused
     from v1 or v2, never used for selection, never ranked or re-tuned on, and never populated
     with data predating the candidate freeze.
  3. **Data path — including the benchmark the v2 protocol never had to name.** The published
     configurations include the `btc_ema_168` family, so the evaluation needs a **BTC series
     covering the window**; it does not exist and cannot exist before the window closes. The
     protocol requires the window's asset candles **and** the window's benchmark series to be
     retrieved **once**, after a readiness test, hash-verified, and index-aligned by UTC candle
     close (the BRAIN-013 rule, `docs/research_protocol.md:101`, no forward fill); it **fails
     closed** when the benchmark is missing, short or misaligned; the 576 `btc_ema_168`
     configurations per asset are never dropped; the development benchmark
     (`50d357b0…`, which does not cover the window) may **not** be substituted for the window
     benchmark; every window read is counted in `holdout_exposed_count`.
  4. **Evaluation rule** — the unchanged v1 evaluation metric, the unchanged cost scenarios
     (1.0 / 2.0 / 3.0, copied from `configs/research_v1.json`), no re-tuning, no re-ranking and no
     grid extension on the window.
  5. **Decision rule — exactly one criterion.** The single preregistered v3 promotion rule,
     copied verbatim from `configs/research_v3.json#holdout.promotion_rule`, with its status
     vocabulary; the verdicts map that one rule onto the vocabulary
     (`PROVISIONAL_HISTORICAL_SURVIVAL` / `REJECTED_ON_HOLDOUT` / `INCONCLUSIVE`, zero trades
     being `INCONCLUSIVE` and never a failure). The verifier scans the whole document for
     criterion-bearing keys and requires **exactly one** — a second criterion anywhere is
     detected.
  6. **Reporting and falsifiers** — every evaluated asset and candidate is reported, the assets
     without a candidate are named, a null result is reported, negative and inconclusive results
     are never discarded, the v1 holdout is never re-opened and the v2 confirmatory window is
     never read; the v1/v2 BTC-alignment deviation (124,416 of 497,664 v2 records, all four
     validation folds) is carried into the final report as a disclosure and is **not** repaired.
  7. **Authorization boundary and code identity** — the protocol authorizes **nothing**: no
     evaluation, no candle read before the window exists, no window-benchmark retrieval. The
     code-identity rule is the portable canonical digest of BRAIN-009
     (`3e8e4169…`), never the checkout-dependent ordered digest; the confirmatory execution code
     must live outside the hashed set; v1 and v2 paths are forbidden and new v3 paths require a
     new versioned amendment.
- `scripts/build_v3_confirmatory_protocol.py` — the deterministic producer. Every field is
  re-derived from the hash-bound artifacts (it refuses to publish against a modified source
  tree, against a moved window and against a benchmark disagreement), the freeze instant is
  pinned, and it refuses to overwrite without `--force`.
- `scripts/verify_v3_confirmatory_protocol.py` — the read-only offline verifier (13 numbered
  rule groups, exit 0/1, JSON report). It recomputes every expectation from the repository: the
  manifest hash, the scope, the window arithmetic, the benchmark rules, the single-criterion
  property, the reporting obligations, the code-hash constraint, the absence of every v3
  confirmatory output path and the v1 artifact digests.
- `tests/test_v3_confirmatory_protocol.py` — 37 deterministic tests, 13 of them tamper controls
  (a tampered scope, a changed configuration id, a widened scope, a second decision criterion, a
  tampered promotion rule, a shortened window, a moved window, a substitutable benchmark, dropped
  BTC configurations, a self-authorizing protocol, a forged manifest hash, a modified hashed
  source tree, a missing v1 artifact, a recorded exposure, an existing confirmatory output path).

**State verified (2026-10-20T20:0xZ):** full suite **837/837 green** (800 pre-existing + 37 new);
every `scripts/verify_*.py` and `scripts/report_*.py` exits 0 (`scripts/verify_cycle_results.py`
requires a `cycle_dir` argument and is not a repository-wide gate); `compute_code_hash()` is
`2efd3b18…` (the authorized value of record, `authorized: true`, `reasons: []`); the canonical
digests are unchanged (`3e8e4169…` hashed set, `c69cc021…` v2 selection path, `277a4bbe…` v2
confirmatory path, `29cd064e…` v3 path); no file under `src/breakout_research/`,
`src/v2_campaign/`, `src/v2_confirmatory/` or `src/v3_campaign/` was touched; no frozen v1/v2/v3
artifact changed; the v2 and v3 confirmatory windows stay `NOT_STARTED` with
`holdout_exposed_count = 0`; no v3 confirmatory output path exists; no confirmatory-window
candle was read; the v3 selection run was not repeated.

**A pre-existing checkout condition was found and repaired (recorded, not hidden).** In this
checkout the gitignored result-stream projection `research/results_v3.jsonl` (199 MB, listed in
`.gitignore` because it exceeds the per-file push limit — residual limitation RL2) was **absent**,
so 4 tests and 5 fixture errors failed in `tests/test_v3_selection_run.py` and
`tests/test_research_v3_manifests.py` with "the run left no result stream". The failure was
reproduced with this session's new files removed, so it is **not** caused by this session: the
shards (`research/shards_v3/v3-campaign/`, 3,323 files) are the authoritative record set and the
stream is their projection. The v3 line had no counterpart of the v2 `scripts/regenerate_v2_result_stream.py`,
so one was written (`scripts/regenerate_v3_result_stream.py`, a faithful v3 counterpart that
re-verifies every experiment id while it writes and renames the projection into place
atomically). The rebuilt file hashes to `63860a7143b79ebc73edbbadfae14629b902862ab51cfbffffdced29ddf466d6`
— **byte-identical to the digest the earlier session recorded for the same stream** — and
`scripts/verify_v3_selection_run.py` independently confirms that it is the projection of the
verified shards. **No grid unit was evaluated, no engine was called and no shard was written:
this is a projection rebuild from the authoritative shards, not a re-run.**

**Still outstanding on the v3 line (queued, not for this session):** the v3 confirmatory
execution path (`src/v3_confirmatory/`, outside the hashed set) and the v3 confirmatory
authorization; then the versioned amendment that reconciles `configs/research_v2.json` (P2/P3
still read `OUTSTANDING` although both are delivered) and the final report once the confirmatory
windows close. The v3 confirmatory evaluation itself cannot be performed before
`2027-01-18T13:00:00Z`, and the v2 confirmatory evaluation not before `2027-01-17T22:00:00Z`.

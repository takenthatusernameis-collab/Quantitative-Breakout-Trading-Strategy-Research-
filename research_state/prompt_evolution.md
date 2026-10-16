# Agent Prompt Evolution Log

This file records evidence-based revisions to the agent-session instructions in `README.md`. It is append-only in intent: preserve earlier entries, correct factual errors with an explicit note, and never erase failed prompt experiments. The quantitative research protocol is governed separately and must not be silently modified by prompt revisions.

## Current policy

- **Prompt contract:** README Section 2A, “Mandatory session continuity, recovery, and self-improving prompt protocol”.
- **Prompt revision introduced:** `P3-2026-10-16-BRAINSTORMING-ESCALATION-GATE` (P2 is preserved below as historical context).
- **Source README commit:** `59162f578e271497f6442752d11ee86a6fd56dd0`.
- **README blob SHA after this revision:** `cea879e5c8fbb2e957cb74809611a44a000cc180`.
- **Initial rollout status:** README prompt updated in `59162f578e271497f6442752d11ee86a6fd56dd0`; workflow startup was updated in `15f5358257e9c34c4f781aab10634cc6ee3cab7c` to read the brainstorming queue and prohibit implementation of the same newly brainstormed root cause in that session. Static repository checks remain separate from behavioral success. Effectiveness is `NOT_YET_VERIFIED` until later sessions demonstrate correct routing. Do not claim that the new gate has already improved outcomes.
- **Prompt regression outcomes:** the mandatory scenario battery is specified in README Section 2A. Actual agent-behavior regressions are **NOT_RUN** until a fresh session exercises the protocol. Static presence checks should be recorded separately from behavioral success.

## P2-2026-10-16-SESSION-CONTINUITY

### Triggering evidence

- A previous Kilo run repeatedly retried a push rejected because the attempted `research/results.jsonl` file was approximately 429.90 MB, ending with a persistence failure: [run #2](https://github.com/takenthatusernameis-collab/Quantitative-Breakout-Trading-Strategy-Research-/actions/runs/38801198121).
- The checked-in data manifest reported synthetic fallbacks for BTCUSDT and ETHUSDT, while the pilot gate recorded campaign authorization.
- The checkpoint reported 81,510 completed records but `last_verified_record: 0`.
- The workflow's initial Kilo instruction was generic and did not explicitly require loading a durable previous-attempt handoff.
- These observations came from the repository and runs inspected at the time; every new session must revalidate them against the latest branch and run state.

### Cause classification

`PROMPT_GAP` for insufficiently explicit cross-session evidence inheritance, failure classification, prompt regression, and handoff requirements. Separate implementation/data/persistence defects remain code and infrastructure tasks; this prompt change does not itself fix them.

### Revision summary

Added a bounded session contract to README Section 2A:
- reconstruct current state and inspect prior successful/failed work;
- label claims by evidence quality and revalidate stale reports;
- classify prompt, implementation, test, data/external-service, platform, permission, and research-design failures separately;
- prioritize one verifiable blocker per session;
- stop unchanged retries against deterministic failures;
- run exactly one prompt-quality review and permit at most one evidence-backed prompt change per session;
- preserve earlier prompt versions and log actual regression results;
- forbid prompt edits from silently changing the frozen quantitative method or weakening holdout/data/persistence safeguards;
- define ten prompt regression scenarios and structured start/end gates;
- require honest separation of attempted, implemented, tested, committed, remotely persisted, research-valid, and economically evaluated states.

Seeded `research_state/agent_handoff.md` with the known issues, evidence links, status caveats, and acceptance criteria. The handoff is a time-stamped historical snapshot and must be refreshed by the next agent.

### Expected effect

Reduce repeated rediscovery, unchanged retries, undocumented failed attempts, stale checkpoint assumptions, unverified campaign authorization, and loss of useful recovery context. This expected effect is a hypothesis, not a measured result.

### Regression tests and actual status

| Scenario | Required behavior | Status at revision |
|---|---|---|
| Permanent oversized-file rejection | Stop unchanged retries; redesign bounded storage and verify commit history | Specified; behavioral test NOT_RUN |
| Synthetic fallback data | Block campaign as invalid data | Specified; behavioral test NOT_RUN |
| Checkpoint/ledger mismatch | Reconcile stable result identities and safely resume | Specified; behavioral test NOT_RUN |
| Stale/mismatched pilot gate | Block authorization | Specified; behavioral test NOT_RUN |
| Holdout contamination | Freeze candidates before accessing holdout | Specified; behavioral test NOT_RUN |
| Unrun tests | Mark NOT_RUN, never PASS | Specified; behavioral test NOT_RUN |
| Worker success but persistence failure | Report persistence failure until remote state is verified | Specified; behavioral test NOT_RUN |
| Repeated failure | Require new evidence or a materially different approach | Specified; behavioral test NOT_RUN |
| Permissions/external limits | Preserve evidence; don't bypass controls or fabricate success | Specified; behavioral test NOT_RUN |
| Stale/untrusted handoff | Revalidate claims against actual repository/run evidence | Specified; behavioral test NOT_RUN |

### Rollback and review rule

If future sessions show that this contract causes prompt churn, repeated work, worse persistence, or weaker research safeguards, preserve the evidence, revise the smallest defective clause, and record a new entry. Do not remove safeguards merely because they block completion. A revision is not considered effective until observed future runs demonstrate the intended behavior.


## P3-2026-10-16-BRAINSTORMING-ESCALATION-GATE

### Triggering evidence

Direct inspection of current tracked source and state showed structural blockers unlikely to be corrected by prompt refinement, extra logging, retries, or workflow hardening alone:
- `load_or_fetch_asset_data()` directly generates synthetic candles, while the checked-in data manifest labels BTCUSDT/ETHUSDT as synthetic fallback data.
- The pilot implementation directly sets `pilot_passed` and `campaign_authorized` to true without deterministic evidence checks.
- The campaign loop iterates all configurations over all folds, including the final holdout, without using `is_holdout` to gate access.
- The campaign restores a checkpoint but resets config/fold/cost cursors at the start of the asset loop; the current checkpoint says 81,510 completed records while `last_verified_record` is 0.
- The current result file is about 51.7 MB; historical run #2 logged a failed ~429.9 MB attempted file push.

Sources are itemized with direct links and statuses in `research_state/brainstorming_queue.md`. The diagnostics JSONL was empty at review time, so these are source/state audit findings rather than events proven to have been captured by the new recorder.

### Cause classification

Primarily `IMPLEMENTATION_DEFECT`, `RESEARCH_DESIGN_RISK`, `PERSISTENCE_FAILURE`, and `PLATFORM_LIMIT`. The observed evidence does not support treating these as mere `PROMPT_GAP` issues.

### Revision summary — minimal instruction change

Added `research_state/brainstorming_queue.md` as a design-decision queue (not a second diagnostic log). Updated README Section 2A and the Kilo startup instruction so that confirmed permanent boundaries, cross-component blockers, and failures surviving two materially different evidence-backed attempts must enter a time-bounded brainstorming phase. Each design record must compare materially different options, state prerequisites/tradeoffs, recommend a staged intervention, specify acceptance evidence and rollback, and mark any unavailable external action. The same root cause must not be implemented in the session that creates its brainstorming decision record. Added the current blockers to the queue and updated the handoff to require brainstorming before implementation.

### Expected effect

Reduce repetitive same-root-cause patching, distinguish actual architectural/platform decisions from prompt gaps, protect research validity, and produce a reviewable deterministic implementation plan. This is a hypothesis, not a measured result.

### Regression scenarios and status

| Scenario | Required behavior | Status at revision |
|---|---|---|
| Confirmed synthetic data path | Enter brainstorming; prohibit economic conclusions and campaign continuation on synthetic data | Static source/manifests verified; agent-behavior regression NOT_RUN |
| Self-authorizing pilot gate | Brainstorm independent deterministic authorization evidence | Static source verified; regression NOT_RUN |
| Holdout exposed before candidate freeze | Brainstorm phase separation and consumed-holdout handling | Static campaign loop verified; result-exposure audit NOT_RUN |
| Resume cursor reset / checkpoint mismatch | Brainstorm stable-ID reconciliation and crash-safe commit protocol | Static code/checkpoint verified; interruption regression NOT_RUN |
| Oversized result persistence | Brainstorm bounded durable storage; never retry the same oversized monolith unchanged | Repository size and historical run evidence reviewed; shard implementation/test NOT_RUN |
| Routine localized test defect | Continue normal bounded correction loop instead of needless escalation | Rule documented; behavioral regression NOT_RUN |
| Transient external failure | Retain bounded transient retry only when evidence supports transience | Rule documented; behavioral regression NOT_RUN |
| External permission/provider prerequisite | Mark `WAITING_EXTERNAL_INTERVENTION`, do not bypass controls | Rule documented; behavioral regression NOT_RUN |

### Rollback and review rule

If future runs show brainstorming merely postpones safe, obvious fixes, revise the entry threshold using evidence. Do not remove the gate for confirmed permanent/structural failures merely to make the workflow appear productive. Keep the queue separate from the one durable workflow error ledger.


## P4-2026-10-16-REAL-DATA-PROVIDER-CONTRACT-IMPLEMENTATION

**Trigger:** Structured source revalidation showed `load_or_fetch_asset_data()` calling the synthetic generator directly, swallowing all data-manifest write errors, and letting the campaign/pilot override the frozen three-year hourly history minimum with `min_candles=1000`. The current manifest labels BTCUSDT/ETHUSDT synthetic, so an ordinary green pilot report cannot support an economic conclusion.

**Prompt improvement:** require a campaign-facing real-provider contract, a specification-derived minimum that caller parameters cannot weaken, fully closed candles, strict timestamp/OHLCV/gap/count validation, atomic content-addressed dataset/manifest persistence, independent cache provenance/hash verification, and fail-closed behavior for provider/manifest failures. Explicitly require preservation of prior synthetic manifest entries as invalidated evidence and make tests cover bad provider/cache paths. Prohibit a full campaign while independent pilot authorization and holdout isolation remain unresolved.

**Changes committed:** provider implementation `5c5ffe56d3ee484da43bf3f8c5044f5560be3028`; caller floor removals `33520ae77dbc18ad2941eacd367245ed3cb11111`, `c808a41844abec367bd4c59a37097c54efefbd0b`; ten new data-contract regression tests `d0c22425b15ec0e3ef545ea4fd140ec838d8a723`. BRAIN-001 is `IMPLEMENTATION_IN_PROGRESS`.

**Evidence status:** commit presence verified through GitHub reads. The execution container could not resolve `github.com`; the repository could not be cloned. Python syntax compilation, pytest execution, live Binance connectivity and the complete three-year canary are therefore `NOT_RUN`. Do not promote to `RESOLVED_VERIFIED` or authorize a campaign based on the commit alone. Next session must re-read `main`, run focused + complete tests, correct any failures, execute a bounded live data canary, and independently verify the remote data and manifest hashes. BRAIN-002–BRAIN-005 remain in brainstorming and were not implemented.


**Follow-up hardening (same P4 cycle):** the real cache must now explicitly declare `fallback_used: false`, the top-level specification hash must match the frozen spec, and cached retrieval metadata must include an approved provider/endpoint, canonical hash algorithm, valid retrieval time, zero rejected rows/gaps, positive request count and exact stored coverage/count. The campaign also fails closed rather than silently skipping a required eligible asset or ignoring failed BTC benchmark loading. Added a regression for ambiguous `fallback_used: "false"` metadata and two campaign hard-stop regressions; the committed test file now contains thirteen tests (`0dbd13c217f18503e928cf3790bd2cdabbf47602`, `60c075b53a94efe0fee5a88c0d7a69ae13758f9c`).

**Still unverified:** GitHub source persistence is verified, but local source compilation, all thirteen tests, live Binance connectivity and data artifact persistence are `NOT_RUN`. The environment could not clone because DNS resolution for GitHub failed. Keep BRAIN-001 `IMPLEMENTATION_IN_PROGRESS` until a network-enabled run passes the tests and a bounded live-data canary; do not start the full campaign while the remaining P0 design gates are open.


## P5-2026-10-16-FOUR-STRUCTURAL-BLOCKER-DESIGN-DECISIONS

**Trigger:** live revalidation after the BRAIN-001 source change still shows four structural gaps: the pilot self-authorizes on limited work; campaign runs the entire config grid on the final holdout; checkpoint/resume cursor and result ledger cannot prove exact-once progress; and result persistence relies on one 51.7 MB-growing monolithic JSONL file after a ~429.9 MB rejected attempt.

**Prompt improvement:** require separate structured decisions for each root cause before implementation and prevent superficially independent fixes from creating incompatible architecture. The completed designs specify: (1) evidence-only pilot + independently recomputing validator + campaign-time validation; (2) validation-only grid + frozen candidate manifest + separate holdout evaluator and honest historical exposure label; (3) stable experiment IDs + transaction batches + verified manifest as source of truth and derived cursor; (4) immutable ≤4 MiB JSONL shards + compact hash/count/ID manifest + careful legacy migration. BRAIN-004 and BRAIN-005 share one transaction/shard architecture. Any new confirmatory period requires a separately versioned/preregistered methodology.

**Durable records:** full designs are in `research_state/brainstorming_queue.md`, committed as `2efaa66dd99b0f430e5c24a144594dc8fd4c61ad`; handoff is in `research_state/agent_handoff.md`, committed as `f54f6813f4aa7d5eab6fa5a7d59dd83bd5d48137`.

**Current statuses:** BRAIN-001 remains `IMPLEMENTATION_IN_PROGRESS` (13 tests and live canary are not run); BRAIN-002 through BRAIN-005 are `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` only. No root cause from BRAIN-002–005 was changed in this design session. Full campaign stays blocked.

**Validation caveat:** latest main, queue, source files, checkpoint, gate, results object size, workflow file list and Actions run records were read through GitHub. Runtime pytest/compile and live data access remain `NOT_RUN` due to local DNS/network failure and no available workflow-dispatch/cancel operation in the connected tool surface. Do not claim tests or an end-to-end workflow passed. Next step is to obtain a network-enabled runner and qualify BRAIN-001, then implement the transaction/shard pair (BRAIN-004/005), the holdout phase boundary (BRAIN-003), and independent authorization (BRAIN-002) in dependency-aware steps.

## Session prompt review — 2026-10-16 UTC

**Outcome:** `NO_PROMPT_CHANGE_JUSTIFIED`.

**Evidence:** the session's failures were an implementation/test defect (`fetcher.py` manifest creation referenced `DataFetcher.RATE_LIMIT_PER_MINUTE`, unavailable on test doubles; one pagination test asserted the wrong next cursor), not an instruction gap. README Section 2A already requires real data, fail-closed behavior, truthful `NOT_RUN` statuses, no synthetic fallback, one bounded task per session, and no implementation of a freshly brainstormed root cause in the same session. All were followed. No quantitative-method safeguard was touched or weakened; no prompt revision is proposed.

**Verification this session:** `git ls-remote origin main` = `00ac735982d825d4c4c8dfe73b361cdc729526c0` matches local HEAD; `py_compile` OK; `pytest tests/` → 20 passed, exit 0; live BTCUSDT canary → HTTP 451 from `api.binance.com/api/v3/klines`, loader failed closed with `DataUnavailableError`, no synthetic data accepted, manifest and data dir untouched. Local edits to `fetcher.py` and `tests/test_data_fetcher.py` are uncommitted and not remotely persisted.

## Session prompt review — 2026-10-16 UTC (continuation)

**Outcome:** `NO_PROMPT_CHANGE_JUSTIFIED`.

**Evidence:** this session revalidated all open brainstorming items against current source at HEAD `38689e417fdfc0f4d20b417e1adeb67b6df30735`. The only blocker is a persistent external provider/location block (HTTP 451 from `api.binance.com`, confirmed by direct curl); the remaining P0 items (BRAIN-002 self-authorizing pilot, BRAIN-003 holdout not gated, BRAIN-004 cursor reset/unreconciled counters, BRAIN-005 monolithic 51.7 MB results file) are unimplemented design items, not instruction gaps. README Section 2A already requires real data, fail-closed behavior, truthful `NOT_RUN` statuses, no synthetic fallback, one bounded task per session, and no same-session implementation of a freshly brainstormed root cause. No quantitative-method safeguard was touched or weakened; no prompt revision is proposed.

**Verification this session:** `git rev-parse HEAD` = `git ls-remote origin main` = `38689e417fdfc0f4d20b417e1adeb67b6df30735` (prior top block naming `6710279` is STALE); `git status` clean; `py_compile` OK; `pytest tests/` → 20 passed, exit 0; direct curl to Binance klines → HTTP 451 (~0.1s), loader fails closed with `DataUnavailableError`, no synthetic data accepted, `research/data/` absent. Handoff update is local-only (not committed/pushed; commit was not requested).

## Session prompt review — 2026-10-16 UTC (~11:56 UTC)

**Outcome:** `NO_PROMPT_CHANGE_JUSTIFIED`.

**Triggering evidence:** live default-branch SHA refreshed to `6443209843af55b72464f7f21e33041016371a4b` (prior handoff top block named `38689e4`, now STALE — one commit behind). All five open brainstorming items revalidated against live source and current run evidence. No item is `BRAINSTORMING_REQUIRED`; all have completed structured design. BRAIN-001 source fix CONFIRMED (no synthetic call in `load_or_fetch_asset_data`; fail-closed; 26,280-candle floor enforced) but live canary remains `WAITING_EXTERNAL_INTERVENTION` (persistent HTTP 451). BRAIN-002–005 remain `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` and unimplemented (holdout not gated in `campaign.py:147`; cursor reset in `campaign.py:109-112,141-143,148-149`; monolithic `results.jsonl` 51,688,138 bytes; `checkpoint.last_verified_record: 0`).

**Cause classification:** `DATA_OR_EXTERNAL_SERVICE` (persistent Binance HTTP 451 egress block) and `UNKNOWN` (no new instruction gap; the open items are pre-existing structural design items already brainstormed).

**Revision summary:** none. No PROMPT_GAP demonstrated. README Section 2A already governs this situation: real data required, fail-closed, no synthetic fallback, truthful `NOT_RUN`, one bounded task per session, no same-session implementation of a freshly brainstormed root cause, and campaign blocked until P0 gates pass.

**Expected effect:** none (no change). The refreshed handoff corrects the stale SHA and revalidates blocker statuses against live source.

**Regression scenarios and status:** all P2/P3/P4/P5 regression scenarios remain as previously specified; behavioral tests NOT_RUN. No safeguard removed or weakened.

**Rollback and review rule:** N/A (no prompt change).

**Verification this session:** `git rev-parse HEAD` = `git ls-remote origin main` = `a8fa4a001557aabdd51123ff11e4bb8041c8476a`; `git status` clean; `py_compile` OK; `pytest tests/` → 20 passed, exit 0; direct curl to Binance klines → HTTP 451 (~0.1s), loader fails closed with `DataUnavailableError`, no synthetic data accepted, `research/data/` absent. Stale in-progress Actions run #38891774797 (head `4b721e6`, 7 commits behind, cancel HTTP 403) may hold the `kilo-repository` concurrency slot. Handoff and prompt-evolution edits committed and pushed as `a8fa4a0`; remote SHA re-verified identical after push.

## Session prompt review — 2026-10-16 UTC (~12:11 UTC)

**Outcome:** `NO_PROMPT_CHANGE_JUSTIFIED`.

**Triggering evidence:** live default-branch SHA refreshed to `2dd6a4fda24590444631d2241607fc3e1acda914` (prior handoff top block named `6443209`/`a8fa4a0`, now STALE — two commits behind current HEAD `2dd6a4f`; intervening `chore(kilo)` checkpoint commits touched only `research_state/prompt_evolution.md` and `research_state/agent_handoff.md`). All five open brainstorming items revalidated against live source at HEAD `2dd6a4f` and current run evidence. No item is `BRAINSTORMING_REQUIRED`; all have completed structured design. BRAIN-001 source fix CONFIRMED (no synthetic call in `load_or_fetch_asset_data`; fail-closed; 26,280-candle floor enforced) but live canary remains `WAITING_EXTERNAL_INTERVENTION` (persistent HTTP 451, reconfirmed ~0.03s this session). BRAIN-002–005 remain `DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION` and unimplemented (holdout not gated in `campaign.py:147`; cursor reset in `campaign.py:109-112,141-143,148-149`; monolithic `results.jsonl` 51,688,138 bytes; `checkpoint.last_verified_record: 0`).

**Cause classification:** `DATA_OR_EXTERNAL_SERVICE` (persistent Binance HTTP 451 egress block) and `UNKNOWN` (no new instruction gap; the open items are pre-existing structural design items already brainstormed).

**Revision summary:** none. No PROMPT_GAP demonstrated. README Section 2A already governs this situation: real data required, fail-closed, no synthetic fallback, truthful `NOT_RUN`, one bounded task per session, no same-session implementation of a freshly brainstormed root cause, and campaign blocked until P0 gates pass.

**Expected effect:** none (no change). The refreshed handoff corrects the stale SHA blocks (`6443209`, `a8fa4a0`, `38689e4`, `00ac7359`, `00174e4`), revalidates all prior claims against live HEAD `2dd6a4f`, and records the fresh canary evidence.

**Regression scenarios and status:** all P2/P3/P4/P5 regression scenarios remain as previously specified; behavioral tests NOT_RUN. No safeguard removed or weakened.

**Rollback and review rule:** N/A (no prompt change).

**Verification this session:** `git rev-parse HEAD` = `git ls-remote origin main` = `2dd6a4fda24590444631d2241607fc3e1acda914`; `git status` clean; `py_compile` OK; `pytest tests/` → 20 passed, exit 0; direct curl to Binance klines → HTTP 451 (~0.03s), loader fails closed with `DataUnavailableError`, no synthetic data accepted, `research/data/` absent; direct curl to api.github.com → HTTP 200 (git remote reachable). Stale in-progress Actions run #38891774797 (head `4b721e6`, cancel HTTP 403) may hold the `kilo-repository` concurrency slot. Handoff and prompt-evolution edits for this session committed and pushed below; remote SHA to be re-verified after push.

## Session prompt review — 2026-10-16 UTC (~12:17 UTC)

**Outcome:** `NO_PROMPT_CHANGE_JUSTIFIED`.

**Triggering evidence:** live default-branch SHA refreshed to `056723a73d3936976055783c3262a2c133e1e4cc` (one commit ahead of prior `2dd6a4f`; `2dd6a4f` touched only handoff/prompt-evolution state). One live defect was found and fixed: `.github/workflows/main.yml:348` `scan_log_archive()` called `sorted()` on raw `ZipInfo` objects (no `__lt__`), producing `"'<' not supported between instances of 'ZipInfo' and 'ZipInfo'"` and leaving every run with `log_capture_status: unavailable`. Fix commit `53ff09c` sorts by `item.filename`. Verified: old path reproduces the exact `TypeError` in a harness executing the extracted live function against a synthetic multi-entry zip; new path returns `status: scanned` and emits only `.txt` log signals. All prior claims revalidated against live HEAD (`fetcher.py` fail-closed/no synthetic call; `campaign.py` holdout not gated and cursor resets; `pilot.py` self-authorizes; `data_manifest.json` synthetic labels; `checkpoint.json` unreconciled). Live Binance canary → HTTP 451 (~0.07s), loader fails closed. `python3 -m pytest tests/` → 20 passed exit 0; workflow YAML parses cleanly.

**Cause classification:** `IMPLEMENTATION_DEFECT` (localized ZipInfo sort in the diagnostic collector, fixed); `DATA_OR_EXTERNAL_SERVICE` (persistent Binance HTTP 451 egress block, unchanged). No PROMPT_GAP demonstrated; the open structural items (BRAIN-002–005) already have completed designs and are not instruction gaps.

**Revision summary:** none. No README Section 2A change; no quantitative-method safeguard touched or weakened; no prompt revision is proposed. No same-session implementation of a brainstormed root cause occurred.

**Expected effect:** none (no prompt change). The handoff was refreshed to HEAD `056723a`, the log-scan defect was fixed and verified, and the next action is unchanged.

**Rollback and review rule:** N/A (no prompt change). The workflow fix can be rolled back by reverting commit `53ff09c` if it interferes with the diagnostic step; it is a one-line behavioral change confined to `scan_log_archive`.

**Regression scenarios and status:** all P2/P3/P4/P5 regression scenarios remain as previously specified; behavioral tests NOT_RUN. The fixed `scan_log_archive()` behavior is deterministic over archive entry ordering and only reads `.txt` files.

**Verification this session:** `git rev-parse HEAD` = `git ls-remote origin main` = `056723a73d3936976055783c3262a2c133e1e4cc`; `git status` clean; `py_compile` OK; `pytest tests/` → 20 passed, exit 0; direct curl to Binance klines → HTTP 451 (~0.07s), loader fails closed; direct curl to api.github.com → HTTP 200; remote SHA re-verified after push. Stale in-progress Actions run #38891774797 (head `4b721e6`, cancel HTTP 403) may hold the `kilo-repository` concurrency slot.

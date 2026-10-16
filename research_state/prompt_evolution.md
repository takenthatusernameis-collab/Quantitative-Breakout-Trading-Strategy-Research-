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

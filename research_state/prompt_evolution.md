# Agent Prompt Evolution Log

This file records evidence-based revisions to the agent-session instructions in `README.md`. It is append-only in intent: preserve earlier entries, correct factual errors with an explicit note, and never erase failed prompt experiments. The quantitative research protocol is governed separately and must not be silently modified by prompt revisions.

## Current policy

- **Prompt contract:** README Section 2A, “Mandatory session continuity, recovery, and self-improving prompt protocol”.
- **Prompt revision introduced:** `P2-2026-10-16-SESSION-CONTINUITY`.
- **Source README commit:** `d067aedc263cffe7326a54ec0195ede032855beb`.
- **README blob SHA after this revision:** `008457a045ef2c1319210393f5b31f7f6baf47c4`.
- **Initial rollout status:** written and committed; startup integration and behavioral effectiveness must be verified. Do not claim that this prompt has already improved agent outcomes.
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

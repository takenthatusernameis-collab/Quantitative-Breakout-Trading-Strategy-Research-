# Authorized Maintenance and Validation Brief — Breakout Repository

Date: 2026-10-21  
Status: Authorized scope and acceptance criteria; execution evidence must be recorded separately.

## Prompt refinement log

### Pass 1 — define the mission
Audit and improve safe research-state reconciliation, bounded waiting, and run diagnostics in the breakout repository.

### Pass 2 — add isolation and research-validity controls
Keep the original 2,304-configuration strategy, historical reports, holdout exposure state, frozen v1–v5 specifications, and current hash-bound authorization immutable. Do not equate workflow activity, a candidate manifest, or a committed prompt with an executed or validated campaign.

### Pass 3 — make the work executable and falsifiable
Require current-HEAD and live-run checks, authorization/hash checks, a complete offline test and verifier run, before/after artifact comparisons, and exact reporting of every blocker. Prefer a fail-closed result to an unverified advancement.

## Authorized scope and sequencing

The user authorized maintenance and validation in the two named research repositories, with no live trading and no changes to the frozen strategy rules.

1. First inspect the current repository HEAD, the final entries of research_state/agent_handoff.md, the latest status of GitHub Actions runs, and the current v5 authorization/execution prerequisites. The earlier handoff identifies a hash-bound v5 task; refresh that finding rather than assume it is still incomplete.
2. Do not interrupt or overwrite another active session's task. Respect its stated stop conditions, record the transition, and start this maintenance audit only at a safe task boundary.
3. Do not trigger, cancel, rerun, or dispatch any GitHub Actions run. Do not edit any workflow file. Do not contact data providers or run a grid, campaign, candidate selection, pilot, backtest, or confirmatory evaluation as part of this maintenance task.
4. Do not edit src/breakout_research, frozen configs/research_v1.json through configs/research_v5* and their amendment/freeze/execution files, historical research/results/reports, research_state/continuous_universe_state.json, candidate manifests, candle data, result shards, or holdout counters. A code or frozen-protocol change would invalidate hash-bound evidence and requires a separately staged, versioned authorization—not a convenient in-place repair.
5. Do not assume a saved state is correct merely because JSON parses. Read state, manifests, code/specification hashes, authorization evidence, candidate-freeze evidence, and result identity/coverage side by side.

## Required audit

### A. Workflow wait-state and diagnostics
- Refresh all current workflow runs. Record run id/number, event, commit SHA, status, last updated time, conclusion, URL, and accessible job/log evidence.
- Distinguish a running job from a stale heartbeat, a queued job, a failed job, an unavailable log archive, and an external permission blocker. Missing or inaccessible logs are not proof of success.
- Existing observation at audit start: run #70 was listed in progress and run #69 failed. Re-check these statuses before relying on them.
- Do not poll repeatedly while waiting for a known future eligibility/confirmation time. A blocked task should perform independent, offline, authorized validation work or stop with a timestamped reason. No unbounded retry loops.
- If a safe wait-state correction requires workflow-file permission, document the exact minimal change and permission blocker; do not attempt a bypass.

### B. Hash-bound campaign integrity
- Recompute the live code hash using the repository's prescribed command and compare it with the authorization artifact and current frozen research specification.
- Run all prescribed read-only v5 specification, manifest, candidate-freeze, execution, and compatibility verifiers that currently apply. Verify current prerequisite files exist and that their contents match the hashes recorded by their parents.
- Inspect the current candidate-selection/cycle state and the underlying manifests/results. Report disagreements with precise JSON paths and expected/observed values; do not repair the state by hand.
- Ensure the already exposed or unknown holdouts remain unavailable for development selection. Do not create an additional exposure or change any exposure counter during this audit.

### C. Offline validation
Run from the repository root, only after reconciling the current task boundary:
- PYTHONPATH=src python3 -m pytest tests/ -q
- Every currently applicable scripts/verify_*.py verifier, individually.
- The prescribed live code-hash calculation.
- git status --short and git diff --stat.

Record exact command, exit code, test count, verifier name/result, current commit SHA, and relevant output. If this ChatGPT session cannot execute a command, do not fabricate its result; leave it for an authorized repository runner and state why.

## Acceptance criteria

The task is complete only if:
- No protected source, frozen config, data, result, report, holdout state, or workflow was changed by this maintenance task.
- Current run/queue status was refreshed and every stale, failed, pending, or inaccessible state is clearly labeled.
- All current applicable offline tests and verifiers pass, or a precise reproducible blocker is preserved.
- Code/specification/authorization and candidate/cycle/result identities are reconciled; no result is called complete without verified expected-unit coverage and matching manifests.
- No campaign, holdout, provider fetch, or new selection/backtest was triggered.
- The handoff states what was actually verified, what remains incomplete, exact URLs/hashes, and one next action with explicit preconditions.

## Stop conditions

Stop before any action that would modify hash-bound code, frozen configs, research state, or historical evidence; expose a holdout; launch a campaign; repeat a known external failure; bypass a permission restriction; or conflict with another in-progress task. Report the blocker rather than silently broadening scope.

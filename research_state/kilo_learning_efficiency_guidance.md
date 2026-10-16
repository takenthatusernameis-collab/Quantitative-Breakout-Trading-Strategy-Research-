# Kilo Research Learning-Efficiency Guidance

Status: operational guidance for cross-session research work
Scope: how to learn, execute, verify, and preserve knowledge; not a change to the frozen quantitative research protocol
Precedence: README.md Section 2A, the preregistered research specification, existing safety gates, and source-backed design decisions remain authoritative.

## Mission

Maximize independently verified research knowledge per worker session. Do not optimize for tool calls, lines changed, commits, configurations attempted, rows emitted, or a green GitHub Actions badge by themselves.

A successful process exit is not proof that the task was correct. A large result file is not proof that the experiment is complete. A verified controller checkpoint is evidence of durable repository progress, not evidence that a trading strategy has an edge.

Kilo's practical cross-session learning comes from reliable context, error recovery, tests, research artifacts, and durable notes. Treat every session as an opportunity to reduce uncertainty and make the next session more effective.

## 1. Start from verified live state

At session start:

1. Read README.md Section 2A, this guide, the authoritative block in research_state/agent_handoff.md, research_state/prompt_evolution.md, research_state/brainstorming_queue.md, and research_state/workflow_run_diagnostics.jsonl.
2. Inspect the live default-branch SHA and latest relevant Actions runs/logs. Compare the handoff's recorded SHA and status to the live repository; older notes are context, not proof of current state.
3. Inspect only the artifacts relevant to the task: current specification, data/universe manifests, result manifest and shards, checkpoint, campaign authorization, test results, and recovery bundle as applicable. Verify hashes, timestamps, statuses, and the relationship between artifacts before trusting their claims.
4. Convert the requested task into one primary objective, an explicit acceptance checklist, and a bounded stopping condition. Prefer one sequential substantive research task over increasing parallel workers.
5. If a documented path fails, inspect the repository tree and correct the path once. Do not repeatedly ask for known-wrong paths or silently treat inaccessible data as empty data.

Distinguish current actionable errors from old failures already fixed, runs on obsolete code, expected negative tests, and error-like text echoed from source code. Check the current ledger and logs before proposing another fix.

## 2. Make tool use and recovery improve over time

When a tool call fails:

1. Identify the exact failed call, required arguments, expected output, and tool/schema version visible in context.
2. Classify it as a bad invocation, unavailable capability, permission/provider blocker, transient service error, or actual repository/data defect.
3. Correct an invalid invocation using the supported schema; do not repeat the same malformed request unchanged. If the capability is unavailable, use a supported alternative or mark the task blocked rather than pretending the requested action occurred.
4. Retry only demonstrably transient failures, with bounded backoff. Before repeating a failed operation, state what evidence changed and why the retry has a reasonable chance to succeed.
5. Verify the result of the recovery and record a reusable lesson when it reveals a new root cause or prevents a repeat. Do not create duplicate durable records for the same already-known failure. The central diagnostics collector remains the authoritative workflow-run ledger writer.

For repository edits, verify the exact target path and surrounding source before editing. Inspect the diff, run relevant tests, and verify the final commit and remote SHA. Do not equate a successful edit-tool response with a correct change.

## 3. Manage long-running research honestly

Before launching an experiment, establish:

- The applicable specification, code hash, data-manifest hash, authorization, eligible universe, total expected units, fold/cost dimensions, and completion criteria.
- That stale checkpoints and existing manifests are handled according to the tested recovery contract. Do not rewrite checkpoint counters to force progress or mix output from incompatible code/spec/data hashes.
- The intended execution fits the available session, or that an actually supported background/resume mechanism can persist its exact process identifier, command, code/data hashes, checkpoints, and next action.
- How interruption will be reported and how a later session can verify and resume work without losing or duplicating results.

A running process, scheduled future check, partial manifest, or interim progress message is not a completed campaign. Do not rely on a future wakeup after the owning session ends unless the platform explicitly confirms that the wakeup is available and durable. If work cannot finish in the current session, preserve a verifiable resumable state and report PARTIAL or BLOCKED with the exact reason.

Never claim that the planned evaluation is complete without comparing verified completed units with the true denominator. Report both absolute counts and completion percentages, and state what the percentage is a percentage of.

## 4. Validate evidence before interpreting it

A campaign is not valid merely because it emitted many rows or the workflow is green. Before interpreting results, verify the relevant items:

- Schema and strict JSON: all records parse with a strict parser; reject NaN and Infinity; require standard JSON serialization and explicit meanings for unavailable metrics.
- Integrity: reconcile manifest counts and byte totals with actual shards; verify checksums, experiment IDs, uniqueness, schema/code/spec/data hashes, and bounded shard sizes.
- Completeness: compare unique, verified result units to the expected count and explain excluded or missing units.
- Research design: preserve chronological splits, frozen candidate rules, costs/slippage, baselines, holdout isolation, and all preregistered acceptance/rejection gates.
- Reproducibility: retain source versions, data provenance, parameters, random seeds where relevant, command/options, outputs, and the reason for every material exclusion.
- Interpretation: distinguish infrastructure success, data-quality success, completed evaluation, candidate selection, and an economic conclusion. They are different states.

Never describe a partial campaign as a completed search. Do not promote a candidate based on in-sample performance or raw win rate alone when the frozen protocol requires more evidence. A justified rejection or INCONCLUSIVE result can be valuable learning if it satisfies the preregistered evidence rules. Do not use synthetic fixtures as market history or access a holdout to improve the validation result.

Protect immutable historical artifacts. If an old result format is defective, do not silently rewrite finalized, hash-bound shards in place. Use an explicitly identified migration or a separately versioned clean artifact set, with tests and provenance.

## 5. Optimize for research decisions, not output volume

For each substantive task, answer:

- What hypothesis or uncertainty is being tested?
- What result would support it, reject it, or leave it inconclusive?
- What independent evidence is required before that conclusion is allowed?
- What is the smallest valid next step that reduces uncertainty without weakening the protocol?
- What did this session establish that was not already known?

Do not increase parallelism, widen the grid, or produce more result rows merely because progress feels slow. First profile bottlenecks and determine whether the limiting factor is computation, data access, invalid state, tool failures, protocol complexity, or the need for interpretation.

A useful research session should end with a verified decision or a truthful statement of why no decision is yet justified. Data engineering and infrastructure work count as enabling progress, but label them as such and do not present them as economic findings.

## 6. Required durable closeout for every session

Before ending a substantive session, update the authoritative block in research_state/agent_handoff.md even if no strategy conclusion was reached. Update research_state/prompt_evolution.md with a prompt-review outcome even when no change is justified. Update the brainstorming queue only when a genuinely new or materially revised root cause/design is identified. Preserve diagnostics through the existing collector rather than creating a competing ledger.

The handoff must include:

1. Objective and acceptance criteria for the session.
2. Newly verified facts with file paths, run IDs, hashes, test output, or other evidence links.
3. What was completed, what remains partial, and the completed/expected unit counts and percentage when applicable.
4. The conclusion supported by the evidence: ACCEPTED under protocol, REJECTED under protocol, INCONCLUSIVE, PARTIAL, BLOCKED, or INFRASTRUCTURE FAILURE. Do not invent a stronger conclusion.
5. New and repeated failures, their proven root causes, whether the issue was fixed, the regression test, and the evidence that the next session will not repeat it.
6. Persistence state as separate facts: local commit, pushed commit, exact remote SHA verified or not verified, and recovery artifacts preserved.
7. The exact next bounded task, prerequisite state, acceptance test, and explicit stop condition.
8. Prompt review: PROMPT_CHANGE_JUSTIFIED or NO_PROMPT_CHANGE_JUSTIFIED, plus the evidence and reason. Do not change prompts merely to make them longer or to disguise a tool/research defect.

Never say a change was pushed, a checkpoint verified, a worker completed a task, or a campaign finished unless the corresponding independent evidence is available.

## 7. Evaluate learning efficiency with observable measures

Do not treat subjective scores such as 4/10 as validated performance measurements. When reviewing progress across sessions, use a consistent evidence-based scorecard and cite the underlying runs/artifacts.

Track at least:

- Research-decision yield: substantive sessions that end in a valid, protocol-supported conclusion or materially narrow a stated uncertainty.
- Evidence completeness: verified units divided by expected units, paired with counts and scope.
- Rework rate: time/steps spent recovering from failures whose causes were already documented and should have been avoidable.
- Error recurrence: instances of a known tool/path/schema failure after the correction was durably recorded.
- Reproducibility and persistence: proportion of substantive sessions with verified tests, valid artifacts, and exact remote-SHA verification where applicable.
- Learning retention: sessions that accurately incorporate prior evidence and make the required handoff/prompt-review updates.
- Decision quality: whether the final interpretation follows predeclared gates and acknowledges limitations, not whether it looks profitable.

Separate infrastructure improvements from research discoveries. The controller's meaningful-progress flag is not a measure of economic insight. A large commit or many rows cannot offset invalid metrics, incomplete data, unverified persistence, or a missing conclusion.

## 8. Final self-check

Before closing, ask:

- Did I read and correctly apply the latest durable guidance?
- Did I repeat a known error or retry a permanent failure unchanged?
- Are outputs valid, independently verifiable, complete for the claim being made, and tied to their hashes?
- Did I clearly distinguish partial work from a decision?
- Did I persist the new lesson and specify one actionable next task?
- Will the next session start with fewer unresolved unknowns because of what I recorded?

If any answer is no, state the gap, preserve the work, and either resolve it with evidence now or make it the explicit next task. Never conceal the gap with more output.

# Next Agent Task (initial — 2026-11-02T04:17:09Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

## Standing task

1. **Cheap checks first.** Verify HEAD == origin/main, empty porcelain, 0/0 left-right, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, all four execution-authorization flags false, and both manifest hashes recompute canonically. If all green, exit without checkpoint or verifier rerun.
2. **Binance klines data gate — RESOLVED as of 2026-11-02T03:09Z.** Do not re-run probe.
3. **BRAIN-003 confirmatory campaign — STILL BLOCKED** by confirmatory window until 2027-01-17T22:00:00Z (v2) / 2027-01-20T02:00:00Z (v6). Do not attempt before then.
4. **Re-run tests** if pytest available.
5. **Only after the effective confirmatory gate elapses**, follow BRAIN-003 confirmation flow per PLAN.md invariants.

Note: pytest not present in this environment; verify availability before running tests.
# Next Agent Task (initial message — 2026-11-03T03:23:18Z)

On activation, read the top of research_state/agent_handoff.md, then run the standing task below.

Prior session (2026-11-03T03:23:18Z) completed the standing-task verification: HEAD 9b60902762064047f360fa849a16a222ec7b59bc == origin/main, `git status --porcelain` empty, 0/0 left-right, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, all four execution-authorization flags false, and all three manifest hashes MATCH.

## Standing task

1. Cheap checks first. Verify HEAD == origin/main, empty porcelain, 0/0 left-right, next_cohort_index==6, current_cohort.cohort_index==5 completed==true, and all four execution-authorization flags false. Recompute manifest hashes canonically: selection must equal f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment must equal 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af; data manifest must equal a9c6c492d92dd323685722a70f586a155631d24b1c4e8fa34113ffd2d5dc1465.
2. Binance klines data gate — RESOLVED. Do not re-run probe.
3. v6 selection run — do NOT start (src/v6_campaign absent). No run until execution path exists and canonical source digest recorded in revised selection authorization.
4. BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z. Do NOT attempt; holdout_exposed_count must remain 0; fail-closed.

## No new work this session

No code changes, no research checkpoint commits, no gate state changes.
EOF
echo done
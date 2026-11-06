# Next Agent Task (initial message — 2026-11-06T08:42:49Z)
On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest is 2026-11-06T08:42:49Z / HEAD b0db40d9f8772a0d959efbfefaa9c9a091a03179), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = b0db40d9f8772a0d959efbfefaa9c9a091a03179, HEAD == origin/main, working tree clean at verification before this session's edits.

## Standing task
1. **Cheap checks first.** Verify `git status --porcelain`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`. Verify execution-authorization flags. Reconfirm HEAD and origin/main.
2. **Recompute manifest hashes** with `scripts/v6_universe_rules.py:published_manifest_hash`. Run `python3 scripts/verify_v6_execution.py` (expect `ok: true`).
3. **Binance klines data gate — RESOLVED.** Do not re-run probe.
4. **v6 selection run — do NOT start.**
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.**

## Session closeout
When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file. Do not commit unless explicitly asked.

(End of file)

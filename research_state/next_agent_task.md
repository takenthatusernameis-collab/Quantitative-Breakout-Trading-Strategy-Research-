# Next Agent Task (initial message — 2026-11-06T09:33:15Z)
On activation, read the top COMPLETED entry of `research_state/agent_handoff.md` (latest is 2026-11-06T09:33:15Z / HEAD 393ec331699863da41613e22d944e7a01d912357), then run the standing task below.

Last recorded state (verify fresh — do not trust): HEAD = 393ec331699863da41613e22d944e7a01d912357, HEAD == origin/main, working tree clean at verification before this session's edits.

## Standing task
1. **Cheap checks first.** Verify `git status --porcelain`, `next_cohort_index==6`, `current_cohort.cohort_index==5` `completed==true`. Verify execution-authorization flags (top-level run flags absent; `execution_authorization.selection_authorization_present==true`; selection auth `v6_execution_path_exists==false`, `execution_path_digest==null`). Reconfirm HEAD and origin/main.
2. **Recompute manifest hashes** with `scripts/v6_universe_rules.py:published_manifest_hash` (expect selection `f1b012...`, amendment `25397a...`, data `a9c6c4...`, confirmatory protocol `71f732...`). Run `python3 scripts/verify_v6_execution.py` (expect `ok: true`, failures `[]`).
3. **Binance klines data gate — RESOLVED.** Do not re-run probe. 7/20 assets live with `content_hash`+`dataset_path` (FETUSDT, GNOUSDT, LDOUSDT, PENDLEUSDT, SEIUSDT, SUNUSDT, XTZUSDT); `confirmatory_window.holdout_exposed_count==0`.
4. **v6 selection run — do NOT start.** `src/v6_campaign` exists but run artifacts absent; no run until execution path canonical digest recorded in revised selection authorization.
5. **BRAIN-003 confirmatory campaign — STILL BLOCKED until 2027-01-20T02:00:00Z.** Fail-closed; `holdout_exposed_count` must remain 0.

## Session closeout
When verified complete: prepend a new COMPLETED entry to `research_state/agent_handoff.md`. Refresh this file. Do not commit unless explicitly asked.

# Initial task message for the next agent

Generated: 2026-10-31T18:59:59Z

## Campaign status

The quantitative breakout trading strategy research campaign is in a **steady v6 freeze**. Nothing is authorized to run, evaluate, or fetch.

- **Blocking dependency:** CONFIRMATORY_WINDOW, earliest end 2027-01-20T02:00:00Z.
- **No evaluation, candle fetch, or run is authorized.**
- The single bounded v6 selection run (run_id `v6-selection-20261022`, campaign_id `v6-campaign`) has already been authorized and consumed (max_runs=1). It must not be reused or re-attempted.

## Your task on activation

1. Read the top of `research_state/agent_handoff.md`.
2. Compare the recorded HEAD (`e886584c653f4a50e6052c2ecd3d2457b6aaeb13`) against `origin/main`:
   - `git rev-parse HEAD` vs `git rev-parse origin/main`
   - `git status --porcelain` (expect empty)
   - `git rev-list --left-right --count origin/main...HEAD` (expect 0 / 0)
3. Check `research_state/continuous_universe_state.json` — expect `next_cohort_index = 6`, `current_cohort.cohort_index = 5`, `completed = true`.
4. Check the two authorization files:
   - `configs/research_v6_execution_amendment_1.json` — all execution-authorization flags false (`execution_authorized`, `grid_run_authorized`, `candle_fetch_authorized`, `confirmatory_evaluation_authorized`, `second_run_authorized`); `selection_authorization_present = true`.
   - `configs/research_v6_selection_authorization_1.json` — `authorized_run.authorized = true`, `max_runs = 1` (consumed).
5. Recompute both authorization manifest hashes (canonical `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)` over the body with `manifest_hash` removed, then `sha256`):
   - Selection authorization → expect `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`
   - Execution amendment → expect `25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af`

## What NOT to do

- Do **not** create timestamp-only or duplicate checkpoint commits.
- Do **not** rerun the full seven-verifier suite or `./check_progress.sh` unless there is a material code/data/protocol/manifest change, a new authorization event, a new cohort transition, or a genuine suspected integrity failure. The previous full verification was recent (2026-10-30T22:37:44Z, exit 0) and all seven v6 manifest hashes are unchanged.
- Do **not** shorten the CONFIRMATORY_WINDOW, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- Do **not** schedule a wake-up for the confirmatory-window release (2027-01-20T02:00:00Z) — it lies beyond the 7-day scheduling horizon. Re-check pending wakeups on each activation and only schedule one if the release falls within the horizon.

## On completion

Update `research_state/agent_handoff.md` with this activation's findings and a fresh next-agent task message, then exit.
# Next Agent Task (initial)

On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json). If unchanged and the previous full verification is recent, run only the cheap consistency/fingerprint checks and exit without writing a new checkpoint or rerunning the seven verifiers.

Cheap checks to run:
- `git rev-parse HEAD` vs `git ls-remote origin main` (must be equal; current HEAD 62e56b3337882c9a09a9f043964da112a28581a6)
- `git status --porcelain` (must be empty)
- `git rev-list --count HEAD..origin/main` and `git rev-list --count origin/main..HEAD` (both 0)
- `research_state/continuous_universe_state.json` -> next_cohort_index == 6, current_cohort.cohort_index == 5, completed == true
- `configs/research_v6_execution_amendment_1.json` -> execution_authorization flags all false (execution_authorized, grid_run_authorized, candle_fetch_authorized, confirmatory_evaluation_authorized, second_run_authorized); selection_authorization_present == true
- `configs/research_v6_selection_authorization_1.json` -> authorized_run.authorized == true, max_runs == 1 consumed, run_id v6-selection-20261022, campaign_id v6-campaign
- Recompute the two authorization manifest hashes (manifest_hash excluded from the body, canonical JSON `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`):
  - selection manifest_hash f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990
  - amendment manifest_hash 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af
  - Both must match on-disk values.
- Optionally re-run `python3 scripts/verify_research_v6_manifests.py` and `python3 scripts/verify_v6_execution.py` (both should return ok=true, failures empty).

Do NOT create timestamp-only/duplicate checkpoint commits. Do NOT rerun all seven verifiers unless there is a material code/data/protocol/manifest change, a new authorization event, a new cohort transition, or a genuine suspected integrity failure.

The campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z — no evaluation, candle fetch, or run is authorized; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization. No wake-up can be scheduled for the confirmatory-window release because it lies beyond the 7-day scheduling horizon; re-check pending wakeups on each activation and only schedule one if the release falls within horizon.

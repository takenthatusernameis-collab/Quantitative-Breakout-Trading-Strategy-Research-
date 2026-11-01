# Next Agent Task (initial)

On activation, read the top of research_state/agent_handoff.md and compare HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, and the authorization files (configs/research_v6_selection_authorization_1.json and configs/research_v6_execution_amendment_1.json).

Current verified state (2026-11-01T10:47:14Z):
- HEAD 1edc2437847cf02af8909655b292e165d63dcce2 == origin/main 1edc2437847cf02af8909655b292e165d63dcce2; git status --porcelain empty; 0 ahead 0 behind.
- next_cohort_index=6 (current_cohort.cohort_index 5, completed=True).
- execution-authorization flags all false per configs/research_v6_execution_amendment_1.json (execution_authorized/grid_run_authorized/candle_fetch_authorized/confirmatory_evaluation_authorized/second_run_authorized all false).
- selection_authorization_present=true; authorized_run.authorized=true; max_runs=1 consumed; run_id v6-selection-20261022; campaign_id v6-campaign.
- Both manifest hashes recomputed and match on-disk: selection f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990; amendment 25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af.
- verify_research_v6_manifests ok=true; verify_v6_execution ok=true.
- NOTE: configs/research_v6_selection_authorization_1.json references verifier scripts/verify_v6_selection_authorization_1.py but that file does not exist on disk (absent path). Treat as an observation, not a blocker.

If unchanged and the previous full verification is recent, run only the cheap consistency/fingerprint checks (git rev-parse HEAD vs origin/main, git status --porcelain, ahead/behind, next_cohort_index=6, execution-authorization flags all false, recompute the two authorization manifest hashes) and exit without writing a new checkpoint or rerunning the seven verifiers.

Do NOT create timestamp-only/duplicate checkpoint commits. Do NOT rerun all seven verifiers unless there is a material code/data/protocol/manifest change, a new authorization event, a new cohort transition, or a genuine suspected integrity failure.

The campaign remains in steady v6 freeze blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z — no evaluation, candle fetch, or run is authorized; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.

No wake-up can be scheduled for the confirmatory-window release because it lies beyond the 7-day scheduling horizon; re-check pending wakeups on each activation and only schedule one if the release falls within horizon.

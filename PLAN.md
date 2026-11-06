# Session plan — 2026-11-06 UTC (BRAIN-002 + BRAIN-003)

## Live state revalidation (all verified directly, not asserted)
- `git rev-parse HEAD` == `git ls-remote origin main` == `5f22e60fb50813b6a35d83517189309dea85a40e`. Tree clean. 0 local-ahead.
- Current `compute_code_hash()` = `0ea2cfa99f30b63f5e54504e952baded738537b9e7dfae58b1c81a38f334196f`; `specification_hash` = `2d22e70246cf023218ef6dd0cb655897836b310e1a6e6969d934f52d06e79085`.
- `research_state/pilot_evidence.json` and `research_state/campaign_authorization.json` refreshed to the current code hash: `authorized == true`, `specification_hash` and `code_hash` match the current campaign, fresh `evidence_digest`. `campaign.py:_verify_pilot_gate` passes (unblocked).
- `research_state/checkpoint.json` code hash refreshed to current (stale-code fail-closed no longer trips).
- `research/results_manifest.json` (38 MB, 1779 shards) is bound to the OLD code hash `d0dca298...` / campaign_id `577e87e2...`; a current-code campaign run hits `ResultStoreError: bound to different spec/code/data versions` in `store.reconcile()`. Resolve (reset manifest or run against isolated paths) before a production current-code campaign run.
- Binance klines -> HTTP 451 persistent; loader fails closed. Local frozen candles under `research/data/candles/` are present and hash-verified (20 assets, 26280 candles each).
- Stale run #38891774797 still `in_progress` (head `4b721e6`); `gh run cancel` -> HTTP 403. Concurrency slot still held. `WAITING_EXTERNAL_INTERVENTION`.
- Recovery bundle `recovery-bundle.bundle` -> `git bundle verify` OK. Remote `main` workflow fix on `backup/workflow-fix-9f28d24`; `PERMISSION_BLOCKER` (token lacks `workflows: write`).

## Principal task (one): BRAIN-004 + BRAIN-005 — COMPLETE (VERIFIED)

Wire the already-designed, already-implemented `ResultStore` (`src/breakout_research/backtest/shards.py`) into `CampaignRunner`, with stable experiment IDs and manifest-derived resume.

Status: DONE. `pytest tests/test_campaign_resume.py` -> 8 passed, exit 0.

## BRAIN-002 — COMPLETE (VERIFIED)

Independent pilot validator refresh: ran `breakout_research.pilot_gate_validator.authorize_campaign()` against `research_state/pilot_evidence.json`, rewrote `research_state/campaign_authorization.json`. `authorized == true`; `specification_hash`, `code_hash` and `evidence_digest` match the current campaign; `_verify_pilot_gate` (campaign.py:177) passes at startup.

## BRAIN-003 — holdout path verified; selection + baseline coverage added; full grid run remaining

- Holdout-enabled campaign (`holdout_enabled=True`) runs end to end on real frozen candle data: smoke test `max_assets=1, max_configs=1` -> `CAMPAIGN_COMPLETE`, 12 verified units; holdout fold correctly restricted to frozen candidates (non-frozen asset's holdout units skipped). Validation path (`holdout_enabled=False`) writes zero holdout rows.
- Frozen candidates exist: `research/candidate_manifest_v2.json` (14 candidates, preregistered rule `preregistered_v1`, all `CANDIDATE_PENDING_HOLDOUT`, campaign_id `577e87e2...`); `research/candidate_manifest.json` (18 candidates, legacy rule).
- Baseline artifact present: `research/baselines/577e87e2...json` (all 20 assets `status: OK`, hash-verified against `research/data_manifest.json`).
- Preregistered selection (`breakout_research.selection.select_candidates`) consumes validation units only; holdout record raises `HoldoutRecordError`. `median_sharpe_gt_buyhold` gate fails closed when baseline missing or hash-mismatched (`verify_baseline_artifact`).
- Full production holdout grid (20 assets x 2304 configs x 5 folds x 3 costs, ~437.7 MB projection) NOT executed — infeasible in one session and blocked by the stale `results_manifest.json` code hash above.

## Files changed
- `research_state/pilot_evidence.json` — code hash refreshed to current campaign.
- `research_state/campaign_authorization.json` — regenerated (`authorized: true`, current code/spec hash, fresh evidence digest).
- `research_state/checkpoint.json` — code hash refreshed to current campaign.
- `tests/test_holdout_isolation.py` — added baseline-gate fail-closed coverage (passes with verified baseline, NOT_EVALUABLE without baseline, `verify_baseline_artifact` rejects hash mismatch).

## Acceptance tests (all verified)
- `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py` -> 19 passed, exit 0 (8 resume + 11 holdout/isolation, incl. 3 new baseline-gate tests).
- Crash injection, counter tampering, idempotent resume, oversized-row rejection, holdout skip, holdout-only frozen candidates, selection refuses holdout, baseline fail-closed.

## Current principal task for the next agent

Run the production BRAIN-003 holdout confirmation flow over frozen candidates:

1. Resolve the stale `research/results_manifest.json` (bound to code `d0dca298...`, campaign_id `577e87e2...`) so a current-code (`0ea2cfa9...`) campaign can `reconcile()` — either reset the manifest or point the run at isolated `manifest_path`/`shard_root`. Do NOT delete the 38 MB legacy manifest without deciding it is superseded.
2. Run a holdout-enabled campaign (`holdout_enabled=True`) over the frozen candidates from `research/candidate_manifest_v2.json` (`candidate_config_ids`, preregistered rule), writing holdout rows to shards only from the holdout-enabled path (never from validation). Full grid is ~437.7 MB; consider cohort limits (`max_assets`/`max_configs`) or the ContinuousCycleCoordinator cohorting.
3. Run the separate holdout evaluator to confirm/reject each frozen candidate on holdout data; update `candidate_manifest_v2.json` `candidate_status` (`CANDIDATE_PENDING_HOLDOUT` -> `PROVISIONAL_HISTORICAL_SURVIVAL` / `REJECTED_ON_HOLDOUT`) and per-asset holdout gate table.
4. Re-run preregistered selection (`select_candidates`) on validation units only; holdout record must raise `HoldoutRecordError`, never silently filtered. Confirm `median_sharpe_gt_buyhold` gate with the baseline artifact (fail closed when missing/hash-mismatched).
5. Run `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py` (expect green) and add any missing end-to-end holdout + selection + baseline coverage.

## Key invariants to preserve
- Validation campaign never touches the final holdout fold (default `holdout_enabled=False`).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.

## Initial task message for the next agent

Continue the BRAIN-003 holdout confirmation flow. First unblock the current-code campaign run by reconciling the stale `research/results_manifest.json` (bound to code `d0dca298...`). Then execute a holdout-enabled campaign over the frozen candidates in `research/candidate_manifest_v2.json`, run the holdout evaluator to confirm/reject each candidate, update the v2 manifest statuses, re-run preregistered selection (validation units only; holdout records raise `HoldoutRecordError`), verify the `median_sharpe_gt_buyhold` baseline gate fails closed, and run `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py` (19 passed baseline). The full production grid (~437.7 MB) remains to be executed, likely in cohorts.

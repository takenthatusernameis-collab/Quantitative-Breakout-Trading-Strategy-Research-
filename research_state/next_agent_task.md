# Next Agent Task — Quantitative Breakout Trading Strategy Research

## On activation
Read the top of `research_state/agent_handoff.md` and compare HEAD vs origin/main, `git status --porcelain`, ahead/behind, `next_cohort_index=6`, and the authorization files (`configs/research_v6_selection_authorization_1.json` and `configs/research_v6_execution_amendment_1.json`).

## Cheap checks first
If HEAD == origin/main, tree clean, 0 ahead/0 behind, next_cohort_index=6, execution-authorization flags all false per `configs/research_v6_execution_amendment_1.json`, and the two authorization manifest hashes match on-disk (selection `f1b012b6208a1be8efa562b176a5ac3422931562e68f2dad47d2298cda12b990`; amendment `25397aeef22af011a2106333afb0ef1c336dbab780b2789b2db385b36337b2af`), run only the cheap checks and exit without writing a new checkpoint or rerunning the seven verifiers.

## Do NOT attempt the holdout-enabled BRAIN-003 campaign
Until the Binance klines data gate resolves (HTTP 200, 3 years continuous hourly candles verified by a bounded live probe recorded with endpoint/status/timestamp/command). A repeat of the same failed endpoint is not a distinct attempt; do not loop.

## Re-run tests
`PYTHONPATH=src python3 -m pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py tests/test_selection.py tests/test_baselines.py tests/test_candidate_freeze.py`

## Only if the data gate resolves (new live evidence)
Run the BRAIN-003 confirmation flow: holdout_enabled=True over frozen candidates (`research/candidate_manifest_v2.json`), write holdout rows only via the holdout path, run the separate holdout evaluator, preregistered selection on validation units only (holdout records raise HoldoutRecordError, never silently filtered), baseline artifact mandatory for `median_sharpe_gt_buyhold` with hash verification. Add end-to-end holdout + selection coverage and run the full test battery.

## Invariants to preserve
- Validation campaign never touches the final holdout fold (default holdout_enabled=False).
- Holdout-enabled campaign evaluates only frozen candidates from the manifest.
- Resume position derived from verified shard manifest, never checkpoint counters.
- Stale/mismatched checkpoint and pilot authorization rejected fail-closed.
- Campaign remains blocked by CONFIRMATORY_WINDOW until 2027-01-20T02:00:00Z; do not shorten the window, reuse the consumed selection authorization, change frozen specs/manifests, or bypass explicit authorization.
- No timestamp-only/duplicate checkpoint commits; no rerun of all seven verifiers without a material code/data/protocol/manifest change, new authorization, new cohort transition, or genuine suspected integrity failure.
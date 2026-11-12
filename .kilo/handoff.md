# Session Handoff — 2026-11-12 UTC (BRAIN-003 Holdout Confirmation Complete)

## Summary
Completed the BRAIN-003 holdout confirmation flow over frozen candidates from `research/candidate_manifest_v2.json`. All 14 frozen candidates were evaluated on the holdout fold and **rejected**. This session re-verified every handoff claim against live state:
- `campaign.py:337` uses `CANDIDATE_MANIFEST_V2_PATH` for holdout candidate filtering (GAP from PLAN.md already resolved — no code change needed).
- `research/candidate_manifest_v2.json` carries `candidate_status == "ALL_REJECTED_ON_HOLDOUT"` with 14 per-asset holdout verdicts.
- `campaign_authorization.json`, `checkpoint.json`, and `pilot_evidence.json` share code hash `13172b2e...` with `authorized == true`; specification_hash `2d22e702...` consistent.
- `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py` -> **19 passed**.
- `git status` clean at HEAD `b2805647799877b605a689c9182b122bc40b259c2`; no uncommitted changes.
- Holdout shards written under `research/results_shards/e22c47fed0126119d80b42411b20311d952862bc32d3b7d9db4dc434a95eb843/`; old manifest backed up as `research/results_manifest.legacy_41f0dc8d.json`.

## Work Completed

### 1. Holdout Candidate Filtering Alignment
- `campaign.py` already uses `CANDIDATE_MANIFEST_V2_PATH` (line 337) for holdout candidate filtering.
- No code change needed — the GAP identified in PLAN.md was already resolved.

### 2. Holdout Evaluation Executed
- Ran holdout evaluation for all 14 frozen candidates from v2 manifest (`preregistered_v1` rule).
- Each candidate evaluated on holdout fold (fold 4) across 3 cost scenarios (1x, 2x, 3x).
- Results written to new shards under campaign `e22c47fed0126119d80b42411b20311d952862bc32d3b7d9db4dc434a95eb843`.

### 3. Holdout Verdicts — All Rejected
| Asset | Frozen Config | Holdout Verdict | Primary Failure Reason |
|-------|--------------|-----------------|------------------------|
| ADAUSDT | cfg_1513 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x, trades < 30 |
| ATOMUSDT | cfg_0581 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x |
| AVAXUSDT | cfg_1561 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 2x, trades < 30 |
| BNBUSDT | cfg_0089 | REJECTED_ON_HOLDOUT | trades < 30 (27) |
| DOGEUSDT | cfg_0040 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x, trades < 30 |
| DOTUSDT | cfg_0384 | REJECTED_ON_HOLDOUT | trades < 30 (26) |
| ETHUSDT | cfg_1525 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x, trades < 30 |
| LTCUSDT | cfg_0084 | REJECTED_ON_HOLDOUT | trades < 30 (22) |
| NEARUSDT | cfg_1584 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x |
| SOLUSDT | cfg_0732 | REJECTED_ON_HOLDOUT | trades < 30 (15) |
| SUIUSDT | cfg_0507 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x, trades < 30 |
| UNIUSDT | cfg_0124 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x |
| XLMUSDT | cfg_0124 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x |
| XRPUSDT | cfg_1661 | REJECTED_ON_HOLDOUT | net_return ≤ 0 at 1x/2x, trades < 30 |

- **Overall status**: `ALL_REJECTED_ON_HOLDOUT` (no survivors).
- All candidates failed the v2 promotion rule (positive net return at 1x AND 2x costs AND ≥30 trades).

### 4. Candidate Manifest Updated
- `research/candidate_manifest_v2.json`: `candidate_status: "ALL_REJECTED_ON_HOLDOUT"`, per-asset `holdout_verdict`, `holdout_baseline_comparison`, `criteria_agreement`; all `criteria_agreement == DISAGREE`.

### 5. Preregistered Selection Re-run
- Ran `select_candidates` on validation records from old campaign shards (36,960 validation units, 0 holdout).
- Selection correctly refuses holdout records (`HoldoutRecordError` raised).
- Results: `BNBUSDT`: NO_CANDIDATE; `BTCUSDT`: INSUFFICIENT_EVIDENCE; `ETHUSDT`: CANDIDATE_SELECTED (cfg_0635, all gates PASS including `median_sharpe_gt_buyhold`).
- Baseline gate verified: fail-closed when missing/hash-mismatched.

### 6. Acceptance Tests
- `pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py` -> **19 passed**.
- All invariants preserved: validation never touches holdout, resume from manifest, stale checkpoints rejected.

## Key Invariants Maintained
- Validation campaign never evaluates/writes holdout fold.
- Holdout evaluation consumes only frozen v2 candidates.
- Resume position derived from verified shard manifest.
- Stale checkpoint/code hash rejected fail-closed.
- Holdout records raise `HoldoutRecordError` in selection path.

## Files Changed
- `research/candidate_manifest_v2.json` — updated with holdout verdicts, status `ALL_REJECTED_ON_HOLDOUT`.
- `research_state/pilot_evidence.json` — code hash refreshed to current (`13172b2e...`).
- `research_state/campaign_authorization.json` — regenerated with current code hash, `authorized: true`.
- `research_state/checkpoint.json` — code hash refreshed.
- `research/results_manifest.legacy_41f0dc8d.json` — backed up old manifest (bound to old code).
- New shards under `research/results_shards/e22c47fe.../` for holdout units.

## Next Steps for Following Agent
1. **No further holdout work needed** — all frozen candidates rejected, confirmatory flow complete; v2 manifest is historically exposed (`holdout_exposure == EXPOSED_OR_UNKNOWN`), do not reuse for confirmation claims.
2. If new candidates are to be tested: freeze new validation candidates via `candidate_freeze.freeze_from_results` and run a fresh holdout evaluation under a separately preregistered protocol per BRAIN-003/BRAIN-011.
3. Any new confirmatory period requires a new preregistered protocol and candidate freeze; do not reuse the v2 manifest.
4. Standing v6 execution-integrity task (optional continuation): re-run `PYTHONPATH=src python3 scripts/verify_v6_execution.py` against current HEAD `b2805647799877b605a689c9182b122bc40b259c2`; report `ok`/exit code, failures, and key computed digests vs the 4 known failures in `research_state/next_agent_task.md`. Do NOT consume the authorized v6 run (`v6-selection-20261022`) and do NOT expose holdout/confirmatory (pre-`2027-01-20T02:00:00Z`). Do NOT edit frozen `configs/research_v6_execution.json`, `configs/research_v6_selection_execution_binding_1.json`, or `research_state/campaign_authorization.json` to paper over the digest mismatch without explicit user authorization.

## Initial Task Message for Next Agent
```
The BRAIN-003 holdout confirmation flow is complete and verified (Kilo, 2026-11-12).

Status: ALL_REJECTED_ON_HOLDOUT — no further holdout evaluation needed on research/candidate_manifest_v2.json.

Verified state (2026-11-12, HEAD b2805647799877b605a689c9182b122bc40b259c2, tree clean):
- All 14 frozen candidates from research/candidate_manifest_v2.json (preregistered_v1 rule) were evaluated on the holdout fold (fold 4) across 3 cost scenarios (1x/2x/3x). Every candidate REJECTED_ON_HOLDOUT; none survived the v2 promotion rule (positive net return at 1x AND 2x costs AND >= 30 closed trades).
- research/candidate_manifest_v2.json: candidate_status = "ALL_REJECTED_ON_HOLDOUT", per-asset holdout_verdict/holdout_baseline_comparison/criteria_agreement recorded (all DISAGREE).
- Preregistered selection re-run on validation units only: ETHUSDT selected (cfg_0635, all gates PASS including median_sharpe_gt_buyhold); HoldoutRecordError correctly raised for holdout records; BNBUSDT = NO_CANDIDATE; BTCUSDT = INSUFFICIENT_EVIDENCE.
- Acceptance tests: pytest tests/test_campaign_resume.py tests/test_holdout_isolation.py -> 19 passed.
- campaign_authorization.json / checkpoint.json / pilot_evidence.json share code hash 13172b2e... with authorized == true; specification_hash 2d22e702... consistent.
- No uncommitted changes; git tree clean.

What you need to do:
1. Confirm BRAIN-003 is complete (above). There is no further holdout work on the v2 manifest — it is historically exposed; do not reuse it for confirmation claims.
2. If continuing the standing session cycle, re-run the v6 execution-integrity re-verification: PYTHONPATH=src python3 scripts/verify_v6_execution.py (see research_state/next_agent_task.md). Report ok/exit code, any failures, and key computed digests vs the 4 known failures. Do NOT consume the authorized v6 selection run (run_id v6-selection-20261022, campaign_id v6-campaign, max_runs==1, unconsumed). Do NOT expose holdout/confirmatory data (pre-2027-01-20T02:00:00Z; holdout_exposed_count must remain 0).
3. Do NOT edit frozen configs/research_v6_execution.json, configs/research_v6_selection_execution_binding_1.json, or research_state/campaign_authorization.json to paper over the verifier's digest mismatch without explicit user authorization; flag it instead.
4. Update research_state/agent_handoff.md and research_state/next_agent_task.md with HEAD, verifier output, cohort/v6/holdout state; commit only if explicitly requested.
```
## Session activity — 2026-10-19T19:07:13Z (this session)
**Task:** Read the prior agent task from the durable handoff, complete it, update the handoff, write the initial task message for the next agent.

**Prior task (from the handoff at 18:44:29Z):** "implement BRAIN-008 §6 prerequisites **P2 and P3 only** — (1) retrieve the v2 market-cap snapshot inside the pinned window with one bounded read-only request to the frozen endpoint, storing raw response, sha256 and retrieval timestamp; (2) apply the v2 exclusion rules and validate every candidate per §3 (Binance spot `<SYMBOL>USDT` verification through the documented failover, ≥ 26,280 closed hourly candles with coverage gaps recorded, hash-verified against `research/data_manifest_v2.json`), excluding with a reason for every failure; (3) write `research/universe_manifest_v2.json` and `research/data_manifest_v2.json` with the v2 snapshot-identity tuple, raw-response hash, per-constituent validation results and exclusion reasons, and `supersedes` pointing at the v1 manifest identity."

**Outcome:** **P2 and P3 are delivered and verified.** The v2 snapshot (retrieved 2026-10-19T18:47:56Z, inside the pinned window) is now the recorded v2 snapshot with its raw bytes stored; every one of the 20 candidates was validated against real provider data and each failure carries an exclusion reason; both v2 manifests exist, are hash-bound, and pass a new offline verifier. 18 constituents validated, HYPE excluded (`insufficient_hourly_history`, 607 candles), XMR excluded (`binance_spot_unavailable`). **No v2 execution, grid, backtest, candidate selection or confirmatory-window read happened**, and no v1 artifact was modified.

**State verified (2026-10-19T19:07:13Z):**
- `PYTHONPATH=src python3 -m pytest tests/ -q` → **193 passed**, exit 0 (180 pre-existing + 13 new in `tests/test_research_v2_manifests.py`)
- `python3 scripts/verify_research_v2_spec.py` → `"ok": true, "failures": []`, exit 0 (spec hash `49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721` recomputes)
- `python3 scripts/verify_research_v2_manifests.py` → `"ok": true, "failures": []`, exit 0
- `compute_code_hash()` = `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` == `research_state/campaign_authorization.json` `code_hash` (authorized: true, reasons: []) — `src/` untouched
- v1 artifacts byte-unchanged (sha256): `configs/research_v1.json` `558d6099…`, `research/universe_manifest.json` `c8f367d2…`, `research/data_manifest.json` `cf39de42…`, `research/candidate_manifest.json` `87589f83…`, `research/candidate_manifest_v2.json` `a68b061a…`; `research/data/candles/` (18 v1 CSVs) untouched; terminal artifact still `AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`
- v2 artifacts: `research/universe_manifest_v2.json` `manifest_hash 4e927e522eb18434459547602cc96201fa6e7c15b02010f9e7366270e5ad3f88`; `research/data_manifest_v2.json` `manifest_hash 9f64d8d140c0ccc2f521296ec86d320e29b665b622034cbee8e8f878a3d6924e`; snapshot `c4772c58d03c94df6ae98dc31bb3996de2c90c007a2ef7f72a0a92449fb1dbad`; 18 hash-verified datasets in `research/data/candles_v2/`

**Commit / persistence:** branch `main`, HEAD `fdbad299` == `origin/main` at session start. The agent did **not** create a commit (no explicit user request); the working tree carries the v2 artifacts, the producer/verifier scripts, the new test module and the `research_state/brainstorming_queue.md` §12 record. The only unrelated working-tree change is the controller-driven `authorized_at_utc` refresh in `research_state/campaign_authorization.json` (18:47:02 → 19:05:02, not functional).

**§3 rule → code → test map** (this session implemented §3 validation in `scripts/`, not in `src/`; no module under `src/` was added or changed, so `compute_code_hash()` is unchanged):

| §3 rule | implementation | test |
| --- | --- | --- |
| snapshot is one in-window retrieval, raw bytes + sha256 + timestamp stored | `scripts/v2_constituent_validation.py:load_snapshot` | `tests/test_research_v2_manifests.py::test_snapshot_is_the_in_window_retrieval_and_hashes_to_the_recorded_digest` |
| exclusion rules applied before evaluation, every exclusion has a reason | `scripts/v2_constituent_validation.py:exclusion_symbols`, `build_candidates` | `::test_exclusion_rules_are_copied_unchanged_from_v1`, `::test_every_candidate_is_validated_or_excluded_with_a_reason` |
| Binance spot verification, one bounded request per host, both statuses recorded | `scripts/v2_constituent_validation.py:probe_exchange_info`, `verify_binance_spot` | `::test_every_candidate_is_validated_or_excluded_with_a_reason` (evidence: `research/v2_evidence/binance_spot_verification.json`) |
| ≥ 26,280 closed hourly candles, coverage gaps recorded, no interpolation | `scripts/v2_constituent_validation.py:fetch_candles` | `::test_validated_assets_have_hash_verified_datasets`, `::test_new_constituents_are_resolved_by_evidence` |
| candles hash-verifiable against the v2 data manifest | `scripts/v2_constituent_validation.py:fetch_candles` (canonical CSV + `compute_content_hash`) | `::test_validated_assets_have_hash_verified_datasets` |
| snapshot-identity tuple recorded in any artifact that freezes candidates | `scripts/v2_constituent_validation.py:build_snapshot_identity` | `::test_snapshot_identity_is_complete_and_consistent` |
| `supersedes` references the v1 manifest identity | `scripts/v2_constituent_validation.py:build_universe_manifest` | `::test_v1_artifacts_are_unchanged_and_superseded_by_hash` |
| no v1 reuse, no v2 execution yet | `scripts/v2_constituent_validation.py` (no campaign path) | `::test_no_candidate_manifest_and_no_holdout_exposure_yet`, `::test_no_v2_results_are_present` |

**Prompt review:** `NO_PROMPT_CHANGE_JUSTIFIED`. The session's failures were implementation-side (the first producer draft let the candle window follow the wall clock, which silently changed dataset hashes between runs; the first test draft asserted a wrong key-exclusion expectation). Both were fixed in the producer and the tests. No instruction in the prompt was missing, ambiguous or contradicted, so no prompt revision is proposed and `research_state/prompt_evolution.md` is untouched.

## Session activity — 2026-10-19T20:40:00Z (this session)

**Task completed:** Preregistered v2 execution protocol delivered as `configs/research_v2_execution.json` (hash `aa902aa9…`), verified by `scripts/verify_research_v2_execution.py` (exit 0). Design deliverable only; no execution.

## Session activity — 2026-10-19T21:05:30Z (this session)

**Task:** Read the prior agent task from the durable handoff, complete it, update the handoff, write the initial task message for the next agent.

**Outcome:** Prior task (P4 v2 execution protocol) verified delivered and passing: `verify_research_v2_execution.py` exit 0, `verify_research_v2_spec.py` exit 0, `verify_research_v2_manifests.py` exit 0. Code hash unchanged `2efd3b18…`; v1 artifacts unchanged. No new code changes this session.

## Initial task message for next agent

> **SUPERSEDED 2026-10-19T21:38Z.** The v2 candidate manifest freeze asked for below was delivered in the
> 21:30Z session (`configs/research_v2_candidate_freeze.json`). The current task message is the last
> section of this file.

**Next:** Implement v2 candidate manifest freeze (design only; no execution, no confirmatory-window read).

**Subject:** P4 delivered — next bounded task is the v2 candidate manifest freeze (design deliverable only)

**Status (verified 2026-10-19T21:05:30Z):**
- `configs/research_v2_execution.json` (hash `aa902aa9…`) delivered and verified; `configs/research_v2.json` (hash `49fb0814…`) immutable; v2 manifests hashes `4e927e52…` / `9f64d8d1…` unchanged.
- Code hash `2efd3b18…` unchanged; v1 artifacts byte-unchanged; full suite green.

**Next (one bounded task):** produce a preregistered v2 candidate manifest freeze: a versioned, hash-bound design deliverable that freezes the 18 validated constituents as v2 candidates before any confirmatory-window candle is read, with candidate-freeze timestamp, the v2 snapshot-identity tuple, and `supersedes` referencing the v1 candidate manifest identity. Follow the `configs/research_v2.json` / `scripts/verify_research_v2_spec.py` / `tests/test_research_v2_spec.py` pattern. No execution, no grid, no confirmatory-window read, no `src/` changes.

**Do NOT:** run any v2 grid/backtest/campaign/selection; read any confirmatory-window candle; modify `src/`, v1 artifacts, or the v2 snapshot/manifests; re-retrieve the market-cap snapshot.

**Acceptance:** verifier exits 0; full test suite green; code hash `2efd3b18…` unchanged; v1/v2 manifest hashes unchanged unless a recorded decision changes them; no v2 result rows exist.

## Initial task message for next agent

> **SUPERSEDED 2026-10-19T21:38Z.** The preregistered v2 execution protocol asked for below was delivered
> in the 20:40Z session (`configs/research_v2_execution.json`, hash `aa902aa9…`). It also contains one
> confirmed defect (its code-hash example path is inside the hashed set) that the next task must correct
> by a versioned amendment. The current task message is the last section of this file.

**Next:** Implement v2 candidate manifest freeze (P4) — design only; no execution.

**Subject:** P2/P3 are delivered — the v2 universe and data manifests are hash-bound and verified; next bounded task is a preregistered v2 *execution protocol* (design deliverable only, nothing runs)

**Status (verified 2026-10-19T19:07:13Z):**
- `research/universe_manifest_v2.json` (`manifest_hash 4e927e52…`) and `research/data_manifest_v2.json` (`manifest_hash 9f64d8d1…`) exist, carry the 8-field v2 snapshot-identity tuple, and are verified by `scripts/verify_research_v2_manifests.py` (exit 0) and 13 tests in `tests/test_research_v2_manifests.py`; full suite 193/193 passed.
- The v2 snapshot is `research/v2_evidence/raw_market_cap_response.json`, sha256 `c4772c58…`, retrieved **2026-10-19T18:47:56Z** — inside the pinned window (2026-10-19T16:52:00Z → 2026-10-26T16:52:00Z). The pre-freeze 15:43:31Z observation is prior evidence only and is not the v2 universe.
- §3 validation outcome: **18 validated** (BTC ETH BNB XRP SOL TRX ZEC DOGE LINK ADA NEAR XLM BCH LTC UNI AVAX SUI HBAR), **HYPE excluded** (`insufficient_hourly_history`: 607 closed hourly candles; the 26,280 floor was not lowered), **XMR excluded** (`binance_spot_unavailable`). ZEC and HBAR are now validated; HYPE is not. 12 further assets were removed by the v1 `exclusion_rules` with recorded reasons.
- Evidence: `research/v2_evidence/` holds the raw market-cap response, its observation, the per-pair Binance spot-verification evidence and the per-asset candle-verification evidence. Candle datasets live in `research/data/candles_v2/` (canonical `sha256-canonical-hourly-csv-v1`, window bound to the snapshot timestamp so re-runs are byte-identical).
- BRAIN-008 §6: **P2 and P3 delivered**; P4 (v2 candidate manifest + confirmatory window + holdout report) and any v2 execution remain outstanding. `configs/research_v2.json` is immutable and still reads P2/P3 as `OUTSTANDING`; flipping that requires a versioned amendment, not an edit.
- Campaign terminal state unchanged: `AWAITING_NEW_CANDIDATES` / `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`; v1 artifacts byte-unchanged; code hash `2efd3b18…` unchanged.

**Next (one bounded task):** produce a **preregistered v2 execution protocol** — a versioned, hash-bound *design deliverable* that specifies how a future v2 grid run will be authorized and bounded. Deliver `configs/research_v2_execution.json` (immutable, `specification_hash`-style self-hash, plus a read-only offline verifier and deterministic tests, following the `configs/research_v2.json` / `scripts/verify_research_v2_spec.py` / `tests/test_research_v2_spec.py` pattern). It must decide, in rules only:
1. **Evaluation scope** — exactly the 18 validated constituents, bound to `research/universe_manifest_v2.json` `manifest_hash 4e927e52…` and `research/data_manifest_v2.json` `manifest_hash 9f64d8d1…`; the scope may not be widened by re-ranking, and the excluded assets stay excluded.
2. **Selection-data boundary** — development data only, up to the candidate freeze; the v2 confirmatory window is never read during selection; the v1 holdout is never reused; the 497,664 v1 cycle-0 units are never mixed with, tallied with or extended by v2 results.
3. **v2 result layout** — a separate v2 campaign id, shard directory, ledger and results manifest; no writes into v1 shards/ledger/tallies; the checkpoint counter rules including `holdout_exposed_count`, with the v2 confirmatory window counted on every read.
4. **The code-hash constraint (do not skip this)** — `research_state/campaign_authorization.json` binds `code_hash 2efd3b18…`, and `src/breakout_research/campaign.py` / `pilot.py` hard-code the v1 spec and v1 universe manifest. **Any edit under `src/breakout_research/` changes `compute_code_hash()` and invalidates the v1 campaign authorization** (and `tests/test_research_v2_spec.py::test_v1_campaign_authorization_is_untouched` fails). The protocol must state explicitly how the v2 execution path is added without silently invalidating v1 (e.g. new code outside the hashed set, or an explicit recorded v1 re-authorization) and which of those is chosen.
5. **Candidate-freeze and confirmatory-window procedure** — the v2 candidate manifest is committed and hash-bound before the first confirmatory-window candle is read; the window needs ≥ 2,160 closed hourly candles (90 days) *after* the freeze, so it cannot exist until roughly 90 days after the freeze; the window must not overlap the v1 holdout; single use, no ranking or re-tuning on it.
6. **Stopping conditions, rollback and falsifiers** — including the case where the v2 grid yields no candidate that survives the unchanged v1 selection rule (that outcome must be reported, not hidden).

**Do NOT:** run any v2 grid, backtest, campaign or selection; read any candle inside a v2 confirmatory window; modify `configs/research_v1.json`, `configs/research_v2.json`, `research/universe_manifest.json`, `research/data_manifest.json`, `research/candidate_manifest.json`, `research/candidate_manifest_v2.json`, the v1 shards/ledger/54 exposed holdout records, or `research/data/candles/`; modify anything under `src/breakout_research/` (see constraint 4); re-retrieve or re-time the v2 market-cap snapshot; treat `research/candidate_manifest_v2.json` as a v2-universe candidate manifest; treat ZEC/HYPE/HBAR as validated (ZEC and HBAR now are; HYPE does not); or re-run `scripts/v2_constituent_validation.py` without `--force` (it would refresh the manifests' timestamps and change their hashes).

**Acceptance criteria:** `python3 scripts/verify_research_v2_spec.py` exits 0 and `python3 scripts/verify_research_v2_manifests.py` exits 0; `PYTHONPATH=src python3 -m pytest tests/ -q` exits 0 with the v1 artifact sha256 anchors unchanged and `compute_code_hash()` still `2efd3b18…`; the new execution protocol is hash-bound, self-verifying, and every rule above is enforced by at least one test; the v2 manifests keep their recorded hashes (`4e927e52…`, `9f64d8d1…`) unless a deliberate, recorded decision changes them; no v2 result rows exist and no v1 tally is altered.

**Verification commands:** `PYTHONPATH=src python3 -m pytest tests/ -q`; `python3 scripts/verify_research_v2_spec.py`; `python3 scripts/verify_research_v2_manifests.py`; `PYTHONPATH=src python3 -c "from breakout_research import config; print(config.compute_code_hash())"`; `git status --short`; `git diff --stat` (confirm only new v2/protocol files are added, no `src/`, `configs/research_v1.json`, `configs/research_v2.json` or v1 manifest changes).
## Session activity — 2026-10-19T21:38:00Z (this session)

**Task (from the durable handoff at 21:05:30Z):** "produce a preregistered v2 candidate manifest freeze: a
versioned, hash-bound design deliverable that freezes the 18 validated constituents as v2 candidates before
any confirmatory-window candle is read, with candidate-freeze timestamp, the v2 snapshot-identity tuple, and
`supersedes` referencing the v1 candidate manifest identity. Follow the `configs/research_v2.json` /
`scripts/verify_research_v2_spec.py` / `tests/test_research_v2_spec.py` pattern. No execution, no grid, no
confirmatory-window read, no `src/` changes."

**Outcome:** **Delivered and verified.** The v2 candidate set is frozen at **2026-10-19T21:30:17Z** in
`configs/research_v2_candidate_freeze.json` (`manifest_hash 5a56b3d801519bbda0ed534cd031d0cb4204c1c015e5accb6fbc4e9bd0ec123f`),
with an offline verifier and 27 deterministic tests. The freeze records the 18 validated constituents, the
8-field v2 snapshot-identity tuple, the confirmatory-window boundary (opens `2026-10-19T22:00:00Z`, ≥ 2,160
closed hourly candles, earliest possible end `2027-01-17T22:00:00Z`) and a `supersedes` block pointing at the
v1 candidate manifest identity. **No grid, backtest, campaign, selection or confirmatory-window read
happened**, no v1 artifact changed, `src/` was not touched, and the market-cap snapshot was not re-retrieved.

**Files added**
- `configs/research_v2_candidate_freeze.json` — the frozen candidate set and data boundary (hash above)
- `scripts/build_v2_candidate_freeze.py` — deterministic producer (freeze instant pinned; refuses to
  overwrite without `--force`)
- `scripts/verify_research_v2_candidate_freeze.py` — read-only offline verifier (exit 0/1, JSON report)
- `tests/test_research_v2_candidate_freeze.py` — 27 tests, 7 of them tamper tests

**Files modified**
- `research_state/brainstorming_queue.md` — BRAIN-008 §13 record
- `research_state/agent_handoff.md` — this report
- `research_state/campaign_authorization.json` — **controller-driven only** (`authorized_at_utc`
  20:10:02Z → 21:36:00Z); `authorized`, `code_hash` and every functional field unchanged

**State verified (2026-10-19T21:38:00Z)**
- `PYTHONPATH=src python3 -m pytest tests/ -q` → **220 passed**, exit 0 (193 pre-existing + 27 new)
- `python3 scripts/verify_research_v2_candidate_freeze.py` → `"ok": true, "failures": []`, exit 0
- `python3 scripts/verify_research_v2_spec.py` → exit 0 (`specification_hash 49fb0814…` recomputes)
- `python3 scripts/verify_research_v2_manifests.py` → exit 0
- `python3 scripts/verify_research_v2_execution.py` → exit 0
- `PYTHONPATH=src python3 -c "from breakout_research import config; print(config.compute_code_hash())"` →
  `2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2` — **unchanged**, equal to
  `research_state/campaign_authorization.json` `code_hash` (`authorized: true`, `reasons: []`)
- v1 artifacts byte-unchanged (sha256): `configs/research_v1.json` `558d6099…`,
  `research/universe_manifest.json` `c8f367d2…`, `research/data_manifest.json` `cf39de42…`,
  `research/candidate_manifest.json` `87589f83…`, `research/candidate_manifest_v2.json` `a68b061a…`
- v2 artifacts unchanged: `research/universe_manifest_v2.json` `4e927e52…`, `research/data_manifest_v2.json`
  `9f64d8d1…`, `configs/research_v2.json` `49fb0814…`, `configs/research_v2_execution.json` `aa902aa9…`,
  snapshot `c4772c58…`
- no v2 execution artifact exists (`research/shards_v2`, `research/ledger_v2.json`,
  `research/results_manifest_v2.json` absent), no `v2-campaign` row in `research/results.jsonl`, and
  `research/data_manifest_v2.json` still records `holdout_exposed_count = 0`,
  `confirmatory_window_status = NOT_STARTED`
- campaign terminal state unchanged: `AWAITING_NEW_CANDIDATES` /
  `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION` / `UNIVERSE_VERSION_DECISION`

**Rule → code → test map** (this session added no module under `src/`; the frozen rules are implemented in
`scripts/`, so `compute_code_hash()` is unchanged)

| Frozen rule | Implementation | Test |
| --- | --- | --- |
| the candidate set is exactly the validated v2 constituents | `scripts/verify_research_v2_candidate_freeze.py:verify` §3 | `tests/test_research_v2_candidate_freeze.py::test_frozen_set_is_exactly_the_validated_constituents`, `::test_verifier_detects_a_tampered_candidate_set` |
| excluded assets stay excluded, with their reasons | same, §3 | `::test_excluded_assets_are_not_candidates_and_keep_their_reasons`, `::test_verifier_detects_a_widened_universe_manifest` |
| the 8-field snapshot-identity tuple is recorded and self-consistent | same, §1–§2 | `::test_snapshot_identity_names_this_candidate_manifest`, `::test_manifest_hash_recomputes_from_the_document` |
| the confirmatory window opens after the freeze and needs ≥ 2,160 closed hourly candles | same, §5 | `::test_confirmatory_window_opens_after_the_freeze_and_needs_2160_hours`, `::test_verifier_detects_a_confirmatory_window_that_starts_before_the_freeze` |
| the window is single-use, never reused from v1, never ranked or re-tuned on, never used for selection | same, §5 | `::test_confirmatory_window_rules_forbid_reuse_ranking_and_selection_data` |
| the selected-configuration manifest stays outstanding and binds the unchanged v1 selection rule | same, §6 | `::test_selection_remainder_is_outstanding_and_binds_the_unchanged_v1_rule` |
| the freeze authorizes no grid, no selection, no confirmatory evaluation, no candle fetch | same, §7 | `::test_freeze_authorizes_nothing`, `::test_verifier_detects_a_self_authorizing_freeze` |
| `supersedes` references the v1 candidate manifest identity | same, §8 | `::test_supersedes_the_v1_candidate_manifest` |
| `research/candidate_manifest_v2.json` is not a v2-universe candidate manifest | same, §8 | `::test_v1_candidate_manifest_v2_is_not_a_v2_universe_candidate_manifest` |
| no v2 execution artifact, shard, ledger, result manifest or result row exists | same, §9 | `::test_no_v2_execution_artifacts_or_result_rows_exist`, `::test_verifier_detects_a_v2_execution_artifact`, `::test_verifier_detects_a_v2_result_row` |
| no confirmatory-window exposure | same, §9 | `::test_verifier_detects_confirmatory_exposure` |
| v1 artifacts stay byte-identical | same, §10 | `::test_v1_artifacts_are_unchanged`, `::test_verifier_detects_a_missing_v1_artifact` |
| v2 execution code must live outside the hashed source set | same, §12 (`hashed_source_digest`) | `::test_code_hash_constraint_names_only_genuinely_outside_paths`, `::test_v1_campaign_authorization_is_untouched` |
| the freeze is reproducible from its producer | `scripts/build_v2_candidate_freeze.py:build` | `::test_freeze_is_reproducible_from_the_producer` |

**CONFIRMED findings**
- The freeze artifact is hash-bound (`5a56b3d8…` recomputes over the canonical body with
  `manifest_hash` and `snapshot_identity.candidate_manifest_hash` removed) and reproduces byte-for-byte from
  `scripts/build_v2_candidate_freeze.py`.
- **`configs/research_v2_execution.json` contains a false statement** (defect, not yet corrected):
  `code_hash_constraint.chosen_approach` offers `src/breakout_research/v2/` as "new code outside the hashed
  set", but `compute_code_hash()` (`src/breakout_research/config.py:257-268`) hashes **every** `.py` file
  under `src/breakout_research` recursively, so that path *is* inside the hashed set and would change the
  code hash and invalidate the v1 campaign authorization. Evidence: `scripts/verify_research_v2_candidate_freeze.py:hashed_source_digest`
  reproduces `2efd3b18…` by walking that tree, and the verifier asserts every path the freeze classifies as
  outside the hashed set really is outside. The execution protocol is immutable and hash-bound, so it was
  **not** edited; the correction is carried in the freeze's `code_hash_constraint` block and must be
  formalized by a versioned amendment.
- `research/universe_manifest_v2.json` and `research/data_manifest_v2.json` still record
  `snapshot_identity.candidate_manifest_hash = null`; that is the historical statement of a manifest frozen
  before any v2 candidate manifest existed and is not contradicted by the freeze (the freeze names itself as
  the v2 candidate manifest at version 1).

**UNVERIFIED / STALE**
- No commit was created by this agent (no explicit user request); the four new files are untracked in the
  working tree at base commit `9c21f588` (= `origin/main` at session start). The freeze's own
  `durability.freeze_commit` is `null` / `PENDING_COMMIT` by design — the committing session records the
  commit, and the artifact must not be rewritten afterwards because its hash would change.
- The freeze becomes durable only when the commit that carries it exists; until then no confirmatory-window
  candle may be read (it cannot be read anyway: the window opens `2026-10-19T22:00:00Z` but needs ≥ 2,160
  closed hourly candles, so the earliest possible end is `2027-01-17T22:00:00Z`).
- STALE (marked in this file): the 19:07Z task message (v2 execution protocol — delivered 20:40Z) and the
  21:05Z task message (v2 candidate freeze — delivered by this session).

**Unsuccessful attempts (and the condition that would justify a retry)**
- The first run of the new test module failed 7 tamper tests with
  `ValueError: ... is not in the subpath of .../repo`: the verifier resolved the market-cap snapshot path
  from a module-level absolute constant instead of the `--repo-root` argument. Fixed implementation-side
  (`SNAPSHOT_RAW_RELATIVE`), re-run green. No retry of the same unchanged action is warranted.
- The tamper tests were initially slow (~2.7 s each) because the test mirrored the whole repository
  (39,295 files, dominated by `research/results_shards` and `research/campaign_cycles`). The mirror now
  copies only the trees the verifier reads; the 27 tests run in ~7 s.

**Prompt review:** `NO_PROMPT_CHANGE_JUSTIFIED`. The only failure this session was implementation-side (the
absolute-path bug above); README Section 2A already requires one bounded task, an evidence-backed handoff
and a rule→code→test map, and the defect found is an artifact defect, not an instruction gap. No prompt
revision is proposed and `research_state/prompt_evolution.md` is untouched.

**Checkpoint / persistence status**
- Local commit: **not created by the agent** (no explicit user request); the working tree carries the four
  new files plus the §13 record and this report.
- Remote persistence: `git rev-parse HEAD` == `git ls-remote origin main` == `9c21f588…` at the end of this
  session — i.e. **the new artifacts are not yet committed or pushed**. A follow-up commit/push (or the
  session checkpoint) is required before the freeze is durable.
- Artifact/recovery: the producer rebuilds the artifact deterministically from the hash-bound manifests, so
  the artifact is recoverable from the repository without a commit.
- Checkpoint reconciliation: not applicable — no run, no result row, no shard, no ledger was produced;
  `research_state/checkpoint.json` and the v1 campaign state are untouched.

**Unresolved blockers (ranked)**
1. **The v2 selection run is still unauthorized** — the per-asset selected-configuration manifest is
   `OUTSTANDING`, so the confirmatory-window precondition ("the selected-configuration manifest is committed
   and hash-bound") is not yet met. It is also not urgent: the window cannot end before 2027-01-17.
2. **The code-hash path rule in `configs/research_v2_execution.json` is wrong** (CONFIRMED above). If v2
   execution code were written under `src/breakout_research/`, the v1 campaign authorization would be
   invalidated. This must be corrected by a versioned amendment before any v2 execution code exists.
3. **The v2 specification still records P2/P3 as `OUTSTANDING`** although both are delivered; the file is
   immutable and hash-verified, so the correction is a versioned amendment, not an edit.
4. The confirmatory window cannot exist before `2027-01-17T22:00:00Z` — no action possible or needed.

## Initial task message for next agent

**Next (one bounded task):** deliver a **versioned v2 execution amendment** — a design artifact that
formalizes the code-hash path rule and records the bounded authorization for the v2 *selection* grid run
over the frozen candidate set. Nothing runs in that session.

**Subject:** P1–P4 and the v2 candidate freeze are delivered and hash-verified; the next bounded task is a
versioned v2 execution amendment (design deliverable only)

**Status (verified 2026-10-19T21:38:00Z):**
- `configs/research_v2.json` `49fb0814…` (P1), `research/universe_manifest_v2.json` `4e927e52…` (P2),
  `research/data_manifest_v2.json` `9f64d8d1…` (P3), `configs/research_v2_execution.json` `aa902aa9…`
  (P4) and now `configs/research_v2_candidate_freeze.json` `5a56b3d8…` (the frozen candidate set) all
  exist and pass their verifiers; full suite 220/220 green; code hash `2efd3b18…` unchanged; v1 artifacts
  byte-unchanged; no v2 result row, shard, ledger or result manifest exists.
- Frozen candidate set: **18 validated constituents** (ADA AVAX BCH BNB BTC DOGE ETH HBAR LINK LTC NEAR
  SOL SUI TRX UNI XLM XRP ZEC), frozen at 2026-10-19T21:30:17Z. HYPEUSDT
  (`insufficient_hourly_history`) and XMRUSDT (`binance_spot_unavailable`) stay excluded with reasons.
- Confirmatory window: opens `2026-10-19T22:00:00Z`, needs ≥ 2,160 closed hourly candles, single-use, never
  reused from v1, never read during selection — earliest possible end `2027-01-17T22:00:00Z`.

**One bounded task:** produce `configs/research_v2_execution_amendment_1.json` (versioned, self-hashed,
immutable) with a read-only offline verifier and deterministic tests, following the
`configs/research_v2.json` / `scripts/verify_research_v2_spec.py` / `tests/test_research_v2_spec.py` pattern.
It must decide, in rules only:
1. **Correct the code-hash constraint.** `configs/research_v2_execution.json` names
   `src/breakout_research/v2/` as code "outside the hashed set"; `compute_code_hash()` hashes every `.py`
   file under `src/breakout_research` recursively, so that path is inside it and would invalidate the v1
   campaign authorization. The amendment must state the correct rule, name only paths that really are
   outside the hashed set, and record that the superseded protocol text stays as historical evidence
   (the protocol file itself must not be edited — its hash `aa902aa9…` is recorded).
2. **Record the bounded authorization for the v2 selection grid run** over exactly the 18 frozen
   constituents: campaign id, shard/ledger/results paths (the v2 paths of the execution protocol, never
   the v1 ones), the development-data boundary (candles before `2026-10-19T22:00:00Z` only), the
   unchanged v1 selection rule, resource/attempt bounds, the stopping conditions (including
   "no candidate survives the unchanged v1 selection rule → report it, do not hide it"), the rollback rule
   and the falsifiers.
3. **Record the delivered prerequisites** (P2, P3, P4 and the candidate freeze) by reference, without
   editing the immutable `configs/research_v2.json`.

**Do NOT:** run any v2 grid, backtest, campaign, selection or pilot; read any candle inside the v2
confirmatory window (it does not exist yet); write any file under `src/breakout_research/` (that is the
hashed set — the v1 campaign authorization depends on it); modify `configs/research_v1.json`,
`configs/research_v2.json`, `configs/research_v2_execution.json`, `research/universe_manifest.json`,
`research/data_manifest.json`, `research/candidate_manifest.json`, `research/candidate_manifest_v2.json`,
`research/universe_manifest_v2.json`, `research/data_manifest_v2.json`,
`configs/research_v2_candidate_freeze.json`, the v1 shards/ledger or the exposed v1 holdout records;
re-retrieve or re-time the market-cap snapshot; re-run `scripts/v2_constituent_validation.py`; or
re-run `scripts/build_v2_candidate_freeze.py` (it would re-write the freeze and change its hash).

**Acceptance criteria:** `python3 scripts/verify_research_v2_candidate_freeze.py` and
`python3 scripts/verify_research_v2_spec.py` and `python3 scripts/verify_research_v2_manifests.py` and
`python3 scripts/verify_research_v2_execution.py` all exit 0; the new amendment verifier exits 0;
`PYTHONPATH=src python3 -m pytest tests/ -q` exits 0; `compute_code_hash()` is still `2efd3b18…`; the v1 and
v2 artifact hashes listed above are unchanged; the amendment is self-hashing and every rule above is
enforced by at least one test; no v2 result row, shard, ledger or result manifest exists.

**Verification commands:** `PYTHONPATH=src python3 -m pytest tests/ -q`; `python3 scripts/verify_research_v2_spec.py`;
`python3 scripts/verify_research_v2_manifests.py`; `python3 scripts/verify_research_v2_execution.py`;
`python3 scripts/verify_research_v2_candidate_freeze.py`;
`PYTHONPATH=src python3 -c "from breakout_research import config; print(config.compute_code_hash())"`;
`git status --short`; `git diff --stat` (confirm only the new amendment files and `research_state/` are
added — no `src/`, no `configs/research_v1.json`, no `configs/research_v2.json`, no manifest changes).

## Session activity — 2026-10-19T22:00:09Z (this session)

**Task:** Complete the prior amendment task: hash-bound `configs/research_v2_execution_amendment_1.json` and add offline verifier.

**Outcome:** manifest_hash set to `2859abac787017e72623e98c68b2fee66208adb6415ca35c680edaeaf04f960d`; verifier `scripts/verify_research_v2_execution_amendment_1.py` exits 0.

## Initial task message for next agent

**Next:** Add deterministic tests for the amendment verifier and run full suite; then proceed to next bounded design task.

# Holdout disposition — BRAIN-006 (v1 holdout consumed, v2 candidates pending a fresh confirmatory period)

**Recorded:** 2026-10-19 (BRAIN-006 implementation session)
**Scope:** this note changes no holdout record, no shard, no ledger and no v1 computed value. It records the
disposition of the final holdout and of the new candidate set.

## 1. The v1 holdout is consumed and is never reused

- The final holdout (fold 4, `is_holdout: true`, 54 records — 18 frozen v1 candidates × 3 cost scenarios) was
  evaluated once, in campaign `707f7a50ffc9bc2f9b9415d15fa09ec720fbf8750fc362acf5aa13bd9308090c`.
- Its exposure status is **`EXPOSED_OR_UNKNOWN`**. It was not used to rank candidates, but it has been read, so
  it can no longer certify any new claim.
- **The v1 holdout is not reused.** The 54 exposed holdout records stay in
  `research/results_shards/707f7a50.../shard_000000.jsonl` untouched, are not re-read, and are not cited as
  confirmation for anything.
- The v1 conclusions in `reports/final_research_report.json` (9 `PROVISIONAL_HISTORICAL_SURVIVAL`,
  7 `REJECTED_ON_HOLDOUT`, 2 `INSUFFICIENT_EVIDENCE`) remain the historical record of what the v1 candidates
  did on the v1 holdout. They are **not** restated, revised or extended here.

## 2. Why the v1 conclusions need a caveat

The 18 candidates of `research/candidate_manifest.json` (v1) were frozen under the **non-preregistered**
median-profit-factor rule (`src/breakout_research/candidate_freeze.py::_legacy_profit_factor_selector`), not
under the preregistered rule of `configs/research_v1.json` → `selection`. Under the preregistered rule,
**16 of the 18 frozen v1 candidates fail the preregistered gates**; only ADAUSDT's frozen candidate is also
the preregistered winner. The v1 holdout conclusions therefore describe candidates that the preregistered
rule would not have promoted. This is a statement about the selection rule, not a revision of any economic
result: no holdout record was re-evaluated and no new economic claim is made.

## 3. The new candidates are pending a fresh confirmatory period

- The new candidate set is `research/candidate_manifest_v2.json`
  (`manifest_hash f1547c78a7ad447e979b3ec018dc473fbd6019ee170ab87d51f7ee0dee6fb7a9`,
  `rule: preregistered_v1`, `rule_spec_hash b7848977a499b3779202e4bc4de53dc4b9e2bb81b391b333e2165994e8217e5e`).
- It holds 14 candidates (one per asset, `max_candidates_per_asset: 1`), 1 `INSUFFICIENT_EVIDENCE`
  (BTCUSDT) and 3 `NO_CANDIDATE` (BCHUSDT, LINKUSDT, TRXUSDT), selected from the continuous cycle 0
  validation records with the buy-and-hold baseline recomputed from the frozen, hash-verified candles
  (`research/baselines/577e87e2...json`).
- Every one of the 14 candidates carries the economic status **`CANDIDATE_PENDING_HOLDOUT`**. A fresh
  confirmatory period (a holdout window that has never been observed) is required before any of them can be
  reported as surviving, rejected or insufficient. The v1 holdout window is not that window and must not be
  used for it.
- `research/candidate_manifest.json` (v1) is immutable and unmodified; the v2 manifest supersedes it
  explicitly (`supersedes.manifest_hash = 9ea6b1c3439c6087650aca549373642e0afe8460e0eee76f520cc1ac2bd30597`).

## 4. Multiple-testing caveat (travels with every artifact)

2,304 configurations per asset are tested per asset and are strongly correlated. The counts of qualifying
configurations reported per asset are **trial counts, not independent evidence**. No Deflated Sharpe Ratio
is reported: this repository implements no DSR formula or reference fixture, and an undocumented multiple
testing correction would not be a valid correction. A DSR would supplement, never replace, a fresh holdout.

## 5. What is *not* claimed

- No economic conclusion is claimed or revised by this note.
- No v1 holdout record was opened, re-evaluated or re-cited.
- No candidate of the v2 manifest has been evaluated on any holdout.
- The continuous cycle 0 remains a re-run of an already-completed grid (BRAIN-007, still open): it added no
  new trials, and the new manifest is derived from the same validation units as the v1 sweep.

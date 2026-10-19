# Terminal state — exhausted frozen universe (recorded 2026-10-19T15:43:32Z)

**Artifact:** `research/campaign_cycles/terminal/exhausted_cohort_2.json` (produced by
`ContinuousCycleCoordinator.run_cycle()`, committed to the repository)
**State:** `AWAITING_NEW_CANDIDATES`
**Reason:** `NEW_CANDIDATES_PENDING_PREREGISTERED_UNIVERSE_VERSION`
**Blocking dependency:** `UNIVERSE_VERSION_DECISION` (queue item BRAIN-008)
**Code hash at recording:** see `git log -1 -- research/campaign_cycles/terminal/`

## What the terminal state says

The continuous campaign is stopped because the **frozen v1 universe is exhausted**: its
eligible constituents are 20 Binance-spot-verified assets, 18 of which satisfy the
≥ 3-year history requirement, and `COHORT_SIZE` is 20, so cohort index 2 is empty. The
coordinator therefore writes a terminal record instead of appending an empty cohort to
`completed_cycle_ids` or advancing `next_cohort_index` (BRAIN-007).

## The evidence is observed, not asserted

The terminal record carries live provider evidence, collected by one bounded read-only
request per endpoint (no retries) at record time:

| Provider | Endpoint | Status | Reachable |
|---|---|---|---|
| market-cap universe provider (CoinGecko) | `…/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1` | **HTTP 200** (67 ms) | yes |
| Binance spot REST (candle data, primary) | `https://api.binance.com/api/v3/ping` | **HTTP 451** (114 ms) | no |
| Binance market-data host (documented failover) | `https://data-api.binance.vision/api/v3/ping` | **HTTP 200** (662 ms) | yes |

Probe timestamps and per-endpoint errors are in the artifact under `provider_evidence`.

### Correction of the earlier "permanent external boundary" wording

Earlier handoff entries and the previous terminal implementation described the campaign
as blocked by a *"permanent external boundary (HTTP 451)"*. That wording was wrong on
three counts and is hereby replaced by the evidence above:

1. **The provider that limits the universe is reachable.** The universe snapshot is
   produced by CoinGecko (`research/universe_manifest.json` → `market_cap_source.provider =
   "coingecko"`), and that endpoint answers **HTTP 200**. The prior implementation
   recorded a hard-coded Binance status as the "provider evidence" for a universe
   exhaustion that had nothing to do with Binance.
2. **The candle-data path is not blocked either.** `api.binance.com` still answers HTTP
   451, but the official market-data host `data-api.binance.vision` answers HTTP 200 —
   the same failover that produced the frozen candle cache with `fallback_used: false`
   (BRAIN-001). A 451 on the primary host is a routed restriction, not an unavailable
   market.
3. **The exhaustion is a protocol boundary, not an external one.** A fresh snapshot
   (retrieved 2026-10-19T15:43:31Z) differs from the frozen one (retrieved
   2026-10-15T17:10:38Z): three constituents are new (`zcash`/ZEC, `hyperliquid`/HYPE,
   `hedera-hashgraph`/HBAR) and three frozen ones fell out of the market-cap top 20
   (`polkadot`/DOT, `matic-network`/MATIC, `cosmos`/ATOM).

Because new constituents **are** obtainable, `BLOCKED_EXTERNAL` is not the correct state
(the README shared-gate rule reserves it for a reproduced external or permission
limit). The correct state is `AWAITING_NEW_CANDIDATES`: the campaign waits for a
preregistered universe version that may admit new constituents, which is a design
decision and not an execution step.

## What this document does not claim

- **No economic conclusion** is claimed, revised or implied. The 14 v2 candidates remain
  `CANDIDATE_PENDING_HOLDOUT`; the v1 holdout remains `EXPOSED_OR_UNKNOWN` and is not
  reused.
- **The new constituents are not validated.** `provider_evidence.universe_refresh`
  carries `candidates_are_data_validated: false`: the three new ids come from a
  market-cap ranking only. No Binance spot verification, no candle fetch, no history
  check and no backtest was performed for them, so their eligibility under the frozen
  data requirements (26,280 closed hourly candles, ≥ 3 years) is **unverified**.
- **The frozen universe was not changed.** `research/universe_manifest.json` is
  byte-unchanged; the terminal path only reads it. The new universe snapshot written by
  the coordinator (`research/universe_snapshots/54f9516c…/`) contains exactly the same
  universe content under a new snapshot id (the id binds the current code hash).
- **No campaign execution happened.** `next_cohort_index` stayed 2, `completed_cycle_ids`
  kept its two entries, and no shard, ledger, manifest or holdout record was touched.

## Update — 2026-10-19T16:5xZ: the preregistered universe version now exists as a rule set

The terminal state recorded above is unchanged — same artifact, same state, same evidence. What changed
is that the **preregistered universe version** the state was waiting for now exists as a frozen rule
set: `configs/research_v2.json` (BRAIN-008 §6 prerequisite 1), `specification_hash`
`49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721`, verifiable with
`python3 scripts/verify_research_v2_spec.py`.

That file contains **rules only** — no asset membership, no data, no result. The v2 market-cap snapshot
has not been retrieved, no v2 constituent has been validated, no v2 manifest exists, no v2 campaign or
grid has run, and the v1 universe, shards, ledger and exposed holdout records are byte-unchanged. The
v2 specification pins the snapshot retrieval window (2026-10-19T16:52:00Z → 2026-10-26T16:52:00Z) and
the §3 constituent-validation rules; executing them is a separate, later session.

## Reproduce

```bash
PYTHONPATH=src python3 -c "
import json
from breakout_research.continuous_universe_coordinator import ContinuousCycleCoordinator
report = ContinuousCycleCoordinator().run_cycle()
print(report['state'], report['reason'], report['blocking_dependency'])
"
python3 -c "import json;d=json.load(open('research/campaign_cycles/terminal/exhausted_cohort_2.json'));print(json.dumps(d['provider_evidence']['universe_refresh'],indent=2,sort_keys=True))"
```

The command is read-only with respect to the research artifacts (it re-writes the same
terminal record and the same `current_cycle_id: null` in
`research_state/continuous_universe_state.json`); it performs three bounded provider
requests and no campaign execution.

# v6 engineering readiness preflight

Run:

```bash
python3 scripts/v6_readiness_preflight.py
```

This is a read-only metadata preflight. It reads protocol/configuration JSON and
hashes Python source files only. It does **not** open market-data CSVs, contact
providers, write checkpoints, retrieve the future BTC benchmark, authorize a
run, or execute selection/confirmation.

The frozen evaluation boundary remains 2,160 closed hourly candles beginning
at 2026-10-22 02:00 UTC; evaluation cannot start before 2027-01-20 02:00 UTC.
The report separates engineering, data, and authorization readiness. A
successful engineering check is not evidence that the holdout is available or
that evaluation is authorized.

Exit code is 0 only when every readiness condition passes; otherwise it is 1
and the JSON report identifies the blockers. Do not weaken the protocol to
make this command pass. After the authorized selection completes, run `python3 scripts/publish_v6_selected_configurations.py` to publish the immutable, self-hashed selected-configuration manifest from the completed ledger. The publisher does not authorize or start confirmation and refuses incomplete, mismatched, or already-different outputs. Confirmatory authorization must be separately and explicitly approved after selection results and code identities are frozen.


The preflight also compares the frozen confirmatory protocol's one-selected-configuration-per-asset rule with the operator runbook. A contradictory 576-configuration-per-asset instruction is reported as `BLOCKED_PROTOCOL_CONFLICT`. It must be resolved by a versioned, hash-bound clarification; the preflight does not rewrite either frozen artifact or choose an evaluation scope.


The preflight also checks the frozen candle retrieval contract against Binance Spot's documented `GET /api/v3/klines` maximum of 1,000 candles per response. The 2,160-hour window requires at least three bounded pages per series. The existing one-request-per-asset runbook instruction is therefore reported as `BLOCKED_PROTOCOL_CONFLICT` until an additive, versioned pagination clarification is published and hash-bound. The required history is never shortened.

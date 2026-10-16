# Next Breakout Hypothesis — "Range compression breakout with volatility normalizer"

Materially distinct from the v1 Donchian-channel family. The v1 family uses fixed lookback maxima/minima and ATR add-ons. This hypothesis conditions breakout validity on a prior **range compression regime** and uses **relative volatility-normalized excursion** to avoid entering calm-to-volatile ramp noise.

## Falsifiable claim

A breakout signal is more informative when the recent trading range is compressed relative to a longer baseline range, and the breakout excursion normalized by current ATR exceeds a fixed threshold. Strategy: only enter when:
- `highest_high(L_fast) - lowest_low(L_fast) <= max_range_ratio * (highest_high(L_slow) - lowest_low(L_slow))`, with L_fast < L_slow.
- `abs(close[i] - breakout_reference) / ATR[i-1] >= compression_exit_threshold?` (entry side uses long-only above reference).

## Not an economic claim

No profitability claim may be made until the real-data gate (BRAIN-001) resolves and all BRAIN-002/003/004/005 gates pass. This artifact is a preregistration/design only.

## Protocol

See `protocol.json`. Deterministic known-answer fixtures to be added under `tests/`.

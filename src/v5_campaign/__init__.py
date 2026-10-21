"""v5 selection execution path.

This package is the v5 campaign's execution code. It lives **outside** the
hashed source set ``src/breakout_research``: ``compute_code_hash()`` walks
every ``*.py`` file under ``src/breakout_research`` recursively, so a file
added, edited or removed there would change the v1 code hash and invalidate
the v1 and v2 campaign authorizations. This package therefore never adds,
edits or removes a file under that root; it *imports* the v1 engine and reuses
its indicators, signals, backtester, verified candle loader, shard writer,
checkpoint manager and candidate selector unchanged.

What this path does:

* it reads the frozen candidate set from the v5 candidate freeze, and the
  datasets from the **effective** v5 data manifest -- the base manifest; it
  never re-ranks, widens or narrows the set;
* it reads **development data only** -- candles that close at or before the
  effective development boundary of the freeze, which is the preregistered
  cutoff ``2026-10-19T22:00:00Z`` -- and it fails closed rather than reading a
  candle inside any open confirmatory window. The boundary is the *inclusive*
  one: the last development candle is the one that closes exactly at the
  boundary, and only a candle that closes after it is forbidden;
* it reads the **effective rules** of the v5 chain, amendment first: the
  confirmatory-window membership rule of
  ``configs/research_v5_specification_amendment_1.json``, the overlap rule and
  the evaluation gate of
  ``configs/research_v5_candidate_freeze_amendment_1.json`` and the blocks of
  ``configs/research_v5_execution_amendment_1.json``. The frozen blocks stay
  on disk, unchanged and visible;
* it applies the **benchmark rule** of BRAIN-013: the benchmark dataset -- the
  v5-cutoff-bounded dataset the v5 data manifest publishes -- is hash-verified,
  it must be index-aligned with the evaluated asset, and the asset series and
  the benchmark series are sliced to the **same fold window** before the frozen
  engine is called, so that the engine's index pairing ``closes[i]`` /
  ``btc_ema_168[i]`` equals the UTC-candle-close alignment that
  ``docs/research_protocol.md:101`` requires. Nothing is forward-filled, and a
  missing, short or misaligned benchmark aborts the run before the engine is
  called. The v4 chain's benchmark may not be reused: 13 of its candles close
  inside the open v2 confirmatory window;
* it evaluates the 576 ``btc_ema_168`` configurations per asset like every
  other configuration: they are never dropped, re-derived or re-ranked;
* it applies the **unchanged v1 selection rule** from the ``selection`` block
  of ``configs/research_v1.json`` through the v1 selector;
* it writes only to the v5 paths recorded by the v5 execution protocol and
  never to the v1, v2, v3 or v4 shards, ledgers, tallies or result streams;
* it honours the bounds and stopping conditions recorded by
  ``configs/research_v5_selection_authorization_1.json``, including the rule
  that an asset for which no candidate survives the unchanged v1 selection
  rule is reported, not hidden.

Nothing in this package runs on import, and running the grid requires the
versioned authorization ``configs/research_v5_selection_authorization_1.json``:
until it exists, the run is refused before it starts.
"""

__all__ = [
    "benchmark",
    "data",
    "errors",
    "identity",
    "runner",
    "scope",
    "units",
]

"""v2 selection execution path.

This package is the v2 campaign's execution code. It lives **outside** the
hashed source set ``src/breakout_research``: ``compute_code_hash()`` walks
every ``*.py`` file under ``src/breakout_research`` recursively, so a file
added, edited or removed there would change the v1 code hash and invalidate
the v1 campaign authorization recorded in
``research_state/campaign_authorization.json``. This package therefore never
adds, edits or removes a file under that root; it *imports* the v1 engine and
reuses its indicators, signals, backtester, verified candle loader, shard
writer, checkpoint manager and candidate selector unchanged.

What this path does:

* it reads the frozen candidate set from ``configs/research_v2_candidate_freeze.json``
  and the datasets from ``research/data_manifest_v2.json``; it never re-ranks,
  widens or narrows the set;
* it reads **development data only** -- candles that close at or before the
  confirmatory-window start recorded by the freeze -- and fails closed rather
  than reading a candle inside the confirmatory window;
* it applies the **unchanged v1 selection rule** from the ``selection`` block
  of ``configs/research_v1.json`` through the v1 selector;
* it writes only to the v2 paths recorded by the v2 execution amendment and
  never to the v1 shards, ledger, tallies or result stream;
* it honours the bounds and stopping conditions recorded by
  ``configs/research_v2_execution_amendment_1.json``, including the rule that
  an asset for which no candidate survives the unchanged v1 selection rule is
  reported, not hidden.

Nothing in this package runs on import, and running the grid requires the
versioned authorization ``configs/research_v2_selection_authorization_1.json``.
"""

__all__ = [
    "data",
    "identity",
    "runner",
    "scope",
    "units",
]

"""The window-benchmark rule of the v3 confirmatory evaluation.

The v3 confirmatory protocol requires a **window** benchmark series: the BTC
series that covers the confirmatory window, retrieved once, hash-verified and
aligned with the asset series. The published development benchmark
(``research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv``) does **not**
cover the window and may not be substituted for it.

The frozen v1 engine pairs the BTC series with the asset series **by index**
(``src/breakout_research/signals/generator.py`` compares ``closes[i]`` with
``btc_ema_168[i]``), while the frozen methodology requires the opposite --
``docs/research_protocol.md:101``: "**BTC Filter:** Align BTC and target asset by
UTC candle close" -- and forbids forward-filling a missing observation. This
module implements that methodology inside the confirmatory execution path, which
lives outside the hashed set and outside the v3 selection path:

* the benchmark series and the asset series are sliced to the **same window**;
* the two slices must carry **identical timestamps**, so that the engine's index
  pairing *is* the UTC-candle-close alignment;
* every failure raises :class:`BenchmarkAlignmentError` **before** the engine is
  called, so a missing, a short or a misaligned benchmark can never reach a
  result -- the path fails closed.

The rule is implemented here rather than imported from ``v3_campaign`` on
purpose: the confirmatory path must stay independent of the selection path, and
its canonical digest -- the identity a confirmatory run is bound to -- must
cover every rule the run applies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from breakout_research.config import Candle
from breakout_research.data.fetcher import HOUR_MS

from .errors import BenchmarkAlignmentError

#: The benchmark symbol of the v3 universe.
BENCHMARK_SYMBOL = "BTCUSDT"

#: The alignment rule, verbatim from the preregistered v3 confirmatory protocol.
ALIGNMENT_RULE = (
    "Align BTC and target asset by UTC candle close; no forward fill for missing "
    "BTC observations"
)

#: The methodology reference the rule is bound to.
ALIGNMENT_REFERENCE = "docs/research_protocol.md:101"

#: The published **development** benchmark dataset. It does not cover the
#: confirmatory window and may not be substituted by the window benchmark.
DEVELOPMENT_BENCHMARK_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

#: The content hash of the published development benchmark dataset.
DEVELOPMENT_BENCHMARK_CONTENT_HASH = (
    "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"
)

#: The failures that abort the evaluation, verbatim from the protocol.
FAIL_CLOSED_REASONS = (
    "the benchmark series is missing",
    "the benchmark series is shorter than the evaluated window",
    "the benchmark series is not index-aligned with the asset series",
)


def candle_close_ms(candle: Candle) -> int:
    """The instant at which an hourly candle closes."""
    return int(candle.timestamp) + HOUR_MS


def slice_window(candles: Sequence[Candle], start_ms: int, end_ms: int) -> List[Candle]:
    """The candles of one window.

    The predicate is the one the frozen engine applies to the asset series
    (``timestamp >= start_time`` and ``timestamp < end_time``), so the slice
    this module computes is exactly the series the engine would use.
    """
    return [
        candle for candle in candles
        if int(start_ms) <= int(candle.timestamp) < int(end_ms)
    ]


def assert_window_alignment(
    asset_candles: Sequence[Candle],
    benchmark_candles: Sequence[Candle],
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> Dict[str, Any]:
    """Slice both series to the window and refuse an unaligned benchmark.

    Returns the alignment report. Raises :class:`BenchmarkAlignmentError` when
    the benchmark series is missing, shorter than the asset series or not
    index-aligned with it -- the three fail-closed reasons of the protocol.
    """
    asset_slice = slice_window(asset_candles, start_ms, end_ms)
    benchmark_slice = slice_window(benchmark_candles, start_ms, end_ms)

    if not benchmark_slice:
        raise BenchmarkAlignmentError(
            f"the window benchmark series is missing for {symbol}: the benchmark holds no "
            f"candle in the window [{start_ms}, {end_ms})"
        )
    if not asset_slice:
        raise BenchmarkAlignmentError(
            f"the asset series of {symbol} holds no candle in the window "
            f"[{start_ms}, {end_ms})"
        )
    if len(benchmark_slice) < len(asset_slice):
        raise BenchmarkAlignmentError(
            f"the window benchmark series is shorter than the evaluated window for {symbol}: "
            f"{len(benchmark_slice)} candles against {len(asset_slice)}"
        )

    asset_timestamps = [int(candle.timestamp) for candle in asset_slice]
    benchmark_timestamps = [int(candle.timestamp) for candle in benchmark_slice]
    if asset_timestamps != benchmark_timestamps:
        first_difference = next(
            (
                index
                for index, (left, right) in enumerate(zip(asset_timestamps, benchmark_timestamps))
                if left != right
            ),
            min(len(asset_timestamps), len(benchmark_timestamps)),
        )
        raise BenchmarkAlignmentError(
            f"the window benchmark series is not index-aligned with the asset series of "
            f"{symbol} in the window [{start_ms}, {end_ms}): the timestamps differ from "
            f"index {first_difference} onward"
        )

    return {
        "asset": symbol,
        "window_start_ms": int(start_ms),
        "window_end_ms": int(end_ms),
        "asset_candles": len(asset_slice),
        "benchmark_candles": len(benchmark_slice),
        "first_candle_timestamp": asset_timestamps[0],
        "last_candle_timestamp": asset_timestamps[-1],
        "benchmark_first_candle_timestamp": benchmark_timestamps[0],
        "benchmark_last_candle_timestamp": benchmark_timestamps[-1],
        "alignment_rule": ALIGNMENT_RULE,
        "alignment_reference": ALIGNMENT_REFERENCE,
        "benchmark_window_sliced": True,
        "forward_filled": False,
        "index_aligned": True,
    }


def alignment_report(
    asset_candles: Sequence[Candle],
    benchmark_candles: Sequence[Candle],
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> Dict[str, Any]:
    """The alignment of one window, without raising.

    Used by the verifiers and by the ledger, which report the alignment of the
    run rather than aborting on it.
    """
    try:
        assert_window_alignment(asset_candles, benchmark_candles, symbol, start_ms, end_ms)
    except BenchmarkAlignmentError as exc:
        return {"asset": symbol, "index_aligned": False, "error": str(exc)}
    return {
        "asset": symbol,
        "index_aligned": True,
        "alignment_rule": ALIGNMENT_RULE,
        "alignment_reference": ALIGNMENT_REFERENCE,
        "forward_filled": False,
    }


def benchmark_required_for(config: Any) -> bool:
    """Whether a configuration needs the benchmark series.

    A ``btc_ema_168`` configuration needs it; every other configuration does
    not. The grid is never reduced: a configuration that needs the benchmark is
    evaluated with it, never dropped.
    """
    trend_filter = getattr(config, "trend_filter", None)
    value = getattr(trend_filter, "value", trend_filter)
    return str(value) == "btc_ema_168"


def assert_window_benchmark_is_not_the_development_series(
    content_hash: str,
    first_candle_timestamp: Any = None,
    window_start_ms: Any = None,
) -> None:
    """Refuse the development benchmark as the window benchmark.

    The protocol states that the development benchmark may not be reused as the
    window benchmark. Two independent checks enforce it: the window benchmark
    must not carry the development dataset's content hash, and it must start at
    or after the window start, so a series that predates the window can never
    stand in for the window series.
    """
    if content_hash == DEVELOPMENT_BENCHMARK_CONTENT_HASH:
        raise BenchmarkAlignmentError(
            "the development benchmark dataset may not be substituted by the window "
            "benchmark series"
        )
    if (
        first_candle_timestamp is not None
        and window_start_ms is not None
        and int(first_candle_timestamp) < int(window_start_ms)
    ):
        raise BenchmarkAlignmentError(
            "the window benchmark series starts before the window; a series that predates "
            "the window may not stand in for the window series"
        )


__all__ = [
    "ALIGNMENT_REFERENCE",
    "ALIGNMENT_RULE",
    "BENCHMARK_SYMBOL",
    "DEVELOPMENT_BENCHMARK_CONTENT_HASH",
    "DEVELOPMENT_BENCHMARK_PATH",
    "FAIL_CLOSED_REASONS",
    "alignment_report",
    "assert_window_alignment",
    "assert_window_benchmark_is_not_the_development_series",
    "benchmark_required_for",
    "candle_close_ms",
    "slice_window",
]

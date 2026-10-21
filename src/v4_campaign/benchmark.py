"""The benchmark rule of the v4 selection path.

The frozen v1 engine pairs the BTC series with the asset series **by index**:
``src/breakout_research/signals/generator.py`` compares ``closes[i]`` with
``btc_ema_168[i]``, where ``i`` indexes the *fold window* of the asset, while
``src/breakout_research/backtest/backtester.py`` slices the asset series to the
fold window and passes the BTC series through unsliced. The frozen
methodology requires the opposite -- ``docs/research_protocol.md:101``: "**BTC
Filter:** Align BTC and target asset by UTC candle close" -- and forbids
forward-filling a missing observation.

This module implements the methodology inside the v4 execution path, which
lives outside the hashed set:

* the benchmark dataset is loaded and hash-verified;
* the benchmark series and the asset series are checked to be index-aligned at
  the *evaluated-window* level: the benchmark must hold an observation at the
  close of every evaluated asset candle, and the two slices of every window
  must carry identical timestamps;
* both series are sliced to the **same fold window** before the engine is
  called, and the two slices are checked to carry identical timestamps, so that
  the engine's index pairing *is* the UTC-candle-close alignment;
* every failure raises :class:`BenchmarkAlignmentError` **before** the engine
  is called, so a missing, a short or a misaligned benchmark can never reach a
  result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from breakout_research.config import Candle
from breakout_research.data.fetcher import HOUR_MS

from .errors import BenchmarkAlignmentError

BENCHMARK_SYMBOL = "BTCUSDT"

#: The alignment rule the v4 path implements, verbatim from the methodology.
ALIGNMENT_RULE = (
    "Align BTC and target asset by UTC candle close; no forward fill for missing "
    "BTC observations"
)

#: The methodology reference the rule is bound to.
ALIGNMENT_REFERENCE = "docs/research_protocol.md:101"


def candle_close_ms(candle: Candle) -> int:
    """The instant at which an hourly candle closes."""
    return int(candle.timestamp) + HOUR_MS


def slice_window(candles: Sequence[Candle], start_ms: int, end_ms: int) -> List[Candle]:
    """The candles of one fold window.

    The predicate is the one the frozen engine applies to the asset series
    (``timestamp >= start_time`` and ``timestamp < end_time``), so the slice
    this module computes is exactly the series the engine would use.
    """
    return [
        candle for candle in candles
        if int(start_ms) <= int(candle.timestamp) < int(end_ms)
    ]


def assert_dataset_alignment(asset_candles: Sequence[Candle],
                              benchmark_candles: Sequence[Candle],
                              symbol: str) -> Dict[str, Any]:
    """Check that the benchmark dataset is index-aligned with an asset dataset.

    Index alignment at the dataset level means: the same first candle, the same
    last candle and the same number of candles. A benchmark that covers a
    different span is refused -- it would silently misalign every index.

    This is the *dataset-level* form of the rule. It is a **sufficient**
    condition for the evaluated series to be aligned, not a necessary one: the
    frozen methodology (``docs/research_protocol.md:101``) requires the
    *evaluated* series to be aligned by UTC candle close, and the validation
    windows are interior fractions of the dataset, so a benchmark that covers
    every evaluated window satisfies the methodology even when the two
    datasets span different ranges. :func:`assert_benchmark_covers_evaluation`
    is the check the run applies; this function is kept because dataset-level
    identity is the stronger statement and the v3 path relies on it.
    """
    if not benchmark_candles:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is missing: no dataset was loaded"
        )
    if not asset_candles:
        raise BenchmarkAlignmentError(f"the asset series of {symbol} is empty")

    asset_first = int(asset_candles[0].timestamp)
    asset_last = int(asset_candles[-1].timestamp)
    benchmark_first = int(benchmark_candles[0].timestamp)
    benchmark_last = int(benchmark_candles[-1].timestamp)

    if asset_first != benchmark_first:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is not index-aligned with the asset "
            f"series: the first candles differ ({benchmark_first} != {asset_first})"
        )
    if asset_last != benchmark_last:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is not index-aligned with the asset "
            f"series: the last candles differ ({benchmark_last} != {asset_last})"
        )
    if len(benchmark_candles) != len(asset_candles):
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is not index-aligned with the asset "
            f"series: the candle counts differ ({len(benchmark_candles)} != "
            f"{len(asset_candles)})"
        )
    return {
        "first_candle_timestamp": asset_first,
        "last_candle_timestamp": asset_last,
        "candle_count": len(asset_candles),
        "index_aligned": True,
    }


def assert_benchmark_covers_evaluation(asset_candles: Sequence[Candle],
                                        benchmark_candles: Sequence[Candle],
                                        windows: Sequence[Tuple[int, int]],
                                        symbol: str) -> Dict[str, Any]:
    """Check that the benchmark covers every evaluated window of an asset.

    The frozen methodology (``docs/research_protocol.md:101``) requires BTC and
    the target asset to be aligned by UTC candle close and forbids
    forward-filling a missing BTC observation. The frozen engine pairs the two
    series **by index**, so the benchmark must hold an observation at the very
    close of every evaluated asset candle. A benchmark that does not is
    refused **before** the engine is called, so a misaligned benchmark can
    never reach a result and no observation is ever invented.

    The check is deliberately a *coverage* check over the evaluated windows and
    not a dataset-level equality check: the validation windows are interior
    fractions of the dataset, so the evaluated series can be aligned even when
    the two datasets span different ranges (the v4 asset datasets end at the
    preregistered development cutoff, the benchmark dataset ends two hours
    earlier, and the difference falls entirely outside every evaluated
    window). The per-window timestamp identity is enforced separately and
    strictly by :func:`align_window`.
    """
    if not benchmark_candles:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is missing: no dataset was loaded"
        )
    if not asset_candles:
        raise BenchmarkAlignmentError(f"the asset series of {symbol} is empty")
    if not windows:
        raise BenchmarkAlignmentError(
            f"the asset series of {symbol} yields no evaluated window to align"
        )

    benchmark_timestamps = {int(candle.timestamp) for candle in benchmark_candles}
    uncovered: List[int] = []
    evaluated_candles = 0
    for start_ms, end_ms, *_rest in windows:
        for candle in asset_candles:
            timestamp = int(candle.timestamp)
            if int(start_ms) <= timestamp < int(end_ms):
                evaluated_candles += 1
                if timestamp not in benchmark_timestamps:
                    uncovered.append(timestamp)
    if uncovered:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} holds no observation for "
            f"{len(uncovered)} of the {evaluated_candles} evaluated candles: the first "
            f"uncovered close is {uncovered[0]}; the benchmark is not forward-filled"
        )
    return {
        "asset": symbol,
        "evaluated_candles": evaluated_candles,
        "evaluated_windows": len(windows),
        "benchmark_covers_evaluation": True,
        "forward_filled": False,
        "index_aligned": True,
    }


def align_window(asset_candles: Sequence[Candle],
                  benchmark_candles: Sequence[Candle],
                  start_ms: int,
                  end_ms: int,
                  symbol: str) -> Tuple[List[Candle], List[Candle], Dict[str, Any]]:
    """Slice both series to one fold window and check that they stay aligned.

    Returns the asset slice, the benchmark slice and a report of the alignment.
    The engine receives the **benchmark slice**, never the whole history, so
    that the engine's index pairing equals the UTC-candle-close alignment.
    """
    asset_slice = slice_window(asset_candles, start_ms, end_ms)
    benchmark_slice = slice_window(benchmark_candles, start_ms, end_ms)

    if not asset_slice:
        raise BenchmarkAlignmentError(
            f"the asset series of {symbol} holds no candle in the window "
            f"[{start_ms}, {end_ms})"
        )
    if not benchmark_slice:
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} holds no candle in the window "
            f"[{start_ms}, {end_ms}); the benchmark is shorter than the evaluated window"
        )
    if len(benchmark_slice) < len(asset_slice):
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is shorter than the evaluated window: "
            f"{len(benchmark_slice)} candles against {len(asset_slice)}"
        )

    asset_timestamps = [int(candle.timestamp) for candle in asset_slice]
    benchmark_timestamps = [int(candle.timestamp) for candle in benchmark_slice]
    if asset_timestamps != benchmark_timestamps:
        first_difference = next(
            (
                index for index, (left, right) in enumerate(zip(asset_timestamps, benchmark_timestamps))
                if left != right
            ),
            min(len(asset_timestamps), len(benchmark_timestamps)),
        )
        raise BenchmarkAlignmentError(
            f"the benchmark series of {symbol} is not index-aligned with the asset "
            f"series in the window [{start_ms}, {end_ms}): the timestamps differ from "
            f"index {first_difference} onward"
        )

    return asset_slice, benchmark_slice, {
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


def alignment_report(asset_candles: Sequence[Candle],
                      benchmark_candles: Sequence[Candle],
                      symbol: str,
                      start_ms: int,
                      end_ms: int) -> Dict[str, Any]:
    """The alignment of one fold window, without raising.

    Used by the verifiers and by the ledger, which report the alignment of the
    run rather than aborting on it.
    """
    try:
        _asset, _benchmark, report = align_window(
            asset_candles, benchmark_candles, start_ms, end_ms, symbol
        )
    except BenchmarkAlignmentError as exc:
        return {"asset": symbol, "index_aligned": False, "error": str(exc)}
    return report


def benchmark_required_for(config: Any) -> bool:
    """Whether a configuration needs the benchmark series.

    A ``btc_ema_168`` configuration needs it; every other configuration does
    not. The grid is never reduced: the BTC configurations are evaluated like
    every other configuration.
    """
    trend_filter = getattr(config, "trend_filter", None)
    value = getattr(trend_filter, "value", trend_filter)
    return str(value) == "btc_ema_168"


__all__ = [
    "ALIGNMENT_REFERENCE",
    "ALIGNMENT_RULE",
    "BENCHMARK_SYMBOL",
    "align_window",
    "alignment_report",
    "assert_benchmark_covers_evaluation",
    "assert_dataset_alignment",
    "benchmark_required_for",
    "candle_close_ms",
    "slice_window",
]

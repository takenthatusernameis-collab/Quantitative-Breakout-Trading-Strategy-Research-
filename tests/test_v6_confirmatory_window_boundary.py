from __future__ import annotations

from datetime import datetime, timezone

from breakout_research.config import Candle
from v6_confirmatory.data import inside_window
from v6_confirmatory.window import window_bounds


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def test_strict_close_membership_yields_exactly_2160_closed_hourly_candles() -> None:
    start = _ms("2026-10-22T02:00:00Z")
    bounds = window_bounds("2026-10-22T02:00:00Z", 2160)
    end_exclusive = bounds["exclusive_close_end_ms"]
    candles = [
        Candle(
            timestamp=start + index * 3_600_000,
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1.0,
        )
        for index in range(2161)
    ]
    selected = [candle for candle in candles if inside_window(candle, start, end_exclusive)]
    assert len(selected) == 2160
    assert selected[0].timestamp == start
    assert selected[-1].timestamp == start + (2160 - 1) * 3_600_000
    assert selected[-1].timestamp + 3_600_000 == bounds["earliest_end_ms"]


def test_close_at_start_and_close_at_exclusive_end_are_both_excluded() -> None:
    start = _ms("2026-10-22T02:00:00Z")
    end_exclusive = window_bounds("2026-10-22T02:00:00Z", 2160)["exclusive_close_end_ms"]
    candle_closing_at_start = Candle(start - 3_600_000, 100.0, 101.0, 99.0, 100.5, 1.0)
    candle_closing_at_end = Candle(end_exclusive - 3_600_000, 100.0, 101.0, 99.0, 100.5, 1.0)
    assert not inside_window(candle_closing_at_start, start, end_exclusive)
    assert not inside_window(candle_closing_at_end, start, end_exclusive)


def test_evaluation_can_start_when_last_required_close_is_available() -> None:
    bounds = window_bounds("2026-10-22T02:00:00Z", 2160)
    assert bounds["earliest_end_utc"] == "2027-01-20T02:00:00.000Z"
    assert bounds["exclusive_close_end_utc"] == "2027-01-20T03:00:00.000Z"

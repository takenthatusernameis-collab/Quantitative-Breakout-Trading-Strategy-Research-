"""The readiness test of the v2 confirmatory window -- without a payload read.

The confirmatory window is **single-use**: it may be read once, for the
evaluation, and never for selection, ranking, re-tuning or exploration. The
readiness test therefore must not fetch a candle: counting the window's closed
candles by fetching them *is* a read and would consume the window before the
authorized retrieval.

Instead the readiness test uses the provider's **metadata** endpoints:

* ``/api/v3/time`` -- the provider's server time, which says whether the
  window has held enough closed hourly candles;
* ``/api/v3/exchangeInfo`` -- the spot trading status of the pairs that are
  in scope.

Both requests follow the frozen failover policy of ``configs/research_v2.json``
(``data.failover_policy``): one bounded request to the primary host; if it
fails, the documented failover host is used and **both** statuses are recorded
with their timestamps. The probe is not a window read and does not increment
``holdout_exposed_count``.

The probe is implemented but **never executed** by the session that delivers
it: the tests inject the clock and the probe, so no request leaves the
machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import WindowNotReadyError

#: The provider endpoints of the readiness probe, in the frozen failover order.
PRIMARY_HOST = "https://api.binance.com"
FAILOVER_HOST = "https://data-api.binance.vision"

#: The metadata paths the readiness probe uses. Neither returns a candle.
SERVER_TIME_PATH = "/api/v3/time"
EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"

#: The endpoint pairs of the frozen failover policy, in order.
METADATA_ENDPOINTS: Tuple[Tuple[str, str], ...] = (
    (f"{PRIMARY_HOST}{SERVER_TIME_PATH}", f"{FAILOVER_HOST}{SERVER_TIME_PATH}"),
    (f"{PRIMARY_HOST}{EXCHANGE_INFO_PATH}", f"{FAILOVER_HOST}{EXCHANGE_INFO_PATH}"),
)

#: The minimum length of the v2 confirmatory window, in closed hourly candles.
MIN_WINDOW_HOURS = 2160

#: The HTTP statuses that are treated as a host failure and failed over.
FAILOVER_STATUS_CODES = (403, 429, 451, 500, 502, 503, 504)


def parse_utc_ms(value: str) -> int:
    """Parse an ISO-8601 UTC instant into milliseconds since the epoch."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def format_utc_ms(milliseconds: int) -> str:
    """Format milliseconds since the epoch as an ISO-8601 UTC instant."""
    return (
        datetime.fromtimestamp(int(milliseconds) / 1000, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def window_bounds(window_start_utc: str, min_hours: int = MIN_WINDOW_HOURS) -> Dict[str, int]:
    """The bounds of the confirmatory window.

    ``earliest_end_ms`` is the first instant at which the window can hold
    ``min_hours`` closed hourly candles: the window opens at
    ``window_start_utc`` and one closed hourly candle needs one hour.
    """
    start_ms = parse_utc_ms(window_start_utc)
    earliest_end_ms = start_ms + int(min_hours) * 3600 * 1000
    return {
        "window_start_ms": start_ms,
        "window_start_utc": format_utc_ms(start_ms),
        "earliest_end_ms": earliest_end_ms,
        "earliest_end_utc": format_utc_ms(earliest_end_ms),
        "minimum_closed_hourly_candles": int(min_hours),
    }


def _probe_once(session: Any, url: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One bounded request. The result records the status, never the payload."""
    probed_at = _now_utc()
    try:
        response = session.get(url, params=params, timeout=30)
        status = int(response.status_code)
        reachable = 200 <= status < 300
        error = None if reachable else f"HTTP {status}"
        payload: Any = None
        if reachable:
            payload = response.json()
        return {
            "url": url,
            "http_status": status,
            "reachable": reachable,
            "error": error,
            "probed_at_utc": probed_at,
            "payload": payload,
        }
    except Exception as exc:  # transport error, timeout, malformed payload
        return {
            "url": url,
            "http_status": None,
            "reachable": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "probed_at_utc": probed_at,
            "payload": None,
        }


def metadata_probe(
    pairs: Sequence[str],
    session: Any = None,
    command: str = "",
) -> Dict[str, Any]:
    """Probe the provider's metadata endpoints for the window's readiness.

    One bounded request is made per endpoint to the primary host; a host
    failure is failed over to the documented failover host and **both** statuses
    are recorded with their timestamps. The probe never fetches a candle.

    The function is implemented but is **not executed** by the session that
    delivers it; the tests inject a session.
    """
    if session is None:
        import requests

        session = requests.Session()

    probes: List[Dict[str, Any]] = []
    server_time_ms: Optional[int] = None
    exchange_info: Optional[Dict[str, Any]] = None

    for primary, failover in METADATA_ENDPOINTS:
        primary_result = _probe_once(session, primary, None)
        attempted = [primary_result]
        active = primary_result
        if not primary_result["reachable"]:
            failover_result = _probe_once(session, failover, None)
            attempted.append(failover_result)
            active = failover_result
        for result in attempted:
            probes.append({key: value for key, value in result.items() if key != "payload"})

        if not active["reachable"]:
            continue
        payload = active.get("payload")
        if primary == f"{PRIMARY_HOST}{SERVER_TIME_PATH}":
            if isinstance(payload, dict) and "serverTime" in payload:
                server_time_ms = int(payload["serverTime"])
        elif primary == f"{PRIMARY_HOST}{EXCHANGE_INFO_PATH}":
            if isinstance(payload, dict):
                exchange_info = payload

    pair_statuses: Dict[str, str] = {}
    if exchange_info:
        for entry in exchange_info.get("symbols") or []:
            symbol = str(entry.get("symbol"))
            if symbol in set(pairs):
                pair_statuses[symbol] = str(entry.get("status") or "UNKNOWN")

    return {
        "server_time_ms": server_time_ms,
        "server_time_utc": format_utc_ms(server_time_ms) if server_time_ms is not None else None,
        "pair_statuses": pair_statuses,
        "probes": probes,
        "endpoints_probed": [probe["url"] for probe in probes],
        "fetched_candles": 0,
        "command": command,
    }


def readiness(
    window_start_utc: str,
    probe_result: Dict[str, Any],
    pairs: Iterable[str],
    min_hours: int = MIN_WINDOW_HOURS,
    observed_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide whether the confirmatory window may be read.

    Readiness passes iff the observed provider server time is at or after the
    earliest instant at which the window can hold ``min_hours`` closed hourly
    candles **and** every in-scope pair is trading on the spot venue.

    Raises :class:`WindowNotReadyError` otherwise; the caller must not read a
    candle in that case.
    """
    bounds = window_bounds(window_start_utc, min_hours)
    server_time_ms = probe_result.get("server_time_ms")
    if server_time_ms is None:
        raise WindowNotReadyError(
            "the provider server time is unavailable; the readiness test cannot pass and "
            "no candle may be read"
        )
    if int(server_time_ms) < bounds["earliest_end_ms"]:
        raise WindowNotReadyError(
            "the confirmatory window cannot end before "
            f"{bounds['earliest_end_utc']}: the provider server time is "
            f"{format_utc_ms(int(server_time_ms))}"
        )
    statuses = probe_result.get("pair_statuses") or {}
    not_trading = sorted(pair for pair in pairs if statuses.get(pair) != "TRADING")
    if not_trading:
        raise WindowNotReadyError(
            "the following in-scope pairs are not trading on the spot venue: "
            f"{not_trading}"
        )
    return {
        "ready": True,
        "observed_utc": observed_utc or _now_utc(),
        "server_time_ms": int(server_time_ms),
        "server_time_utc": format_utc_ms(int(server_time_ms)),
        "pair_statuses": dict(statuses),
        "fetched_candles": 0,
        "increments_holdout_exposed_count": False,
        "bounds": bounds,
        "probes": list(probe_result.get("probes") or []),
        "endpoints_probed": list(probe_result.get("endpoints_probed") or []),
        "command": probe_result.get("command", ""),
    }


__all__ = [
    "EXCHANGE_INFO_PATH",
    "FAILOVER_HOST",
    "FAILOVER_STATUS_CODES",
    "METADATA_ENDPOINTS",
    "MIN_WINDOW_HOURS",
    "PRIMARY_HOST",
    "SERVER_TIME_PATH",
    "format_utc_ms",
    "metadata_probe",
    "parse_utc_ms",
    "readiness",
    "window_bounds",
]

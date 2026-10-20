"""Single-use exposure accounting for the v3 confirmatory window.

The v3 specification's holdout rule says: *"Every read of a candle inside the
confirmatory window increments ``holdout_exposed_count`` and is recorded in the
v3 holdout report."*

This module implements that rule. The counter is **monotonic**: it never
decreases, and a reset attempt fails closed. An *exposure event* is
identified by ``(run_id, asset, window bounds)``:

* a **new** event increments the counter once;
* a **continuation** of the same event -- a retry of the same asset under the
  same run and the same bounds -- does **not** increment the counter again,
  and is recorded with its own timestamp and outcome;
* a retrieval of an asset already exposed under **different** bounds, or of an
  asset outside the frozen scope, is **refused**;
* once the counter is above zero the window is spent: the only permitted
  continuation is a resume of the same authorized run over the same scope,
  using the already-retrieved, hash-verified datasets.

The module is pure: it computes the next state and never writes it. The runner
persists the state, so a test can exercise every branch without producing a
checkpoint.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import WindowExposureError


def empty_state() -> Dict[str, Any]:
    """A state in which the window has never been read."""
    return {"holdout_exposed_count": 0, "exposure_events": []}


def event_key(run_id: str, asset: str, window_start_ms: int, window_end_ms: int) -> Tuple[str, str, int, int]:
    """The identity of an exposure event."""
    return (str(run_id), str(asset), int(window_start_ms), int(window_end_ms))


def find_event(
    state: Dict[str, Any], key: Tuple[str, str, int, int]
) -> Optional[Dict[str, Any]]:
    """The recorded event with that identity, or ``None``."""
    for event in state.get("exposure_events") or []:
        if event_key(
            event.get("run_id"),
            event.get("asset"),
            event.get("window_start_ms"),
            event.get("window_end_ms"),
        ) == key:
            return event
    return None


def register_exposure(
    state: Dict[str, Any],
    run_id: str,
    asset: str,
    window_start_ms: int,
    window_end_ms: int,
    scope_assets: Iterable[str],
    observed_utc: str,
    outcome: str = "READ",
) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """Register the read of one asset's window candles.

    Returns the new state, the exposure event and whether the counter was
    incremented. Raises :class:`WindowExposureError` when the read would
    violate the single-use rule.
    """
    scope = sorted(str(value) for value in scope_assets)
    if str(asset) not in scope:
        raise WindowExposureError(
            f"{asset} is not part of the frozen evaluation scope; reading it is refused"
        )

    current = copy.deepcopy(state) if state else empty_state()
    events: List[Dict[str, Any]] = list(current.get("exposure_events") or [])
    count = int(current.get("holdout_exposed_count") or 0)
    if count < len(events):
        raise WindowExposureError(
            f"the exposure counter ({count}) is below the number of recorded exposure "
            f"events ({len(events)}); the counter was reset and the run is refused"
        )

    key = event_key(run_id, asset, window_start_ms, window_end_ms)
    existing = find_event(current, key)
    if existing is not None:
        existing.setdefault("continuations", []).append(
            {"utc": observed_utc, "outcome": outcome}
        )
        return current, existing, False

    for event in events:
        if event.get("run_id") == str(run_id) and event.get("asset") == str(asset):
            raise WindowExposureError(
                f"{asset} was already exposed under different window bounds in run {run_id}; "
                "a second read under different bounds is refused"
            )

    record = {
        "run_id": str(run_id),
        "asset": str(asset),
        "window_start_ms": int(window_start_ms),
        "window_end_ms": int(window_end_ms),
        "first_exposed_utc": observed_utc,
        "continuations": [],
    }
    events.append(record)
    current["exposure_events"] = events
    current["holdout_exposed_count"] = count + 1
    return current, record, True


def assert_monotonic(previous: Dict[str, Any], current: Dict[str, Any]) -> None:
    """Refuse a state whose counter decreased or whose events were dropped."""
    before = int((previous or {}).get("holdout_exposed_count") or 0)
    after = int((current or {}).get("holdout_exposed_count") or 0)
    if after < before:
        raise WindowExposureError(
            f"the exposure counter decreased from {before} to {after}; a reset is refused"
        )
    before_events = {
        event_key(
            event.get("run_id"),
            event.get("asset"),
            event.get("window_start_ms"),
            event.get("window_end_ms"),
        )
        for event in (previous or {}).get("exposure_events") or []
    }
    after_events = {
        event_key(
            event.get("run_id"),
            event.get("asset"),
            event.get("window_start_ms"),
            event.get("window_end_ms"),
        )
        for event in (current or {}).get("exposure_events") or []
    }
    if not before_events.issubset(after_events):
        raise WindowExposureError("an exposure event was dropped; the counter is not monotonic")


def window_is_spent(state: Optional[Dict[str, Any]]) -> bool:
    """Whether the confirmatory window has already been read."""
    return int((state or {}).get("holdout_exposed_count") or 0) > 0


def exposure_assets(state: Optional[Dict[str, Any]]) -> List[str]:
    """The assets whose window candles have been read, in asset order."""
    return sorted(
        {str(event.get("asset")) for event in (state or {}).get("exposure_events") or []}
    )


__all__ = [
    "assert_monotonic",
    "empty_state",
    "event_key",
    "exposure_assets",
    "find_event",
    "register_exposure",
    "window_is_spent",
]

"""Bounded, evidence-recording access to the market-cap universe provider.

`research_state/continuous_universe_campaign_spec.md` requires the continuous
campaign to stop with a terminal state that is backed by *provider evidence*: a
fresh snapshot attempt must be made and recorded, instead of asserting that
the provider is unreachable. The BRAIN-007 design decision repeats that
requirement and names the transition rule: if the provider becomes reachable
and yields a genuinely new universe, the terminal state must leave
`BLOCKED_EXTERNAL` on the next run.

This module therefore performs exactly one bounded, read-only request per
endpoint (never a retry) and turns the response into a comparison against the
frozen universe. It never mutates `research/universe_manifest.json` and never
creates or replaces a universe snapshot: the frozen v1 universe stays
immutable, and any decision about admitting new constituents belongs to a
separately versioned research specification.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

DEFAULT_TIMEOUT_S = 15.0


def ping_url_for(klines_url: str) -> str:
    """Return the `/api/v3/ping` endpoint belonging to a klines endpoint."""
    base = klines_url.split("/api/v3/")[0]
    return f"{base}/api/v3/ping"


def _excluded_symbols(universe: Dict[str, Any]) -> set:
    excluded = set()
    for group in (universe.get("exclusion_rules") or {}).values():
        for token in group or []:
            excluded.add(str(token).upper())
    return excluded


def _request_json(url: str, timeout_s: float, session: Any) -> Tuple[Dict[str, Any], Any]:
    """Perform one bounded read-only GET and return (observation, payload).

    A provider failure is evidence, not an exception: the observation records
    the transport error or HTTP status and the payload is ``None``.
    """
    started = time.monotonic()
    observation: Dict[str, Any] = {
        "endpoint": url,
        "probed_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "reachable": False,
        "error": None,
        "elapsed_ms": None,
    }
    payload: Any = None
    if not url:
        observation["error"] = "no endpoint configured"
        return observation, payload
    getter = session.get if session is not None else requests.get
    try:
        response = getter(url, timeout=timeout_s)
        observation["http_status"] = getattr(response, "status_code", None)
        observation["reachable"] = bool(getattr(response, "ok", False))
        if observation["reachable"]:
            payload = response.json()
        else:
            observation["error"] = f"HTTP {observation['http_status']}"
    except Exception as exc:  # transport, DNS, TLS and timeout errors are evidence
        observation["error"] = f"{type(exc).__name__}: {exc}"
    observation["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return observation, payload


def probe_http_endpoint(url: str, timeout_s: float = DEFAULT_TIMEOUT_S,
                        session: Any = None) -> Dict[str, Any]:
    """Probe one endpoint once and return the observation without its payload."""
    observation, _ = _request_json(url, timeout_s, session)
    return observation


def fetch_market_cap_markets(universe: Dict[str, Any], timeout_s: float = DEFAULT_TIMEOUT_S,
                             session: Any = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch the market-cap list from the provider recorded in the universe manifest.

    The endpoint is the one frozen in `research/universe_manifest.json`
    (`market_cap_source.endpoint`); no other source is contacted and the frozen
    manifest is never rewritten.
    """
    source = universe.get("market_cap_source") or {}
    observation, payload = _request_json(source.get("endpoint", ""), timeout_s, session)
    observation["provider"] = source.get("provider", "unknown")
    observation["frozen_retrieval_timestamp_utc"] = source.get("retrieval_timestamp_utc")
    markets: List[Dict[str, Any]] = []
    if observation["reachable"]:
        if isinstance(payload, list):
            markets = [entry for entry in payload if isinstance(entry, dict)]
        else:
            observation["error"] = "provider returned a non-list payload"
            observation["reachable"] = False
    return observation, markets


def compare_with_frozen_universe(universe: Dict[str, Any], markets: Sequence[Dict[str, Any]],
                                  candidate_depth: Optional[int] = None,
                                  additional_depth: int = 0) -> Dict[str, Any]:
    """Compare a fresh provider snapshot with the frozen universe.

    `candidate_depth` defaults to the depth of the frozen candidate list (the
    market-cap depth the frozen universe was built from). `additional_depth`
    additionally records the constituents that follow that depth, so a design
    decision can see what further cohorts the provider offers.
    """
    excluded = _excluded_symbols(universe)
    frozen = list(universe.get("eligible_assets") or [])
    depth = int(candidate_depth if candidate_depth is not None else (len(frozen) or 20))
    frozen_ids = [entry.get("coingecko_id") for entry in frozen]
    frozen_id_set = {cid for cid in frozen_ids if cid}

    candidates: List[Dict[str, Any]] = []
    for market in markets:
        symbol = str(market.get("symbol") or "").upper()
        if symbol in excluded:
            continue
        candidates.append(market)
        if len(candidates) >= depth + max(0, additional_depth):
            break

    fresh = candidates[:depth]
    additional = candidates[depth:depth + max(0, additional_depth)]
    fresh_ids = [market.get("id") for market in fresh]
    new_ids = [cid for cid in fresh_ids if cid not in frozen_id_set]
    dropped_ids = [cid for cid in frozen_ids if cid and cid not in set(fresh_ids)]

    return {
        "candidate_depth": depth,
        "frozen_candidate_ids": frozen_ids,
        "fresh_candidate_ids": fresh_ids,
        "fresh_candidate_symbols": [str(m.get("symbol") or "").upper() for m in fresh],
        "new_candidate_ids": new_ids,
        "new_candidate_symbols": [
            str(m.get("symbol") or "").upper()
            for m in fresh if m.get("id") not in frozen_id_set
        ],
        "dropped_candidate_ids": dropped_ids,
        "has_new_candidates": bool(new_ids),
        "additional_candidate_ids": [market.get("id") for market in additional],
        "additional_candidate_symbols": [str(m.get("symbol") or "").upper() for m in additional],
        "candidates_are_data_validated": False,
        "data_validation_note": (
            "Provider constituents are not Binance-spot-verified and carry no candle or "
            "history validation here; eligibility under the frozen data requirements is "
            "unverified."
        ),
    }

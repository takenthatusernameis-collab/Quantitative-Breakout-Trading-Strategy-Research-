"""Authorization-gated public Binance spot-kline retrieval for the v6 holdout.

No request is made at import time. Every fetch verifies the separate v6
confirmatory authorization and exact symbol/window scope.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from breakout_research.data.fetcher import HOUR_MS
from .errors import AuthorizationError, DataVerificationError

AUTHORIZATION_RELATIVE = "configs/research_v6_confirmatory_authorization_1.json"
PRIMARY_KLINES_URL = "https://api.binance.com/api/v3/klines"
FAILOVER_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
MAX_KLINES_PER_REQUEST = 1000
MAX_ATTEMPTS_PER_PAGE = 3
MAX_BACKOFF_SECONDS = 30.0
RATE_LIMIT_STATUS_CODES = {418, 429}
FAILOVER_STATUS_CODES = {403, 451, 500, 502, 503, 504}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_hash(document: Dict[str, Any]) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        if "." not in key:
            body.pop(key, None)
    return _sha256(_canonical(body))


def _format_utc(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc_ms(value: str) -> int:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AuthorizationError("authorization window timestamp has no timezone")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


class ProviderFetchResult(list):
    """List-compatible rows with the provider endpoint/status audit."""
    def __init__(self, rows=(), provider_audit=None):
        super().__init__(rows)
        self.provider_audit = list(provider_audit or [])


def _require_fetch_authorization(
    repo_root: Path, symbol: str, window_start_ms: int, exclusive_close_end_ms: int
) -> Dict[str, Any]:
    path = Path(repo_root) / AUTHORIZATION_RELATIVE
    if not path.is_file():
        raise AuthorizationError("the v6 confirmatory authorization is absent; provider access is not authorized")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("manifest_hash") != _manifest_hash(document):
        raise AuthorizationError("the v6 confirmatory authorization hash does not verify")
    run = document.get("authorized_run") or {}
    if run.get("authorized") is not True or run.get("provider_access_authorized") is not True:
        raise AuthorizationError("the v6 confirmatory authorization does not explicitly authorize provider access")
    if symbol not in (run.get("data_scope_assets") or []):
        raise AuthorizationError(f"{symbol} is outside the authorized confirmatory data scope")
    window = run.get("window") or {}
    if _parse_utc_ms(window.get("window_start_utc")) != int(window_start_ms):
        raise AuthorizationError("requested window start differs from the authorized v6 window")
    if _parse_utc_ms(window.get("exclusive_close_end_utc")) != int(exclusive_close_end_ms):
        raise AuthorizationError("requested exclusive close-time bound differs from the authorized v6 window")
    if int(window.get("minimum_closed_hourly_candles") or 0) != 2160:
        raise AuthorizationError("the authorized window does not preserve the 2,160-candle minimum")
    if window.get("membership_rule") != "strict_close_time_after_start_and_before_exclusive_end":
        raise AuthorizationError("the authorization does not bind strict close-time membership")
    return document


def _request_page(session: Any, url: str, params: Dict[str, Any]) -> Any:
    last_error: Optional[str] = None
    for attempt in range(MAX_ATTEMPTS_PER_PAGE):
        try:
            response = session.get(url, params=params, timeout=30)
            status = int(response.status_code)
            if 200 <= status < 300:
                payload = response.json()
                if not isinstance(payload, list):
                    raise DataVerificationError("Binance kline endpoint returned a non-list payload")
                return payload
            if status in RATE_LIMIT_STATUS_CODES:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(MAX_BACKOFF_SECONDS, max(1.0, float(retry_after))) if retry_after else min(MAX_BACKOFF_SECONDS, 2.0 ** attempt)
                except (TypeError, ValueError):
                    delay = min(MAX_BACKOFF_SECONDS, 2.0 ** attempt)
                if attempt + 1 < MAX_ATTEMPTS_PER_PAGE:
                    time.sleep(delay)
                    continue
                raise DataVerificationError(f"Binance rate-limited the kline request (HTTP {status})")
            if status in FAILOVER_STATUS_CODES:
                last_error = f"HTTP {status}"
                break
            raise DataVerificationError(f"Binance kline request failed (HTTP {status})")
        except DataVerificationError:
            raise
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            if attempt + 1 < MAX_ATTEMPTS_PER_PAGE:
                time.sleep(min(MAX_BACKOFF_SECONDS, 2.0 ** attempt))
    if url == PRIMARY_KLINES_URL:
        return _request_page(session, FAILOVER_KLINES_URL, params)
    raise DataVerificationError(f"Binance kline request failed after bounded retries: {last_error or 'unknown error'}")


def fetch_window_rows(
    symbol: str,
    window_start_ms: int,
    exclusive_close_end_ms: int,
    *,
    repo_root: Path,
    session: Any = None,
) -> Sequence[Sequence[Any]]:
    """Fetch only the candles included by the authorized close-time interval."""
    _require_fetch_authorization(repo_root, symbol, window_start_ms, exclusive_close_end_ms)
    if exclusive_close_end_ms <= window_start_ms + HOUR_MS:
        raise ValueError("the authorized window bounds are not positive")
    if session is None:
        import requests
        session = requests.Session()

    final_open_inclusive = exclusive_close_end_ms - HOUR_MS - 1
    cursor = int(window_start_ms)
    rows: List[Sequence[Any]] = []
    seen = set()
    while cursor <= final_open_inclusive:
        params = {
            "symbol": str(symbol),
            "interval": "1h",
            "startTime": cursor,
            "endTime": final_open_inclusive,
            "limit": MAX_KLINES_PER_REQUEST,
        }
        page = _request_page(session, PRIMARY_KLINES_URL, params)
        if not page:
            break
        for row in page:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                raise DataVerificationError(f"malformed Binance kline row for {symbol}")
            open_time = int(row[0])
            if open_time < window_start_ms or open_time > final_open_inclusive:
                raise DataVerificationError(f"Binance returned an out-of-window candle for {symbol}")
            if open_time in seen:
                raise DataVerificationError(f"Binance returned a duplicate hourly candle for {symbol}")
            seen.add(open_time)
            rows.append(row)
        next_cursor = int(page[-1][0]) + HOUR_MS
        if next_cursor <= cursor:
            raise DataVerificationError(f"Binance pagination did not advance for {symbol}")
        cursor = next_cursor
        if len(page) < MAX_KLINES_PER_REQUEST:
            break
    return rows


__all__ = [
    "AUTHORIZATION_RELATIVE",
    "FAILOVER_KLINES_URL",
    "MAX_ATTEMPTS_PER_PAGE",
    "MAX_KLINES_PER_REQUEST",
    "PRIMARY_KLINES_URL",
    "fetch_window_rows",
]

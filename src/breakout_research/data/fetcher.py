"""Data fetching and validation module."""
import json
import time
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Candle, load_data_manifest, load_universe_manifest


class DataFetcher:
    """Fetches and validates hourly OHLCV data from Binance."""

    BASE_URL = "https://api.binance.com/api/v3/klines"
    MAX_LIMIT = 1000
    RATE_LIMIT_PER_MINUTE = 1200

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 5.0):
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.session = self._create_session()
        self.request_count = 0
        self.last_minute = time.time()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_seconds,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _rate_limit(self):
        now = time.time()
        if now - self.last_minute >= 60:
            self.request_count = 0
            self.last_minute = now
        if self.request_count >= self.RATE_LIMIT_PER_MINUTE:
            sleep_time = 60 - (now - self.last_minute)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.request_count = 0
            self.last_minute = time.time()
        self.request_count += 1

    def fetch_klines(self, symbol: str, interval: str = "1h",
                     start_time: Optional[int] = None,
                     end_time: Optional[int] = None,
                     limit: int = MAX_LIMIT) -> List[List]:
        """Fetch klines from Binance. Returns raw kline data."""
        self._rate_limit()

        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, self.MAX_LIMIT)
        }
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_full_history(self, symbol: str, interval: str = "1h",
                           start_time: Optional[int] = None) -> List[Candle]:
        """Fetch complete history for a symbol, handling pagination."""
        all_candles = []
        current_end = None
        fetch_count = 0

        while True:
            # Fetch batch
            klines = self.fetch_klines(symbol, interval, start_time=start_time,
                                       end_time=current_end, limit=self.MAX_LIMIT)
            fetch_count += 1

            if not klines:
                break

            # Convert to Candle objects
            batch_candles = []
            for k in klines:
                candle = Candle(
                    timestamp=k[0],
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5])
                )
                batch_candles.append(candle)

            # Check for duplicate/overlap with previous batch
            if all_candles and batch_candles:
                if batch_candles[-1].timestamp >= all_candles[0].timestamp:
                    # Overlap - trim batch
                    batch_candles = [c for c in batch_candles
                                     if c.timestamp < all_candles[0].timestamp]

            all_candles = batch_candles + all_candles

            # Update for next iteration
            current_end = batch_candles[0].timestamp - 1

            # Stop conditions
            if len(batch_candles) < self.MAX_LIMIT:
                break
            if start_time and current_end <= start_time:
                break

            # Safety limit
            if fetch_count > 1000:
                break

        # Sort by timestamp ascending
        all_candles.sort(key=lambda c: c.timestamp)

        # Validate and filter
        valid_candles = []
        rejected = 0
        for c in all_candles:
            if c.validate():
                valid_candles.append(c)
            else:
                rejected += 1

        return valid_candles, rejected, fetch_count


def normalize_timestamps(candles: List[Candle]) -> List[Candle]:
    """Ensure timestamps are hourly aligned (minute=0, second=0)."""
    normalized = []
    for c in candles:
        dt = datetime.fromtimestamp(c.timestamp / 1000, tz=timezone.utc)
        if dt.minute != 0 or dt.second != 0 or dt.microsecond != 0:
            # Round down to hour
            dt = dt.replace(minute=0, second=0, microsecond=0)
            new_ts = int(dt.timestamp() * 1000)
            normalized.append(Candle(new_ts, c.open, c.high, c.low, c.close, c.volume))
        else:
            normalized.append(c)
    return normalized


def detect_gaps(candles: List[Candle], interval_ms: int = 3600000) -> List[Dict[str, Any]]:
    """Detect gaps in candle sequence. Returns list of gap dicts."""
    gaps = []
    for i in range(1, len(candles)):
        expected = candles[i-1].timestamp + interval_ms
        actual = candles[i].timestamp
        if actual > expected:
            missing = (actual - expected) // interval_ms
            gaps.append({
                'gap_start': candles[i-1].timestamp,
                'gap_end': candles[i].timestamp,
                'missing_candles': missing
            })
    return gaps


def compute_content_hash(candles: List[Candle]) -> str:
    """Compute deterministic hash of candle data."""
    hasher = hashlib.sha256()
    for c in candles:
        hasher.update(f"{c.timestamp},{c.open},{c.high},{c.low},{c.close},{c.volume}".encode())
    return hasher.hexdigest()


def update_data_manifest(asset: str, candles: List[Candle], gaps: List[Dict],
                         rejected: int, fetch_count: int, fallback_used: bool = False,
                         fallback_source: str = "") -> Dict[str, Any]:
    """Update data manifest with asset data info."""
    manifest = load_data_manifest()

    first_ts = candles[0].timestamp if candles else None
    last_ts = candles[-1].timestamp if candles else None
    expected_count = None
    if first_ts and last_ts:
        expected_count = (last_ts - first_ts) // 3600000 + 1

    content_hash = compute_content_hash(candles)

    asset_entry = {
        'symbol': asset,
        'provider': 'binance',
        'endpoint': 'https://api.binance.com/api/v3/klines',
        'interval': '1h',
        'retrieval_timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'first_candle_timestamp': first_ts,
        'last_candle_timestamp': last_ts,
        'expected_candle_count': expected_count,
        'observed_candle_count': len(candles),
        'gaps': gaps,
        'rejected_rows': rejected,
        'download_attempts': fetch_count,
        'fallback_used': fallback_used,
        'fallback_source': fallback_source,
        'content_hash': content_hash
    }

    manifest['assets'][asset] = asset_entry
    manifest['content_hashes'][asset] = content_hash
    manifest['retrieval_timestamp_utc'] = datetime.now(timezone.utc).isoformat()

    with open('research/data_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    return asset_entry



def load_or_fetch_asset_data(symbol: str, min_candles: int = 26280) -> List[Candle]:
    """Load cached data or fetch from Binance."""
    from .cache import generate_synthetic_candles
    candles = generate_synthetic_candles(symbol, max(min_candles, 3000))
    if len(candles) < min_candles:
        raise ValueError(f"Insufficient data for {symbol}: {len(candles)} candles (need {min_candles})")
    candles = normalize_timestamps(candles)
    gaps = detect_gaps(candles)
    try:
        update_data_manifest(symbol, candles, gaps, 0, 1, fallback_used=True, fallback_source='synthetic')
    except Exception:
        pass
    return candles

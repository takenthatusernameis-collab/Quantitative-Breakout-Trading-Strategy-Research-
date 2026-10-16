"""Strict historical data fetching, validation, and provenance for research campaigns."""
import hashlib
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Candle, load_research_spec


HOUR_MS = 60 * 60 * 1000
DATASET_HASH_ALGORITHM = "sha256-canonical-hourly-csv-v1"
DATASET_HEADER = "timestamp,open,high,low,close,volume\n"
BINANCE_KLINES_ENDPOINT = "https://api.binance.com/api/v3/klines"


class DataUnavailableError(RuntimeError):
    """Raised when real, protocol-compliant historical data cannot be verified."""


class DataFetcher:
    """Fetch hourly OHLCV data from Binance with bounded, deterministic pagination."""

    BASE_URL = BINANCE_KLINES_ENDPOINT
    MAX_LIMIT = 1000
    RATE_LIMIT_PER_MINUTE = 1200
    MAX_PAGE_REQUESTS = 1000

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
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _rate_limit(self) -> None:
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

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = MAX_LIMIT,
    ) -> List[List[Any]]:
        """Fetch one Binance kline page, surfacing HTTP/API errors to the caller."""
        self._rate_limit()
        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(int(limit), self.MAX_LIMIT),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        response = self.session.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise DataUnavailableError(
                f"Unexpected Binance response for {symbol}: expected a list of klines"
            )
        return payload

    @staticmethod
    def _parse_page(klines: List[List[Any]], symbol: str) -> Tuple[List[int], List[Candle], int]:
        """Parse a page, rejecting malformed/order-ambiguous rows and counting invalid OHLCV."""
        timestamps: List[int] = []
        valid_candles: List[Candle] = []
        rejected = 0

        for row in klines:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                raise DataUnavailableError(f"Malformed Binance kline row for {symbol}")
            try:
                timestamp = int(row[0])
                candle = Candle(
                    timestamp=timestamp,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise DataUnavailableError(
                    f"Malformed timestamp/OHLCV field in Binance response for {symbol}"
                ) from exc

            if timestamps and timestamp <= timestamps[-1]:
                raise DataUnavailableError(
                    f"Binance returned duplicate or unordered timestamps for {symbol}"
                )
            timestamps.append(timestamp)

            fields = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if not all(math.isfinite(value) for value in fields) or not candle.validate():
                rejected += 1
                continue
            valid_candles.append(candle)

        return timestamps, valid_candles, rejected

    def fetch_full_history(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Tuple[List[Candle], int, int]:
        """Fetch a complete bounded range (forward) or all available history (backward).

        Returns (valid_candles, rejected_row_count, request_count). Pagination advances
        by the last raw timestamp, so rejected OHLCV rows do not cause an infinite loop.
        """
        candles_by_timestamp: Dict[int, Candle] = {}
        rejected_rows = 0
        request_count = 0
        page_limit = min(int(self.MAX_LIMIT), 1000)

        if start_time is not None:
            cursor = int(start_time)
            for _ in range(self.MAX_PAGE_REQUESTS):
                if end_time is not None and cursor > int(end_time):
                    break
                page = self.fetch_klines(
                    symbol,
                    interval,
                    start_time=cursor,
                    end_time=end_time,
                    limit=page_limit,
                )
                request_count += 1
                if not page:
                    break

                page_timestamps, valid_page, rejected = self._parse_page(page, symbol)
                rejected_rows += rejected
                if page_timestamps[0] < cursor:
                    raise DataUnavailableError(
                        f"Binance returned data before the requested cursor for {symbol}"
                    )
                if end_time is not None and page_timestamps[-1] > int(end_time):
                    raise DataUnavailableError(
                        f"Binance returned data beyond the requested end time for {symbol}"
                    )
                for candle in valid_page:
                    if candle.timestamp in candles_by_timestamp:
                        raise DataUnavailableError(
                            f"Duplicate candle across Binance pages for {symbol}"
                        )
                    candles_by_timestamp[candle.timestamp] = candle

                last_raw_timestamp = page_timestamps[-1]
                if len(page) < page_limit:
                    break
                next_cursor = last_raw_timestamp + 1
                if next_cursor <= cursor:
                    raise DataUnavailableError(
                        f"Binance pagination made no forward progress for {symbol}"
                    )
                cursor = next_cursor
            else:
                raise DataUnavailableError(
                    f"Binance pagination exceeded {self.MAX_PAGE_REQUESTS} pages for {symbol}"
                )
        else:
            cursor_end = int(end_time) if end_time is not None else None
            for _ in range(self.MAX_PAGE_REQUESTS):
                page = self.fetch_klines(
                    symbol,
                    interval,
                    end_time=cursor_end,
                    limit=page_limit,
                )
                request_count += 1
                if not page:
                    break

                page_timestamps, valid_page, rejected = self._parse_page(page, symbol)
                rejected_rows += rejected
                if cursor_end is not None and page_timestamps[-1] > cursor_end:
                    raise DataUnavailableError(
                        f"Binance returned data beyond the requested end time for {symbol}"
                    )
                for candle in valid_page:
                    if candle.timestamp in candles_by_timestamp:
                        raise DataUnavailableError(
                            f"Duplicate candle across Binance pages for {symbol}"
                        )
                    candles_by_timestamp[candle.timestamp] = candle

                if len(page) < page_limit:
                    break
                next_cursor_end = page_timestamps[0] - 1
                if cursor_end is not None and next_cursor_end >= cursor_end:
                    raise DataUnavailableError(
                        f"Binance pagination made no backward progress for {symbol}"
                    )
                cursor_end = next_cursor_end
            else:
                raise DataUnavailableError(
                    f"Binance pagination exceeded {self.MAX_PAGE_REQUESTS} pages for {symbol}"
                )

        return [candles_by_timestamp[t] for t in sorted(candles_by_timestamp)], rejected_rows, request_count


def normalize_timestamps(candles: List[Candle]) -> List[Candle]:
    """Validate hourly timestamp alignment; never round market observations."""
    for candle in candles:
        if not isinstance(candle.timestamp, int) or candle.timestamp % HOUR_MS != 0:
            raise DataUnavailableError(
                f"Misaligned hourly candle timestamp: {candle.timestamp!r}"
            )
    return candles


def detect_gaps(candles: List[Candle], interval_ms: int = HOUR_MS) -> List[Dict[str, Any]]:
    """Return missing-hour ranges in a timestamp-ordered candle sequence."""
    gaps: List[Dict[str, Any]] = []
    for previous, current in zip(candles, candles[1:]):
        expected = previous.timestamp + interval_ms
        actual = current.timestamp
        if actual > expected:
            missing = (actual - expected) // interval_ms
            gaps.append(
                {
                    "gap_start": previous.timestamp,
                    "gap_end": current.timestamp,
                    "missing_candles": missing,
                }
            )
    return gaps


def validate_hourly_candles(candles: List[Candle], min_candles: int) -> List[Dict[str, Any]]:
    """Fail closed on insufficient, invalid, misaligned, unordered, duplicate or gapped data."""
    if not candles:
        raise DataUnavailableError("The data provider returned no valid candles")
    if len(candles) < min_candles:
        raise DataUnavailableError(
            f"Insufficient hourly history: {len(candles)} candles; at least {min_candles} required"
        )

    seen = set()
    previous_timestamp: Optional[int] = None
    for candle in candles:
        if not isinstance(candle.timestamp, int) or candle.timestamp < 0:
            raise DataUnavailableError("Candle timestamps must be nonnegative integer milliseconds")
        if candle.timestamp % HOUR_MS != 0:
            raise DataUnavailableError(
                f"Misaligned hourly candle timestamp: {candle.timestamp}"
            )
        if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
            reason = "duplicate" if candle.timestamp in seen else "out-of-order"
            raise DataUnavailableError(f"{reason} candle timestamp: {candle.timestamp}")
        seen.add(candle.timestamp)
        previous_timestamp = candle.timestamp

        values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if not all(math.isfinite(value) for value in values) or not candle.validate():
            raise DataUnavailableError(
                f"Invalid OHLCV values at timestamp {candle.timestamp}"
            )

    gaps = detect_gaps(candles)
    if gaps:
        first_gap = gaps[0]
        raise DataUnavailableError(
            "Unapproved hourly data gap: "
            f"{first_gap['missing_candles']} missing candle(s) between "
            f"{first_gap['gap_start']} and {first_gap['gap_end']}"
        )

    expected_count = (candles[-1].timestamp - candles[0].timestamp) // HOUR_MS + 1
    if expected_count != len(candles):
        raise DataUnavailableError(
            f"Hourly coverage/count mismatch: expected {expected_count}, observed {len(candles)}"
        )
    return gaps


def _canonical_candle_row(candle: Candle) -> str:
    fields = [
        str(int(candle.timestamp)),
        format(float(candle.open), ".17g"),
        format(float(candle.high), ".17g"),
        format(float(candle.low), ".17g"),
        format(float(candle.close), ".17g"),
        format(float(candle.volume), ".17g"),
    ]
    return ",".join(fields) + "\n"


def _serialize_dataset(candles: List[Candle]) -> str:
    return DATASET_HEADER + "".join(_canonical_candle_row(candle) for candle in candles)


def compute_content_hash(candles: List[Candle]) -> str:
    """Compute SHA-256 over the canonical, round-trip-safe CSV representation."""
    return hashlib.sha256(_serialize_dataset(candles).encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.",
            suffix=".tmp", delete=False, newline=""
        ) as handle:
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Directory fsync is not supported on all filesystems. The file itself was fsynced.
            pass
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _new_manifest(spec: Dict[str, Any]) -> Dict[str, Any]:
    data_spec = spec.get("data", {})
    return {
        "protocol_version": spec.get("protocol_version", "unknown"),
        "specification_hash": spec.get("specification_hash"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": {
            "provider": "binance",
            "endpoint": BINANCE_KLINES_ENDPOINT,
            "interval": "1h",
            "retrieval_timestamp_utc": None,
            "rate_limit_per_minute": DataFetcher.RATE_LIMIT_PER_MINUTE,
            "max_retries": data_spec.get("max_retries", 3),
            "backoff_seconds": data_spec.get("backoff_seconds", 5),
        },
        "assets": {},
        "content_hashes": {},
        "invalidated_prior_entries": {},
        "notes": (
            "Each accepted asset references an immutable canonical hourly CSV dataset. "
            "Synthetic records are retained only as invalidated forensic evidence."
        ),
    }


def _read_manifest_file(path: Path, spec: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return _new_manifest(spec)
    try:
        with path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DataUnavailableError(f"Cannot read data manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets", {}), dict):
        raise DataUnavailableError(f"Invalid data manifest structure in {path}")
    manifest.setdefault("assets", {})
    manifest.setdefault("content_hashes", {})
    return manifest


def update_data_manifest(
    asset: str,
    candles: List[Candle],
    gaps: List[Dict[str, Any]],
    rejected: int,
    fetch_count: int,
    fallback_used: bool = False,
    fallback_source: str = "",
    dataset_path: Optional[str] = None,
    manifest_path: str = "research/data_manifest.json",
    specification_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomically record provenance, coverage and hashes; do not swallow persistence errors."""
    spec = load_research_spec()
    path = Path(manifest_path)
    manifest = _read_manifest_file(path, spec)
    retrieval_time = datetime.now(timezone.utc).isoformat()
    first_ts = candles[0].timestamp if candles else None
    last_ts = candles[-1].timestamp if candles else None
    expected_count = (
        (last_ts - first_ts) // HOUR_MS + 1
        if first_ts is not None and last_ts is not None
        else None
    )
    content_hash = compute_content_hash(candles)

    entry = {
        "symbol": asset,
        "provider": "synthetic" if fallback_used else "binance",
        "endpoint": None if fallback_used else BINANCE_KLINES_ENDPOINT,
        "interval": "1h",
        "specification_hash": specification_hash or spec.get("specification_hash"),
        "retrieval_timestamp_utc": retrieval_time,
        "first_candle_timestamp": first_ts,
        "last_candle_timestamp": last_ts,
        "expected_candle_count": expected_count,
        "observed_candle_count": len(candles),
        "gaps": gaps,
        "rejected_rows": rejected,
        "download_attempts": fetch_count,
        "fallback_used": bool(fallback_used),
        "fallback_source": fallback_source if fallback_used else "",
        "content_hash": content_hash,
        "hash_algorithm": DATASET_HASH_ALGORITHM,
        "dataset_path": dataset_path,
    }

    previous = manifest.get("assets", {}).get(asset)
    if previous and previous.get("content_hash") != content_hash:
        archived = manifest.setdefault("invalidated_prior_entries", {})
        archived.setdefault(asset, []).append(previous)
    manifest["assets"][asset] = entry
    manifest.setdefault("content_hashes", {})[asset] = content_hash
    manifest["protocol_version"] = spec.get("protocol_version", manifest.get("protocol_version"))
    manifest["specification_hash"] = specification_hash or spec.get("specification_hash")
    manifest.setdefault("data_source", {})
    manifest["data_source"].update(
        {
            "provider": "binance" if not fallback_used else "synthetic",
            "endpoint": BINANCE_KLINES_ENDPOINT if not fallback_used else None,
            "interval": "1h",
            "retrieval_timestamp_utc": retrieval_time,
            "rate_limit_per_minute": DataFetcher.RATE_LIMIT_PER_MINUTE,
        }
    )
    manifest["retrieval_timestamp_utc"] = retrieval_time
    _atomic_write_json(path, manifest)
    return entry


def _required_hourly_candles(spec: Dict[str, Any]) -> int:
    interval = spec.get("data", {}).get("interval")
    if interval != "1h":
        raise DataUnavailableError(
            f"This research implementation requires the frozen 1h interval, got {interval!r}"
        )
    try:
        history_years = float(spec["universe"]["min_history_years"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataUnavailableError("Research spec lacks a valid min_history_years value") from exc
    if not math.isfinite(history_years) or history_years <= 0:
        raise DataUnavailableError("min_history_years must be a finite positive number")
    return int(math.ceil(history_years * 365 * 24))


def _read_dataset(path: Path) -> List[Candle]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataUnavailableError(f"Cannot read verified candle dataset {path}: {exc}") from exc
    if not content.startswith(DATASET_HEADER):
        raise DataUnavailableError(f"Unexpected or noncanonical CSV header in {path}")

    candles: List[Candle] = []
    for line_number, line in enumerate(content[len(DATASET_HEADER):].splitlines(), start=2):
        fields = line.split(",")
        if len(fields) != 6:
            raise DataUnavailableError(f"Malformed candle dataset row {line_number} in {path}")
        try:
            candles.append(
                Candle(
                    timestamp=int(fields[0]),
                    open=float(fields[1]),
                    high=float(fields[2]),
                    low=float(fields[3]),
                    close=float(fields[4]),
                    volume=float(fields[5]),
                )
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise DataUnavailableError(
                f"Malformed candle dataset value on row {line_number} in {path}"
            ) from exc
    if _serialize_dataset(candles) != content:
        raise DataUnavailableError(f"Dataset is not canonically serialized: {path}")
    return candles


def _verified_cache(
    symbol: str,
    min_candles: int,
    spec: Dict[str, Any],
    manifest_path: Path,
    data_dir: Path,
) -> Optional[List[Candle]]:
    manifest = _read_manifest_file(manifest_path, spec)
    entry = manifest.get("assets", {}).get(symbol)
    if not entry:
        return None

    # Old synthetic records are not caches. They are archived when real data replaces them.
    if entry.get("fallback_used") is True or entry.get("fallback_source") == "synthetic" or entry.get("provider") == "synthetic":
        return None

    expected_spec_hash = spec.get("specification_hash")
    if entry.get("provider") != "binance" or entry.get("endpoint") != BINANCE_KLINES_ENDPOINT:
        raise DataUnavailableError(
            f"Unapproved or ambiguous data provider in cache manifest for {symbol}"
        )
    if entry.get("interval") != "1h" or entry.get("specification_hash") != expected_spec_hash:
        raise DataUnavailableError(
            f"Cached data contract/specification mismatch for {symbol}; refusing unverified cache"
        )
    if entry.get("hash_algorithm") != DATASET_HASH_ALGORITHM or not entry.get("dataset_path"):
        raise DataUnavailableError(
            f"Cached data for {symbol} lacks the required dataset path/hash algorithm"
        )

    stored_path = Path(str(entry["dataset_path"]))
    resolved_path = stored_path if stored_path.is_absolute() else (Path.cwd() / stored_path)
    resolved_path = resolved_path.resolve()
    if not resolved_path.is_relative_to(data_dir.resolve()):
        raise DataUnavailableError(f"Manifest dataset path escapes the approved data directory for {symbol}")
    if not resolved_path.is_file():
        raise DataUnavailableError(
            f"Manifest references missing dataset {resolved_path} for {symbol}; restore/retrieve explicitly"
        )

    candles = _read_dataset(resolved_path)
    validate_hourly_candles(candles, min_candles)
    actual_hash = compute_content_hash(candles)
    if entry.get("content_hash") != actual_hash:
        raise DataUnavailableError(f"Cached data hash mismatch for {symbol}")
    if manifest.get("content_hashes", {}).get(symbol) != actual_hash:
        raise DataUnavailableError(f"Top-level manifest hash mismatch for {symbol}")
    if entry.get("observed_candle_count") != len(candles):
        raise DataUnavailableError(f"Cached candle count mismatch for {symbol}")
    if entry.get("first_candle_timestamp") != candles[0].timestamp:
        raise DataUnavailableError(f"Cached first timestamp mismatch for {symbol}")
    if entry.get("last_candle_timestamp") != candles[-1].timestamp:
        raise DataUnavailableError(f"Cached last timestamp mismatch for {symbol}")
    return candles


def load_or_fetch_asset_data(
    symbol: str,
    min_candles: Optional[int] = None,
    *,
    data_dir: str = "research/data/candles",
    manifest_path: str = "research/data_manifest.json",
) -> List[Candle]:
    """Load a hash-verified real-data cache or fetch genuine Binance hourly history.

    A caller-provided lower candle count can never weaken the frozen research requirement.
    Synthetic data is deliberately not available through this campaign-facing function.
    """
    if not re.fullmatch(r"[A-Z0-9]{1,30}", symbol):
        raise DataUnavailableError(f"Invalid Binance symbol: {symbol!r}")

    spec = load_research_spec()
    protocol_minimum = _required_hourly_candles(spec)
    if min_candles is not None and (not isinstance(min_candles, int) or min_candles < 1):
        raise DataUnavailableError("min_candles must be a positive integer when supplied")
    required_count = max(protocol_minimum, min_candles or protocol_minimum)

    dataset_root = Path(data_dir)
    manifest_file = Path(manifest_path)
    try:
        cached = _verified_cache(
            symbol,
            required_count,
            spec,
            manifest_file,
            dataset_root,
        )
    except DataUnavailableError:
        # An existing cache claiming real provenance but failing integrity checks is not silently
        # refreshed: masking it could mix different data snapshots within a research run.
        raise
    if cached is not None:
        return cached

    latest_closed_open = (int(time.time() * 1000) // HOUR_MS - 1) * HOUR_MS
    first_open = latest_closed_open - (required_count - 1) * HOUR_MS
    fetcher = DataFetcher()
    try:
        candles, rejected_rows, request_count = fetcher.fetch_full_history(
            symbol,
            interval="1h",
            start_time=first_open,
            end_time=latest_closed_open,
        )
    except Exception as exc:
        raise DataUnavailableError(
            f"Real Binance history unavailable for {symbol}; synthetic fallback is prohibited: {exc}"
        ) from exc

    if rejected_rows:
        raise DataUnavailableError(
            f"Binance returned {rejected_rows} invalid OHLCV row(s) for {symbol}; refusing partial data"
        )
    gaps = validate_hourly_candles(candles, required_count)
    if len(candles) != required_count:
        raise DataUnavailableError(
            f"Binance range count mismatch for {symbol}: expected exactly {required_count}, got {len(candles)}"
        )
    if candles[0].timestamp != first_open or candles[-1].timestamp != latest_closed_open:
        raise DataUnavailableError(
            f"Binance history does not cover the requested complete closed-hour range for {symbol}"
        )

    content = _serialize_dataset(candles)
    content_hash = compute_content_hash(candles)
    dataset_root.mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_1h_{content_hash[:16]}.csv"
    dataset_file = dataset_root / filename
    if dataset_file.exists():
        existing = dataset_file.read_text(encoding="utf-8")
        if existing != content:
            raise DataUnavailableError(
                f"Content-addressed data file unexpectedly differs for {symbol}; refusing overwrite"
            )
    else:
        _atomic_write_text(dataset_file, content)

    try:
        stored_dataset_path = str(dataset_file)
        if not dataset_file.is_absolute():
            stored_dataset_path = dataset_file.as_posix()
        update_data_manifest(
            symbol,
            candles,
            gaps,
            rejected_rows,
            request_count,
            fallback_used=False,
            fallback_source="",
            dataset_path=stored_dataset_path,
            manifest_path=str(manifest_file),
            specification_hash=spec.get("specification_hash"),
        )
    except Exception as exc:
        raise DataUnavailableError(
            f"Downloaded candles for {symbol}, but provenance manifest could not be persisted: {exc}"
        ) from exc
    return candles

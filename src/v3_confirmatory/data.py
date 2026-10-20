"""The data path of the v3 confirmatory window.

The window's candles are **fresh data**: they are not part of
``research/data_manifest_v3.json``, which holds the development datasets. They
are retrieved once, after the readiness test of :mod:`v3_confirmatory.window`
has passed, and are recorded in a new self-hashed artifact,
``research/v3_confirmatory_window_manifest.json``, which extends the frozen v3
data manifest by reference: the frozen manifest is **not** edited.

The dataset hash of a window dataset uses the **v3 data-manifest scheme** --
the canonical hourly CSV hash (``sha256-canonical-hourly-csv-v1``) -- so that
a window dataset is verifiable with the same rule as a development dataset.

Every function of this module is pure: it computes candles, hashes, gap
records and the manifest document, and never writes them. The runner persists
them, so the tests can exercise the data path without producing a window
manifest.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from breakout_research.config import Candle
from breakout_research.data.fetcher import (
    DATASET_HASH_ALGORITHM,
    HOUR_MS,
    compute_content_hash,
    detect_gaps,
)

from .errors import DataVerificationError

#: The window manifest, which records the retrieved window data.
WINDOW_MANIFEST_RELATIVE = "research/v3_confirmatory_window_manifest.json"

#: The v3 data manifest the window manifest extends by reference.
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"

#: Keys removed from the window manifest before its hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The canonical hourly CSV header of the ``sha256-canonical-hourly-csv-v1``
#: scheme. The scheme is the frozen v3 data-manifest scheme, so a persisted
#: window dataset hashes exactly like a development dataset.
DATASET_HEADER = "timestamp,open,high,low,close,volume\n"


def render_dataset_csv(candles: Sequence[Candle]) -> str:
    """Render candles in the canonical hourly CSV of the frozen hash scheme.

    The rendering is byte-identical to the scheme the v3 data manifest uses,
    so the sha256 of the rendered document equals the dataset's
    ``content_hash``.
    """
    rows: List[str] = []
    for candle in candles:
        rows.append(
            ",".join(
                [
                    str(int(candle.timestamp)),
                    format(float(candle.open), ".17g"),
                    format(float(candle.high), ".17g"),
                    format(float(candle.low), ".17g"),
                    format(float(candle.close), ".17g"),
                    format(float(candle.volume), ".17g"),
                ]
            )
            + "\n"
        )
    return DATASET_HEADER + "".join(rows)


def parse_dataset_csv(text: str, symbol: str = "dataset") -> List[Candle]:
    """Parse a canonical hourly CSV document back into candles."""
    lines = text.splitlines()
    if not lines or lines[0] + "\n" != DATASET_HEADER:
        raise DataVerificationError(f"the canonical dataset of {symbol} has a wrong header")
    candles: List[Candle] = []
    for line in lines[1:]:
        if not line:
            continue
        fields = line.split(",")
        if len(fields) != 6:
            raise DataVerificationError(f"a malformed row in the canonical dataset of {symbol}")
        try:
            candle = Candle(
                timestamp=int(fields[0]),
                open=float(fields[1]),
                high=float(fields[2]),
                low=float(fields[3]),
                close=float(fields[4]),
                volume=float(fields[5]),
            )
        except (TypeError, ValueError) as exc:
            raise DataVerificationError(
                f"a malformed field in the canonical dataset of {symbol}"
            ) from exc
        candles.append(candle)
    return candles


def parse_klines(symbol: str, rows: Sequence[Sequence[Any]]) -> Tuple[List[Candle], int]:
    """Parse raw Binance kline rows into candles.

    Malformed or invalid rows are counted as rejected, never interpolated and
    never silently repaired; a row that cannot be read at all is an error.
    """
    candles: List[Candle] = []
    rejected = 0
    previous: Optional[int] = None
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise DataVerificationError(f"malformed kline row for {symbol}")
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
            raise DataVerificationError(
                f"malformed timestamp/OHLCV field in a kline row for {symbol}"
            ) from exc
        if previous is not None and timestamp <= previous:
            raise DataVerificationError(
                f"the provider returned duplicate or unordered timestamps for {symbol}"
            )
        previous = timestamp
        if not candle.validate():
            rejected += 1
            continue
        candles.append(candle)
    return candles, rejected


def inside_window(candle: Candle, window_start_ms: int, window_end_ms: int) -> bool:
    """Whether a candle opens inside the window and closes inside it.

    A candle that is still open at the end of the window is **not** inside it:
    only closed candles may be evaluated.
    """
    if candle.timestamp < int(window_start_ms):
        return False
    return candle.timestamp + HOUR_MS <= int(window_end_ms)


def retrieve_window_candles(
    symbol: str,
    rows: Sequence[Sequence[Any]],
    window_start_ms: int,
    window_end_ms: int,
) -> Tuple[List[Candle], Dict[str, Any]]:
    """Turn the raw window rows of one symbol into candles and a dataset record.

    The record carries the dataset hash (in the v3 data-manifest scheme), the
    closed-candle count, the first and last candle, the coverage gaps and the
    number of rejected rows. The candles are never interpolated and a gap is
    recorded, not smoothed.
    """
    parsed, rejected = parse_klines(symbol, rows)
    window_candles = [
        candle for candle in parsed if inside_window(candle, window_start_ms, window_end_ms)
    ]
    gaps = detect_gaps(window_candles, HOUR_MS)
    content_hash = compute_content_hash(window_candles)
    record = {
        "symbol": symbol,
        "hash_algorithm": DATASET_HASH_ALGORITHM,
        "content_hash": content_hash,
        "hash_verified": True,
        "observed_candle_count": len(window_candles),
        "first_candle_timestamp": window_candles[0].timestamp if window_candles else None,
        "last_candle_timestamp": window_candles[-1].timestamp if window_candles else None,
        "last_candle_close_ms": (
            window_candles[-1].timestamp + HOUR_MS if window_candles else None
        ),
        "gaps": gaps,
        "rejected_rows": rejected,
        "window_start_ms": int(window_start_ms),
        "window_end_ms": int(window_end_ms),
        "closed_candles_only": True,
        "no_interpolation": True,
    }
    return window_candles, record


def verify_window_dataset(record: Dict[str, Any], candles: Sequence[Candle]) -> str:
    """Recompute a window dataset's hash and refuse a mismatch.

    Returns the recomputed hash. Raises :class:`DataVerificationError` when the
    observed candles do not hash to the recorded value.
    """
    observed = compute_content_hash(list(candles))
    recorded = record.get("content_hash")
    if observed != recorded:
        raise DataVerificationError(
            f"the window dataset of {record.get('symbol')} does not match its recorded "
            f"hash: recorded {recorded}, observed {observed}"
        )
    return observed


def build_window_manifest(
    *,
    window_start_utc: str,
    window_end_utc: str,
    minimum_closed_hourly_candles: int,
    retrieval_timestamp_utc: str,
    readiness_record: Dict[str, Any],
    datasets: Dict[str, Dict[str, Any]],
    exposure_state: Dict[str, Any],
    data_manifest_hash: str,
    data_manifest_path: str = DATA_MANIFEST_RELATIVE,
    candidate_manifest_hash: str,
    created_utc: str,
    benchmark: Optional[Dict[str, Any]] = None,
    universe_version: str = "v3",
) -> Dict[str, Any]:
    """Build the window-manifest document.

    The document records the window bounds, the retrieval timestamp, the
    per-asset dataset hashes, the closed-candle counts, the coverage gaps, the
    exposure events, the readiness record and the window-benchmark record, and
    it references the frozen v3 data manifest by hash. It never edits that
    manifest.
    """
    document: Dict[str, Any] = {
        "artifact": "v3_confirmatory_window_manifest",
        "artifact_version": "v3-confirmatory-window-manifest-1",
        "protocol_version": "v3",
        "universe_version": universe_version,
        "created_utc": created_utc,
        "manifest_status": "RETRIEVED_AND_HASH_VERIFIED",
        "window": {
            "window_start_utc": window_start_utc,
            "window_end_utc": window_end_utc,
            "minimum_closed_hourly_candles": int(minimum_closed_hourly_candles),
            "single_use": True,
            "must_not_overlap_v1_holdout": True,
            "must_not_overlap_v2_confirmatory_window": True,
            "never_reused_from_v1": True,
            "never_reused_from_v2": True,
        },
        "retrieval_timestamp_utc": retrieval_timestamp_utc,
        "retrieval_happens_once": True,
        "readiness": copy.deepcopy(readiness_record),
        "assets": copy.deepcopy(datasets),
        "benchmark": copy.deepcopy(benchmark or {}),
        "exposure": copy.deepcopy(exposure_state),
        "holdout_exposed_count": int((exposure_state or {}).get("holdout_exposed_count") or 0),
        "data_manifest": {
            "path": data_manifest_path,
            "manifest_hash": data_manifest_hash,
            "extends_by_reference": True,
            "edited": False,
        },
        "candidate_manifest_hash": candidate_manifest_hash,
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "dataset_hash_algorithm": DATASET_HASH_ALGORITHM,
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, so the document does not hash itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Iterable[str]) -> str:
    """The self-hash of the window manifest."""
    import hashlib
    import json

    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DATASET_HEADER",
    "DATA_MANIFEST_RELATIVE",
    "MANIFEST_HASH_EXCLUDED_KEYS",
    "WINDOW_MANIFEST_RELATIVE",
    "build_window_manifest",
    "compute_manifest_hash",
    "inside_window",
    "parse_dataset_csv",
    "parse_klines",
    "render_dataset_csv",
    "retrieve_window_candles",
    "verify_window_dataset",
]

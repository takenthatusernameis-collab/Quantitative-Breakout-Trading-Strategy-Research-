"""Development-data access for the v2 selection run.

The v2 selection run may read **development data only**: candles that close at
or before the confirmatory-window start recorded by the frozen candidate
manifest. Every dataset is verified against the hash-bound v2 data manifest
before it is used, and the confirmatory-window boundary is enforced twice:

* once *before* the dataset file is read, against the last timestamp the
  manifest declares, and
* once *after* the dataset is read, against every candle it contains.

A dataset that reaches into the confirmatory window is refused; the run never
trims such a dataset silently and never reads it partially. The loader
performs no provider request at all: it reads the immutable local datasets
that the v2 data manifest already binds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from breakout_research.baselines import load_verified_candles
from breakout_research.config import Candle
from breakout_research.data.fetcher import DATASET_HASH_ALGORITHM, HOUR_MS

from .errors import ConfirmatoryWindowViolation, DataVerificationError


def parse_utc_ms(value: str) -> int:
    """Parse an ISO-8601 UTC instant into milliseconds since the epoch."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def candle_close_ms(candle: Candle) -> int:
    """The instant at which a hourly candle closes."""
    return int(candle.timestamp) + HOUR_MS


def load_development_candles(
    repo_root: Path,
    symbol: str,
    data_manifest: Dict[str, Any],
    boundary_ms: int,
) -> Tuple[List[Candle], Dict[str, Any]]:
    """Load one asset's verified candles, refusing any confirmatory exposure.

    Returns the candles and a provenance summary. Raises
    :class:`ConfirmatoryWindowViolation` when the dataset reaches into the
    confirmatory window and :class:`DataVerificationError` when the dataset is
    missing, unverified or inconsistent with the v2 data manifest.
    """
    entry = (data_manifest.get("assets") or {}).get(symbol)
    if entry is None:
        raise DataVerificationError(f"{symbol} is not present in the v2 data manifest")
    if entry.get("validated") is not True:
        raise DataVerificationError(f"{symbol} is not a validated constituent of the v2 universe")
    if entry.get("interval") != "1h":
        raise DataVerificationError(f"{symbol} does not carry the frozen 1h interval")
    if entry.get("hash_algorithm") != DATASET_HASH_ALGORITHM:
        raise DataVerificationError(f"{symbol} does not use the canonical hourly CSV hash algorithm")
    if entry.get("gaps") != [] or entry.get("rejected_rows") != 0:
        raise DataVerificationError(f"{symbol} reports coverage gaps or rejected rows")

    declared_last = entry.get("last_candle_timestamp")
    if not isinstance(declared_last, int):
        raise DataVerificationError(f"{symbol} declares no last candle timestamp")
    if declared_last + HOUR_MS > boundary_ms:
        raise ConfirmatoryWindowViolation(
            f"the dataset of {symbol} declares a last candle that closes inside the "
            f"confirmatory window (closes at {declared_last + HOUR_MS} > {boundary_ms}); "
            "the dataset is not read"
        )

    candles, provenance = load_verified_candles(symbol, data_manifest, Path(repo_root))
    if not candles:
        raise DataVerificationError(f"{symbol} has no candles")
    for candle in candles:
        if candle_close_ms(candle) > boundary_ms:
            raise ConfirmatoryWindowViolation(
                f"the dataset of {symbol} contains a candle that closes inside the "
                f"confirmatory window (closes at {candle_close_ms(candle)} > {boundary_ms})"
            )
    if entry.get("observed_candle_count") != len(candles):
        raise DataVerificationError(f"{symbol} candle count differs from the data manifest")
    if entry.get("first_candle_timestamp") != candles[0].timestamp:
        raise DataVerificationError(f"{symbol} first candle differs from the data manifest")
    if candles[-1].timestamp != declared_last:
        raise DataVerificationError(f"{symbol} last candle differs from the data manifest")
    content_hash = provenance.get("content_hash")
    declared_hash = (data_manifest.get("content_hashes") or {}).get(symbol)
    if declared_hash != content_hash:
        raise DataVerificationError(f"{symbol} content hash differs from the v2 data manifest")

    summary = {
        "asset": symbol,
        "dataset_path": provenance.get("dataset_path"),
        "content_hash": content_hash,
        "hash_verified": True,
        "candle_count": len(candles),
        "first_candle_timestamp": int(candles[0].timestamp),
        "last_candle_timestamp": int(candles[-1].timestamp),
        "last_candle_close_ms": candle_close_ms(candles[-1]),
        "development_boundary_ms": int(boundary_ms),
        "confirmatory_candles_read": 0,
    }
    return candles, summary


__all__ = [
    "candle_close_ms",
    "load_development_candles",
    "parse_utc_ms",
]

"""Development-data access for the v4 selection run.

The v4 selection run may read **development data only**: candles that close at
or before the confirmatory-window start recorded by the frozen candidate set.
Every dataset is verified against the **effective** v4 data manifest -- the
base manifest, since v4 publishes no separate data-manifest amendment --
before it is used, and the confirmatory-window boundary is enforced twice:

* once *before* the dataset file is read, against the last timestamp the
  manifest declares, and
* once *after* the dataset is read, against every candle it contains.

A dataset that reaches into the confirmatory window is refused; the run never
trims such a dataset silently and never reads it partially. The loader
performs no provider request at all: it reads the immutable local datasets
that the effective data manifest binds.

The v4 data manifest does not carry a BTCUSDT benchmark entry. The benchmark
dataset is referenced directly from the v3 data area (immutable historical
data), outside the v4 data-manifest identity. It is therefore read directly
and verified against its recorded content hash, and not through the
manifest-driven loader, which resolves a dataset through a manifest entry the
v4 manifest deliberately does not publish.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from breakout_research.baselines import load_verified_candles
from breakout_research.config import Candle
from breakout_research.data.fetcher import (
    DATASET_HASH_ALGORITHM,
    HOUR_MS,
    _read_dataset,
    compute_content_hash,
)

from .errors import ConfirmatoryWindowViolation, DataVerificationError

DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
BENCHMARK_SYMBOL = "BTCUSDT"

#: Benchmark dataset referenced from v3 data (immutable, outside the v4 manifest).
BENCHMARK_DATASET_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"
BENCHMARK_CONTENT_HASH = "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"
BENCHMARK_FIRST_CANDLE = 1697886000000
BENCHMARK_LAST_CANDLE = 1792490400000
BENCHMARK_CANDLE_COUNT = 26280


def parse_utc_ms(value: str) -> int:
    """Parse an ISO-8601 UTC instant into milliseconds since the epoch."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = ("manifest_hash",)) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_effective_data_manifest(repo_root: Path) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """The effective v4 data manifest, recomputed from the repository.

    v4 publishes no data-manifest amendment, so the effective manifest is the
    base manifest alone. Its identity is recomputed; a manifest that does not
    recompute is refused rather than used.
    """
    root = Path(repo_root)
    base = read_json(root / DATA_MANIFEST_RELATIVE)

    excluded = tuple((base.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    declared = base.get("manifest_hash")
    if compute_manifest_hash(base, excluded) != declared:
        raise DataVerificationError(
            "the v4 base data manifest does not recompute its own manifest_hash"
        )

    manifest = copy.deepcopy(base)
    provenance = {
        "base_manifest_path": DATA_MANIFEST_RELATIVE,
        "base_manifest_hash": base.get("manifest_hash"),
        "effective_data_manifest_hash": declared,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_content_hash": BENCHMARK_CONTENT_HASH,
        "benchmark_dataset_path": BENCHMARK_DATASET_PATH,
        "benchmark_external_to_manifest": True,
    }
    return manifest, declared, provenance


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
    missing, unverified or inconsistent with the effective data manifest.
    """
    entry = (data_manifest.get("assets") or {}).get(symbol)
    if entry is None:
        raise DataVerificationError(f"{symbol} is not present in the effective v4 data manifest")
    if entry.get("validated") is not True:
        raise DataVerificationError(f"{symbol} is not a validated dataset of the v4 universe")
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
        if int(candle.timestamp) + HOUR_MS > boundary_ms:
            raise ConfirmatoryWindowViolation(
                f"the dataset of {symbol} contains a candle that closes inside the "
                f"confirmatory window (closes at {int(candle.timestamp) + HOUR_MS} > "
                f"{boundary_ms})"
            )
    if entry.get("observed_candle_count") != len(candles):
        raise DataVerificationError(f"{symbol} candle count differs from the data manifest")
    if entry.get("first_candle_timestamp") != int(candles[0].timestamp):
        raise DataVerificationError(f"{symbol} first candle differs from the data manifest")
    if int(candles[-1].timestamp) != declared_last:
        raise DataVerificationError(f"{symbol} last candle differs from the data manifest")
    content_hash = provenance.get("content_hash")
    declared_hash = (data_manifest.get("content_hashes") or {}).get(symbol)
    if declared_hash != content_hash:
        raise DataVerificationError(f"{symbol} content hash differs from the data manifest")

    summary = {
        "asset": symbol,
        "dataset_path": provenance.get("dataset_path"),
        "content_hash": content_hash,
        "hash_verified": True,
        "candle_count": len(candles),
        "first_candle_timestamp": int(candles[0].timestamp),
        "last_candle_timestamp": int(candles[-1].timestamp),
        "last_candle_close_ms": int(candles[-1].timestamp) + HOUR_MS,
        "development_boundary_ms": int(boundary_ms),
        "confirmatory_candles_read": 0,
    }
    return candles, summary


def load_benchmark_candles(repo_root: Path,
                           data_manifest: Dict[str, Any],
                           boundary_ms: int) -> Tuple[List[Candle], Dict[str, Any]]:
    """Load the BTCUSDT benchmark candles, refusing any confirmatory exposure.

    The benchmark dataset lives outside the v4 data manifest (v4 publishes no
    benchmark entry). It is referenced directly from the v3 data area, which is
    immutable historical data. The dataset is hash-verified against the
    recorded content hash and checked against the confirmatory boundary exactly
    like an asset dataset.

    The dataset is read directly and verified against the recorded content
    hash, **not** through ``load_verified_candles``: that loader resolves the
    dataset through a ``data_manifest`` entry, and the v4 data manifest
    deliberately publishes no BTCUSDT entry -- the benchmark is external to the
    v4 data-manifest identity by design (see the authorization's residual
    limitation RL2). The verification is the one the manifest-driven loader
    performs: the canonical hourly-CSV content hash of the parsed dataset must
    equal the recorded hash. For this dataset the recorded hash is also the
    sha256 of the file bytes, so both digests are checked.
    """
    dataset_path = Path(repo_root) / BENCHMARK_DATASET_PATH
    if not dataset_path.exists():
        raise DataVerificationError(
            f"the benchmark dataset {BENCHMARK_DATASET_PATH} does not exist"
        )
    content_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    if content_hash != BENCHMARK_CONTENT_HASH:
        raise DataVerificationError(
            f"the benchmark dataset content hash does not match the recorded hash: "
            f"recorded {BENCHMARK_CONTENT_HASH}, computed {content_hash}"
        )
    if BENCHMARK_LAST_CANDLE + HOUR_MS > boundary_ms:
        raise ConfirmatoryWindowViolation(
            f"the benchmark dataset declares a last candle that closes inside the "
            f"confirmatory window (closes at {BENCHMARK_LAST_CANDLE + HOUR_MS} > "
            f"{boundary_ms}); the dataset is not read"
        )

    candles = _read_dataset(dataset_path)
    if not candles:
        raise DataVerificationError("the benchmark dataset has no candles")
    canonical_hash = compute_content_hash(candles)
    if canonical_hash != BENCHMARK_CONTENT_HASH:
        raise DataVerificationError(
            f"the benchmark dataset canonical content hash does not match the recorded "
            f"hash: recorded {BENCHMARK_CONTENT_HASH}, computed {canonical_hash}"
        )
    for candle in candles:
        if int(candle.timestamp) + HOUR_MS > boundary_ms:
            raise ConfirmatoryWindowViolation(
                f"the benchmark dataset contains a candle that closes inside the "
                f"confirmatory window (closes at {int(candle.timestamp) + HOUR_MS} > "
                f"{boundary_ms})"
            )
    if int(candles[0].timestamp) != BENCHMARK_FIRST_CANDLE:
        raise DataVerificationError(
            "the benchmark dataset first candle differs from the recorded value"
        )
    if int(candles[-1].timestamp) != BENCHMARK_LAST_CANDLE:
        raise DataVerificationError(
            "the benchmark dataset last candle differs from the recorded value"
        )
    if BENCHMARK_CANDLE_COUNT != len(candles):
        raise DataVerificationError(
            "the benchmark dataset candle count differs from the recorded value"
        )

    summary = {
        "asset": BENCHMARK_SYMBOL,
        "dataset_path": BENCHMARK_DATASET_PATH,
        "content_hash": content_hash,
        "canonical_content_hash": canonical_hash,
        "hash_verified": True,
        "candle_count": len(candles),
        "first_candle_timestamp": int(candles[0].timestamp),
        "last_candle_timestamp": int(candles[-1].timestamp),
        "last_candle_close_ms": int(candles[-1].timestamp) + HOUR_MS,
        "development_boundary_ms": int(boundary_ms),
        "confirmatory_candles_read": 0,
        "external_to_v4_manifest": True,
    }
    return candles, summary


__all__ = [
    "BENCHMARK_CONTENT_HASH",
    "BENCHMARK_DATASET_PATH",
    "BENCHMARK_FIRST_CANDLE",
    "BENCHMARK_LAST_CANDLE",
    "BENCHMARK_SYMBOL",
    "DATA_MANIFEST_RELATIVE",
    "canonical",
    "compute_manifest_hash",
    "candle_close_ms",
    "load_benchmark_candles",
    "load_development_candles",
    "parse_utc_ms",
    "read_json",
    "resolve_effective_data_manifest",
]

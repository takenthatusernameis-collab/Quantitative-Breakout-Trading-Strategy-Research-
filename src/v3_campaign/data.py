"""Development-data access for the v3 selection run.

The v3 selection run may read **development data only**: candles that close at
or before the confirmatory-window start recorded by the frozen candidate set.
Every dataset is verified against the **effective** v3 data manifest -- the
base manifest plus the benchmark entry published by
``configs/research_v3_data_manifest_amendment_1.json`` -- before it is used,
and the confirmatory-window boundary is enforced twice:

* once *before* the dataset file is read, against the last timestamp the
  manifest declares, and
* once *after* the dataset is read, against every candle it contains.

A dataset that reaches into the confirmatory window is refused; the run never
trims such a dataset silently and never reads it partially. The loader
performs no provider request at all: it reads the immutable local datasets
that the effective data manifest binds.
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
from breakout_research.data.fetcher import DATASET_HASH_ALGORITHM, HOUR_MS

from .errors import ConfirmatoryWindowViolation, DataVerificationError

DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
DATA_AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
BENCHMARK_SYMBOL = "BTCUSDT"


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


def effective_data_manifest(base: Dict[str, Any], entry: Dict[str, Any],
                            source: str) -> Dict[str, Any]:
    """The base data manifest plus the published benchmark entry."""
    body = copy.deepcopy(base)
    body.pop("manifest_hash", None)
    snapshot = body.get("snapshot_identity")
    if isinstance(snapshot, dict):
        snapshot.pop("data_manifest_hash", None)
    body.setdefault("assets", {})[BENCHMARK_SYMBOL] = copy.deepcopy(entry)
    body.setdefault("content_hashes", {})[BENCHMARK_SYMBOL] = entry["content_hash"]
    body["benchmark_asset"] = {
        "symbol": BENCHMARK_SYMBOL,
        "role": "trend_filter_and_benchmark",
        "included_in_universe": True,
        "is_candidate": False,
        "content_hash": entry["content_hash"],
        "dataset_path": entry["dataset_path"],
        "first_candle_timestamp": entry["first_candle_timestamp"],
        "last_candle_timestamp": entry["last_candle_timestamp"],
        "observed_candle_count": entry["observed_candle_count"],
        "source": source,
        "alignment_rule": (
            "the benchmark series and the asset series are aligned by UTC candle close: "
            "both are sliced to the same fold window before the frozen engine is called, "
            "and no observation is forward-filled"
        ),
    }
    return body


def effective_data_manifest_hash(base: Dict[str, Any], entry: Dict[str, Any],
                                  source: str) -> str:
    """The identity of the effective data manifest."""
    return compute_manifest_hash(
        effective_data_manifest(base, entry, source),
        ("manifest_hash", "snapshot_identity.data_manifest_hash"),
    )


def resolve_effective_data_manifest(repo_root: Path) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """The effective v3 data manifest, recomputed from the repository.

    The base manifest and the published benchmark entry are both verified, and
    the effective identity is recomputed; a manifest that does not recompute is
    refused rather than used.
    """
    root = Path(repo_root)
    base = read_json(root / DATA_MANIFEST_RELATIVE)
    amendment = read_json(root / DATA_AMENDMENT_RELATIVE)

    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    if compute_manifest_hash(amendment, excluded) != declared:
        raise DataVerificationError(
            "the v3 data-manifest amendment does not recompute its own manifest_hash"
        )
    recorded_base_hash = (amendment.get("effective_data_manifest") or {}).get("base_manifest_hash")
    if recorded_base_hash != base.get("manifest_hash"):
        raise DataVerificationError(
            "the v3 data-manifest amendment is not bound to the current base data manifest"
        )

    entry = (amendment.get("benchmark_asset") or {}).get("entry")
    if not isinstance(entry, dict):
        raise DataVerificationError("the v3 data-manifest amendment publishes no benchmark entry")

    recomputed = effective_data_manifest_hash(base, entry, DATA_AMENDMENT_RELATIVE)
    recorded = (amendment.get("effective_data_manifest") or {}).get("effective_data_manifest_hash")
    if recorded != recomputed:
        raise DataVerificationError(
            f"the effective data-manifest identity does not recompute: recorded {recorded}, "
            f"recomputed {recomputed}"
        )

    manifest = effective_data_manifest(base, entry, DATA_AMENDMENT_RELATIVE)
    provenance = {
        "base_manifest_path": DATA_MANIFEST_RELATIVE,
        "base_manifest_hash": base.get("manifest_hash"),
        "amendment_path": DATA_AMENDMENT_RELATIVE,
        "amendment_manifest_hash": declared,
        "effective_data_manifest_hash": recomputed,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_content_hash": entry.get("content_hash"),
        "benchmark_dataset_path": entry.get("dataset_path"),
    }
    return manifest, recomputed, provenance


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
        raise DataVerificationError(f"{symbol} is not present in the effective v3 data manifest")
    if entry.get("validated") is not True:
        raise DataVerificationError(f"{symbol} is not a validated dataset of the v3 universe")
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


__all__ = [
    "BENCHMARK_SYMBOL",
    "DATA_AMENDMENT_RELATIVE",
    "DATA_MANIFEST_RELATIVE",
    "canonical",
    "compute_manifest_hash",
    "candle_close_ms",
    "effective_data_manifest",
    "effective_data_manifest_hash",
    "load_development_candles",
    "parse_utc_ms",
    "read_json",
    "resolve_effective_data_manifest",
]

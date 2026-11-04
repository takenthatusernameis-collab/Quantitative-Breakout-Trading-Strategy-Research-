"""Manifest-driven, development-only v6 candle access.

Every protected-boundary test is performed from the manifest before a candle
file is opened, then repeated against the parsed observations. No provider or
network access exists in this module.
"""
from __future__ import annotations
import copy, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from breakout_research.baselines import load_verified_candles
from breakout_research.config import Candle
from breakout_research.data.fetcher import DATASET_HASH_ALGORITHM, HOUR_MS, _read_dataset, compute_content_hash
from .errors import ConfirmatoryWindowViolation, DataVerificationError

DATA_MANIFEST_RELATIVE = "research/data_manifest_v6.json"
BENCHMARK_SYMBOL = "BTCUSDT"

def parse_utc_ms(value: str) -> int:
    text = str(value).strip()
    if text.endswith("Z"): text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {k: v for k, v in document.items() if k not in excluded_keys}
    for dotted in (k for k in excluded_keys if "." in k):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()

def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise DataVerificationError(f"{path} is not a JSON object")
    return value

def _within_root(root: Path, relative: str) -> Path:
    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents:
        raise DataVerificationError(f"dataset path escapes repository root: {relative}")
    return candidate

def resolve_effective_data_manifest(repo_root: Path) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    root = Path(repo_root)
    manifest = read_json(root / DATA_MANIFEST_RELATIVE)
    hashing = manifest.get("hashing") or {}
    excluded = tuple(hashing.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    declared = str(manifest.get("manifest_hash") or "")
    actual = compute_manifest_hash(manifest, excluded)
    if not declared or declared != actual:
        raise DataVerificationError(
            f"v6 data manifest hash mismatch: declared {declared}, recomputed {actual}"
        )
    benchmark = manifest.get("benchmark") or {}
    path = str(benchmark.get("dataset_path") or "")
    content_hash = str(benchmark.get("content_hash") or "")
    if not path or not content_hash or benchmark.get("validated") is not True:
        raise DataVerificationError("v6 data manifest does not publish a verified BTC benchmark")
    if (manifest.get("assets") or {}).get(BENCHMARK_SYMBOL) is not None:
        raise DataVerificationError("BTC benchmark is a reference series, not a candidate asset")
    provenance = {
        "base_manifest_path": DATA_MANIFEST_RELATIVE,
        "base_manifest_hash": declared,
        "effective_data_manifest_hash": declared,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_content_hash": content_hash,
        "benchmark_dataset_path": path,
        "benchmark_first_candle_timestamp": benchmark.get("first_candle_timestamp"),
        "benchmark_last_candle_timestamp": benchmark.get("last_candle_timestamp"),
        "benchmark_observed_candle_count": benchmark.get("observed_candle_count"),
        "benchmark_published_by_manifest": True,
    }
    return copy.deepcopy(manifest), declared, provenance

def load_development_candles(repo_root: Path, symbol: str,
                             data_manifest: Dict[str, Any],
                             boundary_ms: int) -> Tuple[List[Candle], Dict[str, Any]]:
    entry = (data_manifest.get("assets") or {}).get(symbol)
    if entry is None or entry.get("validated") is not True:
        raise DataVerificationError(f"{symbol} is not a validated member of the v6 data manifest")
    if entry.get("interval") != "1h" or entry.get("hash_algorithm") != DATASET_HASH_ALGORITHM:
        raise DataVerificationError(f"{symbol} does not use the frozen canonical 1h data format")
    if entry.get("gaps") != [] or entry.get("rejected_rows") != 0:
        raise DataVerificationError(f"{symbol} reports missing candles or rejected rows")
    declared_last = entry.get("last_candle_timestamp")
    if not isinstance(declared_last, int):
        raise DataVerificationError(f"{symbol} has no integer last candle timestamp")
    if declared_last + HOUR_MS > int(boundary_ms):
        raise ConfirmatoryWindowViolation(
            f"{symbol} declares a candle closing after the development boundary; dataset not opened"
        )
    dataset_path = _within_root(Path(repo_root), str(entry.get("dataset_path") or ""))
    if not dataset_path.is_file():
        raise DataVerificationError(f"{symbol} dataset is missing: {entry.get('dataset_path')}")
    candles, provenance = load_verified_candles(symbol, data_manifest, Path(repo_root))
    if not candles: raise DataVerificationError(f"{symbol} dataset is empty")
    for candle in candles:
        if int(candle.timestamp) + HOUR_MS > int(boundary_ms):
            raise ConfirmatoryWindowViolation(
                f"{symbol} contains a candle closing after the development boundary"
            )
    if entry.get("observed_candle_count") != len(candles):
        raise DataVerificationError(f"{symbol} observed candle count differs from the manifest")
    if entry.get("first_candle_timestamp") != int(candles[0].timestamp):
        raise DataVerificationError(f"{symbol} first timestamp differs from the manifest")
    if int(candles[-1].timestamp) != declared_last:
        raise DataVerificationError(f"{symbol} last timestamp differs from the manifest")
    if int(candles[-1].timestamp) + HOUR_MS != int(boundary_ms):
        raise DataVerificationError(f"{symbol} does not end exactly at the inclusive development boundary")
    content_hash = provenance.get("content_hash")
    if content_hash != entry.get("content_hash"):
        raise DataVerificationError(f"{symbol} content hash differs from its asset record")
    if content_hash != (data_manifest.get("content_hashes") or {}).get(symbol):
        raise DataVerificationError(f"{symbol} content hash differs from the manifest hash map")
    return candles, {
        "asset": symbol, "dataset_path": entry.get("dataset_path"),
        "content_hash": content_hash, "hash_verified": True,
        "candle_count": len(candles), "first_candle_timestamp": int(candles[0].timestamp),
        "last_candle_timestamp": int(candles[-1].timestamp),
        "last_candle_close_ms": int(candles[-1].timestamp) + HOUR_MS,
        "development_boundary_ms": int(boundary_ms), "confirmatory_candles_read": 0,
    }

def load_benchmark_candles(repo_root: Path, data_manifest: Dict[str, Any],
                           boundary_ms: int) -> Tuple[List[Candle], Dict[str, Any]]:
    block = data_manifest.get("benchmark") or {}
    declared_last = block.get("last_candle_timestamp")
    if not isinstance(declared_last, int):
        raise DataVerificationError("BTC benchmark has no declared last candle timestamp")
    if declared_last + HOUR_MS > int(boundary_ms):
        raise ConfirmatoryWindowViolation("BTC benchmark reaches past the development boundary; dataset not opened")
    dataset = _within_root(Path(repo_root), str(block.get("dataset_path") or ""))
    if not dataset.is_file(): raise DataVerificationError("BTC benchmark dataset is missing")
    raw_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
    if raw_hash != block.get("content_hash"):
        raise DataVerificationError("BTC benchmark byte hash differs from its manifest")
    candles = _read_dataset(dataset)
    if not candles: raise DataVerificationError("BTC benchmark dataset is empty")
    canonical_hash = compute_content_hash(candles)
    if canonical_hash != block.get("content_hash"):
        raise DataVerificationError("BTC benchmark canonical content hash differs from its manifest")
    if len(candles) != block.get("observed_candle_count"):
        raise DataVerificationError("BTC benchmark candle count differs from its manifest")
    if int(candles[0].timestamp) != block.get("first_candle_timestamp"):
        raise DataVerificationError("BTC benchmark first timestamp differs from its manifest")
    if int(candles[-1].timestamp) != declared_last:
        raise DataVerificationError("BTC benchmark last timestamp differs from its manifest")
    for candle in candles:
        if int(candle.timestamp) + HOUR_MS > int(boundary_ms):
            raise ConfirmatoryWindowViolation("BTC benchmark contains a protected candle")
    if int(candles[-1].timestamp) + HOUR_MS != int(boundary_ms):
        raise DataVerificationError("BTC benchmark does not close exactly at development boundary")
    return candles, {
        "asset": BENCHMARK_SYMBOL, "dataset_path": block.get("dataset_path"),
        "content_hash": raw_hash, "hash_verified": True, "canonical_content_hash": canonical_hash,
        "candle_count": len(candles), "first_candle_timestamp": int(candles[0].timestamp),
        "last_candle_timestamp": int(candles[-1].timestamp),
        "last_candle_close_ms": int(candles[-1].timestamp) + HOUR_MS,
        "development_boundary_ms": int(boundary_ms), "confirmatory_candles_read": 0,
    }

__all__ = ["BENCHMARK_SYMBOL","DATA_MANIFEST_RELATIVE","compute_manifest_hash",
           "load_benchmark_candles","load_development_candles","parse_utc_ms",
           "read_json","resolve_effective_data_manifest"]

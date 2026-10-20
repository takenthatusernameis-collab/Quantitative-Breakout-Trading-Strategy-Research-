#!/usr/bin/env python3
"""BRAIN-013 stage 1: retrieve the v3 BTCUSDT benchmark dataset exactly once.

The v3 universe declares ``BTCUSDT`` as its benchmark constituent
(``research/universe_manifest_v3.json`` -> ``benchmark_asset``), but the v3 data
manifest holds no dataset for it, while a quarter of the inherited grid
(576 of 2,304 configurations) needs the BTC series. The frozen engine pairs the
BTC series with the asset series **by index**, so the benchmark dataset must be
index-aligned with the evaluated assets or the run is silently wrong.

This script performs the single bounded retrieval that BRAIN-013 Design A
prescribes:

* the window is the **v3 window rule** -- exactly ``min_candles`` closed
  hourly candles ending at the last fully closed hour before the v3
  market-capitalization snapshot, so the benchmark shares the window of the six
  validated v3 assets;
* the provider and the failover policy are the frozen ones
  (``src/breakout_research/data/fetcher.py``: the primary host, then the
  documented market-data host, failing over only on the documented status
  codes);
* the raw response, its sha256 and the retrieval timestamp are recorded;
* the dataset is written under ``research/data/candles_v3/`` in the canonical
  hourly CSV form, content-addressed by its hash.

The script performs **no** evaluation, writes no v1 or v2 path, reads no
confirmatory window and re-retrieves nothing: an existing dataset is verified,
never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.data.fetcher import (  # noqa: E402
    DATASET_HASH_ALGORITHM,
    ENDPOINT_FAILOVER_STATUS_CODES,
    HOUR_MS,
    DataFetcher,
    DataUnavailableError,
    _serialize_dataset,
    compute_content_hash,
    detect_gaps,
    validate_hourly_candles,
)

SPEC_V3_PATH = "configs/research_v3.json"
SNAPSHOT_OBSERVATION_PATH = "research/v3_evidence/snapshot_observation.json"
SNAPSHOT_RAW_PATH = "research/v3_evidence/raw_market_cap_response.json"
EVIDENCE_DIR = "research/v3_evidence"
RAW_RESPONSE_PATH = "research/v3_evidence/benchmark_raw_klines.json"
EVIDENCE_PATH = "research/v3_evidence/benchmark_retrieval.json"
CANDLE_DIR_V3 = "research/data/candles_v3"

BENCHMARK_SYMBOL = "BTCUSDT"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def iso_from_ms(milliseconds: int) -> str:
    return datetime.fromtimestamp(int(milliseconds) / 1000, timezone.utc).isoformat()


def parse_iso_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
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
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


class _CapturingSession:
    """A session proxy that records the raw bytes of every response.

    The frozen ``DataFetcher`` performs the endpoint policy; this proxy only
    observes the responses it makes, so the recorded raw bytes are exactly what
    the provider returned and the policy itself is not re-implemented.
    """

    def __init__(self, session: Any) -> None:
        self._session = session
        self.pages: List[Dict[str, Any]] = []
        self.raw_bodies: List[str] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        response = self._session.get(url, **kwargs)
        try:
            body = response.content
        except Exception:  # pragma: no cover - defensive; a stream may be consumed
            body = b""
        status = int(response.status_code)
        self.pages.append({
            "url": url,
            "http_status": status,
            "bytes": len(body),
            "sha256": sha256_bytes(body),
        })
        if 200 <= status < 300:
            self.raw_bodies.append(body.decode("utf-8"))
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_window(repo_root: Path) -> Dict[str, Any]:
    """The v3 window: exactly ``min_candles`` closed hourly candles.

    The window is bound to the market-capitalization snapshot, not to the wall
    clock, so the benchmark dataset shares the window of the six validated v3
    assets and the retrieval is reproducible.
    """
    spec = load_json(repo_root / SPEC_V3_PATH)
    observation = load_json(repo_root / SNAPSHOT_OBSERVATION_PATH)
    raw_bytes = (repo_root / SNAPSHOT_RAW_PATH).read_bytes()
    digest = sha256_bytes(raw_bytes)
    if digest != observation.get("raw_response_hash"):
        raise SystemExit(
            f"the stored snapshot hash mismatch: file {digest} != recorded "
            f"{observation.get('raw_response_hash')}"
        )
    as_of = parse_iso_utc(observation["retrieval_timestamp_utc"])
    as_of_ms = int(as_of.timestamp() * 1000)
    min_candles = int(spec["universe"]["min_candles"])
    latest_closed_open = (as_of_ms // HOUR_MS - 1) * HOUR_MS
    first_open = latest_closed_open - (min_candles - 1) * HOUR_MS
    return {
        "as_of_utc": observation["retrieval_timestamp_utc"],
        "as_of_ms": as_of_ms,
        "expected_candle_count": min_candles,
        "first_open_ms": first_open,
        "latest_closed_open_ms": latest_closed_open,
        "snapshot_raw_response_hash": digest,
        "snapshot_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        "specification_hash": spec["specification_hash"],
        "protocol_version": spec["protocol_version"],
    }


def retrieve(repo_root: Path) -> Dict[str, Any]:
    """Perform the single bounded retrieval of the benchmark dataset."""
    window = resolve_window(repo_root)
    fetcher = DataFetcher()
    capturing = _CapturingSession(fetcher.session)
    fetcher.session = capturing  # type: ignore[assignment]

    started = now_utc()
    try:
        candles, rejected_rows, request_count = fetcher.fetch_full_history(
            BENCHMARK_SYMBOL,
            interval="1h",
            start_time=window["first_open_ms"],
            end_time=window["latest_closed_open_ms"],
        )
    except DataUnavailableError as exc:
        raise SystemExit(
            f"the benchmark retrieval failed against every configured endpoint: {exc}"
        ) from exc
    completed = now_utc()

    status_of_host: Dict[str, Optional[int]] = {}
    for page in capturing.pages:
        endpoint = str(page["url"]).split("?")[0]
        status_of_host.setdefault(endpoint, int(page["http_status"]))

    raw_text = _raw_response_text(capturing)
    raw_bytes = raw_text.encode("utf-8")
    raw_path = repo_root / RAW_RESPONSE_PATH
    if raw_path.exists() and raw_path.read_bytes() != raw_bytes:
        raise SystemExit(
            "the stored raw benchmark response differs from this retrieval; refusing to "
            "overwrite it (the retrieval is bounded to one)"
        )
    if not raw_path.exists():
        atomic_write_text(raw_path, raw_text)

    if len(candles) != window["expected_candle_count"]:
        raise SystemExit(
            f"the benchmark retrieval returned {len(candles)} candles, expected exactly "
            f"{window['expected_candle_count']}"
        )
    if candles[0].timestamp != window["first_open_ms"] or candles[-1].timestamp != window["latest_closed_open_ms"]:
        raise SystemExit(
            "the benchmark retrieval does not cover the requested complete closed-hour range"
        )
    gaps = detect_gaps(candles)
    if gaps:
        raise SystemExit(f"the benchmark dataset reports coverage gaps: {gaps}")
    if rejected_rows:
        raise SystemExit(f"the benchmark retrieval rejected {rejected_rows} rows")
    validate_hourly_candles(candles, window["expected_candle_count"])

    content = _serialize_dataset(candles)
    content_hash = compute_content_hash(candles)
    candle_dir = repo_root / CANDLE_DIR_V3
    dataset_file = candle_dir / f"{BENCHMARK_SYMBOL}_1h_{content_hash[:16]}.csv"
    if dataset_file.exists():
        if dataset_file.read_text(encoding="utf-8") != content:
            raise SystemExit(
                "the content-addressed benchmark dataset unexpectedly differs; refusing overwrite"
            )
    else:
        atomic_write_text(dataset_file, content)

    evidence: Dict[str, Any] = {
        "artifact": "v3_benchmark_retrieval",
        "artifact_version": 1,
        "created_utc": iso_utc(completed),
        "symbol": BENCHMARK_SYMBOL,
        "role": "benchmark_asset_and_trend_filter_input",
        "as_of_utc": window["as_of_utc"],
        "window": {
            "expected_candle_count": window["expected_candle_count"],
            "first_candle_timestamp": int(candles[0].timestamp),
            "first_candle_utc": iso_from_ms(candles[0].timestamp),
            "last_candle_timestamp": int(candles[-1].timestamp),
            "last_candle_utc": iso_from_ms(candles[-1].timestamp),
            "observed_candle_count": len(candles),
            "rule": (
                "the window is bound to the market-capitalization snapshot: exactly "
                "min_candles closed hourly candles ending at the last fully closed hour "
                "before the snapshot retrieval timestamp"
            ),
        },
        "endpoint_policy": {
            "endpoints": list(fetcher.endpoints),
            "failover_status_codes": sorted(ENDPOINT_FAILOVER_STATUS_CODES),
            "rule": (
                "the frozen DataFetcher performs the primary -> failover policy; a failover "
                "happens only on the documented access/rate-limit/transient status codes"
            ),
        },
        "http_status_of_each_probed_host": status_of_host,
        "endpoint_used": getattr(fetcher, "endpoint_used", None),
        "endpoints_used": list(getattr(fetcher, "endpoints_used", [])),
        "endpoint_failures": list(getattr(fetcher, "endpoint_failures", [])),
        "request_count": int(request_count),
        "retrieval_started_utc": iso_utc(started),
        "retrieval_completed_utc": iso_utc(completed),
        "retrieval_timestamp_utc": iso_utc(completed),
        "raw_response": {
            "path": RAW_RESPONSE_PATH,
            "sha256": sha256_bytes(raw_bytes),
            "bytes": len(raw_bytes),
            "row_count": len(candles),
            "page_count": len(capturing.pages),
            "pages": capturing.pages,
            "note": (
                "the raw kline rows exactly as the provider returned them, concatenated "
                "into one JSON array"
            ),
        },
        "dataset": {
            "dataset_path": dataset_file.relative_to(repo_root).as_posix(),
            "content_hash": content_hash,
            "hash_algorithm": DATASET_HASH_ALGORITHM,
            "bytes": len(content.encode("utf-8")),
            "sha256": sha256_file(dataset_file),
        },
        "gaps": gaps,
        "rejected_rows": int(rejected_rows),
        "snapshot_binding": {
            "raw_response_hash": window["snapshot_raw_response_hash"],
            "retrieval_timestamp_utc": window["snapshot_retrieval_timestamp_utc"],
        },
        "specification_hash": window["specification_hash"],
        "protocol_version": window["protocol_version"],
        "validated": True,
        "note": (
            "This is a data retrieval, not a research result. No grid, backtest, campaign "
            "or selection has been run under v3, and no confirmatory-window candle was read."
        ),
    }
    atomic_write_json(repo_root / EVIDENCE_PATH, evidence)
    return evidence


def _raw_response_text(capturing: _CapturingSession) -> str:
    """The raw kline rows of every page, as one JSON array.

    The page bodies are the provider's own bytes; only the outer brackets are
    re-written so that the pages form one array.
    """
    parts: List[str] = []
    for text in capturing.raw_bodies:
        stripped = text.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            raise SystemExit("a Binance kline page was not a JSON array")
        parts.append(stripped[1:-1].strip())
    return "[" + ",".join(parts) + "]\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    evidence = retrieve(repo_root)
    print(json.dumps({
        "ok": True,
        "symbol": evidence["symbol"],
        "dataset_path": evidence["dataset"]["dataset_path"],
        "content_hash": evidence["dataset"]["content_hash"],
        "raw_response_sha256": evidence["raw_response"]["sha256"],
        "retrieval_timestamp_utc": evidence["retrieval_timestamp_utc"],
        "http_status_of_each_probed_host": evidence["http_status_of_each_probed_host"],
        "request_count": evidence["request_count"],
        "candle_count": evidence["window"]["observed_candle_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

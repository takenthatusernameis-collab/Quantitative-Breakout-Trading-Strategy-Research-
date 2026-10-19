#!/usr/bin/env python3
"""BRAIN-008 section 3 validation of the v2 universe candidates (P2 and P3).

The preregistered v2 specification (``configs/research_v2.json``) freezes the
rules; this script applies them to real provider data and writes the two
artifacts the specification names:

* ``research/universe_manifest_v2.json`` — the v2 universe, built from exactly
  one market-cap snapshot retrieved inside the pinned retrieval window, with
  every candidate validated (Binance spot) or excluded with a reason;
* ``research/data_manifest_v2.json`` — the v2 data manifest with per-asset
  provenance, coverage and content hashes.

The script never touches the v1 artifacts: the frozen v1 universe manifest,
candidate manifests, data manifest, shards and ledger are read-only inputs
here, and the v1 candles directory is never written to (v2 datasets live in
``research/data/candles_v2``).

It also performs no evaluation: no grid, no backtest, no candidate selection
and no read of a confirmatory-window candle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import compute_code_hash  # noqa: E402
from breakout_research.data.fetcher import (  # noqa: E402
    DATASET_HASH_ALGORITHM,
    HOUR_MS,
    DataFetcher,
    DataUnavailableError,
    _serialize_dataset,
    compute_content_hash,
    detect_gaps,
    validate_hourly_candles,
)

SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
V1_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest.json"
V1_DATA_PATH = REPO_ROOT / "research" / "data_manifest.json"
V1_CANDIDATE_PATH = REPO_ROOT / "research" / "candidate_manifest.json"
EVIDENCE_DIR = REPO_ROOT / "research" / "v2_evidence"
SNAPSHOT_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = EVIDENCE_DIR / "snapshot_observation.json"
SPOT_VERIFICATION_PATH = EVIDENCE_DIR / "binance_spot_verification.json"
CANDLE_VERIFICATION_PATH = EVIDENCE_DIR / "candle_verification.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
CANDLE_DIR_V2 = REPO_ROOT / "research" / "data" / "candles_v2"

EXCHANGE_INFO_PRIMARY = "https://api.binance.com/api/v3/exchangeInfo"
EXCHANGE_INFO_FAILOVER = "https://data-api.binance.vision/api/v3/exchangeInfo"
DEFAULT_TIMEOUT_S = 20.0

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)
DATA_MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash", "snapshot_identity.data_manifest_hash")

EXCLUSION_REASON_BY_GROUP = {
    "exchange_tokens": "exchange_token_excluded",
    "leveraged_synthetic": "leveraged_or_synthetic_excluded",
    "low_liquidity_or_new": "low_liquidity_or_new_excluded",
    "stablecoins": "stablecoin_excluded",
    "wrapped_bridged": "wrapped_or_bridged_excluded",
}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
    """Hash a manifest body, excluding the self-referential hash keys.

    ``excluded_keys`` may name a nested key with a dotted path
    (``snapshot_identity.data_manifest_hash``) so that a manifest can carry the
    data-manifest hash without hashing itself into a cycle.
    """
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            nested = {k: v for k, v in body[head].items() if k != tail}
            body[head] = nested
    return sha256_bytes(canonical(body).encode("utf-8"))


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


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_snapshot(spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load the stored v2 snapshot and prove it is the in-window retrieval.

    The raw bytes must hash to the recorded digest and the recorded retrieval
    timestamp must fall inside the pinned window. The snapshot is never
    re-retrieved here: re-timing the window is forbidden by the specification.
    """
    raw_bytes = SNAPSHOT_RAW_PATH.read_bytes()
    observation = json.loads(SNAPSHOT_OBSERVATION_PATH.read_text(encoding="utf-8"))
    digest = sha256_bytes(raw_bytes)

    retrieval = spec["universe"]["snapshot_retrieval"]
    not_before = parse_iso_utc(retrieval["not_before_utc"])
    deadline = parse_iso_utc(retrieval["deadline_utc"])
    retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])

    if digest != observation.get("raw_response_hash"):
        raise SystemExit(
            f"stored snapshot hash mismatch: file {digest} != recorded "
            f"{observation.get('raw_response_hash')}"
        )
    if not (not_before <= retrieved_at <= deadline):
        raise SystemExit(
            f"stored snapshot was retrieved at {observation['retrieval_timestamp_utc']}, "
            f"outside the pinned window [{retrieval['not_before_utc']}, {retrieval['deadline_utc']}]"
        )
    if observation.get("endpoint") != spec["universe"]["endpoint"]:
        raise SystemExit("stored snapshot was not retrieved from the frozen endpoint")

    markets = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(markets, list) or not markets:
        raise SystemExit("stored snapshot is not a non-empty market list")
    return markets, observation


def exclusion_symbols(v1_universe: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Map excluded ticker -> its exclusion rule group and reason."""
    mapping: Dict[str, Dict[str, str]] = {}
    rules = v1_universe.get("exclusion_rules") or {}
    for group, tokens in rules.items():
        reason = EXCLUSION_REASON_BY_GROUP.get(group, f"{group}_excluded")
        for token in tokens or []:
            mapping.setdefault(str(token).upper(), {"group": group, "reason": reason})
    return mapping


def build_candidates(markets: List[Dict[str, Any]], excluded: Dict[str, Dict[str, str]],
                     top_n: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split the snapshot into the evaluation depth and the rule-excluded assets.

    The evaluation depth is taken *after* the exclusion rules, exactly as the
    campaign's own universe provider does: the top ``top_n`` non-excluded
    assets by market capitalization are the v2 candidate set.
    """
    candidates: List[Dict[str, Any]] = []
    excluded_assets: List[Dict[str, Any]] = []
    for position, market in enumerate(markets, start=1):
        ticker = str(market.get("symbol") or "").upper()
        if ticker in excluded:
            excluded_assets.append({
                "market_cap_rank": market.get("market_cap_rank"),
                "market_cap_usd": market.get("market_cap"),
                "name": market.get("name"),
                "raw_snapshot_position": position,
                "within_pre_exclusion_top_n": position <= top_n,
                "coingecko_id": market.get("id"),
                "exclusion_reason": excluded[ticker]["reason"],
                "exclusion_rule_group": excluded[ticker]["group"],
                "symbol": ticker,
            })
            continue
        candidates.append({
            "coingecko_id": market.get("id"),
            "market_cap_rank": market.get("market_cap_rank"),
            "market_cap_usd": market.get("market_cap"),
            "name": market.get("name"),
            "rank": len(candidates) + 1,
            "symbol": ticker,
        })
        if len(candidates) >= top_n:
            break
    return candidates, excluded_assets


def probe_exchange_info(host: str, pair: str, timeout_s: float) -> Dict[str, Any]:
    """One bounded, read-only request to one exchangeInfo host."""
    url = f"{host}?symbol={pair}"
    started = time.monotonic()
    observation: Dict[str, Any] = {
        "endpoint": host,
        "http_status": None,
        "pair_symbol": pair,
        "probed_at_utc": now_utc().isoformat(),
        "reachable": False,
        "tradeable": False,
        "error": None,
    }
    try:
        response = requests.get(url, timeout=timeout_s)
        observation["http_status"] = response.status_code
        observation["reachable"] = bool(response.ok)
        if response.ok:
            payload = response.json()
            symbols = payload.get("symbols") or []
            for entry in symbols:
                if entry.get("symbol") == pair:
                    observation["tradeable"] = (
                        entry.get("status") == "TRADING" and bool(entry.get("isSpotTradingAllowed", True))
                    )
                    observation["exchange_status"] = entry.get("status")
                    observation["base_asset"] = entry.get("baseAsset")
                    observation["quote_asset"] = entry.get("quoteAsset")
                    break
            else:
                observation["error"] = f"pair {pair} is not listed on this host"
        else:
            observation["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # transport errors are evidence, not a retry
        observation["error"] = f"{type(exc).__name__}: {exc}"
    observation["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return observation


def verify_binance_spot(pair: str, timeout_s: float) -> Dict[str, Any]:
    """Verify one spot pair with one bounded request per host."""
    primary = probe_exchange_info(EXCHANGE_INFO_PRIMARY, pair, timeout_s)
    record: Dict[str, Any] = {
        "endpoint_used": None,
        "http_status_of_each_probed_host": {
            EXCHANGE_INFO_PRIMARY: primary.get("http_status"),
        },
        "pair_symbol": pair,
        "probes": [primary],
        "tradeable": False,
        "verification_timestamp_utc": primary.get("probed_at_utc"),
    }
    if primary.get("reachable") and primary.get("tradeable"):
        record["endpoint_used"] = EXCHANGE_INFO_PRIMARY
        record["tradeable"] = True
        return record

    failover = probe_exchange_info(EXCHANGE_INFO_FAILOVER, pair, timeout_s)
    record["probes"].append(failover)
    record["http_status_of_each_probed_host"][EXCHANGE_INFO_FAILOVER] = failover.get("http_status")
    record["verification_timestamp_utc"] = failover.get("probed_at_utc")
    if failover.get("reachable") and failover.get("tradeable"):
        record["endpoint_used"] = EXCHANGE_INFO_FAILOVER
        record["tradeable"] = True
    return record


def fetch_candles(pair: str, min_candles: int, as_of_ms: int) -> Dict[str, Any]:
    """Fetch the complete closed-hour window that ends at the snapshot time.

    The window is bound to the market-cap snapshot timestamp rather than to the
    wall clock, so the v2 dataset is reproducible: re-running the validation
    reproduces byte-identical datasets instead of silently sliding the window
    forward. The window holds exactly ``min_candles`` closed hourly candles and
    is serialized as ``sha256-canonical-hourly-csv-v1``.
    """
    latest_closed_open = (as_of_ms // HOUR_MS - 1) * HOUR_MS
    first_open = latest_closed_open - (min_candles - 1) * HOUR_MS
    fetcher = DataFetcher()
    record: Dict[str, Any] = {
        "dataset_path": None,
        "download_attempts": 0,
        "endpoint": None,
        "endpoint_failures": [],
        "endpoints_used": [],
        "error": None,
        "expected_candle_count": min_candles,
        "first_candle_timestamp": None,
        "gaps": [],
        "last_candle_timestamp": None,
        "observed_candle_count": 0,
        "rejected_rows": 0,
        "symbol": pair,
        "validated": False,
    }
    try:
        candles, rejected_rows, request_count = fetcher.fetch_full_history(
            pair,
            interval="1h",
            start_time=first_open,
            end_time=latest_closed_open,
        )
    except DataUnavailableError as exc:
        record["error"] = str(exc)
        record["download_attempts"] = getattr(fetcher, "request_count", 0)
        record["endpoint_failures"] = list(getattr(fetcher, "endpoint_failures", []))
        record["endpoints_used"] = list(getattr(fetcher, "endpoints_used", []))
        return record

    record["download_attempts"] = request_count
    record["endpoint"] = getattr(fetcher, "endpoint_used", None)
    record["endpoints_used"] = list(getattr(fetcher, "endpoints_used", []))
    record["endpoint_failures"] = list(getattr(fetcher, "endpoint_failures", []))
    record["rejected_rows"] = rejected_rows
    record["observed_candle_count"] = len(candles)
    if candles:
        record["first_candle_timestamp"] = candles[0].timestamp
        record["last_candle_timestamp"] = candles[-1].timestamp
    record["gaps"] = detect_gaps(candles)

    try:
        validate_hourly_candles(candles, min_candles)
        if len(candles) != min_candles:
            raise DataUnavailableError(
                f"Binance range count mismatch for {pair}: expected exactly {min_candles}, "
                f"got {len(candles)}"
            )
        if candles[0].timestamp != first_open or candles[-1].timestamp != latest_closed_open:
            raise DataUnavailableError(
                f"Binance history does not cover the requested complete closed-hour range for {pair}"
            )
    except DataUnavailableError as exc:
        record["error"] = str(exc)
        return record

    content = _serialize_dataset(candles)
    content_hash = compute_content_hash(candles)
    CANDLE_DIR_V2.mkdir(parents=True, exist_ok=True)
    dataset_file = CANDLE_DIR_V2 / f"{pair}_1h_{content_hash[:16]}.csv"
    if dataset_file.exists():
        if dataset_file.read_text(encoding="utf-8") != content:
            raise SystemExit(
                f"content-addressed v2 dataset unexpectedly differs for {pair}; refusing overwrite"
            )
    else:
        atomic_write_text(dataset_file, content)
    record["content_hash"] = content_hash
    record["hash_algorithm"] = DATASET_HASH_ALGORITHM
    record["dataset_path"] = dataset_file.relative_to(REPO_ROOT).as_posix()
    record["validated"] = True
    return record


def build_snapshot_identity(spec: Dict[str, Any], observation: Dict[str, Any],
                            data_manifest_hash: Optional[str]) -> Dict[str, Any]:
    identity = {
        "candidate_manifest_hash": None,
        "code_hash": compute_code_hash(),
        "data_manifest_hash": data_manifest_hash,
        "market_cap_source_endpoint": spec["universe"]["endpoint"],
        "market_cap_source_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        "protocol_version": spec["protocol_version"],
        "specification_hash": spec["specification_hash"],
        "universe_version": spec["universe_version"],
    }
    return identity


def build_universe_manifest(spec: Dict[str, Any], v1_universe: Dict[str, Any],
                            observation: Dict[str, Any], candidates: List[Dict[str, Any]],
                            excluded_assets: List[Dict[str, Any]],
                            validation: Dict[str, Dict[str, Any]],
                            spot_evidence: Dict[str, Any],
                            data_manifest_hash: str) -> Dict[str, Any]:
    universe_spec = spec["universe"]
    eligible_assets: List[Dict[str, Any]] = []
    for candidate in candidates:
        pair = f"{candidate['symbol']}USDT"
        outcome = validation.get(pair, {})
        entry = {
            "binance_spot_verified": bool(outcome.get("binance_spot_verified")),
            "candle_history_verified": bool(outcome.get("candle_history_verified")),
            "coingecko_id": candidate["coingecko_id"],
            "exclusion_reason": outcome.get("exclusion_reason"),
            "market_cap_rank": candidate["market_cap_rank"],
            "market_cap_usd": candidate["market_cap_usd"],
            "name": candidate["name"],
            "observed_candles": outcome.get("observed_candles"),
            "rank": candidate["rank"],
            "symbol": pair,
            "validated": bool(outcome.get("validated")),
        }
        eligible_assets.append(entry)

    manifest: Dict[str, Any] = {
        "benchmark_asset": dict(v1_universe.get("benchmark_asset") or {}),
        "code_hash": compute_code_hash(),
        "created_utc": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_requirements": {
            "endpoint": spec["data"]["endpoint"],
            "failover_endpoints": list(spec["data"]["failover_endpoints"]),
            "interval": spec["data"]["interval"],
            "min_candles": universe_spec["min_candles"],
            "min_history_years": universe_spec["min_history_years"],
            "provider": spec["data"]["provider"],
        },
        "eligible_assets": eligible_assets,
        "exclusion_rules": dict(v1_universe.get("exclusion_rules") or {}),
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the manifest body with the manifest_hash key "
                "removed. The snapshot_identity.data_manifest_hash is the manifest_hash of "
                "research/data_manifest_v2.json."
            ),
        },
        "market_cap_source": {
            "endpoint": universe_spec["endpoint"],
            "note": universe_spec["survivorship_disclaimer"],
            "provider": universe_spec["source"],
            "raw_response_bytes": observation.get("raw_response_bytes"),
            "raw_response_hash": observation.get("raw_response_hash"),
            "raw_response_path": SNAPSHOT_RAW_PATH.relative_to(REPO_ROOT).as_posix(),
            "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            "retrieval_window": {
                "deadline_utc": universe_spec["snapshot_retrieval"]["deadline_utc"],
                "not_before_utc": universe_spec["snapshot_retrieval"]["not_before_utc"],
            },
        },
        "protocol_version": spec["protocol_version"],
        "snapshot_identity": build_snapshot_identity(spec, observation, data_manifest_hash),
        "specification_hash": spec["specification_hash"],
        "supersedes": {
            "candidate_manifest_path": V1_CANDIDATE_PATH.relative_to(REPO_ROOT).as_posix(),
            "candidate_manifest_sha256": sha256_file(V1_CANDIDATE_PATH),
            "protocol_version": v1_universe.get("protocol_version"),
            "universe_manifest_path": V1_UNIVERSE_PATH.relative_to(REPO_ROOT).as_posix(),
            "universe_manifest_sha256": sha256_file(V1_UNIVERSE_PATH),
        },
        "survivorship_disclaimer": (
            "This universe uses one current market-cap snapshot "
            f"({observation['retrieval_timestamp_utc']}) from CoinGecko. Historical point-in-time "
            "market-cap data is not available from a verifiably free source. This universe has "
            "survivorship and selection bias limitations. Assets that have fallen out of the top "
            f"{universe_spec['top_n']} or delisted are excluded. Do not describe this as a "
            "historically point-in-time-selected market portfolio."
        ),
        "universe_version": spec["universe_version"],
        "excluded_candidates": excluded_assets,
        "binance_spot_verification": {
            pair: {
                "endpoint_used": record.get("endpoint_used"),
                "http_status_of_each_probed_host": record.get("http_status_of_each_probed_host"),
                "pair_symbol": record.get("pair_symbol"),
                "tradeable": bool(record.get("tradeable")),
                "verification_timestamp_utc": record.get("verification_timestamp_utc"),
            }
            for pair, record in sorted(spot_evidence.items())
        },
        "candidate_manifest": {
            "candidate_manifest_hash": None,
            "note": (
                "No v2-universe candidate manifest exists. research/candidate_manifest_v2.json is "
                "manifest_version 2 of the v1 campaign, not a v2-universe manifest, and is not "
                "referenced here. Candidate selection is not authorized by this session."
            ),
            "status": "NOT_CREATED",
        },
        "prerequisite_status": {
            "P2": "DELIVERED_BY_THIS_ARTIFACT",
            "P3": "DELIVERED_BY_THIS_ARTIFACT",
            "note": (
                "configs/research_v2.json is immutable and still records P2 and P3 as "
                "OUTSTANDING; that statement describes the specification's own scope at freeze "
                "time and is not rewritten here. Flipping it requires a versioned amendment to "
                "the specification."
            ),
        },
        "validation_summary": {
            "candidate_count": len(eligible_assets),
            "excluded_by_rule_count": len(excluded_assets),
            "validated_count": sum(1 for entry in eligible_assets if entry["validated"]),
            "excluded_after_validation_count": sum(
                1 for entry in eligible_assets if entry["exclusion_reason"]
            ),
        },
    }
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    return manifest


def build_data_manifest(spec: Dict[str, Any], v1_data: Dict[str, Any],
                        observation: Dict[str, Any], validation: Dict[str, Dict[str, Any]],
                        candle_records: Dict[str, Dict[str, Any]],
                        spot_evidence: Dict[str, Any],
                        data_manifest_hash: Optional[str] = None) -> Dict[str, Any]:
    assets: Dict[str, Any] = {}
    content_hashes: Dict[str, str] = {}
    for pair, record in sorted(candle_records.items()):
        entry = {
            "content_hash": record.get("content_hash"),
            "dataset_path": record.get("dataset_path"),
            "download_attempts": record.get("download_attempts", 0),
            "endpoint": record.get("endpoint"),
            "endpoint_failures": list(record.get("endpoint_failures") or []),
            "endpoints_used": list(record.get("endpoints_used") or []),
            "expected_candle_count": record.get("expected_candle_count"),
            "first_candle_timestamp": record.get("first_candle_timestamp"),
            "gaps": list(record.get("gaps") or []),
            "hash_algorithm": record.get("hash_algorithm"),
            "interval": "1h",
            "last_candle_timestamp": record.get("last_candle_timestamp"),
            "observed_candle_count": record.get("observed_candle_count", 0),
            "provider": "binance" if record.get("validated") else None,
            "rejected_rows": record.get("rejected_rows", 0),
            "retrieval_timestamp_utc": record.get("retrieval_timestamp_utc"),
            "specification_hash": spec["specification_hash"],
            "symbol": pair,
            "validated": bool(record.get("validated")),
        }
        assets[pair] = entry
        if record.get("content_hash"):
            content_hashes[pair] = record["content_hash"]

    manifest: Dict[str, Any] = {
        "assets": assets,
        "candles_verified": any(record.get("validated") for record in candle_records.values()),
        "code_hash": compute_code_hash(),
        "content_hashes": content_hashes,
        "created_utc": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": {
            "backoff_seconds": spec["data"]["backoff_seconds"],
            "endpoint": spec["data"]["endpoint"],
            "endpoint_candidates": [spec["data"]["endpoint"]] + list(spec["data"]["failover_endpoints"]),
            "endpoint_policy": "same-provider failover; selected endpoint recorded per asset",
            "interval": spec["data"]["interval"],
            "max_retries": spec["data"]["max_retries"],
            "provider": spec["data"]["provider"],
            "rate_limit_per_minute": spec["data"]["rate_limit_per_minute"],
            "retrieval_timestamp_utc": now_utc().isoformat(),
        },
        "exclusion_reasons": {
            pair: outcome.get("exclusion_reason")
            for pair, outcome in sorted(validation.items())
            if outcome.get("exclusion_reason")
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(DATA_MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the manifest body with manifest_hash and "
                "snapshot_identity.data_manifest_hash removed, so that the manifest can carry "
                "the data-manifest hash without hashing itself into a cycle."
            ),
        },
        "invalidated_prior_entries": {},
        "market_cap_source": {
            "endpoint": spec["universe"]["endpoint"],
            "provider": spec["universe"]["source"],
            "raw_response_bytes": observation.get("raw_response_bytes"),
            "raw_response_hash": observation.get("raw_response_hash"),
            "raw_response_path": SNAPSHOT_RAW_PATH.relative_to(REPO_ROOT).as_posix(),
            "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        },
        "notes": (
            "v2 data manifest. Every accepted asset references an immutable canonical hourly CSV "
            "dataset under research/data/candles_v2. Synthetic records are never permitted. "
            "Nothing here is a research result: no grid, backtest or candidate selection has "
            "been run under v2."
        ),
        "window_policy": {
            "bound_to": "market_cap_source_retrieval_timestamp_utc",
            "candle_count": int(spec["universe"]["min_candles"]),
            "closed_candles_only": True,
            "interval": "1h",
            "last_closed_open_timestamp_ms": (
                int(parse_iso_utc(observation["retrieval_timestamp_utc"]).timestamp() * 1000) // HOUR_MS - 1
            ) * HOUR_MS,
            "note": (
                "The candle window ends at the last fully closed hour at the snapshot retrieval "
                "timestamp, so the dataset is bound to the same snapshot as the universe and "
                "re-running the validation reproduces byte-identical datasets."
            ),
        },
        "protocol_version": spec["protocol_version"],
        "provenance_ok": all(
            record.get("validated") or record.get("exclusion_reason")
            for record in validation.values()
        ),
        "prerequisite_status": {
            "P3": "DELIVERED_BY_THIS_ARTIFACT",
            "note": (
                "configs/research_v2.json is immutable and still records P2 and P3 as "
                "OUTSTANDING; that statement describes the specification's own scope at freeze "
                "time and is not rewritten here. Flipping it requires a versioned amendment to "
                "the specification."
            ),
        },
        "retrieval_timestamp_utc": now_utc().isoformat(),
        "snapshot_identity": build_snapshot_identity(spec, observation, data_manifest_hash),
        "specification_hash": spec["specification_hash"],
        "supersedes": {
            "data_manifest_path": V1_DATA_PATH.relative_to(REPO_ROOT).as_posix(),
            "data_manifest_sha256": sha256_file(V1_DATA_PATH),
            "protocol_version": v1_data.get("protocol_version"),
        },
        "universe_version": spec["universe_version"],
        "validation_results": {
            pair: {
                "binance_spot_verified": bool(outcome.get("binance_spot_verified")),
                "candle_history_verified": bool(outcome.get("candle_history_verified")),
                "exclusion_reason": outcome.get("exclusion_reason"),
                "observed_candles": outcome.get("observed_candles"),
                "validated": bool(outcome.get("validated")),
            }
            for pair, outcome in sorted(validation.items())
        },
        "binance_spot_verification": spot_evidence,
        "confirmatory_window": {
            "candidate_manifest_hash": None,
            "confirmatory_window_status": "NOT_STARTED",
            "holdout_exposed_count": 0,
            "note": (
                "No confirmatory-window candle has been read. The v2 confirmatory window starts "
                "after the v2 candidate freeze and needs at least "
                f"{spec['holdout']['v2_confirmatory_window']['min_hours']} closed hourly candles, "
                "so it cannot be evaluated in this session. The v1 holdout is never reused."
            ),
            "v1_holdout_reuse": spec["holdout"]["v1_holdout_reuse"],
        },
    }
    manifest["manifest_hash"] = compute_manifest_hash(manifest, DATA_MANIFEST_HASH_EXCLUDED_KEYS)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--skip-candles", action="store_true",
                        help="only run the spot verification (diagnostic use)")
    parser.add_argument("--force", action="store_true",
                        help="rewrite manifests that already record this snapshot")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    spec = json.loads((repo_root / "configs" / "research_v2.json").read_text(encoding="utf-8"))
    v1_universe = json.loads((repo_root / "research" / "universe_manifest.json").read_text(encoding="utf-8"))
    v1_data = json.loads((repo_root / "research" / "data_manifest.json").read_text(encoding="utf-8"))

    markets, observation = load_snapshot(spec)
    as_of_ms = int(parse_iso_utc(observation["retrieval_timestamp_utc"]).timestamp() * 1000)
    excluded = exclusion_symbols(v1_universe)

    if UNIVERSE_V2_PATH.exists() and DATA_V2_PATH.exists() and not args.force:
        existing = json.loads(UNIVERSE_V2_PATH.read_text(encoding="utf-8"))
        recorded = (existing.get("market_cap_source") or {}).get("raw_response_hash")
        if recorded == observation.get("raw_response_hash"):
            print(json.dumps({
                "ok": True,
                "rewritten": False,
                "note": (
                    "the v2 manifests already record this snapshot; re-running would only "
                    "refresh validation timestamps. Use --force to rewrite them."
                ),
                "universe_manifest_hash": existing.get("manifest_hash"),
            }, indent=2, sort_keys=True))
            return 0
    candidates, excluded_assets = build_candidates(markets, excluded, int(spec["universe"]["top_n"]))

    validation: Dict[str, Dict[str, Any]] = {}
    spot_evidence: Dict[str, Any] = {}
    candle_records: Dict[str, Dict[str, Any]] = {}

    for candidate in candidates:
        pair = f"{candidate['symbol']}USDT"
        spot = verify_binance_spot(pair, args.timeout_s)
        spot_evidence[pair] = spot
        outcome: Dict[str, Any] = {
            "binance_spot_verified": bool(spot.get("tradeable")),
            "candle_history_verified": False,
            "exclusion_reason": None,
            "observed_candles": None,
            "validated": False,
        }
        if not spot.get("tradeable"):
            outcome["exclusion_reason"] = "binance_spot_unavailable"
            validation[pair] = outcome
            continue
        if args.skip_candles:
            validation[pair] = outcome
            continue

        record = fetch_candles(pair, int(spec["universe"]["min_candles"]), as_of_ms)
        record["retrieval_timestamp_utc"] = now_utc().isoformat()
        candle_records[pair] = record
        outcome["observed_candles"] = record.get("observed_candle_count")
        if record.get("validated"):
            outcome["candle_history_verified"] = True
            outcome["validated"] = True
        elif record.get("observed_candle_count", 0) < int(spec["universe"]["min_candles"]):
            outcome["exclusion_reason"] = "insufficient_hourly_history"
        elif record.get("gaps"):
            outcome["exclusion_reason"] = "coverage_gap"
        else:
            outcome["exclusion_reason"] = "candle_validation_failed"
        validation[pair] = outcome
        print(f"{pair}: validated={outcome['validated']} "
              f"candles={outcome['observed_candles']} reason={outcome['exclusion_reason']}",
              flush=True)

    if not args.skip_candles:
        atomic_write_json(SPOT_VERIFICATION_PATH, {
            "created_utc": now_utc().isoformat(),
            "pairs": spot_evidence,
            "policy": (
                "one bounded read-only request to the primary host per pair; on failure one "
                "bounded request to the documented failover host; both statuses and timestamps "
                "are recorded"
            ),
            "protocol_version": spec["protocol_version"],
        })
        atomic_write_json(CANDLE_VERIFICATION_PATH, {
            "created_utc": now_utc().isoformat(),
            "hash_algorithm": DATASET_HASH_ALGORITHM,
            "interval": "1h",
            "min_candles": int(spec["universe"]["min_candles"]),
            "policy": (
                "the most recent complete closed-hour window of exactly min_candles candles; "
                "gaps and rejected rows are recorded; nothing is interpolated"
            ),
            "protocol_version": spec["protocol_version"],
            "records": candle_records,
            "snapshot_raw_response_hash": observation.get("raw_response_hash"),
        })

    data_manifest = build_data_manifest(spec, v1_data, observation, validation, candle_records,
                                         spot_evidence)
    data_manifest_hash = data_manifest["manifest_hash"]
    data_manifest["snapshot_identity"]["data_manifest_hash"] = data_manifest_hash
    universe_manifest = build_universe_manifest(spec, v1_universe, observation, candidates,
                                                 excluded_assets, validation, spot_evidence,
                                                 data_manifest_hash)

    atomic_write_json(DATA_V2_PATH, data_manifest)
    atomic_write_json(UNIVERSE_V2_PATH, universe_manifest)

    print(json.dumps({
        "data_manifest_hash": data_manifest_hash,
        "data_manifest_path": str(DATA_V2_PATH.relative_to(repo_root)),
        "universe_manifest_hash": universe_manifest["manifest_hash"],
        "universe_manifest_path": str(UNIVERSE_V2_PATH.relative_to(repo_root)),
        "validated_assets": sorted(pair for pair, outcome in validation.items() if outcome["validated"]),
        "excluded_assets": sorted(pair for pair, outcome in validation.items() if outcome["exclusion_reason"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""BRAIN-022: validate the v5 candidate batch and build the v5 manifests.

The preregistered v5 specification (``configs/research_v5.json``) freezes the
rules; this module applies them to real provider data and writes the two
artifacts the specification names:

* ``research/universe_manifest_v5.json`` -- the v5 universe: the candidate
  batch re-derived from the stored market-cap snapshot, every candidate
  validated (Binance spot) or excluded with a reason;
* ``research/data_manifest_v5.json`` -- the v5 data manifest with per-asset
  provenance, coverage and content hashes, the development-window policy and
  the benchmark dataset.

The v1, v2, v3 and v4 artifacts are read-only inputs here. No confirmatory
window is read: every dataset ends with the candle that **closes exactly at**
the preregistered development cutoff ``2026-10-19T22:00:00Z``, so no v5
development candle closes inside the open v2, v3 or v4 confirmatory window.
No evaluation, grid, backtest, campaign or selection runs here, and the
market-cap snapshot is never re-retrieved: the stored raw bytes are verified
against their recorded digest and their in-window retrieval timestamp.

The script performs exactly one bounded, read-only request per host per
candidate (the documented primary -> failover policy) and one paginated candle
fetch per candidate that passes the spot check, plus one fetch for the
benchmark series the v5 chain needs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

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
from v5_universe_rules import (  # noqa: E402
    DATA_MANIFEST_HASH_EXCLUDED_KEYS,
    FLOOR_SOURCE_RELATIVE,
    MANIFEST_HASH_EXCLUDED_KEYS,
    PRIOR_UNIVERSE_RELATIVES,
    SPEC_RELATIVE,
    authorized_code_hash,
    canonical_source_digest,
    compute_manifest_hash,
    development_window,
    derive_batch,
    load_exclusion_rules,
    parse_iso_utc,
    read_json,
    recompute_floor,
    sha256_bytes,
    sha256_file,
)

import requests  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / "research" / "v5_evidence"
SNAPSHOT_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = EVIDENCE_DIR / "snapshot_observation.json"
SPOT_VERIFICATION_PATH = EVIDENCE_DIR / "binance_spot_verification.json"
CANDLE_VERIFICATION_PATH = EVIDENCE_DIR / "candle_verification.json"
BENCHMARK_VERIFICATION_PATH = EVIDENCE_DIR / "benchmark_retrieval.json"
UNIVERSE_V5_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"
DATA_V5_PATH = REPO_ROOT / "research" / "data_manifest_v5.json"
CANDLE_DIR_V5 = REPO_ROOT / "research" / "data" / "candles_v5"
V4_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v4.json"
V4_DATA_PATH = REPO_ROOT / "research" / "data_manifest_v4.json"

EXCHANGE_INFO_PRIMARY = "https://api.binance.com/api/v3/exchangeInfo"
EXCHANGE_INFO_FAILOVER = "https://data-api.binance.vision/api/v3/exchangeInfo"
DEFAULT_TIMEOUT_S = 20.0

ALLOWED_VALIDATION_EXCLUSION_REASONS = (
    "binance_spot_unavailable",
    "coverage_gap",
    "insufficient_hourly_history",
    "candle_validation_failed",
)

#: The confirmatory-window membership rule this chain applies, and where it
#: comes from. The window-owning freeze states it ("candles that close at or
#: before confirmatory_window_start_utc are development data"), so a
#: development candle is inside a window only when its close is strictly after
#: that window's start. The v5 specification's
#: ``confirmatory_window_membership.interval_start_inclusive = true`` says the
#: opposite and contradicts the specification's own development-cutoff claim
#: (BRAIN-022 section 6); the specification is hash-bound and was not edited,
#: and the correction is a versioned amendment.
WINDOW_MEMBERSHIP_RULE = {
    "rule": (
        "a candle is inside a confirmatory window when its close falls strictly after that "
        "window's start and before its end, regardless of which asset the candle belongs to; a "
        "candle that closes exactly at a window's start is development data"
    ),
    "applied_by": "the v5 chain (research/data_manifest_v5.json)",
    "sources": {
        "v2": "configs/research_v2_candidate_freeze.json#data_boundary.development_data_rule",
        "v3": "configs/research_v3_candidate_freeze.json#data_boundary.development_data_rule",
    },
    "source_quote": (
        "Candles that close at or before confirmatory_window_start_utc are development data and "
        "may inform selection."
    ),
    "specification_flag": {
        "path": "configs/research_v5.json#holdout.confirmatory_window_membership",
        "interval_start_inclusive": True,
        "conflict": (
            "the flag says a candle whose close equals a window's start is inside that window, "
            "which would put the v5 boundary candle -- whose close is the v2 window's start -- "
            "inside the open v2 confirmatory window and contradict the v5 specification's own "
            "statement that no v5 development read can fall inside any open confirmatory window"
        ),
        "resolution": (
            "the v5 chain follows the window-owning freeze; configs/research_v5.json is "
            "hash-bound and was not edited; the correction is a versioned amendment (BRAIN-022 "
            "section 6)"
        ),
    },
}


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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# the snapshot
# ---------------------------------------------------------------------------


def load_snapshot(spec: Dict[str, Any], repo_root: Path = REPO_ROOT) -> Tuple[List[Dict[str, Any]],
                                                                            Dict[str, Any]]:
    """Load the stored v5 snapshot and prove it is the in-window retrieval."""
    raw_bytes = (repo_root / "research" / "v5_evidence" / "raw_market_cap_response.json").read_bytes()
    observation = read_json(repo_root / "research" / "v5_evidence" / "snapshot_observation.json")

    retrieval = spec["universe"]["snapshot_retrieval"]
    not_before = parse_iso_utc(retrieval["not_before_utc"])
    deadline = parse_iso_utc(retrieval["deadline_utc"])
    retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])

    if sha256_bytes(raw_bytes) != observation.get("pages", [{}])[0].get("raw_response_hash"):
        raise SystemExit("the stored v5 snapshot does not hash to the recorded digest")
    if not (not_before <= retrieved_at <= deadline):
        raise SystemExit(
            f"the stored v5 snapshot was retrieved at {observation['retrieval_timestamp_utc']}, "
            f"outside the pinned window [{retrieval['not_before_utc']}, {retrieval['deadline_utc']}]"
        )
    if observation.get("endpoint") != spec["universe"]["endpoint"]:
        raise SystemExit("the stored v5 snapshot was not retrieved from the frozen endpoint")

    pages = observation.get("pages") or []
    markets: List[Dict[str, Any]] = []
    for page in pages:
        path = repo_root / page["raw_response_path"]
        page_bytes = path.read_bytes()
        if sha256_bytes(page_bytes) != page.get("raw_response_hash"):
            raise SystemExit(f"the stored page {page['page']} does not hash to its recorded digest")
        rows = json.loads(page_bytes.decode("utf-8"))
        if not isinstance(rows, list) or not rows:
            raise SystemExit(f"the stored page {page['page']} is not a non-empty market list")
        if len(rows) != int(page.get("row_count") or 0):
            raise SystemExit(f"the stored page {page['page']} holds another number of rows")
        markets.extend(rows)
    return markets, observation


# ---------------------------------------------------------------------------
# the provider interactions
# ---------------------------------------------------------------------------


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
            for entry in payload.get("symbols") or []:
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
        "http_status_of_each_probed_host": {EXCHANGE_INFO_PRIMARY: primary.get("http_status")},
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


def fetch_candles(pair: str, min_candles: int, window: Dict[str, Any],
                  directory: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch the complete closed-hour window that ends at the development cutoff.

    The window is bound to the preregistered development cutoff, not to the
    wall clock and not to the market-cap snapshot timestamp, so that

    * no v5 development dataset contains a candle that closes inside the open
      v2, v3 or v4 confirmatory window, and
    * re-running the validation reproduces byte-identical datasets instead of
      silently sliding the window forward.

    The boundary is enforced twice: **before** the read the request's end time
    is the last candle that closes exactly at the cutoff (the fetcher refuses
    any row beyond it), and **after** the read the last candle is checked to
    close exactly at the cutoff.
    """
    first_open = int(window["first_open_ms"])
    latest_closed_open = int(window["last_open_ms"])
    cutoff_ms = int(window["cutoff_ms"])
    directory = Path(directory) if directory is not None else CANDLE_DIR_V5
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

    # the boundary is re-checked after the read
    if candles[-1].timestamp + HOUR_MS != cutoff_ms:
        record["error"] = (
            f"{pair}: the last candle does not close exactly at the development cutoff"
        )
        return record

    content = _serialize_dataset(candles)
    content_hash = compute_content_hash(candles)
    directory.mkdir(parents=True, exist_ok=True)
    dataset_file = directory / f"{pair}_1h_{content_hash[:16]}.csv"
    if dataset_file.exists():
        if dataset_file.read_text(encoding="utf-8") != content:
            raise SystemExit(
                f"content-addressed v5 dataset unexpectedly differs for {pair}; refusing overwrite"
            )
    else:
        atomic_write_text(dataset_file, content)
    record["content_hash"] = content_hash
    record["hash_algorithm"] = DATASET_HASH_ALGORITHM
    try:
        record["dataset_path"] = dataset_file.relative_to(REPO_ROOT).as_posix()
    except ValueError:  # a dataset written outside the repository (tests only)
        record["dataset_path"] = dataset_file.as_posix()
    record["validated"] = True
    return record


# ---------------------------------------------------------------------------
# the manifests
# ---------------------------------------------------------------------------


def build_snapshot_identity(spec: Dict[str, Any], observation: Dict[str, Any],
                             data_manifest_hash: Optional[str],
                             code_hash: Optional[str]) -> Dict[str, Any]:
    """The eight-field snapshot-identity tuple the v5 specification freezes."""
    return {
        "candidate_manifest_hash": None,
        "code_hash": code_hash,
        "data_manifest_hash": data_manifest_hash,
        "market_cap_source_endpoint": spec["universe"]["endpoint"],
        "market_cap_source_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        "protocol_version": spec["protocol_version"],
        "specification_hash": spec["specification_hash"],
        "universe_version": spec["universe_version"],
    }


def build_universe_manifest(spec: Dict[str, Any], v1_universe: Dict[str, Any],
                             v4_universe: Dict[str, Any], observation: Dict[str, Any],
                             batch: List[Dict[str, Any]], excluded_assets: List[Dict[str, Any]],
                             validation: Dict[str, Dict[str, Any]], spot_evidence: Dict[str, Any],
                             exclusion_rules: Dict[str, Any], data_manifest_hash: str,
                             code_hash: Optional[str], canonical_digest: str) -> Dict[str, Any]:
    universe_spec = spec["universe"]
    floor_symbol, floor_market_cap = recompute_floor(v4_universe)
    eligible_assets: List[Dict[str, Any]] = []
    for candidate in batch:
        pair = candidate["binance_pair"]
        outcome = validation.get(pair, {})
        eligible_assets.append({
            "binance_pair": pair,
            "binance_spot_verified": bool(outcome.get("binance_spot_verified")),
            "candle_history_verified": bool(outcome.get("candle_history_verified")),
            "coingecko_id": candidate["coingecko_id"],
            "exclusion_reason": outcome.get("exclusion_reason"),
            "market_cap_rank": candidate["market_cap_rank"],
            "market_cap_usd": candidate["market_cap_usd"],
            "name": candidate["name"],
            "observed_candles": outcome.get("observed_candles"),
            "rank": candidate["rank"],
            "symbol": candidate["symbol"],
            "validated": bool(outcome.get("validated")),
        })

    manifest: Dict[str, Any] = {
        "benchmark_asset": dict(v1_universe.get("benchmark_asset") or {}),
        "canonical_source_digest": canonical_digest,
        "code_hash": code_hash,
        "code_hash_note": (
            "code_hash is the authorized value of record for the hashed set, cross-checked "
            "against research_state/campaign_authorization.json. The ordered digest is "
            "checkout-dependent; canonical_source_digest is the portable identity of the tree "
            "and the live ordered digest is an environment fact, never an identity."
        ),
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
        "excluded_assets": excluded_assets,
        "exclusion_rules": dict(v1_universe.get("exclusion_rules") or {}),
        "exclusion_rules_application": {
            "fixed_lists": exclusion_rules["fixed_lists_source"],
            "published_classifier": exclusion_rules["classifier_source"],
            "application_order": (
                "the inherited fixed lists are evaluated first, then the published classifier "
                "groups in their published group_order; the first group that matches an entry is "
                "the recorded exclusion group"
            ),
            "note": (
                "The v5 specification names the v1 exclusion_rules fixed lists and the six "
                "exclusion categories; the published classifier of the effective v4 exclusion "
                "amendment implements exactly those six categories and is reused read-only."
            ),
        },
        "expansion_scope": {
            "floor_symbol": floor_symbol,
            "floor_market_cap_usd": floor_market_cap,
            "floor_source_manifest_path": FLOOR_SOURCE_RELATIVE,
            "floor_source_manifest_hash": v4_universe.get("manifest_hash"),
            "floor_comparison": "strictly_less_than",
            "prior_universe_versions": ["v1", "v2", "v3", "v4"],
            "ordering_rule": (
                "strictly descending market-capitalization order; the batch holds exactly "
                f"{universe_spec['top_n']} assets unless the snapshot runs out of eligible names"
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the manifest body with the manifest_hash key "
                "removed. The snapshot_identity.data_manifest_hash is the manifest_hash of "
                "research/data_manifest_v5.json."
            ),
        },
        "market_cap_source": {
            "endpoint": universe_spec["endpoint"],
            "note": universe_spec["survivorship_disclaimer"],
            "pages": list(observation.get("pages") or []),
            "provider": universe_spec["source"],
            "ranking_depth_recomputed_from_bytes": observation.get(
                "ranking_depth_recomputed_from_bytes"
            ),
            "raw_response_bytes": (observation.get("pages") or [{}])[0].get("raw_response_bytes"),
            "raw_response_hash": (observation.get("pages") or [{}])[0].get("raw_response_hash"),
            "raw_response_path": (observation.get("pages") or [{}])[0].get("raw_response_path"),
            "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            "retrieval_window": {
                "deadline_utc": universe_spec["snapshot_retrieval"]["deadline_utc"],
                "not_before_utc": universe_spec["snapshot_retrieval"]["not_before_utc"],
            },
        },
        "protocol_version": spec["protocol_version"],
        "snapshot_identity": build_snapshot_identity(spec, observation, data_manifest_hash, code_hash),
        "specification_hash": spec["specification_hash"],
        "supersedes": {
            "universe_manifest_path": FLOOR_SOURCE_RELATIVE,
            "universe_manifest_sha256": sha256_file(V4_UNIVERSE_PATH),
            "universe_manifest_hash": v4_universe.get("manifest_hash"),
            "universe_version": v4_universe.get("universe_version"),
            "note": (
                "The v4 universe manifest is immutable and is not edited by this version; the v5 "
                "universe is the next batch below the recomputed v4 floor, and no v5 "
                "constituent is an asset of the v1, v2, v3 or v4 universe."
            ),
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
        "candidate_freeze": {
            "candidate_manifest_hash": None,
            "note": (
                "The v5 candidate freeze configs/research_v5_candidate_freeze.json is the "
                "artifact that freezes the candidate set; it is produced after this manifest and "
                "is referenced by it, not the other way round."
            ),
            "status": "OUTSTANDING_FROZEN_BY_CONFIGS_RESEARCH_V5_CANDIDATE_FREEZE_JSON",
        },
        "prerequisite_status": {
            "P2": "DELIVERED_BY_THIS_ARTIFACT",
            "P3": "DELIVERED_BY_THIS_ARTIFACT",
            "note": (
                "configs/research_v5.json is immutable and still records P2 and P3 as "
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


def build_data_manifest(spec: Dict[str, Any], v4_data: Dict[str, Any],
                        observation: Dict[str, Any], validation: Dict[str, Dict[str, Any]],
                        candle_records: Dict[str, Dict[str, Any]], spot_evidence: Dict[str, Any],
                        benchmark: Dict[str, Any], code_hash: Optional[str], canonical_digest: str,
                        window: Dict[str, Any]) -> Dict[str, Any]:
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
            "exclusion_reason": record.get("exclusion_reason"),
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
        "benchmark": benchmark,
        "candles_verified": any(record.get("validated") for record in candle_records.values()),
        "canonical_source_digest": canonical_digest,
        "code_hash": code_hash,
        "code_hash_note": (
            "code_hash is the authorized value of record for the hashed set, cross-checked "
            "against research_state/campaign_authorization.json; canonical_source_digest is the "
            "portable identity of the tree."
        ),
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
        "market_cap_source": {
            "endpoint": spec["universe"]["endpoint"],
            "pages": list(observation.get("pages") or []),
            "provider": spec["universe"]["source"],
            "raw_response_bytes": (observation.get("pages") or [{}])[0].get("raw_response_bytes"),
            "raw_response_hash": (observation.get("pages") or [{}])[0].get("raw_response_hash"),
            "raw_response_path": (observation.get("pages") or [{}])[0].get("raw_response_path"),
            "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        },
        "notes": (
            "v5 data manifest. Every accepted asset references an immutable canonical hourly CSV "
            "dataset under research/data/candles_v5. Synthetic records are never permitted. "
            "Nothing here is a research result: no grid, backtest, campaign or candidate "
            "selection has been run under v5."
        ),
        "window_policy": {
            "bound_to": "holdout.development_cutoff_utc",
            "candle_count": int(spec["universe"]["min_candles"]),
            "closed_candles_only": True,
            "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
            "first_candle_open_timestamp_ms": window["first_open_ms"],
            "interval": "1h",
            "last_closed_open_timestamp_ms": window["last_open_ms"],
            "boundary_convention": (
                "inclusive: the last development candle is the one that closes exactly at the "
                "development cutoff, and no candle that closes after the cutoff is read or "
                "accepted"
            ),
            "window_membership_rule": WINDOW_MEMBERSHIP_RULE,
            "note": (
                "The candle window ends at the last fully closed hour at the preregistered "
                "development cutoff (configs/research_v5.json#holdout.development_cutoff_utc), "
                "so no v5 development dataset contains a candle that closes inside the open v2, "
                "v3 or v4 confirmatory window, and re-running the validation reproduces "
                "byte-identical datasets."
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
                "configs/research_v5.json is immutable and still records P2 and P3 as "
                "OUTSTANDING; that statement describes the specification's own scope at freeze "
                "time and is not rewritten here. Flipping it requires a versioned amendment to "
                "the specification."
            ),
        },
        "retrieval_timestamp_utc": now_utc().isoformat(),
        "snapshot_identity": build_snapshot_identity(spec, observation, None, code_hash),
        "specification_hash": spec["specification_hash"],
        "supersedes": {
            "data_manifest_path": "research/data_manifest_v4.json",
            "data_manifest_sha256": sha256_file(V4_DATA_PATH),
            "data_manifest_hash": v4_data.get("manifest_hash"),
            "protocol_version": v4_data.get("protocol_version"),
            "universe_version": v4_data.get("universe_version"),
            "note": (
                "The v4 data manifest is immutable and is not edited by this version; the v5 "
                "data manifest is the next batch below the recomputed v4 floor."
            ),
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
                "No confirmatory-window candle has been read. The v5 confirmatory window starts "
                "after the v5 candidate freeze and needs at least "
                f"{spec['holdout']['v5_confirmatory_window']['min_hours']} closed hourly candles, "
                "so it cannot be evaluated in this session. Neither the v1 holdout, nor the v2, "
                "v3 or v4 confirmatory windows are reused, and no development candle closes "
                "after the preregistered development cutoff: the last development candle is the "
                "one that closes exactly at the cutoff, so it contains no instant inside any "
                "open confirmatory window."
            ),
            "v1_holdout_reuse": spec["holdout"]["v1_holdout_reuse"],
            "v2_confirmatory_window_reuse": "forbidden",
            "v3_confirmatory_window_reuse": "forbidden",
            "v4_confirmatory_window_reuse": "forbidden",
            "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
            "window_membership_rule": WINDOW_MEMBERSHIP_RULE,
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
    spec = read_json(repo_root / SPEC_RELATIVE)
    prior_universes = [read_json(repo_root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    v1_universe = prior_universes[0]
    v4_universe = prior_universes[-1]
    v4_data = read_json(repo_root / "research" / "data_manifest_v4.json")
    exclusion_rules = load_exclusion_rules(repo_root)

    markets, observation = load_snapshot(spec, repo_root)
    window = development_window(spec)
    code_hash = authorized_code_hash(repo_root)
    canonical_digest = canonical_source_digest(repo_root)

    if UNIVERSE_V5_PATH.exists() and DATA_V5_PATH.exists() and not args.force:
        existing = read_json(UNIVERSE_V5_PATH)
        recorded = (existing.get("market_cap_source") or {}).get("raw_response_hash")
        if recorded == (observation.get("pages") or [{}])[0].get("raw_response_hash"):
            print(json.dumps({
                "ok": True,
                "rewritten": False,
                "note": (
                    "the v5 manifests already record this snapshot; re-running would only "
                    "refresh validation timestamps. Use --force to rewrite them."
                ),
                "universe_manifest_hash": existing.get("manifest_hash"),
            }, indent=2, sort_keys=True))
            return 0

    batch, excluded_assets, _records = derive_batch(
        spec, markets, prior_universes, exclusion_rules
    )
    print(f"derived candidate batch: {len(batch)} assets", flush=True)

    validation: Dict[str, Dict[str, Any]] = {}
    spot_evidence: Dict[str, Any] = {}
    candle_records: Dict[str, Dict[str, Any]] = {}

    for candidate in batch:
        pair = candidate["binance_pair"]
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
            # the candidate is recorded even though no candle was read for it, so that
            # every candidate of the batch is visible in the data manifest
            candle_records[pair] = {
                "dataset_path": None,
                "content_hash": None,
                "hash_algorithm": None,
                "download_attempts": 0,
                "endpoint": None,
                "endpoint_failures": [],
                "endpoints_used": [],
                "expected_candle_count": int(spec["universe"]["min_candles"]),
                "first_candle_timestamp": None,
                "last_candle_timestamp": None,
                "gaps": [],
                "observed_candle_count": 0,
                "rejected_rows": 0,
                "retrieval_timestamp_utc": now_utc().isoformat(),
                "symbol": pair,
                "validated": False,
                "exclusion_reason": "binance_spot_unavailable",
            }
            print(f"{pair}: spot_unavailable reason={outcome['exclusion_reason']}", flush=True)
            continue
        if args.skip_candles:
            validation[pair] = outcome
            continue

        record = fetch_candles(pair, int(spec["universe"]["min_candles"]), window)
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

    # --- the benchmark series the v5 chain needs ----------------------------
    benchmark_symbol = str((v1_universe.get("benchmark_asset") or {}).get("symbol") or "BTCUSDT")
    benchmark: Dict[str, Any] = {
        "symbol": benchmark_symbol,
        "role": (v1_universe.get("benchmark_asset") or {}).get("role"),
        "dataset_path": None,
        "content_hash": None,
        "validated": False,
        "observed_candle_count": 0,
        "expected_candle_count": int(spec["universe"]["min_candles"]),
        "first_candle_timestamp": None,
        "last_candle_timestamp": None,
        "gaps": [],
        "rule": (
            "The v5 benchmark series is a separate dataset under research/data/candles_v5, "
            "bounded at the v5 development cutoff. The v4 chain's benchmark dataset "
            "(research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv) ends with a candle "
            "closing at 2026-10-20T11:00:00Z, and 13 of its candles close after the v5 "
            "development cutoff, inside the open v2 confirmatory window, so it is not reused "
            "unchanged by the v5 chain."
        ),
    }
    if not args.skip_candles:
        benchmark_record = fetch_candles(
            benchmark_symbol, int(spec["universe"]["min_candles"]), window
        )
        benchmark_record["retrieval_timestamp_utc"] = now_utc().isoformat()
        benchmark.update({
            "dataset_path": benchmark_record.get("dataset_path"),
            "content_hash": benchmark_record.get("content_hash"),
            "hash_algorithm": benchmark_record.get("hash_algorithm"),
            "validated": bool(benchmark_record.get("validated")),
            "observed_candle_count": benchmark_record.get("observed_candle_count"),
            "first_candle_timestamp": benchmark_record.get("first_candle_timestamp"),
            "last_candle_timestamp": benchmark_record.get("last_candle_timestamp"),
            "gaps": list(benchmark_record.get("gaps") or []),
            "endpoint": benchmark_record.get("endpoint"),
            "endpoints_used": list(benchmark_record.get("endpoints_used") or []),
            "endpoint_failures": list(benchmark_record.get("endpoint_failures") or []),
            "download_attempts": benchmark_record.get("download_attempts"),
            "error": benchmark_record.get("error"),
        })
        print(f"benchmark {benchmark_symbol}: validated={benchmark['validated']} "
              f"candles={benchmark['observed_candle_count']}", flush=True)

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
            "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
            "hash_algorithm": DATASET_HASH_ALGORITHM,
            "interval": "1h",
            "min_candles": int(spec["universe"]["min_candles"]),
            "policy": (
                "the complete closed-hour window of exactly min_candles candles that ends at "
                "the preregistered development cutoff; the boundary is enforced before the "
                "read (the request's end time) and after it (the last candle's close); gaps "
                "and rejected rows are recorded; nothing is interpolated; no candle closes "
                "inside the open v2, v3 or v4 confirmatory window"
            ),
            "protocol_version": spec["protocol_version"],
            "records": candle_records,
            "snapshot_raw_response_hash": (observation.get("pages") or [{}])[0].get(
                "raw_response_hash"
            ),
        })
        atomic_write_json(BENCHMARK_VERIFICATION_PATH, {
            "created_utc": now_utc().isoformat(),
            "protocol_version": spec["protocol_version"],
            "record": benchmark,
        })

    data_manifest = build_data_manifest(spec, v4_data, observation, validation, candle_records,
                                        spot_evidence, benchmark, code_hash, canonical_digest,
                                        window)
    data_manifest_hash = data_manifest["manifest_hash"]
    data_manifest["snapshot_identity"]["data_manifest_hash"] = data_manifest_hash
    universe_manifest = build_universe_manifest(spec, v1_universe, v4_universe, observation,
                                                 batch, excluded_assets, validation, spot_evidence,
                                                 exclusion_rules, data_manifest_hash, code_hash,
                                                 canonical_digest)

    atomic_write_json(DATA_V5_PATH, data_manifest)
    atomic_write_json(UNIVERSE_V5_PATH, universe_manifest)

    print(json.dumps({
        "benchmark_validated": benchmark.get("validated"),
        "canonical_source_digest": canonical_digest,
        "code_hash": code_hash,
        "data_manifest_hash": data_manifest_hash,
        "data_manifest_path": str(DATA_V5_PATH.relative_to(repo_root)),
        "universe_manifest_hash": universe_manifest["manifest_hash"],
        "universe_manifest_path": str(UNIVERSE_V5_PATH.relative_to(repo_root)),
        "validated_assets": sorted(pair for pair, outcome in validation.items() if outcome["validated"]),
        "excluded_assets": sorted(pair for pair, outcome in validation.items() if outcome["exclusion_reason"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

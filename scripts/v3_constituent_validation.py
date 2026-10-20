#!/usr/bin/env python3
"""Build the v3 universe and data manifests (BRAIN-012 P2 and P3).

This script uses the stored v3 market-cap snapshot and the published v3
exclusion classifier to validate every candidate per the v3 specification.
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

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_exclusion_classifier import (  # noqa: E402
    classify_snapshot,
    entry_symbol,
    fixed_list_groups,
    prior_universe_match,
    reason_for_group,
)

SPEC_V3_PATH = REPO_ROOT / "configs" / "research_v3.json"
V1_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest.json"
V2_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v3_exclusion_amendment_1.json"
EVIDENCE_DIR = REPO_ROOT / "research" / "v3_evidence"
SNAPSHOT_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = EVIDENCE_DIR / "snapshot_observation.json"
SPOT_VERIFICATION_PATH = EVIDENCE_DIR / "binance_spot_verification.json"
CANDLE_VERIFICATION_PATH = EVIDENCE_DIR / "candle_verification.json"
UNIVERSE_V3_PATH = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA_V3_PATH = REPO_ROOT / "research" / "data_manifest_v3.json"
CANDLE_DIR_V3 = REPO_ROOT / "research" / "data" / "candles_v3"

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
    "synthetic_tokens": "synthetic_token_excluded",
    "derivative_tokens": "derivative_token_excluded",
}

HOUR_MS = 3600 * 1000
DATASET_HASH_ALGORITHM = "sha256-canonical-hourly-csv-v1"
DATASET_HEADER = "timestamp,open,high,low,close,volume\n"


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


def compute_code_hash(repo_root: Path = REPO_ROOT) -> str:
    try:
        sys.path.insert(0, str(repo_root / "src"))
        from breakout_research import config

        return config.compute_code_hash()
    except Exception:
        digest = hashlib.sha256()
        src_dir = repo_root / "src" / "breakout_research"
        if not src_dir.exists():
            return ""
        for root, _dirs, files in os.walk(src_dir):
            for name in sorted(files):
                if name.endswith(".py"):
                    digest.update((Path(root) / name).read_bytes())
        return digest.hexdigest()

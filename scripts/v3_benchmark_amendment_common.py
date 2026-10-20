#!/usr/bin/env python3
"""Shared recomputation helpers for the v3 benchmark amendment cascade.

BRAIN-013 decides that the v3 benchmark dataset is published by a **versioned**
amendment, because ``research/data_manifest_v3.json`` is hash-bound by the
freeze amendment 1 and by the execution protocol and must not be edited in
place. The cascade is

* ``configs/research_v3_data_manifest_amendment_1.json`` -- publishes the
  BTCUSDT benchmark entry and the *effective* data-manifest identity;
* ``configs/research_v3_candidate_freeze_amendment_2.json`` -- re-binds the
  data-manifest identity inside the frozen candidate set;
* ``configs/research_v3_execution_amendment_1.json`` -- re-binds the
  data-manifest identity inside the execution protocol and records the
  benchmark rule.

Every helper here recomputes its result from the bytes on disk. Nothing
compares an artifact with a constant copied out of that same artifact.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

#: the immutable base of the cascade
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v3.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
EXECUTION_RELATIVE = "configs/research_v3_execution.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v3_execution_amendment_1.json"
DATA_AMENDMENT_1_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
SPEC_RELATIVE = "configs/research_v3.json"
EVIDENCE_RELATIVE = "research/v3_evidence/benchmark_retrieval.json"
RAW_RESPONSE_RELATIVE = "research/v3_evidence/benchmark_raw_klines.json"

BENCHMARK_SYMBOL = "BTCUSDT"
HOUR_MS = 3600 * 1000
MIN_CANDLES = 26280

#: the v1 artifacts whose bytes must never change
V1_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

#: the v3 execution artifacts that must not exist before an authorized run
V3_EXECUTION_PATHS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
    "research/v3_selected_configurations_manifest.json",
)

#: the v3 selection authorization: a separate, versioned artifact. It does
#: not exist while no v3 run is authorized.
V3_AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"


def canonical(obj: Any) -> str:
    """Canonical JSON serialization used for every digest in the cascade."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = ("manifest_hash",)) -> str:
    """The self-hash of a hash-bound artifact.

    ``excluded_keys`` may name dotted paths; the named leaf is removed from the
    canonical body before the digest is taken.
    """
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dataset_window(repo_root: Path, dataset_path: str) -> Dict[str, Any]:
    """The window of a canonical hourly CSV dataset, recomputed from the file.

    The window is never copied out of a manifest: the first and the last
    timestamp and the row count are read from the dataset itself.
    """
    path = Path(repo_root) / dataset_path
    if not path.exists():
        raise FileNotFoundError(f"the dataset {dataset_path} does not exist")
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    if not rows or rows[0] != "timestamp,open,high,low,close,volume":
        raise ValueError(f"the dataset {dataset_path} is not a canonical hourly CSV")
    body = rows[1:]
    if not body:
        raise ValueError(f"the dataset {dataset_path} holds no candle")
    return {
        "first_candle_timestamp": int(body[0].split(",")[0]),
        "last_candle_timestamp": int(body[-1].split(",")[0]),
        "observed_candle_count": len(body),
        "file_sha256": sha256_file(path),
    }


def benchmark_entry(repo_root: Path) -> Dict[str, Any]:
    """The published benchmark entry, recomputed from the retrieved dataset.

    The entry has the same shape as a v3 data-manifest asset entry, so that the
    v3 execution path can treat the benchmark like any other dataset.
    """
    root = Path(repo_root)
    evidence = read_json(root / EVIDENCE_RELATIVE)
    dataset_path = str((evidence.get("dataset") or {}).get("dataset_path") or "")
    if not dataset_path:
        raise ValueError("the benchmark evidence records no dataset path")
    content_hash = str((evidence.get("dataset") or {}).get("content_hash") or "")
    observed = dataset_window(root, dataset_path)
    if observed["file_sha256"] != content_hash:
        raise ValueError(
            "the benchmark dataset does not hash to the content hash recorded in the evidence"
        )
    if observed["observed_candle_count"] != MIN_CANDLES:
        raise ValueError("the benchmark dataset does not hold exactly 26,280 candles")
    if evidence.get("gaps") != [] or int(evidence.get("rejected_rows") or 0) != 0:
        raise ValueError("the benchmark dataset reports coverage gaps or rejected rows")

    return {
        "content_hash": content_hash,
        "dataset_path": dataset_path,
        "download_attempts": int(evidence.get("request_count") or 0),
        "endpoint": evidence.get("endpoint_used"),
        "endpoint_failures": list(evidence.get("endpoint_failures") or []),
        "endpoints_used": list(evidence.get("endpoints_used") or []),
        "expected_candle_count": MIN_CANDLES,
        "first_candle_timestamp": observed["first_candle_timestamp"],
        "gaps": [],
        "hash_algorithm": "sha256-canonical-hourly-csv-v1",
        "interval": "1h",
        "last_candle_timestamp": observed["last_candle_timestamp"],
        "observed_candle_count": observed["observed_candle_count"],
        "provider": "binance",
        "rejected_rows": 0,
        "retrieval_timestamp_utc": evidence.get("retrieval_timestamp_utc"),
        "specification_hash": evidence.get("specification_hash"),
        "symbol": BENCHMARK_SYMBOL,
        "validated": True,
    }


def benchmark_asset_block(entry: Dict[str, Any], source: str) -> Dict[str, Any]:
    """The ``benchmark_asset`` block of the effective data manifest."""
    return {
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


def effective_data_manifest(base: Dict[str, Any], entry: Dict[str, Any],
                            source: str) -> Dict[str, Any]:
    """The base v3 data manifest plus the published benchmark entry.

    The base file keeps its own hashing rule: the self-hash is taken over the
    body with ``manifest_hash`` and ``snapshot_identity.data_manifest_hash``
    removed, so that the identity can be carried without hashing itself into a
    cycle. The effective view follows the same rule.
    """
    body = copy.deepcopy(base)
    body.pop("manifest_hash", None)
    snapshot = body.get("snapshot_identity")
    if isinstance(snapshot, dict):
        snapshot.pop("data_manifest_hash", None)
    assets = body.setdefault("assets", {})
    assets[BENCHMARK_SYMBOL] = copy.deepcopy(entry)
    hashes = body.setdefault("content_hashes", {})
    hashes[BENCHMARK_SYMBOL] = entry["content_hash"]
    body["benchmark_asset"] = benchmark_asset_block(entry, source)
    return body


def effective_data_manifest_hash(base: Dict[str, Any], entry: Dict[str, Any],
                                  source: str) -> str:
    """The identity of the effective data manifest, recomputed from the base."""
    body = effective_data_manifest(base, entry, source)
    return compute_manifest_hash(body, ("manifest_hash", "snapshot_identity.data_manifest_hash"))


def alignment_report(repo_root: Path, base: Dict[str, Any],
                     entry: Dict[str, Any]) -> Dict[str, Any]:
    """Whether the benchmark is index-aligned with the evaluated v3 assets.

    The alignment is recomputed from the dataset files themselves: the first
    timestamp, the last timestamp and the candle count of every validated asset
    and of the benchmark must be identical.
    """
    root = Path(repo_root)
    assets = (base.get("assets") or {})
    validated = sorted(
        symbol for symbol in assets
        if (base.get("content_hashes") or {}).get(symbol)
    )
    asset_windows: Dict[str, Dict[str, Any]] = {}
    for symbol in validated:
        dataset_path = str((assets[symbol] or {}).get("dataset_path") or "")
        asset_windows[symbol] = dataset_window(root, dataset_path)

    benchmark_window = dataset_window(root, entry["dataset_path"])
    benchmark_timestamps = (benchmark_window["first_candle_timestamp"],
                            benchmark_window["last_candle_timestamp"],
                            benchmark_window["observed_candle_count"])
    misaligned = sorted(
        symbol for symbol, window in asset_windows.items()
        if (window["first_candle_timestamp"], window["last_candle_timestamp"],
            window["observed_candle_count"]) != benchmark_timestamps
    )
    return {
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_window": benchmark_window,
        "evaluated_assets": validated,
        "asset_windows": asset_windows,
        "index_aligned": not misaligned,
        "misaligned_assets": misaligned,
        "rule": (
            "the benchmark dataset and every evaluated asset dataset share the first "
            "candle timestamp, the last candle timestamp and the candle count"
        ),
    }


def v1_anchor_digests(repo_root: Path) -> Dict[str, str]:
    """The sha256 of every v1 anchor, recomputed from the files."""
    root = Path(repo_root)
    return {relative: sha256_file(root / relative) for relative in V1_ANCHORS}


def raw_response_record(repo_root: Path) -> Dict[str, Any]:
    """The raw-response evidence of the benchmark retrieval."""
    root = Path(repo_root)
    evidence = read_json(root / EVIDENCE_RELATIVE)
    raw = evidence.get("raw_response") or {}
    recorded_path = str(raw.get("path") or RAW_RESPONSE_RELATIVE)
    observed = sha256_file(root / recorded_path)
    if observed != raw.get("sha256"):
        raise ValueError("the stored raw benchmark response does not match its recorded digest")
    return {
        "path": recorded_path,
        "sha256": observed,
        "bytes": int(raw.get("bytes") or 0),
        "row_count": int(raw.get("row_count") or 0),
        "page_count": int(raw.get("page_count") or 0),
        "http_status_of_each_probed_host": dict(
            evidence.get("http_status_of_each_probed_host") or {}
        ),
        "retrieval_timestamp_utc": evidence.get("retrieval_timestamp_utc"),
    }


def selection_authorization_failures(repo_root: Path) -> List[str]:
    """The failures of the v3 selection authorization, when it exists.

    The cascade authorizes nothing by itself: the selection authorization is a
    separate, versioned artifact. The rule that replaced the former "no v3
    selection authorization exists" check is **state-adaptive** and is never
    weaker than the state it replaces:

    * while the authorization does not exist, no v3 run is authorized and there
      is nothing to check -- the cascade is then the last word;
    * once it exists, it must be the hash-bound artifact that permits exactly
      one bounded selection run over the frozen candidate set, with the
      published benchmark dataset, the effective data-manifest identity and the
      deviation disclosure bound into it. A broken authorization is a failure
      of the cascade, because then the cascade would not be the last word but
      a contradiction.
    """
    root = Path(repo_root)
    path = root / V3_AUTHORIZATION_RELATIVE
    if not path.exists():
        return []

    failures: List[str] = []
    document = read_json(path)
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the v3 selection authorization does not declare its excluded keys")
    elif compute_manifest_hash(document, excluded) != document.get("manifest_hash"):
        failures.append("the v3 selection authorization does not recompute its manifest hash")

    run = document.get("authorized_run") or {}
    if run.get("authorized") is not True:
        failures.append("the v3 selection authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the v3 selection authorization does not bound the run to one attempt")

    freeze_amendment_2 = read_json(root / FREEZE_AMENDMENT_2_RELATIVE)
    frozen_pairs = list(
        (freeze_amendment_2.get("frozen_candidate_set") or {}).get("binance_pairs") or []
    )
    recorded_pairs = list((run.get("scope") or {}).get("binance_pairs") or [])
    if recorded_pairs != frozen_pairs:
        failures.append("the v3 selection authorization does not name the frozen candidate set")

    data_amendment = read_json(root / DATA_AMENDMENT_1_RELATIVE)
    entry = (data_amendment.get("benchmark_asset") or {}).get("entry") or {}
    benchmark = run.get("benchmark") or {}
    if benchmark.get("content_hash") != entry.get("content_hash"):
        failures.append(
            "the v3 selection authorization does not bind the published benchmark dataset"
        )
    if benchmark.get("btc_configurations_dropped") is not False:
        failures.append(
            "the v3 selection authorization does not forbid dropping the BTC configurations"
        )
    effective = (data_amendment.get("effective_data_manifest") or {}).get(
        "effective_data_manifest_hash"
    )
    recorded_effective = (run.get("effective_data_manifest") or {}).get(
        "effective_data_manifest_hash"
    )
    if recorded_effective != effective:
        failures.append(
            "the v3 selection authorization does not bind the effective data-manifest identity"
        )
    disclosure = run.get("deviation_disclosure") or {}
    if not disclosure.get("evidence_path") or not disclosure.get("records_with_btc_filter"):
        failures.append("the v3 selection authorization does not bind the deviation disclosure")
    return failures


__all__ = [
    "BENCHMARK_SYMBOL",
    "DATA_AMENDMENT_1_RELATIVE",
    "DATA_MANIFEST_RELATIVE",
    "EXECUTION_AMENDMENT_1_RELATIVE",
    "EXECUTION_RELATIVE",
    "EVIDENCE_RELATIVE",
    "FREEZE_AMENDMENT_1_RELATIVE",
    "FREEZE_AMENDMENT_2_RELATIVE",
    "FREEZE_RELATIVE",
    "HOUR_MS",
    "MIN_CANDLES",
    "RAW_RESPONSE_RELATIVE",
    "SPEC_RELATIVE",
    "UNIVERSE_MANIFEST_RELATIVE",
    "V1_ANCHORS",
    "V3_AUTHORIZATION_RELATIVE",
    "V3_EXECUTION_PATHS",
    "alignment_report",
    "benchmark_asset_block",
    "benchmark_entry",
    "canonical",
    "compute_manifest_hash",
    "dataset_window",
    "effective_data_manifest",
    "effective_data_manifest_hash",
    "read_json",
    "selection_authorization_failures",
    "sha256_bytes",
    "sha256_file",
    "v1_anchor_digests",
]

"""Tests for the v3 benchmark dataset, its retrieval evidence and the disclosure.

BRAIN-013 publishes the BTCUSDT benchmark dataset that the v3 selection path
needs, and discloses the deviation of the completed v1 and v2 runs. These
tests prove that

* the published dataset exists, and its canonical hourly-CSV content hash
  recomputes from the bytes on disk;
* the dataset covers exactly the window the market-capitalization snapshot
  binds, with no gap and no rejected row;
* the dataset is **index-aligned** with every validated v3 candidate dataset --
  the same first candle, the same last candle and the same candle count --
  which is the precondition of the benchmark rule;
* the dataset lies entirely before the confirmatory window, so the selection
  path can read it without exposing the confirmatory window;
* the raw provider response is retained and its digest matches the evidence;
* the disclosure reports the **recomputed** deviation: every validation fold
  misaligned and 124,416 of 497,664 v2 records affected.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from breakout_research.data.fetcher import _read_dataset, compute_content_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_PATH = REPO_ROOT / "research" / "v3_evidence" / "benchmark_retrieval.json"
RAW_PATH = REPO_ROOT / "research" / "v3_evidence" / "benchmark_raw_klines.json"
DEVIATION_PATH = (
    REPO_ROOT / "research" / "v3_evidence" / "v1_v2_btc_alignment_deviation.json"
)
DATA_AMENDMENT_PATH = (
    REPO_ROOT / "configs" / "research_v3_data_manifest_amendment_1.json"
)
DATA_MANIFEST_PATH = REPO_ROOT / "research" / "data_manifest_v3.json"
FREEZE_AMENDMENT_2_PATH = (
    REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
)
EXECUTION_AMENDMENT_1_PATH = (
    REPO_ROOT / "configs" / "research_v3_execution_amendment_1.json"
)

HOUR_MS = 3_600_000
BENCHMARK_SYMBOL = "BTCUSDT"
CONFIRMATORY_WINDOW_START_UTC = "2026-10-20T13:00:00Z"

#: the six validated v3 candidates
CANDIDATES = ("AAVEUSDT", "ICPUSDT", "PEPEUSDT", "QNTUSDT", "SHIBUSDT", "WLDUSDT")


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _window_start_ms() -> int:
    return int(
        datetime.fromisoformat(CONFIRMATORY_WINDOW_START_UTC.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .timestamp()
        * 1000
    )


@pytest.fixture(scope="module")
def evidence():
    return _load(EVIDENCE_PATH)


@pytest.fixture(scope="module")
def deviation():
    return _load(DEVIATION_PATH)


@pytest.fixture(scope="module")
def benchmark_candles(evidence):
    path = REPO_ROOT / evidence["dataset"]["dataset_path"]
    if not path.exists():
        pytest.skip("the benchmark dataset is not present in this checkout")
    return _read_dataset(path.resolve())


def test_dataset_published_and_hash_recomputes(evidence, benchmark_candles):
    dataset = evidence["dataset"]
    path = REPO_ROOT / dataset["dataset_path"]
    assert path.exists()
    assert compute_content_hash(benchmark_candles) == dataset["content_hash"]
    assert dataset["hash_algorithm"] == "sha256-canonical-hourly-csv-v1"
    assert dataset["sha256"] == dataset["content_hash"]


def test_dataset_covers_the_bound_window_without_gaps(evidence, benchmark_candles):
    window = evidence["window"]
    assert len(benchmark_candles) == window["expected_candle_count"] == 26280
    assert int(benchmark_candles[0].timestamp) == window["first_candle_timestamp"]
    assert int(benchmark_candles[-1].timestamp) == window["last_candle_timestamp"]
    assert evidence["gaps"] == []
    assert evidence["rejected_rows"] == 0

    timestamps = [int(candle.timestamp) for candle in benchmark_candles]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
    steps = {right - left for left, right in zip(timestamps, timestamps[1:])}
    assert steps == {HOUR_MS}


def test_dataset_is_index_aligned_with_every_validated_candidate(evidence):
    manifest = _load(DATA_MANIFEST_PATH)
    window = evidence["window"]
    for symbol in CANDIDATES:
        entry = manifest["assets"][symbol]
        assert entry["first_candle_timestamp"] == window["first_candle_timestamp"]
        assert entry["last_candle_timestamp"] == window["last_candle_timestamp"]
        assert entry["observed_candle_count"] == window["observed_candle_count"]


def test_dataset_closes_before_the_confirmatory_window(benchmark_candles):
    boundary = _window_start_ms()
    last_close = int(benchmark_candles[-1].timestamp) + HOUR_MS
    assert last_close <= boundary
    assert all(int(candle.timestamp) + HOUR_MS <= boundary for candle in benchmark_candles)


def test_raw_provider_response_is_retained_and_matches_the_evidence(evidence):
    if not RAW_PATH.exists():
        pytest.skip("the raw provider response is not present in this checkout")
    digest = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
    assert digest == evidence["raw_response"]["sha256"]
    assert evidence["raw_response"]["path"] == "research/v3_evidence/benchmark_raw_klines.json"
    rows = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    assert len(rows) == evidence["raw_response"]["row_count"]
    assert int(rows[0][0]) == evidence["window"]["first_candle_timestamp"]
    assert int(rows[-1][0]) == evidence["window"]["last_candle_timestamp"]


def test_retrieval_is_bounded_and_recorded(evidence):
    assert evidence["request_count"] == 27
    assert evidence["endpoint_used"] == "https://data-api.binance.vision/api/v3/klines"
    assert evidence["http_status_of_each_probed_host"] == {
        "https://api.binance.com/api/v3/klines": 451,
        "https://data-api.binance.vision/api/v3/klines": 200,
    }
    pages = evidence["raw_response"]["pages"]
    assert len(pages) == evidence["raw_response"]["page_count"] == 54
    statuses = [page["http_status"] for page in pages]
    assert statuses.count(200) == 27
    assert statuses.count(451) == 27
    # The frozen DataFetcher caps its own failure list at twenty entries; the
    # per-page list carries every attempt.
    assert len(evidence["endpoint_failures"]) == 20
    assert evidence["retrieval_timestamp_utc"] == evidence["retrieval_completed_utc"]
    assert evidence["validated"] is True
    assert "No grid, backtest, campaign or selection has been run" in evidence["note"]


def test_evidence_is_bound_to_the_published_amendment_cascade(evidence):
    amendment = _load(DATA_AMENDMENT_PATH)
    entry = (amendment.get("benchmark_asset") or {}).get("entry") or {}
    assert entry["content_hash"] == evidence["dataset"]["content_hash"]
    assert entry["dataset_path"] == evidence["dataset"]["dataset_path"]
    assert entry["first_candle_timestamp"] == evidence["window"]["first_candle_timestamp"]
    assert entry["last_candle_timestamp"] == evidence["window"]["last_candle_timestamp"]
    assert entry["observed_candle_count"] == evidence["window"]["observed_candle_count"]

    freeze_amendment = _load(FREEZE_AMENDMENT_2_PATH)
    benchmark = freeze_amendment["benchmark_asset"]
    assert benchmark["content_hash"] == evidence["dataset"]["content_hash"]
    assert benchmark["dataset_path"] == evidence["dataset"]["dataset_path"]

    execution_amendment = _load(EXECUTION_AMENDMENT_1_PATH)
    rule = execution_amendment["benchmark_rule"]
    assert rule["content_hash"] == evidence["dataset"]["content_hash"]
    assert rule["no_forward_fill"] is True


def test_deviation_disclosure_reports_every_fold_and_the_correct_count(deviation):
    counts = deviation["counts"]
    assert counts["misaligned_validation_folds"] == [0, 1, 2, 3]
    assert counts["aligned_validation_folds"] == []
    assert counts["records_with_btc_filter"] == 124416
    assert counts["total_v2_records"] == 497664
    assert counts["share_of_records"] == 0.25
    assert counts["btc_filter_configurations_per_asset"] == 576
    assert counts["total_configurations_per_asset"] == 2304
    assert counts["validation_folds"] == 4
    assert all(entry["aligned"] is False for entry in deviation["per_fold_offset"])
    assert all(entry["offset_hours"] < 0 for entry in deviation["per_fold_offset"])
    assert "124,416" in deviation["correction"]


def test_deviation_disclosure_is_carried_by_the_execution_amendment(deviation):
    execution_amendment = _load(EXECUTION_AMENDMENT_1_PATH)
    disclosure = execution_amendment["deviation_disclosure"]
    assert disclosure["records_with_btc_filter"] == deviation["counts"]["records_with_btc_filter"]
    assert disclosure["total_v2_records"] == deviation["counts"]["total_v2_records"]
    assert disclosure["misaligned_validation_folds"] == [0, 1, 2, 3]
    assert disclosure["evidence_path"] == "research/v3_evidence/v1_v2_btc_alignment_deviation.json"

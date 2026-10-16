"""Regression tests for fail-closed campaign data provenance and pagination."""
import json
from pathlib import Path

import pytest
import requests

from breakout_research.config import Candle
from types import SimpleNamespace

import breakout_research.campaign as campaign_module
from breakout_research.data import fetcher as fetcher_module
from breakout_research.data.fetcher import (
    BINANCE_KLINES_ENDPOINT,
    BINANCE_MARKET_DATA_KLINES_ENDPOINT,
    BINANCE_KLINES_ENDPOINTS,
    DATASET_HASH_ALGORITHM,
    DataFetcher,
    DataUnavailableError,
    HOUR_MS,
    _required_hourly_candles,
    compute_content_hash,
    load_or_fetch_asset_data,
    normalize_timestamps,
    validate_hourly_candles,
)


def candle(timestamp, close=100.5):
    return Candle(
        timestamp=timestamp,
        open=100.0,
        high=max(101.0, close),
        low=min(99.0, close),
        close=close,
        volume=10.0,
    )


def raw_kline(c):
    return [
        c.timestamp,
        str(c.open),
        str(c.high),
        str(c.low),
        str(c.close),
        str(c.volume),
        c.timestamp + HOUR_MS - 1,
        "1000",
        1,
        "5",
        "500",
        "0",
    ]


def tiny_spec():
    return {
        "protocol_version": "test",
        "specification_hash": "test-spec-hash",
        "data": {"interval": "1h", "max_retries": 1, "backoff_seconds": 0},
        "universe": {"min_history_years": 1 / (365 * 24)},
    }



def _prepare_campaign_runner(tmp_path, monkeypatch, symbol="OTHERUSDT", loader=None):
    monkeypatch.chdir(tmp_path)
    state = SimpleNamespace(
        current_asset_index=0,
        current_config_index=0,
        current_fold_index=0,
        current_cost_index=0,
        completed_records=0,
        pilot_completed=False,
        pilot_passed=False,
    )

    class FakeCheckpointManager:
        def load(self):
            return state

        def create_initial(self, protocol_hash):
            return state

        def save(self, _state):
            return None

    monkeypatch.setattr(campaign_module, "CheckpointManager", FakeCheckpointManager)
    monkeypatch.setattr(campaign_module, "ResultLedger", lambda: object())
    monkeypatch.setattr(campaign_module, "compute_code_hash", lambda: "test-code-hash")
    monkeypatch.setattr(campaign_module, "load_or_fetch_asset_data", loader)

    research_state = tmp_path / "research_state"
    research_state.mkdir()
    (research_state / "pilot_gate.json").write_text(
        json.dumps({
            "campaign_authorized": True,
            "specification_hash": "test-spec",
            "code_hash": "test-code-hash",
        }),
        encoding="utf-8",
    )

    runner = campaign_module.CampaignRunner.__new__(campaign_module.CampaignRunner)
    runner.protocol_hash = "test-spec"
    runner.assets = [{"symbol": symbol, "rank": 1}]
    runner.configs = []
    runner.cost_multipliers = []
    runner.fold_count = 1
    runner.validation_windows = []
    runner.dev_fraction = 0.8
    runner.holdout_fraction = 0.2
    runner.batch_size = 10
    return runner, state


def test_campaign_stops_instead_of_silently_skipping_required_asset(tmp_path, monkeypatch):
    def unavailable_loader(symbol):
        raise DataUnavailableError("provider unavailable")

    runner, state = _prepare_campaign_runner(
        tmp_path, monkeypatch, symbol="OTHERUSDT", loader=unavailable_loader
    )
    with pytest.raises(RuntimeError, match="required eligible asset OTHERUSDT"):
        runner.run()
    assert state.current_asset_index == 0


def test_campaign_stops_if_btc_benchmark_history_is_unavailable(tmp_path, monkeypatch):
    def loader(symbol):
        if symbol == "BTCUSDT":
            raise DataUnavailableError("BTC unavailable")
        return [candle(100 * HOUR_MS)]

    runner, state = _prepare_campaign_runner(
        tmp_path, monkeypatch, symbol="OTHERUSDT", loader=loader
    )
    with pytest.raises(RuntimeError, match="validated BTCUSDT benchmark history is required"):
        runner.run()
    assert state.current_asset_index == 0



def test_frozen_three_year_spec_resolves_to_26280_hourly_candles():
    spec = {
        "data": {"interval": "1h"},
        "universe": {"min_history_years": 3},
    }
    assert _required_hourly_candles(spec) == 26280



def test_loader_does_not_allow_callers_to_weaken_three_year_history_requirement(tmp_path, monkeypatch):
    spec = {
        "protocol_version": "v1",
        "specification_hash": "frozen-spec",
        "data": {"interval": "1h"},
        "universe": {"min_history_years": 3},
    }
    monkeypatch.setattr(fetcher_module, "load_research_spec", lambda: spec)
    observed = {}

    class EmptyFetcher:
        def fetch_full_history(self, symbol, interval="1h", start_time=None, end_time=None):
            observed.update(symbol=symbol, interval=interval, start_time=start_time, end_time=end_time)
            return [], 0, 1

    monkeypatch.setattr(fetcher_module, "DataFetcher", EmptyFetcher)
    with pytest.raises(DataUnavailableError, match="no valid candles"):
        load_or_fetch_asset_data(
            "TESTUSDT",
            min_candles=1000,
            data_dir=str(tmp_path / "candles"),
            manifest_path=str(tmp_path / "data_manifest.json"),
        )

    assert observed["end_time"] - observed["start_time"] == (26280 - 1) * HOUR_MS
    assert observed["interval"] == "1h"



def test_hourly_validator_rejects_gap_duplicate_bad_values_and_misalignment():
    start = 100 * HOUR_MS
    assert len(validate_hourly_candles([candle(start), candle(start + HOUR_MS)], 2)) == 0

    with pytest.raises(DataUnavailableError, match="gap"):
        validate_hourly_candles([candle(start), candle(start + 2 * HOUR_MS)], 2)

    with pytest.raises(DataUnavailableError, match="duplicate"):
        validate_hourly_candles([candle(start), candle(start)], 2)

    with pytest.raises(DataUnavailableError, match="Misaligned"):
        validate_hourly_candles([candle(start + 1)], 1)

    with pytest.raises(DataUnavailableError, match="Invalid OHLCV"):
        validate_hourly_candles([Candle(start, float("nan"), 101, 99, 100, 1)], 1)


def test_normalize_timestamps_never_rounds_market_observations():
    aligned = [candle(100 * HOUR_MS)]
    assert normalize_timestamps(aligned) is aligned

    with pytest.raises(DataUnavailableError, match="Misaligned"):
        normalize_timestamps([candle(100 * HOUR_MS + 5)])


def test_content_hash_is_deterministic_and_sensitive_to_values():
    start = 100 * HOUR_MS
    candles = [candle(start), candle(start + HOUR_MS)]
    assert compute_content_hash(candles) == compute_content_hash(list(candles))
    changed = [candles[0], candle(start + HOUR_MS, close=101.25)]
    assert compute_content_hash(candles) != compute_content_hash(changed)


def test_forward_pagination_uses_advancing_cursor_and_returns_all_rows(monkeypatch):
    monkeypatch.setattr(DataFetcher, "MAX_LIMIT", 2)
    fetcher = DataFetcher.__new__(DataFetcher)
    start = 100 * HOUR_MS
    rows = [candle(start + i * HOUR_MS) for i in range(4)]
    calls = []

    def fake_fetch(symbol, interval="1h", start_time=None, end_time=None, limit=1000):
        calls.append((start_time, end_time, limit))
        return [
            raw_kline(c) for c in rows
            if (start_time is None or c.timestamp >= start_time)
            and (end_time is None or c.timestamp <= end_time)
        ][:limit]

    monkeypatch.setattr(fetcher, "fetch_klines", fake_fetch)
    observed, rejected, request_count = fetcher.fetch_full_history(
        "TESTUSDT", start_time=start, end_time=start + 3 * HOUR_MS
    )

    assert [c.timestamp for c in observed] == [c.timestamp for c in rows]
    assert rejected == 0
    assert request_count == 2
    assert len(calls) == 2
    assert calls[1][0] == start + HOUR_MS + 1


def test_loader_replaces_synthetic_manifest_record_with_verified_real_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_module, "load_research_spec", tiny_spec)
    data_dir = tmp_path / "candles"
    manifest_path = tmp_path / "data_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "protocol_version": "v1",
            "specification_hash": "pending",
            "assets": {
                "TESTUSDT": {
                    "symbol": "TESTUSDT",
                    "provider": "binance",
                    "endpoint": BINANCE_KLINES_ENDPOINT,
                    "interval": "1h",
                    "fallback_used": True,
                    "fallback_source": "synthetic",
                    "content_hash": "old-synthetic-hash",
                    "observed_candle_count": 3000,
                }
            },
            "content_hashes": {"TESTUSDT": "old-synthetic-hash"},
        }),
        encoding="utf-8",
    )

    class FakeFetcher:
        calls = 0

        def fetch_full_history(self, symbol, interval="1h", start_time=None, end_time=None):
            self.calls += 1
            assert symbol == "TESTUSDT"
            assert interval == "1h"
            assert start_time == end_time
            return [candle(start_time)], 0, 1

    fake = FakeFetcher()
    monkeypatch.setattr(fetcher_module, "DataFetcher", lambda: fake)
    first = load_or_fetch_asset_data(
        "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
    )

    assert len(first) == 1
    assert fake.calls == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["assets"]["TESTUSDT"]
    assert entry["fallback_used"] is False
    assert entry["provider"] == "binance"
    assert entry["hash_algorithm"] == DATASET_HASH_ALGORITHM
    assert entry["content_hash"] == compute_content_hash(first)
    assert manifest["invalidated_prior_entries"]["TESTUSDT"][0]["fallback_source"] == "synthetic"
    assert Path(entry["dataset_path"]).is_file()

    # The second call loads the immutable data file and verifies its hash; it does not refetch.
    monkeypatch.setattr(
        fetcher_module,
        "DataFetcher",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected refetch")),
    )
    second = load_or_fetch_asset_data(
        "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
    )
    assert second == first


def test_loader_fails_closed_on_provider_error_without_synthetic_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_module, "load_research_spec", tiny_spec)

    class FailedFetcher:
        def fetch_full_history(self, *args, **kwargs):
            raise OSError("simulated offline provider")

    monkeypatch.setattr(fetcher_module, "DataFetcher", FailedFetcher)
    with pytest.raises(DataUnavailableError, match="synthetic fallback is prohibited"):
        load_or_fetch_asset_data(
            "TESTUSDT",
            min_candles=1,
            data_dir=str(tmp_path / "candles"),
            manifest_path=str(tmp_path / "data_manifest.json"),
        )
    assert not (tmp_path / "data_manifest.json").exists()



def test_real_cache_requires_explicit_false_fallback_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_module, "load_research_spec", tiny_spec)

    class FakeFetcher:
        def fetch_full_history(self, symbol, interval="1h", start_time=None, end_time=None):
            return [candle(start_time)], 0, 1

    monkeypatch.setattr(fetcher_module, "DataFetcher", FakeFetcher)
    data_dir = tmp_path / "candles"
    manifest_path = tmp_path / "data_manifest.json"
    load_or_fetch_asset_data(
        "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"]["TESTUSDT"]["fallback_used"] = "false"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        fetcher_module,
        "DataFetcher",
        lambda: (_ for _ in ()).throw(AssertionError("ambiguous provenance must not be refreshed silently")),
    )

    with pytest.raises(DataUnavailableError, match="explicit no-fallback attestation"):
        load_or_fetch_asset_data(
            "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
        )



def test_manifest_persistence_failure_does_not_return_a_loaded_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_module, "load_research_spec", tiny_spec)

    class FakeFetcher:
        def fetch_full_history(self, symbol, interval="1h", start_time=None, end_time=None):
            return [candle(start_time)], 0, 1

    monkeypatch.setattr(fetcher_module, "DataFetcher", FakeFetcher)

    def fail_manifest_write(path, payload):
        raise OSError("simulated manifest disk failure")

    monkeypatch.setattr(fetcher_module, "_atomic_write_json", fail_manifest_write)
    with pytest.raises(DataUnavailableError, match="provenance manifest could not be persisted"):
        load_or_fetch_asset_data(
            "TESTUSDT",
            min_candles=1,
            data_dir=str(tmp_path / "candles"),
            manifest_path=str(tmp_path / "data_manifest.json"),
        )


def test_real_cache_hash_mismatch_blocks_instead_of_silently_refetching(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_module, "load_research_spec", tiny_spec)

    class FakeFetcher:
        def fetch_full_history(self, symbol, interval="1h", start_time=None, end_time=None):
            return [candle(start_time)], 0, 1

    monkeypatch.setattr(fetcher_module, "DataFetcher", FakeFetcher)
    data_dir = tmp_path / "candles"
    manifest_path = tmp_path / "data_manifest.json"
    load_or_fetch_asset_data(
        "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"]["TESTUSDT"]["content_hash"] = "wrong-hash"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        fetcher_module,
        "DataFetcher",
        lambda: (_ for _ in ()).throw(AssertionError("cache corruption must not trigger refetch")),
    )
    with pytest.raises(DataUnavailableError, match="hash mismatch"):
        load_or_fetch_asset_data(
            "TESTUSDT", min_candles=1, data_dir=str(data_dir), manifest_path=str(manifest_path)
        )



def test_fetcher_fails_over_after_endpoint_451_and_records_actual_endpoint():
    first_candle = candle(1_700_000_000_000)
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.payload = payload if payload is not None else []

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(
                    f"HTTP {self.status_code}",
                    response=SimpleNamespace(status_code=self.status_code),
                )

        def json(self):
            return self.payload

    class FakeSession:
        def get(self, url, **_kwargs):
            calls.append(url)
            if url == BINANCE_KLINES_ENDPOINT:
                return FakeResponse(451)
            return FakeResponse(200, [raw_kline(first_candle)])

    fetcher = DataFetcher(max_retries=1, backoff_seconds=0)
    fetcher._rate_limit = lambda: None
    fetcher.session = FakeSession()

    payload = fetcher.fetch_klines("BTCUSDT")

    assert payload == [raw_kline(first_candle)]
    assert calls == list(BINANCE_KLINES_ENDPOINTS)
    assert fetcher.endpoint_used == BINANCE_MARKET_DATA_KLINES_ENDPOINT
    assert any("HTTP 451" in failure for failure in fetcher.endpoint_failures)


def test_fetcher_does_not_fail_over_for_non_retriable_bad_request():
    calls = []

    class FakeResponse:
        status_code = 400

        def raise_for_status(self):
            raise requests.HTTPError(
                "HTTP 400",
                response=SimpleNamespace(status_code=400),
            )

    class FakeSession:
        def get(self, url, **_kwargs):
            calls.append(url)
            return FakeResponse()

    fetcher = DataFetcher(max_retries=1, backoff_seconds=0)
    fetcher._rate_limit = lambda: None
    fetcher.session = FakeSession()

    with pytest.raises(DataUnavailableError, match="HTTP 400"):
        fetcher.fetch_klines("NOT_A_SYMBOL")

    assert calls == [BINANCE_KLINES_ENDPOINT]


def test_official_endpoint_failover_stays_with_binance_market_data():
    assert BINANCE_KLINES_ENDPOINTS == (
        BINANCE_KLINES_ENDPOINT,
        BINANCE_MARKET_DATA_KLINES_ENDPOINT,
    )
    assert BINANCE_MARKET_DATA_KLINES_ENDPOINT == (
        "https://data-api.binance.vision/api/v3/klines"
    )

"""Tests for the bounded universe-provider evidence module.

The terminal state of the continuous campaign must be backed by observed
provider evidence, not by an asserted provider status
(`research_state/continuous_universe_campaign_spec.md`, BRAIN-007 design
decision section 4). These tests never touch the network: the HTTP layer is
replaced by a fake session.
"""
import pytest

from breakout_research.universe_provider import (
    compare_with_frozen_universe,
    fetch_market_cap_markets,
    ping_url_for,
    probe_http_endpoint,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, raises=None):
        self.status_code = status_code
        self._payload = payload
        self._raises = raises

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


def _universe(markets_provider="coingecko"):
    return {
        "market_cap_source": {
            "provider": markets_provider,
            "endpoint": "https://api.coingecko.com/api/v3/coins/markets?per_page=100&page=1",
            "retrieval_timestamp_utc": "2026-10-15T17:10:38Z",
        },
        "exclusion_rules": {
            "stablecoins": ["USDT", "USDC"],
            "leveraged_synthetic": ["BULL", "BEAR"],
        },
        "eligible_assets": [
            {"symbol": "BTCUSDT", "coingecko_id": "bitcoin"},
            {"symbol": "ETHUSDT", "coingecko_id": "ethereum"},
        ],
    }


def _market(coin_id, symbol, market_cap):
    return {
        "id": coin_id,
        "symbol": symbol,
        "market_cap": market_cap,
    }


def test_ping_url_derives_from_klines_endpoint():
    assert ping_url_for("https://api.binance.com/api/v3/klines") == \
        "https://api.binance.com/api/v3/ping"
    assert ping_url_for("https://data-api.binance.vision/api/v3/klines") == \
        "https://data-api.binance.vision/api/v3/ping"


def test_probe_records_http_status_without_retrying():
    session = FakeSession(response=FakeResponse(status_code=451))
    observation = probe_http_endpoint("https://api.binance.com/api/v3/ping", session=session)
    assert observation["http_status"] == 451
    assert observation["reachable"] is False
    assert observation["error"] == "HTTP 451"
    assert len(session.calls) == 1


def test_probe_records_transport_error_as_evidence():
    session = FakeSession(error=OSError("name resolution failed"))
    observation = probe_http_endpoint("https://example.invalid/api/v3/ping", session=session)
    assert observation["reachable"] is False
    assert observation["http_status"] is None
    assert "OSError" in observation["error"]


def test_probe_of_missing_endpoint_is_evidence_not_exception():
    observation = probe_http_endpoint("", session=FakeSession())
    assert observation["reachable"] is False
    assert observation["error"] == "no endpoint configured"


def test_fetch_market_cap_markets_uses_the_frozen_endpoint():
    payload = [_market("bitcoin", "btc", 1)]
    session = FakeSession(response=FakeResponse(payload=payload))
    observation, markets = fetch_market_cap_markets(_universe(), session=session)
    assert session.calls[0]["url"] == _universe()["market_cap_source"]["endpoint"]
    assert observation["provider"] == "coingecko"
    assert observation["reachable"] is True
    assert observation["frozen_retrieval_timestamp_utc"] == "2026-10-15T17:10:38Z"
    assert markets == payload


def test_fetch_market_cap_markets_rejects_non_list_payload():
    session = FakeSession(response=FakeResponse(payload={"error": "nope"}))
    observation, markets = fetch_market_cap_markets(_universe(), session=session)
    assert observation["reachable"] is False
    assert observation["error"] == "provider returned a non-list payload"
    assert markets == []


def test_comparison_reports_new_and_dropped_constituents():
    universe = _universe()
    markets = [
        _market("bitcoin", "btc", 3),
        _market("ethereum", "eth", 2),
        _market("zcash", "zec", 1),
        _market("tether", "usdt", 9),
    ]
    comparison = compare_with_frozen_universe(universe, markets, candidate_depth=3)
    # tether is excluded by the frozen exclusion rules and never becomes a candidate
    assert comparison["fresh_candidate_ids"] == ["bitcoin", "ethereum", "zcash"]
    assert comparison["new_candidate_ids"] == ["zcash"]
    assert comparison["new_candidate_symbols"] == ["ZEC"]
    assert comparison["dropped_candidate_ids"] == []
    assert comparison["has_new_candidates"] is True
    assert comparison["candidates_are_data_validated"] is False


def test_comparison_reports_no_new_candidates_for_an_unchanged_snapshot():
    universe = _universe()
    markets = [
        _market("bitcoin", "btc", 3),
        _market("ethereum", "eth", 2),
        _market("tether", "usdt", 9),
    ]
    comparison = compare_with_frozen_universe(universe, markets, candidate_depth=3)
    assert comparison["has_new_candidates"] is False
    assert comparison["new_candidate_ids"] == []


def test_comparison_records_additional_candidates_beyond_the_frozen_depth():
    universe = _universe()
    markets = [
        _market("bitcoin", "btc", 5),
        _market("ethereum", "eth", 4),
        _market("zcash", "zec", 3),
        _market("hedera-hashgraph", "hbar", 2),
        _market("hyperliquid", "hype", 1),
    ]
    comparison = compare_with_frozen_universe(
        universe, markets, candidate_depth=2, additional_depth=2)
    assert comparison["candidate_depth"] == 2
    assert comparison["fresh_candidate_ids"] == ["bitcoin", "ethereum"]
    assert comparison["additional_candidate_symbols"] == ["ZEC", "HBAR"]
    assert comparison["has_new_candidates"] is False

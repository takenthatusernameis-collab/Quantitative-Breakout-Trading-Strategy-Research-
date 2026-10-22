"""Tests for the v6 universe and data manifests and their verifier.

The v6 chain is the first one that is bound to a **band-width rule** and to
the **earliest** open confirmatory window at the same time: its development
cutoff is the v2 window's start (``2026-10-19T22:00:00Z``), the same instant
the v5 chain used, and the v6 band is the 20 names below the v5 floor in
strictly descending market-capitalization order. The rules these tests pin are
therefore:

* the **floor rule**: every member of the band is strictly below the floor
  recomputed from the v5 universe manifest, which is the source the v6
  specification names;
* the **identity rule**: no member of the band is an asset of the v1, the v2,
  the v3, the v4 or the v5 universe;
* the **band-width rule**: the band holds exactly ``top_n`` names in strictly
  descending market-capitalization order, and the validated subset is a
  consequence of the band, never its definition;
* the **depth rule**: the ranking depth is recomputed from the stored bytes,
  and the bounded extra page was read only when the first page yielded fewer
  names than the band needs;
* the **development boundary**: every dataset holds exactly ``min_candles``
  closed hourly candles and ends with the candle that closes **exactly at**
  the preregistered cutoff, so no v6 development candle closes inside the open
  v2, v3, v4 or v5 confirmatory window;
* the **benchmark rule**: the v6 benchmark series is a v6-owned dataset bounded
  at the v6 cutoff;
* the **membership rule**: the v6 specification states the corrected
  confirmatory-window membership rule directly, so the v6 chain needs no
  amendment, and the manifest must state that same rule;
* the **run binding**: no v6 run artifact exists, because no v6 run is
  authorized yet.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v6.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v6.json"
SPEC_PATH = REPO_ROOT / "configs" / "research_v6.json"
OBSERVATION_PATH = REPO_ROOT / "research" / "v6_evidence" / "snapshot_observation.json"
PAGE_1_PATH = REPO_ROOT / "research" / "v6_evidence" / "raw_market_cap_response.json"
V5_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"
V5_DATA_PATH = REPO_ROOT / "research" / "data_manifest_v5.json"
V3_BENCHMARK_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

HOUR_MS = 3_600_000
MIN_CANDLES = 26280


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v6_manifests", "scripts/verify_research_v6_manifests.py")
rules = _load_module("v6_universe_rules", "scripts/v6_universe_rules.py")
producer = _load_module("v6_constituent_validation", "scripts/v6_constituent_validation.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap even though the chain
    carries ~50 MB of candle datasets and ~160 MB of result manifests. The
    tamper controls replace single files, and ``_replace`` unlinks the symlink
    before writing.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _rehash(document: Dict[str, Any], excluded: Any = ("manifest_hash",)) -> None:
    document["manifest_hash"] = verifier.compute_manifest_hash(document, excluded)


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]


def test_the_band_is_re_derived_from_the_stored_bytes() -> None:
    universe = _load(UNIVERSE_PATH)
    spec = _load(SPEC_PATH)
    prior = [_load(REPO_ROOT / relative) for relative in rules.PRIOR_UNIVERSE_RELATIVES]
    markets = json.loads(PAGE_1_PATH.read_text(encoding="utf-8"))
    band, _excluded, _records = rules.derive_batch(
        spec, markets, prior, rules.load_exclusion_rules(REPO_ROOT), check_published_batch=False
    )
    derived = [entry["binance_pair"] for entry in band]
    recorded = [entry["binance_pair"] for entry in universe["eligible_assets"]]
    assert derived == recorded
    assert len(derived) == spec["universe"]["top_n"]


def test_every_band_member_is_strictly_below_the_v5_floor() -> None:
    universe = _load(UNIVERSE_PATH)
    v5 = _load(V5_UNIVERSE_PATH)
    floor = min(int(entry["market_cap_usd"]) for entry in v5["eligible_assets"])
    assert floor == 498236520
    for entry in universe["eligible_assets"]:
        assert int(entry["market_cap_usd"]) < floor, entry["binance_pair"]


def test_the_manifest_records_the_recomputed_v5_floor() -> None:
    universe = _load(UNIVERSE_PATH)
    v5 = _load(V5_UNIVERSE_PATH)
    lowest = min(
        v5["eligible_assets"], key=lambda entry: int(entry["market_cap_usd"])
    )
    scope = universe["expansion_scope"]
    assert scope["floor_market_cap_usd"] == int(lowest["market_cap_usd"])
    assert scope["floor_symbol"] == lowest["symbol"]
    assert scope["floor_source_manifest_path"] == "research/universe_manifest_v5.json"


def test_no_band_member_is_an_asset_of_v1_to_v5() -> None:
    universe = _load(UNIVERSE_PATH)
    prior_symbols: Dict[str, str] = {}
    prior_ids: Dict[str, str] = {}
    for version, relative in zip(("v1", "v2", "v3", "v4", "v5"),
                                 rules.PRIOR_UNIVERSE_RELATIVES):
        for entry in _load(REPO_ROOT / relative)["eligible_assets"]:
            prior_symbols[str(entry["symbol"]).upper()] = version
            if entry.get("coingecko_id"):
                prior_ids[str(entry["coingecko_id"])] = version
    assert len(prior_symbols) == 83
    assert len(prior_ids) == 83
    for entry in universe["eligible_assets"]:
        assert str(entry["symbol"]).upper() not in prior_symbols, entry["binance_pair"]
        assert str(entry["coingecko_id"]) not in prior_ids, entry["binance_pair"]


def test_the_v6_cohort_is_not_any_of_the_v1_to_v5_cohorts() -> None:
    universe = _load(UNIVERSE_PATH)
    v6 = {
        entry["binance_pair"] for entry in universe["eligible_assets"]
        if entry.get("validated") is True
    }
    assert v6
    for relative in rules.PRIOR_UNIVERSE_RELATIVES:
        prior = _load(REPO_ROOT / relative)
        prior_validated = {
            entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
            for entry in prior["eligible_assets"]
            if entry.get("validated") is True
        }
        assert not v6 & prior_validated, relative


def test_the_band_holds_top_n_names_in_descending_market_cap_order() -> None:
    """The band-width rule: the band is a market-cap band, not a validated set."""
    universe = _load(UNIVERSE_PATH)
    spec = _load(SPEC_PATH)
    band = universe["eligible_assets"]
    assert len(band) == spec["universe"]["top_n"]
    caps = [int(entry["market_cap_usd"]) for entry in band]
    assert caps == sorted(caps, reverse=True)
    assert len(set(caps)) == len(caps)
    assert [int(entry["rank"]) for entry in band] == list(range(1, len(band) + 1))
    # the validated subset is a consequence of the band, never its definition
    validated = [entry for entry in band if entry.get("validated") is True]
    assert 0 < len(validated) < len(band)


def test_the_ranking_depth_is_recomputed_from_the_stored_bytes() -> None:
    observation = _load(OBSERVATION_PATH)
    rows = json.loads(PAGE_1_PATH.read_text(encoding="utf-8"))
    assert observation["ranking_depth_recomputed_from_bytes"] == len(rows)
    assert observation["total_rows"] == len(rows)
    for page in observation["pages"]:
        page_rows = json.loads((REPO_ROOT / page["raw_response_path"]).read_text(encoding="utf-8"))
        assert len(page_rows) == page["row_count"]


def test_the_bounded_extra_page_was_read_only_when_it_was_needed() -> None:
    observation = _load(OBSERVATION_PATH)
    spec = _load(SPEC_PATH)
    if observation.get("page_2_read"):
        assert observation["qualifying_after_page_1"] < spec["universe"]["top_n"]
    else:
        assert observation["qualifying_after_page_1"] >= spec["universe"]["top_n"]
    assert len(observation["pages"]) <= 2


def test_the_snapshot_was_retrieved_inside_the_pinned_window() -> None:
    observation = _load(OBSERVATION_PATH)
    spec = _load(SPEC_PATH)
    retrieval = spec["universe"]["snapshot_retrieval"]
    observed = observation["retrieval_timestamp_utc"]
    assert retrieval["not_before_utc"] <= observed <= retrieval["deadline_utc"]
    assert observation["endpoint"] == spec["universe"]["endpoint"]


def test_the_development_cutoff_is_the_earliest_open_window_start() -> None:
    spec = _load(SPEC_PATH)
    starts = []
    for gate in spec["phase_gates"]["gates"]:
        block = _load(REPO_ROOT / gate["source_path"])[gate["source_key"]]
        start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
        assert start == gate["window_start_utc"], gate["version"]
        starts.append(start)
    assert spec["holdout"]["development_cutoff_utc"] == min(starts)
    assert spec["holdout"]["development_cutoff_utc"] == "2026-10-19T22:00:00Z"


def test_every_validated_dataset_ends_at_the_development_cutoff() -> None:
    data = _load(DATA_PATH)
    spec = _load(SPEC_PATH)
    window = rules.development_window(spec)
    cutoff_ms = int(window["cutoff_ms"])
    for pair, entry in data["assets"].items():
        if entry.get("validated") is not True:
            continue
        content = (REPO_ROOT / entry["dataset_path"]).read_text(encoding="utf-8")
        rows = content.strip().splitlines()
        assert len(rows) - 1 == MIN_CANDLES, pair
        timestamps = [int(row.split(",")[0]) for row in rows[1:]]
        assert timestamps[0] == int(window["first_open_ms"]), pair
        assert timestamps[-1] + HOUR_MS == cutoff_ms, pair
        assert timestamps[-1] == int(window["last_open_ms"]), pair


def test_the_benchmark_is_bounded_at_the_v6_cutoff() -> None:
    data = _load(DATA_PATH)
    spec = _load(SPEC_PATH)
    window = rules.development_window(spec)
    benchmark = data["benchmark"]
    assert benchmark["dataset_path"].startswith("research/data/candles_v6/")
    assert benchmark["dataset_path"] != V3_BENCHMARK_PATH
    content = (REPO_ROOT / benchmark["dataset_path"]).read_text(encoding="utf-8")
    rows = content.strip().splitlines()
    assert len(rows) - 1 == MIN_CANDLES
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    assert timestamps[-1] + HOUR_MS == int(window["cutoff_ms"])


def test_the_v3_benchmark_dataset_reaches_past_the_v6_cutoff() -> None:
    """The v3/v4 benchmark may not be reused unchanged by the v6 chain."""
    spec = _load(SPEC_PATH)
    window = rules.development_window(spec)
    content = (REPO_ROOT / V3_BENCHMARK_PATH).read_text(encoding="utf-8")
    rows = content.strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    after = [timestamp for timestamp in timestamps if timestamp + HOUR_MS > int(window["cutoff_ms"])]
    assert after, "the v3 benchmark is expected to reach past the v6 cutoff"


def test_the_supersedes_chain_names_the_v5_artifacts() -> None:
    universe = _load(UNIVERSE_PATH)
    data = _load(DATA_PATH)
    v5_universe = _load(V5_UNIVERSE_PATH)
    v5_data = _load(V5_DATA_PATH)
    assert universe["supersedes"]["universe_manifest_path"] == "research/universe_manifest_v5.json"
    assert universe["supersedes"]["universe_manifest_hash"] == v5_universe["manifest_hash"]
    assert data["supersedes"]["data_manifest_path"] == "research/data_manifest_v5.json"
    assert data["supersedes"]["data_manifest_hash"] == v5_data["manifest_hash"]


def test_the_manifest_hashes_recompute() -> None:
    universe = _load(UNIVERSE_PATH)
    data = _load(DATA_PATH)
    assert universe["manifest_hash"] == verifier.compute_manifest_hash(universe, ("manifest_hash",))
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    assert data["manifest_hash"] == verifier.compute_manifest_hash(data, excluded)


def test_every_band_member_is_validated_or_excluded_with_a_reason() -> None:
    universe = _load(UNIVERSE_PATH)
    data = _load(DATA_PATH)
    for entry in universe["eligible_assets"]:
        pair = entry["binance_pair"]
        if entry.get("validated") is True:
            assert entry["exclusion_reason"] is None, pair
            assert entry["binance_spot_verified"] is True, pair
            assert entry["candle_history_verified"] is True, pair
        else:
            assert entry["exclusion_reason"] in (
                "binance_spot_unavailable",
                "coverage_gap",
                "insufficient_hourly_history",
                "candle_validation_failed",
            ), pair
        assert pair in data["assets"], pair


def test_the_prior_universe_assets_are_excluded_with_their_reason() -> None:
    universe = _load(UNIVERSE_PATH)
    reasons = {
        entry["symbol"]: entry["exclusion_reason"] for entry in universe["excluded_assets"]
    }
    assert "BTC" in reasons and reasons["BTC"] == "already_in_prior_universe"
    assert "YLDS" in reasons and reasons["YLDS"] == "already_in_prior_universe"


def test_the_confirmatory_window_is_unexposed() -> None:
    data = _load(DATA_PATH)
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    for relative in (
        "research/data_manifest_v2.json",
        "research/data_manifest_v3.json",
        "research/data_manifest_v4.json",
        "research/data_manifest_v5.json",
    ):
        assert _load(REPO_ROOT / relative)["confirmatory_window"]["holdout_exposed_count"] == 0
    assert not (REPO_ROOT / "research" / "data" / "holdout_v6").exists()


def test_no_v6_run_artifact_exists() -> None:
    """No v6 run is authorized yet, so no v6 run path may exist."""
    for relative in verifier.V6_EXECUTION_PATHS:
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_data_manifest_states_the_confirmatory_window_membership_rule() -> None:
    data = _load(DATA_PATH)
    membership = data["window_policy"]["window_membership_rule"]
    assert "strictly after" in membership["rule"]
    assert membership["sources"]["v2"].startswith("configs/research_v2_candidate_freeze.json")
    assert membership["sources"]["v3"].startswith("configs/research_v3_candidate_freeze.json")
    # the v6 specification states the corrected rule directly: no amendment
    assert membership["specification_flag"]["interval_start_inclusive"] is False
    assert membership["specification_flag"]["conflict"] is None


def test_the_prior_universe_manifests_are_unchanged() -> None:
    spec = _load(SPEC_PATH)
    for source in (spec["universe"]["expansion_scope"]["prior_universe_asset_identity"]
                   ["sources"]):
        digest = rules.sha256_file(REPO_ROOT / source["manifest_path"])
        assert digest == source["file_sha256"], source["manifest_path"]


def test_no_v6_dataset_closes_a_candle_inside_an_open_confirmatory_window() -> None:
    """The rule the window-owning freezes state.

    ``configs/research_v2_candidate_freeze.json`` -> ``data_boundary`` says
    "Candles that close at or before confirmatory_window_start_utc are
    development data"; the v3 freeze states the same. A development candle is
    therefore inside a window only when its close is **strictly after** that
    window's start. The v6 boundary candle closes exactly at the v2 window's
    start, so it is development data and creates no exposure.
    """
    spec = _load(SPEC_PATH)
    data = _load(DATA_PATH)
    for gate in spec["phase_gates"]["gates"]:
        start = rules.parse_iso_utc(gate["window_start_utc"]).timestamp() * 1000
        for pair, entry in data["assets"].items():
            if entry.get("validated") is not True:
                continue
            assert int(entry["last_candle_timestamp"]) + HOUR_MS <= start, (pair, gate["version"])
        benchmark = data["benchmark"]
        assert int(benchmark["last_candle_timestamp"]) + HOUR_MS <= start, gate["version"]


def test_the_boundary_candle_closes_exactly_at_the_v2_window_start() -> None:
    spec = _load(SPEC_PATH)
    data = _load(DATA_PATH)
    cutoff = rules.parse_iso_utc(spec["holdout"]["development_cutoff_utc"]).timestamp() * 1000
    v2_start = rules.parse_iso_utc(
        spec["phase_gates"]["gates"][0]["window_start_utc"]
    ).timestamp() * 1000
    assert cutoff == v2_start
    pair = next(key for key, entry in data["assets"].items() if entry.get("validated") is True)
    assert int(data["assets"][pair]["last_candle_timestamp"]) + HOUR_MS == cutoff


# --------------------------------------------------------------------------
# the boundary refusal (staged acceptance test 4)
# --------------------------------------------------------------------------


class _FakeCandle:
    def __init__(self, timestamp: int) -> None:
        self.timestamp = timestamp
        self.open = 1.0
        self.high = 1.0
        self.low = 1.0
        self.close = 1.0
        self.volume = 1.0

    def validate(self) -> bool:
        return True


class _FakeFetcher:
    """A fetcher that records the requested window and returns a fixed series."""

    calls: List[Dict[str, Any]] = []
    extra_candles = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.endpoint_used = "https://data-api.binance.vision/api/v3/klines"
        self.endpoints_used: List[str] = []
        self.endpoint_failures: List[str] = []
        self.request_count = 0

    def fetch_full_history(self, symbol: str, interval: str = "1h",
                           start_time: Any = None, end_time: Any = None):
        type(self).calls.append({
            "symbol": symbol,
            "interval": interval,
            "start_time": start_time,
            "end_time": end_time,
        })
        count = MIN_CANDLES + type(self).extra_candles
        candles = [
            _FakeCandle(int(start_time) + index * HOUR_MS) for index in range(count)
        ]
        return candles, 0, 1


def test_the_loader_requests_the_window_that_ends_at_the_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before the read: the request itself is bounded by the boundary."""
    spec = _load(SPEC_PATH)
    window = rules.development_window(spec)
    _FakeFetcher.calls = []
    _FakeFetcher.extra_candles = 0
    monkeypatch.setattr(producer, "DataFetcher", _FakeFetcher)
    monkeypatch.setattr(producer, "CANDLE_DIR_V6", tmp_path / "candles")
    record = producer.fetch_candles("TESTUSDT", MIN_CANDLES, window)
    assert _FakeFetcher.calls, "the loader did not call the provider"
    call = _FakeFetcher.calls[0]
    assert call["end_time"] == int(window["last_open_ms"])
    assert call["start_time"] == int(window["first_open_ms"])
    # the last requested candle closes exactly at the cutoff
    assert call["end_time"] + HOUR_MS == int(window["cutoff_ms"])
    assert record["validated"] is True


def test_the_loader_refuses_a_series_that_reaches_past_the_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the read: a series that reaches past the boundary is refused."""
    spec = _load(SPEC_PATH)
    window = rules.development_window(spec)
    _FakeFetcher.calls = []
    _FakeFetcher.extra_candles = 1
    monkeypatch.setattr(producer, "DataFetcher", _FakeFetcher)
    monkeypatch.setattr(producer, "CANDLE_DIR_V6", tmp_path / "candles")
    record = producer.fetch_candles("TESTUSDT", MIN_CANDLES, window)
    assert record["validated"] is False
    assert record["dataset_path"] is None
    assert record["error"]
    assert not list((tmp_path / "candles").glob("*.csv")) if (tmp_path / "candles").exists() else True


# --------------------------------------------------------------------------
# the tamper controls
# --------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_member_above_the_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["eligible_assets"][0]["market_cap_usd"] = 999999999999
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("not strictly below the v5 floor" in failure for failure in failures)


def test_the_verifier_detects_a_stale_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["expansion_scope"]["floor_market_cap_usd"] = 1
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("the floor recomputed from" in failure for failure in failures)


def test_the_verifier_detects_a_member_of_a_prior_universe(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    v5 = _load(V5_UNIVERSE_PATH)
    prior = next(entry for entry in v5["eligible_assets"] if entry.get("validated") is True)
    universe["eligible_assets"][0]["symbol"] = prior["symbol"]
    universe["eligible_assets"][0]["coingecko_id"] = prior["coingecko_id"]
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("already an asset of the" in failure for failure in failures)


def test_the_verifier_detects_a_band_that_is_not_the_re_derived_one(tmp_path: Path) -> None:
    """A band whose width changed after the validation outcome is known."""
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["eligible_assets"] = universe["eligible_assets"][:-1]
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("not the re-derived candidate band" in failure for failure in failures)
    assert any("not the preregistered top_n" in failure for failure in failures)


def test_the_verifier_detects_a_band_that_is_not_in_descending_order(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    band = universe["eligible_assets"]
    band[0]["market_cap_usd"], band[1]["market_cap_usd"] = (
        band[1]["market_cap_usd"], band[0]["market_cap_usd"]
    )
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("descending market-capitalization order" in failure for failure in failures)


def test_the_verifier_detects_a_wrong_depth(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    observation = _load(OBSERVATION_PATH)
    observation["ranking_depth_recomputed_from_bytes"] = 99
    _replace(root, "research/v6_evidence/snapshot_observation.json", observation)
    failures = _failures(root)
    assert any("ranking depth" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_snapshot_page(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    rows = json.loads(PAGE_1_PATH.read_text(encoding="utf-8"))
    rows[0]["market_cap"] = 1
    _replace(root, "research/v6_evidence/raw_market_cap_response.json", rows)
    failures = _failures(root)
    assert any("does not hash to its recorded digest" in failure for failure in failures)


def test_the_verifier_detects_a_dataset_that_crosses_the_boundary(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    pair = next(
        key for key, entry in data["assets"].items() if entry.get("validated") is True
    )
    data["assets"][pair]["last_candle_timestamp"] = 1792533600000
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("development cutoff" in failure for failure in failures)


def test_the_verifier_detects_a_benchmark_that_is_not_bounded_at_the_cutoff(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    data["benchmark"]["dataset_path"] = V3_BENCHMARK_PATH
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("benchmark" in failure for failure in failures)


def test_the_verifier_detects_an_exposed_confirmatory_window(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    data["confirmatory_window"]["holdout_exposed_count"] = 1
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("confirmatory exposure" in failure for failure in failures)


def test_the_verifier_detects_a_supersedes_chain_that_names_an_older_version(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["supersedes"]["universe_manifest_path"] = "research/universe_manifest_v3.json"
    _rehash(universe)
    _replace(root, "research/universe_manifest_v6.json", universe)
    failures = _failures(root)
    assert any("does not supersede the v5 universe manifest" in failure for failure in failures)


def test_the_verifier_detects_a_missing_dataset(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    pair = next(
        key for key, entry in data["assets"].items() if entry.get("validated") is True
    )
    (root / data["assets"][pair]["dataset_path"]).unlink()
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("the dataset does not exist" in failure for failure in failures)


def test_the_verifier_detects_a_dataset_that_closes_inside_an_open_window(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    pair = next(
        key for key, entry in data["assets"].items() if entry.get("validated") is True
    )
    # one hour past the v2 window's start
    data["assets"][pair]["last_candle_timestamp"] = 1792447200000
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("closes a candle inside the open" in failure for failure in failures)


def test_the_verifier_detects_a_v6_run_artifact(tmp_path: Path) -> None:
    """No v6 run is authorized, so a v6 run path must not exist."""
    root = _mirror_repo(tmp_path)
    (root / "research_state" / "checkpoint_v6.json").write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("no v6 run is authorized" in failure for failure in failures), failures


def test_the_data_manifest_states_the_membership_rule_the_specification_owns() -> None:
    """The v6 specification is the effective rule; the manifest states it."""
    data = _load(DATA_PATH)
    spec = _load(SPEC_PATH)
    manifest_rule = data["window_policy"]["window_membership_rule"]["rule"]
    assert verifier.membership_clauses(manifest_rule) == verifier.membership_clauses(
        spec["holdout"]["confirmatory_window_membership"]["rule"]
    )
    assert spec["holdout"]["confirmatory_window_membership"]["interval_start_inclusive"] is False


def test_the_verifier_detects_a_specification_with_the_contradictory_membership_flag(
    tmp_path: Path,
) -> None:
    """The v6 specification owns the rule directly, so a broken flag is refused."""
    root = _mirror_repo(tmp_path)
    spec = _load(SPEC_PATH)
    spec["holdout"]["confirmatory_window_membership"]["interval_start_inclusive"] = True
    _replace(root, "configs/research_v6.json", spec)
    failures = _failures(root)
    assert any("interval_start_inclusive must be false" in failure for failure in failures), failures


def test_the_verifier_detects_a_manifest_that_states_another_membership_rule(
    tmp_path: Path,
) -> None:
    """The manifest and the specification must state the same rule."""
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    data["window_policy"]["window_membership_rule"]["rule"] = (
        "a candle is inside a confirmatory window when its close falls in that window's time "
        "range, regardless of which asset the candle belongs to"
    )
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v6.json", data)
    failures = _failures(root)
    assert any("another membership rule" in failure for failure in failures), failures

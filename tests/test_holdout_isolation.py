"""Holdout-isolation tests for BRAIN-003 phase 2.

Validation code never evaluates or writes final-holdout units; holdout
evaluation consumes only a frozen, hash-verified candidate manifest with at
most one candidate per asset. All fixtures are synthetic software fixtures
and are never presented as market history.
"""
import hashlib
import json
from pathlib import Path

import pytest

import breakout_research.campaign as campaign_module
from breakout_research.campaign import _data_manifest_hash, _read_json_file
from breakout_research.candidate_freeze import save_candidate_manifest
from breakout_research.backtest.backtester import run_fold_backtest as real_run_fold_backtest
from breakout_research.config import (
    Candle, StrategyConfig, EntryRule, ConfirmationMode, TrendFilter, ExitType,
    CostScenario,
)
from breakout_research.data.fetcher import HOUR_MS

SHARD_ROOT = "research/results_shards"
MANIFEST_PATH = "research/results_manifest.json"

START = 100 * HOUR_MS


def make_candles(n=200, start=START):
    return [
        Candle(start + i * HOUR_MS, 100.0 + i * 0.01, 101.0 + i * 0.01,
               99.0 + i * 0.01, 100.0 + i * 0.01, 1000.0)
        for i in range(n)
    ]


def cfg(config_id, **overrides):
    base = dict(
        config_id=config_id,
        entry_rule=EntryRule.CLASSIC_HIGH_BREAKOUT,
        entry_lookback=12,
        buffer_atr_multiple=0.0,
        confirmation=ConfirmationMode.ONE_CLOSE,
        trend_filter=TrendFilter.NONE,
        exit=ExitType.CHANNEL_12,
        content_hash="cfg-hash-" + config_id,
    )
    base.update(overrides)
    return StrategyConfig(**base)


CFGS = [
    cfg("cfg_holdout_0001"),
    cfg("cfg_holdout_0002", entry_rule=EntryRule.CLOSE_BREAKOUT,
        buffer_atr_multiple=0.1, confirmation=ConfirmationMode.TWO_CLOSE,
        exit=ExitType.ATR_TRAIL_2_5),
]

SPEC = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "universe": {"min_history_years": 3},
    "data": {"interval": "1h", "max_retries": 1, "backoff_seconds": 0},
    "costs": {"baseline": {"taker_fee_bps": 10, "slippage_bps": 5}, "scenarios": [1.0]},
    "folds": {"development_fraction": 0.8, "holdout_fraction": 0.2,
              "validation_windows": 4, "window_fractions": [0.4, 0.5, 0.6, 0.7]},
    "checkpointing": {"batch_size": 2, "atomic_writes": True, "verify_on_resume": True,
                      "max_retries": 3},
}

UNIVERSE = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "eligible_assets": [
        {"symbol": "BTCUSDT", "rank": 1, "binance_spot_verified": True},
    ],
}

CONFIG_MANIFEST = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "configurations": [c.to_dict() for c in CFGS],
}

EXPECTED_VALIDATION_UNITS = 1 * 2 * 4 * 1  # asset x configs x validation folds x costs
EXPECTED_HOLDOUT_UNITS = 1 * 1 * 1  # asset x frozen candidates x costs


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_runner(tmp_path, monkeypatch, write_candidate_manifest=True):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(campaign_module, "load_research_spec", lambda: SPEC)
    monkeypatch.setattr(campaign_module, "load_universe_manifest", lambda: UNIVERSE)
    monkeypatch.setattr(campaign_module, "load_config_manifest", lambda: CONFIG_MANIFEST)
    monkeypatch.setattr(campaign_module, "compute_code_hash", lambda: "test-code-hash")

    _write(tmp_path / "configs/research_v1.json", SPEC)
    _write(tmp_path / "research/universe_manifest.json", UNIVERSE)
    _write(tmp_path / "research/config_manifest.json", CONFIG_MANIFEST)
    _write(tmp_path / "research/data_manifest.json", {
        "assets": {"BTCUSDT": {"content_hash": "data-hash-btc"}},
    })
    _write(tmp_path / "research_state/pilot_gate.json", {
        "campaign_authorized": True,
        "specification_hash": SPEC["specification_hash"],
        "code_hash": "test-code-hash",
    })

    if write_candidate_manifest:
        save_candidate_manifest({
            "frozen": True,
            "candidates": {
                "BTCUSDT": {"config_id": "cfg_holdout_0001",
                            "parameters": {}, "freeze_commit": "test"},
            },
        }, str(tmp_path / "research/candidate_manifest.json"))

    candles = make_candles()
    def loader(symbol):
        if symbol != "BTCUSDT":
            raise KeyError(symbol)
        return list(candles)
    monkeypatch.setattr(campaign_module, "load_or_fetch_asset_data", loader)

    runner = campaign_module.CampaignRunner()
    runner.batch_size = 2
    return runner


def _all_records(tmp_path):
    data_manifest = _read_json_file(str(tmp_path / "research/data_manifest.json"))
    campaign_id = hashlib.sha256(
        f"{SPEC['specification_hash']}:test-code-hash:{_data_manifest_hash(data_manifest)}".encode()
    ).hexdigest()
    shard_dir = tmp_path / SHARD_ROOT / campaign_id
    records = []
    if shard_dir.is_dir():
        for path in sorted(shard_dir.glob("shard_*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
    return records


def test_iter_units_validation_skips_holdout_folds_entirely(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch)
    runner = campaign_module.CampaignRunner()
    fold_bounds = runner._get_fold_bounds(make_candles())
    assert any(is_holdout for (_, _, _, is_holdout) in fold_bounds), \
        "fold bounds must contain a holdout fold for this test to be meaningful"

    yielded = list(runner._iter_units(
        UNIVERSE["eligible_assets"], CFGS, [1.0], fold_bounds,
        holdout_enabled=False, asset_index=0,
        data_hashes={"BTCUSDT": "data-hash-btc"},
        protocol_hash=SPEC["specification_hash"], code_hash="test-code-hash",
    ))
    units = [unit for unit, _experiment_id in yielded]
    assert len(units) == EXPECTED_VALIDATION_UNITS
    assert all(not unit["is_holdout"] for unit in units)
    assert all(unit["fold_index"] < 4 for unit in units)


def test_iter_units_holdout_only_yields_frozen_candidates(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch)
    runner = campaign_module.CampaignRunner()
    fold_bounds = runner._get_fold_bounds(make_candles())
    candidate_ids = {"BTCUSDT": {"cfg_holdout_0001"}}

    yielded = list(runner._iter_units(
        UNIVERSE["eligible_assets"], CFGS, [1.0], fold_bounds,
        holdout_enabled=True, asset_index=0,
        data_hashes={"BTCUSDT": "data-hash-btc"},
        protocol_hash=SPEC["specification_hash"], code_hash="test-code-hash",
        candidate_ids=candidate_ids,
    ))
    units = [unit for unit, _experiment_id in yielded]
    holdout_units = [u for u in units if u["is_holdout"]]
    validation_units = [u for u in units if not u["is_holdout"]]
    assert len(validation_units) == EXPECTED_VALIDATION_UNITS
    assert len(holdout_units) == EXPECTED_HOLDOUT_UNITS
    assert all(u["config"].config_id == "cfg_holdout_0001" for u in holdout_units)
    assert all(u["fold_index"] == 4 for u in holdout_units)


def test_validation_run_writes_zero_holdout_rows(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch)
    result = runner.run(holdout_enabled=False)

    assert result["status"] == "CAMPAIGN_PARTIAL"
    assert result["total_experiments"] == EXPECTED_VALIDATION_UNITS
    assert result["executed_this_session"] == EXPECTED_VALIDATION_UNITS

    records = _all_records(tmp_path)
    assert len(records) == EXPECTED_VALIDATION_UNITS
    assert all(not r["is_holdout"] for r in records)
    assert all(r["fold_index"] < 4 for r in records)
    ids = [r["experiment_id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate experiment IDs in validation run"


def test_holdout_run_requires_frozen_candidate_manifest(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch, write_candidate_manifest=False)
    with pytest.raises(RuntimeError, match="frozen candidate manifest"):
        runner.run(holdout_enabled=True)
    # Fail closed: no holdout units were executed or written.
    assert not _all_records(tmp_path)


def test_holdout_run_rejects_unfrozen_manifest(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch, write_candidate_manifest=False)
    save_candidate_manifest({
        "frozen": False,
        "candidates": {
            "BTCUSDT": {"config_id": "cfg_holdout_0001",
                        "parameters": {}, "freeze_commit": "test"},
        },
    }, str(tmp_path / "research/candidate_manifest.json"))

    runner = _build_runner(tmp_path, monkeypatch, write_candidate_manifest=False)
    with pytest.raises(RuntimeError, match="frozen candidate manifest"):
        runner.run(holdout_enabled=True)


def test_holdout_run_rejects_tampered_manifest_hash(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch, write_candidate_manifest=False)
    save_candidate_manifest({
        "frozen": True,
        "candidates": {
            "BTCUSDT": {"config_id": "cfg_holdout_0001",
                        "parameters": {}, "freeze_commit": "test"},
        },
    }, str(tmp_path / "research/candidate_manifest.json"))
    manifest_path = tmp_path / "research/candidate_manifest.json"
    manifest = _read_json_file(str(manifest_path))
    manifest["candidates"]["BTCUSDT"]["config_id"] = "cfg_unknown"
    # Re-serialize without recomputing the manifest hash -> tampered.
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")

    runner = _build_runner(tmp_path, monkeypatch, write_candidate_manifest=False)
    with pytest.raises(RuntimeError, match="frozen candidate manifest"):
        runner.run(holdout_enabled=True)


def test_holdout_candidate_manifest_is_verified_before_any_holdout_execution(
    tmp_path, monkeypatch,
):
    _build_runner(tmp_path, monkeypatch)
    calls = {"backtests": 0, "manifest_loads": 0}

    real_load = campaign_module.load_candidate_manifest

    def counting_load(*args, **kwargs):
        calls["manifest_loads"] += 1
        return real_load(*args, **kwargs)

    def counting_backtest(candles, config, btc_candles=None, start_time=None,
                          end_time=None, cost_scenario=None, fold_index=0, asset=""):
        calls["backtests"] += 1
        if calls["backtests"] > 0 and calls["manifest_loads"] == 0:
            raise AssertionError("holdout backtest executed before manifest load")
        return real_run_fold_backtest(
            candles, config, btc_candles=btc_candles, start_time=start_time,
            end_time=end_time, cost_scenario=cost_scenario, fold_index=fold_index,
            asset=asset,
        )

    monkeypatch.setattr(campaign_module, "load_candidate_manifest", counting_load)
    monkeypatch.setattr(campaign_module, "run_fold_backtest", counting_backtest)

    runner = _build_runner(tmp_path, monkeypatch)
    result = runner.run(holdout_enabled=True)

    assert result["status"] == "CAMPAIGN_COMPLETE"
    assert calls["manifest_loads"] >= 1
    holdout = [r for r in _all_records(tmp_path) if r["is_holdout"]]
    assert len(holdout) == EXPECTED_HOLDOUT_UNITS

"""Crash-recovery and resume tests for the deterministic campaign store.

Covers BRAIN-004 (manifest-derived resume, no counter trust) and BRAIN-005
(bounded shards, fail-closed oversized rows) plus the BRAIN-003 phase 1
holdout-skip gate. All tests run offline with synthetic fixtures only; no
fixture is ever presented as market history.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

import breakout_research.campaign as campaign_module
from breakout_research.campaign import _data_manifest_hash, _read_json_file
from breakout_research.candidate_freeze import save_candidate_manifest
from breakout_research.backtest.shards import ResultStore, ResultStoreError, compute_experiment_id
from breakout_research.backtest.backtester import run_fold_backtest as real_run_fold_backtest
from breakout_research.config import (
    Candle, StrategyConfig, EntryRule, ConfirmationMode, TrendFilter, ExitType,
    CostScenario,
)
from breakout_research.data.fetcher import HOUR_MS
import breakout_research.pilot_gate_validator as pilot_gate_validator

def _data_manifest_with_provenance(spec_hash, assets):
    """Provenance-complete manifest: required by the BRAIN-002 startup gate."""
    return {
        "spec_hash": spec_hash,
        "provenance_ok": True,
        "data_min_history_ok": True,
        "assets": {
            symbol: {
                **entry,
                "fallback_used": False,
                "fallback_source": "real",
                "spec_hash": spec_hash,
            }
            for symbol, entry in assets.items()
        },
    }


def _write_valid_authorization_env(tmp_path, spec, universe, data_manifest,
                                   code_hash="test-code-hash"):
    """Write evidence-only pilot evidence and the independent authorization artifact.

    Mirrors the production BRAIN-002 contract: the pilot never self-authorizes
    (pilot_passed/campaign_authorized are False) and a separate validator
    produces the authorization artifact that campaign startup revalidates.
    """
    pilot = {
        "protocol_version": spec["protocol_version"],
        "specification_hash": spec["specification_hash"],
        "code_hash": code_hash,
        "pilot_completed_at": "2026-01-01T00:00:00+00:00",
        "assets_tested": len(universe.get("eligible_assets", [])),
        "configs_tested": len(CFGS),
        "total_results": len(universe.get("eligible_assets", [])) * len(CFGS),
        "pilot_passed": False,
        "campaign_authorized": False,
        "evidence": {
            "protocol_hash": spec["specification_hash"],
            "code_hash": code_hash,
            "spec_hash": spec["specification_hash"],
            "universe_manifest_hash": pilot_gate_validator._sha256_canonical(universe),
            "data_manifest_hash": pilot_gate_validator._sha256_canonical(data_manifest),
            "asset_data_hashes": {
                symbol: entry.get("content_hash")
                for symbol, entry in data_manifest.get("assets", {}).items()
            },
            "data_provenance_ok": True,
            "data_min_history_ok": True,
            "pilot_run_results": {
                "all_tests_passed": True,
                "test_failures": 0,
                "remote_persistence_verified": True,
                "synthetic_data_used": False,
            },
            "checkpoint_state": {
                "protocol_hash": spec["specification_hash"],
                "code_hash": code_hash,
            },
            "test_reports": ["tests/test_data_fetcher.py"],
        },
    }
    _write(tmp_path / "research_state/pilot_evidence.json", pilot)
    pilot_gate_validator.authorize_campaign()


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
    cfg("cfg_test_0001"),
    cfg("cfg_test_0002", entry_rule=EntryRule.CLOSE_BREAKOUT, entry_lookback=24,
        buffer_atr_multiple=0.1, confirmation=ConfirmationMode.TWO_CLOSE,
        trend_filter=TrendFilter.ASSET_EMA_168, exit=ExitType.ATR_TRAIL_2_5),
]

SPEC = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "universe": {"min_history_years": 3},
    "data": {"interval": "1h", "max_retries": 1, "backoff_seconds": 0},
    "costs": {"baseline": {"taker_fee_bps": 10, "slippage_bps": 5}, "scenarios": [1.0, 2.0]},
    "folds": {"development_fraction": 0.8, "holdout_fraction": 0.2,
              "validation_windows": 4, "window_fractions": [0.4, 0.5, 0.6, 0.7]},
    "checkpointing": {"batch_size": 4, "atomic_writes": True, "verify_on_resume": True, "max_retries": 3},
}

UNIVERSE = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "eligible_assets": [
        {"symbol": "BTCUSDT", "rank": 1, "binance_spot_verified": True},
        {"symbol": "ETHUSDT", "rank": 2, "binance_spot_verified": True},
    ],
}

CONFIG_MANIFEST = {
    "protocol_version": "v1",
    "specification_hash": "test-spec-hash",
    "configurations": [c.to_dict() for c in CFGS],
}

EXPECTED_VALIDATION_UNITS = 2 * 2 * 4 * 2  # assets x configs x validation folds x costs
EXPECTED_FULL_UNITS = 2 * 2 * 4 * 2 + 2 * 1 * 1 * 2  # validation + one frozen candidate per asset on holdout


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_runner(tmp_path, monkeypatch, batch_size=4):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(campaign_module, "load_research_spec", lambda: SPEC)
    monkeypatch.setattr(campaign_module, "load_universe_manifest", lambda: UNIVERSE)
    monkeypatch.setattr(campaign_module, "load_config_manifest", lambda: CONFIG_MANIFEST)
    monkeypatch.setattr(campaign_module, "compute_code_hash", lambda: "test-code-hash")

    _write(tmp_path / "configs/research_v1.json", SPEC)
    _write(tmp_path / "research/universe_manifest.json", UNIVERSE)
    _write(tmp_path / "research/config_manifest.json", CONFIG_MANIFEST)
    data_manifest = _data_manifest_with_provenance(SPEC["specification_hash"], {
        "BTCUSDT": {"content_hash": "data-hash-btc-0123456789abcdef"},
        "ETHUSDT": {"content_hash": "data-hash-eth-0123456789abcdef"},
    })
    _write(tmp_path / "research/data_manifest.json", data_manifest)
    _write_valid_authorization_env(tmp_path, SPEC, UNIVERSE, data_manifest)
    save_candidate_manifest({
        "frozen": True,
        "candidates": {
            "BTCUSDT": {"config_id": "cfg_test_0001", "parameters": {}, "freeze_commit": "test"},
            "ETHUSDT": {"config_id": "cfg_test_0001", "parameters": {}, "freeze_commit": "test"},
        },
    }, str(tmp_path / "research/candidate_manifest.json"))

    candles = make_candles()
    def loader(symbol):
        if symbol not in ("BTCUSDT", "ETHUSDT"):
            raise KeyError(symbol)
        return list(candles)
    monkeypatch.setattr(campaign_module, "load_or_fetch_asset_data", loader)

    runner = campaign_module.CampaignRunner()
    runner.batch_size = batch_size
    return runner


def _campaign_id(tmp_path):
    data_manifest = _read_json_file(str(tmp_path / "research/data_manifest.json"))
    return hashlib.sha256(
        f"{SPEC['specification_hash']}:test-code-hash:{_data_manifest_hash(data_manifest)}".encode()
    ).hexdigest()


def _reject_nonstandard_json_constant(value):
    raise ValueError(f"Non-standard JSON constant in result shard: {value}")


def _all_records(tmp_path):
    campaign_id = _campaign_id(tmp_path)
    shard_dir = tmp_path / SHARD_ROOT / campaign_id
    records = []
    if shard_dir.is_dir():
        for path in sorted(shard_dir.glob("shard_*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line, parse_constant=_reject_nonstandard_json_constant))
    return records


def _shard_bytes(tmp_path):
    campaign_id = _campaign_id(tmp_path)
    shard_dir = tmp_path / SHARD_ROOT / campaign_id
    total = 0
    if shard_dir.is_dir():
        for path in shard_dir.glob("shard_*.jsonl"):
            total += path.stat().st_size
    return total


def test_validation_mode_never_writes_holdout_rows(tmp_path, monkeypatch):
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


def test_full_mode_includes_holdout_once(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch)
    result = runner.run(holdout_enabled=True)

    assert result["status"] == "CAMPAIGN_COMPLETE"
    assert result["total_experiments"] == EXPECTED_FULL_UNITS

    records = _all_records(tmp_path)
    holdout = [r for r in records if r["is_holdout"]]
    assert len(holdout) == 2 * 1 * 2  # frozen assets(candidates) x costs
    assert all(r["fold_index"] == 4 for r in holdout)
    ids = [r["experiment_id"] for r in records]
    assert len(ids) == len(set(ids))


def test_resume_skips_completed_units_is_idempotent(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch)
    first = runner.run(holdout_enabled=False)
    assert first["executed_this_session"] == EXPECTED_VALIDATION_UNITS

    bytes_before = _shard_bytes(tmp_path)
    records_before = _all_records(tmp_path)

    second = runner.run(holdout_enabled=False)
    # Nothing left to run: zero new executions, same shard bytes, same IDs.
    assert second["executed_this_session"] == 0
    assert second["total_experiments"] == EXPECTED_VALIDATION_UNITS
    assert _shard_bytes(tmp_path) == bytes_before
    assert _all_records(tmp_path) == records_before

    # Legacy monolith is never written by the campaign.
    assert not (tmp_path / "research/results.jsonl").exists()


def test_crash_injection_at_each_boundary_resumes_without_loss_or_duplicates(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch)
    state = {"calls": 0}

    def crashing_backtest(candles, config, btc_candles=None, start_time=None, end_time=None,
                          cost_scenario=None, initial_capital=10000.0, fold_index=0, asset=""):
        state["calls"] += 1
        if state["calls"] == 5:  # crash mid-first-batch (batch_size=4)
            raise RuntimeError("simulated crash at call 5")
        return real_run_fold_backtest(
            candles, config, btc_candles=btc_candles, start_time=start_time, end_time=end_time,
            cost_scenario=cost_scenario, fold_index=fold_index, asset=asset,
        )
    monkeypatch.setattr(campaign_module, "run_fold_backtest", crashing_backtest)

    with pytest.raises(RuntimeError, match="simulated crash at call 5"):
        runner.run(holdout_enabled=False)

    # Four records committed before the crash; checkpoint says nothing trusted.
    records_after_crash = _all_records(tmp_path)
    assert len(records_after_crash) == 4

    # Fresh runner (simulates a new session), resume derives position from shards.
    runner2 = _build_runner(tmp_path, monkeypatch)
    monkeypatch.setattr(campaign_module, "run_fold_backtest", real_run_fold_backtest)
    result = runner2.run(holdout_enabled=False)

    assert result["status"] == "CAMPAIGN_PARTIAL"
    assert result["executed_this_session"] == EXPECTED_VALIDATION_UNITS - 4
    records = _all_records(tmp_path)
    assert len(records) == EXPECTED_VALIDATION_UNITS
    ids = [r["experiment_id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate experiment IDs after crash resume"


def test_checkpoint_counter_tampering_derives_position_from_manifest(tmp_path, monkeypatch):
    runner = _build_runner(tmp_path, monkeypatch)
    state = {"calls": 0}

    def crashing_backtest(candles, config, btc_candles=None, start_time=None, end_time=None,
                          cost_scenario=None, initial_capital=10000.0, fold_index=0, asset=""):
        state["calls"] += 1
        if state["calls"] == 9:
            raise RuntimeError("simulated crash at call 9")
        return real_run_fold_backtest(
            candles, config, btc_candles=btc_candles, start_time=start_time, end_time=end_time,
            cost_scenario=cost_scenario, fold_index=fold_index, asset=asset,
        )
    monkeypatch.setattr(campaign_module, "run_fold_backtest", crashing_backtest)
    with pytest.raises(RuntimeError):
        runner.run(holdout_enabled=False)
    assert len(_all_records(tmp_path)) == 8  # two full batches of 4

    # Tamper: wildly wrong counters and cursors, hashes still match.
    _write(tmp_path / "research_state/checkpoint.json", {
        "protocol_hash": SPEC["specification_hash"],
        "code_hash": "test-code-hash",
        "current_asset_index": 99,
        "current_config_index": 99,
        "current_fold_index": 99,
        "current_cost_index": 99,
        "completed_records": 999999,
        "last_verified_record": 0,
        "next_unit": {"asset_index": 99, "config_index": 99, "fold_index": 99, "cost_index": 99},
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "pilot_completed": True,
        "pilot_passed": True,
    })

    runner2 = _build_runner(tmp_path, monkeypatch)
    monkeypatch.setattr(campaign_module, "run_fold_backtest", real_run_fold_backtest)
    result = runner2.run(holdout_enabled=False)

    assert result["executed_this_session"] == EXPECTED_VALIDATION_UNITS - 8
    records = _all_records(tmp_path)
    assert len(records) == EXPECTED_VALIDATION_UNITS
    ids = [r["experiment_id"] for r in records]
    assert len(ids) == len(set(ids))


def test_stale_checkpoint_code_hash_is_rejected(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch)
    _write(tmp_path / "research_state/checkpoint.json", {
        "protocol_hash": SPEC["specification_hash"],
        "code_hash": "stale-code-hash",
        "current_asset_index": 0,
        "current_config_index": 0,
        "current_fold_index": 0,
        "current_cost_index": 0,
        "completed_records": 0,
        "last_verified_record": 0,
        "next_unit": {},
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "pilot_completed": True,
        "pilot_passed": True,
    })
    runner = _build_runner(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="code hash mismatch"):
        runner.run(holdout_enabled=False)


def test_experiment_ids_bind_to_data_hash(tmp_path, monkeypatch):
    _build_runner(tmp_path, monkeypatch)
    base = compute_experiment_id(
        spec_hash="spec", code_hash="code", data_hash="data-a",
        asset="BTCUSDT", config_id="cfg_1", fold_index=0, start_time=1, end_time=2,
        is_holdout=False, cost_multiplier=1.0,
    )
    changed_data = compute_experiment_id(
        spec_hash="spec", code_hash="code", data_hash="data-b",
        asset="BTCUSDT", config_id="cfg_1", fold_index=0, start_time=1, end_time=2,
        is_holdout=False, cost_multiplier=1.0,
    )
    changed_asset = compute_experiment_id(
        spec_hash="spec", code_hash="code", data_hash="data-a",
        asset="ETHUSDT", config_id="cfg_1", fold_index=0, start_time=1, end_time=2,
        is_holdout=False, cost_multiplier=1.0,
    )
    assert base != changed_data
    assert base != changed_asset
    assert compute_experiment_id(
        spec_hash="spec", code_hash="code", data_hash="data-a",
        asset="BTCUSDT", config_id="cfg_1", fold_index=0, start_time=1, end_time=2,
        is_holdout=False, cost_multiplier=1.0,
    ) == base  # deterministic


def test_oversized_row_is_rejected_fail_closed(tmp_path):
    _write(tmp_path / "research/data_manifest.json", {
        "assets": {
            "BTCUSDT": {"content_hash": "data-hash-btc"},
        },
    })
    data_manifest = _read_json_file(str(tmp_path / "research/data_manifest.json"))
    store = ResultStore(
        campaign_id="test-campaign",
        spec_hash=SPEC["specification_hash"],
        code_hash="test-code-hash",
        data_manifest_hash=_data_manifest_hash(data_manifest),
        shard_root=str(tmp_path / SHARD_ROOT),
        manifest_path=str(tmp_path / MANIFEST_PATH),
    )
    big_record = {"experiment_id": "oversized", "equity_curve": [0.0] * (5 * 1024 * 1024)}
    with pytest.raises(ResultStoreError, match="exceeds shard ceiling"):
        store.append("oversized", big_record)
    # Nothing committed: no shard files were created.
    shard_dir = tmp_path / SHARD_ROOT / "test-campaign"
    assert not shard_dir.is_dir() or not any(shard_dir.iterdir())

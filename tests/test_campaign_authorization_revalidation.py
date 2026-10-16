"""Campaign must revalidate authorization at startup (BRAIN-002)."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from breakout_research import pilot_gate_validator, campaign


def _setup_valid(tmpdir: Path):
    spec = {
        "protocol_version": "v1",
        "specification_hash": "abc123",
        "code_hash": "code456",
        "folds": {"validation_windows": 4, "development_fraction": 0.8, "holdout_fraction": 0.2, "window_fractions": [0.0, 0.2, 0.4, 0.6]},
        "checkpointing": {"batch_size": 100},
        "costs": {"scenarios": [1.0]}, "entry_rule": "close_breakout",
    }
    um = {
        "eligible_assets": [
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "status": "TRADING",
                "market_cap_rank": 1,
            }
        ],
        "universe_id": "test-universe",
    }
    dm = {
        "spec_hash": "abc123",
        "data_min_history_ok": True,
        "provenance_ok": True,
        "assets": {
            "BTCUSDT": {
                "fallback_used": False,
                "content_hash": "content1234567890",
                "spec_hash": "abc123",
                "observed_candles": 26280,
                "expected_candles": 26280,
            }
        },
    }
    cm = {
        "configurations": [
            {
                "config_id": "cfg_1",
                "strategy": "breakout",
                "entry_rule": "close_breakout",
                "entry_lookback": 20,
                "buffer_atr_multiple": 0.0,
                "confirmation": "two_close",
                "trend_filter": "none",
                "exit": "atr_trail_2.5",
                "atr_period": 14,
                "atr_multiple": 2.0,
                "confirm_bars": 2,
                "ema_filter": True,
                "channel_exit": False,
                "trailing_stop_atr_multiple": 3.0,
                "content_hash": "hash1"
            }
        ]
    }
    pilot = {
        "protocol_version": "v1",
        "specification_hash": "abc123",
        "code_hash": "code456",
        "pilot_completed_at": "2026-01-01T00:00:00+00:00",
        "assets_tested": 1,
        "configs_tested": 24,
        "total_results": 24,
        "pilot_passed": False,
        "campaign_authorized": False,
        "evidence": {
            "protocol_hash": "abc123",
            "code_hash": "code456",
            "spec_hash": "abc123",
            "universe_manifest_hash": pilot_gate_validator._sha256_canonical(um),
            "data_manifest_hash": pilot_gate_validator._sha256_canonical(dm),
            "asset_data_hashes": {"BTCUSDT": "content1234567890"},
            "data_provenance_ok": True,
            "data_min_history_ok": True,
            "pilot_run_results": {
                "all_tests_passed": True,
                "test_failures": 0,
                "remote_persistence_verified": True,
                "synthetic_data_used": False,
            },
            "checkpoint_state": {
                "protocol_hash": "abc123",
                "code_hash": "code456",
            },
            "test_reports": ["tests/test_data_fetcher.py"],
        },
    }
    (tmpdir / "configs").mkdir()
    (tmpdir / "research").mkdir()
    (tmpdir / "research_state").mkdir()
    (tmpdir / "configs/research_v1.json").write_text(json.dumps(spec))
    (tmpdir / "configs/universe_v1.json").write_text(json.dumps(um))
    (tmpdir / "configs/configurations_v1.json").write_text(json.dumps(cm))
    (tmpdir / "research/universe_manifest.json").write_text(json.dumps(um))
    (tmpdir / "research/data_manifest.json").write_text(json.dumps(dm))
    (tmpdir / "research/config_manifest.json").write_text(json.dumps(cm))
    (tmpdir / "research_state/pilot_evidence.json").write_text(json.dumps(pilot))
    return pilot, spec, dm, um, cm


def test_campaign_blocks_if_authorization_artifact_missing():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _setup_valid(tdp)
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            pilot_gate_validator.authorize_campaign()
            (tdp / "research_state/campaign_authorization.json").unlink()
            c = campaign.CampaignRunner()
            with pytest.raises(RuntimeError):
                c._verify_pilot_gate(c.protocol_hash, c.code_hash)
        finally:
            os.chdir(old_cwd)


def test_campaign_blocks_if_authorization_not_authorized():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _setup_valid(tdp)
        setup[0]["evidence"]["data_provenance_ok"] = False
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup[0]))
        pilot_gate_validator.authorize_campaign()
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            c = campaign.CampaignRunner()
            with pytest.raises(RuntimeError):
                c._verify_pilot_gate(c.protocol_hash, c.code_hash)
        finally:
            os.chdir(old_cwd)


def test_campaign_blocks_if_artifact_stale_after_mutation():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _setup_valid(tdp)
        pilot_gate_validator.authorize_campaign()
        dm = json.loads((tdp / "research/data_manifest.json").read_text())
        dm["assets"]["BTCUSDT"]["content_hash"] = "tampered"
        (tdp / "research/data_manifest.json").write_text(json.dumps(dm))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            c = campaign.CampaignRunner()
            with pytest.raises(RuntimeError):
                c._verify_pilot_gate(c.protocol_hash, c.code_hash)
        finally:
            os.chdir(old_cwd)

"""Tests for BRAIN-002 independent pilot authorization."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from breakout_research import pilot_gate_validator
from breakout_research.pilot_gate_validator import (
    authorize_campaign,
    load_authorization,
    validate_pilot_evidence,
)


def _make_minimal_valid_pilot(tmpdir: Path) -> dict:
    # Create minimal valid pilot evidence
    spec = {
        "protocol_version": "v1",
        "specification_hash": "abc123",
    }
    um = {"universe": {}}
    dm = {
        "spec_hash": "abc123",
        "data_min_history_ok": True,
        "provenance_ok": True,
        "assets": {
            "BTCUSDT": {
                "fallback_used": False,
                "content_hash": "content1234567890",
                "spec_hash": "abc123",
            }
        },
    }
    pilot = {
        "protocol_version": "v1",
        "specification_hash": "abc123",
        "code_hash": "code456",
        "pilot_completed_at": "2026-01-01T00:00:00+00:00",
        "assets_tested": 1,
        "configs_tested": 24,
        "total_results": 24,
        "pilot_passed": False,  # must be False (evidence-only)
        "campaign_authorized": False,  # must be False
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
    return {"spec": spec, "um": um, "dm": dm, "pilot": pilot}


def test_validator_rejects_pilot_with_pilot_passed_true():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _make_minimal_valid_pilot(tdp)
        setup["pilot"]["pilot_passed"] = True  # forged
        (tdp / "configs").mkdir()
        (tdp / "research").mkdir()
        (tdp / "research_state").mkdir()
        (tdp / "configs/research_v1.json").write_text(json.dumps(setup["spec"]))
        (tdp / "research/universe_manifest.json").write_text(json.dumps(setup["um"]))
        (tdp / "research/data_manifest.json").write_text(json.dumps(setup["dm"]))
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup["pilot"]))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            ok, reasons, pilot = validate_pilot_evidence("research_state/pilot_evidence.json")
            assert not ok
            assert any("pilot_passed" in r for r in reasons)
        finally:
            os.chdir(old_cwd)


def test_validator_rejects_pilot_with_campaign_authorized_true():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _make_minimal_valid_pilot(tdp)
        setup["pilot"]["campaign_authorized"] = True  # forged
        (tdp / "configs").mkdir()
        (tdp / "research").mkdir()
        (tdp / "research_state").mkdir()
        (tdp / "configs/research_v1.json").write_text(json.dumps(setup["spec"]))
        (tdp / "research/universe_manifest.json").write_text(json.dumps(setup["um"]))
        (tdp / "research/data_manifest.json").write_text(json.dumps(setup["dm"]))
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup["pilot"]))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            ok, reasons, pilot = validate_pilot_evidence()
            assert not ok
            assert any("campaign_authorized" in r for r in reasons)
        finally:
            os.chdir(old_cwd)


def test_validator_rejects_synthetic_data():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _make_minimal_valid_pilot(tdp)
        setup["dm"]["assets"]["BTCUSDT"]["fallback_used"] = True  # synthetic
        (tdp / "configs").mkdir()
        (tdp / "research").mkdir()
        (tdp / "research_state").mkdir()
        (tdp / "configs/research_v1.json").write_text(json.dumps(setup["spec"]))
        (tdp / "research/universe_manifest.json").write_text(json.dumps(setup["um"]))
        (tdp / "research/data_manifest.json").write_text(json.dumps(setup["dm"]))
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup["pilot"]))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            ok, reasons, pilot = validate_pilot_evidence()
            assert not ok
            assert any("fallback_used" in r or "synthetic" in r for r in reasons)
        finally:
            os.chdir(old_cwd)


def test_authorize_campaign_writes_artifact_and_blocks_on_forgeries():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _make_minimal_valid_pilot(tdp)
        setup["pilot"]["pilot_passed"] = True  # forged
        (tdp / "configs").mkdir()
        (tdp / "research").mkdir()
        (tdp / "research_state").mkdir()
        (tdp / "configs/research_v1.json").write_text(json.dumps(setup["spec"]))
        (tdp / "research/universe_manifest.json").write_text(json.dumps(setup["um"]))
        (tdp / "research/data_manifest.json").write_text(json.dumps(setup["dm"]))
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup["pilot"]))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            res = authorize_campaign()
            assert res["authorized"] is False
            art = load_authorization()
            assert art["authorized"] is False
        finally:
            os.chdir(old_cwd)


def test_validator_accepts_valid_evidence_only():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        setup = _make_minimal_valid_pilot(tdp)
        (tdp / "configs").mkdir()
        (tdp / "research").mkdir()
        (tdp / "research_state").mkdir()
        (tdp / "configs/research_v1.json").write_text(json.dumps(setup["spec"]))
        (tdp / "research/universe_manifest.json").write_text(json.dumps(setup["um"]))
        (tdp / "research/data_manifest.json").write_text(json.dumps(setup["dm"]))
        (tdp / "research_state/pilot_evidence.json").write_text(json.dumps(setup["pilot"]))
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            ok, reasons, pilot = validate_pilot_evidence()
            assert ok, f"reasons: {reasons}"
            res = authorize_campaign()
            assert res["authorized"] is True
        finally:
            os.chdir(old_cwd)

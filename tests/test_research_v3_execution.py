"""Tests for the preregistered v3 execution protocol (configs/research_v3_execution.json)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V3_EXEC = REPO_ROOT / "configs" / "research_v3_execution.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v3_execution", REPO_ROOT / "scripts" / "verify_research_v3_execution.py")


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present")
    return json.loads(path.read_text(encoding="utf-8"))


def test_specification_hash_recomputes():
    spec = _load(SPEC_V3_EXEC)
    assert spec["specification_hash"] == verifier.compute_hash(spec)


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["ok"] is True
    assert report["failures"] == []


def test_authorizes_at_most_one_logical_run():
    spec = _load(SPEC_V3_EXEC)
    assert spec["resource_and_attempt_bounds"]["max_logical_runs"] == 1


def test_scope_is_validated_six():
    spec = _load(SPEC_V3_EXEC)
    assert spec["evaluation_scope"]["count"] == 6
    assert spec["evaluation_scope"]["constituents"] == ["SHIBUSDT", "QNTUSDT", "AAVEUSDT", "WLDUSDT", "PEPEUSDT", "ICPUSDT"]
    assert spec["evaluation_scope"]["superseded_twenty_asset_batch_must_not_be_used"] is True


def test_hard_boundaries():
    spec = _load(SPEC_V3_EXEC)
    b = spec["selection_data_boundary"]
    assert b["v1_holdout_reuse_forbidden"] is True
    assert b["v2_confirmatory_window_reuse_forbidden"] is True
    assert b["v1_cycle0_units_mixed_forbidden"] is True
    assert b["v2_cycle_units_mixed_forbidden"] is True
    assert b["v3_confirmatory_window_read_during_selection_forbidden"] is True


def test_code_hash_constraint_outside_hashed_set():
    spec = _load(SPEC_V3_EXEC)
    c = spec["code_hash_constraint"]
    assert c["authorized_code_hash"] == "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    assert c["v3_execution_must_live_outside_hashed_set"] is True
    assert c["v3_execution_namespace"] == "src/v3_campaign/"
    assert "src/v3_campaign/" in c["chosen_approach"]


def test_separate_namespaces_no_writes_to_v1_v2():
    spec = _load(SPEC_V3_EXEC)
    r = spec["v3_result_layout"]
    assert r["writes_into_v1_forbidden"] is True
    assert r["writes_into_v2_forbidden"] is True
    assert r["campaign_id"] == "v3-campaign"


def test_selection_rule_inherited_unchanged():
    spec = _load(SPEC_V3_EXEC)
    assert spec["selection_rule"]["inherit_from_v1_unchanged"] is True


def test_authorizes_nothing_to_run():
    spec = _load(SPEC_V3_EXEC)
    assert spec["specification_status"] == "PREREGISTERED_EXECUTION_PROTOCOL_ONLY"

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "publish_v6_selected_configurations.py"
SPEC = importlib.util.spec_from_file_location("publish_v6_selected_configurations", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_manifest_keeps_selected_and_nonselected_assets_explicit():
    selections = MODULE.build_selections(
        ["AAAUSDT", "BBBUSDT"],
        {
            "AAAUSDT": {"config_id": "cfg_0001", "status": "SELECTED", "economic_status": "PASS"},
            "BBBUSDT": {"config_id": None, "status": "NO_CANDIDATE", "economic_status": None},
        },
        ["cfg_0001", "cfg_0002"],
    )
    assert selections["AAAUSDT"]["selected"] is True
    assert selections["AAAUSDT"]["config_id"] == "cfg_0001"
    assert selections["BBBUSDT"]["selected"] is False
    assert selections["BBBUSDT"]["config_id"] is None
    assert selections["BBBUSDT"]["reason"] == "NO_CANDIDATE_SURVIVED_THE_UNCHANGED_V1_SELECTION_RULE"


def test_manifest_refuses_a_widened_or_narrowed_selection_scope():
    import pytest
    with pytest.raises(MODULE.ManifestPublicationError):
        MODULE.build_selections(
            ["AAAUSDT", "BBBUSDT"],
            {"AAAUSDT": {"config_id": "cfg_0001"}},
            ["cfg_0001"],
        )
    with pytest.raises(MODULE.ManifestPublicationError):
        MODULE.build_selections(
            ["AAAUSDT"],
            {"AAAUSDT": {"config_id": "cfg_unknown"}},
            ["cfg_0001"],
        )


def test_manifest_hash_is_deterministic_and_excludes_only_its_own_field():
    payload = {"artifact": "v6_selected_configurations_manifest", "value": 7}
    first = MODULE.manifest_hash(payload)
    second = MODULE.manifest_hash({**payload, "manifest_hash": "placeholder"})
    assert first == second

"""Tests for the preregistered v3 specification (``configs/research_v3.json``).

The v3 specification is a design artifact: it freezes the rules for a third
versioned market-cap universe, the eligibility validation of every candidate
and the confirmatory-window boundary *before* any v3 data is retrieved. These
tests prove that

* the specification hash recomputes from the document itself, so any edit to a
  frozen rule is detectable;
* every block v3 inherits from v1 is byte-equal to the v1 block, so the
  2,304-configuration grid, the costs, the folds, the selection rule and the
  status vocabulary cannot drift between protocol versions;
* the specification smuggles in no asset membership;
* the snapshot window, the expansion program and the eligibility rules are
  pinned;
* execution is not authorized while the data prerequisites are outstanding;
* the v1 campaign authorization is untouched by the v3 specification.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V1 = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V3 = REPO_ROOT / "configs" / "research_v3.json"

INHERITED_BLOCKS = (
    "strategy_grid",
    "costs",
    "execution",
    "folds",
    "selection",
    "pilot",
    "metrics",
    "baselines",
    "fixed_breakout_baseline",
    "status",
    "checkpointing",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v3_spec", REPO_ROOT / "scripts" / "verify_research_v3_spec.py")
manifests_verifier = _load_module(
    "verify_research_v3_manifests", REPO_ROOT / "scripts" / "verify_research_v3_manifests.py"
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_specification_hash_recomputes_from_the_document():
    spec = _load(SPEC_V3)
    assert spec["specification_hash"] == verifier.compute_specification_hash(spec)


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_verifier_detects_a_tampered_rule():
    spec = _load(SPEC_V3)
    tampered = json.loads(json.dumps(spec))
    tampered["strategy_grid"]["entry_lookback"] = [12, 24, 48]
    assert verifier.compute_specification_hash(tampered) != spec["specification_hash"]


def test_inherited_blocks_are_identical_to_v1():
    v1 = _load(SPEC_V1)
    v3 = _load(SPEC_V3)
    for block in INHERITED_BLOCKS:
        assert v3[block] == v1.get(block), block


def test_grid_still_enumerates_2304_combinations():
    v3 = _load(SPEC_V3)
    grid = v3["strategy_grid"]
    product = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        product *= len(values)
    assert product == 2304
    assert grid["total_combinations"] == 2304


def test_specification_contains_no_asset_membership():
    v3 = _load(SPEC_V3)
    assert "eligible_assets" not in v3["universe"]
    text = verifier.canonical(v3)
    for symbol in ("TAOUSDT", "SHIBUSDT", "AAVEUSDT", "QNTUSDT", "PEPEUSDT", "WLDUSDT",
                   "ICPUSDT", "CROUSDT", "WLFIUSDT", "ASTERUSDT"):
        assert f'"{symbol}"' not in text, symbol


def test_the_snapshot_window_is_pinned():
    v3 = _load(SPEC_V3)
    retrieval = v3["universe"]["snapshot_retrieval"]
    assert retrieval["not_before_utc"] == "2026-10-20T11:45:00Z"
    assert retrieval["deadline_utc"] == "2026-10-27T11:45:00Z"
    assert retrieval["raw_response_required"] is True
    assert "never re-retrieved" in retrieval["prior_snapshots_are_not_re_retrieved"]


def test_the_expansion_program_requires_the_append_only_log():
    v3 = _load(SPEC_V3)
    program = v3["expansion_program"]
    assert program["log_path"] == "research/v_universe_expansion_log.json"
    assert program["log_mode"] == "append_only_hash_chain"
    assert program["cadence"]["mode"] == "bounded_cadence_not_polling"
    assert program["cadence"]["minimum_interval_between_passes"] == "P7D"
    assert program["cadence"]["polling_forbidden"]
    assert program["cadence"]["no_new_eligible_names_state"] == "AWAITING_NEW_CANDIDATES"


def test_the_expansion_floor_is_the_v2_floor_and_is_recomputable():
    v3 = _load(SPEC_V3)
    floor = v3["universe"]["expansion_scope"]["prior_universe_floor"]
    assert floor["source_universe_version"] == "v2"
    assert floor["source_manifest_path"] == "research/universe_manifest_v2.json"
    assert floor["comparison"] == "strictly_less_than"
    v2 = _load(REPO_ROOT / "research" / "universe_manifest_v2.json")
    assets = v2.get("eligible_assets") or []
    lowest = min(assets, key=lambda item: float(item.get("market_cap_usd") or 0))
    assert lowest.get("market_cap_usd") == floor["floor_market_cap_usd"]


def test_the_eligibility_rules_forbid_a_substitute():
    v3 = _load(SPEC_V3)
    validation = v3["universe"]["eligibility_validation"]
    assert validation["candle_history"]["min_candles"] == 26280
    assert validation["candle_history"]["interval"] == "1h"
    assert validation["candle_history"]["closed_candles_only"] is True
    assert validation["candle_history"]["no_interpolation"] is True
    assert validation["binance_spot_verification"]["required"] is True
    assert "never substitute" in validation["failure_handling"].lower()


def test_the_holdout_rules_forbid_the_v1_and_v2_windows():
    v3 = _load(SPEC_V3)
    holdout = v3["holdout"]
    assert holdout["v1_holdout_reuse"] == "forbidden"
    assert "2027-01-17T22:00:00Z" in holdout["v2_confirmatory_window"]["note"]
    assert holdout["v2_confirmatory_window"]["reuse_by_v3"] == "forbidden"
    assert holdout["v2_confirmatory_window"]["read_by_v3"] == "forbidden"
    window = holdout["v3_confirmatory_window"]
    assert window["min_hours"] == 2160
    assert window["single_use"] is True
    assert window["overlap_with_v1_holdout"] == "forbidden"
    assert window["overlap_with_v2_confirmatory_window"] == "forbidden"


def test_prerequisites_are_p1_to_p6():
    v3 = _load(SPEC_V3)
    prerequisites = {item["id"]: item for item in v3["prerequisites"]}
    assert set(prerequisites) == {"P1", "P2", "P3", "P4", "P5", "P6"}
    assert prerequisites["P1"]["status"] == "SATISFIED_BY_THIS_SPEC"
    for pid in ("P2", "P3", "P4", "P5", "P6"):
        assert prerequisites[pid]["status"] == "OUTSTANDING", pid


def test_execution_is_not_authorized_by_the_specification():
    v3 = _load(SPEC_V3)
    assert v3["authorization"]["execution_authorized"] is False
    prohibited = v3["authorization"]["not_authorized_by_this_specification_alone"]
    assert any("confirmatory" in item for item in prohibited)
    assert any("campaign" in item for item in prohibited)


def test_the_stale_data_manifest_reference_is_corrected_by_reference():
    """The immutable specification still names the v2 data manifest.

    ``universe.eligibility_validation.data_integrity.data_manifest`` was copied
    from the v2 specification and names ``research/data_manifest_v2.json``
    instead of the v3 manifest. The specification is immutable, so the
    correction is owed as a versioned amendment; the manifest verifier must
    fail when no verified amendment supersedes the stale reference.
    """
    v3 = _load(SPEC_V3)
    integrity = v3["universe"]["eligibility_validation"]["data_integrity"]
    report = manifests_verifier.verify(REPO_ROOT)
    if integrity.get("data_manifest") == "research/data_manifest_v3.json":
        assert report["specification_amendment"] is None
    else:
        assert report["specification_amendment"] == "configs/research_v3_spec_amendment_1.json"
        assert report["ok"] is True
        assert any("data_manifest" in item for item in report["warnings"])


def test_the_v1_campaign_authorization_is_untouched():
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    v1 = _load(SPEC_V1)
    assert authorization["protocol_version"] == "v1"
    assert authorization["specification_hash"] == v1["specification_hash"]
    assert authorization["authorized"] is True

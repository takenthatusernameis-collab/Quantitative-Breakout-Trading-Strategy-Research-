"""Tests for the preregistered v2 specification (``configs/research_v2.json``).

The v2 specification is a design artifact: it freezes the rules for a second
versioned market-cap universe and for a fresh confirmatory-holdout protocol
*before* any v2 data is retrieved. These tests prove that

* the specification hash recomputes from the document itself, so any edit to
  a frozen rule is detectable;
* every block v2 inherits from v1 is byte-equal to the v1 block, so the
  2,304-configuration grid, the costs, the folds, the selection rule and the
  status vocabulary cannot drift between protocol versions;
* the v1 evidence it supersedes is still byte-identical;
* the specification smuggles in no asset membership and treats the three
  unvalidated candidates as unvalidated;
* the confirmatory-holdout rules forbid reuse of the v1 holdout;
* execution is not authorized while the data prerequisites are outstanding;
* the v1 campaign authorization is untouched by the v2 specification.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from breakout_research.config import load_research_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V1 = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V2 = REPO_ROOT / "configs" / "research_v2.json"
CODE_HASH_AMENDMENT = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

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

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_research_v2_spec", REPO_ROOT / "scripts" / "verify_research_v2_spec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_specification_hash_recomputes_from_the_document():
    spec = _load(SPEC_V2)
    assert spec["specification_hash"] == verifier.compute_specification_hash(spec)


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_verifier_detects_a_tampered_rule():
    spec = _load(SPEC_V2)
    tampered = json.loads(json.dumps(spec))
    tampered["strategy_grid"]["entry_lookback"] = [12, 24, 48]
    assert verifier.compute_specification_hash(tampered) != spec["specification_hash"]


def test_inherited_blocks_are_identical_to_v1():
    v1 = _load(SPEC_V1)
    v2 = _load(SPEC_V2)
    for block in INHERITED_BLOCKS:
        assert v2[block] == v1[block], block


def test_grid_still_enumerates_2304_combinations():
    v2 = _load(SPEC_V2)
    grid = v2["strategy_grid"]
    product = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        product *= len(values)
    assert product == 2304
    assert grid["total_combinations"] == 2304


def test_v1_artifacts_are_unchanged():
    for rel, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / rel
        if not path.exists():
            pytest.skip(f"{rel} is not present in this checkout")
        assert verifier.sha256_file(path) == digest, rel


def test_supersedes_points_at_the_v1_specification():
    v1 = _load(SPEC_V1)
    v2 = _load(SPEC_V2)
    supersedes = v2["supersedes"]
    assert supersedes["protocol_version"] == "v1"
    assert supersedes["specification_path"] == "configs/research_v1.json"
    assert supersedes["specification_hash"] == v1["specification_hash"]
    assert supersedes["v1_artifacts_are_immutable"] is True


def test_specification_contains_no_asset_membership():
    v2 = _load(SPEC_V2)
    assert "eligible_assets" not in v2["universe"]
    text = verifier.canonical(v2)
    for symbol in ("ZEC", "HYPE", "HBAR"):
        assert f'"{symbol}"' not in text, symbol


def test_confirmatory_window_forbids_v1_holdout_reuse():
    v2 = _load(SPEC_V2)
    holdout = v2["holdout"]
    assert holdout["v1_holdout_status"] == "EXPOSED_OR_UNKNOWN"
    assert holdout["v1_holdout_reuse"] == "forbidden"
    window = holdout["v2_confirmatory_window"]
    assert window["starts_after"] == "v2_candidate_freeze_timestamp_utc"
    assert window["overlap_with_v1_holdout"] == "forbidden"
    assert window["data_used_for_candidate_selection"] == "excluded"
    assert window["single_use"] is True
    assert holdout["candidate_freeze_rule"].startswith("The v2 candidate manifest")


def test_promotion_rule_uses_the_unchanged_status_vocabulary():
    v1 = _load(SPEC_V1)
    v2 = _load(SPEC_V2)
    vocabulary = set(v1["status"]["economic"])
    for status in v2["holdout"]["promotion_rule"]["status_vocabulary"]:
        assert status in vocabulary, status
    assert v2["holdout"]["promotion_rule"]["no_ranking_on_holdout"] is True
    assert v2["holdout"]["promotion_rule"]["no_retuning_on_holdout"] is True


def test_comparability_statement_separates_v1_from_v2():
    v2 = _load(SPEC_V2)
    comparability = v2["comparability"]
    assert comparability["v1_cycle0_units"] == 497664
    assert comparability["bridging_analysis_required"] is True
    assert any("not be appended to" in rule for rule in comparability["rules"])
    assert any(
        "manifest_version 2" in rule for rule in comparability["rules"]
    ), "the spec must state that candidate_manifest_v2.json is a v1-campaign artifact"


def test_execution_is_not_authorized_while_prerequisites_are_outstanding():
    v2 = _load(SPEC_V2)
    prerequisites = {item["id"]: item for item in v2["prerequisites"]}
    assert set(prerequisites) == {"P1", "P2", "P3", "P4", "P5"}
    assert prerequisites["P1"]["status"] == "SATISFIED_BY_THIS_SPEC"
    assert prerequisites["P2"]["status"] == "OUTSTANDING"
    assert prerequisites["P3"]["status"] == "OUTSTANDING"
    assert v2["authorization"]["execution_authorized"] is False


def test_next_session_scope_is_manifests_only_and_excludes_execution():
    v2 = _load(SPEC_V2)
    authorization = v2["authorization"]
    prohibited = authorization["not_authorized_by_this_specification_alone"]
    assert any("confirmatory window" in item for item in prohibited)
    assert any("campaign" in item for item in prohibited)
    assert any("v1 shards" in item for item in prohibited)
    scope = authorization["next_session_authorization"]
    assert "P2 and P3 only" in scope
    assert "must not run a v2 campaign" in scope
    assert "must not touch the v1 artifacts" in scope


def test_v1_campaign_authorization_is_untouched():
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    v1 = _load(SPEC_V1)
    assert authorization["protocol_version"] == "v1"
    assert authorization["specification_hash"] == v1["specification_hash"]
    assert authorization["authorized"] is True


def test_the_v1_campaign_authorization_is_bound_to_the_canonical_tree_identity():
    """BRAIN-009: the tree identity is the portable canonical digest.

    The authorized code hash is the value of record; the identity of the hashed
    source set is checked against the canonical digest, because the ordered
    digest that ``compute_code_hash()`` returns depends on the directory
    enumeration order of the checkout.
    """
    import importlib.util

    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    amendment = _load(CODE_HASH_AMENDMENT)
    spec = importlib.util.spec_from_file_location(
        "verify_research_v2_code_hash_amendment_1",
        REPO_ROOT / "scripts" / "verify_research_v2_code_hash_amendment_1.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorded = amendment["code_hash_constraint"]["canonical_source_digest"]
    assert module.canonical_source_digest(REPO_ROOT) == recorded
    assert authorization["code_hash"] == amendment["code_hash_constraint"]["authorized_code_hash"]


def test_v1_spec_loader_still_reads_the_v1_specification():
    spec = load_research_spec(str(SPEC_V1))
    assert spec["protocol_version"] == "v1"
    assert spec["strategy_grid"]["total_combinations"] == 2304

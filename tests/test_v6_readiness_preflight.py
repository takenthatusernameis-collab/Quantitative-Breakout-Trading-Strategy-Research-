"""Tests for the offline v6 readiness-preflight primitives."""
import hashlib
import json
from pathlib import Path

from scripts.v6_readiness_preflight import (
    manifest_digest, source_tree_digest, verify_selection_source_binding,
    verify_confirmatory_scope_contract, verify_confirmatory_retrieval_contract,
)


def test_manifest_digest_uses_declared_exclusions_and_nested_keys():
    document = {
        "a": 1,
        "manifest_hash": "ignored",
        "snapshot_identity": {"data_manifest_hash": "cycle", "other": "kept"},
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash", "snapshot_identity.data_manifest_hash"]},
    }
    body = {
        "a": 1,
        "snapshot_identity": {"other": "kept"},
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash", "snapshot_identity.data_manifest_hash"]},
    }
    expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert manifest_digest(document) == expected


def test_source_tree_digest_is_order_independent_and_content_sensitive(tmp_path: Path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "b.py").write_text("B = 2\n", encoding="utf-8")
    (root / "a.py").write_text("A = 1\n", encoding="utf-8")
    first = source_tree_digest(root)
    assert first is not None
    (root / "a.py").write_text("A = 3\n", encoding="utf-8")
    assert source_tree_digest(root) != first


def test_source_tree_digest_returns_none_for_missing_or_empty_tree(tmp_path: Path):
    assert source_tree_digest(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert source_tree_digest(empty) is None


def test_selection_binding_accepts_versioned_binding_without_mutating_authorization(tmp_path: Path):
    import hashlib

    root = tmp_path
    campaign = root / "src" / "v6_campaign"
    engine = root / "src" / "breakout_research"
    campaign.mkdir(parents=True)
    engine.mkdir(parents=True)
    (campaign / "runner.py").write_text("RUNNER = True\n", encoding="utf-8")
    (engine / "engine.py").write_text("ENGINE = True\n", encoding="utf-8")
    auth_dir = root / "configs"
    auth_dir.mkdir()
    auth_path = auth_dir / "research_v6_selection_authorization_1.json"
    binding_path = auth_dir / "research_v6_selection_execution_binding_1.json"

    engine_digest = source_tree_digest(engine)
    selection_digest = source_tree_digest(campaign)
    auth = {
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash"]},
        "authorized_run": {"code_identity": {"hashed_set_digest": engine_digest}},
    }
    auth["manifest_hash"] = manifest_digest(auth)
    auth_bytes = (json.dumps(auth, indent=2) + "\n").encode("utf-8")
    auth_path.write_bytes(auth_bytes)

    binding = {
        "binding_status": "IMPLEMENTATION_BOUND_NOT_RUN",
        "amends": {
            "path": "configs/research_v6_selection_authorization_1.json",
            "manifest_hash": auth["manifest_hash"],
            "sha256": hashlib.sha256(auth_bytes).hexdigest(),
        },
        "execution_path": {
            "package": "src/v6_campaign",
            "canonical_source_digest": selection_digest,
        },
        "code_identity": {
            "execution_path_root": "src/v6_campaign",
            "execution_path_digest": selection_digest,
            "hashed_set_root": "src/breakout_research",
            "hashed_set_digest": engine_digest,
        },
        "authority": {
            "single_selection_run_authority_source": "configs/research_v6_selection_authorization_1.json",
            "single_selection_run_authority_manifest_hash": auth["manifest_hash"],
            "max_runs": 1,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "second_v6_selection_run_authorized": False,
            "amendment_of_a_frozen_artifact_authorized": False,
            "holdout_reads_authorized": False,
        },
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash"]},
    }
    binding["manifest_hash"] = manifest_digest(binding)
    binding_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")

    ok, detail = verify_selection_source_binding(root, auth, selection_digest)
    assert ok, detail


def test_selection_binding_rejects_implicit_confirmatory_authority(tmp_path: Path):
    import hashlib

    root = tmp_path
    campaign = root / "src" / "v6_campaign"
    engine = root / "src" / "breakout_research"
    campaign.mkdir(parents=True)
    engine.mkdir(parents=True)
    (campaign / "runner.py").write_text("RUNNER = True\n", encoding="utf-8")
    (engine / "engine.py").write_text("ENGINE = True\n", encoding="utf-8")
    auth_dir = root / "configs"
    auth_dir.mkdir()
    auth_path = auth_dir / "research_v6_selection_authorization_1.json"
    binding_path = auth_dir / "research_v6_selection_execution_binding_1.json"
    engine_digest = source_tree_digest(engine)
    selection_digest = source_tree_digest(campaign)
    auth = {
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash"]},
        "authorized_run": {"code_identity": {"hashed_set_digest": engine_digest}},
    }
    auth["manifest_hash"] = manifest_digest(auth)
    auth_bytes = (json.dumps(auth, indent=2) + "\n").encode("utf-8")
    auth_path.write_bytes(auth_bytes)
    binding = {
        "binding_status": "IMPLEMENTATION_BOUND_NOT_RUN",
        "amends": {
            "path": "configs/research_v6_selection_authorization_1.json",
            "manifest_hash": auth["manifest_hash"],
            "sha256": hashlib.sha256(auth_bytes).hexdigest(),
        },
        "execution_path": {
            "package": "src/v6_campaign",
            "canonical_source_digest": selection_digest,
        },
        "code_identity": {
            "execution_path_root": "src/v6_campaign",
            "execution_path_digest": selection_digest,
            "hashed_set_root": "src/breakout_research",
            "hashed_set_digest": engine_digest,
        },
        "authority": {
            "single_selection_run_authority_source": "configs/research_v6_selection_authorization_1.json",
            "single_selection_run_authority_manifest_hash": auth["manifest_hash"],
            "max_runs": 1,
            "confirmatory_evaluation_authorized": True,
            "candle_fetch_authorized": False,
            "second_v6_selection_run_authorized": False,
            "amendment_of_a_frozen_artifact_authorized": False,
            "holdout_reads_authorized": False,
        },
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash"]},
    }
    binding["manifest_hash"] = manifest_digest(binding)
    binding_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")

    ok, detail = verify_selection_source_binding(root, auth, selection_digest)
    assert not ok
    assert "confirmatory_evaluation_authorized" in detail


def test_confirmatory_scope_contract_blocks_one_config_vs_576_grid_conflict():
    protocol = {
        "scope": {
            "selected_configuration_per_asset": (
                "the one configuration published in the selected-configurations manifest "
                "for each eligible asset"
            )
        }
    }
    runbook = {
        "operator_procedure": {
            "ordered_steps": [
                {
                    "step": 7,
                    "action": (
                        "Evaluate every in-scope asset's frozen configuration over the window. "
                        "The 576 btc_ema_168 configurations per asset are evaluated, never dropped."
                    ),
                }
            ]
        }
    }
    ok, detail = verify_confirmatory_scope_contract(protocol, runbook)
    assert not ok
    assert "versioned, hash-bound clarification" in detail
    assert "step(s) 7" in detail


def test_confirmatory_scope_contract_accepts_unambiguous_selected_config_rule():
    protocol = {
        "scope": {
            "selected_configuration_per_asset": (
                "exactly one configuration is selected per eligible asset by the frozen selection manifest"
            )
        }
    }
    runbook = {
        "operator_procedure": {
            "ordered_steps": [
                {"step": 7, "action": "Evaluate each selected configuration once on the frozen window."}
            ]
        }
    }
    ok, detail = verify_confirmatory_scope_contract(protocol, runbook)
    assert ok
    assert "no conflict" in detail


def test_confirmatory_retrieval_contract_blocks_one_response_for_2160_candles():
    runbook = {
        "applies_to": {"minimum_closed_hourly_candles": 2160},
        "operator_procedure": {
            "retrieval": {
                "one_request_per_asset": True,
                "retrieval_happens_once": True,
            }
        },
    }
    ok, detail = verify_confirmatory_retrieval_contract(runbook)
    assert not ok
    assert "at least 3 responses" in detail
    assert "versioned, hash-bound pagination clarification" in detail


def test_confirmatory_retrieval_contract_accepts_explicit_three_page_window():
    runbook = {
        "applies_to": {"minimum_closed_hourly_candles": 2160},
        "operator_procedure": {
            "retrieval": {
                "one_request_per_asset": False,
                "max_candles_per_request": 1000,
                "max_pages_per_series": 3,
                "pagination_cursor": "open_time",
                "deduplicate_by": "open_time",
                "require_contiguous_hourly_coverage": True,
            }
        },
    }
    ok, detail = verify_confirmatory_retrieval_contract(runbook)
    assert ok
    assert "at least 3 are required" in detail


def test_confirmatory_retrieval_contract_rejects_page_limit_above_documented_maximum():
    runbook = {
        "applies_to": {"minimum_closed_hourly_candles": 2160},
        "operator_procedure": {
            "retrieval": {
                "max_candles_per_request": 2160,
                "max_pages_per_series": 1,
            }
        },
    }
    ok, detail = verify_confirmatory_retrieval_contract(runbook)
    assert not ok
    assert "documented maximum of 1000" in detail

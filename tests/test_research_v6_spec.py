"""Tests for the preregistered v6 specification (``configs/research_v6.json``).

The v6 specification is the preregistration of the sixth versioned market-cap
universe (BRAIN-026).  It freezes the rules *before* any v6 data is retrieved:
the v6 floor, the prior-universe identity rule over v1 to v5, the band-width
rule, the development-data boundary, the benchmark rule, the four confirmatory
gates plus the v6 gate, the v6 namespace, the portable code identity and the
null-result path.

Every check here recomputes its expectation from repository state; a check that
compared the specification with a constant copied out of the specification would
prove nothing (README Section 2A E).  The tamper controls prove that the
verifier still fails when a rule is actually broken.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V6 = REPO_ROOT / "configs" / "research_v6.json"

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

PRIOR_UNIVERSE_MANIFESTS = (
    ("v1", "research/universe_manifest.json"),
    ("v2", "research/universe_manifest_v2.json"),
    ("v3", "research/universe_manifest_v3.json"),
    ("v4", "research/universe_manifest_v4.json"),
    ("v5", "research/universe_manifest_v5.json"),
)

CONFIRMATORY_WINDOW_SOURCES = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The files the v6 specification verifier reads.
MIRRORED_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v3.json",
    "configs/research_v5.json",
    "configs/research_v6.json",
    "configs/research_v6_confirmatory_protocol.json",
    "configs/research_v6_confirmatory_runbook_1.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v4_candidate_freeze.json",
    "configs/research_v5_candidate_freeze.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/universe_manifest_v4.json",
    "research/universe_manifest_v5.json",
    "research/data_manifest_v2.json",
    "research/data_manifest_v3.json",
    "research/data_manifest_v4.json",
    "research/data_manifest_v5.json",
    "research/v5_selected_configurations_manifest.json",
    "research/v_universe_expansion_log.json",
    "research/data/candles_v5/BTCUSDT_1h_626e639b02e54bc1.csv",
    "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
    "research_state/checkpoint_v5.json",
)

MIRRORED_TREES = (
    "src/breakout_research",
    "src/v2_campaign",
    "src/v2_confirmatory",
    "src/v3_campaign",
    "src/v3_confirmatory",
    "src/v4_campaign",
    "src/v5_campaign",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v6_spec", REPO_ROOT / "scripts" / "verify_research_v6_spec.py")
builder = _load_module("build_research_v6_spec", REPO_ROOT / "scripts" / "build_research_v6_spec.py")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary copy of the parts of the repository the v6 verifier reads.

    The source trees and the benchmark datasets are copied for real, so a test
    may modify them without writing through a symlink into the working tree.
    """
    root = tmp_path / "repo"
    for relative in MIRRORED_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for relative in MIRRORED_TREES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def _rewrite_spec(root: Path, mutate) -> None:
    """Apply ``mutate`` to the mirrored specification and re-hash it.

    The specification hash is recomputed so that the tamper exercises the rule
    under test and not only the self-hash.
    """
    path = root / "configs" / "research_v6.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    mutate(spec)
    spec["specification_hash"] = verifier.compute_specification_hash(spec)
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _window_start_and_end(version: str, relative: str, key: str) -> Tuple[str, int]:
    freeze = _load(REPO_ROOT / relative)
    block = freeze[key]
    if key == "data_boundary":
        return block["confirmatory_window_start_utc"], int(block["min_confirmatory_window_hours"])
    return block["opens_utc"], int(block["min_hours"])


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


def test_the_specification_hash_recomputes_from_the_document():
    spec = _load(SPEC_V6)
    assert spec["specification_hash"] == verifier.compute_specification_hash(spec)


def test_the_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_specification_is_reproducible_from_the_producer():
    document = builder.build(REPO_ROOT)
    on_disk = json.loads(SPEC_V6.read_text(encoding="utf-8"))
    assert document == on_disk
    assert builder.compute_specification_hash(document) == on_disk["specification_hash"]


def test_the_specification_is_a_v6_preregistration():
    spec = _load(SPEC_V6)
    assert spec["protocol_version"] == "v6"
    assert spec["universe_version"] == "v6"
    assert spec["specification_status"] == "PREREGISTERED_SPECIFICATION_ONLY"
    assert spec["design_basis"]["brainstorming_item"] == "BRAIN-026"


def test_the_inherited_blocks_are_identical_to_v1():
    v1 = _load(REPO_ROOT / "configs" / "research_v1.json")
    v6 = _load(SPEC_V6)
    for block in INHERITED_BLOCKS:
        assert v6[block] == v1.get(block), block


def test_the_grid_still_enumerates_2304_combinations():
    v6 = _load(SPEC_V6)
    grid = v6["strategy_grid"]
    product = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        product *= len(values)
    assert product == 2304
    assert grid["total_combinations"] == 2304


def test_the_eligibility_validation_block_is_the_inherited_v3_block():
    """The v6 chain inherits the v3 eligibility rules, with two documented deviations."""
    v3 = _load(REPO_ROOT / "configs" / "research_v3.json")
    v6 = _load(SPEC_V6)
    inherited = v3["universe"]["eligibility_validation"]
    recorded = v6["universe"]["eligibility_validation"]
    deviations = {"data_manifest", "data_manifest_note"}
    stripped = json.loads(json.dumps(recorded))
    for key in deviations:
        stripped["data_integrity"].pop(key, None)
    expected = json.loads(json.dumps(inherited))
    for key in deviations:
        expected["data_integrity"].pop(key, None)
    assert stripped == expected
    assert recorded["data_integrity"]["data_manifest"] == "research/data_manifest_v6.json"
    assert recorded["data_integrity"]["data_manifest_note"]


def test_the_specification_records_no_asset_membership():
    v6 = _load(SPEC_V6)
    for forbidden in ("eligible_assets", "candidates", "frozen_candidate_set", "candidate_batch"):
        assert forbidden not in v6["universe"], forbidden


# ---------------------------------------------------------------------------
# the floor, the identity rule and the band width
# ---------------------------------------------------------------------------


def test_the_v6_floor_is_recomputed_from_the_v5_manifest():
    v6 = _load(SPEC_V6)
    manifest = _load(REPO_ROOT / "research" / "universe_manifest_v5.json")
    assets = manifest["eligible_assets"]
    lowest = min(assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol"))))
    floor = v6["universe"]["expansion_scope"]["prior_universe_floor"]
    assert floor["source_manifest_path"] == "research/universe_manifest_v5.json"
    assert floor["source_manifest_hash"] == manifest["manifest_hash"]
    assert floor["floor_market_cap_usd"] == int(lowest["market_cap_usd"])
    assert floor["floor_symbol"] == lowest["symbol"]
    assert floor["floor_market_cap_rank"] == lowest["market_cap_rank"]
    assert floor["comparison"] == "strictly_less_than"


def test_the_v6_floor_is_strictly_below_the_v5_floor():
    """The floor chain v2 -> v3 -> v4 -> v5 -> v6 stays strictly monotone."""
    v6 = _load(SPEC_V6)
    v5 = _load(REPO_ROOT / "configs" / "research_v5.json")
    v6_floor = v6["universe"]["expansion_scope"]["prior_universe_floor"]["floor_market_cap_usd"]
    v5_floor = v5["universe"]["expansion_scope"]["prior_universe_floor"]["floor_market_cap_usd"]
    assert v6_floor < v5_floor


def test_the_identity_rule_covers_v1_to_v5_and_the_counts_recompute():
    v6 = _load(SPEC_V6)
    identity = v6["universe"]["expansion_scope"]["prior_universe_asset_identity"]
    assert [source["universe_version"] for source in identity["sources"]] == [
        "v1",
        "v2",
        "v3",
        "v4",
        "v5",
    ]
    assert sorted(identity["matched_on"]) == ["binance_symbol", "coingecko_id"]

    symbols = set()
    coingecko_ids = set()
    for _version, relative in PRIOR_UNIVERSE_MANIFESTS:
        manifest = _load(REPO_ROOT / relative)
        for asset in manifest["eligible_assets"]:
            symbols.add(asset["symbol"])
            coingecko_ids.add(asset["coingecko_id"])
    assert identity["distinct_prior_symbols"] == len(symbols)
    assert identity["distinct_prior_coingecko_ids"] == len(coingecko_ids)
    assert identity["distinct_prior_symbols"] < sum(
        len(_load(REPO_ROOT / relative)["eligible_assets"]) for _, relative in PRIOR_UNIVERSE_MANIFESTS
    )


def test_the_band_width_rule_matches_the_top_n_and_forbids_widening():
    v6 = _load(SPEC_V6)
    universe = v6["universe"]
    band = universe["expansion_scope"]["band_width_rule"]
    assert band["band_width"] == universe["top_n"] == 20
    assert band["ordering"] == "strictly_descending_market_cap"
    assert band["validated_set_is_a_consequence"] is True
    assert "never widened" in band["band_never_widened"]
    assert band["recompute_rule"]
    assert band["shortfall_rule"]


# ---------------------------------------------------------------------------
# the development boundary, the benchmark rule and the gates
# ---------------------------------------------------------------------------


def test_the_development_cutoff_is_the_earliest_open_window_start():
    v6 = _load(SPEC_V6)
    starts = [
        _window_start_and_end(version, relative, key)[0]
        for version, relative, key in CONFIRMATORY_WINDOW_SOURCES
    ]
    assert v6["holdout"]["development_cutoff_utc"] == min(starts)
    assert v6["holdout"]["development_cutoff_utc"] == "2026-10-19T22:00:00Z"


def test_the_development_cutoff_is_the_same_instant_the_v5_chain_used():
    """v6 differs from v5 in the universe and in nothing else, not even the window."""
    v6 = _load(SPEC_V6)
    v5 = _load(REPO_ROOT / "configs" / "research_v5.json")
    assert v6["holdout"]["development_cutoff_utc"] == v5["holdout"]["development_cutoff_utc"]
    assert v6["holdout"]["development_window"] == v5["holdout"]["development_window"]


def test_the_development_boundary_is_stated_inclusively():
    v6 = _load(SPEC_V6)
    rule = v6["holdout"]["development_cutoff_rule"]
    assert "closes exactly at" in rule
    assert "no candle that closes after" in rule


def test_the_membership_rule_is_the_corrected_start_exclusive_rule():
    """The v6 specification carries the corrected rule, so it needs no amendment."""
    v6 = _load(SPEC_V6)
    membership = v6["holdout"]["confirmatory_window_membership"]
    assert membership["interval_start_inclusive"] is False
    assert membership["interval_end_exclusive"] is True
    assert "strictly after" in membership["rule"]
    assert "regardless of which asset" in membership["rule"]


def test_the_membership_quote_is_a_verbatim_source_rule():
    v6 = _load(SPEC_V6)
    quote = v6["holdout"]["confirmatory_window_membership"]["source_quote"]
    for version, relative, key in (
        ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary.development_data_rule"),
        ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary.development_data_rule"),
    ):
        freeze = _load(REPO_ROOT / relative)
        assert quote in freeze["data_boundary"]["development_data_rule"], version


def test_the_development_window_bounds_recompute_from_the_cutoff():
    v6 = _load(SPEC_V6)
    window = v6["holdout"]["development_window"]
    count = window["candle_count"]
    assert count == 26280
    last_open = window["last_candle_open_timestamp_ms"]
    first_open = window["first_candle_open_timestamp_ms"]
    assert last_open - first_open == (count - 1) * 3600 * 1000
    cutoff = _parse_utc(v6["holdout"]["development_cutoff_utc"])
    assert int((cutoff - timedelta(hours=1)).timestamp() * 1000) == last_open


def test_the_benchmark_rule_recomputes_the_reusable_dataset():
    v6 = _load(SPEC_V6)
    reusable = v6["holdout"]["benchmark_rule"]["reusable_dataset"]
    path = REPO_ROOT / reusable["path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert reusable["content_hash"] == digest
    last_open = int(path.read_text(encoding="utf-8").splitlines()[-1].split(",")[0])
    assert reusable["last_candle_open_timestamp_ms"] == last_open
    assert reusable["closes_after_the_cutoff"] is False


def test_the_benchmark_rule_recomputes_the_forbidden_dataset():
    v6 = _load(SPEC_V6)
    forbidden = v6["holdout"]["benchmark_rule"]["forbidden_dataset"]
    path = REPO_ROOT / forbidden["path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert forbidden["content_hash"] == digest
    last_open = int(path.read_text(encoding="utf-8").splitlines()[-1].split(",")[0])
    cutoff_ms = int(_parse_utc(v6["holdout"]["development_cutoff_utc"]).timestamp() * 1000)
    expected = (last_open + 3600 * 1000 - cutoff_ms) // 3600000
    assert forbidden["candles_closing_after_the_cutoff"] == expected
    assert expected > 0


def test_the_four_gates_recompute_from_the_freezes():
    v6 = _load(SPEC_V6)
    gates = v6["phase_gates"]["gates"]
    assert [gate["version"] for gate in gates] == ["v2", "v3", "v4", "v5"]
    for gate, (version, relative, key) in zip(gates, CONFIRMATORY_WINDOW_SOURCES):
        start, min_hours = _window_start_and_end(version, relative, key)
        earliest = (_parse_utc(start) + timedelta(hours=min_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert gate["window_start_utc"] == start
        assert gate["min_hours"] == min_hours
        assert gate["earliest_possible_end_utc"] == earliest
        assert gate["evaluation_may_not_start_before"] == earliest
        assert gate["source_path"] == relative


def test_the_v6_gate_is_the_later_of_the_four_and_its_own_window():
    v6 = _load(SPEC_V6)
    gate = v6["phase_gates"]["v6_confirmatory_gate"]
    ends = [
        (_parse_utc(window["earliest_possible_end_utc"]))
        for window in v6["phase_gates"]["gates"]
    ]
    latest = max(ends).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert gate["earliest_existing_gate_utc"] == latest
    assert gate["v6_window_min_hours"] == 2160
    assert "later of" in gate["rule"]


def test_the_holdout_counter_starts_at_zero_for_every_version():
    v6 = _load(SPEC_V6)
    holdout = v6["holdout"]
    for version in ("v2", "v3", "v4", "v5", "v6"):
        assert holdout[f"{version}_holdout_exposed_count"] == 0
    assert holdout["v1_v2_v3_v4_v5_holdout_never_reused_for_selection"] is True


def test_the_retrieval_window_opens_at_the_creation_instant():
    v6 = _load(SPEC_V6)
    retrieval = v6["universe"]["snapshot_retrieval"]
    assert retrieval["not_before_utc"] == v6["created_utc"]
    assert retrieval["window_days"] == 7
    expected = (_parse_utc(v6["created_utc"]) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert retrieval["deadline_utc"] == expected


def test_the_retrieval_is_single_use_and_not_a_candle_read():
    v6 = _load(SPEC_V6)
    retrieval = v6["universe"]["snapshot_retrieval"]
    assert retrieval["reuse_forbidden"] is True
    assert retrieval["re_timing_forbidden"] is True
    assert retrieval["is_a_candle_read"] is False
    assert retrieval["retrieval_policy"] == "exactly_once_read_only_bounded"
    assert "first successful retrieval inside the window" in retrieval["rule"]
    assert "versioned amendment" in retrieval["expired_window_rule"]
    assert retrieval["endpoint"] == v6["universe"]["endpoint"]
    assert retrieval["depth"] == v6["universe"]["ranking_depth"]
    assert "raw_market_cap_response.json" in retrieval["evidence_required"]


# ---------------------------------------------------------------------------
# the code identity
# ---------------------------------------------------------------------------


def test_the_code_identity_is_recomputed_from_the_source_tree():
    v6 = _load(SPEC_V6)
    identity = v6["code_identity"]
    assert identity["hashed_set_root"] == "src/breakout_research"
    assert identity["hashed_set_digest"] == verifier.canonical_source_digest(
        REPO_ROOT / "src" / "breakout_research"
    )
    for entry in identity["untouched_execution_paths"]:
        assert entry["canonical_source_digest"] == verifier.canonical_source_digest(REPO_ROOT / entry["root"])
        assert entry["recorded_canonical_source_digest"] == entry["canonical_source_digest"]


def test_the_authorized_ordered_code_hash_is_unchanged():
    v6 = _load(SPEC_V6)
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert v6["code_identity"]["authorized_ordered_code_hash"] == authorization["code_hash"]
    assert v6["code_identity"]["authorized_ordered_code_hash"] == (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    )
    assert v6["code_identity"]["ordered_code_hash_is_portable"] is False


def test_the_hashed_source_set_is_untouched_by_the_v6_specification():
    """The v6 specification did not touch the hashed set: its digest still matches v5's."""
    v5 = _load(REPO_ROOT / "configs" / "research_v5.json")
    v6 = _load(SPEC_V6)
    assert v6["code_identity"]["hashed_set_digest"] == v5["code_identity"]["hashed_set_digest"]


# ---------------------------------------------------------------------------
# the chain, the namespace, the log and the exposure state
# ---------------------------------------------------------------------------


def test_the_supersedes_chain_recomputes_from_the_v5_artifacts():
    v6 = _load(SPEC_V6)
    supersedes = v6["supersedes"]
    assert supersedes["protocol_version"] == "v5"
    assert supersedes["specification_hash"] == _load(REPO_ROOT / "configs" / "research_v5.json")[
        "specification_hash"
    ]
    assert supersedes["universe_manifest_hash"] == _load(
        REPO_ROOT / "research" / "universe_manifest_v5.json"
    )["manifest_hash"]
    assert supersedes["data_manifest_hash"] == _load(REPO_ROOT / "research" / "data_manifest_v5.json")[
        "manifest_hash"
    ]
    assert supersedes["candidate_freeze_hash"] == _load(
        REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
    )["manifest_hash"]
    assert supersedes["selected_configurations_manifest_hash"] == _load(
        REPO_ROOT / "research" / "v5_selected_configurations_manifest.json"
    )["manifest_hash"]
    for version in ("v1", "v2", "v3", "v4", "v5"):
        assert supersedes[f"{version}_artifacts_are_immutable"] is True


def test_the_v6_namespace_does_not_collide_with_the_frozen_paths():
    v6 = _load(SPEC_V6)
    namespace = v6["namespace"]
    paths = {
        value
        for key, value in namespace.items()
        if key not in {"rule", "result_stream_durability"} and isinstance(value, str)
    }
    for foreign in (
        "research/universe_manifest_v5.json",
        "configs/research_v5_candidate_freeze.json",
        "research/ledger_v5.json",
        "research_state/checkpoint_v5.json",
    ):
        assert foreign not in paths, foreign
    assert namespace["universe_manifest"] == "research/universe_manifest_v6.json"
    assert namespace["checkpoint"] == "research_state/checkpoint_v6.json"


def test_the_v6_namespace_names_the_confirmatory_protocol_and_the_runbook():
    """The v6 chain does not repeat the v4/v5 omission of these two objects."""
    v6 = _load(SPEC_V6)
    namespace = v6["namespace"]
    assert namespace["confirmatory_protocol"] == "configs/research_v6_confirmatory_protocol.json"
    assert namespace["confirmatory_runbook"] == "configs/research_v6_confirmatory_runbook_1.json"


def test_the_delivered_stage_artifacts_are_bound_to_the_specification():
    """A v6 artifact that exists carries this specification's identity.

    The v6 chain has not started, so no stage artifact exists yet; the rule
    that holds now and after the retrieval stage is the same: an artifact that
    exists must be bound to this specification and to this universe version.
    """
    v6 = _load(SPEC_V6)
    for relative in verifier.V6_BOUND_STAGE_ARTIFACTS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        artifact = _load(path)
        assert artifact["specification_hash"] == v6["specification_hash"], relative
        assert artifact["universe_version"] == "v6", relative


def test_the_v6_run_artifacts_require_the_selection_authorization():
    """A v6 run artifact may only exist once the v6 selection authorization exists."""
    present = [relative for relative in verifier.V6_RUN_ARTIFACTS if (REPO_ROOT / relative).exists()]
    if not present:
        return
    authorization = REPO_ROOT / verifier.V6_SELECTION_AUTHORIZATION_RELATIVE
    assert authorization.exists(), present
    assert _load(authorization)["specification_hash"] == _load(SPEC_V6)["specification_hash"]


def test_the_v6_confirmatory_chain_is_bound_to_the_specification():
    """The v6 confirmatory protocol and runbook are delivered in this stage.

    The v4 and v5 chains omitted them (BRAIN-025); the v6 chain delivers the
    protocol and the runbook in the same stage as this check, so they must
    exist and must bind this specification.
    """
    v6 = _load(SPEC_V6)
    for relative, binding in verifier.V6_CONFIRMATORY_ARTIFACTS:
        path = REPO_ROOT / relative
        assert path.exists(), relative
        artifact = _load(path)
        value = artifact
        for key in binding.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        assert value == v6["specification_hash"], (relative, binding)


def test_the_expansion_log_chain_is_intact_and_the_v6_entry_is_a_pure_append():
    v6 = _load(SPEC_V6)
    program = v6["expansion_program"]
    log = _load(REPO_ROOT / program["append_only_log_path"])
    entries = log["entries"]
    for index, entry in enumerate(entries):
        body = {key: value for key, value in entry.items() if key != "entry_hash"}
        assert entry["entry_hash"] == hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if index:
            assert entry["previous_entry_hash"] == entries[index - 1]["entry_hash"]
    assert program["append_only_log_path"] == "research/v_universe_expansion_log.json"
    recorded = program["log_state_at_preregistration"]
    recorded_versions = recorded["versions_present"]
    assert [entry["universe_version"] for entry in entries[: len(recorded_versions)]] == recorded_versions
    assert recorded["entry_count"] == len(recorded_versions)
    assert recorded["missing_entries"] == []
    anchor = next(entry for entry in entries if entry["universe_version"] == recorded_versions[-1])
    assert program["log_entry_previous_hash"] == anchor["entry_hash"]


def test_the_exposure_counters_are_zero_everywhere():
    for version in ("v2", "v3", "v4", "v5"):
        manifest = _load(REPO_ROOT / "research" / f"data_manifest_{version}.json")
        assert manifest["confirmatory_window"]["holdout_exposed_count"] == 0
        assert manifest["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"


def test_the_specification_authorizes_nothing():
    v6 = _load(SPEC_V6)
    authorization = v6["authorization"]
    for flag in ("execution_authorized", "campaign_authorized", "selection_authorized", "confirmatory_authorized"):
        assert authorization[flag] is False, flag
    assert v6["specification_status"] == "PREREGISTERED_SPECIFICATION_ONLY"


def test_the_null_result_path_records_the_two_v6_cases():
    v6 = _load(SPEC_V6)
    null_result = v6["null_result_path"]
    assert null_result["state"] == "AWAITING_NEW_CANDIDATES"
    assert null_result["cadence"]["minimum_interval_between_passes"] == "P7D"
    assert null_result["cadence"]["cadence_mode"] == "bounded_cadence_not_polling"
    assert "never a terminal state" in null_result["campaign_completion_rule"]
    assert null_result["cases"]["depth_limit"]["next_pass_scheduled"] is True
    assert null_result["cases"]["empty_validated_set"]["next_pass_scheduled"] is True


def test_the_depth_policy_is_bounded():
    v6 = _load(SPEC_V6)
    depth = v6["universe"]["depth_policy"]
    assert depth["bounded_extra_page"]["max_extra_pages"] == 1
    assert depth["bounded_extra_page"]["cumulative_depth"] == 500
    assert depth["batch_recomputation"]
    assert depth["forbidden"]


def test_the_prerequisites_are_recorded():
    v6 = _load(SPEC_V6)
    prerequisites = v6["prerequisites"]
    assert prerequisites["p1"]["status"] == "DONE"
    for key in ("p2", "p3", "p4", "p5", "p6"):
        assert prerequisites[key]["status"] == "OUTSTANDING", key


# ---------------------------------------------------------------------------
# tamper controls
# ---------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path):
    """The control of every tamper control below.

    Without it, a mirror that is missing an artifact would make every tamper
    test pass for the wrong reason.
    """
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_tampered_floor(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["expansion_scope"]["prior_universe_floor"]["floor_market_cap_usd"] = 1

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("floor" in failure for failure in failures), failures


def test_the_verifier_detects_a_widened_development_cutoff(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["holdout"]["development_cutoff_utc"] = "2026-10-20T13:00:00Z"

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("development cutoff" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_gate(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        for gate in spec["phase_gates"]["gates"]:
            if gate["version"] == "v5":
                gate["earliest_possible_end_utc"] = "2027-01-18T13:00:00Z"
                gate["evaluation_may_not_start_before"] = "2027-01-18T13:00:00Z"

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("gate" in failure for failure in failures), failures


def test_the_verifier_detects_a_missing_gate(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["phase_gates"]["gates"] = [
            gate for gate in spec["phase_gates"]["gates"] if gate["version"] != "v5"
        ]

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("gates" in failure for failure in failures), failures


def test_the_verifier_detects_a_narrowed_identity_rule(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["expansion_scope"]["prior_universe_asset_identity"]["sources"] = [
            source
            for source in spec["universe"]["expansion_scope"]["prior_universe_asset_identity"]["sources"]
            if source["universe_version"] != "v5"
        ]

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("identity rule" in failure for failure in failures), failures


def test_the_verifier_detects_a_widened_band(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["expansion_scope"]["band_width_rule"]["band_width"] = 40

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("band" in failure for failure in failures), failures


def test_the_verifier_detects_a_removed_band_width_rule(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["expansion_scope"]["band_width_rule"]["validated_set_is_a_consequence"] = False

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("band" in failure for failure in failures), failures


def test_the_verifier_detects_a_start_inclusive_membership_rule(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["holdout"]["confirmatory_window_membership"]["interval_start_inclusive"] = True

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("membership" in failure for failure in failures), failures


def test_the_verifier_detects_a_forged_membership_quote(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["holdout"]["confirmatory_window_membership"]["source_quote"] = "Every candle is a development candle."

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("verbatim" in failure for failure in failures), failures


def test_the_verifier_detects_a_wrong_code_digest(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["code_identity"]["hashed_set_digest"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("hashed-set canonical digest" in failure for failure in failures), failures


def test_the_verifier_detects_a_self_authorizing_specification(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["authorization"]["execution_authorized"] = True

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("execution_authorized" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_supersedes_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["supersedes"]["universe_manifest_hash"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("supersedes chain" in failure for failure in failures), failures


def test_the_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / "src" / "breakout_research" / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
    failures = _failures(root)
    assert any("hashed-set canonical digest" in failure for failure in failures), failures


def test_the_verifier_detects_an_exposed_confirmatory_window(tmp_path):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "data_manifest_v3.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["confirmatory_window"]["holdout_exposed_count"] = 3
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("holdout_exposed_count" in failure for failure in failures), failures


def test_the_verifier_detects_a_broken_expansion_log_chain(tmp_path):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][0]["previous_entry_hash"] = "0" * 64
    path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("expansion log" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_expansion_log_previous_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["expansion_program"]["log_entry_previous_hash"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("expansion-log entry" in failure for failure in failures), failures


def test_the_verifier_detects_a_tampered_benchmark_content_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["holdout"]["benchmark_rule"]["reusable_dataset"]["content_hash"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("benchmark" in failure for failure in failures), failures


def test_the_verifier_detects_a_v6_artifact_written_before_authorization(tmp_path):
    """A v6 artifact that exists must be bound to this specification."""
    root = _mirror_repo(tmp_path)
    path = root / "research" / "universe_manifest_v6.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("not bound to this specification" in failure for failure in failures), failures


def test_the_verifier_detects_a_v6_confirmatory_artifact_not_bound_to_the_specification(tmp_path):
    """A confirmatory artifact that exists must bind this specification."""
    root = _mirror_repo(tmp_path)
    path = root / "configs" / "research_v6_confirmatory_protocol.json"
    path.write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("does not bind this specification" in failure for failure in failures), failures


def test_the_verifier_detects_a_v6_run_artifact_without_an_authorization(tmp_path):
    """A v6 run artifact may only exist once the v6 selection authorization exists."""
    root = _mirror_repo(tmp_path)
    path = root / "research_state" / "checkpoint_v6.json"
    path.write_text(json.dumps({"holdout_exposed_count": 0}, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("selection authorization does not" in failure for failure in failures), failures


def test_the_verifier_detects_a_retrieval_window_that_opens_before_the_specification(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["snapshot_retrieval"]["not_before_utc"] = "2026-10-01T00:00:00Z"

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("retrieval window opens" in failure for failure in failures), failures


def test_the_verifier_detects_a_re_timed_retrieval_deadline(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["snapshot_retrieval"]["deadline_utc"] = "2026-11-01T00:00:00Z"

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("retrieval window ends" in failure for failure in failures), failures


def test_the_verifier_detects_a_reusable_snapshot(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["snapshot_retrieval"]["reuse_forbidden"] = False

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("forbid reusing" in failure for failure in failures), failures


def test_the_verifier_detects_a_widened_eligibility_block(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["eligibility_validation"]["candle_history"]["min_candles"] = 1000

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("eligibility validation" in failure for failure in failures), failures


def test_the_verifier_survives_the_v6_expansion_log_entry(tmp_path):
    """The v6 entry is a pure append: the verifier stays green once it is there."""
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    spec = json.loads((root / "configs" / "research_v6.json").read_text(encoding="utf-8"))
    body = {
        "universe_version": "v6",
        "previous_entry_hash": log["entries"][-1]["entry_hash"],
        "specification_hash": spec["specification_hash"],
    }
    body["entry_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    log["entries"].append(body)
    path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    assert _failures(root) == []


def test_the_verifier_detects_a_wrong_development_window_bound(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["holdout"]["development_window"]["last_candle_open_timestamp_ms"] = 1

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("development window" in failure for failure in failures), failures

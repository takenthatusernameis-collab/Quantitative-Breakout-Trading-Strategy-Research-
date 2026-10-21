"""Tests for the preregistered v5 specification (``configs/research_v5.json``).

The v5 specification is the preregistration of the fifth versioned market-cap
universe (BRAIN-019).  It freezes the rules *before* any v5 data is retrieved:
the v5 floor, the prior-universe identity rule, the development-data boundary,
the three confirmatory gates, the v5 namespace, the portable code identity and
the null-result path.

Every check here recomputes its expectation from repository state; a check that
compared the specification with a constant copied out of the specification would
prove nothing (README Section 2A E).  The tamper controls prove that the
verifier still fails when a rule is actually broken.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_V5 = REPO_ROOT / "configs" / "research_v5.json"

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
)

CONFIRMATORY_WINDOW_SOURCES = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
)

#: The files and directories the v5 specification verifier reads.
MIRRORED_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v3.json",
    "configs/research_v4.json",
    "configs/research_v5.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v4_candidate_freeze.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/universe_manifest_v4.json",
    "research/universe_manifest_v5.json",
    "research/data_manifest_v2.json",
    "research/data_manifest_v3.json",
    "research/data_manifest_v4.json",
    "research/data_manifest_v5.json",
    "research/v4_selected_configurations_manifest.json",
    "research/v_universe_expansion_log.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
)

MIRRORED_TREES = (
    "src/breakout_research",
    "src/v2_campaign",
    "src/v2_confirmatory",
    "src/v3_campaign",
    "src/v3_confirmatory",
    "src/v4_campaign",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v5_spec", REPO_ROOT / "scripts" / "verify_research_v5_spec.py")
builder = _load_module("build_research_v5_spec", REPO_ROOT / "scripts" / "build_research_v5_spec.py")


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary copy of the parts of the repository the v5 verifier reads.

    The source trees are copied for real, so a test may modify the hashed set
    without writing through a symlink into the working tree.
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
    path = root / "configs" / "research_v5.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    mutate(spec)
    spec["specification_hash"] = verifier.compute_specification_hash(spec)
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


def test_the_specification_hash_recomputes_from_the_document():
    spec = _load(SPEC_V5)
    assert spec["specification_hash"] == verifier.compute_specification_hash(spec)


def test_the_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_the_specification_is_reproducible_from_the_producer():
    document = builder.build(REPO_ROOT)
    on_disk = json.loads(SPEC_V5.read_text(encoding="utf-8"))
    assert document == on_disk
    assert builder.compute_specification_hash(document) == on_disk["specification_hash"]


def test_the_inherited_blocks_are_identical_to_v1():
    v1 = _load(REPO_ROOT / "configs" / "research_v1.json")
    v5 = _load(SPEC_V5)
    for block in INHERITED_BLOCKS:
        assert v5[block] == v1.get(block), block


def test_the_grid_still_enumerates_2304_combinations():
    v5 = _load(SPEC_V5)
    grid = v5["strategy_grid"]
    product = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        product *= len(values)
    assert product == 2304
    assert grid["total_combinations"] == 2304


def test_the_specification_records_no_asset_membership():
    v5 = _load(SPEC_V5)
    for forbidden in ("eligible_assets", "candidates", "frozen_candidate_set"):
        assert forbidden not in v5["universe"], forbidden


# ---------------------------------------------------------------------------
# the floor and the identity rule
# ---------------------------------------------------------------------------


def test_the_v5_floor_is_recomputed_from_the_v4_manifest():
    v5 = _load(SPEC_V5)
    manifest = _load(REPO_ROOT / "research" / "universe_manifest_v4.json")
    assets = manifest["eligible_assets"]
    lowest = min(assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol"))))
    floor = v5["universe"]["expansion_scope"]["prior_universe_floor"]
    assert floor["source_manifest_path"] == "research/universe_manifest_v4.json"
    assert floor["source_manifest_hash"] == manifest["manifest_hash"]
    assert floor["floor_market_cap_usd"] == int(lowest["market_cap_usd"])
    assert floor["floor_symbol"] == lowest["symbol"]
    assert floor["comparison"] == "strictly_less_than"


def test_the_identity_rule_covers_v1_to_v4_and_the_counts_recompute():
    v5 = _load(SPEC_V5)
    identity = v5["universe"]["expansion_scope"]["prior_universe_asset_identity"]
    assert [source["universe_version"] for source in identity["sources"]] == ["v1", "v2", "v3", "v4"]
    assert sorted(identity["matched_on"]) == ["binance_symbol", "coingecko_id"]

    symbols = set()
    coingecko_ids = set()
    for version, relative in PRIOR_UNIVERSE_MANIFESTS:
        manifest = _load(REPO_ROOT / relative)
        for asset in manifest["eligible_assets"]:
            symbols.add(asset["symbol"])
            coingecko_ids.add(asset["coingecko_id"])
    assert identity["distinct_prior_symbols"] == len(symbols)
    assert identity["distinct_prior_coingecko_ids"] == len(coingecko_ids)
    assert identity["distinct_prior_symbols"] < sum(
        len(_load(REPO_ROOT / relative)["eligible_assets"]) for _, relative in PRIOR_UNIVERSE_MANIFESTS
    )


# ---------------------------------------------------------------------------
# the development boundary and the gates
# ---------------------------------------------------------------------------


def _window_start_and_end(version: str, relative: str, key: str):
    freeze = _load(REPO_ROOT / relative)
    block = freeze[key]
    if key == "data_boundary":
        return block["confirmatory_window_start_utc"], int(block["min_confirmatory_window_hours"])
    return block["opens_utc"], int(block["min_hours"])


def test_the_development_cutoff_is_the_earliest_open_window_start():
    v5 = _load(SPEC_V5)
    starts = [
        _window_start_and_end(version, relative, key)[0]
        for version, relative, key in CONFIRMATORY_WINDOW_SOURCES
    ]
    assert v5["holdout"]["development_cutoff_utc"] == min(starts)
    assert v5["holdout"]["development_cutoff_utc"] == "2026-10-19T22:00:00Z"


def test_the_development_boundary_is_stated_inclusively():
    v5 = _load(SPEC_V5)
    rule = v5["holdout"]["development_cutoff_rule"]
    assert "closes exactly at" in rule
    assert "no candle that closes after" in rule
    membership = v5["holdout"]["confirmatory_window_membership"]
    assert "regardless of which asset" in membership["rule"]
    assert membership["interval_start_inclusive"] is True


def test_the_development_window_bounds_recompute_from_the_cutoff():
    v5 = _load(SPEC_V5)
    window = v5["holdout"]["development_window"]
    count = window["candle_count"]
    assert count == 26280
    last_open = window["last_candle_open_timestamp_ms"]
    first_open = window["first_candle_open_timestamp_ms"]
    assert last_open - first_open == (count - 1) * 3600 * 1000
    cutoff = v5["holdout"]["development_cutoff_utc"]
    from datetime import datetime, timedelta, timezone

    parsed = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert int((parsed - timedelta(hours=1)).timestamp() * 1000) == last_open


def test_the_three_gates_recompute_from_the_freezes():
    v5 = _load(SPEC_V5)
    gates = v5["phase_gates"]["gates"]
    assert [gate["version"] for gate in gates] == ["v2", "v3", "v4"]
    from datetime import datetime, timedelta, timezone

    for gate, (version, relative, key) in zip(gates, CONFIRMATORY_WINDOW_SOURCES):
        start, min_hours = _window_start_and_end(version, relative, key)
        earliest = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(
            hours=min_hours
        )
        assert gate["window_start_utc"] == start
        assert gate["min_hours"] == min_hours
        assert gate["earliest_possible_end_utc"] == earliest.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert gate["evaluation_may_not_start_before"] == gate["earliest_possible_end_utc"]


# ---------------------------------------------------------------------------
# the code identity
# ---------------------------------------------------------------------------


def test_the_code_identity_is_recomputed_from_the_source_tree():
    v5 = _load(SPEC_V5)
    identity = v5["code_identity"]
    assert identity["hashed_set_root"] == "src/breakout_research"
    assert identity["hashed_set_digest"] == verifier.canonical_source_digest(
        REPO_ROOT / "src" / "breakout_research"
    )
    for entry in identity["untouched_execution_paths"]:
        assert entry["canonical_source_digest"] == verifier.canonical_source_digest(REPO_ROOT / entry["root"])
        assert entry["recorded_canonical_source_digest"] == entry["canonical_source_digest"]


def test_the_authorized_ordered_code_hash_is_unchanged():
    v5 = _load(SPEC_V5)
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert v5["code_identity"]["authorized_ordered_code_hash"] == authorization["code_hash"]
    assert v5["code_identity"]["authorized_ordered_code_hash"] == (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    )
    assert v5["code_identity"]["ordered_code_hash_is_portable"] is False


# ---------------------------------------------------------------------------
# the chain, the namespace and the exposure state
# ---------------------------------------------------------------------------


def test_the_supersedes_chain_recomputes_from_the_v4_artifacts():
    v5 = _load(SPEC_V5)
    supersedes = v5["supersedes"]
    assert supersedes["protocol_version"] == "v4"
    assert supersedes["specification_hash"] == _load(REPO_ROOT / "configs" / "research_v4.json")[
        "specification_hash"
    ]
    assert supersedes["universe_manifest_hash"] == _load(
        REPO_ROOT / "research" / "universe_manifest_v4.json"
    )["manifest_hash"]
    assert supersedes["candidate_freeze_hash"] == _load(
        REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"
    )["manifest_hash"]
    assert supersedes["selected_configurations_manifest_hash"] == _load(
        REPO_ROOT / "research" / "v4_selected_configurations_manifest.json"
    )["manifest_hash"]
    for version in ("v1", "v2", "v3", "v4"):
        assert supersedes[f"{version}_artifacts_are_immutable"] is True


def test_the_v5_namespace_does_not_collide_with_the_frozen_paths():
    v5 = _load(SPEC_V5)
    namespace = v5["namespace"]
    paths = {
        value for key, value in namespace.items() if key not in {"rule", "result_stream_durability"} and isinstance(value, str)
    }
    for foreign in (
        "research/universe_manifest_v4.json",
        "configs/research_v4_candidate_freeze.json",
        "research/ledger_v4.json",
        "research_state/checkpoint_v4.json",
    ):
        assert foreign not in paths, foreign
    assert namespace["universe_manifest"] == "research/universe_manifest_v5.json"
    assert namespace["checkpoint"] == "research_state/checkpoint_v5.json"


def test_no_v5_run_artifact_exists():
    """The v5 **run** artifacts must not exist while the chain has not run.

    The universe and the data manifests are the delivered retrieval stage and
    do exist; the freeze, the execution protocol, the authorization, the
    confirmatory protocol and runbook, the ledger, the results and the
    checkpoint are the run artifacts and must not.
    """
    for relative in (
        "configs/research_v5_candidate_freeze.json",
        "configs/research_v5_execution.json",
        "configs/research_v5_selection_authorization_1.json",
        "configs/research_v5_confirmatory_protocol.json",
        "configs/research_v5_confirmatory_runbook_1.json",
        "research/ledger_v5.json",
        "research/results_manifest_v5.json",
        "research/results_v5.jsonl",
        "research_state/checkpoint_v5.json",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_delivered_stage_artifacts_are_bound_to_the_specification():
    """The delivered v5 stage artifacts carry this specification's identity."""
    spec = _load(SPEC_V5)
    for relative in (
        "research/universe_manifest_v5.json",
        "research/data_manifest_v5.json",
    ):
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        stage = _load(path)
        assert stage["specification_hash"] == spec["specification_hash"], relative
        assert stage["universe_version"] == spec["universe_version"], relative


def test_the_expansion_log_chain_is_intact():
    v5 = _load(SPEC_V5)
    program = v5["expansion_program"]
    log = _load(REPO_ROOT / program["append_only_log_path"])
    entries = log["entries"]
    for index, entry in enumerate(entries):
        body = {key: value for key, value in entry.items() if key != "entry_hash"}
        import hashlib

        assert entry["entry_hash"] == hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if index:
            assert entry["previous_entry_hash"] == entries[index - 1]["entry_hash"]
    assert program["append_only_log_path"] == "research/v_universe_expansion_log.json"


def test_the_exposure_counters_are_zero_everywhere():
    for version in ("v2", "v3", "v4"):
        manifest = _load(REPO_ROOT / "research" / f"data_manifest_{version}.json")
        assert manifest["confirmatory_window"]["holdout_exposed_count"] == 0
        assert manifest["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"


def test_the_specification_authorizes_nothing():
    v5 = _load(SPEC_V5)
    authorization = v5["authorization"]
    for flag in ("execution_authorized", "campaign_authorized", "selection_authorized", "confirmatory_authorized"):
        assert authorization[flag] is False, flag
    assert v5["specification_status"] == "PREREGISTERED_SPECIFICATION_ONLY"


def test_the_null_result_path_and_the_depth_policy_are_recorded():
    v5 = _load(SPEC_V5)
    null_result = v5["null_result_path"]
    assert null_result["state"] == "AWAITING_NEW_CANDIDATES"
    assert null_result["cadence"]["minimum_interval_between_passes"] == "P7D"
    assert null_result["cadence"]["cadence_mode"] == "bounded_cadence_not_polling"
    assert "never" in null_result["campaign_completion_rule"]

    depth = v5["universe"]["depth_policy"]
    assert depth["bounded_extra_page"]["max_extra_pages"] == 1
    assert depth["bounded_extra_page"]["cumulative_depth"] == 500
    assert depth["batch_recomputation"]


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
            if gate["version"] == "v4":
                gate["earliest_possible_end_utc"] = "2027-01-18T13:00:00Z"
                gate["evaluation_may_not_start_before"] = "2027-01-18T13:00:00Z"

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("gate" in failure for failure in failures), failures


def test_the_verifier_detects_a_narrowed_identity_rule(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["universe"]["expansion_scope"]["prior_universe_asset_identity"]["sources"] = [
            source
            for source in spec["universe"]["expansion_scope"]["prior_universe_asset_identity"]["sources"]
            if source["universe_version"] != "v4"
        ]

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("identity rule" in failure for failure in failures), failures


def test_the_verifier_detects_a_wrong_code_digest(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["code_identity"]["hashed_set_digest"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("hashed-set canonical digest" in failure for failure in failures), failures


def test_the_verifier_detects_a_modified_hashed_source_tree(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / "src" / "breakout_research" / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
    failures = _failures(root)
    assert any("hashed-set canonical digest" in failure for failure in failures), failures


def test_the_verifier_detects_a_self_authorizing_specification(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["authorization"]["execution_authorized"] = True

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("execution_authorized" in failure for failure in failures), failures


def test_the_verifier_detects_an_existing_v5_run_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "ledger_v5.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("v5 run artifact" in failure for failure in failures), failures


def test_the_verifier_detects_a_stage_artifact_that_is_not_bound_to_the_specification(
    tmp_path,
):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "universe_manifest_v5.json"
    if not path.exists():
        pytest.skip("the v5 universe manifest is not present in this checkout")
    stage = json.loads(path.read_text(encoding="utf-8"))
    stage["specification_hash"] = "0" * 64
    path.write_text(json.dumps(stage, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("not bound to this specification" in failure for failure in failures), failures


def test_the_verifier_detects_a_broken_expansion_log_chain(tmp_path):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "v_universe_expansion_log.json"
    log = json.loads(path.read_text(encoding="utf-8"))
    log["entries"][0]["previous_entry_hash"] = "0" * 64
    path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("expansion log" in failure for failure in failures), failures


def test_the_verifier_detects_an_exposed_confirmatory_window(tmp_path):
    root = _mirror_repo(tmp_path)
    path = root / "research" / "data_manifest_v3.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["confirmatory_window"]["holdout_exposed_count"] = 3
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    failures = _failures(root)
    assert any("holdout_exposed_count" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_supersedes_hash(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(spec):
        spec["supersedes"]["universe_manifest_hash"] = "0" * 64

    _rewrite_spec(root, mutate)
    failures = _failures(root)
    assert any("supersedes chain" in failure for failure in failures), failures

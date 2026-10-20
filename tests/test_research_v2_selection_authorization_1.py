"""Tests for the preregistered v2 selection authorization 1.

``configs/research_v2_selection_authorization_1.json`` authorizes exactly one
bounded v2 selection grid run over the frozen candidate set. The tests prove
that

* the authorization is self-hashing and reproducible from its producer;
* the authorized scope is exactly the frozen candidate set, which is the set of
  validated constituents of the v2 universe manifest;
* the bounds are the bounds of the v2 execution amendment and the planned run
  fits inside them;
* the data boundary is the confirmatory-window start of the candidate freeze,
  and the confirmatory window, the v1 holdout and the v1 cycle-0 units are
  excluded from the selection;
* the selection rule is the unchanged v1 rule;
* the code identity recomputes from the source tree under the canonical digest
  rule of BRAIN-009, and the hashed source set is byte-unchanged;
* the output paths are the v2 paths of the execution amendment and none of them
  is a v1 path;
* the execution path lives outside the hashed set, holds the recorded modules
  and accepts this authorization;
* **the verifier is not vacuous**: tampering with the authorization, with the
  scope, with the bounds, with the data boundary, with the selection rule, with
  the code identity, with the output paths, with the hashed source tree or with
  the executed state is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from breakout_research.config import compute_code_hash

from code_identity_helpers import ordered_digest_variants

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION_PATH = REPO_ROOT / "configs" / "research_v2_selection_authorization_1.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_execution_amendment_1.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
DATA_MANIFEST_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_campaign"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_research_v2_selection_authorization_1",
    "scripts/verify_research_v2_selection_authorization_1.py",
)
producer = _load_module(
    "build_v2_selection_authorization_1", "scripts/build_v2_selection_authorization_1.py"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    The two source trees are copied for real, so a test may modify them without
    ever writing to the working tree. The large result directories are skipped:
    the verifier never reads them. The v2 shard directory is replaced by an
    empty placeholder of the same shape, because the verifier only checks that
    the shards exist; their record-level verification is the deeper check of
    ``scripts/verify_v2_selection_run.py``.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {
        Path("research/results_shards"),
        Path("research/campaign_cycles"),
        Path("research/shards_v2"),
    }
    copy_relative = {Path(HASHED_SET_ROOT), Path(EXECUTION_PATH_ROOT)}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in skip_relative:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if relative in copy_relative:
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    (root / "research" / "shards_v2" / "v2-campaign").mkdir(parents=True, exist_ok=True)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper(
    root: Path,
    mutate: Callable[[Dict[str, Any]], None],
    rehash: bool = True,
) -> Path:
    authorization = _load(AUTHORIZATION_PATH)
    mutate(authorization)
    if rehash:
        authorization["manifest_hash"] = verifier.compute_manifest_hash(
            authorization, ("manifest_hash",)
        )
    _replace(root, "configs/research_v2_selection_authorization_1.json", authorization)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_the_authorization_is_self_hashing() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    recomputed = verifier.compute_manifest_hash(authorization, ("manifest_hash",))
    assert recomputed == authorization["manifest_hash"]


def test_the_authorization_is_reproducible_from_its_producer() -> None:
    rebuilt = producer.build(REPO_ROOT)
    on_disk = _load(AUTHORIZATION_PATH)
    assert rebuilt == on_disk


def test_the_authorized_scope_is_the_frozen_candidate_set() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    freeze = _load(FREEZE_PATH)
    scope = authorization["authorized_run"]["scope"]
    frozen = freeze["frozen_candidate_set"]
    assert scope["constituents"] == frozen["constituents"]
    assert scope["binance_pairs"] == frozen["binance_pairs"]
    assert scope["count"] == len(frozen["constituents"]) == 18
    assert scope["bound_to_freeze_hash"] == freeze["manifest_hash"]


def test_the_frozen_candidate_set_is_the_validated_v2_universe() -> None:
    universe = _load(UNIVERSE_PATH)
    validated = sorted(
        str(entry["symbol"])
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    freeze = _load(FREEZE_PATH)
    assert sorted(freeze["frozen_candidate_set"]["binance_pairs"]) == validated
    assert len(validated) == 18


def test_the_bounds_are_the_bounds_of_the_execution_amendment() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    amendment = _load(AMENDMENT_PATH)
    bounds = authorization["authorized_run"]["bounds"]
    recorded = amendment["v2_selection_authorization"]["bounds"]
    for key in ("max_assets", "max_configs_per_asset", "max_total_config_units", "attempts"):
        assert bounds[key] == recorded[key]
    assert bounds["attempts"] == 1
    assert bounds["planned_config_units"] == 18 * bounds["max_configs_per_asset"]
    assert bounds["planned_config_units"] <= bounds["max_total_config_units"]


def test_the_data_boundary_is_the_confirmatory_window_start() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    freeze = _load(FREEZE_PATH)
    boundary = authorization["authorized_run"]["data_boundary"]
    assert boundary["candles_before_utc"] == freeze["data_boundary"]["confirmatory_window_start_utc"]
    assert boundary["confirmatory_window_never_read_during_selection"] is True
    assert boundary["v1_holdout_never_reused"] is True
    assert boundary["v1_cycle0_units_never_mixed"] is True
    assert boundary["holdout_exposed_count_stays_zero_during_selection"] is True
    assert boundary["provider_requests"] == 0


def test_the_selection_rule_is_the_unchanged_v1_rule() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    spec_v2 = _load(SPEC_V2_PATH)
    rule = authorization["authorized_run"]["selection_rule"]
    digest = verifier.sha256_bytes(verifier.canonical(spec_v1["selection"]).encode("utf-8"))
    assert rule["selection_block_sha256"] == digest
    assert verifier.canonical(spec_v1["selection"]) == verifier.canonical(spec_v2["selection"])
    assert rule["max_candidates_per_asset"] == spec_v1["selection"]["max_candidates_per_asset"]


def test_the_code_identity_recomputes_from_the_source_tree() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    identity = authorization["authorized_run"]["code_identity"]
    hashed_set = verifier.canonical_source_digest(REPO_ROOT / HASHED_SET_ROOT)
    execution_path = verifier.canonical_source_digest(REPO_ROOT / EXECUTION_PATH_ROOT)
    assert identity["hashed_set_digest"] == hashed_set
    assert identity["execution_path_digest"] == execution_path
    assert identity["run_code_identity"] == verifier.run_code_identity(hashed_set, execution_path)


def test_the_hashed_source_set_is_byte_unchanged() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    campaign_authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    # The identity of the hashed set is the portable canonical digest (BRAIN-009).
    assert verifier.canonical_source_digest(REPO_ROOT / HASHED_SET_ROOT) == (
        "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
    )
    # The authorized value of record is cross-checked against the v1 campaign
    # authorization; it is never compared with the live ordered digest.
    assert authorization["authorized_run"]["code_identity"]["authorized_code_hash"] == (
        campaign_authorization["code_hash"]
    )
    # The live ordered digest is an environment fact: it still identifies this
    # tree under the checkout's own enumeration order, and the authorized digest
    # is one of the digests that this tree produces.
    variants = ordered_digest_variants(REPO_ROOT / HASHED_SET_ROOT)
    assert compute_code_hash() in variants
    assert campaign_authorization["code_hash"] in variants


def test_the_output_paths_are_the_v2_paths_and_not_v1_paths() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    amendment = _load(AMENDMENT_PATH)
    paths = authorization["authorized_run"]["paths"]
    recorded = amendment["v2_selection_authorization"]["paths"]
    for key in ("shards_dir", "ledger", "results_manifest", "results_stream", "checkpoint"):
        assert paths[key] == recorded[key]
        assert not paths[key].startswith("research/results_shards")
        assert paths[key] != "research/results.jsonl"
        assert paths[key] != "research_state/checkpoint.json"


def test_the_execution_path_is_outside_the_hashed_set() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    execution = authorization["authorized_run"]["execution_path"]
    package = REPO_ROOT / EXECUTION_PATH_ROOT
    assert package.is_dir()
    assert not package.resolve().is_relative_to((REPO_ROOT / HASHED_SET_ROOT).resolve())
    live_modules = sorted(path.relative_to(package).as_posix() for path in package.rglob("*.py"))
    assert sorted(execution["modules"]) == live_modules
    assert execution["engine_is_reused_unchanged"] is True
    assert execution["hashed_set_untouched"] is True


def test_the_authorization_authorizes_one_run_and_nothing_else() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    run = authorization["authorized_run"]
    assert run["authorized"] is True
    assert run["max_runs"] == 1
    assert run["run_id"]
    assert run["campaign_id"]
    not_authorized = authorization["not_authorized"]
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "v1_reauthorization_authorized",
        "source_tree_change_authorized",
    ):
        assert not_authorized[flag] is False


def test_the_stopping_conditions_rollback_rule_and_falsifiers_are_recorded() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    run = authorization["authorized_run"]
    assert len(run["stopping_conditions"]) >= 3
    assert any("report" in condition.lower() for condition in run["stopping_conditions"])
    assert run["rollback_rule"]
    assert len(run["falsifiers"]) >= 6
    assert authorization["residual_limitations"]


def test_the_execution_path_accepts_the_authorization() -> None:
    import sys

    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    from v2_campaign import runner

    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    assert plan.run_id == _load(AUTHORIZATION_PATH)["authorized_run"]["run_id"]
    assert plan.counts["config_units"] == 18 * 2304
    assert plan.boundary_ms > 0
    assert plan.scope["binance_pairs"][0] == "ADAUSDT"


def _completed_ledger(authorization: Dict[str, Any]) -> Dict[str, Any]:
    """A ledger of a *completed* run of the authorized run.

    It is used by the tamper tests of the executed state, so that they do not
    depend on whether the real run has already been performed.
    """
    run = authorization["authorized_run"]
    pairs = list(run["scope"]["binance_pairs"])
    constituents = list(run["scope"]["constituents"])
    planned = int(run["bounds"]["planned_execution_units"])
    return {
        "artifact": "v2_selection_ledger",
        "artifact_version": "v2-selection-ledger-1",
        "run_id": run["run_id"],
        "campaign_id": run["campaign_id"],
        "run_phase": run["run_phase"],
        "status": "COMPLETED",
        "started_utc": "2026-10-20T00:00:00Z",
        "completed_utc": "2026-10-20T01:00:00Z",
        "authorization_manifest_hash": authorization["manifest_hash"],
        "specification_hash": "synthetic",
        "scope": {
            "constituents": constituents,
            "binance_pairs": pairs,
            "count": len(constituents),
            "excluded_after_validation": dict(run["scope"]["excluded_after_validation"]),
        },
        "counts": {
            "config_units": int(run["bounds"]["planned_config_units"]),
            "execution_units": planned,
            "executed": planned,
            "skipped_already_complete": 0,
            "records_written": planned,
        },
        "selection": {
            "assets_evaluated": len(pairs),
            "assets_with_candidate": [],
            "assets_without_candidate": list(pairs),
            "assets_without_candidate_reported": True,
            "outcome": "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE",
            "per_asset": {
                pair: {
                    "status": "NO_CANDIDATE",
                    "economic_status": "NO_CANDIDATE",
                    "config_id": None,
                    "counts": {},
                }
                for pair in pairs
            },
        },
        "holdout_exposed_count": 0,
        "runs": [],
    }


def _write_completed_ledger(root: Path) -> Dict[str, Any]:
    """Put a completed ledger of the authorized run into the mirrored tree."""
    ledger = _completed_ledger(_load(AUTHORIZATION_PATH))
    _replace(root, "research/ledger_v2.json", ledger)
    return ledger


def _real_checkpoint() -> Dict[str, Any]:
    """The checkpoint of the performed run, or a synthetic one before it ran."""
    path = REPO_ROOT / "research_state" / "checkpoint_v2.json"
    if path.exists():
        return _load(path)
    authorization = _load(AUTHORIZATION_PATH)
    return {
        "protocol_hash": _load(SPEC_V2_PATH)["specification_hash"],
        "code_hash": authorization["authorized_run"]["code_identity"]["run_code_identity"],
        "current_asset_index": 0,
        "current_config_index": 0,
        "current_fold_index": 0,
        "current_cost_index": 0,
        "completed_records": 0,
        "last_verified_record": 0,
        "holdout_exposed_count": 0,
        "next_unit": {},
        "timestamp_utc": "2026-10-20T00:00:00Z",
        "pilot_completed": True,
        "pilot_passed": True,
    }


def _real_results_manifest() -> Dict[str, Any]:
    """The results manifest of the performed run, or a synthetic one."""
    path = REPO_ROOT / "research" / "results_manifest_v2.json"
    if path.exists():
        return _load(path)
    authorization = _load(AUTHORIZATION_PATH)
    run = authorization["authorized_run"]
    return {
        "schema_version": "result-shard-v1",
        "campaign_id": run["campaign_id"],
        "specification_hash": _load(SPEC_V2_PATH)["specification_hash"],
        "code_hash": run["code_identity"]["run_code_identity"],
        "data_manifest_hash": _load(DATA_MANIFEST_PATH)["manifest_hash"],
        "shards": [],
        "total_records": 0,
        "total_bytes": 0,
    }


def test_the_executed_state_is_consistent_with_the_authorization() -> None:
    """The state of the performed run agrees with the authorization.

    Before the run this test asserts the not-executed state; after the run it
    asserts the executed state. Either way the v1 evidence is byte-identical
    and no confirmatory exposure is recorded.
    """
    ledger_path = REPO_ROOT / "research" / "ledger_v2.json"
    executed = ledger_path.exists()
    data_manifest = _load(DATA_MANIFEST_PATH)
    assert data_manifest["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data_manifest["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    if not executed:
        for relative in (
            "research/shards_v2",
            "research/results_manifest_v2.json",
            "research/results_v2.jsonl",
            "research_state/checkpoint_v2.json",
        ):
            assert not (REPO_ROOT / relative).exists(), relative
        return
    authorization = _load(AUTHORIZATION_PATH)
    run = authorization["authorized_run"]
    ledger = _load(ledger_path)
    assert ledger["run_id"] == run["run_id"]
    assert ledger["campaign_id"] == run["campaign_id"]
    assert ledger["authorization_manifest_hash"] == authorization["manifest_hash"]
    assert ledger["status"] in {"RUNNING", "INTERRUPTED", "COMPLETED"}
    assert ledger["holdout_exposed_count"] == 0
    assert ledger["scope"]["binance_pairs"] == run["scope"]["binance_pairs"]
    assert ledger["counts"]["config_units"] <= run["bounds"]["max_total_config_units"]
    assert ledger["counts"]["execution_units"] <= run["bounds"]["planned_execution_units"]
    assert (REPO_ROOT / "research" / "shards_v2" / "v2-campaign").is_dir()
    assert (REPO_ROOT / "research_state" / "checkpoint_v2.json").exists()
    assert (REPO_ROOT / "research" / "results_manifest_v2.json").exists()


def test_the_v1_artifacts_are_byte_identical() -> None:
    for relative, digest in V1_ARTIFACT_SHA256.items():
        assert verifier.sha256_file(REPO_ROOT / relative) == digest, relative


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"manifest_hash": "0" * 64}), rehash=False)
    failures = _failures(root)
    assert failures
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["scope"]["constituents"].append("ZZZ"),
    )
    failures = _failures(root)
    assert any("not the frozen candidate set" in failure for failure in failures)


def test_verifier_detects_a_narrowed_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["scope"]["binance_pairs"].pop(),
    )
    failures = _failures(root)
    assert any("not the frozen Binance pairs" in failure for failure in failures)


def test_verifier_detects_a_changed_bound(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["bounds"].update({"max_assets": 64}),
    )
    failures = _failures(root)
    assert any("differs from the bound recorded by execution" in failure for failure in failures)


def test_verifier_detects_a_data_boundary_inside_the_confirmatory_window(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["data_boundary"].update(
            {"candles_before_utc": "2027-01-17T22:00:00Z"}
        ),
    )
    failures = _failures(root)
    assert any("not the confirmatory window start" in failure for failure in failures)


def test_verifier_detects_a_selection_rule_that_is_not_the_v1_rule(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["selection_rule"].update(
            {"selection_block_sha256": "1" * 64}
        ),
    )
    failures = _failures(root)
    assert any("not the unchanged v1 selection rule" in failure for failure in failures)


def test_verifier_detects_a_stale_execution_path_digest(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["code_identity"].update(
            {"execution_path_digest": "2" * 64}
        ),
    )
    failures = _failures(root)
    assert any("execution-path digest does not match" in failure for failure in failures)


def test_verifier_detects_a_modified_hashed_source_tree(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    failures = _failures(root)
    assert any("hashed-set digest does not match" in failure for failure in failures)


def test_verifier_detects_a_modified_execution_path(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / EXECUTION_PATH_ROOT / "runner.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    failures = _failures(root)
    assert any("execution-path digest does not match" in failure for failure in failures)


def test_verifier_detects_a_v1_output_path(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["paths"].update(
            {"results_stream": "research/results.jsonl"}
        ),
    )
    failures = _failures(root)
    assert any("results.jsonl" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document["authorized_run"].update({"max_runs": 2}))
    failures = _failures(root)
    assert any("one attempt" in failure for failure in failures)


def test_verifier_detects_an_authorized_confirmatory_evaluation(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["not_authorized"].update(
            {"confirmatory_evaluation_authorized": True}
        ),
    )
    failures = _failures(root)
    assert any("confirmatory_evaluation_authorized" in failure for failure in failures)


def test_verifier_detects_an_execution_artifact_without_a_ledger(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "shards_v2" / "v2-campaign").mkdir(parents=True, exist_ok=True)
    (root / "research" / "ledger_v2.json").unlink(missing_ok=True)
    failures = _failures(root)
    assert any("without the ledger of the authorized run" in failure for failure in failures)


def test_verifier_detects_a_ledger_that_names_another_run(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    ledger["run_id"] = "v2-selection-some-other-run"
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any("does not record the authorized run" in failure for failure in failures)


def test_verifier_detects_counts_above_the_authorized_bounds(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    ledger["counts"]["records_written"] = 10_000_000
    ledger["counts"]["executed"] = 10_000_000
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any(
        "more records than the authorized execution-unit bound" in failure
        for failure in failures
    )


def test_verifier_detects_ledger_counts_that_do_not_add_up(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    ledger["counts"]["skipped_already_complete"] = 7
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any("counts do not add up" in failure for failure in failures)


def test_verifier_detects_a_ledger_with_a_nonzero_holdout_exposure(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    ledger["holdout_exposed_count"] = 1
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any("ledger records a confirmatory exposure" in failure for failure in failures)


def test_verifier_detects_a_confirmatory_exposure_in_the_checkpoint(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _write_completed_ledger(root)
    checkpoint = _real_checkpoint()
    checkpoint["holdout_exposed_count"] = 3
    _replace(root, "research_state/checkpoint_v2.json", checkpoint)
    failures = _failures(root)
    assert any("checkpoint records a confirmatory exposure" in failure for failure in failures)


def test_verifier_detects_a_checkpoint_bound_to_another_code_identity(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _write_completed_ledger(root)
    checkpoint = _real_checkpoint()
    checkpoint["code_hash"] = "0" * 64
    _replace(root, "research_state/checkpoint_v2.json", checkpoint)
    failures = _failures(root)
    assert any(
        "checkpoint is not bound to the authorized run code identity" in failure
        for failure in failures
    )


def test_verifier_detects_a_results_manifest_bound_to_another_code_identity(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _write_completed_ledger(root)
    manifest = _real_results_manifest()
    manifest["code_hash"] = "0" * 64
    _replace(root, "research/results_manifest_v2.json", manifest)
    failures = _failures(root)
    assert any(
        "results manifest is not bound to the authorized run code identity" in failure
        for failure in failures
    )


def test_verifier_detects_a_selection_outcome_that_omits_an_asset(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    omitted = ledger["selection"]["per_asset"].pop("BTCUSDT")
    ledger["selection"]["assets_evaluated"] -= 1
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any("omits the asset BTCUSDT" in failure for failure in failures)
    assert omitted["status"] == "NO_CANDIDATE"


def test_verifier_detects_a_selection_outcome_that_hides_the_missing_candidates(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _write_completed_ledger(root)
    ledger["selection"]["assets_without_candidate_reported"] = False
    _replace(root, "research/ledger_v2.json", ledger)
    failures = _failures(root)
    assert any(
        "does not report the assets without a candidate" in failure for failure in failures
    )


def test_verifier_detects_a_v2_result_row(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "research" / "results.jsonl"
    if target.is_symlink():
        target.unlink()
    target.write_text('{"campaign_id": "v2-campaign"}\n', encoding="utf-8")
    failures = _failures(root)
    assert any("v2 result row exists" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "research" / "candidate_manifest.json"
    if target.is_symlink() or target.exists():
        target.unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)

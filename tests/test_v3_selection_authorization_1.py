"""Tests for the preregistered v3 selection authorization 1.

``configs/research_v3_selection_authorization_1.json`` authorizes exactly one
bounded v3 selection grid run over the frozen v3 candidate set, with the
BRAIN-013 benchmark rule and the v1/v2 alignment-deviation disclosure bound
into it. The tests prove that

* the authorization is self-hashing and reproduced byte for byte by its
  producer;
* the authorized scope is exactly the frozen candidate set, which is the set of
  validated constituents of the v3 universe manifest;
* the bounds are the bounds of the frozen scope and of the inherited grid, and
  the planned run fits inside them;
* the data boundary is the confirmatory-window start of the candidate freeze,
  and the confirmatory window, the v1 holdout and the v2 confirmatory window
  are excluded from the selection;
* the selection rule is the unchanged v1 rule;
* the code identity recomputes from the source tree under the canonical digest
  rule of BRAIN-009, and the hashed source set is byte-unchanged;
* the benchmark rule is bound: the dataset, its recomputed content hash, the
  alignment rule, the fail-closed conditions and the "no configuration is
  dropped" rule, and the effective data-manifest identity;
* the deviation disclosure names the evidence file and its recomputed counts;
* the execution path lives outside the hashed set, holds the recorded modules
  and accepts this authorization without executing anything;
* **the verifier is not vacuous**: tampering with the authorization, with the
  scope, with the bounds, with the data boundary, with the selection rule,
  with the code identity, with the benchmark rule, with the disclosure, with
  the output paths, with the hashed source tree or with the executed state is
  detected.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

AUTHORIZATION_PATH = REPO_ROOT / "configs" / "research_v3_selection_authorization_1.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_PATH = (
    REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
)
FREEZE_AMENDMENT_2_PATH = (
    REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
)
DATA_AMENDMENT_PATH = (
    REPO_ROOT / "configs" / "research_v3_data_manifest_amendment_1.json"
)
EXECUTION_AMENDMENT_PATH = (
    REPO_ROOT / "configs" / "research_v3_execution_amendment_1.json"
)
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V3_PATH = REPO_ROOT / "configs" / "research_v3.json"
DATA_MANIFEST_PATH = REPO_ROOT / "research" / "data_manifest_v3.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v3.json"
DEVIATION_PATH = (
    REPO_ROOT / "research" / "v3_evidence" / "v1_v2_btc_alignment_deviation.json"
)

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v3_campaign"

ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called"
)

V3_EXECUTION_ARTIFACTS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
)


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v3_selection_authorization_1",
    "scripts/verify_v3_selection_authorization_1.py",
)
producer = _load_module(
    "build_v3_selection_authorization_1", "scripts/build_v3_selection_authorization_1.py"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    The two source trees are copied for real, so a test may modify them without
    ever writing to the working tree. The large result directories are skipped:
    the verifier never reads them.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {
        Path("research/results_shards"),
        Path("research/campaign_cycles"),
        Path("research/shards_v2"),
        Path("research/shards_v3"),
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
            if relative in copy_relative or any(
                root_path in relative.parents for root_path in copy_relative
            ):
                # The hashed set and the execution path are copied for real,
                # recursively: a symlink would let a test write through it into
                # the working tree.
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
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
    _replace(root, "configs/research_v3_selection_authorization_1.json", authorization)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _execution_state() -> Dict[str, Any]:
    """The state of the v3 execution artifacts: existence, size and mtime."""
    state: Dict[str, Any] = {}
    for relative in V3_EXECUTION_ARTIFACTS:
        path = REPO_ROOT / relative
        if path.is_dir():
            state[relative] = ("dir", sorted(child.name for child in path.iterdir()))
        elif path.exists():
            stat = path.stat()
            state[relative] = ("file", stat.st_size, stat.st_mtime_ns)
        else:
            state[relative] = ("absent",)
    return state


def test_the_authorization_is_self_hashing() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    recomputed = verifier.compute_manifest_hash(authorization, ("manifest_hash",))
    assert recomputed == authorization["manifest_hash"]


def test_the_authorization_is_reproduced_byte_for_byte_by_its_producer() -> None:
    rebuilt = producer.build(REPO_ROOT)
    on_disk = _load(AUTHORIZATION_PATH)
    assert rebuilt == on_disk
    rendered = json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"
    assert rendered == AUTHORIZATION_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v3_selection_authorization_1.json"
    target.unlink()
    assert producer.main(["--repo-root", str(root)]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_authorized_scope_is_the_frozen_candidate_set() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    scope = authorization["authorized_run"]["scope"]
    freeze_amendment_1 = _load(FREEZE_AMENDMENT_1_PATH)
    pairs = [
        str(member["binance_pair"])
        for member in (freeze_amendment_1["validated_candidate_set"] or {})["members"]
    ]
    assert scope["binance_pairs"] == pairs
    assert scope["count"] == len(pairs) == 6
    assert scope["bound_to_freeze_hash"] == _load(FREEZE_PATH)["manifest_hash"]
    assert scope["bound_to_universe_hash"] == _load(UNIVERSE_PATH)["manifest_hash"]
    assert scope["benchmark_is_not_a_candidate"] is True


def test_the_frozen_candidate_set_is_the_validated_v3_universe() -> None:
    universe = _load(UNIVERSE_PATH)
    validated = sorted(
        str(entry["binance_pair"])
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    authorization = _load(AUTHORIZATION_PATH)
    assert sorted(authorization["authorized_run"]["scope"]["binance_pairs"]) == validated
    assert len(validated) == 6
    assert "BTCUSDT" not in validated


def test_the_bounds_are_the_bounds_of_the_frozen_scope_and_the_grid() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    scope = authorization["authorized_run"]["scope"]
    bounds = authorization["authorized_run"]["bounds"]
    config_manifest = _load(REPO_ROOT / "research" / "config_manifest.json")
    spec_v1 = _load(SPEC_V1_PATH)
    config_count = len(config_manifest["configurations"])
    assert bounds["max_assets"] == scope["count"]
    assert bounds["max_configs_per_asset"] == config_count == 2304
    assert bounds["max_total_config_units"] == scope["count"] * config_count == 13824
    assert bounds["attempts"] == 1
    assert 1 <= bounds["max_retries_on_technical_failure"] <= 3
    assert bounds["planned_config_units"] == 13824
    assert bounds["planned_execution_units"] == (
        13824 * len(spec_v1["folds"]["window_fractions"]) * len(spec_v1["costs"]["scenarios"])
    )
    assert bounds["planned_config_units"] <= bounds["max_total_config_units"]


def test_the_data_boundary_is_the_confirmatory_window_start() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    freeze = _load(FREEZE_PATH)
    boundary = authorization["authorized_run"]["data_boundary"]
    assert boundary["candles_before_utc"] == freeze["data_boundary"][
        "confirmatory_window_start_utc"
    ] == "2026-10-20T13:00:00Z"
    for flag in (
        "development_data_only",
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v2_confirmatory_window_never_reused",
        "holdout_exposed_count_stays_zero_during_selection",
        "holdout_position_fold_never_evaluated_during_selection",
    ):
        assert boundary[flag] is True
    assert boundary["provider_requests"] == 0


def test_the_selection_rule_is_the_unchanged_v1_rule() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    spec_v3 = _load(SPEC_V3_PATH)
    rule = authorization["authorized_run"]["selection_rule"]
    digest = verifier.sha256_bytes(verifier.canonical(spec_v1["selection"]).encode("utf-8"))
    assert rule["selection_block_sha256"] == digest
    assert verifier.canonical(spec_v1["selection"]) == verifier.canonical(spec_v3["selection"])
    assert rule["max_candidates_per_asset"] == spec_v1["selection"]["max_candidates_per_asset"] == 1


def test_the_code_identity_recomputes_from_the_source_tree() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    identity = authorization["authorized_run"]["code_identity"]
    hashed_set = verifier.canonical_source_digest(REPO_ROOT / HASHED_SET_ROOT)
    execution_path = verifier.canonical_source_digest(REPO_ROOT / EXECUTION_PATH_ROOT)
    assert identity["hashed_set_digest"] == hashed_set
    assert identity["execution_path_digest"] == execution_path
    assert identity["run_code_identity"] == verifier.run_code_identity(hashed_set, execution_path)


def test_the_hashed_source_set_is_byte_unchanged() -> None:
    campaign_authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert verifier.canonical_source_digest(REPO_ROOT / HASHED_SET_ROOT) == (
        "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
    )
    authorization = _load(AUTHORIZATION_PATH)
    assert authorization["authorized_run"]["code_identity"]["authorized_code_hash"] == (
        campaign_authorization["code_hash"]
    )


def test_the_benchmark_rule_is_bound() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    benchmark = authorization["authorized_run"]["benchmark"]
    dataset = REPO_ROOT / benchmark["dataset_path"]
    assert dataset.exists()
    assert benchmark["content_hash"] == _sha256_file(dataset)
    assert benchmark["alignment_rule"] == ALIGNMENT_RULE
    assert benchmark["btc_configurations_dropped"] is False
    assert benchmark["no_forward_fill"] is True
    assert benchmark["fail_closed"]
    assert "576" in benchmark["grid_rule"]


def test_the_effective_data_manifest_identity_recomputes_and_is_bound() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    effective = authorization["authorized_run"]["effective_data_manifest"]
    base = _load(DATA_MANIFEST_PATH)
    amendment = _load(DATA_AMENDMENT_PATH)
    entry = (amendment["benchmark_asset"] or {})["entry"]

    body = json.loads(json.dumps(base))
    body.pop("manifest_hash", None)
    body.get("snapshot_identity", {}).pop("data_manifest_hash", None)
    body.setdefault("assets", {})["BTCUSDT"] = entry
    body.setdefault("content_hashes", {})["BTCUSDT"] = entry["content_hash"]
    body["benchmark_asset"] = {
        "symbol": "BTCUSDT",
        "role": "trend_filter_and_benchmark",
        "included_in_universe": True,
        "is_candidate": False,
        "content_hash": entry["content_hash"],
        "dataset_path": entry["dataset_path"],
        "first_candle_timestamp": entry["first_candle_timestamp"],
        "last_candle_timestamp": entry["last_candle_timestamp"],
        "observed_candle_count": entry["observed_candle_count"],
        "source": "configs/research_v3_data_manifest_amendment_1.json",
        "alignment_rule": (
            "the benchmark series and the asset series are aligned by UTC candle close: "
            "both are sliced to the same fold window before the frozen engine is called, "
            "and no observation is forward-filled"
        ),
    }
    recomputed = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    assert recomputed == effective["effective_data_manifest_hash"]
    assert effective["base_manifest_hash"] == base["manifest_hash"]
    assert _load(EXECUTION_AMENDMENT_PATH)["evaluation_scope"]["data_manifest_hash"] == recomputed


def test_the_deviation_disclosure_names_the_evidence_and_its_counts() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    disclosure = authorization["authorized_run"]["deviation_disclosure"]
    deviation = _load(DEVIATION_PATH)
    assert disclosure["evidence_path"] == (
        "research/v3_evidence/v1_v2_btc_alignment_deviation.json"
    )
    assert DEVIATION_PATH.exists()
    assert disclosure["records_with_btc_filter"] == (
        deviation["counts"]["records_with_btc_filter"]
    ) == 124416
    assert disclosure["total_v2_records"] == deviation["counts"]["total_v2_records"] == 497664
    assert list(disclosure["misaligned_validation_folds"]) == [0, 1, 2, 3]
    assert disclosure["not_repaired"] is True


def test_the_authorization_authorizes_one_run_and_nothing_else() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    run = authorization["authorized_run"]
    assert run["authorized"] is True
    assert run["max_runs"] == 1
    assert run["run_id"]
    assert run["campaign_id"] == "v3-campaign"
    assert run["run_phase"] == "selection_grid"
    assert run["no_execution_in_this_session"] is True
    not_authorized = authorization["not_authorized"]
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "v1_reauthorization_authorized",
        "source_tree_change_authorized",
        "second_v3_selection_run_authorized",
    ):
        assert not_authorized[flag] is False


def test_the_output_paths_are_the_v3_paths_and_not_v1_or_v2_paths() -> None:
    authorization = _load(AUTHORIZATION_PATH)
    paths = authorization["authorized_run"]["paths"]
    assert paths["shards_dir"] == "research/shards_v3"
    assert paths["ledger"] == "research/ledger_v3.json"
    assert paths["results_manifest"] == "research/results_manifest_v3.json"
    assert paths["results_stream"] == "research/results_v3.jsonl"
    assert paths["checkpoint"] == "research_state/checkpoint_v3.json"
    assert paths["never_use_v1_paths"] is True
    assert paths["never_use_v2_paths"] is True
    for key, value in paths.items():
        if not isinstance(value, str):
            continue
        assert not value.startswith("research/results_shards")
        assert value not in {"research/results.jsonl", "research_state/checkpoint.json"}


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


def test_the_execution_path_accepts_the_authorization_without_executing_it() -> None:
    import sys

    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    from v3_campaign import runner

    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    authorization = _load(AUTHORIZATION_PATH)
    assert plan.run_id == authorization["authorized_run"]["run_id"]
    assert plan.campaign_id == "v3-campaign"
    assert plan.counts["config_units"] == 6 * 2304
    assert plan.boundary_ms > 0
    assert plan.scope["binance_pairs"][0] == "SHIBUSDT"
    # Building the plan runs nothing: the v3 execution artifacts are exactly
    # what they were before the plan was built.
    #
    # The rule "no v3 execution artifact exists" was replaced, not deleted: it
    # was true while the authorized run had not been performed, and it is false
    # by design once the run exists. The replacement is state-independent and
    # stronger: building a plan must change nothing.
    before = _execution_state()
    runner.build_plan(runner.default_workspace(REPO_ROOT))
    assert _execution_state() == before


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
        lambda document: document["authorized_run"]["scope"]["binance_pairs"].append("ZZZUSDT"),
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
    assert any("not the frozen candidate set" in failure for failure in failures)


def test_verifier_detects_a_changed_bound(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["bounds"].update({"max_assets": 64}),
    )
    failures = _failures(root)
    assert any("authorized asset bound" in failure for failure in failures)


def test_verifier_detects_a_data_boundary_inside_the_confirmatory_window(
    tmp_path: Path,
) -> None:
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


def test_verifier_detects_dropped_btc_configurations(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["benchmark"].update(
            {"btc_configurations_dropped": True}
        ),
    )
    failures = _failures(root)
    assert any("forbid dropping the BTC configurations" in failure for failure in failures)


def test_verifier_detects_an_unbound_benchmark_dataset(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["benchmark"].update(
            {"content_hash": "3" * 64}
        ),
    )
    failures = _failures(root)
    assert any("benchmark content hash does not match" in failure for failure in failures)


def test_verifier_detects_a_dropped_alignment_rule(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["benchmark"].update(
            {"alignment_rule": "the engine pairs the series by index"}
        ),
    )
    failures = _failures(root)
    assert any("does not bind the benchmark alignment rule" in failure for failure in failures)


def test_verifier_detects_an_unbound_effective_data_manifest_identity(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["effective_data_manifest"].update(
            {"effective_data_manifest_hash": "4" * 64}
        ),
    )
    failures = _failures(root)
    assert any("effective data-manifest identity" in failure for failure in failures)


def test_verifier_detects_a_dropped_deviation_disclosure(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["deviation_disclosure"].update(
            {"records_with_btc_filter": 93312}
        ),
    )
    failures = _failures(root)
    assert any("deviation count differs from the evidence" in failure for failure in failures)


def test_verifier_detects_an_execution_artifact_without_a_ledger(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "shards_v3" / "v3-campaign").mkdir(parents=True, exist_ok=True)
    # The case under test is an execution artifact *without* the ledger of the
    # authorized run, so the ledger is removed from the mirror as well.
    ledger = root / "research" / "ledger_v3.json"
    if ledger.is_symlink() or ledger.exists():
        ledger.unlink()
    failures = _failures(root)
    assert any("without the ledger of the authorized run" in failure for failure in failures)


def test_verifier_detects_a_missing_v1_anchor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "research" / "candidate_manifest.json"
    if target.is_symlink() or target.exists():
        target.unlink()
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


@pytest.mark.parametrize(
    "verifier_name",
    [
        "verify_v3_data_manifest_amendment_1",
        "verify_v3_candidate_freeze_amendment_2",
        "verify_v3_execution_amendment_1",
    ],
)
def test_the_cascade_verifiers_detect_a_broken_selection_authorization(
    tmp_path: Path, verifier_name: str
) -> None:
    """The state-adaptive cascade rule is not vacuous.

    The cascade authorizes nothing by itself, and the selection authorization is
    a separate, versioned artifact. Once it exists it must be the hash-bound
    artifact that permits exactly one bounded selection run over the frozen
    candidate set: a broken authorization makes the cascade verifiers fail.
    """
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["authorized_run"]["scope"]["binance_pairs"].append("ZZZUSDT"),
    )
    cascade = _load_module(verifier_name, REPO_ROOT / "scripts" / f"{verifier_name}.py")
    report = cascade.verify(root)
    assert report["ok"] is False
    assert any("frozen candidate set" in failure for failure in report["failures"])


@pytest.mark.parametrize(
    "verifier_name",
    [
        "verify_v3_data_manifest_amendment_1",
        "verify_v3_candidate_freeze_amendment_2",
        "verify_v3_execution_amendment_1",
    ],
)
def test_the_cascade_verifiers_accept_the_repository(verifier_name: str) -> None:
    cascade = _load_module(verifier_name, REPO_ROOT / "scripts" / f"{verifier_name}.py")
    report = cascade.verify(REPO_ROOT)
    assert report["ok"] is True, report.get("failures")
    assert report.get("failures") == []

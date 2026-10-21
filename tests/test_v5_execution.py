"""Tests for the preregistered v5 execution protocol, its amendment and their verifier.

``configs/research_v5_execution.json`` records the v5 execution protocol and
``configs/research_v5_execution_amendment_1.json`` supplies the bindings the
first publication did not carry.  The **effective** protocol is the amendment
for the blocks it restates and the protocol for the blocks it does not.  The
rules these tests pin are:

* both documents are self-hashing and are **reproduced byte for byte** by
  their producers;
* the amendment names the protocol it amends by its **recomputed** manifest
  hash and its **recomputed** file digest, and states the precedence rule;
* the effective evaluation scope is exactly the frozen candidate set, which is
  the set of validated constituents of the v5 universe manifest;
* the **benchmark rule** is bound: the dataset, its recomputed content hash,
  its recomputed candle count and bounds, the alignment rule, the fail-closed
  list and the "no configuration is dropped" rule -- and the v4 chain's
  benchmark dataset, whose candles close inside the open v2 confirmatory
  window, is refused;
* the **inherited rules** are the v1 rules, bound by a digest recomputed from
  ``configs/research_v1.json``; the grid still enumerates 2,304 combinations
  and the single confirmatory criterion is the unchanged v1 selection rule;
* the code-hash constraint places the v5 execution path outside the hashed set;
* the execution authorization authorizes nothing and the deviation disclosure
  records that v5 has no prior deviation to disclose;
* the ``supersedes`` chain names the v4 execution protocol with recomputed
  identities, and no v5 run artifact exists.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v5_execution.json"
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v5_execution_amendment_1.json"
AMENDMENT_2_PATH = REPO_ROOT / "configs" / "research_v5_execution_amendment_2.json"
V4_PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v4_execution.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v5.json"
V4_BENCHMARK_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v5_execution", "scripts/verify_v5_execution.py")
producer = _load_module("build_v5_execution", "scripts/build_v5_execution.py")
amendment_producer = _load_module(
    "build_v5_execution_amendment_1", "scripts/build_v5_execution_amendment_1.py"
)
amendment_2_producer = _load_module(
    "build_v5_execution_amendment_2", "scripts/build_v5_execution_amendment_2.py"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap even though the v5 chain
    carries ~50 MB of candle datasets. The tamper controls replace single
    files, and ``_replace`` unlinks the symlink before writing.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if target.is_symlink() or target.exists():
                target.unlink()
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


def _tamper(root: Path, mutate, relative: str, rehash: bool = True) -> Path:
    document = _load(REPO_ROOT / relative)
    mutate(document)
    if rehash:
        document["manifest_hash"] = verifier.compute_manifest_hash(document, ("manifest_hash",))
    _replace(root, relative, document)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_the_protocol_is_self_hashing() -> None:
    protocol = _load(PROTOCOL_PATH)
    assert verifier.compute_manifest_hash(protocol, ("manifest_hash",)) == protocol["manifest_hash"]


def test_the_protocol_is_reproduced_byte_for_byte_by_its_producer() -> None:
    rebuilt = producer.build(REPO_ROOT)
    assert rebuilt == _load(PROTOCOL_PATH)
    rendered = json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"
    assert rendered == PROTOCOL_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v5_execution.json"
    target.unlink()
    assert producer.main(["--repo-root", str(root)]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_amendment_is_self_hashing_and_names_the_protocol() -> None:
    amendment = _load(AMENDMENT_PATH)
    protocol = _load(PROTOCOL_PATH)
    assert verifier.compute_manifest_hash(amendment, ("manifest_hash",)) == amendment["manifest_hash"]
    assert amendment["amends"]["file"] == "configs/research_v5_execution.json"
    assert amendment["amends"]["manifest_hash"] == protocol["manifest_hash"]
    assert "this amendment" in amendment["precedence"]["rule"]


def test_the_amendment_is_reproduced_byte_for_byte_by_its_producer() -> None:
    rebuilt = amendment_producer.build(REPO_ROOT)
    assert rebuilt == _load(AMENDMENT_PATH)
    rendered = json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"
    assert rendered == AMENDMENT_PATH.read_text(encoding="utf-8")


def test_the_amendment_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v5_execution_amendment_1.json"
    target.unlink()
    assert amendment_producer.main(["--repo-root", str(root)]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert amendment_producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_evaluation_scope_is_the_frozen_candidate_set() -> None:
    amendment = _load(AMENDMENT_PATH)
    freeze = _load(FREEZE_PATH)
    scope = amendment["evaluation_scope"]
    pairs = sorted(
        str(member["binance_pair"])
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    )
    assert list(scope["constituents"]) == pairs
    assert scope["count"] == len(pairs) == 7
    assert scope["candidate_freeze_hash"] == freeze["manifest_hash"]
    assert scope["data_manifest_hash"] == _load(DATA_PATH)["manifest_hash"]
    assert scope["universe_manifest_hash"] == _load(UNIVERSE_PATH)["manifest_hash"]
    assert scope["widening_by_reranking_forbidden"] is True


def test_the_frozen_candidate_set_is_the_validated_v5_universe() -> None:
    universe = _load(UNIVERSE_PATH)
    validated = sorted(
        str(entry["binance_pair"])
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    amendment = _load(AMENDMENT_PATH)
    assert sorted(amendment["evaluation_scope"]["constituents"]) == validated
    assert "BTCUSDT" not in validated


def test_the_benchmark_is_the_v5_cutoff_bounded_dataset() -> None:
    amendment = _load(AMENDMENT_PATH)
    benchmark = amendment["benchmark_rule"]
    dataset = REPO_ROOT / benchmark["dataset_path"]
    assert dataset.exists()
    assert benchmark["dataset_path"].startswith("research/data/candles_v5/")
    assert benchmark["content_hash"] == verifier.sha256_file(dataset)
    assert benchmark["observed_candle_count"] == 26280
    assert benchmark["alignment"] == verifier.ALIGNMENT_RULE
    assert benchmark["no_forward_fill"] is True
    assert benchmark["fail_closed"]
    assert "576" in benchmark["grid_rule"]
    assert benchmark["symbol"] == "BTCUSDT"


def test_the_v4_benchmark_dataset_is_not_reused() -> None:
    amendment = _load(AMENDMENT_PATH)
    benchmark = amendment["benchmark_rule"]
    assert benchmark["dataset_path"] != V4_BENCHMARK_PATH
    report = verifier.verify(REPO_ROOT)
    assert report["computed"]["v4_benchmark_candles_after_the_v5_cutoff"] == 13
    assert "13" in benchmark["note"]
    assert V4_BENCHMARK_PATH in benchmark["note"]


def test_the_inherited_rules_are_the_v1_rules() -> None:
    amendment = _load(AMENDMENT_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    inherited = amendment["inherited_rules"]
    assert tuple(inherited["blocks"]) == verifier.INHERITED_V1_BLOCKS
    expected = verifier.sha256_bytes(
        verifier.canonical(
            {block: spec_v1.get(block) for block in verifier.INHERITED_V1_BLOCKS}
        ).encode("utf-8")
    )
    assert inherited["blocks_digest"] == expected
    assert inherited["v1_specification_hash"] == spec_v1["specification_hash"]


def test_the_grid_still_enumerates_2304_combinations() -> None:
    spec_v1 = _load(SPEC_V1_PATH)
    grid = spec_v1["strategy_grid"]
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)
    assert total == 2304
    assert grid["total_combinations"] == 2304
    amendment = _load(AMENDMENT_PATH)
    assert amendment["inherited_rules"]["grid_total_combinations"] == 2304


def test_the_single_confirmatory_criterion_is_the_v1_rule() -> None:
    amendment = _load(AMENDMENT_PATH)
    criterion = amendment["inherited_rules"]["single_confirmatory_criterion"]
    assert "unchanged v1 selection rule" in criterion
    assert "never re-tuned" in criterion
    assert "versioned amendment" in amendment["inherited_rules"]["change_requires"]


def test_the_execution_authorization_authorizes_nothing() -> None:
    amendment = _load(AMENDMENT_PATH)
    protocol = _load(PROTOCOL_PATH)
    authorization = amendment["execution_authorization"]
    for flag in (
        "execution_authorized",
        "grid_run_authorized",
        "candle_fetch_authorized",
        "confirmatory_evaluation_authorized",
        "second_run_authorized",
    ):
        assert authorization[flag] is False
    for flag in (
        "execution_authorized",
        "campaign_authorized",
        "selection_authorized",
        "confirmatory_authorized",
    ):
        assert protocol["authorization"][flag] is False


def test_the_effective_execution_authorization_authorizes_nothing() -> None:
    """The effective block is amendment 2's, and it authorizes nothing either."""
    amendment_2 = _load(AMENDMENT_2_PATH)
    authorization = amendment_2["execution_authorization"]
    for flag in (
        "execution_authorized",
        "grid_run_authorized",
        "candle_fetch_authorized",
        "confirmatory_evaluation_authorized",
        "second_run_authorized",
    ):
        assert authorization[flag] is False


def test_the_frozen_historical_statement_stays_visible() -> None:
    """The frozen protocol and amendment 1 keep the state they recorded.

    ``selection_authorization_present = false`` was true at their publication
    instants. The blocks are hash-bound and are not edited in place, so the
    statement stays on disk and the *effective* rule is the amendment's.
    """
    amendment = _load(AMENDMENT_PATH)
    assert amendment["execution_authorization"]["selection_authorization_present"] is False
    assert "selection_authorization_present" not in (
        _load(PROTOCOL_PATH).get("authorization") or {}
    )


def test_the_amendment_2_is_self_hashing() -> None:
    amendment_2 = _load(AMENDMENT_2_PATH)
    assert (
        verifier.compute_manifest_hash(amendment_2, ("manifest_hash",))
        == amendment_2["manifest_hash"]
    )


def test_the_amendment_2_is_reproduced_byte_for_byte_by_its_producer() -> None:
    rebuilt = amendment_2_producer.build(REPO_ROOT)
    assert rebuilt == _load(AMENDMENT_2_PATH)
    rendered = json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"
    assert rendered == AMENDMENT_2_PATH.read_text(encoding="utf-8")


def test_the_amendment_2_names_the_artifacts_it_supersedes() -> None:
    amendment_2 = _load(AMENDMENT_2_PATH)
    protocol = _load(PROTOCOL_PATH)
    amendment = _load(AMENDMENT_PATH)
    amends = amendment_2["amends"]
    assert amends["file"] == "configs/research_v5_execution.json"
    assert amends["manifest_hash"] == protocol["manifest_hash"]
    assert amends["sha256"] == verifier.sha256_file(PROTOCOL_PATH)
    supersedes = amendment_2["supersedes_in_amendment_1"]
    assert supersedes["file"] == "configs/research_v5_execution_amendment_1.json"
    assert supersedes["manifest_hash"] == amendment["manifest_hash"]
    assert supersedes["sha256"] == verifier.sha256_file(AMENDMENT_PATH)
    assert supersedes["block"] == "execution_authorization"
    assert amendment_2["precedence"]["superseded"] == ["execution_authorization"]


def test_the_effective_authorization_records_the_published_selection_authorization() -> None:
    """The effective block names the authorization, by its recomputed identity."""
    amendment_2 = _load(AMENDMENT_2_PATH)
    authorization = amendment_2["execution_authorization"]
    assert authorization["selection_authorization_present"] is True
    published = _load(REPO_ROOT / authorization["selection_authorization_path"])
    assert (
        verifier.compute_manifest_hash(published, ("manifest_hash",))
        == authorization["selection_authorization_manifest_hash"]
        == published["manifest_hash"]
    )
    assert (
        verifier.sha256_file(REPO_ROOT / authorization["selection_authorization_path"])
        == authorization["selection_authorization_sha256"]
    )
    assert (
        authorization["selection_authorization_run_id"]
        == published["authorized_run"]["run_id"]
    )
    assert (
        authorization["selection_authorization_campaign_id"]
        == published["authorized_run"]["campaign_id"]
    )


def test_the_verifier_detects_a_missing_amendment_2(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v5_execution_amendment_2.json"
    target.unlink()
    failures = _failures(root)
    assert any("missing artifact" in failure for failure in failures)


def test_the_verifier_detects_an_amendment_2_that_names_another_authorization(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["execution_authorization"].update(
            {"selection_authorization_manifest_hash": "0" * 64}
        ),
        "configs/research_v5_execution_amendment_2.json",
    )
    failures = _failures(root)
    assert any("names another manifest hash" in failure for failure in failures)


def test_the_verifier_detects_an_amendment_2_that_keeps_the_stale_flag(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["execution_authorization"].update(
            {"selection_authorization_present": False}
        ),
        "configs/research_v5_execution_amendment_2.json",
    )
    failures = _failures(root)
    assert any(
        "does not record the published v5 selection authorization" in failure
        for failure in failures
    )


def test_the_verifier_detects_an_amendment_2_that_names_another_protocol(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["amends"].update({"file": "configs/research_v4_execution.json"}),
        "configs/research_v5_execution_amendment_2.json",
    )
    failures = _failures(root)
    assert any("does not name the v5 execution protocol" in failure for failure in failures)


def test_the_verifier_detects_an_amendment_2_that_is_not_bound_to_the_protocol(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["amends"].update({"manifest_hash": "0" * 64}),
        "configs/research_v5_execution_amendment_2.json",
    )
    failures = _failures(root)
    assert any(
        "names another manifest hash for the v5 execution protocol" in failure
        for failure in failures
    )


def test_the_deviation_disclosure_records_not_applicable() -> None:
    amendment = _load(AMENDMENT_PATH)
    disclosure = amendment["deviation_disclosure"]
    assert disclosure["not_applicable"] is True
    assert disclosure["records_with_btc_filter"] == 0


def test_the_code_hash_constraint_places_v5_outside_the_hashed_set() -> None:
    amendment = _load(AMENDMENT_PATH)
    constraint = amendment["code_hash_constraint"]
    assert constraint["authorized_code_hash"] == (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    )
    assert constraint["v5_execution_must_live_outside_hashed_set"] is True
    assert constraint["v5_execution_root"] == "src/v5_campaign"
    assert constraint["edit_under_src_breakout_research_forbidden_without_reauthorization"] is True


def test_the_supersedes_chain_names_the_v4_protocol() -> None:
    amendment = _load(AMENDMENT_PATH)
    v4 = _load(V4_PROTOCOL_PATH)
    supersedes = amendment["supersedes"]
    assert supersedes["specification_path"] == "configs/research_v4_execution.json"
    assert supersedes["specification_hash"] == v4["manifest_hash"]
    assert supersedes["v1_v2_v3_v4_artifacts_are_immutable"] is True


def test_no_v5_run_artifact_exists() -> None:
    for relative in verifier.V5_EXECUTION_PATHS:
        assert not (REPO_ROOT / relative).exists(), relative


# --------------------------------------------------------------------------
# the tamper controls
# --------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_benchmark_that_is_the_v3_dataset(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["benchmark_rule"].update(
            {
                "dataset_path": V4_BENCHMARK_PATH,
                "content_hash": (
                    "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"
                ),
            }
        ),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("reuses the v4 chain's benchmark dataset" in failure for failure in failures), failures


def test_the_verifier_detects_a_benchmark_hash_mismatch(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["benchmark_rule"].update({"content_hash": "3" * 64}),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("benchmark content hash does not match" in failure for failure in failures), failures


def test_the_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["evaluation_scope"]["constituents"].append("ZZZUSDT"),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("not the frozen candidate set" in failure for failure in failures), failures


def test_the_verifier_detects_an_execution_authorization_claim(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["execution_authorization"].update(
            {"execution_authorized": True}
        ),
        relative="configs/research_v5_execution_amendment_2.json",
    )
    failures = _failures(root)
    assert any("execution_authorized as false" in failure for failure in failures), failures


def test_the_verifier_detects_a_shadowed_amendment_1_block(tmp_path: Path) -> None:
    """The frozen amendment 1 may not be edited: the chain would lose its binding."""
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["execution_authorization"].update(
            {"execution_authorized": True}
        ),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert failures, failures
    assert any(
        "amendment 1" in failure for failure in failures
    ), failures


def test_the_verifier_detects_a_missing_amendment(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "configs" / "research_v5_execution_amendment_1.json").unlink()
    failures = _failures(root)
    assert any("missing artifact" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_amendment(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["amends"].update({"manifest_hash": "0" * 64}),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("another manifest hash" in failure for failure in failures), failures


def test_the_verifier_detects_a_tampered_amendment(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document.update({"created_utc": "2020-01-01T00:00:00Z"}),
        relative="configs/research_v5_execution_amendment_1.json",
        rehash=False,
    )
    failures = _failures(root)
    assert any("amendment's manifest_hash mismatch" in failure for failure in failures), failures


def test_the_verifier_detects_a_supersedes_chain_that_names_an_older_artifact(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["supersedes"].update(
            {"specification_path": "configs/research_v3_execution.json"}
        ),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("does not supersede the v4 execution protocol" in failure for failure in failures), failures


def test_the_verifier_detects_an_inherited_rules_digest_that_does_not_recompute(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["inherited_rules"].update({"blocks_digest": "4" * 64}),
        relative="configs/research_v5_execution_amendment_1.json",
    )
    failures = _failures(root)
    assert any("inherited rules digest does not recompute" in failure for failure in failures), failures


def test_the_verifier_detects_a_v5_run_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "results_manifest_v5.json").write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("v5 run artifact" in failure for failure in failures), failures

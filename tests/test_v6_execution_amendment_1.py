"""Tests for the v6 execution amendment 1 and the effective-rule resolution.

``configs/research_v6_execution.json`` recorded
``execution_authorization.selection_authorization_present = false``, which was
true at its publication instant and stale once the v6 selection authorization
was published. The repository verifier enforced that stale state, so a
corrected effective rule would have been refused -- the same failure the v5
chain recorded as BRAIN-024.

These tests pin the repair (BRAIN-027, Design A):

* the **amendment** ``configs/research_v6_execution_amendment_1.json`` exists,
  is self-hashing, names the frozen protocol and the published selection
  authorization by their **recomputed** identities, restates the
  execution-authorization block with the five authority flags still false and
  ``selection_authorization_present`` true, and states the precedence and the
  commit-before-run rule;
* the **resolution** is amendment-first and fails closed when the amendment is
  absent, unreadable, does not recompute its own hash or names another
  protocol;
* the **verifier** recomputes the world: it no longer denies a published
  selection authorization, it fails when the effective block contradicts the
  repository, and it fails when the frozen protocol's historical statement is
  edited;
* the **selection authorization** states the generic precedence rule, names no
  amendment, still authorizes exactly one bounded run and is still bound by the
  frozen execution protocol's recomputed hash;
* the **chain** is consistent: the confirmatory protocol and the runbook bind
  the republished authorization, no v6 run artifact exists, and the hashed
  source set is untouched.

The tamper controls mutate a copy of the repository and assert that the
verifier and the resolver refuse the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

PROTOCOL_RELATIVE = "configs/research_v6_execution.json"
AMENDMENT_RELATIVE = "configs/research_v6_execution_amendment_1.json"
AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"
CONFIRMATORY_PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
CONFIRMATORY_RUNBOOK_RELATIVE = "configs/research_v6_confirmatory_runbook_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v6.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v6_execution", "scripts/verify_v6_execution.py")
producer = _load_module("build_v6_execution_amendment_1", "scripts/build_v6_execution_amendment_1.py")
rules = _load_module("v6_universe_rules", "scripts/v6_universe_rules.py")
authorization_producer = _load_module(
    "build_v6_selection_authorization_1", "scripts/build_v6_selection_authorization_1.py"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap. The large trees the v6
    execution verifier never reads are skipped;
    ``test_a_clean_mirror_of_the_repository_passes`` is the guard that keeps
    the optimization honest.
    """
    root = tmp_path / "repo"
    skip_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "campaign_cycles",
        "results_shards",
        "shards_v2",
        "shards_v3",
        "shards_v4",
        "shards_v5",
        "strategies",
        "baselines",
        "candles",
        "candles_v2",
        "candles_v3",
        "candles_v4",
        "candles_v5",
    }
    skip_files = {
        "results.jsonl",
        "results_v2.jsonl",
        "results_v3.jsonl",
        "results_v4.jsonl",
        "results_v5.jsonl",
        "results_manifest.json",
        "results_manifest.legacy_707f.json",
        "results_manifest_v2.json",
        "results_manifest_v3.json",
        "results_manifest_v4.json",
        "results_manifest_v5.json",
    }
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in skip_files:
                continue
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
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write(root: Path, relative: str, document: Dict[str, Any]) -> None:
    _replace(root, relative, document)


def _rehash(document: Dict[str, Any]) -> Dict[str, Any]:
    document["manifest_hash"] = rules.compute_manifest_hash(document, ("manifest_hash",))
    return document


def _mutate(root: Path, relative: str, mutate, rehash: bool = True) -> Dict[str, Any]:
    document = _load(REPO_ROOT / relative)
    mutate(document)
    if rehash:
        _rehash(document)
    _write(root, relative, document)
    return document


def _rebind_amendment(root: Path) -> None:
    """Re-bind the amendment to the protocol currently on disk, and rehash it.

    A tamper control that edits the frozen protocol breaks the amendment's
    binding; re-binding isolates the rule under test from that side effect.
    """
    protocol = _load(root / PROTOCOL_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    amendment["amends"]["manifest_hash"] = rules.compute_manifest_hash(protocol, ("manifest_hash",))
    amendment["amends"]["sha256"] = rules.sha256_file(root / PROTOCOL_RELATIVE)
    _rehash(amendment)
    _write(root, AMENDMENT_RELATIVE, amendment)


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# stage 1: the amendment exists and is self-hashing
# --------------------------------------------------------------------------


def test_the_amendment_recomputes_its_own_manifest_hash() -> None:
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    recomputed = rules.compute_manifest_hash(amendment, ("manifest_hash",))
    assert amendment["manifest_hash"] == recomputed
    assert amendment["artifact"] == "v6_execution_amendment_1"
    assert amendment["amendment_status"] == "PUBLISHED_CORRECTION"


def test_the_amendment_names_the_frozen_protocol_by_its_recomputed_identity() -> None:
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    protocol = _load(REPO_ROOT / PROTOCOL_RELATIVE)
    amends = amendment["amends"]
    assert amends["file"] == PROTOCOL_RELATIVE
    assert amends["manifest_hash"] == rules.compute_manifest_hash(protocol, ("manifest_hash",))
    assert amends["sha256"] == rules.sha256_file(REPO_ROOT / PROTOCOL_RELATIVE)


def test_the_amendment_names_the_selection_authorization_by_its_recomputed_identity() -> None:
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    block = amendment["execution_authorization"]
    assert block["selection_authorization_path"] == AUTHORIZATION_RELATIVE
    assert block["selection_authorization_manifest_hash"] == rules.compute_manifest_hash(
        authorization, ("manifest_hash",)
    )
    assert block["selection_authorization_sha256"] == rules.sha256_file(
        REPO_ROOT / AUTHORIZATION_RELATIVE
    )
    run = authorization["authorized_run"]
    assert block["selection_authorization_run_id"] == run["run_id"]
    assert block["selection_authorization_campaign_id"] == run["campaign_id"]


def test_the_amendment_restates_the_block_with_the_authority_flags_still_false() -> None:
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    block = amendment["execution_authorization"]
    for flag in rules.V6_EXECUTION_AUTHORITY_FLAGS:
        assert block[flag] is False, flag
    assert block["selection_authorization_present"] is True
    assert amendment["precedence"]["superseded"] == ["execution_authorization"]


def test_the_amendment_states_the_precedence_and_the_commit_before_run_rule() -> None:
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    precedence = amendment["precedence"]
    assert "newest published v6 execution amendment" in precedence["rule"]
    assert "configs/research_v6_execution.json" in precedence["rule"]
    assert "fails closed" in precedence["resolution_rule"]
    assert amendment["commit_before_run"]
    assert "committed" in amendment["commit_before_run"]


def test_the_producer_reproduces_the_amendment_byte_for_byte() -> None:
    document = producer.build(REPO_ROOT)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    assert rendered == (REPO_ROOT / AMENDMENT_RELATIVE).read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_amendment_without_force(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert producer.main(["--repo-root", str(root)]) == 1
    assert producer.main(["--repo-root", str(root), "--force"]) == 0
    assert (root / AMENDMENT_RELATIVE).read_text(encoding="utf-8") == (
        REPO_ROOT / AMENDMENT_RELATIVE
    ).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# stage 2: the effective rule resolves, and fails closed
# --------------------------------------------------------------------------


def test_the_effective_rule_resolves_amendment_first() -> None:
    effective = rules.resolve_effective_v6_execution_protocol(REPO_ROOT)
    amendment = _load(REPO_ROOT / AMENDMENT_RELATIVE)
    protocol = _load(REPO_ROOT / PROTOCOL_RELATIVE)
    assert effective["execution_authorization"] == amendment["execution_authorization"]
    assert effective["_amendment_path"] == AMENDMENT_RELATIVE
    # every other block still comes from the frozen protocol
    for block in ("evaluation_scope", "benchmark_rule", "inherited_rules", "supersedes"):
        assert effective[block] == protocol[block]


def test_the_resolution_fails_closed_when_the_amendment_is_absent(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / AMENDMENT_RELATIVE).unlink()
    try:
        rules.resolve_effective_v6_execution_protocol(root)
    except rules.V6RuleError as error:
        assert "does not exist" in str(error)
    else:
        raise AssertionError("the resolution did not fail closed without the amendment")


def test_the_resolution_fails_closed_when_the_amendment_does_not_rehash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(
        root,
        AMENDMENT_RELATIVE,
        lambda document: document["execution_authorization"].__setitem__(
            "selection_authorization_scope", "an edited scope"
        ),
        rehash=False,
    )
    try:
        rules.resolve_effective_v6_execution_protocol(root)
    except rules.V6RuleError as error:
        assert "does not recompute its own manifest_hash" in str(error)
    else:
        raise AssertionError("the resolution did not fail closed on an unhashed amendment")


def test_the_resolution_fails_closed_when_the_amendment_names_another_protocol(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(root, AMENDMENT_RELATIVE, lambda document: document["amends"].__setitem__(
        "file", "configs/research_v5_execution.json"
    ))
    try:
        rules.resolve_effective_v6_execution_protocol(root)
    except rules.V6RuleError as error:
        assert "does not name the v6 execution protocol" in str(error)
    else:
        raise AssertionError("the resolution did not fail closed on a foreign protocol")


def test_the_resolution_fails_closed_when_the_amendment_is_stale(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(root, AMENDMENT_RELATIVE, lambda document: document["amends"].__setitem__(
        "manifest_hash", "0" * 64
    ))
    try:
        rules.resolve_effective_v6_execution_protocol(root)
    except rules.V6RuleError as error:
        assert "not bound to the current v6 execution protocol" in str(error)
    else:
        raise AssertionError("the resolution did not fail closed on a stale amendment")


# --------------------------------------------------------------------------
# stage 3: the verifier recomputes the world
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["computed"]["effective_execution_authorization_source"] == AMENDMENT_RELATIVE
    assert report["computed"]["selection_authorization_manifest_hash"] == rules.compute_manifest_hash(
        _load(REPO_ROOT / AUTHORIZATION_RELATIVE), ("manifest_hash",)
    )


def test_the_verifier_no_longer_denies_a_published_selection_authorization() -> None:
    source = (REPO_ROOT / "scripts" / "verify_v6_execution.py").read_text(encoding="utf-8")
    assert "the execution authorization records a published selection authorization" not in source


def test_the_verifier_fails_when_the_effective_block_denies_the_authorization(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(
        root,
        AMENDMENT_RELATIVE,
        lambda document: document["execution_authorization"].__setitem__(
            "selection_authorization_present", False
        ),
    )
    failures = _failures(root)
    assert any("does not record the published v6 selection authorization" in f for f in failures)


def test_the_verifier_fails_when_the_effective_block_names_another_authorization(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(
        root,
        AMENDMENT_RELATIVE,
        lambda document: document["execution_authorization"].__setitem__(
            "selection_authorization_path", "configs/research_v5_selection_authorization_1.json"
        ),
    )
    failures = _failures(root)
    assert any("names another selection authorization" in f for f in failures)


def test_the_verifier_fails_when_the_historical_statement_is_edited(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(
        root,
        PROTOCOL_RELATIVE,
        lambda document: document["execution_authorization"].__setitem__(
            "selection_authorization_present", True
        ),
    )
    _rebind_amendment(root)
    failures = _failures(root)
    assert any("no longer records the historical state of the chain" in f for f in failures)


def test_the_verifier_fails_when_the_selection_authorization_identity_is_stale(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _mutate(
        root,
        AMENDMENT_RELATIVE,
        lambda document: document["execution_authorization"].__setitem__(
            "selection_authorization_manifest_hash", "1" * 64
        ),
    )
    failures = _failures(root)
    assert any("names another manifest hash for the v6 selection authorization" in f for f in failures)


def test_the_verifier_fails_when_the_amendment_is_absent(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / AMENDMENT_RELATIVE).unlink()
    failures = _failures(root)
    assert any("does not exist" in f for f in failures)


# --------------------------------------------------------------------------
# stage 4: the authorization is amendment-aware
# --------------------------------------------------------------------------


def test_the_authorization_states_the_generic_precedence_rule_and_names_no_amendment() -> None:
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    execution = authorization["authorized_run"]["effective_rules"]["execution"]
    assert "newest published v6 execution amendment" in execution["precedence"]
    assert "configs/research_v6_execution.json" in execution["precedence"]
    assert "no v6 execution amendment is named here" in execution["named_amendment_precedence"]
    assert "amendment-first" in execution["consequence_for_the_run"]


def test_the_authorization_still_authorizes_exactly_one_bounded_run() -> None:
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    run = authorization["authorized_run"]
    assert run["authorized"] is True
    assert run["max_runs"] == 1
    not_authorized = authorization["not_authorized"]
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "v1_reauthorization_authorized",
        "source_tree_change_authorized",
        "second_v6_selection_run_authorized",
        "amendment_of_a_frozen_artifact_authorized",
    ):
        assert not_authorized[flag] is False, flag


def test_the_authorization_is_bound_by_the_frozen_execution_protocol() -> None:
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    protocol = _load(REPO_ROOT / PROTOCOL_RELATIVE)
    execution = authorization["authorized_run"]["effective_rules"]["execution"]
    assert execution["path"] == PROTOCOL_RELATIVE
    assert execution["manifest_hash"] == rules.compute_manifest_hash(protocol, ("manifest_hash",))


def test_the_authorization_is_reproduced_byte_for_byte_by_its_producer() -> None:
    document = authorization_producer.build(REPO_ROOT)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    assert rendered == (REPO_ROOT / AUTHORIZATION_RELATIVE).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# stage 5: the chain is consistent after the republication
# --------------------------------------------------------------------------


def test_the_confirmatory_protocol_binds_the_republished_authorization() -> None:
    protocol = _load(REPO_ROOT / CONFIRMATORY_PROTOCOL_RELATIVE)
    authorization_hash = rules.compute_manifest_hash(
        _load(REPO_ROOT / AUTHORIZATION_RELATIVE), ("manifest_hash",)
    )
    assert protocol["related_artifacts"]["v6_selection_authorization_1"]["manifest_hash"] == (
        authorization_hash
    )
    assert protocol["evaluation_scope"]["selection_authorization_manifest_hash"] == (
        authorization_hash
    )
    assert protocol["manifest_hash"] == rules.compute_manifest_hash(protocol, ("manifest_hash",))


def test_the_confirmatory_runbook_binds_the_republished_authorization_and_protocol() -> None:
    runbook = _load(REPO_ROOT / CONFIRMATORY_RUNBOOK_RELATIVE)
    protocol = _load(REPO_ROOT / CONFIRMATORY_PROTOCOL_RELATIVE)
    authorization_hash = rules.compute_manifest_hash(
        _load(REPO_ROOT / AUTHORIZATION_RELATIVE), ("manifest_hash",)
    )
    assert runbook["related_artifacts"]["selection_authorization_1"]["manifest_hash"] == (
        authorization_hash
    )
    assert runbook["related_artifacts"]["confirmatory_protocol"]["manifest_hash"] == (
        rules.compute_manifest_hash(protocol, ("manifest_hash",))
    )
    assert runbook["manifest_hash"] == rules.compute_manifest_hash(runbook, ("manifest_hash",))


# --------------------------------------------------------------------------
# stage 6: no exposure, no run
# --------------------------------------------------------------------------


def test_no_v6_run_artifact_exists() -> None:
    for relative in (
        "research/shards_v6",
        "research/ledger_v6.json",
        "research/results_manifest_v6.json",
        "research/results_v6.jsonl",
        "research_state/checkpoint_v6.json",
    ):
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_holdout_exposure_counter_is_zero() -> None:
    data = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0


def test_the_hashed_source_set_is_untouched() -> None:
    protocol = _load(REPO_ROOT / PROTOCOL_RELATIVE)
    digest = rules.canonical_source_digest(REPO_ROOT)
    assert digest == protocol["code_hash_constraint"]["canonical_hashed_set_digest"]
    assert digest == "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"


# --------------------------------------------------------------------------
# stage 7: fresh-checkout reproducibility
# --------------------------------------------------------------------------


def test_a_clean_mirror_of_the_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    report = verifier.verify(root)
    assert report["ok"], report["failures"]

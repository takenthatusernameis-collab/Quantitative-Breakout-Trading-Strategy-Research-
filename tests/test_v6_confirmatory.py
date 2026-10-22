"""Tests for the v6 confirmatory protocol and the v6 confirmatory runbook.

The v6 chain is the first one that publishes its confirmatory protocol and
runbook **before** the selection run, so the two artifacts fix the procedure
and the scope rule and leave the selected configuration per asset to the
selection phase. The rules these tests pin are therefore:

* the **scope**: the in-scope assets are the validated members of the frozen
  band and the excluded members keep their exclusion reasons; the protocol
  and the runbook do **not** claim a selected configuration or a
  selected-configurations manifest that do not exist yet, and they bind the
  v6 selection authorization that **does** exist by the hash recomputed from
  the artifact's own bytes;
* the **window**: the start, the minimum hours, the earliest end and the
  evaluation gate, which is the later of the four recomputed earlier gates and
  the v6 window's own earliest end;
* the **decision rule**: exactly one criterion, re-derived from the unchanged
  v1 selection rule, with the v1 status vocabulary, which may not be extended;
* the **readiness test**: the selection authorization, the selected-configurations
  manifest and the confirmatory authorization must exist and be hash-bound
  before the first payload read;
* the **code identity**: the canonical tree digest, recomputed;
* the **authorizes-nothing rule**: neither artifact authorizes a candle read,
  an evaluation or a second run, and no v6 confirmatory artifact exists.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v6_confirmatory_protocol.json"
RUNBOOK_PATH = REPO_ROOT / "configs" / "research_v6_confirmatory_runbook_1.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v6_candidate_freeze.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v6.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v6.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SELECTION_AUTHORIZATION_PATH = (
    REPO_ROOT / "configs" / "research_v6_selection_authorization_1.json"
)

PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
RUNBOOK_RELATIVE = "configs/research_v6_confirmatory_runbook_1.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol_verifier = _load_module(
    "verify_v6_confirmatory_protocol", "scripts/verify_v6_confirmatory_protocol.py"
)
protocol_producer = _load_module(
    "build_v6_confirmatory_protocol", "scripts/build_v6_confirmatory_protocol.py"
)
runbook_verifier = _load_module(
    "verify_v6_confirmatory_runbook_1", "scripts/verify_v6_confirmatory_runbook_1.py"
)
runbook_producer = _load_module(
    "build_v6_confirmatory_runbook_1", "scripts/build_v6_confirmatory_runbook_1.py"
)
rules = _load_module("v6_universe_rules", "scripts/v6_universe_rules.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifiers read."""
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
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper(
    root: Path,
    mutate,
    relative: str,
    rehash: bool = True,
) -> Path:
    document = _load(REPO_ROOT / relative)
    mutate(document)
    if rehash:
        excluded = tuple(
            (document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
        )
        document["manifest_hash"] = rules.compute_manifest_hash(document, excluded)
    _replace(root, relative, document)
    return root


def _protocol_failures(root: Path) -> List[str]:
    return protocol_verifier.verify(root)["failures"]


def _runbook_failures(root: Path) -> List[str]:
    return runbook_verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the protocol
# --------------------------------------------------------------------------


def test_the_protocol_verifier_passes_on_the_repository() -> None:
    report = protocol_verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_the_protocol_is_self_hashing_and_reproducible() -> None:
    protocol = _load(PROTOCOL_PATH)
    assert rules.compute_manifest_hash(protocol, ("manifest_hash",)) == protocol["manifest_hash"]
    rebuilt = protocol_producer.build(REPO_ROOT)
    assert rebuilt == protocol
    assert json.dumps(rebuilt, indent=2) + "\n" == PROTOCOL_PATH.read_text(encoding="utf-8")


def test_the_protocol_producer_refuses_to_overwrite(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / PROTOCOL_RELATIVE
    target.unlink()
    assert protocol_producer.main(["--repo-root", str(root)]) == 0
    written = target.read_text(encoding="utf-8")
    assert protocol_producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_protocol_scope_is_the_validated_subset_of_the_frozen_band() -> None:
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_PATH)
    scope = protocol["evaluation_scope"]
    in_scope = [
        entry["binance_pair"]
        for entry in freeze["band"]["members"]
        if entry.get("validated") is True
    ]
    validated = sorted(
        entry["binance_pair"]
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    assert list(scope["in_scope_assets_list"]) == in_scope
    assert sorted(scope["in_scope_assets_list"]) == validated
    assert scope["in_scope_assets"] == 7
    assert scope["frozen_candidate_set_hash"] == freeze["manifest_hash"]
    assert scope["excluded_assets_stay_excluded"] is True
    assert scope["scope_may_not_be_widened_narrowed_or_reranked"] is True


def test_the_protocol_does_not_claim_an_unpublished_selection_result() -> None:
    protocol = _load(PROTOCOL_PATH)
    scope = protocol["evaluation_scope"]
    assert scope["selected_configurations_manifest_hash"] is None
    assert scope["selected_configurations_manifest_status"] == "NOT_YET_PUBLISHED"
    assert "readiness test" in scope["selected_configuration_per_asset"]


def test_the_protocol_binds_the_published_selection_authorization() -> None:
    """The v6 selection authorization exists, so the protocol binds it.

    The identity is the hash recomputed from the artifact's own bytes, so a
    replaced authorization is a different identity and is refused.
    """
    protocol = _load(PROTOCOL_PATH)
    selection_authorization = _load(SELECTION_AUTHORIZATION_PATH)
    live = rules.published_manifest_hash(REPO_ROOT, SELECTION_AUTHORIZATION_RELATIVE)
    assert live == selection_authorization["manifest_hash"]
    assert protocol["evaluation_scope"]["selection_authorization_manifest_hash"] == live
    assert protocol["supersedes"]["selection_authorization_manifest_hash"] == live
    assert protocol["related_artifacts"]["v6_selection_authorization_1"]["manifest_hash"] == live
    assert protocol["evaluation_scope"]["selection_authorization_path"] == (
        SELECTION_AUTHORIZATION_RELATIVE
    )


def test_the_protocol_decision_rule_is_the_unchanged_v1_rule() -> None:
    protocol = _load(PROTOCOL_PATH)
    spec_v1 = _load(SPEC_V1_PATH)
    decision = protocol["decision_rule"]
    min_trades = spec_v1["selection"]["min_trades_total"]
    assert decision["criterion_count"] == 1
    assert decision["exactly_one_criterion"] is True
    assert decision["criteria"] == [
        "net_total_return > 0 at baseline costs (1x) over the confirmatory window",
        "net_total_return > 0 at 2x costs over the confirmatory window",
        f"closed_trades >= {min_trades} over the confirmatory window",
        "the evaluated parameters are byte-identical to the frozen v6 candidate manifest entry",
    ]
    assert decision["status_vocabulary"] == spec_v1["status"]["economic"]
    assert decision["verdicts"]["zero_trade_status"] == "INCONCLUSIVE"
    assert decision["verdicts"]["low_trade_count_status"] == "REJECTED_ON_HOLDOUT"


def test_the_protocol_readiness_test_requires_the_selection_artifacts() -> None:
    protocol = _load(PROTOCOL_PATH)
    checks = protocol["data_path"]["readiness_test"]["checks"]
    for required in protocol_verifier.REQUIRED_READINESS_CHECKS:
        assert required in checks, required
    for required in (
        "the v6 selection authorization exists and is bound to the v6 candidate freeze",
        "the v6 selected-configuration manifest is committed and hash-bound",
        "a confirmatory evaluation authorization exists and is bound to this protocol's "
        "manifest_hash",
    ):
        assert required in checks, required
    assert protocol["data_path"]["readiness_test"]["must_pass_before_any_window_read"] is True


def test_the_protocol_authorizes_nothing() -> None:
    protocol = _load(PROTOCOL_PATH)
    boundary = protocol["authorization_boundary"]
    assert boundary["authorizes_evaluation"] is False
    assert boundary["authorizes_candle_read_before_window_exists"] is False
    assert boundary["authorizes_window_benchmark_retrieval"] is False
    for relative in protocol_verifier.V6_CONFIRMATORY_RUN_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative


# --------------------------------------------------------------------------
# the runbook
# --------------------------------------------------------------------------


def test_the_runbook_verifier_passes_on_the_repository() -> None:
    report = runbook_verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_the_runbook_is_self_hashing_and_reproducible() -> None:
    runbook = _load(RUNBOOK_PATH)
    assert rules.compute_manifest_hash(runbook, ("manifest_hash",)) == runbook["manifest_hash"]
    rebuilt = runbook_producer.build(REPO_ROOT)
    assert rebuilt == runbook
    assert json.dumps(rebuilt, indent=2) + "\n" == RUNBOOK_PATH.read_text(encoding="utf-8")


def test_the_runbook_producer_refuses_to_overwrite(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / RUNBOOK_RELATIVE
    target.unlink()
    assert runbook_producer.main(["--repo-root", str(root)]) == 0
    written = target.read_text(encoding="utf-8")
    assert runbook_producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_runbook_does_not_claim_the_selected_configurations() -> None:
    runbook = _load(RUNBOOK_PATH)
    applies = runbook["applies_to"]
    assert applies["in_scope_configurations"] is None
    assert applies["in_scope_configurations_rule"]
    bindings = runbook["binding_identities"]
    assert bindings["selected_configurations_manifest"]["manifest_hash"] is None
    assert bindings["authorization"]["manifest_hash"] is None


def test_the_runbook_binds_the_published_selection_authorization() -> None:
    """The runbook binds the v6 selection authorization that exists.

    A published authorization is never recorded as unpublished, and the bound
    identity is the hash recomputed from the artifact's own bytes.
    """
    runbook = _load(RUNBOOK_PATH)
    selection_authorization = _load(SELECTION_AUTHORIZATION_PATH)
    live = rules.published_manifest_hash(REPO_ROOT, SELECTION_AUTHORIZATION_RELATIVE)
    assert live == selection_authorization["manifest_hash"]
    binding = runbook["binding_identities"]["selection_authorization_1"]
    assert binding["path"] == SELECTION_AUTHORIZATION_RELATIVE
    assert binding["manifest_hash"] == live
    assert "status" not in binding
    related = runbook["related_artifacts"]["selection_authorization_1"]
    assert related["path"] == SELECTION_AUTHORIZATION_RELATIVE
    assert related["manifest_hash"] == live


def test_the_runbook_write_order_names_eight_v6_paths() -> None:
    runbook = _load(RUNBOOK_PATH)
    write_order = runbook["operator_procedure"]["write_order"]
    assert len(write_order) == 8
    assert [entry["order"] for entry in write_order] == list(range(1, 9))
    for entry in write_order:
        assert "v6" in entry["path"], entry["path"]
        assert entry["path"] not in runbook_verifier.FROZEN_RESULT_PATHS


def test_the_runbook_authorizes_nothing() -> None:
    runbook = _load(RUNBOOK_PATH)
    assert runbook["authorizes_a_candle_read"] is False
    assert runbook["authorizes_an_evaluation"] is False
    assert runbook["authorizes_a_second_run"] is False
    for relative in runbook_verifier.V6_CONFIRMATORY_RUN_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_runbook_anchors_are_the_recomputed_file_digests() -> None:
    runbook = _load(RUNBOOK_PATH)
    anchors = runbook["binding_identities"]["immutable_artifact_anchors"]
    assert anchors
    for label, entries in anchors.items():
        for relative, digest in entries.items():
            assert rules.sha256_file(REPO_ROOT / relative) == digest, relative


# --------------------------------------------------------------------------
# tamper controls
# --------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert _protocol_failures(root) == []
    assert _runbook_failures(root) == []


def test_the_protocol_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["in_scope_assets_list"].append("BTCUSDT")
        document["evaluation_scope"]["in_scope_assets"] = 8

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any("in-scope assets are not the validated members" in failure for failure in failures)


def test_the_protocol_verifier_detects_a_claimed_selection_result(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["selected_configurations_manifest_hash"] = "0" * 64

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any("claims a selected-configurations manifest" in failure for failure in failures)


def test_the_protocol_verifier_detects_a_second_criterion(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["decision_rule"]["criteria"].append("the return beats buy-and-hold")

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any("criteria are not the criteria of the unchanged v1 selection rule" in failure
               for failure in failures)


def test_the_protocol_verifier_detects_a_dropped_readiness_check(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["data_path"]["readiness_test"]["checks"] = [
            "the v6 confirmatory window holds at least 2160 closed hourly candles"
        ]

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any("readiness test does not state" in failure for failure in failures)


def test_the_protocol_verifier_detects_a_self_authorizing_protocol(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["authorization_boundary"]["authorizes_evaluation"] = True

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any("does not record authorizes_evaluation as false" in failure for failure in failures)


def test_the_protocol_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document.update({"manifest_hash": "0" * 64}),
        PROTOCOL_RELATIVE,
        rehash=False,
    )
    assert any("manifest_hash mismatch" in failure for failure in _protocol_failures(root))


def test_the_runbook_verifier_detects_a_claimed_selected_configuration(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["applies_to"]["in_scope_configurations"] = {"FETUSDT": "cfg_0001"}

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("claims the selected configurations" in failure for failure in failures)


def test_the_runbook_verifier_detects_a_ninth_output_path(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["operator_procedure"]["write_order"].append(
            {
                "order": 9,
                "artifact": "extra",
                "path": "research/v6_extra.json",
                "content": "an unauthorized output",
            }
        )

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("output paths, not eight" in failure for failure in failures)


def test_the_runbook_verifier_detects_a_colliding_output_path(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["operator_procedure"]["write_order"][3]["path"] = "research/ledger_v5.json"

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("collides with a frozen path" in failure for failure in failures)


def test_the_runbook_verifier_detects_a_stale_anchor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        anchors = document["binding_identities"]["immutable_artifact_anchors"]
        label = sorted(anchors)[0]
        relative = sorted(anchors[label])[0]
        anchors[label][relative] = "0" * 64

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("has changed since the runbook was written" in failure for failure in failures)


def test_the_runbook_verifier_detects_an_evaluation_gate_that_is_too_early(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["binding_identities"]["bounds"][
            "evaluation_may_not_start_before_utc"
        ] = "2026-10-22T02:00:00Z"

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("effective v6 evaluation start" in failure for failure in failures)


def test_the_runbook_verifier_detects_a_self_authorizing_runbook(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["authorizes_an_evaluation"] = True

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any("does not record authorizes_an_evaluation as false" in failure
               for failure in failures)


def test_the_runbook_verifier_detects_a_v6_confirmatory_run_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "ledger_v6_confirmatory.json").write_text("{}", encoding="utf-8")
    failures = _runbook_failures(root)
    assert any("the v6 confirmatory artifact" in failure for failure in failures)


def test_the_protocol_verifier_detects_an_unbound_selection_authorization(
    tmp_path: Path,
) -> None:
    """A protocol that does not bind the published authorization is refused."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["selection_authorization_manifest_hash"] = None

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any(
        "does not bind the live v6 selection authorization hash" in failure
        for failure in failures
    )


def test_the_protocol_verifier_detects_another_selection_authorization(
    tmp_path: Path,
) -> None:
    """A protocol bound to a substituted authorization is refused."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["selection_authorization_manifest_hash"] = "0" * 64

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any(
        "does not bind the live v6 selection authorization hash" in failure
        for failure in failures
    )


def test_the_protocol_verifier_detects_an_unbound_supersession(tmp_path: Path) -> None:
    """The supersedes block must bind the live authorization as well."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["supersedes"]["selection_authorization_manifest_hash"] = None

    _tamper(root, mutate, PROTOCOL_RELATIVE)
    failures = _protocol_failures(root)
    assert any(
        "supersedes block does not bind the live v6 selection authorization hash" in failure
        for failure in failures
    )


def test_the_protocol_verifier_detects_a_replaced_selection_authorization(
    tmp_path: Path,
) -> None:
    """A replaced authorization changes the identity and is refused.

    The artifact is republished from a tampered body, so its own manifest hash
    recomputes to a different value than the protocol records.
    """
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["authorized_run"]["max_runs"] = 2

    _tamper(root, mutate, SELECTION_AUTHORIZATION_RELATIVE)
    failures = _protocol_failures(root)
    assert any(
        "does not bind the live v6 selection authorization hash" in failure
        for failure in failures
    )


def test_the_runbook_verifier_detects_an_unbound_selection_authorization(
    tmp_path: Path,
) -> None:
    """A runbook that does not bind the published authorization is refused."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["binding_identities"]["selection_authorization_1"]["manifest_hash"] = None

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any(
        "does not bind the live v6 selection authorization hash" in failure
        for failure in failures
    )


def test_the_runbook_verifier_detects_an_unpublished_published_authorization(
    tmp_path: Path,
) -> None:
    """A published authorization may not be recorded as unpublished."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["binding_identities"]["selection_authorization_1"]["status"] = (
            "NOT_YET_PUBLISHED"
        )

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any(
        "records the published selection authorization as unpublished" in failure
        for failure in failures
    )


def test_the_runbook_verifier_detects_another_related_selection_authorization(
    tmp_path: Path,
) -> None:
    """The related-artifacts block must name the live identity too."""
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["related_artifacts"]["selection_authorization_1"]["manifest_hash"] = "0" * 64

    _tamper(root, mutate, RUNBOOK_RELATIVE)
    failures = _runbook_failures(root)
    assert any(
        "names another manifest hash for" in failure for failure in failures
    )

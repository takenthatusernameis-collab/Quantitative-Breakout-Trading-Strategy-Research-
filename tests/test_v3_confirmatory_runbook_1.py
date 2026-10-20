"""Deterministic, offline tests of the preregistered v3 confirmatory runbook.

The runbook is the operator procedure of the single authorized v3 confirmatory
run. The tests check it against the artifacts it is bound to and against the
delivered execution path:

* the **repository itself**, read-only, for the checks that are about the
  delivered tree (the runbook's self-hash, the binding identities, the frozen
  scope, the readiness probe, the benchmark rule, the write order and the
  absence of a confirmatory artifact);
* a **synthetic mirror** in a temporary directory, for the checks that need a
  tampered runbook. The mirror copies the hash-bound artifacts and the two
  source trees byte-identically; the large results manifests are symlinked
  because they are only ever read. No provider request is made, no market data
  is read, and no confirmatory artifact is ever written inside the repository.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

RUNBOOK_RELATIVE = "configs/research_v3_confirmatory_runbook_1.json"
PRODUCER = "scripts/build_v3_confirmatory_runbook_1.py"
VERIFIER = "scripts/verify_v3_confirmatory_runbook_1.py"

CANONICAL_HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
EXECUTION_PATH_DIGEST = (
    "747c2387ff85b73240d89f744a70e69f25c3af2e723a6d6191fda80e80c94aba"
)
RUN_CODE_IDENTITY = (
    "0b1605be59c4d2d4485b8973a950a4e07593d0a56c6e113a21fb4be470f793fe"
)
AUTHORIZATION_HASH = (
    "0383eee19cdc835ab8cba94b479d6b232281e95a62ee9ed4d15febb14e90fb54"
)
PROTOCOL_HASH = "f008876ba5b85f33c8cb9a4c647f6db71ec8bc067d4635e99905ea323d2bf95e"
SELECTED_CONFIGURATIONS_HASH = (
    "3d24a278f13f8c6878905d45be25d0c0cbd84c0c1138d44c0db41b8d56fb5b53"
)
SELECTION_AUTHORIZATION_HASH = (
    "fd91cc4dc907780fc66ffd9c020e53f3c224a5ae8bb688e30cd7bfec04762dcd"
)
DATA_MANIFEST_HASH = (
    "6793d86c37f8fcbe48824ef0d5833d75df7b3d407c8406e37c50dbd9559415df"
)
EFFECTIVE_DATA_MANIFEST_HASH = (
    "88e90960034718e067cebdabce6aef02e1c1942cd0ebfbd7a6934fc2fc5ac321"
)
V3_SPECIFICATION_HASH = "d6a5f8bbbdcf360ff11c75a56e1857114389090e48f12144e35a7075b3189e58"

IN_SCOPE_ASSETS = ("ICPUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT")
IN_SCOPE_CONFIGS = {
    "ICPUSDT": "cfg_0444",
    "PEPEUSDT": "cfg_1804",
    "SHIBUSDT": "cfg_0544",
    "WLDUSDT": "cfg_1380",
}
OUT_OF_SCOPE_ASSETS = ("AAVEUSDT", "QNTUSDT")
BENCHMARK_SYMBOL = "BTCUSDT"

EXPECTED_STEPS = (
    "PREFLIGHT",
    "READINESS_PROBE",
    "SINGLE_RETRIEVAL",
    "DATASET_PERSISTENCE_AND_EXPOSURE",
    "WINDOW_MANIFEST",
    "PRECONDITION_RECHECK",
    "EVALUATION",
    "VERDICT",
    "WRITE_OUTPUT_LAYOUT",
    "ACCEPTANCE",
)
EXPECTED_WRITE_ORDER = (
    "window_manifest",
    "shards_dir",
    "results_stream",
    "ledger",
    "results_manifest",
    "checkpoint",
    "report",
    "report_markdown",
)
EXPECTED_FAILURE_MODES = (
    "ABORT_BEFORE_THE_FIRST_PAYLOAD_READ",
    "ABORT_AFTER_A_PAYLOAD_READ",
    "PROVIDER_OR_RATE_LIMIT_FAILURE",
    "DATASET_HASH_MISMATCH",
    "PAIR_NOT_TRADING_OR_INSUFFICIENT_DATA",
    "WINDOW_BENCHMARK_MISSING_SHORT_OR_MISALIGNED",
    "DEVELOPMENT_BENCHMARK_SUBSTITUTION",
    "ZERO_TRADE_OR_FAILING_ASSET",
    "NO_CONFIGURATION_SURVIVES",
)

#: The artifacts a confirmatory evaluation would create inside the repository.
CONFIRMATORY_ARTIFACTS = (
    "research/v3_confirmatory_window_manifest.json",
    "research/shards_v3_confirmatory",
    "research/ledger_v3_confirmatory.json",
    "research/results_manifest_v3_confirmatory.json",
    "research/results_v3_confirmatory.jsonl",
    "research_state/checkpoint_v3_confirmatory.json",
    "reports/confirmatory_evaluation_v3.json",
    "reports/confirmatory_report_v3.md",
)

#: The artifacts the mirror copies.
MIRROR_FILES = (
    "configs/research_v1.json",
    "configs/research_v3.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_confirmatory_authorization_1.json",
    "configs/research_v3_confirmatory_protocol.json",
    "configs/research_v3_confirmatory_runbook_1.json",
    "configs/research_v3_data_manifest_amendment_1.json",
    "configs/research_v3_selection_authorization_1.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/data_manifest_v3.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/v2_selected_configurations_manifest.json",
    "research/v3_selected_configurations_manifest.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
)

#: The large results manifests are symlinked: the verifier only reads them.
MIRROR_SYMLINKS = (
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
)

MIRROR_TREES = ("src/breakout_research", "src/v3_confirmatory")


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_source_digest(root: Path) -> str:
    """The portable canonical digest of a ``*.py`` tree, under BRAIN-009's rule."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(hashlib.sha256((base / relative).read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def _live_hashed_set_digest() -> str:
    return _canonical_source_digest(REPO_ROOT / "src" / "breakout_research")


def _live_execution_path_digest() -> str:
    return _canonical_source_digest(REPO_ROOT / "src" / "v3_confirmatory")


def _live_run_code_identity() -> str:
    return hashlib.sha256(
        _canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": "src/breakout_research",
                "hashed_set_digest": _live_hashed_set_digest(),
                "execution_path_root": "src/v3_confirmatory",
                "execution_path_digest": _live_execution_path_digest(),
            }
        ).encode("utf-8")
    ).hexdigest()


def _manifest_hash(document: Dict[str, Any]) -> str:
    excluded = tuple(document.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    body = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _reseal(document: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute a document's self-hash after a tamper."""
    document["manifest_hash"] = _manifest_hash(document)
    return document


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _runbook() -> Dict[str, Any]:
    return _load(REPO_ROOT / RUNBOOK_RELATIVE)


def _mirror(root: Path) -> Path:
    """Build a synthetic mirror of the repository's hash-bound artifacts."""
    root.mkdir(parents=True, exist_ok=True)
    for relative in MIRROR_FILES:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in MIRROR_SYMLINKS:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(source, target)
    for tree in MIRROR_TREES:
        target = root / tree
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO_ROOT / tree, target)
    return root


def _write_runbook(root: Path, document: Dict[str, Any]) -> None:
    (root / RUNBOOK_RELATIVE).write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _run_verifier(repo_root: Path) -> Tuple[int, Dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / VERIFIER), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        report = {"stdout": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, report


def _runner_write_order(source: str) -> List[str]:
    """The order in which the delivered runner writes the output layout."""

    def path_key(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left, right = node.left, node.right
            if (
                isinstance(left, ast.Name)
                and left.id == "root"
                and isinstance(right, ast.Subscript)
                and isinstance(right.value, ast.Attribute)
                and right.value.attr == "paths"
                and isinstance(right.slice, ast.Constant)
            ):
                return str(right.slice.value)
        if isinstance(node, ast.Attribute) and node.attr == "window_manifest":
            return "window_manifest"
        if isinstance(node, ast.Name) and node.id == "shard_path":
            return "shards_dir"
        return None

    order: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"_atomic_write_json", "_atomic_write_text"}:
            continue
        if not node.args:
            continue
        key = path_key(node.args[0])
        if key is not None:
            order.append(key)
    return order


# --------------------------------------------------------------------------
# 1. The runbook is self-hashing and reproducible.
# --------------------------------------------------------------------------


def test_the_runbook_is_self_hashing() -> None:
    document = _runbook()
    assert document["manifest_hash"] == _manifest_hash(document)
    assert document["runbook_status"] == "PREREGISTERED_OPERATOR_PROCEDURE_NOT_EXECUTED"
    assert document["artifact"] == "v3_confirmatory_runbook"
    assert document["artifact_version"] == "v3-confirmatory-runbook-1"


def test_the_runbook_is_reproducible_from_its_producer(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reproduced")
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / PRODUCER), "--repo-root", str(root), "--print"],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src")),
    )
    assert completed.returncode == 0, completed.stderr
    produced = json.loads(completed.stdout)
    assert produced == _runbook()


def test_the_producer_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "refused")
    before = (root / RUNBOOK_RELATIVE).read_bytes()
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / PRODUCER), "--repo-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src")),
    )
    assert completed.returncode == 1
    assert "refusing to overwrite" in completed.stderr
    assert (root / RUNBOOK_RELATIVE).read_bytes() == before


# --------------------------------------------------------------------------
# 2. The binding identities are the live ones.
# --------------------------------------------------------------------------


def test_the_binding_identities_are_the_live_ones() -> None:
    document = _runbook()
    identities = document["binding_identities"]
    assert identities["authorization"]["manifest_hash"] == AUTHORIZATION_HASH
    assert identities["confirmatory_protocol"]["manifest_hash"] == PROTOCOL_HASH
    assert (
        identities["selected_configurations_manifest"]["manifest_hash"]
        == SELECTED_CONFIGURATIONS_HASH
    )
    assert (
        identities["selection_authorization_1"]["manifest_hash"]
        == SELECTION_AUTHORIZATION_HASH
    )
    assert identities["v3_data_manifest"]["manifest_hash"] == DATA_MANIFEST_HASH
    assert (
        identities["v3_data_manifest"]["effective_manifest_hash"]
        == EFFECTIVE_DATA_MANIFEST_HASH
    )
    assert identities["v3_specification"]["specification_hash"] == V3_SPECIFICATION_HASH

    code_identity = identities["code_identity"]
    assert code_identity["hashed_set_digest"] == CANONICAL_HASHED_SET_DIGEST
    assert code_identity["execution_path_digest"] == EXECUTION_PATH_DIGEST
    assert code_identity["run_code_identity"] == RUN_CODE_IDENTITY
    assert code_identity["algorithm"] == "canonical_source_digest_v1"
    assert code_identity["portable"] is True


def test_the_runbook_binds_the_authorization_and_not_a_copy_of_it() -> None:
    """The bound identity is recomputed from the file the runbook names."""
    document = _runbook()
    identity = document["binding_identities"]["authorization"]
    referenced = _load(REPO_ROOT / identity["path"])
    assert referenced["manifest_hash"] == identity["manifest_hash"]
    assert identity["manifest_hash"] == _manifest_hash(referenced)


def test_the_runbook_binds_exactly_one_decision_criterion() -> None:
    decision = _runbook()["binding_identities"]["decision_rule"]
    assert decision["criterion_count"] == 1
    assert decision["exactly_one_criterion"] is True
    assert decision["no_competing_criterion"] is True
    assert decision["secondary_source"] is None
    assert decision["secondary_field"] is None
    assert decision["authoritative_source"] == "configs/research_v3.json#holdout.promotion_rule"
    protocol = _load(REPO_ROOT / "configs" / "research_v3_confirmatory_protocol.json")
    assert decision["protocol_manifest_hash"] == protocol["manifest_hash"]
    assert decision["criteria"] == protocol["decision_rule"]["criteria"]


# --------------------------------------------------------------------------
# 3. The scope and the window.
# --------------------------------------------------------------------------


def test_the_scope_is_the_frozen_four_and_two() -> None:
    applies_to = _runbook()["applies_to"]
    assert applies_to["in_scope_assets"] == list(IN_SCOPE_ASSETS)
    assert applies_to["in_scope_count"] == 4
    assert applies_to["in_scope_configurations"] == IN_SCOPE_CONFIGS
    assert applies_to["out_of_scope_assets_without_candidate"] == list(OUT_OF_SCOPE_ASSETS)
    assert applies_to["out_of_scope_count"] == 2
    assert applies_to["single_use_window"] is True
    assert applies_to["benchmark_symbol"] == BENCHMARK_SYMBOL
    assert applies_to["benchmark_is_not_a_candidate"] is True


def test_the_scope_matches_the_selected_configurations_manifest() -> None:
    selected = _load(REPO_ROOT / "research" / "v3_selected_configurations_manifest.json")
    selections = selected["selections"]
    for asset, config_id in IN_SCOPE_CONFIGS.items():
        assert selections[asset]["selected"] is True
        assert selections[asset]["config_id"] == config_id
    for asset in OUT_OF_SCOPE_ASSETS:
        assert selections[asset]["selected"] is not True


def test_the_window_bounds_follow_from_the_frozen_freeze() -> None:
    freeze = _load(REPO_ROOT / "configs" / "research_v3_candidate_freeze.json")
    boundary = freeze["data_boundary"]
    applies_to = _runbook()["applies_to"]
    assert applies_to["window_start_utc"] == boundary["confirmatory_window_start_utc"]
    assert applies_to["window_end_utc"] == boundary[
        "earliest_possible_confirmatory_window_end_utc"
    ]
    assert applies_to["minimum_closed_hourly_candles"] == boundary[
        "min_confirmatory_window_hours"
    ]


# --------------------------------------------------------------------------
# 4. The readiness probe and the benchmark rule are the delivered ones.
# --------------------------------------------------------------------------


def test_the_readiness_probe_is_the_delivered_probe() -> None:
    window_source = (REPO_ROOT / "src" / "v3_confirmatory" / "window.py").read_text(
        encoding="utf-8"
    )
    probe = _runbook()["operator_procedure"]["readiness_probe"]
    assert probe["primary_host"] in window_source
    assert probe["failover_host"] in window_source
    assert probe["endpoint_order"] == [
        "https://api.binance.com/api/v3/time",
        "https://api.binance.com/api/v3/exchangeInfo",
    ]
    assert probe["failover_order"] == [
        "https://data-api.binance.vision/api/v3/time",
        "https://data-api.binance.vision/api/v3/exchangeInfo",
    ]
    assert probe["fetches_no_candle"] is True
    assert probe["increments_holdout_exposed_count"] is False
    assert probe["one_bounded_request_per_endpoint"] is True


def test_the_retry_budget_and_the_rate_limit_are_the_frozen_ones() -> None:
    spec_v3 = _load(REPO_ROOT / "configs" / "research_v3.json")
    probe = _runbook()["operator_procedure"]["readiness_probe"]
    assert probe["max_retries"] == spec_v3["data"]["max_retries"]
    assert probe["backoff_seconds"] == spec_v3["data"]["backoff_seconds"]
    assert probe["rate_limit_per_minute"] == spec_v3["data"]["rate_limit_per_minute"]
    assert probe["failover_policy"] == spec_v3["data"]["failover_policy"]


def test_the_benchmark_rule_is_the_delivered_rule() -> None:
    from v3_confirmatory import benchmark as delivered

    benchmark = _runbook()["operator_procedure"]["benchmark"]
    assert benchmark["symbol"] == delivered.BENCHMARK_SYMBOL == BENCHMARK_SYMBOL
    assert benchmark["alignment_rule"] == delivered.ALIGNMENT_RULE
    assert benchmark["alignment_reference"] == delivered.ALIGNMENT_REFERENCE
    assert benchmark["alignment_reference"] == "docs/research_protocol.md:101"
    assert benchmark["no_forward_fill"] is True
    assert benchmark["development_benchmark_may_be_reused"] is False
    assert benchmark["development_benchmark_content_hash"] == (
        delivered.DEVELOPMENT_BENCHMARK_CONTENT_HASH
    )
    assert benchmark["development_benchmark_path"] == delivered.DEVELOPMENT_BENCHMARK_PATH
    assert benchmark["btc_configurations_dropped"] is False
    assert benchmark["window_benchmark_series_required"] is True
    assert benchmark["window_benchmark_is_hash_verified"] is True
    assert benchmark["fail_closed"] == list(delivered.FAIL_CLOSED_REASONS)


def test_the_window_benchmark_is_retrieved_with_the_window() -> None:
    retrieval = _runbook()["operator_procedure"]["retrieval"]
    assert retrieval["retrieval_happens_once"] is True
    assert sorted(retrieval["retrieved_series"]) == sorted(
        list(IN_SCOPE_ASSETS) + [BENCHMARK_SYMBOL]
    )


# --------------------------------------------------------------------------
# 5. The ordered steps and the write order.
# --------------------------------------------------------------------------


def test_the_ordered_steps_are_the_required_ones() -> None:
    steps = _runbook()["operator_procedure"]["ordered_steps"]
    assert [step["name"] for step in steps] == list(EXPECTED_STEPS)
    for index, step in enumerate(steps):
        assert step["step"] == index + 1
        assert step["action"]
        assert step["may_not"]
        assert step["on_failure"]


def test_the_write_order_is_the_order_the_delivered_runner_writes() -> None:
    source = (REPO_ROOT / "src" / "v3_confirmatory" / "runner.py").read_text(encoding="utf-8")
    assert _runner_write_order(source) == list(EXPECTED_WRITE_ORDER)
    write_order = _runbook()["operator_procedure"]["write_order"]
    assert [entry["artifact"] for entry in write_order] == list(EXPECTED_WRITE_ORDER)
    for index, entry in enumerate(write_order):
        assert entry["order"] == index + 1
        assert entry["path"]
        assert entry["content"]


def test_the_write_order_names_the_authorized_paths() -> None:
    authorization = _load(REPO_ROOT / "configs" / "research_v3_confirmatory_authorization_1.json")
    paths = authorization["authorized_run"]["paths"]
    write_order = _runbook()["operator_procedure"]["write_order"]
    for entry in write_order:
        key = entry["artifact"]
        if key == "shards_dir":
            expected = (
                f"{paths['shards_dir']}/{authorization['authorized_run']['campaign_id']}/"
                "shard_000000.jsonl"
            )
        else:
            expected = paths[key]
        assert entry["path"] == expected


# --------------------------------------------------------------------------
# 6. The failure decision table.
# --------------------------------------------------------------------------


def test_the_failure_decision_table_decides_every_mode() -> None:
    table = _runbook()["failure_decision_table"]
    assert [entry["failure_mode"] for entry in table] == list(EXPECTED_FAILURE_MODES)
    for entry in table:
        for field in (
            "detection",
            "response",
            "exposure_effect",
            "artifact_state",
            "resumable",
            "reported_as",
        ):
            assert entry[field]


def test_the_failure_modes_carry_their_consequences() -> None:
    by_mode = {
        entry["failure_mode"]: entry for entry in _runbook()["failure_decision_table"]
    }
    before = by_mode["ABORT_BEFORE_THE_FIRST_PAYLOAD_READ"]
    assert "release the attempt" in before["response"]
    assert before["exposure_effect"] == "none: the window was never read"

    after = by_mode["ABORT_AFTER_A_PAYLOAD_READ"]
    assert "EXPOSED_ABORTED" in after["artifact_state"]
    assert "spent" in after["exposure_effect"]

    mismatch = by_mode["DATASET_HASH_MISMATCH"]
    assert "refuse" in mismatch["response"].lower()
    assert "repair" in mismatch["response"].lower()

    benchmark = by_mode["WINDOW_BENCHMARK_MISSING_SHORT_OR_MISALIGNED"]
    assert "abort" in benchmark["response"].lower()
    assert "engine" in benchmark["response"].lower()

    substitution = by_mode["DEVELOPMENT_BENCHMARK_SUBSTITUTION"]
    assert "refuse" in substitution["response"].lower()

    zero_trade = by_mode["ZERO_TRADE_OR_FAILING_ASSET"]
    assert "INCONCLUSIVE" in zero_trade["response"]
    assert "REJECTED_ON_HOLDOUT" in zero_trade["response"]

    null_result = by_mode["NO_CONFIGURATION_SURVIVES"]
    assert "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE" in null_result["response"]


# --------------------------------------------------------------------------
# 7. The acceptance checks and the prohibitions.
# --------------------------------------------------------------------------


def test_the_acceptance_checks_name_existing_files() -> None:
    acceptance = _runbook()["acceptance_checks"]
    assert len(acceptance["checks"]) >= 5
    for check in acceptance["checks"]:
        assert check["check"] and check["how"]
    assert acceptance["verification_commands"]
    for command in acceptance["verification_commands"]:
        tokens = str(command).split()
        if len(tokens) > 1 and tokens[1].startswith("scripts/"):
            assert (REPO_ROOT / tokens[1]).exists(), command


def test_the_prohibitions_cover_the_rules_the_run_may_not_break() -> None:
    prohibitions = " | ".join(_runbook()["prohibitions"])
    for fragment in (
        "read the confirmatory window twice",
        "re-rank",
        "extend",
        "v1 path",
        "v2 selection path",
        "v3 selection path",
        "497,664",
        "second confirmatory criterion",
        "v1 holdout",
        "v2 confirmatory window",
        "holdout_exposed_count",
        "development benchmark",
        "btc_ema_168",
        "never re-run",
    ):
        assert fragment.lower() in prohibitions.lower(), fragment


def test_the_deviation_disclosure_is_carried_into_the_report() -> None:
    disclosure = _runbook()["binding_identities"]["deviation_disclosure"]
    assert disclosure["not_repaired"] is True
    assert disclosure["carried_into_the_final_report"] is True
    assert disclosure["evidence_path"] == "research/v3_evidence/v1_v2_btc_alignment_deviation.json"


# --------------------------------------------------------------------------
# 8. The runbook authorizes nothing.
# --------------------------------------------------------------------------


def test_the_runbook_authorizes_nothing() -> None:
    document = _runbook()
    assert document["authorizes_a_candle_read"] is False
    assert document["authorizes_an_evaluation"] is False
    assert document["authorizes_a_second_run"] is False
    assert document["durability"]["runbook_commit_status"] == "PENDING_COMMIT"
    assert document["durability"]["runbook_commit"] is None


def test_no_confirmatory_artifact_exists() -> None:
    for relative in CONFIRMATORY_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative
    data_manifest = _load(REPO_ROOT / "research" / "data_manifest_v3.json")
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0


# --------------------------------------------------------------------------
# 9. The frozen evidence is unchanged.
# --------------------------------------------------------------------------


def test_the_v1_v2_and_v3_frozen_artifacts_are_byte_unchanged() -> None:
    import hashlib as _hashlib

    anchors = {
        "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
        "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
        "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
        "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
        "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
    }
    for relative, digest in anchors.items():
        assert _hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest() == digest
    for relative, digest in (
        ("configs/research_v3_confirmatory_authorization_1.json", AUTHORIZATION_HASH),
        ("configs/research_v3_confirmatory_protocol.json", PROTOCOL_HASH),
    ):
        assert _load(REPO_ROOT / relative)["manifest_hash"] == digest


# --------------------------------------------------------------------------
# 10. The verifier.
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_delivered_tree() -> None:
    status, report = _run_verifier(REPO_ROOT)
    assert status == 0, report
    assert report["failures"] == []
    assert report["in_scope_assets"] == 4
    assert report["out_of_scope_assets"] == list(OUT_OF_SCOPE_ASSETS)
    assert report["write_order"] == list(EXPECTED_WRITE_ORDER)
    assert report["failure_modes"] == list(EXPECTED_FAILURE_MODES)
    assert report["confirmatory_artifacts_present"] == []
    assert report["benchmark_symbol"] == BENCHMARK_SYMBOL
    assert report["run_code_identity"] == _live_run_code_identity()


def test_the_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "tampered_hash")
    document = _load(root / RUNBOOK_RELATIVE)
    document["manifest_hash"] = "0" * 64
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("manifest hash does not recompute" in failure for failure in report["failures"])


def test_the_verifier_detects_a_changed_binding_identity(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "changed_identity")
    document = _load(root / RUNBOOK_RELATIVE)
    document["binding_identities"]["code_identity"]["execution_path_digest"] = "0" * 64
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("execution-path digest" in failure for failure in report["failures"])


def test_the_verifier_detects_a_changed_authorization_binding(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "changed_authorization")
    document = _load(root / RUNBOOK_RELATIVE)
    document["binding_identities"]["authorization"]["manifest_hash"] = "1" * 64
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("authorization hash" in failure for failure in report["failures"])


def test_the_verifier_detects_a_dropped_failure_mode(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "dropped_failure")
    document = _load(root / RUNBOOK_RELATIVE)
    document["failure_decision_table"] = [
        entry
        for entry in document["failure_decision_table"]
        if entry["failure_mode"] != "WINDOW_BENCHMARK_MISSING_SHORT_OR_MISALIGNED"
    ]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any(
        "WINDOW_BENCHMARK_MISSING_SHORT_OR_MISALIGNED" in failure
        for failure in report["failures"]
    )


def test_the_verifier_detects_a_reordered_write_order(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reordered_write_order")
    document = _load(root / RUNBOOK_RELATIVE)
    write_order = document["operator_procedure"]["write_order"]
    write_order[0], write_order[1] = write_order[1], write_order[0]
    for index, entry in enumerate(write_order):
        entry["order"] = index + 1
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("write order" in failure for failure in report["failures"])


def test_the_verifier_detects_a_changed_readiness_endpoint(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "changed_endpoint")
    document = _load(root / RUNBOOK_RELATIVE)
    probe = document["operator_procedure"]["readiness_probe"]
    probe["endpoint_order"] = [
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://api.binance.com/api/v3/time",
    ]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("endpoint order" in failure for failure in report["failures"])


def test_the_verifier_detects_a_changed_retry_budget(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "changed_retry_budget")
    document = _load(root / RUNBOOK_RELATIVE)
    document["operator_procedure"]["readiness_probe"]["max_retries"] = 99
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("retry budget" in failure for failure in report["failures"])


def test_the_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "widened_scope")
    document = _load(root / RUNBOOK_RELATIVE)
    document["applies_to"]["in_scope_assets"] = list(IN_SCOPE_ASSETS) + ["BTCUSDT"]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("in-scope assets" in failure for failure in report["failures"])


def test_the_verifier_detects_a_reranked_configuration(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reranked_config")
    document = _load(root / RUNBOOK_RELATIVE)
    document["applies_to"]["in_scope_configurations"]["ICPUSDT"] = "cfg_0001"
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("ICPUSDT" in failure for failure in report["failures"])


def test_the_verifier_detects_a_second_decision_criterion(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "second_criterion")
    document = _load(root / RUNBOOK_RELATIVE)
    document["binding_identities"]["decision_rule"]["criterion_count"] = 2
    document["binding_identities"]["decision_rule"]["secondary_source"] = (
        "configs/research_v3_confirmatory_protocol.json#reporting_and_falsifiers"
    )
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("criterion" in failure for failure in report["failures"])


def test_the_verifier_detects_a_dropped_benchmark_fail_closed_reason(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "dropped_benchmark_reason")
    document = _load(root / RUNBOOK_RELATIVE)
    document["operator_procedure"]["benchmark"]["fail_closed"] = [
        "the benchmark series is missing"
    ]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("benchmark" in failure for failure in report["failures"])


def test_the_verifier_detects_a_self_authorizing_runbook(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "self_authorizing")
    document = _load(root / RUNBOOK_RELATIVE)
    document["authorizes_a_candle_read"] = True
    document["authorizes_an_evaluation"] = True
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("candle read" in failure for failure in report["failures"])


def test_the_verifier_detects_a_dropped_prohibition(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "dropped_prohibition")
    document = _load(root / RUNBOOK_RELATIVE)
    document["prohibitions"] = [
        item
        for item in document["prohibitions"]
        if "read the confirmatory window twice" not in item
    ]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("does not forbid" in failure for failure in report["failures"])


def test_the_verifier_detects_a_dropped_acceptance_check(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "dropped_check")
    document = _load(root / RUNBOOK_RELATIVE)
    document["acceptance_checks"]["checks"] = []
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("acceptance checks" in failure for failure in report["failures"])


def test_the_verifier_detects_a_runbook_that_claims_to_be_committed(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "claimed_commit")
    document = _load(root / RUNBOOK_RELATIVE)
    document["durability"]["runbook_commit"] = "0" * 40
    document["durability"]["runbook_commit_status"] = "COMMITTED"
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("PENDING_COMMIT" in failure for failure in report["failures"])

"""Deterministic, offline tests of the preregistered v2 confirmatory runbook.

The runbook is the operator procedure of the single authorized confirmatory
run. The tests check it against the artifacts it is bound to and against the
delivered execution path:

* the **repository itself**, read-only, for the checks that are about the
  delivered tree (the runbook's self-hash, the binding identities, the frozen
  scope, the readiness probe, the write order and the absence of a
  confirmatory artifact);
* a **synthetic mirror** in a temporary directory, for the checks that need a
  tampered runbook. The mirror copies the hash-bound artifacts and the two
  source trees byte-identically; the large results manifest is symlinked
  because it is only ever read. No provider request is made, no market data is
  read, and no confirmatory artifact is ever written inside the repository.
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

RUNBOOK_RELATIVE = "configs/research_v2_confirmatory_runbook_1.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_code_hash_amendment_1.json"
PRODUCER = "scripts/build_v2_confirmatory_runbook_1.py"
VERIFIER = "scripts/verify_v2_confirmatory_runbook_1.py"

CANONICAL_HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
EXECUTION_PATH_DIGEST = (
    "fd748860acec6bd5c583bfdc1dc5421409b2e1eecabcc0e00996597d13bfaf10"
)
RUN_CODE_IDENTITY = (
    "fcf8ba956d2def013af3af157c63ec08c95e851e42037a80c3f67d32c2e7f0e8"
)
AUTHORIZATION_HASH = (
    "f411aba94231e36a4dd711376df8a182a979f20d0a248076db0d5eacfaeef943"
)
PROTOCOL_HASH = (
    "bba9539442c92e7e7f51f72ab51e9f9e82bb4c354639be79b7db0baf4b043be3"
)
AMENDMENT_HASH = "2701c63456e080b1a8a0cbcd478d1bf4dc04d35212f4f270ea88d7460f56f377"
SELECTED_CONFIGURATIONS_HASH = (
    "7acc7fe07ba4b151ee232eb70fd0a187966400005054892c184bfdd754d6d862"
)
DATA_MANIFEST_HASH = (
    "9f64d8d140c0ccc2f521296ec86d320e29b665b622034cbee8e8f878a3d6924e"
)
V2_SPECIFICATION_HASH = (
    "49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721"
)

IN_SCOPE_ASSETS = (
    "ADAUSDT",
    "AVAXUSDT",
    "BNBUSDT",
    "DOGEUSDT",
    "ETHUSDT",
    "HBARUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "UNIUSDT",
    "XLMUSDT",
    "XRPUSDT",
    "ZECUSDT",
)
OUT_OF_SCOPE_ASSETS = ("BCHUSDT", "BTCUSDT", "LINKUSDT", "TRXUSDT")

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
    "ZERO_TRADE_OR_FAILING_ASSET",
    "NO_CONFIGURATION_SURVIVES",
)

#: The artifacts a confirmatory evaluation would create inside the repository.
CONFIRMATORY_ARTIFACTS = (
    "research/v2_confirmatory_window_manifest.json",
    "research/shards_v2_confirmatory",
    "research/ledger_v2_confirmatory.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_v2_confirmatory.jsonl",
    "research_state/checkpoint_v2_confirmatory.json",
    "reports/confirmatory_evaluation_v2.json",
    "reports/confirmatory_report_v2.md",
)

#: The artifacts the mirror copies.
MIRROR_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "configs/research_v2_confirmatory_code_hash_amendment_1.json",
    "configs/research_v2_confirmatory_authorization_1.json",
    "configs/research_v2_confirmatory_protocol.json",
    "configs/research_v2_confirmatory_protocol_amendment_1.json",
    "configs/research_v2_confirmatory_runbook_1.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/ledger_v2.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/v2_selected_configurations_manifest.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
)

#: The large results manifest is symlinked: the verifier only reads it.
MIRROR_SYMLINKS = ("research/results_manifest_v2.json",)

MIRROR_TREES = ("src/breakout_research", "src/v2_confirmatory")


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
    return _canonical_source_digest(REPO_ROOT / "src" / "v2_confirmatory")


def _live_run_code_identity() -> str:
    return hashlib.sha256(
        _canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": "src/breakout_research",
                "hashed_set_digest": _live_hashed_set_digest(),
                "execution_path_root": "src/v2_confirmatory",
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
    assert identities["protocol_amendment_1"]["manifest_hash"] == AMENDMENT_HASH
    assert (
        identities["selected_configurations_manifest"]["manifest_hash"]
        == SELECTED_CONFIGURATIONS_HASH
    )
    assert identities["v2_data_manifest"]["manifest_hash"] == DATA_MANIFEST_HASH
    assert identities["v2_specification"]["specification_hash"] == V2_SPECIFICATION_HASH

    code_identity = identities["code_identity"]
    assert code_identity["hashed_set_digest"] == CANONICAL_HASHED_SET_DIGEST
    assert code_identity["execution_path_digest"] == EXECUTION_PATH_DIGEST
    assert code_identity["run_code_identity"] == RUN_CODE_IDENTITY
    assert code_identity["algorithm"] == "canonical_source_digest_v1"
    assert code_identity["portable"] is True


def test_the_code_hash_amendment_rotates_the_runbook_binding() -> None:
    """The runbook binds the frozen identity; the amendment carries the rotation.

    The runbook is immutable and is not edited: a versioned code-hash amendment
    rotates the execution path's digest to the digest of the live tree and
    names the runbook's superseded field.
    """
    document = _runbook()
    code_identity = document["binding_identities"]["code_identity"]
    amendment = _load(REPO_ROOT / CODE_HASH_AMENDMENT_RELATIVE)
    rotation = amendment["code_hash_rotation"]

    assert rotation["previous_execution_path_digest"] == code_identity["execution_path_digest"]
    assert rotation["previous_run_code_identity"] == code_identity["run_code_identity"]
    assert rotation["execution_path_digest"] == _live_execution_path_digest()
    assert rotation["run_code_identity"] == _live_run_code_identity()
    assert rotation["hashed_set_digest"] == _live_hashed_set_digest()

    amended = amendment["amends"]["confirmatory_runbook_1"]
    assert amended["path"] == RUNBOOK_RELATIVE
    assert amended["manifest_hash"] == document["manifest_hash"]
    assert amended["edited"] is False
    assert amended["superseded_code_identity_field"] == "binding_identities.code_identity"


def test_the_runbook_binds_the_authorization_and_not_a_copy_of_it() -> None:
    """The bound identity is recomputed from the file the runbook names."""
    document = _runbook()
    identity = document["binding_identities"]["authorization"]
    referenced = _load(REPO_ROOT / identity["path"])
    assert referenced["manifest_hash"] == identity["manifest_hash"]
    assert identity["manifest_hash"] == _manifest_hash(referenced)


# --------------------------------------------------------------------------
# 3. The scope and the window.
# --------------------------------------------------------------------------


def test_the_scope_is_the_frozen_fourteen_and_four() -> None:
    applies_to = _runbook()["applies_to"]
    assert applies_to["in_scope_assets"] == list(IN_SCOPE_ASSETS)
    assert applies_to["in_scope_count"] == 14
    assert applies_to["out_of_scope_assets_without_candidate"] == list(OUT_OF_SCOPE_ASSETS)
    assert applies_to["out_of_scope_count"] == 4
    assert applies_to["single_use_window"] is True


def test_the_window_bounds_follow_from_the_frozen_freeze() -> None:
    freeze = _load(REPO_ROOT / "configs" / "research_v2_candidate_freeze.json")
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
# 4. The readiness probe is the delivered probe.
# --------------------------------------------------------------------------


def test_the_readiness_probe_is_the_delivered_probe() -> None:
    window_source = (REPO_ROOT / "src" / "v2_confirmatory" / "window.py").read_text(
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
    spec_v2 = _load(REPO_ROOT / "configs" / "research_v2.json")
    probe = _runbook()["operator_procedure"]["readiness_probe"]
    assert probe["max_retries"] == spec_v2["data"]["max_retries"]
    assert probe["backoff_seconds"] == spec_v2["data"]["backoff_seconds"]
    assert probe["rate_limit_per_minute"] == spec_v2["data"]["rate_limit_per_minute"]
    assert probe["failover_policy"] == spec_v2["data"]["failover_policy"]


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
    source = (REPO_ROOT / "src" / "v2_confirmatory" / "runner.py").read_text(encoding="utf-8")
    assert _runner_write_order(source) == list(EXPECTED_WRITE_ORDER)
    write_order = _runbook()["operator_procedure"]["write_order"]
    assert [entry["artifact"] for entry in write_order] == list(EXPECTED_WRITE_ORDER)
    for index, entry in enumerate(write_order):
        assert entry["order"] == index + 1
        assert entry["path"]
        assert entry["content"]


def test_the_write_order_names_the_authorized_paths() -> None:
    authorization = _load(REPO_ROOT / "configs" / "research_v2_confirmatory_authorization_1.json")
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
        "497,664",
        "amendment's precedence",
        "v1 holdout",
        "holdout_exposed_count",
        "never re-run",
    ):
        assert fragment.lower() in prohibitions.lower(), fragment


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
    data_manifest = _load(REPO_ROOT / "research" / "data_manifest_v2.json")
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0


# --------------------------------------------------------------------------
# 9. The frozen evidence is unchanged.
# --------------------------------------------------------------------------


def test_the_v1_and_v2_artifacts_are_byte_unchanged() -> None:
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
        ("configs/research_v2_confirmatory_authorization_1.json", AUTHORIZATION_HASH),
        ("configs/research_v2_confirmatory_protocol.json", PROTOCOL_HASH),
        (
            "configs/research_v2_confirmatory_protocol_amendment_1.json",
            AMENDMENT_HASH,
        ),
    ):
        assert _load(REPO_ROOT / relative)["manifest_hash"] == digest


# --------------------------------------------------------------------------
# 10. The verifier.
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_delivered_tree() -> None:
    status, report = _run_verifier(REPO_ROOT)
    assert status == 0, report
    assert report["failures"] == []
    assert report["in_scope_assets"] == 14
    assert report["out_of_scope_assets"] == list(OUT_OF_SCOPE_ASSETS)
    assert report["write_order"] == list(EXPECTED_WRITE_ORDER)
    assert report["failure_modes"] == list(EXPECTED_FAILURE_MODES)
    assert report["confirmatory_artifacts_present"] == []
    # The verifier reports the *effective* identity of the live tree: the
    # runbook binds the frozen one and the code-hash amendment rotates it.
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
        if entry["failure_mode"] != "DATASET_HASH_MISMATCH"
    ]
    _reseal(document)
    _write_runbook(root, document)
    status, report = _run_verifier(root)
    assert status == 1
    assert any("DATASET_HASH_MISMATCH" in failure for failure in report["failures"])


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

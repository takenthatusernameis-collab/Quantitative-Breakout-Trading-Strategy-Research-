#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 confirmatory runbook.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks the runbook against the artifacts it is bound
to and against the delivered execution path:

* the runbook is self-hashing: its ``manifest_hash`` recomputes over the
  document body with ``manifest_hash`` removed;
* the binding identities are the live ones -- the authorization's, the
  protocol's, the amendment's, the selected-configurations manifest's and the
  v2 data manifest's self-hashes, the hashed set's portable canonical digest,
  the confirmatory execution path's canonical digest and the composite run
  identity that the live tree produces;
* the runbook's scope is the frozen 14 in / 4 out scope;
* the readiness probe the runbook prescribes is the probe the delivered code
  performs: the same two metadata endpoints, the same primary-to-failover
  order, the same retry, backoff and rate-limit values as the frozen v2
  specification's ``data`` block;
* the write order of the eight authorized output paths is the order the
  delivered runner writes them, read from its source with the Python AST;
* the failure decision table covers every failure mode the runbook must
  decide, and every entry answers the same questions;
* the acceptance checks and the verification commands name files that exist;
* the prohibitions cover the rules the run may never break;
* the runbook authorizes nothing: no candle read, no evaluation, no second
  run; the confirmatory window is still ``NOT_STARTED`` with
  ``holdout_exposed_count = 0`` and no confirmatory artifact exists;
* the v1 evidence and the frozen v2 artifacts are byte-identical.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RUNBOOK_RELATIVE = "configs/research_v2_confirmatory_runbook_1.json"
AUTHORIZATION_RELATIVE = "configs/research_v2_confirmatory_authorization_1.json"
PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_protocol_amendment_1.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v2_selected_configurations_manifest.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
RUNNER_RELATIVE = "src/v2_confirmatory/runner.py"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_confirmatory"

#: The v1 artifacts that must stay byte-identical.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The artifacts a confirmatory evaluation would create. None of them may exist.
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

#: The failure modes the runbook must decide.
REQUIRED_FAILURE_MODES = (
    "ABORT_BEFORE_THE_FIRST_PAYLOAD_READ",
    "ABORT_AFTER_A_PAYLOAD_READ",
    "PROVIDER_OR_RATE_LIMIT_FAILURE",
    "DATASET_HASH_MISMATCH",
    "PAIR_NOT_TRADING_OR_INSUFFICIENT_DATA",
    "ZERO_TRADE_OR_FAILING_ASSET",
    "NO_CONFIGURATION_SURVIVES",
)

#: The questions every entry of the failure decision table must answer.
REQUIRED_FAILURE_FIELDS = (
    "detection",
    "response",
    "exposure_effect",
    "artifact_state",
    "resumable",
    "reported_as",
)

#: The rules the run may never break.
REQUIRED_PROHIBITIONS = (
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
)

#: The ordered steps the procedure must contain, in order.
REQUIRED_STEPS = (
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

#: The eight authorized output paths, in the order the runner writes them.
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


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(root: Path) -> str:
    """The portable identity of a ``*.py`` tree, under BRAIN-009's rule."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _path_key(node: ast.AST) -> Optional[str]:
    """The authorization path key a write call targets, read from the source."""
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


def runner_write_order(runner_source: str) -> List[str]:
    """The order in which the runner writes the authorized output paths."""
    tree = ast.parse(runner_source)
    order: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"_atomic_write_json", "_atomic_write_text"}:
            continue
        if not node.args:
            continue
        key = _path_key(node.args[0])
        if key is not None:
            order.append(key)
    return order


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assigned_value(tree: ast.Module, name: str) -> Optional[ast.AST]:
    """The value node of a module-level assignment, annotated or not."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return node.value
    return None


def _module_string_constant(tree: ast.Module, name: str) -> Optional[str]:
    """A module-level string constant, read from the source."""
    value = _assigned_value(tree, name)
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return str(value.value)
    return None


def _metadata_endpoint_paths(tree: ast.Module) -> List[str]:
    """The order in which the readiness probe visits its metadata paths.

    ``METADATA_ENDPOINTS`` is a tuple of ``(primary, failover)`` f-string
    pairs; the order of the two pairs is read from the source.
    """
    value = _assigned_value(tree, "METADATA_ENDPOINTS")
    if not isinstance(value, ast.Tuple):
        return []
    order: List[str] = []
    for element in value.elts:
        if not isinstance(element, ast.Tuple) or not element.elts:
            continue
        names = [
            part.value.id
            for part in ast.walk(element.elts[0])
            if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name)
        ]
        if not names:
            continue
        # The pair is "<host><path>": the path constant is the last one.
        resolved = _module_string_constant(tree, names[-1])
        order.append(resolved if resolved is not None else names[-1])
    return order


def window_probe_constants(repo_root: Path) -> Dict[str, Any]:
    """The readiness probe's constants, read from the delivered source."""
    source = (Path(repo_root) / EXECUTION_PATH_ROOT / "window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    primary = _module_string_constant(tree, "PRIMARY_HOST")
    failover = _module_string_constant(tree, "FAILOVER_HOST")
    paths = _metadata_endpoint_paths(tree)
    return {
        "primary_host": primary,
        "failover_host": failover,
        "endpoint_paths": paths,
        "server_time_path": _module_string_constant(tree, "SERVER_TIME_PATH"),
        "exchange_info_path": _module_string_constant(tree, "EXCHANGE_INFO_PATH"),
    }


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    required = [
        root / RUNBOOK_RELATIVE,
        root / AUTHORIZATION_RELATIVE,
        root / PROTOCOL_RELATIVE,
        root / AMENDMENT_RELATIVE,
        root / SELECTED_CONFIGURATIONS_RELATIVE,
        root / DATA_MANIFEST_RELATIVE,
        root / SPEC_V2_RELATIVE,
        root / SPEC_V1_RELATIVE,
        root / FREEZE_RELATIVE,
        root / RUNNER_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(root)}"],
            }

    runbook = _load(root / RUNBOOK_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    protocol = _load(root / PROTOCOL_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)

    # 1. The runbook is self-hashing.
    excluded = tuple(runbook.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the runbook does not declare its manifest_hash_excluded_keys")
    declared = runbook.get("manifest_hash")
    if declared != compute_manifest_hash(runbook, excluded):
        failures.append("the runbook manifest hash does not recompute")

    # 2. The binding identities are the live ones.
    identities = runbook.get("binding_identities") or {}
    expected_identities = {
        "authorization": (AUTHORIZATION_RELATIVE, authorization.get("manifest_hash")),
        "confirmatory_protocol": (PROTOCOL_RELATIVE, protocol.get("manifest_hash")),
        "protocol_amendment_1": (AMENDMENT_RELATIVE, amendment.get("manifest_hash")),
        "selected_configurations_manifest": (
            SELECTED_CONFIGURATIONS_RELATIVE,
            selected.get("manifest_hash"),
        ),
        "v2_data_manifest": (DATA_MANIFEST_RELATIVE, data_manifest.get("manifest_hash")),
    }
    for name, (path, digest) in expected_identities.items():
        recorded = identities.get(name) or {}
        if recorded.get("manifest_hash") != digest:
            failures.append(f"the runbook does not bind the live {name} hash")
        if recorded.get("path") != path:
            failures.append(f"the runbook binds {name} to the wrong path")
    specification = identities.get("v2_specification") or {}
    if specification.get("specification_hash") != spec_v2.get("specification_hash"):
        failures.append("the runbook does not bind the live v2 specification hash")

    live_hashed_set = canonical_source_digest(root / HASHED_SET_ROOT)
    live_execution_path = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    live_identity = sha256_bytes(
        canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": live_hashed_set,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": live_execution_path,
            }
        ).encode("utf-8")
    )
    code_identity = identities.get("code_identity") or {}
    if code_identity.get("hashed_set_digest") != live_hashed_set:
        failures.append("the runbook does not bind the live hashed-set digest")
    if code_identity.get("execution_path_digest") != live_execution_path:
        failures.append("the runbook does not bind the live execution-path digest")
    if code_identity.get("run_code_identity") != live_identity:
        failures.append("the runbook does not bind the composite run identity of the live tree")
    recorded_authorization_identity = (authorization.get("authorized_run") or {}).get(
        "code_identity"
    ) or {}
    if code_identity.get("run_code_identity") != recorded_authorization_identity.get(
        "run_code_identity"
    ):
        failures.append("the runbook's run identity differs from the authorized one")

    # 3. The scope is the frozen 14 in / 4 out scope.
    selections = selected.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    applies_to = runbook.get("applies_to") or {}
    if sorted(applies_to.get("in_scope_assets") or []) != assets_with_candidate:
        failures.append("the runbook's in-scope assets are not the frozen scope")
    if sorted(applies_to.get("out_of_scope_assets_without_candidate") or []) != (
        assets_without_candidate
    ):
        failures.append("the runbook's out-of-scope assets are not the frozen ones")
    if applies_to.get("in_scope_count") != len(assets_with_candidate):
        failures.append("the runbook's in-scope count is wrong")
    if applies_to.get("single_use_window") is not True:
        failures.append("the runbook does not record the window as single-use")
    window = (authorization.get("authorized_run") or {}).get("window") or {}
    if applies_to.get("window_start_utc") != window.get("window_start_utc"):
        failures.append("the runbook's window start is not the authorized one")
    if applies_to.get("window_end_utc") != window.get("earliest_possible_end_utc"):
        failures.append("the runbook's window end is not the authorized one")
    if applies_to.get("minimum_closed_hourly_candles") != window.get(
        "minimum_closed_hourly_candles"
    ):
        failures.append("the runbook's window length is not the authorized one")
    boundary = freeze.get("data_boundary") or {}
    if applies_to.get("window_start_utc") != boundary.get("confirmatory_window_start_utc"):
        failures.append("the runbook's window start is not the frozen confirmatory-window start")

    # 4. The readiness probe is the probe the delivered code performs.
    constants = window_probe_constants(root)
    probe = (runbook.get("operator_procedure") or {}).get("readiness_probe") or {}
    if probe.get("primary_host") != constants.get("primary_host"):
        failures.append("the runbook's primary host is not the delivered one")
    if probe.get("failover_host") != constants.get("failover_host"):
        failures.append("the runbook's failover host is not the delivered one")
    endpoint_paths = constants.get("endpoint_paths") or []
    if len(endpoint_paths) != 2:
        failures.append("the delivered readiness probe does not visit two metadata endpoints")
    expected_endpoint_order = [
        f"{constants.get('primary_host')}{path}" for path in endpoint_paths
    ]
    if list(probe.get("endpoint_order") or []) != expected_endpoint_order:
        failures.append("the runbook's readiness endpoint order is not the delivered one")
    expected_failover_order = [
        f"{constants.get('failover_host')}{path}" for path in endpoint_paths
    ]
    if list(probe.get("failover_order") or []) != expected_failover_order:
        failures.append("the runbook's readiness failover order is not the delivered one")
    if probe.get("fetches_no_candle") is not True:
        failures.append("the runbook does not forbid a candle read in the readiness probe")
    if probe.get("increments_holdout_exposed_count") is not False:
        failures.append("the runbook lets the readiness probe count as an exposure")
    if probe.get("one_bounded_request_per_endpoint") is not True:
        failures.append("the runbook does not bound the readiness probe to one request per endpoint")
    data_policy = spec_v2.get("data") or {}
    if probe.get("max_retries") != data_policy.get("max_retries"):
        failures.append("the runbook's retry budget is not the frozen one")
    if probe.get("backoff_seconds") != data_policy.get("backoff_seconds"):
        failures.append("the runbook's backoff is not the frozen one")
    if probe.get("rate_limit_per_minute") != data_policy.get("rate_limit_per_minute"):
        failures.append("the runbook's rate limit is not the frozen one")
    if probe.get("failover_policy") != data_policy.get("failover_policy"):
        failures.append("the runbook's failover policy is not the frozen one")

    # 5. The retrieval is bounded and single.
    retrieval = (runbook.get("operator_procedure") or {}).get("retrieval") or {}
    if retrieval.get("retrieval_happens_once") is not True:
        failures.append("the runbook does not record the retrieval as happening once")
    if retrieval.get("endpoint") != data_policy.get("endpoint"):
        failures.append("the runbook's klines endpoint is not the frozen one")
    if list(retrieval.get("failover_endpoints") or []) != list(
        data_policy.get("failover_endpoints") or []
    ):
        failures.append("the runbook's failover endpoints are not the frozen ones")
    if retrieval.get("dataset_hash_algorithm") != "sha256-canonical-hourly-csv-v1":
        failures.append("the runbook does not use the frozen dataset hash scheme")
    if retrieval.get("gaps_are_recorded") is not True:
        failures.append("the runbook does not record the coverage gaps")
    if retrieval.get("interpolation_is_forbidden") is not True:
        failures.append("the runbook does not forbid interpolation")
    window_bounds = retrieval.get("window_bounds") or {}
    if window_bounds.get("window_start_utc") != applies_to.get("window_start_utc"):
        failures.append("the runbook's retrieval bounds differ from the window it applies to")
    if window_bounds.get("window_end_utc") != applies_to.get("window_end_utc"):
        failures.append("the runbook's retrieval bounds differ from the window it applies to")

    # 6. The evaluation uses the unchanged v1 rule.
    evaluation = (runbook.get("operator_procedure") or {}).get("evaluation") or {}
    if evaluation.get("unchanged_v1_evaluation_metric") is not True:
        failures.append("the runbook does not record the unchanged v1 evaluation metric")
    if evaluation.get("unchanged_cost_scenarios") is not True:
        failures.append("the runbook does not record the unchanged cost scenarios")
    if [float(value) for value in evaluation.get("cost_scenarios") or []] != [
        float(value) for value in spec_v1["costs"]["scenarios"]
    ]:
        failures.append("the runbook's cost scenarios differ from the unchanged v1 ones")
    if evaluation.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        failures.append("the runbook does not prohibit re-tuning on the window")
    if evaluation.get("evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry") is not True:
        failures.append("the runbook does not require byte-identical evaluated parameters")
    precedence = identities.get("criterion_precedence") or {}
    if precedence.get("authoritative_source") != "configs/research_v2.json#holdout.promotion_rule":
        failures.append("the runbook does not bind the authoritative criterion")
    if precedence.get("amendment_manifest_hash") != amendment.get("manifest_hash"):
        failures.append("the runbook's criterion precedence is not bound to the amendment")
    status_vocabulary = set(evaluation.get("status_vocabulary") or [])
    if status_vocabulary != {
        "PROVISIONAL_HISTORICAL_SURVIVAL",
        "REJECTED_ON_HOLDOUT",
        "INCONCLUSIVE",
        "CANDIDATE_PENDING_HOLDOUT",
    }:
        failures.append("the runbook extends or narrows the frozen status vocabulary")
    outcomes = set(evaluation.get("outcomes") or [])
    if "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE" not in outcomes:
        failures.append("the runbook does not name the null result as an outcome")
    if evaluation.get("assets_without_candidate_status") != "NO_CANDIDATE_NOT_EVALUATED":
        failures.append("the runbook does not record the status of the assets without a candidate")

    # 7. The ordered steps and the write order.
    procedure = runbook.get("operator_procedure") or {}
    steps = procedure.get("ordered_steps") or []
    step_names = [str(step.get("name")) for step in steps]
    if step_names != list(REQUIRED_STEPS):
        failures.append(f"the runbook's ordered steps are not the required ones: {step_names}")
    for step in steps:
        for key in ("step", "name", "action", "may_not", "on_failure"):
            if key not in step:
                failures.append(f"the runbook step {step.get('name')} lacks the field {key}")
    write_order = procedure.get("write_order") or []
    if [str(entry.get("artifact")) for entry in write_order] != list(EXPECTED_WRITE_ORDER):
        failures.append("the runbook's write order is not the authorized one")
    for index, entry in enumerate(write_order):
        if entry.get("order") != index + 1:
            failures.append("the runbook's write order is not consecutively numbered")
    live_write_order = runner_write_order((root / RUNNER_RELATIVE).read_text(encoding="utf-8"))
    if live_write_order != [str(entry.get("artifact")) for entry in write_order]:
        failures.append(
            "the runbook's write order differs from the order the delivered runner writes: "
            f"{live_write_order}"
        )
    authorized_paths = (authorization.get("authorized_run") or {}).get("paths") or {}
    for entry in write_order:
        key = str(entry.get("artifact"))
        expected_path = authorized_paths.get(key)
        if key == "shards_dir":
            expected_path = (
                f"{authorized_paths.get('shards_dir')}/"
                f"{(authorization.get('authorized_run') or {}).get('campaign_id')}/"
                "shard_000000.jsonl"
            )
        if expected_path is not None and entry.get("path") != expected_path:
            failures.append(f"the runbook writes {key} to a path the authorization does not name")
        if not entry.get("content"):
            failures.append(f"the runbook does not describe the content of {key}")

    # 8. The failure decision table.
    table = runbook.get("failure_decision_table") or []
    recorded_modes = [str(entry.get("failure_mode")) for entry in table]
    for mode in REQUIRED_FAILURE_MODES:
        if mode not in recorded_modes:
            failures.append(f"the failure decision table does not decide {mode}")
    for entry in table:
        for field in REQUIRED_FAILURE_FIELDS:
            if not entry.get(field):
                failures.append(
                    f"the failure mode {entry.get('failure_mode')} does not answer {field}"
                )
    by_mode = {str(entry.get("failure_mode")): entry for entry in table}
    if by_mode.get("ABORT_BEFORE_THE_FIRST_PAYLOAD_READ", {}).get("exposure_effect", "") != (
        "none: the window was never read"
    ):
        failures.append("the abort before the first payload read does not release the window")
    if "EXPOSED_ABORTED" not in str(
        by_mode.get("ABORT_AFTER_A_PAYLOAD_READ", {}).get("artifact_state", "")
    ):
        failures.append("the abort after a payload read is not recorded as EXPOSED_ABORTED")
    mismatch_response = str(by_mode.get("DATASET_HASH_MISMATCH", {}).get("response", "")).lower()
    if "refuse" not in mismatch_response or "repair" not in mismatch_response:
        failures.append("the hash-mismatch mode does not refuse to repair the dataset")
    if "INCONCLUSIVE" not in str(
        by_mode.get("ZERO_TRADE_OR_FAILING_ASSET", {}).get("response", "")
    ):
        failures.append("the zero-trade mode does not use the frozen INCONCLUSIVE status")
    if "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE" not in str(
        by_mode.get("NO_CONFIGURATION_SURVIVES", {}).get("response", "")
    ):
        failures.append("the null-result mode does not report the frozen null outcome")

    # 9. The acceptance checks and the verification commands.
    acceptance = runbook.get("acceptance_checks") or {}
    checks = acceptance.get("checks") or []
    if len(checks) < 5:
        failures.append("the runbook records fewer than five acceptance checks")
    for check in checks:
        for key in ("check", "how"):
            if not check.get(key):
                failures.append("an acceptance check does not state what it checks or how")
    commands = acceptance.get("verification_commands") or []
    if not commands:
        failures.append("the runbook records no verification command")
    for command in commands:
        token = str(command).split()[1] if len(str(command).split()) > 1 else ""
        if token.startswith("scripts/") and not (root / token).exists():
            failures.append(f"the runbook names a verification command that does not exist: {token}")

    # 10. The prohibitions.
    prohibitions = " | ".join(str(item) for item in runbook.get("prohibitions") or [])
    for required_prohibition in REQUIRED_PROHIBITIONS:
        if required_prohibition.lower() not in prohibitions.lower():
            failures.append(f"the runbook does not forbid: {required_prohibition}")

    # 11. The runbook authorizes nothing.
    if runbook.get("authorizes_a_candle_read") is not False:
        failures.append("the runbook does not forbid a candle read")
    if runbook.get("authorizes_an_evaluation") is not False:
        failures.append("the runbook does not forbid an evaluation")
    if runbook.get("authorizes_a_second_run") is not False:
        failures.append("the runbook does not forbid a second run")
    durability = runbook.get("durability") or {}
    if durability.get("runbook_commit_status") != "PENDING_COMMIT":
        failures.append("the runbook's durability block is not PENDING_COMMIT")
    if durability.get("runbook_commit") is not None:
        failures.append("the runbook already records a commit hash; it is preregistered, not committed")
    for relative in CONFIRMATORY_ARTIFACTS:
        if (root / relative).exists():
            failures.append(f"a confirmatory artifact exists: {relative}")
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is not marked NOT_STARTED")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")

    # 12. The v1 evidence and the frozen v2 artifacts are byte-identical.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    anchors = identities.get("immutable_artifact_anchors") or {}
    for group in ("v1_evidence", "v2_selection_outputs"):
        entries = anchors.get(group) or {}
        if not entries:
            failures.append(f"the runbook records no immutable {group} anchors")
            continue
        for relative, expected in sorted(entries.items()):
            target = root / relative
            if not target.exists():
                failures.append(f"the frozen {group} artifact {relative} is missing")
                continue
            if sha256_file(target) != expected:
                failures.append(
                    f"the frozen {group} artifact {relative} does not match its recorded sha256"
                )

    return {
        "ok": not failures,
        "runbook_manifest_hash": declared,
        "authorization_manifest_hash": authorization.get("manifest_hash"),
        "protocol_manifest_hash": protocol.get("manifest_hash"),
        "amendment_manifest_hash": amendment.get("manifest_hash"),
        "canonical_source_digest": live_hashed_set,
        "execution_path_digest": live_execution_path,
        "run_code_identity": live_identity,
        "in_scope_assets": len(assets_with_candidate),
        "out_of_scope_assets": assets_without_candidate,
        "ordered_steps": step_names,
        "write_order": [str(entry.get("artifact")) for entry in write_order],
        "failure_modes": recorded_modes,
        "confirmatory_artifacts_present": [
            relative for relative in CONFIRMATORY_ARTIFACTS if (root / relative).exists()
        ],
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

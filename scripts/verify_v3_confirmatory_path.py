#!/usr/bin/env python3
"""Read-only, offline verification of the v3 confirmatory evaluation path.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks the delivered confirmatory path against the
artifacts it is bound to:

* the execution path is a real package outside the hashed set, its module set
  is the one the v3 confirmatory protocol names, and the hashed set's portable
  canonical digest is unchanged and order-independent (BRAIN-009's rule);
* the evaluation scope is exactly the 4 published candidates of
  ``research/v3_selected_configurations_manifest.json``, and the 2 assets
  without a candidate stay out of scope and are reported, never dropped;
* the protocol is self-hashing, states **exactly one** confirmatory decision
  criterion, fixes the window, requires the window benchmark series with its
  fail-closed rules, carries the v1/v2 deviation disclosure and authorizes
  nothing;
* the authorization is self-hashing, names the scope, the window, the data
  boundary, the window-benchmark rule, the output layout, the code identity,
  the single decision criterion, the attempt budget, the preconditions, the
  stopping conditions, the falsifiers and the rollback, and it authorizes no
  evaluation and no candle read before the window exists;
* the path itself applies no second criterion: the delivered source carries
  no competing criterion surface;
* the window definition follows from the frozen v3 candidate freeze;
* the output layout touches no v1 path, no v2 *selection* path, no v2
  *confirmatory* path and no v3 *selection* path;
* nothing has been executed: no confirmatory window manifest, shard, ledger,
  results manifest, result row, checkpoint or report exists, the v3
  confirmatory window is still ``NOT_STARTED`` and ``holdout_exposed_count`` is
  still 0;
* the v1 evidence is byte-identical and the frozen v2 and v3 artifacts are
  unchanged.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v3_confirmatory"

PROTOCOL_RELATIVE = "configs/research_v3_confirmatory_protocol.json"
AUTHORIZATION_RELATIVE = "configs/research_v3_confirmatory_authorization_1.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v3_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
DATA_MANIFEST_AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"
CODE_HASH_AMENDMENT_1_RELATIVE = "configs/research_v3_confirmatory_code_hash_amendment_1.json"

#: The modules the confirmatory execution path must carry.
EXPECTED_EXECUTION_MODULES = (
    "__init__.py",
    "artifacts.py",
    "benchmark.py",
    "data.py",
    "errors.py",
    "exposure.py",
    "identity.py",
    "report.py",
    "runner.py",
    "scope.py",
    "window.py",
)

#: The v1 campaign authorization's frozen values.
AUTHORIZED_ORDERED_CODE_HASH = "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
V1_SPECIFICATION_HASH = "2d22e70246cf023218ef6dd0cb655897836b310e1a6e6969d934f52d06e79085"

#: The v1 artifacts that must stay byte-identical.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The frozen v2 and v3 artifacts that must stay unchanged.
FROZEN_ARTIFACTS = {
    "research/universe_manifest_v2.json": "4e927e522eb18434459547602cc96201fa6e7c15b02010f9e7366270e5ad3f88",
    "research/data_manifest_v2.json": "9f64d8d140c0ccc2f521296ec86d320e29b665b622034cbee8e8f878a3d6924e",
    "configs/research_v2.json": "49fb08142f482e8c098ce096b876e3e12bd1644aa31b8ee6849d283ac1380721",
    "configs/research_v2_candidate_freeze.json": "5a56b3d801519bbda0ed534cd031d0cb4204c1c015e5accb6fbc4e9bd0ec123f",
    "research/v2_selected_configurations_manifest.json": "7acc7fe07ba4b151ee232eb70fd0a187966400005054892c184bfdd754d6d862",
    "research/universe_manifest_v3.json": "e53db5ed75ad448e52f02438c491ad76f4da75503472c0945b9adf9283e30cdf",
    "research/data_manifest_v3.json": "6793d86c37f8fcbe48824ef0d5833d75df7b3d407c8406e37c50dbd9559415df",
    "configs/research_v3.json": "d6a5f8bbbdcf360ff11c75a56e1857114389090e48f12144e35a7075b3189e58",
    "configs/research_v3_candidate_freeze.json": "12a981b13c657b51bf2023fbfdb22f531d16c656af5eef0d8242f8c202c154e4",
    "configs/research_v3_confirmatory_protocol.json": "f008876ba5b85f33c8cb9a4c647f6db71ec8bc067d4635e99905ea323d2bf95e",
    "configs/research_v3_selection_authorization_1.json": "fd91cc4dc907780fc66ffd9c020e53f3c224a5ae8bb688e30cd7bfec04762dcd",
    "research/v3_selected_configurations_manifest.json": "3d24a278f13f8c6878905d45be25d0c0cbd84c0c1138d44c0db41b8d56fb5b53",
}

#: The artifacts a confirmatory evaluation would create. None of them may exist.
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

#: The v1 paths a confirmatory evaluation may never write.
V1_PATHS_FORBIDDEN = (
    "research/results_shards/",
    "research/results_manifest.json",
    "research/results.jsonl",
    "research_state/checkpoint.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "configs/research_v1.json",
)

#: The v2 *selection* paths a confirmatory evaluation may never write.
V2_SELECTION_PATHS_FORBIDDEN = (
    "research/shards_v2/",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)

#: The v2 *confirmatory* paths a v3 confirmatory evaluation may never write.
V2_CONFIRMATORY_PATHS_FORBIDDEN = (
    "research/shards_v2_confirmatory/",
    "research/ledger_v2_confirmatory.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_v2_confirmatory.jsonl",
    "research_state/checkpoint_v2_confirmatory.json",
    "research/v2_confirmatory_window_manifest.json",
)

#: The v3 *selection* paths a confirmatory evaluation may never write.
V3_SELECTION_PATHS_FORBIDDEN = (
    "research/shards_v3/",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
)

#: Every path the v3 confirmatory evaluation may not write.
FORBIDDEN_PATHS = (
    V1_PATHS_FORBIDDEN
    + V2_SELECTION_PATHS_FORBIDDEN
    + V2_CONFIRMATORY_PATHS_FORBIDDEN
    + V3_SELECTION_PATHS_FORBIDDEN
)

#: The single confirmatory decision criterion of the v3 line.
AUTHORITATIVE_CRITERION_SOURCE = "configs/research_v3.json#holdout.promotion_rule"

#: The fail-closed benchmark conditions of the preregistered protocol.
FAIL_CLOSED_REASONS = (
    "the benchmark series is missing",
    "the benchmark series is shorter than the evaluated window",
    "the benchmark series is not index-aligned with the asset series",
)

#: Identifiers that would introduce a second confirmatory criterion. The v2
#: line had to amend two frozen artifacts that disagreed about the criterion;
#: the v3 line states one, and the delivered path must not reintroduce a
#: competing criterion surface.
SECOND_CRITERION_IDENTIFIERS = (
    "criteria_agreement",
    "baseline_comparison",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _code_hash_amendment(root: Path, failures: List[str]) -> Optional[Dict[str, Any]]:
    """The versioned code-hash amendment, if it exists and verifies.

    The amendment is the only artifact that may rotate the execution path's
    digest after the authorization was frozen.
    """
    path = root / CODE_HASH_AMENDMENT_1_RELATIVE
    if not path.exists():
        return None
    document = _load(path)
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the code-hash amendment does not declare its manifest_hash_excluded_keys")
        return None
    if document.get("manifest_hash") != compute_manifest_hash(document, excluded):
        failures.append("the code-hash amendment manifest hash does not recompute")
        return None
    return document


def _effective_execution_path_digest(
    root: Path, recorded_digest: Optional[str], amendment: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """The digest the run is bound to, and the amendment that authorises it.

    The recorded digest is the identity of the execution path as it was frozen.
    When the path was corrected afterwards, only a versioned code-hash
    amendment may rotate the binding, and only when it rotates exactly that
    digest to the digest of the live tree.
    """
    live = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    if recorded_digest == live:
        return live, None
    rotation = (amendment or {}).get("code_hash_rotation") or {}
    if (
        rotation.get("previous_execution_path_digest") == recorded_digest
        and rotation.get("execution_path_digest") == live
    ):
        return live, amendment
    return None, None


def _second_criterion_usages(path: Path, identifier: str) -> List[str]:
    """The code (not the prose) of one module that mentions a second criterion.

    The check parses the module, so a docstring that *explains* why the v2
    helpers are absent does not count as a second criterion, while a
    definition, a name, an attribute or a document key does.
    """
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return [f"{path.name} does not parse"]

    found: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == identifier:
                found.append(f"definition {node.name}")
        elif isinstance(node, ast.Name):
            if node.id == identifier:
                found.append(f"name {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr == identifier:
                found.append(f"attribute {node.attr}")
        elif isinstance(node, ast.keyword):
            if node.arg == identifier:
                found.append(f"keyword {node.arg}")
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == identifier:
                    found.append(f"document key {identifier}")
    return sorted(set(found))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    required = [
        root / PROTOCOL_RELATIVE,
        root / AUTHORIZATION_RELATIVE,
        root / SPEC_V3_RELATIVE,
        root / SPEC_V1_RELATIVE,
        root / FREEZE_RELATIVE,
        root / SELECTED_CONFIGURATIONS_RELATIVE,
        root / SELECTION_AUTHORIZATION_RELATIVE,
        root / DATA_MANIFEST_RELATIVE,
        root / DATA_MANIFEST_AMENDMENT_RELATIVE,
        root / CODE_HASH_AMENDMENT_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(root)}"],
            }

    protocol = _load(root / PROTOCOL_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)
    selection_authorization = _load(root / SELECTION_AUTHORIZATION_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    data_manifest_amendment = _load(root / DATA_MANIFEST_AMENDMENT_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)

    # 1. The execution path is a real package outside the hashed set.
    package = root / EXECUTION_PATH_ROOT
    if not package.is_dir():
        failures.append(f"the confirmatory execution path {EXECUTION_PATH_ROOT} does not exist")
    else:
        if not (package / "__init__.py").exists():
            failures.append(
                f"{EXECUTION_PATH_ROOT} has no __init__.py and is not a regular package"
            )
        modules = sorted(
            path.relative_to(package).as_posix() for path in package.rglob("*.py")
        )
        missing = [name for name in EXPECTED_EXECUTION_MODULES if name not in modules]
        if missing:
            failures.append(f"the confirmatory execution path is missing the modules {missing}")
    if (root / HASHED_SET_ROOT).is_relative_to(EXECUTION_PATH_ROOT):
        failures.append("the confirmatory execution path lies inside the hashed set")

    # 2. The tree identity: the portable canonical digest, and the recorded value.
    live_hashed_set = canonical_source_digest(root / HASHED_SET_ROOT)
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    if recorded_canonical != live_hashed_set:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_hashed_set}"
        )
    live_execution_path = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    code_identity = (authorization.get("authorized_run") or {}).get("code_identity") or {}
    if code_identity.get("hashed_set_digest") != live_hashed_set:
        failures.append("the authorization does not record the live hashed-set digest")
    rotation_amendment = _code_hash_amendment(root, failures)
    effective_digest, rotation = _effective_execution_path_digest(
        root, code_identity.get("execution_path_digest"), rotation_amendment
    )
    if effective_digest is None:
        failures.append(
            "the authorization does not record the live execution-path digest and no "
            "versioned code-hash amendment authorises the rotation"
        )
    expected_identity = sha256_bytes(
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
    recorded_identity = code_identity.get("run_code_identity")
    if recorded_identity != expected_identity:
        if not (
            rotation
            and (rotation.get("code_hash_rotation") or {}).get("previous_run_code_identity")
            == recorded_identity
            and (rotation.get("code_hash_rotation") or {}).get("run_code_identity")
            == expected_identity
        ):
            failures.append("the recorded run code identity is not the composite of the two digests")
    if code_identity.get("authorized_ordered_code_hash") != AUTHORIZED_ORDERED_CODE_HASH:
        failures.append("the authorization does not record the authorized ordered code hash")

    # 3. The evaluation scope.
    selections = selected.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    run = authorization.get("authorized_run") or {}
    scope = run.get("scope") or {}
    if sorted(scope.get("assets") or []) != assets_with_candidate:
        failures.append("the authorized scope is not the frozen evaluation scope")
    if sorted(scope.get("out_of_scope_assets_without_candidate") or []) != assets_without_candidate:
        failures.append("the authorized out-of-scope assets differ from the frozen ones")
    expected_config_ids = {
        asset: str((selections.get(asset) or {}).get("config_id"))
        for asset in assets_with_candidate
    }
    if (scope.get("config_ids") or {}) != expected_config_ids:
        failures.append("the authorized configuration ids are not the frozen ones")
    if scope.get("bound_to_selected_configurations_hash") != selected.get("manifest_hash"):
        failures.append("the authorization is not bound to the selected-configurations manifest")
    if scope.get("bound_to_selection_authorization_hash") != selection_authorization.get(
        "manifest_hash"
    ):
        failures.append("the authorization is not bound to the selection authorization")
    effective_data_manifest_hash = (
        (data_manifest_amendment.get("effective_data_manifest") or {}).get(
            "effective_data_manifest_hash"
        )
    )
    if scope.get("bound_to_data_manifest_hash") != effective_data_manifest_hash:
        failures.append("the authorization is not bound to the effective v3 data manifest")
    if scope.get("scope_may_not_be_widened_narrowed_or_reranked") is not True:
        failures.append("the authorization does not forbid widening, narrowing or re-ranking")
    if scope.get("out_of_scope_assets_are_reported_not_dropped") is not True:
        failures.append("the authorization does not require the assets without a candidate to be reported")

    # 4. The protocol: self-hash, one criterion, window, benchmark, no authorization.
    protocol_excluded = tuple(
        protocol.get("hashing", {}).get("manifest_hash_excluded_keys") or ()
    )
    if not protocol_excluded:
        failures.append("the protocol does not declare its manifest_hash_excluded_keys")
    declared_protocol = protocol.get("manifest_hash")
    if declared_protocol != compute_manifest_hash(protocol, protocol_excluded):
        failures.append("the confirmatory protocol manifest hash does not recompute")
    decision = protocol.get("decision_rule") or {}
    if decision.get("criterion_count") != 1:
        failures.append("the protocol does not state exactly one confirmatory decision criterion")
    if decision.get("authoritative_source") != AUTHORITATIVE_CRITERION_SOURCE:
        failures.append("the protocol does not name the v3 promotion rule as authoritative")
    if decision.get("exactly_one_criterion") is not True or decision.get(
        "no_competing_criterion"
    ) is not True:
        failures.append("the protocol does not forbid a competing criterion")
    protocol_window = protocol.get("window_definition") or {}
    if protocol_window.get("single_use") is not True:
        failures.append("the protocol does not make the confirmatory window single-use")
    if protocol_window.get("must_not_overlap_v1_holdout") is not True:
        failures.append("the protocol does not forbid an overlap with the v1 holdout")
    if protocol_window.get("must_not_overlap_v2_confirmatory_window") is not True:
        failures.append("the protocol does not forbid an overlap with the v2 confirmatory window")
    if protocol_window.get("never_used_for_candidate_selection") is not True:
        failures.append("the protocol does not forbid the use of the window for selection")
    if protocol_window.get("no_ranking_or_retuning_on_window") is not True:
        failures.append("the protocol does not forbid ranking or re-tuning on the window")
    protocol_benchmark = (protocol.get("data_path") or {}).get("benchmark") or {}
    if protocol_benchmark.get("window_benchmark_series_required") is not True:
        failures.append("the protocol does not require the window benchmark series")
    if protocol_benchmark.get("development_benchmark_may_be_reused_as_the_window_benchmark") is not False:
        failures.append("the protocol allows the development benchmark as the window benchmark")
    if protocol_benchmark.get("no_forward_fill") is not True:
        failures.append("the protocol does not forbid forward-filling a missing benchmark")
    if protocol_benchmark.get("btc_configurations_dropped") is not False:
        failures.append("the protocol allows the BTC configurations to be dropped")
    if sorted(protocol_benchmark.get("fail_closed") or []) != sorted(FAIL_CLOSED_REASONS):
        failures.append("the protocol's fail-closed benchmark rules differ from the preregistered ones")
    boundary = protocol.get("authorization_boundary") or {}
    if boundary.get("authorizes_evaluation") is not False:
        failures.append("the protocol authorizes an evaluation")
    if boundary.get("authorizes_candle_read_before_window_exists") is not False:
        failures.append("the protocol authorizes a candle read before the window exists")
    if boundary.get("authorizes_window_benchmark_retrieval") is not False:
        failures.append("the protocol authorizes a benchmark retrieval")
    if boundary.get("confirmatory_execution_code_must_live_outside_the_hashed_set") is not True:
        failures.append("the protocol does not require the execution code to live outside the hashed set")
    if (protocol.get("deviation_disclosure") or {}).get("not_repaired") is not True:
        failures.append("the protocol does not record that the BTC-alignment deviation is not repaired")
    if (protocol.get("deviation_disclosure") or {}).get("carried_into_the_final_report") is not True:
        failures.append("the protocol does not carry the deviation disclosure into the final report")

    # 5. The authorization: self-hash, bounds, paths, preconditions, falsifiers.
    authorization_excluded = tuple(
        authorization.get("hashing", {}).get("manifest_hash_excluded_keys") or ()
    )
    if not authorization_excluded:
        failures.append("the authorization does not declare its manifest_hash_excluded_keys")
    declared_authorization = authorization.get("manifest_hash")
    if declared_authorization != compute_manifest_hash(authorization, authorization_excluded):
        failures.append("the authorization manifest hash does not recompute")
    if run.get("authorized") is not True:
        failures.append("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    bounds = run.get("bounds") or {}
    if bounds.get("max_assets") != len(assets_with_candidate):
        failures.append("the authorized asset bound differs from the frozen scope")
    if bounds.get("attempts") != 1:
        failures.append("the authorized attempt budget is not one")
    if not bounds.get("max_retries_on_technical_failure"):
        failures.append("the authorization records no technical-failure retries")
    paths = run.get("paths") or {}
    for name, path in paths.items():
        for banned in FORBIDDEN_PATHS:
            root_path = banned.rstrip("/")
            if str(path) == root_path or str(path).startswith(root_path + "/"):
                failures.append(
                    f"the confirmatory output path {name} points at the forbidden path {banned}"
                )
    if sorted(run.get("forbidden_paths") or []) != sorted(FORBIDDEN_PATHS):
        failures.append("the authorization does not record the forbidden v1, v2 and v3 paths")
    if not run.get("preconditions"):
        failures.append("the authorization records no preconditions")
    if not run.get("stopping_conditions"):
        failures.append("the authorization records no stopping conditions")
    if not run.get("falsifiers"):
        failures.append("the authorization records no falsifiers")
    if not run.get("rollback"):
        failures.append("the authorization records no rollback rule")
    if authorization.get("authorizes_evaluation_before_the_window_exists") is not False:
        failures.append("the authorization does not forbid an evaluation before the window exists")
    if authorization.get("authorizes_a_candle_read_before_the_window_exists") is not False:
        failures.append("the authorization does not forbid a candle read before the window exists")
    if authorization.get("authorizes_a_benchmark_retrieval_before_the_window_exists") is not False:
        failures.append("the authorization does not forbid a benchmark retrieval")
    if (run.get("protocol") or {}).get("manifest_hash") != declared_protocol:
        failures.append("the authorization is not bound to the confirmatory protocol")

    # 6. Exactly one decision criterion, in the authorization and in the path.
    decision_rule = run.get("decision_rule") or {}
    if decision_rule.get("criterion_count") != 1:
        failures.append("the authorization does not record exactly one decision criterion")
    if decision_rule.get("authoritative_source") != AUTHORITATIVE_CRITERION_SOURCE:
        failures.append("the authorization does not name the v3 promotion rule as authoritative")
    if decision_rule.get("exactly_one_criterion") is not True or decision_rule.get(
        "no_competing_criterion"
    ) is not True:
        failures.append("the authorization does not forbid a competing criterion")
    if decision_rule.get("secondary_source") is not None or decision_rule.get(
        "secondary_field"
    ) is not None:
        failures.append("the authorization names a second confirmatory criterion")
    for identifier in SECOND_CRITERION_IDENTIFIERS:
        for source in sorted(package.glob("*.py")) if package.is_dir() else []:
            usages = _second_criterion_usages(source, identifier)
            if usages:
                failures.append(
                    f"the confirmatory execution path carries a second criterion surface: "
                    f"{identifier} in {source.relative_to(root).as_posix()} ({', '.join(usages)})"
                )

    # 7. The window-benchmark rule of the authorization.
    benchmark_rule = run.get("benchmark_rule") or {}
    if benchmark_rule.get("window_benchmark_series_required") is not True:
        failures.append("the authorization does not require the window benchmark series")
    if benchmark_rule.get("development_benchmark_may_be_reused") is not False:
        failures.append("the authorization allows the development benchmark to be reused")
    if sorted(benchmark_rule.get("fail_closed") or []) != sorted(FAIL_CLOSED_REASONS):
        failures.append("the authorization's fail-closed benchmark rules differ from the protocol's")
    if benchmark_rule.get("no_forward_fill") is not True:
        failures.append("the authorization does not forbid forward-filling a missing benchmark")
    if benchmark_rule.get("btc_configurations_dropped") is not False:
        failures.append("the authorization allows the BTC configurations to be dropped")
    if benchmark_rule.get("symbol") != protocol_benchmark.get("symbol"):
        failures.append("the authorization and the protocol name different benchmark symbols")

    # 8. The window definition follows from the frozen candidate freeze.
    frozen_boundary = freeze.get("data_boundary") or {}
    window = run.get("window") or {}
    if window.get("window_start_utc") != frozen_boundary.get("confirmatory_window_start_utc"):
        failures.append("the authorized window start is not the frozen confirmatory-window start")
    if window.get("minimum_closed_hourly_candles") != frozen_boundary.get(
        "min_confirmatory_window_hours"
    ):
        failures.append("the authorized window does not require the frozen minimum hours")
    if window.get("earliest_possible_end_utc") != frozen_boundary.get(
        "earliest_possible_confirmatory_window_end_utc"
    ):
        failures.append("the authorized earliest window end does not follow from the freeze")
    if window.get("single_use") is not True:
        failures.append("the authorized window is not single-use")
    if window.get("must_not_overlap_v1_holdout") is not True:
        failures.append("the authorized window does not forbid a v1 holdout overlap")
    if window.get("must_not_overlap_v2_confirmatory_window") is not True:
        failures.append("the authorized window does not forbid a v2 confirmatory-window overlap")
    if window.get("never_reused_from_v1") is not True or window.get("never_reused_from_v2") is not True:
        failures.append("the authorized window does not forbid reuse from v1 or v2")
    if window.get("never_used_for_selection_ranking_or_retuning") is not True:
        failures.append("the authorized window does not forbid selection, ranking or re-tuning on it")
    if not window.get("evaluation_window_rule"):
        failures.append("the authorization does not fix the evaluated window's length")
    if protocol_window.get("window_opens_utc") != window.get("window_start_utc"):
        failures.append("the protocol and the authorization disagree about the window start")

    # 9. The evaluation rule is the unchanged v1 rule.
    evaluation_rule = run.get("evaluation_rule") or {}
    if evaluation_rule.get("unchanged_v1_evaluation_metric") is not True:
        failures.append("the authorization does not record the unchanged v1 evaluation metric")
    if evaluation_rule.get("unchanged_cost_scenarios") is not True:
        failures.append("the authorization does not record the unchanged cost scenarios")
    if evaluation_rule.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        failures.append("the authorization does not prohibit re-tuning on the window")
    if evaluation_rule.get("cost_scenarios") != [float(value) for value in spec_v1["costs"]["scenarios"]]:
        failures.append("the authorized cost scenarios differ from the unchanged v1 cost scenarios")
    if spec_v3.get("selection") != spec_v1.get("selection"):
        failures.append("the v3 specification no longer inherits the v1 selection block unchanged")

    # 10. Nothing has been executed under this path.
    for relative in CONFIRMATORY_ARTIFACTS:
        if (root / relative).exists():
            failures.append(f"a confirmatory artifact exists: {relative}")
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not marked NOT_STARTED")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("the v3 data manifest records confirmatory-window exposure")
    for relative in (
        "research_state/checkpoint_v3.json",
        "research/ledger_v3.json",
    ):
        path = root / relative
        if path.exists():
            document = _load(path)
            if document.get("holdout_exposed_count", 0):
                failures.append(f"{relative} records confirmatory-window exposure")
    for stream in ("research/results.jsonl", "research/results_v3.jsonl"):
        results_stream = root / stream
        if not results_stream.exists():
            continue
        for line in results_stream.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "confirmatory" in str(row.get("campaign_id", "")):
                failures.append(f"a confirmatory result row exists in {stream}")

    # 11. The v1 evidence is byte-identical and the frozen artifacts unchanged.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    for relative, digest in FROZEN_ARTIFACTS.items():
        target = root / relative
        if not target.exists():
            failures.append(f"the frozen artifact {relative} is missing")
            continue
        if relative.endswith(".json"):
            document = _load(target)
            observed = (
                document.get("manifest_hash")
                or document.get("specification_hash")
                or document.get("specification_identities", {}).get("spec_v3_self_hash")
            )
            if observed is not None and observed != digest:
                failures.append(
                    f"the frozen artifact {relative} does not match its recorded hash"
                )

    # 12. The authorization's immutable anchors still hold.
    anchors = run.get("immutable_artifact_anchors") or {}
    for group in ("v1_evidence", "v2_selection_outputs", "v3_selection_outputs"):
        entries = anchors.get(group) or {}
        if not entries:
            failures.append(f"the authorization records no immutable {group} anchors")
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

    # 13. The v1 campaign authorization is untouched.
    campaign_authorization_path = root / "research_state" / "campaign_authorization.json"
    if campaign_authorization_path.exists():
        campaign_authorization = _load(campaign_authorization_path)
        if campaign_authorization.get("code_hash") != AUTHORIZED_ORDERED_CODE_HASH:
            failures.append("the v1 campaign authorization's code hash changed")
        if campaign_authorization.get("specification_hash") != V1_SPECIFICATION_HASH:
            failures.append("the v1 campaign authorization's specification hash changed")
    else:
        failures.append("research_state/campaign_authorization.json is missing")

    # 14. The window manifest, when it exists, is hash-bound, covered and counted.
    window_manifest_path = root / "research" / "v3_confirmatory_window_manifest.json"
    if window_manifest_path.exists():
        window_manifest = _load(window_manifest_path)
        excluded = tuple(
            window_manifest.get("hashing", {}).get("manifest_hash_excluded_keys") or ()
        )
        if not excluded:
            failures.append("the window manifest does not declare its manifest_hash_excluded_keys")
        elif window_manifest.get("manifest_hash") != compute_manifest_hash(
            window_manifest, excluded
        ):
            failures.append("the window manifest manifest hash does not recompute")
        if window_manifest.get("data_manifest", {}).get("edited") is not False:
            failures.append("the window manifest does not record that the v3 data manifest is unedited")
        minimum_hours = int(
            (freeze.get("data_boundary") or {}).get("min_confirmatory_window_hours") or 0
        )
        for asset, record in sorted((window_manifest.get("assets") or {}).items()):
            if int(record.get("observed_candle_count") or 0) < minimum_hours:
                failures.append(
                    f"the window dataset of {asset} holds fewer than {minimum_hours} closed candles"
                )
        if not (window_manifest.get("benchmark") or {}).get("content_hash"):
            failures.append("the window manifest records no window benchmark dataset")
        exposure = window_manifest.get("exposure") or {}
        events = exposure.get("exposure_events") or []
        if int(window_manifest.get("holdout_exposed_count") or 0) < len(events):
            failures.append("the window manifest's exposure count is below its event count")
    else:
        window_manifest = {}

    # 15. The exposure counter has never been reset.
    confirmatory_checkpoint = root / "research_state" / "checkpoint_v3_confirmatory.json"
    if confirmatory_checkpoint.exists():
        checkpoint = _load(confirmatory_checkpoint)
        exposure = checkpoint.get("exposure") or {}
        events = exposure.get("exposure_events") or []
        if int(checkpoint.get("holdout_exposed_count") or 0) < len(events):
            failures.append("the confirmatory checkpoint's exposure count was reset")
        for event in events:
            if event.get("run_id") != run.get("run_id"):
                failures.append("the confirmatory checkpoint records an exposure of another run")

    return {
        "ok": not failures,
        "protocol_manifest_hash": declared_protocol,
        "authorization_manifest_hash": declared_authorization,
        "canonical_source_digest": live_hashed_set,
        "execution_path_digest": live_execution_path,
        "run_code_identity": expected_identity,
        "recorded_run_code_identity": recorded_identity,
        "code_hash_rotation_applied": bool(rotation),
        "in_scope_assets": len(assets_with_candidate),
        "out_of_scope_assets": assets_without_candidate,
        "benchmark_symbol": benchmark_rule.get("symbol"),
        "window_opens_utc": window.get("window_start_utc"),
        "earliest_possible_end_utc": window.get("earliest_possible_end_utc"),
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

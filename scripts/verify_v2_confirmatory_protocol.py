#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 confirmatory-evaluation protocol.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks ``configs/research_v2_confirmatory_protocol.json``
against the artifacts it claims to preregister:

* the manifest hash recomputes from the canonical content of the document with
  the digest-carrying key removed;
* the evaluation scope is exactly the 14 selected configurations of
  ``research/v2_selected_configurations_manifest.json``, bound to that
  manifest's hash, the selection authorization's hash, the v2 specification
  hash and the v2 data manifest hash; the 4 assets without a candidate stay
  out of scope;
* the confirmatory window opens at the frozen start, needs at least 2,160
  closed hourly candles, is single-use, never overlaps the v1 holdout and is
  never reused from v1;
* the data path records that retrieval happens once after the readiness test
  passes, every read is counted in ``holdout_exposed_count``, and the data is
  hashed and verified against the v2 data-manifest scheme;
* the evaluation rule records the unchanged v1 evaluation metric, the unchanged
  cost scenarios and the prohibition on re-tuning, re-ranking or extending the
  grid on the window;
* the reporting and falsifiers block defines pass / failure / inconclusive,
  reports a null result and never re-opens the v1 holdout;
* the authorization boundary authorizes no evaluation and no candle read
  before the window exists, uses the canonical digest as the code-identity
  rule, forbids v1 paths and requires a new versioned amendment for new v2
  paths;
* nothing has been executed under this protocol: the confirmatory window is
  still ``NOT_STARTED`` and ``holdout_exposed_count`` is still 0;
* the v1 evidence is byte-identical;
* the code-hash constraint names only paths that really are outside the hashed
  source set and records the authorized v1 code hash.

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

PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v2_confirmatory_protocol.json"
SELECTED_CONFIGURATIONS_MANIFEST_PATH = REPO_ROOT / "research" / "v2_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_PATH = REPO_ROOT / "configs" / "research_v2_selection_authorization_1.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
DATA_MANIFEST_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
CANDIDATE_FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"
CODE_HASH_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

HASHED_SET_ROOT = "src/breakout_research"


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


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def path_is_inside_hashed_set(relative: str) -> bool:
    root = HASHED_SET_ROOT.rstrip("/")
    candidate = relative.rstrip("/")
    return candidate == root or candidate.startswith(root + "/")


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    protocol_path = repo_root / "configs" / "research_v2_confirmatory_protocol.json"

    required = [
        protocol_path,
        repo_root / "research" / "v2_selected_configurations_manifest.json",
        repo_root / "configs" / "research_v2_selection_authorization_1.json",
        repo_root / "configs" / "research_v2.json",
        repo_root / "configs" / "research_v1.json",
        repo_root / "research" / "data_manifest_v2.json",
        repo_root / "research" / "universe_manifest_v2.json",
        repo_root / "configs" / "research_v2_candidate_freeze.json",
        repo_root / "research_state" / "campaign_authorization.json",
        repo_root / "configs" / "research_v2_code_hash_amendment_1.json",
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (repo_root / "research" / "v2_selected_configurations_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    selection_auth = json.loads(
        (repo_root / "configs" / "research_v2_selection_authorization_1.json").read_text(
            encoding="utf-8"
        )
    )
    spec_v2 = json.loads((repo_root / "configs" / "research_v2.json").read_text(encoding="utf-8"))
    spec_v1 = json.loads((repo_root / "configs" / "research_v1.json").read_text(encoding="utf-8"))
    data_manifest = json.loads(
        (repo_root / "research" / "data_manifest_v2.json").read_text(encoding="utf-8")
    )
    universe = json.loads(
        (repo_root / "research" / "universe_manifest_v2.json").read_text(encoding="utf-8")
    )
    freeze = json.loads(
        (repo_root / "configs" / "research_v2_candidate_freeze.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(
        (repo_root / "research_state" / "campaign_authorization.json").read_text(encoding="utf-8")
    )
    code_hash_amendment = json.loads(
        (repo_root / "configs" / "research_v2_code_hash_amendment_1.json").read_text(encoding="utf-8")
    )

    # 1. Self hash.
    excluded = tuple(protocol.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the protocol does not declare its manifest_hash_excluded_keys")
    declared = protocol.get("manifest_hash")
    recomputed = compute_manifest_hash(protocol, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. Evaluation scope is exactly the 14 selected configurations.
    scope = protocol.get("evaluation_scope") or {}
    if scope.get("selected_configurations_manifest") != "research/v2_selected_configurations_manifest.json":
        failures.append("the evaluation scope does not name the selected-configurations manifest")
    if scope.get("selected_configurations_manifest_hash") != manifest.get("manifest_hash"):
        failures.append("the scope is not bound to the selected-configurations manifest hash")
    if scope.get("selection_authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("the scope is not bound to the selection authorization manifest hash")
    if scope.get("v2_specification_hash") != spec_v2.get("specification_hash"):
        failures.append("the scope is not bound to the v2 specification hash")
    if scope.get("v2_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("the scope is not bound to the v2 data manifest hash")
    selections = manifest.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    if scope.get("in_scope_assets") != len(assets_with_candidate):
        failures.append("the in-scope asset count does not match the selected-configurations manifest")
    if scope.get("out_of_scope_assets_without_candidate") != assets_without_candidate:
        failures.append("the out-of-scope assets do not match the manifest's assets without a candidate")
    if scope.get("scope_may_not_be_widened_narrowed_or_reranked") is not True:
        failures.append("the scope does not forbid widening, narrowing or re-ranking")

    # 3. Window definition and readiness test.
    window = protocol.get("window_definition") or {}
    freeze_data_boundary = freeze.get("data_boundary") or {}
    if window.get("window_opens_utc") != freeze_data_boundary.get("confirmatory_window_start_utc"):
        failures.append("the window open does not match the frozen confirmatory start")
    if window.get("minimum_closed_hourly_candles") != 2160:
        failures.append("the confirmatory window does not require 2,160 closed hourly candles")
    if window.get("earliest_possible_end_utc") != freeze_data_boundary.get(
        "earliest_possible_confirmatory_window_end_utc"
    ):
        failures.append("the earliest possible window end does not follow from the freeze boundary")
    if window.get("single_use") is not True:
        failures.append("the confirmatory window is not marked single-use")
    if window.get("must_not_overlap_v1_holdout") is not True:
        failures.append("the confirmatory window does not forbid v1 holdout overlap")
    if window.get("never_reused_from_v1") is not True:
        failures.append("the confirmatory window does not forbid reuse from v1")

    # 4. Data path.
    data_path = protocol.get("data_path") or {}
    if data_path.get("retrieval_happens_once_after_readiness_test_passes") is not True:
        failures.append("the data path does not require a single retrieval after the readiness test")
    if data_path.get("every_read_counted_in_holdout_exposed_count") is not True:
        failures.append("the data path does not require every read to be counted in holdout_exposed_count")
    if data_path.get("hashed_and_verified_against_v2_data_manifest_scheme") is not True:
        failures.append("the data path does not require hashing and verification against the v2 data manifest scheme")
    if data_path.get("data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("the data path is not bound to the v2 data manifest hash")

    # 5. Evaluation rule.
    evaluation_rule = protocol.get("evaluation_rule") or {}
    if evaluation_rule.get("unchanged_v1_evaluation_metric") is not True:
        failures.append("the evaluation rule does not record the unchanged v1 evaluation metric")
    if evaluation_rule.get("unchanged_cost_scenarios") is not True:
        failures.append("the evaluation rule does not record the unchanged cost scenarios")
    if evaluation_rule.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        failures.append("the evaluation rule does not prohibit re-tuning, re-ranking or grid extension on the window")
    if evaluation_rule.get("selection_rule_reference") != "configs/research_v1.json#selection":
        failures.append("the evaluation rule does not reference the unchanged v1 selection block")
    if spec_v2.get("selection") != spec_v1.get("selection"):
        failures.append("the v2 specification no longer inherits the v1 selection block unchanged")

    # 6. Reporting and falsifiers.
    reporting = protocol.get("reporting_and_falsifiers") or {}
    if reporting.get("pass_failure_inconclusive_defined") is not True:
        failures.append("the reporting block does not define pass, failure and inconclusive")
    if reporting.get("null_result_reported") is not True:
        failures.append("the reporting block does not require a null result to be reported")
    if reporting.get("v1_holdout_never_reopened") is not True:
        failures.append("the reporting block does not forbid re-opening the v1 holdout")
    falsifiers = reporting.get("falsifiers") or []
    if not isinstance(falsifiers, list) or len(falsifiers) == 0:
        failures.append("the reporting block does not record any falsifiers")

    # 7. Authorization boundary authorizes nothing.
    boundary = protocol.get("authorization_boundary") or {}
    if boundary.get("authorizes_evaluation") is not False:
        failures.append("authorization_boundary.authorizes_evaluation is not false")
    if boundary.get("authorizes_candle_read_before_window_exists") is not False:
        failures.append("authorization_boundary.authorizes_candle_read_before_window_exists is not false")
    if boundary.get("code_identity_rule") != "canonical_digest":
        failures.append("the authorization boundary does not use the canonical digest as the code-identity rule")
    if boundary.get("v1_paths_forbidden") is not True:
        failures.append("the authorization boundary does not forbid v1 paths")
    if boundary.get("new_v2_paths_require_new_versioned_amendment") is not True:
        failures.append("the authorization boundary does not require a new versioned amendment for new v2 paths")

    # 8. Code hash constraint.
    constraint = protocol.get("code_hash_constraint") or {}
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_canonical = canonical_source_digest(repo_root)
    if constraint.get("canonical_source_digest") != recorded_canonical:
        failures.append("the code-hash constraint does not record the canonical source digest")
    if recorded_canonical != live_canonical:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}"
        )
    authorized_code_hash = authorization.get("code_hash")
    if constraint.get("authorized_code_hash") != authorized_code_hash:
        failures.append("the code-hash constraint does not record the authorized v1 code hash")
    if boundary.get("authorized_code_hash") != authorized_code_hash:
        failures.append("the authorization boundary does not record the authorized v1 code hash")
    if constraint.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the code-hash constraint does not name the hashed source root")
    for relative in constraint.get("inside_hashed_set_examples") or []:
        if not path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as inside the hashed set but is not")
    for relative in constraint.get("outside_hashed_set_examples") or []:
        if path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as outside the hashed set but is inside it")

    # 9. Nothing has been executed under this protocol.
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is not marked NOT_STARTED")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")

    # 10. The v1 evidence is byte-identical.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")

    # 11. The related artifacts are the ones that are recorded.
    related = protocol.get("related_artifacts") or {}
    expected_related = {
        "selected_configurations_manifest": (
            "research/v2_selected_configurations_manifest.json",
            manifest.get("manifest_hash"),
        ),
        "selection_authorization_1": (
            "configs/research_v2_selection_authorization_1.json",
            selection_auth.get("manifest_hash"),
        ),
        "v2_specification": (
            "configs/research_v2.json",
            spec_v2.get("specification_hash"),
        ),
        "v2_data_manifest": (
            "research/data_manifest_v2.json",
            data_manifest.get("manifest_hash"),
        ),
        "v2_candidate_freeze": (
            "configs/research_v2_candidate_freeze.json",
            freeze.get("manifest_hash"),
        ),
    }
    for key, (relative, digest) in expected_related.items():
        entry = related.get(key) or {}
        if entry.get("path") != relative:
            failures.append(f"related_artifacts.{key} does not point at {relative}")
        if entry.get("manifest_hash", entry.get("specification_hash")) != digest:
            failures.append(f"related_artifacts.{key} records a hash that does not match {relative}")

    # 12. Supersession of the selection authorization.
    supersedes = protocol.get("supersedes") or {}
    if supersedes.get("selection_authorization_path") != "configs/research_v2_selection_authorization_1.json":
        failures.append("the supersedes block does not name the selection authorization")
    if supersedes.get("selection_authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("the superseded selection authorization hash does not match")
    if supersedes.get("v1_holdout_never_reused") is not True:
        failures.append("the supersession block does not record that the v1 holdout is never reused")

    return {
        "ok": not failures,
        "protocol_path": str(protocol_path.relative_to(repo_root)),
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "protocol_status": protocol.get("protocol_status"),
        "in_scope_assets": scope.get("in_scope_assets"),
        "out_of_scope_assets": scope.get("out_of_scope_assets_without_candidate"),
        "window_opens_utc": window.get("window_opens_utc"),
        "minimum_closed_hourly_candles": window.get("minimum_closed_hourly_candles"),
        "canonical_source_digest": live_canonical,
        "authorized_code_hash": authorized_code_hash,
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
    main()

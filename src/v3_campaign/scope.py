"""Frozen scope, selection rule and authorization validation for the v3 path.

This module resolves *what* a v3 selection run may touch:

* the candidate set, read from the validated candidate set of
  ``configs/research_v3_candidate_freeze_amendment_1.json`` and re-derived
  from ``research/universe_manifest_v3.json``;
* the data boundary, read from the frozen candidate set
  (``configs/research_v3_candidate_freeze.json``);
* the selection rule, read from the ``selection`` block of
  ``configs/research_v1.json`` and required to be byte-equal to the block that
  ``configs/research_v3.json`` inherits;
* the authorization, ``configs/research_v3_selection_authorization_1.json``,
  which must agree with all of them. That artifact does not exist yet, so a
  run is refused before it starts.

Every check recomputes its expectation from the bytes on disk; nothing is
compared against a literal copied out of the artifact under test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ScopeError
from .identity import canonical, canonical_source_digest, execution_path_digest, hashed_set_digest

V1_SPEC_PATH = "configs/research_v1.json"
V3_SPEC_PATH = "configs/research_v3.json"
FREEZE_PATH = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_PATH = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_PATH = "configs/research_v3_candidate_freeze_amendment_2.json"
DATA_AMENDMENT_1_PATH = "configs/research_v3_data_manifest_amendment_1.json"
DATA_MANIFEST_PATH = "research/data_manifest_v3.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest_v3.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
EXECUTION_PATH = "configs/research_v3_execution.json"
EXECUTION_AMENDMENT_1_PATH = "configs/research_v3_execution_amendment_1.json"
AUTHORIZATION_PATH = "configs/research_v3_selection_authorization_1.json"

#: The v1 and v2 output paths a v3 run may never write.
FORBIDDEN_PATHS = (
    "research/results_shards/",
    "research/results_manifest.json",
    "research/results.jsonl",
    "research_state/checkpoint.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "configs/research_v1.json",
    "research/shards_v2/",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)

#: The v3 output paths a selection run may write.
OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    """The self-hash of a hash-bound artifact."""
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def dig(document: Any, dotted: str) -> Any:
    """Read a dotted path out of a document, or ``None`` when it is absent."""
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def universe_validated_constituents(universe: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
    """The validated constituents of the v3 universe and the excluded ones.

    The membership rule is "exactly the constituents marked validated in
    ``research/universe_manifest_v3.json`` (``validated == true``,
    ``exclusion_reason == null``)". The set is re-derived from the universe
    manifest so that the frozen set is checked against its source of truth.
    """
    validated: List[str] = []
    excluded: Dict[str, str] = {}
    for entry in universe.get("eligible_assets") or []:
        symbol = str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        if entry.get("validated") is True and entry.get("exclusion_reason") is None:
            validated.append(symbol)
        else:
            excluded[symbol] = str(entry.get("exclusion_reason") or "excluded")
    return sorted(validated), excluded


def verify_artifact_hash(document: Dict[str, Any], label: str) -> str:
    """Recompute the self-hash of a hash-bound artifact and refuse a mismatch."""
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        raise ScopeError(f"{label} does not declare its manifest_hash_excluded_keys")
    declared = document.get("manifest_hash")
    recomputed = compute_manifest_hash(document, excluded)
    if recomputed != declared:
        raise ScopeError(
            f"the manifest hash of {label} does not recompute: recorded {declared}, "
            f"recomputed {recomputed}"
        )
    return str(declared)


def frozen_scope(freeze: Dict[str, Any], freeze_amendment_1: Dict[str, Any],
                 freeze_amendment_2: Dict[str, Any],
                 universe: Dict[str, Any]) -> Dict[str, Any]:
    """The frozen v3 candidate set, checked against the universe manifest.

    The candidate set is read from the validated candidate set of
    ``configs/research_v3_candidate_freeze_amendment_1.json`` and re-derived
    from ``research/universe_manifest_v3.json``. The data-manifest identity of
    the frozen scope is resolved through the amendment chain: the base freeze
    binds a superseded identity, and ``configs/research_v3_candidate_freeze_amendment_2.json``
    re-binds it to the effective data manifest (the base manifest plus the
    published benchmark entry). The amendment must supersede exactly the
    identity the freeze binds, and it must not change the candidate set.
    """
    verify_artifact_hash(freeze, "the v3 candidate freeze")
    verify_artifact_hash(freeze_amendment_1, "the v3 candidate freeze amendment 1")
    verify_artifact_hash(freeze_amendment_2, "the v3 candidate freeze amendment 2")

    members = (freeze_amendment_1.get("validated_candidate_set") or {}).get("members") or []
    pairs = [str(member.get("binance_pair")) for member in members]
    if not pairs:
        raise ScopeError("the validated candidate set of the freeze amendment is empty")

    rebound_pairs = (freeze_amendment_2.get("frozen_candidate_set") or {}).get("binance_pairs") or []
    if sorted(str(pair) for pair in rebound_pairs) != sorted(pairs):
        raise ScopeError(
            "the v3 candidate freeze amendment 2 changes the frozen candidate set; it may "
            "re-bind the data-manifest identity only"
        )

    validated, excluded = universe_validated_constituents(universe)
    if sorted(pairs) != validated:
        raise ScopeError(
            "the validated candidate set of the freeze amendment is not the set of "
            "validated constituents of research/universe_manifest_v3.json"
        )
    recorded_excluded = {
        str(member.get("binance_pair")): str(member.get("exclusion_reason"))
        for member in (freeze_amendment_1.get("excluded_candidates") or {}).get("members") or []
    }
    for symbol, reason in recorded_excluded.items():
        if excluded.get(symbol) != reason:
            raise ScopeError(
                f"the frozen exclusion reason for {symbol} differs from the reason recorded "
                "by the v3 universe manifest"
            )

    rebound = freeze_amendment_2.get("rebound_identity") or {}
    superseded = (freeze.get("snapshot_identity") or {}).get("data_manifest_hash")
    if rebound.get("superseded_data_manifest_hash") != superseded:
        raise ScopeError(
            "the v3 candidate freeze amendment 2 does not supersede the data-manifest "
            "identity that the frozen candidate set binds"
        )
    if (freeze.get("frozen_candidate_set") or {}).get("data_manifest_hash") != superseded:
        raise ScopeError(
            "the frozen candidate set binds the data-manifest identity in two places that "
            "disagree"
        )

    boundary = freeze.get("data_boundary") or {}
    amendment_boundary = freeze_amendment_2.get("data_boundary") or {}
    if amendment_boundary.get("confirmatory_window_start_utc") != boundary.get(
        "confirmatory_window_start_utc"
    ):
        raise ScopeError(
            "the v3 candidate freeze amendment 2 moves the confirmatory-window boundary"
        )

    return {
        "binance_pairs": pairs,
        "count": len(pairs),
        "excluded_after_validation": recorded_excluded,
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_hash": rebound.get("effective_data_manifest_hash"),
        "superseded_data_manifest_hash": superseded,
        "base_data_manifest_hash": rebound.get("base_data_manifest_hash"),
        "confirmatory_window_start_utc": boundary.get("confirmatory_window_start_utc"),
        "min_confirmatory_window_hours": boundary.get("min_confirmatory_window_hours"),
        "candidate_freeze_timestamp_utc": freeze.get("candidate_freeze_timestamp_utc"),
        "candidate_manifest_hash": freeze.get("manifest_hash"),
        "freeze_amendment_hash": freeze_amendment_1.get("manifest_hash"),
        "freeze_amendment_2_hash": freeze_amendment_2.get("manifest_hash"),
    }


def selection_rule(spec_v1: Dict[str, Any], spec_v3: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """The unchanged v1 selection rule and its digest.

    The v3 specification inherits the ``selection`` block from v1; the block
    must be byte-equal, otherwise the v3 selection rule is not the v1 rule and
    the run is refused.
    """
    block_v1 = spec_v1.get("selection")
    block_v3 = spec_v3.get("selection")
    if not isinstance(block_v1, dict) or not isinstance(block_v3, dict):
        raise ScopeError("a research specification does not carry a selection block")
    if canonical(block_v1) != canonical(block_v3):
        raise ScopeError(
            "the selection block of configs/research_v3.json is not byte-equal to the "
            "selection block of configs/research_v1.json"
        )
    return block_v1, sha256_bytes(canonical(block_v1).encode("utf-8"))


def assert_no_forbidden_output(paths: Dict[str, str]) -> None:
    """Fail closed when an output path points at a v1 or v2 artifact."""
    for name, path in paths.items():
        for banned in FORBIDDEN_PATHS:
            root = banned.rstrip("/")
            if path == root or path.startswith(root + "/"):
                raise ScopeError(f"the v3 output path {name} points at the forbidden path {banned}")


def authorization_output_paths(authorization: Dict[str, Any]) -> Dict[str, str]:
    """The v3 output paths the authorization allows the run to write."""
    paths = dig(authorization, "authorized_run.paths") or {}
    return {key: str(paths.get(key, "")) for key in OUTPUT_PATH_KEYS}


def validate_authorization(
    repo_root: Path,
    authorization: Dict[str, Any],
    scope: Dict[str, Any],
    rule_digest: str,
    rule_block: Dict[str, Any],
) -> Dict[str, Any]:
    """Check the v3 selection authorization against the artifacts it names.

    The authorization does not exist yet; this function is the gate that will
    check it when it does, and it recomputes every expectation from the
    repository.
    """
    excluded = tuple(dig(authorization, "hashing.manifest_hash_excluded_keys") or ())
    if not excluded:
        raise ScopeError("the authorization does not declare its manifest_hash_excluded_keys")
    declared_hash = authorization.get("manifest_hash")
    if compute_manifest_hash(authorization, excluded) != declared_hash:
        raise ScopeError("the authorization manifest hash does not recompute")

    run = authorization.get("authorized_run") or {}
    if run.get("authorized") is not True:
        raise ScopeError("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        raise ScopeError("the authorization does not bound the run to one attempt")

    recorded_scope = run.get("scope") or {}
    if list(recorded_scope.get("binance_pairs") or []) != list(scope["binance_pairs"]):
        raise ScopeError("the authorized candidate set is not the frozen candidate set")

    recorded_rule = run.get("selection_rule") or {}
    if recorded_rule.get("selection_block_sha256") != rule_digest:
        raise ScopeError("the authorized selection rule is not the unchanged v1 selection rule")
    if recorded_rule.get("max_candidates_per_asset") != rule_block.get("max_candidates_per_asset"):
        raise ScopeError("the authorized number of candidates per asset differs from the v1 rule")

    recorded_identity = run.get("code_identity") or {}
    if recorded_identity.get("hashed_set_digest") != hashed_set_digest(repo_root):
        raise ScopeError("the authorized hashed-set digest does not match the current source tree")
    if recorded_identity.get("execution_path_digest") != execution_path_digest(repo_root):
        raise ScopeError("the authorized execution-path digest does not match the current path")

    benchmark = run.get("benchmark") or {}
    if not benchmark.get("dataset_path") or not benchmark.get("content_hash"):
        raise ScopeError("the authorization names no benchmark dataset")
    if benchmark.get("alignment_rule") != (
        "the asset series and the benchmark series are sliced to the same fold window "
        "before the frozen engine is called"
    ):
        raise ScopeError("the authorization does not bind the benchmark alignment rule")
    if benchmark.get("btc_configurations_dropped") is not False:
        raise ScopeError("the authorization does not forbid dropping the BTC configurations")

    paths = authorization_output_paths(authorization)
    for key in OUTPUT_PATH_KEYS:
        if not paths.get(key):
            raise ScopeError(f"the authorization names an empty v3 output path {key}")
    assert_no_forbidden_output(paths)

    return {
        "manifest_hash": declared_hash,
        "run_id": run.get("run_id"),
        "campaign_id": run.get("campaign_id"),
        "run_phase": run.get("run_phase"),
        "bounds": run.get("bounds") or {},
        "data_boundary": run.get("data_boundary") or {},
        "code_identity": recorded_identity,
        "benchmark": benchmark,
    }


def verify_execution_amendment(execution_amendment_1: Dict[str, Any],
                               scope: Dict[str, Any],
                               effective_data_manifest_hash: str) -> Dict[str, Any]:
    """Check the v3 execution amendment against the scope and the identity.

    The amendment records the benchmark rule and re-binds the data-manifest
    identity of the evaluation scope. It authorizes nothing: a run still needs
    the separate selection authorization, which does not exist yet.
    """
    verify_artifact_hash(execution_amendment_1, "the v3 execution amendment 1")

    evaluation = execution_amendment_1.get("evaluation_scope") or {}
    if evaluation.get("data_manifest_hash") != effective_data_manifest_hash:
        raise ScopeError(
            "the v3 execution amendment does not bind the effective data-manifest identity"
        )
    if sorted(str(pair) for pair in evaluation.get("constituents") or []) != sorted(
        scope["binance_pairs"]
    ):
        raise ScopeError(
            "the evaluated scope of the v3 execution amendment is not the frozen candidate set"
        )
    if evaluation.get("candidate_freeze_amendment_2_hash") != scope["freeze_amendment_2_hash"]:
        raise ScopeError(
            "the v3 execution amendment does not bind the v3 candidate freeze amendment 2"
        )

    authorization = execution_amendment_1.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        raise ScopeError(
            "the v3 execution amendment claims an execution authorization; it authorizes none"
        )
    if authorization.get("selection_authorization_present") is not False:
        raise ScopeError(
            "the v3 execution amendment claims a selection authorization; none exists"
        )

    benchmark = execution_amendment_1.get("benchmark_rule") or {}
    if benchmark.get("no_forward_fill") is not True:
        raise ScopeError("the v3 execution amendment does not forbid forward-filling the benchmark")
    if not benchmark.get("content_hash") or not benchmark.get("dataset_path"):
        raise ScopeError("the v3 execution amendment names no benchmark dataset")

    constraint = execution_amendment_1.get("code_hash_constraint") or {}
    if constraint.get("v3_execution_root") != "src/v3_campaign":
        raise ScopeError(
            "the v3 execution amendment does not place the v3 execution path outside the "
            "hashed set"
        )

    return {
        "manifest_hash": execution_amendment_1.get("manifest_hash"),
        "benchmark": benchmark,
        "deviation_disclosure": execution_amendment_1.get("deviation_disclosure"),
        "code_hash_constraint": constraint,
    }


def load_workspace_documents(repo_root: Path) -> Dict[str, Any]:
    """Load every artifact the authorization is checked against."""
    root = Path(repo_root)
    return {
        "authorization": load_json(root / AUTHORIZATION_PATH),
        "freeze": load_json(root / FREEZE_PATH),
        "freeze_amendment_1": load_json(root / FREEZE_AMENDMENT_1_PATH),
        "freeze_amendment_2": load_json(root / FREEZE_AMENDMENT_2_PATH),
        "data_amendment_1": load_json(root / DATA_AMENDMENT_1_PATH),
        "spec_v1": load_json(root / V1_SPEC_PATH),
        "spec_v3": load_json(root / V3_SPEC_PATH),
        "data_manifest": load_json(root / DATA_MANIFEST_PATH),
        "universe_manifest": load_json(root / UNIVERSE_MANIFEST_PATH),
        "config_manifest": load_json(root / CONFIG_MANIFEST_PATH),
    }


__all__ = [
    "AUTHORIZATION_PATH",
    "CONFIG_MANIFEST_PATH",
    "DATA_AMENDMENT_1_PATH",
    "DATA_MANIFEST_PATH",
    "EXECUTION_AMENDMENT_1_PATH",
    "EXECUTION_PATH",
    "FORBIDDEN_PATHS",
    "FREEZE_AMENDMENT_1_PATH",
    "FREEZE_AMENDMENT_2_PATH",
    "FREEZE_PATH",
    "OUTPUT_PATH_KEYS",
    "UNIVERSE_MANIFEST_PATH",
    "V1_SPEC_PATH",
    "V3_SPEC_PATH",
    "assert_no_forbidden_output",
    "authorization_output_paths",
    "canonical",
    "canonical_source_digest",
    "compute_manifest_hash",
    "dig",
    "frozen_scope",
    "load_json",
    "load_workspace_documents",
    "selection_rule",
    "sha256_bytes",
    "sha256_file",
    "universe_validated_constituents",
    "validate_authorization",
    "verify_artifact_hash",
    "verify_execution_amendment",
]

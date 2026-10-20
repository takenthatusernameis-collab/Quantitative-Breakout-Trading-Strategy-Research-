"""Frozen scope, selection rule and authorization validation.

This module resolves *what* a v2 selection run may touch:

* the candidate set, read from the frozen candidate manifest
  ``configs/research_v2_candidate_freeze.json``;
* the selection rule, read from the ``selection`` block of
  ``configs/research_v1.json`` and required to be byte-equal to the block that
  ``configs/research_v2.json`` inherits;
* the bounds, read from ``configs/research_v2_execution_amendment_1.json``;
* the authorization, ``configs/research_v2_selection_authorization_1.json``,
  which must agree with all three.

Every check recomputes its expectation from the bytes on disk. A check that
compared an artifact against a constant copied out of that same artifact would
be vacuous, so nothing here is compared against a literal.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ScopeError
from .identity import canonical, canonical_source_digest, hashed_set_digest, execution_path_digest

V1_SPEC_PATH = "configs/research_v1.json"
V2_SPEC_PATH = "configs/research_v2.json"
FREEZE_PATH = "configs/research_v2_candidate_freeze.json"
DATA_MANIFEST_PATH = "research/data_manifest_v2.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest_v2.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
EXECUTION_AMENDMENT_PATH = "configs/research_v2_execution_amendment_1.json"
AUTHORIZATION_PATH = "configs/research_v2_selection_authorization_1.json"

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

#: The v2 output paths a selection run may write.
OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON document from disk."""
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
    """The self-hash of a hash-bound artifact.

    ``excluded_keys`` may name dotted paths; the named leaf is removed from the
    canonical body before the digest is taken.
    """
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


def frozen_scope(freeze: Dict[str, Any]) -> Dict[str, Any]:
    """The frozen candidate set, exactly as the freeze records it."""
    block = freeze.get("frozen_candidate_set") or {}
    constituents = list(block.get("constituents") or [])
    pairs = list(block.get("binance_pairs") or [])
    if not constituents or len(constituents) != len(pairs):
        raise ScopeError("the frozen candidate set is empty or inconsistent")
    return {
        "constituents": constituents,
        "binance_pairs": pairs,
        "count": len(constituents),
        "excluded_after_validation": dict(block.get("excluded_after_validation") or {}),
        "universe_manifest_hash": block.get("universe_manifest_hash"),
        "data_manifest_hash": block.get("data_manifest_hash"),
        "confirmatory_window_start_utc": dig(freeze, "data_boundary.confirmatory_window_start_utc"),
        "candidate_manifest_hash": freeze.get("manifest_hash"),
        "candidate_freeze_timestamp_utc": freeze.get("candidate_freeze_timestamp_utc"),
    }


def universe_validated_constituents(universe: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
    """The validated constituents of the v2 universe and the excluded ones.

    The membership rule of the frozen candidate manifest is "exactly the
    constituents marked validated in ``research/universe_manifest_v2.json``
    (``validated == true``, ``exclusion_reason == null``)". This function
    re-derives that set from the universe manifest so that the frozen set can
    be checked against its source of truth instead of against itself.
    """
    validated: List[str] = []
    excluded: Dict[str, str] = {}
    for entry in universe.get("eligible_assets") or []:
        symbol = str(entry.get("symbol"))
        if entry.get("validated") is True and entry.get("exclusion_reason") is None:
            validated.append(symbol)
        else:
            excluded[symbol] = str(entry.get("exclusion_reason") or "excluded")
    return sorted(validated), excluded


def selection_rule(spec_v1: Dict[str, Any], spec_v2: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """The unchanged v1 selection rule and its digest.

    The v2 specification inherits the ``selection`` block from v1; the block
    must be byte-equal, otherwise the v2 selection rule is not the v1 rule and
    the run is refused.
    """
    block_v1 = spec_v1.get("selection")
    block_v2 = spec_v2.get("selection")
    if not isinstance(block_v1, dict) or not isinstance(block_v2, dict):
        raise ScopeError("a research specification does not carry a selection block")
    if canonical(block_v1) != canonical(block_v2):
        raise ScopeError(
            "the selection block of configs/research_v2.json is not byte-equal to the "
            "selection block of configs/research_v1.json"
        )
    return block_v1, sha256_bytes(canonical(block_v1).encode("utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScopeError(message)


def validate_authorization(
    repo_root: Path,
    authorization: Dict[str, Any],
    freeze: Dict[str, Any],
    amendment: Dict[str, Any],
    spec_v1: Dict[str, Any],
    spec_v2: Dict[str, Any],
) -> Dict[str, Any]:
    """Check the authorization against the artifacts it names.

    Every expectation is recomputed from the repository: the self-hash, the
    candidate set, the bounds, the data boundary, the selection rule and the
    code identity of the execution path.
    """
    excluded = tuple(authorization.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    _require(bool(excluded), "the authorization does not declare its manifest_hash_excluded_keys")
    declared_hash = authorization.get("manifest_hash")
    recomputed_hash = compute_manifest_hash(authorization, excluded)
    _require(
        declared_hash == recomputed_hash,
        f"the authorization manifest hash does not recompute: declared {declared_hash}, "
        f"recomputed {recomputed_hash}",
    )

    run = authorization.get("authorized_run") or {}
    _require(run.get("authorized") is True, "the authorization does not authorize a run")
    _require(run.get("max_runs") == 1, "the authorization does not bound the run to one attempt")

    scope = frozen_scope(freeze)
    recorded_scope = run.get("scope") or {}
    _require(
        list(recorded_scope.get("constituents") or []) == scope["constituents"],
        "the authorized candidate set is not the frozen candidate set",
    )
    _require(
        list(recorded_scope.get("binance_pairs") or []) == scope["binance_pairs"],
        "the authorized Binance pairs are not the frozen Binance pairs",
    )
    _require(
        recorded_scope.get("bound_to_freeze_hash") == scope["candidate_manifest_hash"],
        "the authorization is not bound to the frozen candidate manifest",
    )
    _require(
        recorded_scope.get("bound_to_universe_hash") == scope["universe_manifest_hash"],
        "the authorization is not bound to the v2 universe manifest",
    )
    _require(
        recorded_scope.get("bound_to_data_hash") == scope["data_manifest_hash"],
        "the authorization is not bound to the v2 data manifest",
    )

    amendment_bounds = dig(amendment, "v2_selection_authorization.bounds") or {}
    recorded_bounds = run.get("bounds") or {}
    for key in ("max_assets", "max_configs_per_asset", "max_total_config_units", "attempts"):
        _require(
            recorded_bounds.get(key) == amendment_bounds.get(key),
            f"the authorized bound {key} differs from the bound recorded by execution "
            f"amendment 1: {recorded_bounds.get(key)} != {amendment_bounds.get(key)}",
        )

    recorded_boundary = run.get("data_boundary") or {}
    _require(
        recorded_boundary.get("candles_before_utc") == scope["confirmatory_window_start_utc"],
        "the authorized data boundary is not the confirmatory window start of the freeze",
    )
    _require(
        recorded_boundary.get("confirmatory_window_never_read_during_selection") is True,
        "the authorization does not forbid reading the confirmatory window during selection",
    )
    _require(
        recorded_boundary.get("v1_holdout_never_reused") is True,
        "the authorization does not forbid reusing the v1 holdout",
    )

    rule_block, rule_digest = selection_rule(spec_v1, spec_v2)
    recorded_rule = run.get("selection_rule") or {}
    _require(
        recorded_rule.get("selection_block_sha256") == rule_digest,
        "the authorized selection rule is not the unchanged v1 selection rule",
    )
    _require(
        recorded_rule.get("max_candidates_per_asset") == rule_block.get("max_candidates_per_asset"),
        "the authorized number of candidates per asset differs from the v1 selection rule",
    )

    recorded_identity = run.get("code_identity") or {}
    live_hashed_set = hashed_set_digest(repo_root)
    live_execution_path = execution_path_digest(repo_root)
    _require(
        recorded_identity.get("hashed_set_digest") == live_hashed_set,
        "the authorized hashed-set digest does not match the current source tree",
    )
    _require(
        recorded_identity.get("execution_path_digest") == live_execution_path,
        "the authorized execution-path digest does not match the current execution path",
    )
    _require(
        recorded_identity.get("run_code_identity")
        == dig(authorization, "authorized_run.code_identity.run_code_identity"),
        "the run code identity is not self-consistent",
    )

    paths = run.get("paths") or {}
    forbidden = [str(value) for value in (paths.get("v1_paths_forbidden") or [])]
    amendment_paths = dig(amendment, "v2_selection_authorization.paths") or {}
    for key in OUTPUT_PATH_KEYS:
        path = str(paths.get(key, ""))
        _require(bool(path), f"the authorization names an empty v2 output path {key}")
        _require(
            path == str(amendment_paths.get(key, "")),
            f"the authorized output path {key} differs from the path recorded by execution "
            f"amendment 1: {path} != {amendment_paths.get(key)}",
        )
        for banned in forbidden:
            root = banned.rstrip("/")
            _require(
                path != root and not path.startswith(root + "/"),
                f"the authorization writes to the forbidden v1 path {path}",
            )
    for banned in forbidden:
        _require(banned in V1_PATHS_FORBIDDEN, f"the forbidden path list names an unknown path {banned}")

    return {
        "manifest_hash": declared_hash,
        "scope": scope,
        "bounds": recorded_bounds,
        "data_boundary": recorded_boundary,
        "selection_rule": rule_block,
        "selection_rule_digest": rule_digest,
        "code_identity": recorded_identity,
        "run_id": run.get("run_id"),
        "campaign_id": run.get("campaign_id"),
        "run_phase": run.get("run_phase"),
    }


def authorization_output_paths(authorization: Dict[str, Any]) -> Dict[str, str]:
    """The v2 output paths the authorization allows the run to write."""
    paths = authorization.get("authorized_run", {}).get("paths") or {}
    return {
        "shards_dir": str(paths.get("shards_dir", "")),
        "ledger": str(paths.get("ledger", "")),
        "results_manifest": str(paths.get("results_manifest", "")),
        "results_stream": str(paths.get("results_stream", "")),
        "checkpoint": str(paths.get("checkpoint", "")),
    }


def assert_no_forbidden_output(paths: Dict[str, str]) -> None:
    """Fail closed when an output path points at a v1 artifact."""
    for name, path in paths.items():
        for banned in V1_PATHS_FORBIDDEN:
            root = banned.rstrip("/")
            if path == root or path.startswith(root + "/"):
                raise ScopeError(f"the v2 output path {name} points at the v1 path {banned}")


def load_workspace_documents(repo_root: Path) -> Dict[str, Any]:
    """Load every artifact the authorization is checked against."""
    root = Path(repo_root)
    return {
        "authorization": load_json(root / AUTHORIZATION_PATH),
        "freeze": load_json(root / FREEZE_PATH),
        "amendment": load_json(root / EXECUTION_AMENDMENT_PATH),
        "spec_v1": load_json(root / V1_SPEC_PATH),
        "spec_v2": load_json(root / V2_SPEC_PATH),
        "data_manifest": load_json(root / DATA_MANIFEST_PATH),
        "universe_manifest": load_json(root / UNIVERSE_MANIFEST_PATH),
        "config_manifest": load_json(root / CONFIG_MANIFEST_PATH),
    }


def list_execution_path_modules(repo_root: Path) -> List[str]:
    """The ``*.py`` modules of the v2 execution path, in path order."""
    root = Path(repo_root) / "src" / "v2_campaign"
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))


__all__ = [
    "AUTHORIZATION_PATH",
    "CONFIG_MANIFEST_PATH",
    "DATA_MANIFEST_PATH",
    "EXECUTION_AMENDMENT_PATH",
    "FREEZE_PATH",
    "UNIVERSE_MANIFEST_PATH",
    "V1_PATHS_FORBIDDEN",
    "V1_SPEC_PATH",
    "V2_SPEC_PATH",
    "assert_no_forbidden_output",
    "authorization_output_paths",
    "canonical",
    "canonical_source_digest",
    "compute_manifest_hash",
    "dig",
    "frozen_scope",
    "list_execution_path_modules",
    "load_json",
    "load_workspace_documents",
    "selection_rule",
    "sha256_bytes",
    "sha256_file",
    "universe_validated_constituents",
    "validate_authorization",
]

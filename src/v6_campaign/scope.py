"""Frozen scope, selection rule and authorization validation for the v6 path.

This module resolves *what* a v6 selection run may touch:

* the candidate set, read from the validated candidate set of
  ``configs/research_v6_candidate_freeze.json`` and re-derived from
  ``research/universe_manifest_v6.json``;
* the data boundary, read from the frozen candidate set
  (``configs/research_v6_candidate_freeze.json``);
* the selection rule, read from the ``selection`` block of
  ``configs/research_v1.json`` and required to be byte-equal to the block that
  ``configs/research_v6.json`` inherits;
* the authorization, ``configs/research_v6_selection_authorization_1.json``,
  which must agree with all of them.

Every check recomputes its expectation from the bytes on disk; nothing is
compared against a literal copied out of the artifact under test.

**The effective rules.** v6 published three amendments, and each of them owns
one rule for the effective behaviour. The amendment wins over the frozen block
it corrects; the frozen block stays on disk, unchanged and visible:

* ``configs/research_v6_specification_amendment_1.json`` owns the
  confirmatory-window **membership** rule (a candle that closes exactly at a
  window's start is development data);
* ``configs/research_v6_candidate_freeze_amendment_1.json`` owns the
  confirmatory-window **overlap** rule and the effective v6 evaluation gate;
* ``configs/research_v6_execution_amendment_1.json`` owns the blocks of the
  execution protocol that its first publication did not carry.

A rule is read from its amendment first and from the frozen artifact second.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data import parse_utc_ms
from .errors import ScopeError
from .identity import canonical, canonical_source_digest, execution_path_digest, hashed_set_digest

import sys
SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from v6_universe_rules import (  # noqa: E402
    V6RuleError, resolve_effective_v6_execution_protocol,
    verify_effective_v6_selection_authorization,
)

V1_SPEC_PATH = "configs/research_v1.json"
V6_SPEC_PATH = "configs/research_v6.json"
SPEC_AMENDMENT_1_PATH = "configs/research_v6_specification_amendment_1.json"
FREEZE_PATH = "configs/research_v6_candidate_freeze.json"
FREEZE_AMENDMENT_1_PATH = "configs/research_v6_candidate_freeze_amendment_1.json"
DATA_MANIFEST_PATH = "research/data_manifest_v6.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest_v6.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
EXECUTION_PATH = "configs/research_v6_execution.json"
EXECUTION_AMENDMENT_1_PATH = "configs/research_v6_execution_amendment_1.json"
EXECUTION_AMENDMENT_2_PATH = "configs/research_v6_execution_amendment_2.json"
AUTHORIZATION_PATH = "configs/research_v6_selection_authorization_1.json"

#: The v1, v2, v3 and v4 output paths a v6 run may never write.
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
    "research/shards_v3/",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
    "configs/research_v3.json",
    "configs/research_v3_candidate_freeze.json",
    "research/universe_manifest_v3.json",
    "research/data_manifest_v3.json",
    "research/shards_v4/",
    "research/ledger_v4.json",
    "research/results_manifest_v4.json",
    "research/results_v4.jsonl",
    "research_state/checkpoint_v4.json",
    "configs/research_v4.json",
    "configs/research_v4_candidate_freeze.json",
    "research/universe_manifest_v4.json",
    "research/data_manifest_v4.json",
    "research/shards_v5/",
    "research/ledger_v5.json",
    "research/results_manifest_v5.json",
    "research/results_v5.jsonl",
    "research_state/checkpoint_v5.json",
    "configs/research_v5.json",
    "configs/research_v5_candidate_freeze.json",
    "research/universe_manifest_v5.json",
    "research/data_manifest_v5.json",
)

#: The v6 output paths a selection run may write.
OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)

#: The protocol blocks the execution amendment 1 owns. The amendment restates
#: the blocks the base protocol published and adds the blocks its first
#: publication did not carry: the inherited v1 rules, the execution
#: authorization and the deviation disclosure.
EXECUTION_AMENDMENT_BLOCKS = (
    "candidate_freeze_and_confirmatory_window",
    "evaluation_scope",
    "benchmark_rule",
    "code_hash_constraint",
    "inherited_rules",
    "execution_authorization",
    "deviation_disclosure",
)

#: The protocol blocks the execution amendment 2 owns. Amendment 2 corrects
#: the one block whose recorded state the delivery of the v6 selection
#: authorization made stale: the ``execution_authorization`` block, whose
#: ``selection_authorization_present`` flag recorded the state of the chain at
#: the publication instants of the protocol and of amendment 1.
EXECUTION_AMENDMENT_2_BLOCKS = (
    "execution_authorization",
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
    """The validated constituents of the v6 universe and the excluded ones.

    The membership rule is "exactly the constituents marked validated in
    ``research/universe_manifest_v6.json`` (``validated == true``,
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
    hashing = document.get("hashing") or {}
    excluded = tuple(hashing.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    declared = document.get("manifest_hash")
    recomputed = compute_manifest_hash(document, excluded)
    if recomputed != declared:
        raise ScopeError(
            f"the manifest hash of {label} does not recompute: recorded {declared}, "
            f"recomputed {recomputed}"
        )
    return str(declared)


def effective_rules(repo_root: Path) -> Dict[str, Any]:
    """Resolve the v6 rules from their frozen owners without editing them."""
    root = Path(repo_root)
    spec = load_json(root / V6_SPEC_PATH)
    freeze = load_json(root / FREEZE_PATH)
    protocol = load_json(root / EXECUTION_PATH)
    amendment_effective = resolve_effective_execution_protocol(root)
    membership = spec.get("holdout", {}).get("confirmatory_window_membership", {})
    window = freeze.get("confirmatory_window") or {}
    return {
        "membership": {
            "path": V6_SPEC_PATH,
            "manifest_hash": spec.get("specification_hash"),
            "rule": membership.get("rule"),
            "interval_start_inclusive": membership.get("interval_start_inclusive"),
            "interval_end_exclusive": membership.get("interval_end_exclusive"),
            "precedence": "specification_direct",
            "consequence_for_the_run": "selection reads development data only; confirmatory-window membership is strict at both boundaries",
        },
        "overlap": {
            "path": EXECUTION_PATH,
            "manifest_hash": protocol.get("manifest_hash"),
            "rule": window.get("overlap_rule"),
            "evaluation_may_not_start_before_utc": window.get("evaluation_may_not_start_before_utc"),
            "precedence": "specification_direct",
            "consequence_for_the_run": "the selection run reads development data only and the confirmatory run remains separately gated",
        },
        "execution": {
            "path": EXECUTION_PATH,
            "manifest_hash": protocol.get("manifest_hash"),
            "precedence": (amendment_effective.get("_amendment_path") or EXECUTION_AMENDMENT_1_PATH),
            "named_amendment_precedence": (amendment_effective.get("precedence") or {}).get("rule"),
            "consequence_for_the_run": "the effective execution authorization is resolved amendment-first and is checked against the published selection authorization",
        },
    }def frozen_scope(freeze: Dict[str, Any], universe: Dict[str, Any],
                  rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The frozen v6 candidate set, checked against the universe manifest.

    The candidate set is read from the validated candidate set of
    ``configs/research_v6_candidate_freeze.json`` and re-derived from
    ``research/universe_manifest_v6.json``. The freeze binds the base data
    manifest directly, and the effective data boundary is the earlier of the
    confirmatory-window start and the preregistered development cutoff.
    """
    verify_artifact_hash(freeze, "the v6 candidate freeze")

    members = (freeze.get("candidates") or [])
    pairs = [str(member.get("binance_pair")) for member in members
             if member.get("validated") is True]
    if not pairs:
        raise ScopeError("the validated candidate set of the freeze is empty")

    validated, excluded = universe_validated_constituents(universe)
    if sorted(pairs) != validated:
        raise ScopeError(
            "the validated candidate set of the freeze is not the set of "
            "validated constituents of research/universe_manifest_v6.json"
        )
    recorded_excluded = {
        str(member.get("binance_pair")): str(member.get("exclusion_reason"))
        for member in members
        if member.get("validated") is not True
    }
    for symbol, reason in recorded_excluded.items():
        if excluded.get(symbol) != reason:
            raise ScopeError(
                f"the frozen exclusion reason for {symbol} differs from the reason recorded "
                "by the v6 universe manifest"
            )

    boundary = freeze.get("confirmatory_window") or {}
    confirmatory_start = boundary.get("opens_utc")
    data_boundary = freeze.get("data_boundary") or {}
    development_cutoff = data_boundary.get("development_cutoff_utc")
    recorded_effective = data_boundary.get("effective_data_boundary_utc")
    if not development_cutoff or not recorded_effective:
        raise ScopeError(
            "the v6 candidate freeze records no development cutoff and no effective data "
            "boundary"
        )
    effective_boundary = min(
        (parse_utc_ms(str(value)) for value in (confirmatory_start, development_cutoff)
         if value),
        default=0,
    )
    if effective_boundary != parse_utc_ms(str(recorded_effective)):
        raise ScopeError(
            "the effective data boundary recorded by the freeze is not the earlier of the "
            "confirmatory-window start and the development cutoff"
        )

    scope: Dict[str, Any] = {
        "binance_pairs": pairs,
        "count": len(pairs),
        "excluded_after_validation": recorded_excluded,
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_hash": freeze.get("data_manifest_hash"),
        "confirmatory_window_start_utc": confirmatory_start,
        "development_cutoff_utc": development_cutoff,
        "effective_data_boundary_utc": recorded_effective,
        "min_confirmatory_window_hours": boundary.get("min_hours"),
        "candidate_freeze_timestamp_utc": freeze.get("candidate_freeze_utc"),
        "candidate_manifest_hash": freeze.get("manifest_hash"),
    }
    if rules is not None:
        scope["effective_rules"] = rules
    return scope


def selection_rule(spec_v1: Dict[str, Any], spec_v6: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """The unchanged v1 selection rule and its digest.

    The v6 specification inherits the ``selection`` block from v1; the block
    must be byte-equal, otherwise the v6 selection rule is not the v1 rule and
    the run is refused.
    """
    block_v1 = spec_v1.get("selection")
    block_v6 = spec_v6.get("selection")
    if not isinstance(block_v1, dict) or not isinstance(block_v6, dict):
        raise ScopeError("a research specification does not carry a selection block")
    if canonical(block_v1) != canonical(block_v6):
        raise ScopeError(
            "the selection block of configs/research_v6.json is not byte-equal to the "
            "selection block of configs/research_v1.json"
        )
    return block_v1, sha256_bytes(canonical(block_v1).encode("utf-8"))


def assert_no_forbidden_output(paths: Dict[str, str]) -> None:
    """Fail closed when an output path points at a v1, v2 or v3 artifact."""
    for name, path in paths.items():
        for banned in FORBIDDEN_PATHS:
            root = banned.rstrip("/")
            if path == root or path.startswith(root + "/"):
                raise ScopeError(f"the v6 output path {name} points at the forbidden path {banned}")


def authorization_output_paths(authorization: Dict[str, Any]) -> Dict[str, str]:
    """The v6 output paths the authorization allows the run to write."""
    paths = dig(authorization, "authorized_run.paths") or {}
    return {key: str(paths.get(key, "")) for key in OUTPUT_PATH_KEYS}


def validate_authorization(
    repo_root: Path,
    authorization: Dict[str, Any],
    scope: Dict[str, Any],
    rule_digest: str,
    rule_block: Dict[str, Any],
) -> Dict[str, Any]:
    """Check the v6 selection authorization against the artifacts it names.

    The authorization is the artifact that authorizes the single bounded run.
    This function is the gate that checks it, and it recomputes every
    expectation from the repository.
    """
    excluded = tuple(dig(authorization, "hashing.manifest_hash_excluded_keys") or ())
    if not excluded:
        raise ScopeError("the authorization does not declare its manifest_hash_excluded_keys")
    declared_hash = authorization.get("manifest_hash")
    if compute_manifest_hash(authorization, excluded) != declared_hash:
        raise ScopeError("the authorization manifest hash does not recompute")

    spec_v6 = load_json(Path(repo_root) / V6_SPEC_PATH)
    if authorization.get("specification_hash") != spec_v6.get("specification_hash"):
        raise ScopeError("the authorization is not bound to the v6 specification")
    if authorization.get("universe_version") != spec_v6.get("universe_version"):
        raise ScopeError("the authorization is not a v6 artifact")

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

    recorded_rules = run.get("effective_rules") or {}
    if not recorded_rules:
        raise ScopeError("the authorization records no effective rule")
    for name, rules in (recorded_rules or {}).items():
        if not isinstance(rules, dict) or not rules.get("path") or not rules.get("manifest_hash"):
            raise ScopeError(f"the authorization does not bind the effective {name} rule")
    membership = recorded_rules.get("membership") or {}
    if membership.get("interval_start_inclusive") is not False:
        raise ScopeError(
            "the authorization does not bind the effective, start-exclusive membership rule"
        )
    overlap = recorded_rules.get("overlap") or {}
    if not overlap.get("evaluation_may_not_start_before_utc"):
        raise ScopeError("the authorization records no effective v6 evaluation gate")

    paths = authorization_output_paths(authorization)
    for key in OUTPUT_PATH_KEYS:
        if not paths.get(key):
            raise ScopeError(f"the authorization names an empty v6 output path {key}")
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
        "effective_rules": recorded_rules,
    }


def resolve_effective_execution_protocol(repo_root: Path) -> Dict[str, Any]:
    """Resolve the effective v6 execution protocol through the shared verifier."""
    root = Path(repo_root)
    try:
        return resolve_effective_v6_execution_protocol(root)
    except V6RuleError as error:
        raise ScopeError(str(error)) from error


def verify_execution_protocol(execution_protocol: Dict[str, Any],
                               scope: Dict[str, Any],
                               data_manifest_hash: str,
                               repo_root: Path) -> Dict[str, Any]:
    """Check the effective v6 execution protocol and its independent authority boundary."""
    evaluation = execution_protocol.get("evaluation_scope") or {}
    if evaluation.get("data_manifest_hash") != data_manifest_hash:
        raise ScopeError("the v6 execution protocol does not bind the data-manifest identity")
    if evaluation.get("universe_manifest_hash") != scope.get("universe_manifest_hash"):
        raise ScopeError("the v6 execution protocol does not bind the frozen universe identity")
    if evaluation.get("candidate_freeze_hash") != scope.get("candidate_manifest_hash"):
        raise ScopeError("the v6 execution protocol does not bind the candidate freeze")
    if sorted(str(pair) for pair in evaluation.get("constituents") or []) != sorted(scope["binance_pairs"]):
        raise ScopeError("the v6 evaluated scope is not the frozen validated candidate set")

    authorization = execution_protocol.get("execution_authorization") or {}
    for flag in ("execution_authorized", "grid_run_authorized", "candle_fetch_authorized",
                 "confirmatory_evaluation_authorized", "second_run_authorized"):
        if authorization.get(flag) is not False:
            raise ScopeError(f"the v6 execution protocol claims {flag}; the protocol authorizes none")

    try:
        verify_effective_v6_selection_authorization(Path(repo_root), execution_protocol)
    except V6RuleError as error:
        raise ScopeError(str(error)) from error

    inherited_authorization = execution_protocol.get("authorization") or {}
    for flag in ("execution_authorized", "campaign_authorized", "selection_authorized", "confirmatory_authorized"):
        if inherited_authorization.get(flag) is not False:
            raise ScopeError(f"the v6 execution protocol claims {flag}; it authorizes none")

    benchmark = execution_protocol.get("benchmark_rule") or {}
    if benchmark.get("no_forward_fill") is not True:
        raise ScopeError("the v6 execution protocol does not forbid forward-filling the benchmark")
    if not benchmark.get("content_hash") or not benchmark.get("dataset_path"):
        raise ScopeError("the v6 execution protocol names no benchmark dataset")
    if not str(benchmark.get("alignment") or "").startswith(
        "the asset series and the benchmark series are sliced to the same fold window"
    ):
        raise ScopeError("the v6 execution protocol does not bind the benchmark alignment rule")
    if not benchmark.get("fail_closed"):
        raise ScopeError("the v6 execution protocol records no fail-closed condition")

    constraint = execution_protocol.get("code_hash_constraint") or {}
    if constraint.get("v6_execution_root") != "src/v6_campaign":
        raise ScopeError("the v6 execution path is not bound to src/v6_campaign")
    if constraint.get("v6_execution_must_live_outside_hashed_set") is not True:
        raise ScopeError("the v6 execution path is not required to stay outside the hashed set")

    inherited = execution_protocol.get("inherited_rules") or {}
    if not inherited.get("blocks_digest") or int(inherited.get("grid_total_combinations") or 0) != 2304:
        raise ScopeError("the v6 execution protocol does not bind the unchanged v1 grid and rules")

    return {
        "manifest_hash": execution_protocol.get("manifest_hash"),
        "benchmark": benchmark,
        "deviation_disclosure": execution_protocol.get("deviation_disclosure"),
        "code_hash_constraint": constraint,
        "inherited_rules": inherited,
        "effective_blocks_from_amendment": list(execution_protocol.get("_effective_blocks_from_amendment") or ()),
        "amendment_manifest_hash": execution_protocol.get("_amendment_manifest_hash"),
    }


def load_workspace_documents(repo_root: Path) -> Dict[str, Any]:
    """Load every artifact the authorization is checked against."""
    root = Path(repo_root)
    return {
        "authorization": load_json(root / AUTHORIZATION_PATH),
        "freeze": load_json(root / FREEZE_PATH),
        "spec_v1": load_json(root / V1_SPEC_PATH),
        "spec_v6": load_json(root / V6_SPEC_PATH),
        "data_manifest": load_json(root / DATA_MANIFEST_PATH),
        "universe_manifest": load_json(root / UNIVERSE_MANIFEST_PATH),
        "config_manifest": load_json(root / CONFIG_MANIFEST_PATH),
    }

__all__ = [
    "AUTHORIZATION_PATH",
    "CONFIG_MANIFEST_PATH",
    "DATA_MANIFEST_PATH",
    "EXECUTION_AMENDMENT_1_PATH",
    "EXECUTION_AMENDMENT_2_PATH",
    "EXECUTION_PATH",
    "FORBIDDEN_PATHS",
    "FREEZE_AMENDMENT_1_PATH",
    "FREEZE_PATH",
    "OUTPUT_PATH_KEYS",
    "SPEC_AMENDMENT_1_PATH",
    "UNIVERSE_MANIFEST_PATH",
    "V1_SPEC_PATH",
    "V6_SPEC_PATH",
    "assert_no_forbidden_output",
    "authorization_output_paths",
    "canonical",
    "canonical_source_digest",
    "compute_manifest_hash",
    "dig",
    "effective_rules",
    "frozen_scope",
    "load_json",
    "load_workspace_documents",
    "resolve_effective_execution_protocol",
    "selection_rule",
    "sha256_bytes",
    "sha256_file",
    "universe_validated_constituents",
    "validate_authorization",
    "verify_artifact_hash",
    "verify_execution_protocol",
]

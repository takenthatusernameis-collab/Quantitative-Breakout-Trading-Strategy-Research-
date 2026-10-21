"""Frozen scope, selection rule and authorization validation for the v5 path.

This module resolves *what* a v5 selection run may touch:

* the candidate set, read from the validated candidate set of
  ``configs/research_v5_candidate_freeze.json`` and re-derived from
  ``research/universe_manifest_v5.json``;
* the data boundary, read from the frozen candidate set
  (``configs/research_v5_candidate_freeze.json``);
* the selection rule, read from the ``selection`` block of
  ``configs/research_v1.json`` and required to be byte-equal to the block that
  ``configs/research_v5.json`` inherits;
* the authorization, ``configs/research_v5_selection_authorization_1.json``,
  which must agree with all of them.

Every check recomputes its expectation from the bytes on disk; nothing is
compared against a literal copied out of the artifact under test.

**The effective rules.** v5 published three amendments, and each of them owns
one rule for the effective behaviour. The amendment wins over the frozen block
it corrects; the frozen block stays on disk, unchanged and visible:

* ``configs/research_v5_specification_amendment_1.json`` owns the
  confirmatory-window **membership** rule (a candle that closes exactly at a
  window's start is development data);
* ``configs/research_v5_candidate_freeze_amendment_1.json`` owns the
  confirmatory-window **overlap** rule and the effective v5 evaluation gate;
* ``configs/research_v5_execution_amendment_1.json`` owns the blocks of the
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

V1_SPEC_PATH = "configs/research_v1.json"
V5_SPEC_PATH = "configs/research_v5.json"
SPEC_AMENDMENT_1_PATH = "configs/research_v5_specification_amendment_1.json"
FREEZE_PATH = "configs/research_v5_candidate_freeze.json"
FREEZE_AMENDMENT_1_PATH = "configs/research_v5_candidate_freeze_amendment_1.json"
DATA_MANIFEST_PATH = "research/data_manifest_v5.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest_v5.json"
CONFIG_MANIFEST_PATH = "research/config_manifest.json"
EXECUTION_PATH = "configs/research_v5_execution.json"
EXECUTION_AMENDMENT_1_PATH = "configs/research_v5_execution_amendment_1.json"
EXECUTION_AMENDMENT_2_PATH = "configs/research_v5_execution_amendment_2.json"
AUTHORIZATION_PATH = "configs/research_v5_selection_authorization_1.json"

#: The v1, v2, v3 and v4 output paths a v5 run may never write.
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
)

#: The v5 output paths a selection run may write.
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
#: the one block whose recorded state the delivery of the v5 selection
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
    """The validated constituents of the v5 universe and the excluded ones.

    The membership rule is "exactly the constituents marked validated in
    ``research/universe_manifest_v5.json`` (``validated == true``,
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
    """The effective rules of the v5 chain, read amendment first.

    Each published amendment owns one rule for the effective behaviour:

    * the **membership** rule of the confirmatory window (a candle that closes
      exactly at a window's start is development data) belongs to the
      specification amendment;
    * the **overlap** rule and the effective evaluation gate belong to the
      candidate-freeze amendment;
    * the blocks the execution protocol's first publication did not carry
      belong to the execution amendment.

    The amendments are hash-bound; an amendment that does not recompute its own
    hash, or that names a frozen artifact other than the one it claims to
    amend, is refused.

    The **execution** rule names the execution amendment 1, which owns the
    inherited v1 rules and the blocks the protocol's first publication lacked.
    The effective *protocol* is resolved separately, in
    :func:`resolve_effective_execution_protocol`, which applies the newest
    published execution amendment to the blocks it restates.
    """
    root = Path(repo_root)

    spec_amendment = load_json(root / SPEC_AMENDMENT_1_PATH)
    verify_artifact_hash(spec_amendment, "the v5 specification amendment 1")
    superseded = spec_amendment.get("supersedes") or {}
    if superseded.get("specification_path") != V5_SPEC_PATH:
        raise ScopeError(
            "the v5 specification amendment 1 does not name the v5 specification"
        )
    spec = load_json(root / V5_SPEC_PATH)
    if superseded.get("specification_hash") != spec.get("specification_hash"):
        raise ScopeError(
            "the v5 specification amendment 1 is not bound to the current v5 specification"
        )

    freeze_amendment = load_json(root / FREEZE_AMENDMENT_1_PATH)
    verify_artifact_hash(freeze_amendment, "the v5 candidate freeze amendment 1")
    superseded_freeze = freeze_amendment.get("supersedes") or {}
    if superseded_freeze.get("artifact_path") != FREEZE_PATH:
        raise ScopeError(
            "the v5 candidate freeze amendment 1 does not name the v5 candidate freeze"
        )
    freeze = load_json(root / FREEZE_PATH)
    if superseded_freeze.get("artifact_manifest_hash") != freeze.get("manifest_hash"):
        raise ScopeError(
            "the v5 candidate freeze amendment 1 is not bound to the current candidate freeze"
        )
    if superseded_freeze.get("artifact_sha256") != sha256_file(root / FREEZE_PATH):
        raise ScopeError(
            "the v5 candidate freeze amendment 1 records a stale digest of the candidate freeze"
        )

    execution_amendment = load_json(root / EXECUTION_AMENDMENT_1_PATH)
    verify_artifact_hash(execution_amendment, "the v5 execution amendment 1")
    if (execution_amendment.get("amends") or {}).get("file") != EXECUTION_PATH:
        raise ScopeError(
            "the v5 execution amendment 1 does not name the v5 execution protocol"
        )

    membership = spec_amendment.get("corrected_rule") or {}
    if membership.get("interval_start_inclusive") is not False:
        raise ScopeError(
            "the effective confirmatory-window membership rule is not start-exclusive; a "
            "candle that closes exactly at a window's start is development data"
        )
    if membership.get("interval_end_exclusive") is not True:
        raise ScopeError(
            "the effective confirmatory-window membership rule is not end-exclusive"
        )

    overlap = freeze_amendment.get("corrected_rule") or {}
    if not overlap.get("evaluation_may_not_start_before_utc"):
        raise ScopeError(
            "the v5 candidate freeze amendment 1 records no effective evaluation gate"
        )
    if overlap.get("no_shared_asset") is not True:
        raise ScopeError(
            "the effective overlap rule does not record that the evaluations share no asset"
        )

    return {
        "membership": {
            "path": SPEC_AMENDMENT_1_PATH,
            "manifest_hash": spec_amendment.get("manifest_hash"),
            "rule": membership.get("rule"),
            "interval_start_inclusive": membership.get("interval_start_inclusive"),
            "interval_end_exclusive": membership.get("interval_end_exclusive"),
            "precedence": (spec_amendment.get("effective_rule") or {}).get("precedence"),
        },
        "overlap": {
            "path": FREEZE_AMENDMENT_1_PATH,
            "manifest_hash": freeze_amendment.get("manifest_hash"),
            "rule": overlap.get("overlap_rule"),
            "evaluation_may_not_start_before_utc": overlap.get(
                "evaluation_may_not_start_before_utc"
            ),
            "precedence": (freeze_amendment.get("effective_rule") or {}).get("precedence"),
        },
        "execution": {
            "path": EXECUTION_AMENDMENT_1_PATH,
            "manifest_hash": execution_amendment.get("manifest_hash"),
            "precedence": (execution_amendment.get("precedence") or {}).get("rule"),
        },
    }


def frozen_scope(freeze: Dict[str, Any], universe: Dict[str, Any],
                  rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The frozen v5 candidate set, checked against the universe manifest.

    The candidate set is read from the validated candidate set of
    ``configs/research_v5_candidate_freeze.json`` and re-derived from
    ``research/universe_manifest_v5.json``. The freeze binds the base data
    manifest directly, and the effective data boundary is the earlier of the
    confirmatory-window start and the preregistered development cutoff.
    """
    verify_artifact_hash(freeze, "the v5 candidate freeze")

    members = (freeze.get("candidates") or [])
    pairs = [str(member.get("binance_pair")) for member in members
             if member.get("validated") is True]
    if not pairs:
        raise ScopeError("the validated candidate set of the freeze is empty")

    validated, excluded = universe_validated_constituents(universe)
    if sorted(pairs) != validated:
        raise ScopeError(
            "the validated candidate set of the freeze is not the set of "
            "validated constituents of research/universe_manifest_v5.json"
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
                "by the v5 universe manifest"
            )

    boundary = freeze.get("confirmatory_window") or {}
    confirmatory_start = boundary.get("opens_utc")
    data_boundary = freeze.get("data_boundary") or {}
    development_cutoff = data_boundary.get("development_cutoff_utc")
    recorded_effective = data_boundary.get("effective_data_boundary_utc")
    if not development_cutoff or not recorded_effective:
        raise ScopeError(
            "the v5 candidate freeze records no development cutoff and no effective data "
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


def selection_rule(spec_v1: Dict[str, Any], spec_v5: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """The unchanged v1 selection rule and its digest.

    The v5 specification inherits the ``selection`` block from v1; the block
    must be byte-equal, otherwise the v5 selection rule is not the v1 rule and
    the run is refused.
    """
    block_v1 = spec_v1.get("selection")
    block_v5 = spec_v5.get("selection")
    if not isinstance(block_v1, dict) or not isinstance(block_v5, dict):
        raise ScopeError("a research specification does not carry a selection block")
    if canonical(block_v1) != canonical(block_v5):
        raise ScopeError(
            "the selection block of configs/research_v5.json is not byte-equal to the "
            "selection block of configs/research_v1.json"
        )
    return block_v1, sha256_bytes(canonical(block_v1).encode("utf-8"))


def assert_no_forbidden_output(paths: Dict[str, str]) -> None:
    """Fail closed when an output path points at a v1, v2 or v3 artifact."""
    for name, path in paths.items():
        for banned in FORBIDDEN_PATHS:
            root = banned.rstrip("/")
            if path == root or path.startswith(root + "/"):
                raise ScopeError(f"the v5 output path {name} points at the forbidden path {banned}")


def authorization_output_paths(authorization: Dict[str, Any]) -> Dict[str, str]:
    """The v5 output paths the authorization allows the run to write."""
    paths = dig(authorization, "authorized_run.paths") or {}
    return {key: str(paths.get(key, "")) for key in OUTPUT_PATH_KEYS}


def validate_authorization(
    repo_root: Path,
    authorization: Dict[str, Any],
    scope: Dict[str, Any],
    rule_digest: str,
    rule_block: Dict[str, Any],
) -> Dict[str, Any]:
    """Check the v5 selection authorization against the artifacts it names.

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

    spec_v5 = load_json(Path(repo_root) / V5_SPEC_PATH)
    if authorization.get("specification_hash") != spec_v5.get("specification_hash"):
        raise ScopeError("the authorization is not bound to the v5 specification")
    if authorization.get("universe_version") != spec_v5.get("universe_version"):
        raise ScopeError("the authorization is not a v5 artifact")

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
        raise ScopeError("the authorization records no effective v5 evaluation gate")

    paths = authorization_output_paths(authorization)
    for key in OUTPUT_PATH_KEYS:
        if not paths.get(key):
            raise ScopeError(f"the authorization names an empty v5 output path {key}")
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
    """The effective v5 execution protocol: the amendments first, the protocol second.

    ``configs/research_v5_execution.json`` is hash-bound and is not edited in
    place. Its first publication did not carry the inherited v1 rules, the
    benchmark's recomputed identity, the execution-authorization block, the
    deviation disclosure or the supersedes chain, so
    ``configs/research_v5_execution_amendment_1.json`` records those blocks and
    wins over the protocol for the blocks it restates.

    ``configs/research_v5_execution_amendment_2.json`` then corrected the one
    block whose recorded state the delivery of the v5 selection authorization
    made stale: the ``execution_authorization`` block, whose
    ``selection_authorization_present`` flag recorded the state of the chain at
    the publication instants of the protocol and of amendment 1. The effective
    block is amendment 2's, and it names the published selection authorization
    by its recomputed identity.

    Every artifact stays on disk, unchanged and visible. When amendment 2 is
    absent the effective block is amendment 1's, which records that no
    selection authorization is present: the run gate then refuses, so the
    absence fails closed.
    """
    root = Path(repo_root)
    protocol = load_json(root / EXECUTION_PATH)
    verify_artifact_hash(protocol, "the v5 execution protocol")

    amendment = load_json(root / EXECUTION_AMENDMENT_1_PATH)
    verify_artifact_hash(amendment, "the v5 execution amendment 1")
    amends = amendment.get("amends") or {}
    if amends.get("file") != EXECUTION_PATH:
        raise ScopeError(
            "the v5 execution amendment 1 does not name the v5 execution protocol"
        )
    if amends.get("manifest_hash") != protocol.get("manifest_hash"):
        raise ScopeError(
            "the v5 execution amendment 1 is not bound to the current execution protocol"
        )
    if amends.get("sha256") != sha256_file(root / EXECUTION_PATH):
        raise ScopeError(
            "the v5 execution amendment 1 records a stale digest of the execution protocol"
        )

    superseded = tuple((amendment.get("precedence") or {}).get("superseded") or ())
    if not superseded:
        raise ScopeError(
            "the v5 execution amendment 1 names no superseded block of the protocol"
        )
    effective = json.loads(json.dumps(protocol))
    for block in superseded:
        if block not in amendment:
            raise ScopeError(
                f"the v5 execution amendment 1 does not restate the block {block!r} it claims "
                "to supersede"
            )
        effective[block] = amendment[block]
    for block in EXECUTION_AMENDMENT_BLOCKS:
        if block in amendment:
            effective[block] = amendment[block]
    effective["_effective_blocks_from_amendment"] = list(superseded)
    effective["_amendment_manifest_hash"] = amendment.get("manifest_hash")

    amendment_2_path = root / EXECUTION_AMENDMENT_2_PATH
    if amendment_2_path.exists():
        amendment_2 = load_json(amendment_2_path)
        verify_artifact_hash(amendment_2, "the v5 execution amendment 2")
        amends_2 = amendment_2.get("amends") or {}
        if amends_2.get("file") != EXECUTION_PATH:
            raise ScopeError(
                "the v5 execution amendment 2 does not name the v5 execution protocol"
            )
        if amends_2.get("manifest_hash") != protocol.get("manifest_hash"):
            raise ScopeError(
                "the v5 execution amendment 2 is not bound to the current execution protocol"
            )
        if amends_2.get("sha256") != sha256_file(root / EXECUTION_PATH):
            raise ScopeError(
                "the v5 execution amendment 2 records a stale digest of the execution protocol"
            )
        supersedes_1 = amendment_2.get("supersedes_in_amendment_1") or {}
        if supersedes_1.get("file") != EXECUTION_AMENDMENT_1_PATH:
            raise ScopeError(
                "the v5 execution amendment 2 does not name the v5 execution amendment 1"
            )
        if supersedes_1.get("manifest_hash") != amendment.get("manifest_hash"):
            raise ScopeError(
                "the v5 execution amendment 2 is not bound to the current execution amendment 1"
            )
        if supersedes_1.get("sha256") != sha256_file(root / EXECUTION_AMENDMENT_1_PATH):
            raise ScopeError(
                "the v5 execution amendment 2 records a stale digest of the execution "
                "amendment 1"
            )
        superseded_2 = tuple((amendment_2.get("precedence") or {}).get("superseded") or ())
        if not superseded_2:
            raise ScopeError(
                "the v5 execution amendment 2 names no superseded block of the amendment 1"
            )
        for block in superseded_2:
            if block not in amendment_2:
                raise ScopeError(
                    f"the v5 execution amendment 2 does not restate the block {block!r} it "
                    "claims to supersede"
                )
            effective[block] = amendment_2[block]
        for block in EXECUTION_AMENDMENT_2_BLOCKS:
            if block in amendment_2:
                effective[block] = amendment_2[block]
        effective["_effective_blocks_from_amendment_2"] = list(superseded_2)
        effective["_amendment_2_manifest_hash"] = amendment_2.get("manifest_hash")
    return effective



def verify_execution_protocol(execution_protocol: Dict[str, Any],
                               scope: Dict[str, Any],
                               data_manifest_hash: str,
                               repo_root: Path) -> Dict[str, Any]:
    """Check the effective v5 execution protocol against the scope and the identity.

    The protocol records the benchmark rule and the data-manifest identity of
    the evaluation scope. It authorizes nothing: a run still needs the separate
    selection authorization.

    The ``execution_authorization`` block of the **effective** protocol carries
    one statement about the world rather than about the protocol's own
    authority: ``selection_authorization_present``. The frozen protocol and the
    execution amendment 1 recorded it as ``false``, which was true at their
    publication instants and stale once the v5 selection authorization was
    published. The effective block is the one the execution amendment 2
    records, and this function checks it against the repository: the recorded
    selection authorization must exist and must be the artifact whose identity
    the block names.
    """
    evaluation = execution_protocol.get("evaluation_scope") or {}
    if evaluation.get("data_manifest_hash") != data_manifest_hash:
        raise ScopeError(
            "the v5 execution protocol does not bind the data-manifest identity"
        )
    if sorted(str(pair) for pair in evaluation.get("constituents") or []) != sorted(
        scope["binance_pairs"]
    ):
        raise ScopeError(
            "the evaluated scope of the v5 execution protocol is not the frozen candidate set"
        )

    authorization = execution_protocol.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        raise ScopeError(
            "the v5 execution protocol claims an execution authorization; it authorizes none"
        )
    if authorization.get("selection_authorization_present") is not True:
        raise ScopeError(
            "the effective v5 execution protocol does not record the published v5 selection "
            "authorization; the single bounded run is gated on that artifact"
        )
    recorded_path = str(authorization.get("selection_authorization_path") or "")
    if recorded_path != AUTHORIZATION_PATH:
        raise ScopeError(
            "the effective v5 execution protocol names another selection authorization"
        )
    recorded_hash = str(authorization.get("selection_authorization_manifest_hash") or "")
    recorded_sha256 = str(authorization.get("selection_authorization_sha256") or "")
    authorization_path = Path(repo_root) / recorded_path
    if not authorization_path.exists():
        raise ScopeError(
            "the v5 selection authorization named by the effective v5 execution protocol "
            "does not exist"
        )
    published = load_json(authorization_path)
    verify_artifact_hash(published, "the v5 selection authorization")
    if published.get("manifest_hash") != recorded_hash:
        raise ScopeError(
            "the v5 selection authorization does not match the identity the effective v5 "
            "execution protocol records"
        )
    if recorded_sha256 and sha256_file(authorization_path) != recorded_sha256:
        raise ScopeError(
            "the v5 selection authorization does not match the file digest the effective v5 "
            "execution protocol records"
        )
    if authorization.get("candle_fetch_authorized") is not False:
        raise ScopeError(
            "the v5 execution protocol claims a candle-fetch authorization; it authorizes none"
        )
    if authorization.get("confirmatory_evaluation_authorized") is not False:
        raise ScopeError(
            "the v5 execution protocol claims a confirmatory evaluation; it authorizes none"
        )
    if authorization.get("grid_run_authorized") is not False:
        raise ScopeError("the v5 execution protocol claims a grid run; it authorizes none")
    if authorization.get("second_run_authorized") is not False:
        raise ScopeError("the v5 execution protocol claims a second run; it authorizes none")

    inherited_authorization = execution_protocol.get("authorization") or {}
    for flag in (
        "execution_authorized",
        "campaign_authorized",
        "selection_authorized",
        "confirmatory_authorized",
    ):
        if inherited_authorization.get(flag) is not False:
            raise ScopeError(
                f"the v5 execution protocol claims {flag}; it authorizes none"
            )

    benchmark = execution_protocol.get("benchmark_rule") or {}
    if benchmark.get("no_forward_fill") is not True:
        raise ScopeError("the v5 execution protocol does not forbid forward-filling the benchmark")
    if not benchmark.get("content_hash") or not benchmark.get("dataset_path"):
        raise ScopeError("the v5 execution protocol names no benchmark dataset")
    if not str(benchmark.get("alignment") or "").startswith(
        "the asset series and the benchmark series are sliced to the same fold window"
    ):
        raise ScopeError("the v5 execution protocol does not bind the benchmark alignment rule")
    if not benchmark.get("fail_closed"):
        raise ScopeError("the v5 execution protocol records no fail-closed condition")

    constraint = execution_protocol.get("code_hash_constraint") or {}
    if constraint.get("v5_execution_root") != "src/v5_campaign":
        raise ScopeError(
            "the v5 execution protocol does not place the v5 execution path outside the "
            "hashed set"
        )
    if constraint.get("v5_execution_must_live_outside_hashed_set") is not True:
        raise ScopeError(
            "the v5 execution protocol does not require the v5 execution path to live "
            "outside the hashed set"
        )

    inherited = execution_protocol.get("inherited_rules") or {}
    if not inherited.get("blocks_digest"):
        raise ScopeError("the v5 execution protocol binds no inherited v1 rule block")
    if int(inherited.get("grid_total_combinations") or 0) <= 0:
        raise ScopeError("the v5 execution protocol records no inherited grid size")

    return {
        "manifest_hash": execution_protocol.get("manifest_hash"),
        "benchmark": benchmark,
        "deviation_disclosure": execution_protocol.get("deviation_disclosure"),
        "code_hash_constraint": constraint,
        "inherited_rules": inherited,
        "effective_blocks_from_amendment": list(
            execution_protocol.get("_effective_blocks_from_amendment") or ()
        ),
        "amendment_manifest_hash": execution_protocol.get("_amendment_manifest_hash"),
    }


def load_workspace_documents(repo_root: Path) -> Dict[str, Any]:
    """Load every artifact the authorization is checked against."""
    root = Path(repo_root)
    return {
        "authorization": load_json(root / AUTHORIZATION_PATH),
        "freeze": load_json(root / FREEZE_PATH),
        "spec_v1": load_json(root / V1_SPEC_PATH),
        "spec_v5": load_json(root / V5_SPEC_PATH),
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
    "V5_SPEC_PATH",
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

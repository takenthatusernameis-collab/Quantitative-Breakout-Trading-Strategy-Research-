#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v5 selection authorization 1.

``configs/research_v5_selection_authorization_1.json`` authorizes exactly one
bounded v5 selection grid run over the frozen v5 candidate set, with the
effective rules of the v5 chain and the v5-cutoff-bounded benchmark bound into
it. The verifier never writes to the repository, never contacts a provider,
never reads a candle and never runs a grid. It checks:

1. the manifest hash recomputes from the canonical content of the document with
   the hash key removed;
2. the authorized scope is exactly the frozen candidate set, and the frozen set
   is the set of validated constituents of the v5 universe manifest;
3. the bounds are the bounds of the frozen scope and of the inherited grid, and
   the planned run fits inside them;
4. the data boundary is the effective development boundary of the freeze, the
   convention is the inclusive one, and no v1 holdout and no v2, v3 or v4
   confirmatory window may be read;
5. the effective rules are the published amendments': the start-exclusive
   membership rule, the overlap rule and the effective evaluation gate, and the
   effective execution protocol;
6. the selection rule is the unchanged v1 rule, and the v5 specification
   inherits it byte-equal;
7. the code identity recomputes from the source tree under the canonical
   digest rule, and the authorized value of record is still the authorized v1
   code hash;
8. the output paths are the v5 paths of the execution path and none of them is
   a v1, v2, v3 or v4 path;
9. the execution path exists, lives outside the hashed source set and holds
   exactly the recorded modules;
10. the authorization authorizes one run and nothing else;
11. the benchmark rule is bound: the dataset, its recomputed content hash, the
    alignment rule, the fail-closed list and the "no configuration is dropped"
    rule, and the data-manifest identity;
12. the execution path accepts this authorization and resolves a run plan from
    the repository without executing anything;
13. the v1 anchors are byte-identical, and no v5 row appears in the v1 result
    stream.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

AUTHORIZATION_RELATIVE = "configs/research_v5_selection_authorization_1.json"
FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
FREEZE_AMENDMENT_RELATIVE = "configs/research_v5_candidate_freeze_amendment_1.json"
SPEC_AMENDMENT_RELATIVE = "configs/research_v5_specification_amendment_1.json"
EXECUTION_RELATIVE = "configs/research_v5_execution.json"
EXECUTION_AMENDMENT_RELATIVE = "configs/research_v5_execution_amendment_1.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v5.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v5.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v5_campaign"

OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)

#: The alignment rule the execution path requires the authorization to bind.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called"
)

#: The v4 chain's benchmark dataset, which the v5 chain may not reuse: 13 of its
#: candles close inside the open v2 confirmatory window.
V4_BENCHMARK_DATASET = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

#: Phrasings that state the development-data boundary exclusively. A candle
#: that closes exactly at the boundary is development data -- it contains no
#: instant inside an open confirmatory window -- and the delivered v5 datasets
#: and the v2, v3 and v4 freezes all use that inclusive convention.
EXCLUSIVE_BOUNDARY_MARKERS = (
    "closes at or after",
    "at or after the cutoff",
    "at or after that instant",
)

#: Phrasings that state the boundary inclusively.
INCLUSIVE_BOUNDARY_MARKERS = (
    "at or before",
    "closes exactly at",
    "closes after",
    "after that instant",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
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
    """The portable identity of the ``*.py`` tree under ``root``.

    This is the ``canonical_source_digest_v1`` rule of BRAIN-009: a sha256
    over the POSIX relative path and the content digest of every ``*.py`` file
    under the root, in ascending path order.
    """
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def run_code_identity(hashed_set: str, execution_path: str) -> str:
    """The composite, portable identity of one v5 run."""
    payload = {
        "algorithm": "canonical_source_digest_v1",
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
    }
    return sha256_bytes(canonical(payload).encode("utf-8"))


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    repo_root = Path(repo_root)

    required = [
        repo_root / AUTHORIZATION_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / FREEZE_AMENDMENT_RELATIVE,
        repo_root / SPEC_AMENDMENT_RELATIVE,
        repo_root / EXECUTION_RELATIVE,
        repo_root / EXECUTION_AMENDMENT_RELATIVE,
        repo_root / UNIVERSE_RELATIVE,
        repo_root / DATA_MANIFEST_RELATIVE,
        repo_root / SPEC_V1_RELATIVE,
        repo_root / SPEC_V5_RELATIVE,
        repo_root / CONFIG_MANIFEST_RELATIVE,
        repo_root / CAMPAIGN_AUTHORIZATION_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    authorization = _load(repo_root / AUTHORIZATION_RELATIVE)
    freeze = _load(repo_root / FREEZE_RELATIVE)
    freeze_amendment = _load(repo_root / FREEZE_AMENDMENT_RELATIVE)
    spec_amendment = _load(repo_root / SPEC_AMENDMENT_RELATIVE)
    execution = _load(repo_root / EXECUTION_RELATIVE)
    execution_amendment = _load(repo_root / EXECUTION_AMENDMENT_RELATIVE)
    universe = _load(repo_root / UNIVERSE_RELATIVE)
    data_manifest = _load(repo_root / DATA_MANIFEST_RELATIVE)
    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    spec_v5 = _load(repo_root / SPEC_V5_RELATIVE)
    config_manifest = _load(repo_root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(repo_root / CAMPAIGN_AUTHORIZATION_RELATIVE)

    run = authorization.get("authorized_run") or {}

    # 1. The authorization is self-hashing.
    excluded = tuple(authorization.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the authorization does not declare its manifest_hash_excluded_keys")
    declared_hash = authorization.get("manifest_hash")
    recomputed_hash = compute_manifest_hash(authorization, excluded)
    if declared_hash != recomputed_hash:
        failures.append(
            f"manifest_hash mismatch: declared {declared_hash}, recomputed {recomputed_hash}"
        )
    if authorization.get("authorization_status") != (
        "PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN"
    ):
        failures.append("the authorization status does not record a single bounded run")

    # 2. The authorized scope is the frozen candidate set.
    from v5_campaign.scope import effective_rules, frozen_scope, selection_rule

    try:
        rules = effective_rules(repo_root)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the effective v5 rules do not resolve: {exc}")
        rules = {}
    try:
        scope = frozen_scope(freeze, universe, rules)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the frozen v5 scope does not resolve: {exc}")
        scope = {}
    pairs = list(scope.get("binance_pairs") or [])
    recorded_scope = run.get("scope") or {}
    if list(recorded_scope.get("binance_pairs") or []) != pairs:
        failures.append("the authorized candidate set is not the frozen candidate set")
    if recorded_scope.get("count") != len(pairs):
        failures.append("the authorized candidate count differs from the frozen count")
    if recorded_scope.get("bound_to_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("the authorization is not bound to the frozen candidate manifest")
    if recorded_scope.get("bound_to_universe_hash") != universe.get("manifest_hash"):
        failures.append("the authorization is not bound to the v5 universe manifest")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(pairs) != validated:
        failures.append("the frozen candidate set is not the validated v5 universe")
    if recorded_scope.get("widening_by_reranking_forbidden") is not True:
        failures.append("the authorization does not forbid widening the candidate set")
    if recorded_scope.get("excluded_assets_stay_excluded") is not True:
        failures.append("the authorization does not keep the excluded assets excluded")
    excluded_after = [m for m in (freeze.get("candidates") or []) if m.get("validated") is not True]
    for member in excluded_after:
        symbol = str(member.get("binance_pair"))
        if (recorded_scope.get("excluded_after_validation") or {}).get(symbol) != member.get(
            "exclusion_reason"
        ):
            failures.append(f"the exclusion reason of {symbol} is not carried by the authorization")
    if recorded_scope.get("benchmark_is_not_a_candidate") is not True:
        failures.append("the authorization does not record that the benchmark is not a candidate")

    # 3. The bounds are the bounds of the frozen scope and of the inherited grid.
    config_count = len(config_manifest.get("configurations") or [])
    fold_count = len(spec_v1["folds"]["window_fractions"])
    cost_count = len(spec_v1["costs"]["scenarios"])
    bounds = run.get("bounds") or {}
    expected_config_units = len(pairs) * config_count
    if bounds.get("max_assets") != len(pairs):
        failures.append("the authorized asset bound is not the frozen candidate count")
    if bounds.get("max_configs_per_asset") != config_count:
        failures.append("the authorized grid size is not the inherited configuration count")
    if bounds.get("max_total_config_units") != expected_config_units:
        failures.append("the authorized configuration-unit bound is not the planned grid size")
    if bounds.get("attempts") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    retries = int(bounds.get("max_retries_on_technical_failure") or 0)
    if retries < 1 or retries > 3:
        failures.append("the authorized number of technical retries is out of range")
    if bounds.get("planned_config_units") != expected_config_units:
        failures.append("the recorded planned configuration units do not recompute")
    if bounds.get("planned_execution_units") != expected_config_units * fold_count * cost_count:
        failures.append("the recorded planned execution units do not recompute")
    if int(bounds.get("planned_config_units") or 0) > int(
        bounds.get("max_total_config_units") or 0
    ):
        failures.append("the planned run exceeds the authorized configuration-unit bound")

    # 4. The data boundary is the effective development boundary of the freeze.
    boundary = run.get("data_boundary") or {}
    window_start = dig(freeze, "confirmatory_window.opens_utc")
    development_cutoff = dig(freeze, "data_boundary.development_cutoff_utc")
    recorded_effective = dig(freeze, "data_boundary.effective_data_boundary_utc")
    if not development_cutoff or not recorded_effective:
        failures.append("the frozen candidate set records no development cutoff")
    else:
        if dig(spec_v5, "holdout.development_cutoff_utc") != development_cutoff:
            failures.append(
                "the development cutoff of the freeze is not the cutoff the v5 specification "
                "preregisters"
            )
        expected_effective = min(value for value in (window_start, development_cutoff) if value)
        if recorded_effective != expected_effective:
            failures.append(
                "the effective data boundary of the freeze is not the earlier of the "
                "confirmatory-window start and the development cutoff"
            )
        if boundary.get("candles_before_utc") != recorded_effective:
            failures.append("the authorized data boundary is not the effective development boundary")
        if boundary.get("development_cutoff_utc") != development_cutoff:
            failures.append("the authorization does not record the development cutoff")
        if boundary.get("v5_confirmatory_window_start_utc") != window_start:
            failures.append("the authorization does not record the v5 confirmatory-window start")
        if str(boundary.get("candles_before_utc")) > str(development_cutoff):
            failures.append(
                "the authorized data boundary is after the development cutoff, so the run "
                "could read a candle inside the open v2 confirmatory window"
            )
    for flag in (
        "development_data_only",
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v2_confirmatory_window_never_reused",
        "v3_confirmatory_window_never_reused",
        "v4_confirmatory_window_never_reused",
        "holdout_exposed_count_stays_zero_during_selection",
        "holdout_position_fold_never_evaluated_during_selection",
    ):
        if boundary.get(flag) is not True:
            failures.append(f"the data boundary does not record {flag}")
    if boundary.get("provider_requests") != 0:
        failures.append("the authorization does not record that the run makes no provider request")
    cutoff_ms = 0
    if boundary.get("candles_before_utc"):
        cutoff_ms = _parse_utc_ms(str(boundary["candles_before_utc"]))
    for pair, entry in (data_manifest.get("assets") or {}).items():
        if entry.get("validated") is not True:
            continue
        last = entry.get("last_candle_timestamp")
        if last is None or not cutoff_ms:
            continue
        if int(last) + 3600000 > cutoff_ms:
            failures.append(
                f"the dataset of {pair} closes a candle after the authorized data boundary"
            )
        if int(last) + 3600000 != cutoff_ms:
            failures.append(
                f"the dataset of {pair} does not end with the candle that closes exactly at the "
                "authorized data boundary, so the data does not implement the boundary "
                "convention the artifacts state"
            )

    # 4b. Every artifact that states the development-data boundary states it in
    #     the same, inclusive convention.
    rule_texts = [
        ("the candidate freeze", dig(freeze, "data_boundary.development_data_rule")),
        ("the candidate freeze", dig(freeze, "data_boundary.development_cutoff_rule")),
        ("the data manifest", dig(data_manifest, "confirmatory_window.note")),
        ("the selection authorization", boundary.get("candles_before_utc_rule")),
    ]
    for label, text in rule_texts:
        if not isinstance(text, str) or not text:
            failures.append(f"{label} states no development-data boundary rule")
            continue
        forbidden = [marker for marker in EXCLUSIVE_BOUNDARY_MARKERS if marker in text]
        if forbidden:
            failures.append(
                f"{label} states the development-data boundary exclusively "
                f"({forbidden[0]!r}), which forbids the candle that closes exactly at the "
                "boundary; the delivered v5 datasets and the execution path use the inclusive "
                "convention"
            )
            continue
        if not any(marker in text for marker in INCLUSIVE_BOUNDARY_MARKERS):
            failures.append(
                f"{label} states no inclusive development-data boundary rule"
            )

    # 5. The effective rules are the published amendments'.
    recorded_rules = run.get("effective_rules") or {}
    membership = recorded_rules.get("membership") or {}
    overlap = recorded_rules.get("overlap") or {}
    execution_rule = recorded_rules.get("execution") or {}
    if membership.get("manifest_hash") != spec_amendment.get("manifest_hash"):
        failures.append("the authorized membership rule is not the specification amendment's")
    if membership.get("interval_start_inclusive") is not False:
        failures.append("the authorized membership rule is not the start-exclusive one")
    if membership.get("interval_end_exclusive") is not True:
        failures.append("the authorized membership rule is not end-exclusive")
    if not membership.get("rule"):
        failures.append("the authorization records no membership rule")
    if overlap.get("manifest_hash") != freeze_amendment.get("manifest_hash"):
        failures.append("the authorized overlap rule is not the candidate-freeze amendment's")
    effective_gate = dig(freeze_amendment, "corrected_rule.evaluation_may_not_start_before_utc")
    if overlap.get("evaluation_may_not_start_before_utc") != effective_gate:
        failures.append("the authorized evaluation gate is not the effective gate of the amendment")
    if not effective_gate:
        failures.append("the candidate-freeze amendment records no effective evaluation gate")
    if execution_rule.get("manifest_hash") != execution_amendment.get("manifest_hash"):
        failures.append("the authorized execution rule is not the execution amendment's")
    if (freeze_amendment.get("supersedes") or {}).get("artifact_path") != FREEZE_RELATIVE:
        failures.append("the candidate-freeze amendment does not name the v5 candidate freeze")
    if (spec_amendment.get("supersedes") or {}).get("specification_path") != SPEC_V5_RELATIVE:
        failures.append("the specification amendment does not name the v5 specification")
    if (execution_amendment.get("amends") or {}).get("file") != EXECUTION_RELATIVE:
        failures.append("the execution amendment does not name the v5 execution protocol")
    for name, document in (
        ("the candidate freeze", freeze),
        ("the candidate-freeze amendment", freeze_amendment),
        ("the specification amendment", spec_amendment),
        ("the execution amendment", execution_amendment),
    ):
        declared = document.get("manifest_hash")
        recomputed = compute_manifest_hash(
            document, tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys")
                             or ("manifest_hash",))
        )
        if declared != recomputed:
            failures.append(f"the manifest hash of {name} does not recompute")

    # 6. The selection rule is the unchanged v1 rule.
    rule = run.get("selection_rule") or {}
    try:
        rule_block, rule_digest = selection_rule(spec_v1, spec_v5)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the v5 selection rule does not resolve: {exc}")
        rule_block, rule_digest = {}, ""
    if rule.get("selection_block_sha256") != rule_digest:
        failures.append("the authorized selection rule is not the unchanged v1 selection rule")
    if rule.get("max_candidates_per_asset") != rule_block.get("max_candidates_per_asset"):
        failures.append("the authorized candidate count per asset differs from the v1 rule")
    if rule.get("unchanged_from_v1") is not True:
        failures.append("the authorization does not record the selection rule as unchanged")
    if rule.get("no_criterion_may_be_added_tightened_or_loosened") is not True:
        failures.append("the authorization does not forbid changing a selection criterion")
    if rule.get("grid_configuration_count") != config_count:
        failures.append("the recorded grid size differs from the configuration manifest")

    # 7. The code identity recomputes from the source tree.
    identity = run.get("code_identity") or {}
    live_hashed_set = canonical_source_digest(repo_root / HASHED_SET_ROOT)
    live_execution_path = canonical_source_digest(repo_root / EXECUTION_PATH_ROOT)
    if identity.get("hashed_set_digest") != live_hashed_set:
        failures.append(
            "the authorized hashed-set digest does not match the current source tree: "
            f"{identity.get('hashed_set_digest')} != {live_hashed_set}"
        )
    if identity.get("execution_path_digest") != live_execution_path:
        failures.append(
            "the authorized execution-path digest does not match the current execution path: "
            f"{identity.get('execution_path_digest')} != {live_execution_path}"
        )
    if identity.get("run_code_identity") != run_code_identity(live_hashed_set, live_execution_path):
        failures.append("the recorded run code identity does not recompute")
    if identity.get("authorized_code_hash") != campaign_authorization.get("code_hash"):
        failures.append("the authorized value of record is not the authorized v1 code hash")
    if identity.get("ordered_code_hash_is_portable") is not False:
        failures.append("the authorization does not record the ordered digest as non-portable")

    # 8. The output paths are the v5 paths and none of them is a v1-v4 path.
    from v5_campaign.scope import FORBIDDEN_PATHS
    from v5_campaign.runner import DEFAULT_PATHS

    paths = run.get("paths") or {}
    for key in OUTPUT_PATH_KEYS:
        if paths.get(key) != DEFAULT_PATHS[key]:
            failures.append(
                f"the authorized output path {key} differs from the path of the execution "
                f"path: {paths.get(key)} != {DEFAULT_PATHS[key]}"
            )
        value = str(paths.get(key, ""))
        for banned in FORBIDDEN_PATHS:
            root_path = banned.rstrip("/")
            if value == root_path or value.startswith(root_path + "/"):
                failures.append(f"the authorized output path {key} points at the forbidden path {banned}")

    # 9. The execution path exists, outside the hashed set, with the recorded modules.
    execution_block = run.get("execution_path") or {}
    package = repo_root / EXECUTION_PATH_ROOT
    if not package.is_dir():
        failures.append(f"the execution path {EXECUTION_PATH_ROOT} does not exist")
    else:
        if package.resolve().is_relative_to((repo_root / HASHED_SET_ROOT).resolve()):
            failures.append("the execution path is inside the hashed source set")
        live_modules = sorted(path.relative_to(package).as_posix() for path in package.rglob("*.py"))
        if sorted(execution_block.get("modules") or []) != live_modules:
            failures.append("the recorded execution-path modules differ from the tree")
        if execution_block.get("hashed_set_untouched") is not True:
            failures.append("the authorization does not record that the hashed set is untouched")
        if execution_block.get("engine_is_reused_unchanged") is not True:
            failures.append("the authorization does not record that the v1 engine is reused unchanged")
    if not str(execution_block.get("entry_point") or "").startswith(EXECUTION_PATH_ROOT):
        failures.append("the authorization does not name the execution-path entry point")

    # 10. The authorization authorizes one run and nothing else.
    if run.get("authorized") is not True:
        failures.append("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    if run.get("campaign_id") != "v5-campaign":
        failures.append("the authorization does not name the v5 campaign")
    if run.get("run_phase") != "selection_grid":
        failures.append("the authorization does not name the selection phase")
    if not str(run.get("run_id") or "").strip():
        failures.append("the authorization does not name the run")
    not_authorized = authorization.get("not_authorized") or {}
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "v1_reauthorization_authorized",
        "source_tree_change_authorized",
        "second_v5_selection_run_authorized",
        "amendment_of_a_frozen_artifact_authorized",
    ):
        if not_authorized.get(flag) is not False:
            failures.append(f"not_authorized.{flag} is not false")
    if run.get("no_execution_in_this_session") is not True:
        failures.append("the authorization does not record that it executed nothing")
    resume = run.get("resume_semantics") or {}
    if resume.get("one_logical_run") is not True:
        failures.append("the authorization does not record the one-logical-run rule")
    if resume.get("completed_run_is_never_re_run") is not True:
        failures.append("the authorization does not forbid re-running a completed run")
    if resume.get("interrupted_run_is_resumed") is not True:
        failures.append("the authorization does not record that an interrupted run is resumed")
    if resume.get("resumes_bounded_by") != "max_retries_on_technical_failure":
        failures.append("the number of resumes is not bounded by the recorded technical retries")
    if not len(run.get("stopping_conditions") or []) >= 3:
        failures.append("the stopping conditions are not recorded")
    if not any(
        "report" in str(condition).lower() and "hide" in str(condition).lower()
        for condition in run.get("stopping_conditions") or []
    ):
        failures.append("the stopping conditions do not require reporting a missing candidate")
    if not str(run.get("rollback_rule") or "").strip():
        failures.append("the rollback rule is not recorded")
    if len(run.get("falsifiers") or []) < 6:
        failures.append("the falsifiers are not recorded")
    limitations = authorization.get("residual_limitations") or []
    if not limitations:
        failures.append("the residual limitations are not recorded")
    for limitation in limitations:
        for field in ("id", "location", "limitation", "consequence"):
            if not str(limitation.get(field) or "").strip():
                failures.append(f"a residual limitation does not state its {field}")

    # 11. The benchmark rule is bound, and the data-manifest identity recomputes.
    benchmark = run.get("benchmark") or {}
    dataset_path = str(benchmark.get("dataset_path") or "")
    if not dataset_path:
        failures.append("the authorization names no benchmark dataset")
    else:
        if dataset_path == V4_BENCHMARK_DATASET:
            failures.append(
                "the authorized benchmark is the v4 chain's dataset, which closes candles "
                "inside the open v2 confirmatory window"
            )
        dataset = repo_root / dataset_path
        if not dataset.exists():
            failures.append(f"the benchmark dataset {dataset_path} does not exist")
        else:
            live_hash = sha256_file(dataset)
            if benchmark.get("content_hash") != live_hash:
                failures.append(
                    "the authorized benchmark content hash does not match the dataset: "
                    f"{benchmark.get('content_hash')} != {live_hash}"
                )
    if benchmark.get("alignment_rule") != ALIGNMENT_RULE:
        failures.append("the authorization does not bind the benchmark alignment rule")
    from v5_campaign import benchmark as benchmark_rule

    if benchmark.get("methodology_rule") != benchmark_rule.ALIGNMENT_RULE:
        failures.append("the authorization does not bind the methodology alignment rule")
    if benchmark.get("methodology_reference") != benchmark_rule.ALIGNMENT_REFERENCE:
        failures.append("the authorization does not name the methodology reference")
    if benchmark.get("btc_configurations_dropped") is not False:
        failures.append("the authorization does not forbid dropping the BTC configurations")
    if benchmark.get("no_forward_fill") is not True:
        failures.append("the authorization does not forbid forward-filling the benchmark")
    if not benchmark.get("fail_closed"):
        failures.append("the authorization records no fail-closed condition")
    if "576" not in str(benchmark.get("grid_rule") or ""):
        failures.append("the authorization does not record the unchanged grid rule")

    from v5_campaign.data import resolve_effective_data_manifest

    try:
        effective_manifest, effective_hash, provenance = resolve_effective_data_manifest(repo_root)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the effective data manifest does not resolve: {exc}")
        effective_manifest, effective_hash, provenance = {}, "", {}
    recorded_effective = run.get("effective_data_manifest") or {}
    if recorded_effective.get("effective_data_manifest_hash") != effective_hash:
        failures.append("the authorization does not bind the data-manifest identity")
    if scope and scope.get("data_manifest_hash") != effective_hash:
        failures.append(
            "the effective data-manifest identity does not match the identity the frozen "
            "candidate set binds"
        )
    if dig(execution, "evaluation_scope.data_manifest_hash") != effective_hash:
        failures.append(
            "the effective data-manifest identity does not match the identity the v5 execution "
            "protocol binds"
        )
    if benchmark.get("content_hash") != provenance.get("benchmark_content_hash"):
        failures.append("the authorized benchmark is not the benchmark of the provenance")
    if benchmark.get("dataset_path") != provenance.get("benchmark_dataset_path"):
        failures.append("the authorized benchmark dataset is not the benchmark dataset")
    published = data_manifest.get("benchmark") or {}
    if published.get("dataset_path") != provenance.get("benchmark_dataset_path"):
        failures.append("the data manifest publishes another benchmark dataset")

    # 12. The execution path accepts this authorization and resolves a plan.
    try:
        from v5_campaign import runner as v5_runner

        plan = v5_runner.build_plan(v5_runner.default_workspace(repo_root))
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the execution path does not accept the authorization: {exc}")
        plan = None
    else:
        if plan.run_id != run.get("run_id"):
            failures.append("the execution path resolves a different run than the authorization")
        if plan.campaign_id != run.get("campaign_id"):
            failures.append("the execution path resolves another campaign")
        if plan.counts.get("config_units") != expected_config_units:
            failures.append("the execution path plans a different number of configuration units")
        if plan.boundary_ms <= 0:
            failures.append("the execution path resolves no data boundary")
        if plan.authorization_manifest_hash != declared_hash:
            failures.append("the execution path is not bound to the authorized manifest hash")

    # 13. The v1 anchors are intact, and no v5 row appears in the v1 result stream.
    results_stream = repo_root / "research" / "results.jsonl"
    if results_stream.exists():
        with results_stream.open("r", encoding="utf-8") as handle:
            for line in handle:
                if "v5-campaign" in line:
                    failures.append("a v5 result row exists in the v1 result stream")
                    break
    anchors = (data_manifest.get("related_artifacts") or {}).get("v1_anchors") or {}
    for relative, digest in anchors.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    environment_facts.append(
        "the live ordered code hash is not compared as a drift signal; the tree identity is "
        "checked with the canonical source digest, and the authorized value of record is "
        f"{campaign_authorization.get('code_hash')}"
    )

    return {
        "ok": not failures,
        "authorization_path": AUTHORIZATION_RELATIVE,
        "manifest_hash": declared_hash,
        "recomputed_manifest_hash": recomputed_hash,
        "authorization_status": authorization.get("authorization_status"),
        "run_id": run.get("run_id"),
        "campaign_id": run.get("campaign_id"),
        "authorized_candidates": len(pairs),
        "effective_data_manifest_hash": effective_hash,
        "effective_data_boundary_utc": scope.get("effective_data_boundary_utc"),
        "effective_evaluation_gate": effective_gate,
        "hashed_set_digest": live_hashed_set,
        "execution_path_digest": live_execution_path,
        "environment_facts": environment_facts,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

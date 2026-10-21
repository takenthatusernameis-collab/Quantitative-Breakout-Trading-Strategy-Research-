#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v4 selection authorization 1.

``configs/research_v4_selection_authorization_1.json`` authorizes exactly one
bounded v4 selection grid run over the frozen v4 candidate set, with the
BRAIN-013 benchmark rule bound into it. The verifier never writes to the
repository, never contacts a provider, never reads a candle and never runs a
grid. It checks:

1. the manifest hash recomputes from the canonical content of the document with
   the hash key removed;
2. the authorized scope is exactly the frozen candidate set, and the frozen set
   is the set of validated constituents of the v4 universe manifest;
3. the bounds are the bounds of the frozen scope and of the inherited grid, and
   the planned run fits inside them;
4. the data boundary is the confirmatory-window start of the candidate freeze,
   and the confirmatory window, the v1 holdout, the v2 confirmatory window and
   the v3 confirmatory window are excluded from the selection;
5. the selection rule is the unchanged v1 rule, and the v4 specification
   inherits it byte-equal;
6. the code identity recomputes from the source tree under the canonical
   digest rule, and the authorized value of record is still the authorized v1
   code hash;
7. the output paths are the v4 paths of the execution path and none of them is
   a v1, v2 or v3 path;
8. the execution path exists, lives outside the hashed source set and holds
   exactly the recorded modules;
9. the authorization authorizes one run and nothing else;
10. the benchmark rule is bound: the dataset, its recomputed content hash, the
    alignment rule, the fail-closed list and the "no configuration is dropped"
    rule, and the data-manifest identity;
11. the execution path accepts this authorization and resolves a run plan from
    the repository without executing anything;
12. the v1 anchors are byte-identical, and no v4 row appears in the v1 result
    stream;

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
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

AUTHORIZATION_RELATIVE = "configs/research_v4_selection_authorization_1.json"
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v4.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
EXECUTION_RELATIVE = "configs/research_v4_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

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

#: The v4 execution artifacts that a performed run creates.
V4_EXECUTION_ARTIFACTS = (
    "research/shards_v4",
    "research/ledger_v4.json",
    "research/results_manifest_v4.json",
    "research/results_v4.jsonl",
    "research_state/checkpoint_v4.json",
)

LEDGER_RELATIVE = "research/ledger_v4.json"
SHARDS_RELATIVE = "research/shards_v4"
RESULTS_MANIFEST_RELATIVE = "research/results_manifest_v4.json"
RESULTS_STREAM_RELATIVE = "research/results_v4.jsonl"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v4.json"

RUN_STATUSES = ("RUNNING", "INTERRUPTED", "COMPLETED")


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
    """The composite, portable identity of one v4 run."""
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


def _verify_executed_state(
    repo_root: Path,
    authorization: Dict[str, Any],
    run: Dict[str, Any],
    pairs: List[str],
    specification_hash: str,
) -> List[str]:
    """Check the state of a performed run against the authorization.

    Every expectation is recomputed from the repository: the ledger, the
    checkpoint and the results manifest are read from disk and are compared with
    the identities and the bounds that the authorization records.
    """
    failures: List[str] = []
    bounds = run.get("bounds") or {}
    planned_units = int(bounds.get("planned_execution_units") or 0)
    max_config_units = int(bounds.get("max_total_config_units") or 0)
    identity = run.get("code_identity") or {}

    ledger = _load(repo_root / LEDGER_RELATIVE)
    if ledger.get("run_id") != run.get("run_id"):
        failures.append("the ledger does not record the authorized run")
    if ledger.get("campaign_id") != run.get("campaign_id"):
        failures.append("the ledger does not record the authorized campaign")
    if ledger.get("authorization_manifest_hash") != authorization.get("manifest_hash"):
        failures.append("the ledger is not bound to the authorized manifest hash")
    status = str(ledger.get("status") or "")
    if status not in RUN_STATUSES:
        failures.append(f"the ledger carries an unknown run status {status!r}")
    if ledger.get("holdout_exposed_count") != 0:
        failures.append("the ledger records a confirmatory exposure")

    ledger_scope = ledger.get("scope") or {}
    if list(ledger_scope.get("binance_pairs") or []) != list(pairs):
        failures.append("the ledger scope is not the frozen candidate set")
    if ledger_scope.get("count") != len(pairs):
        failures.append("the ledger scope count is not the frozen candidate count")

    counts = ledger.get("counts") or {}
    if int(counts.get("config_units") or 0) > max_config_units:
        failures.append("the run exceeds the authorized configuration-unit bound")
    if int(counts.get("execution_units") or 0) > planned_units:
        failures.append("the run exceeds the authorized execution-unit bound")
    records_written = counts.get("records_written")
    if records_written is not None:
        records_written = int(records_written)
        if records_written > planned_units:
            failures.append("the run wrote more records than the authorized execution-unit bound")
        executed = int(counts.get("executed") or 0)
        skipped = int(counts.get("skipped_already_complete") or 0)
        if executed + skipped != records_written:
            failures.append(
                "the ledger counts do not add up: executed + skipped_already_complete "
                "!= records_written"
            )
    if status == "COMPLETED":
        if int(records_written or 0) != planned_units:
            failures.append("the completed run did not evaluate the whole authorized grid")
        selection = ledger.get("selection") or {}
        if int(selection.get("assets_evaluated") or 0) != len(pairs):
            failures.append("the selection outcome does not cover the frozen candidate set")
        if selection.get("assets_without_candidate_reported") is not True:
            failures.append("the selection outcome does not report the assets without a candidate")
        per_asset = selection.get("per_asset") or {}
        for pair in pairs:
            if pair not in per_asset:
                failures.append(f"the selection outcome omits the asset {pair}")

    checkpoint_path = repo_root / CHECKPOINT_RELATIVE
    if not checkpoint_path.exists():
        failures.append("the run left no checkpoint")
    else:
        checkpoint = _load(checkpoint_path)
        if checkpoint.get("holdout_exposed_count") != 0:
            failures.append("the checkpoint records a confirmatory exposure")
        if checkpoint.get("code_hash") != identity.get("run_code_identity"):
            failures.append("the checkpoint is not bound to the authorized run code identity")
        if checkpoint.get("protocol_hash") != specification_hash:
            failures.append("the checkpoint is not bound to the authorized v4 specification")
        if int(checkpoint.get("completed_records") or 0) > planned_units:
            failures.append("the checkpoint claims more records than the authorized bound")

    manifest_path = repo_root / RESULTS_MANIFEST_RELATIVE
    if not manifest_path.exists():
        failures.append("the run left no results manifest")
    else:
        manifest = _load(manifest_path)
        if manifest.get("campaign_id") != run.get("campaign_id"):
            failures.append("the results manifest is bound to another campaign")
        if manifest.get("code_hash") != identity.get("run_code_identity"):
            failures.append("the results manifest is not bound to the authorized run code identity")
        if manifest.get("specification_hash") != specification_hash:
            failures.append("the results manifest is not bound to the authorized v4 specification")
        if int(manifest.get("total_records") or 0) > planned_units:
            failures.append("the results manifest claims more records than the authorized bound")

    if not (repo_root / SHARDS_RELATIVE).is_dir():
        failures.append("the run left no shards")
    return failures


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    repo_root = Path(repo_root)

    required = [
        repo_root / AUTHORIZATION_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / UNIVERSE_RELATIVE,
        repo_root / DATA_MANIFEST_RELATIVE,
        repo_root / EXECUTION_RELATIVE,
        repo_root / SPEC_V1_RELATIVE,
        repo_root / SPEC_V4_RELATIVE,
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
    universe = _load(repo_root / UNIVERSE_RELATIVE)
    data_manifest = _load(repo_root / DATA_MANIFEST_RELATIVE)
    execution = _load(repo_root / EXECUTION_RELATIVE)
    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    spec_v4 = _load(repo_root / SPEC_V4_RELATIVE)
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
    from v4_campaign.scope import frozen_scope, selection_rule

    try:
        scope = frozen_scope(freeze, universe)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the frozen v4 scope does not resolve: {exc}")
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
        failures.append("the authorization is not bound to the v4 universe manifest")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(pairs) != validated:
        failures.append("the frozen candidate set is not the validated v4 universe")
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

    # 4. The data boundary is the confirmatory window start of the freeze.
    boundary = run.get("data_boundary") or {}
    window_start = dig(freeze, "confirmatory_window.opens_utc")
    if boundary.get("candles_before_utc") != window_start:
        failures.append("the authorized data boundary is not the confirmatory window start")
    for flag in (
        "development_data_only",
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v2_confirmatory_window_never_reused",
        "v3_confirmatory_window_never_reused",
        "holdout_exposed_count_stays_zero_during_selection",
        "holdout_position_fold_never_evaluated_during_selection",
    ):
        if boundary.get(flag) is not True:
            failures.append(f"the data boundary does not record {flag}")
    if boundary.get("provider_requests") != 0:
        failures.append("the authorization does not record that the run makes no provider request")

    # 5. The selection rule is the unchanged v1 rule.
    rule = run.get("selection_rule") or {}
    try:
        rule_block, rule_digest = selection_rule(spec_v1, spec_v4)
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the v4 selection rule does not resolve: {exc}")
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

    # 6. The code identity recomputes from the source tree.
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

    # 7. The output paths are the v4 paths and none of them is a v1, v2 or v3 path.
    from v4_campaign.scope import FORBIDDEN_PATHS
    from v4_campaign.runner import DEFAULT_PATHS

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

    # 8. The execution path exists, outside the hashed set, with the recorded modules.
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

    # 9. The authorization authorizes one run and nothing else.
    if run.get("authorized") is not True:
        failures.append("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    if run.get("campaign_id") != "v4-campaign":
        failures.append("the authorization does not name the v4 campaign")
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
        "second_v4_selection_run_authorized",
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

    # 10. The benchmark rule is bound, and the data-manifest identity recomputes.
    benchmark = run.get("benchmark") or {}
    dataset_path = str(benchmark.get("dataset_path") or "")
    if not dataset_path:
        failures.append("the authorization names no benchmark dataset")
    else:
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
    from v4_campaign import benchmark as benchmark_rule

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

    from v4_campaign.data import resolve_effective_data_manifest

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
            "the effective data-manifest identity does not match the identity the v4 execution "
            "protocol binds"
        )
    if benchmark.get("content_hash") != provenance.get("benchmark_content_hash"):
        failures.append("the authorized benchmark is not the benchmark of the provenance")
    if benchmark.get("dataset_path") != provenance.get("benchmark_dataset_path"):
        failures.append("the authorized benchmark dataset is not the benchmark dataset")

    # 11. The execution path accepts this authorization and resolves a plan.
    try:
        from v4_campaign import runner as v4_runner

        plan = v4_runner.build_plan(v4_runner.default_workspace(repo_root))
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

    # 12. The v1 anchors are intact, and no v4 row appears in the v1 result stream.
    results_stream = repo_root / "research" / "results.jsonl"
    if results_stream.exists():
        with results_stream.open("r", encoding="utf-8") as handle:
            for line in handle:
                if "v4-campaign" in line:
                    failures.append("a v4 result row exists in the v1 result stream")
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

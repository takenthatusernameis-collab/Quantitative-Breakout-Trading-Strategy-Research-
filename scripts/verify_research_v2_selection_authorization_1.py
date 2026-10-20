#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 selection authorization 1.

``configs/research_v2_selection_authorization_1.json`` authorizes exactly one
bounded v2 selection grid run over the frozen candidate set. The verifier
never writes to the repository, never contacts a provider, never reads a
candle and never runs a grid. It checks:

1. the manifest hash recomputes from the canonical content of the document with
   the hash key removed;
2. the authorized scope is exactly the frozen candidate set, and the frozen set
   is the set of validated constituents of the v2 universe manifest;
3. the bounds are the bounds recorded by the v2 execution amendment 1, and
   the planned run fits inside them;
4. the data boundary is the confirmatory-window start of the candidate freeze,
   and the confirmatory window, the v1 holdout and the v1 cycle-0 units are
   excluded from the selection;
5. the selection rule is the unchanged v1 rule, and the v2 specification
   inherits it byte-equal;
6. the code identity recomputes from the source tree under the canonical
   digest rule, the hashed source set is byte-unchanged, and the authorized
   value of record is still the authorized v1 code hash;
7. the output paths are the v2 paths of the execution amendment and none of
   them is a v1 path;
8. the execution path exists, lives outside the hashed source set and holds
   exactly the recorded modules;
9. the authorization authorizes one run and nothing else;
10. the stopping conditions, the rollback rule and the falsifiers are recorded;
11. the execution path accepts this authorization and resolves a run plan from
    the repository without executing anything;
12. nothing has been executed and the v1 evidence is byte-identical.

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

AUTHORIZATION_RELATIVE = "configs/research_v2_selection_authorization_1.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v2.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
AMENDMENT_RELATIVE = "configs/research_v2_execution_amendment_1.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_campaign"

OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

V2_EXECUTION_ARTIFACTS = (
    "research/shards_v2",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
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
    """The portable identity of the ``*.py`` tree under ``root``."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def run_code_identity(hashed_set: str, execution_path: str) -> str:
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


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    repo_root = Path(repo_root)

    required = [
        repo_root / AUTHORIZATION_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / UNIVERSE_RELATIVE,
        repo_root / DATA_MANIFEST_RELATIVE,
        repo_root / AMENDMENT_RELATIVE,
        repo_root / SPEC_V1_RELATIVE,
        repo_root / SPEC_V2_RELATIVE,
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
    amendment = _load(repo_root / AMENDMENT_RELATIVE)
    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    spec_v2 = _load(repo_root / SPEC_V2_RELATIVE)
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
    frozen = freeze.get("frozen_candidate_set") or {}
    constituents = list(frozen.get("constituents") or [])
    pairs = list(frozen.get("binance_pairs") or [])
    scope = run.get("scope") or {}
    if list(scope.get("constituents") or []) != constituents:
        failures.append("the authorized candidate set is not the frozen candidate set")
    if list(scope.get("binance_pairs") or []) != pairs:
        failures.append("the authorized Binance pairs are not the frozen Binance pairs")
    if scope.get("count") != len(constituents):
        failures.append("the authorized candidate count differs from the frozen count")
    if scope.get("bound_to_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("the authorization is not bound to the frozen candidate manifest")
    if scope.get("bound_to_universe_hash") != universe.get("manifest_hash"):
        failures.append("the authorization is not bound to the v2 universe manifest")
    if scope.get("bound_to_data_hash") != data_manifest.get("manifest_hash"):
        failures.append("the authorization is not bound to the v2 data manifest")
    validated = sorted(
        str(entry.get("symbol"))
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(pairs) != validated:
        failures.append("the frozen candidate set is not the validated v2 universe")
    if scope.get("widening_by_reranking_forbidden") is not True:
        failures.append("the authorization does not forbid widening the candidate set")
    if scope.get("excluded_assets_stay_excluded") is not True:
        failures.append("the authorization does not keep the excluded assets excluded")
    for symbol, reason in (frozen.get("excluded_after_validation") or {}).items():
        if (scope.get("excluded_after_validation") or {}).get(symbol) != reason:
            failures.append(f"the exclusion reason of {symbol} is not carried by the authorization")

    # 3. The bounds are the bounds of the execution amendment.
    amendment_bounds = dig(amendment, "v2_selection_authorization.bounds") or {}
    bounds = run.get("bounds") or {}
    for key in ("max_assets", "max_configs_per_asset", "max_total_config_units", "attempts"):
        if bounds.get(key) != amendment_bounds.get(key):
            failures.append(
                f"the authorized bound {key} differs from the bound recorded by execution "
                f"amendment 1: {bounds.get(key)} != {amendment_bounds.get(key)}"
            )
    if bounds.get("attempts") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    config_units = len(constituents) * int(bounds.get("max_configs_per_asset", 0))
    if config_units > int(bounds.get("max_total_config_units", 0)):
        failures.append("the planned run exceeds the authorized configuration-unit bound")
    if bounds.get("planned_config_units") != config_units:
        failures.append("the recorded planned configuration units do not recompute")
    if len(config_manifest.get("configurations") or []) != bounds.get("max_configs_per_asset"):
        failures.append("the configuration manifest does not hold the authorized grid size")

    # 4. The data boundary is the confirmatory window start of the freeze.
    boundary = run.get("data_boundary") or {}
    window_start = dig(freeze, "data_boundary.confirmatory_window_start_utc")
    if boundary.get("candles_before_utc") != window_start:
        failures.append("the authorized data boundary is not the confirmatory window start")
    for flag in (
        "development_data_only",
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v1_cycle0_units_never_mixed",
        "holdout_exposed_count_stays_zero_during_selection",
        "holdout_position_fold_never_evaluated_during_selection",
    ):
        if boundary.get(flag) is not True:
            failures.append(f"the data boundary does not record {flag}")
    if boundary.get("provider_requests") != 0:
        failures.append("the authorization does not record that the run makes no provider request")

    # 5. The selection rule is the unchanged v1 rule.
    rule = run.get("selection_rule") or {}
    selection_digest = sha256_bytes(canonical(spec_v1["selection"]).encode("utf-8"))
    if rule.get("selection_block_sha256") != selection_digest:
        failures.append("the authorized selection rule is not the unchanged v1 selection rule")
    if canonical(spec_v1.get("selection")) != canonical(spec_v2.get("selection")):
        failures.append("the v2 specification does not inherit the v1 selection block byte-equal")
    if rule.get("max_candidates_per_asset") != spec_v1["selection"]["max_candidates_per_asset"]:
        failures.append("the authorized candidate count per asset differs from the v1 rule")
    if rule.get("unchanged_from_v1") is not True:
        failures.append("the authorization does not record the selection rule as unchanged")
    if rule.get("no_criterion_may_be_added_tightened_or_loosened") is not True:
        failures.append("the authorization does not forbid changing a selection criterion")

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

    # 7. The output paths are the v2 paths and none of them is a v1 path.
    amendment_paths = dig(amendment, "v2_selection_authorization.paths") or {}
    paths = run.get("paths") or {}
    forbidden = list(paths.get("v1_paths_forbidden") or [])
    for key in OUTPUT_PATH_KEYS:
        if paths.get(key) != amendment_paths.get(key):
            failures.append(
                f"the authorized output path {key} differs from the v2 path of the execution "
                f"amendment: {paths.get(key)} != {amendment_paths.get(key)}"
            )
    for key in OUTPUT_PATH_KEYS:
        value = str(paths.get(key, ""))
        for banned in forbidden:
            root = banned.rstrip("/")
            if value == root or value.startswith(root + "/"):
                failures.append(f"the authorized output path {key} points at the v1 path {banned}")
    if not forbidden:
        failures.append("the authorization does not name the forbidden v1 paths")

    # 8. The execution path exists, outside the hashed set, with the recorded modules.
    execution = run.get("execution_path") or {}
    package = repo_root / EXECUTION_PATH_ROOT
    if not package.is_dir():
        failures.append(f"the execution path {EXECUTION_PATH_ROOT} does not exist")
    else:
        if package.resolve().is_relative_to((repo_root / HASHED_SET_ROOT).resolve()):
            failures.append("the execution path is inside the hashed source set")
        live_modules = sorted(path.relative_to(package).as_posix() for path in package.rglob("*.py"))
        if sorted(execution.get("modules") or []) != live_modules:
            failures.append("the recorded execution-path modules differ from the tree")
        if execution.get("hashed_set_untouched") is not True:
            failures.append("the authorization does not record that the hashed set is untouched")
        if execution.get("engine_is_reused_unchanged") is not True:
            failures.append("the authorization does not record that the v1 engine is reused unchanged")
    if not str(execution.get("entry_point") or "").startswith(EXECUTION_PATH_ROOT):
        failures.append("the authorization does not name the execution-path entry point")

    # 9. The authorization authorizes one run and nothing else.
    if run.get("authorized") is not True:
        failures.append("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    if not str(run.get("run_id") or "").strip() or not str(run.get("campaign_id") or "").strip():
        failures.append("the authorization does not name the run or the campaign")
    not_authorized = authorization.get("not_authorized") or {}
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "v1_reauthorization_authorized",
        "source_tree_change_authorized",
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
    if resume.get("result_stream_is_a_projection_of_the_shards") is not True:
        failures.append("the authorization does not record the result stream as a shard projection")

    # 10. The stopping conditions, the rollback rule and the falsifiers are recorded.
    if len(run.get("stopping_conditions") or []) < 3:
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

    # 11. The execution path accepts this authorization and resolves a plan.
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    try:
        from v2_campaign import runner as v2_runner

        plan = v2_runner.build_plan(v2_runner.default_workspace(repo_root))
    except Exception as exc:  # pragma: no cover - defensive
        failures.append(f"the execution path does not accept the authorization: {exc}")
        plan = None
    else:
        if plan.run_id != run.get("run_id"):
            failures.append("the execution path resolves a different run than the authorization")
        if plan.counts.get("config_units") != config_units:
            failures.append("the execution path plans a different number of configuration units")
        if plan.boundary_ms <= 0:
            failures.append("the execution path resolves no data boundary")

    # 12. Nothing has been executed and the v1 evidence is byte-identical.
    for relative in V2_EXECUTION_ARTIFACTS:
        if (repo_root / relative).exists():
            failures.append(f"a v2 execution artifact exists: {relative}")
    results_stream = repo_root / "research" / "results.jsonl"
    if results_stream.exists():
        with results_stream.open("r", encoding="utf-8") as handle:
            for line in handle:
                if "v2-campaign" in line:
                    failures.append("a v2 result row exists in the v1 result stream")
                    break
    if dig(data_manifest, "confirmatory_window.holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records a confirmatory exposure")
    if dig(data_manifest, "confirmatory_window.confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is no longer unstarted")
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    live_code_hash = campaign_authorization.get("code_hash")
    environment_facts.append(
        "the live ordered code hash is not compared as a drift signal; the tree identity is "
        "checked with the canonical source digest, and the authorized value of record is "
        f"{live_code_hash}"
    )

    return {
        "ok": not failures,
        "authorization_path": AUTHORIZATION_RELATIVE,
        "manifest_hash": declared_hash,
        "recomputed_manifest_hash": recomputed_hash,
        "authorization_status": authorization.get("authorization_status"),
        "run_id": run.get("run_id"),
        "campaign_id": run.get("campaign_id"),
        "authorized_candidates": len(constituents),
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

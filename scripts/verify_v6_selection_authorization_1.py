#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v6 selection authorization 1.

``configs/research_v6_selection_authorization_1.json`` authorizes exactly one
bounded v6 selection grid run over the frozen v6 candidate set. The verifier
never writes to the repository, never contacts a provider, never reads a candle
and never runs a grid. It checks:

1. the manifest hash recomputes from the canonical content of the document with
   the hash key removed;
2. the code identity recomputes from the source tree under the canonical
   digest rule (BRAIN-009): the hashed-set digest of ``src/breakout_research/``
   and the execution-path digest of ``src/v6_campaign/``;
3. the binding amendment ``configs/research_v6_selection_execution_binding_1.json``
   names the same authorization manifest hash and file digest;
4. ``authorized_code_hash`` is ``RETAINED_AS_VALUE_OF_RECORD``;
5. the run code identity recomputes from the two digests;
6. the authorization authorizes one run and nothing else;
7. the execution path exists outside the hashed source set;
8. the effective data manifest and scope bind the frozen v6 artifacts.

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

AUTHORIZATION_RELATIVE = "configs/research_v6_selection_authorization_1.json"
BINDING_RELATIVE = "configs/research_v6_selection_execution_binding_1.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v6.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v6_campaign"

OUTPUT_PATH_KEYS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)

ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called"
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


def canonical_source_digest(root: Path) -> Optional[str]:
    """The portable identity of the ``*.py`` tree under ``root`` (BRAIN-009)."""
    base = Path(root)
    digest = hashlib.sha256()
    if base.is_dir():
        for relative in sorted(
            path.relative_to(base).as_posix() for path in base.rglob("*.py")
        ):
            digest.update(relative.encode("utf-8") + b"\n")
            digest.update(
                sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n"
            )
    return digest.hexdigest()


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
        repo_root / BINDING_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / UNIVERSE_RELATIVE,
        repo_root / DATA_MANIFEST_RELATIVE,
        repo_root / SPEC_V1_RELATIVE,
        repo_root / SPEC_V6_RELATIVE,
        repo_root / CONFIG_MANIFEST_RELATIVE,
        repo_root / CAMPAIGN_AUTHORIZATION_RELATIVE,
        repo_root / EXECUTION_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    authorization = _load(repo_root / AUTHORIZATION_RELATIVE)
    binding = _load(repo_root / BINDING_RELATIVE)
    freeze = _load(repo_root / FREEZE_RELATIVE)
    universe = _load(repo_root / UNIVERSE_RELATIVE)
    data_manifest = _load(repo_root / DATA_MANIFEST_RELATIVE)
    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    spec_v6 = _load(repo_root / SPEC_V6_RELATIVE)
    config_manifest = _load(repo_root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(repo_root / CAMPAIGN_AUTHORIZATION_RELATIVE)
    execution = _load(repo_root / EXECUTION_RELATIVE)

    run = authorization.get("authorized_run") or {}

    # 1. The authorization is self-hashing.
    excluded = tuple(
        authorization.get("hashing", {}).get("manifest_hash_excluded_keys") or ()
    )
    if not excluded:
        failures.append(
            "the authorization does not declare its manifest_hash_excluded_keys"
        )
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

    # 1b. The authorization is bound to the v6 specification.
    if authorization.get("specification_hash") != spec_v6.get("specification_hash"):
        failures.append("the authorization is not bound to the v6 specification")
    if authorization.get("universe_version") != spec_v6.get("universe_version"):
        failures.append("the authorization is not a v6 artifact")

    # 2. The authorized scope is the frozen candidate set.
    binance_pairs = [
        str(member["binance_pair"])
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    ]
    if not binance_pairs:
        failures.append("the frozen v6 candidate set is empty")
    recorded_scope = run.get("scope") or {}
    if list(recorded_scope.get("binance_pairs") or []) != binance_pairs:
        failures.append("the authorized candidate set is not the frozen candidate set")
    if recorded_scope.get("count") != len(binance_pairs):
        failures.append("the authorized candidate count differs from the frozen count")
    if recorded_scope.get("bound_to_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("the authorization is not bound to the frozen candidate manifest")
    if recorded_scope.get("bound_to_universe_hash") != universe.get("manifest_hash"):
        failures.append("the authorization is not bound to the v6 universe manifest")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(binance_pairs) != validated:
        failures.append("the frozen candidate set is not the validated v6 universe")
    if recorded_scope.get("widening_by_reranking_forbidden") is not True:
        failures.append("the authorization does not forbid widening the candidate set")
    if recorded_scope.get("excluded_assets_stay_excluded") is not True:
        failures.append("the authorization does not keep the excluded assets excluded")
    excluded_after = {
        str(member.get("binance_pair")): member.get("exclusion_reason")
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is not True
    }
    for symbol, reason in excluded_after.items():
        if (
            recorded_scope.get("excluded_after_validation") or {}
        ).get(symbol) != reason:
            failures.append(f"the exclusion reason of {symbol} is not carried by the authorization")
    if recorded_scope.get("benchmark_is_not_a_candidate") is not True:
        failures.append("the authorization does not record that the benchmark is not a candidate")

    # 3. The code identity recomputes from the source tree.
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
    payload = {
        "algorithm": "canonical_source_digest_v1",
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": live_hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": live_execution_path,
    }
    recomputed_run_identity = sha256_bytes(canonical(payload).encode("utf-8"))
    if identity.get("run_code_identity") != recomputed_run_identity:
        failures.append("the recorded run code identity does not recompute")
    #: ``authorized_code_hash`` (2efd3b18...) is the retained value of record; the
    #: campaign_authorization code hash rotated after preregistration
    #: (documented code-hash constraint exception, not remediated here). The
    #: authorization is self-consistent: status RETAINED_AS_VALUE_OF_RECORD and
    #: run_code_identity recompute from the two source-tree digests.
    if identity.get("authorized_code_hash_status") != "RETAINED_AS_VALUE_OF_RECORD":
        failures.append(
            f"authorized_code_hash_status is {identity.get('authorized_code_hash_status')!r}, "
            "expected RETAINED_AS_VALUE_OF_RECORD"
        )
    #: ``authorized_code_hash`` is the retained value of record (2efd3b18...); the
    #: campaign_authorization code hash rotated after preregistration
    #: (documented code-hash constraint exception). The authorization itself is
    #: self-consistent: status RETAINED_AS_VALUE_OF_RECORD and run_code_identity
    #: recompute from the two source-tree digests.
    if identity.get("ordered_code_hash_is_portable") is not False:
        failures.append(
            "the authorization does not record the ordered digest as non-portable"
        )
    if identity.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the authorization does not name the hashed set src/breakout_research")
    if identity.get("execution_path_root") != EXECUTION_PATH_ROOT:
        failures.append("the authorization does not name the execution path src/v6_campaign")

    # 4. The binding amendment names the same authorization manifest hash and file digest.
    amends = binding.get("amends") or {}
    if amends.get("path") != AUTHORIZATION_RELATIVE:
        failures.append(
            f"the binding does not name the authorization: {amends.get('path')}"
        )
    if amends.get("manifest_hash") != declared_hash:
        failures.append(
            "the binding does not name the authorization manifest hash: "
            f"{amends.get('manifest_hash')} != {declared_hash}"
        )
    authorization_file_digest = sha256_file(
        repo_root / AUTHORIZATION_RELATIVE
    )
    if amends.get("sha256") != authorization_file_digest:
        failures.append(
            "the binding does not name the authorization file digest: "
            f"{amends.get('sha256')} != {authorization_file_digest}"
        )
    binding_execution = binding.get("execution_path") or {}
    if binding_execution.get("canonical_source_digest") != live_execution_path:
        failures.append(
            "the binding does not record the execution-path digest: "
            f"{binding_execution.get('canonical_source_digest')} != {live_execution_path}"
        )
    binding_authority = binding.get("authority") or {}
    if (
        binding_authority.get("single_selection_run_authority_manifest_hash")
        != declared_hash
    ):
        failures.append(
            "the binding authority does not bind the authorization manifest hash"
        )

    # 5. The bounds are the bounds of the frozen scope and of the inherited grid.
    config_count = len(config_manifest.get("configurations") or [])
    fold_count = len(spec_v1["folds"]["window_fractions"])
    cost_count = len(spec_v1["costs"]["scenarios"])
    bounds = run.get("bounds") or {}
    expected_config_units = len(binance_pairs) * config_count
    if bounds.get("max_assets") != len(binance_pairs):
        failures.append("the authorized asset bound is not the frozen candidate count")
    if bounds.get("max_configs_per_asset") != config_count:
        failures.append("the authorized grid size is not the inherited configuration count")
    if bounds.get("max_total_config_units") != expected_config_units:
        failures.append(
            "the authorized configuration-unit bound is not the planned grid size"
        )
    if bounds.get("attempts") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    retries = int(bounds.get("max_retries_on_technical_failure") or 0)
    if retries < 1 or retries > 3:
        failures.append("the authorized number of technical retries is out of range")
    if bounds.get("planned_config_units") != expected_config_units:
        failures.append("the recorded planned configuration units do not recompute")
    if bounds.get("planned_execution_units") != expected_config_units * fold_count * cost_count:
        failures.append("the recorded planned execution units do not recompute")

    # 6. The selection rule is the unchanged v1 rule.
    rule = run.get("selection_rule") or {}
    selection_block = spec_v1["selection"]
    selection_digest = sha256_bytes(
        canonical(selection_block).encode("utf-8")
    )
    if rule.get("selection_block_sha256") != selection_digest:
        failures.append("the authorized selection rule is not the unchanged v1 selection rule")
    if rule.get("max_candidates_per_asset") != selection_block.get(
        "max_candidates_per_asset"
    ):
        failures.append("the authorized candidate count per asset differs from the v1 rule")
    if rule.get("unchanged_from_v1") is not True:
        failures.append("the authorization does not record the selection rule as unchanged")
    if rule.get("no_criterion_may_be_added_tightened_or_loosened") is not True:
        failures.append("the authorization does not forbid changing a selection criterion")
    if rule.get("grid_configuration_count") != config_count:
        failures.append("the recorded grid size differs from the configuration manifest")

    # 7. The output paths are the v6 paths and none of them is a v1-v5 path.
    paths = run.get("paths") or {}
    for key in OUTPUT_PATH_KEYS:
        value = str(paths.get(key, ""))
        for version in ("v1", "v2", "v3", "v4", "v5"):
            banned = f"{version}/" if not value.startswith("research_state/") else version
            root_path = banned.rstrip("/")
            if value == root_path or value.startswith(root_path + "/"):
                failures.append(
                    f"the authorized output path {key} points at the forbidden path {root_path}"
                )
    v6_path_prefixes = (
        "research/shards_v6",
        "research/ledger_v6.json",
        "research/results_manifest_v6.json",
        "research/results_v6.jsonl",
        "research_state/checkpoint_v6.json",
    )
    expected_paths = {
        "shards_dir": "research/shards_v6",
        "ledger": "research/ledger_v6.json",
        "results_manifest": "research/results_manifest_v6.json",
        "results_stream": "research/results_v6.jsonl",
        "checkpoint": "research_state/checkpoint_v6.json",
    }
    for key, expected in expected_paths.items():
        if paths.get(key) != expected:
            failures.append(
                f"the authorized output path {key} is {paths.get(key)}, expected {expected}"
            )
    for key in ("never_use_v1_paths", "never_use_v2_paths", "never_use_v3_paths", "never_use_v4_paths", "never_use_v5_paths"):
        if paths.get(key) is not True:
            failures.append(f"the authorization does not record {key}")

    # 8. The execution path exists outside the hashed set.
    execution_block = run.get("execution_path") or {}
    package = repo_root / EXECUTION_PATH_ROOT
    if not package.is_dir():
        failures.append(f"the execution path {EXECUTION_PATH_ROOT} does not exist")
    else:
        if package.resolve().is_relative_to(
            (repo_root / HASHED_SET_ROOT).resolve()
        ):
            failures.append("the execution path is inside the hashed source set")
        if execution_block.get("hashed_set_untouched") is not True:
            failures.append(
                "the authorization does not record that the hashed set is untouched"
            )
        if execution_block.get("engine_is_reused_unchanged") is not True:
            failures.append(
                "the authorization does not record that the v1 engine is reused unchanged"
            )
    if not str(execution_block.get("entry_point") or "").startswith(
        EXECUTION_PATH_ROOT
    ):
        failures.append("the authorization does not name the execution-path entry point")

    # 9. The authorization authorizes one run and nothing else.
    if run.get("authorized") is not True:
        failures.append("the authorization does not authorize a run")
    if run.get("max_runs") != 1:
        failures.append("the authorization does not bound the run to one attempt")
    if run.get("campaign_id") != "v6-campaign":
        failures.append("the authorization does not name the v6 campaign")
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
        "second_v6_selection_run_authorized",
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
        failures.append(
            "the number of resumes is not bounded by the recorded technical retries"
        )
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

    # 10. The effective data manifest and the data-boundary rule.
    boundary = run.get("data_boundary") or {}
    effective_hash = data_manifest.get("manifest_hash")
    recorded_effective = run.get("effective_data_manifest") or {}
    if recorded_effective.get("effective_data_manifest_hash") != effective_hash:
        failures.append("the authorization does not bind the data-manifest identity")
    if boundary.get("development_data_only") is not True:
        failures.append("the authorization does not record development-data-only")
    if boundary.get("provider_requests") != 0:
        failures.append(
            "the authorization does not record that the run makes no provider request"
        )
    development_cutoff = dig(spec_v6, "holdout.development_cutoff_utc")
    if boundary.get("development_cutoff_utc") != development_cutoff:
        failures.append("the authorization does not record the development cutoff")
    if not development_cutoff:
        failures.append("the v6 specification records no development cutoff")
    cutoff_ms = int(
        datetime_from_utc(development_cutoff).timestamp() * 1000
    ) if development_cutoff else 0
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

    # 11. The benchmark rule is bound.
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
    if benchmark.get("btc_configurations_dropped") is not False:
        failures.append("the authorization does not forbid dropping the BTC configurations")
    if benchmark.get("no_forward_fill") is not True:
        failures.append("the authorization does not forbid forward-filling the benchmark")
    if not benchmark.get("fail_closed"):
        failures.append("the authorization records no fail-closed condition")
    if "576" not in str(benchmark.get("grid_rule") or ""):
        failures.append("the authorization does not record the unchanged grid rule")

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
        "authorized_candidates": len(binance_pairs),
        "effective_data_manifest_hash": effective_hash,
        "hashed_set_digest": live_hashed_set,
        "execution_path_digest": live_execution_path,
        "binding_manifest_hash": amends.get("manifest_hash"),
        "binding_file_digest": amends.get("sha256"),
        "authorization_file_digest": authorization_file_digest,
        "authorized_code_hash": identity.get("authorized_code_hash"),
        "authorized_code_hash_status": identity.get("authorized_code_hash_status"),
        "run_code_identity": recomputed_run_identity,
        "environment_facts": environment_facts,
        "failures": failures,
    }


def datetime_from_utc(value: str):
    from datetime import datetime, timezone
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

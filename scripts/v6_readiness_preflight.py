#!/usr/bin/env python3
"""Offline v6 readiness preflight.

This command inspects protocol/configuration JSON and source-tree metadata only.
It deliberately does not open candle CSVs, contact providers, write campaign
state, fetch benchmark data, or authorize/launch a run.

Run from any directory:
    python3 scripts/v6_readiness_preflight.py
    python3 scripts/v6_readiness_preflight.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
PROTECTED_WINDOW_START = "2026-10-22T02:00:00Z"
EVALUATION_NOT_BEFORE = "2027-01-20T02:00:00Z"
MINIMUM_CANDLES = 2160

REQUIRED_PROTOCOLS = {
    "v6_specification": "configs/research_v6.json",
    "candidate_freeze": "configs/research_v6_candidate_freeze.json",
    "execution_protocol": "configs/research_v6_execution.json",
    "execution_amendment": "configs/research_v6_execution_amendment_1.json",
    "selection_authorization": "configs/research_v6_selection_authorization_1.json",
    "confirmatory_protocol": "configs/research_v6_confirmatory_protocol.json",
    "confirmatory_runbook": "configs/research_v6_confirmatory_runbook_1.json",
    "data_manifest": "research/data_manifest_v6.json",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifest_digest(document: Dict[str, Any]) -> str:
    """Recompute a manifest hash using its declared excluded-key rules."""
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = {key: value for key, value in document.items() if key not in excluded}
    for dotted in (key for key in excluded if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {key: value for key, value in body[head].items() if key != tail}
    return hashlib.sha256(canonical(body)).hexdigest()


def source_tree_digest(path: Path) -> Optional[str]:
    """Portable digest of *.py files; returns None for an absent/empty tree."""
    path = Path(path)
    if not path.is_dir():
        return None
    files = sorted(path.rglob("*.py"))
    if not files:
        return None
    digest = hashlib.sha256()
    for file_path in files:
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(hashlib.sha256(file_path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def add(checks: List[Dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def verify_selection_source_binding(
    root: Path, selection: Dict[str, Any], live_selection_digest: Optional[str]
) -> tuple[bool, str]:
    """Verify the versioned implementation binding without editing frozen authorization."""
    if not live_selection_digest:
        return False, "src/v6_campaign is absent or has no Python source"
    auth_relative = "configs/research_v6_selection_authorization_1.json"
    binding_relative = "configs/research_v6_selection_execution_binding_1.json"
    auth_path = Path(root) / auth_relative
    binding_path = Path(root) / binding_relative
    if not auth_path.is_file() or not binding_path.is_file():
        return False, "the frozen selection authorization or its versioned execution binding is missing"
    try:
        auth = load_json(auth_path)
        binding = load_json(binding_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, f"cannot read selection authorization/binding: {exc}"

    auth_hash = manifest_digest(auth)
    if auth.get("manifest_hash") != auth_hash:
        return False, "the v6 selection authorization self-hash does not recompute"
    binding_hash = manifest_digest(binding)
    if binding.get("manifest_hash") != binding_hash:
        return False, "the v6 selection execution binding self-hash does not recompute"
    if binding.get("binding_status") != "IMPLEMENTATION_BOUND_NOT_RUN":
        return False, "the selection binding does not retain its not-run status"
    amends = binding.get("amends") or {}
    if amends.get("path") != auth_relative or amends.get("manifest_hash") != auth_hash:
        return False, "the selection binding is not bound to the live frozen authorization"
    if amends.get("sha256") != hashlib.sha256(auth_path.read_bytes()).hexdigest():
        return False, "the selection binding records another authorization file digest"

    execution = binding.get("execution_path") or {}
    identity = binding.get("code_identity") or {}
    expected_engine_digest = source_tree_digest(Path(root) / "src" / "breakout_research")
    if execution.get("package") != "src/v6_campaign":
        return False, "the binding names another selection execution package"
    if execution.get("canonical_source_digest") != live_selection_digest:
        return False, "the binding does not match the live selection execution source digest"
    if identity.get("execution_path_root") != "src/v6_campaign" or identity.get("execution_path_digest") != live_selection_digest:
        return False, "the binding's composite code identity does not match the live selection source"
    if identity.get("hashed_set_root") != "src/breakout_research" or identity.get("hashed_set_digest") != expected_engine_digest:
        return False, "the binding does not match the live frozen engine digest"
    if identity.get("hashed_set_digest") != (selection.get("authorized_run") or {}).get("code_identity", {}).get("hashed_set_digest"):
        return False, "the binding changes the frozen engine digest recorded by the authorization"

    authority = binding.get("authority") or {}
    if authority.get("single_selection_run_authority_source") != auth_relative:
        return False, "the binding does not retain the frozen authorization as the sole run authority"
    if authority.get("single_selection_run_authority_manifest_hash") != auth_hash or authority.get("max_runs") != 1:
        return False, "the binding does not preserve the original one-run authorization"
    for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "second_v6_selection_run_authorized",
        "amendment_of_a_frozen_artifact_authorized",
        "holdout_reads_authorized",
    ):
        if authority.get(flag) is not False:
            return False, f"the binding improperly grants {flag}"
    return True, f"versioned binding {binding_hash} matches the live selection source and frozen engine"


def verify_confirmatory_scope_contract(
    protocol: Dict[str, Any], runbook: Dict[str, Any]
) -> tuple[bool, str]:
    """Reject the known mismatch between selected-config scope and the runbook's 576-grid sentence."""
    scope = protocol.get("scope") or {}
    scope_rule = str(scope.get("selected_configuration_per_asset") or "")
    if not scope_rule.strip():
        return False, "the frozen confirmatory protocol does not define selected configuration per asset"

    steps = ((runbook.get("operator_procedure") or {}).get("ordered_steps") or [])
    conflicts = []
    for step in steps:
        action = str((step or {}).get("action") or "")
        normalized = " ".join(action.lower().split())
        if (
            "576" in normalized
            and "btc_ema_168" in normalized
            and "per asset" in normalized
            and "evaluated" in normalized
        ):
            conflicts.append(int((step or {}).get("step") or -1))

    if conflicts:
        step_labels = ", ".join(str(value) for value in conflicts)
        return (
            False,
            "protocol scope requires the one selected configuration per eligible asset, "
            f"but confirmatory runbook step(s) {step_labels} also require all 576 "
            "btc_ema_168 configurations per asset to be evaluated; publish and verify "
            "a versioned, hash-bound clarification before implementing or authorizing the executor",
        )
    return True, "no conflict: the frozen protocol and runbook agree on the selected-configuration scope"


# Binance Spot GET /api/v3/klines documents a maximum response limit of 1,000.
# Source: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
BINANCE_KLINES_MAX_LIMIT = 1000


def verify_confirmatory_retrieval_contract(runbook: Dict[str, Any]) -> tuple[bool, str]:
    """Reject a one-response retrieval plan that cannot return the frozen window."""
    applies_to = runbook.get("applies_to") or {}
    operator = runbook.get("operator_procedure") or {}
    retrieval = operator.get("retrieval") or {}
    required = int(applies_to.get("minimum_closed_hourly_candles") or 0)
    if required <= 0:
        return False, "the runbook does not declare a positive closed-hourly candle minimum"

    page_limit = int(retrieval.get("max_candles_per_request") or BINANCE_KLINES_MAX_LIMIT)
    if page_limit <= 0 or page_limit > BINANCE_KLINES_MAX_LIMIT:
        return (
            False,
            f"the declared kline page limit {page_limit} exceeds Binance's documented maximum "
            f"of {BINANCE_KLINES_MAX_LIMIT} candles per response",
        )

    required_pages = (required + page_limit - 1) // page_limit
    declared_pages = retrieval.get("max_pages_per_series")
    if declared_pages is None:
        declared_pages = 1 if retrieval.get("one_request_per_asset") is True else 0
    try:
        declared_pages = int(declared_pages)
    except (TypeError, ValueError):
        return False, "the runbook's maximum pages per series is not an integer"
    if declared_pages < required_pages:
        return (
            False,
            f"the runbook permits {declared_pages} page(s) per series, but {required} closed "
            f"hourly candles require at least {required_pages} responses at the documented "
            f"{page_limit}-candle page limit; publish a versioned, hash-bound pagination clarification",
        )

    if required_pages > 1:
        required_fields = {
            "pagination_cursor": "open_time",
            "deduplicate_by": "open_time",
            "require_contiguous_hourly_coverage": True,
        }
        for key, expected in required_fields.items():
            if retrieval.get(key) != expected:
                return False, f"the paginated retrieval contract does not explicitly bind {key}={expected!r}"
    return True, (
        f"retrieval allows {declared_pages} bounded page(s) per series; at least "
        f"{required_pages} are required for {required} closed hourly candles"
    )


def run_preflight(root: Path = ROOT) -> Dict[str, Any]:
    """Return a fail-closed readiness report without reading market candles."""
    root = Path(root)
    checks: List[Dict[str, str]] = []
    docs: Dict[str, Dict[str, Any]] = {}

    for name, relative in REQUIRED_PROTOCOLS.items():
        path = root / relative
        if not path.is_file():
            add(checks, name, "BLOCKED_ENGINEERING", f"missing {relative}")
            continue
        try:
            docs[name] = load_json(path)
            add(checks, name, "PASS", f"present: {relative}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            add(checks, name, "BLOCKED_ENGINEERING", f"unreadable {relative}: {exc}")

    # Verify all self-hashing protocol artifacts that publish manifest_hash.
    for name, document in docs.items():
        declared = document.get("manifest_hash")
        if declared is not None:
            actual = manifest_digest(document)
            add(checks, f"{name}_manifest_hash",
                "PASS" if declared == actual else "BLOCKED_INTEGRITY",
                "manifest hash recomputes" if declared == actual else f"declared {declared}; recomputed {actual}")

    spec = docs.get("v6_specification", {})
    freeze = docs.get("candidate_freeze", {})
    protocol = docs.get("confirmatory_protocol", {})
    runbook = docs.get("confirmatory_runbook", {})
    selection = docs.get("selection_authorization", {})
    amendment = docs.get("execution_amendment", {})
    data = docs.get("data_manifest", {})

    scope_contract_ok, scope_contract_detail = verify_confirmatory_scope_contract(
        protocol, runbook
    )
    add(
        checks,
        "confirmatory_scope_contract",
        "PASS" if scope_contract_ok else "BLOCKED_PROTOCOL_CONFLICT",
        scope_contract_detail,
    )

    retrieval_contract_ok, retrieval_contract_detail = verify_confirmatory_retrieval_contract(
        runbook
    )
    add(
        checks,
        "confirmatory_retrieval_contract",
        "PASS" if retrieval_contract_ok else "BLOCKED_PROTOCOL_CONFLICT",
        retrieval_contract_detail,
    )

    # The frozen scientific boundary is asserted, never edited here.
    window = freeze.get("confirmatory_window") or {}
    expected_window = (
        window.get("opens_utc") == PROTECTED_WINDOW_START
        and window.get("earliest_possible_end_utc") == EVALUATION_NOT_BEFORE
        and int(window.get("min_hours", -1)) == MINIMUM_CANDLES
    )
    protocol_window = protocol.get("window_definition") or {}
    expected_window = expected_window and (
        protocol_window.get("window_opens_utc") == PROTECTED_WINDOW_START
        and protocol_window.get("earliest_possible_end_utc") == EVALUATION_NOT_BEFORE
        and int(protocol_window.get("minimum_closed_hourly_candles", -1)) == MINIMUM_CANDLES
        and protocol_window.get("single_use") is True
    )
    add(checks, "frozen_confirmatory_boundary", "PASS" if expected_window else "BLOCKED_INTEGRITY",
        "2160 closed hourly candles; 2026-10-22 02:00 UTC start; no evaluation before 2027-01-20 02:00 UTC"
        if expected_window else "frozen protocol/freeze differs from the required boundary")

    # Confirm no run/evaluation authority is accidentally enabled by the amendment.
    auth = amendment.get("execution_authorization") or {}
    authority_keys = ("candle_fetch_authorized", "confirmatory_evaluation_authorized",
                      "execution_authorized", "grid_run_authorized", "second_run_authorized")
    all_false = all(auth.get(key) is False for key in authority_keys)
    add(checks, "no_implicit_execution_authority", "PASS" if all_false else "BLOCKED_AUTHORITY",
        "all execution/fetch/evaluation flags remain false" if all_false
        else "one or more execution/fetch/evaluation flags are not explicitly false")

    # Selection runner and confirmatory runner are separate, versioned source trees.
    selection_root = root / "src" / "v6_campaign"
    confirm_root = root / "src" / "v6_confirmatory"
    selection_digest = source_tree_digest(selection_root)
    confirm_digest = source_tree_digest(confirm_root)
    add(checks, "selection_runner", "PASS" if selection_digest else "BLOCKED_ENGINEERING",
        f"source digest {selection_digest}" if selection_digest else "src/v6_campaign is absent or contains no Python source")
    add(checks, "confirmatory_runner", "PASS" if confirm_digest else "BLOCKED_ENGINEERING",
        f"source digest {confirm_digest}" if confirm_digest else "src/v6_confirmatory is absent or contains no Python source")

    # Execution code must remain outside the immutable engine tree.
    hashed_root = (root / "src" / "breakout_research").resolve()
    paths_outside = all(
        not path.resolve().is_relative_to(hashed_root)
        for path in (selection_root, confirm_root)
    )
    add(checks, "execution_code_isolated", "PASS" if paths_outside else "BLOCKED_INTEGRITY",
        "both execution paths are outside src/breakout_research" if paths_outside
        else "an execution path is inside the frozen engine tree")

    # Verify the versioned implementation binding. The frozen selection authorization
    # remains unchanged and continues to be the sole source of run authority.
    selection_bound, selection_binding_detail = verify_selection_source_binding(
        root, selection, selection_digest
    )
    add(checks, "selection_source_binding",
        "PASS" if selection_bound else "BLOCKED_AUTHORITY",
        selection_binding_detail)

    publisher_path = root / "scripts" / "publish_v6_selected_configurations.py"
    publisher_present = publisher_path.is_file()
    add(checks, "selection_manifest_publisher",
        "PASS" if publisher_present else "BLOCKED_ENGINEERING",
        "post-selection hash-bound manifest publisher is present" if publisher_present
        else "scripts/publish_v6_selected_configurations.py is missing")

    # Confirmatory selected configs and authorization must exist and self-hash.
    selected_path = root / "research" / "v6_selected_configurations_manifest.json"
    selected_ok = False
    if selected_path.is_file():
        try:
            selected_doc = load_json(selected_path)
            selected_ok = selected_doc.get("manifest_hash") == manifest_digest(selected_doc)
        except (OSError, ValueError, json.JSONDecodeError):
            selected_ok = False
    add(checks, "selected_configurations_manifest",
        "PASS" if selected_ok else "BLOCKED_EXTERNAL",
        "present and self-hashing" if selected_ok else "selection output manifest is not yet published/self-hashing")

    confirm_auth_path = root / "configs" / "research_v6_confirmatory_authorization_1.json"
    confirm_auth_ok = False
    if confirm_auth_path.is_file():
        try:
            confirm_auth_doc = load_json(confirm_auth_path)
            confirm_auth_ok = confirm_auth_doc.get("manifest_hash") == manifest_digest(confirm_auth_doc)
        except (OSError, ValueError, json.JSONDecodeError):
            confirm_auth_ok = False
    add(checks, "confirmatory_authorization",
        "PASS" if confirm_auth_ok else "NOT_AUTHORIZED",
        "published and self-hashing" if confirm_auth_ok
        else "separate explicit confirmatory authorization has not been published")

    # The future window benchmark must be a distinct dataset. This check reads
    # only JSON metadata and tests path existence; it never opens a candle file.
    benchmark = ((protocol.get("data_path") or {}).get("benchmark") or {})
    benchmark_path_value = benchmark.get("window_benchmark_dataset_path")
    benchmark_exists = bool(benchmark_path_value and (root / str(benchmark_path_value)).is_file())
    add(checks, "confirmatory_benchmark",
        "PASS" if benchmark_exists else "BLOCKED_EXTERNAL",
        f"window benchmark file exists: {benchmark_path_value}" if benchmark_exists
        else "window benchmark series is not yet published; development BTC series is not a substitute")

    exposure = data.get("holdout_exposed_count", 0)
    add(checks, "holdout_exposure_counter",
        "PASS" if exposure == 0 else "BLOCKED_INTEGRITY",
        "zero exposure recorded" if exposure == 0 else f"expected zero pre-run exposure; found {exposure}")

    # This report intentionally does not open any dataset file or initiate a run.
    blocked = [item for item in checks if item["status"].startswith(("BLOCKED", "NOT_AUTHORIZED"))]
    engineering_names = {"selection_runner", "selection_manifest_publisher", "confirmatory_runner", "execution_code_isolated"}
    engineering_ready = all(
        item["status"] == "PASS" for item in checks if item["name"] in engineering_names
    )
    data_ready = all(item["status"] == "PASS" for item in checks if item["name"] == "confirmatory_benchmark")
    authorization_ready = all(
        item["status"] == "PASS" for item in checks
        if item["name"] in {"selection_source_binding", "confirmatory_authorization", "no_implicit_execution_authority"}
    )
    return {
        "report_version": "v6-readiness-preflight-1",
        "mode": "READ_ONLY_METADATA_PREFLIGHT_NO_CANDLE_READS",
        "evaluation_target_utc": EVALUATION_NOT_BEFORE,
        "minimum_closed_hourly_candles": MINIMUM_CANDLES,
        "engineering_ready": engineering_ready,
        "data_ready": data_ready,
        "authorization_ready": authorization_ready,
        "confirmatory_scope_ready": scope_contract_ok,
        "confirmatory_retrieval_ready": retrieval_contract_ok,
        "evaluation_eligible": (
            not blocked and engineering_ready and data_ready and authorization_ready
            and scope_contract_ok and retrieval_contract_ok
        ),
        "holdout_reads_performed": 0,
        "run_started": False,
        "checks": checks,
        "blocker_count": len(blocked),
        "next_action": "Resolve listed engineering/data prerequisites; obtain separate explicit authorization only after selection outputs and code identities are frozen."
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)
    report = run_preflight()
    print(json.dumps(report, indent=None if args.json else 2, sort_keys=True))
    return 0 if report["evaluation_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

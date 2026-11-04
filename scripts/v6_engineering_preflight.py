#!/usr/bin/env python3
"""Read-only engineering/data/authorization preflight for the v6 campaign.

This command reads protocol and manifest metadata only. It never opens a
confirmatory candle, retrieves market data, increments exposure, starts a
selection run, or starts an evaluation.

Run:
    python3 scripts/v6_engineering_preflight.py
    python3 scripts/v6_engineering_preflight.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
HOUR = timedelta(hours=1)

FILES = {
    "spec": "configs/research_v6.json",
    "freeze": "configs/research_v6_candidate_freeze.json",
    "protocol": "configs/research_v6_confirmatory_protocol.json",
    "runbook": "configs/research_v6_confirmatory_runbook_1.json",
    "selection_authorization": "configs/research_v6_selection_authorization_1.json",
    "execution": "configs/research_v6_execution.json",
    "execution_amendment": "configs/research_v6_execution_amendment_1.json",
    "universe": "research/universe_manifest_v6.json",
    "data": "research/data_manifest_v6.json",
    "selected_manifest": "research/v6_selected_configurations_manifest.json",
    "confirmatory_authorization": "configs/research_v6_confirmatory_authorization_1.json",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def self_hash(document: Dict[str, Any]) -> str:
    hashing = document.get("hashing") or {}
    excluded = tuple(hashing.get("manifest_hash_excluded_keys") or hashing.get("excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        if "." not in key:
            body.pop(key, None)
        else:
            head, _, tail = key.partition(".")
            if isinstance(body.get(head), dict):
                body[head] = dict(body[head])
                body[head].pop(tail, None)
    return sha256_bytes(canonical(body))


def parse_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def check(report: Dict[str, Any], name: str, status: str, detail: str, **extra: Any) -> None:
    report["checks"].append({"name": name, "status": status, "detail": detail, **extra})


def _load_documents(root: Path, report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    documents: Dict[str, Dict[str, Any]] = {}
    for name, relative in FILES.items():
        path = root / relative
        if not path.is_file():
            status = "NOT_AUTHORIZED" if name == "confirmatory_authorization" else "BLOCKED_ENGINEERING"
            check(report, f"artifact:{name}", status, f"required artifact is not published: {relative}")
            continue
        try:
            documents[name] = read_json(path)
        except (OSError, ValueError) as error:
            check(report, f"artifact:{name}", "BLOCKED_ENGINEERING", f"cannot parse {relative}: {error}")
    return documents


def build_report(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    report: Dict[str, Any] = {
        "artifact": "v6_engineering_readiness",
        "artifact_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "confirmatory_candles_opened": False,
        "provider_requests": 0,
        "selection_started": False,
        "confirmatory_evaluation_started": False,
        "checks": [],
        "window": {},
        "summary": {},
    }
    docs = _load_documents(root, report)

    # Verify the metadata chain. These checks only parse small JSON documents.
    for name in ("spec", "freeze", "protocol", "runbook", "selection_authorization",
                 "execution_amendment", "universe", "data"):
        document = docs.get(name)
        if document is None:
            continue
        declared = document.get("specification_hash") if name == "spec" else document.get("manifest_hash")
        computed = self_hash(document)
        check(report, f"hash:{name}", "PASS" if declared == computed else "BLOCKED_ENGINEERING",
              "self-hash recomputes" if declared == computed else f"self-hash mismatch: declared={declared}, computed={computed}")

    spec = docs.get("spec")
    freeze = docs.get("freeze")
    protocol = docs.get("protocol")
    runbook = docs.get("runbook")
    selection_auth = docs.get("selection_authorization")
    amendment = docs.get("execution_amendment")
    data = docs.get("data")

    if spec and freeze and protocol and runbook:
        try:
            start = parse_utc((freeze.get("confirmatory_window") or {})["opens_utc"])
            minimum = int((freeze.get("confirmatory_window") or {})["min_hours"])
            frozen_end = parse_utc((freeze.get("confirmatory_window") or {})["earliest_possible_end_utc"])
            # Candle closes are hourly instants. Start and end are both strict
            # in the registered membership rule. The first eligible close is
            # start+1h, so 2160 eligible closes require an exclusive end of
            # start+(2160+1)h.
            first_eligible_close = start + HOUR
            last_required_close = start + HOUR * minimum
            # Close timestamps are strict at both ends. The last required close is
            # start + 2160h; the exclusive boundary is one hour later. Evaluation
            # may begin immediately when that final candle closes.
            required_exclusive_end = last_required_close + HOUR
            required_evaluation_start = last_required_close
            prior_gates = [
                parse_utc(str(gate["earliest_possible_end_utc"]))
                for gate in (freeze.get("confirmatory_window") or {}).get("gates", [])
                if gate.get("earliest_possible_end_utc")
            ]
            effective_gate = max([required_evaluation_start, *prior_gates])
            rule = (spec.get("holdout") or {}).get("confirmatory_window_membership") or {}
            strict_start = rule.get("interval_start_inclusive") is False
            strict_end = rule.get("interval_end_exclusive") is True
            interval_hours = int((frozen_end - start).total_seconds() // 3600)
            eligible_close_count = max(0, interval_hours - 1) if strict_start and strict_end else interval_hours
            runbook_bounds = runbook.get("applies_to") or {}
            runbook_end = parse_utc(str(runbook_bounds.get("window_end_utc")))
            report["window"] = {
                "opens_utc": start.isoformat().replace("+00:00", "Z"),
                "minimum_closed_hourly_candles": minimum,
                "first_eligible_close_utc": first_eligible_close.isoformat().replace("+00:00", "Z"),
                "last_required_close_utc": last_required_close.isoformat().replace("+00:00", "Z"),
                "minimum_exclusive_end_utc": required_exclusive_end.isoformat().replace("+00:00", "Z"),
                "minimum_evaluation_start_utc": required_evaluation_start.isoformat().replace("+00:00", "Z"),
                "freeze_earliest_end_utc": frozen_end.isoformat().replace("+00:00", "Z"),
                "runbook_window_end_utc": runbook_end.isoformat().replace("+00:00", "Z"),
                "eligible_closes_with_frozen_end": eligible_close_count,
                "effective_gate_including_prior_windows_utc": effective_gate.isoformat().replace("+00:00", "Z"),
            }
            valid_window = eligible_close_count >= minimum and runbook_end >= required_exclusive_end
            check(report, "window:closed_candle_count",
                  "PASS" if valid_window else "BLOCKED_PROTOCOL_INCONSISTENCY",
                  (f"frozen interval yields {eligible_close_count} eligible candle closes; {minimum} required"
                   if not valid_window else f"at least {minimum} eligible closes fit inside the exclusive window end"),
                  eligible_closes=eligible_close_count, required=minimum)
            if frozen_end < required_exclusive_end or runbook_end < required_exclusive_end:
                check(report, "window:one_hour_boundary",
                      "BLOCKED_PROTOCOL_INCONSISTENCY",
                      "strict close-time membership requires an exclusive close-time bound one hour after the 2,160th eligible close; retain the evaluation gate at the last close and publish a versioned correction (do not edit frozen artifacts in place)",
                      required_exclusive_end_utc=required_exclusive_end.isoformat().replace("+00:00", "Z"),
                      earliest_evaluation_start_utc=required_evaluation_start.isoformat().replace("+00:00", "Z"))
            else:
                check(report, "window:one_hour_boundary", "PASS", "strict close-time boundary includes the full registered sample")
            declared_protocol_gate = parse_utc(str((protocol.get("window_definition") or {}).get("evaluation_may_not_start_before_utc")))
            declared_runbook_gate = parse_utc(str(runbook_bounds.get("evaluation_may_not_start_before_utc")))
            gate_ok = (declared_protocol_gate >= effective_gate and declared_runbook_gate >= effective_gate
                       and declared_protocol_gate >= required_evaluation_start
                       and declared_runbook_gate >= required_evaluation_start)
            check(report, "window:prior_gates", "PASS" if gate_ok else "BLOCKED_PROTOCOL_INCONSISTENCY",
                  "protocol and operator runbook respect the later of the sample end and earlier-version gates" if gate_ok else
                  "protocol/runbook evaluation gate is earlier than the computed effective gate",
                  computed_gate_utc=effective_gate.isoformat().replace("+00:00", "Z"))
        except (KeyError, TypeError, ValueError) as error:
            check(report, "window:definition", "BLOCKED_ENGINEERING", f"cannot derive frozen window bounds: {error}")

    # Source identity checks do not load data files or read confirmatory candles.
    selection_root = root / "src" / "v6_campaign"
    confirmatory_root = root / "src" / "v6_confirmatory"
    check(report, "engineering:selection_path", "PASS" if (selection_root / "runner.py").is_file()
          else "BLOCKED_ENGINEERING", "v6 selection runner exists" if (selection_root / "runner.py").is_file()
          else "src/v6_campaign/runner.py is missing")
    check(report, "engineering:confirmatory_path", "PASS" if (confirmatory_root / "runner.py").is_file()
          else "BLOCKED_ENGINEERING", "v6 confirmatory runner exists" if (confirmatory_root / "runner.py").is_file()
          else "src/v6_confirmatory/runner.py is missing")

    # The identity check is intentionally performed without importing the run path,
    # whose code is separately included in the digest.
    if selection_auth and selection_root.is_dir():
        source_digest = canonical_tree_digest(selection_root)
        recorded = (selection_auth.get("authorized_run") or {}).get("code_identity") or {}
        bound = recorded.get("execution_path_digest")
        check(report, "authorization:selection_source_digest",
              "PASS" if bound == source_digest else "BLOCKED_AUTHORIZATION_AMENDMENT",
              "selection execution path digest matches the hash-bound authorization" if bound == source_digest
              else "the current path digest is not bound by selection authorization 1; publish a versioned selection-authorization amendment",
              recorded_digest=bound, computed_digest=source_digest)
    elif selection_auth:
        check(report, "authorization:selection_source_digest", "BLOCKED_ENGINEERING",
              "selection source path is not present")

    if runbook:
        binding = runbook.get("binding_identities") or {}
        selected_path = root / str((binding.get("selected_configurations_manifest") or {}).get("path") or FILES["selected_manifest"])
        check(report, "authorization:selected_manifest",
              "PASS" if selected_path.is_file() else "NOT_AUTHORIZED",
              "selected configurations manifest is published" if selected_path.is_file()
              else "selection results have not yet been published; no confirmatory candidate set is bound")
        auth_path = root / str((binding.get("authorization") or {}).get("path") or FILES["confirmatory_authorization"])
        check(report, "authorization:confirmatory",
              "PASS" if auth_path.is_file() else "NOT_AUTHORIZED",
              "separate confirmatory authorization exists" if auth_path.is_file()
              else "no confirmatory authorization exists; engineering must not create/infer user approval")
        code_id = (binding.get("code_identity") or {})
        code_digest = code_id.get("execution_path_digest")
        actual_confirmatory_digest = canonical_tree_digest(confirmatory_root) if confirmatory_root.is_dir() else None
        check(report, "authorization:confirmatory_source_digest",
              "PASS" if actual_confirmatory_digest and code_digest == actual_confirmatory_digest else "BLOCKED_AUTHORIZATION_AMENDMENT",
              "confirmatory execution path digest is bound" if actual_confirmatory_digest and code_digest == actual_confirmatory_digest
              else "the confirmatory runner digest is absent or not bound by a versioned confirmatory authorization",
              recorded_digest=code_digest, computed_digest=actual_confirmatory_digest)

    if data:
        exposure = data.get("confirmatory_window") or {}
        exposed = int(exposure.get("holdout_exposed_count") or 0)
        check(report, "safety:holdout_exposure_counter", "PASS" if exposed == 0 else "BLOCKED_SAFETY",
              f"recorded holdout exposure count is {exposed}", holdout_exposed_count=exposed)
        check(report, "safety:no_window_reads", "PASS" if exposure.get("confirmatory_window_status") == "NOT_STARTED" and exposed == 0 else "BLOCKED_SAFETY",
              "manifest records no confirmatory read" if exposure.get("confirmatory_window_status") == "NOT_STARTED" and exposed == 0
              else "confirmatory exposure is already recorded; reconcile before any further access")
    else:
        check(report, "safety:holdout_exposure_counter", "BLOCKED_ENGINEERING", "v6 data manifest is unavailable")

    report["summary"] = {
        "ready_for_selection": False,
        "ready_for_confirmatory_evaluation": False,
        "target_date": "2027-01-20",
        "effective_earliest_evaluation_utc": report["window"].get("effective_gate_including_prior_windows_utc"),
        "blocked_checks": [c["name"] for c in report["checks"] if c["status"] != "PASS"],
        "confirmatory_window_accessed": False,
        "next_required_action": "complete implementation and versioned identity binding; publish selected configurations; separately authorize and retrieve the confirmatory window only after the complete readiness gate passes",
    }
    return report


def canonical_tree_digest(base: Path) -> str:
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"
")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"
")
    return digest.hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    report = build_report(Path(args.repo_root))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("V6 engineering readiness (read-only; no confirmatory candle opened)")
        for item in report["checks"]:
            print(f"[{item['status']}] {item['name']}: {item['detail']}")
        print(json.dumps(report["summary"], indent=2))
    return 0 if all(item["status"] == "PASS" for item in report["checks"]) else 2


if __name__ == "__main__":
    sys.exit(main())

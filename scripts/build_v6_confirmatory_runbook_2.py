#!/usr/bin/env python3
"""Build a versioned v6 confirmatory runbook correcting the strict end boundary.

The frozen freeze/protocol/runbook-1 remain untouched. The 2,160th candle closes
at 2027-01-20T02:00:00Z. The protocol's strict close-time predicate therefore
needs an exclusive close-time bound of 03:00Z, while evaluation can begin at
02:00Z. Default mode prints; --write creates the successor artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "configs/research_v6_confirmatory_runbook_1.json"
TARGET = "configs/research_v6_confirmatory_runbook_2.json"
SELECTED = "research/v6_selected_configurations_manifest.json"
SELECTION_AUTH = "configs/research_v6_selection_authorization_2.json"
EXECUTION_ROOT = "src/v6_confirmatory"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def artifact_hash(document: Dict[str, Any]) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        if "." not in key:
            body.pop(key, None)
    return sha256_bytes(canonical(body))


def source_digest(root: Path) -> str:
    base = root / EXECUTION_ROOT
    files = sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py"))
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def build(root: Path = ROOT) -> Dict[str, Any]:
    source_path = root / SOURCE
    runbook = json.loads(source_path.read_text(encoding="utf-8"))
    if artifact_hash(runbook) != runbook.get("manifest_hash"):
        raise SystemExit("runbook 1 self-hash does not verify")
    spec = json.loads((root / "configs/research_v6.json").read_text(encoding="utf-8"))
    freeze = json.loads((root / "configs/research_v6_candidate_freeze.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "configs/research_v6_confirmatory_protocol.json").read_text(encoding="utf-8"))
    start = datetime.fromisoformat(freeze["confirmatory_window"]["opens_utc"].replace("Z", "+00:00"))
    minimum = int(freeze["confirmatory_window"]["min_hours"])
    evaluation_start = start + timedelta(hours=minimum)
    exclusive_end = evaluation_start + timedelta(hours=1)
    if evaluation_start.isoformat().replace("+00:00", "Z") != "2027-01-20T02:00:00Z":
        raise SystemExit("the computed evaluation start no longer matches the frozen v6 date")
    if spec["holdout"]["confirmatory_window_membership"]["interval_start_inclusive"] is not False:
        raise SystemExit("strict close-time start membership is not frozen as expected")
    if spec["holdout"]["confirmatory_window_membership"]["interval_end_exclusive"] is not True:
        raise SystemExit("strict close-time end membership is not frozen as expected")

    result = json.loads(json.dumps(runbook))
    result["artifact_version"] = "v6-confirmatory-runbook-2"
    result["supersedes"] = {
        "path": SOURCE,
        "manifest_hash": runbook["manifest_hash"],
        "sha256": file_hash(source_path),
        "reason": "separate the last required candle close from the exclusive close-time window boundary",
    }
    applies = result["applies_to"]
    applies["evaluation_start_utc"] = evaluation_start.isoformat().replace("+00:00", "Z")
    applies["window_end_utc"] = exclusive_end.isoformat().replace("+00:00", "Z")
    applies["evaluation_window_rule"] = (
        "The 2,160 eligible hourly candles are selected by strict candle-close membership: "
        "window_start_utc < candle_close_utc < window_end_utc. The 2,160th candle closes at "
        "2027-01-20T02:00:00Z; the exclusive close-time bound is 2027-01-20T03:00:00Z. "
        "Evaluation may begin at 2027-01-20T02:00:00Z, once that final candle is closed. "
        "No candle is read before the independent readiness and authorization gates pass."
    )
    applies["membership_rule"] = "strict_close_time_after_start_and_before_exclusive_end"
    applies["earliest_evaluation_start_utc"] = evaluation_start.isoformat().replace("+00:00", "Z")
    applies["exclusive_close_end_utc"] = exclusive_end.isoformat().replace("+00:00", "Z")

    selected_path = root / SELECTED
    selection_auth_path = root / SELECTION_AUTH
    if not selected_path.is_file() or not selection_auth_path.is_file():
        raise SystemExit("selection has not completed: selected-configurations manifest and versioned selection authorization are required")
    selected_manifest = json.loads(selected_path.read_text(encoding="utf-8"))
    selection_auth = json.loads(selection_auth_path.read_text(encoding="utf-8"))
    if artifact_hash(selected_manifest) != selected_manifest.get("manifest_hash"):
        raise SystemExit("selected-configurations manifest self-hash does not verify")
    if artifact_hash(selection_auth) != selection_auth.get("manifest_hash"):
        raise SystemExit("selection authorization 2 self-hash does not verify")

    binding = result["binding_identities"]
    binding["confirmatory_protocol"]["manifest_hash"] = protocol["manifest_hash"]
    binding["selected_configurations_manifest"] = {
        "path": SELECTED,
        "manifest_hash": selected_manifest["manifest_hash"],
        "status": "PUBLISHED_HASH_VERIFIED",
    }
    binding["selection_authorization_2"] = {
        "path": SELECTION_AUTH,
        "manifest_hash": selection_auth["manifest_hash"],
    }
    applies["in_scope_configurations"] = {
        asset: entry.get("config_id")
        for asset, entry in sorted((selected_manifest.get("selections") or {}).items())
        if entry.get("selected") is True
    }
    binding["code_identity"] = dict(binding["code_identity"])
    binding["code_identity"].update({
        "execution_path_digest": source_digest(root),
        "execution_path_status": "IMPLEMENTED_AND_DIGESTED",
        "execution_path_root": EXECUTION_ROOT,
        "algorithm_description": (
            "sha256 over the concatenation, for every *.py file under the root in "
            "ascending POSIX relative-path order, of the relative path, a newline, "
            "the sha256 hex digest of the file bytes, and a newline."
        ),
    })
    binding["code_identity"]["note"] = (
        "The execution-path digest is computed from the current src/v6_confirmatory tree. "
        "Any subsequent source change requires a new versioned code-hash amendment and "
        "authorization binding before the confirmatory run."
    )
    result["verification"] = dict(result.get("verification") or {})
    commands = list(result["verification"].get("verification_commands") or [])
    for command in (
        "python3 scripts/v6_engineering_preflight.py",
        "python3 scripts/verify_v6_confirmatory_runbook_2.py",
        "PYTHONPATH=src python3 -m pytest tests/test_v6_confirmatory_window_boundary.py tests/test_v6_engineering_preflight.py -q",
    ):
        if command not in commands:
            commands.append(command)
    result["verification"]["verification_commands"] = commands
    result["created_utc"] = "2026-11-04T00:00:00Z"
    result.setdefault("hashing", {})["manifest_hash_excluded_keys"] = ["manifest_hash"]
    result["manifest_hash"] = ""
    result["manifest_hash"] = artifact_hash(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write versioned runbook 2")
    args = parser.parse_args()
    result = build()
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        target = ROOT / TARGET
        if target.exists():
            raise SystemExit(f"refusing to overwrite {TARGET}")
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {TARGET} manifest_hash={result['manifest_hash']}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

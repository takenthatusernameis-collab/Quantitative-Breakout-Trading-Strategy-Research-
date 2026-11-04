#!/usr/bin/env python3
"""Build the single v6 confirmatory authorization.

Default output is an unauthorized draft. It cannot start retrieval or evaluation.
Only the separate --authorize --write invocation publishes an authorized artifact.
The script never retrieves market data, reads a confirmatory candle or runs an
evaluation.

Prerequisites:
  - the v6 selection run has completed and its selected-configurations manifest
    has been published and independently hash-verified;
  - runbook 2 and the confirmatory protocol verify;
  - confirmatory runner source is final, digested and reviewed;
  - all frozen artifact anchors are present and unchanged.

Examples:
  python3 scripts/build_v6_confirmatory_authorization_1.py
  python3 scripts/build_v6_confirmatory_authorization_1.py --write
  python3 scripts/build_v6_confirmatory_authorization_1.py --authorize --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v6_confirmatory.identity import (  # noqa: E402
    canonical_source_digest,
    run_code_identity,
    hashed_set_digest,
    execution_path_digest,
)
from v6_confirmatory.runner import (  # noqa: E402
    DEFAULT_PATHS,
    FORBIDDEN_OUTPUT_PATHS,
    FAIL_CLOSED_REASONS,
    MIN_WINDOW_HOURS,
)
from v6_confirmatory.window import window_bounds  # noqa: E402

TARGET = "configs/research_v6_confirmatory_authorization_1.json"
PROTOCOL = "configs/research_v6_confirmatory_protocol.json"
RUNBOOK = "configs/research_v6_confirmatory_runbook_2.json"
SELECTION_MANIFEST = "research/v6_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION = "configs/research_v6_selection_authorization_2.json"
FREEZE = "configs/research_v6_candidate_freeze.json"
DATA_MANIFEST = "research/data_manifest_v6.json"
UNIVERSE_MANIFEST = "research/universe_manifest_v6.json"
SPEC_V1 = "configs/research_v1.json"
SPEC_V6 = "configs/research_v6.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(root: Path, relative: str) -> Dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise SystemExit(f"required prerequisite is missing: {relative}")
    return json.loads(path.read_text(encoding="utf-8"))


def self_hash(document: Dict[str, Any]) -> str:
    excluded = tuple(
        (document.get("hashing") or {}).get("manifest_hash_excluded_keys")
        or (document.get("hashing") or {}).get("excluded_keys")
        or ("manifest_hash",)
    )
    body = dict(document)
    for key in excluded:
        parts = str(key).split(".")
        cursor = body
        for part in parts[:-1]:
            if not isinstance(cursor.get(part), dict):
                cursor = None
                break
            cursor = cursor[part]
        if cursor is not None:
            cursor.pop(parts[-1], None)
    return sha256_bytes(canonical(body))


def anchor_group(root: Path, paths: list[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"required immutable artifact is missing: {relative}")
        result[relative] = file_hash(path)
    return result


def build(root: Path = ROOT, *, authorize: bool = False) -> Dict[str, Any]:
    protocol = load_json(root, PROTOCOL)
    runbook = load_json(root, RUNBOOK)
    freeze = load_json(root, FREEZE)
    data_manifest = load_json(root, DATA_MANIFEST)
    universe = load_json(root, UNIVERSE_MANIFEST)
    spec_v1 = load_json(root, SPEC_V1)
    spec_v6 = load_json(root, SPEC_V6)
    selection_auth = load_json(root, SELECTION_AUTHORIZATION)
    selected = load_json(root, SELECTION_MANIFEST)

    for name, document, key in (
        ("protocol", protocol, "manifest_hash"),
        ("runbook", runbook, "manifest_hash"),
        ("freeze", freeze, "manifest_hash"),
        ("data manifest", data_manifest, "manifest_hash"),
        ("universe manifest", universe, "manifest_hash"),
        ("selection authorization", selection_auth, "manifest_hash"),
    ):
        if document.get(key) != self_hash(document):
            raise SystemExit(f"{name} self-hash does not verify")
    if spec_v6.get("specification_hash") != self_hash(spec_v6):
        raise SystemExit("v6 specification self-hash does not verify")
    if selected.get("manifest_hash") != self_hash(selected):
        raise SystemExit("selected-configurations manifest self-hash does not verify")
    if (selected.get("run_identity") or {}).get("authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        raise SystemExit("selected-configurations manifest is not bound to selection authorization 2")
    if (runbook.get("binding_identities") or {}).get("selected_configurations_manifest", {}).get("manifest_hash") != selected.get("manifest_hash"):
        raise SystemExit("runbook 2 is not bound to the current selected-configurations manifest")

    window = runbook["applies_to"]
    bounds = window_bounds(window["window_start_utc"], MIN_WINDOW_HOURS)
    if window.get("evaluation_start_utc") != bounds["earliest_end_utc"]:
        raise SystemExit("runbook evaluation start does not equal the exact 2,160th candle close")
    if window.get("window_end_utc") != bounds["exclusive_close_end_utc"]:
        raise SystemExit("runbook exclusive close-time endpoint is inconsistent")
    if window.get("minimum_closed_hourly_candles") != MIN_WINDOW_HOURS:
        raise SystemExit("runbook does not preserve the 2,160-candle minimum")
    if window.get("membership_rule") != "strict_close_time_after_start_and_before_exclusive_end":
        raise SystemExit("runbook does not bind strict close-time membership")

    selections = selected.get("selections") or {}
    expected_assets = sorted(asset for asset, entry in selections.items() if entry.get("selected") is True)
    if not expected_assets:
        raise SystemExit("the selection manifest contains no selected candidate; there is nothing to authorize")
    if expected_assets != sorted(window.get("in_scope_assets") or []):
        raise SystemExit("selected assets differ from the frozen runbook scope")
    config_ids = {
        asset: str(selections[asset].get("config_id") or "")
        for asset in expected_assets
    }
    if any(not value for value in config_ids.values()):
        raise SystemExit("one or more selected assets has no frozen configuration id")

    hashed_digest = hashed_set_digest(root)
    if hashed_digest != (runbook.get("binding_identities") or {}).get("code_identity", {}).get("hashed_set_digest"):
        raise SystemExit("the hashed v1 engine differs from the v6 runbook anchor")
    confirmatory_digest = execution_path_digest(root)
    run_identity = run_code_identity(hashed_digest, confirmatory_digest)
    if confirmatory_digest != (runbook.get("binding_identities") or {}).get("code_identity", {}).get("execution_path_digest"):
        raise SystemExit("the confirmatory source digest differs from runbook 2; publish a versioned code-hash correction")

    v1_anchors = anchor_group(root, [
        SPEC_V1,
        "research/universe_manifest.json",
        "research/data_manifest.json",
        "research/candidate_manifest.json",
    ])
    v5_anchors = anchor_group(root, [
        "configs/research_v5.json",
        "research/universe_manifest_v5.json",
        "research/data_manifest_v5.json",
        "configs/research_v5_candidate_freeze.json",
        "configs/research_v5_execution.json",
    ])
    v6_anchors = anchor_group(root, [
        SPEC_V6,
        UNIVERSE_MANIFEST,
        DATA_MANIFEST,
        FREEZE,
        "configs/research_v6_execution.json",
        "configs/research_v6_execution_amendment_1.json",
        "configs/research_v6_execution_amendment_2.json",
        PROTOCOL,
        RUNBOOK,
        SELECTION_AUTHORIZATION,
        SELECTION_MANIFEST,
        "research/ledger_v6.json",
        "research/results_manifest_v6.json",
        "research/results_v6.jsonl",
        "research_state/checkpoint_v6.json",
    ])

    selected_hash = selected["manifest_hash"]
    paths = dict(DEFAULT_PATHS)
    paths["authorization"] = TARGET
    paths["selected_configurations"] = SELECTION_MANIFEST
    forbidden = list(FORBIDDEN_OUTPUT_PATHS)
    criteria = list((runbook.get("binding_identities") or {}).get("decision_rule", {}).get("criteria") or [])
    if len(criteria) != 4:
        raise SystemExit("the inherited v1 promotion rule is not the expected four-part rule")
    decision_rule = {
        "criterion_count": 1,
        "authoritative_source": "configs/research_v1.json#selection",
        "criteria": criteria,
        "exactly_one_criterion": True,
        "no_competing_criterion": True,
        "status_vocabulary": list((runbook.get("binding_identities") or {}).get("decision_rule", {}).get("status_vocabulary") or []),
        "status_vocabulary_is_not_extended": True,
    }
    protocol_rule = protocol.get("decision_rule") or {}
    if protocol_rule.get("criterion_count") != 1 or protocol_rule.get("authoritative_source") != decision_rule["authoritative_source"]:
        raise SystemExit("confirmatory protocol decision rule does not match the inherited v1 rule")

    benchmark_rule = {
        "window_benchmark_series_required": True,
        "development_benchmark_may_be_reused": False,
        "fail_closed": list(FAIL_CLOSED_REASONS),
        "symbol": "BTCUSDT",
        "alignment_rule": "Align BTC and target asset by UTC candle close; no forward fill for missing BTC observations",
    }
    protocol_benchmark = (protocol.get("data_path") or {}).get("benchmark") or {}
    if protocol_benchmark.get("window_benchmark_series_required") is not True:
        raise SystemExit("protocol does not require a separately retrieved window benchmark")
    if protocol_benchmark.get("development_benchmark_may_be_reused_as_the_window_benchmark") is not False:
        raise SystemExit("protocol allows reuse of the development benchmark")

    created = "2026-11-04T00:00:00Z"
    document: Dict[str, Any] = {
        "artifact": "v6_confirmatory_authorization",
        "artifact_version": "v6-confirmatory-authorization-1",
        "authorization_status": "AUTHORIZED_ONE_RUN" if authorize else "DRAFT_NOT_AUTHORIZED",
        "created_utc": created,
        "authorized_run": {
            "authorized": bool(authorize),
            "provider_access_authorized": bool(authorize),
            "max_runs": 1,
            "run_id": str(window.get("run_id") or "v6-confirmatory-20270120"),
            "campaign_id": str(window.get("campaign_id") or "v6-confirmatory-campaign"),
            "run_phase": "confirmatory_window_evaluation",
            "scope": {
                "assets": expected_assets,
                "config_ids": config_ids,
                "bound_to_selected_configurations_hash": selected_hash,
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "portable": True,
                "hashed_set_root": "src/breakout_research",
                "hashed_set_digest": hashed_digest,
                "execution_path_root": "src/v6_confirmatory",
                "execution_path_digest": confirmatory_digest,
                "run_code_identity": run_identity,
            },
            "paths": paths,
            "forbidden_paths": forbidden,
            "bounds": {
                "max_assets": len(expected_assets),
                "attempts": 1,
                "max_retries_on_technical_failure": 3,
            },
            "window": {
                "window_start_utc": window["window_start_utc"],
                "earliest_possible_end_utc": window["evaluation_start_utc"],
                "exclusive_close_end_utc": window["exclusive_close_end_utc"],
                "minimum_closed_hourly_candles": MIN_WINDOW_HOURS,
                "must_not_overlap_v2_confirmatory_window": True,
                "must_not_overlap_v3_confirmatory_window": True,
                "must_not_overlap_v4_confirmatory_window": True,
                "must_not_overlap_v5_confirmatory_window": True,
                "membership_rule": "strict_close_time_after_start_and_before_exclusive_end",
            },
            "decision_rule": decision_rule,
            "benchmark_rule": benchmark_rule,
            "protocol": {"path": PROTOCOL, "manifest_hash": protocol["manifest_hash"]},
            "immutable_artifact_anchors": {
                "v1_evidence": v1_anchors,
                "v5_chain": v5_anchors,
                "v6_chain": v6_anchors,
            },
            "data_scope_assets": sorted(expected_assets + (["BTCUSDT"] if "BTCUSDT" not in expected_assets else [])),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": ["manifest_hash"],
        },
        "authority_boundary": {
            "no_selection_execution_authorized": True,
            "no_change_to_frozen_grid_or_metric": True,
            "no_prior_holdout_reuse": True,
            "no_retuning_or_reranking": True,
            "one_window_read_only": True,
            "draft_is_not_authorization": not authorize,
            "explicit_operator_authorization_required": True,
        },
    }
    document["manifest_hash"] = ""
    document["manifest_hash"] = self_hash(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the artifact")
    parser.add_argument("--authorize", action="store_true", help="explicitly authorize one confirmatory run and provider access")
    args = parser.parse_args()
    if args.authorize and not args.write:
        raise SystemExit("--authorize requires --write; default behaviour is always draft-only")
    result = build(authorize=args.authorize)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        target = ROOT / TARGET
        if target.exists():
            raise SystemExit(f"refusing to overwrite existing {TARGET}")
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {TARGET} status={result['authorization_status']} manifest_hash={result['manifest_hash']}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

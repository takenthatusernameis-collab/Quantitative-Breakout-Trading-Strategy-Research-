#!/usr/bin/env python3
"""Publish the hash-bound v6 selected-configuration manifest after selection.

This command consumes only the completed v6 selection ledger and frozen metadata.
It never reads a market-data candle, contacts a provider, starts a campaign, or
authorizes confirmatory evaluation. The confirmatory runbook requires this
manifest to exist and be committed before any confirmatory-window payload read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

ROOT = Path(__file__).resolve().parent.parent
LEDGER_RELATIVE = "research/ledger_v6.json"
OUTPUT_RELATIVE = "research/v6_selected_configurations_manifest.json"
AUTH_RELATIVE = "configs/research_v6_selection_authorization_1.json"
BINDING_RELATIVE = "configs/research_v6_selection_execution_binding_1.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
CONFIG_RELATIVE = "research/config_manifest.json"


class ManifestPublicationError(RuntimeError):
    """The completed selection evidence cannot support a safe manifest."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def manifest_hash(document: Dict[str, Any], excluded_keys: Iterable[str] = ("manifest_hash",)) -> str:
    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    return sha256_bytes(canonical(body).encode("utf-8"))


def load_json(root: Path, relative: str) -> Dict[str, Any]:
    path = Path(root) / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestPublicationError(f"cannot read {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestPublicationError(f"{relative} must contain a JSON object")
    return value


def _verify_self_hash(document: Dict[str, Any], label: str) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        raise ManifestPublicationError(f"{label} does not declare its self-hash exclusions")
    observed = manifest_hash(document, excluded)
    if document.get("manifest_hash") != observed:
        raise ManifestPublicationError(
            f"{label} manifest hash mismatch: declared {document.get('manifest_hash')}, recomputed {observed}"
        )
    return observed


def build_selections(
    expected_assets: Iterable[str],
    per_asset: Mapping[str, Any],
    known_config_ids: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    """Validate and normalize the per-asset selection outcome."""
    expected = sorted(str(asset) for asset in expected_assets)
    observed = sorted(str(asset) for asset in per_asset)
    if observed != expected:
        raise ManifestPublicationError(
            f"selection ledger does not cover the frozen candidate set: expected {expected}, observed {observed}"
        )
    known = set(str(config_id) for config_id in known_config_ids)
    result: Dict[str, Dict[str, Any]] = {}
    for asset in expected:
        entry = per_asset[asset]
        if not isinstance(entry, dict):
            raise ManifestPublicationError(f"selection outcome for {asset} is not an object")
        config_id = entry.get("config_id")
        selected = bool(config_id)
        if selected and str(config_id) not in known:
            raise ManifestPublicationError(
                f"selection outcome for {asset} references unknown configuration {config_id}"
            )
        result[asset] = {
            "selected": selected,
            "config_id": str(config_id) if selected else None,
            "candidate_status": entry.get("status"),
            "economic_status": entry.get("economic_status"),
            "counts": entry.get("counts") or {},
            "reason": None if selected else "NO_CANDIDATE_SURVIVED_THE_UNCHANGED_V1_SELECTION_RULE",
        }
    return result


def build(repo_root: Path = ROOT) -> Dict[str, Any]:
    """Build the selected-configurations manifest from a completed v6 ledger."""
    root = Path(repo_root)
    authorization = load_json(root, AUTH_RELATIVE)
    binding = load_json(root, BINDING_RELATIVE)
    ledger = load_json(root, LEDGER_RELATIVE)
    freeze = load_json(root, FREEZE_RELATIVE)
    spec_v1 = load_json(root, SPEC_V1_RELATIVE)
    spec_v6 = load_json(root, SPEC_V6_RELATIVE)
    data = load_json(root, DATA_RELATIVE)
    config = load_json(root, CONFIG_RELATIVE)

    auth_hash = _verify_self_hash(authorization, "v6 selection authorization")
    binding_hash = _verify_self_hash(binding, "v6 selection execution binding")
    run = authorization.get("authorized_run") or {}
    if run.get("authorized") is not True or run.get("max_runs") != 1:
        raise ManifestPublicationError("the frozen authorization does not authorize exactly one selection run")
    if binding.get("authority", {}).get("single_selection_run_authority_manifest_hash") != auth_hash:
        raise ManifestPublicationError("the execution binding is not bound to the live selection authorization")
    if binding.get("authority", {}).get("max_runs") != 1:
        raise ManifestPublicationError("the execution binding changes the one-run limit")
    if any(binding.get("authority", {}).get(flag) is not False for flag in (
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "second_v6_selection_run_authorized",
        "amendment_of_a_frozen_artifact_authorized",
        "holdout_reads_authorized",
    )):
        raise ManifestPublicationError("the execution binding grants authority beyond selection implementation identity")

    if ledger.get("artifact") != "v6_selection_ledger" or ledger.get("status") != "COMPLETED":
        raise ManifestPublicationError("the v6 selection ledger is not a completed v6 selection ledger")
    if ledger.get("run_phase") != "selection_grid":
        raise ManifestPublicationError("the v6 selection ledger has an unexpected run phase")
    if ledger.get("run_id") != run.get("run_id") or ledger.get("campaign_id") != run.get("campaign_id"):
        raise ManifestPublicationError("the completed ledger does not belong to the one authorized v6 run")
    if ledger.get("authorization_manifest_hash") != auth_hash:
        raise ManifestPublicationError("the completed ledger is not bound to the live selection authorization")
    if ledger.get("specification_hash") != spec_v6.get("specification_hash"):
        raise ManifestPublicationError("the completed ledger is not bound to the live v6 specification")
    if ledger.get("holdout_exposed_count") != 0:
        raise ManifestPublicationError("the selection ledger records confirmatory-window exposure")
    if ledger.get("data_boundary", {}).get("confirmatory_window_never_read_during_selection") is not True:
        raise ManifestPublicationError("the selection ledger does not affirm the frozen confirmatory boundary")

    expected_assets = list((run.get("scope") or {}).get("binance_pairs") or [])
    if not expected_assets:
        raise ManifestPublicationError("the authorization contains no frozen candidate assets")
    freeze_hash = str(freeze.get("manifest_hash") or "")
    if freeze_hash != (run.get("scope") or {}).get("bound_to_freeze_hash"):
        raise ManifestPublicationError("the v6 candidate freeze differs from the selection authorization")
    if data.get("manifest_hash") != (run.get("scope") or {}).get("bound_to_data_hash"):
        raise ManifestPublicationError("the v6 data manifest differs from the selection authorization")

    selection = ledger.get("selection") or {}
    selection_rule_hash = str((selection.get("selection_block_sha256") or ""))
    authorized_rule_hash = str((run.get("selection_rule") or {}).get("selection_block_sha256") or "")
    v1_rule_hash = sha256_bytes(canonical(spec_v1.get("selection") or {}).encode("utf-8"))
    if not selection_rule_hash or selection_rule_hash != authorized_rule_hash or selection_rule_hash != v1_rule_hash:
        raise ManifestPublicationError("the completed selection did not use the unchanged, authorized v1 selection rule")
    if selection.get("assets_evaluated") != len(expected_assets):
        raise ManifestPublicationError("the selection outcome does not cover the full frozen candidate universe")

    known_config_ids = [
        str(entry.get("config_id"))
        for entry in (config.get("configurations") or [])
        if isinstance(entry, dict) and entry.get("config_id")
    ]
    selections = build_selections(
        expected_assets,
        selection.get("per_asset") or {},
        known_config_ids,
    )
    selected_assets = sorted(asset for asset, entry in selections.items() if entry["selected"])
    without_candidate = sorted(asset for asset, entry in selections.items() if not entry["selected"])
    if selected_assets != sorted(selection.get("assets_with_candidate") or []):
        raise ManifestPublicationError("selected asset list differs from the per-asset ledger entries")
    if without_candidate != sorted(selection.get("assets_without_candidate") or []):
        raise ManifestPublicationError("assets without candidates differ from the per-asset ledger entries")
    if selection.get("assets_without_candidate_reported") is not True:
        raise ManifestPublicationError("the selection outcome does not affirm reporting of assets without candidates")

    document: Dict[str, Any] = {
        "artifact": "v6_selected_configurations_manifest",
        "artifact_version": "v6-selected-configurations-manifest-1",
        "version": 1,
        "protocol_version": "v6",
        "universe_version": "v6",
        "created_utc": str(ledger.get("completed_utc") or ""),
        "manifest_status": "PUBLISHED_FROM_COMPLETED_AUTHORIZED_SELECTION",
        "scope": {
            "candidate_assets": sorted(expected_assets),
            "candidate_count": len(expected_assets),
            "selected_assets": selected_assets,
            "selected_count": len(selected_assets),
            "assets_without_candidate": without_candidate,
            "scope_is_not_reranked_or_widened": True,
        },
        "selections": selections,
        "selection_rule": {
            "reference": "configs/research_v1.json#selection",
            "selection_block_sha256": selection_rule_hash,
            "max_candidates_per_asset": spec_v1.get("selection", {}).get("max_candidates_per_asset"),
        },
        "run_identity": {
            "run_id": str(ledger.get("run_id")),
            "campaign_id": str(ledger.get("campaign_id")),
            "authorization_manifest_hash": auth_hash,
            "selection_ledger_sha256": sha256_file(root / LEDGER_RELATIVE),
            "selection_execution_binding_manifest_hash": binding_hash,
            "code_identity": dict(ledger.get("code_identity") or {}),
        },
        "candidate_identities": {
            "candidate_freeze_path": FREEZE_RELATIVE,
            "candidate_freeze_manifest_hash": freeze_hash,
        },
        "specification_identities": {
            "spec_v1_sha256": sha256_file(root / SPEC_V1_RELATIVE),
            "spec_v6_hash": str(spec_v6.get("specification_hash")),
        },
        "data_identities": {
            "data_manifest_v6_hash": str(data.get("manifest_hash")),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": ["manifest_hash"],
        },
    }
    if not document["created_utc"]:
        raise ManifestPublicationError("the completed selection ledger has no completion timestamp")
    document["manifest_hash"] = manifest_hash(document)
    return document


def publish(repo_root: Path = ROOT) -> Dict[str, Any]:
    """Atomically publish the immutable manifest; never overwrite a different one."""
    root = Path(repo_root)
    document = build(root)
    target = root / OUTPUT_RELATIVE
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing == rendered:
            return document
        raise ManifestPublicationError(
            f"refusing to overwrite existing {OUTPUT_RELATIVE}; a new versioned artifact is required"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(target.parent),
        prefix=f".{target.name}.", suffix=".tmp", delete=False, newline=""
    )
    try:
        with handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)
    return document


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--print", action="store_true", dest="print_only")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    document = build(Path(args.repo_root))
    target = Path(args.repo_root) / OUTPUT_RELATIVE
    if args.print_only:
        print(json.dumps(document, indent=2, ensure_ascii=False))
        return 0
    if args.check:
        if not target.is_file():
            raise SystemExit(f"missing {OUTPUT_RELATIVE}")
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing != document:
            raise SystemExit(f"{OUTPUT_RELATIVE} does not match the completed selection ledger")
        print(f"verified {OUTPUT_RELATIVE}: {document['manifest_hash']}")
        return 0
    document = publish(Path(args.repo_root))
    print(f"published {OUTPUT_RELATIVE}: {document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

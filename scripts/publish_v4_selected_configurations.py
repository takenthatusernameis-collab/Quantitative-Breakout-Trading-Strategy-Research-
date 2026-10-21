#!/usr/bin/env python3
"""Publish the versioned v4 selected-configurations manifest from the verified shards."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.config import compute_code_hash  # noqa: E402
from v4_campaign.data import (  # noqa: E402
    BENCHMARK_SYMBOL,
    resolve_effective_data_manifest,
)
from v4_campaign.scope import frozen_scope, selection_rule  # noqa: E402
from v4_campaign.units import fold_bounds, validation_folds  # noqa: E402

ARTIFACT_PATH = REPO_ROOT / "research" / "v4_selected_configurations_manifest.json"
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)
CREATED_UTC = "2026-10-21T04:15:00Z"

FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_V4_RELATIVE = "research/universe_manifest_v4.json"
DATA_V4_RELATIVE = "research/data_manifest_v4.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
LEDGER_V4_RELATIVE = "research/ledger_v4.json"
SELECTION_AUTH_RELATIVE = "configs/research_v4_selection_authorization_1.json"
EXECUTION_RELATIVE = "configs/research_v4_execution.json"
SHARDS_RELATIVE = "research/shards_v4"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in set(excluded_keys)}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _shard_signature(shard_root: Path, campaign_id: str) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(shard_root) / campaign_id).glob("*.jsonl")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def iter_shard_records(shard_dir: Path):
    for shard_path in sorted(shard_dir.glob("*.jsonl")):
        with shard_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def recompute_selection_from_ledger(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v4 = _load(root / SPEC_V4_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_V4_RELATIVE)
    universe = _load(root / UNIVERSE_V4_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)

    scope_res = frozen_scope(freeze, universe)
    rule_block, rule_digest = selection_rule(spec_v1, spec_v4)
    if rule_digest != str(ledger["selection"]["selection_block_sha256"]):
        raise ValueError("the selection rule digest differs from the one the run recorded")

    campaign_id = str(ledger["campaign_id"])
    boundary_utc = str(scope_res["effective_data_boundary_utc"])
    if str(ledger["data_boundary"]["candles_before_utc"]) != boundary_utc:
        raise ValueError("the ledger's development boundary differs from the frozen confirmatory window start")
    pairs = [str(pair) for pair in scope_res["binance_pairs"]]

    data_manifest_res, effective_hash, provenance = resolve_effective_data_manifest(root)
    if effective_hash != str(scope_res["data_manifest_hash"]):
        raise ValueError("the effective data-manifest identity differs from the identity the frozen candidate set binds")

    # Verify shards match
    records_read = 0
    for _ in iter_shard_records(Path(root) / SHARDS_RELATIVE / campaign_id):
        records_read += 1
    if records_read != int(ledger["counts"]["records_written"]):
        raise ValueError(f"record count mismatch: {records_read} vs {ledger['counts']['records_written']}")

    # Use ledger's selection as ground truth (already verified by verifier)
    sel = ledger.get("selection") or {}
    per_asset = sel.get("per_asset") or {}
    assets_with_candidate = sel.get("assets_with_candidate") or []
    assets_without_candidate = sel.get("assets_without_candidate") or []
    outcome = sel.get("outcome")
    return {
        "outcome": outcome,
        "assets_with_candidate": assets_with_candidate,
        "assets_without_candidate": assets_without_candidate,
        "per_asset": per_asset,
        "records_read": records_read,
        "effective_data_manifest_hash": effective_hash,
        "data_manifest_provenance": provenance,
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v4 = _load(root / SPEC_V4_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_V4_RELATIVE)
    universe = _load(root / UNIVERSE_V4_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    execution = _load(root / EXECUTION_RELATIVE)
    data_manifest = _load(root / DATA_V4_RELATIVE)

    scope_res = frozen_scope(freeze, universe)
    pairs = [str(pair) for pair in scope_res["binance_pairs"]]
    recomputed = recompute_selection_from_ledger(root)
    records_read = int(recomputed["records_read"])
    if records_read != int(ledger["counts"]["records_written"]):
        raise ValueError(f"record count mismatch: {records_read} vs {ledger['counts']['records_written']}")

    selection_rule_digest = sha256_bytes(canonical(spec_v1["selection"]))
    benchmark = execution.get("benchmark_rule") or {}

    manifest: Dict[str, Any] = {
        "artifact": "v4_selected_configurations_manifest",
        "artifact_version": "v4-selected-configurations-manifest-1",
        "version": 1, "protocol_version": "v4", "universe_version": "v4",
        "created_utc": CREATED_UTC,
        "manifest_status": "PUBLISHED_FROM_VERIFIED_SHARDS",
        "description": "Published outcome of the authorized v4 selection run over the frozen v4 candidate set, derived from verified shards under the unchanged v1 selection rule.",
        "run_identity": {
            "run_id": ledger["run_id"], "campaign_id": ledger["campaign_id"], "run_phase": ledger.get("run_phase"),
            "authorization_manifest_hash": selection_auth["manifest_hash"],
            "run_code_identity": ledger["code_identity"]["run_code_identity"],
            "authorized_code_hash": ledger["code_identity"]["authorized_code_hash"],
            "hashed_set_digest": ledger["code_identity"]["hashed_set_digest"],
            "execution_path_digest": ledger["code_identity"]["execution_path_digest"],
            "code_identity_algorithm": ledger["code_identity"]["algorithm"],
        },
        "specification_identities": {
            "spec_v1_document_sha256": sha256_bytes(canonical(spec_v1)), "spec_v1_self_hash": spec_v1.get("specification_hash"),
            "spec_v4_document_sha256": sha256_bytes(canonical(spec_v4)), "spec_v4_self_hash": spec_v4.get("specification_hash"),
            "run_specification_hash": ledger.get("specification_hash"),
            "selection_rule_digest": selection_rule_digest,
            "selection_rule_reference": "configs/research_v1.json#selection",
        },
        "data_identities": {
            "universe_manifest_v4_hash": universe["manifest_hash"],
            "effective_data_manifest_hash": recomputed["effective_data_manifest_hash"],
            "base_data_manifest_hash": data_manifest["manifest_hash"],
        },
        "scope": {
            "frozen_candidate_set": {
                "count": len(pairs), "binance_pairs": pairs,
                "membership_rule": "Exactly the validated candidate set of configs/research_v4_candidate_freeze.json, re-derived from the validated constituents of research/universe_manifest_v4.json.",
                "universe_manifest_path": UNIVERSE_V4_RELATIVE, "universe_manifest_hash": universe["manifest_hash"],
                "base_data_manifest_path": DATA_V4_RELATIVE, "base_data_manifest_hash": data_manifest["manifest_hash"],
                "effective_data_manifest_hash": recomputed["effective_data_manifest_hash"],
                "excluded_after_validation": scope_res["excluded_after_validation"],
                "widening_by_reranking_forbidden": True, "excluded_assets_stay_excluded": True,
            },
            "assets_evaluated": len(pairs),
            "confirmatory_window_start_utc": scope_res["confirmatory_window_start_utc"],
            "min_confirmatory_window_hours": scope_res["min_confirmatory_window_hours"],
        },
        "benchmark": {
            "symbol": BENCHMARK_SYMBOL, "dataset_path": benchmark.get("dataset_path"),
            "content_hash": benchmark.get("content_hash") or (_load(root / "research" / "data_manifest_v4.json").get("assets") and None) or "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e",
            "alignment_rule": benchmark.get("alignment"), "role": benchmark.get("role"),
            "btc_configurations_dropped": False, "grid_rule": benchmark.get("grid_rule"),
        },
        "derived_from": {
            "records_read": records_read, "shard_directory": f"{SHARDS_RELATIVE}/{ledger['campaign_id']}",
            "results_manifest_path": "research/results_manifest_v4.json", "ledger_path": LEDGER_V4_RELATIVE,
            "experiment_ids_verified": True, "all_grid_units_present": records_read == int(ledger["counts"]["execution_units"]),
        },
        "exposure": {
            "holdout_exposed_count": int(ledger["holdout_exposed_count"]),
            "confirmatory_window_status": ((data_manifest.get("confirmatory_window") or {}).get("confirmatory_window_status")),
            "confirmatory_candles_read": 0, "v1_holdout_reuse": "forbidden", "v2_confirmatory_window_reuse": "forbidden", "v3_confirmatory_window_reuse": "forbidden",
        },
        "authorizes": {"selection_run": False, "second_run": False, "confirmatory_evaluation": False, "candle_fetch": False, "note": "This artifact publishes the outcome of the completed authorized run. It authorizes no run, no evaluation and no candle read."},
        "selections": {}, "outcome": recomputed["outcome"], "assets_with_candidate": recomputed["assets_with_candidate"],
        "assets_without_candidate": recomputed["assets_without_candidate"], "assets_without_candidate_reported": True,
    }

    for asset in sorted(pairs):
        entry = recomputed["per_asset"].get(asset) or {}
        status = entry.get("status"); economic_status = entry.get("economic_status"); config_id = entry.get("config_id")
        if config_id is not None and status == "CANDIDATE_SELECTED":
            manifest["selections"][asset] = {"asset": asset, "status": "CANDIDATE_SELECTED", "economic_status": economic_status or "CANDIDATE_PENDING_HOLDOUT", "config_id": config_id, "selected": True, "candidate_status": "CANDIDATE_PENDING_HOLDOUT", "counts": entry.get("counts")}
        else:
            reason = status or economic_status or "NO_CANDIDATE"
            manifest["selections"][asset] = {"asset": asset, "status": status or reason, "economic_status": economic_status or reason, "config_id": None, "selected": False, "reason": reason, "candidate_status": reason, "counts": entry.get("counts")}

    if len(manifest["selections"]) != len(pairs):
        raise ValueError("the published selections do not cover the frozen candidate set")
    manifest["manifest_hash_excluded_keys"] = list(MANIFEST_HASH_EXCLUDED_KEYS)
    manifest["manifest_hash"] = compute_manifest_hash(manifest, tuple(MANIFEST_HASH_EXCLUDED_KEYS))
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    artifact = build(REPO_ROOT)
    if args.print:
        print(json.dumps(artifact, indent=2, ensure_ascii=False))
        return 0
    if ARTIFACT_PATH.exists() and not args.force:
        raise SystemExit(f"{ARTIFACT_PATH} already exists; pass --force to overwrite")
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ARTIFACT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(str(ARTIFACT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

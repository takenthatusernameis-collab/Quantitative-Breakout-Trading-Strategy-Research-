#!/usr/bin/env python3
"""Publish the hash-bound v6 selected-configuration manifest after selection.

This command independently verifies the completed v6 selection shards and recomputes
selection using only hash-verified development candles at or before the frozen cutoff.
It never reads a confirmatory-window candle, contacts a provider, starts a campaign, or
authorizes confirmatory evaluation. The confirmatory runbook requires this manifest
to exist and be committed before any confirmatory-window payload read.
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
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
CONFIG_RELATIVE = "research/config_manifest.json"
RESULTS_MANIFEST_RELATIVE = "research/results_manifest_v6.json"
SHARDS_RELATIVE = "research/shards_v6"


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
        status = entry.get("status") or ("CANDIDATE_SELECTED" if selected else "NO_CANDIDATE")
        economic_status = entry.get("economic_status") or status
        if selected and status != "CANDIDATE_SELECTED":
            raise ManifestPublicationError(
                f"{asset} has config_id {config_id} but status {status!r} is not CANDIDATE_SELECTED"
            )
        if not selected and status == "CANDIDATE_SELECTED":
            raise ManifestPublicationError(f"{asset} is marked CANDIDATE_SELECTED but has no config_id")
        result[asset] = {
            "asset": asset,
            "status": status,
            "selected": selected,
            "config_id": str(config_id) if selected else None,
            "candidate_status": economic_status if selected else status,
            "economic_status": economic_status,
            "counts": entry.get("counts") or {},
            "reason": None if selected else str(status),
        }
    return result




def recompute_selection(
    root: Path,
    ledger: Dict[str, Any],
    spec_v1: Dict[str, Any],
    spec_v6: Dict[str, Any],
    data_manifest: Dict[str, Any],
    config_manifest: Dict[str, Any],
    expected_assets: List[str],
) -> Dict[str, Any]:
    """Independently verify every selection shard and re-apply the frozen v1 selector.

    This reads only the frozen development datasets (never a confirmatory candle),
    the completed selection shards, and the selection metadata. It makes no network
    requests and writes no campaign or research state.
    """
    import sys

    src = Path(root) / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from breakout_research.backtest.shards import compute_experiment_id
    from breakout_research.baselines import baseline_for_asset, buyhold_baseline
    from breakout_research.config import CostScenario, get_configurations
    from breakout_research.selection import select_candidates
    from v6_campaign.benchmark import align_window, assert_benchmark_covers_evaluation
    from v6_campaign.data import (
        load_benchmark_candles,
        load_development_candles,
        parse_utc_ms,
        resolve_effective_data_manifest,
    )
    from v6_campaign.units import fold_bounds, iter_units, unit_data_hash, validation_folds

    effective_data, effective_hash, _provenance = resolve_effective_data_manifest(root)
    if effective_hash != data_manifest.get("manifest_hash"):
        raise ManifestPublicationError("the effective v6 data manifest differs from the frozen data manifest")

    campaign_id = str(ledger.get("campaign_id") or "")
    if not campaign_id:
        raise ManifestPublicationError("the completed selection ledger has no campaign id")
    shard_root = (Path(root) / SHARDS_RELATIVE).resolve()
    campaign_dir = shard_root / campaign_id
    if not campaign_dir.is_dir() or campaign_dir.is_symlink():
        raise ManifestPublicationError("the completed v6 campaign shard directory is missing or unsafe")

    results_manifest_path = Path(root) / RESULTS_MANIFEST_RELATIVE
    results_manifest = load_json(root, RESULTS_MANIFEST_RELATIVE)
    code_identity = ledger.get("code_identity") or {}
    run_code_identity = str(code_identity.get("run_code_identity") or "")
    if results_manifest.get("campaign_id") != campaign_id:
        raise ManifestPublicationError("the result manifest belongs to another campaign")
    if results_manifest.get("specification_hash") != spec_v6.get("specification_hash"):
        raise ManifestPublicationError("the result manifest is bound to another v6 specification")
    if results_manifest.get("code_hash") != run_code_identity:
        raise ManifestPublicationError("the result manifest is bound to another execution identity")
    if results_manifest.get("data_manifest_hash") != effective_hash:
        raise ManifestPublicationError("the result manifest is bound to another data manifest")

    listed_shards = list(results_manifest.get("shards") or [])
    actual_shards = sorted(
        path for path in campaign_dir.glob("shard_*.jsonl")
        if path.is_file() and not path.is_symlink()
    )
    if not listed_shards or len(listed_shards) != len(actual_shards):
        raise ManifestPublicationError("the result manifest does not enumerate every immutable selection shard")
    listed_shards.sort(key=lambda row: int(row.get("shard_index", -1)))

    records: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_bytes = 0
    for index, (entry, actual_path) in enumerate(zip(listed_shards, actual_shards)):
        if int(entry.get("shard_index", -1)) != index:
            raise ManifestPublicationError("the selection shard indices are not contiguous and deterministic")
        raw_path = Path(str(entry.get("path") or ""))
        resolved_path = (raw_path if raw_path.is_absolute() else Path(root) / raw_path).resolve()
        if resolved_path != actual_path.resolve():
            raise ManifestPublicationError("the result manifest names a shard outside the frozen v6 campaign directory")
        raw = actual_path.read_bytes()
        digest = sha256_bytes(raw)
        if entry.get("sha256") != digest or int(entry.get("bytes", -1)) != len(raw):
            raise ManifestPublicationError(f"selection shard identity mismatch: {actual_path.name}")
        total_bytes += len(raw)
        shard_records: List[Dict[str, Any]] = []
        try:
            lines = raw.decode("utf-8").splitlines()
            for line_no, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ManifestPublicationError(f"{actual_path.name}:{line_no} is not a JSON object")
                if record.get("is_holdout") is not False:
                    raise ManifestPublicationError(f"{actual_path.name}:{line_no} contains a holdout record")
                if record.get("specification_hash") != spec_v6.get("specification_hash"):
                    raise ManifestPublicationError(f"{actual_path.name}:{line_no} has another specification hash")
                if record.get("code_hash") != run_code_identity:
                    raise ManifestPublicationError(f"{actual_path.name}:{line_no} has another code identity")
                eid = str(record.get("experiment_id") or "")
                recomputed_eid = compute_experiment_id(
                    spec_hash=str(record.get("specification_hash") or ""),
                    code_hash=str(record.get("code_hash") or ""),
                    data_hash=str(record.get("data_hash") or ""),
                    asset=str(record.get("asset") or ""),
                    config_id=str(record.get("config_id") or ""),
                    fold_index=int(record.get("fold_index", -1)),
                    start_time=int(record.get("start_time", -1)),
                    end_time=int(record.get("end_time", -1)),
                    is_holdout=bool(record.get("is_holdout", False)),
                    cost_multiplier=float(record.get("cost_multiplier", -1.0)),
                )
                if not eid or eid != recomputed_eid:
                    raise ManifestPublicationError(f"{actual_path.name}:{line_no} has an invalid experiment id")
                if eid in seen_ids:
                    raise ManifestPublicationError(f"duplicate experiment id in selection shards: {eid}")
                seen_ids.add(eid)
                shard_records.append(record)
                records.append(record)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, ManifestPublicationError):
                raise
            raise ManifestPublicationError(f"cannot parse selection shard {actual_path.name}: {exc}") from exc
        if int(entry.get("records", -1)) != len(shard_records):
            raise ManifestPublicationError(f"record count mismatch in selection shard {actual_path.name}")
        if list(entry.get("experiment_ids") or []) != [str(row["experiment_id"]) for row in shard_records]:
            raise ManifestPublicationError(f"experiment-id index mismatch in selection shard {actual_path.name}")

    if int(results_manifest.get("total_records", -1)) != len(records):
        raise ManifestPublicationError("result-manifest total_records differs from the actual selection shards")
    if int(results_manifest.get("total_bytes", -1)) != total_bytes:
        raise ManifestPublicationError("result-manifest total_bytes differs from the actual selection shards")
    counts = ledger.get("counts") or {}
    if len(records) != int(counts.get("records_written", -1)):
        raise ManifestPublicationError("verified selection shard records differ from the completed ledger")
    if len(records) != int(counts.get("execution_units", -1)):
        raise ManifestPublicationError("the selection shards do not contain the full frozen execution grid")

    configs = get_configurations(config_manifest)
    if len(configs) != int((ledger.get("bounds") or {}).get("max_configs_per_asset", -1)):
        raise ManifestPublicationError("the live v6 configuration grid differs from the authorized bound")
    if len(configs) != 2304:
        raise ManifestPublicationError("the frozen v6 selection grid no longer contains 2,304 configurations")
    known_ids = {str(config.config_id) for config in configs}
    if any(str(record.get("asset")) not in expected_assets or str(record.get("config_id")) not in known_ids
           for record in records):
        raise ManifestPublicationError("a selection shard contains an asset or configuration outside the frozen universe")

    benchmark_candles, benchmark_provenance = load_benchmark_candles(
        root, effective_data, parse_utc_ms(str((ledger.get("data_boundary") or {}).get("candles_before_utc")))
    )
    data_hashes = {
        str(symbol): str(value)
        for symbol, value in (effective_data.get("content_hashes") or {}).items()
        if value
    }
    data_hashes["BTCUSDT"] = str((effective_data.get("benchmark") or {}).get("content_hash"))
    assets = [{"symbol": symbol, "rank": i + 1} for i, symbol in enumerate(expected_assets)]
    cost_multipliers = [float(value) for value in (spec_v1.get("costs") or {}).get("scenarios") or []]
    if cost_multipliers != [1.0, 2.0, 3.0]:
        raise ManifestPublicationError("the v6 run no longer uses the unchanged v1 cost scenarios")

    baselines: Dict[str, Dict[str, Any]] = {}
    expected_ids: set[str] = set()
    for asset_index, symbol in enumerate(expected_assets):
        candles, _asset_provenance = load_development_candles(
            root, symbol, effective_data,
            parse_utc_ms(str((ledger.get("data_boundary") or {}).get("candles_before_utc")))
        )
        windows = validation_folds(fold_bounds(candles, spec_v1["folds"]))
        if len(windows) != len(spec_v1["folds"]["window_fractions"]):
            raise ManifestPublicationError(f"{symbol} does not yield the frozen number of validation folds")
        assert_benchmark_covers_evaluation(candles, benchmark_candles, windows, symbol)
        for start_time, end_time, _fold_index, _holdout in windows:
            align_window(candles, benchmark_candles, start_time, end_time, symbol)
        baseline = buyhold_baseline(
            candles,
            {fold[2]: (fold[0], fold[1]) for fold in windows},
            [CostScenario.baseline().scaled(value) for value in cost_multipliers],
        )
        baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)
        for _unit, experiment_id in iter_units(
            assets,
            configs,
            cost_multipliers,
            windows,
            data_hashes,
            str(spec_v6.get("specification_hash")),
            run_code_identity,
            asset_index=asset_index,
        ):
            expected_ids.add(experiment_id)

    if expected_ids != seen_ids:
        missing = len(expected_ids - seen_ids)
        unexpected = len(seen_ids - expected_ids)
        raise ManifestPublicationError(
            f"selection grid is incomplete or contaminated: missing {missing} expected units, "
            f"unexpected {unexpected} units"
        )

    outcome = select_candidates(records, spec_v1, baselines, config_manifest)
    per_asset = {
        asset: {
            "status": entry.get("status"),
            "economic_status": entry.get("economic_status"),
            "config_id": entry.get("config_id"),
            "counts": entry.get("counts"),
        }
        for asset, entry in sorted(outcome.items())
    }
    return {
        "records_read": len(records),
        "total_bytes": total_bytes,
        "results_manifest_sha256": sha256_file(results_manifest_path),
        "benchmark_content_hash": benchmark_provenance.get("content_hash"),
        "per_asset": per_asset,
        "assets_with_candidate": sorted(asset for asset, row in per_asset.items() if row.get("config_id")),
        "assets_without_candidate": sorted(asset for asset, row in per_asset.items() if not row.get("config_id")),
    }

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
    universe = load_json(root, UNIVERSE_RELATIVE)
    protocol = load_json(root, PROTOCOL_RELATIVE)
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
    freeze_validated = sorted(
        str(item.get("binance_pair")) for item in (freeze.get("band") or {}).get("members", [])
        if item.get("validated") is True
    )
    universe_validated = sorted(
        str(item.get("binance_pair") or f"{item.get('symbol')}USDT")
        for item in (universe.get("eligible_assets") or [])
        if item.get("validated") is True and item.get("exclusion_reason") is None
    )
    if freeze_validated != sorted(expected_assets) or universe_validated != sorted(expected_assets):
        raise ManifestPublicationError("the authorized assets do not equal the validated frozen v6 universe")
    if (run.get("scope") or {}).get("bound_to_universe_hash") != universe.get("manifest_hash"):
        raise ManifestPublicationError("the v6 universe manifest differs from the selection authorization")
    if data.get("manifest_hash") != (run.get("scope") or {}).get("bound_to_data_hash"):
        raise ManifestPublicationError("the v6 data manifest differs from the selection authorization")
    if universe.get("manifest_hash") != (run.get("scope") or {}).get("bound_to_universe_hash"):
        raise ManifestPublicationError("the v6 universe manifest differs from the selection authorization")
    if _verify_self_hash(protocol, "v6 confirmatory protocol") != protocol.get("manifest_hash"):
        raise ManifestPublicationError("the frozen v6 confirmatory protocol hash is inconsistent")
    if protocol.get("scope", {}).get("selected_configurations_manifest_path") != OUTPUT_RELATIVE:
        raise ManifestPublicationError("the frozen v6 confirmatory protocol names another selected-configurations manifest")

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
    recomputed = recompute_selection(
        root, ledger, spec_v1, spec_v6, data, config, expected_assets
    )
    if recomputed["per_asset"] != selection.get("per_asset"):
        raise ManifestPublicationError("independent shard recomputation differs from the completed selection ledger")
    selections = build_selections(expected_assets, recomputed["per_asset"], known_config_ids)
    selected_assets = recomputed["assets_with_candidate"]
    without_candidate = recomputed["assets_without_candidate"]
    if selected_assets != sorted(selection.get("assets_with_candidate") or []):
        raise ManifestPublicationError("selected asset list differs from the per-asset ledger entries")
    if without_candidate != sorted(selection.get("assets_without_candidate") or []):
        raise ManifestPublicationError("assets without candidates differ from the per-asset ledger entries")
    if selection.get("assets_without_candidate_reported") is not True:
        raise ManifestPublicationError("the selection outcome does not affirm reporting of assets without candidates")

    code_identity = dict(ledger.get("code_identity") or {})
    universe_hash = str(universe.get("manifest_hash") or "")
    benchmark = data.get("benchmark") or {}
    excluded = {
        str(item.get("binance_pair")): str(item.get("exclusion_reason"))
        for item in (freeze.get("band") or {}).get("members", [])
        if item.get("validated") is not True
    }
    selected_count = len(selected_assets)
    if selected_count and without_candidate:
        overall = "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    elif selected_count:
        overall = "CANDIDATES_SELECTED"
    else:
        overall = "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"
    frozen_candidate_set = {
        "count": len(expected_assets),
        "binance_pairs": sorted(expected_assets),
        "membership_rule": (run.get("scope") or {}).get("membership_rule"),
        "universe_manifest_path": UNIVERSE_RELATIVE,
        "universe_manifest_hash": universe_hash,
        "data_manifest_path": DATA_RELATIVE,
        "data_manifest_hash": str(data.get("manifest_hash")),
        "benchmark_asset": "BTCUSDT",
        "widening_by_reranking_forbidden": True,
        "excluded_assets_stay_excluded": True,
        "excluded_after_validation": dict(excluded),
    }
    document: Dict[str, Any] = {
        "artifact": "v6_selected_configurations_manifest",
        "artifact_version": "v6-selected-configurations-manifest-1",
        "version": 1,
        "protocol_version": "v6",
        "universe_version": "v6",
        "created_utc": str(ledger.get("completed_utc") or ""),
        "manifest_status": "PUBLISHED_FROM_COMPLETED_AUTHORIZED_SELECTION",
        "description": (
            "Published outcome of the single authorized v6 selection grid over the frozen "
            "seven-asset candidate set. It is derived from the completed v6 ledger and is "
            "bound to the unchanged v1 selection rule, v6 execution binding and frozen "
            "candidate/data/universe identities. It authorizes no confirmatory read or run."
        ),
        "run_identity": {
            "run_id": str(ledger.get("run_id")),
            "campaign_id": str(ledger.get("campaign_id")),
            "run_phase": str(ledger.get("run_phase")),
            "authorization_manifest_hash": auth_hash,
            "run_code_identity": code_identity.get("run_code_identity"),
            "authorized_code_hash": code_identity.get("authorized_code_hash"),
            "ordered_code_hash_authorized": code_identity.get("authorized_code_hash"),
            "hashed_set_digest": code_identity.get("hashed_set_digest"),
            "execution_path_digest": code_identity.get("execution_path_digest"),
            "code_identity_algorithm": code_identity.get("algorithm"),
            "selection_ledger_sha256": sha256_file(root / LEDGER_RELATIVE),
            "selection_execution_binding_manifest_hash": binding_hash,
        },
        "specification_identities": {
            "spec_v1_document_sha256": sha256_bytes(canonical(spec_v1).encode("utf-8")),
            "spec_v1_self_hash": spec_v1.get("specification_hash"),
            "spec_v6_document_sha256": sha256_bytes(canonical(spec_v6).encode("utf-8")),
            "spec_v6_self_hash": spec_v6.get("specification_hash"),
            "run_specification_hash": ledger.get("specification_hash"),
            "selection_rule_digest": selection_rule_hash,
            "selection_rule_reference": "configs/research_v1.json#selection",
        },
        "data_identities": {
            "universe_manifest_v6_hash": universe_hash,
            "effective_data_manifest_hash": str(data.get("manifest_hash")),
            "base_data_manifest_hash": str(data.get("manifest_hash")),
            "candidate_freeze_hash": freeze_hash,
            "benchmark_dataset_path": benchmark.get("dataset_path"),
            "benchmark_content_hash": benchmark.get("content_hash"),
        },
        "scope": {
            "frozen_candidate_set": frozen_candidate_set,
            "assets_evaluated": len(expected_assets),
            "candidate_assets": sorted(expected_assets),
            "candidate_count": len(expected_assets),
            "selected_assets": selected_assets,
            "selected_count": selected_count,
            "assets_without_candidate": without_candidate,
            "scope_is_not_reranked_or_widened": True,
        },
        "benchmark": {
            "symbol": "BTCUSDT",
            "dataset_path": benchmark.get("dataset_path"),
            "content_hash": benchmark.get("content_hash"),
            "role": "development benchmark and BTC trend-filter reference; never a candidate",
            "btc_configurations_dropped": False,
            "grid_rule": "all 576 btc_ema_168 configurations per asset remain in the 2,304-configuration v6 selection grid",
        },
        "derived_from": {
            "records_read": int((ledger.get("counts") or {}).get("records_written") or 0),
            "shard_directory": str((run.get("paths") or {}).get("shards_dir") or "research/shards_v6"),
            "results_manifest_path": RESULTS_MANIFEST_RELATIVE,
            "results_manifest_sha256": recomputed["results_manifest_sha256"],
            "ledger_path": LEDGER_RELATIVE,
            "selection_execution_binding_manifest_hash": binding_hash,
            "selection_rule_digest": selection_rule_hash,
            "experiment_ids_verified": True,
            "all_grid_units_present": True,
        },
        "exposure": {
            "holdout_exposed_count": int(ledger.get("holdout_exposed_count") or 0),
            "confirmatory_candles_read": 0,
            "v1_holdout_reuse": "forbidden",
            "v2_v3_v4_v5_confirmatory_window_reuse": "forbidden",
        },
        "authorizes": {
            "selection_run": False,
            "second_selection_run": False,
            "confirmatory_evaluation": False,
            "candle_fetch": False,
            "holdout_read": False,
        },
        "deviation_disclosure": dict(protocol.get("deviation_disclosure") or {}),
        "selections": selections,
        "outcome": overall,
        "assets_with_candidate": selected_assets,
        "assets_without_candidate": without_candidate,
        "assets_without_candidate_reported": True,
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

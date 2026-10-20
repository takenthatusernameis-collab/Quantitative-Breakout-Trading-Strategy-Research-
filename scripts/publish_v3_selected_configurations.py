#!/usr/bin/env python3
"""Publish the versioned v3 selected-configurations manifest from the verified shards.

The published artifact records the outcome of the authorized v3 selection run over the
frozen v3 candidate set.  The selection is **re-derived** here: the preregistered v1
selection rule is applied to the verified result shards, with the buy-and-hold baselines
recomputed from the hash-verified v3 datasets under the benchmark rule and the
development boundary enforced by the v3 loader.  The producer never copies the selection
out of the run ledger and never falls back to it: if the selection cannot be re-derived,
the producer fails loudly and writes nothing.

The producer reads development data only.  Every dataset is verified against the
effective v3 data manifest, and a dataset that reaches into the confirmatory window is
refused before it is read, so no confirmatory-window candle can enter this artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.baselines import baseline_for_asset, buyhold_baseline  # noqa: E402
from breakout_research.config import CostScenario  # noqa: E402
from breakout_research.selection import select_candidates  # noqa: E402
from v3_campaign.benchmark import assert_dataset_alignment  # noqa: E402
from v3_campaign.data import (  # noqa: E402
    BENCHMARK_SYMBOL,
    load_development_candles,
    parse_utc_ms,
    resolve_effective_data_manifest,
)
from v3_campaign.scope import frozen_scope, load_json, selection_rule  # noqa: E402
from v3_campaign.units import fold_bounds, validation_folds  # noqa: E402

ARTIFACT_PATH = REPO_ROOT / "research" / "v3_selected_configurations_manifest.json"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

# The creation instant is pinned so that the artifact is byte-reproducible.
CREATED_UTC = "2026-10-20T19:15:00Z"

FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
UNIVERSE_V3_RELATIVE = "research/universe_manifest_v3.json"
DATA_V3_RELATIVE = "research/data_manifest_v3.json"
DATA_AMENDMENT_1_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
LEDGER_V3_RELATIVE = "research/ledger_v3.json"
SELECTION_AUTH_RELATIVE = "configs/research_v3_selection_authorization_1.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v3_execution_amendment_1.json"
SHARDS_RELATIVE = "research/shards_v3"

# The re-derivation is expensive, so it is cached per content signature.  The signature
# covers every input the derivation consumes (the shard bytes, the effective v3 data
# manifest, the preregistered specification, the campaign id and the data boundary), so a
# cache hit can only happen when the evidence is unchanged.
_RECOMPUTATION_CACHE: Dict[str, Dict[str, Any]] = {}


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
    """A content signature of the campaign's shard files."""
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


def _effective_outcome(outcome: Dict[str, Any]) -> Tuple[List[str], List[str], str]:
    assets_with_candidate = sorted(
        asset for asset, entry in outcome.items() if entry.get("config_id")
    )
    assets_without_candidate = sorted(
        asset for asset, entry in outcome.items() if not entry.get("config_id")
    )
    if assets_with_candidate and assets_without_candidate:
        overall = "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    elif assets_with_candidate:
        overall = "CANDIDATES_SELECTED"
    else:
        overall = "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"
    return assets_with_candidate, assets_without_candidate, overall


def recompute_selection(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Re-derive the v3 selection from the verified shards.

    The preregistered v1 selection rule is re-applied to the shard records of the
    completed run.  The buy-and-hold baselines are recomputed from the hash-verified v3
    datasets exactly as the run computed them, the benchmark alignment is checked as the
    run checked it, and the development boundary is enforced by the v3 loader, so a
    dataset that reaches into the confirmatory window refuses to load.
    """
    root = Path(repo_root)

    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_V3_RELATIVE)
    universe = _load(root / UNIVERSE_V3_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    freeze_amendment_1 = _load(root / FREEZE_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = _load(root / FREEZE_AMENDMENT_2_RELATIVE)

    scope = frozen_scope(freeze, freeze_amendment_1, freeze_amendment_2, universe)
    rule_block, rule_digest = selection_rule(spec_v1, spec_v3)
    if rule_digest != str(ledger["selection"]["selection_block_sha256"]):
        raise ValueError(
            "the selection rule digest differs from the one the run recorded")

    campaign_id = str(ledger["campaign_id"])
    boundary_utc = str(scope["confirmatory_window_start_utc"])
    if str(ledger["data_boundary"]["candles_before_utc"]) != boundary_utc:
        raise ValueError(
            "the ledger's development boundary differs from the frozen confirmatory window start")
    pairs = [str(pair) for pair in scope["binance_pairs"]]

    data_manifest, effective_hash, provenance = resolve_effective_data_manifest(root)
    if effective_hash != str(scope["data_manifest_hash"]):
        raise ValueError(
            "the effective data-manifest identity differs from the identity the frozen "
            "candidate set binds")

    signature = "|".join((
        campaign_id,
        boundary_utc,
        effective_hash,
        sha256_bytes(canonical(spec_v1)),
        sha256_bytes(canonical(spec_v3)),
        _shard_signature(root / SHARDS_RELATIVE, campaign_id),
    ))
    cached = _RECOMPUTATION_CACHE.get(signature)
    if cached is not None:
        return cached

    boundary_ms = parse_utc_ms(boundary_utc)
    cost_scenarios = [
        CostScenario.baseline().scaled(float(value))
        for value in spec_v1["costs"]["scenarios"]
    ]

    benchmark_candles, benchmark_provenance = load_development_candles(
        root, BENCHMARK_SYMBOL, data_manifest, boundary_ms)

    baselines: Dict[str, Dict[str, Any]] = {}
    for symbol in pairs:
        candles, _provenance = load_development_candles(
            root, symbol, data_manifest, boundary_ms)
        assert_dataset_alignment(candles, benchmark_candles, symbol)
        windows = validation_folds(fold_bounds(candles, spec_v1["folds"]))
        baseline = buyhold_baseline(
            candles,
            {fold[2]: (fold[0], fold[1]) for fold in windows},
            cost_scenarios,
        )
        baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)

    records = iter_shard_records(root / SHARDS_RELATIVE / campaign_id)
    verified: List[Dict[str, Any]] = []
    for record in records:
        recomputed_eid = compute_experiment_id(
            spec_hash=str(record.get("specification_hash")),
            code_hash=str(record.get("code_hash")),
            data_hash=str(record.get("data_hash")),
            asset=str(record["asset"]),
            config_id=str(record["config_id"]),
            fold_index=int(record["fold_index"]),
            start_time=int(record["start_time"]),
            end_time=int(record["end_time"]),
            is_holdout=bool(record.get("is_holdout", False)),
            cost_multiplier=float(record["cost_multiplier"]),
            schema_version=str(record.get("schema_version", "result-shard-v1")),
        )
        if recomputed_eid != record.get("experiment_id"):
            raise ValueError(
                f"experiment_id mismatch for {record.get('asset')} {record.get('config_id')}")
        if record.get("is_holdout"):
            raise ValueError("holdout record found in the v3 selection shards")
        verified.append(record)

    outcome = select_candidates(verified, spec_v1, baselines, config_manifest)
    assets_with_candidate, assets_without_candidate, overall = _effective_outcome(outcome)

    result = {
        "signature": signature,
        "records_read": len(verified),
        "assets_with_candidate": assets_with_candidate,
        "assets_without_candidate": assets_without_candidate,
        "outcome": overall,
        "per_asset": {
            asset: {
                "config_id": entry.get("config_id"),
                "status": entry.get("status"),
                "economic_status": entry.get("economic_status"),
                "counts": entry.get("counts"),
            }
            for asset, entry in sorted(outcome.items())
        },
        "benchmark_content_hash": benchmark_provenance.get("content_hash"),
        "effective_data_manifest_hash": effective_hash,
        "data_manifest_provenance": provenance,
    }
    _RECOMPUTATION_CACHE[signature] = result
    return result


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Build the published v3 selected-configurations manifest."""
    root = Path(repo_root)
    freeze = _load(root / FREEZE_RELATIVE)
    freeze_amendment_1 = _load(root / FREEZE_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = _load(root / FREEZE_AMENDMENT_2_RELATIVE)
    universe = _load(root / UNIVERSE_V3_RELATIVE)
    data_manifest = _load(root / DATA_V3_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    ledger = _load(root / LEDGER_V3_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    execution_amendment_1 = _load(root / EXECUTION_AMENDMENT_1_RELATIVE)

    scope = frozen_scope(freeze, freeze_amendment_1, freeze_amendment_2, universe)
    pairs = [str(pair) for pair in scope["binance_pairs"]]

    recomputed = recompute_selection(root)
    records_read = int(recomputed["records_read"])
    if records_read != int(ledger["counts"]["records_written"]):
        raise ValueError(
            f"record count mismatch: {records_read} vs {ledger['counts']['records_written']}")

    selection_rule_digest = sha256_bytes(canonical(spec_v1["selection"]))
    benchmark = execution_amendment_1.get("benchmark_rule") or {}

    manifest: Dict[str, Any] = {
        "artifact": "v3_selected_configurations_manifest",
        "artifact_version": "v3-selected-configurations-manifest-1",
        "version": 1,
        "protocol_version": "v3",
        "universe_version": "v3",
        "created_utc": CREATED_UTC,
        "manifest_status": "PUBLISHED_FROM_VERIFIED_SHARDS",
        "description": (
            "Published outcome of the authorized v3 selection run over the frozen v3 "
            "candidate set, derived from verified shards under the unchanged v1 selection "
            "rule."),
        "run_identity": {
            "run_id": ledger["run_id"],
            "campaign_id": ledger["campaign_id"],
            "run_phase": ledger.get("run_phase"),
            "authorization_manifest_hash": selection_auth["manifest_hash"],
            "run_code_identity": ledger["code_identity"]["run_code_identity"],
            "authorized_code_hash": ledger["code_identity"]["authorized_code_hash"],
            "hashed_set_digest": ledger["code_identity"]["hashed_set_digest"],
            "execution_path_digest": ledger["code_identity"]["execution_path_digest"],
            "code_identity_algorithm": ledger["code_identity"]["algorithm"],
        },
        "specification_identities": {
            # The document digest is the sha256 of the canonical full JSON of the file;
            # the self-hash is the digest the specification declares for its own body.
            # Both are recorded under distinct names so that neither can be mistaken
            # for the other (README Section 2A E).
            "spec_v1_document_sha256": sha256_bytes(canonical(spec_v1)),
            "spec_v1_self_hash": spec_v1.get("specification_hash"),
            "spec_v3_document_sha256": sha256_bytes(canonical(spec_v3)),
            "spec_v3_self_hash": spec_v3.get("specification_hash"),
            "run_specification_hash": ledger.get("specification_hash"),
            "selection_rule_digest": selection_rule_digest,
            "selection_rule_reference": "configs/research_v1.json#selection",
        },
        "data_identities": {
            "universe_manifest_v3_hash": universe["manifest_hash"],
            "effective_data_manifest_hash": recomputed["effective_data_manifest_hash"],
            "base_data_manifest_hash": data_manifest["manifest_hash"],
            "data_manifest_amendment_1_hash": (
                recomputed["data_manifest_provenance"].get("amendment_manifest_hash")),
            "candidate_freeze_hash": freeze["manifest_hash"],
            "candidate_freeze_amendment_1_hash": freeze_amendment_1["manifest_hash"],
            "candidate_freeze_amendment_2_hash": freeze_amendment_2["manifest_hash"],
        },
        "scope": {
            "frozen_candidate_set": {
                "count": len(pairs),
                "binance_pairs": pairs,
                "membership_rule": (
                    "Exactly the validated candidate set of "
                    "configs/research_v3_candidate_freeze_amendment_1.json, re-derived from "
                    "the validated constituents of research/universe_manifest_v3.json. "
                    "Membership is not re-derived, re-ranked, widened or narrowed by this "
                    "artifact."),
                "universe_manifest_path": UNIVERSE_V3_RELATIVE,
                "universe_manifest_hash": universe["manifest_hash"],
                "base_data_manifest_path": DATA_V3_RELATIVE,
                "base_data_manifest_hash": data_manifest["manifest_hash"],
                "effective_data_manifest_hash": recomputed["effective_data_manifest_hash"],
                "excluded_after_validation": scope["excluded_after_validation"],
                "widening_by_reranking_forbidden": True,
                "excluded_assets_stay_excluded": True,
            },
            "assets_evaluated": len(pairs),
            "confirmatory_window_start_utc": scope["confirmatory_window_start_utc"],
            "min_confirmatory_window_hours": scope["min_confirmatory_window_hours"],
        },
        "benchmark": {
            "symbol": BENCHMARK_SYMBOL,
            "dataset_path": benchmark.get("dataset_path"),
            "content_hash": recomputed["benchmark_content_hash"],
            "alignment_rule": benchmark.get("alignment"),
            "role": benchmark.get("role"),
            "btc_configurations_dropped": False,
            "grid_rule": benchmark.get("grid_rule"),
        },
        "derived_from": {
            "records_read": records_read,
            "shard_directory": f"{SHARDS_RELATIVE}/{ledger['campaign_id']}",
            "results_manifest_path": "research/results_manifest_v3.json",
            "ledger_path": LEDGER_V3_RELATIVE,
            "experiment_ids_verified": True,
            "all_grid_units_present": records_read == int(
                ledger["counts"]["execution_units"]),
        },
        "exposure": {
            "holdout_exposed_count": int(ledger["holdout_exposed_count"]),
            "confirmatory_window_status": (
                (data_manifest.get("confirmatory_window") or {}).get(
                    "confirmatory_window_status")),
            "confirmatory_candles_read": 0,
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
        },
        "authorizes": {
            "selection_run": False,
            "second_run": False,
            "confirmatory_evaluation": False,
            "candle_fetch": False,
            "note": (
                "This artifact publishes the outcome of the completed authorized run. It "
                "authorizes no run, no evaluation and no candle read."),
        },
        "deviation_disclosure": {
            "scope": "the completed v1 and v2 runs",
            "statement": (
                "The completed v1 and v2 runs evaluated the BTC trend filter against a BTC "
                "EMA taken from a different period; the deviation is a disclosure for the "
                "final report and is not repaired here."),
            "records_with_btc_filter": 124416,
            "total_v2_records": 497664,
            "misaligned_validation_folds": [0, 1, 2, 3],
            "evidence_path": "research/v3_evidence/v1_v2_btc_alignment_deviation.json",
            "v3_run_alignment": (
                "the v3 run evaluated the BTC trend filter against the index-aligned v3 "
                "benchmark dataset"),
        },
        "selections": {},
        "outcome": recomputed["outcome"],
        "assets_with_candidate": recomputed["assets_with_candidate"],
        "assets_without_candidate": recomputed["assets_without_candidate"],
        "assets_without_candidate_reported": True,
    }

    for asset in sorted(pairs):
        entry = recomputed["per_asset"].get(asset) or {}
        status = entry.get("status")
        economic_status = entry.get("economic_status")
        config_id = entry.get("config_id")
        if config_id is not None and status == "CANDIDATE_SELECTED":
            manifest["selections"][asset] = {
                "asset": asset,
                "status": "CANDIDATE_SELECTED",
                "economic_status": economic_status or "CANDIDATE_PENDING_HOLDOUT",
                "config_id": config_id,
                "selected": True,
                "candidate_status": "CANDIDATE_PENDING_HOLDOUT",
                "counts": entry.get("counts"),
            }
        else:
            reason = status or economic_status or "NO_CANDIDATE"
            manifest["selections"][asset] = {
                "asset": asset,
                "status": status or reason,
                "economic_status": economic_status or reason,
                "config_id": None,
                "selected": False,
                "reason": reason,
                "candidate_status": reason,
                "counts": entry.get("counts"),
            }

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

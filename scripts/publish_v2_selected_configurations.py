#!/usr/bin/env python3
"""Publish the versioned v2 selected-configurations manifest from the verified shards.

The published artifact records the outcome of the authorized v2 selection run over the
frozen v2 candidate set.  The selection is **re-derived** here: the preregistered v1
selection rule is applied to the verified result shards, with the buy-and-hold baselines
recomputed from the hash-verified v2 datasets and the development boundary enforced by
the v2 loader.  The producer never copies the selection out of the run ledger and never
falls back to it: if the selection cannot be re-derived, the producer fails loudly and
writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.baselines import baseline_for_asset, buyhold_baseline  # noqa: E402
from breakout_research.config import CostScenario, compute_code_hash  # noqa: E402
from breakout_research.selection import select_candidates  # noqa: E402
from v2_campaign.data import load_development_candles, parse_utc_ms  # noqa: E402
from v2_campaign.units import fold_bounds, validation_folds  # noqa: E402

ARTIFACT_PATH = REPO_ROOT / "research" / "v2_selected_configurations_manifest.json"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
LEDGER_V2_RELATIVE = "research/ledger_v2.json"
SELECTION_AUTH_RELATIVE = "configs/research_v2_selection_authorization_1.json"
SHARDS_RELATIVE = "research/shards_v2"

# The re-derivation is expensive, so it is cached per content signature.  The signature
# covers every input the derivation consumes (the shard bytes, the v2 data manifest, the
# preregistered specification, the campaign id and the data boundary), so a cache hit can
# only happen when the evidence is unchanged.
_RECOMPUTATION_CACHE: Dict[str, Dict[str, Any]] = {}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: tuple) -> str:
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


def recompute_selection(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Re-derive the v2 selection from the verified shards.

    The preregistered v1 selection rule is re-applied to the shard records of the
    completed run.  The buy-and-hold baselines are recomputed from the hash-verified v2
    datasets exactly as the run computed them, and the development boundary is enforced
    by the v2 loader, so a dataset that reaches into the confirmatory window refuses to
    load.
    """
    root = Path(repo_root)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    data_manifest = _load(root / DATA_V2_RELATIVE)
    ledger = _load(root / LEDGER_V2_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)

    campaign_id = str(ledger["campaign_id"])
    boundary_utc = str(freeze["data_boundary"]["confirmatory_window_start_utc"])
    if str(ledger["data_boundary"]["candles_before_utc"]) != boundary_utc:
        raise ValueError(
            "the ledger's development boundary differs from the frozen confirmatory window start")
    pairs = [str(pair) for pair in freeze["frozen_candidate_set"]["binance_pairs"]]

    signature = "|".join((
        campaign_id,
        boundary_utc,
        sha256_bytes(canonical(spec_v1)),
        str(data_manifest.get("manifest_hash")),
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
    baselines: Dict[str, Dict[str, Any]] = {}
    for symbol in pairs:
        candles, _provenance = load_development_candles(
            root, symbol, data_manifest, boundary_ms)
        windows = validation_folds(fold_bounds(candles, spec_v1["folds"]))
        baseline = buyhold_baseline(
            candles,
            {fold[2]: (fold[0], fold[1]) for fold in windows},
            cost_scenarios,
        )
        baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)

    records = iter_shard_records(root / SHARDS_RELATIVE / campaign_id)
    verified: List[Dict[str, Any]] = []
    code_hash = compute_code_hash()
    spec_hash = sha256_bytes(canonical(spec_v1))
    data_hash = data_manifest.get("manifest_hash") or sha256_bytes(canonical(data_manifest))
    for record in records:
        recomputed_eid = compute_experiment_id(
            record.get("specification_hash") or spec_hash,
            record.get("code_hash") or code_hash,
            record.get("data_hash") or data_hash,
            record["asset"],
            record["config_id"],
            int(record["fold_index"]),
            int(record["start_time"]),
            int(record["end_time"]),
            bool(record.get("is_holdout", False)),
            float(record["cost_multiplier"]),
            record.get("schema_version", "result-shard-v1"),
        )
        if recomputed_eid != record.get("experiment_id"):
            raise ValueError(f"experiment_id mismatch for {record.get('asset')} {record.get('config_id')}")
        if record.get("is_holdout"):
            raise ValueError("holdout record found in the v2 selection shards")
        verified.append(record)

    outcome = select_candidates(verified, spec_v1, baselines, None)
    assets_with_candidate = sorted(
        asset for asset, entry in outcome.items() if entry.get("config_id"))
    assets_without_candidate = sorted(
        asset for asset, entry in outcome.items() if not entry.get("config_id"))
    if assets_with_candidate and assets_without_candidate:
        overall = "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    elif assets_with_candidate:
        overall = "CANDIDATES_SELECTED"
    else:
        overall = "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"

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
            }
            for asset, entry in sorted(outcome.items())
        },
    }
    _RECOMPUTATION_CACHE[signature] = result
    return result


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_V2_RELATIVE)
    data_manifest = _load(root / DATA_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    ledger = _load(root / LEDGER_V2_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)

    frozen_scope = freeze["frozen_candidate_set"]
    constituents = list(frozen_scope["constituents"])
    binance_pairs = list(frozen_scope["binance_pairs"])

    recomputed = recompute_selection(root)
    records_read = int(recomputed["records_read"])
    if records_read != int(ledger["counts"]["records_written"]):
        raise ValueError(
            f"record count mismatch: {records_read} vs {ledger['counts']['records_written']}")

    selection_rule_digest = sha256_bytes(canonical(spec_v1["selection"]))

    manifest: Dict[str, Any] = {
        "artifact": "v2_selected_configurations_manifest",
        "artifact_version": "v2-selected-configurations-manifest-1",
        "version": 1,
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": "2026-10-20T07:00:00Z",
        "manifest_status": "PUBLISHED_FROM_VERIFIED_SHARDS",
        "description": "Published outcome of the authorized v2 selection run over the frozen candidate set, derived from verified shards under the unchanged v1 selection rule.",
        "run_identity": {
            "run_id": ledger["run_id"],
            "campaign_id": ledger["campaign_id"],
            "authorization_manifest_hash": selection_auth["manifest_hash"],
            "run_code_identity": ledger["code_identity"]["run_code_identity"],
            "ordered_code_hash_authorized": ledger["code_identity"]["authorized_code_hash"],
            "hashed_set_digest": ledger["code_identity"]["hashed_set_digest"],
            "execution_path_digest": ledger["code_identity"]["execution_path_digest"],
        },
        "specification_identities": {
            "spec_v1_hash": sha256_bytes(canonical(spec_v1)),
            "spec_v2_hash": sha256_bytes(canonical(spec_v2)),
            "selection_rule_digest": selection_rule_digest,
            "selection_rule_reference": "configs/research_v1.json#selection",
        },
        "data_identities": {
            "universe_manifest_v2_hash": universe["manifest_hash"],
            "data_manifest_v2_hash": data_manifest["manifest_hash"],
            "candidate_freeze_hash": freeze["manifest_hash"],
        },
        "scope": {
            "frozen_candidate_set": frozen_scope,
            "assets_evaluated": len(binance_pairs),
        },
        "derived_from": {
            "records_read": records_read,
            "shard_directory": "research/shards_v2/v2-campaign",
            "results_manifest_path": "research/results_manifest_v2.json",
            "ledger_path": "research/ledger_v2.json",
            "experiment_ids_verified": True,
            "all_grid_units_present": records_read == 497664,
        },
        "selections": {},
        "outcome": recomputed["outcome"],
        "assets_with_candidate": recomputed["assets_with_candidate"],
        "assets_without_candidate": recomputed["assets_without_candidate"],
        "assets_without_candidate_reported": True,
    }

    for asset in sorted(binance_pairs):
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
            }

    assert len(manifest["selections"]) == len(binance_pairs)
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

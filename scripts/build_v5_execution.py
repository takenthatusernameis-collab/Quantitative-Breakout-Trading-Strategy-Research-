#!/usr/bin/env python3
"""Build the v5 execution protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V5_PATH = REPO_ROOT / "configs" / "research_v5.json"
FREEZE_V5_PATH = REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
UNIVERSE_V5_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"
DATA_V5_PATH = REPO_ROOT / "research" / "data_manifest_v5.json"
ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v5_execution.json"

MANIFEST_HASH_EXCLUDED_KEYS = ["manifest_hash"]


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys = MANIFEST_HASH_EXCLUDED_KEYS) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec_v1 = json.loads((repo_root / SPEC_V1_PATH).read_text(encoding="utf-8"))
    spec_v5 = json.loads((repo_root / SPEC_V5_PATH).read_text(encoding="utf-8"))
    freeze_v5 = json.loads((repo_root / FREEZE_V5_PATH).read_text(encoding="utf-8"))
    universe_v5 = json.loads((repo_root / UNIVERSE_V5_PATH).read_text(encoding="utf-8"))
    data_v5 = json.loads((repo_root / DATA_V5_PATH).read_text(encoding="utf-8"))

    document: Dict[str, Any] = {
        "artifact": "v5_execution_protocol",
        "artifact_version": "v5-execution-protocol-1",
        "protocol_version": "v5-execution",
        "universe_version": "v5",
        "manifest_hash": None,
        "specification_hash": spec_v5["specification_hash"],
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "specification_purpose": "Preregister how a future v5 grid run will be authorized and bounded. Design deliverable only; nothing runs.",
        "specification_status": "PREREGISTERED_EXECUTION_PROTOCOL_ONLY",
        "supersedes": {
            "protocol_version": "v4",
            "specification_path": "configs/research_v4_execution.json",
            "specification_hash": None,
        },
        "candidate_freeze_and_confirmatory_window": {
            "candidate_manifest_committed_and_hash_bound_before_first_confirmatory_candle": True,
            "candidate_freeze_path": str(FREEZE_V5_PATH.relative_to(repo_root)),
            "candidate_freeze_hash": freeze_v5["manifest_hash"],
            "confirmatory_window_opens_utc": freeze_v5["confirmatory_window"]["opens_utc"],
            "min_confirmatory_window_hours": 2160,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after freeze",
            "development_cutoff_utc": data_v5["window_policy"]["development_cutoff_utc"],
            "development_data_boundary_rule": "no v5 development candle may close inside any open confirmatory window; a candle that closes exactly at a window start is development data per the v5 specification amendment",
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
        },
        "evaluation_scope": {
            "universe_manifest_path": str(UNIVERSE_V5_PATH.relative_to(repo_root)),
            "universe_manifest_hash": universe_v5["manifest_hash"],
            "data_manifest_path": str(DATA_V5_PATH.relative_to(repo_root)),
            "data_manifest_hash": data_v5["manifest_hash"],
            "constituents": [a["binance_pair"] for a in universe_v5["eligible_assets"] if a.get("validated")],
            "count": len([a["binance_pair"] for a in universe_v5["eligible_assets"] if a.get("validated")]),
            "excluded_assets_stay_excluded": True,
            "widening_by_reranking_forbidden": True,
        },
        "benchmark_rule": {
            "symbol": "BTCUSDT",
            "dataset_path": "research/data/candles_v5/BTCUSDT_1h_626e639b02e54bc1.csv",
            "role": "trend_filter_and_benchmark",
            "rule": "The v5 benchmark must be the v5-cutoff-bounded dataset from research/data/candles_v5 (ends at the v5 development cutoff). The v4 chain's research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv cannot be reused for v5 because it contains candles that close after the v5 cutoff inside the open v2 confirmatory window.",
            "content_hash_must_match_canonical": True,
            "note": "The v5 benchmark is bounded at development_cutoff_utc 2026-10-19T22:00:00Z and is hash-verified before use.",
        },
        "selection_rule": {
            "inherit_from_v1_unchanged": True,
            "note": "v5 inherits the strategy grid, costs, execution semantics, fold structure, selection rule, pilot gate, metrics and baselines from v1 without modification (configs/research_v1.json).",
        },
        "code_hash_constraint": {
            "authorized_code_hash": "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2",
            "hashed_source_root": "src/breakout_research",
            "v5_execution_must_live_outside_hashed_set": True,
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
        },
        "resource_and_attempt_bounds": {
            "max_logical_runs": 1,
            "checkpoint_every_n_shards": 10,
        },
        "v5_result_layout": {
            "shard_directory": "research/shards_v5",
            "ledger_path": "research/ledger_v5.json",
            "results_manifest_path": "research/results_manifest_v5.json",
            "result_stream": "research/results_v5.jsonl",
            "checkpoint": "research_state/checkpoint_v5.json",
        },
        "authorization": {
            "execution_authorized": False,
            "campaign_authorized": False,
            "selection_authorized": False,
            "confirmatory_authorized": False,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": MANIFEST_HASH_EXCLUDED_KEYS,
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if ARTIFACT_PATH.exists() and not args.force:
        print(json.dumps({"ok": False, "error": "artifact exists; use --force to overwrite"}, indent=2))
        return 1
    document = build(Path(args.repo_root))
    ARTIFACT_PATH.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(ARTIFACT_PATH.relative_to(REPO_ROOT)), "manifest_hash": document["manifest_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

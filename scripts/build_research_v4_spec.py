#!/usr/bin/env python3
"""Build the preregistered v4 specification (BRAIN-013, universe version v4)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v4.json"

CREATED_UTC = "2026-10-20T23:16:00Z"
SNAPSHOT_NOT_BEFORE_UTC = "2026-10-20T23:16:00Z"
SNAPSHOT_DEADLINE_UTC = "2026-10-27T23:16:00Z"

MARKET_CAP_ENDPOINT = (
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
    "&order=market_cap_desc&per_page=250&page=1"
)

TOP_N = 20

INHERITED_BLOCKS = (
    "strategy_grid",
    "costs",
    "execution",
    "folds",
    "selection",
    "pilot",
    "metrics",
    "baselines",
    "fixed_breakout_baseline",
    "status",
    "checkpointing",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_specification_hash(spec: Dict[str, Any]) -> str:
    body = {key: value for key, value in spec.items() if key != "specification_hash"}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def prior_universe_floor(universe_v3: Dict[str, Any]) -> Dict[str, Any]:
    assets = universe_v3.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v3 universe manifest carries no eligible assets")
    lowest = min(assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol"))))
    return {
        "source_universe_version": universe_v3.get("universe_version"),
        "source_manifest_path": "research/universe_manifest_v3.json",
        "source_manifest_hash": universe_v3.get("manifest_hash"),
        "floor_symbol": lowest.get("symbol"),
        "floor_market_cap_usd": int(lowest.get("market_cap_usd") or 0),
        "comparison": "strictly_less_than",
        "recompute_rule": (
            "the floor is the minimum market_cap_usd over the eligible_assets of "
            "research/universe_manifest_v3.json; the verifier recomputes it from that "
            "manifest and never trusts this recorded value"
        ),
        "note": (
            "The v4 batch contains only assets that a fresh, deeper ranking places below "
            "the market capitalization of the lowest asset that universe version v3 "
            "evaluated. The v3 universe itself is not re-ranked, widened or narrowed."
        ),
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec_v1 = _load(repo_root / "configs" / "research_v1.json")
    spec_v2 = _load(repo_root / "configs" / "research_v2.json")
    spec_v3 = _load(repo_root / "configs" / "research_v3.json")
    universe_v2 = _load(repo_root / "research" / "universe_manifest_v2.json")
    universe_v3 = _load(repo_root / "research" / "universe_manifest_v3.json")
    freeze_v3 = _load(repo_root / "configs" / "research_v3_candidate_freeze.json")
    selected_v3 = _load(repo_root / "research" / "v3_selected_configurations_manifest.json")

    document: Dict[str, Any] = {
        "protocol_version": "v4",
        "universe_version": "v4",
        "specification_hash": None,
        "created_utc": CREATED_UTC,
        "specification_status": "PREREGISTERED_SPECIFICATION_ONLY",
        "specification_purpose": (
            "Preregister the rules for a fourth, separately versioned market-cap universe "
            "that is a strictly additional batch of assets below the v3 universe floor. "
            "This file is a design artifact: it freezes rules before any v4 data is "
            "retrieved or any v4 result exists, and it authorizes nothing."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-013",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-013 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "sections_implemented_here": [
                "BRAIN-013 recommendation 1: preregister the new version and its retrieval window first",
                "BRAIN-013 recommendation 2: retrieve exactly one market-cap snapshot inside the pinned window",
                "BRAIN-013 recommendation 3: validate every candidate against real provider data",
                "BRAIN-013 recommendation 4: separate namespaces for every version",
                "BRAIN-013 recommendation 4: extend identity rule to v1,v2,v3",
                "BRAIN-013 recommendation 6: inherit the strategy grid, costs, folds and selection rule unchanged",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v4 execution path",
                "any authorized v4 run",
                "any v4 confirmatory-window evaluation",
            ],
        },
        "supersedes": {
            "protocol_version": spec_v3.get("protocol_version"),
            "specification_path": "configs/research_v3.json",
            "specification_hash": spec_v3.get("specification_hash"),
            "universe_manifest_path": "research/universe_manifest_v3.json",
            "universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v3.json"),
            "universe_manifest_hash": universe_v3.get("manifest_hash"),
            "candidate_freeze_path": "configs/research_v3_candidate_freeze.json",
            "candidate_freeze_sha256": sha256_file(repo_root / "configs" / "research_v3_candidate_freeze.json"),
            "candidate_freeze_hash": freeze_v3.get("manifest_hash"),
            "selected_configurations_manifest_path": "research/v3_selected_configurations_manifest.json",
            "selected_configurations_manifest_sha256": sha256_file(
                repo_root / "research" / "v3_selected_configurations_manifest.json"
            ),
            "selected_configurations_manifest_hash": selected_v3.get("manifest_hash"),
            "reason": (
                "The v3 universe is frozen, its selection run has been performed and its "
                "confirmatory window is single-use. The v4 universe is a strictly additional "
                "batch of assets below the v3 universe floor, so it supersedes the v3 universe "
                "only in the sense that it is the program's current universe version."
            ),
            "supersession_scope": (
                "Additive only. The v1, v2 and v3 artifacts are not replaced, rewritten or "
                "reinterpreted: they remain immutable historical evidence, and the v4 "
                "candidate set contains no asset of any of them."
            ),
            "v1_artifacts_are_immutable": True,
            "v2_artifacts_are_immutable": True,
            "v3_artifacts_are_immutable": True,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "excluded_keys": ["specification_hash"],
            "verify_command": "python3 scripts/verify_research_v4_spec.py",
            "note": (
                "The specification_hash binds every other field of this file, including "
                "created_utc. Recomputing it over the parsed document with the key removed "
                "is the only accepted verification."
            ),
        },
        "inheritance": {
            "inherited_from": "configs/research_v1.json",
            "inherited_unchanged_blocks": list(INHERITED_BLOCKS),
            "inherited_from_v2_unchanged_blocks": ["data"],
            "changed_or_added_blocks": [
                "universe",
                "holdout",
                "comparability",
                "expansion_program",
                "prerequisites",
                "authorization",
            ],
            "statement": (
                "v4 changes the evaluated universe only. The strategy family, the "
                "2,304-configuration grid, cost assumptions, execution semantics, fold "
                "structure, selection rule, pilot gate, metrics, baselines and status "
                "vocabulary are inherited from v1 without modification, and the data "
                "retrieval contract is inherited from v2 without modification, so that v4 "
                "differs from v3 in which assets are evaluated and not in how a strategy "
                "is measured."
            ),
        },
        "universe": {
            "source": spec_v2["universe"]["source"],
            "endpoint": MARKET_CAP_ENDPOINT,
            "ranking_depth": 250,
            "eligible_quote": "USDT",
            "exchange": "binance",
            "market_type": "spot",
            "top_n": TOP_N,
            "min_history_years": spec_v2["universe"]["min_history_years"],
            "min_candles": spec_v2["universe"]["min_candles"],
            "exclusions": list(spec_v2["universe"]["exclusions"]),
            "benchmark_asset": "BTCUSDT",
            "survivorship_disclaimer": spec_v2["universe"]["survivorship_disclaimer"],
            "expansion_scope": {
                "rule": (
                    "The v4 universe is the next batch below the recorded floor: assets of a "
                    "fresh market-cap snapshot whose market capitalization is strictly below "
                    "the floor and that are not assets of the v1, v2, or v3 universe."
                ),
                "prior_universe_floor": prior_universe_floor(universe_v3),
                "prior_universe_asset_identity": {
                    "rule": "An asset is 'already in a prior universe' when its Binance symbol or its CoinGecko id already occurs in the eligible assets of the v1, v2, or v3 universe manifest.",
                    "sources": [
                        {"universe_version": "v1", "manifest_path": "research/universe_manifest.json", "manifest_hash": None},
                        {"universe_version": "v2", "manifest_path": "research/universe_manifest_v2.json", "manifest_hash": universe_v2.get("manifest_hash")},
                        {"universe_version": "v3", "manifest_path": "research/universe_manifest_v3.json", "manifest_hash": universe_v3.get("manifest_hash")},
                    ],
                    "matched_on": ["binance_symbol", "coingecko_id"],
                    "rename_rule": "A renamed asset keeps its CoinGecko id and is therefore the same asset; it is excluded from the v4 batch as already_in_prior_universe.",
                    "exclusion_reason": "already_in_prior_universe"
                },
                "ordering_rule": "Candidates are taken in strictly descending market-capitalization order after the prior-universe and exclusion rules have been applied; the batch contains exactly top_n assets unless the snapshot runs out of eligible names, in which case the shortfall is recorded."
            },
            "snapshot_retrieval": {
                "rule": "The v4 universe is exactly one timestamped market-cap snapshot retrieved inside the window below. The first successful retrieval inside the window is the v4 snapshot.",
                "not_before_utc": SNAPSHOT_NOT_BEFORE_UTC,
                "deadline_utc": SNAPSHOT_DEADLINE_UTC,
                "endpoint": MARKET_CAP_ENDPOINT,
                "depth": 250,
                "retrieval_policy": "exactly_once_read_only_bounded",
                "evidence_required": ["raw_market_cap_response.json", "snapshot_observation.json"],
                "reuse_forbidden": True,
                "re_timing_forbidden": True,
            },
        },
        "holdout": {
            "policy": "single_use_after_freeze",
            "v1_holdout_path": "research/data/holdout/holdout_index.json",
            "v1_holdout_exposed_count": 0,
            "v2_holdout_path": "research/data/holdout_v2/holdout_index.json",
            "v2_holdout_exposed_count": 0,
            "v3_holdout_path": "research/data/holdout_v3/holdout_index.json",
            "v3_holdout_exposed_count": 0,
            "v4_holdout_path": "research/data/holdout_v4/holdout_index.json",
            "v4_holdout_exposed_count": 0,
            "v1_v2_v3_holdout_never_reused_for_selection": True,
            "confirmatory_windows_are_single_use": True,
            "holdout_counted_on_every_confirmatory_read": True,
            "development_cutoff_utc": "2026-10-20T13:00:00Z",
            "development_data_cutoff_note": "BRAIN-013: any development data read at or after v3 window open is inside v3 confirmatory window; v4 development data bounded at cutoff with cost noted."
        },
        "comparability": {
            "rule": "v4 differs only in the universe. The grid, costs, execution, folds, selection rule and single confirmatory criterion are identical to v1.",
            "grid_specification_path": "configs/research_v1.json",
            "selection_rule_path": "configs/research_v1.json",
            "cost_model_path": "configs/research_v1.json",
        },
        "expansion_program": {
            "program": "continuous_universe_expansion",
            "append_only_log_path": "research/universe_expansion_log.jsonl",
            "routing": {
                "on_exhaustion_or_completion_of_frozen_version": "preregister_next_version_via_design_record_before_implementation",
                "rewrite_forbidden": True,
                "rerun_of_frozen_selection_forbidden": True,
            },
            "prior_versions": [
                {"version": "v1", "status": "terminal_or_frozen", "manifest_path": "research/universe_manifest.json"},
                {"version": "v2", "status": "frozen", "manifest_path": "research/universe_manifest_v2.json"},
                {"version": "v3", "status": "frozen", "manifest_path": "research/universe_manifest_v3.json"},
            ],
        },
        "prerequisites": {
            "p1": {"name": "preregister_v4_spec", "status": "DONE"},
            "p2": {"name": "retrieve_and_freeze_v4_universe", "status": "OUTSTANDING"},
            "p3": {"name": "validate_v4_candidates_and_freeze_data_manifest", "status": "OUTSTANDING"},
            "p4": {"name": "preregister_v4_execution_protocol_and_candidate_freeze", "status": "OUTSTANDING"},
        },
        "authorization": {
            "execution_authorized": False,
            "campaign_authorized": False,
            "selection_authorized": False,
            "confirmatory_authorized": False,
            "reason": "This specification authorizes nothing. All authorizations require separate, hash-bound artifacts and must not begin before their time gates.",
            "campaign_authorization_path": "research_state/campaign_authorization.json",
            "code_hash_must_remain_unchanged": True,
        },
    }

    for block in INHERITED_BLOCKS:
        if block in spec_v1:
            document[block] = json.loads(json.dumps(spec_v1[block]))

    document["specification_hash"] = compute_specification_hash(document)
    return document


def write_document(document: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing artifact")
    parser.add_argument("--print", action="store_true", dest="print_only", help="print JSON only")
    args = parser.parse_args(argv)

    document = build(REPO_ROOT)

    if args.print_only:
        print(json.dumps(document, indent=2))
        return 0

    if ARTIFACT_PATH.exists() and not args.force:
        print(f"refusing to overwrite existing {ARTIFACT_PATH} without --force", file=sys.stderr)
        return 1

    write_document(document, ARTIFACT_PATH)
    print(f"wrote {ARTIFACT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

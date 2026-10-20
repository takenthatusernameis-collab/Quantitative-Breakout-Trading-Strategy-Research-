#!/usr/bin/env python3
"""Build the preregistered v3 specification (BRAIN-012, universe version v3).

The v3 universe is a strictly additional batch of assets: it contains only
names that are not in the v1 or v2 universe and that lie below the recorded v2
universe floor. This script freezes the rules for that batch *before* any
retrieval happens, which is the ordering the decision record requires.

The artifact is deterministic: every field is either a pinned constant or is
derived from artifacts that are already hash-bound (the v1 specification, the
v2 specification, the v2 universe manifest, the v2 candidate freeze and the v2
selected-configurations manifest), so re-running the producer reproduces the
same bytes.

Usage::

    python3 scripts/build_research_v3_spec.py            # write the artifact
    python3 scripts/build_research_v3_spec.py --force    # rewrite it
    python3 scripts/build_research_v3_spec.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3.json"

#: The instant at which the v3 rules are frozen. It is pinned so that the
#: artifact is byte-reproducible, and it opens the retrieval window.
CREATED_UTC = "2026-10-20T11:45:00Z"

#: The preregistered retrieval window. The snapshot is retrieved exactly once,
#: inside this window; the window is never delayed, repeated or re-timed.
SNAPSHOT_NOT_BEFORE_UTC = "2026-10-20T11:45:00Z"
SNAPSHOT_DEADLINE_UTC = "2026-10-27T11:45:00Z"

#: The frozen endpoint. One bounded, read-only request to this URL is the v3
#: market-cap snapshot. The depth (250) is larger than the v2 depth (100)
#: because the v3 batch must reach below the v2 universe floor.
MARKET_CAP_ENDPOINT = (
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
    "&order=market_cap_desc&per_page=250&page=1"
)

#: The number of candidates evaluated per version.
TOP_N = 20

#: The blocks inherited byte-equal from the v1 specification.
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


def prior_universe_floor(universe_v2: Dict[str, Any]) -> Dict[str, Any]:
    """The market-capitalization floor below which the v3 batch must lie.

    The floor is the market capitalization of the lowest-ranked asset that
    universe version v2 actually evaluated. It is derived from the frozen v2
    universe manifest, never re-derived from a live ranking.
    """
    assets = universe_v2.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v2 universe manifest carries no eligible assets")
    lowest = min(assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol"))))
    return {
        "source_universe_version": universe_v2.get("universe_version"),
        "source_manifest_path": "research/universe_manifest_v2.json",
        "source_manifest_hash": universe_v2.get("manifest_hash"),
        "floor_symbol": lowest.get("symbol"),
        "floor_market_cap_usd": int(lowest.get("market_cap_usd") or 0),
        "comparison": "strictly_less_than",
        "recompute_rule": (
            "the floor is the minimum market_cap_usd over the eligible_assets of "
            "research/universe_manifest_v2.json; the verifier recomputes it from that "
            "manifest and never trusts this recorded value"
        ),
        "note": (
            "The v3 batch contains only assets that a fresh, deeper ranking places below "
            "the market capitalization of the lowest asset that universe version v2 "
            "evaluated. The v2 universe itself is not re-ranked, widened or narrowed."
        ),
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v3 specification from the frozen v1/v2 artifacts."""
    spec_v1 = _load(repo_root / "configs" / "research_v1.json")
    spec_v2 = _load(repo_root / "configs" / "research_v2.json")
    universe_v2 = _load(repo_root / "research" / "universe_manifest_v2.json")
    freeze_v2 = _load(repo_root / "configs" / "research_v2_candidate_freeze.json")
    selected_v2 = _load(repo_root / "research" / "v2_selected_configurations_manifest.json")

    document: Dict[str, Any] = {
        "protocol_version": "v3",
        "universe_version": "v3",
        "specification_hash": None,
        "created_utc": CREATED_UTC,
        "specification_status": "PREREGISTERED_SPECIFICATION_ONLY",
        "specification_purpose": (
            "Preregister the rules for a third, separately versioned market-cap universe "
            "that is a strictly additional batch of assets below the v2 universe floor. "
            "This file is a design artifact: it freezes rules before any v3 data is "
            "retrieved or any v3 result exists, and it authorizes nothing."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-012",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-012 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "sections_implemented_here": [
                "BRAIN-012 recommendation 1: preregister the new version and its retrieval window first",
                "BRAIN-012 recommendation 2: retrieve exactly one market-cap snapshot inside the pinned window",
                "BRAIN-012 recommendation 3: validate every candidate against real provider data",
                "BRAIN-012 recommendation 5: separate namespaces for every version",
                "BRAIN-012 recommendation 6: inherit the strategy grid, costs, folds and selection rule unchanged",
                "BRAIN-012 recommendation 7: keep an append-only cross-version expansion log",
                "BRAIN-012 recommendation 8: re-check on a bounded cadence and record a null result",
                "BRAIN-012 recommendation 9: route exhaustion to the next version, never to a rewrite",
            ],
            "sections_deliberately_not_implemented_here": [
                "BRAIN-012 acceptance test 4: the v3 execution path (src/v3_campaign/)",
                "BRAIN-012 acceptance test 9: any authorized v3 run",
                "any v3 confirmatory-window evaluation",
            ],
        },
        "supersedes": {
            "protocol_version": spec_v2.get("protocol_version"),
            "specification_path": "configs/research_v2.json",
            "specification_hash": spec_v2.get("specification_hash"),
            "universe_manifest_path": "research/universe_manifest_v2.json",
            "universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v2.json"),
            "universe_manifest_hash": universe_v2.get("manifest_hash"),
            "candidate_freeze_path": "configs/research_v2_candidate_freeze.json",
            "candidate_freeze_sha256": sha256_file(repo_root / "configs" / "research_v2_candidate_freeze.json"),
            "candidate_freeze_hash": freeze_v2.get("manifest_hash"),
            "selected_configurations_manifest_path": "research/v2_selected_configurations_manifest.json",
            "selected_configurations_manifest_sha256": sha256_file(
                repo_root / "research" / "v2_selected_configurations_manifest.json"
            ),
            "selected_configurations_manifest_hash": selected_v2.get("manifest_hash"),
            "reason": (
                "The v2 universe is frozen, its selection run has been performed and its "
                "confirmatory window is single-use. The v3 universe is a strictly additional "
                "batch of assets below the v2 universe floor, so it supersedes the v2 universe "
                "only in the sense that it is the program's current universe version."
            ),
            "supersession_scope": (
                "Additive only. The v1 and v2 artifacts are not replaced, rewritten or "
                "reinterpreted: they remain immutable historical evidence, and the v3 "
                "candidate set contains no asset of either of them."
            ),
            "v1_artifacts_are_immutable": True,
            "v2_artifacts_are_immutable": True,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "excluded_keys": ["specification_hash"],
            "verify_command": "python3 scripts/verify_research_v3_spec.py",
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
                "v3 changes the evaluated universe only. The strategy family, the "
                "2,304-configuration grid, cost assumptions, execution semantics, fold "
                "structure, selection rule, pilot gate, metrics, baselines and status "
                "vocabulary are inherited from v1 without modification, and the data "
                "retrieval contract is inherited from v2 without modification, so that v3 "
                "differs from v2 in which assets are evaluated and not in how a strategy "
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
                    "The v3 universe is the next batch below the recorded floor: assets of a "
                    "fresh market-cap snapshot whose market capitalization is strictly below "
                    "the floor and that are not assets of the v1 or v2 universe."
                ),
                "prior_universe_floor": prior_universe_floor(universe_v2),
                "prior_universe_asset_identity": {
                    "rule": (
                        "An asset is 'already in a prior universe' when its Binance symbol or "
                        "its CoinGecko id already occurs in the eligible assets of the v1 or "
                        "the v2 universe manifest."
                    ),
                    "sources": [
                        {
                            "universe_version": "v1",
                            "manifest_path": "research/universe_manifest.json",
                            "manifest_hash": _load(
                                repo_root / "research" / "universe_manifest.json"
                            ).get("manifest_hash"),
                        },
                        {
                            "universe_version": "v2",
                            "manifest_path": "research/universe_manifest_v2.json",
                            "manifest_hash": universe_v2.get("manifest_hash"),
                        },
                    ],
                    "matched_on": ["binance_symbol", "coingecko_id"],
                    "rename_rule": (
                        "A renamed asset keeps its CoinGecko id and is therefore the same "
                        "asset; it is excluded from the v3 batch as already_in_prior_universe."
                    ),
                    "exclusion_reason": "already_in_prior_universe",
                },
                "ordering_rule": (
                    "Candidates are taken in strictly descending market-capitalization order "
                    "after the prior-universe and exclusion rules have been applied; the "
                    "batch contains exactly top_n assets unless the snapshot runs out of "
                    "eligible names, in which case the shortfall is recorded."
                ),
            },
            "snapshot_retrieval": {
                "rule": (
                    "The v3 universe is exactly one timestamped market-cap snapshot retrieved "
                    "inside the window below. The first successful retrieval inside the window "
                    "is the v3 snapshot."
                ),
                "not_before_utc": SNAPSHOT_NOT_BEFORE_UTC,
                "deadline_utc": SNAPSHOT_DEADLINE_UTC,
                "if_window_expires": (
                    "Record the provider failure evidence with endpoint, HTTP status, probe "
                    "timestamp and command, and re-preregister a new window in a versioned "
                    "amendment. Never reuse an expired window silently."
                ),
                "no_cherry_picking": (
                    "The window is fixed by this specification. The retrieval must not be "
                    "delayed, repeated or re-timed to obtain a more convenient ranking, and "
                    "the snapshot must not be selected after seeing any strategy result."
                ),
                "raw_response_required": True,
                "raw_response_hash": (
                    "sha256 over the exact bytes of the provider response, stored beside the "
                    "v3 universe manifest"
                ),
                "prior_snapshots_are_not_re_retrieved": (
                    "The v1 snapshot (2026-10-15T17:10:38Z) and the v2 snapshot "
                    "(2026-10-19T18:47:56Z) are immutable historical evidence and are never "
                    "re-retrieved or re-timed."
                ),
            },
            "snapshot_identity": {
                "fields": [
                    "protocol_version",
                    "universe_version",
                    "specification_hash",
                    "market_cap_source_endpoint",
                    "market_cap_source_retrieval_timestamp_utc",
                    "code_hash",
                    "data_manifest_hash",
                    "candidate_manifest_hash",
                ],
                "note": (
                    "BRAIN-008 section 1, carried forward. Any artifact that freezes v3 "
                    "candidates must record this tuple."
                ),
            },
            "eligibility_validation": json.loads(json.dumps(spec_v2["universe"]["eligibility_validation"])),
        },
        "holdout": {
            "v1_holdout_status": spec_v2["holdout"]["v1_holdout_status"],
            "v1_holdout_reuse": "forbidden",
            "v1_holdout_note": spec_v2["holdout"]["v1_holdout_note"],
            "v2_confirmatory_window": {
                "status": "NOT_STARTED",
                "reuse_by_v3": "forbidden",
                "read_by_v3": "forbidden",
                "note": (
                    "The v2 confirmatory window is single-use evidence for the v2 candidate "
                    "set and cannot exist before 2027-01-17T22:00:00Z. A v3 expansion never "
                    "reads it, re-times it, reuses it or extends it (BRAIN-012 D-3), and the "
                    "v2 holdout exposure counter is not touched by any v3 artifact."
                ),
            },
            "v3_confirmatory_window": {
                "rule": (
                    "A fresh, unexposed confirmatory window evaluated only after the v3 "
                    "candidate manifest is frozen and hash-bound."
                ),
                "starts_after": "v3_candidate_freeze_timestamp_utc",
                "min_hours": 2160,
                "min_hours_rationale": spec_v2["holdout"]["v2_confirmatory_window"]["min_hours_rationale"],
                "overlap_with_v1_holdout": "forbidden",
                "overlap_with_v2_confirmatory_window": "forbidden",
                "data_used_for_candidate_selection": "excluded",
                "single_use": True,
                "access_counting": (
                    "Every read of a candle inside the v3 confirmatory window increments "
                    "holdout_exposed_count in the v3 checkpoint and is recorded in the v3 "
                    "holdout report."
                ),
                "not_a_v1_or_v2_holdout": (
                    "This is a new protocol object, not a re-opening of the v1 final holdout or "
                    "of the v2 confirmatory window. It is never populated with data that "
                    "predates the v3 candidate freeze."
                ),
            },
            "candidate_freeze_rule": (
                "The v3 candidate manifest (at most one candidate per asset, selected under "
                "the unchanged v1 selection block) must be committed and hash-bound before "
                "the first confirmatory-window candle is read."
            ),
            "promotion_rule": json.loads(json.dumps(spec_v2["holdout"]["promotion_rule"])),
            "v3_holdout_report_required_fields": [
                "universe_version",
                "snapshot_id",
                "candidate_manifest_path",
                "candidate_manifest_hash",
                "confirmatory_window_start_utc",
                "confirmatory_window_end_utc",
                "candles_evaluated",
                "exposure_count",
                "per_asset_outcomes",
                "comparability_statement",
            ],
        },
        "comparability": {
            "v1_cycle0_units": spec_v2["comparability"]["v1_cycle0_units"],
            "v2_selection_units": 497664,
            "statement": (
                "v1 cycle-0 results (497,664 validation-only units, 0 holdout units) and the "
                "v2 selection results (497,664 validation-only units, 0 holdout units) are "
                "bound to their own universes, grids and data manifests. They are not "
                "comparable to v3 results without a bridging analysis, and they are never "
                "restated, re-counted or extended by v3."
            ),
            "rules": [
                "v3 results must not be appended to, tallied with, or substituted into v1 or v2 shards, ledgers, manifests or tallies",
                "the v3 expansion neither confirms nor rejects any v1 or v2 candidate",
                "the v3 universe is an additional batch below the v2 floor, not a re-ranking of the v2 universe",
                "a bridging analysis is required before any cross-version quantitative comparison is reported",
            ],
            "bridging_analysis_required": True,
        },
        "expansion_program": {
            "log_path": "research/v_universe_expansion_log.json",
            "log_mode": "append_only_hash_chain",
            "log_entry_rule": (
                "Each universe version appends exactly one entry to the log. Every entry "
                "carries its own hash and the hash of the previous entry, so the log is "
                "append-only and its history is verifiable."
            ),
            "new_name_rule": (
                "A v3 candidate is an asset that is not in the v1 or v2 universe (matched on "
                "Binance symbol and CoinGecko id) and whose market capitalization is strictly "
                "below the recorded prior floor."
            ),
            "floor_rule": (
                "The floor of the next version is the market capitalization of the "
                "lowest-ranked candidate of this version."
            ),
            "cadence": {
                "mode": "bounded_cadence_not_polling",
                "pass_is_one_preregistered_version": True,
                "no_new_eligible_names_state": "AWAITING_NEW_CANDIDATES",
                "minimum_interval_between_passes": "P7D",
                "polling_forbidden": (
                    "The program must not contact the provider on every agent activation; a "
                    "pass is scheduled at the bounded cadence instead."
                ),
                "not_permanently_complete": (
                    "One pass without new eligible names does not make the program "
                    "permanently complete; the program re-checks at the bounded cadence."
                ),
            },
            "negative_result_handling": (
                "A pass that yields no currently eligible new names is recorded with the "
                "observed endpoint, timestamp, ranking depth and the validation/exclusion "
                "results, and the program enters AWAITING_NEW_CANDIDATES."
            ),
            "routing": (
                "Completion or exhaustion of one frozen version routes to the "
                "preregistration of the next version, never to a rewrite of the finished "
                "snapshot."
            ),
        },
        "prerequisites": [
            {
                "id": "P1",
                "requirement": (
                    "A preregistered v3 specification (universe, expansion scope, data "
                    "requirements, holdout) recorded in an immutable hashed spec"
                ),
                "artifact": "configs/research_v3.json",
                "status": "SATISFIED_BY_THIS_SPEC",
                "evidence": (
                    "specification_hash over the canonical content of this file, verified by "
                    "scripts/verify_research_v3_spec.py and tests/test_research_v3_spec.py"
                ),
            },
            {
                "id": "P2",
                "requirement": (
                    "A v3 universe manifest built from one snapshot inside the pinned window, "
                    "with every new constituent validated per the eligibility rules above"
                ),
                "artifact": "research/universe_manifest_v3.json",
                "status": "OUTSTANDING",
            },
            {
                "id": "P3",
                "requirement": "A v3 data manifest and candle verification artifacts",
                "artifact": "research/data_manifest_v3.json",
                "status": "OUTSTANDING",
            },
            {
                "id": "P4",
                "requirement": (
                    "A v3 candidate freeze that is hash-bound before any selection or "
                    "confirmatory read"
                ),
                "artifact": "configs/research_v3_candidate_freeze.json",
                "status": "OUTSTANDING",
            },
            {
                "id": "P5",
                "requirement": (
                    "A v3 execution protocol and an explicit bounded run authorization for at "
                    "most one logical run"
                ),
                "artifact": "configs/research_v3_execution.json and the v3 selection authorization",
                "status": "OUTSTANDING",
            },
            {
                "id": "P6",
                "requirement": (
                    "A preregistered v3 confirmatory-window protocol, its runbook and its "
                    "authorization, written before the window exists"
                ),
                "artifact": "the v3 confirmatory protocol and its amendments",
                "status": "OUTSTANDING",
            },
        ],
        "authorization": {
            "execution_authorized": False,
            "scope": (
                "This specification freezes rules. It does not authorize a v3 snapshot "
                "retrieval, a v3 data fetch, a v3 manifest, a v3 campaign, a v3 grid run, a "
                "v3 selection or any confirmatory-window evaluation."
            ),
            "not_authorized_by_this_specification_alone": [
                "retrieving the v3 market-cap snapshot outside the preregistered retrieval window",
                "fetching candles for any v3 constituent",
                "writing research/universe_manifest_v3.json or research/data_manifest_v3.json",
                "running any campaign, grid or backtest under v3",
                "reading any candle inside a v2 or v3 confirmatory window",
                "modifying configs/research_v1.json, configs/research_v2.json, any v1 or v2 manifest, the v1 or v2 shards, the v1 or v2 ledger or the exposed v1 holdout records",
            ],
            "next_session_authorization": (
                "A later session may implement P2 and P3 only: take the market-cap snapshot "
                "inside the pinned retrieval window, validate every candidate per the "
                "eligibility rules above, and write research/universe_manifest_v3.json and "
                "research/data_manifest_v3.json with the raw provider response and its hash. "
                "That session must not run a v3 campaign, a v3 grid, a v3 selection or any "
                "confirmatory-window evaluation, and it must not touch the v1 or v2 artifacts."
            ),
            "v1_campaign_authorization": (
                "Unchanged. research_state/campaign_authorization.json remains bound to "
                "protocol v1 and the v1 specification hash. This specification does not "
                "rotate, extend, re-authorize or revoke it, and it does not change the code "
                "hash."
            ),
            "v2_artifacts_authorization": (
                "Unchanged. The v2 specification, the v2 universe and data manifests, the v2 "
                "candidate freeze, the v2 selection authorization, the v2 selection ledger "
                "and the v2 selected-configurations manifest are immutable and remain the "
                "evidence of the completed v2 selection run."
            ),
            "unblocking_condition": (
                "P2, P3 and P4 committed and hash-bound are required before any v3 selection. "
                "Each further step requires its own recorded decision and evidence."
            ),
        },
    }

    for block in INHERITED_BLOCKS:
        document[block] = json.loads(json.dumps(spec_v1[block]))
    document["data"] = json.loads(json.dumps(spec_v2["data"]))

    document["specification_hash"] = compute_specification_hash(document)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / "configs" / "research_v3.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} specification_hash={document['specification_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

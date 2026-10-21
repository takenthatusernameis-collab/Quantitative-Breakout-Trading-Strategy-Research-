#!/usr/bin/env python3
"""Build the preregistered v5 specification (BRAIN-019, universe version v5).

Every identity the specification records is derived here from the artifact that
owns it: the v5 floor from ``research/universe_manifest_v4.json``, the
prior-universe identity sets from the four universe manifests, the three
confirmatory gates from the three candidate freezes, the code identities from
the source tree, and the ``supersedes`` chain from the v4 artifacts themselves.
Nothing is copied by hand and no digest is written as a literal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v5.json"

CREATED_UTC = "2026-10-21T09:40:00Z"
RETRIEVAL_WINDOW_DAYS = 7

MARKET_CAP_ENDPOINT = (
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
    "&order=market_cap_desc&per_page=250&page=1"
)
MARKET_CAP_ENDPOINT_PAGE_2 = (
    "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
    "&order=market_cap_desc&per_page=250&page=2"
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

PRIOR_UNIVERSE_MANIFESTS: Tuple[Tuple[str, str], ...] = (
    ("v1", "research/universe_manifest.json"),
    ("v2", "research/universe_manifest_v2.json"),
    ("v3", "research/universe_manifest_v3.json"),
    ("v4", "research/universe_manifest_v4.json"),
)

CONFIRMATORY_WINDOWS: Tuple[Tuple[str, str, str], ...] = (
    # version, freeze path, key inside the freeze that owns the window
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
)

UNTOUCHED_EXECUTION_PATHS: Tuple[Tuple[str, str, str], ...] = (
    (
        "src/v2_campaign",
        "c69cc02188d95def8a9c2e24f717ccc20c36035d5049a3216451e841dfe42cba",
        "configs/research_v2_selection_authorization_1.json",
    ),
    (
        "src/v2_confirmatory",
        "277a4bbec286b581ccb415fd88bb362ca2151e1b67745df23ad6802cee0ed4c9",
        "configs/research_v2_confirmatory_code_hash_amendment_1.json",
    ),
    (
        "src/v3_campaign",
        "29cd064e3f67e6bb66b052978bba61290adc97d4b3f8f7989fe2a01e1990cd55",
        "configs/research_v3_selection_authorization_1.json",
    ),
    (
        "src/v3_confirmatory",
        "747c2387ff85b73240d89f744a70e69f25c3af2e723a6d6191fda80e80c94aba",
        "configs/research_v3_confirmatory_authorization_1.json",
    ),
    (
        "src/v4_campaign",
        "49adc05c785304f32bbf64ef990c6788b0e32c8a069224acf740ae791ccee22f",
        "configs/research_v4_execution_amendment_1.json",
    ),
)

HASHED_SET_ROOT = "src/breakout_research"


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


def canonical_source_digest(root: Path) -> str:
    """The portable identity of the ``*.py`` tree under ``root`` (BRAIN-009)."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def base_symbol(marker: str) -> str:
    """The base Binance symbol of a marker (``BTCUSDT`` and ``BTC`` are one asset)."""
    text = str(marker or "").strip()
    if text.endswith("USDT"):
        return text[: -len("USDT")]
    return text


def prior_universe_identity(repo_root: Path) -> Dict[str, Any]:
    """The identity sets of the four prior universes, recomputed from the manifests."""
    sources: List[Dict[str, Any]] = []
    symbols: set = set()
    coingecko_ids: set = set()
    for version, relative in PRIOR_UNIVERSE_MANIFESTS:
        path = repo_root / relative
        manifest = _load(path)
        assets = manifest.get("eligible_assets") or []
        for asset in assets:
            symbol = asset.get("symbol")
            if symbol:
                symbols.add(base_symbol(symbol))
            coingecko_id = asset.get("coingecko_id")
            if coingecko_id:
                coingecko_ids.add(coingecko_id)
        sources.append(
            {
                "universe_version": version,
                "manifest_path": relative,
                "manifest_hash": manifest.get("manifest_hash"),
                "file_sha256": sha256_file(path),
                "eligible_asset_count": len(assets),
            }
        )
    return {
        "sources": sources,
        "distinct_prior_symbols": len(symbols),
        "distinct_prior_coingecko_ids": len(coingecko_ids),
    }


def prior_universe_floor(repo_root: Path) -> Dict[str, Any]:
    """The v5 floor, recomputed from the v4 manifest's eligible assets."""
    relative = "research/universe_manifest_v4.json"
    path = repo_root / relative
    manifest = _load(path)
    assets = manifest.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v4 universe manifest carries no eligible assets")
    lowest = min(assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol"))))
    validated = [entry for entry in assets if entry.get("validated")]
    validated_floor = min(
        validated, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol")))
    )
    return {
        "source_universe_version": manifest.get("universe_version"),
        "source_manifest_path": relative,
        "source_manifest_hash": manifest.get("manifest_hash"),
        "source_manifest_sha256": sha256_file(path),
        "floor_symbol": lowest.get("symbol"),
        "floor_market_cap_usd": int(lowest.get("market_cap_usd") or 0),
        "floor_market_cap_rank": lowest.get("market_cap_rank"),
        "comparison": "strictly_less_than",
        "recompute_rule": (
            "the floor is the minimum market_cap_usd over the eligible_assets of "
            "research/universe_manifest_v4.json; the verifier recomputes it from that "
            "manifest and never trusts this recorded value"
        ),
        "validated_set_floor": {
            "symbol": validated_floor.get("symbol"),
            "market_cap_usd": int(validated_floor.get("market_cap_usd") or 0),
            "market_cap_rank": validated_floor.get("market_cap_rank"),
            "note": (
                "recorded for transparency only: the floor rule uses the minimum over the "
                "eligible_assets of the source manifest, not the minimum over its validated subset"
            ),
        },
        "note": (
            "The v5 batch contains only assets that a fresh, deeper ranking places strictly "
            "below the market capitalization of the lowest asset that universe version v4 "
            "evaluated. The v4 universe itself is not re-ranked, widened or narrowed."
        ),
    }


def confirmatory_windows(repo_root: Path) -> List[Dict[str, Any]]:
    """The three open confirmatory windows, recomputed from the freezes that own them."""
    windows: List[Dict[str, Any]] = []
    for version, relative, key in CONFIRMATORY_WINDOWS:
        freeze = _load(repo_root / relative)
        block = freeze.get(key) or {}
        if key == "data_boundary":
            start = block.get("confirmatory_window_start_utc")
            min_hours = int(block.get("min_confirmatory_window_hours"))
        else:
            start = block.get("opens_utc")
            min_hours = int(block.get("min_hours"))
        if not start:
            raise SystemExit(f"{relative} does not carry the {version} confirmatory-window start")
        earliest = parse_utc(start) + timedelta(hours=min_hours)
        windows.append(
            {
                "version": version,
                "source_path": relative,
                "source_key": f"{key}",
                "window_start_utc": start,
                "min_hours": min_hours,
                "earliest_possible_end_utc": format_utc(earliest),
                "recorded_earliest_possible_end_utc": block.get(
                    "earliest_possible_confirmatory_window_end_utc"
                )
                or block.get("earliest_possible_end_utc"),
                "evaluation_may_not_start_before": format_utc(earliest),
            }
        )
    return windows


def development_window(cutoff: datetime, candle_count: int) -> Dict[str, Any]:
    last_open = cutoff - timedelta(hours=1)
    first_open = last_open - timedelta(hours=candle_count - 1)
    return {
        "candle_count": candle_count,
        "interval": "1h",
        "closed_candles_only": True,
        "first_candle_open_timestamp_ms": int(first_open.timestamp() * 1000),
        "last_candle_open_timestamp_ms": int(last_open.timestamp() * 1000),
        "first_candle_open_utc": format_utc(first_open),
        "last_candle_close_utc": format_utc(cutoff),
        "recompute_rule": (
            "the window is the closed hourly candle span that ends at the development "
            "cutoff: the last candle is the one that closes exactly at the cutoff and the "
            "first candle opens candle_count - 1 hours before it; the verifier recomputes "
            "both bounds from the cutoff and the candle count"
        ),
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec_v1 = _load(repo_root / "configs" / "research_v1.json")
    spec_v2 = _load(repo_root / "configs" / "research_v2.json")
    spec_v3 = _load(repo_root / "configs" / "research_v3.json")
    spec_v4 = _load(repo_root / "configs" / "research_v4.json")
    universe_v4 = _load(repo_root / "research" / "universe_manifest_v4.json")
    data_v4 = _load(repo_root / "research" / "data_manifest_v4.json")
    freeze_v4 = _load(repo_root / "configs" / "research_v4_candidate_freeze.json")
    selected_v4 = _load(repo_root / "research" / "v4_selected_configurations_manifest.json")
    campaign_authorization = _load(repo_root / "research_state" / "campaign_authorization.json")
    expansion_log = _load(repo_root / "research" / "v_universe_expansion_log.json")

    identity = prior_universe_identity(repo_root)
    floor = prior_universe_floor(repo_root)
    windows = confirmatory_windows(repo_root)

    earliest_window_start = min(parse_utc(window["window_start_utc"]) for window in windows)
    development_cutoff = format_utc(earliest_window_start)
    candle_count = int(spec_v2["data"]["min_candles"])

    hashed_set_digest = canonical_source_digest(repo_root / HASHED_SET_ROOT)
    execution_paths = [
        {
            "root": root,
            "canonical_source_digest": canonical_source_digest(repo_root / root),
            "recorded_canonical_source_digest": recorded,
            "owner": owner,
        }
        for root, recorded, owner in UNTOUCHED_EXECUTION_PATHS
    ]

    eligibility_validation = json.loads(json.dumps(spec_v3["universe"]["eligibility_validation"]))
    eligibility_validation["data_integrity"]["data_manifest"] = "research/data_manifest_v5.json"
    eligibility_validation["data_integrity"]["data_manifest_note"] = (
        "the v5 chain's own data manifest; the v3 block names the v2 manifest, which the v3 chain "
        "corrected by reference in configs/research_v3_spec_amendment_1.json"
    )

    created = parse_utc(CREATED_UTC)
    deadline = created + timedelta(days=RETRIEVAL_WINDOW_DAYS)

    document: Dict[str, Any] = {
        "protocol_version": "v5",
        "universe_version": "v5",
        "specification_hash": None,
        "created_utc": CREATED_UTC,
        "specification_status": "PREREGISTERED_SPECIFICATION_ONLY",
        "specification_purpose": (
            "Preregister the rules for a fifth, separately versioned market-cap universe that is "
            "a strictly additional batch of assets below the v4 universe floor. This file is a "
            "design artifact: it freezes rules before any v5 data is retrieved or any v5 result "
            "exists, and it authorizes nothing."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-019",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-019 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "sections_implemented_here": [
                "BRAIN-019 recommendation 1: a new v5 version with one new pinned-window retrieval, a depth policy, the v5 floor recomputed from the v4 manifest and the identity rule extended to v1,v2,v3,v4",
                "BRAIN-019 recommendation 2: the development data bounded at the earliest open confirmatory window, with an explicit definition of window membership",
                "BRAIN-019 recommendation 3: the phase gates against the three pending confirmatory evaluations",
                "BRAIN-019 recommendation 4: the isolated v5 namespace, the supersedes chain, the portable code identity and the expansion-log completion",
                "BRAIN-019 recommendation 5: the AWAITING_NEW_CANDIDATES null-result path with the bounded cadence",
                "BRAIN-019 recommendation 6: the falsifiers, the rollback and the staged acceptance tests are recorded in the decision record",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v5 market-cap retrieval and the v5 universe and data manifests",
                "the v5 execution path",
                "any authorized v5 run",
                "any v5 confirmatory-window evaluation",
                "the expansion-log entries (the derived v4 entry and the v5 entry)",
            ],
        },
        "supersedes": {
            "protocol_version": spec_v4.get("protocol_version"),
            "specification_path": "configs/research_v4.json",
            "specification_hash": spec_v4.get("specification_hash"),
            "specification_sha256": sha256_file(repo_root / "configs" / "research_v4.json"),
            "universe_manifest_path": "research/universe_manifest_v4.json",
            "universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v4.json"),
            "universe_manifest_hash": universe_v4.get("manifest_hash"),
            "data_manifest_path": "research/data_manifest_v4.json",
            "data_manifest_sha256": sha256_file(repo_root / "research" / "data_manifest_v4.json"),
            "data_manifest_hash": data_v4.get("manifest_hash"),
            "candidate_freeze_path": "configs/research_v4_candidate_freeze.json",
            "candidate_freeze_sha256": sha256_file(repo_root / "configs" / "research_v4_candidate_freeze.json"),
            "candidate_freeze_hash": freeze_v4.get("manifest_hash"),
            "selected_configurations_manifest_path": "research/v4_selected_configurations_manifest.json",
            "selected_configurations_manifest_sha256": sha256_file(
                repo_root / "research" / "v4_selected_configurations_manifest.json"
            ),
            "selected_configurations_manifest_hash": selected_v4.get("manifest_hash"),
            "reason": (
                "The v4 universe is frozen, its eligible pool is exhausted, its selection run has "
                "been performed and published, and its confirmatory window is single-use. The v5 "
                "universe is a strictly additional batch of assets below the v4 universe floor, so "
                "it supersedes the v4 universe only in the sense that it is the program's current "
                "universe version."
            ),
            "supersession_scope": (
                "Additive only. The v1, v2, v3 and v4 artifacts are not replaced, rewritten or "
                "reinterpreted: they remain immutable historical evidence, and the v5 candidate "
                "set contains no asset of any of them."
            ),
            "v1_artifacts_are_immutable": True,
            "v2_artifacts_are_immutable": True,
            "v3_artifacts_are_immutable": True,
            "v4_artifacts_are_immutable": True,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "excluded_keys": ["specification_hash"],
            "verify_command": "python3 scripts/verify_research_v5_spec.py",
            "note": (
                "The specification_hash binds every other field of this file, including "
                "created_utc. Recomputing it over the parsed document with the key removed is the "
                "only accepted verification."
            ),
        },
        "inheritance": {
            "inherited_from": "configs/research_v1.json",
            "inherited_unchanged_blocks": list(INHERITED_BLOCKS),
            "inherited_from_v2_unchanged_blocks": ["data"],
            "inherited_from_v3_unchanged_blocks": ["eligibility_validation"],
            "changed_or_added_blocks": [
                "universe",
                "holdout",
                "phase_gates",
                "code_identity",
                "namespace",
                "fresh_checkout_verifiability",
                "null_result_path",
                "expansion_program",
                "prerequisites",
                "authorization",
            ],
            "statement": (
                "v5 changes the evaluated universe only. The strategy family, the "
                "2,304-configuration grid, cost assumptions, execution semantics, fold structure, "
                "selection rule, pilot gate, metrics, baselines, status vocabulary and the single "
                "confirmatory criterion are inherited from v1 without modification, the data "
                "retrieval contract is inherited from v2 without modification and the eligibility "
                "validation rules are inherited from v3 without modification, so that v5 differs "
                "from v4 in which assets are evaluated and not in how a strategy is measured."
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
            "depth_policy": {
                "rule": (
                    "The v5 snapshot records the ranking depth that was actually retrieved. The "
                    "depth is recomputed from the raw response bytes and never copied from a "
                    "recorded value: the v3 expansion-log entry recorded 99 while the v3 raw "
                    "response holds 250 rows."
                ),
                "primary_page": {"per_page": 250, "page": 1, "depth": 250},
                "bounded_extra_page": {
                    "endpoint": MARKET_CAP_ENDPOINT_PAGE_2,
                    "per_page": 250,
                    "page": 2,
                    "cumulative_depth": 500,
                    "condition": (
                        "read only when the first page yields fewer than top_n qualifying names "
                        "after the exclusion rules and the prior-universe identity rule have been "
                        "applied"
                    ),
                    "max_extra_pages": 1,
                },
                "pages_recorded": (
                    "each page's raw bytes, its sha256 and its retrieval timestamp are recorded "
                    "separately"
                ),
                "batch_recomputation": (
                    "the batch is re-derived from the concatenated raw pages of the recorded "
                    "snapshot and is never copied from a recorded member list"
                ),
                "forbidden": [
                    "re-reading a page",
                    "a third page",
                    "re-timing or repeating the retrieval to obtain a more convenient ranking",
                ],
            },
            "expansion_scope": {
                "rule": (
                    "The v5 universe is the next batch below the recorded floor: assets of a fresh "
                    "market-cap snapshot whose market capitalization is strictly below the floor "
                    "and that are not assets of the v1, v2, v3 or v4 universe."
                ),
                "prior_universe_floor": floor,
                "prior_universe_asset_identity": {
                    "rule": (
                        "An asset is 'already in a prior universe' when its Binance symbol or its "
                        "CoinGecko id already occurs in the eligible assets of the v1, v2, v3 or v4 "
                        "universe manifest."
                    ),
                    "sources": identity["sources"],
                    "matched_on": ["binance_symbol", "coingecko_id"],
                    "symbol_normalization": (
                        "the Binance marker is the base symbol: the 'USDT' suffix of a binance_pair "
                        "is stripped before the comparison, so 'BTCUSDT' and 'BTC' are one marker"
                    ),
                    "distinct_prior_symbols": identity["distinct_prior_symbols"],
                    "distinct_prior_coingecko_ids": identity["distinct_prior_coingecko_ids"],
                    "counts_note": (
                        "the two counts are the numbers of distinct prior-universe assets, "
                        "recomputed by the verifier from the four manifests; the base symbol and "
                        "the pair spelling of the same Binance symbol are one marker, not two"
                    ),
                    "rename_rule": (
                        "A renamed asset keeps its CoinGecko id and is therefore the same asset; it "
                        "is excluded from the v5 batch as already_in_prior_universe."
                    ),
                    "exclusion_reason": "already_in_prior_universe",
                },
                "ordering_rule": (
                    "Candidates are taken in strictly descending market-capitalization order after "
                    "the prior-universe and exclusion rules have been applied; the batch contains "
                    "exactly top_n assets unless the snapshot runs out of eligible names, in which "
                    "case the shortfall is recorded."
                ),
            },
            "snapshot_retrieval": {
                "rule": (
                    "The v5 universe is exactly one timestamped market-cap snapshot retrieved "
                    "inside the window below. The first successful retrieval inside the window is "
                    "the v5 snapshot."
                ),
                "not_before_utc": CREATED_UTC,
                "deadline_utc": format_utc(deadline),
                "window_days": RETRIEVAL_WINDOW_DAYS,
                "endpoint": MARKET_CAP_ENDPOINT,
                "depth": 250,
                "retrieval_policy": "exactly_once_read_only_bounded",
                "evidence_required": ["raw_market_cap_response.json", "snapshot_observation.json"],
                "reuse_forbidden": True,
                "re_timing_forbidden": True,
                "expired_window_rule": (
                    "if the pinned window expires before a successful retrieval, the provider "
                    "failure evidence is recorded and a new window is preregistered in a versioned "
                    "amendment; the expired window is never reused or re-timed"
                ),
            },
            "eligibility_validation": eligibility_validation,
        },
        "holdout": {
            "policy": "single_use_after_freeze",
            "v1_holdout_path": "research/data/holdout/holdout_index.json",
            "v1_holdout_status": "EXPOSED_OR_UNKNOWN",
            "v1_holdout_status_source": "configs/research_v2_candidate_freeze.json#data_boundary",
            "v2_holdout_path": "research/data/holdout_v2/holdout_index.json",
            "v2_holdout_exposed_count": 0,
            "v3_holdout_path": "research/data/holdout_v3/holdout_index.json",
            "v3_holdout_exposed_count": 0,
            "v4_holdout_path": "research/data/holdout_v4/holdout_index.json",
            "v4_holdout_exposed_count": 0,
            "v5_holdout_path": "research/data/holdout_v5/holdout_index.json",
            "v5_holdout_exposed_count": 0,
            "v1_v2_v3_v4_holdout_never_reused_for_selection": True,
            "confirmatory_windows_are_single_use": True,
            "holdout_counted_on_every_confirmatory_read": True,
            "holdout_counter_rule": (
                "the v5 checkpoint starts holdout_exposed_count at 0 and increments it on every "
                "read of a candle inside any confirmatory window, counting by the "
                "confirmatory_window_membership rule; the v1, v2, v3 and v4 counters are never "
                "reused and never reset"
            ),
            "development_cutoff_utc": development_cutoff,
            "development_cutoff_rule": (
                "the v5 development data ends at the last fully closed hour that closes at or "
                "before the cutoff: the last development candle is the one that closes exactly at "
                "the cutoff, and no candle that closes after the cutoff may be read (the "
                "inclusive convention of BRAIN-015)"
            ),
            "development_cutoff_recompute_rule": (
                "the cutoff is the earliest confirmatory-window start among the windows that are "
                "open, recomputed from the v2, v3 and v4 candidate freezes; the verifier "
                "recomputes it and never trusts this recorded value"
            ),
            "development_cutoff_cost": (
                "the cutoff is the v2 confirmatory window's start, so it is earlier than the v4 "
                "chain's cutoff: the v5 development window is correspondingly shorter, and no v5 "
                "development read can fall inside any open confirmatory window"
            ),
            "development_window": development_window(earliest_window_start, candle_count),
            "confirmatory_window_membership": {
                "rule": (
                    "a candle is inside a confirmatory window when the close timestamp of the "
                    "candle falls in that window's time range, regardless of which asset the "
                    "candle belongs to"
                ),
                "interval_start_inclusive": True,
                "interval_end_exclusive": True,
                "asset_scope": (
                    "any asset, including assets that are not candidates of the window's own "
                    "version"
                ),
                "consequence": (
                    "no v5 read may fall inside the v2, the v3 or the v4 confirmatory window, so "
                    "the exposure question that is open for the v2, v3 and v4 chains cannot arise "
                    "for v5"
                ),
            },
            "v5_confirmatory_window": {
                "rule": (
                    "A fresh, unexposed confirmatory window evaluated only after the v5 candidate "
                    "manifest is frozen and hash-bound."
                ),
                "starts_after": "v5_candidate_freeze_timestamp_utc",
                "min_hours": 2160,
                "min_hours_rationale": (
                    "90 days of closed hourly candles; the v1 protocol used a 0.2 holdout fraction "
                    "of a multi-year window, which is of the same order."
                ),
                "overlap_with_v1_holdout": "forbidden",
                "overlap_with_v2_confirmatory_window": "forbidden",
                "overlap_with_v3_confirmatory_window": "forbidden",
                "overlap_with_v4_confirmatory_window": "forbidden",
                "data_used_for_candidate_selection": "excluded",
                "single_use": True,
                "access_counting": (
                    "Every read of a candle inside the v5 confirmatory window increments "
                    "holdout_exposed_count in the v5 checkpoint and is recorded in the v5 holdout "
                    "report."
                ),
                "not_a_prior_holdout": (
                    "This is a new protocol object, not a re-opening of the v1 final holdout or of "
                    "the v2, v3 or v4 confirmatory windows. It is never populated with data that "
                    "predates the v5 candidate freeze."
                ),
                "window_path": "configs/research_v5_confirmatory_protocol.json",
            },
            "v1_holdout_reuse": "forbidden",
        },
        "phase_gates": {
            "rule": (
                "Each confirmatory evaluation is version-isolated: a confirmation is never re-run, "
                "never re-tuned on, and its result is never used to select anything. A window is "
                "never read for selection."
            ),
            "gates": [
                {
                    "version": window["version"],
                    "window_start_utc": window["window_start_utc"],
                    "min_hours": window["min_hours"],
                    "earliest_possible_end_utc": window["earliest_possible_end_utc"],
                    "evaluation_may_not_start_before": window["evaluation_may_not_start_before"],
                    "source_path": window["source_path"],
                    "source_key": window["source_key"],
                }
                for window in windows
            ],
            "gate_recompute_rule": (
                "each gate instant is recomputed by the verifier from the freeze that owns the "
                "window: the window start plus min_hours"
            ),
            "v5_selection_run_gate": (
                "only after the v5 candidate freeze and the v5 selection authorization exist, and "
                "only on data that ends at the development cutoff"
            ),
            "v5_confirmatory_gate": (
                "the v5 evaluation may not start before the v4 gate clears and not before the v5 "
                "window's own minimum of 2160 closed hourly candles has elapsed"
            ),
            "v5_retrieval_is_not_a_candle_read": (
                "a market-cap snapshot is universe metadata, not price data; it may be retrieved "
                "inside the v5 pinned window and is not a confirmatory read"
            ),
        },
        "code_identity": {
            "algorithm": "canonical_source_digest_v1",
            "portable": True,
            "hashed_set_root": HASHED_SET_ROOT,
            "hashed_set_digest": hashed_set_digest,
            "authorized_ordered_code_hash": campaign_authorization.get("code_hash"),
            "authorized_ordered_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
            "ordered_code_hash_is_portable": False,
            "ordered_digest_note": (
                "the live ordered digest of compute_code_hash() is an environment fact of the "
                "checkout's directory enumeration order and is never used as an identity; the "
                "canonical digest is the tree identity"
            ),
            "untouched_execution_paths": execution_paths,
            "v5_execution_path_rule": (
                "if the v5 chain needs an execution path it is a new directory outside the hashed "
                "set, with its own canonical digest; it is never added to src/breakout_research"
            ),
            "rotation_rule": (
                "any deliberate rotation of a digest requires a published, versioned code-hash "
                "amendment, as the v2 chain did"
            ),
        },
        "namespace": {
            "rule": (
                "every v5 artifact has its own name; no v5 artifact is written into a v1, v2, v3 "
                "or v4 path, and no v1, v2, v3 or v4 artifact is edited in place"
            ),
            "specification": "configs/research_v5.json",
            "universe_manifest": "research/universe_manifest_v5.json",
            "data_manifest": "research/data_manifest_v5.json",
            "datasets_directory": "research/data/candles_v5/",
            "evidence_directory": "research/v5_evidence/",
            "candidate_freeze": "configs/research_v5_candidate_freeze.json",
            "execution_protocol": "configs/research_v5_execution.json",
            "selection_authorization": "configs/research_v5_selection_authorization_1.json",
            "confirmatory_protocol": "configs/research_v5_confirmatory_protocol.json",
            "confirmatory_runbook": "configs/research_v5_confirmatory_runbook_1.json",
            "shards_directory": "research/shards_v5/",
            "ledger": "research/ledger_v5.json",
            "results_manifest": "research/results_manifest_v5.json",
            "result_stream": "research/results_v5.jsonl",
            "checkpoint": "research_state/checkpoint_v5.json",
            "result_stream_durability": (
                "the result stream is an uncommitted projection of the verified shards, because it "
                "exceeds the per-file push limit; a v5 verifier treats its absence as not "
                "materialized and reports the shard projection's digest instead of failing"
            ),
        },
        "fresh_checkout_verifiability": {
            "rule": (
                "every v5 verifier and every v5 acceptance check must pass on a checkout that "
                "holds no v5 run artifacts: an absent uncommitted projection is reported, not "
                "failed, and every identity check uses the canonical digest, never the "
                "checkout-dependent ordered digest"
            ),
            "reference_pattern": (
                "scripts/verify_v2_selection_run.py reports result_stream_sha256: null and does not "
                "fail when the projection is absent"
            ),
            "rejected_pattern": (
                "scripts/verify_v3_selection_run.py and scripts/verify_v4_selection_run.py failed "
                "on a fresh checkout before BRAIN-020 repaired their test modules"
            ),
        },
        "null_result_path": {
            "state": "AWAITING_NEW_CANDIDATES",
            "rule": (
                "a v5 pass that yields no eligible new name records AWAITING_NEW_CANDIDATES with "
                "the full evidence bundle below and schedules the next pass at the bounded "
                "cadence; the campaign is never declared complete because one snapshot was empty"
            ),
            "evidence_required": [
                "the observed endpoint, as the exact URL",
                "the observed HTTP status, or the transport error",
                "the probe timestamp",
                "the exact command",
                "the ranking depth retrieved and the depth recomputed from the raw bytes",
                "the number of assets evaluated",
                "the exclusion reasons with counts by reason",
                "the number excluded by the prior-universe identity rule",
                "the snapshot's raw bytes and their sha256",
                "the next scheduled pass",
            ],
            "cadence": {
                "cadence_mode": "bounded_cadence_not_polling",
                "minimum_interval_between_passes": "P7D",
                "polling_forbidden": (
                    "The program must not contact the provider on every agent activation; a pass "
                    "is scheduled at the bounded cadence instead."
                ),
            },
            "campaign_completion_rule": (
                "complete is a state reached only by a version whose cycle finished and whose "
                "confirmatory evaluation was performed; an empty pass is a scheduled retry, never "
                "a terminal state"
            ),
        },
        "comparability": {
            "rule": (
                "v5 differs only in the universe. The grid, costs, execution, folds, selection rule "
                "and single confirmatory criterion are identical to v1."
            ),
            "grid_specification_path": "configs/research_v1.json",
            "selection_rule_path": "configs/research_v1.json",
            "cost_model_path": "configs/research_v1.json",
        },
        "expansion_program": {
            "program": "continuous_universe_expansion",
            "append_only_log_path": expansion_log.get("log_path"),
            "append_only_log_mode": expansion_log.get("log_mode"),
            "append_only_log_entry_rule": expansion_log.get("entry_rule"),
            "append_only_log_path_note": (
                "configs/research_v4.json#expansion_program.append_only_log_path names "
                "research/universe_expansion_log.jsonl, a file that does not exist; the v5 "
                "specification names the log that exists. The v4 specification is hash-bound and "
                "is not edited in place, so the discrepancy is recorded here as a supersession "
                "note."
            ),
            "log_state_at_preregistration": {
                "entry_count": expansion_log.get("entry_count"),
                "versions_present": [entry.get("universe_version") for entry in expansion_log.get("entries") or []],
                "missing_entries": ["v4"],
                "note": (
                    "a historical statement of the log at the time of preregistration: the v4 "
                    "universe version was never appended to the log, so the v5 implementation must "
                    "append the derived v4 entry before the v5 entry"
                ),
            },
            "pending_log_entries": [
                "the derived v4 entry, re-derived from the v4 artifacts with its ranking depth recomputed from the v4 raw response",
                "the v5 entry, chained onto the v4 entry",
            ],
            "log_entry_rule": (
                "each universe version appends exactly one entry carrying its own hash and the "
                "hash of the previous entry; an entry is never hand-written, it is derived from "
                "the artifacts of its own version"
            ),
            "routing": {
                "on_exhaustion_or_completion_of_frozen_version": (
                    "preregister_next_version_via_design_record_before_implementation"
                ),
                "rewrite_forbidden": True,
                "rerun_of_frozen_selection_forbidden": True,
            },
            "prior_versions": [
                {"version": version, "status": "frozen", "manifest_path": relative}
                for version, relative in PRIOR_UNIVERSE_MANIFESTS
            ],
        },
        "prerequisites": {
            "p1": {"name": "preregister_v5_spec", "status": "DONE"},
            "p2": {"name": "retrieve_and_freeze_v5_universe", "status": "OUTSTANDING"},
            "p3": {"name": "validate_v5_candidates_and_freeze_data_manifest", "status": "OUTSTANDING"},
            "p4": {"name": "preregister_v5_execution_protocol_and_candidate_freeze", "status": "OUTSTANDING"},
            "p5": {"name": "append_the_derived_v4_entry_and_the_v5_entry_to_the_expansion_log", "status": "OUTSTANDING"},
        },
        "authorization": {
            "execution_authorized": False,
            "campaign_authorized": False,
            "selection_authorized": False,
            "confirmatory_authorized": False,
            "reason": (
                "This specification authorizes nothing. All authorizations require separate, "
                "hash-bound artifacts and must not begin before their time gates."
            ),
            "campaign_authorization_path": "research_state/campaign_authorization.json",
            "code_hash_must_remain_unchanged": True,
        },
    }

    for block in INHERITED_BLOCKS:
        if block in spec_v1:
            document[block] = json.loads(json.dumps(spec_v1[block]))
    document["data"] = json.loads(json.dumps(spec_v2["data"]))

    document["specification_hash"] = compute_specification_hash(document)
    return document


def write_document(document: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
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

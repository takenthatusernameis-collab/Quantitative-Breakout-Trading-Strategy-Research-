#!/usr/bin/env python3
"""Build the preregistered v6 specification (BRAIN-026, universe version v6).

Every identity the specification records is derived here from the artifact that
owns it: the v6 floor from ``research/universe_manifest_v5.json``, the
prior-universe identity sets from the five universe manifests, the development
cutoff and the four confirmatory gates from the candidate freezes, the benchmark
boundary from the benchmark datasets themselves, the code identities from the
source tree, and the ``supersedes`` chain from the v5 artifacts.  Nothing is
copied by hand and no digest is written as a literal.

The specification authorizes nothing: it freezes the rules of the v6 chain
before any v6 data is retrieved or any v6 result exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v6.json"

#: The pinned creation instant of the v6 specification.  It opens the v6
#: market-cap retrieval window and is part of the specification's hash.
CREATED_UTC = "2026-10-22T00:45:00Z"

RETRIEVAL_WINDOW_DAYS = 7

#: The universe versions whose expansion-log entries existed when the v6
#: specification was preregistered.  The log is append-only, so this pinned
#: history stays the prefix of the log once the v6 entry is appended and the
#: document stays reproducible from this producer.
PINNED_LOG_VERSIONS = ("v3", "v4", "v5")

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
    ("v5", "research/universe_manifest_v5.json"),
)

CONFIRMATORY_WINDOWS: Tuple[Tuple[str, str, str], ...] = (
    # version, freeze path, key inside the freeze that owns the window
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

UNTOUCHED_EXECUTION_PATHS: Tuple[Tuple[str, str], ...] = (
    ("src/v2_campaign", "configs/research_v2_selection_authorization_1.json"),
    ("src/v2_confirmatory", "configs/research_v2_confirmatory_code_hash_amendment_1.json"),
    ("src/v3_campaign", "configs/research_v3_selection_authorization_1.json"),
    ("src/v3_confirmatory", "configs/research_v3_confirmatory_authorization_1.json"),
    ("src/v4_campaign", "configs/research_v4_execution_amendment_1.json"),
    ("src/v5_campaign", "configs/research_v5_selection_authorization_1.json"),
)

HASHED_SET_ROOT = "src/breakout_research"

#: The benchmark dataset the v5 chain froze.  It already ends with a candle that
#: closes exactly at the v6 development cutoff, so it may be reused under the
#: benchmark rule -- bound by its recomputed content hash and not silently.
V5_BENCHMARK_DATASET = "research/data/candles_v5/BTCUSDT_1h_626e639b02e54bc1.csv"

#: The v3 chain's benchmark dataset.  Its last 13 candles close inside the open
#: v2 confirmatory window, so the v6 chain may not reuse it unchanged.
V3_BENCHMARK_DATASET = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"


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


def dataset_last_candle_open_ms(path: Path) -> int:
    """The open timestamp of the last candle of a canonical hourly CSV dataset."""
    last = ""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                last = line
    if not last:
        raise SystemExit(f"{path} holds no candle rows")
    return int(last.split(",", 1)[0])


def dataset_candle_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip()) - 1


def prior_universe_identity(repo_root: Path) -> Dict[str, Any]:
    """The identity sets of the five prior universes, recomputed from the manifests."""
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
    """The v6 floor, recomputed from the v5 manifest's eligible assets."""
    relative = "research/universe_manifest_v5.json"
    path = repo_root / relative
    manifest = _load(path)
    assets = manifest.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v5 universe manifest carries no eligible assets")
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
            "research/universe_manifest_v5.json; the verifier recomputes it from that "
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
            "The v6 batch contains only assets that a fresh, deeper ranking places strictly "
            "below the market capitalization of the lowest asset that universe version v5 "
            "evaluated. The v5 universe itself is not re-ranked, widened or narrowed."
        ),
    }


def confirmatory_windows(repo_root: Path) -> List[Dict[str, Any]]:
    """The four open confirmatory windows, recomputed from the freezes that own them."""
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


def benchmark_rule(repo_root: Path, cutoff: datetime) -> Dict[str, Any]:
    """The benchmark rule, with both datasets recomputed from their bytes."""
    reusable_path = repo_root / V5_BENCHMARK_DATASET
    reusable_hash = sha256_file(reusable_path)
    reusable_last_open = dataset_last_candle_open_ms(reusable_path)
    reusable_close = reusable_last_open + 3600 * 1000
    reusable_count = dataset_candle_count(reusable_path)

    forbidden_path = repo_root / V3_BENCHMARK_DATASET
    forbidden_hash = sha256_file(forbidden_path)
    forbidden_last_open = dataset_last_candle_open_ms(forbidden_path)
    forbidden_close = forbidden_last_open + 3600 * 1000
    cutoff_ms = int(cutoff.timestamp() * 1000)
    candles_after_cutoff = (forbidden_close - cutoff_ms) // 3600000

    return {
        "rule": (
            "The benchmark series the v6 chain uses must be bounded at the v6 development "
            "cutoff, and the v6 execution protocol must bind it by its recomputed content "
            "hash; a benchmark that is reused without that binding is a defect (BRAIN-016)."
        ),
        "boundary_rule": (
            "the benchmark dataset's last candle must close at or before the development "
            "cutoff; a dataset whose last candle closes after the cutoff is refused"
        ),
        "binding_rule": (
            "the v6 execution protocol names the benchmark dataset path and its recomputed "
            "content hash (sha256-canonical-hourly-csv-v1 over the dataset file's bytes)"
        ),
        "recompute_rule": (
            "the verifier recomputes the content hash of every dataset this rule names from "
            "the file on disk and recomputes the last candle's close from the dataset's last "
            "row; it never trusts a recorded digest"
        ),
        "reusable_dataset": {
            "path": V5_BENCHMARK_DATASET,
            "content_hash": reusable_hash,
            "hash_algorithm": "sha256-canonical-hourly-csv-v1",
            "candle_count": reusable_count,
            "last_candle_open_timestamp_ms": reusable_last_open,
            "last_candle_close_utc": format_utc(
                datetime.fromtimestamp(reusable_close / 1000, tz=timezone.utc)
            ),
            "closes_after_the_cutoff": reusable_close > cutoff_ms,
            "reuse_condition": (
                "the v5 chain's benchmark dataset already ends with a candle that closes "
                "exactly at the v6 development cutoff, so it satisfies the boundary rule; it "
                "may be reused only if the v6 execution protocol binds it by the recomputed "
                "content hash and states the boundary rule"
            ),
        },
        "forbidden_dataset": {
            "path": V3_BENCHMARK_DATASET,
            "content_hash": forbidden_hash,
            "hash_algorithm": "sha256-canonical-hourly-csv-v1",
            "last_candle_open_timestamp_ms": forbidden_last_open,
            "last_candle_close_utc": format_utc(
                datetime.fromtimestamp(forbidden_close / 1000, tz=timezone.utc)
            ),
            "candles_closing_after_the_cutoff": int(candles_after_cutoff),
            "reason": (
                "the v3 chain's benchmark dataset ends with a candle that closes after the v6 "
                "development cutoff, inside the open v2 confirmatory window, so it is not "
                "reused unchanged by the v6 chain"
            ),
        },
        "forbidden": [
            "a benchmark dataset whose last candle closes after the development cutoff",
            "a benchmark bound without its recomputed content hash",
            "a silent reuse of a benchmark dataset owned by another version",
        ],
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec_v1 = _load(repo_root / "configs" / "research_v1.json")
    spec_v2 = _load(repo_root / "configs" / "research_v2.json")
    spec_v3 = _load(repo_root / "configs" / "research_v3.json")
    spec_v5 = _load(repo_root / "configs" / "research_v5.json")
    universe_v5 = _load(repo_root / "research" / "universe_manifest_v5.json")
    data_v5 = _load(repo_root / "research" / "data_manifest_v5.json")
    freeze_v5 = _load(repo_root / "configs" / "research_v5_candidate_freeze.json")
    selected_v5 = _load(repo_root / "research" / "v5_selected_configurations_manifest.json")
    campaign_authorization = _load(repo_root / "research_state" / "campaign_authorization.json")
    expansion_log = _load(repo_root / "research" / "v_universe_expansion_log.json")

    identity = prior_universe_identity(repo_root)
    floor = prior_universe_floor(repo_root)
    windows = confirmatory_windows(repo_root)

    earliest_window_start = min(parse_utc(window["window_start_utc"]) for window in windows)
    latest_window_end = max(parse_utc(window["earliest_possible_end_utc"]) for window in windows)
    development_cutoff = format_utc(earliest_window_start)
    candle_count = int(spec_v2["data"]["min_candles"])

    hashed_set_digest = canonical_source_digest(repo_root / HASHED_SET_ROOT)
    execution_paths = [
        {
            "root": root,
            "canonical_source_digest": canonical_source_digest(repo_root / root),
            "recorded_canonical_source_digest": canonical_source_digest(repo_root / root),
            "owner": owner,
        }
        for root, owner in UNTOUCHED_EXECUTION_PATHS
    ]

    eligibility_validation = json.loads(json.dumps(spec_v3["universe"]["eligibility_validation"]))
    eligibility_validation["data_integrity"]["data_manifest"] = "research/data_manifest_v6.json"
    eligibility_validation["data_integrity"]["data_manifest_note"] = (
        "the v6 chain's own data manifest; the v3 block names the v2 manifest, which the v3 "
        "chain corrected by reference in configs/research_v3_spec_amendment_1.json"
    )

    created = parse_utc(CREATED_UTC)
    deadline = created + timedelta(days=RETRIEVAL_WINDOW_DAYS)

    log_entries = expansion_log.get("entries") or []
    entries_by_version = {
        entry.get("universe_version"): entry for entry in log_entries if entry.get("universe_version")
    }
    missing_versions = [version for version in PINNED_LOG_VERSIONS if version not in entries_by_version]
    if missing_versions:
        raise SystemExit(
            f"the expansion log holds no entry for {missing_versions}, so the pinned log "
            "history cannot be derived"
        )
    pinned_log_entries = [entries_by_version[version] for version in PINNED_LOG_VERSIONS]
    last_log_entry = pinned_log_entries[-1]

    document: Dict[str, Any] = {
        "protocol_version": "v6",
        "universe_version": "v6",
        "specification_hash": None,
        "created_utc": CREATED_UTC,
        "specification_status": "PREREGISTERED_SPECIFICATION_ONLY",
        "specification_purpose": (
            "Preregister the rules for a sixth, separately versioned market-cap universe that "
            "is a strictly additional batch of assets below the v5 universe floor. This file is "
            "a design artifact: it freezes rules before any v6 data is retrieved or any v6 "
            "result exists, and it authorizes nothing."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-026",
            "decision_record": (
                "research_state/brainstorming_queue.md -> BRAIN-026 "
                "(DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)"
            ),
            "sections_implemented_here": [
                "BRAIN-026 recommendation 1: a new v6 version with one new pinned-window retrieval, the v6 floor recomputed from the v5 manifest, the identity rule extended to v1,v2,v3,v4,v5, the band-width rule and the depth policy inherited from v5",
                "BRAIN-026 recommendation 2: the development data bounded at the earliest open confirmatory window, with an explicit definition of window membership and the benchmark rule",
                "BRAIN-026 recommendation 3: the phase gates against the four pending confirmatory evaluations, with the v6 window as the fifth and last gate",
                "BRAIN-026 recommendation 4: the isolated v6 namespace, the supersedes chain from the five v5 identities, the portable code identity and the expansion-log append",
                "BRAIN-026 recommendation 5: the AWAITING_NEW_CANDIDATES null-result path with the bounded cadence, the depth-limit case and the empty-validated-set case",
                "BRAIN-026 recommendation 6: the falsifiers, the rollback and the staged acceptance tests are recorded in the decision record",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v6 market-cap retrieval and the v6 universe and data manifests",
                "the v6 candidate freeze, execution protocol and selection authorization",
                "the v6 execution path",
                "any authorized v6 run",
                "any v6 confirmatory-window evaluation",
                "the v6 expansion-log entry",
            ],
        },
        "supersedes": {
            "protocol_version": spec_v5.get("protocol_version"),
            "specification_path": "configs/research_v5.json",
            "specification_hash": spec_v5.get("specification_hash"),
            "specification_sha256": sha256_file(repo_root / "configs" / "research_v5.json"),
            "universe_manifest_path": "research/universe_manifest_v5.json",
            "universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v5.json"),
            "universe_manifest_hash": universe_v5.get("manifest_hash"),
            "data_manifest_path": "research/data_manifest_v5.json",
            "data_manifest_sha256": sha256_file(repo_root / "research" / "data_manifest_v5.json"),
            "data_manifest_hash": data_v5.get("manifest_hash"),
            "candidate_freeze_path": "configs/research_v5_candidate_freeze.json",
            "candidate_freeze_sha256": sha256_file(repo_root / "configs" / "research_v5_candidate_freeze.json"),
            "candidate_freeze_hash": freeze_v5.get("manifest_hash"),
            "selected_configurations_manifest_path": "research/v5_selected_configurations_manifest.json",
            "selected_configurations_manifest_sha256": sha256_file(
                repo_root / "research" / "v5_selected_configurations_manifest.json"
            ),
            "selected_configurations_manifest_hash": selected_v5.get("manifest_hash"),
            "reason": (
                "The v5 universe is frozen, its eligible pool is exhausted, its selection run "
                "has been performed and published, and its confirmatory window is single-use. "
                "The v6 universe is a strictly additional batch of assets below the v5 universe "
                "floor, so it supersedes the v5 universe only in the sense that it is the "
                "program's current universe version."
            ),
            "supersession_scope": (
                "Additive only. The v1, v2, v3, v4 and v5 artifacts are not replaced, "
                "rewritten or reinterpreted: they remain immutable historical evidence, and "
                "the v6 candidate set contains no asset of any of them."
            ),
            "v1_artifacts_are_immutable": True,
            "v2_artifacts_are_immutable": True,
            "v3_artifacts_are_immutable": True,
            "v4_artifacts_are_immutable": True,
            "v5_artifacts_are_immutable": True,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "excluded_keys": ["specification_hash"],
            "verify_command": "python3 scripts/verify_research_v6_spec.py",
            "note": (
                "The specification_hash binds every other field of this file, including "
                "created_utc. Recomputing it over the parsed document with the key removed is "
                "the only accepted verification."
            ),
        },
        "inheritance": {
            "inherited_from": "configs/research_v1.json",
            "inherited_unchanged_blocks": list(INHERITED_BLOCKS),
            "inherited_from_v2_unchanged_blocks": ["data"],
            "inherited_from_v3_unchanged_blocks": ["eligibility_validation"],
            "inherited_from_v3_documented_deviations": [
                "universe.eligibility_validation.data_integrity.data_manifest names the v6 "
                "chain's own data manifest instead of the v2 manifest the v3 block names; the "
                "deviation is recorded in that block's data_manifest_note"
            ],
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
                "v6 changes the evaluated universe only. The strategy family, the "
                "2,304-configuration grid, cost assumptions, execution semantics, fold "
                "structure, selection rule, pilot gate, metrics, baselines, status vocabulary "
                "and the single confirmatory criterion are inherited from v1 without "
                "modification, the data retrieval contract is inherited from v2 without "
                "modification and the eligibility validation rules are inherited from v3 "
                "without modification, so that v6 differs from v5 in which assets are "
                "evaluated and not in how a strategy is measured."
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
                    "The v6 snapshot records the ranking depth that was actually retrieved. "
                    "The depth is recomputed from the raw response bytes and never copied from "
                    "a recorded value: the v3 expansion-log entry recorded 99 while the v3 raw "
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
                        "after the exclusion rules and the prior-universe identity rule have "
                        "been applied"
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
                    "The v6 universe is the next batch below the recorded floor: assets of a "
                    "fresh market-cap snapshot whose market capitalization is strictly below "
                    "the floor and that are not assets of the v1, v2, v3, v4 or v5 universe."
                ),
                "prior_universe_floor": floor,
                "prior_universe_asset_identity": {
                    "rule": (
                        "An asset is 'already in a prior universe' when its Binance symbol or "
                        "its CoinGecko id already occurs in the eligible assets of the v1, v2, "
                        "v3, v4 or v5 universe manifest."
                    ),
                    "sources": identity["sources"],
                    "matched_on": ["binance_symbol", "coingecko_id"],
                    "symbol_normalization": (
                        "the Binance marker is the base symbol: the 'USDT' suffix of a "
                        "binance_pair is stripped before the comparison, so 'BTCUSDT' and 'BTC' "
                        "are one marker"
                    ),
                    "distinct_prior_symbols": identity["distinct_prior_symbols"],
                    "distinct_prior_coingecko_ids": identity["distinct_prior_coingecko_ids"],
                    "counts_note": (
                        "the two counts are the numbers of distinct prior-universe assets, "
                        "recomputed by the verifier from the five manifests; the base symbol "
                        "and the pair spelling of the same Binance symbol are one marker, not "
                        "two"
                    ),
                    "rename_rule": (
                        "A renamed asset keeps its CoinGecko id and is therefore the same "
                        "asset; it is excluded from the v6 batch as already_in_prior_universe."
                    ),
                    "exclusion_reason": "already_in_prior_universe",
                },
                "band_width_rule": {
                    "rule": (
                        "The v6 batch is exactly top_n names taken in strictly descending "
                        "market-capitalization order after the exclusion rules and the "
                        "prior-universe identity rule have been applied. The band is a "
                        "market-cap band: the validated subset is a consequence of the band, "
                        "never its definition."
                    ),
                    "band_width": TOP_N,
                    "band_width_source": "universe.top_n",
                    "ordering": "strictly_descending_market_cap",
                    "validated_set_is_a_consequence": True,
                    "band_never_widened": (
                        "the band is never widened and the floor is never lowered to "
                        "compensate for a small or empty validated set"
                    ),
                    "recompute_rule": (
                        "the batch is re-derived from the concatenated raw pages of the "
                        "recorded snapshot: the qualifying names (strictly below the floor, "
                        "not rule-excluded, not a prior-universe asset) are taken in strictly "
                        "descending market_cap_usd order and the first band_width of them are "
                        "the batch; the verifier recomputes the band from the raw bytes and "
                        "never trusts a recorded member list"
                    ),
                    "shortfall_rule": (
                        "if fewer than band_width names qualify, the shortfall is recorded with "
                        "the depth actually reached and the exclusion reasons; the band is not "
                        "widened"
                    ),
                    "expected_yield_note": (
                        "the validated yield has fallen with every band (v3 6 of 20, v4 7 of "
                        "20, v5 7 of 20); a lower v6 yield is an expected outcome, not an "
                        "anomaly, and it is never a reason to widen the band, lower the floor "
                        "or lower the history requirement"
                    ),
                },
                "ordering_rule": (
                    "Candidates are taken in strictly descending market-capitalization order "
                    "after the prior-universe and exclusion rules have been applied; the batch "
                    "contains exactly top_n assets unless the snapshot runs out of eligible "
                    "names, in which case the shortfall is recorded."
                ),
            },
            "snapshot_retrieval": {
                "rule": (
                    "The v6 universe is exactly one timestamped market-cap snapshot retrieved "
                    "inside the window below. The first successful retrieval inside the window "
                    "is the v6 snapshot."
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
                "is_a_candle_read": False,
                "is_a_candle_read_note": (
                    "a market-cap snapshot is universe metadata, not price data; retrieving it "
                    "inside the pinned window is not a confirmatory read"
                ),
                "expired_window_rule": (
                    "if the pinned window expires before a successful retrieval, the provider "
                    "failure evidence is recorded and a new window is preregistered in a "
                    "versioned amendment; the expired window is never reused or re-timed"
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
            "v6_holdout_path": "research/data/holdout_v6/holdout_index.json",
            "v6_holdout_exposed_count": 0,
            "v1_v2_v3_v4_v5_holdout_never_reused_for_selection": True,
            "confirmatory_windows_are_single_use": True,
            "holdout_counted_on_every_confirmatory_read": True,
            "holdout_counter_rule": (
                "the v6 checkpoint starts holdout_exposed_count at 0 and increments it on every "
                "read of a candle inside any confirmatory window, counting by the "
                "confirmatory_window_membership rule; the v1, v2, v3, v4 and v5 counters are "
                "never reused and never reset"
            ),
            "development_cutoff_utc": development_cutoff,
            "development_cutoff_rule": (
                "the v6 development data ends at the last fully closed hour that closes at or "
                "before the cutoff: the last development candle is the one that closes exactly "
                "at the cutoff, and no candle that closes after the cutoff may be read (the "
                "inclusive convention of BRAIN-015)"
            ),
            "development_cutoff_recompute_rule": (
                "the cutoff is the earliest confirmatory-window start among the windows that "
                "are open, recomputed from the v2, v3, v4 and v5 candidate freezes; the "
                "verifier recomputes it and never trusts this recorded value"
            ),
            "development_cutoff_cost": (
                "the cutoff is the v2 confirmatory window's start and it is the same instant "
                "the v5 chain used, so the v6 development window is identical to the v5 one: "
                "v6 differs from v5 in the universe and in nothing else, and no v6 "
                "development read can fall inside any open confirmatory window"
            ),
            "development_window": development_window(earliest_window_start, candle_count),
            "confirmatory_window_membership": {
                "rule": (
                    "a candle is inside a confirmatory window when its close falls strictly "
                    "after that window's start and before its end, regardless of which asset "
                    "the candle belongs to; a candle that closes exactly at a window's start "
                    "is development data"
                ),
                "interval_start_inclusive": False,
                "interval_end_exclusive": True,
                "asset_scope": (
                    "any asset, including assets that are not candidates of the window's own "
                    "version"
                ),
                "source_quote": (
                    "Candles that close at or before confirmatory_window_start_utc are "
                    "development data and may inform selection."
                ),
                "source_paths": [
                    "configs/research_v2_candidate_freeze.json#data_boundary.development_data_rule",
                    "configs/research_v3_candidate_freeze.json#data_boundary.development_data_rule",
                ],
                "corrected_by": (
                    "the v5 specification recorded a start-inclusive flag that contradicted "
                    "the window-owning freezes and was corrected by the published amendment "
                    "configs/research_v5_specification_amendment_1.json; the v6 specification "
                    "is written with the corrected rule, so it needs no amendment"
                ),
                "consequence": (
                    "no v6 read may fall inside the v2, the v3, the v4 or the v5 confirmatory "
                    "window, so the exposure question that is open for the v3 and the v4 "
                    "chains cannot arise for v6"
                ),
            },
            "benchmark_rule": benchmark_rule(repo_root, earliest_window_start),
            "v6_confirmatory_window": {
                "rule": (
                    "A fresh, unexposed confirmatory window evaluated only after the v6 "
                    "candidate manifest is frozen and hash-bound."
                ),
                "starts_after": "v6_candidate_freeze_timestamp_utc",
                "min_hours": 2160,
                "min_hours_rationale": (
                    "90 days of closed hourly candles; the v1 protocol used a 0.2 holdout "
                    "fraction of a multi-year window, which is of the same order."
                ),
                "overlap_with_v1_holdout": "forbidden",
                "overlap_with_v2_confirmatory_window": "forbidden",
                "overlap_with_v3_confirmatory_window": "forbidden",
                "overlap_with_v4_confirmatory_window": "forbidden",
                "overlap_with_v5_confirmatory_window": "forbidden",
                "data_used_for_candidate_selection": "excluded",
                "single_use": True,
                "access_counting": (
                    "Every read of a candle inside the v6 confirmatory window increments "
                    "holdout_exposed_count in the v6 checkpoint and is recorded in the v6 "
                    "holdout report."
                ),
                "not_a_prior_holdout": (
                    "This is a new protocol object, not a re-opening of the v1 final holdout "
                    "or of the v2, v3, v4 or v5 confirmatory windows. It is never populated "
                    "with data that predates the v6 candidate freeze."
                ),
                "window_path": "configs/research_v6_confirmatory_protocol.json",
                "runbook_path": "configs/research_v6_confirmatory_runbook_1.json",
            },
            "v1_holdout_reuse": "forbidden",
        },
        "phase_gates": {
            "rule": (
                "Each confirmatory evaluation is version-isolated: a confirmation is never "
                "re-run, never re-tuned on, and its result is never used to select anything. "
                "A window is never read for selection."
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
                "each gate instant is recomputed by the verifier from the freeze that owns "
                "the window: the window start plus min_hours"
            ),
            "v6_confirmatory_gate": {
                "rule": (
                    "the v6 evaluation may not start before the later of the four recorded "
                    "gates and the v6 window's own earliest end"
                ),
                "earliest_existing_gate_utc": format_utc(latest_window_end),
                "earliest_existing_gate_recompute_rule": (
                    "the earliest existing gate is the maximum of the four recorded gate "
                    "ends, each recomputed from the freeze that owns its window"
                ),
                "v6_window_min_hours": 2160,
                "v6_window_start_rule": (
                    "the v6 confirmatory window opens after the v6 candidate freeze, at the "
                    "first UTC hour boundary strictly after it"
                ),
                "evaluation_may_not_start_before": (
                    "the later of the four recorded gates and the v6 window's own earliest end"
                ),
            },
            "v6_selection_run_gate": (
                "only after the v6 candidate freeze and the v6 selection authorization exist, "
                "and only on data that ends at the development cutoff"
            ),
            "v6_retrieval_is_not_a_candle_read": (
                "a market-cap snapshot is universe metadata, not price data; it may be "
                "retrieved inside the v6 pinned window and is not a confirmatory read"
            ),
            "version_isolation_rule": (
                "a confirmation is never re-run, never re-tuned on, and its result is never "
                "used to select anything; the v1 to v5 artifacts are never edited in place"
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
            "v6_execution_path_rule": (
                "if the v6 chain needs an execution path it is a new directory outside the "
                "hashed set, with its own canonical digest; it is never added to "
                "src/breakout_research"
            ),
            "rotation_rule": (
                "any deliberate rotation of a digest requires a published, versioned code-hash "
                "amendment, as the v2 chain did"
            ),
        },
        "namespace": {
            "rule": (
                "every v6 artifact has its own name; no v6 artifact is written into a v1, v2, "
                "v3, v4 or v5 path, and no v1, v2, v3, v4 or v5 artifact is edited in place"
            ),
            "specification": "configs/research_v6.json",
            "universe_manifest": "research/universe_manifest_v6.json",
            "data_manifest": "research/data_manifest_v6.json",
            "datasets_directory": "research/data/candles_v6/",
            "evidence_directory": "research/v6_evidence/",
            "candidate_freeze": "configs/research_v6_candidate_freeze.json",
            "execution_protocol": "configs/research_v6_execution.json",
            "selection_authorization": "configs/research_v6_selection_authorization_1.json",
            "confirmatory_protocol": "configs/research_v6_confirmatory_protocol.json",
            "confirmatory_runbook": "configs/research_v6_confirmatory_runbook_1.json",
            "shards_directory": "research/shards_v6/",
            "ledger": "research/ledger_v6.json",
            "results_manifest": "research/results_manifest_v6.json",
            "result_stream": "research/results_v6.jsonl",
            "checkpoint": "research_state/checkpoint_v6.json",
            "result_stream_durability": (
                "the result stream is an uncommitted projection of the verified shards, "
                "because it exceeds the per-file push limit; a v6 verifier treats its absence "
                "as not materialized and reports the shard projection's digest instead of "
                "failing"
            ),
        },
        "fresh_checkout_verifiability": {
            "rule": (
                "every v6 verifier and every v6 acceptance check must pass on a checkout that "
                "holds no v6 run artifacts: an absent uncommitted projection is reported, not "
                "failed, and every identity check uses the canonical digest, never the "
                "checkout-dependent ordered digest"
            ),
            "reference_pattern": (
                "scripts/verify_v2_selection_run.py reports result_stream_sha256: null and does "
                "not fail when the projection is absent"
            ),
            "rejected_pattern": (
                "scripts/verify_v3_selection_run.py and scripts/verify_v4_selection_run.py "
                "failed on a fresh checkout before BRAIN-020 repaired their test modules"
            ),
        },
        "null_result_path": {
            "state": "AWAITING_NEW_CANDIDATES",
            "rule": (
                "a v6 pass that yields no eligible new name records AWAITING_NEW_CANDIDATES "
                "with the full evidence bundle below and schedules the next pass at the "
                "bounded cadence; the campaign is never declared complete because one "
                "snapshot was empty"
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
                    "The program must not contact the provider on every agent activation; a "
                    "pass is scheduled at the bounded cadence instead."
                ),
            },
            "cases": {
                "depth_limit": {
                    "rule": (
                        "if page 1 and the one bounded extra page together yield fewer than "
                        "band_width qualifying names, the shortfall is recorded with the depth "
                        "actually reached and the exclusion reasons; no third page is read and "
                        "the band is not widened"
                    ),
                    "outcome_state": "AWAITING_NEW_CANDIDATES",
                    "next_pass_scheduled": True,
                },
                "empty_validated_set": {
                    "rule": (
                        "if the band is drawn but none of its members passes the 26,280-candle "
                        "requirement, that is a validation outcome and not a null pass: the "
                        "band, the exclusion reasons and the observed candle counts are "
                        "recorded, the floor is not lowered, the band is not widened to "
                        "compensate and the history requirement is not lowered"
                    ),
                    "outcome_state": "AWAITING_NEW_CANDIDATES",
                    "next_pass_scheduled": True,
                },
            },
            "campaign_completion_rule": (
                "complete is a state reached only by a version whose cycle finished and whose "
                "confirmatory evaluation was performed; an empty pass is a scheduled retry, "
                "never a terminal state"
            ),
        },
        "comparability": {
            "rule": (
                "v6 differs only in the universe. The grid, costs, execution, folds, selection "
                "rule and single confirmatory criterion are identical to v1."
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
            "log_state_at_preregistration": {
                # A historical statement, pinned: the log is append-only and has
                # since grown, but this block records the log at the moment the
                # specification was preregistered. The live state of the log is
                # the log itself.
                "entry_count": len(pinned_log_entries),
                "versions_present": [
                    entry.get("universe_version") for entry in pinned_log_entries
                ],
                "missing_entries": [],
                "note": (
                    "a historical statement of the log at the time of preregistration: the log "
                    "holds exactly one entry per frozen universe version (v3, v4 and v5), so the "
                    "v6 entry is a pure append"
                ),
            },
            "pending_log_entries": [
                "the v6 entry, chained onto the v5 entry",
            ],
            "log_entry_previous_hash": last_log_entry.get("entry_hash"),
            "log_entry_is_pure_append": True,
            "log_entry_rule": (
                "each universe version appends exactly one entry carrying its own hash and the "
                "hash of the previous entry; an entry is never hand-written, it is derived "
                "from the artifacts of its own version"
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
            "p1": {"name": "preregister_v6_spec", "status": "DONE"},
            "p2": {"name": "retrieve_and_freeze_v6_universe", "status": "OUTSTANDING"},
            "p3": {
                "name": "validate_v6_candidates_and_freeze_data_manifest",
                "status": "OUTSTANDING",
            },
            "p4": {
                "name": "preregister_v6_execution_protocol_and_candidate_freeze",
                "status": "OUTSTANDING",
            },
            "p5": {
                "name": "append_the_v6_entry_to_the_expansion_log",
                "status": "OUTSTANDING",
            },
            "p6": {
                "name": "preregister_the_v6_confirmatory_protocol_and_runbook",
                "status": "OUTSTANDING",
            },
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

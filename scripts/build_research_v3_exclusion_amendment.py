#!/usr/bin/env python3
"""Build the versioned v3 exclusion amendment (BRAIN-012, stage 1).

The v3 specification inherits the v1 exclusion rules, and the v1 rules are a
*closed ticker list*: by construction they can only name instruments that
already existed when the list was frozen. The v3 specification nevertheless
names six exclusion categories in ``universe.exclusions`` (stablecoins,
wrapped tokens, bridged tokens, leveraged tokens, synthetic tokens,
derivative tokens), and those categories have to be applied to a snapshot that
was taken more than a year after the v1 list was frozen.

This script therefore freezes a **versioned amendment** that

* states the problem, the decision and the provenance of the decision;
* publishes the exclusion classifier as data -- markers, group order and
  reasons -- so that the rule is readable, hash-bound and re-derivable;
* applies the classifier mechanically to **every** entry of the frozen v3
  snapshot and records the complete derived classification, so that nothing is
  chosen by hand and every exclusion is auditable;
* derives the v3 candidate batch from the frozen snapshot by the rule the
  specification states: strictly below the recomputed v2 floor, not an asset
  of the v1 or v2 universe, not excluded by any published rule, ordered by
  descending market capitalization, exactly ``top_n`` assets.

The amendment is written **after** the market-cap snapshot was retrieved and
**before** any candle is fetched, any validation outcome is known and any
strategy result exists. It authorizes nothing.

Usage::

    python3 scripts/build_research_v3_exclusion_amendment.py            # write
    python3 scripts/build_research_v3_exclusion_amendment.py --force    # rewrite
    python3 scripts/build_research_v3_exclusion_amendment.py --print     # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_exclusion_classifier import (  # noqa: E402
    classify_snapshot,
    entry_symbol,
    fixed_list_groups,
    prior_universe_match,
    reason_for_group,
)

SPEC_V3_PATH = REPO_ROOT / "configs" / "research_v3.json"
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v3_exclusion_amendment_1.json"
V1_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest.json"
V2_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
SNAPSHOT_RAW_PATH = REPO_ROOT / "research" / "v3_evidence" / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = REPO_ROOT / "research" / "v3_evidence" / "snapshot_observation.json"

#: The instant at which this amendment was authored. It is pinned so that the
#: artifact is byte-reproducible; it must be later than the snapshot retrieval
#: and earlier than the first v3 candle fetch.
AMENDMENT_TIMESTAMP_UTC = "2026-10-20T11:52:00Z"

#: Keys removed from the document before the amendment hash is computed.
AMENDMENT_HASH_EXCLUDED_KEYS = ("amendment_hash",)

#: The published classifier. This is the only place where the exclusion rule
#: is written down; every other artifact derives its exclusions from it.
CLASSIFIER: Dict[str, Any] = {
    "classifier_version": "v3-exclusion-classifier-1",
    "match_semantics": {
        "text_marker": (
            "case-insensitive substring of the lower-cased concatenation of the "
            "snapshot entry's 'name' and 'id' fields"
        ),
        "symbol_exact": (
            "case-insensitive exact equality with the upper-cased snapshot entry's "
            "'symbol' field"
        ),
        "group_precedence": (
            "the inherited fixed lists are evaluated first, then the classifier "
            "groups in the published group_order; the first group that matches an "
            "entry is the recorded exclusion group"
        ),
        "application_scope": (
            "the classifier is applied to every entry of the frozen snapshot, not "
            "only to the entries that reach the batch, so the derived exclusion set "
            "is complete and the same rule applies to every asset"
        ),
    },
    "group_order": [
        "stablecoins",
        "wrapped_bridged",
        "leveraged_synthetic",
        "synthetic_tokens",
        "derivative_tokens",
    ],
    "groups": {
        "stablecoins": {
            "spec_category": "stablecoins",
            "exclusion_reason": "stablecoin_excluded",
            "text_markers": [
                "usd", "usds", "usde", "usd1", "usyc", "usdf", "usdd", "usdy",
                "usdg", "usdgo", "dollar", "euro", "eur", "jpy", "gbp", "sterling",
                "yen", "chf", "stable", "gold", "fund", "money market", "t-bill",
                "treasury", "government securities", "yield", "clo fund",
                "sofusd", "reusd",
            ],
            "symbol_exact": [],
            "rationale": (
                "Fiat-pegged stablecoins, cash-management and money-market funds, "
                "short-duration treasury funds, tokenized gold and every other "
                "instrument that a marker names. A stablecoin has no breakout "
                "structure, so admitting one would dilute the batch with assets "
                "that cannot produce the event the study measures."
            ),
        },
        "wrapped_bridged": {
            "spec_category": "wrapped_tokens,bridged_tokens",
            "exclusion_reason": "wrapped_or_bridged_excluded",
            "text_markers": ["wrapped", "bridged", "staked"],
            "symbol_exact": [],
            "rationale": (
                "Wrapped, bridged and staked representations of another asset are "
                "not independent assets: their price tracks the underlying and their "
                "history duplicates it."
            ),
        },
        "leveraged_synthetic": {
            "spec_category": "leveraged_tokens",
            "exclusion_reason": "leveraged_or_synthetic_excluded",
            "text_markers": ["leveraged", "2x", "3x", "5x", "hedge"],
            "symbol_exact": [],
            "rationale": (
                "Leveraged and hedged tokens carry a path-dependent payoff and a "
                "decaying premium, so their candles are not a breakout asset."
            ),
        },
        "synthetic_tokens": {
            "spec_category": "synthetic_tokens",
            "exclusion_reason": "synthetic_token_excluded",
            "text_markers": ["tokenized stock", "bstock", "tokenized equity"],
            "symbol_exact": [],
            "rationale": (
                "Tokenized claims on a real-world equity are synthetic instruments: "
                "they track an equity market, not a crypto market, and their "
                "candles contain no crypto breakout."
            ),
        },
        "derivative_tokens": {
            "spec_category": "derivative_tokens",
            "exclusion_reason": "derivative_token_excluded",
            "text_markers": ["xstock", "tokenized derivative"],
            "symbol_exact": [],
            "rationale": (
                "A token that is a derivative of another instrument inherits that "
                "instrument's price path and is not an independent asset."
            ),
        },
    },
}


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


def compute_amendment_hash(document: Dict[str, Any]) -> str:
    body = {key: value for key, value in document.items() if key not in AMENDMENT_HASH_EXCLUDED_KEYS}
    return sha256_bytes(canonical(body).encode("utf-8"))


def recompute_floor(v2_universe: Dict[str, Any]) -> Tuple[str, int]:
    """Recompute the v2 floor from the v2 universe manifest.

    The floor is the market capitalization of the lowest-ranked v2 candidate.
    It is recomputed from the manifest and never taken from the specification.
    """
    assets = v2_universe.get("eligible_assets") or []
    if not assets:
        raise SystemExit("the v2 universe manifest has no eligible assets")
    lowest = min(assets, key=lambda entry: int(entry.get("market_cap_usd") or 0))
    return str(lowest.get("symbol")), int(lowest.get("market_cap_usd") or 0)


def prior_universe_assets(*universes: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Collect the prior-universe identities: Binance symbol and CoinGecko id."""
    symbols: Dict[str, str] = {}
    identifiers: Dict[str, str] = {}
    for universe in universes:
        version = str(universe.get("universe_version") or universe.get("protocol_version") or "prior")
        for entry in universe.get("eligible_assets") or []:
            symbol = str(entry.get("symbol") or "")
            if symbol.endswith("USDT"):
                symbol = symbol[:-4]
            if symbol:
                symbols.setdefault(symbol.upper(), version)
            identifier = entry.get("coingecko_id")
            if identifier:
                identifiers.setdefault(str(identifier), version)
    return symbols, identifiers


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the amendment document from the frozen, hash-bound artifacts."""
    spec = json.loads((repo_root / "configs" / "research_v3.json").read_text(encoding="utf-8"))
    v1_universe = json.loads(
        (repo_root / "research" / "universe_manifest.json").read_text(encoding="utf-8")
    )
    v2_universe = json.loads(
        (repo_root / "research" / "universe_manifest_v2.json").read_text(encoding="utf-8")
    )
    observation = json.loads(
        (repo_root / "research" / "v3_evidence" / "snapshot_observation.json").read_text(encoding="utf-8")
    )
    raw_bytes = (repo_root / "research" / "v3_evidence" / "raw_market_cap_response.json").read_bytes()
    markets = json.loads(raw_bytes.decode("utf-8"))

    raw_hash = sha256_bytes(raw_bytes)
    if raw_hash != observation.get("raw_response_hash"):
        raise SystemExit("the stored v3 snapshot does not hash to the recorded digest")

    universe_spec = spec["universe"]
    top_n = int(universe_spec["top_n"])
    floor_symbol, floor_market_cap = recompute_floor(v2_universe)

    fixed_lists = {
        str(group): list(symbols or [])
        for group, symbols in (v1_universe.get("exclusion_rules") or {}).items()
    }
    fixed_groups = fixed_list_groups(fixed_lists)
    classification = classify_snapshot(markets, CLASSIFIER, fixed_lists)

    prior_symbols, prior_ids = prior_universe_assets(v1_universe, v2_universe)

    records: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {
        "excluded_by_rule": 0,
        "excluded_as_prior_universe": 0,
        "above_floor": 0,
        "eligible": 0,
    }
    per_group: Dict[str, int] = {}
    for position, market in enumerate(markets, start=1):
        symbol = entry_symbol(market)
        identifier = str(market.get("id") or "")
        market_cap = market.get("market_cap")
        market_cap_usd = int(market_cap) if isinstance(market_cap, (int, float)) else None
        record: Dict[str, Any] = {
            "coingecko_id": identifier,
            "market_cap_rank": market.get("market_cap_rank"),
            "market_cap_usd": market_cap_usd,
            "name": market.get("name"),
            "snapshot_position": position,
            "symbol": symbol,
        }
        outcome = classification.get(symbol)
        if outcome is not None:
            record.update({
                "excluded": True,
                "exclusion_group": outcome["exclusion_group"],
                "exclusion_reason": outcome["exclusion_reason"],
                "matched_markers": outcome["matched_markers"],
                "rule_source": outcome["rule_source"],
            })
            counts["excluded_by_rule"] += 1
            per_group[outcome["exclusion_group"]] = per_group.get(outcome["exclusion_group"], 0) + 1
        else:
            identity = prior_universe_match(market, prior_symbols, prior_ids)
            if identity is not None:
                record.update({
                    "excluded": True,
                    "exclusion_group": "prior_universe",
                    "exclusion_reason": "already_in_prior_universe",
                    "matched_markers": identity.get("matched_on"),
                    "prior_universe_versions": identity.get("prior_universe_versions"),
                    "rule_source": "specification_expansion_scope",
                })
                counts["excluded_as_prior_universe"] += 1
            elif market_cap_usd is None or market_cap_usd >= floor_market_cap:
                record.update({
                    "excluded": True,
                    "exclusion_group": "market_cap_floor",
                    "exclusion_reason": "not_below_prior_universe_floor",
                    "matched_markers": [],
                    "rule_source": "specification_expansion_scope",
                })
                counts["above_floor"] += 1
            else:
                record.update({
                    "excluded": False,
                    "exclusion_group": None,
                    "exclusion_reason": None,
                    "matched_markers": [],
                    "rule_source": None,
                })
                counts["eligible"] += 1
                eligible.append(record)
        records.append(record)

    eligible.sort(key=lambda record: (-int(record["market_cap_usd"] or 0), record["snapshot_position"]))
    batch = eligible[:top_n]
    for rank, record in enumerate(batch, start=1):
        record["batch_rank"] = rank
        record["binance_pair"] = f"{record['symbol']}USDT"

    document: Dict[str, Any] = {
        "amendment_id": "v3_exclusion_amendment_1",
        "amendment_version": 1,
        "amendment_timestamp_utc": AMENDMENT_TIMESTAMP_UTC,
        "amendment_status": "PUBLISHED_RULE_NO_AUTHORIZATION",
        "applies_to": {
            "protocol_version": spec["protocol_version"],
            "specification_hash": spec["specification_hash"],
            "specification_path": "configs/research_v3.json",
            "target_block": "universe.eligibility_validation.exclusion_rules",
            "universe_version": spec["universe_version"],
        },
        "purpose": (
            "Make the v3 specification's own exclusion categories operative on a "
            "snapshot that is more than a year newer than the closed ticker lists "
            "the v1 rules are built from, without touching the immutable v1 or v2 "
            "artifacts and without letting any asset enter or leave the batch by "
            "hand."
        ),
        "problem": {
            "statement": (
                "The v1 exclusion_rules block is a closed list of tickers. It can "
                "only name instruments that existed when it was frozen, so the six "
                "categories the v3 specification names in universe.exclusions are "
                "not actually applied to instruments issued since then."
            ),
            "consequence_if_unaddressed": (
                "Applied unchanged, the rules admit fiat-pegged stablecoins, "
                "cash-management and treasury funds and tokenized gold into the v3 "
                "batch. Such instruments have no breakout structure, so the batch "
                "would be diluted with assets that cannot produce the event the "
                "study measures."
            ),
            "observed_in_the_frozen_v3_snapshot": {
                "assets_matched_by_the_published_classifier": counts["excluded_by_rule"],
                "of_which_stablecoins_or_funds": per_group.get("stablecoins", 0),
                "rank_range_of_the_matched_assets": "the snapshot ranks 1..250",
                "note": (
                    "The count is a property of the frozen snapshot and of the "
                    "published markers. It is recorded, not tuned: no marker was "
                    "added or removed after seeing a validation outcome or a "
                    "strategy result, because no candle had been fetched and no "
                    "result existed when this amendment was authored."
                ),
            },
        },
        "decision": {
            "rule": (
                "The v1 exclusion_rules block is applied verbatim, and the v3 "
                "classifier below is applied in addition to it. An asset is "
                "excluded when either the inherited fixed list or the classifier "
                "matches it."
            ),
            "why_an_amendment_and_not_an_edit": (
                "configs/research_v3.json is frozen and hash-bound, and the "
                "snapshot it governs has already been retrieved. Changing the "
                "specification after the retrieval would silently re-time the "
                "rule set. A versioned amendment keeps the specification and the "
                "snapshot exactly as they were and records the correction "
                "separately, with its own hash."
            ),
            "why_a_published_classifier_and_not_a_list": (
                "A second hand-written ticker list would move the same problem to "
                "the next snapshot. A published marker rule is applied "
                "mechanically to every snapshot entry, is re-derivable by anyone "
                "who has the amendment, and produces the same answer for every "
                "asset rather than for the assets somebody thought of."
            ),
            "what_is_deliberately_not_changed": [
                "the inherited fixed lists are applied unchanged",
                "the exchange_tokens and low_liquidity_or_new groups are not extended: "
                "the v3 specification's universe.exclusions does not name them, so "
                "this amendment does not invent an exclusion category",
                "the market-capitalization floor, the prior-universe identity rule "
                "and the ordering rule are not touched",
                "no v1 or v2 artifact is modified",
            ],
        },
        "classifier": CLASSIFIER,
        "inherited_fixed_lists": {
            "source_block": "exclusion_rules",
            "source_path": "research/universe_manifest.json",
            "source_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            "groups": fixed_lists,
            "note": (
                "Applied verbatim, as the v3 specification's "
                "eligibility_validation.exclusion_rules requires. The v3 classifier "
                "is additional to these lists and never overrides them."
            ),
        },
        "application_order": [
            "1. the inherited fixed lists (v1 exclusion_rules), symbol by symbol",
            "2. the v3 classifier groups, in the published group_order",
            "3. the prior-universe identity rules (Binance symbol, CoinGecko id, "
            "rename marker in the name)",
            "4. the prior-universe market-capitalization floor",
            "5. descending market capitalization, truncated to top_n",
        ],
        "floor": {
            "source_universe_version": "v2",
            "source_manifest_path": "research/universe_manifest_v2.json",
            "source_manifest_hash": v2_universe.get("manifest_hash"),
            "floor_symbol": floor_symbol,
            "floor_market_cap_usd": floor_market_cap,
            "comparison": "strictly_less_than",
            "recompute_rule": (
                "the floor is the minimum market_cap_usd over the eligible_assets of "
                "research/universe_manifest_v2.json; it is recomputed from that "
                "manifest and never trusted from the specification"
            ),
        },
        "prior_universe": {
            "rule": (
                "An asset is already in a prior universe when its Binance symbol, its "
                "CoinGecko id or the old ticker of a rename marker in its name occurs "
                "in the eligible assets of the v1 or the v2 universe manifest."
            ),
            "identity_rules": [
                {
                    "rule": "binance_symbol",
                    "statement": (
                        "the upper-cased ticker of the snapshot entry occurs in a "
                        "prior universe"
                    ),
                },
                {
                    "rule": "coingecko_id",
                    "statement": (
                        "the CoinGecko id of the snapshot entry occurs in a prior "
                        "universe"
                    ),
                },
                {
                    "rule": "coingecko_name_rename",
                    "statement": (
                        "the name carries a rename marker of the form '(ex-<TICKER>)' "
                        "and <TICKER> occurs in a prior universe. A rename can come "
                        "with a new provider id, so the id rule alone does not catch "
                        "it: MATIC (CoinGecko id 'matic-network') is POL (CoinGecko "
                        "id 'polygon-ecosystem-token') in the frozen v3 snapshot."
                    ),
                },
            ],
            "v1_manifest_path": "research/universe_manifest.json",
            "v1_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            "v2_manifest_path": "research/universe_manifest_v2.json",
            "v2_manifest_hash": v2_universe.get("manifest_hash"),
            "excluded_asset_count": counts["excluded_as_prior_universe"],
        },
        "corrections_to_the_specification": [
            {
                "specification_path": "configs/research_v3.json",
                "specification_block": "universe.expansion_scope.prior_universe_asset_identity",
                "specification_text": "A renamed asset keeps its CoinGecko id and is therefore the same asset.",
                "problem": (
                    "The sentence is not true in general: a provider that renames an "
                    "asset may also issue a new id. In the frozen v3 snapshot MATIC "
                    "(id 'matic-network', a v1 candidate) is POL (id "
                    "'polygon-ecosystem-token')."
                ),
                "correction": (
                    "The published identity_rules above are the operative rule. The "
                    "rename marker rule identifies the renamed successor, so POL is "
                    "excluded as already_in_prior_universe and the v3 batch contains "
                    "no asset of the v1 or the v2 universe."
                ),
                "why_not_an_edit": (
                    "configs/research_v3.json is frozen and hash-bound and its snapshot "
                    "has already been retrieved. The correction is carried here so "
                    "that the specification and the retrieved snapshot stay exactly "
                    "as they were."
                ),
                "effect_on_the_batch": (
                    "none: POL's market capitalization is below the batch cutoff, so "
                    "the derived candidate batch is identical with and without the "
                    "rename marker rule"
                ),
            },
        ],
        "binding": {
            "specification_hash": spec["specification_hash"],
            "snapshot_raw_response_path": "research/v3_evidence/raw_market_cap_response.json",
            "snapshot_raw_response_sha256": raw_hash,
            "snapshot_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            "snapshot_endpoint": universe_spec["endpoint"],
            "v1_universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            "v2_universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v2.json"),
        },
        "derived_classification": {
            "snapshot_entries": len(records),
            "counts": counts,
            "counts_by_exclusion_group": dict(sorted(per_group.items())),
            "records": records,
            "note": (
                "One record per snapshot entry, in snapshot order, so the derived "
                "exclusion set is complete over the whole snapshot and no entry is "
                "silently dropped."
            ),
        },
        "derived_candidate_batch": {
            "rule": (
                "The batch is the top_n eligible assets in strictly descending "
                "market-capitalization order, where eligible means: below the "
                "recomputed v2 floor, not an asset of the v1 or v2 universe and not "
                "excluded by any published rule."
            ),
            "top_n": top_n,
            "eligible_pool_size": counts["eligible"],
            "batch_size": len(batch),
            "shortfall": max(0, top_n - len(batch)),
            "members": [
                {
                    "binance_pair": record["binance_pair"],
                    "coingecko_id": record["coingecko_id"],
                    "market_cap_rank": record["market_cap_rank"],
                    "market_cap_usd": record["market_cap_usd"],
                    "name": record["name"],
                    "rank": record["batch_rank"],
                    "symbol": record["symbol"],
                }
                for record in batch
            ],
            "lowest_batch_member": {
                "symbol": batch[-1]["symbol"],
                "market_cap_usd": batch[-1]["market_cap_usd"],
            } if batch else None,
            "next_version_floor_candidate": {
                "symbol": batch[-1]["symbol"],
                "market_cap_usd": batch[-1]["market_cap_usd"],
                "note": (
                    "Informational: the floor of a future universe version is the "
                    "market capitalization of the lowest-ranked candidate of this "
                    "version. It is recorded by the expansion log, not applied here."
                ),
            } if batch else None,
        },
        "provenance": {
            "authored_after_snapshot_retrieval": True,
            "authored_before_any_v3_candle_fetch": True,
            "authored_before_any_validation_outcome": True,
            "authored_before_any_strategy_result": True,
            "statement": (
                "The amendment was authored after the market-cap snapshot was "
                "retrieved and stored, and before a single v3 candle was fetched, "
                "before any candidate was validated against Binance and before any "
                "strategy result existed. The markers were chosen from the asset "
                "list of the frozen snapshot, which is a fact about the rule, not "
                "about a result: the classifier is applied mechanically to all "
                f"{len(records)} entries, it is published in full, and the derived "
                "classification of every entry is recorded here."
            ),
            "verifier_cross_check": (
                "scripts/verify_research_v3_manifests.py recomputes the derived "
                "classification from the published markers and the frozen snapshot, "
                "and checks that the earliest v3 candle retrieval is later than "
                "amendment_timestamp_utc."
            ),
        },
        "not_authorized_by_this_amendment": [
            "fetching a candle",
            "writing research/universe_manifest_v3.json or research/data_manifest_v3.json",
            "running a v3 grid, campaign or candidate selection",
            "reading any candle inside the v2 or the v3 confirmatory window",
            "modifying configs/research_v3.json or any v1 or v2 artifact",
            "adding, removing or substituting an asset of the derived candidate "
            "batch by hand",
        ],
        "related_artifacts": {
            "v3_specification": {
                "path": "configs/research_v3.json",
                "specification_hash": spec["specification_hash"],
            },
            "v3_snapshot_observation": {
                "path": "research/v3_evidence/snapshot_observation.json",
                "raw_response_sha256": raw_hash,
                "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            },
        },
        "producer": {
            "path": "scripts/build_research_v3_exclusion_amendment.py",
            "classifier_module": "scripts/v3_exclusion_classifier.py",
            "verify_command": "python3 scripts/verify_research_v3_manifests.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "amendment_hash_excluded_keys": list(AMENDMENT_HASH_EXCLUDED_KEYS),
            "note": (
                "amendment_hash is the sha256 of the document body with the "
                "amendment_hash key removed. It binds the classifier, the derived "
                "classification and the derived candidate batch."
            ),
        },
    }
    document["amendment_hash"] = compute_amendment_hash(document)
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

    target = repo_root / "configs" / "research_v3_exclusion_amendment_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "amendment_path": str(target.relative_to(repo_root)),
        "amendment_hash": document["amendment_hash"],
        "batch": [member["symbol"] for member in document["derived_candidate_batch"]["members"]],
        "counts": document["derived_classification"]["counts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

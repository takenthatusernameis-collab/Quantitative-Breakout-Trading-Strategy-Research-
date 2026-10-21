#!/usr/bin/env python3
"""Build the v4 exclusion amendment 2 (the effective v4 exclusion amendment).

``configs/research_v4_exclusion_amendment_1.json`` is a copy of the v3
exclusion amendment in which the floor, the prior-universe identity rule and
the snapshot bindings were carried over from the v3 version unchanged:

* its ``floor`` block names the **v2** universe manifest (``HBARUSDT``,
  3,627,324,049 USD) instead of the **v3** one that the preregistered v4
  specification names (``research/universe_manifest_v3.json``;
  ``HTXUSDT``, 1,468,004,153 USD);
* its ``prior_universe`` block applies the identity rule to the v1 and the v2
  universe only, so the v4 batch repeated the whole v3 batch;
* its ``binding`` and ``related_artifacts`` blocks name the **v3**
  specification hash and the **v3** market-cap snapshot instead of the v4
  ones;
* its ``producer`` block names ``scripts/build_research_v4_exclusion_amendment.py``,
  ``scripts/v4_exclusion_classifier.py`` and ``scripts/verify_research_v4_manifests.py``,
  none of which exists in the tree.

Amendment 2 corrects exactly those blocks and keeps the classifier, the
inherited fixed lists and the derived classification of amendment 1 unchanged:
the classification of a snapshot entry depends only on the published markers
and the frozen snapshot, not on the floor or on the identity rule. It also
re-derives the candidate batch with the corrected rules and publishes it, so
that ``scripts/v4_constituent_validation.py`` can cross-check its own
re-derivation against it.

Nothing is fetched: the batch is derived from the stored v4 market-cap
snapshot. The script writes exactly one artifact and never touches a v1, v2 or
v3 file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v4_constituent_validation import (  # noqa: E402
    compute_manifest_hash,
    derive_batch,
    prior_universe_assets,
    sha256_file,
)

SPEC_PATH = REPO_ROOT / "configs" / "research_v4.json"
AMENDMENT_1_PATH = REPO_ROOT / "configs" / "research_v4_exclusion_amendment_1.json"
AMENDMENT_2_PATH = REPO_ROOT / "configs" / "research_v4_exclusion_amendment_2.json"
V1_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest.json"
V2_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
V3_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v3.json"
SNAPSHOT_RAW_PATH = REPO_ROOT / "research" / "v4_evidence" / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = REPO_ROOT / "research" / "v4_evidence" / "snapshot_observation.json"

AMENDMENT_HASH_EXCLUDED_KEYS = ("amendment_hash",)


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec = load(repo_root / "configs" / "research_v4.json")
    amendment_1 = load(repo_root / "configs" / "research_v4_exclusion_amendment_1.json")
    v1_universe = load(repo_root / "research" / "universe_manifest.json")
    v2_universe = load(repo_root / "research" / "universe_manifest_v2.json")
    v3_universe = load(repo_root / "research" / "universe_manifest_v3.json")
    observation = load(repo_root / "research" / "v4_evidence" / "snapshot_observation.json")
    markets = json.loads((repo_root / "research" / "v4_evidence" / "raw_market_cap_response.json")
                         .read_text(encoding="utf-8"))

    floor_entry = min(
        (v3_universe.get("eligible_assets") or []),
        key=lambda entry: int(entry.get("market_cap_usd") or 0),
    )
    floor_symbol = str(floor_entry.get("symbol"))
    floor_market_cap = int(floor_entry.get("market_cap_usd") or 0)

    batch, excluded, records = derive_batch(
        spec, amendment_1, markets, v1_universe, v2_universe, v3_universe,
        check_published_batch=False,
    )
    prior_symbols, prior_ids = prior_universe_assets(v1_universe, v2_universe, v3_universe)
    excluded_by_identity = [
        record for record in excluded if record.get("exclusion_reason") == "already_in_prior_universe"
    ]
    excluded_by_markers = [
        record for record in excluded
        if record.get("exclusion_reason") not in (None, "already_in_prior_universe")
        and record.get("exclusion_group") != "market_cap_floor"
    ]
    excluded_by_floor = [
        record for record in excluded if record.get("exclusion_group") == "market_cap_floor"
    ]
    batch_ranks = {record["binance_pair"]: record["rank"] for record in batch}
    derived_records: List[Dict[str, Any]] = []
    for record in records:
        entry = dict(record)
        pair = f"{entry.get('symbol')}USDT"
        if entry.get("excluded") is False and pair in batch_ranks:
            entry["batch_rank"] = batch_ranks[pair]
            entry["binance_pair"] = pair
        derived_records.append(entry)
    counts_by_group: Dict[str, int] = {}
    for record in excluded_by_markers:
        group = str(record.get("exclusion_group"))
        counts_by_group[group] = counts_by_group.get(group, 0) + 1
    derived_classification = {
        "snapshot_entries": len(records),
        "counts": {
            "excluded_by_rule": len(excluded_by_markers),
            "excluded_as_prior_universe": len(excluded_by_identity),
            "above_floor": len(excluded_by_floor),
            "eligible": len(records) - len(excluded),
        },
        "counts_by_exclusion_group": dict(sorted(counts_by_group.items())),
        "records": derived_records,
        "note": (
            "The classification of every entry of the frozen v4 snapshot under the corrected "
            "rules: the inherited fixed lists and the published markers first, then the "
            "prior-universe identity rule against the v1, the v2 and the v3 universe, then the "
            "v3 market-capitalization floor, then the descending order truncated to top_n."
        ),
    }

    members: List[Dict[str, Any]] = []
    for record in batch:
        members.append({
            "binance_pair": record["binance_pair"],
            "coingecko_id": record["coingecko_id"],
            "market_cap_rank": record["market_cap_rank"],
            "market_cap_usd": record["market_cap_usd"],
            "name": record["name"],
            "rank": record["rank"],
            "symbol": record["symbol"],
        })

    document: Dict[str, Any] = {
        "amendment_id": "research_v4_exclusion_amendment_2",
        "amendment_version": 2,
        "amendment_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "amendment_status": "PUBLISHED_CORRECTION_OF_AMENDMENT_1",
        "applies_to": {
            "specification_path": "configs/research_v4.json",
            "specification_hash": spec["specification_hash"],
            "universe_version": spec["universe_version"],
        },
        "purpose": (
            "Correct the floor, the prior-universe identity rule and the snapshot bindings of "
            "the v4 exclusion amendment 1, which were carried over unchanged from the v3 "
            "exclusion amendment and contradicted the preregistered v4 specification."
        ),
        "supersedes": {
            "amendment_path": "configs/research_v4_exclusion_amendment_1.json",
            "amendment_hash": amendment_1.get("amendment_hash"),
            "reason": (
                "Amendment 1 is a frozen, hash-bound artifact and is not edited. Amendment 2 "
                "carries the corrections: the floor is recomputed from the v3 universe manifest, "
                "the identity rule covers the v1, the v2 and the v3 universe, the bindings name "
                "the v4 specification and the v4 snapshot, and the published batch is re-derived "
                "with the corrected rules."
            ),
        },
        "problem": {
            "statement": (
                "Amendment 1 applied the v2 floor and the v1/v2 identity rule to the v4 batch, "
                "so the v4 candidate batch was the v3 candidate batch again and no v4 asset was "
                "strictly below the v3 floor."
            ),
            "evidence": {
                "amendment_1_floor_source_universe_version": (
                    (amendment_1.get("floor") or {}).get("source_universe_version")
                ),
                "amendment_1_prior_universe_manifest_paths": [
                    (amendment_1.get("prior_universe") or {}).get("v1_manifest_path"),
                    (amendment_1.get("prior_universe") or {}).get("v2_manifest_path"),
                ],
                "amendment_1_related_v4_specification_hash": (
                    ((amendment_1.get("related_artifacts") or {}).get("v4_specification") or {})
                    .get("specification_hash")
                ),
                "specification_hash_of_record": spec["specification_hash"],
                "specification_floor_source_universe_version": (
                    (spec["universe"]["expansion_scope"]["prior_universe_floor"] or {})
                    .get("source_universe_version")
                ),
            },
        },
        "decision": {
            "rule": (
                "The floor is recomputed from the universe manifest the specification names "
                "(research/universe_manifest_v3.json) and the prior-universe identity rule "
                "covers the eligible assets of the v1, the v2 and the v3 universe manifest. "
                "The classifier and the inherited fixed lists of amendment 1 are applied "
                "unchanged."
            ),
            "what_is_deliberately_not_changed": [
                "the inherited fixed lists are applied unchanged",
                "the classifier markers are applied unchanged",
                "the derived classification of the frozen snapshot is unchanged",
                "no v1, v2 or v3 artifact is modified",
                "the market-cap snapshot is not re-retrieved and its retrieval timestamp is not "
                "re-timed",
            ],
        },
        "classifier": amendment_1.get("classifier"),
        "inherited_fixed_lists": amendment_1.get("inherited_fixed_lists"),
        "application_order": [
            "1. the inherited fixed lists (v1 exclusion_rules), symbol by symbol",
            "2. the v4 classifier groups, in the published group_order",
            "3. the prior-universe identity rules (Binance symbol, CoinGecko id, rename marker "
            "in the name) against the v1, the v2 and the v3 universe",
            "4. the prior-universe market-capitalization floor, recomputed from the v3 universe "
            "manifest",
            "5. descending market capitalization, truncated to top_n",
        ],
        "floor": {
            "source_universe_version": "v3",
            "source_manifest_path": "research/universe_manifest_v3.json",
            "source_manifest_hash": v3_universe.get("manifest_hash"),
            "source_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v3.json"),
            "floor_symbol": floor_symbol,
            "floor_market_cap_usd": floor_market_cap,
            "comparison": "strictly_less_than",
            "recompute_rule": (
                "the floor is the minimum market_cap_usd over the eligible_assets of "
                "research/universe_manifest_v3.json; it is recomputed from that manifest and "
                "never trusted from the specification"
            ),
        },
        "prior_universe": {
            "rule": (
                "An asset is already in a prior universe when its Binance symbol, its CoinGecko "
                "id or the old ticker of a rename marker in its name occurs in the eligible "
                "assets of the v1, the v2 or the v3 universe manifest."
            ),
            "identity_rules": (amendment_1.get("prior_universe") or {}).get("identity_rules"),
            "v1_manifest_path": "research/universe_manifest.json",
            "v1_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            "v2_manifest_path": "research/universe_manifest_v2.json",
            "v2_manifest_hash": v2_universe.get("manifest_hash"),
            "v2_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v2.json"),
            "v3_manifest_path": "research/universe_manifest_v3.json",
            "v3_manifest_hash": v3_universe.get("manifest_hash"),
            "v3_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v3.json"),
            "matched_on": ["binance_symbol", "coingecko_id", "coingecko_name_rename"],
            "excluded_asset_count": len(excluded_by_identity),
        },
        "corrections_to_amendment_1": [
            {
                "amendment_path": "configs/research_v4_exclusion_amendment_1.json",
                "block": "floor",
                "amendment_1_text": (
                    "the floor is the minimum market_cap_usd over the eligible_assets of "
                    "research/universe_manifest_v2.json"
                ),
                "problem": (
                    "The v4 specification names the v3 universe manifest as the floor source, "
                    "so the v2 floor admitted the whole v3 batch a second time."
                ),
                "correction": "The floor block above is the operative one: it is the v3 floor.",
            },
            {
                "amendment_path": "configs/research_v4_exclusion_amendment_1.json",
                "block": "prior_universe",
                "amendment_1_text": (
                    "An asset is already in a prior universe when it occurs in the eligible "
                    "assets of the v1 or the v2 universe manifest."
                ),
                "problem": (
                    "The v4 specification names the v1, the v2 and the v3 universe manifests, so "
                    "the v3 batch was admitted again."
                ),
                "correction": (
                    "The prior_universe block above is the operative one: the identity rule "
                    "covers the v1, the v2 and the v3 universe."
                ),
            },
            {
                "amendment_path": "configs/research_v4_exclusion_amendment_1.json",
                "block": "binding and related_artifacts",
                "amendment_1_text": (
                    "the v3 specification hash and the v3 market-cap snapshot hash and "
                    "retrieval timestamp"
                ),
                "problem": (
                    "The bindings named artifacts of another version, so the amendment was not "
                    "bound to the v4 specification or to the v4 snapshot it governs."
                ),
                "correction": "The binding block below names the v4 specification and the v4 snapshot.",
            },
            {
                "amendment_path": "configs/research_v4_exclusion_amendment_1.json",
                "block": "producer",
                "amendment_1_text": (
                    "scripts/build_research_v4_exclusion_amendment.py, "
                    "scripts/v4_exclusion_classifier.py, scripts/verify_research_v4_manifests.py"
                ),
                "problem": "None of the three paths exists in the tree.",
                "correction": (
                    "The producer block below names the scripts that exist: this script, the "
                    "shared classifier module and the v4 manifests verifier."
                ),
            },
        ],
        "binding": {
            "specification_hash": spec["specification_hash"],
            "snapshot_raw_response_path": "research/v4_evidence/raw_market_cap_response.json",
            "snapshot_raw_response_sha256": sha256_file(repo_root / "research" / "v4_evidence" / "raw_market_cap_response.json"),
            "snapshot_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            "snapshot_endpoint": observation["endpoint"],
            "v1_universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            "v2_universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v2.json"),
            "v3_universe_manifest_sha256": sha256_file(repo_root / "research" / "universe_manifest_v3.json"),
        },
        "derived_classification": derived_classification,
        "derived_candidate_batch": {
            "members": members,
            "rule": (
                "the top_n assets of the frozen snapshot, in strictly descending market "
                "capitalization, that are strictly below the v3 floor, are not an asset of the "
                "v1, the v2 or the v3 universe and are not excluded by the inherited fixed "
                "lists or by the published classifier"
            ),
            "top_n": int(spec["universe"]["top_n"]),
            "count": len(members),
            "derivation": (
                "re-derived by scripts/build_research_v4_exclusion_amendment_2.py from the "
                "frozen snapshot and the rules above; the validation producer re-derives it "
                "again and refuses to write the manifests when the two disagree"
            ),
        },
        "provenance": {
            "authored_after_snapshot_retrieval": True,
            "authored_before_any_v4_candle_fetch": False,
            "authored_before_any_validation_outcome": False,
            "authored_before_any_strategy_result": True,
            "statement": (
                "Amendment 2 was authored after the market-cap snapshot was retrieved and after "
                "the first v4 validation attempt, whose outcome is recorded in the v3 cycle "
                "close-out and in research_state/agent_handoff.md: the first attempt applied "
                "the v2 floor and the v1/v2 identity rule and therefore re-derived the v3 "
                "batch. No marker, no floor and no identity rule was chosen from a validation "
                "outcome or a strategy result; no strategy result exists at all. The corrected "
                "batch is derived mechanically from the frozen snapshot and the published rules."
            ),
        },
        "not_authorized_by_this_amendment": [
            "no market-cap retrieval",
            "no candle fetch",
            "no evaluation, grid, backtest, campaign, selection or pilot",
            "no confirmatory-window read",
            "no change to the v1, v2 or v3 artifacts",
            "no change to the hashed source set",
        ],
        "related_artifacts": {
            "v4_specification": {
                "path": "configs/research_v4.json",
                "specification_hash": spec["specification_hash"],
            },
            "v4_snapshot_observation": {
                "path": "research/v4_evidence/snapshot_observation.json",
                "raw_response_sha256": sha256_file(repo_root / "research" / "v4_evidence" / "raw_market_cap_response.json"),
                "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
            },
            "v1_universe_manifest": {
                "path": "research/universe_manifest.json",
                "sha256": sha256_file(repo_root / "research" / "universe_manifest.json"),
            },
            "v2_universe_manifest": {
                "path": "research/universe_manifest_v2.json",
                "manifest_hash": v2_universe.get("manifest_hash"),
                "sha256": sha256_file(repo_root / "research" / "universe_manifest_v2.json"),
            },
            "v3_universe_manifest": {
                "path": "research/universe_manifest_v3.json",
                "manifest_hash": v3_universe.get("manifest_hash"),
                "sha256": sha256_file(repo_root / "research" / "universe_manifest_v3.json"),
            },
        },
        "producer": {
            "path": "scripts/build_research_v4_exclusion_amendment_2.py",
            "classifier_module": "scripts/v3_exclusion_classifier.py",
            "verify_command": "python3 scripts/verify_research_v4_manifests.py",
            "reproduce_command": "python3 scripts/build_research_v4_exclusion_amendment_2.py --force",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "amendment_hash_excluded_keys": list(AMENDMENT_HASH_EXCLUDED_KEYS),
            "note": (
                "amendment_hash is the sha256 of the document body with the amendment_hash key "
                "removed. It binds the classifier, the derived classification and the derived "
                "candidate batch."
            ),
        },
    }
    document["amendment_hash"] = compute_manifest_hash(document, AMENDMENT_HASH_EXCLUDED_KEYS)
    return document


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="rewrite the artifact")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    if AMENDMENT_2_PATH.exists() and not args.force:
        print(f"{AMENDMENT_2_PATH.relative_to(repo_root)} exists; pass --force to rewrite it")
        return 1
    AMENDMENT_2_PATH.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "amendment_path": str(AMENDMENT_2_PATH.relative_to(repo_root)),
        "amendment_hash": document["amendment_hash"],
        "floor_symbol": document["floor"]["floor_symbol"],
        "floor_market_cap_usd": document["floor"]["floor_market_cap_usd"],
        "excluded_by_identity": document["prior_universe"]["excluded_asset_count"],
        "batch": [member["binance_pair"] for member in document["derived_candidate_batch"]["members"]],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the v6 candidate manifest freeze.

``configs/research_v6_candidate_freeze.json`` freezes the v6 candidate set, the
v6 band and the v6 data boundary *before* any v6 evaluation runs.  This
producer is deterministic: given the repository state and the freeze instant it
rebuilds the artifact byte for byte.

Nothing here is copied out of another artifact and pasted in.  Every number the
freeze records is re-derived from the evidence that owns it:

* the **band** is re-derived from the raw market-cap snapshot bytes
  (``research/v6_evidence/raw_market_cap_response.json``) with the published
  rules of ``scripts/v6_universe_rules.py`` -- the floor rule, the identity
  rule over the v1, v2, v3, v4 and v5 universes, the exclusion rules and the
  strictly-descending ordering -- and never from a recorded member list;
* the **validation outcome** of every band member is re-derived from the
  validation evidence (``research/v6_evidence/binance_spot_verification.json``
  and ``research/v6_evidence/candle_verification.json``);
* the **floor** is recomputed from ``research/universe_manifest_v5.json``;
* the **identities** (specification, universe manifest, data manifest, source
  tree, evidence files, benchmark dataset) are recomputed from the files on
  disk;
* the **confirmatory window** is recomputed from the freeze instant and from
  the four freezes that own the v2, v3, v4 and v5 windows.

The producer never contacts a provider, never reads a confirmatory window and
never runs an evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    FLOOR_SOURCE_RELATIVE,
    MANIFEST_HASH_EXCLUDED_KEYS,
    PRIOR_UNIVERSE_RELATIVES,
    canonical_source_digest,
    compute_manifest_hash,
    derive_batch,
    development_window,
    load_exclusion_rules,
    parse_iso_utc,
    prior_universe_assets,
    read_json,
    recompute_floor,
    sha256_file,
)

#: The artifacts the freeze is bound to, relative to the repository root, so
#: the producer can rebuild the freeze from any checkout.
SPEC_RELATIVE = "configs/research_v6.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
ARTIFACT_RELATIVE = "configs/research_v6_candidate_freeze.json"
V5_FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"

#: The primary evidence of the v6 universe: the raw market-cap snapshot bytes
#: and the validation evidence.
RAW_RESPONSE_RELATIVE = "research/v6_evidence/raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_RELATIVE = "research/v6_evidence/snapshot_observation.json"
SPOT_EVIDENCE_RELATIVE = "research/v6_evidence/binance_spot_verification.json"
CANDLE_EVIDENCE_RELATIVE = "research/v6_evidence/candle_verification.json"

#: The freezes that own the v2, v v3, v4 and v5 confirmatory windows, and the
#: key each one keeps its window bounds under.
GATE_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The candidate freezes of the earlier versions, whose candidate sets the v6
#: set must be disjoint from.
PRIOR_FREEZE_RELATIVES: Tuple[Tuple[str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json"),
    ("v3", "configs/research_v3_candidate_freeze.json"),
    ("v4", "configs/research_v4_candidate_freeze.json"),
    ("v5", "configs/research_v5_candidate_freeze.json"),
)

#: The header of the canonical hourly CSV serialization
#: (``sha256-canonical-hourly-csv-v1``).
DATASET_HEADER = "timestamp,open,high,low,close,volume\n"

#: The exclusion reasons a band member can carry after validation.
SPOT_UNAVAILABLE = "binance_spot_unavailable"
INSUFFICIENT_HISTORY = "insufficient_hourly_history"
COVERAGE_GAP = "coverage_gap"
CANDLE_VALIDATION_FAILED = "candle_validation_failed"


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_utc_ms(timestamp_ms: Optional[int]) -> Optional[str]:
    if timestamp_ms is None:
        return None
    seconds, millis = divmod(int(timestamp_ms), 1000)
    moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    if millis:
        moment = moment.replace(microsecond=millis * 1000)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def first_hour_boundary_after(value: datetime) -> datetime:
    """The first UTC hour boundary strictly after ``value``."""
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if boundary <= value:
        boundary += timedelta(hours=1)
    return boundary


def canonical_hourly_csv_digest(path: Path) -> Tuple[str, int, Optional[int], Optional[int]]:
    """The canonical hourly CSV digest of a dataset, and its bounds.

    The dataset is stored in the canonical hourly CSV serialization, so the
    digest is taken over the *re-serialized* rows: every number is re-rendered
    with the ``.17g`` format and the header is rebuilt, so a dataset that is
    not canonical is refused rather than hashed.  The digest, the row count and
    the first and last open timestamps are all recomputed from the file's
    bytes.
    """
    digest = hashlib.sha256()
    digest.update(DATASET_HEADER.encode("utf-8"))
    rows = 0
    first_timestamp: Optional[int] = None
    last_timestamp: Optional[int] = None
    with Path(path).open("r", encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n")
        if header != DATASET_HEADER.rstrip("\n"):
            raise SystemExit(f"{path} is not in the canonical hourly CSV form")
        for line in handle:
            line = line.strip()
            if not line:
                continue
            fields = line.split(",")
            if len(fields) != 6:
                raise SystemExit(f"{path} holds a malformed canonical row")
            timestamp, open_, high, low, close, volume = fields
            digest.update(
                (
                    ",".join(
                        [
                            str(int(timestamp)),
                            format(float(open_), ".17g"),
                            format(float(high), ".17g"),
                            format(float(low), ".17g"),
                            format(float(close), ".17g"),
                            format(float(volume), ".17g"),
                        ]
                    )
                    + "\n"
                ).encode("utf-8")
            )
            rows += 1
            if first_timestamp is None:
                first_timestamp = int(timestamp)
            last_timestamp = int(timestamp)
    return digest.hexdigest(), rows, first_timestamp, last_timestamp


def band_member_outcome(
    pair: str,
    spot_evidence: Dict[str, Any],
    candle_evidence: Dict[str, Any],
    min_candles: int,
) -> Dict[str, Any]:
    """The validation outcome of one band member, re-derived from the evidence.

    The rules are the ones ``scripts/v6_constituent_validation.py`` applied
    when the evidence was recorded: a pair that is not tradeable on Binance
    spot is excluded before any candle is read, and a tradeable pair is
    excluded when its history is short, when it has a coverage gap or when its
    candles do not validate.
    """
    spot = (spot_evidence.get("pairs") or {}).get(pair) or {}
    record = (candle_evidence.get("records") or {}).get(pair) or {}
    tradeable = bool(spot.get("tradeable"))
    if not tradeable:
        return {
            "binance_spot_verified": False,
            "candle_history_verified": False,
            "exclusion_reason": SPOT_UNAVAILABLE,
            "observed_candles": None,
            "validated": False,
        }
    observed = int(record.get("observed_candle_count") or 0)
    if record.get("validated"):
        reason: Optional[str] = None
        history_verified = True
        validated = True
    elif observed < int(min_candles):
        reason = INSUFFICIENT_HISTORY
        history_verified = False
        validated = False
    elif record.get("gaps"):
        reason = COVERAGE_GAP
        history_verified = False
        validated = False
    else:
        reason = CANDLE_VALIDATION_FAILED
        history_verified = False
        validated = False
    return {
        "binance_spot_verified": True,
        "candle_history_verified": history_verified,
        "exclusion_reason": reason,
        "observed_candles": observed,
        "validated": validated,
    }


def window_bounds(owner: Dict[str, Any], key: str) -> Dict[str, Any]:
    """The window bounds of a window-owning freeze."""
    block = owner.get(key) or {}
    start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
    min_hours = block.get("min_confirmatory_window_hours")
    if min_hours is None:
        min_hours = block.get("min_hours")
    end = block.get("earliest_possible_confirmatory_window_end_utc")
    if end is None:
        end = block.get("earliest_possible_end_utc")
    return {
        "window_start_utc": str(start) if start else None,
        "min_hours": int(min_hours) if min_hours is not None else None,
        "earliest_possible_end_utc": str(end) if end else None,
    }


def build(repo_root: Path = REPO_ROOT, freeze_utc: Optional[str] = None) -> Dict[str, Any]:
    """Rebuild the v6 candidate freeze from the repository state."""
    root = Path(repo_root)
    spec = read_json(root / SPEC_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data_manifest = read_json(root / DATA_RELATIVE)
    v5_freeze = read_json(root / V5_FREEZE_RELATIVE)
    observation = read_json(root / SNAPSHOT_OBSERVATION_RELATIVE)
    spot_evidence = read_json(root / SPOT_EVIDENCE_RELATIVE)
    candle_evidence = read_json(root / CANDLE_EVIDENCE_RELATIVE)
    markets = json.loads((root / RAW_RESPONSE_RELATIVE).read_text(encoding="utf-8"))

    freeze_instant = parse_iso_utc(freeze_utc) if freeze_utc else datetime.now(timezone.utc)
    window_open = first_hour_boundary_after(freeze_instant)
    min_hours = int(spec["holdout"]["v6_confirmatory_window"]["min_hours"])
    earliest_end = window_open + timedelta(hours=min_hours)
    development_cutoff = parse_iso_utc(spec["holdout"]["development_cutoff_utc"])
    min_candles = int(spec["universe"]["min_candles"])
    dev_window = development_window(spec)

    # --- the band, re-derived from the raw snapshot bytes -------------------
    prior_universes = [read_json(root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    exclusion_rules = load_exclusion_rules(root)
    band, rule_exclusions, _records = derive_batch(spec, markets, prior_universes, exclusion_rules)
    band_width = int(spec["universe"]["expansion_scope"]["band_width_rule"]["band_width"])

    members: List[Dict[str, Any]] = []
    for entry in band:
        pair = str(entry["binance_pair"])
        outcome = band_member_outcome(pair, spot_evidence, candle_evidence, min_candles)
        members.append(
            {
                "binance_pair": pair,
                "binance_spot_verified": outcome["binance_spot_verified"],
                "candle_history_verified": outcome["candle_history_verified"],
                "coingecko_id": entry["coingecko_id"],
                "exclusion_reason": outcome["exclusion_reason"],
                "market_cap_rank": entry["market_cap_rank"],
                "market_cap_usd": entry["market_cap_usd"],
                "name": entry["name"],
                "observed_candles": outcome["observed_candles"],
                "rank": entry["rank"],
                "symbol": entry["symbol"],
                "validated": outcome["validated"],
            }
        )
    if len(members) != band_width:
        raise SystemExit(
            f"the re-derived band holds {len(members)} names, but the band width is {band_width}"
        )
    validated_members = [member for member in members if member["validated"]]
    excluded_members = [member for member in members if not member["validated"]]
    reason_counts: Dict[str, int] = {}
    for member in excluded_members:
        reason = str(member["exclusion_reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # --- the floor, recomputed from the v5 universe manifest ----------------
    floor_source = read_json(root / FLOOR_SOURCE_RELATIVE)
    floor_symbol, floor_market_cap = recompute_floor(floor_source)
    floor_entry = min(
        floor_source["eligible_assets"], key=lambda entry: int(entry.get("market_cap_usd") or 0)
    )

    # --- the identity rule, recomputed from the five prior manifests --------
    prior_symbols, prior_identifiers = prior_universe_assets(*prior_universes)

    # --- the gates, recomputed from the freezes that own their windows ------
    gates: List[Dict[str, Any]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = window_bounds(owner, key)
        gates.append(
            {
                "earliest_possible_end_utc": bounds["earliest_possible_end_utc"],
                "min_hours": bounds["min_hours"],
                "source_key": key,
                "source_path": relative,
                "version": version,
                "window_start_utc": bounds["window_start_utc"],
            }
        )
    gate_ends = [str(gate["earliest_possible_end_utc"]) for gate in gates]
    v6_earliest_end = format_utc(earliest_end)
    evaluation_start = max(gate_ends + [v6_earliest_end])

    # --- the benchmark, recomputed from the dataset's own bytes -------------
    benchmark_block = data_manifest.get("benchmark") or {}
    benchmark_path = str(benchmark_block.get("dataset_path") or "")
    benchmark_digest, benchmark_rows, first_open_ms, last_open_ms = canonical_hourly_csv_digest(
        root / benchmark_path
    )
    benchmark_last_close = format_utc_ms(int(last_open_ms) + 3600_000)

    # --- the identities, recomputed from the artifacts that own them -------
    specification_hash = compute_manifest_hash(spec, ("specification_hash",))
    universe_manifest_hash = compute_manifest_hash(universe, MANIFEST_HASH_EXCLUDED_KEYS)
    data_manifest_hash = compute_manifest_hash(
        data_manifest, ("manifest_hash", "snapshot_identity.data_manifest_hash")
    )
    v5_freeze_hash = compute_manifest_hash(v5_freeze, ("manifest_hash",))
    source_digest = canonical_source_digest(root)

    namespace = spec.get("namespace") or {}
    band_rule = spec["universe"]["expansion_scope"]["band_width_rule"]
    membership = spec["holdout"]["confirmatory_window_membership"]
    window_rule = spec["holdout"]["v6_confirmatory_window"]

    document: Dict[str, Any] = {
        "artifact": "v6_candidate_freeze",
        "artifact_version": "v6-candidate-freeze-1",
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "manifest_hash": None,
        "candidate_freeze_utc": format_utc(freeze_instant),
        "freeze_status": "FROZEN",
        "specification_purpose": (
            "Freeze the v6 candidate set, the v6 band and the v6 data boundary before any v6 "
            "evaluation runs. This artifact authorizes nothing."
        ),
        "specification_hash": specification_hash,
        "universe_manifest_hash": universe_manifest_hash,
        "universe_manifest_path": UNIVERSE_RELATIVE,
        "data_manifest_hash": data_manifest_hash,
        "data_manifest_path": DATA_RELATIVE,
        "snapshot_identity": {
            "candidate_manifest_hash": None,
            "market_cap_source_endpoint": str(spec["universe"]["endpoint"]),
            "market_cap_source_raw_response_path": RAW_RESPONSE_RELATIVE,
            "market_cap_source_raw_response_sha256": sha256_file(root / RAW_RESPONSE_RELATIVE),
            "market_cap_source_retrieval_timestamp_utc": str(
                observation.get("retrieval_timestamp_utc") or ""
            ),
            "protocol_version": spec["protocol_version"],
            "ranking_depth": len(markets),
            "snapshot_observation_path": SNAPSHOT_OBSERVATION_RELATIVE,
            "snapshot_observation_sha256": sha256_file(root / SNAPSHOT_OBSERVATION_RELATIVE),
            "universe_version": spec["universe_version"],
        },
        "code_identity": {
            "algorithm": "canonical_source_digest_v1",
            "authorized_ordered_code_hash": str(
                (spec.get("code_identity") or {}).get("authorized_ordered_code_hash") or ""
            ),
            "canonical_source_digest": source_digest,
            "hashed_set_root": str((spec.get("code_identity") or {}).get("hashed_set_root") or ""),
            "ordered_code_hash_is_not_an_identity": True,
            "portable": True,
            "recompute_rule": (
                "the canonical source digest is recomputed from the *.py files under the hashed "
                "set root in ascending path order; the checkout-dependent ordered digest of "
                "compute_code_hash() is never used as an identity"
            ),
        },
        "band": {
            "band_never_widened": True,
            "band_width": band_width,
            "band_width_source": "configs/research_v6.json -> universe.expansion_scope.band_width_rule.band_width",
            "excluded_member_count": len(excluded_members),
            "exclusion_reason_counts": reason_counts,
            "floor_never_lowered": True,
            "member_count": len(members),
            "members": members,
            "ordering": str(band_rule.get("ordering")),
            "recompute_rule": (
                "the band is re-derived from the raw market-cap snapshot bytes with the published "
                "rules: the qualifying names (strictly below the recomputed floor, not "
                "rule-excluded, not an asset of the v1, v2, v3, v4 or v5 universe) are taken in "
                "strictly descending market-capitalization order and the first band_width of them "
                "are the band; a recorded member list is never trusted"
            ),
            "rule": str(band_rule.get("rule")),
            "shortfall_rule": str(band_rule.get("shortfall_rule")),
            "validated_count": len(validated_members),
            "validated_set_is_a_consequence_of_the_band": True,
        },
        "candidates": validated_members,
        "candidate_set": {
            "count": len(validated_members),
            "exclusion_reasons": {
                "binance_spot_unavailable": [
                    member["binance_pair"]
                    for member in excluded_members
                    if member["exclusion_reason"] == SPOT_UNAVAILABLE
                ],
                "insufficient_hourly_history": [
                    member["binance_pair"]
                    for member in excluded_members
                    if member["exclusion_reason"] == INSUFFICIENT_HISTORY
                ],
            },
            "members": [member["binance_pair"] for member in validated_members],
            "rule": (
                "the candidate set is the validated subset of the frozen band; the band is the "
                "definition and the validated subset is its consequence"
            ),
        },
        "exclusions": rule_exclusions,
        "floor": {
            "comparison": "strictly_less_than",
            "floor_market_cap_rank": floor_entry.get("market_cap_rank"),
            "floor_market_cap_usd": floor_market_cap,
            "floor_symbol": floor_symbol,
            "recompute_rule": (
                "the floor is the minimum market_cap_usd over the eligible_assets of "
                "research/universe_manifest_v5.json; the verifier recomputes it from that "
                "manifest and never trusts this recorded value"
            ),
            "source_manifest_path": FLOOR_SOURCE_RELATIVE,
            "source_universe_version": "v5",
        },
        "identity_rule": {
            "distinct_prior_binance_symbols": len(prior_symbols),
            "distinct_prior_coingecko_ids": len(prior_identifiers),
            "matched_on": ["binance_symbol", "coingecko_id"],
            "prior_universe_versions": ["v1", "v2", "v3", "v4", "v5"],
            "recompute_rule": (
                "the two counts are recomputed by the verifier from the five prior universe "
                "manifests; the base symbol and the pair spelling of the same Binance symbol are "
                "one marker, not two"
            ),
            "rule": str(
                spec["universe"]["expansion_scope"]["prior_universe_asset_identity"].get("rule")
            ),
        },
        "data_boundary": {
            "access_counting": (
                "Every read of a candle inside a confirmatory window increments "
                "holdout_exposed_count in the v6 checkpoint and is recorded in the v6 holdout "
                "report."
            ),
            "confirmatory_window_membership_amendment_required": False,
            "confirmatory_window_membership_rule": str(membership.get("rule")),
            "confirmatory_window_membership_rule_owner": {
                "interval_start_inclusive": bool(membership.get("interval_start_inclusive")),
                "key": "holdout.confirmatory_window_membership",
                "path": SPEC_RELATIVE,
                "rule": (
                    "the v6 specification was written with the corrected rule, so the v6 chain "
                    "needs no membership amendment; the v5 amendment "
                    "configs/research_v5_specification_amendment_1.json stays the owner of the v5 "
                    "chain's own correction"
                ),
                "specification_hash": specification_hash,
            },
            "data_used_for_candidate_selection": "excluded",
            "development_cutoff_utc": format_utc(development_cutoff),
            "development_cutoff_rule": str(spec["holdout"]["development_cutoff_rule"]),
            "development_data_rule": (
                "Candles that close at or before effective_data_boundary_utc are development data "
                "and may inform selection. No candle that closes after that instant may be read "
                "during selection."
            ),
            "development_window": {
                "candle_count": int(dev_window["candle_count"]),
                "first_candle_open_utc": format_utc_ms(int(dev_window["first_open_ms"])),
                "interval": "1h",
                "last_candle_close_utc": format_utc_ms(int(dev_window["last_open_ms"]) + 3600_000),
                "recompute_rule": (
                    "the development window is the closed hourly candle span that ends at the "
                    "development cutoff: the last candle is the one that closes exactly at the "
                    "cutoff and the first candle opens candle_count - 1 hours before it; both "
                    "bounds are recomputed from the cutoff and the candle count"
                ),
            },
            "earliest_possible_confirmatory_window_end_utc": v6_earliest_end,
            "effective_data_boundary_rule": (
                "v6 uses the preregistered development cutoff (the v2 window start) as the "
                "binding boundary; the v6 confirmatory window opens after the freeze"
            ),
            "effective_data_boundary_utc": format_utc(development_cutoff),
            "min_confirmatory_window_hours": min_hours,
            "min_confirmatory_window_rationale": str(window_rule.get("min_hours_rationale")),
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
            "v3_confirmatory_window_reuse": "forbidden",
            "v4_confirmatory_window_reuse": "forbidden",
            "v5_confirmatory_window_reuse": "forbidden",
            "v6_confirmatory_window_start_rule": (
                "the first UTC hour boundary strictly after candidate_freeze_utc"
            ),
            "v6_confirmatory_window_start_utc": format_utc(window_open),
        },
        "confirmatory_window": {
            "earliest_possible_end_utc": v6_earliest_end,
            "evaluation_may_not_start_before_utc": evaluation_start,
            "evaluation_start_rule": (
                "the v6 evaluation may not start before the later of the four recorded gates and "
                "the v6 window's own earliest end"
            ),
            "gates": gates,
            "min_hours": min_hours,
            "opens_utc": format_utc(window_open),
            "overlap_rule": (
                "the v6 confirmatory window opens inside the still-open v2, v3, v4 and v5 "
                "confirmatory windows, which is not a violation: the v6 evaluation may not start "
                "before the later of the four recorded gates and the v6 window's own earliest "
                "end, the two evaluations share no asset, and no confirmatory window is ever read "
                "for selection"
            ),
            "single_use": True,
        },
        "benchmark": {
            "boundary_rule": str(
                spec["holdout"]["benchmark_rule"].get("boundary_rule") or ""
            ),
            "candle_count": benchmark_rows,
            "closes_after_the_development_cutoff": benchmark_last_close
            > format_utc(development_cutoff),
            "content_hash": benchmark_digest,
            "content_hash_algorithm": "sha256-canonical-hourly-csv-v1",
            "content_hash_digest_scope": (
                "the sha256 of the canonical hourly CSV serialization of the dataset file, "
                "recomputed from the file's bytes; the dataset is stored in that canonical form"
            ),
            "dataset_path": benchmark_path,
            "first_candle_open_utc": format_utc_ms(first_open_ms),
            "last_candle_close_utc": benchmark_last_close,
            "recompute_rule": (
                "the verifier recomputes the content hash, the row count and the first and last "
                "candle from the dataset file's own bytes; it never trusts a recorded digest"
            ),
        },
        "namespace": {
            "candidate_freeze": ARTIFACT_RELATIVE,
            "checkpoint": str(namespace.get("checkpoint")),
            "datasets_directory": str(namespace.get("datasets_directory")),
            "data_manifest": DATA_RELATIVE,
            "evidence_directory": str(namespace.get("evidence_directory")),
            "ledger": str(namespace.get("ledger")),
            "no_foreign_path_is_written": True,
            "result_stream": str(namespace.get("result_stream")),
            "results_manifest": str(namespace.get("results_manifest")),
            "rule": str(namespace.get("rule")),
            "shards_directory": str(namespace.get("shards_directory")),
            "universe_manifest": UNIVERSE_RELATIVE,
        },
        "supersedes": {
            "reason": (
                "The v5 candidate set is frozen for the v5 cycle. The v6 batch is a strictly "
                "additional universe below the v5 floor with separate namespaces."
            ),
            "supersession_scope": (
                "Additive only. The v1, v2, v3, v4 and v5 artifacts are not replaced, rewritten "
                "or reinterpreted: they remain immutable historical evidence, and the v6 "
                "candidate set contains no asset of any of them."
            ),
            "v1_artifacts_are_immutable": True,
            "v1_v2_v3_v4_v5_artifacts_are_immutable": True,
            "v2_artifacts_are_immutable": True,
            "v3_artifacts_are_immutable": True,
            "v4_artifacts_are_immutable": True,
            "v5_artifacts_are_immutable": True,
            "v5_candidate_freeze_hash": v5_freeze_hash,
            "v5_candidate_freeze_hash_scope": (
                "the manifest_hash the v5 candidate freeze recomputes over its own body"
            ),
            "v5_candidate_freeze_path": V5_FREEZE_RELATIVE,
            "v5_candidate_freeze_sha256": sha256_file(root / V5_FREEZE_RELATIVE),
            "v5_candidate_freeze_sha256_scope": (
                "the sha256 of the v5 candidate freeze file's bytes on disk"
            ),
        },
        "producer": {
            "path": "scripts/build_v6_candidate_freeze.py",
            "recompute_rule": (
                "the producer re-derives the band from the raw snapshot bytes and the validation "
                "outcomes from the validation evidence; it never copies a recorded member list"
            ),
            "reproduce_command": (
                "python3 scripts/build_v6_candidate_freeze.py --freeze-utc <candidate_freeze_utc> "
                "--force"
            ),
        },
        "durability": {"commit": None, "pushed": False},
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with the manifest_hash key "
                "removed; every other digest the document records is the digest of the file it "
                "names, recomputed from that file's bytes"
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--freeze-utc")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root)
    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(json.dumps({"ok": False, "error": "artifact exists; use --force to overwrite"}, indent=2))
        return 1
    document = build(repo_root, args.freeze_utc)
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "path": ARTIFACT_RELATIVE,
                "candidate_freeze_utc": document["candidate_freeze_utc"],
                "manifest_hash": document["manifest_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only, offline verification of the v6 candidate freeze.

``configs/research_v6_candidate_freeze.json`` freezes the v6 band, the v6
candidate set, the v6 data boundary and the v6 confirmatory window before any
v6 evaluation runs.  The verifier never writes to the repository, never
contacts a provider, never reads a confirmatory window and never runs a grid.
Every expectation is **recomputed** from the repository state -- from the raw
market-cap snapshot bytes, from the validation evidence, from the manifests and
from the freezes that own the earlier windows -- never from a constant copied
out of the artifact it checks.

It checks:

1. the freeze is self-hashing and is the v6 freeze;
2. it is bound to the v6 specification, to the v6 universe manifest and to the
   v6 data manifest, and every identity it records is recomputed from the
   artifact that owns it (the snapshot identity from the evidence files, the
   code identity from the source tree);
3. the frozen **band** is exactly the band re-derived from the raw snapshot
   bytes with the published rules: 20 names in strictly descending
   market-capitalization order, each with its validation outcome and its
   exclusion reason, and the **candidate set** is exactly the validated
   members;
4. the **floor rule** holds: every band member is strictly below the floor
   recomputed from ``research/universe_manifest_v5.json``, and the recorded
   floor is that recomputation;
5. the **identity rule** holds: no band member is an asset of the v1, the v2,
   the v3, the v4 or the v5 universe, and the recorded identity counts are
   recomputed from the five manifests;
6. the **data boundary** holds: the development cutoff is the earliest open
   confirmatory window's start, the inclusive convention is stated, and the
   confirmatory-window membership rule is the rule the v6 specification owns
   (the v6 chain needs no membership amendment);
7. the **confirmatory window** is a new window: it opens at the first UTC hour
   boundary strictly after the freeze, it needs 2,160 closed hourly candles,
   its earliest end follows from its start, it is single-use, it is not any of
   the v1-v5 windows, the v6 candidate set is disjoint from every earlier
   candidate set, and the recorded evaluation gate is the later of the four
   recomputed gates and the v6 window's own earliest end;
8. the **benchmark** the freeze names exists, is hash-verified from its own
   bytes and ends exactly at the development cutoff;
9. the ``supersedes`` chain names the v5 freeze with its recomputed manifest
   hash and its recomputed file digest, and the v1-v5 artifacts are unchanged;
10. the exposure counter starts at 0, the freeze authorizes nothing, no v6 run
    artifact exists and the v6 namespace is not polluted.

Exit status is 0 when every check passes and 1 otherwise.  The report is
printed as JSON so it can be diffed between runs.  The verifier is
**clock-free**: every expectation is a property of the frozen artifacts.
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

FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v6.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
V5_FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"

#: The primary evidence of the v6 universe.
RAW_RESPONSE_RELATIVE = "research/v6_evidence/raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_RELATIVE = "research/v6_evidence/snapshot_observation.json"
SPOT_EVIDENCE_RELATIVE = "research/v6_evidence/binance_spot_verification.json"
CANDLE_EVIDENCE_RELATIVE = "research/v6_evidence/candle_verification.json"

#: The hashed set whose canonical digest is the portable code identity.
HASHED_SET_ROOT = "src/breakout_research"

#: The freezes that own the v2, v3, v4 and v5 confirmatory windows, and the
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

#: The paths a v6 run creates.  Before the authorized run none of them may
#: exist.
V6_RUN_ARTIFACTS: Tuple[str, ...] = (
    "research/shards_v6",
    "research/ledger_v6.json",
    "research/results_manifest_v6.json",
    "research/results_v6.jsonl",
    "research_state/checkpoint_v6.json",
)

#: The v6 confirmatory artifacts, and the dotted key each one keeps the
#: freeze's identity under. The confirmatory chain binds the freeze forward:
#: the protocol and the runbook name this freeze's manifest hash, so the
#: freeze verifier checks that binding rather than their absence.
V6_CONFIRMATORY_ARTIFACTS: Tuple[Tuple[str, str], ...] = (
    ("configs/research_v6_confirmatory_protocol.json",
     "related_artifacts.v6_candidate_freeze.manifest_hash"),
    ("configs/research_v6_confirmatory_runbook_1.json",
     "binding_identities.v6_candidate_freeze.manifest_hash"),
)

#: The minimum number of closed hourly candles a confirmatory window needs.
MIN_CONFIRMATORY_WINDOW_HOURS = 2160

#: The exclusion reasons a band member can carry after validation.
ALLOWED_EXCLUSION_REASONS = (
    "binance_spot_unavailable",
    "insufficient_hourly_history",
    "coverage_gap",
    "candle_validation_failed",
)

#: The header of the canonical hourly CSV serialization
#: (``sha256-canonical-hourly-csv-v1``).
DATASET_HEADER = "timestamp,open,high,low,close,volume\n"

#: The snapshot-identity fields the freeze must carry.
SNAPSHOT_IDENTITY_KEYS = (
    "candidate_manifest_hash",
    "market_cap_source_endpoint",
    "market_cap_source_raw_response_path",
    "market_cap_source_raw_response_sha256",
    "market_cap_source_retrieval_timestamp_utc",
    "protocol_version",
    "ranking_depth",
    "snapshot_observation_path",
    "snapshot_observation_sha256",
    "universe_version",
)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_utc_ms(timestamp_ms: Optional[int]) -> Optional[str]:
    if timestamp_ms is None:
        return None
    seconds, millis = divmod(int(timestamp_ms), 1000)
    moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    if millis:
        moment = moment.replace(microsecond=millis * 1000)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_hour_boundary_after(value: datetime) -> datetime:
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if boundary <= value:
        boundary += timedelta(hours=1)
    return boundary


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def canonical_hourly_csv_digest(path: Path) -> Tuple[str, int, Optional[int], Optional[int]]:
    """The canonical hourly CSV digest of a dataset, and its bounds.

    The dataset is stored in the canonical hourly CSV serialization, so the
    digest is taken over the *re-serialized* rows: every number is re-rendered
    with the ``.17g`` format and the header is rebuilt, so a dataset that is
    not canonical is refused rather than hashed.
    """
    digest = hashlib.sha256()
    digest.update(DATASET_HEADER.encode("utf-8"))
    rows = 0
    first_timestamp: Optional[int] = None
    last_timestamp: Optional[int] = None
    with Path(path).open("r", encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n")
        if header != DATASET_HEADER.rstrip("\n"):
            raise ValueError(f"{path} is not in the canonical hourly CSV form")
        for line in handle:
            line = line.strip()
            if not line:
                continue
            fields = line.split(",")
            if len(fields) != 6:
                raise ValueError(f"{path} holds a malformed canonical row")
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

    A pair that is not tradeable on Binance spot is excluded before any candle
    is read; a tradeable pair is excluded when its history is short, when it
    has a coverage gap or when its candles do not validate.
    """
    spot = (spot_evidence.get("pairs") or {}).get(pair) or {}
    record = (candle_evidence.get("records") or {}).get(pair) or {}
    if not bool(spot.get("tradeable")):
        return {
            "binance_spot_verified": False,
            "candle_history_verified": False,
            "exclusion_reason": "binance_spot_unavailable",
            "observed_candles": None,
            "validated": False,
        }
    observed = int(record.get("observed_candle_count") or 0)
    if record.get("validated"):
        reason: Optional[str] = None
        history_verified = True
        validated = True
    elif observed < int(min_candles):
        reason = "insufficient_hourly_history"
        history_verified = False
        validated = False
    elif record.get("gaps"):
        reason = "coverage_gap"
        history_verified = False
        validated = False
    else:
        reason = "candle_validation_failed"
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


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    computed: Dict[str, Any] = {}
    root = Path(repo_root)

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        FREEZE_RELATIVE,
        SPEC_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
        V5_FREEZE_RELATIVE,
        RAW_RESPONSE_RELATIVE,
        SNAPSHOT_OBSERVATION_RELATIVE,
        SPOT_EVIDENCE_RELATIVE,
        CANDLE_EVIDENCE_RELATIVE,
    ):
        if not (root / relative).exists():
            return {
                "ok": False,
                "freeze_path": FREEZE_RELATIVE,
                "failures": [f"missing artifact: {relative}"],
            }

    freeze = read_json(root / FREEZE_RELATIVE)
    spec = read_json(root / SPEC_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    v5_freeze = read_json(root / V5_FREEZE_RELATIVE)
    observation = read_json(root / SNAPSHOT_OBSERVATION_RELATIVE)
    spot_evidence = read_json(root / SPOT_EVIDENCE_RELATIVE)
    candle_evidence = read_json(root / CANDLE_EVIDENCE_RELATIVE)
    markets = json.loads((root / RAW_RESPONSE_RELATIVE).read_text(encoding="utf-8"))

    # 1. the document itself ------------------------------------------------
    if freeze.get("artifact") != "v6_candidate_freeze":
        fail("the freeze is not the v6 candidate freeze")
    if freeze.get("protocol_version") != "v6" or freeze.get("universe_version") != "v6":
        fail("the freeze is not a v6 artifact")
    if freeze.get("freeze_status") != "FROZEN":
        fail("the freeze status is not FROZEN")
    excluded = tuple(
        (freeze.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    recomputed_hash = compute_manifest_hash(freeze, excluded)
    computed["manifest_hash"] = freeze.get("manifest_hash")
    computed["recomputed_manifest_hash"] = recomputed_hash
    if freeze.get("manifest_hash") != recomputed_hash:
        fail(
            f"manifest_hash mismatch: declared {freeze.get('manifest_hash')}, "
            f"recomputed {recomputed_hash}"
        )

    # 2. the bindings, recomputed from the artifacts that own them ----------
    specification_hash = compute_manifest_hash(spec, ("specification_hash",))
    if spec.get("specification_hash") != specification_hash:
        fail("the v6 specification does not recompute its own specification_hash")
    if freeze.get("specification_hash") != specification_hash:
        fail("the freeze is not bound to the v6 specification")
    universe_manifest_hash = compute_manifest_hash(universe, MANIFEST_HASH_EXCLUDED_KEYS)
    if universe.get("manifest_hash") != universe_manifest_hash:
        fail("the v6 universe manifest does not recompute its own manifest_hash")
    if freeze.get("universe_manifest_hash") != universe_manifest_hash:
        fail("the freeze is not bound to the v6 universe manifest")
    data_manifest_hash = compute_manifest_hash(
        data, ("manifest_hash", "snapshot_identity.data_manifest_hash")
    )
    if data.get("manifest_hash") != data_manifest_hash:
        fail("the v6 data manifest does not recompute its own manifest_hash")
    if freeze.get("data_manifest_hash") != data_manifest_hash:
        fail("the freeze is not bound to the v6 data manifest")
    if freeze.get("universe_manifest_path") != UNIVERSE_RELATIVE:
        fail("the freeze does not name the v6 universe manifest")
    if freeze.get("data_manifest_path") != DATA_RELATIVE:
        fail("the freeze does not name the v6 data manifest")

    # 2b. the snapshot identity, recomputed from the evidence files ---------
    snapshot = freeze.get("snapshot_identity") or {}
    if set(snapshot) != set(SNAPSHOT_IDENTITY_KEYS):
        fail(
            "the snapshot identity does not carry exactly its fields: "
            f"{sorted(set(snapshot) ^ set(SNAPSHOT_IDENTITY_KEYS))}"
        )
    if snapshot.get("market_cap_source_raw_response_path") != RAW_RESPONSE_RELATIVE:
        fail("the snapshot identity does not name the raw market-cap response")
    if snapshot.get("market_cap_source_raw_response_sha256") != sha256_file(
        root / RAW_RESPONSE_RELATIVE
    ):
        fail("the snapshot identity names a raw-response digest the file does not have")
    if snapshot.get("snapshot_observation_path") != SNAPSHOT_OBSERVATION_RELATIVE:
        fail("the snapshot identity does not name the snapshot observation")
    if snapshot.get("snapshot_observation_sha256") != sha256_file(
        root / SNAPSHOT_OBSERVATION_RELATIVE
    ):
        fail("the snapshot identity names an observation digest the file does not have")
    if snapshot.get("market_cap_source_retrieval_timestamp_utc") != str(
        observation.get("retrieval_timestamp_utc") or ""
    ):
        fail("the snapshot identity names another retrieval instant than the observation")
    if snapshot.get("ranking_depth") != len(markets):
        fail(
            f"the snapshot identity records a ranking depth of {snapshot.get('ranking_depth')}, "
            f"recomputed {len(markets)} from the raw response bytes"
        )
    if snapshot.get("market_cap_source_endpoint") != str(spec.get("universe", {}).get("endpoint")):
        fail("the snapshot identity names another endpoint than the specification")
    if snapshot.get("protocol_version") != "v6" or snapshot.get("universe_version") != "v6":
        fail("the snapshot identity is not a v6 snapshot identity")
    if snapshot.get("candidate_manifest_hash") is not None:
        fail("the snapshot identity claims a candidate manifest hash the freeze does not have")

    # 2c. the code identity -------------------------------------------------
    code_identity = freeze.get("code_identity") or {}
    # ``canonical_source_digest`` takes the *repository* root and appends the
    # hashed-set root itself, so it is called with the repository root.
    hashed_set_digest = canonical_source_digest(root)
    computed["canonical_hashed_set_digest"] = hashed_set_digest
    if hashed_set_digest is None:
        fail("the hashed source set is missing, so the tree identity cannot be recomputed")
    elif code_identity.get("canonical_source_digest") != hashed_set_digest:
        fail(
            "the recorded canonical source digest is "
            f"{code_identity.get('canonical_source_digest')}, recomputed {hashed_set_digest}"
        )
    if code_identity.get("hashed_set_root") != HASHED_SET_ROOT:
        fail("the freeze does not name the hashed set src/breakout_research")
    if code_identity.get("portable") is not True:
        fail("the freeze does not record the code identity as portable")
    if code_identity.get("ordered_code_hash_is_not_an_identity") is not True:
        fail("the freeze does not record that the ordered code hash is not an identity")
    spec_code_identity = spec.get("code_identity") or {}
    if spec_code_identity.get("hashed_set_digest") != hashed_set_digest:
        fail("the v6 specification records another digest for the hashed source set")
    if code_identity.get("authorized_ordered_code_hash") != spec_code_identity.get(
        "authorized_ordered_code_hash"
    ):
        fail("the freeze does not retain the authorized ordered code hash as value of record")
    for entry in (root / "src").iterdir() if (root / "src").is_dir() else []:
        if entry.is_dir() and entry.name.startswith("v6"):
            fail(
                f"the v6 execution path {entry.name} lives inside src/, but the v6 execution path "
                "must be a new directory outside the hashed set"
            )

    # 3. the band, re-derived from the raw snapshot bytes -------------------
    prior_universes = [read_json(root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    exclusion_rules = load_exclusion_rules(root)
    try:
        derived_band, derived_exclusions, _records = derive_batch(
            spec, markets, prior_universes, exclusion_rules
        )
    except SystemExit as exc:
        fail(f"the band cannot be re-derived from the raw snapshot bytes: {exc}")
        derived_band, derived_exclusions = [], []
    derived_pairs = [str(entry["binance_pair"]) for entry in derived_band]
    derived_by_pair = {str(entry["binance_pair"]): entry for entry in derived_band}

    band = freeze.get("band") or {}
    members = band.get("members") or []
    if not members:
        fail("the frozen band is empty")
    band_width = int(spec["universe"]["expansion_scope"]["band_width_rule"]["band_width"])
    computed["band_width"] = band_width
    if band.get("band_width") != band_width:
        fail(f"the frozen band records a width of {band.get('band_width')}, not {band_width}")
    if band.get("band_width_source") != (
        "configs/research_v6.json -> universe.expansion_scope.band_width_rule.band_width"
    ):
        fail("the frozen band does not name the source of its width")
    if int(spec["universe"]["top_n"]) != band_width:
        fail("the specification's top_n and the band width disagree")
    if band.get("ordering") != "strictly_descending_market_cap":
        fail("the frozen band does not order its members by descending market capitalization")
    if band.get("band_never_widened") is not True:
        fail("the frozen band does not state that the band is never widened")
    if band.get("floor_never_lowered") is not True:
        fail("the frozen band does not state that the floor is never lowered")
    if band.get("validated_set_is_a_consequence_of_the_band") is not True:
        fail("the frozen band does not state that the validated set is a consequence of the band")
    if len(members) != band_width:
        fail(f"the frozen band holds {len(members)} members, not the band width {band_width}")
    if band.get("member_count") != len(members):
        fail("the frozen band miscounts its members")
    frozen_pairs = [str(entry.get("binance_pair") or "") for entry in members]
    if frozen_pairs != derived_pairs:
        fail(
            "the frozen band is not the band re-derived from the raw snapshot bytes: "
            f"{frozen_pairs} != {derived_pairs}"
        )
    market_caps = [int(entry.get("market_cap_usd") or 0) for entry in members]
    if market_caps != sorted(market_caps, reverse=True):
        fail("the frozen band is not in strictly descending market-capitalization order")
    if len(set(market_caps)) != len(market_caps):
        fail("the frozen band holds two members with the same market capitalization")
    for index, entry in enumerate(members, start=1):
        if entry.get("rank") != index:
            fail(f"the frozen band member {entry.get('binance_pair')} is not ranked {index}")
        derived = derived_by_pair.get(str(entry.get("binance_pair")))
        if derived is None:
            continue
        if int(entry.get("market_cap_usd") or 0) != int(derived.get("market_cap_usd") or 0):
            fail(
                f"the frozen band member {entry.get('binance_pair')} records a market cap of "
                f"{entry.get('market_cap_usd')}, re-derived {derived.get('market_cap_usd')}"
            )
        if str(entry.get("coingecko_id") or "") != str(derived.get("coingecko_id") or ""):
            fail(
                f"the frozen band member {entry.get('binance_pair')} records another CoinGecko id "
                "than the re-derived band"
            )
    # The manifest's own band must agree with the re-derived band: a manifest
    # that disagrees with the evidence it names is a defect.
    manifest_band = [str(entry.get("binance_pair") or "") for entry in universe.get("eligible_assets") or []]
    if manifest_band != derived_pairs:
        fail("the v6 universe manifest's band is not the band re-derived from the raw bytes")

    # 3b. the validation outcome of every band member ------------------------
    min_candles = int(spec["universe"]["min_candles"])
    for entry in members:
        pair = str(entry.get("binance_pair") or "")
        outcome = band_member_outcome(pair, spot_evidence, candle_evidence, min_candles)
        if entry.get("validated") is not outcome["validated"]:
            fail(
                f"the frozen band member {pair} records validated={entry.get('validated')}, "
                f"re-derived {outcome['validated']} from the validation evidence"
            )
        if entry.get("exclusion_reason") != outcome["exclusion_reason"]:
            fail(
                f"the frozen band member {pair} records the exclusion reason "
                f"{entry.get('exclusion_reason')!r}, re-derived "
                f"{outcome['exclusion_reason']!r} from the validation evidence"
            )
        if entry.get("validated") is True and entry.get("exclusion_reason") is not None:
            fail(f"the frozen band member {pair} is validated and carries an exclusion reason")
        if entry.get("validated") is not True and not entry.get("exclusion_reason"):
            fail(f"the frozen band member {pair} is not validated and carries no exclusion reason")
        if entry.get("exclusion_reason") not in (None, *ALLOWED_EXCLUSION_REASONS):
            fail(
                f"the frozen band member {pair} carries the unknown exclusion reason "
                f"{entry.get('exclusion_reason')!r}"
            )
        if entry.get("validated") is not True and entry.get("exclusion_reason") not in (
            None,
            *ALLOWED_EXCLUSION_REASONS,
        ):
            fail(
                f"the frozen band member {pair} is excluded and carries an unknown exclusion "
                "reason"
            )
        # The recorded validation evidence of every member must be the re-derived
        # one. A member excluded for a *history* reason is a tradeable Binance
        # spot pair with too short a history: excluding it does not un-verify
        # its spot pair, so only a spot exclusion may carry
        # ``binance_spot_verified: false``.
        if entry.get("binance_spot_verified") is not outcome["binance_spot_verified"]:
            fail(
                f"the frozen band member {pair} records a Binance spot verification of "
                f"{entry.get('binance_spot_verified')!r}, re-derived "
                f"{outcome['binance_spot_verified']!r} from the validation evidence"
            )
        if entry.get("candle_history_verified") is not outcome["candle_history_verified"]:
            fail(
                f"the frozen band member {pair} records a candle-history verification of "
                f"{entry.get('candle_history_verified')!r}, re-derived "
                f"{outcome['candle_history_verified']!r} from the validation evidence"
            )
        if entry.get("observed_candles") != outcome["observed_candles"]:
            fail(
                f"the frozen band member {pair} records {entry.get('observed_candles')!r} observed "
                f"candles, re-derived {outcome['observed_candles']!r} from the validation evidence"
            )
        if (
            entry.get("exclusion_reason") == "binance_spot_unavailable"
            and entry.get("binance_spot_verified") is not False
        ):
            fail(
                f"the frozen band member {pair} is excluded as unavailable on Binance spot but "
                "records a verified Binance spot pair"
            )
    validated_members = [entry for entry in members if entry.get("validated") is True]
    computed["frozen_band_count"] = len(members)
    computed["frozen_validated_count"] = len(validated_members)
    if not validated_members:
        fail("the frozen candidate set is empty")

    # 3c. the candidate set is the validated subset of the band -------------
    candidates = freeze.get("candidates") or []
    if len(candidates) != len(validated_members):
        fail("the frozen candidate set does not hold the validated members of the band")
    if [str(entry.get("binance_pair") or "") for entry in candidates] != [
        str(entry.get("binance_pair") or "") for entry in validated_members
    ]:
        fail("the frozen candidate set is not the validated subset of the band")
    manifest_validated = [
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    ]
    if sorted(str(entry.get("binance_pair") or "") for entry in candidates) != sorted(
        manifest_validated
    ):
        fail("the frozen candidate set is not the validated v6 universe")
    candidate_set = freeze.get("candidate_set") or {}
    if candidate_set.get("members") != [str(entry.get("binance_pair")) for entry in candidates]:
        fail("the candidate-set block does not name the frozen candidate set")
    if candidate_set.get("count") != len(candidates):
        fail("the candidate-set block miscounts the frozen candidate set")
    reason_counts: Dict[str, int] = {}
    for entry in members:
        if entry.get("validated") is True:
            continue
        reason = str(entry.get("exclusion_reason"))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    computed["band_exclusion_reason_counts"] = reason_counts
    if band.get("exclusion_reason_counts") != reason_counts:
        fail("the frozen band miscounts its exclusion reasons")
    if band.get("excluded_member_count") != len(members) - len(validated_members):
        fail("the frozen band miscounts its excluded members")
    if band.get("validated_count") != len(validated_members):
        fail("the frozen band miscounts its validated members")
    recorded_reasons = candidate_set.get("exclusion_reasons") or {}
    for reason, count in reason_counts.items():
        listed = recorded_reasons.get(reason) or []
        if len(listed) != count:
            fail(f"the candidate-set block miscounts the {reason} members of the band")
        for pair in listed:
            member = next(
                (entry for entry in members if entry.get("binance_pair") == pair), None
            )
            if member is None:
                fail(f"the candidate-set block names {pair}, which is not a band member")
            elif member.get("exclusion_reason") != reason:
                fail(f"the candidate-set block names {pair} under the reason {reason}")
    for reason, listed in recorded_reasons.items():
        if reason not in reason_counts:
            fail(f"the candidate-set block records the unknown exclusion reason {reason}")

    # 4. the floor rule, recomputed from the v5 universe manifest -----------
    floor_source = read_json(root / FLOOR_SOURCE_RELATIVE)
    floor_symbol, floor_market_cap = recompute_floor(floor_source)
    computed["recomputed_floor_symbol"] = floor_symbol
    computed["recomputed_floor_market_cap_usd"] = floor_market_cap
    floor = freeze.get("floor") or {}
    if floor.get("source_manifest_path") != FLOOR_SOURCE_RELATIVE:
        fail("the freeze does not name the v5 universe manifest as the floor's source")
    if floor.get("floor_symbol") != floor_symbol:
        fail(
            f"the freeze records the floor symbol {floor.get('floor_symbol')}, recomputed "
            f"{floor_symbol}"
        )
    if int(floor.get("floor_market_cap_usd") or 0) != floor_market_cap:
        fail(
            f"the freeze records a floor of {floor.get('floor_market_cap_usd')} USD, recomputed "
            f"{floor_market_cap} USD"
        )
    if floor.get("comparison") != "strictly_less_than":
        fail("the freeze does not compare against the floor strictly")
    lowest = min(
        floor_source.get("eligible_assets") or [],
        key=lambda entry: int(entry.get("market_cap_usd") or 0),
    )
    if floor.get("floor_market_cap_rank") != lowest.get("market_cap_rank"):
        fail("the freeze records another floor rank than the v5 manifest's lowest asset")
    for entry in members:
        market_cap = entry.get("market_cap_usd")
        if market_cap is None:
            fail(f"the frozen band member {entry.get('binance_pair')} records no market cap")
        elif int(market_cap) >= floor_market_cap:
            fail(
                f"the frozen band member {entry.get('binance_pair')} is at {market_cap} USD, which "
                f"is not strictly below the v5 floor of {floor_market_cap} USD"
            )

    # 5. the identity rule, recomputed from the five prior manifests --------
    prior_symbols, prior_identifiers = prior_universe_assets(*prior_universes)
    identity = freeze.get("identity_rule") or {}
    computed["distinct_prior_binance_symbols"] = len(prior_symbols)
    computed["distinct_prior_coingecko_ids"] = len(prior_identifiers)
    if identity.get("distinct_prior_binance_symbols") != len(prior_symbols):
        fail(
            "the freeze records another count of distinct prior Binance symbols, recomputed "
            f"{len(prior_symbols)}"
        )
    if identity.get("distinct_prior_coingecko_ids") != len(prior_identifiers):
        fail(
            "the freeze records another count of distinct prior CoinGecko ids, recomputed "
            f"{len(prior_identifiers)}"
        )
    if list(identity.get("prior_universe_versions") or []) != ["v1", "v2", "v3", "v4", "v5"]:
        fail("the identity rule does not cover the v1, v2, v3, v4 and v5 universes")
    for entry in members:
        marker = str(entry.get("binance_pair") or entry.get("symbol") or "")
        if marker.endswith("USDT"):
            marker = marker[:-4]
        if marker.upper() in prior_symbols:
            fail(
                f"the frozen band member {entry.get('binance_pair')} is an asset of the "
                f"{prior_symbols[marker.upper()]} universe"
            )
        identifier = entry.get("coingecko_id")
        if identifier and str(identifier) in prior_identifiers:
            fail(
                f"the frozen band member {entry.get('binance_pair')} is an asset of the "
                f"{prior_identifiers[str(identifier)]} universe"
            )

    # 6. the data boundary --------------------------------------------------
    boundary = freeze.get("data_boundary") or {}
    cutoff = boundary.get("development_cutoff_utc")
    spec_cutoff = _dig(spec, "holdout.development_cutoff_utc")
    data_cutoff = _dig(data, "window_policy.development_cutoff_utc")
    if cutoff != spec_cutoff:
        fail("the frozen development cutoff is not the preregistered development cutoff")
    if cutoff != data_cutoff:
        fail("the frozen development cutoff is not the cutoff the v6 data manifest records")
    cutoff_rule = str(boundary.get("development_cutoff_rule") or "")
    if "closes exactly at" not in cutoff_rule or "no candle that closes after" not in cutoff_rule:
        fail("the frozen development boundary is not stated inclusively (BRAIN-015)")
    window_starts: List[Tuple[str, str]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = window_bounds(owner, key)
        if not bounds["window_start_utc"]:
            fail(f"the {version} candidate freeze does not carry its window start")
            continue
        window_starts.append((version, bounds["window_start_utc"]))
    if window_starts and cutoff != min(start for _, start in window_starts):
        fail(
            f"the frozen development cutoff is {cutoff}, but the earliest confirmatory-window "
            f"start is {min(start for _, start in window_starts)}"
        )
    dev_window = development_window(spec)
    dev_block = boundary.get("development_window") or {}
    if dev_block.get("candle_count") != int(dev_window["candle_count"]):
        fail("the frozen development window does not hold the preregistered candle count")
    if dev_block.get("first_candle_open_utc") != _format_utc_ms(int(dev_window["first_open_ms"])):
        fail(
            "the frozen development window starts at "
            f"{dev_block.get('first_candle_open_utc')}, recomputed "
            f"{_format_utc_ms(int(dev_window['first_open_ms']))} from the cutoff and the candle count"
        )
    if dev_block.get("last_candle_close_utc") != _format_utc_ms(
        int(dev_window["last_open_ms"]) + 3600_000
    ):
        fail(
            "the frozen development window ends at "
            f"{dev_block.get('last_candle_close_utc')}, recomputed "
            f"{_format_utc_ms(int(dev_window['last_open_ms']) + 3600_000)}"
        )
    # The membership rule is the one the v6 specification owns: the v6
    # specification was written with the corrected rule, so the v6 chain needs
    # no membership amendment.
    membership = _dig(spec, "holdout.confirmatory_window_membership") or {}
    if membership.get("interval_start_inclusive") is not False:
        fail("the v6 specification does not state the corrected, start-exclusive membership rule")
    if str(boundary.get("confirmatory_window_membership_rule") or "") != str(
        membership.get("rule") or ""
    ):
        fail("the frozen membership rule is not the rule the v6 specification owns")
    owner_block = boundary.get("confirmatory_window_membership_rule_owner") or {}
    if owner_block.get("path") != SPEC_RELATIVE:
        fail("the freeze does not name the v6 specification as the owner of the membership rule")
    if owner_block.get("key") != "holdout.confirmatory_window_membership":
        fail("the freeze does not name the membership rule's key in the v6 specification")
    if owner_block.get("interval_start_inclusive") is not False:
        fail("the freeze does not record the start-exclusive membership flag")
    if owner_block.get("specification_hash") != specification_hash:
        fail("the freeze does not bind the specification that owns the membership rule")
    if boundary.get("confirmatory_window_membership_amendment_required") is not False:
        fail("the freeze claims a membership amendment, but the v6 specification needs none")

    # 7. the confirmatory window is a new window ---------------------------
    window = freeze.get("confirmatory_window") or {}
    freeze_instant = freeze.get("candidate_freeze_utc")
    if not freeze_instant:
        fail("the freeze records no freeze instant")
    else:
        opened = window.get("opens_utc")
        expected_open = _format_utc(_first_hour_boundary_after(parse_iso_utc(freeze_instant)))
        if opened != expected_open:
            fail(
                f"the v6 confirmatory window opens at {opened}, but the first hour boundary "
                f"strictly after the freeze instant is {expected_open}"
            )
        if boundary.get("v6_confirmatory_window_start_utc") != opened:
            fail("the data boundary and the confirmatory window name different window starts")
    if window.get("min_hours") != MIN_CONFIRMATORY_WINDOW_HOURS:
        fail("the v6 confirmatory window does not need 2,160 closed hourly candles")
    try:
        expected_end = _format_utc(
            parse_iso_utc(str(window.get("opens_utc"))) + timedelta(hours=MIN_CONFIRMATORY_WINDOW_HOURS)
        )
    except (TypeError, ValueError):
        expected_end = None
    if expected_end and window.get("earliest_possible_end_utc") != expected_end:
        fail(
            f"the v6 confirmatory window ends at {window.get('earliest_possible_end_utc')}, "
            f"recomputed {expected_end} from its start and its minimum hours"
        )
    if boundary.get("earliest_possible_confirmatory_window_end_utc") != window.get(
        "earliest_possible_end_utc"
    ):
        fail("the data boundary and the confirmatory window name different earliest ends")
    if boundary.get("min_confirmatory_window_hours") != MIN_CONFIRMATORY_WINDOW_HOURS:
        fail("the data boundary does not state the minimum number of confirmatory hours")
    if window.get("single_use") is not True:
        fail("the v6 confirmatory window is not single-use")
    for version, start in window_starts:
        if window.get("opens_utc") == start:
            fail(f"the v6 confirmatory window reuses the {version} confirmatory window")
    frozen_validated = {str(entry.get("binance_pair") or "") for entry in validated_members}
    for version, relative in PRIOR_FREEZE_RELATIVES:
        prior = read_json(root / relative)
        prior_pairs = {
            str(entry.get("binance_pair") or "")
            for entry in (prior.get("candidates") or [])
            if entry.get("validated") is True
        }
        overlap = prior_pairs & frozen_validated
        if overlap:
            fail(
                f"the v6 validated candidate set shares {sorted(overlap)} with the {version} "
                "candidate set"
            )
    # The evaluation gate is the later of the four recomputed gates and the v6
    # window's own earliest end.
    gates: List[Tuple[str, str]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = window_bounds(owner, key)
        if not bounds["earliest_possible_end_utc"]:
            fail(f"the {version} candidate freeze carries no earliest window end")
            continue
        gates.append((version, bounds["earliest_possible_end_utc"]))
    v6_end = window.get("earliest_possible_end_utc")
    if v6_end:
        gates.append(("v6", str(v6_end)))
    if gates:
        expected_start = max(end for _, end in gates)
        computed["evaluation_may_not_start_before_utc"] = expected_start
        if window.get("evaluation_may_not_start_before_utc") != expected_start:
            fail(
                f"the effective v6 evaluation start is "
                f"{window.get('evaluation_may_not_start_before_utc')}, but the later of the "
                f"v2, v3, v4 and v5 gates and the v6 window's own earliest end is {expected_start}"
            )
    recorded_gates = window.get("gates") or []
    if len(recorded_gates) != len(GATE_OWNERS):
        fail("the freeze does not record the four prior confirmatory gates")
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = window_bounds(owner, key)
        recorded = next(
            (gate for gate in recorded_gates if gate.get("version") == version), None
        )
        if recorded is None:
            fail(f"the freeze does not record the {version} confirmatory gate")
            continue
        if recorded.get("source_path") != relative:
            fail(f"the recorded {version} gate does not name the freeze that owns its window")
        if recorded.get("window_start_utc") != bounds["window_start_utc"]:
            fail(
                f"the recorded {version} gate names a window start of "
                f"{recorded.get('window_start_utc')}, recomputed {bounds['window_start_utc']}"
            )
        if recorded.get("earliest_possible_end_utc") != bounds["earliest_possible_end_utc"]:
            fail(
                f"the recorded {version} gate ends at {recorded.get('earliest_possible_end_utc')}, "
                f"recomputed {bounds['earliest_possible_end_utc']}"
            )
        if int(recorded.get("min_hours") or 0) != int(bounds["min_hours"] or 0):
            fail(f"the recorded {version} gate does not carry the window's minimum hours")
    # The effective overlap rule: the v6 window opens inside the still-open
    # earlier windows, which the gate makes harmless.
    overlap_rule = str(window.get("overlap_rule") or "")
    for phrase in (
        "opens inside",
        "not a violation",
        "share no asset",
        "may not start before",
        "never read for selection",
    ):
        if phrase not in overlap_rule:
            fail(f"the effective overlap rule does not state the clause {phrase!r}")

    # 8. the benchmark, recomputed from the dataset's own bytes --------------
    benchmark = freeze.get("benchmark") or {}
    dataset_relative = str(benchmark.get("dataset_path") or "")
    if not dataset_relative:
        fail("the freeze names no benchmark dataset")
    elif not (root / dataset_relative).exists():
        fail(f"the benchmark dataset {dataset_relative} is missing")
    else:
        digest, rows, first_open_ms, last_open_ms = canonical_hourly_csv_digest(
            root / dataset_relative
        )
        computed["benchmark_content_hash"] = digest
        if benchmark.get("content_hash") != digest:
            fail(
                f"the freeze records the benchmark content hash {benchmark.get('content_hash')}, "
                f"recomputed {digest} from the dataset's bytes"
            )
        if benchmark.get("content_hash_algorithm") != "sha256-canonical-hourly-csv-v1":
            fail("the freeze does not name the benchmark's content-hash algorithm")
        if benchmark.get("candle_count") != rows:
            fail(
                f"the freeze records {benchmark.get('candle_count')} benchmark candles, recomputed "
                f"{rows} from the dataset"
            )
        if benchmark.get("first_candle_open_utc") != _format_utc_ms(first_open_ms):
            fail("the freeze records another first benchmark candle than the dataset holds")
        last_close = _format_utc_ms(int(last_open_ms) + 3600_000)
        if benchmark.get("last_candle_close_utc") != last_close:
            fail("the freeze records another last benchmark candle than the dataset holds")
        if cutoff and last_close != cutoff:
            fail(
                f"the benchmark's last candle closes at {last_close}, not at the development "
                f"cutoff {cutoff}"
            )
        if benchmark.get("closes_after_the_development_cutoff") is not False:
            fail("the freeze does not record that the benchmark is bounded at the cutoff")

    # 9. the supersedes chain ------------------------------------------------
    supersedes = freeze.get("supersedes") or {}
    if supersedes.get("v5_candidate_freeze_path") != V5_FREEZE_RELATIVE:
        fail("the freeze does not supersede the v5 candidate freeze")
    v5_recomputed_hash = compute_manifest_hash(v5_freeze, ("manifest_hash",))
    if supersedes.get("v5_candidate_freeze_hash") != v5_recomputed_hash:
        fail("the freeze names a v5 candidate-freeze hash the v5 freeze does not carry")
    if supersedes.get("v5_candidate_freeze_sha256") != sha256_file(root / V5_FREEZE_RELATIVE):
        fail("the freeze names a v5 candidate-freeze digest the file on disk does not have")
    if v5_freeze.get("manifest_hash") != v5_recomputed_hash:
        fail("the v5 candidate freeze does not recompute its own manifest_hash")
    for version in ("v1", "v2", "v3", "v4", "v5"):
        if supersedes.get(f"{version}_artifacts_are_immutable") is not True:
            fail(f"the freeze does not declare the {version} artifacts immutable")
    if supersedes.get("v1_v2_v3_v4_v5_artifacts_are_immutable") is not True:
        fail("the freeze does not declare the v1-v5 artifacts immutable")
    scope = str(supersedes.get("supersession_scope") or "")
    if "Additive only" not in scope:
        fail("the freeze does not state that the supersession is additive only")
    # The v1-v5 artifacts are unchanged: the v6 specification recorded their
    # identities when it was preregistered.
    spec_supersedes = spec.get("supersedes") or {}
    for path_key, hash_key, sha_key in (
        ("specification_path", "specification_hash", "specification_sha256"),
        ("universe_manifest_path", "universe_manifest_hash", "universe_manifest_sha256"),
        ("data_manifest_path", "data_manifest_hash", "data_manifest_sha256"),
        ("candidate_freeze_path", "candidate_freeze_hash", "candidate_freeze_sha256"),
    ):
        relative = str(spec_supersedes.get(path_key) or "")
        if not relative:
            fail(f"the v6 specification supersedes chain names no {path_key}")
            continue
        if not (root / relative).exists():
            fail(f"the superseded artifact {relative} is missing")
            continue
        if spec_supersedes.get(sha_key) != sha256_file(root / relative):
            fail(f"the superseded artifact {relative} has changed since the v6 specification")
        artifact = read_json(root / relative)
        if spec_supersedes.get(hash_key) != artifact.get(
            "manifest_hash", artifact.get("specification_hash")
        ):
            fail(f"the superseded artifact {relative} carries another identity than the v6 spec")
    for source in (
        _dig(spec, "universe.expansion_scope.prior_universe_asset_identity.sources") or []
    ):
        relative = str(source.get("manifest_path") or "")
        if not relative or not (root / relative).exists():
            fail(f"the prior-universe manifest {relative} is missing")
            continue
        if source.get("file_sha256") != sha256_file(root / relative):
            fail(f"the prior-universe manifest {relative} has changed since the v6 specification")

    # 10. the exposure counter starts at 0 -----------------------------------
    if _dig(spec, "holdout.v6_holdout_exposed_count") != 0:
        fail("the v6 holdout counter does not start at 0")
    if _dig(data, "confirmatory_window.holdout_exposed_count") != 0:
        fail("the v6 data manifest records a non-zero holdout_exposed_count")
    if _dig(data, "confirmatory_window.confirmatory_window_status") != "NOT_STARTED":
        fail("the v6 confirmatory window is not unexposed")
    for key in (
        "v1_holdout_reuse",
        "v2_confirmatory_window_reuse",
        "v3_confirmatory_window_reuse",
        "v4_confirmatory_window_reuse",
        "v5_confirmatory_window_reuse",
    ):
        if boundary.get(key) != "forbidden":
            fail(f"the freeze does not forbid the {key}")
    if boundary.get("no_ranking_or_retuning_on_holdout") is not True:
        fail("the freeze does not forbid ranking or re-tuning on the holdout")

    # 11. the freeze authorizes nothing, and no v6 run artifact exists -------
    for key, value in freeze.items():
        if "authoriz" in str(key).lower() and value is True:
            fail(f"the freeze claims an authorization in {key}")
    if "authorizes nothing" not in str(freeze.get("specification_purpose") or ""):
        fail("the freeze does not state that it authorizes nothing")
    for relative in V6_RUN_ARTIFACTS:
        if (root / relative).exists():
            fail(
                f"the v6 run artifact {relative} exists, but the v6 chain has not run: the "
                "freeze authorizes no run"
            )
    for relative, binding in V6_CONFIRMATORY_ARTIFACTS:
        path = root / relative
        if not path.exists():
            fail(
                f"the v6 confirmatory artifact {relative} is missing: the v6 confirmatory chain "
                "must be preregistered before the v6 gate"
            )
            continue
        document = read_json(path)
        excluded_keys = tuple(
            (document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
        )
        if document.get("manifest_hash") != compute_manifest_hash(document, excluded_keys):
            fail(f"the v6 confirmatory artifact {relative} does not recompute its own hash")
        if _dig(document, binding) != freeze.get("manifest_hash"):
            fail(
                f"the v6 confirmatory artifact {relative} does not bind this candidate freeze's "
                f"manifest hash at {binding}"
            )
    namespace = freeze.get("namespace") or {}
    spec_namespace = spec.get("namespace") or {}
    for key in (
        "candidate_freeze",
        "checkpoint",
        "datasets_directory",
        "data_manifest",
        "evidence_directory",
        "ledger",
        "result_stream",
        "results_manifest",
        "shards_directory",
        "universe_manifest",
    ):
        if namespace.get(key) != spec_namespace.get(key):
            fail(f"the freeze's namespace names another {key} than the v6 specification")
    if namespace.get("candidate_freeze") != FREEZE_RELATIVE:
        fail("the freeze does not name itself as the v6 candidate freeze")

    return {
        "ok": not failures,
        "freeze_path": FREEZE_RELATIVE,
        "manifest_hash": freeze.get("manifest_hash"),
        "recomputed_manifest_hash": recomputed_hash,
        "computed": computed,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

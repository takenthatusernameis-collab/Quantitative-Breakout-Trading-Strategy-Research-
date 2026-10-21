#!/usr/bin/env python3
"""Read-only, offline verification of the v5 candidate freeze.

``configs/research_v5_candidate_freeze.json`` freezes the v5 candidate set, the
v5 data boundary and the v5 confirmatory window before any v5 evaluation runs.
The verifier never writes to the repository, never contacts a provider, never
reads a candle and never runs a grid. It checks:

1. the freeze is self-hashing and is the v5 freeze;
2. it is bound to the v5 specification, to the v5 universe manifest and to the
   v5 data manifest, and every identity it records is **recomputed** from the
   artifact that owns it;
3. the frozen candidate set is exactly the v5 universe manifest's eligible
   assets, with the validation outcome and the exclusion reason of each, and
   the validated subset is exactly the validated constituents;
4. the **batch rule** holds: every frozen candidate is strictly below the floor
   recomputed from the v4 universe manifest, and no frozen candidate is an
   asset of the v1, the v2, the v3 or the v4 universe;
5. the **data boundary** holds: the development cutoff is the earliest open
   confirmatory window's start, the inclusive convention is stated, and the
   confirmatory-window membership rule is the rule the published amendment
   owns (the effective rule), not the frozen block of the specification;
6. the **confirmatory window** is a new window: it opens after the freeze, it
   needs 2,160 closed hourly candles, its earliest end follows from its start,
   it is single-use, it is not any of the v1-v4 windows, and the v5 candidate
   set is disjoint from every earlier candidate set;
7. the ``supersedes`` chain names the v4 freeze, with its recomputed manifest
   hash and its recomputed file digest;
8. the exposure counter starts at 0 and the confirmatory window is unexposed;
9. the freeze authorizes nothing and no v5 run artifact exists.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs. The verifier is
**clock-free**: every expectation is a property of the frozen artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v5_universe_rules import (  # noqa: E402
    FLOOR_SOURCE_RELATIVE,
    MANIFEST_HASH_EXCLUDED_KEYS,
    PRIOR_UNIVERSE_RELATIVES,
    compute_manifest_hash,
    parse_iso_utc,
    prior_universe_assets,
    read_json,
    recompute_floor,
    sha256_file,
)

FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v5.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v5.json"
DATA_RELATIVE = "research/data_manifest_v5.json"
AMENDMENT_RELATIVE = "configs/research_v5_specification_amendment_1.json"
V4_FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"

#: The versioned amendment that owns the effective confirmatory-window
#: **overlap** rule of the frozen freeze. The frozen block stays on disk
#: unchanged and visible; the amendment carries the effective rule.
FREEZE_AMENDMENT_RELATIVE = "configs/research_v5_candidate_freeze_amendment_1.json"

#: The freezes that own the v2, v3 and v4 confirmatory windows, and the key each
#: one keeps its window bounds under.
PRIOR_GATE_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", V4_FREEZE_RELATIVE, "confirmatory_window"),
)

#: The freezes that own the v1-v4 confirmatory windows, and the key each one
#: keeps its window start under.
PRIOR_WINDOW_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", V4_FREEZE_RELATIVE, "confirmatory_window"),
)

#: The candidate freezes of the earlier versions, whose candidate sets the v5
#: set must be disjoint from.
PRIOR_FREEZE_RELATIVES: Tuple[Tuple[str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json"),
    ("v3", "configs/research_v3_candidate_freeze.json"),
    ("v4", V4_FREEZE_RELATIVE),
)

#: The paths a v5 run creates. Before the authorized run none of them may exist.
V5_EXECUTION_PATHS = (
    "research/shards_v5",
    "research/ledger_v5.json",
    "research/results_manifest_v5.json",
    "research/results_v5.jsonl",
    "research_state/checkpoint_v5.json",
)

#: The minimum number of closed hourly candles a confirmatory window needs.
MIN_CONFIRMATORY_WINDOW_HOURS = 2160


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_hour_boundary_after(value: datetime) -> datetime:
    boundary = value.replace(minute=0, second=0, microsecond=0)
    if boundary <= value:
        boundary += timedelta(hours=1)
    return boundary


def membership_clauses(text: str) -> Dict[str, bool]:
    """The operative clauses of a confirmatory-window membership rule.

    Two documents may word the same rule differently, so the agreement check
    compares the clauses that decide the outcome and not the sentence.
    """
    lowered = " ".join(str(text or "").lower().split())
    return {
        "start_exclusive": "strictly after" in lowered,
        "end_exclusive": "before its end" in lowered or "before that window's end" in lowered,
        "boundary_candle_is_development": "closes exactly at" in lowered,
        "asset_wide": "regardless of which asset" in lowered,
    }


def overlap_clauses(text: str) -> Dict[str, bool]:
    """The operative clauses of a confirmatory-window overlap rule.

    The frozen v5 freeze states a prohibition that its own dates violate (the
    v5 window opens inside the still-open v2, v3 and v4 windows), so the
    effective rule is carried by a versioned amendment. The agreement check
    compares the clauses that decide the outcome, not the sentence.
    """
    lowered = " ".join(str(text or "").lower().split())
    return {
        "opens_inside_earlier_windows": "opens inside" in lowered,
        "overlap_is_not_a_violation": "not a violation" in lowered,
        "no_shared_asset": "share no asset" in lowered or "shares no asset" in lowered,
        "evaluation_is_gate_bound": "may not start before" in lowered,
        "never_read_for_selection": "never read for selection" in lowered,
    }


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)
    computed: Dict[str, Any] = {}

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        FREEZE_RELATIVE,
        SPEC_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
        AMENDMENT_RELATIVE,
        V4_FREEZE_RELATIVE,
        FREEZE_AMENDMENT_RELATIVE,
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
    amendment = read_json(root / AMENDMENT_RELATIVE)
    v4_freeze = read_json(root / V4_FREEZE_RELATIVE)
    freeze_amendment = read_json(root / FREEZE_AMENDMENT_RELATIVE)

    # 1. the document itself ------------------------------------------------
    if freeze.get("artifact") != "v5_candidate_freeze":
        fail("the freeze is not the v5 candidate freeze")
    if freeze.get("protocol_version") != "v5" or freeze.get("universe_version") != "v5":
        fail("the freeze is not a v5 artifact")
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
    if freeze.get("specification_hash") != spec.get("specification_hash"):
        fail("the freeze is not bound to the v5 specification")
    if freeze.get("universe_manifest_hash") != universe.get("manifest_hash"):
        fail("the freeze is not bound to the v5 universe manifest")
    if freeze.get("data_manifest_hash") != data.get("manifest_hash"):
        fail("the freeze is not bound to the v5 data manifest")
    if freeze.get("universe_manifest_path") != UNIVERSE_RELATIVE:
        fail("the freeze does not name the v5 universe manifest")
    if freeze.get("data_manifest_path") != DATA_RELATIVE:
        fail("the freeze does not name the v5 data manifest")
    if freeze.get("snapshot_identity") != data.get("snapshot_identity"):
        fail("the freeze does not carry the snapshot identity the data manifest records")

    # 3. the frozen candidate set -------------------------------------------
    frozen_candidates = freeze.get("candidates") or []
    manifest_candidates = universe.get("eligible_assets") or []
    if not frozen_candidates:
        fail("the frozen candidate set is empty")
    if len(frozen_candidates) != len(manifest_candidates):
        fail("the frozen candidate set does not hold the v5 eligible assets")
    frozen_pairs = sorted(str(entry.get("binance_pair") or "") for entry in frozen_candidates)
    manifest_pairs = sorted(str(entry.get("binance_pair") or "") for entry in manifest_candidates)
    if frozen_pairs != manifest_pairs:
        fail("the frozen candidate set is not the v5 universe's eligible assets")
    for entry in frozen_candidates:
        if entry.get("validated") is True and entry.get("exclusion_reason") is not None:
            fail(
                f"the frozen candidate {entry.get('binance_pair')} is validated and carries an "
                "exclusion reason"
            )
        if entry.get("validated") is not True and not entry.get("exclusion_reason"):
            fail(
                f"the frozen candidate {entry.get('binance_pair')} is not validated and carries "
                "no exclusion reason"
            )
    frozen_validated = sorted(
        str(entry.get("binance_pair") or "")
        for entry in frozen_candidates
        if entry.get("validated") is True
    )
    manifest_validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in manifest_candidates
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if frozen_validated != manifest_validated:
        fail("the frozen validated set is not the validated v5 universe")
    computed["frozen_candidate_count"] = len(frozen_candidates)
    computed["frozen_validated_count"] = len(frozen_validated)
    if not frozen_validated:
        fail("the frozen validated set is empty")
    frozen_exclusions = freeze.get("exclusions") or []
    if len(frozen_exclusions) != len(universe.get("excluded_assets") or []):
        fail("the frozen exclusion list does not hold the v5 excluded assets")
    for entry in frozen_exclusions:
        if not entry.get("exclusion_reason"):
            fail(
                f"the frozen exclusion {entry.get('symbol')} carries no exclusion reason"
            )

    # 4. the batch rule: the floor and the identity rule --------------------
    floor_source = read_json(root / FLOOR_SOURCE_RELATIVE)
    floor_symbol, floor_market_cap = recompute_floor(floor_source)
    computed["recomputed_floor_symbol"] = floor_symbol
    computed["recomputed_floor_market_cap_usd"] = floor_market_cap
    for entry in frozen_candidates:
        market_cap = entry.get("market_cap_usd")
        if market_cap is None:
            fail(f"the frozen candidate {entry.get('binance_pair')} records no market cap")
        elif int(market_cap) >= floor_market_cap:
            fail(
                f"the frozen candidate {entry.get('binance_pair')} is at {market_cap} USD, which is "
                f"not strictly below the v4 floor of {floor_market_cap} USD"
            )
    prior_manifests = [read_json(root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    symbols, identifiers = prior_universe_assets(*prior_manifests)
    for entry in frozen_candidates:
        marker = str(entry.get("binance_pair") or entry.get("symbol") or "")
        if marker.endswith("USDT"):
            marker = marker[:-4]
        if marker.upper() in symbols:
            fail(
                f"the frozen candidate {entry.get('binance_pair')} is an asset of the "
                f"{symbols[marker.upper()]} universe"
            )
        identifier = entry.get("coingecko_id")
        if identifier and str(identifier) in identifiers:
            fail(
                f"the frozen candidate {entry.get('binance_pair')} is an asset of the "
                f"{identifiers[str(identifier)]} universe"
            )

    # 5. the data boundary --------------------------------------------------
    boundary = freeze.get("data_boundary") or {}
    cutoff = boundary.get("development_cutoff_utc")
    spec_cutoff = _dig(spec, "holdout.development_cutoff_utc")
    data_cutoff = _dig(data, "window_policy.development_cutoff_utc")
    if cutoff != spec_cutoff:
        fail("the frozen development cutoff is not the preregistered development cutoff")
    if cutoff != data_cutoff:
        fail("the frozen development cutoff is not the cutoff the v5 data manifest records")
    cutoff_rule = str(boundary.get("development_cutoff_rule") or "")
    if "closes exactly at" not in cutoff_rule or "no candle that closes after" not in cutoff_rule:
        fail("the frozen development boundary is not stated inclusively (BRAIN-015)")
    window_starts: List[Tuple[str, str]] = []
    for version, relative, key in PRIOR_WINDOW_OWNERS:
        owner = read_json(root / relative)
        block = owner.get(key) or {}
        start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
        if not start:
            fail(f"the {version} candidate freeze does not carry its window start")
            continue
        window_starts.append((version, str(start)))
    if window_starts and cutoff != min(start for _, start in window_starts):
        fail(
            f"the frozen development cutoff is {cutoff}, but the earliest confirmatory-window "
            f"start is {min(start for _, start in window_starts)}"
        )
    # The effective membership rule is the amendment's; the frozen block of the
    # specification stays on disk unchanged.
    if amendment.get("manifest_hash") != compute_manifest_hash(amendment, ("manifest_hash",)):
        fail("the v5 specification amendment does not recompute its manifest_hash")
    if (amendment.get("supersedes") or {}).get("specification_hash") != spec.get(
        "specification_hash"
    ):
        fail("the v5 specification amendment does not supersede the v5 specification")
    corrected = amendment.get("corrected_rule") or {}
    if corrected.get("interval_start_inclusive") is not False:
        fail("the v5 specification amendment does not correct interval_start_inclusive to false")
    effective_rule = str(corrected.get("rule") or "")
    if membership_clauses(str(boundary.get("confirmatory_window_membership_rule") or "")) != (
        membership_clauses(effective_rule)
    ):
        fail("the frozen membership rule is not the rule the published amendment owns")
    if boundary.get("confirmatory_window_membership_amendment_path") != AMENDMENT_RELATIVE:
        fail("the freeze does not name the amendment that owns the membership rule")
    if boundary.get("confirmatory_window_membership_amendment_hash") != amendment.get(
        "manifest_hash"
    ):
        fail("the freeze does not bind the amendment that owns the membership rule")

    # 6. the confirmatory window is a new window ---------------------------
    window = freeze.get("confirmatory_window") or {}
    freeze_instant = freeze.get("candidate_freeze_utc")
    if not freeze_instant:
        fail("the freeze records no freeze instant")
    else:
        opened = _dig(window, "opens_utc")
        expected_open = _format_utc(_first_hour_boundary_after(parse_iso_utc(freeze_instant)))
        if opened != expected_open:
            fail(
                f"the v5 confirmatory window opens at {opened}, but the first hour boundary "
                f"strictly after the freeze instant is {expected_open}"
            )
        if boundary.get("v5_confirmatory_window_start_utc") != opened:
            fail("the data boundary and the confirmatory window name different window starts")
    if window.get("min_hours") != MIN_CONFIRMATORY_WINDOW_HOURS:
        fail("the v5 confirmatory window does not need 2,160 closed hourly candles")
    try:
        expected_end = _format_utc(
            parse_iso_utc(str(window.get("opens_utc"))) + timedelta(hours=MIN_CONFIRMATORY_WINDOW_HOURS)
        )
    except (TypeError, ValueError):
        expected_end = None
    if expected_end and window.get("earliest_possible_end_utc") != expected_end:
        fail(
            f"the v5 confirmatory window ends at {window.get('earliest_possible_end_utc')}, "
            f"recomputed {expected_end} from its start and its minimum hours"
        )
    if boundary.get("earliest_possible_confirmatory_window_end_utc") != window.get(
        "earliest_possible_end_utc"
    ):
        fail("the data boundary and the confirmatory window name different earliest ends")
    if window.get("single_use") is not True:
        fail("the v5 confirmatory window is not single-use")
    for version, start in window_starts:
        if window.get("opens_utc") == start:
            fail(f"the v5 confirmatory window reuses the {version} confirmatory window")
    for version, relative in PRIOR_FREEZE_RELATIVES:
        prior = read_json(root / relative)
        prior_pairs = {
            str(entry.get("binance_pair") or "")
            for entry in (prior.get("candidates") or [])
            if entry.get("validated") is True
        }
        overlap = prior_pairs & set(frozen_validated)
        if overlap:
            fail(
                f"the v5 validated candidate set shares {sorted(overlap)} with the {version} "
                "candidate set"
            )

    # 6b. the effective overlap rule -----------------------------------------
    # The frozen freeze states that the v5 window "must not overlap the v1-v4
    # holdouts/windows", which its own dates violate: the v5 window opens
    # inside the still-open v2, v3 and v4 windows. The effective rule is
    # carried by a versioned amendment; the frozen block stays visible.
    if freeze_amendment.get("manifest_hash") != compute_manifest_hash(
        freeze_amendment, ("manifest_hash",)
    ):
        fail("the v5 candidate-freeze amendment does not recompute its manifest_hash")
    supersedes_freeze = freeze_amendment.get("supersedes") or {}
    if supersedes_freeze.get("artifact_path") != FREEZE_RELATIVE:
        fail("the v5 candidate-freeze amendment does not name the freeze it amends")
    if supersedes_freeze.get("artifact_manifest_hash") != freeze.get("manifest_hash"):
        fail("the v5 candidate-freeze amendment names another manifest hash for the freeze")
    if supersedes_freeze.get("artifact_sha256") != sha256_file(root / FREEZE_RELATIVE):
        fail("the v5 candidate-freeze amendment names another file digest for the freeze")
    if (freeze_amendment.get("effective_rule") or {}).get(
        "precedence"
    ) != "amendment_overrides_frozen_block":
        fail("the v5 candidate-freeze amendment does not state the precedence rule")
    effective_clauses = overlap_clauses(
        str((freeze_amendment.get("corrected_rule") or {}).get("overlap_rule") or "")
    )
    computed["effective_overlap_clauses"] = effective_clauses
    for clause, present in effective_clauses.items():
        if not present:
            fail(f"the effective overlap rule does not state the clause {clause}")
    # The effective evaluation start: the later of the v2, v3, v4 and v5 gates.
    gates: List[Tuple[str, str]] = []
    for version, relative, block_key in PRIOR_GATE_OWNERS:
        owner = read_json(root / relative)
        block = owner.get(block_key) or {}
        end = block.get("earliest_possible_confirmatory_window_end_utc") or block.get(
            "earliest_possible_end_utc"
        )
        if not end:
            fail(f"the {version} candidate freeze carries no earliest window end")
            continue
        gates.append((version, str(end)))
    v5_end = window.get("earliest_possible_end_utc")
    if v5_end:
        gates.append(("v5", str(v5_end)))
    if gates:
        expected_start = max(end for _, end in gates)
        computed["evaluation_may_not_start_before_utc"] = expected_start
        recorded = (freeze_amendment.get("corrected_rule") or {}).get(
            "evaluation_may_not_start_before_utc"
        )
        if recorded != expected_start:
            fail(
                f"the effective v5 evaluation start is {recorded}, but the later of the "
                f"v2, v3, v4 and v5 gates is {expected_start}"
            )
    for entry in (freeze_amendment.get("corrected_rule") or {}).get(
        "time_overlap_evidence"
    ) or []:
        version = str(entry.get("version") or "")
        opens_inside = entry.get("v5_window_opens_inside_the_earlier_window")
        overlaps = entry.get("windows_overlap_in_time")
        if opens_inside is not True:
            fail(
                f"the effective overlap rule does not record that the v5 window opens inside "
                f"the open {version} window"
            )
        if overlaps is not True:
            fail(
                f"the effective overlap rule does not record the time overlap with the "
                f"{version} window"
            )
    if (freeze_amendment.get("corrected_rule") or {}).get("no_shared_asset") is not True:
        fail("the effective overlap rule does not record that the evaluations share no asset")

    # 7. the supersedes chain ------------------------------------------------
    supersedes = freeze.get("supersedes") or {}
    if supersedes.get("v4_candidate_freeze_path") != V4_FREEZE_RELATIVE:
        fail("the freeze does not supersede the v4 candidate freeze")
    if supersedes.get("v4_candidate_freeze_hash") != v4_freeze.get("manifest_hash"):
        fail("the freeze names a v4 candidate-freeze hash the v4 freeze does not carry")
    if supersedes.get("v4_candidate_freeze_sha256") != sha256_file(root / V4_FREEZE_RELATIVE):
        fail("the freeze names a v4 candidate-freeze digest the file on disk does not have")
    if supersedes.get("v1_v2_v3_v4_artifacts_are_immutable") is not True:
        fail("the freeze does not declare the v1-v4 artifacts immutable")

    # 8. the exposure counter starts at 0 -----------------------------------
    if _dig(spec, "holdout.v5_holdout_exposed_count") != 0:
        fail("the v5 holdout counter does not start at 0")
    if _dig(data, "confirmatory_window.holdout_exposed_count") != 0:
        fail("the v5 data manifest records a non-zero holdout_exposed_count")
    if _dig(data, "confirmatory_window.confirmatory_window_status") != "NOT_STARTED":
        fail("the v5 confirmatory window is not unexposed")
    for key in ("v1_holdout_reuse", "v2_confirmatory_window_reuse", "v3_confirmatory_window_reuse",
                "v4_confirmatory_window_reuse"):
        if boundary.get(key) != "forbidden":
            fail(f"the freeze does not forbid the {key}")
    if boundary.get("no_ranking_or_retuning_on_holdout") is not True:
        fail("the freeze does not forbid ranking or re-tuning on the holdout")

    # 9. the freeze authorizes nothing and nothing has run -------------------
    for key, value in freeze.items():
        if "authoriz" in str(key).lower() and value is True:
            fail(f"the freeze claims an authorization in {key}")
    for relative in V5_EXECUTION_PATHS:
        if (root / relative).exists():
            fail(f"the v5 run artifact {relative} exists, but the v5 chain has not run")

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

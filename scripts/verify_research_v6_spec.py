#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v6 specification.

The verifier recomputes every identity the specification records from the
artifact that owns it -- the v6 floor from the v5 universe manifest, the
prior-universe identity sets from the five universe manifests, the development
cutoff and the four confirmatory gates from the candidate freezes, the benchmark
boundary from the benchmark datasets' own bytes, the code identities from the
source tree, and the ``supersedes`` chain from the v5 artifacts themselves.  A
recorded value that no artifact produces is a failure, never a value to be
trusted (BRAIN-018's lesson).

It is deliberately clock-free: every expectation is a property of the frozen
artifacts, so the verifier gives the same answer on any checkout and at any
time.
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

SPEC_V6_RELATIVE = "configs/research_v6.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"

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
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The window-owning freezes that state the development-data rule the v6
#: membership rule must be consistent with.
MEMBERSHIP_SOURCE_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary.development_data_rule"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary.development_data_rule"),
)

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOTS = (
    "src/v2_campaign",
    "src/v2_confirmatory",
    "src/v3_campaign",
    "src/v3_confirmatory",
    "src/v4_campaign",
    "src/v5_campaign",
)

#: The v1-v5 paths a v6 artifact must never collide with.
FOREIGN_NAMESPACES = (
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/universe_manifest_v4.json",
    "research/universe_manifest_v5.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/data_manifest_v3.json",
    "research/data_manifest_v4.json",
    "research/data_manifest_v5.json",
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v3.json",
    "configs/research_v4.json",
    "configs/research_v5.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v4_candidate_freeze.json",
    "configs/research_v5_candidate_freeze.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/ledger_v4.json",
    "research/ledger_v5.json",
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
    "research/results_manifest_v4.json",
    "research/results_manifest_v5.json",
    "research_state/checkpoint.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
    "research_state/checkpoint_v5.json",
)

HOLDOUT_INDEX_PATHS = (
    "research/data/holdout/holdout_index.json",
    "research/data/holdout_v2/holdout_index.json",
    "research/data/holdout_v3/holdout_index.json",
    "research/data/holdout_v4/holdout_index.json",
    "research/data/holdout_v5/holdout_index.json",
    "research/data/holdout_v6/holdout_index.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_specification_hash(spec: Dict[str, Any]) -> str:
    body = {key: value for key, value in spec.items() if key != "specification_hash"}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(root: Path) -> Optional[str]:
    """The portable identity of the ``*.py`` tree under ``root`` (BRAIN-009)."""
    base = Path(root)
    if not base.exists():
        return None
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def base_symbol(marker: str) -> str:
    text = str(marker or "").strip()
    if text.endswith("USDT"):
        return text[: -len("USDT")]
    return text


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def dataset_last_candle_open_ms(path: Path) -> Optional[int]:
    """The open timestamp of the last candle of a canonical hourly CSV dataset."""
    last = ""
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                last = stripped
    if not last:
        return None
    try:
        return int(last.split(",", 1)[0])
    except ValueError:
        return None


def _grid_combinations(grid: Dict[str, Any]) -> int:
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)
    return total


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    computed: Dict[str, Any] = {}

    def fail(message: str) -> None:
        failures.append(message)

    spec = _load_json(repo_root / SPEC_V6_RELATIVE)
    if spec is None:
        return {
            "ok": False,
            "spec_path": SPEC_V6_RELATIVE,
            "failures": [f"the v6 specification is missing or unreadable: {SPEC_V6_RELATIVE}"],
        }

    # 1. the document itself ------------------------------------------------
    if spec.get("protocol_version") != "v6" or spec.get("universe_version") != "v6":
        fail("the specification is not the v6 protocol/universe version")
    if spec.get("specification_status") != "PREREGISTERED_SPECIFICATION_ONLY":
        fail("the specification status is not PREREGISTERED_SPECIFICATION_ONLY")
    declared = spec.get("specification_hash")
    recomputed = compute_specification_hash(spec)
    computed["declared_specification_hash"] = declared
    computed["recomputed_specification_hash"] = recomputed
    if declared != recomputed:
        fail(f"specification_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the inherited blocks are the v1 blocks ------------------------------
    spec_v1 = _load_json(repo_root / SPEC_V1_RELATIVE) or {}
    spec_v2 = _load_json(repo_root / SPEC_V2_RELATIVE) or {}
    for block in INHERITED_BLOCKS:
        if block not in spec:
            fail(f"the v6 specification is missing the inherited block {block}")
        elif spec[block] != spec_v1.get(block):
            fail(f"inherited block {block} differs from v1")
    if "data" in spec and spec.get("data") != spec_v2.get("data"):
        fail("the inherited data block differs from v2")
    grid = spec.get("strategy_grid", {})
    if grid.get("total_combinations") != 2304:
        fail("strategy_grid.total_combinations is not 2304")
    elif _grid_combinations(grid) != 2304:
        fail("strategy_grid dimensions do not multiply to total_combinations")
    inheritance = spec.get("inheritance", {})
    for block in list(inheritance.get("inherited_unchanged_blocks") or []):
        if block not in INHERITED_BLOCKS:
            fail(f"inheritance claims {block} is inherited from v1, but it is not a v1 block")
    if "universe" in (inheritance.get("inherited_unchanged_blocks") or []):
        fail("the universe block must not be claimed as inherited unchanged from v1")

    # 3. the v6 floor, recomputed from the v5 universe manifest -------------
    scope = spec.get("universe", {}).get("expansion_scope", {})
    floor = scope.get("prior_universe_floor", {})
    manifest_v5 = _load_json(repo_root / "research" / "universe_manifest_v5.json")
    if manifest_v5 is None:
        fail("the v5 universe manifest is missing, so the v6 floor cannot be recomputed")
    else:
        assets = manifest_v5.get("eligible_assets") or []
        if not assets:
            fail("the v5 universe manifest carries no eligible assets")
        else:
            lowest = min(
                assets, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol")))
            )
            computed["recomputed_floor_market_cap_usd"] = int(lowest.get("market_cap_usd") or 0)
            computed["recomputed_floor_symbol"] = lowest.get("symbol")
            if floor.get("source_manifest_path") != "research/universe_manifest_v5.json":
                fail("the v6 floor does not name the v5 universe manifest as its source")
            if floor.get("source_manifest_hash") != manifest_v5.get("manifest_hash"):
                fail("the v6 floor names a source manifest hash that the v5 manifest does not carry")
            recorded_sha = floor.get("source_manifest_sha256")
            actual_sha = sha256_file(repo_root / "research" / "universe_manifest_v5.json")
            if recorded_sha != actual_sha:
                fail("the v6 floor's source manifest sha256 does not match the file on disk")
            if floor.get("floor_market_cap_usd") != int(lowest.get("market_cap_usd") or 0):
                fail(
                    f"the v6 floor is {floor.get('floor_market_cap_usd')}, but the minimum "
                    f"market_cap_usd over the v5 eligible assets is {lowest.get('market_cap_usd')}"
                )
            if floor.get("floor_symbol") != lowest.get("symbol"):
                fail(
                    f"the v6 floor names {floor.get('floor_symbol')}, but the lowest v5 eligible "
                    f"asset is {lowest.get('symbol')}"
                )
            if floor.get("floor_market_cap_rank") != lowest.get("market_cap_rank"):
                fail("the v6 floor's market_cap_rank does not match the lowest v5 eligible asset")
        if floor.get("comparison") != "strictly_less_than":
            fail("the v6 floor comparison is not strictly_less_than")
        validated = [entry for entry in (manifest_v5.get("eligible_assets") or []) if entry.get("validated")]
        if validated:
            lowest_validated = min(
                validated, key=lambda entry: (int(entry.get("market_cap_usd") or 0), str(entry.get("symbol")))
            )
            recorded = floor.get("validated_set_floor", {})
            if recorded.get("market_cap_usd") != int(lowest_validated.get("market_cap_usd") or 0):
                fail("the recorded validated-set floor does not match the v5 manifest")
            if recorded.get("symbol") != lowest_validated.get("symbol"):
                fail("the recorded validated-set floor names a different asset than the v5 manifest")

    # 4. the prior-universe identity rule -----------------------------------
    identity = scope.get("prior_universe_asset_identity", {})
    sources = identity.get("sources") or []
    if [source.get("universe_version") for source in sources] != [v for v, _ in PRIOR_UNIVERSE_MANIFESTS]:
        fail("the prior-universe identity rule does not name exactly the v1, v2, v3, v4 and v5 universes")
    symbols = set()
    coingecko_ids = set()
    for source in sources:
        version = source.get("universe_version")
        relative = source.get("manifest_path")
        expected = dict(PRIOR_UNIVERSE_MANIFESTS).get(version)
        if expected is None:
            continue
        if relative != expected:
            fail(f"the identity source {version} names {relative}, not {expected}")
            continue
        manifest = _load_json(repo_root / relative)
        if manifest is None:
            fail(f"the identity source manifest {relative} is missing or unreadable")
            continue
        if source.get("manifest_hash") != manifest.get("manifest_hash"):
            fail(f"the identity source {version} names a manifest hash the manifest does not carry")
        if source.get("file_sha256") != sha256_file(repo_root / relative):
            fail(f"the identity source {version} names a file sha256 that does not match the file")
        assets = manifest.get("eligible_assets") or []
        if source.get("eligible_asset_count") != len(assets):
            fail(f"the identity source {version} names a wrong eligible-asset count")
        for asset in assets:
            if asset.get("symbol"):
                symbols.add(base_symbol(asset["symbol"]))
            if asset.get("coingecko_id"):
                coingecko_ids.add(asset["coingecko_id"])
    computed["recomputed_distinct_prior_symbols"] = len(symbols)
    computed["recomputed_distinct_prior_coingecko_ids"] = len(coingecko_ids)
    if identity.get("distinct_prior_symbols") != len(symbols):
        fail(
            f"the recorded distinct prior-universe symbol count is "
            f"{identity.get('distinct_prior_symbols')}, recomputed {len(symbols)}"
        )
    if identity.get("distinct_prior_coingecko_ids") != len(coingecko_ids):
        fail(
            f"the recorded distinct prior-universe CoinGecko id count is "
            f"{identity.get('distinct_prior_coingecko_ids')}, recomputed {len(coingecko_ids)}"
        )
    if sorted(identity.get("matched_on") or []) != ["binance_symbol", "coingecko_id"]:
        fail("the identity rule does not match on both the Binance symbol and the CoinGecko id")
    if identity.get("exclusion_reason") != "already_in_prior_universe":
        fail("the identity rule's exclusion reason is not already_in_prior_universe")

    # 5. the band-width rule ------------------------------------------------
    band = scope.get("band_width_rule", {})
    top_n = spec.get("universe", {}).get("top_n")
    if band.get("band_width") != top_n:
        fail(f"the band width is {band.get('band_width')}, but the universe top_n is {top_n}")
    if band.get("band_width") != 20:
        fail("the band width is not 20 names")
    if band.get("ordering") != "strictly_descending_market_cap":
        fail("the band-width rule does not order the batch by descending market capitalization")
    if band.get("validated_set_is_a_consequence") is not True:
        fail("the band-width rule does not state that the validated set is a consequence of the band")
    if not band.get("recompute_rule"):
        fail("the band-width rule states no recompute rule")
    if not band.get("shortfall_rule"):
        fail("the band-width rule states no shortfall rule")
    if "never widened" not in str(band.get("band_never_widened") or ""):
        fail("the band-width rule does not forbid widening the band")

    # 6. the development boundary, recomputed from the four freezes ---------
    windows: List[Dict[str, Any]] = []
    for version, relative, key in CONFIRMATORY_WINDOWS:
        freeze = _load_json(repo_root / relative)
        if freeze is None:
            fail(f"the {version} candidate freeze is missing, so the {version} window is unknown")
            continue
        block = freeze.get(key) or {}
        if key == "data_boundary":
            start = block.get("confirmatory_window_start_utc")
            min_hours = block.get("min_confirmatory_window_hours")
        else:
            start = block.get("opens_utc")
            min_hours = block.get("min_hours")
        if not start or not min_hours:
            fail(f"the {version} candidate freeze does not carry its window start or minimum hours")
            continue
        earliest = format_utc(parse_utc(start) + timedelta(hours=int(min_hours)))
        recorded_end = block.get("earliest_possible_confirmatory_window_end_utc") or block.get(
            "earliest_possible_end_utc"
        )
        if recorded_end and recorded_end != earliest:
            fail(
                f"the {version} freeze records an earliest end of {recorded_end}, recomputed "
                f"{earliest} from its window start and its minimum hours"
            )
        windows.append(
            {
                "version": version,
                "window_start_utc": start,
                "min_hours": int(min_hours),
                "earliest_possible_end_utc": earliest,
                "source_path": relative,
            }
        )
    holdout = spec.get("holdout", {})
    cutoff = holdout.get("development_cutoff_utc")
    computed["recomputed_earliest_window_start"] = min((w["window_start_utc"] for w in windows), default=None)
    if windows and cutoff != min(w["window_start_utc"] for w in windows):
        fail(
            f"the development cutoff is {cutoff}, but the earliest confirmatory-window start is "
            f"{min(w['window_start_utc'] for w in windows)}"
        )
    rule_text = str(holdout.get("development_cutoff_rule") or "")
    if "closes exactly at" not in rule_text or "no candle that closes after" not in rule_text:
        fail("the development boundary is not stated inclusively (BRAIN-015)")
    membership = holdout.get("confirmatory_window_membership", {})
    if "regardless of which asset" not in str(membership.get("rule") or ""):
        fail("the specification does not define confirmatory-window membership asset-wide")
    if membership.get("interval_start_inclusive") is not False:
        fail(
            "the confirmatory-window membership rule is not the corrected one: the v6 "
            "specification must state that a candle closing exactly at a window's start is "
            "development data (configs/research_v5_specification_amendment_1.json)"
        )
    if "strictly after" not in str(membership.get("rule") or ""):
        fail("the confirmatory-window membership rule is not start-exclusive")
    quote = str(membership.get("source_quote") or "")
    if not quote:
        fail("the confirmatory-window membership rule quotes no source rule")
    for version, relative, key in MEMBERSHIP_SOURCE_RULES:
        source = _load_json(repo_root / relative)
        source_rule = _dig(source, key) if source is not None else None
        if not source_rule:
            fail(f"the {version} candidate freeze does not state {key}, so the membership rule's source is unknown")
            continue
        if quote not in str(source_rule):
            fail(f"the membership rule's quote is not a verbatim rule of the {version} candidate freeze")
    window_block = holdout.get("development_window", {})
    if cutoff:
        expected_last_open = int((parse_utc(cutoff) - timedelta(hours=1)).timestamp() * 1000)
        expected_first_open = int(
            (parse_utc(cutoff) - timedelta(hours=int(window_block.get("candle_count") or 0))).timestamp() * 1000
        )
        if window_block.get("last_candle_open_timestamp_ms") != expected_last_open:
            fail("the development window's last candle does not close exactly at the cutoff")
        if window_block.get("first_candle_open_timestamp_ms") != expected_first_open:
            fail("the development window's first candle does not follow from the cutoff and the candle count")
        if window_block.get("candle_count") != 26280:
            fail("the development window does not hold 26,280 hourly candles")
    if holdout.get("v6_holdout_exposed_count") != 0:
        fail("the v6 holdout counter does not start at 0")
    for version in ("v2", "v3", "v4", "v5"):
        if holdout.get(f"{version}_holdout_exposed_count") != 0:
            fail(f"the {version} holdout counter recorded in the specification is not 0")
    if holdout.get("v1_v2_v3_v4_v5_holdout_never_reused_for_selection") is not True:
        fail("the specification does not forbid reusing the v1 to v5 holdouts for selection")

    # 7. the benchmark rule, recomputed from the datasets' own bytes --------
    benchmark = holdout.get("benchmark_rule", {})
    reusable = benchmark.get("reusable_dataset") or {}
    forbidden = benchmark.get("forbidden_dataset") or {}
    for label, block in (("reusable", reusable), ("forbidden", forbidden)):
        relative = block.get("path")
        if not relative:
            fail(f"the benchmark rule names no {label} dataset")
            continue
        path = repo_root / relative
        if not path.exists():
            fail(f"the benchmark {label} dataset {relative} is missing, so its identity is unknown")
            continue
        digest = sha256_file(path)
        computed[f"benchmark_{label}_content_hash"] = digest
        if block.get("content_hash") != digest:
            fail(
                f"the recorded content hash of the benchmark {label} dataset {relative} does not "
                f"match the file's bytes"
            )
        last_open = dataset_last_candle_open_ms(path)
        if last_open is None:
            fail(f"the benchmark {label} dataset {relative} holds no readable candle rows")
            continue
        close_ms = last_open + 3600 * 1000
        if block.get("last_candle_open_timestamp_ms") != last_open:
            fail(f"the recorded last candle of the benchmark {label} dataset does not match the file")
        if cutoff:
            cutoff_ms = int(parse_utc(cutoff).timestamp() * 1000)
            closes_after = close_ms > cutoff_ms
            if label == "reusable":
                if closes_after:
                    fail("the reusable benchmark dataset closes after the development cutoff")
                if block.get("closes_after_the_cutoff") is not False:
                    fail("the reusable benchmark dataset's cutoff flag is not recomputed")
                if close_ms != cutoff_ms:
                    fail("the reusable benchmark dataset does not end exactly at the development cutoff")
            else:
                if not closes_after:
                    fail("the forbidden benchmark dataset does not close after the development cutoff")
                count = (close_ms - cutoff_ms) // 3600000
                computed["benchmark_forbidden_candles_after_cutoff"] = int(count)
                if block.get("candles_closing_after_the_cutoff") != int(count):
                    fail(
                        "the recorded number of candles of the forbidden benchmark dataset that "
                        "close after the development cutoff does not recompute"
                    )
    if not benchmark.get("binding_rule"):
        fail("the benchmark rule does not bind the benchmark by its recomputed content hash")
    if not benchmark.get("boundary_rule"):
        fail("the benchmark rule states no boundary rule")

    # 8. the phase gates ---------------------------------------------------
    gates = spec.get("phase_gates", {}).get("gates") or []
    if [gate.get("version") for gate in gates] != [version for version, _, _ in CONFIRMATORY_WINDOWS]:
        fail("the phase gates do not name the v2, v3, v4 and v5 confirmatory evaluations")
    for gate in gates:
        match = next((w for w in windows if w["version"] == gate.get("version")), None)
        if match is None:
            continue
        if gate.get("window_start_utc") != match["window_start_utc"]:
            fail(f"the {gate.get('version')} gate names a window start the freeze does not carry")
        if gate.get("min_hours") != match["min_hours"]:
            fail(f"the {gate.get('version')} gate names a minimum of hours the freeze does not carry")
        if gate.get("earliest_possible_end_utc") != match["earliest_possible_end_utc"]:
            fail(
                f"the {gate.get('version')} gate ends at {gate.get('earliest_possible_end_utc')}, "
                f"recomputed {match['earliest_possible_end_utc']}"
            )
        if gate.get("evaluation_may_not_start_before") != match["earliest_possible_end_utc"]:
            fail(f"the {gate.get('version')} gate does not forbid an evaluation before its earliest end")
        if gate.get("source_path") != match["source_path"]:
            fail(f"the {gate.get('version')} gate does not name the freeze that owns its window")
    v6_gate = spec.get("phase_gates", {}).get("v6_confirmatory_gate", {})
    if windows:
        latest = max(w["earliest_possible_end_utc"] for w in windows)
        computed["recomputed_latest_existing_gate"] = latest
        if v6_gate.get("earliest_existing_gate_utc") != latest:
            fail(
                f"the v6 gate names {v6_gate.get('earliest_existing_gate_utc')} as the latest "
                f"existing gate, recomputed {latest}"
            )
    if v6_gate.get("v6_window_min_hours") != 2160:
        fail("the v6 gate does not require 2,160 closed hourly candles in its own window")
    if "later of" not in str(v6_gate.get("rule") or ""):
        fail("the v6 gate does not state that it is the later of the four gates and its own window")

    # 9. the code identity --------------------------------------------------
    code_identity = spec.get("code_identity", {})
    hashed_set_digest = canonical_source_digest(repo_root / HASHED_SET_ROOT)
    computed["canonical_hashed_set_digest"] = hashed_set_digest
    if hashed_set_digest is None:
        fail("the hashed source set is missing, so the tree identity cannot be recomputed")
    elif code_identity.get("hashed_set_digest") != hashed_set_digest:
        fail(
            f"the recorded hashed-set canonical digest is {code_identity.get('hashed_set_digest')}, "
            f"recomputed {hashed_set_digest}"
        )
    if code_identity.get("hashed_set_root") != HASHED_SET_ROOT:
        fail("the specification does not name the hashed set src/breakout_research")
    if code_identity.get("ordered_code_hash_is_portable") is not False:
        fail("the specification does not record that the ordered code hash is not portable")
    authorization = _load_json(repo_root / "research_state" / "campaign_authorization.json") or {}
    if code_identity.get("authorized_ordered_code_hash") != authorization.get("code_hash"):
        fail("the recorded authorized ordered code hash is not the value of record in campaign_authorization.json")
    for entry in code_identity.get("untouched_execution_paths") or []:
        root = entry.get("root")
        digest = canonical_source_digest(repo_root / root)
        computed[f"canonical_{root}"] = digest
        if digest is None:
            fail(f"the execution path {root} is missing, so its digest cannot be recomputed")
        elif entry.get("canonical_source_digest") != digest:
            fail(f"the recorded digest of {root} does not match the source tree")
        if entry.get("recorded_canonical_source_digest") != entry.get("canonical_source_digest"):
            fail(f"the recorded value of record for {root} differs from the recomputed digest")
    if sorted(entry.get("root") for entry in code_identity.get("untouched_execution_paths") or []) != sorted(
        EXECUTION_PATH_ROOTS
    ):
        fail("the specification does not name every execution path it claims to leave untouched")

    # 10. the supersedes chain ---------------------------------------------
    supersedes = spec.get("supersedes", {})
    chain = (
        ("specification_path", "specification_hash", "specification_sha256", "configs/research_v5.json"),
        ("universe_manifest_path", "universe_manifest_hash", "universe_manifest_sha256", "research/universe_manifest_v5.json"),
        ("data_manifest_path", "data_manifest_hash", "data_manifest_sha256", "research/data_manifest_v5.json"),
        ("candidate_freeze_path", "candidate_freeze_hash", "candidate_freeze_sha256", "configs/research_v5_candidate_freeze.json"),
        (
            "selected_configurations_manifest_path",
            "selected_configurations_manifest_hash",
            "selected_configurations_manifest_sha256",
            "research/v5_selected_configurations_manifest.json",
        ),
    )
    for path_key, hash_key, sha_key, expected_path in chain:
        relative = supersedes.get(path_key)
        if relative != expected_path:
            fail(f"the supersedes chain names {relative} for {path_key}, not {expected_path}")
            continue
        artifact = _load_json(repo_root / relative)
        if artifact is None:
            fail(f"the superseded artifact {relative} is missing or unreadable")
            continue
        if supersedes.get(hash_key) != artifact.get("manifest_hash") and supersedes.get(hash_key) != artifact.get(
            "specification_hash"
        ):
            fail(f"the supersedes chain names a hash the {relative} does not carry")
        if supersedes.get(sha_key) != sha256_file(repo_root / relative):
            fail(f"the supersedes chain names a file sha256 that {relative} does not have")
    if supersedes.get("protocol_version") != "v5":
        fail("the specification does not supersede the v5 protocol version")
    for version in ("v1", "v2", "v3", "v4", "v5"):
        if supersedes.get(f"{version}_artifacts_are_immutable") is not True:
            fail(f"the specification does not declare the {version} artifacts immutable")

    # 11. the namespace -----------------------------------------------------
    namespace = spec.get("namespace", {})
    narrative_keys = {"rule", "result_stream_durability"}
    v6_paths = [
        str(value)
        for key, value in namespace.items()
        if key not in narrative_keys and isinstance(value, str)
    ]
    for foreign in FOREIGN_NAMESPACES:
        if foreign in v6_paths:
            fail(f"the v6 namespace collides with the frozen path {foreign}")
    for key in (
        "specification",
        "universe_manifest",
        "data_manifest",
        "candidate_freeze",
        "execution_protocol",
        "selection_authorization",
        "confirmatory_protocol",
        "confirmatory_runbook",
        "ledger",
        "results_manifest",
        "checkpoint",
    ):
        if not namespace.get(key):
            fail(f"the v6 namespace does not name its {key}")
    if namespace.get("specification") != SPEC_V6_RELATIVE:
        fail("the v6 namespace does not name this specification as the v6 specification")
    # Nothing in the v6 namespace may exist before the v6 chain has run: the
    # specification authorizes nothing, so a v6 artifact here would be an
    # unauthorized write.
    for relative in sorted(set(v6_paths)):
        if relative == SPEC_V6_RELATIVE:
            continue
        if (repo_root / relative).exists():
            fail(
                f"the v6 artifact {relative} exists, but the v6 specification authorizes "
                f"nothing and no v6 stage has been delivered"
            )

    # 12. the expansion log -------------------------------------------------
    program = spec.get("expansion_program", {})
    log_relative = program.get("append_only_log_path")
    if not log_relative:
        fail("the expansion program does not name an append-only log")
    else:
        log = _load_json(repo_root / log_relative)
        if log is None:
            fail(f"the expansion log {log_relative} is missing or unreadable")
        else:
            if program.get("append_only_log_mode") != log.get("log_mode"):
                fail("the recorded expansion-log mode is not the log's own mode")
            if program.get("append_only_log_entry_rule") != log.get("entry_rule"):
                fail("the recorded expansion-log entry rule is not the log's own entry rule")
            entries = log.get("entries") or []
            for index, entry in enumerate(entries):
                body = {key: value for key, value in entry.items() if key != "entry_hash"}
                if entry.get("entry_hash") != sha256_bytes(canonical(body).encode("utf-8")):
                    fail(f"the expansion log entry {index} does not hash to its recorded entry_hash")
                if index == 0:
                    if entry.get("previous_entry_hash") is not None:
                        fail("the first expansion-log entry has a previous_entry_hash")
                elif entry.get("previous_entry_hash") != entries[index - 1].get("entry_hash"):
                    fail(f"the expansion log entry {index} does not chain onto its predecessor")
            state = program.get("log_state_at_preregistration") or {}
            live_versions = [entry.get("universe_version") for entry in entries]
            computed["expansion_log_versions"] = live_versions
            if state.get("versions_present") != live_versions:
                fail(
                    f"the recorded expansion-log versions are {state.get('versions_present')}, "
                    f"the log holds {live_versions}"
                )
            if state.get("entry_count") != len(entries):
                fail(
                    f"the recorded expansion-log entry count is {state.get('entry_count')}, the "
                    f"log holds {len(entries)}"
                )
            if state.get("missing_entries"):
                fail("the expansion log is missing an entry of a frozen universe version")
            if entries:
                last_hash = entries[-1].get("entry_hash")
                computed["expansion_log_last_entry_hash"] = last_hash
                if program.get("log_entry_previous_hash") != last_hash:
                    fail("the v6 expansion-log entry does not chain onto the last entry of the log")
            pending = " ".join(program.get("pending_log_entries") or [])
            if "v6" not in pending:
                fail("the expansion program does not record the v6 entry")

    # 13. the exposure counters --------------------------------------------
    for version in ("v2", "v3", "v4", "v5"):
        data_manifest = _load_json(repo_root / "research" / f"data_manifest_{version}.json")
        if data_manifest is None:
            fail(f"the v{version} data manifest is missing, so its exposure counter is unknown")
        else:
            counter = (data_manifest.get("confirmatory_window") or {}).get("holdout_exposed_count")
            status = (data_manifest.get("confirmatory_window") or {}).get("confirmatory_window_status")
            if counter != 0:
                fail(f"the {version} holdout_exposed_count is {counter}, not 0")
            if status != "NOT_STARTED":
                fail(f"the {version} confirmatory_window_status is {status}, not NOT_STARTED")
        checkpoint = _load_json(repo_root / "research_state" / f"checkpoint_{version}.json")
        if checkpoint is None:
            fail(f"the v{version} checkpoint is missing, so its exposure counter is unknown")
        else:
            if checkpoint.get("holdout_exposed_count") not in (0, None):
                fail(f"the v{version} checkpoint holdout_exposed_count is not 0")
    for relative in HOLDOUT_INDEX_PATHS:
        if (repo_root / relative).exists():
            fail(f"a holdout index exists at {relative}, but no confirmatory window has been read")

    # 14. the authorization -------------------------------------------------
    authorization_block = spec.get("authorization", {})
    for flag in ("execution_authorized", "campaign_authorized", "selection_authorized", "confirmatory_authorized"):
        if authorization_block.get(flag) is not False:
            fail(f"authorization.{flag} is not false")

    # 15. the null-result path and the depth policy -------------------------
    null_result = spec.get("null_result_path", {})
    if null_result.get("state") != "AWAITING_NEW_CANDIDATES":
        fail("the null-result path does not record AWAITING_NEW_CANDIDATES")
    if (null_result.get("cadence") or {}).get("minimum_interval_between_passes") != "P7D":
        fail("the null-result path does not carry the P7D bounded cadence")
    if len(null_result.get("evidence_required") or []) < 5:
        fail("the null-result path does not record the evidence bundle")
    cases = null_result.get("cases") or {}
    for case in ("depth_limit", "empty_validated_set"):
        block = cases.get(case) or {}
        if not block.get("rule"):
            fail(f"the null-result path does not state the {case} case")
        if block.get("next_pass_scheduled") is not True:
            fail(f"the {case} case does not schedule the next pass")
    if "never a terminal state" not in str(null_result.get("campaign_completion_rule") or ""):
        fail("the null-result path does not state that an empty pass is never a terminal state")
    depth_policy = spec.get("universe", {}).get("depth_policy", {})
    extra = depth_policy.get("bounded_extra_page") or {}
    if extra.get("max_extra_pages") != 1:
        fail("the depth policy does not bound the extra pages to one")
    if (extra.get("cumulative_depth") or 0) != 500:
        fail("the depth policy's extra page does not state the cumulative depth")
    if not depth_policy.get("forbidden"):
        fail("the depth policy states no forbidden retrieval behaviour")

    # 16. the specification smuggles in no asset membership -----------------
    for forbidden_key in ("eligible_assets", "candidates", "frozen_candidate_set", "candidate_batch"):
        if forbidden_key in spec.get("universe", {}):
            fail(f"the v6 specification records asset membership in universe.{forbidden_key}")
    recorded_symbols = {
        floor.get("floor_symbol"),
        (floor.get("validated_set_floor") or {}).get("symbol"),
    }
    text = canonical(spec)
    for symbol in recorded_symbols:
        if symbol and f'"{symbol}"' not in text:
            fail(f"the floor symbol {symbol} is recorded but absent from the document")

    return {
        "ok": not failures,
        "spec_path": SPEC_V6_RELATIVE,
        "declared_specification_hash": declared,
        "recomputed_specification_hash": recomputed,
        "computed": computed,
        "failures": failures,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

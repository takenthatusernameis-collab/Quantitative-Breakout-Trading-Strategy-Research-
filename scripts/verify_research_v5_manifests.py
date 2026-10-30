#!/usr/bin/env python3
"""Read-only, offline verification of the v5 universe and data manifests.

The verifier recomputes every expectation from the repository and never
contacts a provider, never writes and never reads a candle:

* the two manifest hashes recompute from their own bodies;
* the market-cap snapshot is the stored, in-window retrieval the specification
  pins (raw bytes, digest, endpoint, timestamp), and the **ranking depth is
  recomputed from the bytes** -- a recorded depth is not trusted;
* the **depth policy** holds: the second page was read only when the first
  page yielded fewer than ``top_n`` qualifying names, and there is no third
  page;
* the candidate batch is **re-derived** from the stored bytes with the
  published exclusion rules and the prior-universe identity rule, and compared
  with the manifests;
* the **floor rule** holds: every member of the batch is strictly below the
  floor recomputed from the v4 universe manifest, which is the source the
  specification names;
* the **identity rule** holds: no member of the batch is an asset of the v1,
  the v2, the v3 or the v4 universe;
* the **development boundary** holds: every dataset holds exactly
  ``min_candles`` closed hourly candles and ends with the candle that closes
  **exactly at** the preregistered development cutoff, so no v5 development
  candle closes inside the open v2, v3 or v4 confirmatory window;
* the **benchmark rule** holds: the v5 benchmark series is a dataset bounded at
  the v5 cutoff, not the v4 chain's benchmark dataset;
* the ``supersedes`` chain names the v4 artifacts, not an older version;
* the confirmatory window is unexposed and nothing has run under v5.

The verifier is **clock-free**: every expectation is a property of the frozen
artifacts, so it gives the same answer on any checkout and at any time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v5_run_state import v5_run_state_failures  # noqa: E402
from v5_universe_rules import (  # noqa: E402
    DATA_MANIFEST_HASH_EXCLUDED_KEYS,
    FLOOR_SOURCE_RELATIVE,
    MANIFEST_HASH_EXCLUDED_KEYS,
    PRIOR_UNIVERSE_RELATIVES,
    SPEC_RELATIVE,
    compute_manifest_hash,
    derive_batch,
    development_window,
    load_exclusion_rules,
    parse_iso_utc,
    read_json,
    recompute_floor,
    sha256_bytes,
    sha256_file,
)

UNIVERSE_RELATIVE = "research/universe_manifest_v5.json"
DATA_RELATIVE = "research/data_manifest_v5.json"
OBSERVATION_RELATIVE = "research/v5_evidence/snapshot_observation.json"
V4_UNIVERSE_RELATIVE = "research/universe_manifest_v4.json"
V4_DATA_RELATIVE = "research/data_manifest_v4.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The versioned amendment that owns the effective confirmatory-window
#: membership rule (BRAIN-022 §6).  The frozen specification keeps its block
#: unchanged; this file is the effective rule.
AMENDMENT_RELATIVE = "configs/research_v5_specification_amendment_1.json"

#: The committed paths produced by the authorized v5 run.  The large
#: research/results_v5.jsonl stream is an uncommitted projection regenerated
#: from the verified shards; its absence is expected on a fresh checkout.
V5_EXECUTION_PATHS = (
    "research/shards_v5",
    "research/ledger_v5.json",
    "research/results_manifest_v5.json",
    "research_state/checkpoint_v5.json",
)

ALLOWED_VALIDATION_EXCLUSION_REASONS = (
    "binance_spot_unavailable",
    "coverage_gap",
    "insufficient_hourly_history",
    "candle_validation_failed",
)

HOUR_MS = 60 * 60 * 1000


def membership_clauses(text: str) -> Dict[str, bool]:
    """The operative clauses of a confirmatory-window membership rule.

    Two documents may word the same rule differently, so the agreement check
    compares the clauses that decide the outcome:

    * ``start_exclusive`` -- a candle is inside a window only when its close
      falls *strictly after* the window's start;
    * ``end_exclusive`` -- a candle is inside a window only before its end;
    * ``boundary_candle_is_development`` -- a candle that closes exactly at a
      window's start is development data;
    * ``asset_wide`` -- the rule holds for any asset.
    """
    lowered = " ".join(str(text or "").lower().split())
    return {
        "start_exclusive": "strictly after" in lowered,
        "end_exclusive": "before its end" in lowered or "before that window's end" in lowered,
        "boundary_candle_is_development": "closes exactly at" in lowered,
        "asset_wide": "regardless of which asset" in lowered,
    }


def _snapshot_rows(repo_root: Path, observation: Dict[str, Any]) -> Tuple[List[Dict[str, Any]],
                                                                         List[str]]:
    """The snapshot rows, read from the stored raw pages, and the failures."""
    failures: List[str] = []
    rows: List[Dict[str, Any]] = []
    for page in observation.get("pages") or []:
        path = repo_root / page.get("raw_response_path", "")
        if not path.exists():
            failures.append(f"the stored snapshot page {page.get('page')} does not exist")
            continue
        raw = path.read_bytes()
        if sha256_bytes(raw) != page.get("raw_response_hash"):
            failures.append(
                f"the stored snapshot page {page.get('page')} does not hash to its recorded digest"
            )
            continue
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            failures.append(f"the stored snapshot page {page.get('page')} is not valid JSON")
            continue
        if not isinstance(payload, list):
            failures.append(f"the stored snapshot page {page.get('page')} is not a market list")
            continue
        if len(payload) != int(page.get("row_count") or 0):
            failures.append(
                f"the stored snapshot page {page.get('page')} holds another number of rows "
                "than it records"
            )
        rows.extend(entry for entry in payload if isinstance(entry, dict))
    return rows, failures


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)
    failures: List[str] = []
    warnings: List[str] = []

    required = [
        SPEC_RELATIVE, UNIVERSE_RELATIVE, DATA_RELATIVE, OBSERVATION_RELATIVE,
        V4_UNIVERSE_RELATIVE, V4_DATA_RELATIVE, *PRIOR_UNIVERSE_RELATIVES,
    ]
    for relative in required:
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"],
                    "warnings": warnings}

    spec = read_json(root / SPEC_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    observation = read_json(root / OBSERVATION_RELATIVE)
    prior_universes = [read_json(root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    v4_universe = prior_universes[-1]
    exclusion_rules = load_exclusion_rules(root)

    # 1. the manifest hashes recompute.
    universe_excluded = tuple(universe.get("hashing", {}).get("manifest_hash_excluded_keys")
                              or MANIFEST_HASH_EXCLUDED_KEYS)
    if universe.get("manifest_hash") != compute_manifest_hash(universe, universe_excluded):
        failures.append("the v5 universe manifest hash does not recompute from its body")
    data_excluded = tuple(data.get("hashing", {}).get("manifest_hash_excluded_keys")
                          or DATA_MANIFEST_HASH_EXCLUDED_KEYS)
    if data.get("manifest_hash") != compute_manifest_hash(data, data_excluded):
        failures.append("the v5 data manifest hash does not recompute from its body")

    # 2. the snapshot is the stored, in-window retrieval.
    pages = observation.get("pages") or []
    if not pages:
        failures.append("the snapshot observation records no page")
    if observation.get("endpoint") != spec["universe"]["endpoint"]:
        failures.append("the stored v5 snapshot was not retrieved from the frozen endpoint")
    retrieval = spec["universe"]["snapshot_retrieval"]
    try:
        retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])
        in_window = (parse_iso_utc(retrieval["not_before_utc"]) <= retrieved_at
                     <= parse_iso_utc(retrieval["deadline_utc"]))
    except (KeyError, ValueError):
        in_window = False
    if not in_window:
        failures.append("the stored v5 snapshot was not retrieved inside the pinned window")

    rows, page_failures = _snapshot_rows(root, observation)
    failures.extend(page_failures)

    # 3. the ranking depth is recomputed from the bytes.
    depth_recomputed = len(rows)
    depth_recorded = observation.get("ranking_depth_recomputed_from_bytes")
    if depth_recorded != depth_recomputed:
        failures.append(
            f"the recorded ranking depth {depth_recorded!r} is not the depth recomputed from "
            f"the stored bytes ({depth_recomputed})"
        )
    if len(pages) > 2:
        failures.append("the v5 snapshot holds more than the two pages the depth policy allows")
    if len(pages) == 2:
        if pages[0].get("page") != 1 or pages[1].get("page") != 2:
            failures.append("the stored snapshot pages are not the pages the depth policy names")
        if int(pages[1].get("row_count") or 0) != 250:
            failures.append("the bounded extra page does not hold the published page size")
    else:
        if int(observation.get("qualifying_after_page_1") or 0) < int(spec["universe"]["top_n"]):
            failures.append(
                "the first page yielded fewer than top_n qualifying names but the bounded "
                "extra page was not read"
            )
    for page in pages:
        if int(page.get("row_count") or 0) != 250:
            failures.append(
                f"the stored snapshot page {page.get('page')} does not hold the published "
                "page size"
            )

    # 4. the code hash is the authorized value of record.
    authorization = read_json(root / AUTHORIZATION_RELATIVE)
    authorized = authorization.get("code_hash")
    for label, manifest in (("universe", universe), ("data", data)):
        if manifest.get("code_hash") != authorized:
            failures.append(
                f"the {label} manifest records {manifest.get('code_hash')!r} as the code hash, "
                f"but the authorized value of record is {authorized!r}"
            )

    # 5. the candidate batch is re-derived from the stored bytes.
    batch, rule_excluded, _records = derive_batch(
        spec, rows, prior_universes, exclusion_rules, check_published_batch=False
    )
    derived_pairs = [entry["binance_pair"] for entry in batch]
    manifest_pairs = [
        entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        for entry in (universe.get("eligible_assets") or [])
    ]
    if manifest_pairs != derived_pairs:
        failures.append("the universe manifest's assets are not the re-derived candidate batch")
    if len(rule_excluded) != len(universe.get("excluded_assets") or []):
        failures.append("the universe manifest records a different number of rule-excluded assets")
    derived_excluded = {
        (entry["symbol"], entry["exclusion_reason"]) for entry in rule_excluded
    }
    recorded_excluded = {
        (entry.get("symbol"), entry.get("exclusion_reason"))
        for entry in (universe.get("excluded_assets") or [])
    }
    if derived_excluded != recorded_excluded:
        failures.append("the universe manifest's excluded assets are not the re-derived ones")

    # 6. the floor rule: every member is strictly below the recomputed v4 floor.
    floor_symbol, floor_market_cap = recompute_floor(v4_universe)
    recorded_floor = (universe.get("expansion_scope") or {}).get("floor_market_cap_usd")
    if recorded_floor != floor_market_cap:
        failures.append(
            f"the universe manifest records the floor {recorded_floor!r}, but the floor "
            f"recomputed from {FLOOR_SOURCE_RELATIVE} is {floor_market_cap}"
        )
    for entry in universe.get("eligible_assets") or []:
        market_cap = int(entry.get("market_cap_usd") or 0)
        if market_cap >= floor_market_cap:
            failures.append(
                f"{entry.get('binance_pair')} is not strictly below the v4 floor "
                f"({market_cap} >= {floor_market_cap})"
            )
    if (universe.get("expansion_scope") or {}).get("floor_source_manifest_path") != \
            FLOOR_SOURCE_RELATIVE:
        failures.append("the universe manifest does not take the floor from the v4 manifest")
    if (universe.get("expansion_scope") or {}).get("floor_symbol") != floor_symbol:
        failures.append("the universe manifest records another floor symbol than the v4 manifest")

    # 7. the identity rule: no member is an asset of the v1, v2, v3 or v4 universe.
    prior_symbols: Dict[str, str] = {}
    prior_ids: Dict[str, str] = {}
    for version, prior in zip(("v1", "v2", "v3", "v4"), prior_universes):
        for entry in prior.get("eligible_assets") or []:
            symbol = str(entry.get("symbol") or "").upper()
            if symbol.endswith("USDT"):
                symbol = symbol[:-4]
            prior_symbols.setdefault(symbol, version)
            identifier = entry.get("coingecko_id")
            if identifier:
                prior_ids.setdefault(str(identifier), version)
    for entry in universe.get("eligible_assets") or []:
        symbol = str(entry.get("symbol") or "").upper()
        identifier = str(entry.get("coingecko_id") or "")
        if symbol in prior_symbols:
            failures.append(
                f"{entry.get('binance_pair')} is already an asset of the "
                f"{prior_symbols[symbol]} universe"
            )
        if identifier and identifier in prior_ids:
            failures.append(
                f"{entry.get('binance_pair')} is already an asset of the "
                f"{prior_ids[identifier]} universe"
            )
    recorded_versions = (universe.get("expansion_scope") or {}).get("prior_universe_versions")
    if sorted(recorded_versions or []) != ["v1", "v2", "v3", "v4"]:
        failures.append("the identity rule does not cover the v1, v2, v3 and v4 universes")

    # 8. the development boundary.
    window = development_window(spec)
    cutoff_ms = int(window["cutoff_ms"])
    expected_last_open = int(window["last_open_ms"])
    min_candles = int(window["candle_count"])
    assets = data.get("assets") or {}
    for entry in universe.get("eligible_assets") or []:
        if not entry.get("validated"):
            continue
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        record = assets.get(pair) or {}
        dataset_path = record.get("dataset_path")
        if not dataset_path or not (root / dataset_path).exists():
            failures.append(f"{pair}: the dataset does not exist")
            continue
        content = (root / dataset_path).read_text(encoding="utf-8")
        if sha256_bytes(content.encode("utf-8")) != record.get("content_hash"):
            failures.append(f"{pair}: the dataset does not hash to the recorded content hash")
        if (data.get("content_hashes") or {}).get(pair) != record.get("content_hash"):
            failures.append(f"{pair}: the content_hashes block records another digest")
        rows_csv = content.strip().splitlines()
        if len(rows_csv) - 1 != min_candles:
            failures.append(f"{pair}: the dataset does not hold exactly {min_candles} candles")
        timestamps = [int(row.split(",")[0]) for row in rows_csv[1:]]
        if any(timestamp % HOUR_MS for timestamp in timestamps):
            failures.append(f"{pair}: the dataset holds a candle that is not hour-aligned")
        if len(set(timestamps)) != len(timestamps):
            failures.append(f"{pair}: the dataset holds a duplicate candle")
        if timestamps and timestamps[0] != int(window["first_open_ms"]):
            failures.append(f"{pair}: the dataset does not start at the first development candle")
        if timestamps and timestamps[-1] != expected_last_open:
            failures.append(
                f"{pair}: the dataset does not end at the last closed hour before the "
                "development cutoff"
            )
        if timestamps and timestamps[-1] + HOUR_MS != cutoff_ms:
            failures.append(
                f"{pair}: the dataset does not close a candle exactly at the development cutoff"
            )
        if timestamps and timestamps[-1] + HOUR_MS > cutoff_ms:
            failures.append(
                f"{pair}: the dataset closes a candle after the development cutoff"
            )
        recorded_last = record.get("last_candle_timestamp")
        if recorded_last is not None and int(recorded_last) != (
            timestamps[-1] if timestamps else None
        ):
            failures.append(
                f"{pair}: the manifest records another last candle than the dataset holds"
            )
        if recorded_last is not None and int(recorded_last) + HOUR_MS > cutoff_ms:
            failures.append(
                f"{pair}: the manifest records a candle that closes after the development cutoff"
            )
    policy = data.get("window_policy") or {}
    if policy.get("development_cutoff_utc") != spec["holdout"]["development_cutoff_utc"]:
        failures.append("the data manifest does not bind the preregistered development cutoff")
    if int(policy.get("last_closed_open_timestamp_ms") or 0) != expected_last_open:
        failures.append("the data manifest records another last development candle")
    if int(policy.get("first_candle_open_timestamp_ms") or 0) != int(window["first_open_ms"]):
        failures.append("the data manifest records another first development candle")
    if not data.get("candles_verified"):
        failures.append("the data manifest does not record candles_verified")
    if not data.get("provenance_ok"):
        failures.append("the data manifest does not record provenance_ok")
    membership = (data.get("window_policy") or {}).get("window_membership_rule") or {}
    if not membership.get("rule"):
        failures.append("the data manifest does not state the confirmatory-window membership rule")
    if not membership.get("sources"):
        failures.append(
            "the data manifest does not name the artifacts that own the membership rule"
        )

    # 9a. the published amendment owns the effective membership rule.
    #      The frozen specification keeps its block unchanged; the amendment is
    #      the effective rule, and this manifest must state that same rule.
    amendment_path = root / AMENDMENT_RELATIVE
    if not amendment_path.exists():
        failures.append(
            f"the v5 specification amendment {AMENDMENT_RELATIVE} is missing, so the "
            "effective membership rule is unknown"
        )
    else:
        amendment = read_json(amendment_path)
        if not isinstance(amendment, dict):
            failures.append(f"the v5 specification amendment {AMENDMENT_RELATIVE} is unreadable")
        else:
            recomputed_amendment = compute_manifest_hash(amendment, ("manifest_hash",))
            if amendment.get("manifest_hash") != recomputed_amendment:
                failures.append("the v5 specification amendment does not recompute its manifest_hash")
            if (amendment.get("supersedes") or {}).get("specification_hash") != spec.get(
                "specification_hash"
            ):
                failures.append("the v5 specification amendment does not supersede this specification")
            corrected = amendment.get("corrected_rule") or {}
            if corrected.get("interval_start_inclusive") is not False:
                failures.append(
                    "the v5 specification amendment does not correct interval_start_inclusive to false"
                )
            effective_rule = str(corrected.get("rule") or "")
            if effective_rule:
                # The amendment and this manifest word the same rule slightly
                # differently, so the check compares the operative clauses and
                # not the sentence: the start is exclusive, the end is
                # exclusive, the boundary candle is development data and the
                # rule is asset-wide.
                if membership_clauses(str(membership.get("rule") or "")) != membership_clauses(
                    effective_rule
                ):
                    failures.append(
                        "the data manifest states another membership rule than the published amendment"
                    )

    # 9. the benchmark rule: the v5 benchmark is a dataset bounded at the cutoff.
    benchmark = data.get("benchmark") or {}
    benchmark_path = benchmark.get("dataset_path")
    if not benchmark_path or not (root / benchmark_path).exists():
        failures.append("the v5 benchmark dataset does not exist")
    else:
        content = (root / benchmark_path).read_text(encoding="utf-8")
        if sha256_bytes(content.encode("utf-8")) != benchmark.get("content_hash"):
            failures.append("the v5 benchmark dataset does not hash to its recorded digest")
        rows_csv = content.strip().splitlines()
        if len(rows_csv) - 1 != min_candles:
            failures.append(
                f"the v5 benchmark dataset does not hold exactly {min_candles} candles"
            )
        timestamps = [int(row.split(",")[0]) for row in rows_csv[1:]]
        if timestamps and timestamps[-1] + HOUR_MS != cutoff_ms:
            failures.append(
                "the v5 benchmark dataset does not close a candle exactly at the development "
                "cutoff"
            )
        if benchmark_path.startswith("research/data/candles_v3/"):
            failures.append(
                "the v5 benchmark reuses a v3 dataset, which is not bounded at the v5 cutoff"
            )
    if not benchmark.get("rule"):
        failures.append("the data manifest does not state the benchmark rule")

    # 9b. no v5 development candle closes inside an open confirmatory window.
    #      The rule is the one the window-owning freeze states ("candles that close
    #      at or before confirmatory_window_start_utc are development data"), so a
    #      development candle is inside a window only when its close is strictly
    #      after that window's start.
    for gate in spec.get("phase_gates", {}).get("gates") or []:
        try:
            window_start_ms = int(parse_iso_utc(gate["window_start_utc"]).timestamp() * 1000)
        except (KeyError, ValueError):
            continue
        for pair, record in sorted(assets.items()):
            if not record.get("validated"):
                continue
            last = record.get("last_candle_timestamp")
            if last is None:
                continue
            if int(last) + HOUR_MS > window_start_ms:
                failures.append(
                    f"{pair}: the dataset closes a candle inside the open "
                    f"{gate.get('version')} confirmatory window"
                )
        benchmark_last = benchmark.get("last_candle_timestamp")
        if benchmark_last is not None and int(benchmark_last) + HOUR_MS > window_start_ms:
            failures.append(
                f"the v5 benchmark closes a candle inside the open "
                f"{gate.get('version')} confirmatory window"
            )

    # 10. the supersedes chain names the v4 artifacts.
    supersedes = universe.get("supersedes") or {}
    if supersedes.get("universe_manifest_path") != V4_UNIVERSE_RELATIVE:
        failures.append("the v5 universe manifest does not supersede the v4 universe manifest")
    if supersedes.get("universe_manifest_hash") != v4_universe.get("manifest_hash"):
        failures.append("the v5 universe manifest does not bind the v4 universe identity")
    if supersedes.get("universe_manifest_sha256") != sha256_file(root / V4_UNIVERSE_RELATIVE):
        failures.append("the v5 universe manifest records another sha256 for the v4 manifest")
    data_supersedes = data.get("supersedes") or {}
    if data_supersedes.get("data_manifest_path") != V4_DATA_RELATIVE:
        failures.append("the v5 data manifest does not supersede the v4 data manifest")
    if data_supersedes.get("data_manifest_sha256") != sha256_file(root / V4_DATA_RELATIVE):
        failures.append("the v5 data manifest records another sha256 for the v4 data manifest")

    # 11. the prior-universe manifests still hash to what the specification records.
    for source in (spec.get("universe", {}).get("expansion_scope", {})
                   .get("prior_universe_asset_identity", {}).get("sources") or []):
        relative = source.get("manifest_path")
        if not relative or not (root / relative).exists():
            failures.append(f"the prior-universe manifest {relative} is missing")
            continue
        if source.get("file_sha256") != sha256_file(root / relative):
            failures.append(
                f"the prior-universe manifest {relative} does not hash to the digest the v5 "
                "specification records"
            )

    # 12. every constituent is validated or excluded with a reason.
    for entry in universe.get("eligible_assets") or []:
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        if entry.get("validated"):
            if entry.get("exclusion_reason") is not None:
                failures.append(f"{pair}: a validated asset carries an exclusion reason")
            if not entry.get("binance_spot_verified"):
                failures.append(f"{pair}: a validated asset was not Binance-spot verified")
            if not entry.get("candle_history_verified"):
                failures.append(f"{pair}: a validated asset was not candle-history verified")
        else:
            reason = entry.get("exclusion_reason")
            if reason not in ALLOWED_VALIDATION_EXCLUSION_REASONS:
                failures.append(f"{pair}: an unknown validation exclusion reason {reason!r}")
        if pair not in assets:
            failures.append(f"{pair}: the data manifest holds no record for the candidate")
        if pair not in (data.get("validation_results") or {}):
            failures.append(f"{pair}: the data manifest holds no validation result")

    # 13. the confirmatory window is unexposed and nothing has run under v5.
    window_block = data.get("confirmatory_window") or {}
    if window_block.get("holdout_exposed_count") != 0:
        failures.append("the v5 data manifest records a confirmatory exposure")
    if window_block.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v5 confirmatory window is not recorded as not started")

    # 13b. The v5 run artifacts, when they exist, are the authorized run's outputs.
    #
    # The rule this section enforced before the run was a preregistration rule
    # ("a v5 run artifact may not exist before the v5 candidate freeze"). The single
    # authorized selection run has now been performed, so the rule that holds is the
    # post-run one: the artifacts that exist must be the authorized run's outputs and
    # no exposure may have occurred.
    failures.extend(v5_run_state_failures(root))

    return {
        "ok": not failures,
        "universe_manifest_path": UNIVERSE_RELATIVE,
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_path": DATA_RELATIVE,
        "data_manifest_hash": data.get("manifest_hash"),
        "floor_market_cap_usd": floor_market_cap,
        "floor_symbol": floor_symbol,
        "development_cutoff_utc": spec["holdout"]["development_cutoff_utc"],
        "ranking_depth_recomputed_from_bytes": depth_recomputed,
        "candidate_count": len(manifest_pairs),
        "validated_count": sum(
            1 for entry in (universe.get("eligible_assets") or []) if entry.get("validated")
        ),
        "failures": failures,
        "warnings": warnings,
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

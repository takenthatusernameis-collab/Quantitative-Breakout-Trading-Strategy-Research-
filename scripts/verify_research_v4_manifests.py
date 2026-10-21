#!/usr/bin/env python3
"""Read-only, offline verification of the v4 universe and data manifests.

This is the verifier that the effective v4 exclusion amendment names in its
``producer.verify_command``. It recomputes every expectation from the
repository:

* the two manifest hashes recompute from their own bodies;
* the market-cap snapshot is the stored, in-window retrieval the specification
  pins (raw bytes, digest, endpoint, timestamp);
* the candidate batch is **re-derived** from the stored snapshot with the
  published exclusion rules and the effective amendment, and compared with the
  manifests;
* the **floor rule** holds: every member of the batch is strictly below the
  floor recomputed from the v3 universe manifest, which is the source the
  specification names;
* the **identity rule** holds: no member of the batch is an asset of the v1,
  the v2 or the v3 universe;
* the **development cutoff** holds: no validated dataset closes a candle at or
  after the preregistered development cutoff, so no v4 development candle
  closes inside the open v3 confirmatory window;
* the ``supersedes`` chain names the v3 artifacts, not an older version;
* the confirmatory window is unexposed and nothing has run under v4.

The verifier never writes, never fetches and never contacts a provider.
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

from v4_constituent_validation import (  # noqa: E402
    derive_batch,
    load_snapshot,
    parse_iso_utc,
    prior_universe_assets,
    resolve_effective_amendment,
)

SPEC_RELATIVE = "configs/research_v4.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v4.json"
DATA_RELATIVE = "research/data_manifest_v4.json"
SNAPSHOT_RELATIVE = "research/v4_evidence/raw_market_cap_response.json"
OBSERVATION_RELATIVE = "research/v4_evidence/snapshot_observation.json"
V1_UNIVERSE_RELATIVE = "research/universe_manifest.json"
V2_UNIVERSE_RELATIVE = "research/universe_manifest_v2.json"
V3_UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
V3_DATA_RELATIVE = "research/data_manifest_v3.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v1, v2 and v3 artifacts whose bytes must not have changed.
FROZEN_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/universe_manifest_v2.json",
    "research/data_manifest_v2.json",
    "configs/research_v2.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v3.json",
    "configs/research_v3_candidate_freeze.json",
    "research/universe_manifest_v3.json",
    "research/data_manifest_v3.json",
)

#: The paths a v4 execution run creates. Before the authorized run none of
#: them may exist; after it they are the authorized ones.
V4_EXECUTION_PATHS = (
    "research/shards_v4",
    "research/ledger_v4.json",
    "research/results_manifest_v4.json",
    "research/results_v4.jsonl",
    "research_state/checkpoint_v4.json",
)

#: The v4 selection authorization, once it exists.
V4_AUTHORIZATION_RELATIVE = "configs/research_v4_selection_authorization_1.json"

ALLOWED_VALIDATION_EXCLUSION_REASONS = (
    "binance_spot_unavailable",
    "coverage_gap",
    "insufficient_hourly_history",
    "candle_validation_failed",
)

MIN_CANDLES = 26280
HOUR_MS = 3600 * 1000


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = ("manifest_hash",)) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def v4_execution_state_failures(repo_root: Path) -> List[str]:
    """The failures of the v4 execution state.

    The rule that replaced the former "a v4 execution artifact exists" check
    is **state-adaptive** and is never weaker than the state it replaces -- the
    same rule the v3 chain adopted in
    ``scripts/v3_benchmark_amendment_common.py``:

    * while the v4 selection authorization does not exist, no v4 execution
      artifact may exist -- the cascade is then the last word, and a v4
      execution artifact would contradict it;
    * once the authorization exists, the authorized run has been performed: the
      v4 execution artifacts are the authorized ones, the ledger of the run is
      bound to the authorization's manifest hash, reports a completed run and
      records no confirmatory exposure. A v4 execution artifact that is not
      backed by the authorization, or a ledger that is not bound to it, is a
      contradiction of the cascade.
    """
    root = Path(repo_root)
    authorization_path = root / V4_AUTHORIZATION_RELATIVE
    existing = [relative for relative in V4_EXECUTION_PATHS if (root / relative).exists()]
    if not authorization_path.exists():
        return [
            f"a v4 execution artifact exists without the v4 selection authorization: {relative}"
            for relative in existing
        ]
    if not existing:
        return []
    failures: List[str] = []
    ledger_path = root / "research" / "ledger_v4.json"
    if not ledger_path.exists():
        failures.append(
            "a v4 execution artifact exists without the ledger of the authorized run: "
            + ", ".join(existing)
        )
        return failures
    ledger = read_json(ledger_path)
    authorization = read_json(authorization_path)
    if ledger.get("authorization_manifest_hash") != authorization.get("manifest_hash"):
        failures.append("the v4 ledger is not bound to the v4 selection authorization")
    if ledger.get("status") != "COMPLETED":
        failures.append(
            f"the v4 ledger reports the run status {ledger.get('status')!r}, not 'COMPLETED'"
        )
    if int(ledger.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v4 ledger records a confirmatory exposure")
    run = authorization.get("authorized_run") or {}
    if ledger.get("run_id") != run.get("run_id"):
        failures.append("the v4 ledger does not record the authorized run id")
    if ledger.get("campaign_id") != run.get("campaign_id"):
        failures.append("the v4 ledger does not record the authorized campaign id")
    return failures


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []

    required = [
        SPEC_RELATIVE, UNIVERSE_RELATIVE, DATA_RELATIVE, SNAPSHOT_RELATIVE,
        OBSERVATION_RELATIVE, V1_UNIVERSE_RELATIVE, V2_UNIVERSE_RELATIVE,
        V3_UNIVERSE_RELATIVE, V3_DATA_RELATIVE,
    ]
    for relative in required:
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"],
                    "warnings": warnings}

    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)
    observation = read_json(repo_root / OBSERVATION_RELATIVE)
    v1_universe = read_json(repo_root / V1_UNIVERSE_RELATIVE)
    v2_universe = read_json(repo_root / V2_UNIVERSE_RELATIVE)
    v3_universe = read_json(repo_root / V3_UNIVERSE_RELATIVE)
    amendment_path, amendment = resolve_effective_amendment(repo_root)

    # 1. the manifest hashes recompute.
    universe_excluded = tuple(universe.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if universe.get("manifest_hash") != compute_manifest_hash(universe, universe_excluded):
        failures.append("the v4 universe manifest hash does not recompute from its body")
    data_excluded = tuple(data.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if data.get("manifest_hash") != compute_manifest_hash(data, data_excluded):
        failures.append("the v4 data manifest hash does not recompute from its body")

    # 2. the snapshot is the stored, in-window retrieval.
    raw_bytes = (repo_root / SNAPSHOT_RELATIVE).read_bytes()
    if sha256_bytes(raw_bytes) != observation.get("raw_response_hash"):
        failures.append("the stored v4 snapshot does not hash to the recorded digest")
    for label, manifest in (("universe", universe), ("data", data)):
        if (manifest.get("market_cap_source") or {}).get("raw_response_hash") != observation.get(
            "raw_response_hash"
        ):
            failures.append(f"the {label} manifest records a different snapshot digest")
    retrieval = spec["universe"]["snapshot_retrieval"]
    retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])
    if not (parse_iso_utc(retrieval["not_before_utc"]) <= retrieved_at
            <= parse_iso_utc(retrieval["deadline_utc"])):
        failures.append("the stored v4 snapshot was not retrieved inside the pinned window")
    if observation.get("endpoint") != spec["universe"]["endpoint"]:
        failures.append("the stored v4 snapshot was not retrieved from the frozen endpoint")

    # 3. the code hash is the authorized value of record.
    authorization = read_json(repo_root / AUTHORIZATION_RELATIVE)
    authorized = authorization.get("code_hash")
    for label, manifest in (("universe", universe), ("data", data)):
        if manifest.get("code_hash") != authorized:
            failures.append(
                f"the {label} manifest records {manifest.get('code_hash')!r} as the code hash, "
                f"but the authorized value of record is {authorized!r}"
            )

    # 4. the candidate batch is re-derived from the snapshot with the published rules.
    markets = json.loads(raw_bytes.decode("utf-8"))
    batch, rule_excluded, _records = derive_batch(
        spec, amendment, markets, v1_universe, v2_universe, v3_universe
    )
    derived_pairs = [entry["binance_pair"] for entry in batch]
    published_pairs = [
        member.get("binance_pair")
        for member in (amendment.get("derived_candidate_batch", {}).get("members") or [])
    ]
    if derived_pairs != published_pairs:
        failures.append("the re-derived candidate batch does not match the published derived batch")
    manifest_pairs = [
        entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        for entry in (universe.get("eligible_assets") or [])
    ]
    if manifest_pairs != derived_pairs:
        failures.append("the universe manifest's assets are not the re-derived candidate batch")
    if len(rule_excluded) != len(universe.get("excluded_assets") or []):
        failures.append("the universe manifest records a different number of rule-excluded assets")

    # 5. the floor rule: every member is strictly below the recomputed v3 floor.
    floor_entry = min(
        (v3_universe.get("eligible_assets") or []),
        key=lambda entry: int(entry.get("market_cap_usd") or 0),
    )
    floor_market_cap = int(floor_entry.get("market_cap_usd") or 0)
    for entry in universe.get("eligible_assets") or []:
        market_cap = int(entry.get("market_cap_usd") or 0)
        if market_cap >= floor_market_cap:
            failures.append(
                f"{entry.get('binance_pair')} is not strictly below the v3 floor "
                f"({market_cap} >= {floor_market_cap})"
            )
    recorded_floor = (amendment.get("floor") or {}).get("floor_market_cap_usd")
    if recorded_floor != floor_market_cap:
        failures.append("the effective amendment does not publish the recomputed v3 floor")
    if (amendment.get("floor") or {}).get("source_universe_version") != "v3":
        failures.append("the effective amendment does not take the floor from the v3 universe")

    # 6. the identity rule: no member is an asset of the v1, v2 or v3 universe.
    prior_symbols, prior_ids = prior_universe_assets(v1_universe, v2_universe, v3_universe)
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
    prior_versions = set((amendment.get("prior_universe") or {}).get("v3_manifest_path") or "")
    if not prior_versions:
        failures.append("the effective amendment does not name the v3 universe in its identity rule")

    # 7. the development cutoff: no dataset closes a candle inside the v3 window.
    development_cutoff = spec["holdout"]["development_cutoff_utc"]
    cutoff_ms = int(parse_iso_utc(development_cutoff).timestamp() * 1000)
    expected_last_open = (cutoff_ms // HOUR_MS - 1) * HOUR_MS
    assets = data.get("assets") or {}
    for entry in universe.get("eligible_assets") or []:
        if not entry.get("validated"):
            continue
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        record = assets.get(pair) or {}
        dataset_path = record.get("dataset_path")
        if not dataset_path or not (repo_root / dataset_path).exists():
            failures.append(f"{pair}: the dataset does not exist")
            continue
        content = (repo_root / dataset_path).read_text(encoding="utf-8")
        if sha256_bytes(content.encode("utf-8")) != record.get("content_hash"):
            failures.append(f"{pair}: the dataset does not hash to the recorded content hash")
        if (data.get("content_hashes") or {}).get(pair) != record.get("content_hash"):
            failures.append(f"{pair}: the content_hashes block records another digest")
        rows = content.strip().splitlines()
        if len(rows) - 1 != MIN_CANDLES:
            failures.append(f"{pair}: the dataset does not hold exactly {MIN_CANDLES} candles")
        timestamps = [int(row.split(",")[0]) for row in rows[1:]]
        if any(timestamp % HOUR_MS for timestamp in timestamps):
            failures.append(f"{pair}: the dataset holds a candle that is not hour-aligned")
        if len(set(timestamps)) != len(timestamps):
            failures.append(f"{pair}: the dataset holds a duplicate candle")
        if timestamps and timestamps[-1] != expected_last_open:
            failures.append(
                f"{pair}: the dataset does not end at the last closed hour before the "
                "development cutoff"
            )
        recorded_last = record.get("last_candle_timestamp")
        if timestamps and recorded_last is not None and int(recorded_last) != timestamps[-1]:
            failures.append(
                f"{pair}: the manifest records another last candle than the dataset holds"
            )
        if recorded_last is not None and int(recorded_last) + HOUR_MS > cutoff_ms:
            failures.append(
                f"{pair}: the manifest records a candle that closes after the "
                "development cutoff"
            )
        if timestamps and timestamps[-1] + HOUR_MS > cutoff_ms:
            failures.append(
                f"{pair}: the dataset closes a candle after the development cutoff"
            )
    if (data.get("window_policy") or {}).get("development_cutoff_utc") != development_cutoff:
        failures.append("the data manifest does not bind the preregistered development cutoff")
    if not data.get("candles_verified"):
        failures.append("the data manifest does not record candles_verified")
    if not data.get("provenance_ok"):
        failures.append("the data manifest does not record provenance_ok")

    # 8. the supersedes chain names the v3 artifacts.
    supersedes = universe.get("supersedes") or {}
    if supersedes.get("universe_manifest_path") != V3_UNIVERSE_RELATIVE:
        failures.append("the v4 universe manifest does not supersede the v3 universe manifest")
    if supersedes.get("universe_manifest_hash") != v3_universe.get("manifest_hash"):
        failures.append("the v4 universe manifest does not bind the v3 universe identity")
    data_supersedes = data.get("supersedes") or {}
    if data_supersedes.get("data_manifest_path") != V3_DATA_RELATIVE:
        failures.append("the v4 data manifest does not supersede the v3 data manifest")

    # 9. every constituent is validated or excluded with a reason.
    for entry in universe.get("eligible_assets") or []:
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        if entry.get("validated"):
            if entry.get("exclusion_reason") is not None:
                failures.append(f"{pair}: a validated asset carries an exclusion reason")
        else:
            reason = entry.get("exclusion_reason")
            if reason not in ALLOWED_VALIDATION_EXCLUSION_REASONS:
                failures.append(f"{pair}: an unknown validation exclusion reason {reason!r}")

    # 10. the confirmatory window is unexposed and the v4 execution state is
    #     the authorized one.
    window = data.get("confirmatory_window") or {}
    if window.get("holdout_exposed_count") != 0:
        failures.append("the v4 data manifest records a confirmatory exposure")
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v4 confirmatory window is not recorded as not started")
    failures.extend(v4_execution_state_failures(repo_root))

    # 11. the v1, v2 and v3 artifacts are unchanged.
    for relative in FROZEN_ANCHORS:
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the frozen anchor {relative} is missing")
            continue
        digest = sha256_file(target)
        recorded = (data.get("related_artifacts") or {}).get("v1_anchors", {}).get(relative)
        if recorded is not None and recorded != digest:
            failures.append(f"the frozen anchor {relative} does not match its recorded sha256")

    return {
        "ok": not failures,
        "universe_manifest_path": UNIVERSE_RELATIVE,
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_path": DATA_RELATIVE,
        "data_manifest_hash": data.get("manifest_hash"),
        "effective_amendment_path": str(amendment_path.relative_to(repo_root)),
        "effective_amendment_hash": amendment.get("amendment_hash"),
        "floor_market_cap_usd": floor_market_cap,
        "development_cutoff_utc": development_cutoff,
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

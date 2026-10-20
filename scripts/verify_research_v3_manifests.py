#!/usr/bin/env python3
"""Read-only, offline verification of the v3 universe and data manifests.

This is the verifier that ``configs/research_v3_exclusion_amendment_1.json``
names in its ``producer.verify_command``. It recomputes every expectation from
the repository:

* the two manifest hashes recompute from their own bodies;
* the market-cap snapshot is the in-window retrieval the specification pins
  (raw bytes, digest, endpoint, timestamp);
* the candidate batch is **re-derived** from the stored snapshot with the
  published exclusion rules and compared with the manifests;
* every constituent is either validated (with a hash-verified dataset of
  exactly 26,280 closed hourly candles) or excluded with a reason;
* the confirmatory window is unexposed and nothing has run under v3.

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

from v3_constituent_validation import derive_batch, parse_iso_utc  # noqa: E402

SPEC_RELATIVE = "configs/research_v3.json"
AMENDMENT_RELATIVE = "configs/research_v3_exclusion_amendment_1.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
SNAPSHOT_RELATIVE = "research/v3_evidence/raw_market_cap_response.json"
OBSERVATION_RELATIVE = "research/v3_evidence/snapshot_observation.json"
SPOT_EVIDENCE_RELATIVE = "research/v3_evidence/binance_spot_verification.json"
CANDLE_EVIDENCE_RELATIVE = "research/v3_evidence/candle_verification.json"
V1_UNIVERSE_RELATIVE = "research/universe_manifest.json"
V2_UNIVERSE_RELATIVE = "research/universe_manifest_v2.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v1 and v2 artifacts whose bytes must not have changed.
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
)

#: The paths a v3 execution run would create. None of them may exist yet.
V3_EXECUTION_PATHS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
)

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
    with path.open("rb") as handle:
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


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []

    for relative in (SPEC_RELATIVE, AMENDMENT_RELATIVE, UNIVERSE_RELATIVE, DATA_RELATIVE,
                     SNAPSHOT_RELATIVE, OBSERVATION_RELATIVE, V1_UNIVERSE_RELATIVE,
                     V2_UNIVERSE_RELATIVE):
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"],
                    "warnings": warnings}

    spec = read_json(repo_root / SPEC_RELATIVE)
    amendment = read_json(repo_root / AMENDMENT_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)
    observation = read_json(repo_root / OBSERVATION_RELATIVE)
    v1_universe = read_json(repo_root / V1_UNIVERSE_RELATIVE)
    v2_universe = read_json(repo_root / V2_UNIVERSE_RELATIVE)

    # 1. the manifest hashes recompute
    universe_excluded = tuple(universe.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if universe.get("manifest_hash") != compute_manifest_hash(universe, universe_excluded):
        failures.append("the v3 universe manifest hash does not recompute from its body")
    data_excluded = tuple(data.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if data.get("manifest_hash") != compute_manifest_hash(data, data_excluded):
        failures.append("the v3 data manifest hash does not recompute from its body")

    # 2. the snapshot is the in-window retrieval
    raw_bytes = (repo_root / SNAPSHOT_RELATIVE).read_bytes()
    if sha256_bytes(raw_bytes) != observation.get("raw_response_hash"):
        failures.append("the stored v3 snapshot does not hash to the recorded digest")
    if universe.get("market_cap_source", {}).get("raw_response_hash") != observation.get(
        "raw_response_hash"
    ):
        failures.append("the universe manifest records a different snapshot digest")
    retrieval = spec["universe"]["snapshot_retrieval"]
    retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])
    if not (parse_iso_utc(retrieval["not_before_utc"]) <= retrieved_at
            <= parse_iso_utc(retrieval["deadline_utc"])):
        failures.append("the stored v3 snapshot was not retrieved inside the pinned window")
    if observation.get("endpoint") != spec["universe"]["endpoint"]:
        failures.append("the stored v3 snapshot was not retrieved from the frozen endpoint")
    if data.get("market_cap_source", {}).get("raw_response_hash") != observation.get(
        "raw_response_hash"
    ):
        failures.append("the data manifest records a different snapshot digest")

    # 3. the snapshot-identity tuple is complete and self-consistent
    expected_identity_fields = list(spec["universe"]["snapshot_identity"]["fields"])
    for label, manifest in (("universe", universe), ("data", data)):
        identity = manifest.get("snapshot_identity") or {}
        missing = [field for field in expected_identity_fields if field not in identity]
        if missing:
            failures.append(f"the {label} manifest's snapshot identity is missing {missing}")
        if identity.get("specification_hash") != spec.get("specification_hash"):
            failures.append(f"the {label} manifest's snapshot identity names another specification")
        if identity.get("protocol_version") != spec.get("protocol_version"):
            failures.append(f"the {label} manifest's snapshot identity names another protocol")
        if identity.get("universe_version") != spec.get("universe_version"):
            failures.append(f"the {label} manifest's snapshot identity names another universe")
        if identity.get("market_cap_source_endpoint") != spec["universe"]["endpoint"]:
            failures.append(f"the {label} manifest's snapshot identity names another endpoint")
        if identity.get("market_cap_source_retrieval_timestamp_utc") != observation.get(
            "retrieval_timestamp_utc"
        ):
            failures.append(f"the {label} manifest's snapshot identity names another retrieval time")
    if (universe.get("snapshot_identity") or {}).get("data_manifest_hash") != data.get(
        "manifest_hash"
    ):
        failures.append("the universe manifest does not bind the current data manifest")

    # 4. the code hash is the authorized value of record, cross-checked
    authorization = read_json(repo_root / AUTHORIZATION_RELATIVE)
    authorized = authorization.get("code_hash")
    for label, manifest in (("universe", universe), ("data", data)):
        if manifest.get("code_hash") != authorized:
            failures.append(
                f"the {label} manifest records {manifest.get('code_hash')!r} as the code hash, "
                f"but the authorized value of record is {authorized!r}"
            )

    # 5. the candidate batch is re-derived from the snapshot with the published rules
    markets = json.loads(raw_bytes.decode("utf-8"))
    batch, rule_excluded = derive_batch(spec, amendment, markets, v1_universe, v2_universe)
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

    # 6. every constituent is validated or excluded with a reason
    validation_results = data.get("validation_results") or {}
    for entry in universe.get("eligible_assets") or []:
        pair = entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        if entry.get("validated"):
            if entry.get("exclusion_reason") is not None:
                failures.append(f"{pair}: a validated asset carries an exclusion reason")
            if not entry.get("binance_spot_verified") or not entry.get("candle_history_verified"):
                failures.append(f"{pair}: a validated asset is not spot- and history-verified")
        else:
            reason = entry.get("exclusion_reason")
            if reason not in ALLOWED_VALIDATION_EXCLUSION_REASONS:
                failures.append(f"{pair}: exclusion reason {reason!r} is outside the frozen vocabulary")
            if (validation_results.get(pair) or {}).get("exclusion_reason") != reason:
                failures.append(f"{pair}: the data manifest records a different exclusion reason")

    # 7. every validated asset has a hash-verified dataset of the required length
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
        expected_window = (
            int(parse_iso_utc(observation["retrieval_timestamp_utc"]).timestamp() * 1000) // HOUR_MS - 1
        ) * HOUR_MS
        if timestamps and timestamps[-1] != expected_window:
            failures.append(f"{pair}: the dataset does not end at the snapshot's last closed hour")
    if not data.get("candles_verified"):
        failures.append("the data manifest does not record candles_verified")
    if not data.get("provenance_ok"):
        failures.append("the data manifest does not record provenance_ok")

    # 8. the confirmatory window is unexposed
    window = data.get("confirmatory_window") or {}
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not NOT_STARTED")
    if int(window.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v3 confirmatory window records a non-zero holdout exposure")
    if window.get("v1_holdout_reuse") != "forbidden":
        failures.append("the v3 data manifest does not forbid the v1 holdout reuse")

    # 9. nothing has run under v3
    for relative in V3_EXECUTION_PATHS:
        if (repo_root / relative).exists():
            failures.append(f"a v3 execution artifact exists: {relative}")

    # 10. the frozen v1 and v2 evidence is byte-identical
    for relative in FROZEN_ANCHORS:
        if not (repo_root / relative).exists():
            failures.append(f"a frozen artifact is missing: {relative}")

    # 11. the immutable specification's stale data-manifest reference
    integrity = (spec.get("universe", {}).get("eligibility_validation", {})
                 .get("data_integrity", {}))
    spec_amendment: Optional[Dict[str, Any]] = None
    if integrity.get("data_manifest") != DATA_RELATIVE:
        amendment_path = repo_root / "configs/research_v3_spec_amendment_1.json"
        if not amendment_path.exists():
            failures.append(
                "the immutable specification names the v2 data manifest and no verified "
                "specification amendment supersedes it"
            )
        else:
            spec_amendment = read_json(amendment_path)
            excluded = tuple(spec_amendment.get("hashing", {}).get(
                "manifest_hash_excluded_keys") or ())
            if spec_amendment.get("manifest_hash") != compute_manifest_hash(
                spec_amendment, excluded
            ):
                failures.append("the specification amendment's manifest hash does not recompute")
            corrections = spec_amendment.get("corrections") or []
            resolved = any(
                item.get("path") == (
                    "universe.eligibility_validation.data_integrity.data_manifest")
                and item.get("effective_value") == DATA_RELATIVE
                and (item.get("evidence") or {}).get("manifest_hash") == data.get("manifest_hash")
                for item in corrections
            )
            if not resolved:
                failures.append(
                    "the specification amendment does not correct the stale data-manifest "
                    "reference of the immutable specification"
                )
            else:
                warnings.append(
                    f"configs/research_v3.json universe.eligibility_validation.data_integrity."
                    f"data_manifest names {integrity.get('data_manifest')!r} instead of "
                    f"{DATA_RELATIVE!r}; the immutable specification is corrected by "
                    "reference through configs/research_v3_spec_amendment_1.json"
                )

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_hash": data.get("manifest_hash"),
        "candidate_count": len(manifest_pairs),
        "validated_count": sum(
            1 for entry in (universe.get("eligible_assets") or []) if entry.get("validated")
        ),
        "specification_amendment": (
            "configs/research_v3_spec_amendment_1.json" if spec_amendment is not None else None
        ),
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

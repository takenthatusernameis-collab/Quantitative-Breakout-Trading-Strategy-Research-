#!/usr/bin/env python3
"""Read-only, offline verification of the v2 manifests (BRAIN-008 P2 and P3).

The verifier never writes to the repository and never contacts a provider. It
checks the two artifacts named by the preregistered specification:

* ``research/universe_manifest_v2.json`` — the v2 universe;
* ``research/data_manifest_v2.json`` — the v2 data manifest;

against the rules frozen in ``configs/research_v2.json``:

* both manifests carry the snapshot-identity tuple and it agrees with the
  specification, with the stored raw provider response and with each other;
* the market-cap snapshot is the one retrieved inside the pinned window and its
  stored bytes hash to the recorded digest;
* every manifest self-hash recomputes over the documented canonicalization;
* the identity of the hashed source set is checked against the portable
  canonical source digest, and the recorded code hash is cross-checked
  against the v1 campaign authorization: a live ordered-digest mismatch is an
  environment fact about the directory enumeration order of the checkout, not
  evidence of source drift (BRAIN-009);
* every candidate is either validated (Binance spot + a complete, gap-free,
  hash-verified hourly dataset of at least 26,280 candles) or excluded with a
  reason, and no candidate is silently dropped;
* every validated dataset exists, re-hashes to its recorded content hash and
  has the recorded coverage;
* the exclusion rules are copied unchanged from the v1 universe manifest, and
  the v1 artifacts the manifests supersede are still byte-identical;
* no v2 candidate manifest and no confirmatory-window exposure exist yet.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
V1_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest.json"
V1_DATA_PATH = REPO_ROOT / "research" / "data_manifest.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
SNAPSHOT_RAW_PATH = REPO_ROOT / "research" / "v2_evidence" / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = REPO_ROOT / "research" / "v2_evidence" / "snapshot_observation.json"
CANDLE_DIR_V2 = REPO_ROOT / "research" / "data" / "candles_v2"
CODE_HASH_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"

SNAPSHOT_IDENTITY_FIELDS = (
    "protocol_version",
    "universe_version",
    "specification_hash",
    "market_cap_source_endpoint",
    "market_cap_source_retrieval_timestamp_utc",
    "code_hash",
    "data_manifest_hash",
    "candidate_manifest_hash",
)

DATA_MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash", "snapshot_identity.data_manifest_hash")
UNIVERSE_MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

DATASET_HEADER = "timestamp,open,high,low,close,volume\n"


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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    """The portable identity of the hashed source tree.

    Every ``*.py`` file under the hashed set contributes its POSIX relative path
    and the sha256 hex digest of its bytes, in ascending path order. Unlike
    ``compute_code_hash()`` this does not depend on the directory enumeration
    order of the checkout, so it is reproducible on any machine.
    """
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def live_ordered_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Reproduce ``compute_code_hash()`` exactly, for the informational report.

    The result depends on the filesystem enumeration order of the checkout and
    is therefore not a portable identity of the tree.
    """
    src_dir = repo_root / HASHED_SET_ROOT
    if not src_dir.exists():
        return None
    digest = hashlib.sha256()
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            if name.endswith(".py"):
                digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def dataset_content_hash(path: Path) -> Tuple[str, int, Optional[int], Optional[int]]:
    """Re-hash a canonical hourly CSV and report its coverage."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith(DATASET_HEADER):
        return sha256_bytes(content.encode("utf-8")), 0, None, None
    rows = content[len(DATASET_HEADER):].splitlines()
    timestamps: List[int] = []
    for row in rows:
        fields = row.split(",")
        if len(fields) != 6:
            return sha256_bytes(content.encode("utf-8")), len(rows), None, None
        timestamps.append(int(fields[0]))
    return sha256_bytes(content.encode("utf-8")), len(rows), timestamps[0], timestamps[-1]


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    spec_path = repo_root / "configs" / "research_v2.json"
    universe_path = repo_root / "research" / "universe_manifest_v2.json"
    data_path = repo_root / "research" / "data_manifest_v2.json"

    for path in (
        spec_path,
        universe_path,
        data_path,
        repo_root / "configs" / "research_v2_code_hash_amendment_1.json",
        repo_root / "research_state" / "campaign_authorization.json",
    ):
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    data = json.loads(data_path.read_text(encoding="utf-8"))
    v1_universe = json.loads((repo_root / "research" / "universe_manifest.json").read_text(encoding="utf-8"))
    v1_data = json.loads((repo_root / "research" / "data_manifest.json").read_text(encoding="utf-8"))
    code_hash_amendment = json.loads(
        (repo_root / "configs" / "research_v2_code_hash_amendment_1.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(
        (repo_root / "research_state" / "campaign_authorization.json").read_text(encoding="utf-8")
    )

    universe_spec = spec["universe"]
    min_candles = int(universe_spec["min_candles"])
    top_n = int(universe_spec["top_n"])

    # 1. Self hashes.
    if universe.get("manifest_hash") != compute_manifest_hash(universe, UNIVERSE_MANIFEST_HASH_EXCLUDED_KEYS):
        failures.append("universe_manifest_v2.manifest_hash does not recompute")
    if data.get("manifest_hash") != compute_manifest_hash(data, DATA_MANIFEST_HASH_EXCLUDED_KEYS):
        failures.append("data_manifest_v2.manifest_hash does not recompute")

    # 2. Snapshot identity.
    universe_identity = universe.get("snapshot_identity") or {}
    data_identity = data.get("snapshot_identity") or {}
    for field in SNAPSHOT_IDENTITY_FIELDS:
        if field not in universe_identity:
            failures.append(f"universe snapshot_identity is missing {field}")
        if field not in data_identity:
            failures.append(f"data snapshot_identity is missing {field}")
    for field in SNAPSHOT_IDENTITY_FIELDS:
        if field != "data_manifest_hash" and universe_identity.get(field) != data_identity.get(field):
            failures.append(f"snapshot identity field {field} differs between the two manifests")

    if universe_identity.get("protocol_version") != spec["protocol_version"]:
        failures.append("snapshot identity protocol_version does not match the specification")
    if universe_identity.get("universe_version") != spec["universe_version"]:
        failures.append("snapshot identity universe_version does not match the specification")
    if universe_identity.get("specification_hash") != spec["specification_hash"]:
        failures.append("snapshot identity specification_hash does not match the specification")
    if universe_identity.get("market_cap_source_endpoint") != universe_spec["endpoint"]:
        failures.append("snapshot identity market_cap_source_endpoint is not the frozen endpoint")
    if universe_identity.get("candidate_manifest_hash") is not None:
        failures.append("a v2 candidate manifest hash is recorded, but no v2 candidate manifest exists")

    # 2b. Tree identity (BRAIN-009). The portable canonical source digest is the
    # identity of the hashed set; the recorded code hash is cross-checked against
    # the v1 campaign authorization. The live ordered digest is checkout-dependent
    # and is reported as an environment fact, never compared as a drift signal.
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_canonical = canonical_source_digest(repo_root)
    if recorded_canonical != live_canonical:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}"
        )
    authorized_code_hash = authorization.get("code_hash")
    if universe_identity.get("code_hash") != authorized_code_hash:
        failures.append("snapshot identity code_hash is not the authorized v1 code hash")
    live_ordered = live_ordered_code_hash(repo_root)
    if live_ordered != authorized_code_hash:
        environment_facts.append(
            f"the live ordered code hash {live_ordered} differs from the authorized value of "
            f"record {authorized_code_hash}; this is an environment fact about the directory "
            "enumeration order of this checkout, not evidence of source drift"
        )

    if universe_identity.get("data_manifest_hash") != data.get("manifest_hash"):
        failures.append("universe snapshot_identity.data_manifest_hash does not match the data manifest")
    if data_identity.get("data_manifest_hash") != data.get("manifest_hash"):
        failures.append("data snapshot_identity.data_manifest_hash does not match the data manifest")

    # 3. The stored snapshot is the in-window retrieval and hashes to the recorded digest.
    snapshot_raw_path = repo_root / "research" / "v2_evidence" / "raw_market_cap_response.json"
    observation_path = repo_root / "research" / "v2_evidence" / "snapshot_observation.json"
    if not snapshot_raw_path.exists() or not observation_path.exists():
        failures.append("the stored market-cap snapshot or its observation is missing")
    else:
        raw_bytes = snapshot_raw_path.read_bytes()
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        digest = sha256_bytes(raw_bytes)
        recorded = (universe.get("market_cap_source") or {}).get("raw_response_hash")
        if digest != recorded:
            failures.append("the stored market-cap response does not hash to the recorded digest")
        if recorded != observation.get("raw_response_hash"):
            failures.append("the universe manifest and the snapshot observation disagree on the digest")
        retrieval = universe_spec["snapshot_retrieval"]
        retrieved_at = parse_iso_utc(observation["retrieval_timestamp_utc"])
        if not (parse_iso_utc(retrieval["not_before_utc"]) <= retrieved_at <= parse_iso_utc(retrieval["deadline_utc"])):
            failures.append("the stored snapshot was not retrieved inside the pinned window")
        if universe_identity.get("market_cap_source_retrieval_timestamp_utc") != observation["retrieval_timestamp_utc"]:
            failures.append("the snapshot identity timestamp does not match the snapshot observation")

    # 4. Candidates are validated or excluded, never silently dropped.
    eligible = universe.get("eligible_assets") or []
    if len(eligible) != top_n:
        failures.append(f"the v2 universe has {len(eligible)} candidates, expected {top_n}")
    ranks = sorted(int(entry.get("rank") or 0) for entry in eligible)
    if ranks != list(range(1, len(eligible) + 1)):
        failures.append("the v2 candidate ranks are not contiguous")

    validated_pairs: List[str] = []
    for entry in eligible:
        symbol = entry.get("symbol")
        reason = entry.get("exclusion_reason")
        if entry.get("validated"):
            validated_pairs.append(symbol)
            if reason:
                failures.append(f"{symbol} is validated but carries an exclusion reason")
            if not entry.get("binance_spot_verified"):
                failures.append(f"{symbol} is validated without a Binance spot verification")
            if not entry.get("candle_history_verified"):
                failures.append(f"{symbol} is validated without a candle-history verification")
            if int(entry.get("observed_candles") or 0) < min_candles:
                failures.append(f"{symbol} is validated with fewer than {min_candles} candles")
        else:
            if not reason:
                failures.append(f"{symbol} is neither validated nor excluded")
            if entry.get("binance_spot_verified") and entry.get("candle_history_verified"):
                failures.append(f"{symbol} passed both validations but is not marked validated")

    # 5. Every validated asset has a hash-verified dataset with the recorded coverage.
    assets = data.get("assets") or {}
    for symbol in validated_pairs:
        entry = assets.get(symbol)
        if not entry:
            failures.append(f"{symbol} is validated but missing from the v2 data manifest")
            continue
        dataset_path = repo_root / str(entry.get("dataset_path") or "")
        if not dataset_path.exists():
            failures.append(f"{symbol} references a missing dataset: {entry.get('dataset_path')}")
            continue
        digest, rows, first_ts, last_ts = dataset_content_hash(dataset_path)
        if digest != entry.get("content_hash"):
            failures.append(f"{symbol} dataset does not hash to its recorded content hash")
        if digest != (data.get("content_hashes") or {}).get(symbol):
            failures.append(f"{symbol} top-level content hash does not match the dataset")
        if rows != entry.get("observed_candle_count"):
            failures.append(f"{symbol} dataset row count does not match the recorded count")
        if rows < min_candles:
            failures.append(f"{symbol} dataset holds fewer than {min_candles} candles")
        if first_ts != entry.get("first_candle_timestamp") or last_ts != entry.get("last_candle_timestamp"):
            failures.append(f"{symbol} dataset coverage does not match the recorded timestamps")
        if entry.get("gaps"):
            failures.append(f"{symbol} dataset records coverage gaps")
        if entry.get("rejected_rows"):
            failures.append(f"{symbol} dataset records rejected rows")
        if entry.get("provider") != "binance":
            failures.append(f"{symbol} dataset provenance is not binance")
        if not str(dataset_path).startswith(str(CANDLE_DIR_V2.resolve())):
            failures.append(f"{symbol} dataset is not stored in the v2 candle directory")

    for symbol, entry in assets.items():
        if symbol in validated_pairs:
            continue
        if entry.get("dataset_path"):
            failures.append(f"{symbol} is not validated but references a dataset")

    # 6. Exclusion rules are copied unchanged from v1 and every exclusion has a reason.
    if universe.get("exclusion_rules") != v1_universe.get("exclusion_rules"):
        failures.append("the v2 exclusion rules differ from the v1 exclusion rules")
    for entry in universe.get("excluded_candidates") or []:
        if not entry.get("exclusion_reason"):
            failures.append(f"excluded candidate {entry.get('symbol')} has no exclusion reason")

    # 7. The superseded v1 artifacts are still byte-identical.
    supersedes = universe.get("supersedes") or {}
    for path_key, digest_key in (
        ("universe_manifest_path", "universe_manifest_sha256"),
        ("candidate_manifest_path", "candidate_manifest_sha256"),
    ):
        relative = supersedes.get(path_key)
        if not relative:
            failures.append(f"the v2 universe manifest does not record {path_key}")
            continue
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the superseded artifact {relative} is missing")
            continue
        if sha256_file(target) != supersedes.get(digest_key):
            failures.append(f"the superseded artifact {relative} does not match its recorded sha256")
    data_supersedes = data.get("supersedes") or {}
    relative = data_supersedes.get("data_manifest_path")
    if relative:
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the superseded artifact {relative} is missing")
        elif sha256_file(target) != data_supersedes.get("data_manifest_sha256"):
            failures.append(f"the superseded artifact {relative} does not match its recorded sha256")
    if v1_universe.get("protocol_version") != "v1" or v1_data.get("protocol_version") != "v1":
        failures.append("the superseded artifacts are not protocol v1")

    # 8. Nothing has been selected or exposed yet.
    window = data.get("confirmatory_window") or {}
    if window.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is not marked NOT_STARTED")

    return {
        "ok": not failures,
        "universe_manifest_path": str(universe_path.relative_to(repo_root)),
        "universe_manifest_hash": universe.get("manifest_hash"),
        "data_manifest_path": str(data_path.relative_to(repo_root)),
        "data_manifest_hash": data.get("manifest_hash"),
        "snapshot_identity": universe_identity,
        "candidate_count": len(eligible),
        "validated_assets": sorted(validated_pairs),
        "excluded_assets": sorted(
            str(entry.get("symbol")) for entry in eligible if entry.get("exclusion_reason")
        ),
        "canonical_source_digest": live_canonical,
        "live_ordered_code_hash": live_ordered,
        "ordered_code_hash_matches_authorized": live_ordered == authorized_code_hash,
        "environment_facts": environment_facts,
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

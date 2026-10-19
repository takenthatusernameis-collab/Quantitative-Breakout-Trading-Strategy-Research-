#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 candidate freeze.

The verifier never writes to the repository, never contacts a provider and
never reads a candle. It checks ``configs/research_v2_candidate_freeze.json``
against the artifacts it claims to freeze:

* the manifest hash recomputes from the canonical content of the document with
  the two digest-carrying keys removed, and the snapshot-identity tuple names
  that same hash;
* the identity tuple agrees with the v2 specification, the v2 universe
  manifest, the v2 data manifest, the stored market-cap snapshot and the
  current source tree;
* the identity of the hashed source set is checked against the portable
  canonical source digest, and the recorded code hash is cross-checked
  against the v1 campaign authorization: a live ordered-digest mismatch is an
  environment fact about the directory enumeration order of the checkout, not
  evidence of source drift (BRAIN-009);
* the frozen candidate set is exactly the validated constituents of universe
  version v2 and exactly the evaluation scope of the v2 execution protocol;
  the excluded assets are absent and keep their exclusion reasons;
* the confirmatory window opens after the freeze, needs at least 2,160 closed
  hourly candles, is single-use, never overlaps the v1 holdout and is never
  read during selection;
* the superseded v1 candidate manifest is still byte-identical, and the v1
  campaign's ``manifest_version 2`` artifact is not mistaken for a v2-universe
  candidate manifest;
* nothing has been executed: no v2 shard, ledger, result manifest or result
  row exists, and the v2 confirmatory window is still unexposed;
* the code-hash constraint names only paths that really are outside the hashed
  source set.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

FREEZE_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"
PROTOCOL_V2_PATH = REPO_ROOT / "configs" / "research_v2_execution.json"
SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
UNIVERSE_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"
V1_CANDIDATE_PATH = REPO_ROOT / "research" / "candidate_manifest.json"
V1_CANDIDATE_V2_PATH = REPO_ROOT / "research" / "candidate_manifest_v2.json"
SNAPSHOT_RAW_RELATIVE = "research/v2_evidence/raw_market_cap_response.json"
CODE_HASH_AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

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

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

V2_EXECUTION_ARTIFACTS = (
    "research/shards_v2",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
)

HASHED_SET_ROOT = "src/breakout_research"


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


def next_hour_boundary(value: datetime) -> datetime:
    floored = value.replace(minute=0, second=0, microsecond=0)
    return floored + timedelta(hours=1)


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


def path_is_inside_hashed_set(relative: str) -> bool:
    root = HASHED_SET_ROOT.rstrip("/")
    candidate = relative.rstrip("/")
    return candidate == root or candidate.startswith(root + "/")


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    freeze_path = repo_root / "configs" / "research_v2_candidate_freeze.json"

    for path in (
        freeze_path,
        repo_root / "configs" / "research_v2.json",
        repo_root / "configs" / "research_v2_execution.json",
        repo_root / "configs" / "research_v2_code_hash_amendment_1.json",
        repo_root / "research" / "universe_manifest_v2.json",
        repo_root / "research" / "data_manifest_v2.json",
        repo_root / "research" / "candidate_manifest.json",
        repo_root / "research" / "candidate_manifest_v2.json",
        repo_root / "research_state" / "campaign_authorization.json",
    ):
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    spec = json.loads((repo_root / "configs" / "research_v2.json").read_text(encoding="utf-8"))
    spec_v1 = json.loads((repo_root / "configs" / "research_v1.json").read_text(encoding="utf-8"))
    protocol = json.loads(
        (repo_root / "configs" / "research_v2_execution.json").read_text(encoding="utf-8")
    )
    universe = json.loads(
        (repo_root / "research" / "universe_manifest_v2.json").read_text(encoding="utf-8")
    )
    data = json.loads((repo_root / "research" / "data_manifest_v2.json").read_text(encoding="utf-8"))
    v1_candidates = json.loads(
        (repo_root / "research" / "candidate_manifest.json").read_text(encoding="utf-8")
    )
    v1_candidates_v2 = json.loads(
        (repo_root / "research" / "candidate_manifest_v2.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(
        (repo_root / "research_state" / "campaign_authorization.json").read_text(encoding="utf-8")
    )
    code_hash_amendment = json.loads(
        (repo_root / "configs" / "research_v2_code_hash_amendment_1.json").read_text(encoding="utf-8")
    )

    # 1. Self hash.
    excluded = tuple(freeze.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the freeze does not declare its manifest_hash_excluded_keys")
    declared = freeze.get("manifest_hash")
    recomputed = compute_manifest_hash(freeze, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. Snapshot identity.
    identity = freeze.get("snapshot_identity") or {}
    for field in SNAPSHOT_IDENTITY_FIELDS:
        if field not in identity:
            failures.append(f"the snapshot identity is missing {field}")
    if identity.get("candidate_manifest_hash") != declared:
        failures.append("the snapshot identity does not name this candidate manifest's hash")
    if identity.get("protocol_version") != spec.get("protocol_version"):
        failures.append("the snapshot identity protocol_version does not match the specification")
    if identity.get("universe_version") != spec.get("universe_version"):
        failures.append("the snapshot identity universe_version does not match the specification")
    if identity.get("specification_hash") != spec.get("specification_hash"):
        failures.append("the snapshot identity specification_hash does not match the specification")
    if identity.get("market_cap_source_endpoint") != spec["universe"]["endpoint"]:
        failures.append("the snapshot identity endpoint is not the frozen endpoint")
    universe_identity = universe.get("snapshot_identity") or {}
    if identity.get("market_cap_source_retrieval_timestamp_utc") != universe_identity.get(
        "market_cap_source_retrieval_timestamp_utc"
    ):
        failures.append("the snapshot identity timestamp does not match the v2 universe manifest")
    if identity.get("data_manifest_hash") != data.get("manifest_hash"):
        failures.append("the snapshot identity data_manifest_hash does not match the v2 data manifest")

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
    if identity.get("code_hash") != authorized_code_hash:
        failures.append("the snapshot identity code_hash is not the authorized v1 code hash")
    if (freeze.get("code_hash_constraint") or {}).get("authorized_code_hash") != authorized_code_hash:
        failures.append("the code-hash constraint does not record the authorized v1 code hash")
    live_ordered = live_ordered_code_hash(repo_root)
    if live_ordered != authorized_code_hash:
        environment_facts.append(
            f"the live ordered code hash {live_ordered} differs from the authorized value of "
            f"record {authorized_code_hash}; this is an environment fact about the directory "
            "enumeration order of this checkout, not evidence of source drift"
        )

    # 3. The frozen candidate set.
    validated_pairs = sorted(
        str(entry.get("symbol"))
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated")
    )
    excluded_pairs = {
        str(entry.get("symbol")): str(entry.get("exclusion_reason"))
        for entry in universe.get("eligible_assets") or []
        if not entry.get("validated")
    }
    frozen = freeze.get("frozen_candidate_set") or {}
    frozen_pairs = sorted(str(pair) for pair in frozen.get("binance_pairs") or [])
    frozen_constituents = sorted(str(item) for item in frozen.get("constituents") or [])
    if frozen_pairs != validated_pairs:
        failures.append("the frozen candidate set is not the validated v2 candidate set")
    if frozen_constituents != sorted(pair[:-4] for pair in validated_pairs):
        failures.append("the frozen constituents do not match the frozen pairs")
    if frozen.get("count") != len(validated_pairs):
        failures.append("the frozen candidate count does not match the frozen set")
    if frozen.get("universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("the freeze is not bound to the current v2 universe manifest")
    if frozen.get("data_manifest_hash") != data.get("manifest_hash"):
        failures.append("the freeze is not bound to the current v2 data manifest")
    if frozen.get("widening_by_reranking_forbidden") is not True:
        failures.append("the freeze does not forbid widening the scope by re-ranking")
    if frozen.get("excluded_assets_stay_excluded") is not True:
        failures.append("the freeze does not keep the excluded assets excluded")
    recorded_exclusions = frozen.get("excluded_after_validation") or {}
    for symbol, reason in excluded_pairs.items():
        if symbol in frozen_pairs:
            failures.append(f"the excluded asset {symbol} is frozen as a candidate")
        if recorded_exclusions.get(symbol) != reason:
            failures.append(f"the exclusion reason of {symbol} is not recorded by the freeze")
    for symbol in recorded_exclusions:
        if symbol not in excluded_pairs:
            failures.append(f"the freeze records an exclusion for {symbol}, which is not excluded")

    protocol_scope = sorted(
        str(item) for item in protocol.get("evaluation_scope", {}).get("constituents") or []
    )
    if frozen_constituents != protocol_scope:
        failures.append("the frozen candidate set differs from the execution protocol scope")

    # 4. The v2 manifests the freeze binds to are themselves hash-consistent.
    if universe.get("manifest_hash") != compute_manifest_hash(universe, ("manifest_hash",)):
        failures.append("the v2 universe manifest hash does not recompute")
    if data.get("manifest_hash") != compute_manifest_hash(
        data, ("manifest_hash", "snapshot_identity.data_manifest_hash")
    ):
        failures.append("the v2 data manifest hash does not recompute")

    # 5. The data boundary.
    boundary = freeze.get("data_boundary") or {}
    try:
        frozen_at = parse_iso_utc(freeze["candidate_freeze_timestamp_utc"])
    except Exception as exc:
        failures.append(f"the candidate freeze timestamp cannot be parsed: {exc}")
        frozen_at = None
    try:
        window_start = parse_iso_utc(boundary["confirmatory_window_start_utc"])
    except Exception as exc:
        failures.append(f"the confirmatory window start cannot be parsed: {exc}")
        window_start = None
    if frozen_at and window_start:
        if window_start <= frozen_at:
            failures.append("the confirmatory window does not start after the candidate freeze")
        if window_start != next_hour_boundary(frozen_at):
            failures.append(
                "the confirmatory window start is not the first hour boundary after the freeze"
            )
    if boundary.get("min_confirmatory_window_hours") != 2160:
        failures.append("the confirmatory window does not require 2,160 closed hourly candles")
    if window_start and boundary.get("earliest_possible_confirmatory_window_end_utc"):
        expected_end = window_start + timedelta(hours=int(boundary["min_confirmatory_window_hours"]))
        if parse_iso_utc(boundary["earliest_possible_confirmatory_window_end_utc"]) != expected_end:
            failures.append("the earliest possible window end does not follow from the window start")
    if boundary.get("single_use") is not True:
        failures.append("the confirmatory window is not marked single-use")
    if boundary.get("no_ranking_or_retuning_on_holdout") is not True:
        failures.append("the confirmatory window does not forbid ranking or re-tuning on it")
    if boundary.get("window_overlap_with_v1_holdout") != "forbidden":
        failures.append("the confirmatory window does not forbid v1 holdout overlap")
    if boundary.get("v1_holdout_reuse") != "forbidden":
        failures.append("the v1 holdout reuse is not forbidden")
    if boundary.get("data_used_for_candidate_selection") != "excluded":
        failures.append("the confirmatory window is not excluded from candidate selection")
    if not str(boundary.get("access_counting") or "").strip():
        failures.append("the confirmatory window does not record the exposure counting rule")
    if not str(boundary.get("evaluation_only_after") or "").strip():
        failures.append("the confirmatory window does not state what must exist before evaluation")

    # 6. The selection remainder is outstanding and bound to the unchanged v1 rule.
    remainder = freeze.get("selection_remainder") or {}
    if remainder.get("status") != "OUTSTANDING":
        failures.append("the selection remainder is not recorded as outstanding")
    if remainder.get("may_not_change_the_frozen_candidate_set") is not True:
        failures.append("the selection remainder may change the frozen candidate set")
    if remainder.get("must_be_hash_bound_before_first_confirmatory_read") is not True:
        failures.append("the selected-configuration manifest is not required before the first read")
    if remainder.get("max_candidates_per_asset") != spec["selection"]["max_candidates_per_asset"]:
        failures.append("the selection remainder does not use the unchanged selection block")
    if spec.get("selection") != spec_v1.get("selection"):
        failures.append("the v2 specification no longer inherits the v1 selection block unchanged")

    # 7. Nothing is authorized by this artifact.
    execution = freeze.get("execution_authorization") or {}
    for flag in (
        "grid_run_authorized",
        "candidate_selection_authorized",
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
    ):
        if execution.get(flag) is not False:
            failures.append(f"execution_authorization.{flag} is not false")
    if freeze.get("freeze_status") != "CANDIDATE_SET_FROZEN_NO_EXECUTION":
        failures.append("the freeze status does not record that nothing was executed")

    # 8. Supersession of the v1 candidate manifest.
    supersedes = freeze.get("supersedes") or {}
    if supersedes.get("protocol_version") != "v1":
        failures.append("the freeze does not supersede the v1 candidate manifest")
    if supersedes.get("candidate_manifest_path") != "research/candidate_manifest.json":
        failures.append("the supersedes block does not name the v1 candidate manifest")
    if supersedes.get("candidate_manifest_sha256") != sha256_file(repo_root / "research" / "candidate_manifest.json"):
        failures.append("the superseded v1 candidate manifest does not match its recorded sha256")
    if supersedes.get("candidate_manifest_hash") != v1_candidates.get("manifest_hash"):
        failures.append("the superseded v1 candidate manifest hash does not match the manifest")
    if v1_candidates.get("frozen") is not True:
        failures.append("the superseded v1 candidate manifest is not frozen")
    not_a_v2 = supersedes.get("not_a_v2_universe_candidate_manifest") or {}
    if not_a_v2.get("path") != "research/candidate_manifest_v2.json":
        failures.append("the freeze does not record the v1-campaign manifest_version 2 artifact")
    if not_a_v2.get("sha256") != sha256_file(repo_root / "research" / "candidate_manifest_v2.json"):
        failures.append("the recorded manifest_version 2 digest does not match the file")
    if not_a_v2.get("manifest_version") != v1_candidates_v2.get("manifest_version"):
        failures.append("the recorded manifest_version does not match the v1-campaign artifact")
    remainder_text = canonical(
        {key: value for key, value in freeze.items() if key != "supersedes"}
    )
    if "research/candidate_manifest_v2.json" in remainder_text:
        failures.append("the v1-campaign manifest_version 2 artifact is referenced outside the supersedes block")

    # 9. Nothing has been executed and nothing is exposed.
    for relative in V2_EXECUTION_ARTIFACTS:
        if (repo_root / relative).exists():
            failures.append(f"a v2 execution artifact exists: {relative}")
    results_path = repo_root / "research" / "results.jsonl"
    if results_path.exists():
        with results_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                if b"v2-campaign" in chunk:
                    failures.append("the v1 results file contains v2 campaign rows")
                    break
    window = data.get("confirmatory_window") or {}
    if window.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is not marked NOT_STARTED")

    # 10. The v1 evidence is byte-identical.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")

    # 11. The related artifacts are the ones that are recorded.
    related = freeze.get("related_artifacts") or {}
    expected_related = {
        "v2_specification": ("configs/research_v2.json", spec.get("specification_hash")),
        "v2_execution_protocol": (
            "configs/research_v2_execution.json",
            protocol.get("specification_hash"),
        ),
        "v2_universe_manifest": (
            "research/universe_manifest_v2.json",
            universe.get("manifest_hash"),
        ),
        "v2_data_manifest": ("research/data_manifest_v2.json", data.get("manifest_hash")),
    }
    for key, (relative, digest) in expected_related.items():
        entry = related.get(key) or {}
        if entry.get("path") != relative:
            failures.append(f"related_artifacts.{key} does not point at {relative}")
        if entry.get("specification_hash", entry.get("manifest_hash")) != digest:
            failures.append(f"related_artifacts.{key} records a hash that does not match {relative}")
    snapshot_entry = related.get("v2_raw_snapshot") or {}
    if snapshot_entry.get("sha256") != sha256_file(repo_root / SNAPSHOT_RAW_RELATIVE):
        failures.append("the recorded market-cap snapshot digest does not match the stored bytes")

    # 12. The code-hash constraint names only genuinely outside paths.
    constraint = freeze.get("code_hash_constraint") or {}
    if constraint.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the code-hash constraint does not name the hashed source root")
    for relative in constraint.get("inside_hashed_set_examples") or []:
        if not path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as inside the hashed set but is not")
    for relative in constraint.get("outside_hashed_set_examples") or []:
        if path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as outside the hashed set but is inside it")

    return {
        "ok": not failures,
        "freeze_path": str(freeze_path.relative_to(repo_root)),
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "candidate_freeze_timestamp_utc": freeze.get("candidate_freeze_timestamp_utc"),
        "confirmatory_window_start_utc": boundary.get("confirmatory_window_start_utc"),
        "frozen_candidates": frozen_constituents,
        "excluded_assets": dict(sorted(recorded_exclusions.items())),
        "snapshot_identity": identity,
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

#!/usr/bin/env python3
"""Read-only, offline verification of the v3 candidate-freeze amendment 1.

The verifier recomputes every expectation from the repository: it never trusts
a digest that is copied out of the artifact it is checking. It exits 0 when the
amendment is consistent with the frozen v3 artifacts and 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from v3_benchmark_amendment_common import v3_execution_state_failures  # noqa: E402

AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
SPEC_RELATIVE = "configs/research_v3.json"
EXCLUSION_AMENDMENT_RELATIVE = "configs/research_v3_exclusion_amendment_1.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
SPOT_EVIDENCE_RELATIVE = "research/v3_evidence/binance_spot_verification.json"
CANDLE_EVIDENCE_RELATIVE = "research/v3_evidence/candle_verification.json"

#: The v1 artifacts whose bytes must not have changed.
V1_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

#: The paths a v3 execution run creates. Their state is checked against the
#: v3 selection authorization, not against their mere existence.
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

    amendment_path = repo_root / "configs" / "research_v3_candidate_freeze_amendment_1.json"
    for relative in (FREEZE_RELATIVE, SPEC_RELATIVE, EXCLUSION_AMENDMENT_RELATIVE,
                     UNIVERSE_RELATIVE, DATA_RELATIVE, SPOT_EVIDENCE_RELATIVE,
                     CANDLE_EVIDENCE_RELATIVE):
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}
    if not amendment_path.exists():
        return {"ok": False, "failures": ["missing artifact: the v3 candidate-freeze amendment 1"]}

    amendment = read_json(amendment_path)
    freeze = read_json(repo_root / FREEZE_RELATIVE)
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)

    # 1. the amendment is self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the frozen freeze is byte-identical and still carries its own hash
    recorded_freeze = amendment.get("problem", {}).get("affected_artifact_manifest_hash")
    if recorded_freeze != freeze.get("manifest_hash"):
        failures.append("the amendment does not record the frozen artifact's current manifest_hash")
    freeze_sha = sha256_file(repo_root / FREEZE_RELATIVE)
    if amendment.get("related_artifacts", {}).get("v3_candidate_freeze", {}).get("file_sha256") != freeze_sha:
        failures.append("the recorded sha256 of the frozen candidate freeze does not match the file")

    # 3. the validated set is exactly the validated assets of the universe manifest
    assets = universe.get("eligible_assets") or []
    expected_validated = [
        entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        for entry in sorted(assets, key=lambda item: int(item.get("rank") or 0))
        if entry.get("validated")
    ]
    recorded_validated = [
        member.get("binance_pair")
        for member in amendment.get("validated_candidate_set", {}).get("members") or []
    ]
    if recorded_validated != expected_validated:
        failures.append(
            f"the validated candidate set does not match the universe manifest: "
            f"{recorded_validated} != {expected_validated}"
        )

    # 4. the excluded set is exactly the excluded assets, with the same reasons
    expected_excluded = {
        (entry.get("binance_pair") or f"{entry.get('symbol')}USDT"): entry.get("exclusion_reason")
        for entry in assets
        if not entry.get("validated")
    }
    recorded_excluded = {
        member.get("binance_pair"): member.get("exclusion_reason")
        for member in amendment.get("excluded_candidates", {}).get("members") or []
    }
    if recorded_excluded != expected_excluded:
        failures.append(
            "the excluded candidates or their reasons do not match the universe manifest: "
            f"{recorded_excluded} != {expected_excluded}"
        )
    for pair, reason in recorded_excluded.items():
        if reason not in ALLOWED_VALIDATION_EXCLUSION_REASONS:
            failures.append(f"{pair}: exclusion reason {reason!r} is outside the frozen vocabulary")

    # 5. the exclusion reasons agree with the data manifest's validation results
    validation_results = data.get("validation_results") or {}
    for pair, reason in recorded_excluded.items():
        result = validation_results.get(pair) or {}
        if result.get("exclusion_reason") != reason:
            failures.append(f"{pair}: the data manifest records a different exclusion reason")

    # 6. the shortfall arithmetic
    shortfall = amendment.get("shortfall", {})
    derived_batch = freeze.get("frozen_candidate_set", {}).get("binance_pairs") or []
    if int(shortfall.get("derived_batch_size") or -1) != len(derived_batch):
        failures.append("the recorded derived batch size does not match the frozen artifact")
    if int(shortfall.get("validated_count") or -1) != len(expected_validated):
        failures.append("the recorded validated count does not match the universe manifest")
    if int(shortfall.get("shortfall") or -1) != max(0, len(derived_batch) - len(expected_validated)):
        failures.append("the recorded shortfall does not add up")
    if shortfall.get("no_backfill") is not True:
        failures.append("the amendment does not record that no substitute candidate was admitted")

    # 7. the manifest hashes are recomputed from the files on disk
    for key, relative in (("universe_manifest", UNIVERSE_RELATIVE),
                           ("data_manifest", DATA_RELATIVE)):
        block = amendment.get("validation_evidence", {}).get(key) or {}
        if block.get("manifest_hash") != (universe if key == "universe_manifest" else data).get(
            "manifest_hash"
        ):
            failures.append(f"{key}: the amendment records a different manifest_hash")
        if block.get("file_sha256") != sha256_file(repo_root / relative):
            failures.append(f"{key}: the recorded file sha256 does not match the file")

    # 8. the evidence files are the ones the validation wrote
    for key, relative in (("binance_spot_verification", SPOT_EVIDENCE_RELATIVE),
                           ("candle_verification", CANDLE_EVIDENCE_RELATIVE)):
        block = amendment.get("validation_evidence", {}).get(key) or {}
        if block.get("file_sha256") != sha256_file(repo_root / relative):
            failures.append(f"{key}: the recorded file sha256 does not match the file")

    # 9. every validated member's dataset exists, hashes and holds the required candles
    datasets = dict(data.get("assets") or {})
    for member in amendment.get("validated_candidate_set", {}).get("members") or []:
        pair = member.get("binance_pair")
        dataset_path = member.get("dataset_path")
        if not dataset_path or not (repo_root / dataset_path).exists():
            failures.append(f"{pair}: the recorded dataset does not exist")
            continue
        recorded = datasets.get(pair) or {}
        if recorded.get("content_hash") != member.get("content_hash"):
            failures.append(f"{pair}: the dataset content hash does not match the data manifest")
        rows = (repo_root / dataset_path).read_text(encoding="utf-8").strip().splitlines()
        if len(rows) - 1 != MIN_CANDLES:
            failures.append(f"{pair}: the dataset does not hold exactly {MIN_CANDLES} candles")
        if rows and int(rows[1].split(",")[0]) % HOUR_MS != 0:
            failures.append(f"{pair}: the first candle is not aligned to an hour")
        if rows and int(rows[-1].split(",")[0]) % HOUR_MS != 0:
            failures.append(f"{pair}: the last candle is not aligned to an hour")
        recorded_dataset = next(
            (entry for entry in (amendment.get("validation_evidence", {}).get("datasets") or [])
             if entry.get("binance_pair") == pair), None)
        if recorded_dataset is None:
            failures.append(f"{pair}: the amendment records no dataset evidence")
        elif recorded_dataset.get("file_sha256") != sha256_file(repo_root / dataset_path):
            failures.append(f"{pair}: the recorded dataset sha256 does not match the file")

    # 10. the data boundary is unchanged by the amendment
    boundary = amendment.get("data_boundary", {})
    if boundary.get("window_moved_by_this_amendment") is not False:
        failures.append("the amendment does not state that the window was not moved")
    freeze_boundary = freeze.get("data_boundary", {})
    for key in ("confirmatory_window_start_utc", "min_confirmatory_window_hours",
                "earliest_possible_confirmatory_window_end_utc"):
        if boundary.get(key) != freeze_boundary.get(key):
            failures.append(f"the amendment changed the frozen {key}")

    # 11. the amendment authorizes nothing
    if amendment.get("execution_authorization", {}).get("execution_authorized") is not False:
        failures.append("execution_authorization.execution_authorized is not false")
    if amendment.get("execution_authorization", {}).get("grid_run_authorized") is not False:
        failures.append("execution_authorization.grid_run_authorized is not false")

    # 12. the prerequisite status is recorded and honest
    status = amendment.get("prerequisite_status", {})
    if status.get("P2") != "DELIVERED_BY_REFERENCE" or status.get("P3") != "DELIVERED_BY_REFERENCE":
        failures.append("the amendment does not record P2 and P3 as delivered")
    if status.get("P5") != "OUTSTANDING" or status.get("P6") != "OUTSTANDING":
        failures.append("the amendment does not record P5 and P6 as outstanding")

    # 13. the v1 evidence is byte-identical
    for relative in V1_ANCHORS:
        recorded = (amendment.get("related_artifacts", {}).get("v1_anchors") or {}).get(relative)
        if recorded != sha256_file(repo_root / relative):
            failures.append(f"the v1 anchor for {relative} does not match the file")

    # 14. nothing has run under v3
    # The rule "a v3 execution artifact exists" was replaced, not deleted: it
    # was true while the v3 selection run had not been performed. The
    # replacement is state-adaptive and stronger: the v3 execution state must
    # be consistent with the v3 selection authorization.
    failures.extend(v3_execution_state_failures(repo_root))
    window = data.get("confirmatory_window") or {}
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not NOT_STARTED")
    if int(window.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v3 confirmatory window records a non-zero holdout exposure")

    # 15. the specification and the exclusion amendment are the ones the chain names
    if amendment.get("related_artifacts", {}).get("v3_specification", {}).get(
        "specification_hash"
    ) != spec.get("specification_hash"):
        failures.append("the amendment does not bind the current v3 specification")
    exclusion_amendment = read_json(repo_root / EXCLUSION_AMENDMENT_RELATIVE)
    if amendment.get("related_artifacts", {}).get("v3_exclusion_amendment", {}).get(
        "amendment_hash"
    ) != exclusion_amendment.get("amendment_hash"):
        failures.append("the amendment does not bind the current v3 exclusion amendment")

    return {
        "ok": not failures,
        "failures": failures,
        "manifest_hash": declared,
        "validated_candidates": expected_validated,
        "excluded_count": len(expected_excluded),
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

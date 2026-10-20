#!/usr/bin/env python3
"""Read-only, offline verification of the v3 candidate-freeze amendment 2.

The amendment re-binds the data-manifest identity of the frozen candidate set
to the effective data manifest. The verifier recomputes the effective identity
independently, checks that the frozen artifact and the amendment 1 are
byte-unchanged, checks that the candidate set and the data boundary are
unchanged, and checks that the amendment authorizes nothing.

The rule that checks the selection authorization is state-adaptive and is never
weaker than the state it replaces. The cascade authorizes nothing by itself and
the selection authorization is a separate, versioned artifact: while it does
not exist, no v3 run is authorized; once it exists, it must be the hash-bound
artifact that permits exactly one bounded selection run over the frozen
candidate set, with the published benchmark dataset, the effective
data-manifest identity and the deviation disclosure bound into it. The former
"a v3 selection authorization exists" check was replaced -- not deleted -- by
that stronger check.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from v3_benchmark_amendment_common import selection_authorization_failures  # noqa: E402

AMENDMENT_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
DATA_AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"

V1_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

V3_EXECUTION_PATHS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
    "research/v3_selected_configurations_manifest.json",
)

BENCHMARK_SYMBOL = "BTCUSDT"


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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def effective_data_manifest_hash(base: Dict[str, Any], entry: Dict[str, Any],
                                  source: str) -> str:
    """The effective data-manifest identity, recomputed independently."""
    body = copy.deepcopy(base)
    body.pop("manifest_hash", None)
    snapshot = body.get("snapshot_identity")
    if isinstance(snapshot, dict):
        snapshot.pop("data_manifest_hash", None)
    body.setdefault("assets", {})[BENCHMARK_SYMBOL] = copy.deepcopy(entry)
    body.setdefault("content_hashes", {})[BENCHMARK_SYMBOL] = entry["content_hash"]
    body["benchmark_asset"] = {
        "symbol": BENCHMARK_SYMBOL,
        "role": "trend_filter_and_benchmark",
        "included_in_universe": True,
        "is_candidate": False,
        "content_hash": entry["content_hash"],
        "dataset_path": entry["dataset_path"],
        "first_candle_timestamp": entry["first_candle_timestamp"],
        "last_candle_timestamp": entry["last_candle_timestamp"],
        "observed_candle_count": entry["observed_candle_count"],
        "source": source,
        "alignment_rule": (
            "the benchmark series and the asset series are aligned by UTC candle close: "
            "both are sliced to the same fold window before the frozen engine is called, "
            "and no observation is forward-filled"
        ),
    }
    return compute_manifest_hash(body, ("manifest_hash", "snapshot_identity.data_manifest_hash"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    for relative in (AMENDMENT_RELATIVE, DATA_AMENDMENT_RELATIVE, FREEZE_RELATIVE,
                     FREEZE_AMENDMENT_1_RELATIVE, DATA_MANIFEST_RELATIVE, UNIVERSE_RELATIVE):
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    amendment = read_json(root / AMENDMENT_RELATIVE)
    data_amendment = read_json(root / DATA_AMENDMENT_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    freeze_amendment_1 = read_json(root / FREEZE_AMENDMENT_1_RELATIVE)
    base = read_json(root / DATA_MANIFEST_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)

    # 1. the amendment is self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the frozen artifact and amendment 1 are byte-unchanged
    problem = amendment.get("problem") or {}
    if problem.get("affected_artifact_manifest_hash") != freeze.get("manifest_hash"):
        failures.append("the amendment does not record the frozen artifact's current manifest_hash")
    if problem.get("affected_artifact_sha256") != sha256_file(root / FREEZE_RELATIVE):
        failures.append("the recorded sha256 of the frozen candidate freeze does not match the file")
    related = amendment.get("related_artifacts") or {}
    if (related.get("v3_candidate_freeze_amendment_1") or {}).get("manifest_hash") != \
            freeze_amendment_1.get("manifest_hash"):
        failures.append("the amendment does not bind the current candidate-freeze amendment 1")

    # 3. the re-bound identity is the recomputed effective identity
    entry = (data_amendment.get("benchmark_asset") or {}).get("entry") or {}
    recomputed_effective = effective_data_manifest_hash(base, entry, DATA_AMENDMENT_RELATIVE)
    rebound = amendment.get("rebound_identity") or {}
    if rebound.get("effective_data_manifest_hash") != recomputed_effective:
        failures.append(
            "the re-bound identity does not recompute: recorded "
            f"{rebound.get('effective_data_manifest_hash')}, recomputed {recomputed_effective}"
        )
    if rebound.get("superseded_data_manifest_hash") != freeze.get(
        "snapshot_identity", {}
    ).get("data_manifest_hash"):
        failures.append("the amendment does not record the identity it supersedes")
    if rebound.get("base_data_manifest_hash") != base.get("manifest_hash"):
        failures.append("the re-bound identity is not bound to the base data manifest")

    # 4. the candidate set is unchanged: the validated set of the universe manifest
    expected_pairs = [
        entry.get("binance_pair") or f"{entry.get('symbol')}USDT"
        for entry in sorted(universe.get("eligible_assets") or [],
                            key=lambda item: int(item.get("rank") or 0))
        if entry.get("validated")
    ]
    recorded_pairs = list((amendment.get("frozen_candidate_set") or {}).get("binance_pairs") or [])
    if recorded_pairs != expected_pairs:
        failures.append(
            f"the candidate set differs from the validated set of the universe manifest: "
            f"{recorded_pairs} != {expected_pairs}"
        )
    if (amendment.get("frozen_candidate_set") or {}).get("unchanged_by_this_amendment") is not True:
        failures.append("the amendment does not record that the candidate set is unchanged")
    if BENCHMARK_SYMBOL in recorded_pairs:
        failures.append("the benchmark joined the candidate set")

    # 5. the data boundary is unchanged
    freeze_boundary = freeze.get("data_boundary") or {}
    boundary = amendment.get("data_boundary") or {}
    for key in ("confirmatory_window_start_utc", "min_confirmatory_window_hours",
                "earliest_possible_confirmatory_window_end_utc"):
        if boundary.get(key) != freeze_boundary.get(key):
            failures.append(f"the amendment changed the frozen {key}")
    if boundary.get("window_moved_by_this_amendment") is not False:
        failures.append("the amendment does not state that the window was not moved")

    # 6. the benchmark block names the published dataset
    benchmark = amendment.get("benchmark_asset") or {}
    published = data_amendment.get("benchmark_asset") or {}
    for key in ("symbol", "content_hash", "dataset_path", "first_candle_timestamp",
                "last_candle_timestamp", "observed_candle_count"):
        if benchmark.get(key) != published.get(key):
            failures.append(f"the benchmark block differs from the published entry: {key}")
    if benchmark.get("is_candidate") is not False:
        failures.append("the benchmark is not recorded as a non-candidate")

    # 7. the alignment rule is recorded
    alignment = amendment.get("alignment_rule") or {}
    if "UTC candle close" not in str(alignment.get("methodology") or ""):
        failures.append("the amendment does not bind the frozen alignment methodology")
    for key in ("rule", "fail_closed", "grid_rule"):
        if not alignment.get(key):
            failures.append(f"the amendment records no alignment {key}")

    # 8. the v1 evidence is byte-identical
    for relative in V1_ANCHORS:
        if (related.get("v1_anchors") or {}).get(relative) != sha256_file(root / relative):
            failures.append(f"the v1 anchor for {relative} does not match the file")

    # 9. the amendment authorizes nothing
    authorization = amendment.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        failures.append("execution_authorization.execution_authorized is not false")
    if authorization.get("grid_run_authorized") is not False:
        failures.append("execution_authorization.grid_run_authorized is not false")
    failures.extend(selection_authorization_failures(root))

    # 10. nothing has run under v3
    for relative in V3_EXECUTION_PATHS:
        if (root / relative).exists():
            failures.append(f"a v3 execution artifact exists: {relative}")
    window_block = base.get("confirmatory_window") or {}
    if window_block.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not NOT_STARTED")
    if int(window_block.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v3 confirmatory window records a non-zero holdout exposure")

    return {
        "ok": not failures,
        "failures": failures,
        "manifest_hash": declared,
        "effective_data_manifest_hash": rebound.get("effective_data_manifest_hash"),
        "candidate_set": recorded_pairs,
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

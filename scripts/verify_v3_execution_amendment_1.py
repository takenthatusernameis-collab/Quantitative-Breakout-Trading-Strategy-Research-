#!/usr/bin/env python3
"""Read-only, offline verification of the v3 execution amendment 1.

The amendment records the benchmark rule and re-binds the data-manifest
identity of the v3 evaluation scope. The verifier recomputes the effective
identity independently, checks that the execution protocol is byte-unchanged,
checks that the evaluation scope and the benchmark rule are consistent with the
published benchmark entry, and checks that the amendment authorizes nothing.
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

AMENDMENT_RELATIVE = "configs/research_v3_execution_amendment_1.json"
DATA_AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
EXECUTION_RELATIVE = "configs/research_v3_execution.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
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
MIN_CANDLES = 26280


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

    for relative in (AMENDMENT_RELATIVE, DATA_AMENDMENT_RELATIVE, FREEZE_AMENDMENT_2_RELATIVE,
                     EXECUTION_RELATIVE, DATA_MANIFEST_RELATIVE):
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    amendment = read_json(root / AMENDMENT_RELATIVE)
    data_amendment = read_json(root / DATA_AMENDMENT_RELATIVE)
    freeze_amendment_2 = read_json(root / FREEZE_AMENDMENT_2_RELATIVE)
    execution = read_json(root / EXECUTION_RELATIVE)
    base = read_json(root / DATA_MANIFEST_RELATIVE)

    # 1. the amendment is self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the execution protocol is byte-unchanged
    problem = amendment.get("problem") or {}
    if problem.get("affected_artifact_specification_hash") != execution.get("specification_hash"):
        failures.append("the amendment does not record the protocol's current specification_hash")
    if problem.get("affected_artifact_sha256") != sha256_file(root / EXECUTION_RELATIVE):
        failures.append("the recorded sha256 of the execution protocol does not match the file")

    # 3. the re-bound identity is the recomputed effective identity
    entry = (data_amendment.get("benchmark_asset") or {}).get("entry") or {}
    recomputed_effective = effective_data_manifest_hash(base, entry, DATA_AMENDMENT_RELATIVE)
    scope = amendment.get("evaluation_scope") or {}
    if scope.get("data_manifest_hash") != recomputed_effective:
        failures.append(
            "the re-bound identity does not recompute: recorded "
            f"{scope.get('data_manifest_hash')}, recomputed {recomputed_effective}"
        )
    if scope.get("superseded_data_manifest_hash") != execution.get(
        "evaluation_scope", {}
    ).get("data_manifest_hash"):
        failures.append("the amendment does not record the identity it supersedes")
    if (amendment.get("related_artifacts") or {}).get(
        "v3_candidate_freeze_amendment_2", {}
    ).get("manifest_hash") != freeze_amendment_2.get("manifest_hash"):
        failures.append("the amendment does not bind the current candidate-freeze amendment 2")

    # 4. the evaluation scope is unchanged
    protocol_scope = execution.get("evaluation_scope") or {}
    if list(scope.get("constituents") or []) != list(protocol_scope.get("constituents") or []):
        failures.append("the evaluation scope differs from the execution protocol")
    if int(scope.get("count") or -1) != int(protocol_scope.get("count") or -2):
        failures.append("the evaluation scope count differs from the execution protocol")
    if scope.get("unchanged_by_this_amendment") is not True:
        failures.append("the amendment does not record that the scope is unchanged")
    if scope.get("widening_by_reranking_forbidden") is not True:
        failures.append("the amendment does not forbid widening the scope by re-ranking")

    # 5. the benchmark rule names the published dataset and the recomputed hash
    rule = amendment.get("benchmark_rule") or {}
    published = data_amendment.get("benchmark_asset") or {}
    for key in ("symbol", "dataset_path", "content_hash", "first_candle_timestamp",
                "last_candle_timestamp", "observed_candle_count"):
        if rule.get(key) != published.get(key):
            failures.append(f"the benchmark rule differs from the published entry: {key}")
    dataset_path = root / str(rule.get("dataset_path") or "")
    if not dataset_path.exists():
        failures.append("the benchmark dataset does not exist")
    else:
        rows = dataset_path.read_text(encoding="utf-8").strip().splitlines()[1:]
        if len(rows) != MIN_CANDLES:
            failures.append(f"the benchmark dataset does not hold exactly {MIN_CANDLES} candles")
        if sha256_file(dataset_path) != rule.get("content_hash"):
            failures.append("the benchmark content hash does not match the dataset file")
    for key in ("alignment", "fail_closed", "grid_rule", "exposure_rule"):
        if not rule.get(key):
            failures.append(f"the benchmark rule records no {key}")
    if rule.get("no_forward_fill") is not True:
        failures.append("the benchmark rule does not forbid forward filling")

    # 6. the code-hash constraint keeps the execution path outside the hashed set
    constraint = amendment.get("code_hash_constraint") or {}
    if constraint.get("v3_execution_must_live_outside_hashed_set") is not True:
        failures.append("the code-hash constraint does not require an execution path outside the hashed set")
    if constraint.get("edit_under_src_breakout_research_forbidden_without_reauthorization") is not True:
        failures.append("the code-hash constraint does not forbid editing the hashed set")
    if constraint.get("v3_execution_root") != "src/v3_campaign":
        failures.append("the code-hash constraint names an unexpected v3 execution root")
    if constraint.get("authorized_code_hash") != execution.get(
        "code_hash_constraint", {}
    ).get("authorized_code_hash"):
        failures.append("the amendment records a different authorized code hash")

    # 7. the deviation disclosure agrees with the published one
    disclosure = amendment.get("deviation_disclosure") or {}
    published_disclosure = data_amendment.get("deviation_disclosure") or {}
    for key in ("records_with_btc_filter", "total_v2_records", "misaligned_validation_folds"):
        if disclosure.get(key) != published_disclosure.get(key):
            failures.append(f"the deviation disclosure differs from the published one: {key}")

    # 8. the v1 evidence is byte-identical
    for relative in V1_ANCHORS:
        if (amendment.get("related_artifacts") or {}).get("v1_anchors", {}).get(relative) != \
                sha256_file(root / relative):
            failures.append(f"the v1 anchor for {relative} does not match the file")

    # 9. the amendment authorizes nothing
    authorization = amendment.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        failures.append("execution_authorization.execution_authorized is not false")
    if authorization.get("grid_run_authorized") is not False:
        failures.append("execution_authorization.grid_run_authorized is not false")
    if (root / AUTHORIZATION_RELATIVE).exists():
        failures.append("a v3 selection authorization exists")

    # 10. nothing has run under v3 and the confirmatory window is untouched
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
        "effective_data_manifest_hash": scope.get("data_manifest_hash"),
        "evaluation_scope": scope.get("constituents"),
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

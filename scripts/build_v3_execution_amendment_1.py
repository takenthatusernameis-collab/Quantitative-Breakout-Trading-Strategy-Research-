#!/usr/bin/env python3
"""Build the v3 execution amendment 1 (benchmark rule and re-bound identity).

BRAIN-013 requires the v3 execution protocol to name the benchmark dataset,
its content hash, the alignment rule and the fail-closed behaviour, and to
bind the effective data-manifest identity instead of the base manifest's
identity. The execution protocol itself is hash-bound and is **not** edited in
place.

The amendment authorizes no run: the v3 selection authorization does not exist
yet, and this session performs no grid, backtest, campaign or selection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_benchmark_amendment_common import (  # noqa: E402
    DATA_AMENDMENT_1_RELATIVE,
    DATA_MANIFEST_RELATIVE,
    EXECUTION_AMENDMENT_1_RELATIVE,
    EXECUTION_RELATIVE,
    FREEZE_AMENDMENT_1_RELATIVE,
    FREEZE_AMENDMENT_2_RELATIVE,
    FREEZE_RELATIVE,
    SPEC_RELATIVE,
    UNIVERSE_MANIFEST_RELATIVE,
    compute_manifest_hash,
    read_json,
    sha256_file,
    v1_anchor_digests,
)

HASHED_SET_ROOT = "src/breakout_research"
V3_EXECUTION_ROOT = "src/v3_campaign"


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.",
            suffix=".tmp", delete=False, newline=""
        ) as handle:
            temporary_path = handle.name
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def build(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root)
    execution = read_json(root / EXECUTION_RELATIVE)
    data_amendment = read_json(root / DATA_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = read_json(root / FREEZE_AMENDMENT_2_RELATIVE)
    spec = read_json(root / SPEC_RELATIVE)

    effective_hash = data_amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    benchmark = data_amendment["benchmark_asset"]
    evaluation_scope = execution["evaluation_scope"]

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_BENCHMARK_RULE_NO_AUTHORIZATION",
        "artifact": "v3_execution_amendment_1",
        "artifact_version": 1,
        "created_utc": "2026-10-20T15:45:00Z",
        "problem": {
            "statement": (
                "the v3 execution protocol binds the identity of research/data_manifest_v3.json "
                "and does not mention the benchmark constituent that the v3 universe declares "
                "and that a quarter of the inherited grid needs."
            ),
            "affected_artifact_path": EXECUTION_RELATIVE,
            "affected_artifact_specification_hash": execution.get("specification_hash"),
            "affected_artifact_sha256": sha256_file(root / EXECUTION_RELATIVE),
            "repair": (
                "the execution protocol is hash-bound and is not edited in place; the "
                "benchmark rule and the re-bound identity are recorded by this amendment"
            ),
        },
        "evaluation_scope": {
            "count": evaluation_scope["count"],
            "constituents": list(evaluation_scope["constituents"]),
            "unchanged_by_this_amendment": True,
            "rule": (
                "the evaluated scope is the frozen candidate set; the benchmark is not a "
                "candidate and does not widen the scope"
            ),
            "candidate_freeze_path": FREEZE_RELATIVE,
            "candidate_freeze_hash": evaluation_scope["candidate_freeze_hash"],
            "candidate_freeze_amendment_path": FREEZE_AMENDMENT_1_RELATIVE,
            "candidate_freeze_amendment_hash": evaluation_scope["candidate_freeze_amendment_hash"],
            "candidate_freeze_amendment_2_path": FREEZE_AMENDMENT_2_RELATIVE,
            "candidate_freeze_amendment_2_hash": freeze_amendment_2.get("manifest_hash"),
            "universe_manifest_path": UNIVERSE_MANIFEST_RELATIVE,
            "universe_manifest_hash": evaluation_scope["universe_manifest_hash"],
            "data_manifest_path": DATA_MANIFEST_RELATIVE,
            "superseded_data_manifest_hash": evaluation_scope["data_manifest_hash"],
            "data_manifest_hash": effective_hash,
            "widening_by_reranking_forbidden": True,
            "excluded_assets_stay_excluded": True,
        },
        "benchmark_rule": {
            "symbol": benchmark["symbol"],
            "role": benchmark["role"],
            "dataset_path": benchmark["dataset_path"],
            "content_hash": benchmark["content_hash"],
            "first_candle_timestamp": benchmark["first_candle_timestamp"],
            "last_candle_timestamp": benchmark["last_candle_timestamp"],
            "observed_candle_count": benchmark["observed_candle_count"],
            "alignment": (
                "the asset series and the benchmark series are sliced to the same fold "
                "window before the frozen engine is called, so that the engine's index "
                "pairing equals the UTC-candle-close alignment of "
                "docs/research_protocol.md:101"
            ),
            "no_forward_fill": True,
            "fail_closed": [
                "the benchmark series is missing",
                "the benchmark series is shorter than the evaluated window",
                "the benchmark series is not index-aligned with the asset series",
            ],
            "grid_rule": (
                "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                "re-derived or re-ranked"
            ),
            "exposure_rule": (
                "the benchmark dataset is development data; it lies entirely before the "
                "confirmatory window and no confirmatory-window candle is read"
            ),
            "source": DATA_AMENDMENT_1_RELATIVE,
        },
        "code_hash_constraint": {
            "hashed_source_root": HASHED_SET_ROOT,
            "v3_execution_root": V3_EXECUTION_ROOT,
            "v3_execution_must_live_outside_hashed_set": True,
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
            "authorized_code_hash": execution["code_hash_constraint"]["authorized_code_hash"],
            "identity_rule": (
                "the identity of a source tree is its canonical source digest -- the "
                "sha256 over the POSIX relative path and the content digest of every *.py "
                "file in ascending path order -- and never the checkout-dependent ordered "
                "digest compute_code_hash() (BRAIN-009)"
            ),
        },
        "deviation_disclosure": {
            "statement": (
                "the completed v1 and v2 runs evaluated the BTC trend filter under the "
                "frozen engine's index pairing; the deviation is a disclosure for the final "
                "report and is not repaired"
            ),
            "records_with_btc_filter": data_amendment["deviation_disclosure"]["records_with_btc_filter"],
            "total_v2_records": data_amendment["deviation_disclosure"]["total_v2_records"],
            "misaligned_validation_folds":
                data_amendment["deviation_disclosure"]["misaligned_validation_folds"],
            "evidence_path": data_amendment["deviation_disclosure"]["evidence_path"],
        },
        "precedence": {
            "rule": (
                "the effective data-manifest identity of the v3 evaluation scope is the one "
                "recorded by this amendment; the base manifest's identity is superseded by "
                "reference only"
            ),
            "superseded": ["evaluation_scope.data_manifest_hash"],
            "unchanged": [
                "evaluation_scope.constituents",
                "evaluation_scope.count",
                "selection_data_boundary",
                "selection_rule",
                "resource_and_attempt_bounds",
                "candidate_freeze_and_confirmatory_window",
                "v3_result_layout",
                "stopping_conditions_rollback_falsifiers",
            ],
            "resolution_rule": (
                "a verifier that reads the v3 evaluation scope resolves the data-manifest "
                "identity through this amendment when the amendment is present and verified"
            ),
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "selection_authorization_present": False,
            "scope": (
                "this amendment records the benchmark rule and the re-bound identity. It "
                "authorizes no run, no evaluation and no confirmatory-window read."
            ),
        },
        "related_artifacts": {
            "v1_anchors": v1_anchor_digests(root),
            "v3_specification": {
                "path": SPEC_RELATIVE,
                "specification_hash": spec.get("specification_hash"),
            },
            "v3_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "specification_hash": execution.get("specification_hash"),
            },
            "v3_data_manifest_amendment_1": {
                "path": DATA_AMENDMENT_1_RELATIVE,
                "manifest_hash": data_amendment.get("manifest_hash"),
                "effective_data_manifest_hash": effective_hash,
            },
            "v3_candidate_freeze_amendment_2": {
                "path": FREEZE_AMENDMENT_2_RELATIVE,
                "manifest_hash": freeze_amendment_2.get("manifest_hash"),
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": read_json(root / DATA_MANIFEST_RELATIVE).get("manifest_hash"),
            },
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-013",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-013",
            "stage": "stage 1 (the benchmark dataset and the amendment cascade)",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": ["manifest_hash"],
            "note": "manifest_hash is the sha256 of the document body with manifest_hash removed.",
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, ("manifest_hash",))
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="rewrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    document = build(repo_root)
    target = repo_root / EXECUTION_AMENDMENT_1_RELATIVE
    if args.print_only:
        print(json.dumps(document, indent=2, sort_keys=True))
        return 0
    if target.exists() and not args.force:
        print(json.dumps({
            "ok": False,
            "reason": "the amendment already exists; pass --force to rewrite it",
            "manifest_hash": document["manifest_hash"],
        }, indent=2, sort_keys=True))
        return 1
    atomic_write_json(target, document)
    print(json.dumps({
        "ok": True,
        "path": EXECUTION_AMENDMENT_1_RELATIVE,
        "manifest_hash": document["manifest_hash"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

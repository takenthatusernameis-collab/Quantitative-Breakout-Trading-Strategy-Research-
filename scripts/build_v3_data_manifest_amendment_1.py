#!/usr/bin/env python3
"""Build the v3 data-manifest amendment 1 (the published benchmark entry).

BRAIN-013 Design A: the v3 universe declares ``BTCUSDT`` as its benchmark
constituent and a quarter of the inherited grid needs the BTC series, but the
v3 data manifest holds no dataset for it. The data manifest is hash-bound by
the freeze amendment 1 and by the execution protocol, so it is **not** edited
in place: this amendment publishes the benchmark entry and states the
*effective* data-manifest identity that the v3 chain is bound to.

The producer recomputes every fact from the repository: the benchmark entry
from the retrieved dataset itself, the alignment from the dataset files, and
the effective identity from the base manifest plus the published entry. It
refuses to overwrite an existing artifact without ``--force``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_benchmark_amendment_common import (  # noqa: E402
    DATA_AMENDMENT_1_RELATIVE,
    DATA_MANIFEST_RELATIVE,
    EVIDENCE_RELATIVE,
    EXECUTION_RELATIVE,
    FREEZE_AMENDMENT_1_RELATIVE,
    FREEZE_RELATIVE,
    RAW_RESPONSE_RELATIVE,
    SPEC_RELATIVE,
    UNIVERSE_MANIFEST_RELATIVE,
    alignment_report,
    benchmark_entry,
    compute_manifest_hash,
    effective_data_manifest_hash,
    read_json,
    sha256_file,
    v1_anchor_digests,
)

DEVIATION_RELATIVE = "research/v3_evidence/v1_v2_btc_alignment_deviation.json"


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
    """The amendment document, recomputed from the repository."""
    root = Path(repo_root)
    base = read_json(root / DATA_MANIFEST_RELATIVE)
    universe = read_json(root / UNIVERSE_MANIFEST_RELATIVE)
    spec = read_json(root / SPEC_RELATIVE)
    evidence = read_json(root / EVIDENCE_RELATIVE)

    entry = benchmark_entry(root)
    alignment = alignment_report(root, base, entry)
    if not alignment["index_aligned"]:
        raise SystemExit(
            "the benchmark dataset is not index-aligned with the evaluated v3 assets: "
            f"{alignment['misaligned_assets']}"
        )

    effective_hash = effective_data_manifest_hash(base, entry, DATA_AMENDMENT_1_RELATIVE)
    deviation = read_json(root / DEVIATION_RELATIVE)

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_BENCHMARK_ENTRY_NO_AUTHORIZATION",
        "artifact": "v3_data_manifest_amendment_1",
        "artifact_version": 1,
        "created_utc": evidence["retrieval_timestamp_utc"],
        "problem": {
            "statement": (
                "research/universe_manifest_v3.json declares BTCUSDT as the benchmark "
                "constituent (benchmark_asset.included_in_universe = true) and the v1 "
                "methodology requires BTC as the trend-filter input, but "
                "research/data_manifest_v3.json holds no dataset for it, while 576 of the "
                "2,304 inherited configurations per asset need the BTC series."
            ),
            "affected_artifact_manifest_hash": base.get("manifest_hash"),
            "affected_artifact_path": DATA_MANIFEST_RELATIVE,
            "affected_artifact_sha256": sha256_file(root / DATA_MANIFEST_RELATIVE),
            "grid_configurations_requiring_the_btc_series": 576,
            "grid_configurations_total": 2304,
            "repair": (
                "the data manifest is hash-bound by the freeze amendment 1 and by the "
                "execution protocol, so it is not edited in place; the benchmark entry is "
                "published by this amendment and the effective identity is re-bound by the "
                "freeze amendment 2 and the execution amendment 1"
            ),
        },
        "benchmark_asset": {
            "symbol": entry["symbol"],
            "role": "trend_filter_and_benchmark",
            "included_in_universe": True,
            "is_candidate": False,
            "is_candidate_note": (
                "the benchmark is not a member of the frozen candidate set; it is the "
                "trend-filter input of the inherited grid, as in v1"
            ),
            "content_hash": entry["content_hash"],
            "dataset_path": entry["dataset_path"],
            "first_candle_timestamp": entry["first_candle_timestamp"],
            "last_candle_timestamp": entry["last_candle_timestamp"],
            "observed_candle_count": entry["observed_candle_count"],
            "entry": entry,
        },
        "retrieval_evidence": {
            "evidence_path": EVIDENCE_RELATIVE,
            "evidence_sha256": sha256_file(root / EVIDENCE_RELATIVE),
            "raw_response_path": RAW_RESPONSE_RELATIVE,
            "raw_response_sha256": sha256_file(root / RAW_RESPONSE_RELATIVE),
            "raw_response_bytes": int((evidence.get("raw_response") or {}).get("bytes") or 0),
            "raw_response_row_count": int((evidence.get("raw_response") or {}).get("row_count") or 0),
            "retrieval_timestamp_utc": evidence.get("retrieval_timestamp_utc"),
            "retrieval_started_utc": evidence.get("retrieval_started_utc"),
            "http_status_of_each_probed_host": dict(
                evidence.get("http_status_of_each_probed_host") or {}
            ),
            "endpoint_used": evidence.get("endpoint_used"),
            "endpoints_used": list(evidence.get("endpoints_used") or []),
            "endpoint_failures": list(evidence.get("endpoint_failures") or []),
            "request_count": int(evidence.get("request_count") or 0),
            "policy": (
                "one bounded retrieval of one asset under the v3 window rule through the "
                "frozen primary -> failover policy; the raw response, its sha256 and the "
                "retrieval timestamp are recorded"
            ),
        },
        "alignment_rule": {
            "methodology": "docs/research_protocol.md:101 - Align BTC and target asset by UTC candle close",
            "rule": (
                "the asset series and the benchmark series are sliced to the same fold "
                "window before the frozen engine is called, so that the engine's index "
                "pairing equals the UTC-candle-close alignment; no observation is "
                "forward-filled and no value is interpolated"
            ),
            "fail_closed": (
                "the v3 execution path refuses to run when the benchmark series is "
                "missing, shorter than the evaluated window or not index-aligned with the "
                "asset series"
            ),
            "grid_rule": (
                "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                "re-derived or re-ranked"
            ),
            "index_alignment": alignment,
        },
        "effective_data_manifest": {
            "base_manifest_path": DATA_MANIFEST_RELATIVE,
            "base_manifest_hash": base.get("manifest_hash"),
            "base_manifest_sha256": sha256_file(root / DATA_MANIFEST_RELATIVE),
            "effective_data_manifest_hash": effective_hash,
            "effective_asset_count": len((base.get("assets") or {})) + 1,
            "effective_content_hash_count": len((base.get("content_hashes") or {})) + 1,
            "hashing_rule": (
                "the effective identity is the sha256 over the canonical JSON of the base "
                "manifest body -- with manifest_hash and snapshot_identity.data_manifest_hash "
                "removed -- plus the published benchmark entry in assets and content_hashes "
                "and the benchmark_asset block"
            ),
            "note": (
                "the effective view is materialized by the v3 execution path at run time "
                "from the base manifest and this amendment; no file carries it"
            ),
        },
        "deviation_disclosure": {
            "statement": (
                "the completed v1 and v2 runs evaluated the BTC trend filter under the "
                "frozen engine's index pairing, not under the UTC-candle-close alignment "
                "the frozen methodology requires"
            ),
            "records_with_btc_filter": int((deviation.get("counts") or {}).get("records_with_btc_filter") or 0),
            "total_v2_records": int((deviation.get("counts") or {}).get("total_v2_records") or 0),
            "share_of_records": (deviation.get("counts") or {}).get("share_of_records"),
            "misaligned_validation_folds": list(
                (deviation.get("counts") or {}).get("misaligned_validation_folds") or []
            ),
            "evidence_path": DEVIATION_RELATIVE,
            "evidence_sha256": sha256_file(root / DEVIATION_RELATIVE),
            "correction": (
                "BRAIN-013 recorded that fold 0 was aligned and that 93,312 of 497,664 v2 "
                "records were affected; recomputation from the frozen fold rule shows that "
                "the first validation fold already starts 40% of the way into the history, "
                "so no validation fold was aligned and the affected count is 124,416"
            ),
            "repair": (
                "none: the completed runs are immutable and are not re-run; the deviation "
                "is a disclosure for the final report"
            ),
        },
        "precedence": {
            "rule": (
                "the effective data manifest of universe version v3 is "
                "research/data_manifest_v3.json plus the benchmark entry published by this "
                "amendment"
            ),
            "base_manifest_edited": False,
            "superseded": [],
            "unchanged": [
                "research/data_manifest_v3.json",
                "research/universe_manifest_v3.json",
                "configs/research_v3_candidate_freeze.json",
                "configs/research_v3_candidate_freeze_amendment_1.json",
                "configs/research_v3_execution.json",
            ],
            "resolution_rule": (
                "a verifier that reads the v3 datasets resolves them through this "
                "amendment and refuses a benchmark entry that is not index-aligned with "
                "the evaluated assets"
            ),
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "selection_authorization_present": False,
            "scope": (
                "this amendment publishes a dataset and an identity. It authorizes no run, "
                "no evaluation and no confirmatory-window read."
            ),
        },
        "related_artifacts": {
            "v1_anchors": v1_anchor_digests(root),
            "v3_specification": {
                "path": SPEC_RELATIVE,
                "specification_hash": spec.get("specification_hash"),
            },
            "v3_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
                "benchmark_asset": universe.get("benchmark_asset"),
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": base.get("manifest_hash"),
            },
            "v3_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": read_json(root / FREEZE_RELATIVE).get("manifest_hash"),
            },
            "v3_candidate_freeze_amendment_1": {
                "path": FREEZE_AMENDMENT_1_RELATIVE,
                "manifest_hash": read_json(root / FREEZE_AMENDMENT_1_RELATIVE).get("manifest_hash"),
            },
            "v3_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "specification_hash": read_json(root / EXECUTION_RELATIVE).get("specification_hash"),
            },
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-013",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-013",
            "design": "Design A - publish a v3-bound benchmark dataset and align by UTC candle close",
            "sections_implemented_here": [
                "BRAIN-013 D-2: the benchmark dataset is hash-verified and index-aligned",
                "BRAIN-013 D-4: the alignment rule follows the frozen methodology",
                "BRAIN-013 D-7: the provider dependency is bounded and recorded",
                "BRAIN-013 D-8: the v1/v2 deviation is disclosed with its exact count",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v3 selection run and the v3 selection authorization",
                "the v3 confirmatory-window evaluation",
            ],
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
    target = repo_root / DATA_AMENDMENT_1_RELATIVE
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
        "path": DATA_AMENDMENT_1_RELATIVE,
        "manifest_hash": document["manifest_hash"],
        "effective_data_manifest_hash":
            document["effective_data_manifest"]["effective_data_manifest_hash"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

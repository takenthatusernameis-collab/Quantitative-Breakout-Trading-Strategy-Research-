#!/usr/bin/env python3
"""Build the v4 execution amendment 1 (the performed run and its publication).

The v4 execution protocol (``configs/research_v4_execution.json``) is hash-bound and
is **not** edited in place: it was written before the run, names the evaluation scope
and the benchmark rule, and authorizes nothing.  The run that it bounds happened
afterwards, so the amendment records the identity of the performed run and binds the
published selection outcome into the v4 line.

Every value in the amendment is **re-derived** from the repository: the run identity
and the code identity come from the run ledger, the evaluation scope from the
execution protocol and the candidate freeze, the benchmark rule from the execution
protocol, and the published manifest's hash from the published manifest itself.  A
hand-written digest would not be caught by the self-hash of the document, which is
exactly the failure this producer exists to prevent.

The amendment authorizes nothing: it starts no run, evaluates no confirmatory window
and reads no candle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

EXECUTION_RELATIVE = "configs/research_v4_execution.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v4_execution_amendment_1.json"
SELECTION_MANIFEST_RELATIVE = "research/v4_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v4.json"
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_V4_RELATIVE = "research/universe_manifest_v4.json"
DATA_V4_RELATIVE = "research/data_manifest_v4.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"
SELECTION_AUTH_RELATIVE = "configs/research_v4_selection_authorization_1.json"

#: The creation instant is pinned so that the artifact is byte-reproducible.
CREATED_UTC = "2026-10-21T07:40:00Z"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys=("manifest_hash",)) -> str:
    body = {key: value for key, value in document.items() if key not in set(excluded_keys)}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


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
    """Build the v4 execution amendment 1 from the repository."""
    root = Path(repo_root)
    execution = read_json(root / EXECUTION_RELATIVE)
    ledger = read_json(root / LEDGER_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    selection_manifest = read_json(root / SELECTION_MANIFEST_RELATIVE)
    selection_auth = read_json(root / SELECTION_AUTH_RELATIVE)
    universe = read_json(root / UNIVERSE_V4_RELATIVE)
    data_manifest = read_json(root / DATA_V4_RELATIVE)

    # -- the run identity comes from the ledger, never from a literal -------
    code_identity = ledger.get("code_identity") or {}
    run_id = str(ledger.get("run_id"))
    campaign_id = str(ledger.get("campaign_id"))
    authorization_hash = str(ledger.get("authorization_manifest_hash"))
    if authorization_hash != str(selection_auth.get("manifest_hash")):
        raise ValueError(
            "the ledger is not bound to the selection authorization's manifest hash")
    if ledger.get("status") != "COMPLETED":
        raise ValueError("the ledger does not record a completed run")

    # -- the evaluation scope comes from the execution protocol ------------
    evaluation = execution.get("evaluation_scope") or {}
    candidates = [str(pair) for pair in evaluation.get("constituents") or []]
    published_pairs = [str(pair) for pair in (selection_manifest.get("scope") or {})
                       .get("frozen_candidate_set", {}).get("binance_pairs") or []]
    if sorted(candidates) != sorted(published_pairs):
        raise ValueError(
            "the execution protocol's evaluation scope differs from the published "
            "selection manifest's frozen candidate set")

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_PERFORMED_RUN_NO_AUTHORIZATION",
        "artifact": "v4_execution_amendment_1",
        "artifact_version": 1,
        "amends": {
            "file": EXECUTION_RELATIVE,
            "manifest_hash": execution.get("manifest_hash"),
            "rule": (
                "the v4 execution protocol is hash-bound and is not edited in place; this "
                "amendment records the performed run and the published selection outcome"
            ),
        },
        "created_utc": CREATED_UTC,
        "problem": {
            "statement": (
                "the v4 execution protocol was written before the run and names the "
                "evaluation scope and the benchmark rule, but it cannot name the identity "
                "of a run that had not happened yet."
            ),
            "affected_artifact_path": EXECUTION_RELATIVE,
            "affected_artifact_manifest_hash": execution.get("manifest_hash"),
            "affected_artifact_sha256": sha256_file(root / EXECUTION_RELATIVE),
            "repair": (
                "the execution protocol is hash-bound and is not edited in place; the "
                "performed run's identity and the published selection outcome are recorded "
                "by this amendment"
            ),
        },
        "evaluation_scope": {
            "count": evaluation.get("count"),
            "constituents": candidates,
            "candidate_freeze_path": FREEZE_RELATIVE,
            "candidate_freeze_hash": freeze.get("manifest_hash"),
            "universe_manifest_path": UNIVERSE_V4_RELATIVE,
            "universe_manifest_hash": universe.get("manifest_hash"),
            "data_manifest_path": DATA_V4_RELATIVE,
            "data_manifest_hash": data_manifest.get("manifest_hash"),
            "excluded_assets_stay_excluded": True,
            "widening_by_reranking_forbidden": True,
            "unchanged_by_this_amendment": True,
            "rule": (
                "the evaluated scope is the frozen candidate set; the benchmark is not a "
                "candidate and does not widen the scope"
            ),
        },
        "benchmark_rule": execution.get("benchmark_rule") or {},
        "code_hash_constraint": execution.get("code_hash_constraint") or {},
        "performed_run": {
            "run_id": run_id,
            "campaign_id": campaign_id,
            "status": ledger.get("status"),
            "ledger_path": LEDGER_RELATIVE,
            "shards_path": f"research/shards_v4/{campaign_id}",
            "results_manifest_path": "research/results_manifest_v4.json",
            "results_stream_path": "research/results_v4.jsonl",
            "checkpoint_path": "research_state/checkpoint_v4.json",
            "authorization_manifest_hash": authorization_hash,
            "run_code_identity": code_identity.get("run_code_identity"),
            "execution_path_digest": code_identity.get("execution_path_digest"),
            "hashed_set_digest": code_identity.get("hashed_set_digest"),
            "authorized_code_hash": code_identity.get("authorized_code_hash"),
            "code_identity_algorithm": code_identity.get("algorithm"),
            "specification_hash": ledger.get("specification_hash"),
            "selection_block_sha256": (ledger.get("selection") or {}).get(
                "selection_block_sha256"),
            "records_written": (ledger.get("counts") or {}).get("records_written"),
            "execution_units": (ledger.get("counts") or {}).get("execution_units"),
            "holdout_exposed_count": ledger.get("holdout_exposed_count"),
            "started_utc": ledger.get("started_utc"),
            "completed_utc": ledger.get("completed_utc"),
        },
        "selection_manifest": {
            "path": SELECTION_MANIFEST_RELATIVE,
            "manifest_hash": selection_manifest.get("manifest_hash"),
            "outcome": selection_manifest.get("outcome"),
            "assets_with_candidate": selection_manifest.get("assets_with_candidate"),
            "assets_without_candidate": selection_manifest.get("assets_without_candidate"),
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "second_run_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "scope": (
                "this amendment records the performed run and its published outcome. It "
                "authorizes no run, no second run, no evaluation and no confirmatory-window "
                "read."
            ),
        },
        "precedence": {
            "rule": (
                "the performed run and the published selection outcome of the v4 line are "
                "the ones recorded by this amendment; the execution protocol's own "
                "authorization flags stay false and are not superseded"
            ),
            "superseded": [],
            "unchanged": [
                "evaluation_scope.constituents",
                "evaluation_scope.count",
                "candidate_freeze_and_confirmatory_window",
                "benchmark_rule",
                "code_hash_constraint",
            ],
            "resolution_rule": (
                "a verifier that reads the v4 evaluation scope or the performed run resolves "
                "the identity through this amendment when the amendment is present and "
                "verified"
            ),
        },
        "related_artifacts": {
            "v4_execution_protocol": {
                "path": EXECUTION_RELATIVE,
                "manifest_hash": execution.get("manifest_hash"),
            },
            "v4_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v4_selection_authorization": {
                "path": SELECTION_AUTH_RELATIVE,
                "manifest_hash": selection_auth.get("manifest_hash"),
            },
            "v4_universe_manifest": {
                "path": UNIVERSE_V4_RELATIVE,
                "manifest_hash": universe.get("manifest_hash"),
            },
            "v4_data_manifest": {
                "path": DATA_V4_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
            },
            "v4_specification": {
                "path": SPEC_V4_RELATIVE,
                "specification_hash": read_json(root / SPEC_V4_RELATIVE).get(
                    "specification_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": read_json(root / SPEC_V1_RELATIVE).get(
                    "specification_hash"),
            },
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-018",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-018",
            "stage": "stage 3 (the publication of the v4 selection outcome)",
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


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="rewrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print, write nothing")
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

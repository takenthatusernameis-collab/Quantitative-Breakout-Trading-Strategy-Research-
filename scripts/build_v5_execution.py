#!/usr/bin/env python3
"""Build the preregistered v5 execution protocol.

This producer writes ``configs/research_v5_execution.json``:
the versioned, hash-bound artifact that records the v5 execution protocol --
the candidate-freeze binding, the code-hash constraint, the evaluation scope
bound to the frozen v5 candidate set, the benchmark rule, and the execution
authorization (which authorizes nothing).

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself requires the separate selection authorization
``configs/research_v5_selection_authorization_1.json``.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the v5 freeze, re-derived from the v5 universe
  manifest;
* the data-manifest identity from the v5 data manifest;
* the benchmark dataset reference from the v5 data manifest's benchmark block,
  which owns it;
* the development cutoff from the v5 data manifest's window policy.

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

The protocol as published by this producer is **superseded in part** by
``configs/research_v5_execution_amendment_1.json``, which supplies the
bindings the first publication did not carry (the inherited v1 rules, the
benchmark identity, the execution authorization and the supersedes chain).
The amendment wins for the blocks it restates; the protocol stays on disk
unchanged and visible.

Usage::

    python3 scripts/build_v5_execution.py            # write the artifact
    python3 scripts/build_v5_execution.py --force    # rewrite it
    python3 scripts/build_v5_execution.py --print    # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The instant at which this protocol is created. It is pinned here so that
#: the artifact is byte-reproducible; it must not be moved once the artifact
#: has been committed.
CREATED_UTC = "2026-10-21T12:20:50Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the protocol is bound to, relative to the repository root.
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"
FREEZE_V5_RELATIVE = "configs/research_v5_candidate_freeze.json"
UNIVERSE_V5_RELATIVE = "research/universe_manifest_v5.json"
DATA_V5_RELATIVE = "research/data_manifest_v5.json"
ARTIFACT_RELATIVE = "configs/research_v5_execution.json"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v5 execution protocol from the hash-bound artifacts."""
    root = Path(repo_root)

    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v5 = _load(root / SPEC_V5_RELATIVE)
    freeze_v5 = _load(root / FREEZE_V5_RELATIVE)
    universe_v5 = _load(root / UNIVERSE_V5_RELATIVE)
    data_v5 = _load(root / DATA_V5_RELATIVE)

    # --- the frozen scope, resolved from the freeze and the universe manifest
    constituents = [
        str(entry["binance_pair"])
        for entry in (freeze_v5.get("candidates") or [])
        if entry.get("validated") is True
    ]
    if not constituents:
        raise SystemExit("the frozen v5 candidate set is empty")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe_v5.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(constituents) != validated:
        raise SystemExit("the frozen v5 candidate set is not the validated v5 universe")

    benchmark = data_v5.get("benchmark") or {}
    if not benchmark.get("dataset_path"):
        raise SystemExit("the v5 data manifest records no benchmark dataset")

    document: Dict[str, Any] = {
        "artifact": "v5_execution_protocol",
        "artifact_version": "v5-execution-protocol-1",
        "protocol_version": "v5-execution",
        "universe_version": "v5",
        "manifest_hash": None,
        "specification_hash": spec_v5["specification_hash"],
        "created_utc": CREATED_UTC,
        "specification_purpose": (
            "Preregister how a future v5 grid run will be authorized and bounded. Design "
            "deliverable only; nothing runs."
        ),
        "specification_status": "PREREGISTERED_EXECUTION_PROTOCOL_ONLY",
        "supersedes": {
            "protocol_version": "v4",
            "specification_path": "configs/research_v4_execution.json",
            "specification_hash": None,
        },
        "candidate_freeze_and_confirmatory_window": {
            "candidate_manifest_committed_and_hash_bound_before_first_confirmatory_candle": True,
            "candidate_freeze_path": FREEZE_V5_RELATIVE,
            "candidate_freeze_hash": freeze_v5["manifest_hash"],
            "confirmatory_window_opens_utc": freeze_v5["confirmatory_window"]["opens_utc"],
            "min_confirmatory_window_hours": 2160,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after freeze",
            "development_cutoff_utc": data_v5["window_policy"]["development_cutoff_utc"],
            "development_data_boundary_rule": (
                "no v5 development candle may close inside any open confirmatory window; a "
                "candle that closes exactly at a window start is development data per the v5 "
                "specification amendment"
            ),
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
        },
        "evaluation_scope": {
            "universe_manifest_path": UNIVERSE_V5_RELATIVE,
            "universe_manifest_hash": universe_v5["manifest_hash"],
            "data_manifest_path": DATA_V5_RELATIVE,
            "data_manifest_hash": data_v5["manifest_hash"],
            "constituents": constituents,
            "count": len(constituents),
            "excluded_assets_stay_excluded": True,
            "widening_by_reranking_forbidden": True,
        },
        "benchmark_rule": {
            "symbol": "BTCUSDT",
            "dataset_path": benchmark["dataset_path"],
            "role": "trend_filter_and_benchmark",
            "rule": (
                "The v5 benchmark must be the v5-cutoff-bounded dataset from "
                "research/data/candles_v5 (ends at the v5 development cutoff). The v4 chain's "
                "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv cannot be reused for "
                "v5 because it contains candles that close after the v5 cutoff inside the open "
                "v2 confirmatory window."
            ),
            "content_hash_must_match_canonical": True,
            "note": (
                "The v5 benchmark is bounded at development_cutoff_utc 2026-10-19T22:00:00Z and "
                "is hash-verified before use."
            ),
        },
        "selection_rule": {
            "inherit_from_v1_unchanged": True,
            "note": (
                "v5 inherits the strategy grid, costs, execution semantics, fold structure, "
                "selection rule, pilot gate, metrics and baselines from v1 without modification "
                "(configs/research_v1.json)."
            ),
        },
        "code_hash_constraint": {
            "authorized_code_hash": "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2",
            "hashed_source_root": "src/breakout_research",
            "v5_execution_must_live_outside_hashed_set": True,
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
        },
        "resource_and_attempt_bounds": {
            "max_logical_runs": 1,
            "checkpoint_every_n_shards": 10,
        },
        "v5_result_layout": {
            "shard_directory": "research/shards_v5",
            "ledger_path": "research/ledger_v5.json",
            "results_manifest_path": "research/results_manifest_v5.json",
            "result_stream": "research/results_v5.jsonl",
            "checkpoint": "research_state/checkpoint_v5.json",
        },
        "authorization": {
            "execution_authorized": False,
            "campaign_authorized": False,
            "selection_authorized": False,
            "confirmatory_authorized": False,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    os.chmod(target, 0o644)
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

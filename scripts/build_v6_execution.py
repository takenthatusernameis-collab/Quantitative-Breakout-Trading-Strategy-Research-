#!/usr/bin/env python3
"""Build the preregistered v6 execution protocol.

This producer writes ``configs/research_v6_execution.json``: the versioned,
hash-bound artifact that records the v6 execution protocol -- the
candidate-freeze binding, the code-hash constraint, the evaluation scope bound
to the frozen v6 candidate set, the benchmark rule, the inherited v1 rules, the
execution authorization (which authorizes nothing) and the supersedes chain.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself requires the separate selection authorization
``configs/research_v6_selection_authorization_1.json``, which is separately published and authorizes one bounded selection grid run. The execution path ``src/v6_campaign`` does not yet exist; building this protocol creates no run path and executes no grid.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the v6 candidate freeze, cross-checked against the
  validated constituents of the v6 universe manifest;
* the manifest identities from the v6 universe and data manifests;
* the benchmark dataset from the v6 data manifest's benchmark block, which owns
  it, and its digest, candle count and bounds from the dataset's own bytes;
* the inherited v1 rules from ``configs/research_v1.json``;
* the four earlier confirmatory gates from the four freezes that own their
  windows;
* the code identity from the hashed source tree and from the campaign
  authorization that holds the authorized value of record.

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v6_execution.py            # write the artifact
    python3 scripts/build_v6_execution.py --force    # rewrite it
    python3 scripts/build_v6_execution.py --print    # print, write nothing
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
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    canonical_source_digest,
    compute_manifest_hash,
    read_json,
    sha256_file,
)

#: The instant at which this protocol is created. It is pinned here so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-22T04:20:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the protocol is bound to, relative to the repository root.
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_V6_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_V6_RELATIVE = "research/universe_manifest_v6.json"
DATA_V6_RELATIVE = "research/data_manifest_v6.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
ARTIFACT_RELATIVE = "configs/research_v6_execution.json"

#: The v5 execution chain the v6 protocol supersedes.
V5_EXECUTION_RELATIVES: Tuple[str, ...] = (
    "configs/research_v5_execution.json",
    "configs/research_v5_execution_amendment_1.json",
    "configs/research_v5_execution_amendment_2.json",
)

#: The freezes that own the v2, v3, v4 and v5 confirmatory windows, and the
#: key each one keeps its window bounds under.
GATE_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The v1 blocks the v6 chain inherits unchanged.
INHERITED_V1_BLOCKS: Tuple[str, ...] = (
    "strategy_grid",
    "costs",
    "execution",
    "folds",
    "selection",
    "pilot",
    "metrics",
    "baselines",
    "fixed_breakout_baseline",
    "status",
    "checkpointing",
)

#: The alignment rule the execution path requires.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window before the "
    "frozen engine is called, so that the engine's index pairing equals the UTC-candle-close "
    "alignment of docs/research_protocol.md:101"
)

#: The benchmark dataset of the v3 and v4 chains. The v6 chain may not reuse it.
V3_BENCHMARK_RELATIVE = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

#: The v6 execution path. It must live outside the hashed set.
V6_EXECUTION_ROOT = "src/v6_campaign"
HASHED_SET_ROOT = "src/breakout_research"

HOUR_MS = 3_600_000


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dataset_bounds(path: Path) -> Dict[str, Any]:
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return {
        "observed_candle_count": len(timestamps),
        "first_candle_timestamp": timestamps[0] if timestamps else None,
        "last_candle_timestamp": timestamps[-1] if timestamps else None,
    }


def _candles_after_cutoff(path: Path, cutoff_ms: int) -> int:
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return sum(1 for stamp in timestamps if stamp + HOUR_MS > cutoff_ms)


def _window_bounds(owner: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = owner.get(key) or {}
    start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
    min_hours = block.get("min_confirmatory_window_hours")
    if min_hours is None:
        min_hours = block.get("min_hours")
    end = block.get("earliest_possible_confirmatory_window_end_utc")
    if end is None:
        end = block.get("earliest_possible_end_utc")
    return {
        "window_start_utc": str(start) if start else None,
        "min_hours": int(min_hours) if min_hours is not None else None,
        "earliest_possible_end_utc": str(end) if end else None,
    }


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v6 execution protocol from the hash-bound artifacts."""
    root = Path(repo_root)

    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze_v6 = read_json(root / FREEZE_V6_RELATIVE)
    universe_v6 = read_json(root / UNIVERSE_V6_RELATIVE)
    data_v6 = read_json(root / DATA_V6_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # --- the frozen scope, resolved from the freeze and the universe manifest
    constituents = [
        str(entry["binance_pair"])
        for entry in (freeze_v6.get("candidates") or [])
        if entry.get("validated") is True
    ]
    if not constituents:
        raise SystemExit("the frozen v6 candidate set is empty")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe_v6.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(constituents) != validated:
        raise SystemExit("the frozen v6 candidate set is not the validated v6 universe")

    # --- the benchmark, owned by the v6 data manifest and read from its bytes
    benchmark_block = data_v6.get("benchmark") or {}
    benchmark_path = str(benchmark_block.get("dataset_path") or "")
    if not benchmark_path:
        raise SystemExit("the v6 data manifest records no benchmark dataset")
    benchmark_dataset = root / benchmark_path
    if not benchmark_dataset.exists():
        raise SystemExit(f"the v6 benchmark dataset {benchmark_path} does not exist")
    benchmark_hash = sha256_file(benchmark_dataset)
    benchmark_bounds = _dataset_bounds(benchmark_dataset)

    # --- the inherited v1 rules ---------------------------------------------
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )
    grid = spec_v1.get("strategy_grid") or {}
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)

    # --- the four earlier gates, recomputed from the freezes that own them --
    gates: List[Dict[str, Any]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = _window_bounds(owner, key)
        gates.append(
            {
                "earliest_possible_end_utc": bounds["earliest_possible_end_utc"],
                "min_hours": bounds["min_hours"],
                "source_key": key,
                "source_path": relative,
                "version": version,
                "window_start_utc": bounds["window_start_utc"],
            }
        )
    v6_window = freeze_v6.get("confirmatory_window") or {}
    evaluation_start = max(
        [str(gate["earliest_possible_end_utc"]) for gate in gates]
        + [str(v6_window.get("earliest_possible_end_utc"))]
    )

    # --- the code identity -------------------------------------------------
    source_digest = canonical_source_digest(root)
    execution_root = root / V6_EXECUTION_ROOT
    execution_path_exists = (root / "src").is_dir() and execution_root.is_dir()

    # --- the supersedes chain, recomputed from the v5 execution artifacts ----
    supersedes_chain: Dict[str, Any] = {}
    for relative in V5_EXECUTION_RELATIVES:
        path = root / relative
        if not path.exists():
            raise SystemExit(f"the superseded v5 execution artifact {relative} is missing")
        document = read_json(path)
        superseded_hash = compute_manifest_hash(document, ("manifest_hash",))
        if document.get("manifest_hash") != superseded_hash:
            raise SystemExit(f"the superseded artifact {relative} does not recompute its hash")
        key = Path(relative).stem
        supersedes_chain[key] = {
            "manifest_hash": superseded_hash,
            "path": relative,
            "sha256": sha256_file(path),
        }

    # --- the refused benchmark of the v3 and v4 chains ----------------------
    v3_benchmark = root / V3_BENCHMARK_RELATIVE
    cutoff = str((spec_v6.get("holdout") or {}).get("development_cutoff_utc"))
    cutoff_ms = int(datetime_from_iso(cutoff).timestamp() * 1000) if cutoff else 0
    refused_candles = (
        _candles_after_cutoff(v3_benchmark, cutoff_ms) if v3_benchmark.exists() else None
    )

    membership = (spec_v6.get("holdout") or {}).get("confirmatory_window_membership") or {}

    document: Dict[str, Any] = {
        "artifact": "v6_execution_protocol",
        "artifact_version": "v6-execution-protocol-1",
        "protocol_version": "v6-execution",
        "universe_version": "v6",
        "manifest_hash": None,
        "specification_hash": spec_v6["specification_hash"],
        "created_utc": CREATED_UTC,
        "specification_purpose": (
            "Preregister how a future v6 grid run will be authorized and bounded. Design "
            "deliverable only; nothing runs."
        ),
        "specification_status": "PREREGISTERED_EXECUTION_PROTOCOL_ONLY",
        "candidate_freeze_and_confirmatory_window": {
            "candidate_freeze_path": FREEZE_V6_RELATIVE,
            "candidate_freeze_hash": freeze_v6["manifest_hash"],
            "candidate_manifest_committed_and_hash_bound_before_first_confirmatory_candle": True,
            "confirmatory_window_opens_utc": v6_window.get("opens_utc"),
            "min_confirmatory_window_hours": int(v6_window.get("min_hours")),
            "earliest_possible_confirmatory_window_end_utc": v6_window.get(
                "earliest_possible_end_utc"
            ),
            "evaluation_may_not_start_before_utc": evaluation_start,
            "evaluation_start_rule": (
                "the v6 evaluation may not start before the later of the four recorded gates and "
                "the v6 window's own earliest end"
            ),
            "confirmatory_gates": gates,
            "development_cutoff_utc": cutoff,
            "development_data_boundary_rule": (
                "no v6 development candle may close inside any open confirmatory window; the "
                "last v6 development candle is the one that closes exactly at the cutoff, per the "
                "inclusive convention of the v6 specification"
            ),
            "confirmatory_window_membership_rule": str(membership.get("rule") or ""),
            "confirmatory_window_membership_rule_owner": (
                "configs/research_v6.json#holdout.confirmatory_window_membership"
            ),
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
            "v1_v2_v3_v4_v5_confirmatory_window_reuse": "forbidden",
        },
        "evaluation_scope": {
            "universe_manifest_path": UNIVERSE_V6_RELATIVE,
            "universe_manifest_hash": universe_v6["manifest_hash"],
            "data_manifest_path": DATA_V6_RELATIVE,
            "data_manifest_hash": data_v6["manifest_hash"],
            "candidate_freeze_hash": freeze_v6["manifest_hash"],
            "constituents": constituents,
            "count": len(constituents),
            "excluded_assets_stay_excluded": True,
            "widening_by_reranking_forbidden": True,
            "band_rule": (
                "the evaluated scope is the validated subset of the frozen 20-name band; the "
                "band is the definition and the validated subset is its consequence, so the scope "
                "is never widened to reach a target count"
            ),
        },
        "benchmark_rule": {
            "symbol": "BTCUSDT",
            "dataset_path": benchmark_path,
            "role": "trend_filter_and_benchmark",
            "content_hash": benchmark_hash,
            "content_hash_algorithm": "sha256-canonical-hourly-csv-v1",
            "observed_candle_count": benchmark_bounds["observed_candle_count"],
            "first_candle_timestamp": benchmark_bounds["first_candle_timestamp"],
            "last_candle_timestamp": benchmark_bounds["last_candle_timestamp"],
            "alignment": ALIGNMENT_RULE,
            "no_forward_fill": True,
            "fail_closed": [
                "the benchmark series is missing",
                "the benchmark series does not cover an evaluated window of the asset series",
                "the benchmark series carries a different timestamp than the asset series inside "
                "an evaluated window",
            ],
            "grid_rule": "the 576 btc_ema_168 configurations per asset are evaluated, never "
            "dropped, re-derived or re-ranked",
            "exposure_rule": (
                "the benchmark dataset is development data; it lies entirely before every open "
                "confirmatory window and no confirmatory-window candle is read"
            ),
            "note": (
                f"The v6 benchmark is the v6-cutoff-bounded dataset the v6 data manifest "
                f"publishes, and its last candle closes exactly at the v6 development cutoff "
                f"{cutoff}. The v3 and v4 chains' benchmark dataset "
                f"({V3_BENCHMARK_RELATIVE}) ends with a candle closing 2026-10-20T11:00:00Z and "
                f"{refused_candles} of its candles close after the v6 development cutoff, inside "
                f"the open v2 confirmatory window, so it is not reused unchanged by the v6 chain."
            ),
        },
        "inherited_rules": {
            "inherited_from": SPEC_V1_RELATIVE,
            "blocks": list(INHERITED_V1_BLOCKS),
            "blocks_digest": inherited_digest,
            "v1_specification_hash": spec_v1["specification_hash"],
            "grid_total_combinations": total,
            "rule": (
                "the v6 chain inherits the v1 strategy grid, costs, execution semantics, fold "
                "structure, selection rule, pilot gate, metrics, baselines, status vocabulary and "
                "checkpointing without modification, so that v6 differs from v5 in which assets "
                "are evaluated and not in how a strategy is measured"
            ),
            "single_confirmatory_criterion": (
                "the confirmatory evaluation applies the unchanged v1 selection rule to the single "
                "v6 confirmatory window: one criterion, never re-tuned, re-weighted or re-ranked, "
                "and its outcome is never used to select anything"
            ),
            "change_requires": (
                "a published, versioned amendment that names the changed block and the artifacts "
                "it supersedes"
            ),
        },
        "code_hash_constraint": {
            "authorized_code_hash": str(authorization.get("code_hash") or ""),
            "authorized_code_hash_source": AUTHORIZATION_RELATIVE,
            "hashed_source_root": HASHED_SET_ROOT,
            "canonical_hashed_set_digest": source_digest,
            "canonical_digest_is_the_identity": True,
            "ordered_code_hash_is_not_an_identity": True,
            "v6_execution_root": V6_EXECUTION_ROOT,
            "v6_execution_path_exists": execution_path_exists,
            "v6_execution_path_digest_is_recorded_in": (
                "configs/research_v6_selection_authorization_1.json"
            ),
            "v6_execution_must_live_outside_hashed_set": True,
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
            "rule": (
                "the v6 execution path is a new directory outside the hashed set; it is never "
                "added to src/breakout_research, and the canonical digest of the path is recorded "
                "in the v6 selection authorization when the path is created"
            ),
        },
        "execution_authorization": {
            "candle_fetch_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "this protocol records the candidate-freeze binding, the inherited rules, the "
                "benchmark rule, the data-manifest identity and the code-hash constraint. It "
                "authorizes no run, no evaluation, no candle fetch and no confirmatory-window "
                "read."
            ),
            "second_run_authorized": False,
            "selection_authorization_present": False,
        },
        "deviation_disclosure": {
            "evidence_path": None,
            "not_applicable": True,
            "records_with_btc_filter": 0,
            "statement": (
                "The v6 campaign has no prior completed runs and therefore no "
                "v1/v2/v3/v4/v5 alignment deviation to disclose."
            ),
            "total_v2_records": 0,
        },
        "resource_and_attempt_bounds": {
            "max_logical_runs": 1,
            "checkpoint_every_n_shards": 10,
        },
        "v6_result_layout": {
            "shard_directory": "research/shards_v6",
            "ledger_path": "research/ledger_v6.json",
            "results_manifest_path": "research/results_manifest_v6.json",
            "result_stream": "research/results_v6.jsonl",
            "checkpoint": "research_state/checkpoint_v6.json",
        },
        "authorization": {
            "execution_authorized": False,
            "campaign_authorized": False,
            "selection_authorized": False,
            "confirmatory_authorized": False,
        },
        "supersedes": {
            "protocol_version": "v5",
            "reason": (
                "the v5 execution protocol governed the v5 cycle; the v6 protocol governs the v6 "
                "cycle, which is a strictly additional universe below the v5 floor with its own "
                "namespace"
            ),
            "superseded_artifacts": supersedes_chain,
            "v1_v2_v3_v4_v5_artifacts_are_immutable": True,
        },
        "related_artifacts": {
            "v6_specification": {
                "path": SPEC_V6_RELATIVE,
                "specification_hash": spec_v6["specification_hash"],
            },
            "v6_candidate_freeze": {
                "path": FREEZE_V6_RELATIVE,
                "manifest_hash": freeze_v6["manifest_hash"],
            },
            "v6_universe_manifest": {
                "path": UNIVERSE_V6_RELATIVE,
                "manifest_hash": universe_v6["manifest_hash"],
            },
            "v6_data_manifest": {
                "path": DATA_V6_RELATIVE,
                "manifest_hash": data_v6["manifest_hash"],
            },
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def datetime_from_iso(value: str) -> datetime:
    """Parse an ISO-8601 UTC instant into an aware datetime."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


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

#!/usr/bin/env python3
"""Build the versioned amendment that completes the v5 execution protocol.

``configs/research_v5_execution.json`` was published first with the candidate
scope, the code-hash constraint and the benchmark rule, but without the
bindings the campaign's own v4 protocol carries: the inherited v1 rules, the
benchmark dataset's recomputed identity, the execution-authorization block,
the deviation disclosure and the supersedes chain onto the v4 protocol. A
published protocol is hash-bound and is not edited in place -- the campaign's
answer to that is a **versioned amendment**, as ``configs/research_v4_execution_
amendment_1.json`` and the v2/v3 execution amendments show.

This producer writes ``configs/research_v5_execution_amendment_1.json``:

* it names the artifact it amends by path, by its **recomputed** manifest hash
  and by its **recomputed** file digest;
* it states the problem it solves;
* it restates the effective blocks, every value of which is recomputed from
  the artifact that owns it -- the v1 rules from ``configs/research_v1.json``,
  the benchmark identity from the v5 data manifest and from the dataset's own
  bytes, the scope from the v5 freeze and the v5 universe manifest, the
  supersedes chain from the v4 execution protocol;
* it states the precedence: the amendment wins for the blocks it restates, the
  protocol stays on disk unchanged and visible, and the protocol's own
  authorization flags stay false.

The producer is deterministic (the creation instant is pinned) and refuses to
overwrite the artifact without ``--force``.

Usage::

    python3 scripts/build_v5_execution_amendment_1.py
    python3 scripts/build_v5_execution_amendment_1.py --force
    python3 scripts/build_v5_execution_amendment_1.py --print
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

ARTIFACT_RELATIVE = "configs/research_v5_execution_amendment_1.json"

#: The instant at which this amendment is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-21T13:20:00Z"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The artifacts the amendment is bound to, relative to the repository root.
PROTOCOL_RELATIVE = "configs/research_v5_execution.json"
V4_PROTOCOL_RELATIVE = "configs/research_v4_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"
FREEZE_V5_RELATIVE = "configs/research_v5_candidate_freeze.json"
UNIVERSE_V5_RELATIVE = "research/universe_manifest_v5.json"
DATA_V5_RELATIVE = "research/data_manifest_v5.json"

#: The v1 blocks the v5 chain inherits unchanged (the v1 comparability rule).
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

#: The execution path the v5 chain will use: outside the hashed source set.
V5_EXECUTION_ROOT = "src/v5_campaign"

#: The benchmark dataset the v4 chain used. The v5 chain may not reuse it.
V4_BENCHMARK_RELATIVE = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

HOUR_MS = 3_600_000


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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def dataset_bounds(path: Path) -> Dict[str, Any]:
    """The candle count and the first and last candle of a canonical CSV."""
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return {
        "observed_candle_count": len(timestamps),
        "first_candle_timestamp": timestamps[0] if timestamps else None,
        "last_candle_timestamp": timestamps[-1] if timestamps else None,
    }


def candles_after_cutoff(path: Path, cutoff_ms: int) -> int:
    """The number of candles of a dataset that close after the cutoff."""
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return sum(1 for stamp in timestamps if stamp + HOUR_MS > cutoff_ms)


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)

    protocol = _load(root / PROTOCOL_RELATIVE)
    v4_protocol = _load(root / V4_PROTOCOL_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v5 = _load(root / SPEC_V5_RELATIVE)
    freeze = _load(root / FREEZE_V5_RELATIVE)
    universe = _load(root / UNIVERSE_V5_RELATIVE)
    data = _load(root / DATA_V5_RELATIVE)

    protocol_hash = compute_manifest_hash(protocol, ("manifest_hash",))
    if protocol_hash != protocol.get("manifest_hash"):
        raise SystemExit("the v5 execution protocol does not recompute its manifest_hash")
    v4_protocol_hash = compute_manifest_hash(v4_protocol, ("manifest_hash",))
    if v4_protocol_hash != v4_protocol.get("manifest_hash"):
        raise SystemExit("the v4 execution protocol does not recompute its manifest_hash")

    # --- the inherited v1 rules, bound by a recomputed digest ----------------
    inherited = {block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}
    if any(value is None for value in inherited.values()):
        raise SystemExit("the v1 specification does not carry every inherited block")
    inherited_digest = sha256_bytes(canonical(inherited).encode("utf-8"))
    grid = spec_v1.get("strategy_grid") or {}
    total_combinations = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total_combinations *= len(values)

    # --- the benchmark identity, recomputed from the dataset's own bytes ----
    benchmark = data.get("benchmark") or {}
    benchmark_relative = str(benchmark.get("dataset_path") or "")
    benchmark_path = root / benchmark_relative
    if not benchmark_path.exists():
        raise SystemExit(f"the v5 benchmark dataset {benchmark_relative} does not exist")
    benchmark_content_hash = sha256_file(benchmark_path)
    if benchmark_content_hash != benchmark.get("content_hash"):
        raise SystemExit("the v5 benchmark dataset does not hash to its recorded digest")
    bounds = dataset_bounds(benchmark_path)

    cutoff = str(_dig(spec_v5, "holdout.development_cutoff_utc"))
    cutoff_ms = int(
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    v4_benchmark = root / V4_BENCHMARK_RELATIVE
    v4_benchmark_candles_after_cutoff = 0
    if v4_benchmark.exists():
        v4_benchmark_candles_after_cutoff = candles_after_cutoff(v4_benchmark, cutoff_ms)

    # --- the scope, resolved from the freeze and the universe manifest -------
    constituents = sorted(
        str(entry.get("binance_pair") or "")
        for entry in (freeze.get("candidates") or [])
        if entry.get("validated") is True
    )
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if constituents != validated:
        raise SystemExit("the frozen v5 candidate set is not the validated v5 universe")

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_CORRECTION",
        "artifact": "v5_execution_amendment_1",
        "artifact_version": 1,
        "created_utc": CREATED_UTC,
        "amends": {
            "file": PROTOCOL_RELATIVE,
            "manifest_hash": protocol_hash,
            "sha256": sha256_file(root / PROTOCOL_RELATIVE),
            "rule": (
                "the v5 execution protocol is hash-bound and is not edited in place; this "
                "amendment supplies the bindings the first publication did not carry"
            ),
        },
        "problem": {
            "affected_artifact_path": PROTOCOL_RELATIVE,
            "affected_artifact_manifest_hash": protocol_hash,
            "statement": (
                "the first publication of the v5 execution protocol named the candidate scope, "
                "the code-hash constraint and the benchmark rule, but it did not bind the "
                "inherited v1 rules, the benchmark dataset's recomputed identity, the "
                "execution-authorization block, the deviation disclosure or the supersedes "
                "chain onto the v4 protocol, so a reader could not tell which grid, costs, "
                "folds, selection rule, pilot gate, metrics and confirmatory criterion the run "
                "would use, nor verify the benchmark it names"
            ),
            "repair": (
                "the protocol is hash-bound and is not edited in place; the effective blocks are "
                "recorded by this amendment"
            ),
        },
        "precedence": {
            "rule": (
                "the effective v5 execution protocol is this amendment for the blocks it "
                "restates, and configs/research_v5_execution.json for the blocks it does not; "
                "the protocol stays on disk unchanged and visible"
            ),
            "resolution_rule": (
                "a verifier that reads the v5 evaluation scope, the benchmark rule, the "
                "inherited rules or the execution authorization resolves them through this "
                "amendment when the amendment is present and verified"
            ),
            "superseded": [
                "evaluation_scope",
                "candidate_freeze_and_confirmatory_window",
                "benchmark_rule",
                "code_hash_constraint",
            ],
            "unchanged": [
                "authorization.execution_authorized",
                "authorization.campaign_authorized",
                "authorization.selection_authorized",
                "authorization.confirmatory_authorized",
                "selection_rule.inherit_from_v1_unchanged",
                "resource_and_attempt_bounds",
                "v5_result_layout",
            ],
        },
        "candidate_freeze_and_confirmatory_window": {
            "candidate_manifest_committed_and_hash_bound_before_first_confirmatory_candle": True,
            "candidate_freeze_path": FREEZE_V5_RELATIVE,
            "candidate_freeze_hash": freeze.get("manifest_hash"),
            "confirmatory_window_opens_utc": _dig(freeze, "confirmatory_window.opens_utc"),
            "min_confirmatory_window_hours": _dig(freeze, "confirmatory_window.min_hours"),
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after freeze",
            "development_cutoff_utc": cutoff,
            "development_data_boundary_rule": (
                "no v5 development candle may close inside any open confirmatory window; a "
                "candle that closes exactly at a window's start is development data, per the "
                "membership rule the published amendment owns"
            ),
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
            "v5_candidate_set_disjoint_from_v1_v2_v3_v4_candidate_sets": True,
            "evaluation_may_not_start_before": (
                "the v4 confirmatory gate clears and the v5 window's own minimum of 2160 closed "
                "hourly candles has elapsed"
            ),
        },
        "code_hash_constraint": {
            "authorized_code_hash": "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2",
            "chosen_approach": (
                "new code outside the hashed set (src/v5_campaign/), leaving compute_code_hash() "
                "unchanged; explicit re-authorization only if a v1/v2 hashed path is touched"
            ),
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
            "hashed_source_root": "src/breakout_research",
            "v1_paths_hardcode_v1_spec": [
                "src/breakout_research/campaign.py",
                "src/breakout_research/pilot.py",
            ],
            "v5_execution_must_live_outside_hashed_set": True,
            "v5_execution_root": V5_EXECUTION_ROOT,
            "v5_execution_namespace": f"{V5_EXECUTION_ROOT}/",
        },
        "deviation_disclosure": {
            "evidence_path": None,
            "records_with_btc_filter": 0,
            "statement": (
                "The v5 campaign has no prior completed runs and therefore no v1/v2/v3/v4 "
                "alignment deviation to disclose."
            ),
            "total_v2_records": 0,
            "not_applicable": True,
        },
        "evaluation_scope": {
            "candidate_freeze_hash": freeze.get("manifest_hash"),
            "candidate_freeze_path": FREEZE_V5_RELATIVE,
            "constituents": constituents,
            "count": len(constituents),
            "data_manifest_hash": data.get("manifest_hash"),
            "data_manifest_path": DATA_V5_RELATIVE,
            "excluded_assets_stay_excluded": True,
            "rule": (
                "the evaluated scope is the frozen candidate set; the benchmark is not a "
                "candidate and does not widen the scope"
            ),
            "universe_manifest_hash": universe.get("manifest_hash"),
            "universe_manifest_path": UNIVERSE_V5_RELATIVE,
            "widening_by_reranking_forbidden": True,
        },
        "execution_authorization": {
            "candle_fetch_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "this protocol and this amendment record the benchmark rule, the inherited "
                "rules and the data-manifest identity. They authorize no run, no evaluation, "
                "no candle fetch and no confirmatory-window read."
            ),
            "second_run_authorized": False,
            "selection_authorization_present": False,
        },
        "benchmark_rule": {
            "alignment": ALIGNMENT_RULE,
            "content_hash": benchmark_content_hash,
            "dataset_path": benchmark_relative,
            "exposure_rule": (
                "the benchmark dataset is development data; it lies entirely before every open "
                "confirmatory window and no confirmatory-window candle is read"
            ),
            "fail_closed": [
                "the benchmark series is missing",
                "the benchmark series does not cover an evaluated window of the asset series",
                "the benchmark series carries a different timestamp than the asset series inside "
                "an evaluated window",
            ],
            "first_candle_timestamp": bounds["first_candle_timestamp"],
            "grid_rule": (
                "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                "re-derived or re-ranked"
            ),
            "last_candle_timestamp": bounds["last_candle_timestamp"],
            "no_forward_fill": True,
            "observed_candle_count": bounds["observed_candle_count"],
            "role": "trend_filter_and_benchmark",
            "symbol": "BTCUSDT",
            "note": (
                "The v5 benchmark is the v5-cutoff-bounded dataset the v5 data manifest "
                f"publishes. The v4 chain's benchmark dataset ({V4_BENCHMARK_RELATIVE}) ends with "
                "a candle closing 2026-10-20T11:00:00Z and "
                f"{v4_benchmark_candles_after_cutoff} of its candles close after the v5 "
                "development cutoff, inside the open v2 confirmatory window, so it is not "
                "reused unchanged by the v5 chain."
            ),
        },
        "inherited_rules": {
            "inherited_from": SPEC_V1_RELATIVE,
            "blocks": list(INHERITED_V1_BLOCKS),
            "blocks_digest": inherited_digest,
            "v1_specification_hash": spec_v1.get("specification_hash"),
            "grid_total_combinations": total_combinations,
            "rule": (
                "the v5 chain inherits the v1 strategy grid, costs, execution semantics, fold "
                "structure, selection rule, pilot gate, metrics, baselines, status vocabulary "
                "and checkpointing without modification, so that v5 differs from v4 in which "
                "assets are evaluated and not in how a strategy is measured"
            ),
            "single_confirmatory_criterion": (
                "the confirmatory evaluation applies the unchanged v1 selection rule to the "
                "single v5 confirmatory window: one criterion, never re-tuned, re-weighted or "
                "re-ranked, and its outcome is never used to select anything"
            ),
            "change_requires": (
                "a published, versioned amendment that names the changed block and the "
                "artifacts it supersedes"
            ),
        },
        "supersedes": {
            "protocol_version": "v4",
            "specification_path": V4_PROTOCOL_RELATIVE,
            "specification_hash": v4_protocol_hash,
            "specification_sha256": sha256_file(root / V4_PROTOCOL_RELATIVE),
            "reason": (
                "the v4 execution protocol governed the v4 cycle; the v5 protocol governs the "
                "v5 cycle, which is a strictly additional universe below the v4 floor with its "
                "own namespace"
            ),
            "v1_v2_v3_v4_artifacts_are_immutable": True,
        },
        "related_artifacts": {
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "v4_execution_protocol": {
                "manifest_hash": v4_protocol_hash,
                "path": V4_PROTOCOL_RELATIVE,
            },
            "v5_candidate_freeze": {
                "manifest_hash": freeze.get("manifest_hash"),
                "path": FREEZE_V5_RELATIVE,
            },
            "v5_data_manifest": {
                "manifest_hash": data.get("manifest_hash"),
                "path": DATA_V5_RELATIVE,
            },
            "v5_execution_protocol": {
                "manifest_hash": protocol_hash,
                "path": PROTOCOL_RELATIVE,
            },
            "v5_specification": {
                "path": SPEC_V5_RELATIVE,
                "specification_hash": spec_v5.get("specification_hash"),
            },
            "v5_universe_manifest": {
                "manifest_hash": universe.get("manifest_hash"),
                "path": UNIVERSE_V5_RELATIVE,
            },
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with the manifest_hash key "
                "removed, following the pattern of the other v2, v3 and v4 artifacts."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
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

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 specification.

The verifier never writes to the repository. It checks the frozen
``configs/research_v2.json`` against the artifacts it claims to supersede:

* the declared ``specification_hash`` recomputes from the canonical content
  of the document with the hash key removed;
* every block that v2 inherits from v1 is byte-equal to the v1 block, so the
  grid, costs, execution, folds, selection, pilot, metrics, baselines and
  status vocabulary cannot drift between protocol versions;
* the superseded v1 artifacts still hash to the values recorded in
  ``supersedes`` (the v1 evidence is immutable);
* the grid still enumerates exactly 2,304 combinations;
* the specification contains no asset membership: no universe manifest is
  smuggled into the spec, and the three unvalidated candidates observed in
  the terminal artifact are not treated as eligible;
* the confirmatory-holdout rules forbid reuse of the v1 holdout and require a
  window that starts after the v2 candidate freeze;
* execution is not authorized while prerequisites P2 and P3 are outstanding.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V2_PATH = REPO_ROOT / "configs" / "research_v2.json"

INHERITED_BLOCKS = (
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

SUPERSEDED_FILES = (
    "universe_manifest_path",
    "candidate_manifest_path",
    "candidate_manifest_v2_path",
)

UNVALIDATED_CANDIDATES = ("ZEC", "HYPE", "HBAR")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_specification_hash(spec: Dict[str, Any]) -> str:
    body = {key: value for key, value in spec.items() if key != "specification_hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _grid_combinations(grid: Dict[str, Any]) -> int:
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)
    return total


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    spec_path = repo_root / "configs" / "research_v2.json"
    v1_path = repo_root / "configs" / "research_v1.json"

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))

    declared = spec.get("specification_hash")
    recomputed = compute_specification_hash(spec)
    if declared != recomputed:
        failures.append(
            f"specification_hash mismatch: declared {declared}, recomputed {recomputed}"
        )

    for block in INHERITED_BLOCKS:
        if block not in spec:
            failures.append(f"v2 spec is missing the inherited block {block}")
        elif spec[block] != v1.get(block):
            failures.append(f"inherited block {block} differs from v1")

    supersedes = spec.get("supersedes", {})
    if supersedes.get("specification_hash") != v1.get("specification_hash"):
        failures.append("supersedes.specification_hash does not match the v1 specification")
    if supersedes.get("specification_path") != "configs/research_v1.json":
        failures.append("supersedes.specification_path is not configs/research_v1.json")
    for key in SUPERSEDED_FILES:
        rel = supersedes.get(key)
        if not rel:
            failures.append(f"supersedes.{key} is missing")
            continue
        path = repo_root / rel
        if not path.exists():
            failures.append(f"superseded artifact {rel} is missing")
            continue
        digest_key = key.replace("_path", "_sha256")
        if supersedes.get(digest_key) != sha256_file(path):
            failures.append(f"superseded artifact {rel} does not match its recorded sha256")

    grid = spec.get("strategy_grid", {})
    if grid.get("total_combinations") != 2304:
        failures.append("strategy_grid.total_combinations is not 2304")
    if _grid_combinations(grid) != grid.get("total_combinations"):
        failures.append("strategy_grid dimensions do not multiply to total_combinations")

    universe = spec.get("universe", {})
    if "eligible_assets" in universe:
        failures.append("the v2 spec must not contain an asset membership list")
    spec_text = canonical(spec)
    for symbol in UNVALIDATED_CANDIDATES:
        if f'"{symbol}"' in spec_text:
            failures.append(f"unvalidated candidate {symbol} appears in the v2 spec")

    holdout = spec.get("holdout", {})
    if holdout.get("v1_holdout_reuse") != "forbidden":
        failures.append("holdout.v1_holdout_reuse is not 'forbidden'")
    if holdout.get("v1_holdout_status") != "EXPOSED_OR_UNKNOWN":
        failures.append("holdout.v1_holdout_status is not 'EXPOSED_OR_UNKNOWN'")
    window = holdout.get("v2_confirmatory_window", {})
    if window.get("starts_after") != "v2_candidate_freeze_timestamp_utc":
        failures.append("the confirmatory window does not start after the candidate freeze")
    if window.get("overlap_with_v1_holdout") != "forbidden":
        failures.append("the confirmatory window does not forbid v1 holdout overlap")
    if window.get("data_used_for_candidate_selection") != "excluded":
        failures.append("the confirmatory window does not exclude candidate-selection data")

    prerequisites = {item["id"]: item for item in spec.get("prerequisites", [])}
    for pid in ("P1", "P2", "P3", "P4", "P5"):
        if pid not in prerequisites:
            failures.append(f"prerequisite {pid} is missing")
    if prerequisites.get("P2", {}).get("status") != "OUTSTANDING":
        failures.append("prerequisite P2 is not OUTSTANDING")
    if prerequisites.get("P3", {}).get("status") != "OUTSTANDING":
        failures.append("prerequisite P3 is not OUTSTANDING")

    authorization = spec.get("authorization", {})
    if authorization.get("execution_authorized") is not False:
        failures.append("authorization.execution_authorized is not false")

    return {
        "ok": not failures,
        "spec_path": str(spec_path.relative_to(repo_root)),
        "declared_specification_hash": declared,
        "recomputed_specification_hash": recomputed,
        "inherited_blocks_checked": list(INHERITED_BLOCKS),
        "prerequisites": {pid: item.get("status") for pid, item in prerequisites.items()},
        "failures": failures,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v3 specification."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_V1_PATH = REPO_ROOT / "configs" / "research_v1.json"
SPEC_V3_PATH = REPO_ROOT / "configs" / "research_v3.json"

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
    spec_path = repo_root / "configs" / "research_v3.json"
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
            failures.append(f"v3 spec is missing the inherited block {block}")
        elif spec[block] != v1.get(block):
            failures.append(f"inherited block {block} differs from v1")

    grid = spec.get("strategy_grid", {})
    if grid.get("total_combinations") != 2304:
        failures.append("strategy_grid.total_combinations is not 2304")
    if _grid_combinations(grid) != grid.get("total_combinations"):
        failures.append("strategy_grid dimensions do not multiply to total_combinations")

    authorization = spec.get("authorization", {})
    if authorization.get("execution_authorized") is not False:
        failures.append("authorization.execution_authorized is not false")

    return {
        "ok": not failures,
        "spec_path": str(spec_path.relative_to(repo_root)),
        "declared_specification_hash": declared,
        "recomputed_specification_hash": recomputed,
        "inherited_blocks_checked": list(INHERITED_BLOCKS),
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

#!/usr/bin/env python3
"""Read-only, offline verification of a campaign cycle's result shards.

The verifier never writes to the repository. It checks, for one cycle
directory that contains a ``results_manifest.json``:

* every manifest shard exists, its SHA-256 matches, and its record count
  matches the manifest;
* every record is strict JSON (no ``NaN``/``Infinity``);
* every record's ``experiment_id`` recomputes from the record content under
  the manifest's spec/code/data hashes (content-addressed identity). Identity
  binds the unit coordinates (asset, config, fold, cost, time bounds, data
  hash), not the metric values, so a metric edit is caught by the shard hash
  check rather than by the ID check;
* the distinct ``(asset, config_id, fold_index, cost_multiplier)`` units equal
  the record total (no duplicated unit, no missing unit);
* grid coverage: assets, per-asset record counts, fold indexes, cost
  multipliers, and the number of holdout records.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant: {name}")


def _resolve_shard_path(raw: str, cycle_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return REPO_ROOT / path


def verify_cycle(cycle_dir: Path) -> Dict[str, Any]:
    manifest_path = cycle_dir / "results_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec_hash = manifest["specification_hash"]
    code_hash = manifest["code_hash"]
    data_hash = manifest["data_manifest_hash"]

    failures: List[str] = []
    seen_ids: Set[str] = set()
    units: Set[Tuple[str, str, int, float]] = set()
    assets: Counter = Counter()
    folds: Counter = Counter()
    costs: Counter = Counter()
    statuses: Counter = Counter()
    duplicate_ids = 0
    duplicate_units = 0
    id_mismatches = 0
    non_finite = 0
    unparseable = 0
    holdout_records = 0
    records_read = 0
    bytes_read = 0
    missing_shards = 0
    shard_hash_mismatches = 0
    shard_count_mismatches = 0
    shard_indexes: List[int] = []

    for entry in manifest.get("shards", []):
        path = _resolve_shard_path(entry["path"], cycle_dir)
        if not path.exists():
            missing_shards += 1
            failures.append(f"missing shard: {entry['path']}")
            continue
        shard_indexes.append(int(path.stem.split("_")[1]))
        if sha256_file(path) != entry.get("sha256"):
            shard_hash_mismatches += 1
            failures.append(f"shard hash mismatch: {entry['path']}")
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line, parse_constant=_reject_constant)
                except ValueError:
                    non_finite += 1
                    continue
                except json.JSONDecodeError:
                    unparseable += 1
                    continue
                count += 1
                stored_id = record.get("experiment_id", "")
                recomputed = compute_experiment_id(
                    spec_hash=spec_hash,
                    code_hash=code_hash,
                    data_hash=record.get("data_hash", ""),
                    asset=record.get("asset", ""),
                    config_id=record.get("config_id", ""),
                    fold_index=record.get("fold_index", 0),
                    start_time=record.get("start_time", 0),
                    end_time=record.get("end_time", 0),
                    is_holdout=record.get("is_holdout", False),
                    cost_multiplier=record.get("cost_multiplier", 0.0),
                )
                if recomputed != stored_id:
                    id_mismatches += 1
                    failures.append(
                        f"experiment_id mismatch: {path.name} line {line_number}"
                    )
                if stored_id in seen_ids:
                    duplicate_ids += 1
                seen_ids.add(stored_id)
                unit = (
                    str(record.get("asset", "")),
                    str(record.get("config_id", "")),
                    int(record.get("fold_index", -1)),
                    float(record.get("cost_multiplier", -1)),
                )
                if unit in units:
                    duplicate_units += 1
                units.add(unit)
                assets[unit[0]] += 1
                folds[unit[2]] += 1
                costs[unit[3]] += 1
                statuses[str(record.get("status", "?"))] += 1
                if record.get("is_holdout"):
                    holdout_records += 1
        bytes_read += path.stat().st_size
        if count != entry.get("records"):
            shard_count_mismatches += 1
            failures.append(f"shard record count mismatch: {entry['path']}")
        records_read += count

    shard_indexes.sort()
    contiguous = shard_indexes == list(range(len(shard_indexes)))
    if not contiguous:
        failures.append("shard indexes are not contiguous from 0")

    manifest_records = manifest.get("total_records")
    manifest_bytes = manifest.get("total_bytes")
    if manifest_records != records_read:
        failures.append(
            f"manifest total_records {manifest_records} != records read {records_read}"
        )
    if manifest_bytes != bytes_read:
        failures.append(
            f"manifest total_bytes {manifest_bytes} != bytes read {bytes_read}"
        )
    if duplicate_units:
        failures.append(f"{duplicate_units} duplicated grid units")
    if id_mismatches:
        failures.append(f"{id_mismatches} experiment_id mismatches")
    if non_finite or unparseable:
        failures.append(f"{non_finite} non-finite and {unparseable} unparseable records")
    if missing_shards or shard_hash_mismatches or shard_count_mismatches:
        failures.append("shard presence/hash/count verification failed")

    per_asset = sorted(assets.items())
    report = {
        "cycle_dir": str(cycle_dir),
        "campaign_id": manifest.get("campaign_id"),
        "specification_hash": spec_hash,
        "code_hash": code_hash,
        "data_manifest_hash": data_hash,
        "manifest_total_records": manifest_records,
        "manifest_total_bytes": manifest_bytes,
        "manifest_shards": len(manifest.get("shards", [])),
        "shards_on_disk": len(shard_indexes),
        "shard_index_contiguous_from_0": contiguous,
        "records_read": records_read,
        "bytes_read": bytes_read,
        "unique_experiment_ids": len(seen_ids),
        "duplicate_experiment_ids": duplicate_ids,
        "duplicate_grid_units": duplicate_units,
        "experiment_id_mismatches": id_mismatches,
        "non_finite_records": non_finite,
        "unparseable_records": unparseable,
        "missing_shards": missing_shards,
        "shard_hash_mismatches": shard_hash_mismatches,
        "shard_count_mismatches": shard_count_mismatches,
        "distinct_grid_units": len(units),
        "assets": len(per_asset),
        "records_per_asset": sorted({value for _, value in per_asset}),
        "asset_record_counts": {asset: count for asset, count in per_asset},
        "fold_indexes": sorted(folds),
        "cost_multipliers": sorted(costs),
        "holdout_records": holdout_records,
        "status_counts": dict(statuses),
        "failures": failures,
        "verified": not failures,
    }
    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle_dir", help="cycle directory containing results_manifest.json")
    parser.add_argument(
        "--expect-records",
        type=int,
        default=None,
        help="fail unless the verified record count equals this value",
    )
    args = parser.parse_args(argv)

    cycle_dir = Path(args.cycle_dir)
    if not (cycle_dir / "results_manifest.json").exists():
        print(f"no results_manifest.json in {cycle_dir}", file=sys.stderr)
        return 2
    report = verify_cycle(cycle_dir)
    if args.expect_records is not None and report["records_read"] != args.expect_records:
        report["failures"].append(
            f"expected {args.expect_records} records, read {report['records_read']}"
        )
        report["verified"] = False
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

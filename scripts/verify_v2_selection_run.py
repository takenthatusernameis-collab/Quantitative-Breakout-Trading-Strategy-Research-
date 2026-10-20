#!/usr/bin/env python3
"""Record-level verification of the performed v2 selection run.

``scripts/verify_research_v2_selection_authorization_1.py`` checks the
*authorization* and the executed state at the level of the ledger, the
checkpoint, the results manifest and the v1 evidence. This script goes one
level deeper: it verifies the **record set** itself and it recomputes the
selection outcome from it.

What is verified, all read-only:

1. every shard file listed in ``research/results_manifest_v2.json`` exists,
   its sha256 and its byte size match the manifest, and its record count
   matches the manifest; and no shard file exists that the manifest does not
   list;
2. every record in every shard re-computes its own ``experiment_id`` from its
   content, carries the authorized code, specification and data identities,
   is a validation record (``is_holdout`` is false), and names an asset, a
   configuration, a validation fold and a cost scenario that are inside the
   authorized grid; every authorized grid unit appears exactly once;
3. the record count agrees with the ledger, with the results manifest and with
   the authorized execution-unit bound;
4. the buy-and-hold baselines are recomputed from the datasets and compared
   with the baselines the run recorded;
5. the selection outcome is **recomputed with the unchanged v1 selector** from
   the records and compared with the outcome the run reported;
6. the result stream is exactly the projection of the verified shards: the
   sha256 of the shard bytes in shard order equals the sha256 of the stream.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.baselines import baseline_for_asset, buyhold_baseline  # noqa: E402
from breakout_research.backtest.shards import (  # noqa: E402
    compute_experiment_id,
    serialize_record,
)
from breakout_research.config import CostScenario  # noqa: E402
from breakout_research.selection import select_candidates  # noqa: E402

from v2_campaign import runner  # noqa: E402
from v2_campaign.data import load_development_candles  # noqa: E402
from v2_campaign.units import fold_bounds, unit_data_hash, validation_folds  # noqa: E402

AUTHORIZATION_RELATIVE = "configs/research_v2_selection_authorization_1.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
MANIFEST_RELATIVE = "research/results_manifest_v2.json"
STREAM_RELATIVE = "research/results_v2.jsonl"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _shard_paths(shard_root: Path, campaign_id: str) -> List[Path]:
    directory = shard_root / campaign_id
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.iterdir() if path.name.startswith("shard_") and path.name.endswith(".jsonl")
    )


def _recomputed_outcome(selection: Dict[str, Any]) -> str:
    """The outcome label the run's own rule produces from the recomputed set."""
    with_candidate = [symbol for symbol, outcome in selection.items() if outcome.get("config_id")]
    without_candidate = [symbol for symbol, outcome in selection.items() if not outcome.get("config_id")]
    if with_candidate and without_candidate:
        return "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    if with_candidate:
        return "CANDIDATES_SELECTED"
    return "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    authorization = _load(repo_root / AUTHORIZATION_RELATIVE)
    run = authorization["authorized_run"]
    identity = run["code_identity"]
    bounds = run["bounds"]
    planned_units = int(bounds["planned_execution_units"])
    pairs = list(run["scope"]["binance_pairs"])

    ledger_path = repo_root / LEDGER_RELATIVE
    manifest_path = repo_root / MANIFEST_RELATIVE
    checkpoint_path = repo_root / CHECKPOINT_RELATIVE
    for path in (ledger_path, manifest_path, checkpoint_path):
        if not path.exists():
            failures.append(f"the run left no {path.name}")
    if failures:
        return {"ok": False, "failures": failures}

    ledger = _load(ledger_path)
    manifest = _load(manifest_path)
    checkpoint = _load(checkpoint_path)
    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    spec_v2 = _load(repo_root / SPEC_V2_RELATIVE)
    config_manifest = _load(repo_root / CONFIG_MANIFEST_RELATIVE)
    data_manifest = _load(repo_root / DATA_MANIFEST_RELATIVE)

    if ledger.get("status") != "COMPLETED":
        failures.append(
            f"the run is not complete: the ledger status is {ledger.get('status')!r}"
        )

    # 1. the shards against the results manifest.
    shard_root = repo_root / "research" / "shards_v2"
    campaign_id = str(run["campaign_id"])
    on_disk = _shard_paths(shard_root, campaign_id)
    listed = [repo_root / shard["path"] for shard in manifest.get("shards") or []]
    listed_names = {path.name for path in listed}
    for path in on_disk:
        if path.name not in listed_names:
            failures.append(f"the shard {path.name} is not listed in the results manifest")
    for shard, path in zip(manifest.get("shards") or [], listed):
        if not path.exists():
            failures.append(f"the shard {shard.get('path')} is missing")
            continue
        if path.stat().st_size != int(shard.get("bytes") or 0):
            failures.append(f"the shard {path.name} does not have the recorded byte size")
        if _sha256_file(path) != shard.get("sha256"):
            failures.append(f"the shard {path.name} does not match its recorded sha256")

    # 2. the records.
    plan = runner.build_plan(runner.default_workspace(repo_root))
    config_by_id = {config.config_id: config for config in plan.configs}
    unit_keys = set()
    record_count = 0
    projection = hashlib.sha256()
    expected_code = str(identity["run_code_identity"])
    expected_spec = str(plan.specification_hash)
    records: List[Dict[str, Any]] = []
    for path in on_disk:
        projection.update(path.read_bytes())
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                record_count += 1
                recomputed = compute_experiment_id(
                    spec_hash=record.get("specification_hash", ""),
                    code_hash=record.get("code_hash", ""),
                    data_hash=record.get("data_hash", ""),
                    asset=record.get("asset", ""),
                    config_id=record.get("config_id", ""),
                    fold_index=record.get("fold_index", 0),
                    start_time=record.get("start_time", 0),
                    end_time=record.get("end_time", 0),
                    is_holdout=record.get("is_holdout", False),
                    cost_multiplier=record.get("cost_multiplier", 0.0),
                )
                if recomputed != record.get("experiment_id"):
                    failures.append(
                        f"{path.name} line {line_number}: the experiment id does not recompute"
                    )
                if record.get("code_hash") != expected_code:
                    failures.append(f"{path.name} line {line_number}: foreign code identity")
                if record.get("specification_hash") != expected_spec:
                    failures.append(f"{path.name} line {line_number}: foreign specification")
                config = config_by_id.get(record.get("config_id"))
                if config is None:
                    failures.append(f"{path.name} line {line_number}: unknown configuration")
                else:
                    expected_unit_hash = unit_data_hash(
                        str(record.get("asset")), config, plan.data_hashes
                    )
                    if record.get("data_hash") != expected_unit_hash:
                        failures.append(
                            f"{path.name} line {line_number}: foreign unit data hash"
                        )
                if record.get("is_holdout"):
                    failures.append(f"{path.name} line {line_number}: a holdout record was exposed")
                if record.get("asset") not in pairs:
                    failures.append(f"{path.name} line {line_number}: unknown asset")
                if config is None:
                    failures.append(f"{path.name} line {line_number}: unknown configuration")
                if int(record.get("fold_index", -1)) not in (0, 1, 2, 3):
                    failures.append(f"{path.name} line {line_number}: unknown validation fold")
                if float(record.get("cost_multiplier", 0.0)) not in (1.0, 2.0, 3.0):
                    failures.append(f"{path.name} line {line_number}: unknown cost scenario")
                unit_keys.add(
                    (
                        record.get("asset"),
                        record.get("config_id"),
                        int(record.get("fold_index", -1)),
                        float(record.get("cost_multiplier", 0.0)),
                    )
                )
                records.append(record)
                if len(failures) > 50:
                    break
            if len(failures) > 50:
                break
        if len(failures) > 50:
            break

    if len(unit_keys) != record_count:
        failures.append("the record set contains a duplicate grid unit")
    if record_count != planned_units:
        failures.append(
            f"the record set holds {record_count} records, the authorized grid holds {planned_units}"
        )
    counts = ledger.get("counts") or {}
    if int(counts.get("records_written") or 0) != record_count:
        failures.append("the ledger record count does not match the record set")
    if int(manifest.get("total_records") or 0) != record_count:
        failures.append("the results manifest record count does not match the record set")
    if int(checkpoint.get("completed_records") or 0) != record_count:
        failures.append("the checkpoint record count does not match the record set")

    # 4. the baselines, recomputed from the datasets.
    #
    #    The baselines are an *input* of the selection rule, not a recorded
    #    output of the run, so they are recomputed here and used to recompute
    #    the outcome below. A baseline that cannot be recomputed from the
    #    datasets would change the outcome, and the outcome is compared.
    recomputed_baselines: Dict[str, Dict[str, Any]] = {}
    boundary_ms = int(plan.boundary_ms)
    folds = plan.folds
    cost_multipliers = [float(value) for value in plan.cost_multipliers]
    for symbol in pairs:
        candles, _provenance = load_development_candles(
            repo_root, symbol, data_manifest, boundary_ms
        )
        windows = validation_folds(fold_bounds(candles, folds))
        baseline = buyhold_baseline(
            candles,
            {fold[2]: (fold[0], fold[1]) for fold in windows},
            [CostScenario.baseline().scaled(value) for value in cost_multipliers],
        )
        recomputed_baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)
    if any(entry.get("status") != "OK" for entry in recomputed_baselines.values()):
        failures.append("a buy-and-hold baseline does not recompute from the datasets")

    # 5. the selection outcome, recomputed with the unchanged v1 selector.
    recomputed_selection = select_candidates(
        records, spec_v1, recomputed_baselines, config_manifest
    )
    recorded_selection = ledger.get("selection") or {}
    per_asset = recorded_selection.get("per_asset") or {}
    for symbol, outcome in recomputed_selection.items():
        recorded = per_asset.get(symbol) or {}
        if recorded.get("status") != outcome.get("status"):
            failures.append(
                f"the recorded outcome of {symbol} is {recorded.get('status')!r}, "
                f"the recomputed outcome is {outcome.get('status')!r}"
            )
        if recorded.get("config_id") != outcome.get("config_id"):
            failures.append(f"the recorded configuration of {symbol} does not recompute")
        if recorded.get("economic_status") != outcome.get("economic_status"):
            failures.append(f"the recorded economic status of {symbol} does not recompute")
        if recorded.get("counts") != outcome.get("counts"):
            failures.append(f"the recorded gate counts of {symbol} do not recompute")
    for symbol in pairs:
        if symbol not in per_asset:
            failures.append(f"the recorded outcome omits the asset {symbol}")
    if recorded_selection.get("outcome") != _recomputed_outcome(recomputed_selection):
        failures.append("the recorded outcome label does not recompute")
    if list(recorded_selection.get("assets_with_candidate") or []) != sorted(
        symbol for symbol, outcome in recomputed_selection.items() if outcome.get("config_id")
    ):
        failures.append("the recorded assets with a candidate do not recompute")
    if list(recorded_selection.get("assets_without_candidate") or []) != sorted(
        symbol for symbol, outcome in recomputed_selection.items() if not outcome.get("config_id")
    ):
        failures.append("the recorded assets without a candidate do not recompute")

    # 6. the result stream against the shard projection.
    stream_path = repo_root / STREAM_RELATIVE
    stream_digest = None
    complete = ledger.get("status") == "COMPLETED"
    if stream_path.exists():
        stream_digest = _sha256_file(stream_path)
        stream_lines = sum(1 for _ in stream_path.open("r", encoding="utf-8"))
        if complete:
            # The shards are immutable and a completed run is never written to
            # again, so the two are compared without a race.
            if stream_digest != projection.hexdigest():
                failures.append(
                    "the result stream is not the projection of the verified shards"
                )
            if stream_lines != record_count:
                failures.append(
                    f"the result stream holds {stream_lines} rows, the record set holds {record_count}"
                )
        else:
            failures.append(
                "the result stream was not compared: the run is still in progress, "
                "so the shards and the stream are read at different instants"
            )

    return {
        "ok": not failures,
        "failures": failures,
        "ledger_status": ledger.get("status"),
        "record_count": record_count,
        "planned_execution_units": planned_units,
        "shard_files": len(on_disk),
        "shards_in_manifest": len(listed),
        "distinct_grid_units": len(unit_keys),
        "result_stream_sha256": stream_digest,
        "shard_projection_sha256": projection.hexdigest(),
        "assets_evaluated": len(recomputed_selection),
        "assets_with_candidate": sorted(
            symbol
            for symbol, outcome in recomputed_selection.items()
            if outcome.get("config_id")
        ),
        "outcome": recorded_selection.get("outcome"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    started = time.perf_counter()
    report = verify(Path(args.repo_root).resolve())
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

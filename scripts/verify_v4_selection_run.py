#!/usr/bin/env python3
"""Record-level verification of the performed v4 selection run.

``scripts/verify_v4_selection_authorization_1.py`` checks the *authorization*
and the executed state at the level of the ledger, the checkpoint and the
results manifest. This script goes one level deeper: it verifies the **record
set** itself and it recomputes the selection outcome from it.

What is verified, all read-only and without re-running anything:

1. every shard file listed in ``research/results_manifest_v4.json`` exists,
   its sha256 and its byte size match the manifest, and its record count
   matches the manifest; and no shard file exists that the manifest does not
   list;
2. the cheap counters of the ledger, of the results manifest and of the
   checkpoint agree with each other and with the authorized plan;
3. every record in every shard re-computes its own ``experiment_id`` from its
   content, carries the authorized code, specification and data identities,
   is a validation record (``is_holdout`` is false), names an asset, a
   configuration, a validation fold and a cost scenario that are inside the
   authorized grid, carries the fold window the frozen fold rule derives for
   that asset and fold, and binds the benchmark content hash;
4. the record set is **exactly** the authorized grid: the expected experiment
   ids are re-derived from the frozen rule and compared with the observed set,
   so that a missing unit and a foreign unit are both detected;
5. the record count agrees with the ledger, with the results manifest and with
   the checkpoint, and stays inside the authorized bounds;
6. no confirmatory exposure is recorded: ``holdout_exposed_count`` is zero in
   the ledger and in the checkpoint, the holdout-position fold was never
   evaluated, and every evaluated window closes at or before the effective
   development boundary;
7. the result stream is exactly the projection of the verified shards: the
   sha256 of the shard bytes in shard order equals the sha256 of the stream;
8. the buy-and-hold baselines are recomputed from the datasets and the
   selection outcome is **recomputed with the unchanged v1 selector** from the
   records and compared with the outcome the run reported, including the
   assets without a candidate.

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
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.baselines import baseline_for_asset, buyhold_baseline  # noqa: E402
from breakout_research.config import CostScenario  # noqa: E402
from breakout_research.data.fetcher import HOUR_MS  # noqa: E402
from breakout_research.selection import select_candidates  # noqa: E402

from v4_campaign import runner  # noqa: E402
from v4_campaign.benchmark import BENCHMARK_SYMBOL  # noqa: E402
from v4_campaign.data import load_benchmark_candles, load_development_candles  # noqa: E402
from v4_campaign.units import fold_bounds, iter_units, unit_data_hash, validation_folds  # noqa: E402

AUTHORIZATION_RELATIVE = "configs/research_v4_selection_authorization_1.json"
LEDGER_RELATIVE = "research/ledger_v4.json"
MANIFEST_RELATIVE = "research/results_manifest_v4.json"
STREAM_RELATIVE = "research/results_v4.jsonl"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v4.json"
SHARD_ROOT_RELATIVE = "research/shards_v4"
SPEC_V1_RELATIVE = "configs/research_v1.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"

#: The number of failures after which the record scan stops early.
MAX_FAILURES = 50


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
        path for path in directory.iterdir()
        if path.is_file() and path.name.startswith("shard_") and path.name.endswith(".jsonl")
    )


def _resolve_shard(repo_root: Path, shard: Dict[str, Any], campaign_id: str) -> Path:
    """The shard of *this* tree that a results-manifest entry names.

    The results manifest records the path the store was given, which is
    absolute when the run was started from an absolute workspace (the v2
    manifest is absolute for the same reason; the v3 manifest is relative).
    The verifier must verify the shards of the tree it is given, so the
    recorded path is resolved by its file name inside this tree's own shard
    directory, and the tail of the recorded path is checked against the
    expected one -- a manifest that names another tree is refused.
    """
    recorded = str(shard.get("path") or "")
    name = Path(recorded).name
    expected = f"{SHARD_ROOT_RELATIVE}/{campaign_id}/{name}"
    if not recorded.replace("\\", "/").endswith(expected):
        raise ValueError(
            f"the results manifest records the shard {recorded!r}, which is not a "
            f"shard of this tree ({expected})"
        )
    return repo_root / SHARD_ROOT_RELATIVE / campaign_id / name


def _numbered_records(shard_paths: List[Path]) -> Iterator[Tuple[Path, int, Dict[str, Any]]]:
    """Yield ``(path, line_number, record)`` for every record of the shard set."""
    for path in shard_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                yield path, line_number, json.loads(line)


def _iter_records(shard_root: Path, campaign_id: str) -> Iterator[Dict[str, Any]]:
    """Yield every record of the campaign, in shard order."""
    for _path, _line_number, record in _numbered_records(_shard_paths(shard_root, campaign_id)):
        yield record


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
    report: Dict[str, Any] = {"ok": False, "failures": failures}

    def done() -> Dict[str, Any]:
        report["ok"] = not failures
        return report

    # --- 1. the artifacts the run must have left -------------------------
    authorization_path = repo_root / AUTHORIZATION_RELATIVE
    ledger_path = repo_root / LEDGER_RELATIVE
    manifest_path = repo_root / MANIFEST_RELATIVE
    checkpoint_path = repo_root / CHECKPOINT_RELATIVE
    stream_path = repo_root / STREAM_RELATIVE
    for path in (authorization_path, ledger_path, manifest_path, checkpoint_path):
        if not path.exists():
            failures.append(f"the run left no {path.name}")
    if failures:
        return done()

    authorization = _load(authorization_path)
    run = authorization["authorized_run"]
    identity = run["code_identity"]
    bounds = run["bounds"]
    planned_units = int(bounds["planned_execution_units"])
    pairs = list(run["scope"]["binance_pairs"])
    campaign_id = str(run["campaign_id"])

    ledger = _load(ledger_path)
    manifest = _load(manifest_path)
    checkpoint = _load(checkpoint_path)

    if ledger.get("status") != "COMPLETED":
        failures.append(
            f"the run is not complete: the ledger status is {ledger.get('status')!r}"
        )
    if ledger.get("authorization_manifest_hash") != authorization.get("manifest_hash"):
        failures.append("the ledger is not bound to the authorization's manifest hash")
    if ledger.get("run_id") != run.get("run_id"):
        failures.append("the ledger records a different run id than the authorization")
    if ledger.get("campaign_id") != campaign_id:
        failures.append("the ledger records a different campaign id than the authorization")
    if failures:
        return done()

    # --- 2. the plan, the frozen rule and the data ----------------------
    plan = runner.build_plan(runner.default_workspace(repo_root))
    config_by_id = {config.config_id: config for config in plan.configs}
    expected_code = str(identity["run_code_identity"])
    expected_spec = str(plan.specification_hash)
    boundary_ms = int(plan.boundary_ms)
    cost_multipliers = [float(value) for value in plan.cost_multipliers]
    fold_count = len(plan.folds["window_fractions"])

    # The benchmark content hash is recomputed from the dataset file, not read
    # out of the manifest.
    _benchmark_candles, benchmark_provenance = load_benchmark_candles(
        repo_root, plan.data_manifest, boundary_ms
    )
    benchmark_content_hash = str(benchmark_provenance.get("content_hash"))

    # --- 3. the shards against the results manifest ----------------------
    shard_root = repo_root / SHARD_ROOT_RELATIVE
    on_disk = _shard_paths(shard_root, campaign_id)
    listed: List[Path] = []
    for shard in manifest.get("shards") or []:
        try:
            listed.append(_resolve_shard(repo_root, shard, campaign_id))
        except ValueError as exc:
            failures.append(str(exc))
    listed_names = {path.name for path in listed}
    for path in on_disk:
        if path.name not in listed_names:
            failures.append(f"the shard {path.name} is not listed in the results manifest")
    for shard, path in zip(manifest.get("shards") or [], listed):
        if not path.exists():
            failures.append(f"the shard {path.name} is missing")
            continue
        if path.stat().st_size != int(shard.get("bytes") or 0):
            failures.append(f"the shard {path.name} does not have the recorded byte size")
        if _sha256_file(path) != shard.get("sha256"):
            failures.append(f"the shard {path.name} does not match its recorded sha256")
    report["shard_files"] = len(on_disk)
    report["shards_in_manifest"] = len(listed)

    # --- 4. the cheap counters, against the authorized plan ---------------
    counts = ledger.get("counts") or {}
    if int(counts.get("records_written") or 0) != planned_units:
        failures.append(
            f"the ledger records {counts.get('records_written')} records, the authorized "
            f"grid holds {planned_units}"
        )
    if int(manifest.get("total_records") or 0) != planned_units:
        failures.append(
            f"the results manifest records {manifest.get('total_records')} records, the "
            f"authorized grid holds {planned_units}"
        )
    if int(checkpoint.get("completed_records") or 0) != planned_units:
        failures.append(
            f"the checkpoint records {checkpoint.get('completed_records')} records, the "
            f"authorized grid holds {planned_units}"
        )
    if int(ledger.get("holdout_exposed_count") or 0) != 0:
        failures.append("the ledger records a confirmatory exposure")
    if int(checkpoint.get("holdout_exposed_count") or 0) != 0:
        failures.append("the checkpoint records a confirmatory exposure")
    boundary = ledger.get("data_boundary") or {}
    if boundary.get("candles_before_utc") != plan.effective_data_boundary_utc:
        failures.append("the ledger records a different data boundary")
    for flag in (
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v2_confirmatory_window_never_reused",
    ):
        if boundary.get(flag) is not True:
            failures.append(f"the ledger does not assert {flag}")
    if manifest.get("campaign_id") != campaign_id:
        failures.append("the results manifest records a different campaign id")
    if manifest.get("code_hash") != expected_code:
        failures.append("the results manifest carries a foreign code identity")
    if manifest.get("specification_hash") != expected_spec:
        failures.append("the results manifest carries a foreign specification")
    if manifest.get("data_manifest_hash") != plan.data_manifest_provenance[
        "effective_data_manifest_hash"
    ]:
        failures.append("the results manifest carries a foreign data-manifest identity")
    if failures:
        return done()

    # --- 5. the record set ------------------------------------------------
    candles_by_asset: Dict[str, List[Any]] = {}
    windows_by_asset: Dict[str, Dict[int, Tuple[int, int]]] = {}
    for asset in plan.assets:
        symbol = str(asset["symbol"])
        candles, _provenance = load_development_candles(
            repo_root, symbol, plan.data_manifest, boundary_ms
        )
        candles_by_asset[symbol] = candles
        windows = validation_folds(fold_bounds(candles, plan.folds))
        windows_by_asset[symbol] = {
            int(window[2]): (int(window[0]), int(window[1])) for window in windows
        }

    projection = hashlib.sha256()
    for path in on_disk:
        projection.update(path.read_bytes())

    record_count = 0
    observed_ids: Set[str] = set()
    unit_keys: Set[Tuple[Any, ...]] = set()
    btc_record_count = 0
    for path, line_number, record in _numbered_records(on_disk):
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
        observed_ids.add(recomputed)
        if record.get("code_hash") != expected_code:
            failures.append(f"{path.name} line {line_number}: foreign code identity")
        if record.get("specification_hash") != expected_spec:
            failures.append(f"{path.name} line {line_number}: foreign specification")
        if record.get("is_holdout"):
            failures.append(f"{path.name} line {line_number}: a holdout record was exposed")
        symbol = str(record.get("asset"))
        if symbol not in pairs:
            failures.append(f"{path.name} line {line_number}: unknown asset")
        config = config_by_id.get(record.get("config_id"))
        if config is None:
            failures.append(f"{path.name} line {line_number}: unknown configuration")
        else:
            expected_unit_hash = unit_data_hash(symbol, config, plan.data_hashes)
            if record.get("data_hash") != expected_unit_hash:
                failures.append(f"{path.name} line {line_number}: foreign unit data hash")
            if config.trend_filter.value == "btc_ema_168":
                btc_record_count += 1
        fold_index = int(record.get("fold_index", -1))
        windows = windows_by_asset.get(symbol) or {}
        if fold_index not in windows:
            failures.append(f"{path.name} line {line_number}: unknown validation fold")
        else:
            start_time, end_time = windows[fold_index]
            if int(record.get("start_time", -1)) != start_time or int(
                record.get("end_time", -1)
            ) != end_time:
                failures.append(
                    f"{path.name} line {line_number}: the fold window differs from "
                    "the window the frozen fold rule derives"
                )
        if float(record.get("cost_multiplier", 0.0)) not in cost_multipliers:
            failures.append(f"{path.name} line {line_number}: unknown cost scenario")
        alignment = record.get("benchmark_alignment") or {}
        if alignment.get("benchmark_content_hash") != benchmark_content_hash:
            failures.append(
                f"{path.name} line {line_number}: the record does not bind the "
                "benchmark content hash"
            )
        if alignment.get("index_aligned") is not True:
            failures.append(
                f"{path.name} line {line_number}: the record is not index-aligned"
            )
        if alignment.get("forward_filled") is not False:
            failures.append(
                f"{path.name} line {line_number}: the benchmark was forward-filled"
            )
        if alignment.get("benchmark_window_sliced") is not True:
            failures.append(
                f"{path.name} line {line_number}: the benchmark was not sliced to the "
                "fold window"
            )
        unit_keys.add(
            (
                record.get("asset"),
                record.get("config_id"),
                fold_index,
                float(record.get("cost_multiplier", 0.0)),
            )
        )
        if len(failures) > MAX_FAILURES:
            break
    report["record_count"] = record_count
    report["btc_filter_record_count"] = btc_record_count

    # --- 6. the record set against the authorized grid --------------------
    expected_ids: Set[str] = set()
    for asset_index, _asset in enumerate(plan.assets):
        symbol = str(plan.assets[asset_index]["symbol"])
        windows = validation_folds(fold_bounds(candles_by_asset[symbol], plan.folds))
        for _unit, experiment_id in iter_units(
            plan.assets,
            plan.configs,
            plan.cost_multipliers,
            windows,
            plan.data_hashes,
            plan.specification_hash,
            plan.code_identity["run_code_identity"],
            asset_index=asset_index,
        ):
            expected_ids.add(experiment_id)
    report["expected_experiment_ids"] = len(expected_ids)

    if len(unit_keys) != record_count:
        failures.append("the record set contains a duplicate grid unit")
    missing = expected_ids - observed_ids
    foreign = observed_ids - expected_ids
    if missing:
        failures.append(f"the record set misses {len(missing)} authorized grid units")
    if foreign:
        failures.append(f"the record set holds {len(foreign)} units outside the authorized grid")
    if record_count != planned_units:
        failures.append(
            f"the record set holds {record_count} records, the authorized grid holds "
            f"{planned_units}"
        )
    expected_btc = len(pairs) * 576 * fold_count * len(cost_multipliers)
    if btc_record_count != expected_btc:
        failures.append(
            f"the record set holds {btc_record_count} BTC trend-filter records, the "
            f"authorized grid holds {expected_btc}"
        )
    if int(counts.get("records_written") or 0) != record_count:
        failures.append("the ledger record count does not match the record set")
    if int(counts.get("executed") or 0) > record_count:
        failures.append("the ledger executed more records than the record set holds")
    if int(counts.get("skipped_already_complete") or 0) < 0:
        failures.append("the ledger reports a negative number of skipped units")
    if int(manifest.get("total_records") or 0) != record_count:
        failures.append("the results manifest record count does not match the record set")
    if int(checkpoint.get("completed_records") or 0) != record_count:
        failures.append("the checkpoint record count does not match the record set")
    if int(counts.get("config_units") or 0) > int(bounds.get("max_total_config_units") or 0):
        failures.append("the run exceeds the authorized configuration-unit bound")
    if record_count > planned_units:
        failures.append("the run exceeds the authorized execution-unit bound")

    # --- 7. the exposure --------------------------------------------------
    for symbol, entry in (plan.data_manifest.get("assets") or {}).items():
        if symbol not in pairs:
            continue
        last = entry.get("last_candle_timestamp")
        if not isinstance(last, int) or last + HOUR_MS > boundary_ms:
            failures.append(f"the dataset of {symbol} reaches into the confirmatory window")
    for symbol, windows in windows_by_asset.items():
        for fold_index, (_start, end) in windows.items():
            if end > boundary_ms:
                failures.append(
                    f"the evaluated window of {symbol} fold {fold_index} reaches into the "
                    "confirmatory window"
                )

    # --- 8. the result stream against the shard projection ----------------
    stream_digest = None
    if stream_path.exists():
        stream_digest = _sha256_file(stream_path)
        stream_lines = sum(1 for _ in stream_path.open("r", encoding="utf-8"))
        if stream_digest != projection.hexdigest():
            failures.append("the result stream is not the projection of the verified shards")
        if stream_lines != record_count:
            failures.append(
                f"the result stream holds {stream_lines} rows, the record set holds {record_count}"
            )
    # An absent stream is not a failure: the streams are uncommitted projections
    # of the shards (see .gitignore) and need not be materialized on a fresh
    # checkout. A present stream is still checked against the projection.

    if failures:
        return done()

    # --- 9. the baselines and the selection outcome ------------------------
    recomputed_baselines: Dict[str, Dict[str, Any]] = {}
    for symbol in pairs:
        candles = candles_by_asset[symbol]
        windows = validation_folds(fold_bounds(candles, plan.folds))
        baseline = buyhold_baseline(
            candles,
            {fold[2]: (fold[0], fold[1]) for fold in windows},
            [CostScenario.baseline().scaled(value) for value in cost_multipliers],
        )
        recomputed_baselines[symbol] = baseline_for_asset({"assets": {symbol: baseline}}, symbol)
    if any(entry.get("status") != "OK" for entry in recomputed_baselines.values()):
        failures.append("a buy-and-hold baseline does not recompute from the datasets")

    spec_v1 = _load(repo_root / SPEC_V1_RELATIVE)
    config_manifest = _load(repo_root / CONFIG_MANIFEST_RELATIVE)
    recomputed_selection = select_candidates(
        _iter_records(shard_root, campaign_id), spec_v1, recomputed_baselines, config_manifest
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
    if recorded_selection.get("assets_without_candidate_reported") is not True:
        failures.append("the ledger does not report the assets without a candidate")

    report.update(
        {
            "ledger_status": ledger.get("status"),
            "planned_execution_units": planned_units,
            "distinct_grid_units": len(unit_keys),
            "benchmark_content_hash": benchmark_content_hash,
            "result_stream_sha256": stream_digest,
            "shard_projection_sha256": projection.hexdigest(),
            "assets_evaluated": len(recomputed_selection),
            "assets_with_candidate": sorted(
                symbol
                for symbol, outcome in recomputed_selection.items()
                if outcome.get("config_id")
            ),
            "assets_without_candidate": sorted(
                symbol
                for symbol, outcome in recomputed_selection.items()
                if not outcome.get("config_id")
            ),
            "outcome": recorded_selection.get("outcome"),
            "effective_data_boundary_utc": plan.effective_data_boundary_utc,
        }
    )
    return done()


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

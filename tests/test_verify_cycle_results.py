"""Tests for the read-only cycle result verifier."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_cycle_results", REPO_ROOT / "scripts" / "verify_cycle_results.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _write_shard(path: Path, records, spec_hash="spec", code_hash="code", data_hash="data"):
    lines = []
    for record in records:
        record = dict(record)
        record.setdefault("data_hash", data_hash)
        record["experiment_id"] = verifier.compute_experiment_id(
            spec_hash=spec_hash,
            code_hash=code_hash,
            data_hash=record["data_hash"],
            asset=record["asset"],
            config_id=record["config_id"],
            fold_index=record["fold_index"],
            start_time=record.get("start_time", 0),
            end_time=record.get("end_time", 0),
            is_holdout=record.get("is_holdout", False),
            cost_multiplier=record["cost_multiplier"],
        )
        lines.append(json.dumps(record, sort_keys=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _base_record(**overrides):
    record = {
        "asset": "BTCUSDT",
        "config_id": "cfg_0000",
        "fold_index": 0,
        "cost_multiplier": 1.0,
        "status": "COMPLETED",
        "is_holdout": False,
        "trade_count": 10,
        "net_total_return": 0.1,
        "daily_sharpe": 0.5,
    }
    record.update(overrides)
    return record


def _build_cycle(tmp_path: Path, records) -> Path:
    cycle_dir = tmp_path / "cycle"
    shard_path = _write_shard(cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl", records)
    shard = {
        "path": str(shard_path),
        "shard_index": 0,
        "sha256": verifier.sha256_file(shard_path),
        "bytes": shard_path.stat().st_size,
        "records": len(records),
    }
    manifest = {
        "schema_version": "result-shard-v1",
        "campaign_id": "camp",
        "specification_hash": "spec",
        "code_hash": "code",
        "data_manifest_hash": "data",
        "shards": [shard],
        "total_records": len(records),
        "total_bytes": shard_path.stat().st_size,
    }
    (cycle_dir / "results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return cycle_dir


def test_verifies_clean_cycle(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record(), _base_record(cost_multiplier=2.0)])
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is True
    assert report["records_read"] == 2
    assert report["unique_experiment_ids"] == 2
    assert report["distinct_grid_units"] == 2
    assert report["duplicate_grid_units"] == 0
    assert report["experiment_id_mismatches"] == 0
    assert report["holdout_records"] == 0
    assert report["assets"] == 1
    assert report["shard_index_contiguous_from_0"] is True


def test_detects_tampered_shard_hash(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record()])
    shard_path = cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl"
    shard_path.write_text(shard_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is False
    assert report["shard_hash_mismatches"] == 1
    assert any("hash mismatch" in failure for failure in report["failures"])


def test_detects_experiment_id_mismatch(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record()])
    shard_path = cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl"
    record = json.loads(shard_path.read_text(encoding="utf-8").strip())
    record["config_id"] = "cfg_9999"
    shard_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is False
    assert report["experiment_id_mismatches"] == 1


def test_metric_change_does_not_break_identity_binding(tmp_path):
    """Experiment identity binds unit coordinates, not metric values."""
    cycle_dir = _build_cycle(tmp_path, [_base_record()])
    shard_path = cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl"
    record = json.loads(shard_path.read_text(encoding="utf-8").strip())
    record["net_total_return"] = 99.0
    shard_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    report = verifier.verify_cycle(cycle_dir)
    assert report["experiment_id_mismatches"] == 0
    assert report["shard_hash_mismatches"] == 1
    assert report["verified"] is False


def test_detects_duplicated_grid_unit(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record(), _base_record()])
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is False
    assert report["duplicate_grid_units"] == 1


def test_detects_missing_shard(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record()])
    (cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl").unlink()
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is False
    assert report["missing_shards"] == 1


def test_detects_non_finite_metric(tmp_path):
    cycle_dir = tmp_path / "cycle"
    shard_path = cycle_dir / "results_shards" / "camp" / "shard_000000.jsonl"
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    shard_path.write_text(
        '{"asset": "BTCUSDT", "config_id": "cfg_0000", "fold_index": 0, '
        '"cost_multiplier": 1.0, "daily_sharpe": NaN}\n',
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "result-shard-v1",
        "campaign_id": "camp",
        "specification_hash": "spec",
        "code_hash": "code",
        "data_manifest_hash": "data",
        "shards": [
            {
                "path": str(shard_path),
                "shard_index": 0,
                "sha256": verifier.sha256_file(shard_path),
                "bytes": shard_path.stat().st_size,
                "records": 1,
            }
        ],
        "total_records": 1,
        "total_bytes": shard_path.stat().st_size,
    }
    (cycle_dir / "results_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = verifier.verify_cycle(cycle_dir)
    assert report["verified"] is False
    assert report["non_finite_records"] == 1


def test_counts_holdout_records(tmp_path):
    cycle_dir = _build_cycle(tmp_path, [_base_record(is_holdout=True, fold_index=4)])
    report = verifier.verify_cycle(cycle_dir)
    assert report["holdout_records"] == 1
    assert report["fold_indexes"] == [4]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))

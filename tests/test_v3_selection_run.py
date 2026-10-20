"""Tests for the record-level verifier of the performed v3 selection run.

``scripts/verify_v3_selection_run.py`` verifies the **record set** that the
single authorized v3 selection run produced: the shards against the results
manifest, every record against the frozen rule, the record set against the
authorized grid, the counters against the authorized bounds, the absence of
any confirmatory exposure, the result stream against the shards and the
selection outcome against the unchanged v1 selector.

The tests prove that

* the run produced exactly the five v3 output paths and wrote into no v1 or v2
  path;
* the ledger records the authorized run, bound to the authorization's manifest
  hash, with the authorized counts and the authorized data boundary;
* the record set is exactly the authorized grid, and every record binds the
  benchmark content hash and the fold window the frozen fold rule derives;
* the BTC trend-filter configurations were evaluated, never dropped;
* no confirmatory exposure is recorded, in the ledger or in the checkpoint;
* the selection outcome covers the six assets and reports the assets without a
  candidate, under the unchanged v1 selection rule;
* **the verifier is not vacuous**: tampering with a shard, with the results
  manifest, with the ledger, with the checkpoint, with the result stream or
  with the recorded selection outcome is detected.

The tamper controls run against a mirrored tree of symlinks, so a test never
writes into the working tree and the record set is never copied.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

LEDGER_RELATIVE = "research/ledger_v3.json"
MANIFEST_RELATIVE = "research/results_manifest_v3.json"
STREAM_RELATIVE = "research/results_v3.jsonl"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v3.json"
SHARDS_RELATIVE = "research/shards_v3"
AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"

V3_OUTPUT_PATHS = (
    SHARDS_RELATIVE,
    LEDGER_RELATIVE,
    MANIFEST_RELATIVE,
    STREAM_RELATIVE,
    CHECKPOINT_RELATIVE,
)

#: The directories of the working tree that the mirror skips: they are large
#: and the verifier never reads them.
SKIP_RELATIVE = (
    Path(".git"),
    Path("research/results_shards"),
    Path("research/campaign_cycles"),
    Path("research/shards_v2"),
    Path("research/universe_snapshots"),
)


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v3_selection_run", "scripts/verify_v3_selection_run.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mirror_repo(root: Path) -> Path:
    """A tree of symlinks that mirrors the parts of the repository the verifier reads.

    The source trees are copied for real, so that a test may modify them
    without writing through a symlink into the working tree. The record set is
    symlinked: it is immutable and a test replaces a single file of it.
    """
    skip_dirs = {"__pycache__", ".pytest_cache"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in SKIP_RELATIVE:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if relative.parts[:2] == ("src", "breakout_research") or relative.parts[
                :2
            ] == ("src", "v3_campaign"):
                # The hashed set and the execution path are copied for real,
                # recursively: a symlink would let a test write through it into
                # the working tree.
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: bytes) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _failures(root: Path) -> List[str]:
    return list(verifier.verify(root)["failures"])


@pytest.fixture(scope="module")
def mirror(tmp_path_factory) -> Path:
    """A mirrored tree of the repository, shared by the tamper controls."""
    root = tmp_path_factory.mktemp("v3-selection-run") / "repo"
    root.mkdir(parents=True, exist_ok=True)
    return _mirror_repo(root)


@pytest.fixture()
def restore(mirror: Path) -> Iterator[Callable[[str], None]]:
    """Restore every file a tamper control replaced."""
    originals: Dict[str, bytes] = {}

    def _snapshot(relative: str) -> None:
        if relative not in originals:
            originals[relative] = (mirror / relative).read_bytes()

    yield _snapshot
    for relative, payload in originals.items():
        _replace(mirror, relative, payload)


@pytest.fixture(scope="module")
def clean_report() -> Dict[str, Any]:
    """The verifier's report on the produced run, computed once."""
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    return report


# --- the produced run -------------------------------------------------------

def test_the_run_produced_exactly_the_five_v3_output_paths() -> None:
    for relative in V3_OUTPUT_PATHS:
        assert (REPO_ROOT / relative).exists(), relative
    assert (REPO_ROOT / SHARDS_RELATIVE / "v3-campaign").is_dir()


def test_the_run_wrote_into_no_v1_or_v2_path() -> None:
    tracked = [
        "research/results_shards",
        "research/shards_v2",
        "research/results.jsonl",
        "research/results_manifest.json",
        "research/results_manifest_v2.json",
        "research/ledger_v2.json",
        "research_state/checkpoint.json",
        "research_state/checkpoint_v2.json",
        "configs/research_v1.json",
    ]
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--"] + tracked,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):  # pragma: no cover - git is not available
        pytest.skip("git is not available")
    if completed.returncode != 0:  # pragma: no cover - not a git checkout
        pytest.skip("the working tree is not a git checkout")
    assert completed.stdout.strip() == ""


def test_the_ledger_records_the_authorized_run() -> None:
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    ledger = _load(REPO_ROOT / LEDGER_RELATIVE)
    run = authorization["authorized_run"]
    assert ledger["status"] == "COMPLETED"
    assert ledger["authorization_manifest_hash"] == authorization["manifest_hash"]
    assert ledger["run_id"] == run["run_id"]
    assert ledger["campaign_id"] == run["campaign_id"]
    assert ledger["run_phase"] == run["run_phase"]
    assert ledger["holdout_exposed_count"] == 0
    assert len(ledger["runs"]) == 1
    assert ledger["runs"][0]["status"] == "COMPLETED"


def test_the_record_set_is_exactly_the_authorized_grid(clean_report: Dict[str, Any]) -> None:
    planned = int(
        _load(REPO_ROOT / AUTHORIZATION_RELATIVE)["authorized_run"]["bounds"][
            "planned_execution_units"
        ]
    )
    assert clean_report["record_count"] == planned == 165888
    assert clean_report["distinct_grid_units"] == planned
    assert clean_report["expected_experiment_ids"] == planned


def test_every_record_binds_the_benchmark_content_hash(clean_report: Dict[str, Any]) -> None:
    benchmark_hash = clean_report["benchmark_content_hash"]
    assert benchmark_hash == "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"
    # 6 assets x 576 BTC configurations x 4 validation folds x 3 cost scenarios.
    assert clean_report["btc_filter_record_count"] == 6 * 576 * 4 * 3


def test_no_confirmatory_exposure_is_recorded(clean_report: Dict[str, Any]) -> None:
    ledger = _load(REPO_ROOT / LEDGER_RELATIVE)
    checkpoint = _load(REPO_ROOT / CHECKPOINT_RELATIVE)
    assert ledger["holdout_exposed_count"] == 0
    assert checkpoint["holdout_exposed_count"] == 0
    assert ledger["data_boundary"]["candles_before_utc"] == "2026-10-20T13:00:00Z"
    assert ledger["data_boundary"]["confirmatory_window_never_read_during_selection"] is True
    assert ledger["data_boundary"]["v1_holdout_never_reused"] is True
    assert ledger["data_boundary"]["v2_confirmatory_window_never_reused"] is True
    assert clean_report["confirmatory_window_start_utc"] == "2026-10-20T13:00:00Z"


def test_the_selection_outcome_covers_the_six_assets(clean_report: Dict[str, Any]) -> None:
    ledger = _load(REPO_ROOT / LEDGER_RELATIVE)
    selection = ledger["selection"]
    pairs = list(
        _load(REPO_ROOT / AUTHORIZATION_RELATIVE)["authorized_run"]["scope"]["binance_pairs"]
    )
    assert selection["assets_evaluated"] == 6
    assert sorted(selection["per_asset"]) == sorted(pairs)
    assert selection["assets_without_candidate_reported"] is True
    assert (
        sorted(
            selection["assets_with_candidate"] + selection["assets_without_candidate"]
        )
        == sorted(pairs)
    )
    assert clean_report["assets_evaluated"] == 6
    assert clean_report["outcome"] == selection["outcome"]


def test_the_selection_rule_is_the_unchanged_v1_rule() -> None:
    spec_v1 = _load(REPO_ROOT / SPEC_V1_RELATIVE)
    ledger = _load(REPO_ROOT / LEDGER_RELATIVE)
    expected = _sha256_bytes(_canonical(spec_v1["selection"]).encode("utf-8"))
    assert ledger["selection"]["selection_block_sha256"] == expected
    assert (
        ledger["selection_rule"]["max_candidates_per_asset"]
        == spec_v1["selection"]["max_candidates_per_asset"]
    )


def test_the_result_stream_is_the_projection_of_the_shards(
    clean_report: Dict[str, Any],
) -> None:
    assert clean_report["result_stream_sha256"] == clean_report["shard_projection_sha256"]


# --- the verifier is not vacuous -------------------------------------------

def test_the_verifier_detects_a_tampered_shard(mirror: Path, restore) -> None:
    relative = "research/shards_v3/v3-campaign/shard_000000.jsonl"
    restore(relative)
    original = (mirror / relative).read_bytes()
    _replace(mirror, relative, original.replace(b'"trade_count":', b'"trade_count" :', 1))
    failures = _failures(mirror)
    assert failures
    assert any("shard_000000.jsonl" in failure for failure in failures)


def test_the_verifier_detects_a_missing_shard(mirror: Path, restore) -> None:
    relative = "research/shards_v3/v3-campaign/shard_000001.jsonl"
    restore(relative)
    original = (mirror / relative).read_bytes()
    _replace(mirror, relative, b"")
    failures = _failures(mirror)
    assert failures
    assert any("shard_000001.jsonl" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_results_manifest(mirror: Path, restore) -> None:
    restore(MANIFEST_RELATIVE)
    manifest = _load(mirror / MANIFEST_RELATIVE)
    manifest["total_records"] = int(manifest["total_records"]) - 1
    _replace(
        mirror,
        MANIFEST_RELATIVE,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any("results manifest" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_ledger_record_count(mirror: Path, restore) -> None:
    restore(LEDGER_RELATIVE)
    ledger = _load(mirror / LEDGER_RELATIVE)
    ledger["counts"]["records_written"] = int(ledger["counts"]["records_written"]) - 1
    _replace(
        mirror,
        LEDGER_RELATIVE,
        (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any("ledger records" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_checkpoint_record_count(
    mirror: Path, restore
) -> None:
    restore(CHECKPOINT_RELATIVE)
    checkpoint = _load(mirror / CHECKPOINT_RELATIVE)
    checkpoint["completed_records"] = int(checkpoint["completed_records"]) - 1
    _replace(
        mirror,
        CHECKPOINT_RELATIVE,
        (json.dumps(checkpoint, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any("checkpoint records" in failure for failure in failures)


def test_the_verifier_detects_a_confirmatory_exposure(mirror: Path, restore) -> None:
    restore(LEDGER_RELATIVE)
    ledger = _load(mirror / LEDGER_RELATIVE)
    ledger["holdout_exposed_count"] = 1
    _replace(
        mirror,
        LEDGER_RELATIVE,
        (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any("confirmatory exposure" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_data_boundary(mirror: Path, restore) -> None:
    restore(LEDGER_RELATIVE)
    ledger = _load(mirror / LEDGER_RELATIVE)
    ledger["data_boundary"]["candles_before_utc"] = "2026-10-20T14:00:00Z"
    _replace(
        mirror,
        LEDGER_RELATIVE,
        (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any("data boundary" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_result_stream(mirror: Path, restore) -> None:
    restore(STREAM_RELATIVE)
    original = (mirror / STREAM_RELATIVE).read_bytes()
    _replace(mirror, STREAM_RELATIVE, original.replace(b'"trade_count":', b'"trade_count" :', 1))
    failures = _failures(mirror)
    assert failures
    assert any("result stream" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_selection_outcome(mirror: Path, restore) -> None:
    restore(LEDGER_RELATIVE)
    ledger = _load(mirror / LEDGER_RELATIVE)
    symbol = sorted(ledger["selection"]["per_asset"])[0]
    ledger["selection"]["per_asset"][symbol]["status"] = "CANDIDATE_SELECTED"
    ledger["selection"]["per_asset"][symbol]["config_id"] = "cfg_0000"
    _replace(
        mirror,
        LEDGER_RELATIVE,
        (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    failures = _failures(mirror)
    assert failures
    assert any(symbol in failure for failure in failures)

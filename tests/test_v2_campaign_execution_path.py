"""Deterministic tests of the v2 selection execution path.

Every test runs against a **synthetic fixture repository** in a temporary
directory: synthetic candles, a synthetic universe, a synthetic configuration
manifest and a synthetic authorization. The test never touches the real
universe, the real datasets, the repository's own v2 paths or any provider.

The fixture copies the two source trees (``src/breakout_research`` and
``src/v2_campaign``) so that the canonical source digests the authorization
binds are the real ones; the code under test is the installed package.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.campaign import CampaignRunner, _unit_data_hash as v1_unit_data_hash  # noqa: E402
from breakout_research.config import Candle, compute_code_hash  # noqa: E402
from breakout_research.data.fetcher import (  # noqa: E402
    DATASET_HASH_ALGORITHM,
    HOUR_MS,
    _serialize_dataset,
    compute_content_hash,
)

from v2_campaign import identity, runner, scope, units  # noqa: E402
from v2_campaign.data import load_development_candles  # noqa: E402
from v2_campaign.errors import (  # noqa: E402
    AttemptBudgetError,
    BoundsError,
    ConfirmatoryWindowViolation,
    ScopeError,
)

FIXTURE_SYMBOLS = ("AAAUSDT", "BBBUSDT", "BTCUSDT")
FIXTURE_CANDLES = 240
FIXTURE_START = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
FIXTURE_BOUNDARY = FIXTURE_START + (FIXTURE_CANDLES + 1) * HOUR_MS
BOUNDARY_UTC = datetime.fromtimestamp(FIXTURE_BOUNDARY / 1000, tz=timezone.utc).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _synthetic_candles(symbol: str, count: int = FIXTURE_CANDLES) -> List[Candle]:
    candles: List[Candle] = []
    price = 100.0
    seed = sum(ord(character) for character in symbol)
    for index in range(count):
        drift = ((index * 37 + seed) % 11) - 5
        price = max(1.0, price + drift * 0.1)
        open_price = price
        close_price = max(1.0, price + (((index * 13 + seed) % 7) - 3) * 0.05)
        high = max(open_price, close_price) + 0.2
        low = min(open_price, close_price) - 0.2
        candles.append(
            Candle(
                timestamp=FIXTURE_START + index * HOUR_MS,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=1000.0 + index,
            )
        )
    return candles


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_fixture(root: Path, boundary_ms: int = FIXTURE_BOUNDARY,
                   authorization_overrides: Optional[Dict[str, Any]] = None) -> Path:
    """Build a synthetic repository that the execution path can run against."""
    shutil.copytree(
        REPO_ROOT / "src",
        root / "src",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    spec_v1_real = json.loads((REPO_ROOT / "configs" / "research_v1.json").read_text(encoding="utf-8"))
    spec_v1 = {
        "protocol_version": "v1",
        "specification_hash": "fixture-spec-v1",
        "folds": spec_v1_real["folds"],
        "costs": spec_v1_real["costs"],
        "selection": spec_v1_real["selection"],
        "checkpointing": spec_v1_real["checkpointing"],
    }
    spec_v2 = {
        "protocol_version": "v2",
        "universe_version": "v2",
        "specification_hash": "fixture-spec-v2",
        "selection": spec_v1_real["selection"],
    }
    _write_json(root / "configs" / "research_v1.json", spec_v1)
    _write_json(root / "configs" / "research_v2.json", spec_v2)

    configurations = [
        {
            "config_id": "cfg_0000",
            "entry_rule": "classic_high_breakout",
            "entry_lookback": 12,
            "buffer_atr_multiple": 0.0,
            "confirmation": "one_close",
            "trend_filter": "none",
            "exit": "channel_12",
            "content_hash": "fixturecfg0",
        },
        {
            "config_id": "cfg_0001",
            "entry_rule": "close_breakout",
            "entry_lookback": 24,
            "buffer_atr_multiple": 0.1,
            "confirmation": "two_close",
            "trend_filter": "btc_ema_168",
            "exit": "atr_trail_2.5",
            "content_hash": "fixturecfg1",
        },
    ]
    _write_json(
        root / "research" / "config_manifest.json",
        {
            "protocol_version": "v1",
            "specification_hash": "fixture-spec-v1",
            "total_configurations": len(configurations),
            "dimensions": {
                "entry_rule": ["classic_high_breakout", "close_breakout"],
                "entry_lookback": [12, 24],
                "buffer_atr_multiple": [0.0, 0.1],
                "confirmation": ["one_close", "two_close"],
                "trend_filter": ["none", "btc_ema_168"],
                "exit": ["channel_12", "atr_trail_2.5"],
            },
            "configurations": configurations,
        },
    )

    data_assets: Dict[str, Any] = {}
    content_hashes: Dict[str, str] = {}
    for symbol in FIXTURE_SYMBOLS:
        candles = _synthetic_candles(symbol)
        content_hash = compute_content_hash(candles)
        dataset_path = f"research/data/candles_v2/{symbol}_1h_{content_hash[:16]}.csv"
        target = root / dataset_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_serialize_dataset(candles), encoding="utf-8")
        content_hashes[symbol] = content_hash
        data_assets[symbol] = {
            "symbol": symbol,
            "content_hash": content_hash,
            "dataset_path": dataset_path,
            "hash_algorithm": DATASET_HASH_ALGORITHM,
            "interval": "1h",
            "provider": "binance",
            "validated": True,
            "gaps": [],
            "rejected_rows": 0,
            "observed_candle_count": len(candles),
            "first_candle_timestamp": candles[0].timestamp,
            "last_candle_timestamp": candles[-1].timestamp,
        }
    data_manifest = {
        "protocol_version": "v2",
        "universe_version": "v2",
        "manifest_hash": "fixture-data-manifest",
        "assets": data_assets,
        "content_hashes": content_hashes,
    }
    _write_json(root / "research" / "data_manifest_v2.json", data_manifest)

    eligible = [
        {
            "symbol": symbol,
            "validated": True,
            "exclusion_reason": None,
            "rank": index + 1,
        }
        for index, symbol in enumerate(FIXTURE_SYMBOLS)
    ]
    eligible.append(
        {
            "symbol": "ZZZUSDT",
            "validated": False,
            "exclusion_reason": "insufficient_hourly_history",
            "rank": 99,
        }
    )
    universe_manifest = {
        "protocol_version": "v2",
        "universe_version": "v2",
        "manifest_hash": "fixture-universe-manifest",
        "eligible_assets": eligible,
        "excluded_candidates": [],
    }
    _write_json(root / "research" / "universe_manifest_v2.json", universe_manifest)

    freeze = {
        "artifact": "v2_candidate_freeze",
        "artifact_version": "v2-candidate-freeze-1",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": "2024-01-02T00:00:00Z",
        "candidate_freeze_timestamp_utc": "2024-01-02T00:00:00Z",
        "frozen_candidate_set": {
            "count": len(FIXTURE_SYMBOLS),
            "constituents": [symbol[:-4] for symbol in FIXTURE_SYMBOLS],
            "binance_pairs": list(FIXTURE_SYMBOLS),
            "universe_manifest_hash": "fixture-universe-manifest",
            "data_manifest_hash": "fixture-data-manifest",
            "excluded_after_validation": {"ZZZUSDT": "insufficient_hourly_history"},
        },
        "data_boundary": {
            "confirmatory_window_start_utc": datetime.fromtimestamp(
                boundary_ms / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "min_confirmatory_window_hours": 2160,
        },
        "manifest_hash": "fixture-freeze",
    }
    _write_json(root / "configs" / "research_v2_candidate_freeze.json", freeze)

    v2_paths = {
        "shards_dir": "research/shards_v2",
        "ledger": "research/ledger_v2.json",
        "results_manifest": "research/results_manifest_v2.json",
        "results_stream": "research/results_v2.jsonl",
        "checkpoint": "research_state/checkpoint_v2.json",
        "never_use_v1_paths": True,
        "v1_paths_forbidden": list(scope.V1_PATHS_FORBIDDEN),
    }
    bounds = {
        "max_assets": len(FIXTURE_SYMBOLS),
        "max_configs_per_asset": len(configurations),
        "max_total_config_units": len(FIXTURE_SYMBOLS) * len(configurations),
        "attempts": 1,
        "max_retries_on_technical_failure": 3,
    }
    amendment = {
        "artifact": "v2_execution_amendment",
        "artifact_version": "v2-execution-amendment-1",
        "manifest_hash": "fixture-amendment",
        "v2_selection_authorization": {
            "bounds": bounds,
            "paths": v2_paths,
        },
    }
    _write_json(root / "configs" / "research_v2_execution_amendment_1.json", amendment)

    selection_block = spec_v1_real["selection"]
    selection_digest = scope.sha256_bytes(_canonical(selection_block).encode("utf-8"))
    hashed_set = identity.hashed_set_digest(root)
    execution_path = identity.execution_path_digest(root)
    code_identity = {
        "algorithm": identity.CANONICAL_DIGEST_ALGORITHM,
        "hashed_set_root": identity.HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": identity.EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
        "run_code_identity": identity.run_code_identity(hashed_set, execution_path),
    }
    authorization = {
        "artifact": "v2_selection_authorization",
        "artifact_version": "v2-selection-authorization-1",
        "manifest_hash": None,
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": "fixture-selection-run",
            "campaign_id": "v2-campaign",
            "run_phase": "selection_grid",
            "scope": {
                "constituents": [symbol[:-4] for symbol in FIXTURE_SYMBOLS],
                "binance_pairs": list(FIXTURE_SYMBOLS),
                "count": len(FIXTURE_SYMBOLS),
                "bound_to_universe_hash": "fixture-universe-manifest",
                "bound_to_data_hash": "fixture-data-manifest",
                "bound_to_freeze_hash": "fixture-freeze",
            },
            "code_identity": code_identity,
            "data_boundary": {
                "candles_before_utc": datetime.fromtimestamp(
                    boundary_ms / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "confirmatory_window_never_read_during_selection": True,
                "v1_holdout_never_reused": True,
            },
            "selection_rule": {
                "selection_block_sha256": selection_digest,
                "max_candidates_per_asset": selection_block["max_candidates_per_asset"],
            },
            "paths": v2_paths,
            "bounds": bounds,
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": _canonical({}),
            "manifest_hash_excluded_keys": ["manifest_hash"],
        },
    }
    if authorization_overrides:
        authorization["authorized_run"].update(authorization_overrides)
    authorization["manifest_hash"] = scope.compute_manifest_hash(
        authorization, ("manifest_hash",)
    )
    _write_json(root / "configs" / "research_v2_selection_authorization_1.json", authorization)
    return root


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    return _build_fixture(tmp_path / "fixture")


def _workspace(root: Path) -> runner.Workspace:
    return runner.default_workspace(root)


def _run(root: Path) -> Dict[str, Any]:
    return runner.run_selection(_workspace(root))


def test_the_execution_path_lives_outside_the_hashed_set() -> None:
    package = REPO_ROOT / "src" / "v2_campaign"
    assert package.is_dir()
    assert not package.is_relative_to(REPO_ROOT / "src" / "breakout_research")
    recorded = json.loads(
        (REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert recorded["code_hash_constraint"]["canonical_source_digest"] == identity.hashed_set_digest(
        REPO_ROOT
    )


def test_importing_the_execution_path_does_not_change_the_code_hash() -> None:
    before = compute_code_hash()
    assert identity.hashed_set_digest(REPO_ROOT) == (
        "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
    )
    assert before == "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"


def test_the_fold_structure_is_the_unchanged_v1_rule() -> None:
    spec = json.loads((REPO_ROOT / "configs" / "research_v1.json").read_text(encoding="utf-8"))
    candles = _synthetic_candles("AAAUSDT")
    runner_without_init = CampaignRunner.__new__(CampaignRunner)
    runner_without_init.dev_fraction = spec["folds"]["development_fraction"]
    runner_without_init.validation_windows = spec["folds"]["window_fractions"]
    assert units.fold_bounds(candles, spec["folds"]) == runner_without_init._get_fold_bounds(candles)


def test_the_unit_data_hash_is_the_unchanged_v1_rule() -> None:
    from breakout_research.config import get_configurations

    config_manifest = json.loads(
        (REPO_ROOT / "research" / "config_manifest.json").read_text(encoding="utf-8")
    )
    configs = get_configurations(config_manifest)[:64]
    hashes = {"AAAUSDT": "a" * 64, "BBBUSDT": "b" * 64, "BTCUSDT": "c" * 64}
    for config in configs:
        assert units.unit_data_hash("AAAUSDT", config, hashes) == v1_unit_data_hash(
            "AAAUSDT", config, hashes
        )


def test_the_selection_rule_of_the_fixture_is_the_repository_v1_rule(fixture_repo: Path) -> None:
    real = json.loads((REPO_ROOT / "configs" / "research_v1.json").read_text(encoding="utf-8"))
    fixture = json.loads(
        (fixture_repo / "configs" / "research_v1.json").read_text(encoding="utf-8")
    )
    assert _canonical(fixture["selection"]) == _canonical(real["selection"])
    plan = runner.build_plan(_workspace(fixture_repo))
    assert _canonical(plan.selection_rule) == _canonical(real["selection"])


def test_the_run_writes_only_the_v2_paths(fixture_repo: Path) -> None:
    document = _run(fixture_repo)
    assert document["status"] == "COMPLETED"
    for relative in (
        "research/shards_v2",
        "research/ledger_v2.json",
        "research/results_manifest_v2.json",
        "research/results_v2.jsonl",
        "research_state/checkpoint_v2.json",
    ):
        assert (fixture_repo / relative).exists(), relative
    for relative in (
        "research/results_shards",
        "research/results_manifest.json",
        "research/results.jsonl",
        "research_state/checkpoint.json",
    ):
        assert not (fixture_repo / relative).exists(), relative


def test_the_run_reports_an_asset_without_a_candidate(fixture_repo: Path) -> None:
    document = _run(fixture_repo)
    selection = document["selection"]
    assert selection["assets_evaluated"] == len(FIXTURE_SYMBOLS)
    assert selection["assets_without_candidate"] == sorted(FIXTURE_SYMBOLS)
    assert selection["assets_without_candidate_reported"] is True
    assert selection["outcome"] == "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE"
    for asset, outcome in selection["per_asset"].items():
        assert outcome["status"] in {"NO_CANDIDATE", "INSUFFICIENT_EVIDENCE"}
        assert outcome["config_id"] is None


def test_the_run_never_evaluates_the_holdout_fold(fixture_repo: Path) -> None:
    _run(fixture_repo)
    records = [
        json.loads(line)
        for line in (fixture_repo / "research" / "results_v2.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert records
    assert {record["fold_index"] for record in records} == {0, 1, 2, 3}
    assert all(record["is_holdout"] is False for record in records)
    checkpoint = json.loads(
        (fixture_repo / "research_state" / "checkpoint_v2.json").read_text(encoding="utf-8")
    )
    assert checkpoint["holdout_exposed_count"] == 0


def test_the_records_are_bound_to_the_run_identity(fixture_repo: Path) -> None:
    _run(fixture_repo)
    records = [
        json.loads(line)
        for line in (fixture_repo / "research" / "results_v2.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    plan = runner.build_plan(_workspace(fixture_repo))
    for record in records:
        recomputed = compute_experiment_id(
            spec_hash=record["specification_hash"],
            code_hash=record["code_hash"],
            data_hash=record["data_hash"],
            asset=record["asset"],
            config_id=record["config_id"],
            fold_index=record["fold_index"],
            start_time=record["start_time"],
            end_time=record["end_time"],
            is_holdout=record["is_holdout"],
            cost_multiplier=record["cost_multiplier"],
        )
        assert recomputed == record["experiment_id"]
        assert record["code_hash"] == plan.code_identity["run_code_identity"]


def test_the_run_refuses_a_widened_candidate_set(fixture_repo: Path) -> None:
    freeze_path = fixture_repo / "configs" / "research_v2_candidate_freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze["frozen_candidate_set"]["binance_pairs"].append("CCCUSDT")
    freeze["frozen_candidate_set"]["constituents"].append("CCC")
    _write_json(freeze_path, freeze)
    with pytest.raises(ScopeError):
        _run(fixture_repo)
    assert not (fixture_repo / "research" / "results_v2.jsonl").exists()


def test_the_run_refuses_a_dataset_that_reaches_into_the_confirmatory_window(
    tmp_path: Path,
) -> None:
    root = _build_fixture(
        tmp_path / "fixture",
        boundary_ms=FIXTURE_START + 10 * HOUR_MS,
    )
    with pytest.raises(ConfirmatoryWindowViolation):
        _run(root)
    assert not (root / "research" / "results_v2.jsonl").exists()
    assert not (root / "research" / "ledger_v2.json").exists()


def test_the_run_consumes_its_single_run(fixture_repo: Path) -> None:
    _run(fixture_repo)
    with pytest.raises(AttemptBudgetError):
        _run(fixture_repo)


def test_a_boundary_abort_rolls_back_and_releases_the_run(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise ConfirmatoryWindowViolation("injected boundary violation")

    monkeypatch.setattr(runner, "load_development_candles", forbidden)
    with pytest.raises(ConfirmatoryWindowViolation):
        _run(fixture_repo)
    assert not (fixture_repo / "research" / "results_v2.jsonl").exists()
    assert not (fixture_repo / "research" / "results_manifest_v2.json").exists()
    assert not (fixture_repo / "research_state" / "checkpoint_v2.json").exists()
    assert not (fixture_repo / "research" / "shards_v2" / "v2-campaign").exists()
    assert not (fixture_repo / "research" / "ledger_v2.json").exists()


def test_a_technical_failure_keeps_the_partial_state_for_a_resume(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}
    original = runner.run_fold_backtest

    def failing(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("injected technical failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "run_fold_backtest", failing)
    with pytest.raises(RuntimeError):
        _run(fixture_repo)
    ledger = json.loads(
        (fixture_repo / "research" / "ledger_v2.json").read_text(encoding="utf-8")
    )
    assert ledger["status"] == "INTERRUPTED"
    assert ledger["runs"][0]["last_failure"]["type"] == "RuntimeError"
    assert (fixture_repo / "research" / "shards_v2" / "v2-campaign").exists()
    stream = fixture_repo / "research" / "results_v2.jsonl"
    committed_before = (
        len([line for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()])
        if stream.exists()
        else 0
    )

    monkeypatch.setattr(runner, "run_fold_backtest", original)
    document = _run(fixture_repo)
    assert document["status"] == "COMPLETED"
    records = [
        json.loads(line)
        for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(records) == document["counts"]["records_written"]
    assert len({record["experiment_id"] for record in records}) == len(records)
    assert committed_before <= len(records)
    assert document["counts"]["executed"] + document["counts"]["skipped_already_complete"] == (
        document["counts"]["records_written"]
    )


def test_the_number_of_resumes_is_bounded(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("injected technical failure")

    monkeypatch.setattr(runner, "run_fold_backtest", failing)
    for _ in range(4):
        with pytest.raises(RuntimeError):
            _run(fixture_repo)
    with pytest.raises(AttemptBudgetError):
        _run(fixture_repo)


def test_the_run_is_bounded_by_the_authorized_asset_count(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path / "fixture")
    authorization_path = root / "configs" / "research_v2_selection_authorization_1.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["authorized_run"]["bounds"]["max_assets"] = 1
    authorization["manifest_hash"] = scope.compute_manifest_hash(authorization, ("manifest_hash",))
    _write_json(authorization_path, authorization)
    amendment_path = root / "configs" / "research_v2_execution_amendment_1.json"
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    amendment["v2_selection_authorization"]["bounds"]["max_assets"] = 1
    _write_json(amendment_path, amendment)
    with pytest.raises(BoundsError):
        _run(root)


def test_an_abort_rolls_back_the_artifacts_the_run_created(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"count": 0}
    original = runner.run_fold_backtest

    def failing(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] > 2:
            raise ConfirmatoryWindowViolation("injected boundary violation")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "run_fold_backtest", failing)
    with pytest.raises(ConfirmatoryWindowViolation):
        _run(fixture_repo)
    assert not (fixture_repo / "research" / "results_v2.jsonl").exists()
    assert not (fixture_repo / "research" / "results_manifest_v2.json").exists()
    assert not (fixture_repo / "research_state" / "checkpoint_v2.json").exists()
    assert not (fixture_repo / "research" / "shards_v2" / "v2-campaign").exists()
    assert not (fixture_repo / "research" / "ledger_v2.json").exists()


def test_the_run_makes_no_provider_request(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import requests.sessions

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the selection run must not contact a provider")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    document = _run(fixture_repo)
    assert document["status"] == "COMPLETED"


def test_the_run_refuses_an_authorization_whose_code_identity_is_stale(
    fixture_repo: Path,
) -> None:
    authorization_path = fixture_repo / "configs" / "research_v2_selection_authorization_1.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["authorized_run"]["code_identity"]["execution_path_digest"] = "0" * 64
    authorization["manifest_hash"] = scope.compute_manifest_hash(authorization, ("manifest_hash",))
    _write_json(authorization_path, authorization)
    with pytest.raises(ScopeError):
        _run(fixture_repo)


def test_the_run_refuses_an_authorization_whose_selection_rule_is_not_the_v1_rule(
    fixture_repo: Path,
) -> None:
    authorization_path = fixture_repo / "configs" / "research_v2_selection_authorization_1.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["authorized_run"]["selection_rule"]["selection_block_sha256"] = "1" * 64
    authorization["manifest_hash"] = scope.compute_manifest_hash(authorization, ("manifest_hash",))
    _write_json(authorization_path, authorization)
    with pytest.raises(ScopeError):
        _run(fixture_repo)


def test_the_run_refuses_a_tampered_authorization(fixture_repo: Path) -> None:
    authorization_path = fixture_repo / "configs" / "research_v2_selection_authorization_1.json"
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["authorized_run"]["bounds"]["max_assets"] = 64
    _write_json(authorization_path, authorization)
    with pytest.raises(ScopeError):
        _run(fixture_repo)


def test_the_development_loader_refuses_a_dataset_that_declares_a_later_candle(
    fixture_repo: Path,
) -> None:
    data_manifest = json.loads(
        (fixture_repo / "research" / "data_manifest_v2.json").read_text(encoding="utf-8")
    )
    data_manifest["assets"]["AAAUSDT"]["last_candle_timestamp"] = FIXTURE_START + 10 * HOUR_MS
    with pytest.raises(ConfirmatoryWindowViolation):
        load_development_candles(
            fixture_repo,
            "AAAUSDT",
            data_manifest,
            FIXTURE_START + 10 * HOUR_MS,
        )


def test_the_hashed_set_is_byte_unchanged_by_the_execution_path() -> None:
    assert compute_code_hash() == "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    recorded = json.loads(
        (REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert recorded["code_hash_constraint"]["canonical_source_digest"] == identity.hashed_set_digest(
        REPO_ROOT
    )

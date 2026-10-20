"""Deterministic, offline tests of the v2 confirmatory evaluation path.

The tests cover the staged acceptance tests 1-10 of BRAIN-011 and the tamper
cases its decision D-10 requires.

Two fixtures are used:

* the **repository itself**, read-only, for the checks that are about the
  delivered tree (the package, the digests, the frozen scope, the absence of a
  confirmatory artifact);
* a **synthetic mirror** in a temporary directory, for the checks that need an
  execution or a tampered artifact. The mirror copies the hash-bound artifacts
  and the two source trees byte-identically and serves **synthetic** candles
  through an injected retrieval callable. No provider request is made, no real
  market data is read, and no confirmatory artifact is ever written inside the
  repository: every artifact a test produces lives in the temporary directory.

The repository's confirmatory window therefore stays ``NOT_STARTED`` with
``holdout_exposed_count = 0``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import Candle, compute_code_hash  # noqa: E402
from breakout_research.data.fetcher import HOUR_MS, compute_content_hash  # noqa: E402

from v2_confirmatory import artifacts, data, exposure, identity, report, runner, scope  # noqa: E402
from v2_confirmatory.errors import (  # noqa: E402
    AuthorizationError,
    ScopeError,
    WindowExposureError,
    WindowNotReadyError,
)

CANONICAL_HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
SELECTED_CONFIGURATIONS_HASH = (
    "7acc7fe07ba4b151ee232eb70fd0a187966400005054892c184bfdd754d6d862"
)
AMENDMENT_HASH = "2701c63456e080b1a8a0cbcd478d1bf4dc04d35212f4f270ea88d7460f56f377"
WINDOW_START_UTC = "2026-10-19T22:00:00Z"
WINDOW_END_UTC = "2027-01-17T22:00:00Z"
WINDOW_HOURS = 2160

IN_SCOPE_ASSETS = (
    "ADAUSDT",
    "AVAXUSDT",
    "BNBUSDT",
    "DOGEUSDT",
    "ETHUSDT",
    "HBARUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "UNIUSDT",
    "XLMUSDT",
    "XRPUSDT",
    "ZECUSDT",
)
OUT_OF_SCOPE_ASSETS = ("BCHUSDT", "BTCUSDT", "LINKUSDT", "TRXUSDT")

#: The artifacts a confirmatory evaluation would create inside the repository.
CONFIRMATORY_ARTIFACTS = (
    "research/v2_confirmatory_window_manifest.json",
    "research/shards_v2_confirmatory",
    "research/ledger_v2_confirmatory.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_v2_confirmatory.jsonl",
    "research_state/checkpoint_v2_confirmatory.json",
    "reports/confirmatory_evaluation_v2.json",
    "reports/confirmatory_report_v2.md",
)

#: The artifacts the mirror copies. The large results manifest is symlinked
#: instead of copied: the tests never write it.
MIRROR_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "configs/research_v2_confirmatory_protocol.json",
    "configs/research_v2_confirmatory_protocol_amendment_1.json",
    "configs/research_v2_confirmatory_authorization_1.json",
    "configs/research_v2_selection_authorization_1.json",
    "research/config_manifest.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/ledger_v2.json",
    "research/v2_selected_configurations_manifest.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
)

MIRROR_SYMLINKS = ("research/results_manifest_v2.json",)

MIRROR_TREES = ("src/breakout_research", "src/v2_confirmatory")

VERIFIER = "scripts/verify_v2_confirmatory_path.py"


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _manifest_hash(document: Dict[str, Any]) -> str:
    import hashlib

    excluded = tuple(document.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    body = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _reseal(document: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute a document's self-hash after a tamper."""
    document["manifest_hash"] = _manifest_hash(document)
    return document


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror(root: Path) -> Path:
    """Build a synthetic mirror of the repository's hash-bound artifacts."""
    root.mkdir(parents=True, exist_ok=True)
    for relative in MIRROR_FILES:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in MIRROR_SYMLINKS:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(source, target)
    for tree in MIRROR_TREES:
        target = root / tree
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO_ROOT / tree, target)
    return root


def _synthetic_rows(asset: str, start_ms: int, count: int = WINDOW_HOURS) -> List[List[Any]]:
    """Deterministic synthetic kline rows for one asset."""
    rows: List[List[Any]] = []
    price = 100.0
    seed = sum(ord(character) for character in asset)
    for index in range(count):
        drift = ((index * 37 + seed) % 11) - 5
        open_price = price
        close = open_price * (1.0 + drift / 1000.0)
        high = max(open_price, close) * 1.002
        low = min(open_price, close) * 0.998
        rows.append(
            [
                start_ms + index * HOUR_MS,
                open_price,
                high,
                low,
                close,
                1000.0 + (index % 17) * 3.0,
                0,
                0,
                0,
                0,
                0,
                0,
            ]
        )
        price = close
    return rows


def _ready_probe(server_time_ms: int, pairs: Sequence[str]) -> Dict[str, Any]:
    return {
        "server_time_ms": int(server_time_ms),
        "server_time_utc": None,
        "pair_statuses": {pair: "TRADING" for pair in pairs},
        "probes": [],
        "endpoints_probed": [],
        "fetched_candles": 0,
        "command": "",
    }


def _run_verifier(repo_root: Path) -> Tuple[int, Dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / VERIFIER), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        report = {"stdout": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, report


# --------------------------------------------------------------------------
# 1. The execution path is a real package that runs nothing on import.
# --------------------------------------------------------------------------


def test_the_confirmatory_path_is_a_real_package() -> None:
    package = REPO_ROOT / "src" / "v2_confirmatory"
    assert package.is_dir()
    assert (package / "__init__.py").exists()
    modules = sorted(path.name for path in package.glob("*.py"))
    assert modules == [
        "__init__.py",
        "artifacts.py",
        "data.py",
        "errors.py",
        "exposure.py",
        "identity.py",
        "report.py",
        "runner.py",
        "scope.py",
        "window.py",
    ]


def test_importing_the_confirmatory_path_runs_nothing() -> None:
    """The package imports without a network call, a file write or a run."""
    program = (
        "import socket\n"
        "class Guard(socket.socket):\n"
        "    def connect(self, *args, **kwargs):\n"
        "        raise AssertionError('the package opened a connection on import')\n"
        "socket.socket = Guard\n"
        "import v2_confirmatory\n"
        "assert v2_confirmatory.__version__\n"
        "print('ok')\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout
    for relative in CONFIRMATORY_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists()


# --------------------------------------------------------------------------
# 2. The tree identity: portable, order-independent and unchanged.
# --------------------------------------------------------------------------


def test_the_hashed_set_digest_is_unchanged_and_order_independent(monkeypatch) -> None:
    live = identity.hashed_set_digest(REPO_ROOT)
    assert live == CANONICAL_HASHED_SET_DIGEST

    # The canonical digest does not depend on the directory enumeration order of
    # the checkout: reversing that order changes the ordered digest that
    # ``compute_code_hash()`` returns, and leaves the canonical digest alone.
    hashed_set = REPO_ROOT / "src" / "breakout_research"
    ordered_before = compute_code_hash()
    real_walk = os.walk

    def patched(top, *args, **kwargs):
        for root, dirs, files in real_walk(top, *args, **kwargs):
            dirs.sort(reverse=True)
            yield root, dirs, files

    monkeypatch.setattr(os, "walk", patched)
    assert compute_code_hash() != ordered_before, "the ordered digest ignored the enumeration order"
    assert identity.hashed_set_digest(REPO_ROOT) == live
    assert identity.execution_path_digest(REPO_ROOT) == identity.canonical_source_digest(
        REPO_ROOT / identity.EXECUTION_PATH_ROOT
    )


def test_the_execution_path_digest_binds_this_package() -> None:
    assert identity.execution_path_digest(REPO_ROOT) == identity.canonical_source_digest(
        REPO_ROOT / identity.EXECUTION_PATH_ROOT
    )


# --------------------------------------------------------------------------
# 3. The scope is exactly the frozen 14 in, 4 out.
# --------------------------------------------------------------------------


def test_the_scope_is_the_frozen_fourteen_and_four() -> None:
    live = scope.evaluation_scope(REPO_ROOT)
    assert live["in_scope_assets"] == list(IN_SCOPE_ASSETS)
    assert live["out_of_scope_without_candidate"] == list(OUT_OF_SCOPE_ASSETS)
    assert live["selected_configurations_manifest_hash"] == SELECTED_CONFIGURATIONS_HASH
    assert live["scope_may_not_be_widened_narrowed_or_reranked"] is True
    for asset in IN_SCOPE_ASSETS:
        assert live["in_scope"][asset]["config_id"].startswith("cfg_")


def test_a_widened_narrowed_or_reranked_scope_is_refused() -> None:
    live = scope.evaluation_scope(REPO_ROOT)
    config_ids = {asset: live["in_scope"][asset]["config_id"] for asset in IN_SCOPE_ASSETS}

    with pytest.raises(ScopeError):
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS) + ["BTCUSDT"], config_ids)
    with pytest.raises(ScopeError):
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS)[:-1], config_ids)

    reranked = dict(config_ids)
    reranked[IN_SCOPE_ASSETS[0]] = "cfg_0001"
    with pytest.raises(ScopeError):
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS), reranked)


# --------------------------------------------------------------------------
# 4. The readiness test: metadata only, no payload read.
# --------------------------------------------------------------------------


def test_the_readiness_test_refuses_before_the_window_end() -> None:
    early = runner.parse_utc_ms(WINDOW_END_UTC) - 1
    with pytest.raises(WindowNotReadyError):
        runner.readiness(
            WINDOW_START_UTC,
            _ready_probe(early, IN_SCOPE_ASSETS),
            IN_SCOPE_ASSETS,
            WINDOW_HOURS,
        )


def test_the_readiness_test_passes_at_the_window_end_and_reads_no_candle() -> None:
    at_end = runner.parse_utc_ms(WINDOW_END_UTC)
    record = runner.readiness(
        WINDOW_START_UTC,
        _ready_probe(at_end, IN_SCOPE_ASSETS),
        IN_SCOPE_ASSETS,
        WINDOW_HOURS,
    )
    assert record["ready"] is True
    assert record["fetched_candles"] == 0
    assert record["increments_holdout_exposed_count"] is False
    assert record["bounds"]["earliest_end_utc"] == WINDOW_END_UTC


def test_the_readiness_test_refuses_a_pair_that_is_not_trading() -> None:
    at_end = runner.parse_utc_ms(WINDOW_END_UTC)
    probe = _ready_probe(at_end, IN_SCOPE_ASSETS)
    probe["pair_statuses"]["ETHUSDT"] = "BREAK"
    with pytest.raises(WindowNotReadyError):
        runner.readiness(WINDOW_START_UTC, probe, IN_SCOPE_ASSETS, WINDOW_HOURS)


def test_the_readiness_probe_uses_only_metadata_endpoints() -> None:
    from v2_confirmatory import window

    assert window.SERVER_TIME_PATH == "/api/v3/time"
    assert window.EXCHANGE_INFO_PATH == "/api/v3/exchangeInfo"
    for primary, failover in window.METADATA_ENDPOINTS:
        assert primary.startswith(window.PRIMARY_HOST)
        assert failover.startswith(window.FAILOVER_HOST)


# --------------------------------------------------------------------------
# 5. The authorization validator refuses every tampered authorization.
# --------------------------------------------------------------------------


def test_the_authorization_validates_against_the_delivered_tree() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    assert plan.run_id == "v2-confirmatory-20260117"
    assert sorted(plan.selected) == list(IN_SCOPE_ASSETS)
    assert plan.data_scope_assets == list(IN_SCOPE_ASSETS)
    assert plan.cost_multipliers == [1.0, 2.0, 3.0]
    assert plan.minimum_closed_hourly_candles == WINDOW_HOURS
    assert plan.earliest_end_utc == WINDOW_END_UTC


def test_the_authorization_is_refused_when_its_code_identity_is_stale(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "stale_identity")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["code_identity"]["execution_path_digest"] = "0" * 64
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_the_scope_is_widened(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "widened_scope")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["scope"]["assets"] = list(IN_SCOPE_ASSETS) + ["BTCUSDT"]
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_it_is_edited(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "edited_authorization")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["max_runs"] = 2
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_a_path_points_at_a_v1_artifact(
    tmp_path: Path,
) -> None:
    root = _mirror(tmp_path / "forbidden_path")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["paths"]["report"] = "research/results.jsonl"
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ScopeError):
        runner.build_plan(runner.default_workspace(root))


def test_the_preconditions_refuse_an_uncommitted_run() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record={"ready": True},
        window_manifest={"readiness": {"ready": True}},
        exposure_state=exposure.empty_state(),
        committed={"authorization": False, "protocol": True, "amendment": True},
    )
    assert any("not committed" in failure for failure in failures)


def test_the_preconditions_refuse_a_missing_readiness_record() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record=None,
        window_manifest=None,
        exposure_state=exposure.empty_state(),
        committed={"authorization": True, "protocol": True, "amendment": True},
    )
    assert any("readiness" in failure for failure in failures)


def test_the_preconditions_refuse_a_window_that_is_already_exposed() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "another-run", "ADAUSDT", 1, 2, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record={"ready": True},
        window_manifest={"readiness": {"ready": True}},
        exposure_state=state,
        committed={"authorization": True, "protocol": True, "amendment": True},
    )
    assert any("already exposed" in failure for failure in failures)


def test_the_preconditions_refuse_a_changed_v1_artifact(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "changed_v1")
    target = root / "research" / "candidate_manifest.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    plan = runner.build_plan(runner.default_workspace(root))
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record={"ready": True},
        window_manifest={"readiness": {"ready": True}},
        exposure_state=exposure.empty_state(),
        committed={"authorization": True, "protocol": True, "amendment": True},
    )
    assert any("candidate_manifest.json" in failure for failure in failures)


# --------------------------------------------------------------------------
# 6. The exposure counter: once per event, never decreasing.
# --------------------------------------------------------------------------


def test_the_exposure_counter_increments_once_per_event() -> None:
    state = exposure.empty_state()
    assert state["holdout_exposed_count"] == 0
    state, _event, incremented = exposure.register_exposure(
        state, "run-1", "ADAUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    assert incremented is True
    assert state["holdout_exposed_count"] == 1
    state, _event, incremented = exposure.register_exposure(
        state, "run-1", "ETHUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:01:00Z"
    )
    assert incremented is True
    assert state["holdout_exposed_count"] == 2


def test_a_continuation_of_the_same_event_does_not_increment() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ADAUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    state, event, incremented = exposure.register_exposure(
        state, "run-1", "ADAUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:05:00Z"
    )
    assert incremented is False
    assert state["holdout_exposed_count"] == 1
    assert event["continuations"][-1]["utc"] == "2026-10-20T00:05:00Z"


def test_a_read_under_different_bounds_is_refused() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ADAUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            state, "run-1", "ADAUSDT", 1000, 3000, list(IN_SCOPE_ASSETS), "2026-10-20T00:05:00Z"
        )


def test_a_read_outside_the_scope_is_refused() -> None:
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            exposure.empty_state(),
            "run-1",
            "DOGEUSDT2",
            1000,
            2000,
            list(IN_SCOPE_ASSETS),
            "2026-10-20T00:00:00Z",
        )


def test_the_exposure_counter_never_decreases() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ADAUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    with pytest.raises(WindowExposureError):
        exposure.assert_monotonic(state, exposure.empty_state())

    # A reset attempt -- a counter below the number of recorded events -- fails closed.
    reset = {"holdout_exposed_count": 0, "exposure_events": state["exposure_events"]}
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            reset, "run-1", "ETHUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:01:00Z"
        )


# --------------------------------------------------------------------------
# 7. The criterion reconciliation of decision D-5.
# --------------------------------------------------------------------------


def _metrics(net_1x: float, net_2x: float, trades: int) -> Dict[str, Any]:
    return {
        "net_total_return_1x": net_1x,
        "net_total_return_2x": net_2x,
        "net_total_return_3x": net_1x,
        "closed_trades": trades,
        "data_sufficient": True,
        "parameters_match": True,
    }


def test_the_specification_criterion_governs_and_the_baseline_is_reported() -> None:
    outcome = report.asset_outcome("ADAUSDT", "cfg_0073", _metrics(0.05, 0.04, 40), 0.10)
    assert outcome["status"] == report.STATUS_SURVIVAL
    assert outcome["baseline_comparison"]["outcome"] == "FAIL"
    assert outcome["criteria_agreement"] == "DISAGREE"
    assert outcome["criteria"]["net_total_return_positive_at_1x"] is True
    assert outcome["criteria"]["closed_trades_at_least_threshold"] is True


def test_a_disagreement_is_marked_and_the_status_vocabulary_is_not_extended() -> None:
    outcome = report.asset_outcome("ADAUSDT", "cfg_0073", _metrics(0.05, 0.04, 40), 0.10)
    assert outcome["criteria_agreement"] in {"AGREE", "DISAGREE", "NOT_COMPARABLE"}
    assert outcome["status"] in {
        report.STATUS_SURVIVAL,
        report.STATUS_REJECTED,
        report.STATUS_INCONCLUSIVE,
        report.STATUS_PENDING,
    }
    agreeing = report.asset_outcome("ETHUSDT", "cfg_1241", _metrics(0.05, 0.04, 40), 0.01)
    assert agreeing["criteria_agreement"] == "AGREE"


def test_the_zero_trade_case_is_inconclusive_and_not_a_failure() -> None:
    outcome = report.asset_outcome("ADAUSDT", "cfg_0073", _metrics(0.0, 0.0, 0), 0.01)
    assert outcome["status"] == report.STATUS_INCONCLUSIVE
    assert outcome["criteria_evaluated"] is False
    assert outcome["criteria_agreement"] == "NOT_COMPARABLE"


def test_a_low_trade_count_is_rejected_on_the_holdout() -> None:
    outcome = report.asset_outcome("ADAUSDT", "cfg_0073", _metrics(0.5, 0.4, 29), 0.01)
    assert outcome["status"] == report.STATUS_REJECTED
    assert outcome["criteria"]["closed_trades_at_least_threshold"] is False


def test_insufficient_data_is_inconclusive() -> None:
    metrics = _metrics(0.5, 0.4, 40)
    metrics["data_sufficient"] = False
    outcome = report.asset_outcome("ADAUSDT", "cfg_0073", metrics, 0.01)
    assert outcome["status"] == report.STATUS_INCONCLUSIVE


def test_the_amendment_records_the_precedence_and_edits_no_frozen_artifact() -> None:
    document = _load(REPO_ROOT / "configs" / "research_v2_confirmatory_protocol_amendment_1.json")
    assert document["manifest_hash"] == AMENDMENT_HASH
    assert document["manifest_hash"] == _manifest_hash(document)
    assert (
        document["criterion_precedence"]["authoritative_source"]
        == "configs/research_v2.json#holdout.promotion_rule"
    )
    assert document["criterion_precedence"]["secondary_never_assigns_the_status"] is True
    assert document["verdicts"]["zero_trade_status"] == "INCONCLUSIVE"
    assert document["verdicts"]["low_trade_count_status"] == "REJECTED_ON_HOLDOUT"
    assert document["verdicts"]["status_vocabulary_is_not_extended"] is True
    assert document["amends"]["edits_no_frozen_artifact"] is True


# --------------------------------------------------------------------------
# 8. The data path: the canonical hourly CSV of the frozen hash scheme.
# --------------------------------------------------------------------------


def test_the_canonical_dataset_rendering_matches_the_frozen_hash_scheme() -> None:
    rows = _synthetic_rows("ADAUSDT", runner.parse_utc_ms(WINDOW_START_UTC), count=5)
    candles, rejected = data.parse_klines("ADAUSDT", rows)
    assert rejected == 0
    rendered = data.render_dataset_csv(candles)
    import hashlib

    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == compute_content_hash(candles)
    assert data.parse_dataset_csv(rendered, "ADAUSDT") == candles


def test_the_window_dataset_is_hash_verified_and_gaps_are_recorded() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    rows = _synthetic_rows("ADAUSDT", start, count=10)
    candles, record = data.retrieve_window_candles("ADAUSDT", rows, start, start + 10 * HOUR_MS)
    assert record["hash_algorithm"] == "sha256-canonical-hourly-csv-v1"
    assert record["observed_candle_count"] == 10
    assert record["gaps"] == []
    assert data.verify_window_dataset(record, candles) == record["content_hash"]

    gapped = [row for index, row in enumerate(rows) if index != 5]
    _candles, gap_record = data.retrieve_window_candles(
        "ADAUSDT", gapped, start, start + 10 * HOUR_MS
    )
    assert gap_record["gaps"], "the coverage gap is not recorded"
    assert gap_record["gaps"][0]["missing_candles"] == 1


# --------------------------------------------------------------------------
# 9. The run: the output layout, the exposure and the report.
# --------------------------------------------------------------------------


@pytest.fixture()
def mirror_repo(tmp_path: Path) -> Path:
    return _mirror(tmp_path / "repo")


def _ready_fetch(plan: runner.Plan):
    def fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        count = max(1, (end_ms - start_ms) // HOUR_MS)
        return _synthetic_rows(asset, start_ms, count=count)

    return fetch


def test_the_run_writes_only_the_confirmatory_paths(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    result = runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )

    assert result["outcome"] in {
        "CANDIDATES_SURVIVED_THE_CONFIRMATORY_WINDOW",
        "CANDIDATES_SURVIVED_THE_CONFIRMATORY_WINDOW_WITH_REPORTED_DISAGREEMENT",
        "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE",
    }
    for relative in (
        "research/v2_confirmatory_window_manifest.json",
        "research/ledger_v2_confirmatory.json",
        "research/results_manifest_v2_confirmatory.json",
        "research/results_v2_confirmatory.jsonl",
        "research_state/checkpoint_v2_confirmatory.json",
        "reports/confirmatory_evaluation_v2.json",
        "reports/confirmatory_report_v2.md",
    ):
        assert (mirror_repo / relative).exists(), relative
    assert (mirror_repo / "research" / "shards_v2_confirmatory").is_dir()

    # The v1 and v2-selection paths are untouched.
    for relative in runner.FORBIDDEN_OUTPUT_PATHS:
        target = mirror_repo / relative.rstrip("/")
        if target.exists() and target.is_file():
            assert relative not in {
                "research/results.jsonl",
                "research/results_manifest.json",
            }
    assert (mirror_repo / "research" / "ledger_v2.json").exists()
    assert (mirror_repo / "research_state" / "checkpoint_v2.json").exists()


def test_the_run_reports_every_asset_of_the_frozen_scope(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    report_document = runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )

    assert sorted(report_document["per_asset_outcomes"]) == list(IN_SCOPE_ASSETS)
    assert sorted(report_document["assets_without_candidate"]) == list(OUT_OF_SCOPE_ASSETS)
    assert report_document["assets_without_candidate_reported"] is True
    assert report_document["assets_without_candidate_status"] == "NO_CANDIDATE_NOT_EVALUATED"
    for field in report.REQUIRED_REPORT_FIELDS:
        assert field in report_document

    rows = [
        json.loads(line)
        for line in (mirror_repo / "research" / "results_v2_confirmatory.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) == len(IN_SCOPE_ASSETS)
    assert {row["asset"] for row in rows} == set(IN_SCOPE_ASSETS)


def test_the_run_counts_every_read_in_the_exposure_counter(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    report_document = runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )
    assert report_document["exposure_count"] == len(IN_SCOPE_ASSETS)

    checkpoint = _load(mirror_repo / "research_state" / "checkpoint_v2_confirmatory.json")
    assert checkpoint["holdout_exposed_count"] == len(IN_SCOPE_ASSETS)
    assert len(checkpoint["exposure"]["exposure_events"]) == len(IN_SCOPE_ASSETS)

    window_manifest = _load(mirror_repo / "research" / "v2_confirmatory_window_manifest.json")
    assert window_manifest["manifest_hash"] == _manifest_hash(window_manifest)
    assert window_manifest["data_manifest"]["edited"] is False
    for record in window_manifest["assets"].values():
        assert record["observed_candle_count"] == WINDOW_HOURS
        assert record["hash_verified"] is True


def test_the_readiness_probe_does_not_read_a_candle(mirror_repo: Path) -> None:
    """The probe is metadata-only: the run reads nothing before it passes."""
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    calls: List[str] = []

    def fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        calls.append(asset)
        return []

    with pytest.raises(WindowNotReadyError):
        runner.run_confirmatory(
            workspace,
            probe=lambda pairs: _ready_probe(
                runner.parse_utc_ms(WINDOW_END_UTC) - 1, pairs
            ),
            fetch_rows=fetch,
        )
    assert calls == []


def test_an_abort_before_the_first_payload_read_rolls_back(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    def failing_fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        raise RuntimeError("the provider is unreachable")

    with pytest.raises(RuntimeError):
        runner.run_confirmatory(
            workspace,
            probe=lambda pairs: _ready_probe(at_end, pairs),
            fetch_rows=failing_fetch,
        )

    assert not (mirror_repo / "research" / "v2_confirmatory_window_manifest.json").exists()
    assert not (mirror_repo / "research_state" / "checkpoint_v2_confirmatory.json").exists()
    assert not (mirror_repo / "research" / "shards_v2_confirmatory").exists()


def test_an_abort_after_a_payload_read_keeps_the_exposure(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)
    calls: List[str] = []

    def failing_fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        calls.append(asset)
        if len(calls) > 2:
            raise RuntimeError("the provider failed mid-window")
        count = max(1, (end_ms - start_ms) // HOUR_MS)
        return _synthetic_rows(asset, start_ms, count=count)

    with pytest.raises(RuntimeError):
        runner.run_confirmatory(
            workspace,
            probe=lambda pairs: _ready_probe(at_end, pairs),
            fetch_rows=failing_fetch,
        )

    checkpoint = _load(mirror_repo / "research_state" / "checkpoint_v2_confirmatory.json")
    assert checkpoint["status"] == "EXPOSED_ABORTED"
    # The last call failed before it returned a payload, so it exposed nothing.
    assert checkpoint["holdout_exposed_count"] == len(calls) - 1
    assert not (mirror_repo / "reports" / "confirmatory_evaluation_v2.json").exists()


def test_a_resumed_run_does_not_read_the_window_a_second_time(mirror_repo: Path) -> None:
    """A resumed run reuses the persisted, hash-verified dataset."""
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)
    calls: List[str] = []

    def failing_fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        calls.append(asset)
        if len(calls) > 1:
            raise RuntimeError("the provider failed mid-window")
        count = max(1, (end_ms - start_ms) // HOUR_MS)
        return _synthetic_rows(asset, start_ms, count=count)

    with pytest.raises(RuntimeError):
        runner.run_confirmatory(
            workspace,
            probe=lambda pairs: _ready_probe(at_end, pairs),
            fetch_rows=failing_fetch,
        )
    reads_before = len(calls)

    resumed_calls: List[str] = []

    def counting_fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        resumed_calls.append(asset)
        count = max(1, (end_ms - start_ms) // HOUR_MS)
        return _synthetic_rows(asset, start_ms, count=count)

    runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=counting_fetch,
    )
    # The first asset's dataset was persisted and hash-verified, so the resume
    # reads it from the store instead of reading the window a second time.
    assert reads_before == 2
    assert len(resumed_calls) == len(IN_SCOPE_ASSETS) - 1
    assert IN_SCOPE_ASSETS[0] not in resumed_calls


def test_the_run_never_writes_the_repository_paths(mirror_repo: Path) -> None:
    """The fixture run writes only inside the mirror."""
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)
    runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )
    for relative in CONFIRMATORY_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists()


# --------------------------------------------------------------------------
# 10. The verifier.
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_delivered_tree() -> None:
    status, report_document = _run_verifier(REPO_ROOT)
    assert status == 0, report_document
    assert report_document["failures"] == []
    assert report_document["in_scope_assets"] == 14
    assert report_document["out_of_scope_assets"] == list(OUT_OF_SCOPE_ASSETS)
    assert report_document["confirmatory_artifacts_present"] == []
    assert report_document["canonical_source_digest"] == CANONICAL_HASHED_SET_DIGEST


def test_the_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "widened_scope")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["scope"]["assets"] = list(IN_SCOPE_ASSETS) + ["BTCUSDT"]
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any("scope" in failure for failure in report_document["failures"])


def test_the_verifier_detects_an_edited_authorization(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "edited_authorization")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["bounds"]["attempts"] = 5
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "authorization manifest hash does not recompute" in failure
        for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_mismatched_code_identity(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "stale_identity")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["code_identity"]["run_code_identity"] = "0" * 64
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "run code identity" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_reset_exposure_counter(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reset_counter")
    checkpoint = root / "research_state" / "checkpoint_v2_confirmatory.json"
    checkpoint.write_text(
        json.dumps(
            {
                "run_id": "v2-confirmatory-20260117",
                "status": "COMPLETED",
                "holdout_exposed_count": 0,
                "exposure": {
                    "holdout_exposed_count": 0,
                    "exposure_events": [
                        {
                            "run_id": "v2-confirmatory-20260117",
                            "asset": "ADAUSDT",
                            "window_start_ms": 1,
                            "window_end_ms": 2,
                        }
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "exposure count was reset" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_forbidden_v1_path(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "forbidden_path")
    path = root / "configs" / "research_v2_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["paths"]["ledger"] = "research/ledger_v2.json"
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any("forbidden" in failure for failure in report_document["failures"])


def test_the_verifier_detects_a_flipped_criterion_precedence(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "flipped_precedence")
    path = root / "configs" / "research_v2_confirmatory_protocol_amendment_1.json"
    document = _load(path)
    document["criterion_precedence"]["authoritative_source"] = (
        "configs/research_v2_confirmatory_protocol.json#reporting_and_falsifiers"
    )
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "frozen specification authoritative" in failure
        for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_window_that_was_never_read() -> None:
    status, report_document = _run_verifier(REPO_ROOT)
    assert status == 0
    assert report_document["confirmatory_artifacts_present"] == []

    data_manifest = _load(REPO_ROOT / "research" / "data_manifest_v2.json")
    window = data_manifest.get("confirmatory_window") or {}
    assert window.get("confirmatory_window_status") == "NOT_STARTED"
    assert window.get("holdout_exposed_count") == 0

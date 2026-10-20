"""Deterministic, offline tests of the v3 confirmatory evaluation path.

The tests cover the delivered path: the package, the frozen scope, the window
benchmark rule, the single confirmatory criterion, the exposure accounting,
the output layout, the authorization and the verifier's tamper controls.

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

from v3_confirmatory import (  # noqa: E402
    artifacts,
    benchmark,
    data,
    errors,
    exposure,
    identity,
    report,
    runner,
    scope,
)
from v3_confirmatory.errors import (  # noqa: E402
    AuthorizationError,
    BenchmarkAlignmentError,
    ScopeError,
    WindowExposureError,
    WindowNotReadyError,
)

CANONICAL_HASHED_SET_DIGEST = (
    "3e8e4169522d962c004a9e649ea8c978e08f52f4d6102bb68737f7d4180ba0ff"
)
SELECTED_CONFIGURATIONS_HASH = (
    "3d24a278f13f8c6878905d45be25d0c0cbd84c0c1138d44c0db41b8d56fb5b53"
)
PROTOCOL_HASH = "f008876ba5b85f33c8cb9a4c647f6db71ec8bc067d4635e99905ea323d2bf95e"
WINDOW_START_UTC = "2026-10-20T13:00:00Z"
WINDOW_END_UTC = "2027-01-18T13:00:00Z"
WINDOW_HOURS = 2160
RUN_ID = "v3-confirmatory-20270118"

IN_SCOPE_ASSETS = ("ICPUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT")
OUT_OF_SCOPE_ASSETS = ("AAVEUSDT", "QNTUSDT")
BENCHMARK_ASSET = "BTCUSDT"

#: The artifacts a confirmatory evaluation would create inside the repository.
CONFIRMATORY_ARTIFACTS = (
    "research/v3_confirmatory_window_manifest.json",
    "research/shards_v3_confirmatory",
    "research/ledger_v3_confirmatory.json",
    "research/results_manifest_v3_confirmatory.json",
    "research/results_v3_confirmatory.jsonl",
    "research_state/checkpoint_v3_confirmatory.json",
    "reports/confirmatory_evaluation_v3.json",
    "reports/confirmatory_report_v3.md",
)

#: The artifacts the mirror copies.
MIRROR_FILES = (
    "configs/research_v1.json",
    "configs/research_v2.json",
    "configs/research_v2_candidate_freeze.json",
    "configs/research_v2_code_hash_amendment_1.json",
    "configs/research_v3.json",
    "configs/research_v3_candidate_freeze.json",
    "configs/research_v3_confirmatory_protocol.json",
    "configs/research_v3_confirmatory_authorization_1.json",
    "configs/research_v3_data_manifest_amendment_1.json",
    "configs/research_v3_selection_authorization_1.json",
    "research/config_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "research/data_manifest.json",
    "research/data_manifest_v2.json",
    "research/data_manifest_v3.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
    "research/universe_manifest.json",
    "research/universe_manifest_v2.json",
    "research/universe_manifest_v3.json",
    "research/v2_selected_configurations_manifest.json",
    "research/v3_selected_configurations_manifest.json",
    "research_state/campaign_authorization.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
)

MIRROR_TREES = ("src/breakout_research", "src/v3_confirmatory")

VERIFIER = "scripts/verify_v3_confirmatory_path.py"
PRODUCER = "scripts/build_v3_confirmatory_authorization_1.py"


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
    for tree in MIRROR_TREES:
        target = root / tree
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            REPO_ROOT / tree,
            target,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
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


def _synthetic_candles(asset: str, start_ms: int, count: int = WINDOW_HOURS) -> List[Candle]:
    candles, _rejected = data.parse_klines(asset, _synthetic_rows(asset, start_ms, count))
    return candles


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
    package = REPO_ROOT / "src" / "v3_confirmatory"
    assert package.is_dir()
    assert (package / "__init__.py").exists()
    modules = sorted(path.name for path in package.glob("*.py"))
    assert modules == [
        "__init__.py",
        "artifacts.py",
        "benchmark.py",
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
        "import v3_confirmatory\n"
        "assert v3_confirmatory.__version__\n"
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


def test_the_execution_path_lives_outside_the_hashed_set() -> None:
    hashed_set = REPO_ROOT / "src" / "breakout_research"
    execution_path = REPO_ROOT / "src" / "v3_confirmatory"
    assert not hashed_set.is_relative_to("src/v3_confirmatory")
    assert not execution_path.is_relative_to("src/breakout_research")
    assert identity.EXECUTION_PATH_ROOT == "src/v3_confirmatory"


# --------------------------------------------------------------------------
# 2. The tree identity: portable, order-independent and unchanged.
# --------------------------------------------------------------------------


def test_the_hashed_set_digest_is_unchanged_and_order_independent(monkeypatch) -> None:
    live = identity.hashed_set_digest(REPO_ROOT)
    assert live == CANONICAL_HASHED_SET_DIGEST

    # The canonical digest does not depend on the directory enumeration order of
    # the checkout: reversing that order changes the ordered digest that
    # ``compute_code_hash()`` returns, and leaves the canonical digest alone.
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
# 3. The scope is exactly the frozen four in, two out.
# --------------------------------------------------------------------------


def test_the_scope_is_the_frozen_four_and_two() -> None:
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
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS) + [BENCHMARK_ASSET], config_ids)
    with pytest.raises(ScopeError):
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS)[:-1], config_ids)

    reranked = dict(config_ids)
    reranked[IN_SCOPE_ASSETS[0]] = "cfg_0001"
    with pytest.raises(ScopeError):
        scope.assert_scope_matches(live, list(IN_SCOPE_ASSETS), reranked)


# --------------------------------------------------------------------------
# 4. The window benchmark rule: aligned, and fail-closed.
# --------------------------------------------------------------------------


def test_the_benchmark_rule_is_the_frozen_methodology() -> None:
    assert benchmark.BENCHMARK_SYMBOL == BENCHMARK_ASSET
    assert benchmark.ALIGNMENT_RULE == (
        "Align BTC and target asset by UTC candle close; no forward fill for missing "
        "BTC observations"
    )
    assert benchmark.ALIGNMENT_REFERENCE == "docs/research_protocol.md:101"
    assert benchmark.FAIL_CLOSED_REASONS == (
        "the benchmark series is missing",
        "the benchmark series is shorter than the evaluated window",
        "the benchmark series is not index-aligned with the asset series",
    )


def test_an_aligned_benchmark_is_accepted_and_reported() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    end = runner.parse_utc_ms(WINDOW_END_UTC)
    asset = _synthetic_candles("ICPUSDT", start, count=10)
    reference = _synthetic_candles(BENCHMARK_ASSET, start, count=10)

    report_document = benchmark.assert_window_alignment(
        asset, reference, "ICPUSDT", start, end
    )
    assert report_document["index_aligned"] is True
    assert report_document["forward_filled"] is False
    assert report_document["asset_candles"] == 10
    assert report_document["benchmark_candles"] == 10


def test_a_missing_benchmark_fails_closed() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    end = runner.parse_utc_ms(WINDOW_END_UTC)
    asset = _synthetic_candles("ICPUSDT", start, count=10)
    with pytest.raises(BenchmarkAlignmentError):
        benchmark.assert_window_alignment(asset, [], "ICPUSDT", start, end)


def test_a_short_benchmark_fails_closed() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    end = runner.parse_utc_ms(WINDOW_END_UTC)
    asset = _synthetic_candles("ICPUSDT", start, count=10)
    short = _synthetic_candles(BENCHMARK_ASSET, start, count=9)
    with pytest.raises(BenchmarkAlignmentError):
        benchmark.assert_window_alignment(asset, short, "ICPUSDT", start, end)


def test_a_misaligned_benchmark_fails_closed() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    end = runner.parse_utc_ms(WINDOW_END_UTC)
    asset = _synthetic_candles("ICPUSDT", start, count=10)
    shifted = _synthetic_candles(BENCHMARK_ASSET, start + HOUR_MS, count=10)
    with pytest.raises(BenchmarkAlignmentError):
        benchmark.assert_window_alignment(asset, shifted, "ICPUSDT", start, end)


def test_the_alignment_report_records_a_failure_instead_of_raising() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    end = runner.parse_utc_ms(WINDOW_END_UTC)
    asset = _synthetic_candles("ICPUSDT", start, count=10)
    shifted = _synthetic_candles(BENCHMARK_ASSET, start + HOUR_MS, count=10)

    failure = benchmark.alignment_report(asset, shifted, "ICPUSDT", start, end)
    assert failure["index_aligned"] is False
    assert failure["asset"] == "ICPUSDT"
    assert failure["error"]

    aligned = benchmark.alignment_report(
        asset, _synthetic_candles(BENCHMARK_ASSET, start, count=10), "ICPUSDT", start, end
    )
    assert aligned["index_aligned"] is True
    assert aligned["forward_filled"] is False


def test_the_candle_close_is_the_alignment_instant() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    candle = _synthetic_candles("ICPUSDT", start, count=1)[0]
    assert benchmark.candle_close_ms(candle) == int(candle.timestamp) + HOUR_MS


def test_the_development_benchmark_may_not_be_substituted() -> None:
    with pytest.raises(BenchmarkAlignmentError):
        benchmark.assert_window_benchmark_is_not_the_development_series(
            benchmark.DEVELOPMENT_BENCHMARK_CONTENT_HASH
        )
    with pytest.raises(BenchmarkAlignmentError):
        benchmark.assert_window_benchmark_is_not_the_development_series(
            "a" * 64,
            first_candle_timestamp=runner.parse_utc_ms(WINDOW_START_UTC) - HOUR_MS,
            window_start_ms=runner.parse_utc_ms(WINDOW_START_UTC),
        )
    # A window series that starts inside the window and is not the published
    # development dataset is accepted.
    benchmark.assert_window_benchmark_is_not_the_development_series(
        "b" * 64,
        first_candle_timestamp=runner.parse_utc_ms(WINDOW_START_UTC),
        window_start_ms=runner.parse_utc_ms(WINDOW_START_UTC),
    )


def test_a_configuration_is_never_dropped_because_it_needs_the_benchmark() -> None:
    """The benchmark rule is about the data, never about the grid."""
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    for asset, config_id in plan.selected.items():
        config = plan.configs[config_id]
        needs = benchmark.benchmark_required_for(config)
        assert isinstance(needs, bool)
        # Whatever the trend filter is, the configuration stays in the scope.
        assert asset in plan.selected


# --------------------------------------------------------------------------
# 5. The readiness test: metadata only, no payload read.
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
    probe["pair_statuses"]["ICPUSDT"] = "BREAK"
    with pytest.raises(WindowNotReadyError):
        runner.readiness(WINDOW_START_UTC, probe, IN_SCOPE_ASSETS, WINDOW_HOURS)


def test_the_readiness_probe_uses_only_metadata_endpoints() -> None:
    from v3_confirmatory import window

    assert window.SERVER_TIME_PATH == "/api/v3/time"
    assert window.EXCHANGE_INFO_PATH == "/api/v3/exchangeInfo"
    for primary, failover in window.METADATA_ENDPOINTS:
        assert primary.startswith(window.PRIMARY_HOST)
        assert failover.startswith(window.FAILOVER_HOST)


# --------------------------------------------------------------------------
# 6. The authorization: self-hashing, single-criterion, bound to the tree.
# --------------------------------------------------------------------------


def test_the_authorization_validates_against_the_delivered_tree() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    assert plan.run_id == RUN_ID
    assert sorted(plan.selected) == list(IN_SCOPE_ASSETS)
    assert plan.data_scope_assets == sorted(list(IN_SCOPE_ASSETS) + [BENCHMARK_ASSET])
    assert plan.cost_multipliers == [1.0, 2.0, 3.0]
    assert plan.minimum_closed_hourly_candles == WINDOW_HOURS
    assert plan.earliest_end_utc == WINDOW_END_UTC
    assert plan.window_start_utc == WINDOW_START_UTC
    assert plan.decision_rule["criterion_count"] == 1
    assert plan.decision_rule["authoritative_source"] == (
        "configs/research_v3.json#holdout.promotion_rule"
    )


def test_the_authorization_is_self_hashing_and_states_one_criterion() -> None:
    document = _load(REPO_ROOT / "configs" / "research_v3_confirmatory_authorization_1.json")
    assert document["manifest_hash"] == _manifest_hash(document)
    run = document["authorized_run"]
    assert run["decision_rule"]["criterion_count"] == 1
    assert run["decision_rule"]["exactly_one_criterion"] is True
    assert run["decision_rule"]["no_competing_criterion"] is True
    assert run["decision_rule"]["secondary_source"] is None
    assert run["decision_rule"]["secondary_field"] is None
    assert document["authorizes_evaluation_before_the_window_exists"] is False
    assert document["authorizes_a_candle_read_before_the_window_exists"] is False
    assert document["authorizes_a_benchmark_retrieval_before_the_window_exists"] is False


def test_the_authorization_is_reproducible_from_the_producer(tmp_path: Path) -> None:
    """The producer rebuilds the artifact byte for byte."""
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / PRODUCER), "--repo-root", str(REPO_ROOT), "--print"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    rebuilt = completed.stdout
    delivered = (REPO_ROOT / "configs" / "research_v3_confirmatory_authorization_1.json").read_text(
        encoding="utf-8"
    )
    assert json.loads(rebuilt) == json.loads(delivered)
    assert _manifest_hash(json.loads(rebuilt)) == json.loads(delivered)["manifest_hash"]


def test_the_authorization_is_refused_when_its_code_identity_is_stale(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "stale_identity")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["code_identity"]["execution_path_digest"] = "0" * 64
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_the_scope_is_widened(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "widened_scope")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["scope"]["assets"] = list(IN_SCOPE_ASSETS) + [BENCHMARK_ASSET]
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_it_is_edited(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "edited_authorization")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["max_runs"] = 2
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_a_path_points_at_a_forbidden_artifact(
    tmp_path: Path,
) -> None:
    root = _mirror(tmp_path / "forbidden_path")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["paths"]["report"] = "research/results.jsonl"
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ScopeError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_a_second_criterion_is_introduced(
    tmp_path: Path,
) -> None:
    root = _mirror(tmp_path / "second_criterion")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["decision_rule"]["criterion_count"] = 2
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_the_development_benchmark_may_be_reused(
    tmp_path: Path,
) -> None:
    root = _mirror(tmp_path / "development_benchmark")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["benchmark_rule"]["development_benchmark_may_be_reused"] = True
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_authorization_is_refused_when_the_window_start_is_moved(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "moved_window")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["window"]["window_start_utc"] = "2026-01-01T00:00:00Z"
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AuthorizationError):
        runner.build_plan(runner.default_workspace(root))


def test_the_preconditions_refuse_an_uncommitted_run() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record={"ready": True},
        window_manifest={"readiness": {"ready": True}},
        exposure_state=exposure.empty_state(),
        committed={"authorization": False, "protocol": True},
    )
    assert any("not committed" in failure for failure in failures)


def test_the_preconditions_refuse_a_missing_readiness_record() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record=None,
        window_manifest=None,
        exposure_state=exposure.empty_state(),
        committed={"authorization": True, "protocol": True},
    )
    assert any("readiness" in failure for failure in failures)


def test_the_preconditions_refuse_a_window_that_is_already_exposed() -> None:
    plan = runner.build_plan(runner.default_workspace(REPO_ROOT))
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "another-run", "ICPUSDT", 1, 2, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    failures = runner.evaluate_preconditions(
        plan,
        readiness_record={"ready": True},
        window_manifest={"readiness": {"ready": True}},
        exposure_state=state,
        committed={"authorization": True, "protocol": True},
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
        committed={"authorization": True, "protocol": True},
    )
    assert any("candidate_manifest.json" in failure for failure in failures)


# --------------------------------------------------------------------------
# 7. The exposure counter: once per event, never decreasing.
# --------------------------------------------------------------------------


def test_the_exposure_counter_increments_once_per_event() -> None:
    state = exposure.empty_state()
    assert state["holdout_exposed_count"] == 0
    state, _event, incremented = exposure.register_exposure(
        state, "run-1", "ICPUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    assert incremented is True
    assert state["holdout_exposed_count"] == 1
    state, _event, incremented = exposure.register_exposure(
        state, "run-1", "PEPEUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:01:00Z"
    )
    assert incremented is True
    assert state["holdout_exposed_count"] == 2


def test_a_continuation_of_the_same_event_does_not_increment() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ICPUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    state, event, incremented = exposure.register_exposure(
        state, "run-1", "ICPUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:05:00Z"
    )
    assert incremented is False
    assert state["holdout_exposed_count"] == 1
    assert event["continuations"][-1]["utc"] == "2026-10-20T00:05:00Z"


def test_a_read_under_different_bounds_is_refused() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ICPUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            state, "run-1", "ICPUSDT", 1000, 3000, list(IN_SCOPE_ASSETS), "2026-10-20T00:05:00Z"
        )


def test_a_read_outside_the_scope_is_refused() -> None:
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            exposure.empty_state(),
            "run-1",
            "DOGEUSDT",
            1000,
            2000,
            list(IN_SCOPE_ASSETS),
            "2026-10-20T00:00:00Z",
        )


def test_the_exposure_counter_never_decreases() -> None:
    state = exposure.empty_state()
    state, _event, _incremented = exposure.register_exposure(
        state, "run-1", "ICPUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:00:00Z"
    )
    with pytest.raises(WindowExposureError):
        exposure.assert_monotonic(state, exposure.empty_state())

    # A reset attempt -- a counter below the number of recorded events -- fails closed.
    reset = {"holdout_exposed_count": 0, "exposure_events": state["exposure_events"]}
    with pytest.raises(WindowExposureError):
        exposure.register_exposure(
            reset, "run-1", "PEPEUSDT", 1000, 2000, list(IN_SCOPE_ASSETS), "2026-10-20T00:01:00Z"
        )


# --------------------------------------------------------------------------
# 8. The single confirmatory criterion.
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


def test_the_promotion_rule_governs_and_no_second_criterion_is_applied() -> None:
    outcome = report.asset_outcome("ICPUSDT", "cfg_0444", _metrics(0.05, 0.04, 40), 0.10)
    assert outcome["status"] == report.STATUS_SURVIVAL
    assert outcome["criteria"]["net_total_return_positive_at_1x"] is True
    assert outcome["criteria"]["closed_trades_at_least_threshold"] is True
    # The v3 line states one criterion: the report carries no second one.
    assert "criteria_agreement" not in outcome
    assert "baseline_comparison" not in outcome


def test_the_zero_trade_case_is_inconclusive_and_not_a_failure() -> None:
    outcome = report.asset_outcome("ICPUSDT", "cfg_0444", _metrics(0.0, 0.0, 0), 0.01)
    assert outcome["status"] == report.STATUS_INCONCLUSIVE
    assert outcome["criteria_evaluated"] is False


def test_a_low_trade_count_is_rejected_on_the_holdout() -> None:
    outcome = report.asset_outcome("ICPUSDT", "cfg_0444", _metrics(0.5, 0.4, 29), 0.01)
    assert outcome["status"] == report.STATUS_REJECTED
    assert outcome["criteria"]["closed_trades_at_least_threshold"] is False


def test_insufficient_data_is_inconclusive() -> None:
    metrics = _metrics(0.5, 0.4, 40)
    metrics["data_sufficient"] = False
    outcome = report.asset_outcome("ICPUSDT", "cfg_0444", metrics, 0.01)
    assert outcome["status"] == report.STATUS_INCONCLUSIVE


def test_the_protocol_states_exactly_one_criterion() -> None:
    document = _load(REPO_ROOT / "configs" / "research_v3_confirmatory_protocol.json")
    assert document["manifest_hash"] == PROTOCOL_HASH
    assert document["manifest_hash"] == _manifest_hash(document)
    decision = document["decision_rule"]
    assert decision["criterion_count"] == 1
    assert decision["exactly_one_criterion"] is True
    assert decision["no_competing_criterion"] is True
    assert decision["authoritative_source"] == "configs/research_v3.json#holdout.promotion_rule"


# --------------------------------------------------------------------------
# 9. The data path: the canonical hourly CSV of the frozen hash scheme.
# --------------------------------------------------------------------------


def test_the_canonical_dataset_rendering_matches_the_frozen_hash_scheme() -> None:
    rows = _synthetic_rows("ICPUSDT", runner.parse_utc_ms(WINDOW_START_UTC), count=5)
    candles, rejected = data.parse_klines("ICPUSDT", rows)
    assert rejected == 0
    rendered = data.render_dataset_csv(candles)
    import hashlib

    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == compute_content_hash(candles)
    assert data.parse_dataset_csv(rendered, "ICPUSDT") == candles


def test_the_window_dataset_is_hash_verified_and_gaps_are_recorded() -> None:
    start = runner.parse_utc_ms(WINDOW_START_UTC)
    rows = _synthetic_rows("ICPUSDT", start, count=10)
    candles, record = data.retrieve_window_candles("ICPUSDT", rows, start, start + 10 * HOUR_MS)
    assert record["hash_algorithm"] == "sha256-canonical-hourly-csv-v1"
    assert record["observed_candle_count"] == 10
    assert record["gaps"] == []
    assert data.verify_window_dataset(record, candles) == record["content_hash"]

    gapped = [row for index, row in enumerate(rows) if index != 5]
    _candles, gap_record = data.retrieve_window_candles(
        "ICPUSDT", gapped, start, start + 10 * HOUR_MS
    )
    assert gap_record["gaps"], "the coverage gap is not recorded"
    assert gap_record["gaps"][0]["missing_candles"] == 1


# --------------------------------------------------------------------------
# 10. The run: the output layout, the exposure, the benchmark and the report.
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
        "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE",
    }
    for relative in (
        "research/v3_confirmatory_window_manifest.json",
        "research/ledger_v3_confirmatory.json",
        "research/results_manifest_v3_confirmatory.json",
        "research/results_v3_confirmatory.jsonl",
        "research_state/checkpoint_v3_confirmatory.json",
        "reports/confirmatory_evaluation_v3.json",
        "reports/confirmatory_report_v3.md",
    ):
        assert (mirror_repo / relative).exists(), relative
    assert (mirror_repo / "research" / "shards_v3_confirmatory").is_dir()

    # The v1, v2 and v3-selection paths are untouched.
    for relative in runner.FORBIDDEN_OUTPUT_PATHS:
        target = mirror_repo / relative.rstrip("/")
        if target.exists() and target.is_file():
            assert relative not in {
                "research/results.jsonl",
                "research/results_manifest.json",
            }
    assert (mirror_repo / "research" / "ledger_v3.json").exists()
    assert (mirror_repo / "research_state" / "checkpoint_v3.json").exists()


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
        for line in (mirror_repo / "research" / "results_v3_confirmatory.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) == len(IN_SCOPE_ASSETS)
    assert {row["asset"] for row in rows} == set(IN_SCOPE_ASSETS)


def test_the_run_records_the_window_benchmark_and_its_alignment(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    report_document = runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )

    window_manifest = _load(mirror_repo / "research" / "v3_confirmatory_window_manifest.json")
    benchmark_block = window_manifest["benchmark"]
    assert benchmark_block["symbol"] == BENCHMARK_ASSET
    assert benchmark_block["role"] == "window_benchmark"
    assert benchmark_block["hash_verified"] is True
    assert benchmark_block["development_benchmark_may_be_reused"] is False
    assert benchmark_block["forward_filled"] is False
    assert benchmark_block["retrieved_once_with_the_window"] is True
    assert benchmark_block["fail_closed"] == list(benchmark.FAIL_CLOSED_REASONS)
    assert BENCHMARK_ASSET in window_manifest["assets"]

    # The alignment of the benchmark with every asset series is recorded in the
    # ledger and in the report, both of which the run writes after the
    # alignment has been verified.
    ledger = _load(mirror_repo / "research" / "ledger_v3_confirmatory.json")
    for carrier in (ledger["benchmark"], report_document["benchmark"]):
        assert carrier["symbol"] == BENCHMARK_ASSET
        for asset in IN_SCOPE_ASSETS:
            alignment = carrier["alignments"][asset]
            assert alignment["index_aligned"] is True
            assert alignment["forward_filled"] is False
    assert report_document["benchmark"]["symbol"] == BENCHMARK_ASSET


def test_the_run_fails_closed_on_a_misaligned_benchmark(mirror_repo: Path) -> None:
    """A misaligned benchmark aborts the run before any result is written."""
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    def fetch(asset: str, start_ms: int, end_ms: int) -> List[List[Any]]:
        count = max(1, (end_ms - start_ms) // HOUR_MS)
        offset = HOUR_MS if asset == BENCHMARK_ASSET else 0
        return _synthetic_rows(asset, start_ms + offset, count=count)

    with pytest.raises(BenchmarkAlignmentError):
        runner.run_confirmatory(
            workspace,
            probe=lambda pairs: _ready_probe(at_end, pairs),
            fetch_rows=fetch,
        )
    assert not (mirror_repo / "reports" / "confirmatory_evaluation_v3.json").exists()


def test_the_run_counts_every_read_in_the_exposure_counter(mirror_repo: Path) -> None:
    workspace = runner.default_workspace(mirror_repo)
    plan = runner.build_plan(workspace)
    at_end = runner.parse_utc_ms(plan.earliest_end_utc)

    report_document = runner.run_confirmatory(
        workspace,
        probe=lambda pairs: _ready_probe(at_end, pairs),
        fetch_rows=_ready_fetch(plan),
    )
    # Every read inside the window counts, the benchmark included.
    assert report_document["exposure_count"] == len(IN_SCOPE_ASSETS) + 1

    checkpoint = _load(mirror_repo / "research_state" / "checkpoint_v3_confirmatory.json")
    assert checkpoint["holdout_exposed_count"] == len(IN_SCOPE_ASSETS) + 1
    assert len(checkpoint["exposure"]["exposure_events"]) == len(IN_SCOPE_ASSETS) + 1

    window_manifest = _load(mirror_repo / "research" / "v3_confirmatory_window_manifest.json")
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

    assert not (mirror_repo / "research" / "v3_confirmatory_window_manifest.json").exists()
    assert not (mirror_repo / "research_state" / "checkpoint_v3_confirmatory.json").exists()
    assert not (mirror_repo / "research" / "shards_v3_confirmatory").exists()


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

    checkpoint = _load(mirror_repo / "research_state" / "checkpoint_v3_confirmatory.json")
    assert checkpoint["status"] == "EXPOSED_ABORTED"
    # The last call failed before it returned a payload, so it exposed nothing.
    assert checkpoint["holdout_exposed_count"] == len(calls) - 1
    assert not (mirror_repo / "reports" / "confirmatory_evaluation_v3.json").exists()


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
    assert len(resumed_calls) == len(plan.data_scope_assets) - 1
    assert plan.data_scope_assets[0] not in resumed_calls


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
# 11. The verifier.
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_delivered_tree() -> None:
    status, report_document = _run_verifier(REPO_ROOT)
    assert status == 0, report_document
    assert report_document["failures"] == []
    assert report_document["in_scope_assets"] == 4
    assert report_document["out_of_scope_assets"] == list(OUT_OF_SCOPE_ASSETS)
    assert report_document["confirmatory_artifacts_present"] == []
    assert report_document["canonical_source_digest"] == CANONICAL_HASHED_SET_DIGEST
    assert report_document["benchmark_symbol"] == BENCHMARK_ASSET


def test_the_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "widened_scope")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["scope"]["assets"] = list(IN_SCOPE_ASSETS) + [BENCHMARK_ASSET]
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any("scope" in failure for failure in report_document["failures"])


def test_the_verifier_detects_an_edited_authorization(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "edited_authorization")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
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
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["code_identity"]["run_code_identity"] = "0" * 64
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "run code identity" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_second_criterion(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "second_criterion")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["decision_rule"]["criterion_count"] = 2
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "criterion" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_second_criterion_in_the_path(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "second_criterion_in_path")
    target = root / "src" / "v3_confirmatory" / "report.py"
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\n\ndef criteria_agreement():\n    return 'AGREE'\n",
        encoding="utf-8",
    )
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "second criterion surface" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_development_benchmark_substitution(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "development_benchmark")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["benchmark_rule"]["development_benchmark_may_be_reused"] = True
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "development benchmark" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_forbidden_path(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "forbidden_path")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorized_run"]["paths"]["ledger"] = "research/ledger_v3.json"
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any("forbidden" in failure for failure in report_document["failures"])


def test_the_verifier_detects_a_self_authorizing_authorization(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "self_authorizing")
    path = root / "configs" / "research_v3_confirmatory_authorization_1.json"
    document = _load(path)
    document["authorizes_evaluation_before_the_window_exists"] = True
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "before the window exists" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_an_edited_protocol(tmp_path: Path) -> None:
    """An edited protocol is detected twice: its own hash and the binding."""
    root = _mirror(tmp_path / "edited_protocol")
    path = root / "configs" / "research_v3_confirmatory_protocol.json"
    document = _load(path)
    document["decision_rule"]["criterion_count"] = 2
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "protocol manifest hash does not recompute" in failure
        for failure in report_document["failures"]
    )


def test_a_resealed_protocol_breaks_the_authorization_binding(tmp_path: Path) -> None:
    """A tamper that is resealed still breaks the authorization's binding."""
    root = _mirror(tmp_path / "resealed_protocol")
    path = root / "configs" / "research_v3_confirmatory_protocol.json"
    document = _load(path)
    document["decision_rule"]["criterion_count"] = 2
    _reseal(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "not bound to the confirmatory protocol" in failure
        for failure in report_document["failures"]
    )
    assert any(
        "does not state exactly one confirmatory decision criterion" in failure
        for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_modified_hashed_source_tree(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "modified_hashed_set")
    target = root / "src" / "breakout_research" / "config.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "canonical digest" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_v3_confirmatory_output_artifact(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "confirmatory_output")
    target = root / "research" / "ledger_v3_confirmatory.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\n", encoding="utf-8")
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "confirmatory artifact exists" in failure for failure in report_document["failures"]
    )


def test_the_verifier_detects_a_reset_exposure_counter(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "reset_counter")
    checkpoint = root / "research_state" / "checkpoint_v3_confirmatory.json"
    checkpoint.write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "status": "COMPLETED",
                "holdout_exposed_count": 0,
                "exposure": {
                    "holdout_exposed_count": 0,
                    "exposure_events": [
                        {
                            "run_id": RUN_ID,
                            "asset": "ICPUSDT",
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


def test_the_verifier_detects_a_missing_v1_artifact(tmp_path: Path) -> None:
    root = _mirror(tmp_path / "missing_v1")
    (root / "research" / "candidate_manifest.json").unlink()
    status, report_document = _run_verifier(root)
    assert status == 1
    assert any(
        "candidate_manifest.json" in failure for failure in report_document["failures"]
    )


def test_the_window_was_never_read() -> None:
    status, report_document = _run_verifier(REPO_ROOT)
    assert status == 0
    assert report_document["confirmatory_artifacts_present"] == []

    data_manifest = _load(REPO_ROOT / "research" / "data_manifest_v3.json")
    window = data_manifest.get("confirmatory_window") or {}
    assert window.get("confirmatory_window_status") == "NOT_STARTED"
    assert window.get("holdout_exposed_count") == 0

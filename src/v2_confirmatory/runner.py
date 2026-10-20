"""The bounded v2 confirmatory evaluation run.

This module drives **one** confirmatory evaluation of the 14 selected
configurations on the v2 confirmatory window. It is *not* executed by the
session that delivers it: the run requires the versioned authorization
``configs/research_v2_confirmatory_authorization_1.json``, and that
authorization permits **at most one** logical run, and only after the window
exists.

Boundaries the run enforces:

* the evaluation scope is exactly the 14 selected configurations of
  ``research/v2_selected_configurations_manifest.json``; it is never re-ranked,
  widened or narrowed, and the 4 assets without a candidate are reported as
  ``NO_CANDIDATE_NOT_EVALUATED``;
* the window is read **once**, after the metadata-only readiness test has
  passed, and every read is counted in ``holdout_exposed_count``;
* the evaluation uses the **unchanged v1 metric** and the **unchanged cost
  scenarios**; there is no re-tuning, no re-ranking and no grid extension on
  the window;
* only the new v2 confirmatory paths are written; the v1 paths and the v2
  *selection* paths are never touched and never tallied with;
* an abort before the first payload read rolls every created artifact back and
  leaves ``holdout_exposed_count = 0``; an abort **after** a payload read
  leaves the exposure in place and records the run as ``EXPOSED_ABORTED``,
  because the window is spent;
* the verdict follows the frozen specification's promotion rule; the protocol's
  buy-and-hold criterion is computed and reported alongside it, and a
  disagreement is disclosed (decision D-5).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from breakout_research.backtest.backtester import run_fold_backtest
from breakout_research.baselines import buyhold_fold_metrics
from breakout_research.config import CostScenario, get_configurations
from breakout_research.data.fetcher import compute_content_hash

from . import identity
from .artifacts import (
    EVALUATION_WINDOW_RULE,
    build_checkpoint,
    build_ledger,
    build_result_rows,
    build_results_manifest,
    render_jsonl,
    render_report_markdown,
    sha256_bytes,
)
from .data import (
    WINDOW_MANIFEST_RELATIVE,
    build_window_manifest,
    parse_dataset_csv,
    render_dataset_csv,
    retrieve_window_candles,
    verify_window_dataset,
)
from .errors import (
    AttemptBudgetError,
    AuthorizationError,
    BoundsError,
    ConfirmatoryError,
    ScopeError,
    WindowExposureError,
    WindowNotReadyError,
)
from .exposure import assert_monotonic, empty_state, register_exposure, window_is_spent
from .report import asset_outcome, build_report, report_outcome
from .scope import (
    SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
    assert_scope_matches,
    evaluation_scope,
)
from .window import (
    MIN_WINDOW_HOURS,
    format_utc_ms,
    metadata_probe,
    parse_utc_ms,
    readiness,
    window_bounds,
)

DEFAULT_PATHS = {
    "spec_v1": "configs/research_v1.json",
    "spec_v2": "configs/research_v2.json",
    "protocol": "configs/research_v2_confirmatory_protocol.json",
    "amendment": "configs/research_v2_confirmatory_protocol_amendment_1.json",
    "authorization": "configs/research_v2_confirmatory_authorization_1.json",
    "freeze": "configs/research_v2_candidate_freeze.json",
    "selected_configurations": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
    "data_manifest": "research/data_manifest_v2.json",
    "config_manifest": "research/config_manifest.json",
    "window_manifest": WINDOW_MANIFEST_RELATIVE,
    "shards_dir": "research/shards_v2_confirmatory",
    "ledger": "research/ledger_v2_confirmatory.json",
    "results_manifest": "research/results_manifest_v2_confirmatory.json",
    "results_stream": "research/results_v2_confirmatory.jsonl",
    "checkpoint": "research_state/checkpoint_v2_confirmatory.json",
    "report": "reports/confirmatory_evaluation_v2.json",
    "report_markdown": "reports/confirmatory_report_v2.md",
}

#: The v1 paths a v2 run may never write.
V1_PATHS_FORBIDDEN = (
    "research/results_shards/",
    "research/results_manifest.json",
    "research/results.jsonl",
    "research_state/checkpoint.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
    "configs/research_v1.json",
)

#: The v2 *selection* paths: the selection run's outputs are never tallied
#: with, extended by or written over by the confirmatory evaluation.
V2_SELECTION_PATHS_FORBIDDEN = (
    "research/shards_v2/",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)

#: Every path the confirmatory evaluation may not write.
FORBIDDEN_OUTPUT_PATHS = V1_PATHS_FORBIDDEN + V2_SELECTION_PATHS_FORBIDDEN


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
        newline="",
    )
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
        newline="",
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON document from disk."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Iterable[str]) -> str:
    """The self-hash of a hash-bound artifact."""
    import hashlib

    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Workspace:
    """Every path the run touches. Nothing is implied; nothing is defaulted."""

    repo_root: Path
    spec_v1: Path
    spec_v2: Path
    protocol: Path
    amendment: Path
    authorization: Path
    freeze: Path
    selected_configurations: Path
    data_manifest: Path
    config_manifest: Path
    window_manifest: Path
    shards_dir: Path
    ledger: Path
    results_manifest: Path
    results_stream: Path
    checkpoint: Path
    report: Path
    report_markdown: Path


def default_workspace(repo_root: Path) -> Workspace:
    """The repository's standard v2 confirmatory workspace."""
    root = Path(repo_root)
    return Workspace(repo_root=root, **{name: root / relative for name, relative in DEFAULT_PATHS.items()})


@dataclass
class Plan:
    """The validated, frozen description of the run that may execute."""

    workspace: Workspace
    run_id: str
    campaign_id: str
    scope: Dict[str, Any]
    selected: Dict[str, str]
    data_scope_assets: List[str]
    benchmark_asset: str
    window_start_utc: str
    minimum_closed_hourly_candles: int
    earliest_end_utc: str
    bounds: Dict[str, Any]
    paths: Dict[str, str]
    code_identity: Dict[str, Any]
    criteria_precedence: Dict[str, Any]
    cost_multipliers: List[float]
    authorization_manifest_hash: str
    amendment_manifest_hash: str
    protocol_manifest_hash: str
    specification_hash: str
    candidate_manifest_hash: str
    data_manifest_hash: str
    immutable_anchors: Dict[str, Dict[str, str]] = field(default_factory=dict)
    window_rule: str = EVALUATION_WINDOW_RULE
    configs: Dict[str, Any] = field(default_factory=dict)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationError(message)


def assert_output_paths_allowed(paths: Dict[str, str]) -> None:
    """Fail closed when an output path points at a v1 or v2-selection artifact."""
    for name, path in paths.items():
        for banned in FORBIDDEN_OUTPUT_PATHS:
            root = banned.rstrip("/")
            if path == root or path.startswith(root + "/"):
                raise ScopeError(
                    f"the confirmatory output path {name} points at the forbidden path {banned}"
                )


def sha256_file(path: Path) -> str:
    """The sha256 of a file's bytes."""
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def immutable_artifact_failures(
    repo_root: Path, anchors: Dict[str, Dict[str, str]]
) -> List[str]:
    """Which of the frozen artifacts no longer match their recorded sha256.

    The anchors are the ones the authorization records: the v1 evidence and the
    v2 *selection* outputs. A confirmatory run may not proceed while any of them
    has changed.
    """
    root = Path(repo_root)
    failures: List[str] = []
    for group, entries in sorted((anchors or {}).items()):
        for relative, expected in sorted((entries or {}).items()):
            target = root / relative
            if not target.exists():
                failures.append(f"the frozen {group} artifact {relative} is missing")
                continue
            observed = sha256_file(target)
            if observed != expected:
                failures.append(
                    f"the frozen {group} artifact {relative} changed: recorded {expected}, "
                    f"observed {observed}"
                )
    return failures


def build_plan(workspace: Workspace) -> Plan:
    """Validate every bound of the confirmatory run and resolve what it may touch.

    Nothing is executed here: the plan is the frozen description that the
    authorization permits. Every expectation is recomputed from the repository.
    """
    root = Path(workspace.repo_root)
    authorization = load_json(workspace.authorization)
    amendment = load_json(workspace.amendment)
    protocol = load_json(workspace.protocol)
    spec_v1 = load_json(workspace.spec_v1)
    spec_v2 = load_json(workspace.spec_v2)
    freeze = load_json(workspace.freeze)
    data_manifest = load_json(workspace.data_manifest)
    selected_manifest = load_json(workspace.selected_configurations)

    excluded = tuple(authorization.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    _require(bool(excluded), "the authorization does not declare its manifest_hash_excluded_keys")
    declared = authorization.get("manifest_hash")
    recomputed = compute_manifest_hash(authorization, excluded)
    _require(
        declared == recomputed,
        f"the authorization manifest hash does not recompute: declared {declared}, "
        f"recomputed {recomputed}",
    )

    run = authorization.get("authorized_run") or {}
    _require(run.get("authorized") is True, "the authorization does not authorize a run")
    _require(run.get("max_runs") == 1, "the authorization does not bound the run to one attempt")

    scope = evaluation_scope(root)
    selections = selected_manifest.get("selections") or {}
    expected_assets = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    expected_configs = {
        asset: str((selections.get(asset) or {}).get("config_id")) for asset in expected_assets
    }
    assert_scope_matches(scope, expected_assets, expected_configs)
    recorded_scope = run.get("scope") or {}
    _require(
        sorted(recorded_scope.get("assets") or []) == expected_assets,
        "the authorized scope is not the frozen evaluation scope",
    )
    _require(
        (recorded_scope.get("config_ids") or {}) == expected_configs,
        "the authorized configuration ids are not the frozen configuration ids",
    )
    _require(
        recorded_scope.get("bound_to_selected_configurations_hash")
        == scope["selected_configurations_manifest_hash"],
        "the authorization is not bound to the selected-configurations manifest",
    )

    code_identity = identity.resolve_code_identity(root, dict(run.get("code_identity") or {}))
    live_hashed_set = identity.hashed_set_digest(root)
    live_execution_path = identity.execution_path_digest(root)
    _require(
        code_identity.get("hashed_set_digest") == live_hashed_set,
        "the authorized hashed-set digest does not match the current source tree",
    )
    _require(
        code_identity.get("execution_path_digest") == live_execution_path,
        "the authorized execution-path digest does not match the current execution path",
    )
    _require(
        code_identity.get("run_code_identity")
        == identity.run_code_identity(live_hashed_set, live_execution_path),
        "the recorded run code identity is not the composite of the two live digests",
    )

    paths = {key: str(value) for key, value in (run.get("paths") or {}).items()}
    for key in (
        "shards_dir",
        "ledger",
        "results_manifest",
        "results_stream",
        "checkpoint",
        "window_manifest",
        "report",
        "report_markdown",
    ):
        _require(bool(paths.get(key)), f"the authorization names an empty confirmatory path {key}")
    assert_output_paths_allowed(paths)
    forbidden = [str(value) for value in (run.get("forbidden_paths") or [])]
    _require(
        sorted(forbidden) == sorted(FORBIDDEN_OUTPUT_PATHS),
        "the authorization does not record the forbidden v1 and v2-selection paths",
    )

    # The run writes where the authorization says it may write: the workspace's
    # paths must be exactly the authorized ones.
    for name, relative in DEFAULT_PATHS.items():
        authorized = paths.get(name)
        if authorized is None:
            continue
        _require(
            authorized == relative,
            f"the authorized path {name} is {authorized} but the workspace path is {relative}; "
            "the run may only write where the authorization points it",
        )

    bounds = dict(run.get("bounds") or {})
    _require(
        bounds.get("max_assets") == len(expected_assets),
        "the authorized asset bound differs from the frozen evaluation scope",
    )
    _require(bounds.get("attempts") == 1, "the authorization does not bound the run to one attempt")
    _require(
        int(bounds.get("max_retries_on_technical_failure") or 0) > 0,
        "the authorization records no technical-failure retries",
    )

    window = run.get("window") or {}
    frozen_start = (freeze.get("data_boundary") or {}).get("confirmatory_window_start_utc")
    _require(
        window.get("window_start_utc") == frozen_start,
        "the authorized window start is not the frozen confirmatory-window start",
    )
    _require(
        window.get("minimum_closed_hourly_candles") == MIN_WINDOW_HOURS,
        "the authorized window does not require the frozen 2,160 closed hourly candles",
    )
    bounds_utc = window_bounds(frozen_start, MIN_WINDOW_HOURS)
    _require(
        window.get("earliest_possible_end_utc") == bounds_utc["earliest_end_utc"],
        "the authorized earliest window end does not follow from the window start",
    )

    amendment_excluded = tuple(
        amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ()
    )
    _require(
        bool(amendment_excluded),
        "the protocol amendment does not declare its manifest_hash_excluded_keys",
    )
    _require(
        amendment.get("manifest_hash")
        == compute_manifest_hash(amendment, amendment_excluded),
        "the protocol amendment manifest hash does not recompute",
    )
    precedence = dict(amendment.get("criterion_precedence") or {})
    _require(
        precedence.get("authoritative_source") == "configs/research_v2.json#holdout.promotion_rule",
        "the protocol amendment does not record the specification as the authoritative source",
    )
    _require(
        (amendment.get("amends") or {}).get("protocol_manifest_hash")
        == protocol.get("manifest_hash"),
        "the protocol amendment does not amend the recorded protocol",
    )
    _require(
        (amendment.get("amends") or {}).get("specification_hash") == spec_v2.get("specification_hash"),
        "the protocol amendment does not amend the recorded v2 specification",
    )
    _require(
        protocol.get("manifest_hash") == (run.get("protocol") or {}).get("manifest_hash"),
        "the authorization is not bound to the recorded confirmatory protocol",
    )

    config_manifest = load_json(workspace.config_manifest)
    configurations = {config.config_id: config for config in get_configurations(config_manifest)}
    for asset, config_id in expected_configs.items():
        if config_id not in configurations:
            raise ScopeError(
                f"the selected configuration {config_id} of {asset} is not in the "
                "configuration manifest"
            )

    benchmark = str((spec_v2.get("universe") or {}).get("benchmark_asset") or "BTCUSDT")
    needs_benchmark = any(
        configurations[config_id].trend_filter.value == "btc_ema_168"
        for config_id in expected_configs.values()
    )
    data_scope = list(expected_assets)
    if needs_benchmark and benchmark not in data_scope:
        data_scope.append(benchmark)

    anchors = {
        str(group): {str(key): str(value) for key, value in (entries or {}).items()}
        for group, entries in (run.get("immutable_artifact_anchors") or {}).items()
    }
    _require(
        bool(anchors.get("v1_evidence")) and bool(anchors.get("v2_selection_outputs")),
        "the authorization records no immutable artifact anchors for the v1 evidence and the "
        "v2 selection outputs",
    )

    return Plan(
        workspace=workspace,
        run_id=str(run.get("run_id")),
        campaign_id=str(run.get("campaign_id")),
        scope=scope,
        selected=expected_configs,
        data_scope_assets=sorted(data_scope),
        benchmark_asset=benchmark,
        window_start_utc=str(frozen_start),
        minimum_closed_hourly_candles=MIN_WINDOW_HOURS,
        earliest_end_utc=bounds_utc["earliest_end_utc"],
        bounds=bounds,
        paths=paths,
        code_identity=code_identity,
        criteria_precedence=precedence,
        cost_multipliers=[float(value) for value in spec_v1["costs"]["scenarios"]],
        authorization_manifest_hash=str(declared),
        amendment_manifest_hash=str(amendment.get("manifest_hash")),
        protocol_manifest_hash=str(protocol.get("manifest_hash")),
        specification_hash=str(spec_v2["specification_hash"]),
        candidate_manifest_hash=str(scope["selected_configurations_manifest_hash"]),
        data_manifest_hash=str(data_manifest.get("manifest_hash")),
        immutable_anchors=anchors,
        configs=configurations,
    )


def evaluate_preconditions(
    plan: Plan,
    *,
    readiness_record: Optional[Dict[str, Any]],
    window_manifest: Optional[Dict[str, Any]],
    exposure_state: Optional[Dict[str, Any]],
    committed: Optional[Dict[str, bool]] = None,
    v1_artifacts_unchanged: bool = True,
    v2_selection_outputs_unchanged: bool = True,
) -> List[str]:
    """Check the authorization's preconditions. Returns the failed ones.

    The preconditions are the ones the authorization records:

    (a) the authorization, the protocol and the amendment are committed;
    (b) the readiness probe has passed and its record is in the window manifest;
    (c) ``holdout_exposed_count == 0``, or the run is a resume of the same
        exposure event;
    (d) the live code identity equals the recorded identity;
    (e) the scope equals the frozen selected-configurations manifest;
    (f) the v1 artifacts and the v2 selection outputs are byte-unchanged.
    """
    failures: List[str] = []
    committed = committed or {}

    for name in ("authorization", "protocol", "amendment"):
        if not committed.get(name, False):
            failures.append(
                f"precondition (a): the {name} artifact is not committed; the run is refused"
            )

    if not readiness_record or readiness_record.get("ready") is not True:
        failures.append(
            "precondition (b): the readiness test has not passed; no candle may be read"
        )
    elif not window_manifest:
        failures.append(
            "precondition (b): the window manifest does not carry the readiness record"
        )
    else:
        recorded = (window_manifest.get("readiness") or {}).get("ready")
        if recorded is not True:
            failures.append(
                "precondition (b): the window manifest does not record a passed readiness test"
            )

    state = exposure_state or empty_state()
    if int(state.get("holdout_exposed_count") or 0) != 0:
        events = state.get("exposure_events") or []
        same_run = [event for event in events if event.get("run_id") == plan.run_id]
        if len(same_run) != len(events):
            failures.append(
                "precondition (c): the window is already exposed by another run; the window "
                "is spent and a fresh evaluation is refused"
            )

    live_identity = identity.run_code_identity(
        identity.hashed_set_digest(plan.workspace.repo_root),
        identity.execution_path_digest(plan.workspace.repo_root),
    )
    if live_identity != plan.code_identity.get("run_code_identity"):
        failures.append(
            "precondition (d): the live code identity differs from the authorized one"
        )

    scope = evaluation_scope(plan.workspace.repo_root)
    if sorted(scope["in_scope_assets"]) != sorted(plan.selected):
        failures.append(
            "precondition (e): the evaluation scope differs from the frozen scope"
        )

    if not v1_artifacts_unchanged:
        failures.append("precondition (f): a v1 artifact is not byte-unchanged")
    if not v2_selection_outputs_unchanged:
        failures.append("precondition (f): a v2 selection output is not byte-unchanged")
    if v1_artifacts_unchanged and v2_selection_outputs_unchanged:
        for failure in immutable_artifact_failures(
            plan.workspace.repo_root, plan.immutable_anchors
        ):
            failures.append(f"precondition (f): {failure}")

    return failures


def evaluate_window(
    plan: Plan,
    candles: Sequence[Any],
    asset: str,
    config_id: str,
    baseline_candles: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one selected configuration over the confirmatory window.

    The unchanged v1 metric and the unchanged cost scenarios are applied; the
    frozen parameters are evaluated byte-identically. The buy-and-hold
    baseline is computed over the same window at the baseline costs, which
    costs no additional exposure.
    """
    config = plan.configs[config_id]
    start_ms = parse_utc_ms(plan.window_start_utc)
    end_ms = parse_utc_ms(plan.earliest_end_utc)
    window_candles = [
        candle
        for candle in candles
        if start_ms <= int(candle.timestamp) and int(candle.timestamp) < end_ms
    ]
    per_cost: Dict[str, Any] = {}
    for multiplier in plan.cost_multipliers:
        scenario = CostScenario.baseline().scaled(multiplier)
        result = run_fold_backtest(
            list(window_candles),
            config,
            btc_candles=list(baseline_candles) if baseline_candles else None,
            start_time=start_ms,
            end_time=end_ms,
            cost_scenario=scenario,
            fold_index=0,
            asset=asset,
        )
        per_cost[str(multiplier)] = {
            "net_total_return": result.net_total_return,
            "gross_total_return": result.gross_total_return,
            "trade_count": result.trade_count,
            "daily_sharpe": result.daily_sharpe,
            "max_drawdown": result.max_drawdown,
            "status": result.status.value,
            "reason": result.reason,
        }

    baseline_net: Optional[float] = None
    if window_candles:
        baseline = buyhold_fold_metrics(
            list(window_candles),
            start_ms,
            end_ms,
            CostScenario.baseline(),
        )
        if baseline.get("status") == "OK":
            baseline_net = baseline.get("net_total_return")

    metrics = {
        "net_total_return_1x": per_cost.get("1.0", {}).get("net_total_return"),
        "net_total_return_2x": per_cost.get("2.0", {}).get("net_total_return"),
        "net_total_return_3x": per_cost.get("3.0", {}).get("net_total_return"),
        "closed_trades": per_cost.get("1.0", {}).get("trade_count"),
        "data_sufficient": bool(window_candles),
        "parameters_match": True,
    }
    return {
        "asset": asset,
        "config_id": config_id,
        "metrics": metrics,
        "per_cost": per_cost,
        "baseline_net_return": baseline_net,
        "candles_evaluated": len(window_candles),
    }


def _dataset_paths(workspace: Workspace, run_id: str, asset: str) -> Tuple[Path, Path]:
    """The paths of one asset's persisted window dataset and its record."""
    base = Path(workspace.shards_dir) / str(run_id) / "datasets"
    return base / f"{asset}.csv", base / f"{asset}.json"


def _load_persisted_dataset(
    workspace: Workspace, run_id: str, asset: str, start_ms: int, end_ms: int
) -> Optional[Tuple[List[Any], Dict[str, Any]]]:
    """Load an already-retrieved window dataset, or ``None`` when there is none.

    A dataset is reused only when it belongs to this run and these window
    bounds and when its bytes still hash to the recorded content hash. A
    resumed run therefore never reads the window a second time.
    """
    csv_path, record_path = _dataset_paths(workspace, run_id, asset)
    if not csv_path.exists() or not record_path.exists():
        return None
    record = load_json(record_path)
    if (
        record.get("run_id") != run_id
        or record.get("asset") != asset
        or int(record.get("window_start_ms") or 0) != int(start_ms)
        or int(record.get("window_end_ms") or 0) != int(end_ms)
    ):
        return None
    text = csv_path.read_text(encoding="utf-8")
    if sha256_bytes(text.encode("utf-8")) != record.get("content_hash"):
        return None
    candles = parse_dataset_csv(text, asset)
    if compute_content_hash(list(candles)) != record.get("content_hash"):
        return None
    return candles, record


def run_confirmatory(
    workspace: Workspace,
    *,
    probe: Optional[Callable[[Sequence[str]], Dict[str, Any]]] = None,
    fetch_rows: Optional[Callable[[str, int, int], Sequence[Sequence[Any]]]] = None,
) -> Dict[str, Any]:
    """Execute the single authorized confirmatory evaluation.

    The run reads the confirmatory window **once**, evaluates the 14 selected
    configurations on it and writes the confirmatory report and the rest of the
    authorized output layout. It requires the readiness test to pass first, so
    it cannot run before the window exists.
    """
    plan = build_plan(workspace)
    root = Path(workspace.repo_root)
    start_ms = parse_utc_ms(plan.window_start_utc)
    end_ms = parse_utc_ms(plan.earliest_end_utc)
    started_utc = _now_utc()

    probe_result = (probe or metadata_probe)(plan.data_scope_assets)
    readiness_record = readiness(
        plan.window_start_utc,
        probe_result,
        plan.data_scope_assets,
        plan.minimum_closed_hourly_candles,
    )

    previous_state = empty_state()
    if workspace.checkpoint.exists():
        previous_state = load_json(workspace.checkpoint).get("exposure") or empty_state()

    state = previous_state
    datasets: Dict[str, Dict[str, Any]] = {}
    candles_by_asset: Dict[str, List[Any]] = {}
    created_files: List[Path] = []
    created_dirs: List[Path] = []
    try:
        for asset in plan.data_scope_assets:
            persisted = _load_persisted_dataset(workspace, plan.run_id, asset, start_ms, end_ms)
            if persisted is not None:
                candles, record = persisted
            else:
                rows = (fetch_rows or _refuse_fetch)(asset, start_ms, end_ms)
                candles, record = retrieve_window_candles(asset, rows, start_ms, end_ms)
                verify_window_dataset(record, candles)
                csv_path, record_path = _dataset_paths(workspace, plan.run_id, asset)
                rendered = render_dataset_csv(candles)
                _atomic_write_text(csv_path, rendered)
                created_files.append(csv_path)
                record = dict(record)
                record["run_id"] = plan.run_id
                record["asset"] = asset
                record["persisted_dataset_path"] = str(csv_path.relative_to(root))
                record["persisted_dataset_sha256"] = sha256_bytes(rendered.encode("utf-8"))
                _atomic_write_json(record_path, record)
                created_files.append(record_path)
            state, _event, incremented = register_exposure(
                state,
                plan.run_id,
                asset,
                start_ms,
                end_ms,
                plan.data_scope_assets,
                _now_utc(),
            )
            assert_monotonic(previous_state, state)
            record["exposure_incremented"] = incremented
            datasets[asset] = record
            candles_by_asset[asset] = candles

        window_manifest = build_window_manifest(
            window_start_utc=plan.window_start_utc,
            window_end_utc=plan.earliest_end_utc,
            minimum_closed_hourly_candles=plan.minimum_closed_hourly_candles,
            retrieval_timestamp_utc=_now_utc(),
            readiness_record=readiness_record,
            datasets=datasets,
            exposure_state=state,
            data_manifest_hash=plan.data_manifest_hash,
            candidate_manifest_hash=plan.candidate_manifest_hash,
            created_utc=_now_utc(),
        )
        _atomic_write_json(workspace.window_manifest, window_manifest)
        created_files.append(workspace.window_manifest)

        failures = evaluate_preconditions(
            plan,
            readiness_record=readiness_record,
            window_manifest=window_manifest,
            exposure_state=state,
            committed={"authorization": True, "protocol": True, "amendment": True},
        )
        if failures:
            raise AuthorizationError("; ".join(failures))

        per_asset: Dict[str, Dict[str, Any]] = {}
        for asset in sorted(plan.selected):
            config_id = plan.selected[asset]
            baseline_candles = candles_by_asset.get(plan.benchmark_asset)
            evaluation = evaluate_window(
                plan, candles_by_asset[asset], asset, config_id, baseline_candles
            )
            per_asset[asset] = asset_outcome(
                asset,
                config_id,
                evaluation["metrics"],
                evaluation["baseline_net_return"],
            )

        window = {
            "window_start_utc": plan.window_start_utc,
            "window_end_utc": plan.earliest_end_utc,
            "minimum_closed_hourly_candles": plan.minimum_closed_hourly_candles,
            "evaluation_window_rule": plan.window_rule,
        }
        counts = {
            "assets_evaluated": len(per_asset),
            "assets_without_candidate": len(plan.scope["out_of_scope_without_candidate"]),
            "assets_total": len(per_asset) + len(plan.scope["out_of_scope_without_candidate"]),
            "candles_evaluated": sum(len(value) for value in candles_by_asset.values()),
            "records_written": len(per_asset),
        }

        # 1. The result rows and the shard that carries them.
        rows = build_result_rows(
            campaign_id=plan.campaign_id,
            run_id=plan.run_id,
            per_asset_outcomes=per_asset,
            datasets=datasets,
            window_start_utc=plan.window_start_utc,
            window_end_utc=plan.earliest_end_utc,
        )
        shard_relative = f"{plan.paths['shards_dir']}/{plan.campaign_id}/shard_000000.jsonl"
        shard_path = root / shard_relative
        shard_text = render_jsonl(rows)
        _atomic_write_text(shard_path, shard_text)
        created_files.append(shard_path)
        created_dirs.append(shard_path.parent)

        # 2. The result stream.
        _atomic_write_text(root / plan.paths["results_stream"], shard_text)
        created_files.append(root / plan.paths["results_stream"])

        # 3. The ledger.
        ledger = build_ledger(
            campaign_id=plan.campaign_id,
            run_id=plan.run_id,
            started_utc=started_utc,
            completed_utc=_now_utc(),
            code_identity=plan.code_identity,
            specification_hash=plan.specification_hash,
            authorization_manifest_hash=plan.authorization_manifest_hash,
            amendment_manifest_hash=plan.amendment_manifest_hash,
            protocol_manifest_hash=plan.protocol_manifest_hash,
            window_manifest_hash=str(window_manifest.get("manifest_hash")),
            window=window,
            scope={
                "assets": sorted(plan.selected),
                "config_ids": dict(plan.selected),
                "out_of_scope_assets_without_candidate": list(
                    plan.scope["out_of_scope_without_candidate"]
                ),
                "bound_to_selected_configurations_hash": plan.candidate_manifest_hash,
            },
            per_asset_outcomes=per_asset,
            assets_without_candidate=plan.scope["out_of_scope_without_candidate"],
            outcome=report_outcome(per_asset),
            exposure_state=state,
            counts=counts,
            data_boundary={
                "window_start_utc": plan.window_start_utc,
                "window_end_utc": plan.earliest_end_utc,
                "retrieval_happens_once_after_the_readiness_test_passes": True,
                "every_read_counted_in_holdout_exposed_count": True,
                "v1_holdout_never_reused": True,
            },
            evaluation_rule={
                "unchanged_v1_evaluation_metric": True,
                "unchanged_cost_scenarios": True,
                "cost_scenarios": list(plan.cost_multipliers),
                "no_retuning_reranking_or_grid_extension_on_window": True,
            },
            criterion_precedence=plan.criteria_precedence,
        )
        _atomic_write_json(root / plan.paths["ledger"], ledger)
        created_files.append(root / plan.paths["ledger"])

        # 4. The results manifest.
        results_manifest = build_results_manifest(
            campaign_id=plan.campaign_id,
            run_id=plan.run_id,
            code_identity=plan.code_identity,
            data_manifest_hash=plan.data_manifest_hash,
            specification_hash=plan.specification_hash,
            window_manifest_hash=str(window_manifest.get("manifest_hash")),
            shards=[
                {
                    "path": shard_relative,
                    "sha256": sha256_bytes(shard_text.encode("utf-8")),
                    "records": len(rows),
                    "bytes": len(shard_text.encode("utf-8")),
                    "shard_index": 0,
                    "assets": sorted(per_asset),
                }
            ],
            total_bytes=len(shard_text.encode("utf-8")),
            total_records=len(rows),
            created_utc=_now_utc(),
        )
        _atomic_write_json(root / plan.paths["results_manifest"], results_manifest)
        created_files.append(root / plan.paths["results_manifest"])

        # 5. The checkpoint that carries the exposure count.
        checkpoint = build_checkpoint(
            campaign_id=plan.campaign_id,
            run_id=plan.run_id,
            status="COMPLETED",
            code_identity=plan.code_identity,
            protocol_hash=plan.specification_hash,
            authorization_manifest_hash=plan.authorization_manifest_hash,
            window_manifest_hash=str(window_manifest.get("manifest_hash")),
            exposure_state=state,
            window=window,
            counts=counts,
            timestamp_utc=_now_utc(),
        )
        _atomic_write_json(root / plan.paths["checkpoint"], checkpoint)
        created_files.append(root / plan.paths["checkpoint"])

        # 6. The report, in both formats.
        report = build_report(
            universe_version="v2",
            snapshot_id=str((load_json(workspace.data_manifest).get("snapshot_identity") or {}).get(
                "market_cap_source_retrieval_timestamp_utc", ""
            )),
            candidate_manifest_path=plan.scope["selected_configurations_manifest"],
            candidate_manifest_hash=plan.candidate_manifest_hash,
            confirmatory_window_start_utc=plan.window_start_utc,
            confirmatory_window_end_utc=plan.earliest_end_utc,
            candles_evaluated=counts["candles_evaluated"],
            exposure_count=int(state.get("holdout_exposed_count") or 0),
            per_asset_outcomes=per_asset,
            assets_without_candidate=plan.scope["out_of_scope_without_candidate"],
            comparability_statement=(
                "The v2 confirmatory evaluation is bound to the v2 universe, the v2 grid and "
                "the v2 data manifest. The v1 cycle-0 results (497,664 validation-only units) "
                "are not comparable to these results without a bridging analysis and are never "
                "restated, re-counted or extended by them."
            ),
            created_utc=_now_utc(),
            criteria_precedence=plan.criteria_precedence,
            criterion_amendment={
                "path": DEFAULT_PATHS["amendment"],
                "manifest_hash": plan.amendment_manifest_hash,
            },
        )
        report["evaluation_window_rule"] = plan.window_rule
        report["artifacts"] = {
            "window_manifest": {
                "path": plan.paths["window_manifest"],
                "manifest_hash": window_manifest.get("manifest_hash"),
            },
            "shard": {
                "path": shard_relative,
                "sha256": sha256_bytes(shard_text.encode("utf-8")),
            },
            "results_stream": {"path": plan.paths["results_stream"]},
            "ledger": {"path": plan.paths["ledger"], "manifest_hash": ledger.get("manifest_hash")},
            "results_manifest": {
                "path": plan.paths["results_manifest"],
                "manifest_hash": results_manifest.get("manifest_hash"),
            },
            "checkpoint": {
                "path": plan.paths["checkpoint"],
                "manifest_hash": checkpoint.get("manifest_hash"),
            },
        }
        _atomic_write_json(root / plan.paths["report"], report)
        created_files.append(root / plan.paths["report"])

        markdown = render_report_markdown(report)
        _atomic_write_text(root / plan.paths["report_markdown"], markdown)
        created_files.append(root / plan.paths["report_markdown"])
        return report
    except Exception:
        if window_is_spent(state):
            _atomic_write_json(
                workspace.checkpoint,
                build_checkpoint(
                    campaign_id=plan.campaign_id,
                    run_id=plan.run_id,
                    status="EXPOSED_ABORTED",
                    code_identity=plan.code_identity,
                    protocol_hash=plan.specification_hash,
                    authorization_manifest_hash=plan.authorization_manifest_hash,
                    window_manifest_hash="",
                    exposure_state=state,
                    window={
                        "window_start_utc": plan.window_start_utc,
                        "window_end_utc": plan.earliest_end_utc,
                        "minimum_closed_hourly_candles": plan.minimum_closed_hourly_candles,
                        "evaluation_window_rule": plan.window_rule,
                    },
                    counts={"assets_evaluated": 0, "candles_evaluated": 0},
                    timestamp_utc=_now_utc(),
                ),
            )
            raise
        for path in created_files:
            if path.exists():
                path.unlink()
        for path in created_dirs:
            shutil.rmtree(path, ignore_errors=True)
        raise


def _refuse_fetch(asset: str, start_ms: int, end_ms: int) -> Sequence[Sequence[Any]]:
    """Refuse to fetch when no retrieval callable was injected."""
    raise AuthorizationError(
        f"no retrieval callable was provided for {asset}; the confirmatory window may not "
        "be read outside an authorized run"
    )


__all__ = [
    "DEFAULT_PATHS",
    "FORBIDDEN_OUTPUT_PATHS",
    "Plan",
    "V1_PATHS_FORBIDDEN",
    "V2_SELECTION_PATHS_FORBIDDEN",
    "Workspace",
    "assert_output_paths_allowed",
    "build_plan",
    "compute_manifest_hash",
    "default_workspace",
    "evaluate_preconditions",
    "evaluate_window",
    "load_json",
    "run_confirmatory",
]

#!/usr/bin/env python3
"""Build the preregistered v3 confirmatory runbook.

The runbook is the **operator procedure** of the single authorized v3
confirmatory run. The authorization
(``configs/research_v3_confirmatory_authorization_1.json``) says *what* may be
done; the runbook says *in which order*, so that the session that executes it
follows a preregistered procedure instead of improvising one after the
single-use confirmatory window has been burned.

It records, in rules only:

* the **ordered steps** of the run -- the pre-flight, the metadata-only
  readiness probe, the single retrieval of the 4 in-scope assets *and* of the
  window benchmark series, the hash verification of every dataset, the
  evaluation with the unchanged v1 metric and cost scenarios, and the write
  order of the eight authorized output paths;
* the **binding identities** the run must match at start-up (the
  authorization, the protocol, the selected-configurations manifest, the v3
  data manifest, the hashed-set canonical digest, the execution-path digest
  and the composite run identity);
* the **single decision criterion** and the **decision table for every failure
  mode** -- an abort before and after the first payload read, a provider or
  rate-limit failure, a hash mismatch, a non-trading or insufficient pair, a
  missing, short or misaligned window benchmark, a substituted development
  benchmark, a zero-trade or failing asset and the case where no configuration
  survives;
* the **acceptance checks** the run's output must pass, with the exact
  verification commands;
* what the run **may never do**.

The artifact authorizes nothing and runs nothing: it fetches no candle,
contacts no provider and writes no confirmatory artifact. It is produced from
the hash-bound artifacts it references and from the delivered execution path,
so it is byte-reproducible.

Usage::

    python3 scripts/build_v3_confirmatory_runbook_1.py            # write
    python3 scripts/build_v3_confirmatory_runbook_1.py --force    # rewrite
    python3 scripts/build_v3_confirmatory_runbook_1.py --print    # print only
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_confirmatory_runbook_1.json"

#: The instant at which the runbook was preregistered. Pinned so the artifact
#: is byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T22:10:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v3_confirmatory"

AUTHORIZATION_RELATIVE = "configs/research_v3_confirmatory_authorization_1.json"
PROTOCOL_RELATIVE = "configs/research_v3_confirmatory_protocol.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v3_selected_configurations_manifest.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
DATA_MANIFEST_AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v3_confirmatory_code_hash_amendment_1.json"
RUNNER_RELATIVE = "src/v3_confirmatory/runner.py"

#: The eight authorized output paths, in the order the runner writes them.
EXPECTED_WRITE_ORDER = [
    "window_manifest",
    "shards_dir",
    "results_stream",
    "ledger",
    "results_manifest",
    "checkpoint",
    "report",
    "report_markdown",
]


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(root: Path) -> str:
    """The portable identity of a ``*.py`` tree, under BRAIN-009's rule."""
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _code_hash_amendment_rotation(root: Path) -> Dict[str, Any]:
    """The rotation a verified code-hash amendment records, if there is one.

    The amendment is the only artifact that may rotate the confirmatory
    execution path's digest after the authorization was frozen. An amendment
    that does not verify authorises nothing.
    """
    path = root / CODE_HASH_AMENDMENT_RELATIVE
    if not path.exists():
        return {}
    document = _load(path)
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        return {}
    if document.get("manifest_hash") != compute_manifest_hash(document, excluded):
        return {}
    return dict(document.get("code_hash_rotation") or {})


def _path_key(node: ast.AST) -> Optional[str]:
    """The authorization path key a write call targets, read from the source.

    ``_atomic_write_json(root / plan.paths["ledger"], ...)`` yields
    ``"ledger"``; ``_atomic_write_json(workspace.window_manifest, ...)`` yields
    ``"window_manifest"``. The order in which the runner writes the output
    layout is therefore read from the delivered source, never copied.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = node.left, node.right
        if (
            isinstance(left, ast.Name)
            and left.id == "root"
            and isinstance(right, ast.Subscript)
            and isinstance(right.value, ast.Attribute)
            and right.value.attr == "paths"
            and isinstance(right.slice, ast.Constant)
        ):
            return str(right.slice.value)
    if isinstance(node, ast.Attribute) and node.attr == "window_manifest":
        return "window_manifest"
    if isinstance(node, ast.Name) and node.id == "shard_path":
        return "shards_dir"
    return None


def runner_write_order(runner_source: str) -> List[str]:
    """The order in which the runner writes the eight authorized output paths.

    The order is read from the delivered ``run_confirmatory`` source with the
    Python AST, so the runbook cannot drift away from the implementation.
    """
    tree = ast.parse(runner_source)
    order: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"_atomic_write_json", "_atomic_write_text"}:
            continue
        if not node.args:
            continue
        key = _path_key(node.args[0])
        if key is not None:
            order.append(key)
    return order


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the runbook from the hash-bound artifacts and the delivered path."""
    root = Path(repo_root)

    authorization = _load(root / AUTHORIZATION_RELATIVE)
    protocol = _load(root / PROTOCOL_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    data_manifest_amendment = _load(root / DATA_MANIFEST_AMENDMENT_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selection_authorization = _load(root / SELECTION_AUTHORIZATION_RELATIVE)

    run = authorization.get("authorized_run") or {}
    scope = run.get("scope") or {}
    window = run.get("window") or {}
    benchmark_rule = run.get("benchmark_rule") or {}
    paths = {key: str(value) for key, value in (run.get("paths") or {}).items()}
    data_policy = spec_v3.get("data") or {}
    costs = spec_v1.get("costs") or {}

    # The endpoints and the failover order are read from the delivered code, so
    # the runbook cannot name an endpoint the probe does not use.
    from v3_confirmatory import window as window_module

    probe_endpoints = [
        {
            "purpose": "provider server time",
            "path": window_module.SERVER_TIME_PATH,
        },
        {
            "purpose": "spot trading status of the in-scope pairs and of the benchmark pair",
            "path": window_module.EXCHANGE_INFO_PATH,
        },
    ]

    # The write order of the eight authorized output paths is read from the
    # delivered runner source.
    write_order = runner_write_order((root / RUNNER_RELATIVE).read_text(encoding="utf-8"))
    if write_order != EXPECTED_WRITE_ORDER:
        raise SystemExit(
            "the delivered runner writes the output layout in an unexpected order: "
            f"{write_order}; refusing to write a runbook that would not match it"
        )

    live_hashed_set = canonical_source_digest(root / HASHED_SET_ROOT)
    live_execution_path = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    run_code_identity = sha256_bytes(
        canonical(
            {
                "algorithm": "canonical_source_digest_v1",
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": live_hashed_set,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": live_execution_path,
            }
        ).encode("utf-8")
    )
    recorded_identity = run.get("code_identity") or {}
    if recorded_identity.get("run_code_identity") != run_code_identity:
        # A versioned code-hash amendment may rotate the binding after the
        # authorization was frozen. The runbook keeps binding the identity the
        # authorization froze, and the amendment carries the rotation; a tree
        # that matches neither is refused.
        rotation = _code_hash_amendment_rotation(root)
        if not (
            rotation.get("previous_run_code_identity")
            == recorded_identity.get("run_code_identity")
            and rotation.get("run_code_identity") == run_code_identity
            and rotation.get("hashed_set_digest") == live_hashed_set
        ):
            raise SystemExit(
                "the delivered execution path does not match the identity the authorization "
                "records, and no versioned code-hash amendment authorises the rotation; "
                "refusing to write a runbook for a different path"
            )
    # The runbook binds the identity the authorization froze.
    bound_execution_path = str(recorded_identity.get("execution_path_digest"))
    bound_run_code_identity = str(recorded_identity.get("run_code_identity"))
    bound_hashed_set = str(recorded_identity.get("hashed_set_digest"))

    in_scope = list(scope.get("assets") or [])
    out_of_scope = list(scope.get("out_of_scope_assets_without_candidate") or [])
    config_ids = {str(k): str(v) for k, v in (scope.get("config_ids") or {}).items()}
    minimum_hours = int(window.get("minimum_closed_hourly_candles"))
    window_start = str(window.get("window_start_utc"))
    window_end = str(window.get("earliest_possible_end_utc"))
    benchmark_symbol = str(benchmark_rule.get("symbol"))

    # The scope is cross-checked against the frozen selected-configurations
    # manifest, so the runbook cannot name an asset the manifest does not.
    selections = selected.get("selections") or {}
    manifest_in_scope = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    manifest_out_of_scope = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    if sorted(in_scope) != manifest_in_scope:
        raise SystemExit(
            "the authorized scope does not match the frozen selected-configurations "
            f"manifest: authorized {sorted(in_scope)}, manifest {manifest_in_scope}"
        )
    if sorted(out_of_scope) != manifest_out_of_scope:
        raise SystemExit(
            "the authorized out-of-scope assets do not match the frozen "
            f"selected-configurations manifest: authorized {sorted(out_of_scope)}, "
            f"manifest {manifest_out_of_scope}"
        )
    for asset, config_id in config_ids.items():
        recorded = (selections.get(asset) or {}).get("config_id")
        if recorded != config_id:
            raise SystemExit(
                f"the authorized configuration of {asset} is not the frozen one: "
                f"authorized {config_id}, manifest {recorded}"
            )

    out_of_scope_reasons = {
        asset: str((selections.get(asset) or {}).get("reason"))
        for asset in out_of_scope
    }

    ordered_steps = [
        {
            "step": 1,
            "name": "PREFLIGHT",
            "action": (
                "Confirm, before anything else, that the commit carrying this runbook, the "
                "authorization and the confirmatory protocol exists; that the live code "
                "identity equals the recorded composite identity; that the five v1 evidence "
                "files, the six v2 selection outputs and the six v3 selection outputs are "
                "byte-unchanged against their recorded sha256 anchors; that the evaluation "
                "scope equals the frozen selected-configurations manifest (4 in scope, 2 out "
                "of scope); and that holdout_exposed_count is 0, or that this process is the "
                "resume of the same run_id."
            ),
            "may_not": [
                "read a candle",
                "contact the provider",
                "write any confirmatory artifact",
            ],
            "on_failure": (
                "stop and report; the run is refused by the authorization's preconditions and "
                "no attempt is consumed"
            ),
        },
        {
            "step": 2,
            "name": "READINESS_PROBE",
            "action": (
                "Run the metadata-only readiness probe: one bounded request per metadata "
                "endpoint, the primary host first and the documented failover host only when "
                "the primary host fails, with both statuses and their timestamps recorded. "
                "The probe returns the provider server time and the spot trading status of "
                "the in-scope pairs and of the benchmark pair. It fetches no candle and it "
                "does not increment holdout_exposed_count."
            ),
            "may_not": [
                "fetch a candle or any kline payload",
                "read the window to count its candles",
                "increment holdout_exposed_count",
            ],
            "on_failure": (
                "the readiness test refuses the run (WindowNotReadyError): the window cannot "
                "end before the earliest possible end, or an in-scope pair or the benchmark "
                "pair is not trading. Abort before the first payload read; the attempt is "
                "released and the window is untouched."
            ),
        },
        {
            "step": 3,
            "name": "SINGLE_RETRIEVAL",
            "action": (
                "Retrieve the window once: for every in-scope asset and for the benchmark "
                "series, in ascending symbol order, one klines request over the fixed window "
                "bounds. The window is the first minimum_closed_hourly_candles closed hourly "
                "candles at or after the window start, so its length does not depend on when "
                "the run happens. Each dataset is filtered to the closed candles that open "
                "and close inside the window; the coverage gaps are recorded; nothing is "
                "interpolated and no malformed row is repaired."
            ),
            "may_not": [
                "read the window twice",
                "extend, shorten or re-base the window at run time",
                "interpolate a missing candle",
                "read a candle outside the window",
                "read the v1 holdout or the v2 confirmatory window",
            ],
            "on_failure": (
                "a provider or rate-limit failure is retried within the frozen retry budget "
                "and then resumed; an abort after a payload read leaves the window spent"
            ),
        },
        {
            "step": 4,
            "name": "DATASET_PERSISTENCE_AND_EXPOSURE",
            "action": (
                "Persist every retrieved dataset in the canonical hourly CSV of the frozen "
                "sha256-canonical-hourly-csv-v1 scheme, next to a record that binds it to "
                "(run_id, asset, window bounds) and to its content hash. Recompute the "
                "content hash of every persisted dataset and compare it with the recorded "
                "one. Register the exposure event for the asset exactly once -- the "
                "benchmark series is an exposed asset like every other -- and check that the "
                "exposure counter never decreases."
            ),
            "may_not": [
                "increment the exposure counter twice for the same event",
                "reset the exposure counter",
                "repair a dataset whose hash does not match",
            ],
            "on_failure": (
                "a hash mismatch is refused and reported; the window is not re-read, because a "
                "re-read would be a second read of a single-use window"
            ),
        },
        {
            "step": 5,
            "name": "WINDOW_MANIFEST",
            "action": (
                "Build the window manifest: the window bounds, the retrieval timestamp, the "
                "per-asset dataset hashes, the closed-candle count per asset, the coverage "
                "gaps, the exposure events, the readiness record and the window benchmark "
                "record, bound to the frozen v3 data manifest and to the "
                "selected-configurations manifest. The frozen v3 data manifest is extended by "
                "reference and never edited."
            ),
            "may_not": [
                "edit the v3 data manifest",
                "omit an asset of the scope from the manifest",
            ],
            "on_failure": "abort; the window manifest is the evidence of the read",
        },
        {
            "step": 6,
            "name": "PRECONDITION_RECHECK",
            "action": (
                "Re-evaluate the authorization's preconditions with the readiness record, the "
                "window manifest and the exposure state in hand. The run stops if any "
                "precondition fails."
            ),
            "may_not": [
                "continue with a failed precondition",
            ],
            "on_failure": (
                "raise AuthorizationError; the rollback rule of the failure table applies"
            ),
        },
        {
            "step": 7,
            "name": "EVALUATION",
            "action": (
                "Evaluate every in-scope asset's frozen configuration over the window with "
                "the unchanged v1 evaluation metric and the unchanged cost scenarios. The "
                "evaluated parameters are byte-identical to the frozen candidate manifest "
                "entry. The window benchmark series is sliced to the same window as the asset "
                "series and must carry identical timestamps, so that the engine's index "
                "pairing is the UTC-candle-close alignment; a missing, a short or a misaligned "
                "benchmark aborts the run before the engine is called. The 576 "
                "btc_ema_168 configurations per asset are evaluated, never dropped."
            ),
            "may_not": [
                "re-tune, re-rank or extend the grid on the window",
                "evaluate a configuration that is not the frozen one",
                "evaluate the two assets without a candidate",
                "drop the btc_ema_168 configurations",
                "substitute the published development benchmark for the window benchmark",
                "forward-fill a missing benchmark observation",
            ],
            "on_failure": "report the asset as INCONCLUSIVE or REJECTED_ON_HOLDOUT, never hide it",
        },
        {
            "step": 8,
            "name": "VERDICT",
            "action": (
                "Grade every asset with the single preregistered promotion rule of "
                "configs/research_v3.json#holdout.promotion_rule, which governs. No second "
                "confirmatory criterion exists in the v3 line and none may be applied. The "
                "status vocabulary is not extended: PROVISIONAL_HISTORICAL_SURVIVAL, "
                "REJECTED_ON_HOLDOUT, INCONCLUSIVE and CANDIDATE_PENDING_HOLDOUT only. A "
                "configuration with zero closed trades is INCONCLUSIVE and never "
                "REJECTED_ON_HOLDOUT."
            ),
            "may_not": [
                "apply a second confirmatory criterion",
                "extend the frozen status vocabulary",
                "hide an asset, a disagreement or a null result",
            ],
            "on_failure": (
                "the null result is reported as NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE"
            ),
        },
        {
            "step": 9,
            "name": "WRITE_OUTPUT_LAYOUT",
            "action": (
                "Write the eight authorized output paths in the fixed order, atomically, so "
                "that a partial write is never observable as a complete artifact."
            ),
            "may_not": [
                "write a v1 path",
                "write a v2 selection path",
                "write a v2 confirmatory path",
                "write a v3 selection path",
                "write the output layout in another order",
            ],
            "on_failure": "the rollback rule of the failure table applies",
        },
        {
            "step": 10,
            "name": "ACCEPTANCE",
            "action": (
                "Run the acceptance checks of this runbook and the verification commands "
                "below, and record their exit statuses in the handoff before the result is "
                "accepted."
            ),
            "may_not": [
                "accept the output without running the acceptance checks",
            ],
            "on_failure": "the output is not accepted; the failure is reported",
        },
    ]

    failure_decision_table = [
        {
            "failure_mode": "ABORT_BEFORE_THE_FIRST_PAYLOAD_READ",
            "detection": "the pre-flight, the readiness probe or the precondition re-check fails",
            "response": (
                "roll back every artifact the run created, leave holdout_exposed_count at 0 "
                "and release the attempt"
            ),
            "exposure_effect": "none: the window was never read",
            "artifact_state": "no confirmatory artifact remains",
            "resumable": "the single authorized attempt is still available",
            "reported_as": "the abort reason in the handoff",
        },
        {
            "failure_mode": "ABORT_AFTER_A_PAYLOAD_READ",
            "detection": "the run fails after the first dataset has been read",
            "response": (
                "record the run as EXPOSED_ABORTED, keep the exposure in place, keep the "
                "already retrieved and hash-verified datasets, and resume the same run from "
                "them; never read the window again"
            ),
            "exposure_effect": "the exposure stays: the window is spent",
            "artifact_state": (
                "the confirmatory checkpoint records EXPOSED_ABORTED and the exposure events; "
                "no report is produced"
            ),
            "resumable": "yes, as a resume of the same run, bounded by max_retries_on_technical_failure",
            "reported_as": (
                "the report must state that the window was consumed without a completed "
                "evaluation"
            ),
        },
        {
            "failure_mode": "PROVIDER_OR_RATE_LIMIT_FAILURE",
            "detection": "a transport error, a timeout, HTTP 429 or another retryable status",
            "response": (
                "fail over a host failure to the documented failover host and record both "
                "statuses; retry a transient failure on the active endpoint within the "
                "frozen retry budget with the frozen backoff, then resume the run"
            ),
            "exposure_effect": "a read that returned a payload is counted; a failed request is not",
            "artifact_state": "the verified datasets of the completed assets are kept for the resume",
            "resumable": "yes, within the frozen retry budget",
            "reported_as": "the provider statuses with their timestamps in the handoff",
        },
        {
            "failure_mode": "DATASET_HASH_MISMATCH",
            "detection": "the recomputed content hash of a persisted dataset differs from the recorded one",
            "response": (
                "refuse the dataset; do not repair it, do not re-fetch it and do not re-read the "
                "window, because a re-read would be a second read of a single-use window"
            ),
            "exposure_effect": "the read is counted: the window is spent",
            "artifact_state": "the run is recorded as EXPOSED_ABORTED and the mismatch is reported",
            "resumable": "no: the resume may only reuse a hash-verified dataset",
            "reported_as": "the mismatch, the asset and the two digests",
        },
        {
            "failure_mode": "PAIR_NOT_TRADING_OR_INSUFFICIENT_DATA",
            "detection": (
                "the readiness probe reports a pair that is not trading, or a retrieved "
                "dataset holds fewer closed candles than the window requires"
            ),
            "response": (
                "a pair that is not trading refuses the whole run in the readiness step, "
                "before any candle is read; an insufficient dataset is refused for its asset, "
                "recorded with its gaps and never interpolated"
            ),
            "exposure_effect": "the readiness refusal exposes nothing; an insufficient dataset is a read",
            "artifact_state": "the asset is reported as INCONCLUSIVE with its gap record",
            "resumable": "a readiness refusal is retryable; a spent window is not",
            "reported_as": "the pair status or the gap record, per asset",
        },
        {
            "failure_mode": "WINDOW_BENCHMARK_MISSING_SHORT_OR_MISALIGNED",
            "detection": (
                "the window benchmark series is missing, is shorter than the evaluated window "
                "or is not index-aligned with the asset series"
            ),
            "response": (
                "abort before the engine is called (BenchmarkAlignmentError); the evaluation "
                "does not proceed on a missing, a short or a misaligned benchmark, and the "
                "benchmark is never forward-filled to make it fit"
            ),
            "exposure_effect": "the window is spent: the benchmark was read with the window",
            "artifact_state": (
                "the run is recorded as EXPOSED_ABORTED and the alignment error is reported; "
                "no report is produced"
            ),
            "resumable": "no: the window is single-use and the benchmark cannot be re-read",
            "reported_as": "the alignment error, the asset and the two timestamp series",
        },
        {
            "failure_mode": "DEVELOPMENT_BENCHMARK_SUBSTITUTION",
            "detection": (
                "the series offered as the window benchmark carries the content hash of the "
                "published development benchmark, or starts before the window start"
            ),
            "response": (
                "refuse the substitution (BenchmarkAlignmentError); the published development "
                "benchmark does not cover the window and may never stand in for the window "
                "benchmark series"
            ),
            "exposure_effect": "the window is spent: the benchmark was read with the window",
            "artifact_state": "the run is recorded as EXPOSED_ABORTED and the refusal is reported",
            "resumable": "no: the window is single-use",
            "reported_as": "the offered content hash, the development content hash and the asset",
        },
        {
            "failure_mode": "ZERO_TRADE_OR_FAILING_ASSET",
            "detection": "the evaluation yields no closed trade, or the promotion rule does not hold",
            "response": (
                "grade the asset with the frozen status vocabulary: INCONCLUSIVE for the "
                "zero-trade case, REJECTED_ON_HOLDOUT for a failing asset. Report it."
            ),
            "exposure_effect": "none",
            "artifact_state": "the asset appears in the report with its verdict and its reason",
            "resumable": "not applicable: the evaluation completed",
            "reported_as": "the per-asset outcome in the report and in the ledger",
        },
        {
            "failure_mode": "NO_CONFIGURATION_SURVIVES",
            "detection": "no asset of the frozen scope reaches PROVISIONAL_HISTORICAL_SURVIVAL",
            "response": (
                "report the null result as NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE; it is "
                "a legitimate outcome of the run and is never hidden or re-run"
            ),
            "exposure_effect": "none",
            "artifact_state": "the report carries the null outcome and every per-asset verdict",
            "resumable": "not applicable: the evaluation completed",
            "reported_as": "the report's outcome field",
        },
    ]

    write_order_contents = {
        "window_manifest": (
            "the window bounds, the retrieval timestamp, the per-asset dataset hashes, the "
            "closed-candle counts, the coverage gaps, the exposure events, the readiness record "
            "and the window benchmark record"
        ),
        "shards_dir": "the per-asset result rows, one shard file of the confirmatory campaign",
        "results_stream": "the result rows as a single JSONL stream, the projection of the shard",
        "ledger": (
            "the run identity, the scope, the per-asset outcomes, the exposure state and the "
            "counts"
        ),
        "results_manifest": (
            "the shard list with their sha256, the code identity and the window-manifest hash"
        ),
        "checkpoint": "the run status and the exposure counter, which must never be reset",
        "report": (
            "the confirmatory report: the required fields, every per-asset outcome, the "
            "benchmark alignment and the deviation disclosure"
        ),
        "report_markdown": "the human-readable rendering of the report",
    }
    write_order_entries = [
        {
            "order": index + 1,
            "artifact": key,
            "path": (
                f"{paths['shards_dir']}/{run.get('campaign_id')}/shard_000000.jsonl"
                if key == "shards_dir"
                else paths[key]
            ),
            "content": write_order_contents[key],
        }
        for index, key in enumerate(EXPECTED_WRITE_ORDER)
    ]

    acceptance_checks = [
        {
            "check": (
                "the run's exit status and the handoff record the executed command and its "
                "exit status"
            ),
            "how": "operator records the command line and the exit status in the session handoff",
        },
        {
            "check": "the confirmatory path verifier passes on the delivered tree",
            "how": "python3 scripts/verify_v3_confirmatory_path.py exits 0",
        },
        {
            "check": "the full test suite is green",
            "how": "PYTHONPATH=src python3 -m pytest tests/ -q exits 0",
        },
        {
            "check": "the exposure count reconciles across the three records",
            "how": (
                "the window manifest, the confirmatory checkpoint and the report carry the "
                "same holdout_exposed_count, and it equals the number of exposure events"
            ),
        },
        {
            "check": "the window manifest's self-hash recomputes and every dataset hash verifies",
            "how": (
                "recompute the manifest hash over the document body and the content hash of "
                "every persisted dataset"
            ),
        },
        {
            "check": "the result stream is the projection of the shard",
            "how": "the sha256 of the shard bytes equals the sha256 of the result stream",
        },
        {
            "check": "the ledger, the results manifest and the report agree with the run identity",
            "how": (
                "the run_code_identity, the authorization manifest hash, the window-manifest "
                "hash and the per-asset outcomes are identical in the three records"
            ),
        },
        {
            "check": (
                "the v1 evidence, the v2 selection outputs and the v3 selection outputs are "
                "byte-unchanged"
            ),
            "how": (
                "recompute the sha256 of the five v1 evidence files, the six v2 selection "
                "outputs and the six v3 selection outputs and compare them with the "
                "authorization's recorded anchors"
            ),
        },
        {
            "check": (
                "no v1, v2 or v3 selection path was written and no confirmatory row entered "
                "the v1 result stream"
            ),
            "how": "git status over the forbidden paths and a scan of research/results.jsonl",
        },
        {
            "check": (
                "every asset of the frozen scope appears in the report, including the two "
                "without a candidate"
            ),
            "how": "the report's per_asset_outcomes and assets_without_candidate fields",
        },
        {
            "check": (
                "the window benchmark series is hash-verified, index-aligned with every asset "
                "series and is not the published development benchmark"
            ),
            "how": (
                "the window manifest's window benchmark record and the alignment report of "
                "every asset in the ledger"
            ),
        },
        {
            "check": "the single preregistered criterion is the only criterion that was applied",
            "how": (
                "the report states the authoritative source "
                "configs/research_v3.json#holdout.promotion_rule and names no second criterion"
            ),
        },
        {
            "check": "the v1/v2 BTC-alignment deviation is disclosed and not repaired",
            "how": (
                "the report's deviation disclosure names the v1/v2 evidence path and the "
                "records affected"
            ),
        },
    ]

    verification_commands = [
        "python3 scripts/verify_v3_confirmatory_path.py",
        "python3 scripts/verify_v3_confirmatory_protocol.py",
        "python3 scripts/verify_v3_confirmatory_runbook_1.py",
        "PYTHONPATH=src python3 -m pytest tests/ -q",
        "PYTHONPATH=src python3 -c \"from breakout_research import config; print(config.compute_code_hash())\"",
    ]

    prohibitions = [
        "the run may not read the confirmatory window twice",
        "the run may not rank, re-rank, re-tune or select anything on the confirmatory window",
        "the run may not extend, shorten or re-base the grid, the window or the cost scenarios",
        "the run may not write a v1 path",
        "the run may not write a v2 selection path",
        "the run may not write a v2 confirmatory path",
        "the run may not write a v3 selection path",
        (
            "the run may not mix the 497,664 v2 selection units with the confirmatory "
            "results, and the two are never tallied with"
        ),
        (
            "the run may not mix the v3 selection results with the confirmatory results, and "
            "the two are never tallied with"
        ),
        (
            "the run may not grade the outcome with a rule other than the single preregistered "
            "v3 promotion rule, and no second confirmatory criterion may be applied"
        ),
        "the run may not open the v1 holdout",
        "the run may not read the v2 confirmatory window",
        "the run may not reset or decrease holdout_exposed_count",
        (
            "the run may not evaluate an asset outside the frozen scope, nor re-evaluate an "
            "asset that has no candidate"
        ),
        (
            "the run may not substitute the published development benchmark for the window "
            "benchmark series"
        ),
        "the run may not drop the 576 btc_ema_168 configurations per asset",
        (
            "the run may not repair the v1/v2 BTC-alignment deviation; it is disclosed in the "
            "final report"
        ),
        (
            "the run may not be started before the commit that carries the runbook and the "
            "authorization exists"
        ),
        "the run may not be started before the confirmatory window can end",
        "a completed run is never re-run; an interrupted run is resumed, never restarted",
    ]

    decision_rule = {
        "criterion_count": 1,
        "authoritative_source": "configs/research_v3.json#holdout.promotion_rule",
        "exactly_one_criterion": True,
        "no_competing_criterion": True,
        "secondary_source": None,
        "secondary_field": None,
        "protocol_path": PROTOCOL_RELATIVE,
        "protocol_manifest_hash": protocol.get("manifest_hash"),
        "criteria": list((protocol.get("decision_rule") or {}).get("criteria") or []),
        "status_vocabulary": list(
            (protocol.get("decision_rule") or {}).get("status_vocabulary") or []
        ),
        "note": (
            "The v3 line states exactly one confirmatory criterion. The v2 line had to amend "
            "two frozen artifacts that disagreed about it; the v3 protocol and this "
            "authorization state one criterion and the execution path applies no second one."
        ),
    }

    document: Dict[str, Any] = {
        "artifact": "v3_confirmatory_runbook",
        "artifact_version": "v3-confirmatory-runbook-1",
        "protocol_version": "v3",
        "universe_version": "v3",
        "created_utc": CREATED_UTC,
        "runbook_status": "PREREGISTERED_OPERATOR_PROCEDURE_NOT_EXECUTED",
        "specification_purpose": (
            "Fix the operator procedure of the single authorized v3 confirmatory run, so "
            "that the session that executes it follows a preregistered procedure instead of "
            "improvising one after the single-use confirmatory window has been burned. The "
            "runbook records rules only; it authorizes nothing, fetches nothing, reads no "
            "candle and writes no confirmatory artifact."
        ),
        "applies_to": {
            "run_id": run.get("run_id"),
            "campaign_id": run.get("campaign_id"),
            "run_phase": run.get("run_phase"),
            "window_start_utc": window_start,
            "window_end_utc": window_end,
            "minimum_closed_hourly_candles": minimum_hours,
            "evaluation_window_rule": window.get("evaluation_window_rule"),
            "in_scope_assets": in_scope,
            "in_scope_count": len(in_scope),
            "in_scope_configurations": config_ids,
            "out_of_scope_assets_without_candidate": out_of_scope,
            "out_of_scope_count": len(out_of_scope),
            "out_of_scope_reasons": out_of_scope_reasons,
            "single_use_window": True,
            "benchmark_symbol": benchmark_symbol,
            "benchmark_is_not_a_candidate": True,
            "benchmark_is_counted_as_an_exposed_asset": True,
        },
        "binding_identities": {
            "authorization": {
                "path": AUTHORIZATION_RELATIVE,
                "manifest_hash": authorization.get("manifest_hash"),
            },
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": selected.get("manifest_hash"),
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_authorization.get("manifest_hash"),
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
                "effective_manifest_hash": (
                    (data_manifest_amendment.get("effective_data_manifest") or {}).get(
                        "effective_data_manifest_hash"
                    )
                ),
                "base_manifest_hash": (
                    (data_manifest_amendment.get("effective_data_manifest") or {}).get(
                        "base_manifest_hash"
                    )
                ),
                "amendment_path": DATA_MANIFEST_AMENDMENT_RELATIVE,
                "amendment_manifest_hash": data_manifest_amendment.get("manifest_hash"),
            },
            "v3_specification": {
                "path": SPEC_V3_RELATIVE,
                "specification_hash": spec_v3.get("specification_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "portable": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": bound_hashed_set,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": bound_execution_path,
                "run_code_identity": bound_run_code_identity,
                "authorized_ordered_code_hash": recorded_identity.get(
                    "authorized_ordered_code_hash"
                ),
                "note": (
                    "The identity of the run is the composite of the canonical digest of the "
                    "hashed v1 engine and the canonical digest of the confirmatory execution "
                    "path. The checkout-dependent ordered digest compute_code_hash() is an "
                    "environment fact and is never used as an identity."
                ),
            },
            "immutable_artifact_anchors": run.get("immutable_artifact_anchors"),
            "decision_rule": decision_rule,
            "evaluation_rule": run.get("evaluation_rule"),
            "bounds": run.get("bounds"),
            "deviation_disclosure": authorization.get("deviation_disclosure"),
        },
        "operator_procedure": {
            "global_rules": [
                "the run is a single logical run: it may be resumed, never restarted",
                "every step is fail-closed: a step that cannot prove its precondition stops the run",
                "nothing is repaired: a mismatch is reported, not corrected",
                "every read of the window is counted in holdout_exposed_count",
                "no step contacts a provider except the readiness probe and the single retrieval",
                "the window benchmark series is retrieved with the window, never substituted",
            ],
            "ordered_steps": ordered_steps,
            "readiness_probe": {
                "primary_host": window_module.PRIMARY_HOST,
                "failover_host": window_module.FAILOVER_HOST,
                "endpoints": probe_endpoints,
                "endpoint_order": [
                    f"{window_module.PRIMARY_HOST}{entry['path']}" for entry in probe_endpoints
                ],
                "failover_order": [
                    f"{window_module.FAILOVER_HOST}{entry['path']}" for entry in probe_endpoints
                ],
                "one_bounded_request_per_endpoint": True,
                "a_host_failure_is_failed_over_not_retried": True,
                "both_statuses_are_recorded_with_timestamps": True,
                "fetches_no_candle": True,
                "increments_holdout_exposed_count": False,
                "max_retries": int(data_policy.get("max_retries")),
                "backoff_seconds": int(data_policy.get("backoff_seconds")),
                "rate_limit_per_minute": int(data_policy.get("rate_limit_per_minute")),
                "failover_policy": data_policy.get("failover_policy"),
                "source_of_truth": "src/v3_confirmatory/window.py",
            },
            "retrieval": {
                "provider": data_policy.get("provider"),
                "endpoint": data_policy.get("endpoint"),
                "failover_endpoints": list(data_policy.get("failover_endpoints") or []),
                "interval": data_policy.get("interval"),
                "closed_candles_only": bool(data_policy.get("closed_candles_only")),
                "retrieval_happens_once": True,
                "one_request_per_asset": True,
                "asset_order": "ascending symbol order",
                "retrieved_series": sorted(in_scope + [benchmark_symbol]),
                "window_bounds": {
                    "window_start_utc": window_start,
                    "window_end_utc": window_end,
                    "minimum_closed_hourly_candles": minimum_hours,
                },
                "dataset_hash_algorithm": "sha256-canonical-hourly-csv-v1",
                "dataset_persistence": (
                    "the canonical hourly CSV next to a record that binds it to "
                    "(run_id, asset, window bounds) and to its content hash, under the shard "
                    "directory of the run"
                ),
                "gaps_are_recorded": True,
                "interpolation_is_forbidden": True,
            },
            "benchmark": {
                "symbol": benchmark_symbol,
                "role": benchmark_rule.get("role"),
                "benchmark_is_not_a_candidate": True,
                "window_benchmark_series_required": True,
                "window_benchmark_retrieval_happens_once": True,
                "window_benchmark_is_hash_verified": True,
                "development_benchmark_may_be_reused": False,
                "development_benchmark_path": benchmark_rule.get("development_benchmark_path"),
                "development_benchmark_content_hash": benchmark_rule.get(
                    "development_benchmark_content_hash"
                ),
                "alignment_rule": benchmark_rule.get("alignment_rule"),
                "alignment_reference": benchmark_rule.get("alignment_reference"),
                "no_forward_fill": True,
                "fail_closed": list(benchmark_rule.get("fail_closed") or []),
                "btc_configurations_dropped": False,
                "grid_rule": (
                    "the 576 btc_ema_168 configurations per asset are evaluated, never "
                    "dropped, re-derived or re-ranked"
                ),
                "source_of_truth": "src/v3_confirmatory/benchmark.py",
            },
            "evaluation": {
                "unchanged_v1_evaluation_metric": True,
                "unchanged_cost_scenarios": True,
                "cost_scenarios": [float(value) for value in costs.get("scenarios") or []],
                "baseline_costs": costs.get("baseline"),
                "evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry": True,
                "no_retuning_reranking_or_grid_extension_on_window": True,
                "authoritative_criterion": (
                    "configs/research_v3.json#holdout.promotion_rule: the single preregistered "
                    "v3 confirmatory criterion"
                ),
                "no_secondary_criterion_is_applied": True,
                "status_vocabulary": list(decision_rule.get("status_vocabulary") or []),
                "outcomes": [
                    "CANDIDATES_SURVIVED_THE_CONFIRMATORY_WINDOW",
                    "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE",
                ],
                "assets_without_candidate_status": "NO_CANDIDATE_NOT_EVALUATED",
            },
            "write_order": write_order_entries,
        },
        "failure_decision_table": failure_decision_table,
        "acceptance_checks": {
            "checks": acceptance_checks,
            "verification_commands": verification_commands,
            "the_output_is_accepted_only_when": [
                "every acceptance check above passes",
                "every verification command exits 0",
                "the handoff records the commands, their exit statuses and the per-asset outcome",
            ],
        },
        "prohibitions": prohibitions,
        "related_artifacts": {
            "confirmatory_authorization_1": {
                "path": AUTHORIZATION_RELATIVE,
                "manifest_hash": authorization.get("manifest_hash"),
            },
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": selected.get("manifest_hash"),
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_authorization.get("manifest_hash"),
            },
            "v3_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v3_specification": {
                "path": SPEC_V3_RELATIVE,
                "specification_hash": spec_v3.get("specification_hash"),
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
                "effective_manifest_hash": (
                    (data_manifest_amendment.get("effective_data_manifest") or {}).get(
                        "effective_data_manifest_hash"
                    )
                ),
            },
            "v3_data_manifest_amendment_1": {
                "path": DATA_MANIFEST_AMENDMENT_RELATIVE,
                "manifest_hash": data_manifest_amendment.get("manifest_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "confirmatory_execution_path": {
                "path": EXECUTION_PATH_ROOT,
                "canonical_source_digest": bound_execution_path,
            },
        },
        "authorizes_a_candle_read": False,
        "authorizes_an_evaluation": False,
        "authorizes_a_second_run": False,
        "durability": {
            "rule": (
                "The runbook is preregistered by being committed. The confirmatory run may "
                "not start before the commit that carries this runbook and the authorization "
                "exists, and it may not start before the window can end."
            ),
            "runbook_commit": None,
            "runbook_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v3_confirmatory_runbook_1.py",
            "verify_command": "python3 scripts/verify_v3_confirmatory_runbook_1.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "so the document does not hash itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / "configs" / "research_v3_confirmatory_runbook_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v6 execution protocol.

``configs/research_v6_execution.json`` records the frozen v6 execution protocol:
the candidate-freeze binding, the evaluation scope bound to the frozen v6
candidate set, the benchmark rule, the inherited v1 rules, the code-hash
constraint, the historical execution-authorization block and the supersedes
chain. The effective execution-authorization block is supplied by
``configs/research_v6_execution_amendment_1.json``. The shared resolver in
``scripts/v6_universe_rules.py`` checks that amendment and resolves it first,
failing closed rather than falling back to the historical static flag.

The verifier never writes to the repository, never contacts a provider, never
reads a candle and never runs a grid. It checks:

1. the protocol is self-hashing, is the v6 execution protocol and is bound to
   the v6 specification;
2. the evaluation scope is exactly the frozen candidate set, which is the set
   of validated constituents of the v6 universe manifest, and it is bound to
   the freeze and to the two manifests by their recomputed identities;
3. the **benchmark rule** is bound: the dataset, its recomputed content hash,
   its recomputed candle count and its recomputed first and last candle, the
   alignment rule, the fail-closed list and the "no configuration is dropped"
   rule -- and the v3 and v4 chains' benchmark dataset, whose candles close
   inside the open v2 confirmatory window, is refused;
4. the **inherited rules** are the v1 rules: the digest of the inherited
   blocks is recomputed from ``configs/research_v1.json``, the grid still
   enumerates 2,304 combinations, and the single confirmatory criterion is the
   unchanged v1 selection rule;
5. the code-hash constraint places the v6 execution path outside the hashed
   set and records the authorized v1 code hash and the canonical tree digest,
   both recomputed;
6. the **effective** execution authorization authorizes nothing, and the one
   statement it makes about the world -- that the v6 selection authorization is
   published -- is recomputed from the repository instead of being read off the
   frozen protocol's static flag. The effective block is resolved amendment
   first, the frozen protocol second, by the same shared helper the future run
   gate calls, and the frozen protocol's historical statement stays on disk
   unchanged;
7. the deviation disclosure records that v6 has no prior deviation to
   disclose;
8. the ``supersedes`` chain names the v5 execution protocol and its two
   amendments with their recomputed identities;
9. the confirmatory-window binding: the freeze's identity, the window's start
   and minimum hours, the development cutoff and the evaluation gate, which is
   recomputed as the later of the four earlier gates and the v6 window's own
   earliest end;
10. the v6 result layout does not collide with a frozen v1-v5 path and no v6
    run artifact exists.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs. The verifier is
**clock-free**: every expectation is a property of the frozen artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    V6RuleError,
    canonical_source_digest,
    compute_manifest_hash,
    read_json,
    resolve_effective_v6_execution_protocol,
    sha256_file,
    verify_effective_v6_selection_authorization,
    verify_v6_historical_execution_authorization,
)

PROTOCOL_RELATIVE = "configs/research_v6_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v5 execution chain the v6 protocol supersedes.
V5_EXECUTION_RELATIVES: Tuple[str, ...] = (
    "configs/research_v5_execution.json",
    "configs/research_v5_execution_amendment_1.json",
    "configs/research_v5_execution_amendment_2.json",
)

#: The freezes that own the v2, v3, v4 and v5 confirmatory windows, and the
#: key each one keeps its window bounds under.
GATE_OWNERS: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary"),
    ("v4", "configs/research_v4_candidate_freeze.json", "confirmatory_window"),
    ("v5", "configs/research_v5_candidate_freeze.json", "confirmatory_window"),
)

#: The v1 blocks the v6 chain inherits unchanged.
INHERITED_V1_BLOCKS: Tuple[str, ...] = (
    "strategy_grid",
    "costs",
    "execution",
    "folds",
    "selection",
    "pilot",
    "metrics",
    "baselines",
    "fixed_breakout_baseline",
    "status",
    "checkpointing",
)

#: The alignment rule the execution path requires.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window before the "
    "frozen engine is called, so that the engine's index pairing equals the UTC-candle-close "
    "alignment of docs/research_protocol.md:101"
)

#: The benchmark dataset of the v3 and v4 chains. The v6 chain may not reuse it.
V3_BENCHMARK_RELATIVE = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

#: The v6 execution path and the hashed set it may not live in.
V6_EXECUTION_ROOT = "src/v6_campaign"
HASHED_SET_ROOT = "src/breakout_research"

#: The paths a v6 run creates. Before the authorized run none of them may exist.
V6_EXECUTION_PATHS: Tuple[str, ...] = (
    "research/shards_v6",
    "research/ledger_v6.json",
    "research/results_manifest_v6.json",
    "research/results_v6.jsonl",
    "research_state/checkpoint_v6.json",
)

#: The frozen v1-v5 paths the v6 result layout may not collide with.
FROZEN_RESULT_PATHS: Tuple[str, ...] = (
    "research/shards",
    "research/shards_v2",
    "research/shards_v3",
    "research/shards_v4",
    "research/shards_v5",
    "research/ledger.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/ledger_v4.json",
    "research/ledger_v5.json",
    "research/results_manifest.json",
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
    "research/results_manifest_v4.json",
    "research/results_manifest_v5.json",
    "research/results.jsonl",
    "research/results_v2.jsonl",
    "research/results_v3.jsonl",
    "research/results_v4.jsonl",
    "research/results_v5.jsonl",
    "research_state/checkpoint.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
    "research_state/checkpoint_v5.json",
)

HOUR_MS = 3_600_000


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(base: Path) -> Optional[str]:
    """The portable identity of the ``*.py`` tree under ``base``.

    Every file contributes its POSIX relative path and the sha256 hex digest of
    its bytes, in ascending path order, so the digest does not depend on the
    checkout's directory enumeration order.
    """
    base = Path(base)
    if not base.is_dir():
        return None
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _dataset_bounds(path: Path) -> Dict[str, Any]:
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return {
        "observed_candle_count": len(timestamps),
        "first_candle_timestamp": timestamps[0] if timestamps else None,
        "last_candle_timestamp": timestamps[-1] if timestamps else None,
    }


def _candles_after_cutoff(path: Path, cutoff_ms: int) -> int:
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    timestamps = [int(row.split(",")[0]) for row in rows[1:]]
    return sum(1 for stamp in timestamps if stamp + HOUR_MS > cutoff_ms)


def _window_bounds(owner: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = owner.get(key) or {}
    start = block.get("confirmatory_window_start_utc") or block.get("opens_utc")
    min_hours = block.get("min_confirmatory_window_hours")
    if min_hours is None:
        min_hours = block.get("min_hours")
    end = block.get("earliest_possible_confirmatory_window_end_utc")
    if end is None:
        end = block.get("earliest_possible_end_utc")
    return {
        "window_start_utc": str(start) if start else None,
        "min_hours": int(min_hours) if min_hours is not None else None,
        "earliest_possible_end_utc": str(end) if end else None,
    }


def _parse_iso(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    computed: Dict[str, Any] = {}
    root = Path(repo_root)

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        PROTOCOL_RELATIVE,
        SPEC_V1_RELATIVE,
        SPEC_V6_RELATIVE,
        FREEZE_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
        AUTHORIZATION_RELATIVE,
    ) + V5_EXECUTION_RELATIVES:
        if not (root / relative).exists():
            return {
                "ok": False,
                "protocol_path": PROTOCOL_RELATIVE,
                "failures": [f"missing artifact: {relative}"],
            }

    protocol = read_json(root / PROTOCOL_RELATIVE)
    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # 1. the document itself ------------------------------------------------
    excluded = tuple(
        (protocol.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    protocol_hash = compute_manifest_hash(protocol, excluded)
    computed["manifest_hash"] = protocol.get("manifest_hash")
    computed["recomputed_manifest_hash"] = protocol_hash
    if protocol.get("manifest_hash") != protocol_hash:
        fail(
            f"manifest_hash mismatch: declared {protocol.get('manifest_hash')}, "
            f"recomputed {protocol_hash}"
        )
    if protocol.get("artifact") != "v6_execution_protocol":
        fail("the protocol is not the v6 execution protocol")
    if protocol.get("universe_version") != "v6":
        fail("the protocol is not a v6 artifact")
    if protocol.get("specification_hash") != spec_v6.get("specification_hash"):
        fail("the protocol is not bound to the v6 specification")
    if protocol.get("specification_status") != "PREREGISTERED_EXECUTION_PROTOCOL_ONLY":
        fail("the protocol does not record that it is a preregistration only")
    if "nothing runs" not in str(protocol.get("specification_purpose") or ""):
        fail("the protocol does not state that nothing runs")

    # 2. the evaluation scope ------------------------------------------------
    scope = protocol.get("evaluation_scope") or {}
    frozen = sorted(
        str(entry.get("binance_pair") or "")
        for entry in (freeze.get("candidates") or [])
        if entry.get("validated") is True
    )
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if not frozen:
        fail("the frozen v6 candidate set is empty")
    if sorted(str(entry) for entry in (scope.get("constituents") or [])) != frozen:
        fail("the evaluated scope is not the frozen candidate set")
    band_order = [
        str(entry.get("binance_pair") or "")
        for entry in (freeze.get("candidates") or [])
        if entry.get("validated") is True
    ]
    if list(scope.get("constituents") or []) != band_order:
        fail("the evaluated scope does not follow the frozen band's order")
    if frozen != validated:
        fail("the frozen candidate set is not the validated v6 universe")
    if scope.get("count") != len(frozen):
        fail("the evaluated scope count differs from the frozen count")
    if scope.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        fail("the evaluated scope is not bound to the freeze manifest hash")
    if scope.get("universe_manifest_hash") != universe.get("manifest_hash"):
        fail("the evaluated scope is not bound to the v6 universe manifest")
    if scope.get("data_manifest_hash") != data.get("manifest_hash"):
        fail("the evaluated scope is not bound to the v6 data manifest")
    if scope.get("universe_manifest_path") != UNIVERSE_RELATIVE:
        fail("the evaluated scope does not name the v6 universe manifest")
    if scope.get("data_manifest_path") != DATA_RELATIVE:
        fail("the evaluated scope does not name the v6 data manifest")
    if scope.get("widening_by_reranking_forbidden") is not True:
        fail("the protocol does not forbid widening the candidate set")
    if scope.get("excluded_assets_stay_excluded") is not True:
        fail("the protocol does not keep excluded assets excluded")
    computed["evaluated_constituents"] = len(frozen)

    # 3. the benchmark rule --------------------------------------------------
    benchmark = protocol.get("benchmark_rule") or {}
    dataset_relative = str(benchmark.get("dataset_path") or "")
    if not dataset_relative:
        fail("the protocol names no benchmark dataset")
    elif dataset_relative == V3_BENCHMARK_RELATIVE:
        fail(
            "the protocol reuses the v3 and v4 chains' benchmark dataset, which is not bounded at "
            "the v6 cutoff"
        )
    else:
        dataset = root / dataset_relative
        if not dataset.exists():
            fail(f"the benchmark dataset {dataset_relative} does not exist")
        else:
            live_hash = sha256_file(dataset)
            if benchmark.get("content_hash") != live_hash:
                fail(
                    "the benchmark content hash does not match the dataset: "
                    f"{benchmark.get('content_hash')} != {live_hash}"
                )
            bounds = _dataset_bounds(dataset)
            if benchmark.get("observed_candle_count") != bounds["observed_candle_count"]:
                fail("the benchmark candle count does not match the dataset")
            if benchmark.get("first_candle_timestamp") != bounds["first_candle_timestamp"]:
                fail("the benchmark first candle does not match the dataset")
            if benchmark.get("last_candle_timestamp") != bounds["last_candle_timestamp"]:
                fail("the benchmark last candle does not match the dataset")
    if benchmark.get("alignment") != ALIGNMENT_RULE:
        fail("the protocol does not bind the benchmark alignment rule")
    if benchmark.get("no_forward_fill") is not True:
        fail("the protocol does not forbid forward-filling the benchmark")
    if not benchmark.get("fail_closed"):
        fail("the protocol records no fail-closed condition")
    if "576" not in str(benchmark.get("grid_rule") or ""):
        fail("the protocol does not record the unchanged grid rule")
    if benchmark.get("symbol") != "BTCUSDT":
        fail("the benchmark symbol is not BTCUSDT")
    cutoff = str((spec_v6.get("holdout") or {}).get("development_cutoff_utc"))
    v3_benchmark = root / V3_BENCHMARK_RELATIVE
    if v3_benchmark.exists():
        cutoff_ms = int(_parse_iso(cutoff).timestamp() * 1000)
        after = _candles_after_cutoff(v3_benchmark, cutoff_ms)
        computed["v3_benchmark_candles_after_the_v6_cutoff"] = after
        if str(after) not in str(benchmark.get("note") or ""):
            fail(
                "the protocol does not record how many candles of the v3 and v4 benchmark close "
                "after the cutoff"
            )

    # 4. the inherited v1 rules ---------------------------------------------
    inherited = protocol.get("inherited_rules") or {}
    blocks = tuple(inherited.get("blocks") or ())
    if blocks != INHERITED_V1_BLOCKS:
        fail("the protocol does not inherit exactly the v1 rule blocks")
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )
    computed["recomputed_inherited_blocks_digest"] = inherited_digest
    if inherited.get("blocks_digest") != inherited_digest:
        fail("the inherited rules digest does not recompute from the v1 specification")
    if inherited.get("v1_specification_hash") != spec_v1.get("specification_hash"):
        fail("the inherited rules do not name the v1 specification")
    grid = spec_v1.get("strategy_grid") or {}
    total = 1
    for key, values in grid.items():
        if key == "total_combinations":
            continue
        total *= len(values)
    if total != 2304:
        fail("the v1 grid no longer enumerates 2,304 combinations")
    if inherited.get("grid_total_combinations") != 2304:
        fail("the protocol does not record the unchanged 2,304-configuration grid")
    criterion = str(inherited.get("single_confirmatory_criterion") or "")
    if "unchanged v1 selection rule" not in criterion or "never re-tuned" not in criterion:
        fail("the protocol does not bind the single confirmatory criterion to the v1 rule")

    # 5. the code-hash constraint -------------------------------------------
    constraint = protocol.get("code_hash_constraint") or {}
    if constraint.get("authorized_code_hash") != authorization.get("code_hash"):
        fail("the code-hash constraint does not record the authorized code hash of record")
    if constraint.get("hashed_source_root") != HASHED_SET_ROOT:
        fail("the code-hash constraint does not name the hashed source root")
    hashed_set_digest = canonical_source_digest(root)
    computed["canonical_hashed_set_digest"] = hashed_set_digest
    if hashed_set_digest is None:
        fail("the hashed source set is missing, so its digest cannot be recomputed")
    elif constraint.get("canonical_hashed_set_digest") != hashed_set_digest:
        fail(
            "the code-hash constraint records another canonical tree digest, recomputed "
            f"{hashed_set_digest}"
        )
    if constraint.get("canonical_digest_is_the_identity") is not True:
        fail("the code-hash constraint does not record the canonical digest as the identity")
    if constraint.get("v6_execution_must_live_outside_hashed_set") is not True:
        fail("the code-hash constraint does not require the v6 execution path outside the hashed set")
    recorded_execution_root = str(constraint.get("v6_execution_root") or "")
    if recorded_execution_root != V6_EXECUTION_ROOT:
        fail("the code-hash constraint does not name the v6 execution root")
    if recorded_execution_root.startswith(HASHED_SET_ROOT + "/"):
        fail("the v6 execution root is inside the hashed source set")
    if constraint.get("edit_under_src_breakout_research_forbidden_without_reauthorization") is not True:
        fail("the code-hash constraint does not forbid edits under src/breakout_research")
    execution_root = root / V6_EXECUTION_ROOT
    execution_path_exists = (root / "src").is_dir() and execution_root.is_dir()
    if constraint.get("v6_execution_path_exists") is not execution_path_exists:
        fail(
            "the code-hash constraint records the wrong state for the v6 execution path: "
            f"{constraint.get('v6_execution_path_exists')!r}, recomputed {execution_path_exists!r}"
        )
    if execution_path_exists:
        recorded = str(constraint.get("v6_execution_path_canonical_digest") or "")
        live = tree_digest(execution_root)
        computed["v6_execution_path_canonical_digest"] = live
        if not recorded:
            fail(
                "the v6 execution path exists but the protocol records no canonical digest for it"
            )
        elif recorded != live:
            fail(
                "the code-hash constraint records another canonical digest for the v6 execution "
                f"path: {recorded}, recomputed {live}"
            )

    # 6. the execution authorization authorizes nothing ----------------------
    # The **effective** execution-authorization block is resolved amendment
    # first, the frozen protocol second, by the shared helper the future run
    # gate calls. The frozen protocol's block recorded the state of the chain
    # at its publication instant; the amendment supplies the effective one.
    effective: Dict[str, Any] = {}
    resolved = True
    try:
        effective = resolve_effective_v6_execution_protocol(root)
    except V6RuleError as error:
        fail(str(error))
        resolved = False
    execution_authorization = effective.get("execution_authorization") or {}
    computed["effective_execution_authorization_source"] = effective.get(
        "_amendment_path"
    ) or PROTOCOL_RELATIVE
    if resolved:
        for flag in (
            "execution_authorized",
            "grid_run_authorized",
            "candle_fetch_authorized",
            "confirmatory_evaluation_authorized",
            "second_run_authorized",
        ):
            if execution_authorization.get(flag) is not False:
                fail(f"the execution authorization does not record {flag} as false")
        # The one statement of the block that is about the world and not about
        # the protocol's own authority: the published selection authorization.
        # It is recomputed from the repository, not read off a static flag.
        try:
            computed.update(verify_effective_v6_selection_authorization(root, effective))
        except V6RuleError as error:
            fail(str(error))
    # The frozen protocol's own authority flags, on disk: the protocol
    # authorizes nothing in its own right, and the amendment does not change
    # that.
    frozen_block = protocol.get("execution_authorization") or {}
    for flag in (
        "execution_authorized",
        "grid_run_authorized",
        "candle_fetch_authorized",
        "confirmatory_evaluation_authorized",
        "second_run_authorized",
    ):
        if frozen_block.get(flag) is not False:
            fail(f"the frozen v6 execution protocol does not record {flag} as false")
    # The historical statement stays on disk, unchanged and visible.
    try:
        computed.update(verify_v6_historical_execution_authorization(root))
    except V6RuleError as error:
        fail(str(error))
    for flag in (
        "execution_authorized",
        "campaign_authorized",
        "selection_authorized",
        "confirmatory_authorized",
    ):
        if (protocol.get("authorization") or {}).get(flag) is not False:
            fail(f"the protocol's own authorization.{flag} is not false")

    # 7. the deviation disclosure -------------------------------------------
    disclosure = protocol.get("deviation_disclosure") or {}
    if disclosure.get("not_applicable") is not True:
        fail("the deviation disclosure does not record v6 as not applicable")
    if disclosure.get("records_with_btc_filter") != 0:
        fail("the deviation disclosure records a non-zero affected-record count")

    # 8. the supersedes chain ------------------------------------------------
    supersedes = protocol.get("supersedes") or {}
    if supersedes.get("protocol_version") != "v5":
        fail("the protocol does not supersede the v5 execution protocol")
    if supersedes.get("v1_v2_v3_v4_v5_artifacts_are_immutable") is not True:
        fail("the protocol does not declare the v1-v5 artifacts immutable")
    recorded_chain = supersedes.get("superseded_artifacts") or {}
    for relative in V5_EXECUTION_RELATIVES:
        key = Path(relative).stem
        entry = recorded_chain.get(key)
        if entry is None:
            fail(f"the supersedes chain does not name {relative}")
            continue
        if entry.get("path") != relative:
            fail(f"the supersedes chain names another path for {relative}")
        path = root / relative
        document = read_json(path)
        recomputed = compute_manifest_hash(document, ("manifest_hash",))
        if document.get("manifest_hash") != recomputed:
            fail(f"the superseded artifact {relative} does not recompute its own manifest_hash")
        if entry.get("manifest_hash") != recomputed:
            fail(f"the supersedes chain names another manifest hash for {relative}")
        if entry.get("sha256") != sha256_file(path):
            fail(f"the supersedes chain names another file digest for {relative}")

    # 9. the confirmatory-window binding ------------------------------------
    window_block = protocol.get("candidate_freeze_and_confirmatory_window") or {}
    if window_block.get("candidate_freeze_path") != FREEZE_RELATIVE:
        fail("the protocol does not name the v6 candidate freeze")
    if window_block.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        fail("the protocol is not bound to the v6 candidate freeze")
    v6_window = freeze.get("confirmatory_window") or {}
    if window_block.get("confirmatory_window_opens_utc") != v6_window.get("opens_utc"):
        fail("the protocol names another confirmatory-window start than the freeze")
    if window_block.get("min_confirmatory_window_hours") != v6_window.get("min_hours"):
        fail("the protocol names another minimum of hours than the freeze")
    if window_block.get("earliest_possible_confirmatory_window_end_utc") != v6_window.get(
        "earliest_possible_end_utc"
    ):
        fail("the protocol names another earliest window end than the freeze")
    if window_block.get("development_cutoff_utc") != cutoff:
        fail("the protocol names another development cutoff than the preregistered one")
    if window_block.get("single_use") is not True:
        fail("the protocol does not record the confirmatory window as single-use")
    if window_block.get("no_ranking_or_retuning_on_holdout") is not True:
        fail("the protocol does not forbid ranking or re-tuning on the holdout")
    if window_block.get("v1_v2_v3_v4_v5_confirmatory_window_reuse") != "forbidden":
        fail("the protocol does not forbid the reuse of an earlier confirmatory window")
    membership = (spec_v6.get("holdout") or {}).get("confirmatory_window_membership") or {}
    if window_block.get("confirmatory_window_membership_rule") != str(membership.get("rule") or ""):
        fail("the protocol does not bind the membership rule the v6 specification owns")
    # The evaluation gate is recomputed from the four earlier freezes and the
    # v6 window's own earliest end.
    gates: List[Tuple[str, str]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = _window_bounds(owner, key)
        if not bounds["earliest_possible_end_utc"]:
            fail(f"the {version} candidate freeze carries no earliest window end")
            continue
        gates.append((version, bounds["earliest_possible_end_utc"]))
    if v6_window.get("earliest_possible_end_utc"):
        gates.append(("v6", str(v6_window["earliest_possible_end_utc"])))
    if gates:
        expected_gate = max(end for _, end in gates)
        computed["evaluation_may_not_start_before_utc"] = expected_gate
        if window_block.get("evaluation_may_not_start_before_utc") != expected_gate:
            fail(
                "the effective v6 evaluation start is "
                f"{window_block.get('evaluation_may_not_start_before_utc')}, but the later of the "
                f"v2, v3, v4 and v5 gates and the v6 window's own earliest end is {expected_gate}"
            )
    recorded_gates = window_block.get("confirmatory_gates") or []
    if len(recorded_gates) != len(GATE_OWNERS):
        fail("the protocol does not record the four prior confirmatory gates")
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        bounds = _window_bounds(owner, key)
        recorded = next(
            (gate for gate in recorded_gates if gate.get("version") == version), None
        )
        if recorded is None:
            fail(f"the protocol does not record the {version} confirmatory gate")
            continue
        if recorded.get("source_path") != relative:
            fail(f"the recorded {version} gate does not name the freeze that owns its window")
        if recorded.get("window_start_utc") != bounds["window_start_utc"]:
            fail(f"the recorded {version} gate names another window start")
        if recorded.get("earliest_possible_end_utc") != bounds["earliest_possible_end_utc"]:
            fail(f"the recorded {version} gate ends at another instant")
        if int(recorded.get("min_hours") or 0) != int(bounds["min_hours"] or 0):
            fail(f"the recorded {version} gate does not carry the window's minimum hours")

    # 10. the result layout and the empty namespace --------------------------
    layout = protocol.get("v6_result_layout") or {}
    layout_paths = [str(value) for value in layout.values() if isinstance(value, str)]
    for foreign in FROZEN_RESULT_PATHS:
        if foreign in layout_paths:
            fail(f"the v6 result layout collides with the frozen path {foreign}")
    for relative in V6_EXECUTION_PATHS:
        if (root / relative).exists():
            fail(
                f"the v6 run artifact {relative} exists, but the v6 chain has not run: the "
                "protocol authorizes no run"
            )

    return {
        "ok": not failures,
        "protocol_path": PROTOCOL_RELATIVE,
        "manifest_hash": protocol.get("manifest_hash"),
        "recomputed_manifest_hash": protocol_hash,
        "computed": computed,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

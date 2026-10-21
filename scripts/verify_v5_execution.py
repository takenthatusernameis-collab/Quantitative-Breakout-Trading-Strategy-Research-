#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v5 execution protocol.

``configs/research_v5_execution.json`` records the v5 execution protocol, and
``configs/research_v5_execution_amendment_1.json`` supplies the bindings the
first publication did not carry.  The **effective** protocol is the amendment
for the blocks it restates and the protocol for the blocks it does not; both
stay on disk, unchanged and visible.

The verifier never writes to the repository, never contacts a provider, never
reads a candle and never runs a grid.  It checks:

1. the protocol and the amendment are both self-hashing, and the amendment
   names the protocol it amends by its **recomputed** manifest hash and its
   **recomputed** file digest;
2. the effective evaluation scope is exactly the frozen candidate set, which is
   the set of validated constituents of the v5 universe manifest, and it is
   bound to the freeze and to the two manifests by their recomputed identities;
3. the **benchmark rule** is bound: the dataset, its recomputed content hash,
   its recomputed candle count and its recomputed first and last candle, the
   alignment rule, the fail-closed list and the "no configuration is dropped"
   rule -- and the v4 chain's benchmark dataset, whose candles close inside the
   open v2 confirmatory window, is refused;
4. the **inherited rules** are the v1 rules: the digest of the inherited
   blocks is recomputed from ``configs/research_v1.json``, the grid still
   enumerates 2,304 combinations, and the single confirmatory criterion is the
   unchanged v1 selection rule;
5. the code-hash constraint places the v5 execution path outside the hashed
   set and records the authorized v1 code hash as the value of record;
6. the execution authorization authorizes nothing;
7. the deviation disclosure records that v5 has no prior deviation to
   disclose;
8. the ``supersedes`` chain names the v4 execution protocol, with its
   recomputed identities;
9. the v5 result layout does not collide with a frozen v1-v4 path and no v5
   run artifact exists.

Exit status is 0 when every check passes and 1 otherwise.  The report is
printed as JSON so it can be diffed between runs.  The verifier is
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

PROTOCOL_RELATIVE = "configs/research_v5_execution.json"
AMENDMENT_RELATIVE = "configs/research_v5_execution_amendment_1.json"
V4_PROTOCOL_RELATIVE = "configs/research_v4_execution.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V5_RELATIVE = "configs/research_v5.json"
FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v5.json"
DATA_RELATIVE = "research/data_manifest_v5.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

HASHED_SET_ROOT = "src/breakout_research"
V5_EXECUTION_ROOT = "src/v5_campaign"

#: The v1 blocks the v5 chain inherits unchanged.
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

#: The benchmark dataset of the v4 chain. The v5 chain may not reuse it.
V4_BENCHMARK_RELATIVE = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

#: The paths a v5 run creates. Before the authorized run none of them may exist.
V5_EXECUTION_PATHS = (
    "research/shards_v5",
    "research/ledger_v5.json",
    "research/results_manifest_v5.json",
    "research/results_v5.jsonl",
    "research_state/checkpoint_v5.json",
)

#: The frozen v1-v4 paths the v5 result layout may not collide with.
FROZEN_RESULT_PATHS = (
    "research/shards",
    "research/shards_v2",
    "research/shards_v3",
    "research/shards_v4",
    "research/ledger.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/ledger_v4.json",
    "research/results_manifest.json",
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
    "research/results_manifest_v4.json",
    "research/results.jsonl",
    "research/results_v2.jsonl",
    "research/results_v3.jsonl",
    "research/results_v4.jsonl",
    "research_state/checkpoint.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
)

HOUR_MS = 3_600_000


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(root: Path) -> Optional[str]:
    """The portable identity of the ``*.py`` tree under ``root`` (BRAIN-009)."""
    base = Path(root)
    if not base.exists():
        return None
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


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


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)
    computed: Dict[str, Any] = {}

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        PROTOCOL_RELATIVE,
        AMENDMENT_RELATIVE,
        V4_PROTOCOL_RELATIVE,
        SPEC_V1_RELATIVE,
        SPEC_V5_RELATIVE,
        FREEZE_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
    ):
        if not (root / relative).exists():
            return {
                "ok": False,
                "protocol_path": PROTOCOL_RELATIVE,
                "failures": [f"missing artifact: {relative}"],
            }

    protocol = _load(root / PROTOCOL_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    v4_protocol = _load(root / V4_PROTOCOL_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v5 = _load(root / SPEC_V5_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_RELATIVE)
    data = _load(root / DATA_RELATIVE)

    # 1. the two documents, and the precedence between them -----------------
    protocol_excluded = tuple(
        (protocol.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    protocol_hash = compute_manifest_hash(protocol, protocol_excluded)
    if protocol.get("manifest_hash") != protocol_hash:
        fail(
            f"manifest_hash mismatch: declared {protocol.get('manifest_hash')}, "
            f"recomputed {protocol_hash}"
        )
    if protocol.get("artifact") != "v5_execution_protocol":
        fail("the protocol is not the v5 execution protocol")
    if protocol.get("universe_version") != "v5":
        fail("the protocol is not a v5 artifact")
    if protocol.get("specification_hash") != spec_v5.get("specification_hash"):
        fail("the protocol is not bound to the v5 specification")

    amendment_excluded = tuple(
        (amendment.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    amendment_hash = compute_manifest_hash(amendment, amendment_excluded)
    computed["amendment_manifest_hash"] = amendment_hash
    if amendment.get("manifest_hash") != amendment_hash:
        fail(
            f"the amendment's manifest_hash mismatch: declared {amendment.get('manifest_hash')}, "
            f"recomputed {amendment_hash}"
        )
    amends = amendment.get("amends") or {}
    if amends.get("file") != PROTOCOL_RELATIVE:
        fail("the amendment does not name the v5 execution protocol")
    if amends.get("manifest_hash") != protocol_hash:
        fail("the amendment names another manifest hash for the v5 execution protocol")
    if amends.get("sha256") != sha256_file(root / PROTOCOL_RELATIVE):
        fail("the amendment names another file digest for the v5 execution protocol")
    precedence = amendment.get("precedence") or {}
    if "this amendment" not in str(precedence.get("rule") or ""):
        fail("the amendment does not state the precedence rule")

    # The effective protocol: the amendment first, the protocol second.
    effective: Dict[str, Any] = {}
    for block in set(protocol) | set(amendment):
        if block in {"amends", "amendment_status", "artifact", "artifact_version", "created_utc",
                     "hashing", "manifest_hash", "precedence", "problem", "related_artifacts"}:
            continue
        effective[block] = amendment[block] if block in amendment else protocol.get(block)

    # 2. the evaluation scope ------------------------------------------------
    scope = effective.get("evaluation_scope") or {}
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
        fail("the frozen v5 candidate set is empty")
    if list(scope.get("constituents") or []) != frozen:
        fail("the evaluated scope is not the frozen candidate set")
    if frozen != validated:
        fail("the frozen candidate set is not the validated v5 universe")
    if scope.get("count") != len(frozen):
        fail("the evaluated scope count differs from the frozen count")
    if scope.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        fail("the evaluated scope is not bound to the freeze manifest hash")
    if scope.get("universe_manifest_hash") != universe.get("manifest_hash"):
        fail("the evaluated scope is not bound to the v5 universe manifest")
    if scope.get("data_manifest_hash") != data.get("manifest_hash"):
        fail("the evaluated scope is not bound to the v5 data manifest")
    if scope.get("widening_by_reranking_forbidden") is not True:
        fail("the protocol does not forbid widening the candidate set")
    if scope.get("excluded_assets_stay_excluded") is not True:
        fail("the protocol does not keep excluded assets excluded")
    computed["evaluated_constituents"] = len(frozen)

    # 3. the benchmark rule --------------------------------------------------
    benchmark = effective.get("benchmark_rule") or {}
    dataset_relative = str(benchmark.get("dataset_path") or "")
    if not dataset_relative:
        fail("the protocol names no benchmark dataset")
    elif dataset_relative == V4_BENCHMARK_RELATIVE:
        fail("the protocol reuses the v4 chain's benchmark dataset, which is not bounded at the v5 cutoff")
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
    v4_benchmark = root / V4_BENCHMARK_RELATIVE
    cutoff = str(_dig(spec_v5, "holdout.development_cutoff_utc"))
    if v4_benchmark.exists():
        cutoff_ms = int(
            datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )
        after = _candles_after_cutoff(v4_benchmark, cutoff_ms)
        computed["v4_benchmark_candles_after_the_v5_cutoff"] = after
        if str(after) not in str(benchmark.get("note") or ""):
            fail("the protocol does not record how many candles of the v4 benchmark close after the cutoff")

    # 4. the inherited v1 rules ---------------------------------------------
    inherited = effective.get("inherited_rules") or {}
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
    constraint = effective.get("code_hash_constraint") or {}
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    if constraint.get("authorized_code_hash") != authorization.get("code_hash"):
        fail("the code-hash constraint does not record the authorized code hash of record")
    if constraint.get("v5_execution_must_live_outside_hashed_set") is not True:
        fail("the code-hash constraint does not require the v5 execution path outside the hashed set")
    if constraint.get("v5_execution_root") != V5_EXECUTION_ROOT:
        fail("the code-hash constraint does not name the v5 execution root")
    if V5_EXECUTION_ROOT.startswith(HASHED_SET_ROOT + "/"):
        fail("the v5 execution root is inside the hashed source set")
    if constraint.get("edit_under_src_breakout_research_forbidden_without_reauthorization") is not True:
        fail("the code-hash constraint does not forbid edits under src/breakout_research")
    hashed_set_digest = canonical_source_digest(root / HASHED_SET_ROOT)
    computed["hashed_set_digest"] = hashed_set_digest
    if hashed_set_digest is None:
        fail("the hashed source set is missing, so its digest cannot be recomputed")

    # 6. the execution authorization authorizes nothing ----------------------
    execution_authorization = effective.get("execution_authorization") or {}
    for flag in (
        "execution_authorized",
        "grid_run_authorized",
        "candle_fetch_authorized",
        "confirmatory_evaluation_authorized",
        "second_run_authorized",
        "selection_authorization_present",
    ):
        if execution_authorization.get(flag) is not False:
            fail(f"the execution authorization does not record {flag} as false")
    for flag in ("execution_authorized", "campaign_authorized", "selection_authorized",
                 "confirmatory_authorized"):
        if (protocol.get("authorization") or {}).get(flag) is not False:
            fail(f"the protocol's own authorization.{flag} is not false")
    selection_authorization = root / "configs" / "research_v5_selection_authorization_1.json"
    if selection_authorization.exists():
        fail("a v5 selection authorization exists, but the v5 chain has not been authorized")

    # 7. the deviation disclosure -------------------------------------------
    disclosure = effective.get("deviation_disclosure") or {}
    if disclosure.get("not_applicable") is not True:
        fail("the deviation disclosure does not record v5 as not applicable")
    if disclosure.get("records_with_btc_filter") != 0:
        fail("the deviation disclosure records a non-zero affected-record count")

    # 8. the supersedes chain ------------------------------------------------
    supersedes = effective.get("supersedes") or {}
    if supersedes.get("specification_path") != V4_PROTOCOL_RELATIVE:
        fail("the protocol does not supersede the v4 execution protocol")
    v4_hash = compute_manifest_hash(v4_protocol, ("manifest_hash",))
    if v4_hash != v4_protocol.get("manifest_hash"):
        fail("the v4 execution protocol does not recompute its manifest_hash")
    if supersedes.get("specification_hash") != v4_hash:
        fail("the protocol names another hash for the v4 execution protocol")
    if supersedes.get("specification_sha256") != sha256_file(root / V4_PROTOCOL_RELATIVE):
        fail("the protocol names another file digest for the v4 execution protocol")
    if supersedes.get("v1_v2_v3_v4_artifacts_are_immutable") is not True:
        fail("the protocol does not declare the v1-v4 artifacts immutable")

    # 9. the candidate-freeze binding, the layout and the empty namespace ----
    window_block = effective.get("candidate_freeze_and_confirmatory_window") or {}
    if window_block.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        fail("the protocol is not bound to the v5 candidate freeze")
    if window_block.get("confirmatory_window_opens_utc") != _dig(freeze, "confirmatory_window.opens_utc"):
        fail("the protocol names another confirmatory-window start than the freeze")
    if window_block.get("min_confirmatory_window_hours") != _dig(freeze, "confirmatory_window.min_hours"):
        fail("the protocol names another minimum of hours than the freeze")
    if window_block.get("development_cutoff_utc") != cutoff:
        fail("the protocol names another development cutoff than the preregistered one")
    if window_block.get("single_use") is not True:
        fail("the protocol does not record the confirmatory window as single-use")
    if window_block.get("no_ranking_or_retuning_on_holdout") is not True:
        fail("the protocol does not forbid ranking or re-tuning on the holdout")
    layout = effective.get("v5_result_layout") or {}
    layout_paths = [str(value) for value in layout.values() if isinstance(value, str)]
    for foreign in FROZEN_RESULT_PATHS:
        if foreign in layout_paths:
            fail(f"the v5 result layout collides with the frozen path {foreign}")
    for relative in V5_EXECUTION_PATHS:
        if (root / relative).exists():
            fail(f"the v5 run artifact {relative} exists, but the v5 chain has not run")

    return {
        "ok": not failures,
        "protocol_path": PROTOCOL_RELATIVE,
        "amendment_path": AMENDMENT_RELATIVE,
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

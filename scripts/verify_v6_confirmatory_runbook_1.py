#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v6 confirmatory runbook.

``configs/research_v6_confirmatory_runbook_1.json`` fixes the operator
procedure of the single authorized v6 confirmatory run. The verifier never
writes to the repository, never contacts a provider, never reads a candle and
never runs an evaluation. It checks:

1. the runbook is self-hashing, is the v6 confirmatory runbook and is bound to
   the v6 confirmatory protocol and the v6 candidate freeze;
2. the **scope** is re-derived from the frozen band: the in-scope assets are
   the validated members, the excluded members keep their reasons, and the
   selected configurations are *not* claimed, because the selection run has not
   happened yet;
3. the **window bounds** are re-derived from the freeze and the four earlier
   freezes: the start, the minimum hours, the earliest end and the evaluation
   gate;
4. the **decision rule** is the unchanged v1 rule: the criteria are re-derived
   from the v1 selection block, the status vocabulary is the v1 status
   vocabulary and the vocabulary may not be extended;
5. the **immutable anchors** are the recomputed file digests of the artifacts
   the run must not disturb;
6. the **code identity** is the canonical tree digest, recomputed;
7. the **write order** names exactly eight output paths, all in the v6
   namespace and none of them colliding with a frozen v1-v5 path;
8. the runbook **authorizes nothing**: no candle read, no evaluation and no
   second run, and no v6 confirmatory artifact exists.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs. The verifier is
**clock-free**: every expectation is a property of the frozen artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    canonical_source_digest,
    compute_manifest_hash,
    read_json,
    sha256_file,
)

RUNBOOK_RELATIVE = "configs/research_v6_confirmatory_runbook_1.json"
PROTOCOL_RELATIVE = "configs/research_v6_confirmatory_protocol.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V6_RELATIVE = "configs/research_v6.json"
FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v6.json"
DATA_RELATIVE = "research/data_manifest_v6.json"
EXECUTION_RELATIVE = "configs/research_v6_execution.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

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

#: The frozen v1-v5 paths the v6 confirmatory output paths may not collide with.
FROZEN_RESULT_PATHS: Tuple[str, ...] = (
    "research/shards",
    "research/shards_v2",
    "research/shards_v3",
    "research/shards_v4",
    "research/shards_v5",
    "research/shards_v2_confirmatory",
    "research/shards_v3_confirmatory",
    "research/ledger.json",
    "research/ledger_v2.json",
    "research/ledger_v3.json",
    "research/ledger_v4.json",
    "research/ledger_v5.json",
    "research/ledger_v2_confirmatory.json",
    "research/ledger_v3_confirmatory.json",
    "research/results.jsonl",
    "research/results_v2.jsonl",
    "research/results_v3.jsonl",
    "research/results_v4.jsonl",
    "research/results_v5.jsonl",
    "research/results_v2_confirmatory.jsonl",
    "research/results_v3_confirmatory.jsonl",
    "research/results_manifest.json",
    "research/results_manifest_v2.json",
    "research/results_manifest_v3.json",
    "research/results_manifest_v4.json",
    "research/results_manifest_v5.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_manifest_v3_confirmatory.json",
    "research_state/checkpoint.json",
    "research_state/checkpoint_v2.json",
    "research_state/checkpoint_v3.json",
    "research_state/checkpoint_v4.json",
    "research_state/checkpoint_v5.json",
    "research_state/checkpoint_v2_confirmatory.json",
    "research_state/checkpoint_v3_confirmatory.json",
    "reports/confirmatory_evaluation_v2.json",
    "reports/confirmatory_evaluation_v3.json",
    "reports/confirmatory_report_v2.md",
    "reports/confirmatory_report_v3.md",
)

#: The v6 confirmatory artifacts a run creates. Before the authorized run none
#: of them may exist.
V6_CONFIRMATORY_RUN_ARTIFACTS: Tuple[str, ...] = (
    "research/v6_confirmatory_window_manifest.json",
    "research/shards_v6_confirmatory",
    "research/results_v6_confirmatory.jsonl",
    "research/ledger_v6_confirmatory.json",
    "research/results_manifest_v6_confirmatory.json",
    "research_state/checkpoint_v6_confirmatory.json",
    "configs/research_v6_confirmatory_authorization_1.json",
    "reports/confirmatory_evaluation_v6.json",
    "reports/confirmatory_report_v6.md",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    computed: Dict[str, Any] = {}
    root = Path(repo_root)

    def fail(message: str) -> None:
        failures.append(message)

    for relative in (
        RUNBOOK_RELATIVE,
        PROTOCOL_RELATIVE,
        SPEC_V1_RELATIVE,
        SPEC_V6_RELATIVE,
        FREEZE_RELATIVE,
        UNIVERSE_RELATIVE,
        DATA_RELATIVE,
        EXECUTION_RELATIVE,
        AUTHORIZATION_RELATIVE,
    ):
        if not (root / relative).exists():
            return {
                "ok": False,
                "runbook_path": RUNBOOK_RELATIVE,
                "failures": [f"missing artifact: {relative}"],
            }

    runbook = read_json(root / RUNBOOK_RELATIVE)
    protocol = read_json(root / PROTOCOL_RELATIVE)
    spec_v1 = read_json(root / SPEC_V1_RELATIVE)
    spec_v6 = read_json(root / SPEC_V6_RELATIVE)
    freeze = read_json(root / FREEZE_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    data = read_json(root / DATA_RELATIVE)
    execution = read_json(root / EXECUTION_RELATIVE)
    authorization = read_json(root / AUTHORIZATION_RELATIVE)

    # 1. the document itself ------------------------------------------------
    excluded = tuple(
        (runbook.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    runbook_hash = compute_manifest_hash(runbook, excluded)
    computed["manifest_hash"] = runbook.get("manifest_hash")
    computed["recomputed_manifest_hash"] = runbook_hash
    if runbook.get("manifest_hash") != runbook_hash:
        fail(
            f"manifest_hash mismatch: declared {runbook.get('manifest_hash')}, "
            f"recomputed {runbook_hash}"
        )
    if runbook.get("artifact") != "v6_confirmatory_runbook":
        fail("the runbook is not the v6 confirmatory runbook")
    if runbook.get("universe_version") != "v6":
        fail("the runbook is not a v6 artifact")
    if runbook.get("runbook_status") != "PREREGISTERED_OPERATOR_PROCEDURE_NOT_EXECUTED":
        fail("the runbook does not record that the procedure has not been executed")
    if "authorizes no candle read" not in str(runbook.get("specification_purpose") or ""):
        fail("the runbook does not state that it authorizes no candle read")

    bindings = runbook.get("binding_identities") or {}
    protocol_binding = bindings.get("confirmatory_protocol") or {}
    if protocol_binding.get("path") != PROTOCOL_RELATIVE:
        fail("the runbook does not name the v6 confirmatory protocol")
    protocol_excluded = tuple(
        (protocol.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    if protocol.get("manifest_hash") != compute_manifest_hash(protocol, protocol_excluded):
        fail("the v6 confirmatory protocol does not recompute its own manifest_hash")
    if protocol_binding.get("manifest_hash") != protocol.get("manifest_hash"):
        fail("the runbook is not bound to the v6 confirmatory protocol")
    freeze_binding = bindings.get("v6_candidate_freeze") or {}
    if freeze_binding.get("manifest_hash") != freeze.get("manifest_hash"):
        fail("the runbook is not bound to the v6 candidate freeze")

    # 2. the scope -----------------------------------------------------------
    applies = runbook.get("applies_to") or {}
    members = list((freeze.get("band") or {}).get("members") or [])
    in_scope = [str(entry["binance_pair"]) for entry in members if entry.get("validated") is True]
    excluded_members = [entry for entry in members if entry.get("validated") is not True]
    manifest_validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in (universe.get("eligible_assets") or [])
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(in_scope) != manifest_validated:
        fail("the frozen v6 candidate set is not the validated v6 universe")
    if list(applies.get("in_scope_assets") or []) != in_scope:
        fail("the runbook's in-scope assets are not the validated members of the frozen band")
    if applies.get("in_scope_count") != len(in_scope):
        fail("the runbook miscounts the in-scope assets")
    computed["in_scope_assets"] = len(in_scope)
    if applies.get("in_scope_configurations") is not None:
        fail(
            "the runbook claims the selected configurations, but the v6 selection run has not "
            "happened yet"
        )
    if not applies.get("in_scope_configurations_rule"):
        fail("the runbook does not state how the selected configuration per asset is bound")
    if list(applies.get("out_of_scope_assets_excluded_at_validation") or []) != [
        str(entry["binance_pair"]) for entry in excluded_members
    ]:
        fail("the runbook's out-of-scope assets are not the excluded members of the frozen band")
    recorded_reasons = applies.get("out_of_scope_reasons") or {}
    for entry in excluded_members:
        pair = str(entry["binance_pair"])
        if recorded_reasons.get(pair) != entry.get("exclusion_reason"):
            fail(f"the runbook records another exclusion reason for {pair}")
    if applies.get("out_of_scope_count") != len(excluded_members):
        fail("the runbook miscounts the out-of-scope assets")
    if applies.get("single_use_window") is not True:
        fail("the runbook does not record the window as single-use")
    if applies.get("benchmark_symbol") != "BTCUSDT":
        fail("the runbook's benchmark symbol is not BTCUSDT")
    if applies.get("benchmark_is_not_a_candidate") is not True:
        fail("the runbook does not record that the benchmark is not a candidate")
    if applies.get("benchmark_is_counted_as_an_exposed_asset") is not True:
        fail("the runbook does not count the benchmark as an exposed asset")

    # 3. the window bounds ---------------------------------------------------
    window = freeze.get("confirmatory_window") or {}
    bounds = bindings.get("bounds") or {}
    if applies.get("window_start_utc") != window.get("opens_utc"):
        fail("the runbook names another confirmatory-window start than the freeze")
    if applies.get("window_end_utc") != window.get("earliest_possible_end_utc"):
        fail("the runbook names another earliest window end than the freeze")
    if applies.get("minimum_closed_hourly_candles") != window.get("min_hours"):
        fail("the runbook names another minimum of hours than the freeze")
    for key, expected in (
        ("window_start_utc", window.get("opens_utc")),
        ("window_end_utc", window.get("earliest_possible_end_utc")),
        ("minimum_closed_hourly_candles", window.get("min_hours")),
    ):
        if bounds.get(key) != expected:
            fail(f"the runbook's bounds block names another {key}")
    if bounds.get("development_cutoff_utc") != (spec_v6.get("holdout") or {}).get(
        "development_cutoff_utc"
    ):
        fail("the runbook's bounds block names another development cutoff")
    gates: List[Tuple[str, str]] = []
    for version, relative, key in GATE_OWNERS:
        owner = read_json(root / relative)
        owner_bounds = _window_bounds(owner, key)
        if not owner_bounds["earliest_possible_end_utc"]:
            fail(f"the {version} candidate freeze carries no earliest window end")
            continue
        gates.append((version, owner_bounds["earliest_possible_end_utc"]))
    if window.get("earliest_possible_end_utc"):
        gates.append(("v6", str(window["earliest_possible_end_utc"])))
    if gates:
        expected_gate = max(end for _, end in gates)
        computed["evaluation_may_not_start_before_utc"] = expected_gate
        if bounds.get("evaluation_may_not_start_before_utc") != expected_gate:
            fail(
                "the effective v6 evaluation start is "
                f"{bounds.get('evaluation_may_not_start_before_utc')}, but the later of the v2, "
                f"v3, v4 and v5 gates and the v6 window's own earliest end is {expected_gate}"
            )

    # 4. the decision rule ---------------------------------------------------
    decision = bindings.get("decision_rule") or {}
    selection = spec_v1.get("selection") or {}
    min_trades = int(selection.get("min_trades_total"))
    expected_criteria = [
        "net_total_return > 0 at baseline costs (1x) over the confirmatory window",
        "net_total_return > 0 at 2x costs over the confirmatory window",
        f"closed_trades >= {min_trades} over the confirmatory window",
        "the evaluated parameters are byte-identical to the frozen v6 candidate manifest entry",
    ]
    if list(decision.get("criteria") or []) != expected_criteria:
        fail("the runbook's criteria are not the criteria of the unchanged v1 selection rule")
    if decision.get("criterion_count") != 1:
        fail("the runbook does not record exactly one confirmatory criterion")
    if decision.get("no_secondary_criterion_is_applied") is not True:
        fail("the runbook does not forbid a secondary criterion")
    if list(decision.get("status_vocabulary") or []) != list(
        (spec_v1.get("status") or {}).get("economic") or []
    ):
        fail("the runbook's status vocabulary is not the v1 status vocabulary")
    if decision.get("status_vocabulary_is_not_extended") is not True:
        fail("the runbook does not forbid extending the status vocabulary")
    evaluation = bindings.get("evaluation_rule") or {}
    if list(evaluation.get("cost_scenarios") or []) != list(
        (spec_v1.get("costs") or {}).get("scenarios") or []
    ):
        fail("the runbook's cost scenarios are not the v1 cost scenarios")
    inherited_digest = sha256_bytes(
        canonical({block: spec_v1.get(block) for block in INHERITED_V1_BLOCKS}).encode("utf-8")
    )
    computed["recomputed_inherited_blocks_digest"] = inherited_digest
    if evaluation.get("inherited_rules_blocks_digest") != inherited_digest:
        fail("the inherited rules digest does not recompute from the v1 specification")
    if evaluation.get("no_retuning_reranking_or_grid_extension_on_window") is not True:
        fail("the runbook does not forbid re-tuning on the window")
    if evaluation.get("evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry") is not True:
        fail("the runbook does not bind the evaluated parameters to the frozen manifest entry")

    # 5. the immutable anchors ------------------------------------------------
    anchors = bindings.get("immutable_artifact_anchors") or {}
    if not anchors:
        fail("the runbook records no immutable artifact anchors")
    for label, entries in anchors.items():
        for relative, digest in (entries or {}).items():
            path = root / relative
            if not path.exists():
                fail(f"the anchored artifact {relative} is missing")
                continue
            if digest != sha256_file(path):
                fail(f"the anchored artifact {relative} has changed since the runbook was written")

    # 6. the code identity ----------------------------------------------------
    identity = bindings.get("code_identity") or {}
    source_digest = canonical_source_digest(root)
    computed["canonical_hashed_set_digest"] = source_digest
    if source_digest is None:
        fail("the hashed source set is missing, so its digest cannot be recomputed")
    elif identity.get("hashed_set_digest") != source_digest:
        fail(
            "the runbook records another canonical tree digest, recomputed "
            f"{source_digest}"
        )
    if identity.get("authorized_ordered_code_hash") != authorization.get("code_hash"):
        fail("the runbook does not record the authorized code hash of record")
    if identity.get("hashed_set_root") != "src/breakout_research":
        fail("the runbook does not name the hashed set root")
    if str(identity.get("execution_path_root") or "").startswith("src/breakout_research/"):
        fail("the confirmatory execution path lives inside the hashed set")

    # 7. the write order ------------------------------------------------------
    procedure = runbook.get("operator_procedure") or {}
    write_order = procedure.get("write_order") or []
    if len(write_order) != 8:
        fail(f"the write order names {len(write_order)} output paths, not eight")
    orders = [entry.get("order") for entry in write_order]
    if orders != list(range(1, len(write_order) + 1)):
        fail("the write order is not numbered consecutively from one")
    for entry in write_order:
        path = str(entry.get("path") or "")
        if not path:
            fail("a write-order entry names no path")
            continue
        if path in FROZEN_RESULT_PATHS:
            fail(f"the v6 confirmatory output path {path} collides with a frozen path")
        if "v6" not in path:
            fail(f"the v6 confirmatory output path {path} is not in the v6 namespace")
    if not procedure.get("ordered_steps"):
        fail("the runbook records no ordered procedure")
    if not runbook.get("failure_decision_table"):
        fail("the runbook records no failure decision table")
    if not runbook.get("prohibitions"):
        fail("the runbook records no prohibitions")
    acceptance = runbook.get("acceptance_checks") or {}
    if not acceptance.get("checks"):
        fail("the runbook records no acceptance checks")
    if not acceptance.get("verification_commands"):
        fail("the runbook records no verification commands")

    # 8. the runbook authorizes nothing ---------------------------------------
    for flag in (
        "authorizes_a_candle_read",
        "authorizes_an_evaluation",
        "authorizes_a_second_run",
    ):
        if runbook.get(flag) is not False:
            fail(f"the runbook does not record {flag} as false")
    for relative in V6_CONFIRMATORY_RUN_ARTIFACTS:
        if (root / relative).exists():
            fail(
                f"the v6 confirmatory artifact {relative} exists, but the v6 confirmatory chain "
                "has not run: the runbook authorizes no run"
            )

    return {
        "ok": not failures,
        "runbook_path": RUNBOOK_RELATIVE,
        "manifest_hash": runbook.get("manifest_hash"),
        "recomputed_manifest_hash": runbook_hash,
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

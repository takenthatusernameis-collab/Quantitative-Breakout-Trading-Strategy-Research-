#!/usr/bin/env python3
"""Build the preregistered v2 selection authorization 1.

This producer writes ``configs/research_v2_selection_authorization_1.json``: the
versioned, hash-bound artifact that authorizes **one** bounded v2 selection
grid run over the frozen candidate set.

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself is performed by a later session, through the
execution path in ``src/v2_campaign`` that this artifact names and whose
canonical source digest it binds.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v2_selection_authorization_1.py            # write the artifact
    python3 scripts/build_v2_selection_authorization_1.py --force    # rewrite it
    python3 scripts/build_v2_selection_authorization_1.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_selection_authorization_1.json"

#: The instant at which this authorization is created. It is pinned here so
#: that the artifact is byte-reproducible; it must not be moved once the
#: artifact has been committed.
CREATED_UTC = "2026-10-20T00:10:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source trees the run identity binds.
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_campaign"

#: The v2 artifacts the authorization is bound to.
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v2.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
AMENDMENT_RELATIVE = "configs/research_v2_execution_amendment_1.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"

#: The v2 output paths, as recorded by execution amendment 1.
V2_OUTPUT_PATHS = (
    "shards_dir",
    "ledger",
    "results_manifest",
    "results_stream",
    "checkpoint",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def canonical_source_digest(root: Path) -> str:
    """The portable identity of the ``*.py`` tree under ``root``.

    This is the ``canonical_source_digest_v1`` rule of BRAIN-009: a sha256
    over the POSIX relative path and the content digest of every ``*.py`` file
    under the root, in ascending path order. It does not depend on the
    directory enumeration order of the checkout.
    """
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def run_code_identity(hashed_set: str, execution_path: str) -> str:
    """The composite, portable identity of one v2 run."""
    payload = {
        "algorithm": "canonical_source_digest_v1",
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
    }
    return sha256_bytes(canonical(payload).encode("utf-8"))


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _execution_path_modules(repo_root: Path) -> List[str]:
    root = repo_root / EXECUTION_PATH_ROOT
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the selection authorization from the hash-bound artifacts."""
    root = Path(repo_root)
    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_MANIFEST_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    config_manifest = _load(root / CONFIG_MANIFEST_RELATIVE)
    campaign_authorization = _load(root / AUTHORIZATION_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)

    scope_block = freeze["frozen_candidate_set"]
    constituents = list(scope_block["constituents"])
    binance_pairs = list(scope_block["binance_pairs"])
    if len(constituents) != len(binance_pairs):
        raise SystemExit("the frozen candidate set is inconsistent")

    bounds = dict(dig(amendment, "v2_selection_authorization.bounds") or {})
    paths = dict(dig(amendment, "v2_selection_authorization.paths") or {})
    for key in V2_OUTPUT_PATHS:
        if not paths.get(key):
            raise SystemExit(f"execution amendment 1 records no {key}")

    selection_block = spec_v1["selection"]
    if canonical(selection_block) != canonical(spec_v2["selection"]):
        raise SystemExit(
            "the selection block of configs/research_v2.json is not byte-equal to the "
            "selection block of configs/research_v1.json"
        )
    selection_digest = sha256_bytes(canonical(selection_block).encode("utf-8"))

    hashed_set_digest = canonical_source_digest(root / HASHED_SET_ROOT)
    execution_path_digest = canonical_source_digest(root / EXECUTION_PATH_ROOT)
    recorded_canonical = dig(code_hash_amendment, "code_hash_constraint.canonical_source_digest")
    if recorded_canonical != hashed_set_digest:
        raise SystemExit(
            "the hashed source tree does not match the canonical digest recorded by the "
            "code-hash amendment"
        )

    fold_count = len(spec_v1["folds"]["window_fractions"])
    cost_count = len(spec_v1["costs"]["scenarios"])
    config_units = len(constituents) * int(bounds["max_configs_per_asset"])
    execution_units = config_units * fold_count * cost_count

    document: Dict[str, Any] = {
        "artifact": "v2_selection_authorization",
        "artifact_version": "v2-selection-authorization-1",
        "version": 1,
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "authorization_status": "PREREGISTERED_SELECTION_AUTHORIZATION_ONE_BOUNDED_RUN",
        "specification_purpose": (
            "Authorize exactly one bounded v2 selection grid run over the frozen candidate "
            "set, under the unchanged v1 selection rule, on development data only, writing "
            "only to the v2 paths. This artifact names the execution path, the bounds, the "
            "stopping conditions, the rollback rule and the falsifiers of that run. Building "
            "it executes nothing: no grid is run, no candle is read, no result exists."
        ),
        "design_basis": {
            "brainstorming_item": "BRAIN-008",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-008 sections 1, 3, 4 and 6",
            "prerequisites_delivered": [
                "P1 configs/research_v2.json",
                "P2 research/universe_manifest_v2.json",
                "P3 research/data_manifest_v2.json",
                "P4 configs/research_v2_execution.json",
                "the v2 candidate manifest freeze",
                "the v2 execution amendment 1",
                "the v2 code-hash amendment 1",
            ],
            "execution_path_outside_hashed_set": (
                "The v2 execution code lives in src/v2_campaign, outside the hashed source set "
                "src/breakout_research. It imports the v1 engine unchanged; it adds, edits and "
                "removes no file under src/breakout_research, so the v1 campaign authorization "
                "and the v2 identity tuples stay valid."
            ),
        },
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": "v2-selection-20261019",
            "campaign_id": "v2-campaign",
            "run_phase": "selection_grid",
            "authorization_note": (
                "The run is recorded in the ledger before the first result is written. The "
                "authorization permits one logical run: a completed run is never re-run, and an "
                "interrupted run is resumed from the verified shards, with the number of resumes "
                "bounded by max_retries_on_technical_failure. A boundary abort rolls the ledger "
                "back and releases the run, so that a defect can be fixed and the run started "
                "again."
            ),
            "resume_semantics": {
                "one_logical_run": True,
                "completed_run_is_never_re_run": True,
                "interrupted_run_is_resumed": True,
                "resumes_bounded_by": "max_retries_on_technical_failure",
                "resume_source_of_truth": "the verified shards under research/shards_v2",
                "result_stream_is_a_projection_of_the_shards": True,
                "note": (
                    "A process that is killed leaves the run in the ledger as RUNNING. The next "
                    "process resumes it from the verified shards instead of starting a second "
                    "run, so an interruption cannot burn the single authorized run."
                ),
            },
            "scope": {
                "constituents": constituents,
                "binance_pairs": binance_pairs,
                "count": len(constituents),
                "candidate_manifest_path": FREEZE_RELATIVE,
                "bound_to_universe_hash": universe["manifest_hash"],
                "bound_to_data_hash": data_manifest["manifest_hash"],
                "bound_to_freeze_hash": freeze["manifest_hash"],
                "membership_rule": (
                    "Exactly the constituents marked validated in "
                    "research/universe_manifest_v2.json. The run may not re-rank, widen or "
                    "narrow the frozen set."
                ),
                "widening_by_reranking_forbidden": True,
                "excluded_assets_stay_excluded": True,
                "excluded_after_validation": dict(scope_block.get("excluded_after_validation") or {}),
                "excluded_by_rule": dict(scope_block.get("excluded_by_rule") or {}),
            },
            "execution_path": {
                "package": EXECUTION_PATH_ROOT,
                "entry_point": f"{EXECUTION_PATH_ROOT}/runner.py:run_selection",
                "modules": _execution_path_modules(root),
                "engine_imports": [
                    "breakout_research.backtest.backtester.run_fold_backtest",
                    "breakout_research.backtest.shards.ResultStore",
                    "breakout_research.backtest.shards.compute_experiment_id",
                    "breakout_research.backtest.checkpoint.CheckpointManager",
                    "breakout_research.baselines.load_verified_candles",
                    "breakout_research.baselines.buyhold_baseline",
                    "breakout_research.selection.select_candidates",
                    "breakout_research.config.get_configurations",
                ],
                "engine_is_reused_unchanged": True,
                "hashed_set_untouched": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "note": (
                    "The execution path reuses the v1 indicators, signals, backtester, "
                    "verified candle loader, shard writer, checkpoint manager and candidate "
                    "selector without modification. It adds no parameter, threshold, fold, "
                    "cost or selection criterion of its own."
                ),
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "algorithm_description": (
                    "sha256 over the concatenation, for every *.py file under the root in "
                    "ascending POSIX relative-path order, of the relative path, a newline, the "
                    "sha256 hex digest of the file bytes, and a newline."
                ),
                "portable": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": hashed_set_digest,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": execution_path_digest,
                "run_code_identity": run_code_identity(hashed_set_digest, execution_path_digest),
                "authorized_code_hash": campaign_authorization["code_hash"],
                "authorized_code_hash_status": "RETAINED_AS_VALUE_OF_RECORD",
                "ordered_code_hash_is_portable": False,
                "note": (
                    "The identity of a v2 run is the composite of the canonical digest of the "
                    "hashed v1 engine and the canonical digest of the v2 execution path. The "
                    "checkout-dependent ordered digest compute_code_hash() stays the authorized "
                    "value of record and is never used as an identity."
                ),
            },
            "data_boundary": {
                "development_data_only": True,
                "candles_before_utc": dig(freeze, "data_boundary.confirmatory_window_start_utc"),
                "candles_before_utc_rule": (
                    "Only candles that close at or before the confirmatory-window start "
                    "recorded by the candidate freeze may be read during the selection run. A "
                    "dataset that reaches into the confirmatory window is refused before it is "
                    "read."
                ),
                "confirmatory_window_never_read_during_selection": True,
                "v1_holdout_never_reused": True,
                "v1_cycle0_units_never_mixed": True,
                "v1_cycle0_units": 497664,
                "holdout_exposed_count_stays_zero_during_selection": True,
                "holdout_position_fold_never_evaluated_during_selection": True,
                "provider_requests": 0,
                "provider_requests_note": (
                    "The run reads the immutable local datasets that research/data_manifest_v2.json "
                    "already binds and verifies. It performs no provider request, so it cannot "
                    "re-retrieve, re-time or refresh any market data."
                ),
            },
            "selection_rule": {
                "unchanged_from_v1": True,
                "reference": SPEC_V1_RELATIVE,
                "block": "selection",
                "selection_block_sha256": selection_digest,
                "v2_block_is_byte_equal": True,
                "max_candidates_per_asset": selection_block["max_candidates_per_asset"],
                "selector": "breakout_research.selection.select_candidates",
                "grid_reference": (
                    "the strategy_grid of configs/research_v1.json, inherited unchanged by "
                    "configs/research_v2.json: 2,304 configurations per asset"
                ),
                "grid_configuration_count": len(config_manifest["configurations"]),
                "no_criterion_may_be_added_tightened_or_loosened": True,
            },
            "paths": {
                **{key: paths[key] for key in V2_OUTPUT_PATHS},
                "never_use_v1_paths": True,
                "v1_paths_forbidden": list(paths.get("v1_paths_forbidden") or []),
            },
            "bounds": {
                "max_assets": bounds["max_assets"],
                "max_configs_per_asset": bounds["max_configs_per_asset"],
                "max_total_config_units": bounds["max_total_config_units"],
                "attempts": bounds["attempts"],
                "max_retries_on_technical_failure": bounds.get("max_retries_on_technical_failure", 3),
                "planned_config_units": config_units,
                "planned_execution_units": execution_units,
                "planned_execution_units_note": (
                    "The bounded run holds 18 assets x 2,304 configurations x 4 validation folds "
                    "x 3 cost scenarios execution units. The bound that the authorization "
                    "enforces is max_total_config_units, the number of asset-configuration "
                    "pairs; the fold and cost multipliers follow the inherited, unchanged fold "
                    "and cost blocks."
                ),
                "resource_limits": bounds.get("resource_limits", ""),
            },
            "stopping_conditions": [
                "Normal completion within the recorded bounds",
                "No candidate survives the unchanged v1 selection rule -> report the outcome (do not hide it)",
                "Any boundary violation -> abort and rollback",
                "A technical interruption -> keep the verified shards and resume the same run",
            ],
            "rollback_rule": (
                "Do not write to v1 artifacts; remove any newly created v2 artifact if the "
                "execution is aborted; do not alter research_state/checkpoint.json or the v1 "
                "campaign state."
            ),
            "falsifiers": [
                "Any modification to src/breakout_research/ (would change the code hash)",
                "Reading any candle in the v2 confirmatory window during selection",
                "Writing into v1 shards, ledger, tallies or result streams",
                "Reusing the v1 holdout",
                "Mixing v1 cycle-0 units with v2 results",
                "Widening or narrowing the frozen candidate set",
                "A second run attempt under this authorization",
            ],
            "no_execution_in_this_session": True,
        },
        "not_authorized": {
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "v1_reauthorization_authorized": False,
            "source_tree_change_authorized": False,
            "statement": (
                "This artifact authorizes one bounded selection run and nothing else. It does "
                "not authorize a confirmatory-window evaluation, a candle fetch, a change to "
                "the hashed source set or a v1 re-authorization. The selected-configuration "
                "manifest that the confirmatory window requires must be committed and "
                "hash-bound before the first confirmatory-window candle is read."
            ),
        },
        "related_artifacts": {
            "v2_specification": {
                "path": "configs/research_v2.json",
                "specification_hash": spec_v2["specification_hash"],
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "v2_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze["manifest_hash"],
                "frozen_at_utc": freeze["candidate_freeze_timestamp_utc"],
            },
            "v2_universe_manifest": {
                "path": UNIVERSE_MANIFEST_RELATIVE,
                "manifest_hash": universe["manifest_hash"],
            },
            "v2_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest["manifest_hash"],
            },
            "v2_execution_protocol": {
                "path": "configs/research_v2_execution.json",
                "specification_hash": dig(amendment, "amends.specification_hash"),
            },
            "v2_execution_amendment_1": {
                "path": AMENDMENT_RELATIVE,
                "manifest_hash": amendment["manifest_hash"],
            },
            "v2_code_hash_amendment_1": {
                "path": CODE_HASH_AMENDMENT_RELATIVE,
                "manifest_hash": code_hash_amendment["manifest_hash"],
                "canonical_source_digest": recorded_canonical,
            },
            "v1_campaign_authorization": {
                "path": AUTHORIZATION_RELATIVE,
                "code_hash": campaign_authorization["code_hash"],
                "authorized": campaign_authorization.get("authorized"),
                "note": (
                    "The functional field of the authorization is recorded, not the digest of "
                    "its bytes: the controller refreshes the authorized_at_utc timestamp, so "
                    "the file digest changes without the authorization changing."
                ),
            },
            "configuration_manifest": {
                "path": CONFIG_MANIFEST_RELATIVE,
                "total_configurations": config_manifest.get("total_configurations"),
            },
        },
        "residual_limitations": [
            {
                "id": "RL2",
                "location": "the v2 selection run's result volume",
                "limitation": (
                    "The bounded run writes 497,664 execution units. At the v1 record size this "
                    "is of the order of 1.3 GB of shards and of the order of 300 MB of result "
                    "stream. The v1 shards are bounded to 4 MiB per file and were pushed as many "
                    "small files; the v1 result stream was a single file of 50 MB that the "
                    "campaign could not push as one blob."
                ),
                "consequence": (
                    "The shards under research/shards_v2 are the authoritative record set and "
                    "are committed as bounded files of at most 4 MiB each, as the v1 campaign "
                    "did. The single-file result stream research/results_v2.jsonl is expected "
                    "to exceed the 100 MB per-file push limit and is therefore not committed as "
                    "one file: it is a projection of the verified shards and is regenerated "
                    "from them. The ledger, the results manifest and the checkpoint are small "
                    "and are committed. The v1 shards, ledger and result stream stay untouched "
                    "either way."
                ),
            }
        ],
        "verification": {
            "verifier_script": "scripts/verify_research_v2_selection_authorization_1.py",
            "tests_module": "tests/test_research_v2_selection_authorization_1.py",
            "verify_command": "python3 scripts/verify_research_v2_selection_authorization_1.py",
            "execution_path_tests": "tests/test_v2_campaign_execution_path.py",
        },
        "durability": {
            "commit": None,
            "pushed": False,
            "note": (
                "Becomes durable when the commit that carries this artifact exists. The "
                "artifact is not rewritten after that commit, because its manifest_hash must "
                "not change."
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "following the pattern of the other v2 artifacts."
            ),
        },
    }

    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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

    target = repo_root / "configs" / "research_v2_selection_authorization_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

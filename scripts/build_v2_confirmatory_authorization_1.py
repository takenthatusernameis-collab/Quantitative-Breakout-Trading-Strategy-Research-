#!/usr/bin/env python3
"""Build the versioned authorization of the v2 confirmatory evaluation.

The authorization permits **at most one** logical confirmatory run over the 14
selected configurations of ``research/v2_selected_configurations_manifest.json``
and records everything the run is bound to (decision D-7 of BRAIN-011):

* the **scope** -- exactly the 14 selected configurations, bound to the
  selected-configurations manifest; the 4 assets without a candidate stay out
  of scope and the scope may not be widened, narrowed or re-ranked;
* the **window** -- its start, the 2,160 closed hourly candles it needs, the
  earliest instant at which it can end, and the single-use rule;
* the **data boundary** -- one retrieval, after the metadata-only readiness
  test, every read counted in ``holdout_exposed_count``, and the window
  manifest that records the retrieved data;
* the **output layout** -- the new v2 confirmatory paths, with the v1 paths
  and the v2 *selection* paths explicitly forbidden;
* the **code identity** -- the composite canonical digest of the hashed v1
  engine and of the confirmatory execution path (BRAIN-009's portable rule);
* the **attempt budget** -- one attempt, at most three technical retries
  before the first payload read, and a resume of the same run afterwards;
* the **preconditions**, the **stopping conditions**, the **falsifiers** and
  the **rollback**.

The artifact authorizes a run; it does not perform one. No candle may be read
before the window exists, and the run itself is a later, separately
authorized session.

The script is deterministic: every field is derived from artifacts that are
already hash-bound, so re-running it reproduces the same bytes. It never
fetches anything, never reads a candle and never runs an evaluation.

Usage::

    python3 scripts/build_v2_confirmatory_authorization_1.py            # write
    python3 scripts/build_v2_confirmatory_authorization_1.py --force    # rewrite
    python3 scripts/build_v2_confirmatory_authorization_1.py --print    # print only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_confirmatory_authorization_1.json"

#: The instant at which the authorization was preregistered. Pinned so the
#: artifact is byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T11:00:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_confirmatory"

PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
AMENDMENT_RELATIVE = "configs/research_v2_confirmatory_protocol_amendment_1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v2_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v2_selection_authorization_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v2.json"
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"
CAMPAIGN_AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The v1 paths the confirmatory evaluation may never write.
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

#: The v2 *selection* outputs: never tallied with, extended by or written over.
V2_SELECTION_PATHS_FORBIDDEN = (
    "research/shards_v2/",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)

#: The output layout of the confirmatory evaluation.
CONFIRMATORY_PATHS = {
    "shards_dir": "research/shards_v2_confirmatory",
    "ledger": "research/ledger_v2_confirmatory.json",
    "results_manifest": "research/results_manifest_v2_confirmatory.json",
    "results_stream": "research/results_v2_confirmatory.jsonl",
    "checkpoint": "research_state/checkpoint_v2_confirmatory.json",
    "window_manifest": "research/v2_confirmatory_window_manifest.json",
    "report": "reports/confirmatory_evaluation_v2.json",
    "report_markdown": "reports/confirmatory_report_v2.md",
}

#: The v1 evidence the confirmatory evaluation may not touch.
V1_EVIDENCE_FILES = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

#: The v2 *selection* outputs the confirmatory evaluation may not touch.
V2_SELECTION_OUTPUT_FILES = (
    "research/universe_manifest_v2.json",
    "research/data_manifest_v2.json",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/v2_selected_configurations_manifest.json",
    "research_state/checkpoint_v2.json",
)

#: The rule that fixes the evaluated window's length. The evaluated window is
#: exactly the first ``minimum_closed_hourly_candles`` closed hourly candles at
#: or after the window start, so its length does not depend on when the run
#: happens and the run has no discretionary choice of window length.
EVALUATION_WINDOW_RULE = (
    "The evaluated window is exactly the first minimum_closed_hourly_candles closed hourly "
    "candles at or after the window start, so it ends at the earliest instant the frozen "
    "boundary allows. The evaluated window's length does not depend on when the run happens, "
    "and the window may not be extended, shortened or re-based at run time."
)


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the authorization document from the hash-bound artifacts."""
    root = Path(repo_root)
    protocol = _load(root / PROTOCOL_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)
    selection_authorization = _load(root / SELECTION_AUTHORIZATION_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)
    campaign_authorization = _load(root / CAMPAIGN_AUTHORIZATION_RELATIVE)

    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_hashed_set = canonical_source_digest(root / HASHED_SET_ROOT)
    if recorded_canonical != live_hashed_set:
        raise SystemExit(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_hashed_set}; refusing to "
            "authorize a run against a modified source tree"
        )
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

    selections = selected.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    config_ids = {
        asset: str((selections.get(asset) or {}).get("config_id"))
        for asset in assets_with_candidate
    }

    window_start = (freeze.get("data_boundary") or {}).get("confirmatory_window_start_utc")
    earliest_end = (freeze.get("data_boundary") or {}).get(
        "earliest_possible_confirmatory_window_end_utc"
    )
    minimum_hours = (freeze.get("data_boundary") or {}).get("min_confirmatory_window_hours")
    if not window_start or not earliest_end or not minimum_hours:
        raise SystemExit("the frozen candidate freeze carries no confirmatory-window boundary")

    anchors: Dict[str, Dict[str, str]] = {}
    for group, files in (
        ("v1_evidence", V1_EVIDENCE_FILES),
        ("v2_selection_outputs", V2_SELECTION_OUTPUT_FILES),
    ):
        entries: Dict[str, str] = {}
        for relative in files:
            target = root / relative
            if not target.exists():
                raise SystemExit(f"the frozen artifact {relative} is missing")
            entries[relative] = sha256_file(target)
        anchors[group] = entries

    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_authorization",
        "artifact_version": "v2-confirmatory-authorization-1",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "authorization_status": "AUTHORIZED_FOR_AT_MOST_ONE_LOGICAL_RUN",
        "specification_purpose": (
            "Authorize at most one logical confirmatory evaluation of the 14 selected "
            "configurations on the v2 confirmatory window, and record the scope, the window, "
            "the data boundary, the output layout, the code identity, the attempt budget, "
            "the preconditions, the stopping conditions, the falsifiers and the rollback. "
            "No evaluation may run before the window exists."
        ),
        "authorized_run": {
            "authorized": True,
            "max_runs": 1,
            "run_id": "v2-confirmatory-20260117",
            "campaign_id": "v2-confirmatory-campaign",
            "run_phase": "confirmatory_window_evaluation",
            "scope": {
                "assets": assets_with_candidate,
                "config_ids": config_ids,
                "count": len(assets_with_candidate),
                "out_of_scope_assets_without_candidate": assets_without_candidate,
                "bound_to_selected_configurations_hash": selected.get("manifest_hash"),
                "bound_to_selection_authorization_hash": selection_authorization.get(
                    "manifest_hash"
                ),
                "bound_to_data_manifest_hash": data_manifest.get("manifest_hash"),
                "scope_may_not_be_widened_narrowed_or_reranked": True,
                "out_of_scope_assets_are_reported_not_dropped": True,
                "data_scope_rule": (
                    "the data scope is the 14 in-scope assets; the benchmark asset is added to "
                    "the data scope only when a selected configuration's trend filter needs it, "
                    "and the benchmark is then counted as an exposed asset like every other"
                ),
            },
            "code_identity": {
                "algorithm": "canonical_source_digest_v1",
                "portable": True,
                "hashed_set_root": HASHED_SET_ROOT,
                "hashed_set_digest": live_hashed_set,
                "execution_path_root": EXECUTION_PATH_ROOT,
                "execution_path_digest": live_execution_path,
                "run_code_identity": run_code_identity,
                "authorized_ordered_code_hash": campaign_authorization.get("code_hash"),
                "note": (
                    "The identity of a confirmatory run is the composite of the canonical "
                    "digest of the hashed v1 engine and the canonical digest of the "
                    "confirmatory execution path. The checkout-dependent ordered digest "
                    "compute_code_hash() is an environment fact and is never used as an "
                    "identity."
                ),
            },
            "window": {
                "window_start_utc": window_start,
                "minimum_closed_hourly_candles": int(minimum_hours),
                "earliest_possible_end_utc": earliest_end,
                "evaluation_window_rule": EVALUATION_WINDOW_RULE,
                "single_use": True,
                "must_not_overlap_v1_holdout": True,
                "never_reused_from_v1": True,
                "never_used_for_selection_ranking_or_retuning": True,
            },
            "data_boundary": {
                "readiness_test": (
                    "a bounded metadata-only probe of the provider's server time and the "
                    "spot exchange status of the in-scope pairs; it fetches no candle and "
                    "does not increment holdout_exposed_count"
                ),
                "retrieval_happens_once_after_the_readiness_test_passes": True,
                "every_read_counted_in_holdout_exposed_count": True,
                "exposure_counter_is_monotonic": True,
                "exposure_event_identity": "(run_id, asset, window bounds)",
                "a_continuation_of_the_same_event_does_not_increment_the_counter": True,
                "a_read_under_different_bounds_or_outside_the_scope_is_refused": True,
                "window_manifest_path": CONFIRMATORY_PATHS["window_manifest"],
                "window_manifest_records": [
                    "window bounds",
                    "retrieval timestamp",
                    "per-asset dataset hashes",
                    "closed-candle count per asset",
                    "coverage gaps",
                    "exposure events",
                    "the readiness record",
                ],
                "v2_data_manifest_is_extended_by_reference_and_never_edited": True,
                "v1_holdout_never_reused": True,
            },
            "paths": dict(CONFIRMATORY_PATHS),
            "forbidden_paths": list(V1_PATHS_FORBIDDEN) + list(V2_SELECTION_PATHS_FORBIDDEN),
            "immutable_artifact_anchors": anchors,
            "v1_paths_forbidden": True,
            "v2_selection_paths_forbidden": True,
            "v2_selection_results_are_never_tallied_with": True,
            "bounds": {
                "max_assets": len(assets_with_candidate),
                "max_configurations": len(assets_with_candidate),
                "max_cost_scenarios": len(spec_v1["costs"]["scenarios"]),
                "attempts": 1,
                "max_retries_on_technical_failure": int(spec_v1["checkpointing"]["max_retries"]),
                "retries_before_the_first_payload_read": int(
                    spec_v1["checkpointing"]["max_retries"]
                ),
            },
            "evaluation_rule": {
                "unchanged_v1_evaluation_metric": True,
                "unchanged_cost_scenarios": True,
                "cost_scenarios": [float(value) for value in spec_v1["costs"]["scenarios"]],
                "no_retuning_reranking_or_grid_extension_on_window": True,
                "evaluated_parameters_are_byte_identical_to_the_frozen_manifest_entry": True,
                "selection_rule_reference": "configs/research_v1.json#selection",
            },
            "criterion_precedence": {
                "authoritative_source": "configs/research_v2.json#holdout.promotion_rule",
                "secondary_source": (
                    "configs/research_v2_confirmatory_protocol.json#reporting_and_falsifiers"
                ),
                "secondary_field": "baseline_comparison",
                "amendment_path": AMENDMENT_RELATIVE,
                "amendment_manifest_hash": amendment.get("manifest_hash"),
            },
            "protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "amendment": {
                "path": AMENDMENT_RELATIVE,
                "manifest_hash": amendment.get("manifest_hash"),
            },
            "preconditions": [
                "the authorization, the confirmatory protocol and the protocol amendment are committed",
                "the metadata-only readiness test has passed and its record is in the window manifest",
                "holdout_exposed_count is 0, or the run is a resume of the same exposure event",
                "the live code identity equals the recorded code identity",
                "the evaluation scope equals the frozen selected-configurations manifest",
                "the v1 artifacts and the v2 selection outputs are byte-unchanged",
            ],
            "stopping_conditions": [
                "the run stops when every in-scope asset has been evaluated",
                "the run stops at the first boundary violation, rolls back and releases the attempt",
                "the run stops when the window is spent: a second read of the window is refused",
                "an inconclusive outcome is reported, never hidden",
                "if no configuration survives the preregistered promotion rule, that null result is reported",
            ],
            "falsifiers": [
                "the evaluated parameters differ from the frozen candidate manifest entry",
                "the grid is extended, re-ranked or re-tuned on the window",
                "a candle inside the window is read more than once",
                "holdout_exposed_count is incremented outside a confirmatory read",
                "the exposure counter is reset",
                "the v1 holdout is re-opened or the v2 selection outputs are tallied with",
                "an asset of the frozen scope is omitted from the report",
            ],
            "rollback": {
                "before_the_first_payload_read": (
                    "an abort rolls back every artifact the run created and leaves "
                    "holdout_exposed_count = 0, so the attempt is released"
                ),
                "after_a_payload_read": (
                    "an abort leaves the exposure in place: the run is recorded as "
                    "EXPOSED_ABORTED, the window is spent, and the report must state that "
                    "the window was consumed without a completed evaluation"
                ),
                "resume": (
                    "an interrupted run is resumed from the verified shards and the already "
                    "retrieved, hash-verified datasets; the number of resumes is bounded by "
                    "max_retries_on_technical_failure"
                ),
            },
        },
        "authorizes_evaluation_before_the_window_exists": False,
        "authorizes_a_candle_read_before_the_window_exists": False,
        "related_artifacts": {
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "confirmatory_protocol_amendment_1": {
                "path": AMENDMENT_RELATIVE,
                "manifest_hash": amendment.get("manifest_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": selected.get("manifest_hash"),
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_authorization.get("manifest_hash"),
            },
            "v2_candidate_freeze": {
                "path": FREEZE_RELATIVE,
                "manifest_hash": freeze.get("manifest_hash"),
            },
            "v2_specification": {
                "path": SPEC_V2_RELATIVE,
                "specification_hash": spec_v2.get("specification_hash"),
            },
            "v2_data_manifest": {
                "path": DATA_MANIFEST_RELATIVE,
                "manifest_hash": data_manifest.get("manifest_hash"),
            },
        },
        "durability": {
            "rule": (
                "The authorization takes effect when this artifact is committed. No "
                "confirmatory-window candle may be read and no evaluation may run before "
                "the commit that carries this artifact exists."
            ),
            "authorization_commit": None,
            "authorization_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v2_confirmatory_authorization_1.py",
            "verify_command": "python3 scripts/verify_v2_confirmatory_path.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, so the document does not hash itself into a cycle."
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

    target = repo_root / "configs" / "research_v2_confirmatory_authorization_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

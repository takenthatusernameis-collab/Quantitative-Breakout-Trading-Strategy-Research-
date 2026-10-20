#!/usr/bin/env python3
"""Build the preregistered v3 confirmatory-evaluation protocol.

The protocol is a one-shot, hash-bound design record of how the four published
v3 candidates of ``research/v3_selected_configurations_manifest.json`` will be
evaluated on the v3 confirmatory window once that window exists:

* the **evaluation scope** -- exactly the four published candidates, bound to
  the selected-configurations manifest, the selection authorization, the v3
  specification, the effective v3 data-manifest identity and the v3 universe
  manifest; the two assets without a candidate stay out of scope and are named
  with their reason; the scope may not be widened, narrowed or re-ranked;
* the **window definition** -- the window opens ``2026-10-20T13:00:00Z``, needs
  at least 2,160 closed hourly candles, is single-use, never overlaps the v1
  holdout or the v2 confirmatory window, is never reused from v1 or v2, is
  never used for selection and is never ranked or re-tuned on;
* the **data path** -- the window's asset candles *and* the window's benchmark
  series are retrieved once after the readiness test passes, are hash-verified
  and are index-aligned by UTC candle close; the evaluation fails closed when
  the benchmark is missing, short or misaligned; the 576 ``btc_ema_168``
  configurations per asset are never dropped; every window read is counted in
  ``holdout_exposed_count``;
* the **evaluation rule** -- the unchanged v1 evaluation metric and the
  unchanged cost scenarios, with no re-tuning, re-ranking or grid extension on
  the window;
* the **decision rule** -- exactly **one** confirmatory decision criterion, the
  preregistered v3 promotion rule, copied verbatim from
  ``configs/research_v3.json#holdout.promotion_rule``.  The v2 line needed a
  protocol amendment because two frozen artifacts stated different confirmatory
  decision criteria; the v3 protocol must not repeat that conflict, so the
  document states one criterion and the verifier proves it;
* the **reporting and falsifiers** -- every evaluated asset and candidate is
  reported, including the assets without a candidate, a null result and a
  candidate that fails in the window; the v1/v2 BTC-alignment deviation is
  carried into the final report as a disclosure and is not repaired;
* the **authorization boundary** -- the protocol authorizes no evaluation, no
  window read and no benchmark retrieval; the code-identity rule is the
  canonical digest of BRAIN-009, never the checkout-dependent ordered digest;
  v1 and v2 paths are forbidden and new v3 paths require a new versioned
  amendment.

Every field is derived from artifacts that are already hash-bound, so re-running
the script reproduces the same bytes.  It never fetches anything, never runs an
evaluation and never reads a candle.

Usage::

    python3 scripts/build_v3_confirmatory_protocol.py            # write the artifact
    python3 scripts/build_v3_confirmatory_protocol.py --force    # rewrite it
    python3 scripts/build_v3_confirmatory_protocol.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_confirmatory_protocol.json"

#: The instant at which the protocol was preregistered.  Pinned here so the
#: artifact is byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T19:45:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"

#: The code-hash amendment that records the portable identity of the hashed set.
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"

#: Referenced artifacts.
SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
DATA_MANIFEST_V3_RELATIVE = "research/data_manifest_v3.json"
DATA_MANIFEST_AMENDMENT_1_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
UNIVERSE_V3_RELATIVE = "research/universe_manifest_v3.json"
CANDIDATE_FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
CANDIDATE_FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
CANDIDATE_FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
EXECUTION_PROTOCOL_RELATIVE = "configs/research_v3_execution.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v3_execution_amendment_1.json"
EXECUTION_AMENDMENT_2_RELATIVE = "configs/research_v3_execution_amendment_2.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
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


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def format_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_source_digest(repo_root: Path = REPO_ROOT) -> str:
    """The portable identity of the hashed source tree."""
    base = repo_root / HASHED_SET_ROOT
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the confirmatory-protocol document from the hash-bound artifacts."""
    root = Path(repo_root)
    manifest = _load(root / SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTHORIZATION_RELATIVE)
    spec_v3 = _load(root / SPEC_V3_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_V3_RELATIVE)
    data_amendment = _load(root / DATA_MANIFEST_AMENDMENT_1_RELATIVE)
    universe = _load(root / UNIVERSE_V3_RELATIVE)
    freeze = _load(root / CANDIDATE_FREEZE_RELATIVE)
    freeze_amendment_1 = _load(root / CANDIDATE_FREEZE_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = _load(root / CANDIDATE_FREEZE_AMENDMENT_2_RELATIVE)
    execution = _load(root / EXECUTION_PROTOCOL_RELATIVE)
    execution_amendment_1 = _load(root / EXECUTION_AMENDMENT_1_RELATIVE)
    execution_amendment_2 = _load(root / EXECUTION_AMENDMENT_2_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)

    # BRAIN-009: the identity of the hashed source set is the portable
    # canonical digest; the checkout-dependent ordered digest is never
    # recomputed as an identity, so this artifact is reproducible on any machine.
    code_hash = authorization["code_hash"]
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_canonical = canonical_source_digest(repo_root)
    if recorded_canonical != live_canonical:
        raise SystemExit(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}; "
            "refusing to publish a protocol against a modified source tree"
        )

    # --- evaluation scope -------------------------------------------------
    selections = manifest.get("selections") or {}
    in_scope = [
        {
            "asset": asset,
            "config_id": entry["config_id"],
            "candidate_status": entry.get("candidate_status"),
        }
        for asset, entry in sorted(selections.items())
        if entry.get("selected") is True
    ]
    out_of_scope = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )
    out_of_scope_reasons = {
        asset: selections[asset].get("reason") or selections[asset].get("status")
        for asset in out_of_scope
    }
    effective_data = data_amendment.get("effective_data_manifest") or {}

    evaluation_scope: Dict[str, Any] = {
        "selected_configurations_manifest": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
        "selected_configurations_manifest_hash": manifest["manifest_hash"],
        "selection_authorization_manifest_hash": selection_auth["manifest_hash"],
        "v3_specification_hash": spec_v3["specification_hash"],
        "v3_data_manifest_path": DATA_MANIFEST_V3_RELATIVE,
        "v3_data_manifest_hash": effective_data["effective_data_manifest_hash"],
        "v3_base_data_manifest_hash": effective_data["base_manifest_hash"],
        "v3_universe_manifest_hash": universe["manifest_hash"],
        "in_scope_assets": len(in_scope),
        "in_scope_configurations": in_scope,
        "out_of_scope_assets_without_candidate": out_of_scope,
        "out_of_scope_reasons": out_of_scope_reasons,
        "excluded_assets_stay_excluded": True,
        "scope_may_not_be_widened_narrowed_or_reranked": True,
    }

    # --- window definition ------------------------------------------------
    boundary = freeze.get("data_boundary") or {}
    window_start = str(boundary["confirmatory_window_start_utc"])
    min_hours = int(boundary["min_confirmatory_window_hours"])
    earliest_end = format_iso_utc(
        parse_iso_utc(window_start) + timedelta(hours=min_hours)
    )
    if earliest_end != boundary["earliest_possible_confirmatory_window_end_utc"]:
        raise SystemExit(
            "the frozen earliest possible window end does not follow from the frozen "
            f"window start: recorded {boundary['earliest_possible_confirmatory_window_end_utc']}, "
            f"recomputed {earliest_end}"
        )
    for name, amendment in (
        ("freeze amendment 1", freeze_amendment_1),
        ("freeze amendment 2", freeze_amendment_2),
    ):
        amended = amendment.get("data_boundary") or {}
        if amended.get("confirmatory_window_start_utc") != window_start:
            raise SystemExit(
                f"the {name} moves the confirmatory window to "
                f"{amended.get('confirmatory_window_start_utc')}; the protocol refuses to "
                "preregister a moved window"
            )

    window_definition: Dict[str, Any] = {
        "window_opens_utc": window_start,
        "minimum_closed_hourly_candles": min_hours,
        "earliest_possible_end_utc": earliest_end,
        "window_source": "configs/research_v3_candidate_freeze.json#data_boundary",
        "single_use": True,
        "must_not_overlap_v1_holdout": True,
        "must_not_overlap_v2_confirmatory_window": True,
        "never_reused_from_v1": True,
        "never_reused_from_v2": True,
        "never_used_for_candidate_selection": True,
        "no_ranking_or_retuning_on_window": True,
        "never_populated_with_data_predating_the_candidate_freeze": True,
        "window_moved_by_the_candidate_freeze_amendments": False,
    }

    # --- data path, including the window benchmark ------------------------
    auth_benchmark = (selection_auth.get("authorized_run") or {}).get("benchmark") or {}
    manifest_benchmark = manifest.get("benchmark") or {}
    benchmark: Dict[str, Any] = {
        "symbol": auth_benchmark["symbol"],
        "role": auth_benchmark["role"],
        "benchmark_is_not_a_candidate": True,
        "window_benchmark_series_required": True,
        "window_benchmark_series_exists_yet": False,
        "development_benchmark_dataset_path": auth_benchmark["dataset_path"],
        "development_benchmark_content_hash": auth_benchmark["content_hash"],
        "development_benchmark_covers_the_window": False,
        "development_benchmark_may_be_reused_as_the_window_benchmark": False,
        "window_benchmark_retrieval_happens_once": True,
        "window_benchmark_is_hash_verified": True,
        "alignment_rule": auth_benchmark["alignment_rule"],
        "methodology_rule": auth_benchmark["methodology_rule"],
        "methodology_reference": auth_benchmark["methodology_reference"],
        "no_forward_fill": True,
        "fail_closed": list(auth_benchmark["fail_closed"]),
        "grid_rule": auth_benchmark["grid_rule"],
        "btc_configurations_dropped": False,
    }
    if manifest_benchmark.get("content_hash") != auth_benchmark.get("content_hash"):
        raise SystemExit(
            "the published selected-configurations manifest and the selection authorization "
            "disagree about the benchmark content hash; refusing to publish a protocol"
        )

    data_path: Dict[str, Any] = {
        "retrieval_happens_once_after_readiness_test_passes": True,
        "every_read_counted_in_holdout_exposed_count": True,
        "hashed_and_verified_against_v3_data_manifest_scheme": True,
        "universe_manifest_path": UNIVERSE_V3_RELATIVE,
        "universe_manifest_hash": universe["manifest_hash"],
        "data_manifest_path": DATA_MANIFEST_V3_RELATIVE,
        "data_manifest_hash": effective_data["effective_data_manifest_hash"],
        "base_data_manifest_path": DATA_MANIFEST_V3_RELATIVE,
        "base_data_manifest_hash": effective_data["base_manifest_hash"],
        "confirmatory_window_start_utc": window_start,
        "benchmark": benchmark,
        "readiness_test": {
            "must_pass_before_any_window_read": True,
            "checks": [
                "the v3 confirmatory window holds at least 2160 closed hourly candles",
                "the published v3 selected-configuration manifest is committed and hash-bound",
                "this protocol is committed",
                "a confirmatory evaluation authorization exists and is bound to this protocol's manifest_hash",
                "the confirmatory execution path lives outside the hashed set and its canonical digest is recorded",
                "the v1 holdout and the v2 confirmatory window are not read",
                "the window benchmark series is retrievable, hash-verifiable and index-aligned with the asset series",
            ],
            "failure_mode": "BLOCKED_EXTERNAL",
        },
    }

    # --- evaluation rule --------------------------------------------------
    evaluation_rule: Dict[str, Any] = {
        "unchanged_v1_evaluation_metric": True,
        "unchanged_cost_scenarios": True,
        "no_retuning_reranking_or_grid_extension_on_window": True,
        "selection_rule_reference": "configs/research_v1.json#selection",
        "cost_scenarios": [float(value) for value in spec_v1["costs"]["scenarios"]],
    }

    # --- the single decision rule ----------------------------------------
    promotion = (spec_v3.get("holdout") or {}).get("promotion_rule") or {}
    decision_rule: Dict[str, Any] = {
        "criterion_count": 1,
        "authoritative_source": "configs/research_v3.json#holdout.promotion_rule",
        "criteria": list(promotion["criteria"]),
        "status_vocabulary": list(promotion["status_vocabulary"]),
        "exactly_one_criterion": True,
        "no_competing_criterion": True,
        "note": (
            "The confirmatory decision is the single preregistered v3 promotion rule, "
            "copied verbatim from the immutable v3 specification. No second criterion "
            "(for example a buy-and-hold comparison) is stated anywhere in this document, "
            "because the v2 line had to be amended after two frozen artifacts disagreed "
            "about what passing the window means."
        ),
        "verdicts": {
            "survival_status": "PROVISIONAL_HISTORICAL_SURVIVAL",
            "survival_rule": (
                "every criterion of the single preregistered promotion rule holds"
            ),
            "rejected_status": "REJECTED_ON_HOLDOUT",
            "rejected_rule": (
                "the evaluation is conclusive and at least one criterion of the single "
                "preregistered promotion rule fails"
            ),
            "inconclusive_status": "INCONCLUSIVE",
            "inconclusive_rules": [
                "the window data is insufficient to evaluate the configuration",
                "the configuration produced zero closed trades on the window",
            ],
            "zero_trade_status": "INCONCLUSIVE",
            "zero_trade_rule": (
                "a configuration with zero closed trades is INCONCLUSIVE and never "
                "REJECTED_ON_HOLDOUT: a never-traded strategy is not reported as a failure, "
                "because the data cannot support that claim"
            ),
            "low_trade_count_status": "REJECTED_ON_HOLDOUT",
            "low_trade_count_rule": (
                "a configuration with 1 to 29 closed trades fails the closed_trades >= 30 "
                "criterion and is REJECTED_ON_HOLDOUT"
            ),
            "status_vocabulary_is_not_extended": True,
        },
    }

    # --- reporting, falsifiers and the carried deviation ------------------
    reporting_and_falsifiers: Dict[str, Any] = {
        "every_evaluated_asset_and_candidate_reported": True,
        "assets_without_a_candidate_are_named": True,
        "null_result_reported": True,
        "negative_and_inconclusive_results_are_never_discarded": True,
        "v1_holdout_never_reopened": True,
        "v2_confirmatory_window_never_read": True,
        "holdout_report_required_fields": list(
            (spec_v3.get("holdout") or {}).get("v3_holdout_report_required_fields") or []
        ),
        "falsifiers": [
            "a confirmatory evaluation omits one of the four published candidates",
            "an asset without a candidate is hidden from the report",
            "the grid is extended, re-tuned or re-ranked on the window",
            "a candle inside the window is read more than once",
            "holdout_exposed_count is incremented outside a confirmatory read",
            "the window benchmark series is missing, short or misaligned and the evaluation proceeds anyway",
            "the 576 btc_ema_168 configurations per asset are dropped",
            "the v1 holdout or the v2 confirmatory window is read",
            "a second confirmatory decision criterion is applied",
            "the v1/v2 BTC-alignment deviation is repaired instead of disclosed",
        ],
    }

    deviation = manifest.get("deviation_disclosure") or {}
    deviation_disclosure: Dict[str, Any] = {
        "scope": deviation["scope"],
        "statement": deviation["statement"],
        "records_with_btc_filter": deviation["records_with_btc_filter"],
        "total_v2_records": deviation["total_v2_records"],
        "misaligned_validation_folds": list(deviation["misaligned_validation_folds"]),
        "evidence_path": deviation["evidence_path"],
        "v3_run_alignment": deviation["v3_run_alignment"],
        "carried_into_the_final_report": True,
        "not_repaired": True,
    }

    # --- authorization boundary and code identity -------------------------
    authorization_boundary: Dict[str, Any] = {
        "authorizes_evaluation": False,
        "authorizes_candle_read_before_window_exists": False,
        "authorizes_window_benchmark_retrieval": False,
        "code_identity_rule": "canonical_digest",
        "authorized_code_hash": code_hash,
        "v1_paths_forbidden": True,
        "v2_paths_forbidden": True,
        "new_v3_paths_require_new_versioned_amendment": True,
        "confirmatory_execution_code_must_live_outside_the_hashed_set": True,
        "hashed_set_root": HASHED_SET_ROOT,
        "statement": (
            "This protocol authorizes nothing. It preregisters how the confirmatory "
            "evaluation will be performed once the window exists. No candle inside the "
            "window may be read, no benchmark series may be retrieved, and no evaluation "
            "may be run, under this protocol."
        ),
    }

    document: Dict[str, Any] = {
        "artifact": "v3_confirmatory_protocol",
        "artifact_version": "v3-confirmatory-protocol-1",
        "protocol_version": "v3",
        "universe_version": "v3",
        "created_utc": CREATED_UTC,
        "protocol_status": "PREREGISTERED_NO_EVALUATION",
        "specification_purpose": (
            "Preregister the v3 confirmatory-evaluation protocol: the 4 published "
            "candidates, the window definition and readiness test, the data path "
            "including the window benchmark series, the unchanged evaluation rule, the "
            "single confirmatory decision criterion, the reporting and falsifiers, and "
            "the authorization boundary. This artifact authorizes no evaluation, no "
            "window read and no benchmark retrieval before the window exists."
        ),
        "evaluation_scope": evaluation_scope,
        "window_definition": window_definition,
        "data_path": data_path,
        "evaluation_rule": evaluation_rule,
        "decision_rule": decision_rule,
        "reporting_and_falsifiers": reporting_and_falsifiers,
        "deviation_disclosure": deviation_disclosure,
        "authorization_boundary": authorization_boundary,
        "code_hash_constraint": {
            "authorized_code_hash": code_hash,
            "canonical_source_digest": recorded_canonical,
            "canonical_source_digest_algorithm": "canonical_source_digest_v1",
            "hashed_set_root": HASHED_SET_ROOT,
            "confirmatory_execution_code_must_live_outside_the_hashed_set": True,
            "outside_hashed_set_examples": [
                "scripts/",
                "src/v3_campaign/",
                "src/v3_confirmatory/",
            ],
            "inside_hashed_set_examples": [
                "src/breakout_research/",
                "src/breakout_research/v2/",
            ],
            "ordered_code_hash_is_portable": False,
            "note": (
                "The identity of the hashed source set is the canonical source digest, "
                "which is portable across checkouts. The checkout-dependent ordered "
                "digest compute_code_hash() stays the authorized value of record and is "
                "never recomputed as a drift signal."
            ),
        },
        "supersedes": {
            "protocol_version": "v3",
            "selection_authorization_path": SELECTION_AUTHORIZATION_RELATIVE,
            "selection_authorization_manifest_hash": selection_auth["manifest_hash"],
            "reason": (
                "The v3 selection run selected at most one configuration per asset of the "
                "frozen v3 candidate set. The confirmatory protocol evaluates exactly the "
                "four published candidates on the v3 confirmatory window; the selection "
                "run remains the preceding, immutable step."
            ),
            "v1_holdout_never_reused": True,
            "v2_confirmatory_window_never_read": True,
        },
        "related_artifacts": {
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
                "manifest_hash": manifest["manifest_hash"],
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_auth["manifest_hash"],
            },
            "v3_specification": {
                "path": SPEC_V3_RELATIVE,
                "specification_hash": spec_v3["specification_hash"],
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1["specification_hash"],
            },
            "v3_data_manifest": {
                "path": DATA_MANIFEST_V3_RELATIVE,
                "manifest_hash": effective_data["base_manifest_hash"],
                "effective_manifest_hash": effective_data["effective_data_manifest_hash"],
            },
            "v3_data_manifest_amendment_1": {
                "path": DATA_MANIFEST_AMENDMENT_1_RELATIVE,
                "manifest_hash": data_amendment["manifest_hash"],
            },
            "v3_universe_manifest": {
                "path": UNIVERSE_V3_RELATIVE,
                "manifest_hash": universe["manifest_hash"],
            },
            "v3_candidate_freeze": {
                "path": CANDIDATE_FREEZE_RELATIVE,
                "manifest_hash": freeze["manifest_hash"],
            },
            "v3_candidate_freeze_amendment_1": {
                "path": CANDIDATE_FREEZE_AMENDMENT_1_RELATIVE,
                "manifest_hash": freeze_amendment_1["manifest_hash"],
            },
            "v3_candidate_freeze_amendment_2": {
                "path": CANDIDATE_FREEZE_AMENDMENT_2_RELATIVE,
                "manifest_hash": freeze_amendment_2["manifest_hash"],
            },
            "v3_execution_protocol": {
                "path": EXECUTION_PROTOCOL_RELATIVE,
                "specification_hash": execution["specification_hash"],
            },
            "v3_execution_amendment_1": {
                "path": EXECUTION_AMENDMENT_1_RELATIVE,
                "manifest_hash": execution_amendment_1["manifest_hash"],
            },
            "v3_execution_amendment_2": {
                "path": EXECUTION_AMENDMENT_2_RELATIVE,
                "manifest_hash": execution_amendment_2["manifest_hash"],
            },
        },
        "durability": {
            "rule": (
                "The protocol takes effect when this artifact is committed. No "
                "confirmatory-window candle may be read and no evaluation may run "
                "before the commit that carries this artifact exists."
            ),
            "protocol_commit": None,
            "protocol_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is "
                "not rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v3_confirmatory_protocol.py",
            "verify_command": "python3 scripts/verify_v3_confirmatory_protocol.py",
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

    target = repo_root / "configs" / "research_v3_confirmatory_protocol.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

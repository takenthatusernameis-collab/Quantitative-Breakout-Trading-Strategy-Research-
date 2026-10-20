#!/usr/bin/env python3
"""Build the versioned amendment of the v2 confirmatory-evaluation protocol.

Two frozen, hash-bound artifacts state the confirmatory decision criterion and
they do not agree:

* ``configs/research_v2.json`` -> ``holdout.promotion_rule`` promotes a
  candidate only if its net total return is positive at 1x costs **and** at 2x
  costs **and** it closed at least 30 trades **and** the evaluated parameters
  are byte-identical to the frozen candidate manifest entry;
* ``configs/research_v2_confirmatory_protocol.json`` ->
  ``reporting_and_falsifiers`` defines a **pass** as a net result at baseline
  costs that exceeds the buy-and-hold baseline's net result.

A configuration with a positive net return and 40 trades is a survival under
the specification and a failure under the protocol. Both artifacts are
immutable, so the conflict is settled by this **versioned amendment** (decision
D-5 of BRAIN-011), never by editing either of them:

* the specification's promotion rule is **authoritative** for the status;
* the protocol's buy-and-hold criterion is **computed and reported alongside**
  it as the secondary field ``baseline_comparison``, because it costs no
  additional exposure -- both are derived from the same single evaluation;
* where the two disagree the report marks the asset
  ``criteria_agreement = DISAGREE`` and states the disagreement in the summary;
* the status vocabulary is not extended: ``criteria_agreement`` is a report
  field, not a status;
* a configuration with **zero** closed trades is ``INCONCLUSIVE``, never
  ``REJECTED_ON_HOLDOUT``: a never-traded strategy cannot be reported as a
  failure;
* the amendment must be committed **before** the first window candle is read;
  a rule chosen after the window is exposed is forbidden.

The script is deterministic: every field is derived from artifacts that are
already hash-bound, so re-running it reproduces the same bytes. It never
fetches anything, never reads a candle and never runs an evaluation.

Usage::

    python3 scripts/build_v2_confirmatory_protocol_amendment_1.py            # write
    python3 scripts/build_v2_confirmatory_protocol_amendment_1.py --force    # rewrite
    python3 scripts/build_v2_confirmatory_protocol_amendment_1.py --print    # print only
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

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_confirmatory_protocol_amendment_1.json"

#: The instant at which the amendment was preregistered. Pinned so the
#: artifact is byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T11:00:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SELECTED_CONFIGURATIONS_RELATIVE = "research/v2_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v2_selection_authorization_1.json"


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


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the amendment document from the hash-bound artifacts."""
    root = Path(repo_root)
    protocol = _load(root / PROTOCOL_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    selected = _load(root / SELECTED_CONFIGURATIONS_RELATIVE)
    selection_authorization = _load(root / SELECTION_AUTHORIZATION_RELATIVE)

    promotion = (spec_v2.get("holdout") or {}).get("promotion_rule") or {}
    criteria = list(promotion.get("criteria") or [])
    vocabulary = list(promotion.get("status_vocabulary") or [])
    if not criteria or not vocabulary:
        raise SystemExit("the v2 specification carries no promotion rule; refusing to amend")

    protocol_reporting = protocol.get("reporting_and_falsifiers") or {}
    if not protocol_reporting.get("pass_criterion") or not protocol_reporting.get(
        "failure_criterion"
    ):
        raise SystemExit("the confirmatory protocol carries no pass/failure criterion")

    selections = selected.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is not True
    )

    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_protocol_amendment",
        "artifact_version": "v2-confirmatory-protocol-amendment-1",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "amendment_status": "PREREGISTERED_AMENDMENT_BEFORE_ANY_WINDOW_READ",
        "specification_purpose": (
            "Reconcile the confirmatory decision criterion of two frozen artifacts before "
            "the first confirmatory-window candle is read, and record the verdict rules, "
            "the disclosure of a disagreement and the commit-before-read rule. This "
            "amendment authorizes no evaluation and no candle read."
        ),
        "amends": {
            "protocol_path": PROTOCOL_RELATIVE,
            "protocol_manifest_hash": protocol.get("manifest_hash"),
            "specification_path": SPEC_V2_RELATIVE,
            "specification_hash": spec_v2.get("specification_hash"),
            "reason": (
                "The frozen v2 specification's promotion rule and the frozen confirmatory "
                "protocol's buy-and-hold pass/failure criterion disagree on what passing "
                "the confirmatory window means, and both artifacts are immutable and "
                "hash-bound. A single-use window cannot be re-graded after it has been "
                "burned, so the criterion is fixed by this versioned amendment, before any "
                "read."
            ),
            "edits_no_frozen_artifact": True,
            "frozen_artifacts_remain_byte_identical": True,
        },
        "criterion_precedence": {
            "authoritative_source": "configs/research_v2.json#holdout.promotion_rule",
            "authoritative_status_vocabulary": vocabulary,
            "authoritative_criteria": criteria,
            "secondary_source": (
                "configs/research_v2_confirmatory_protocol.json#reporting_and_falsifiers"
            ),
            "secondary_field": "baseline_comparison",
            "secondary_never_assigns_the_status": True,
            "secondary_costs_no_additional_exposure": True,
            "reason": (
                "The promotion rule is part of the hash-bound preregistration, and BRAIN-006 "
                "established that the preregistered rule governs candidate promotion. The "
                "protocol's criterion is computed from the same single evaluation and is "
                "reported beside the status, so the disagreement is disclosed rather than "
                "silently resolved."
            ),
        },
        "verdicts": {
            "survival_status": "PROVISIONAL_HISTORICAL_SURVIVAL",
            "survival_rule": "every criterion of the preregistered promotion rule holds",
            "rejected_status": "REJECTED_ON_HOLDOUT",
            "rejected_rule": (
                "the evaluation is conclusive and at least one criterion of the promotion "
                "rule fails"
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
        "disclosure": {
            "criteria_agreement_field": "criteria_agreement",
            "criteria_agreement_values": ["AGREE", "DISAGREE", "NOT_COMPARABLE"],
            "disagreement_is_reported": True,
            "disagreement_is_stated_in_the_summary": True,
            "criteria_agreement_is_a_field_not_a_status": True,
            "null_result_is_reported": True,
            "no_asset_is_dropped_from_the_report": True,
        },
        "baseline_comparison": {
            "outcome_values": ["PASS", "FAIL", "INCONCLUSIVE"],
            "pass_rule": (
                "the net result at baseline costs exceeds the corresponding buy-and-hold "
                "baseline's net result"
            ),
            "failure_rule": (
                "the net result at baseline costs is below the corresponding buy-and-hold "
                "baseline's net result"
            ),
            "inconclusive_rule": "the net result or the baseline is not computable",
            "tie_rule": (
                "an exact tie is not an excess and is therefore reported as FAIL with "
                "tie = true"
            ),
            "agreement_rule": (
                "PROVISIONAL_HISTORICAL_SURVIVAL with PASS and REJECTED_ON_HOLDOUT with FAIL "
                "agree; every other pairing of a conclusive status with a conclusive "
                "baseline outcome disagrees"
            ),
        },
        "commit_before_first_read": {
            "rule": (
                "This amendment must be committed before the first confirmatory-window candle "
                "is read. A rule chosen after the window has been exposed is forbidden."
            ),
            "amendment_commit": None,
            "amendment_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "scope_of_this_amendment": {
            "in_scope_assets": len(assets_with_candidate),
            "out_of_scope_assets_without_candidate": assets_without_candidate,
            "the_scope_is_unchanged_by_this_amendment": True,
        },
        "related_artifacts": {
            "confirmatory_protocol": {
                "path": PROTOCOL_RELATIVE,
                "manifest_hash": protocol.get("manifest_hash"),
            },
            "v2_specification": {
                "path": SPEC_V2_RELATIVE,
                "specification_hash": spec_v2.get("specification_hash"),
            },
            "v1_specification": {
                "path": SPEC_V1_RELATIVE,
                "specification_hash": spec_v1.get("specification_hash"),
            },
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_RELATIVE,
                "manifest_hash": selected.get("manifest_hash"),
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_authorization.get("manifest_hash"),
            },
        },
        "durability": {
            "rule": (
                "The amendment takes effect when this artifact is committed. No "
                "confirmatory-window candle may be read before the commit that carries it "
                "exists."
            ),
            "amendment_commit": None,
            "amendment_commit_status": "PENDING_COMMIT",
        },
        "producer": {
            "path": "scripts/build_v2_confirmatory_protocol_amendment_1.py",
            "verify_command": (
                "python3 scripts/verify_v2_confirmatory_path.py"
            ),
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

    target = repo_root / "configs" / "research_v2_confirmatory_protocol_amendment_1.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

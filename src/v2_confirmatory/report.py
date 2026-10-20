"""The confirmatory verdict rules and the holdout report.

Two frozen artifacts state the confirmatory decision criterion and they do not
agree:

* ``configs/research_v2.json`` -> ``holdout.promotion_rule`` promotes a
  candidate only if its net total return is positive at 1x costs **and** at 2x
  costs **and** it closed at least 30 trades **and** the evaluated parameters
  are byte-identical to the frozen candidate manifest entry. Its status
  vocabulary is ``CANDIDATE_PENDING_HOLDOUT``, ``PROVISIONAL_HISTORICAL_SURVIVAL``,
  ``REJECTED_ON_HOLDOUT``, ``INCONCLUSIVE``.
* ``configs/research_v2_confirmatory_protocol.json`` ->
  ``reporting_and_falsifiers`` defines a **pass** as a net result at baseline
  costs that exceeds the buy-and-hold baseline's net result, a **failure** as
  below it, and an **inconclusive** outcome as insufficient data or a
  zero-trade result.

Decision D-5 of BRAIN-011 settles the conflict by a versioned amendment
(``configs/research_v2_confirmatory_protocol_amendment_1.json``): the
**specification's promotion rule is authoritative** for the status, because it
is part of the hash-bound preregistration; the protocol's buy-and-hold
criterion is **computed and reported alongside** it as a secondary field, since
it costs no additional exposure. Where the two disagree the report marks the
asset ``criteria_agreement = DISAGREE`` and says so in the summary.

The status vocabulary is not extended: ``criteria_agreement`` is a report
**field**, not a status.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

#: The status vocabulary of the frozen v2 specification.
STATUS_SURVIVAL = "PROVISIONAL_HISTORICAL_SURVIVAL"
STATUS_REJECTED = "REJECTED_ON_HOLDOUT"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
STATUS_PENDING = "CANDIDATE_PENDING_HOLDOUT"

#: The report fields the frozen v2 specification requires.
REQUIRED_REPORT_FIELDS = (
    "universe_version",
    "snapshot_id",
    "candidate_manifest_path",
    "candidate_manifest_hash",
    "confirmatory_window_start_utc",
    "confirmatory_window_end_utc",
    "candles_evaluated",
    "exposure_count",
    "per_asset_outcomes",
    "comparability_statement",
)

#: The minimum number of closed trades the promotion rule requires.
MIN_CLOSED_TRADES = 30


def specification_verdict(
    metrics: Dict[str, Any],
    min_trades: int = MIN_CLOSED_TRADES,
) -> Dict[str, Any]:
    """Apply the frozen v2 promotion rule to one asset's window metrics.

    ``metrics`` carries ``net_total_return_1x``, ``net_total_return_2x``,
    ``closed_trades``, ``data_sufficient`` and ``parameters_match``.

    The zero-trade case is ``INCONCLUSIVE`` and never ``REJECTED_ON_HOLDOUT``:
    a strategy that was never observed to trade cannot be reported as a
    failure, because the data cannot support that claim.
    """
    data_sufficient = bool(metrics.get("data_sufficient"))
    closed_trades = metrics.get("closed_trades")
    criteria = {
        "net_total_return_positive_at_1x": False,
        "net_total_return_positive_at_2x": False,
        "closed_trades_at_least_threshold": False,
        "parameters_match_frozen_manifest": bool(metrics.get("parameters_match")),
    }

    if not data_sufficient:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": "the window data is insufficient to evaluate the configuration",
            "criteria": criteria,
            "criteria_evaluated": False,
        }
    if closed_trades is None:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": "the number of closed trades on the window is unknown",
            "criteria": criteria,
            "criteria_evaluated": False,
        }
    if int(closed_trades) == 0:
        return {
            "status": STATUS_INCONCLUSIVE,
            "reason": (
                "the configuration produced no closed trade on the window; a never-traded "
                "strategy is not reported as a failure"
            ),
            "criteria": criteria,
            "criteria_evaluated": False,
        }

    net_1x = metrics.get("net_total_return_1x")
    net_2x = metrics.get("net_total_return_2x")
    criteria["net_total_return_positive_at_1x"] = net_1x is not None and float(net_1x) > 0.0
    criteria["net_total_return_positive_at_2x"] = net_2x is not None and float(net_2x) > 0.0
    criteria["closed_trades_at_least_threshold"] = int(closed_trades) >= int(min_trades)

    failed = [name for name, holds in criteria.items() if not holds]
    if failed:
        return {
            "status": STATUS_REJECTED,
            "reason": f"the promotion rule was not met: {', '.join(failed)}",
            "criteria": criteria,
            "criteria_evaluated": True,
        }
    return {
        "status": STATUS_SURVIVAL,
        "reason": "every criterion of the preregistered promotion rule holds",
        "criteria": criteria,
        "criteria_evaluated": True,
    }


def baseline_comparison(
    metrics: Dict[str, Any], baseline_net_return: Optional[float]
) -> Dict[str, Any]:
    """The protocol's buy-and-hold criterion, computed and reported.

    The outcome never assigns the status; it is the secondary, disclosed
    comparison. An exact tie is not an excess and is therefore reported as
    ``FAIL`` with ``tie = true``.
    """
    net = metrics.get("net_total_return_1x")
    if net is None or baseline_net_return is None or not metrics.get("data_sufficient"):
        return {
            "outcome": "INCONCLUSIVE",
            "net_total_return": net,
            "baseline_net_total_return": baseline_net_return,
            "difference": None,
            "tie": False,
        }
    difference = float(net) - float(baseline_net_return)
    if difference > 0.0:
        outcome = "PASS"
    else:
        outcome = "FAIL"
    return {
        "outcome": outcome,
        "net_total_return": float(net),
        "baseline_net_total_return": float(baseline_net_return),
        "difference": difference,
        "tie": difference == 0.0,
    }


def criteria_agreement(specification_status: str, baseline_outcome: str) -> str:
    """Whether the two criteria agree on this asset.

    ``AGREE``, ``DISAGREE`` or ``NOT_COMPARABLE`` (an inconclusive evaluation
    cannot disagree with anything).
    """
    if specification_status == STATUS_INCONCLUSIVE:
        return "NOT_COMPARABLE"
    if specification_status == STATUS_SURVIVAL and baseline_outcome == "PASS":
        return "AGREE"
    if specification_status == STATUS_REJECTED and baseline_outcome == "FAIL":
        return "AGREE"
    return "DISAGREE"


def asset_outcome(
    asset: str,
    config_id: str,
    metrics: Dict[str, Any],
    baseline_net_return: Optional[float],
) -> Dict[str, Any]:
    """The report entry of one in-scope asset."""
    verdict = specification_verdict(metrics)
    comparison = baseline_comparison(metrics, baseline_net_return)
    agreement = criteria_agreement(verdict["status"], comparison["outcome"])
    return {
        "asset": asset,
        "config_id": config_id,
        "status": verdict["status"],
        "reason": verdict["reason"],
        "criteria": verdict["criteria"],
        "criteria_evaluated": verdict["criteria_evaluated"],
        "net_total_return_1x": metrics.get("net_total_return_1x"),
        "net_total_return_2x": metrics.get("net_total_return_2x"),
        "net_total_return_3x": metrics.get("net_total_return_3x"),
        "closed_trades": metrics.get("closed_trades"),
        "baseline_comparison": comparison,
        "criteria_agreement": agreement,
    }


def report_outcome(per_asset_outcomes: Dict[str, Dict[str, Any]]) -> str:
    """The run's overall outcome, derived from the per-asset verdicts.

    A null result -- no configuration surviving the preregistered promotion
    rule -- is an outcome of its own and is never hidden.
    """
    survivors = sorted(
        asset
        for asset, entry in (per_asset_outcomes or {}).items()
        if entry.get("status") == STATUS_SURVIVAL
    )
    disagreements = sorted(
        asset
        for asset, entry in (per_asset_outcomes or {}).items()
        if entry.get("criteria_agreement") == "DISAGREE"
    )
    if survivors and not disagreements:
        return "CANDIDATES_SURVIVED_THE_CONFIRMATORY_WINDOW"
    if survivors:
        return "CANDIDATES_SURVIVED_THE_CONFIRMATORY_WINDOW_WITH_REPORTED_DISAGREEMENT"
    return "NO_CANDIDATE_SURVIVED_THE_CONFIRMATORY_RULE"


def build_report(
    *,
    universe_version: str,
    snapshot_id: str,
    candidate_manifest_path: str,
    candidate_manifest_hash: str,
    confirmatory_window_start_utc: str,
    confirmatory_window_end_utc: str,
    candles_evaluated: int,
    exposure_count: int,
    per_asset_outcomes: Dict[str, Dict[str, Any]],
    assets_without_candidate: Sequence[str],
    comparability_statement: str,
    created_utc: str,
    criteria_precedence: Optional[Dict[str, Any]] = None,
    criterion_amendment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the v2 holdout report.

    The report carries the ten fields the frozen v2 specification requires and
    lists **every** asset of the frozen scope: the evaluated ones with their
    verdict, and the assets without a candidate as ``NO_CANDIDATE_NOT_EVALUATED``.
    A null result is reported as such and never hidden.
    """
    survivors = sorted(
        asset
        for asset, entry in per_asset_outcomes.items()
        if entry.get("status") == STATUS_SURVIVAL
    )
    disagreements = sorted(
        asset
        for asset, entry in per_asset_outcomes.items()
        if entry.get("criteria_agreement") == "DISAGREE"
    )
    outcome = report_outcome(per_asset_outcomes)

    report: Dict[str, Any] = {
        "artifact": "v2_confirmatory_evaluation",
        "artifact_version": "v2-confirmatory-evaluation-1",
        "protocol_version": "v2",
        "universe_version": universe_version,
        "snapshot_id": snapshot_id,
        "candidate_manifest_path": candidate_manifest_path,
        "candidate_manifest_hash": candidate_manifest_hash,
        "confirmatory_window_start_utc": confirmatory_window_start_utc,
        "confirmatory_window_end_utc": confirmatory_window_end_utc,
        "candles_evaluated": int(candles_evaluated),
        "exposure_count": int(exposure_count),
        "per_asset_outcomes": dict(per_asset_outcomes),
        "comparability_statement": comparability_statement,
        "created_utc": created_utc,
        "outcome": outcome,
        "assets_surviving": survivors,
        "assets_without_candidate": sorted(assets_without_candidate),
        "assets_without_candidate_status": "NO_CANDIDATE_NOT_EVALUATED",
        "assets_without_candidate_reported": True,
        "criteria_disagreements": disagreements,
        "criteria_precedence": criteria_precedence or {},
        "criterion_amendment": criterion_amendment or {},
        "v1_holdout_never_reused": True,
        "null_result_reported": True,
    }
    missing = [field for field in REQUIRED_REPORT_FIELDS if field not in report]
    if missing:
        raise ValueError(f"the holdout report is missing the required fields {missing}")
    return report


def missing_report_fields(report: Dict[str, Any]) -> List[str]:
    """The required report fields the report does not carry."""
    return [field for field in REQUIRED_REPORT_FIELDS if field not in (report or {})]


def assets_with_status(report: Dict[str, Any], status: str) -> List[str]:
    """The assets whose verdict is that status."""
    outcomes = (report or {}).get("per_asset_outcomes") or {}
    return sorted(asset for asset, entry in outcomes.items() if entry.get("status") == status)


__all__ = [
    "MIN_CLOSED_TRADES",
    "REQUIRED_REPORT_FIELDS",
    "STATUS_INCONCLUSIVE",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "STATUS_SURVIVAL",
    "asset_outcome",
    "assets_with_status",
    "baseline_comparison",
    "build_report",
    "criteria_agreement",
    "missing_report_fields",
    "report_outcome",
    "specification_verdict",
]

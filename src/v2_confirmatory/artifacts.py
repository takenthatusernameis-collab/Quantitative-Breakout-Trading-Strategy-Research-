"""The output layout of the v2 confirmatory evaluation.

Decision D-6 of BRAIN-011 fixes the layout, and decision D-11 fixes the report:

* ``research/shards_v2_confirmatory/`` -- one shard per run, holding one result
  row per evaluated asset;
* ``research/results_v2_confirmatory.jsonl`` -- the result stream, one JSON row
  per evaluated asset;
* ``research/ledger_v2_confirmatory.json`` -- the run's ledger: the scope, the
  window, the exposure accounting, the per-asset outcomes and the counts;
* ``research/results_manifest_v2_confirmatory.json`` -- the manifest of the
  written shards, their hashes and their sizes;
* ``research_state/checkpoint_v2_confirmatory.json`` -- the checkpoint that
  carries ``holdout_exposed_count``;
* ``research/v2_confirmatory_window_manifest.json`` -- the window manifest
  (built by :mod:`v2_confirmatory.data`);
* ``reports/confirmatory_evaluation_v2.json`` and
  ``reports/confirmatory_report_v2.md`` -- the holdout report.

The v1 paths and the v2 *selection* paths are not part of this layout and are
never written by the confirmatory path.

Every builder of this module is **pure**: it computes a document and never
writes it, so the tests can exercise the whole layout without producing a
single confirmatory artifact. The runner persists the documents.

The **evaluated window is fixed**: it is exactly the first
``minimum_closed_hourly_candles`` closed hourly candles at or after the window
start, i.e. it ends at the earliest instant the frozen boundary allows. The
length of the evaluated window therefore does not depend on when the run
happens, which keeps the run free of a discretionary choice of window length.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .report import STATUS_SURVIVAL

#: The rule that fixes the evaluated window's length.
EVALUATION_WINDOW_RULE = (
    "The evaluated window is exactly the first minimum_closed_hourly_candles closed "
    "hourly candles at or after the window start, so it ends at the earliest instant the "
    "frozen boundary allows. The evaluated window's length does not depend on when the "
    "run happens, and the window may not be extended, shortened or re-based at run time."
)

#: Keys removed from a document before its manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The status of an asset that has no candidate and is therefore not evaluated.
NO_CANDIDATE_STATUS = "NO_CANDIDATE_NOT_EVALUATED"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Iterable[str]) -> str:
    """The self-hash of a hash-bound artifact."""
    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    return sha256_bytes(canonical(body).encode("utf-8"))


def _hashing_block() -> Dict[str, Any]:
    return {
        "algorithm": "sha256",
        "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
        "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
        "note": (
            "manifest_hash is the sha256 of the document body with manifest_hash removed, "
            "so the document does not hash itself into a cycle."
        ),
    }


def build_result_rows(
    *,
    campaign_id: str,
    run_id: str,
    per_asset_outcomes: Dict[str, Dict[str, Any]],
    datasets: Dict[str, Dict[str, Any]],
    window_start_utc: str,
    window_end_utc: str,
) -> List[Dict[str, Any]]:
    """One result row per evaluated asset, in asset order."""
    rows: List[Dict[str, Any]] = []
    for asset in sorted(per_asset_outcomes):
        outcome = per_asset_outcomes[asset]
        dataset = datasets.get(asset) or {}
        rows.append(
            {
                "artifact": "v2_confirmatory_result",
                "campaign_id": campaign_id,
                "run_id": run_id,
                "asset": asset,
                "config_id": outcome.get("config_id"),
                "status": outcome.get("status"),
                "reason": outcome.get("reason"),
                "criteria": outcome.get("criteria"),
                "criteria_evaluated": outcome.get("criteria_evaluated"),
                "net_total_return_1x": outcome.get("net_total_return_1x"),
                "net_total_return_2x": outcome.get("net_total_return_2x"),
                "net_total_return_3x": outcome.get("net_total_return_3x"),
                "closed_trades": outcome.get("closed_trades"),
                "baseline_comparison": outcome.get("baseline_comparison"),
                "criteria_agreement": outcome.get("criteria_agreement"),
                "dataset_content_hash": dataset.get("content_hash"),
                "dataset_hash_algorithm": dataset.get("hash_algorithm"),
                "observed_candle_count": dataset.get("observed_candle_count"),
                "coverage_gaps": dataset.get("gaps"),
                "window_start_utc": window_start_utc,
                "window_end_utc": window_end_utc,
                "evaluated": True,
            }
        )
    return rows


def render_jsonl(rows: Sequence[Dict[str, Any]]) -> str:
    """Render result rows as a JSONL document, one row per line."""
    return "".join(canonical(row) + "\n" for row in rows)


def build_results_manifest(
    *,
    campaign_id: str,
    run_id: str,
    code_identity: Dict[str, Any],
    data_manifest_hash: str,
    specification_hash: str,
    window_manifest_hash: str,
    shards: Sequence[Dict[str, Any]],
    total_bytes: int,
    total_records: int,
    created_utc: str,
) -> Dict[str, Any]:
    """The manifest of the written shards."""
    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_results_manifest",
        "artifact_version": "v2-confirmatory-results-manifest-1",
        "schema_version": "result-shard-v1",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "code_hash": code_identity.get("run_code_identity"),
        "code_identity": dict(code_identity),
        "data_manifest_hash": data_manifest_hash,
        "specification_hash": specification_hash,
        "window_manifest_hash": window_manifest_hash,
        "shards": [dict(shard) for shard in shards],
        "total_bytes": int(total_bytes),
        "total_records": int(total_records),
        "created_utc": created_utc,
        "updated_utc": created_utc,
        "hashing": _hashing_block(),
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def build_ledger(
    *,
    campaign_id: str,
    run_id: str,
    started_utc: str,
    completed_utc: str,
    code_identity: Dict[str, Any],
    specification_hash: str,
    authorization_manifest_hash: str,
    amendment_manifest_hash: str,
    protocol_manifest_hash: str,
    window_manifest_hash: str,
    window: Dict[str, Any],
    scope: Dict[str, Any],
    per_asset_outcomes: Dict[str, Dict[str, Any]],
    assets_without_candidate: Sequence[str],
    outcome: str,
    exposure_state: Dict[str, Any],
    counts: Dict[str, Any],
    data_boundary: Dict[str, Any],
    evaluation_rule: Dict[str, Any],
    criterion_precedence: Dict[str, Any],
) -> Dict[str, Any]:
    """The confirmatory run's ledger."""
    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_ledger",
        "artifact_version": "v2-confirmatory-ledger-1",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "run_phase": "confirmatory_window_evaluation",
        "status": "COMPLETED",
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "code_identity": dict(code_identity),
        "code_hash": code_identity.get("run_code_identity"),
        "specification_hash": specification_hash,
        "authorization_manifest_hash": authorization_manifest_hash,
        "amendment_manifest_hash": amendment_manifest_hash,
        "protocol_manifest_hash": protocol_manifest_hash,
        "window_manifest_hash": window_manifest_hash,
        "window": dict(window),
        "scope": dict(scope),
        "evaluation_rule": dict(evaluation_rule),
        "criterion_precedence": dict(criterion_precedence),
        "selection": {
            "assets_evaluated": sorted(per_asset_outcomes),
            "assets_evaluated_count": len(per_asset_outcomes),
            "assets_without_candidate": sorted(assets_without_candidate),
            "assets_without_candidate_reported": True,
            "outcome": outcome,
            "per_asset": {
                asset: {
                    "config_id": entry.get("config_id"),
                    "status": entry.get("status"),
                    "criteria_agreement": entry.get("criteria_agreement"),
                    "closed_trades": entry.get("closed_trades"),
                    "net_total_return_1x": entry.get("net_total_return_1x"),
                    "net_total_return_2x": entry.get("net_total_return_2x"),
                    "net_total_return_3x": entry.get("net_total_return_3x"),
                }
                for asset, entry in sorted(per_asset_outcomes.items())
            },
        },
        "exposure": dict(exposure_state),
        "holdout_exposed_count": int((exposure_state or {}).get("holdout_exposed_count") or 0),
        "counts": dict(counts),
        "data_boundary": dict(data_boundary),
        "runs": [
            {
                "campaign_id": campaign_id,
                "run_id": run_id,
                "started_utc": started_utc,
                "completed_utc": completed_utc,
                "status": "COMPLETED",
                "resumes": 0,
                "resume_events": [],
            }
        ],
        "v1_artifacts_touched": [],
        "v2_selection_outputs_touched": [],
        "hashing": _hashing_block(),
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def build_checkpoint(
    *,
    campaign_id: str,
    run_id: str,
    status: str,
    code_identity: Dict[str, Any],
    protocol_hash: str,
    authorization_manifest_hash: str,
    window_manifest_hash: str,
    exposure_state: Dict[str, Any],
    window: Dict[str, Any],
    counts: Dict[str, Any],
    timestamp_utc: str,
) -> Dict[str, Any]:
    """The checkpoint that carries ``holdout_exposed_count``."""
    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_checkpoint",
        "artifact_version": "v2-confirmatory-checkpoint-1",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "status": status,
        "code_hash": code_identity.get("run_code_identity"),
        "code_identity": dict(code_identity),
        "protocol_hash": protocol_hash,
        "authorization_manifest_hash": authorization_manifest_hash,
        "window_manifest_hash": window_manifest_hash,
        "holdout_exposed_count": int((exposure_state or {}).get("holdout_exposed_count") or 0),
        "exposure": dict(exposure_state),
        "window": dict(window),
        "counts": dict(counts),
        "timestamp_utc": timestamp_utc,
        "hashing": _hashing_block(),
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.2f}%"


def render_report_markdown(report: Dict[str, Any]) -> str:
    """Render the human-readable confirmatory report."""
    outcomes = report.get("per_asset_outcomes") or {}
    lines: List[str] = []
    lines.append("# v2 confirmatory evaluation report")
    lines.append("")
    lines.append(f"- Outcome: **{report.get('outcome')}**")
    lines.append(
        f"- Confirmatory window: `{report.get('confirmatory_window_start_utc')}` "
        f"→ `{report.get('confirmatory_window_end_utc')}`"
    )
    lines.append(f"- Candles evaluated: {report.get('candles_evaluated')}")
    lines.append(f"- Exposure count (`holdout_exposed_count`): {report.get('exposure_count')}")
    lines.append(f"- Candidate manifest: `{report.get('candidate_manifest_path')}`")
    lines.append(f"- Candidate manifest hash: `{report.get('candidate_manifest_hash')}`")
    lines.append("")

    lines.append("## Per-asset outcomes")
    lines.append("")
    lines.append(
        "| Asset | Config | Status | Net 1x | Net 2x | Net 3x | Trades | "
        "Buy-and-hold net | Baseline criterion | Criteria agreement |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for asset in sorted(outcomes):
        entry = outcomes[asset]
        comparison = entry.get("baseline_comparison") or {}
        lines.append(
            "| {asset} | {config} | {status} | {net1} | {net2} | {net3} | {trades} | "
            "{baseline} | {outcome} | {agreement} |".format(
                asset=asset,
                config=entry.get("config_id"),
                status=entry.get("status"),
                net1=_format_percent(entry.get("net_total_return_1x")),
                net2=_format_percent(entry.get("net_total_return_2x")),
                net3=_format_percent(entry.get("net_total_return_3x")),
                trades=entry.get("closed_trades"),
                baseline=_format_percent(comparison.get("baseline_net_total_return")),
                outcome=comparison.get("outcome"),
                agreement=entry.get("criteria_agreement"),
            )
        )
    lines.append("")

    lines.append("## Assets without a candidate")
    lines.append("")
    without = sorted(report.get("assets_without_candidate") or [])
    if without:
        for asset in without:
            lines.append(f"- {asset}: {NO_CANDIDATE_STATUS}")
    else:
        lines.append("- none")
    lines.append("")

    disagreements = sorted(report.get("criteria_disagreements") or [])
    lines.append("## Criterion disagreement")
    lines.append("")
    lines.append(
        "The frozen specification's promotion rule is authoritative for the status; the "
        "protocol's buy-and-hold criterion is reported beside it."
    )
    lines.append("")
    if disagreements:
        for asset in disagreements:
            lines.append(f"- {asset}: `criteria_agreement = DISAGREE`")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Comparability")
    lines.append("")
    lines.append(str(report.get("comparability_statement")))
    lines.append("")

    artifacts = report.get("artifacts") or {}
    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for name in sorted(artifacts):
            entry = artifacts[name]
            if isinstance(entry, dict):
                lines.append(f"- `{name}`: `{entry.get('path')}` — `{entry.get('manifest_hash')}`")
            else:
                lines.append(f"- `{name}`: `{entry}`")
        lines.append("")

    survivors = sorted(report.get("assets_surviving") or [])
    lines.append("## Survival")
    lines.append("")
    if survivors:
        for asset in survivors:
            lines.append(f"- {asset}: `PROVISIONAL_HISTORICAL_SURVIVAL`")
    else:
        lines.append(
            "- No configuration survived the preregistered promotion rule. The null result "
            "is reported as such."
        )
    lines.append("")
    return "\n".join(lines)


def surviving_assets(report: Dict[str, Any]) -> List[str]:
    """The assets whose status is a survival."""
    outcomes = report.get("per_asset_outcomes") or {}
    return sorted(asset for asset, entry in outcomes.items() if entry.get("status") == STATUS_SURVIVAL)


__all__ = [
    "EVALUATION_WINDOW_RULE",
    "MANIFEST_HASH_EXCLUDED_KEYS",
    "NO_CANDIDATE_STATUS",
    "build_checkpoint",
    "build_ledger",
    "build_result_rows",
    "build_results_manifest",
    "canonical",
    "compute_manifest_hash",
    "render_jsonl",
    "render_report_markdown",
    "sha256_bytes",
    "surviving_assets",
]

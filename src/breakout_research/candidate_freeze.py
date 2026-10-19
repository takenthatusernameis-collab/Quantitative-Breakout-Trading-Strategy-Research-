"""Frozen candidate manifest helpers (BRAIN-003 holdout isolation, BRAIN-006 rule).

The v1 manifest (``research/candidate_manifest.json``) was frozen with the
legacy profit-factor rule, which is **not** the preregistered rule of
``configs/research_v1.json`` -> ``selection``.  That manifest stays immutable:
it is the historical record of what was frozen and when, and it is relabelled
as non-preregistered by the new, separately versioned manifest.

:func:`select_best_candidate` is the conforming selector of the preregistered
rule (see :mod:`breakout_research.selection`).  The legacy profit-factor rule
is kept only as :func:`_legacy_profit_factor_selector` for provenance.
"""

import argparse
import hashlib
import json
import os
from statistics import median
from typing import Any, Dict, List, Optional

from .selection import select_candidates

CANDIDATE_MANIFEST_PATH = "research/candidate_manifest.json"
CANDIDATE_MANIFEST_V2_PATH = "research/candidate_manifest_v2.json"
RULE_PREREGISTERED = "preregistered_v1"
RULE_LEGACY_PROFIT_FACTOR = "legacy_median_profit_factor"


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_hash(manifest: Dict[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def rule_spec_hash(selection_spec: Dict[str, Any]) -> str:
    """Content hash of the preregistered selection rule that produced a manifest."""
    return hashlib.sha256(_canonical(selection_spec).encode("utf-8")).hexdigest()


def save_candidate_manifest(manifest: Dict[str, Any], path: str = CANDIDATE_MANIFEST_PATH) -> None:
    manifest = dict(manifest)
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_canonical(manifest) + "\n")


def load_candidate_manifest(path: str = CANDIDATE_MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    expected = compute_manifest_hash(manifest)
    if manifest.get("manifest_hash") != expected:
        raise ValueError("candidate manifest hash mismatch")
    if not manifest.get("frozen"):
        raise ValueError("candidate manifest is not frozen")
    # At most one candidate per asset.
    for asset, payload in manifest.get("candidates", {}).items():
        if not isinstance(payload, dict) or "config_id" not in payload:
            raise ValueError(f"invalid candidate for {asset}")
    return manifest


def candidate_config_ids(manifest: Dict[str, Any]) -> Dict[str, set]:
    result = {}
    for asset, entry in manifest.get("candidates", {}).items():
        result[asset] = {entry["config_id"]}
    return result


def select_best_candidate(records: List[Dict[str, Any]], spec: Dict[str, Any],
                           baselines: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Select at most one candidate per asset under the preregistered rule.

    ``baselines`` maps an asset to its selector-facing buy-and-hold baseline
    (see :func:`breakout_research.baselines.baseline_for_asset`).  It is
    mandatory: without it the ``median_sharpe_gt_buyhold`` gate cannot be
    evaluated and the selection would not be confirmed.
    """
    selection = select_candidates(records, spec, baselines)
    return {
        asset: {
            "config_id": payload["config_id"],
            "selection_status": payload["status"],
            "economic_status": payload["economic_status"],
            "gates": payload["gates"],
            "ranking": payload["ranking"],
        }
        for asset, payload in selection.items()
        if payload["config_id"] is not None
    }


def _legacy_profit_factor_selector(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Provenance record of the rule that produced the v1 candidate manifest.

    This is the historical, non-preregistered rule: it maximises the median
    profit factor across validation folds and costs, tie-broken by the lower
    median maximum drawdown and then by the lower configuration ID.  It is
    **not** used for candidate promotion any more; it exists so the v1
    manifest can be explained and reproduced.
    """
    by_asset: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for rec in records:
        if rec.get("is_holdout"):
            continue
        if rec.get("status") != "COMPLETED":
            continue
        asset = rec["asset"]
        cid = rec["config_id"]
        by_asset.setdefault(asset, {}).setdefault(cid, []).append(rec)

    candidates = {}
    for asset, configs in by_asset.items():
        best = None
        for cid, recs in configs.items():
            pfs = [r.get("profit_factor") for r in recs]
            pfs = [p if p is not None else 0.0 for p in pfs]
            dds = [r.get("max_drawdown", 0.0) for r in recs]
            candidate_key = (median(pfs), -median(dds))
            if best is None or candidate_key > best[0] or (candidate_key == best[0] and cid < best[1]):
                best = (candidate_key, cid, recs)
        if best is None:
            continue
        _, cid, recs = best
        params = recs[0].get("parameters") if "parameters" in recs[0] else None
        candidates[asset] = {"config_id": cid}
        if params is not None:
            candidates[asset]["parameters"] = params
    return candidates


def freeze_from_results(results_manifest_path: str = "research/results_manifest.json",
                        shards_root: str = "research/results_shards",
                        output_path: str = CANDIDATE_MANIFEST_V2_PATH,
                        freeze_commit: str = "unknown",
                        spec: Optional[Dict[str, Any]] = None,
                        baselines: Optional[Dict[str, Dict[str, Any]]] = None,
                        supersedes_path: str = CANDIDATE_MANIFEST_PATH,
                        campaign_id: Optional[str] = None,
                        code_hash: Optional[str] = None,
                        data_manifest_hash: Optional[str] = None) -> Dict[str, Any]:
    """Freeze at most one candidate per asset under the preregistered rule.

    The written manifest carries the rule that produced it (``rule``), the
    content hash of that rule (``rule_spec_hash``), the manifest it supersedes
    (``supersedes``), the code/data hashes and the per-asset gate table.
    """
    from .config import compute_code_hash, load_research_spec

    if spec is None:
        spec = load_research_spec()
    if baselines is None:
        raise ValueError("the preregistered rule needs the buy-and-hold baseline artifact")
    selection_spec = spec["selection"]

    with open(results_manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    records = []
    campaign_dir = os.path.join(shards_root, manifest["campaign_id"])
    for shard in manifest.get("shards", []):
        shard_path = shard.get("path") or os.path.join(campaign_dir, shard["filename"])
        with open(shard_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    candidates = select_best_candidate(records, spec, baselines)
    supersedes: Dict[str, Any] = {}
    if os.path.exists(supersedes_path):
        with open(supersedes_path, encoding="utf-8") as handle:
            previous = json.load(handle)
        supersedes = {
            "path": supersedes_path,
            "manifest_hash": previous.get("manifest_hash"),
            "freeze_commit": previous.get("freeze_commit"),
            "rule": RULE_LEGACY_PROFIT_FACTOR,
            "reason": ("the v1 manifest was frozen with the non-preregistered "
                       "median-profit-factor rule"),
        }

    out = {
        "frozen": True,
        "manifest_version": 2,
        "rule": RULE_PREREGISTERED,
        "rule_spec_hash": rule_spec_hash(selection_spec),
        "supersedes": supersedes,
        "freeze_commit": freeze_commit,
        "campaign_id": campaign_id or manifest.get("campaign_id"),
        "spec_hash": manifest.get("spec_hash"),
        "code_hash": code_hash or manifest.get("code_hash") or compute_code_hash(),
        "data_manifest_hash": data_manifest_hash or manifest.get("data_manifest_hash"),
        "holdout_exposure": "EXPOSED_OR_UNKNOWN",
        "holdout_reuse": "forbidden",
        "candidate_status": "CANDIDATE_PENDING_HOLDOUT",
        "candidates": candidates,
    }
    save_candidate_manifest(out, output_path)
    return out


def _main():
    parser = argparse.ArgumentParser(description="Freeze best validation candidate per asset.")
    parser.add_argument("--results-manifest", default="research/results_manifest.json")
    parser.add_argument("--shards-root", default="research/results_shards")
    parser.add_argument("--output", default=CANDIDATE_MANIFEST_V2_PATH)
    parser.add_argument("--freeze-commit", default="unknown")
    parser.add_argument("--baselines", default=None,
                        help="baseline artifact (research/baselines/<campaign_id>.json) to consume")
    args = parser.parse_args()
    baselines = None
    if args.baselines:
        from .baselines import baseline_for_asset

        with open(args.baselines, encoding="utf-8") as handle:
            artifact = json.load(handle)
        baselines = {asset: baseline_for_asset(artifact, asset)
                     for asset in artifact.get("assets", {})}
    m = freeze_from_results(args.results_manifest, args.shards_root, args.output,
                            args.freeze_commit, baselines=baselines)
    print(json.dumps({"assets": len(m["candidates"]), "output": args.output}, sort_keys=True))


if __name__ == "__main__":
    _main()

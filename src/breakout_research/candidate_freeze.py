"""Frozen candidate manifest helpers for BRAIN-003 (holdout isolation)."""

import argparse
import hashlib
import json
from statistics import median
from typing import Any, Dict, List

CANDIDATE_MANIFEST_PATH = "research/candidate_manifest.json"


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_manifest_hash(manifest: Dict[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


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


def select_best_candidate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministically select the best validation config per asset.

    Selection criterion (pre-registered, frozen): maximize median profit_factor
    across validation folds/costs, tie-broken by lower median max_drawdown, then
    by lower config_id. Only validation records (is_holdout == False) are used.
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
            score = (median(pfs), -median(dds))
            key = (score[0], score[1], )  # higher better
            # tie-break: higher median pf, lower median dd, then lower config_id
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
                        output_path: str = CANDIDATE_MANIFEST_PATH,
                        freeze_commit: str = "unknown") -> Dict[str, Any]:
    import os
    with open(results_manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    records = []
    campaign_dir = os.path.join(shards_root, manifest["campaign_id"])
    for shard in manifest.get("shards", []):
        shard_path = os.path.join(campaign_dir, shard["filename"])
        with open(shard_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    candidates = select_best_candidate(records)
    out = {
        "frozen": True,
        "freeze_commit": freeze_commit,
        "spec_hash": manifest.get("spec_hash"),
        "code_hash": manifest.get("code_hash"),
        "data_manifest_hash": manifest.get("data_manifest_hash"),
        "candidates": candidates,
    }
    save_candidate_manifest(out, output_path)
    return out


def _main():
    parser = argparse.ArgumentParser(description="Freeze best validation candidate per asset.")
    parser.add_argument("--results-manifest", default="research/results_manifest.json")
    parser.add_argument("--shards-root", default="research/results_shards")
    parser.add_argument("--output", default=CANDIDATE_MANIFEST_PATH)
    parser.add_argument("--freeze-commit", default="unknown")
    args = parser.parse_args()
    m = freeze_from_results(args.results_manifest, args.shards_root, args.output, args.freeze_commit)
    print(json.dumps({"assets": len(m["candidates"]), "output": args.output}, sort_keys=True))


if __name__ == "__main__":
    _main()

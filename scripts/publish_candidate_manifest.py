#!/usr/bin/env python3
"""Publish the new versioned candidate manifest under the preregistered rule.

The conforming selector of ``src/breakout_research/selection.py`` is applied to
the validation records of a campaign cycle, using the buy-and-hold baseline
artifact as the only baseline source.  The result is written as a **new**,
separately versioned manifest (``research/candidate_manifest_v2.json``); the v1
manifest (``research/candidate_manifest.json``) is never modified.

The v1 holdout is already exposed and is never reused: the candidates of this
manifest are ``CANDIDATE_PENDING_HOLDOUT`` and need a fresh confirmatory
period.

Usage:
    PYTHONPATH=src python3 scripts/publish_candidate_manifest.py <cycle_root> \
        --baselines research/baselines/<campaign_id>.json \
        [--out research/candidate_manifest_v2.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.baselines import (  # noqa: E402
    BaselineDataError,
    baseline_for_asset,
    data_manifest_content_hash,
    verify_baseline_artifact,
)
from breakout_research.candidate_freeze import (  # noqa: E402
    CANDIDATE_MANIFEST_PATH,
    CANDIDATE_MANIFEST_V2_PATH,
    RULE_LEGACY_PROFIT_FACTOR,
    RULE_PREREGISTERED,
    rule_spec_hash,
    save_candidate_manifest,
)
from breakout_research.config import compute_code_hash  # noqa: E402
from breakout_research.selection import iter_shard_records, select_candidates  # noqa: E402


def load_json(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_shard_root(cycle_root: Path) -> Path:
    candidates = [path for path in sorted(cycle_root.rglob("*"))
                  if path.is_dir() and any(path.glob("*.jsonl"))]
    if not candidates:
        raise SystemExit(f"no result shards found under {cycle_root}")
    if len(candidates) > 1:
        raise SystemExit(f"ambiguous shard sets under {cycle_root}: {[str(p) for p in candidates]}")
    return candidates[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cycle_root", help="cycle directory containing results_shards/<campaign_id>/")
    parser.add_argument("--baselines", required=True, help="baseline artifact to consume")
    parser.add_argument("--out", default=CANDIDATE_MANIFEST_V2_PATH)
    parser.add_argument("--spec", default=str(REPO_ROOT / "configs" / "research_v1.json"))
    parser.add_argument("--data-manifest", default=str(REPO_ROOT / "research" / "data_manifest.json"))
    parser.add_argument("--config-manifest", default=str(REPO_ROOT / "research" / "config_manifest.json"))
    parser.add_argument("--supersedes", default=CANDIDATE_MANIFEST_PATH)
    parser.add_argument("--freeze-commit", default="unknown")
    args = parser.parse_args(argv)

    cycle_root = Path(args.cycle_root).resolve()
    shard_root = resolve_shard_root(cycle_root)
    campaign_id = shard_root.name

    spec = load_json(Path(args.spec))
    data_manifest = load_json(Path(args.data_manifest))
    config_manifest = load_json(Path(args.config_manifest))
    baseline_artifact = load_json(Path(args.baselines))

    if baseline_artifact.get("campaign_id") != campaign_id:
        raise SystemExit(
            f"baseline artifact belongs to campaign {baseline_artifact.get('campaign_id')}, "
            f"not {campaign_id}")
    try:
        verify_baseline_artifact(baseline_artifact, data_manifest)
    except BaselineDataError as exc:
        raise SystemExit(f"baseline artifact rejected: {exc}")

    dimension_names = list(config_manifest.get("dimensions", {}).keys())
    parameters = {
        entry["config_id"]: {
            **{name: entry[name] for name in dimension_names if name in entry},
            "content_hash": entry.get("content_hash"),
        }
        for entry in config_manifest["configurations"]
    }

    baselines = {asset: baseline_for_asset(baseline_artifact, asset)
                 for asset in baseline_artifact.get("assets", {})}
    selection = select_candidates(iter_shard_records(shard_root), spec, baselines, config_manifest)

    previous: Dict[str, Any] = {}
    if Path(args.supersedes).exists():
        previous = load_json(Path(args.supersedes))
    previous_candidates = previous.get("candidates", {})

    candidates: Dict[str, Any] = {}
    for asset in sorted(selection):
        payload = selection[asset]
        if payload["config_id"] is None:
            continue
        superseded = previous_candidates.get(asset, {}) or {}
        superseded_id = superseded.get("config_id") if isinstance(superseded, dict) else None
        candidates[asset] = {
            "config_id": payload["config_id"],
            "parameters": parameters.get(payload["config_id"]),
            "selection_status": payload["status"],
            "economic_status": payload["economic_status"],
            "gates": payload["gates"],
            "ranking": payload["ranking"],
            "counts": payload["counts"],
            "neighbor_analysis": payload["neighbor_analysis"],
            "superseded_config_id": superseded_id,
            "matches_superseded_manifest": bool(superseded_id) and superseded_id == payload["config_id"],
        }

    manifest: Dict[str, Any] = {
        "frozen": True,
        "manifest_version": 2,
        "rule": RULE_PREREGISTERED,
        "rule_spec_hash": rule_spec_hash(spec["selection"]),
        "supersedes": {
            "path": args.supersedes,
            "manifest_hash": previous.get("manifest_hash"),
            "freeze_commit": previous.get("freeze_commit"),
            "rule": RULE_LEGACY_PROFIT_FACTOR,
            "reason": ("the v1 manifest was frozen with the non-preregistered "
                       "median-profit-factor rule"),
        },
        "freeze_commit": args.freeze_commit,
        "campaign_id": campaign_id,
        "spec_hash": spec.get("specification_hash"),
        "code_hash": compute_code_hash(),
        "data_manifest_hash": data_manifest_content_hash(data_manifest),
        "baseline_artifact_path": str(Path(args.baselines).as_posix()),
        "baseline_artifact_hash": baseline_artifact.get("baseline_hash"),
        "holdout_exposure": "EXPOSED_OR_UNKNOWN",
        "holdout_reuse": "forbidden",
        "holdout_note": ("the v1 holdout was already consumed by the superseded manifest and is "
                         "never reused as confirmation; these candidates need a fresh "
                         "confirmatory period"),
        "candidate_status": "CANDIDATE_PENDING_HOLDOUT",
        "selection_summary": {
            asset: {
                "selection_status": selection[asset]["status"],
                "economic_status": selection[asset]["economic_status"],
                "selected_config_id": selection[asset]["config_id"],
            }
            for asset in sorted(selection)
        },
        "candidates": candidates,
    }
    save_candidate_manifest(manifest, args.out)

    print(json.dumps({
        "output": args.out,
        "assets_with_candidate": len(candidates),
        "selection_status_counts": {
            status: sum(1 for asset in selection if selection[asset]["status"] == status)
            for status in sorted({payload["status"] for payload in selection.values()})
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

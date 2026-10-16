"""Frozen candidate manifest helpers for BRAIN-003 (holdout isolation)."""

import hashlib
import json
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

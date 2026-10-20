"""Frozen scope of the v2 confirmatory evaluation.

The evaluation scope is **exactly** the selected configurations of
``research/v2_selected_configurations_manifest.json``: one configuration per
asset for the 14 assets that survived the v1 selection rule, bound to that
manifest's hash, the selection authorization's hash, the v2 specification hash
and the v2 data manifest hash. The 4 assets without a candidate stay out of
scope and the scope may not be widened, narrowed or re-ranked.

The scope is derived from artifacts that are already hash-bound, so building
it is deterministic and re-running the builder reproduces the same scope. It
never reads a candle and never runs an evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ScopeError

#: The selected-configurations manifest the scope is bound to.
SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE = "research/v2_selected_configurations_manifest.json"

#: The confirmatory-window data manifest the scope is bound to.
CONFIRMATORY_WINDOW_MANIFEST_RELATIVE = "configs/research_v2_confirmatory_window_manifest.json"


def _load(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluation_scope(repo_root: Path = Path(__file__).resolve().parent.parent.parent) -> Dict[str, Any]:
    """Assemble the frozen evaluation scope from the hash-bound artifacts.

    Returns a dict with the in-scope assets, their selected configuration ids,
    the out-of-scope assets and the hashes the scope is bound to. Raises
    :class:`ScopeError` when the manifest is missing or internally inconsistent.
    """
    root = Path(repo_root)
    manifest_path = root / SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE
    if not manifest_path.exists():
        raise ScopeError(f"missing selected-configurations manifest: {manifest_path}")
    manifest = _load(manifest_path)

    selections = manifest.get("selections") or {}
    in_scope: Dict[str, Dict[str, Any]] = {}
    out_of_scope: Dict[str, Dict[str, Any]] = {}
    for asset, entry in sorted(selections.items()):
        if not isinstance(entry, dict):
            raise ScopeError(f"selection entry for {asset} is not an object")
        if entry.get("selected") is True:
            config_id = entry.get("config_id")
            if not config_id:
                raise ScopeError(f"{asset} is marked selected but carries no config_id")
            in_scope[asset] = {
                "asset": asset,
                "config_id": str(config_id),
                "economic_status": entry.get("economic_status"),
                "candidate_status": entry.get("candidate_status"),
            }
        else:
            out_of_scope[asset] = {
                "asset": asset,
                "selected": False,
                "reason": entry.get("reason"),
                "config_id": None,
            }

    window_manifest_path = root / CONFIRMATORY_WINDOW_MANIFEST_RELATIVE
    window_manifest: Dict[str, Any] = {}
    if window_manifest_path.exists():
        window_manifest = _load(window_manifest_path)

    return {
        "selected_configurations_manifest": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
        "selected_configurations_manifest_hash": manifest.get("manifest_hash"),
        "selection_authorization_manifest_hash": (manifest.get("run_identity") or {}).get(
            "authorization_manifest_hash"
        ),
        "v2_specification_hash": (manifest.get("specification_identities") or {}).get("spec_v2_hash"),
        "v2_data_manifest_hash": (manifest.get("data_identities") or {}).get("data_manifest_v2_hash"),
        "confirmatory_window_manifest": CONFIRMATORY_WINDOW_MANIFEST_RELATIVE,
        "confirmatory_window_manifest_hash": window_manifest.get("manifest_hash"),
        "in_scope": in_scope,
        "in_scope_assets": sorted(in_scope),
        "in_scope_count": len(in_scope),
        "out_of_scope_without_candidate": sorted(out_of_scope),
        "out_of_scope_count": len(out_of_scope),
        "scope_may_not_be_widened_narrowed_or_reranked": True,
    }


def selected_configurations(scope: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The ``(asset, config_id)`` pairs the evaluation is bound to, in asset order."""
    pairs = [(asset, entry["config_id"]) for asset, entry in sorted(scope["in_scope"].items())]
    if len(pairs) != scope["in_scope_count"]:
        raise ScopeError("the in-scope set is internally inconsistent")
    return pairs


def assert_scope_unchanged(scope: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    """Refuse a scope that no longer matches the selected-configurations manifest."""
    selections = manifest.get("selections") or {}
    live_in_scope = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    if live_in_scope != scope["in_scope_assets"]:
        raise ScopeError(
            "the evaluation scope no longer matches the selected-configurations manifest: "
            f"recorded {scope['in_scope_assets']}, live {live_in_scope}"
        )
    for asset in scope["in_scope_assets"]:
        recorded_id = scope["in_scope"][asset]["config_id"]
        live_id = (selections.get(asset) or {}).get("config_id")
        if live_id != recorded_id:
            raise ScopeError(
                f"{asset} selected configuration changed: recorded {recorded_id}, live {live_id}"
            )


__all__ = [
    "CONFIRMATORY_WINDOW_MANIFEST_RELATIVE",
    "SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE",
    "assert_scope_unchanged",
    "evaluation_scope",
    "selected_configurations",
]
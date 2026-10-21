#!/usr/bin/env python3
"""Record the v5 selection cycle in the continuous-universe state.

The v5 cycle is recorded from the artifacts that own it, never typed by hand: the
frozen candidate set and the exclusion reasons come from the v5 candidate freeze,
the snapshot identity comes from the v5 snapshot observation, the run identity
comes from the v5 ledger, and the selection outcome comes from the published v5
selected-configurations manifest.

The update is idempotent: the recorded v5 block is derived from the same inputs
every time, so re-running the recorder reproduces the same document.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

STATE_RELATIVE = "research_state/continuous_universe_state.json"
FREEZE_RELATIVE = "configs/research_v5_candidate_freeze.json"
SNAPSHOT_RELATIVE = "research/v5_evidence/snapshot_observation.json"
LEDGER_RELATIVE = "research/ledger_v5.json"
SELECTION_MANIFEST_RELATIVE = "research/v5_selected_configurations_manifest.json"

#: The instant the v5 cycle was recorded. It is pinned so that the recorded state
#: is reproducible: the recorder derives everything else from the artifacts.
UPDATED_UTC = "2026-10-21T21:45:00+00:00"

CYCLE_ID = "v5-selection-20261021"
COHORT_INDEX = 5


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_v5_block(root: Path = REPO_ROOT) -> Dict[str, Any]:
    """The v5 facts the state file records, derived from the artifacts that own them."""
    root = Path(root)
    freeze = _load(root / FREEZE_RELATIVE)
    snapshot = _load(root / SNAPSHOT_RELATIVE)
    ledger = _load(root / LEDGER_RELATIVE)
    manifest = _load(root / SELECTION_MANIFEST_RELATIVE)

    pages = snapshot.get("pages") or []
    if len(pages) != 1:
        raise ValueError(
            "the v5 snapshot observation does not record exactly one retrieval page")
    snapshot_id = str(pages[0].get("raw_response_hash"))

    assets = [
        str(member.get("binance_pair"))
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    ]
    excluded = [
        {"symbol": str(member.get("binance_pair")),
         "exclusion_reason": str(member.get("exclusion_reason"))}
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is not True
    ]

    selections = manifest.get("selections") or {}
    with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected"))
    without_candidate = sorted(
        asset for asset, entry in selections.items() if not entry.get("selected"))

    window = freeze.get("confirmatory_window") or {}
    return {
        "cycle_id": ledger.get("run_id"),
        "snapshot_id": snapshot_id,
        "assets": assets,
        "excluded": excluded,
        "outcome": manifest.get("outcome"),
        "with_candidate": with_candidate,
        "without_candidate": without_candidate,
        "blocking_dependency": (
            f"CONFIRMATORY_WINDOW (earliest end {window.get('earliest_possible_end_utc')})"
        ),
    }


def build(root: Path = REPO_ROOT) -> Dict[str, Any]:
    """The continuous-universe state with the v5 cycle recorded."""
    root = Path(root)
    state = _load(root / STATE_RELATIVE)
    block = build_v5_block(root)

    if block["cycle_id"] != CYCLE_ID:
        raise ValueError(
            f"the v5 ledger names the run {block['cycle_id']!r}, not {CYCLE_ID!r}")

    completed_cycle_ids: List[str] = list(state.get("completed_cycle_ids") or [])
    if CYCLE_ID not in completed_cycle_ids:
        completed_cycle_ids.append(CYCLE_ID)
    completed_snapshot_ids: List[str] = list(state.get("completed_snapshot_ids") or [])
    if block["snapshot_id"] not in completed_snapshot_ids:
        completed_snapshot_ids.append(block["snapshot_id"])

    state["completed_cycle_ids"] = completed_cycle_ids
    state["completed_snapshot_ids"] = completed_snapshot_ids
    state["current_cycle_id"] = CYCLE_ID
    state["current_snapshot"] = {"snapshot_id": block["snapshot_id"]}
    state["current_cohort"] = {
        "assets": block["assets"],
        "cohort_index": COHORT_INDEX,
        "completed": True,
        "excluded": block["excluded"],
    }
    state["next_cohort_index"] = COHORT_INDEX + 1
    state["updated_utc"] = UPDATED_UTC
    state["blocking_dependency"] = block["blocking_dependency"]
    state["v5_selection_outcome"] = block["outcome"]
    state["v5_candidates"] = len(block["with_candidate"])
    state["v5_without_candidate"] = block["without_candidate"]
    state["v5_candidates_with_candidate"] = block["with_candidate"]
    return state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    state = build(REPO_ROOT)
    if args.print:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0
    path = REPO_ROOT / STATE_RELATIVE
    payload = json.dumps(state, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        print(f"{path} is already the recorded v5 state")
        return 0
    if path.exists() and not args.force:
        raise SystemExit(f"{path} differs from the recorded v5 state; pass --force")
    path.write_text(payload, encoding="utf-8")
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

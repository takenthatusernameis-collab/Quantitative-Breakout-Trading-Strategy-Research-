"""Tests for the durable continuous-universe campaign state.

``research_state/continuous_universe_state.json`` is the file every session
reads first (README Section 2A A): it says which cycle is current, which
cohort was completed, what is blocked and what the next cohort index is. A
number in it that is wrong is a silent corruption of the campaign's control
state, so every value is re-derived here from the hash-bound artifacts that
produced it:

* the current cycle id, the selection outcome and the candidate split come
  from ``research/v3_selected_configurations_manifest.json``;
* ``<version>_candidates`` counts the constituents **with** a selected
  configuration, which is the meaning the v2 close-out established
  (``v2_candidates = 14`` for a cohort of 18), so ``v3_candidates`` is 4 and
  not the cohort size 6, and ``v3_candidates + len(v3_without_candidate)`` is
  the cohort size;
* the cohort's assets and the excluded assets are the validated and excluded
  constituents of ``research/universe_manifest_v3.json``, in the manifest's own
  order and with the manifest's own reasons;
* the v2 history is preserved and still agrees with
  ``research/v2_selected_configurations_manifest.json``;
* the snapshot id is **recomputed** from the stored snapshot manifest, the v1
  specification hash and the authorized code hash with the same helper the
  coordinator used, rather than compared with a copied constant;
* the blocking dependency names the confirmatory window's earliest possible
  end, re-derived from the confirmatory protocol, and it is the later of the
  two open gates;
* neither confirmatory window is exposed: the v3 data manifest still records
  ``NOT_STARTED`` and ``holdout_exposed_count = 0``.

The checks are pure functions over a state dictionary, so the tamper controls
feed a mutated **copy** of the state to the same checks and prove that a
wrong count, a wrong cycle id, a widened cohort, a swapped exclusion reason
or a stale blocking dependency is detected.  No test writes into the working
tree, reads a candle or contacts a provider.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.continuous_universe import compute_snapshot_id  # noqa: E402

STATE_RELATIVE = "research_state/continuous_universe_state.json"
V3_SELECTION_RELATIVE = "research/v3_selected_configurations_manifest.json"
V2_SELECTION_RELATIVE = "research/v2_selected_configurations_manifest.json"
V3_UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
V3_DATA_RELATIVE = "research/data_manifest_v3.json"
V2_DATA_RELATIVE = "research/data_manifest_v2.json"
V3_PROTOCOL_RELATIVE = "configs/research_v3_confirmatory_protocol.json"
V2_PROTOCOL_RELATIVE = "configs/research_v2_confirmatory_protocol.json"
V1_SPEC_RELATIVE = "configs/research_v1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
V2_RAW_RESPONSE_RELATIVE = "research/v2_evidence/raw_market_cap_response.json"

#: The pair suffix the campaign uses for a constituent (``SHIB`` -> ``SHIBUSDT``).
PAIR_SUFFIX = "USDT"


def _load(relative: str) -> Dict[str, Any]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _state() -> Dict[str, Any]:
    return _load(STATE_RELATIVE)


def _v3_selection() -> Dict[str, Any]:
    return _load(V3_SELECTION_RELATIVE)


def _v2_selection() -> Dict[str, Any]:
    return _load(V2_SELECTION_RELATIVE)


def _v3_universe() -> Dict[str, Any]:
    return _load(V3_UNIVERSE_RELATIVE)


def _validated_constituents() -> List[str]:
    """The validated constituents of the v3 universe, in the manifest's order."""
    universe = _v3_universe()
    return [
        f"{asset['symbol']}{PAIR_SUFFIX}"
        for asset in universe.get("eligible_assets", [])
        if asset.get("validated")
    ]


def _excluded_constituents() -> List[Dict[str, str]]:
    """The excluded constituents of the v3 universe with their reason."""
    universe = _v3_universe()
    return [
        {
            "symbol": f"{asset['symbol']}{PAIR_SUFFIX}",
            "exclusion_reason": str(asset.get("exclusion_reason")),
        }
        for asset in universe.get("eligible_assets", [])
        if not asset.get("validated")
    ]


def _snapshot_manifest(snapshot_id: str) -> Dict[str, Any]:
    path = REPO_ROOT / "research" / "universe_snapshots" / snapshot_id / "universe_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _exposure_failures(v3_data: Dict[str, Any], v2_data: Dict[str, Any]) -> List[str]:
    """Every way in which a confirmatory window could be exposed."""
    failures: List[str] = []
    for data, label in ((v3_data, "v3"), (v2_data, "v2")):
        window = data.get("confirmatory_window") or {}
        if window.get("holdout_exposed_count") != 0:
            failures.append(f"the {label} confirmatory window records an exposure")
        if window.get("confirmatory_window_status") != "NOT_STARTED":
            failures.append(f"the {label} confirmatory window is not NOT_STARTED")
    return failures


def _state_failures(state: Dict[str, Any]) -> List[str]:
    """Every way in which ``state`` disagrees with the hash-bound artifacts."""
    failures: List[str] = []
    v3_selection = _v3_selection()
    v2_selection = _v2_selection()
    universe = _v3_universe()
    cohort = state.get("current_cohort") or {}

    # -- the schema itself -------------------------------------------------
    if state.get("schema_version") != 1:
        failures.append(f"schema_version is {state.get('schema_version')!r}, expected 1")

    # -- the current cycle -------------------------------------------------
    if state.get("current_cycle_id") != v3_selection.get("run_identity", {}).get("run_id"):
        failures.append(
            f"current_cycle_id is {state.get('current_cycle_id')!r}, the v3 selection run is "
            f"{v3_selection.get('run_identity', {}).get('run_id')!r}"
        )
    if state.get("v3_selection_outcome") != v3_selection.get("outcome"):
        failures.append(
            f"v3_selection_outcome is {state.get('v3_selection_outcome')!r}, the manifest records "
            f"{v3_selection.get('outcome')!r}"
        )

    # -- the candidate split ------------------------------------------------
    with_candidate = list(v3_selection.get("assets_with_candidate", []))
    without_candidate = list(v3_selection.get("assets_without_candidate", []))
    if state.get("v3_candidates") != len(with_candidate):
        failures.append(
            f"v3_candidates is {state.get('v3_candidates')!r}, {len(with_candidate)} constituents "
            "have a selected configuration"
        )
    if state.get("v3_candidates_with_candidate") != with_candidate:
        failures.append("v3_candidates_with_candidate does not match the selection manifest")
    if state.get("v3_without_candidate") != without_candidate:
        failures.append("v3_without_candidate does not match the selection manifest")
    if state.get("v3_candidates") != len(state.get("v3_candidates_with_candidate") or []):
        failures.append("v3_candidates and v3_candidates_with_candidate disagree")

    # -- the cohort ---------------------------------------------------------
    assets = list(cohort.get("assets") or [])
    validated = _validated_constituents()
    if assets != validated:
        failures.append("current_cohort.assets is not the validated v3 cohort")
    if state.get("v3_candidates", 0) + len(state.get("v3_without_candidate") or []) != len(assets):
        failures.append(
            "the candidate split and the cohort size disagree: "
            f"{state.get('v3_candidates')} + {len(state.get('v3_without_candidate') or [])} != "
            f"{len(assets)}"
        )
    if cohort.get("completed") is not True:
        failures.append("current_cohort is not marked completed")
    if not isinstance(cohort.get("cohort_index"), int):
        failures.append("current_cohort.cohort_index is not an integer")
    elif state.get("next_cohort_index") != cohort.get("cohort_index") + 1:
        failures.append("next_cohort_index is not the cohort index plus one")
    if cohort.get("excluded") != _excluded_constituents():
        failures.append("current_cohort.excluded does not match the v3 universe manifest")
    summary = universe.get("validation_summary") or {}
    if summary.get("validated_count") != len(validated):
        failures.append("the v3 universe manifest's validated_count disagrees with its own assets")

    # -- the preserved v2 history ------------------------------------------
    v2_with_candidate = list(v2_selection.get("assets_with_candidate", []))
    if state.get("v2_selection_outcome") != v2_selection.get("outcome"):
        failures.append("v2_selection_outcome does not match the v2 selection manifest")
    if state.get("v2_candidates") != len(v2_with_candidate):
        failures.append(
            f"v2_candidates is {state.get('v2_candidates')!r}, the v2 selection manifest records "
            f"{len(v2_with_candidate)} constituents with a candidate"
        )
    if state.get("v2_without_candidate") != list(v2_selection.get("assets_without_candidate", [])):
        failures.append("v2_without_candidate does not match the v2 selection manifest")

    # -- the completed cycle and snapshot ids ------------------------------
    completed_cycles = list(state.get("completed_cycle_ids") or [])
    for cycle_id in (v2_selection.get("run_identity", {}).get("run_id"), v3_selection.get("run_identity", {}).get("run_id")):
        if cycle_id not in completed_cycles:
            failures.append(f"the completed cycle id {cycle_id!r} is not recorded")
    snapshot_id = (state.get("current_snapshot") or {}).get("snapshot_id")
    completed_snapshots = list(state.get("completed_snapshot_ids") or [])
    v2_snapshot_id = hashlib.sha256(
        (REPO_ROOT / V2_RAW_RESPONSE_RELATIVE).read_bytes()
    ).hexdigest()
    if v2_snapshot_id not in completed_snapshots:
        failures.append(
            "the v2 snapshot id (the sha256 of the stored raw market-cap response) is not recorded"
        )
    if not snapshot_id:
        failures.append("current_snapshot.snapshot_id is missing")
    else:
        if snapshot_id not in completed_snapshots:
            failures.append("the current snapshot id is not in completed_snapshot_ids")
        manifest_path = (
            REPO_ROOT / "research" / "universe_snapshots" / snapshot_id / "universe_manifest.json"
        )
        if not manifest_path.exists():
            failures.append(f"the snapshot manifest of {snapshot_id!r} does not exist")
        else:
            specification_hash = _load(V1_SPEC_RELATIVE).get("specification_hash")
            code_hash = _load(AUTHORIZATION_RELATIVE).get("code_hash")
            recomputed = compute_snapshot_id(
                _snapshot_manifest(snapshot_id), specification_hash, code_hash
            )
            if recomputed != snapshot_id:
                failures.append(
                    f"the snapshot id does not recompute: {recomputed!r} != {snapshot_id!r}"
                )

    # -- the blocking dependency -------------------------------------------
    v3_earliest_end = (
        _load(V3_PROTOCOL_RELATIVE).get("window_definition") or {}
    ).get("earliest_possible_end_utc")
    v2_earliest_end = (
        _load(V2_PROTOCOL_RELATIVE).get("window_definition") or {}
    ).get("earliest_possible_end_utc")
    blocking = str(state.get("blocking_dependency") or "")
    if v3_earliest_end and v3_earliest_end not in blocking:
        failures.append(
            f"blocking_dependency does not name the v3 confirmatory window's earliest end "
            f"{v3_earliest_end!r}"
        )
    if v2_earliest_end and v2_earliest_end in blocking:
        failures.append("blocking_dependency names the earlier v2 confirmatory window")
    if v2_earliest_end and v3_earliest_end and v3_earliest_end < v2_earliest_end:
        failures.append("the recorded blocking dependency is not the later of the two gates")

    # -- the confirmatory windows are unexposed ----------------------------
    failures.extend(_exposure_failures(_load(V3_DATA_RELATIVE), _load(V2_DATA_RELATIVE)))

    return failures


def test_the_campaign_state_is_consistent_with_the_hash_bound_artifacts() -> None:
    failures = _state_failures(_state())
    assert failures == [], failures


def test_the_state_file_is_valid_json_with_the_frozen_schema_version() -> None:
    state = _state()
    assert isinstance(state, dict)
    assert state["schema_version"] == 1
    for key in (
        "current_cycle_id",
        "completed_cycle_ids",
        "completed_snapshot_ids",
        "current_cohort",
        "current_snapshot",
        "next_cohort_index",
        "updated_utc",
        "blocking_dependency",
    ):
        assert key in state, key


def test_the_candidate_count_is_the_number_of_constituents_with_a_candidate() -> None:
    state = _state()
    with_candidate = _v3_selection()["assets_with_candidate"]
    assert state["v3_candidates"] == len(with_candidate) == 4
    assert state["v3_candidates"] != len(state["current_cohort"]["assets"])


def test_the_candidate_split_covers_the_cohort_exactly_once() -> None:
    state = _state()
    cohort = set(state["current_cohort"]["assets"])
    with_candidate = set(state["v3_candidates_with_candidate"])
    without_candidate = set(state["v3_without_candidate"])
    assert with_candidate & without_candidate == set()
    assert with_candidate | without_candidate == cohort


def test_the_cohort_is_the_validated_constituents_of_the_v3_universe() -> None:
    state = _state()
    assert state["current_cohort"]["assets"] == _validated_constituents()
    assert state["current_cohort"]["excluded"] == _excluded_constituents()


def test_the_v2_history_is_preserved_and_still_agrees_with_its_manifest() -> None:
    state = _state()
    v2_selection = _v2_selection()
    assert state["v2_selection_outcome"] == v2_selection["outcome"]
    assert state["v2_candidates"] == len(v2_selection["assets_with_candidate"])
    assert state["v2_without_candidate"] == v2_selection["assets_without_candidate"]


def test_the_snapshot_id_is_recomputed_from_the_stored_snapshot() -> None:
    state = _state()
    snapshot_id = state["current_snapshot"]["snapshot_id"]
    specification_hash = _load(V1_SPEC_RELATIVE)["specification_hash"]
    code_hash = _load(AUTHORIZATION_RELATIVE)["code_hash"]
    assert compute_snapshot_id(
        _snapshot_manifest(snapshot_id), specification_hash, code_hash
    ) == snapshot_id


def test_the_blocking_dependency_names_the_later_confirmatory_gate() -> None:
    state = _state()
    v3_end = _load(V3_PROTOCOL_RELATIVE)["window_definition"]["earliest_possible_end_utc"]
    v2_end = _load(V2_PROTOCOL_RELATIVE)["window_definition"]["earliest_possible_end_utc"]
    assert v3_end in state["blocking_dependency"]
    assert v2_end not in state["blocking_dependency"]


def test_no_confirmatory_window_is_exposed() -> None:
    for relative in (V3_DATA_RELATIVE, V2_DATA_RELATIVE):
        window = _load(relative)["confirmatory_window"]
        assert window["holdout_exposed_count"] == 0
        assert window["confirmatory_window_status"] == "NOT_STARTED"


def test_the_checks_detect_a_wrong_candidate_count() -> None:
    state = copy.deepcopy(_state())
    state["v3_candidates"] = len(state["current_cohort"]["assets"])
    failures = _state_failures(state)
    assert any("v3_candidates" in failure for failure in failures), failures


def test_the_checks_detect_a_widened_candidate_split() -> None:
    state = copy.deepcopy(_state())
    state["v3_candidates_with_candidate"] = state["v3_candidates_with_candidate"] + ["AAVEUSDT"]
    failures = _state_failures(state)
    assert failures, failures


def test_the_checks_detect_a_wrong_cycle_id() -> None:
    state = copy.deepcopy(_state())
    state["current_cycle_id"] = "v2-selection-run-2026-10-20"
    failures = _state_failures(state)
    assert any("current_cycle_id" in failure for failure in failures), failures


def test_the_checks_detect_a_widened_cohort() -> None:
    state = copy.deepcopy(_state())
    state["current_cohort"]["assets"] = state["current_cohort"]["assets"] + ["DOGEUSDT"]
    failures = _state_failures(state)
    assert failures, failures


def test_the_checks_detect_a_swapped_exclusion_reason() -> None:
    state = copy.deepcopy(_state())
    state["current_cohort"]["excluded"][0]["exclusion_reason"] = "binance_spot_unavailable"
    failures = _state_failures(state)
    assert failures, failures


def test_the_checks_detect_a_stale_blocking_dependency() -> None:
    state = copy.deepcopy(_state())
    state["blocking_dependency"] = "CONFIRMATORY_WINDOW (earliest end 2027-01-17T22:00:00Z)"
    failures = _state_failures(state)
    assert failures, failures


def test_the_checks_detect_a_next_cohort_index_that_does_not_advance() -> None:
    state = copy.deepcopy(_state())
    state["next_cohort_index"] = state["current_cohort"]["cohort_index"]
    failures = _state_failures(state)
    assert any("next_cohort_index" in failure for failure in failures), failures


def test_the_checks_detect_an_exposed_confirmatory_window() -> None:
    v3_data = copy.deepcopy(_load(V3_DATA_RELATIVE))
    v3_data["confirmatory_window"]["holdout_exposed_count"] = 1
    failures = _exposure_failures(v3_data, _load(V2_DATA_RELATIVE))
    assert any("exposure" in failure for failure in failures), failures
    started = copy.deepcopy(_load(V2_DATA_RELATIVE))
    started["confirmatory_window"]["confirmatory_window_status"] = "EXPOSED"
    failures = _exposure_failures(_load(V3_DATA_RELATIVE), started)
    assert any("NOT_STARTED" in failure for failure in failures), failures

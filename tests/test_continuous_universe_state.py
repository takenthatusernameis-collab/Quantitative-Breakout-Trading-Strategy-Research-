"""Tests for the durable continuous-universe campaign state.

``research_state/continuous_universe_state.json`` is the file every session
reads first (README Section 2A A): it says which cycle is current, which
cohort was completed, what is blocked and what the next cohort index is. A
number in it that is wrong is a silent corruption of the campaign's control
state, so every value is re-derived here from the hash-bound artifacts that
produced it.

The file is **version-aware**: every published selection cycle (v2, v3, v4, v5)
contributes one row to the table below, and the checks are written against
that table rather than against one hard-coded version. A new cycle therefore
extends the table instead of rewriting the checks, and a stale check that
still expects the previous version as the current one fails loudly.

For the **current** cycle the checks are:

* the current cycle id, the selection outcome and the candidate split come
  from the published selection manifest of the current version;
* ``<version>_candidates`` counts the constituents **with** a selected
  configuration, which is the meaning the v2 close-out established
  (``v2_candidates = 14`` for a cohort of 18), so ``v3_candidates`` is 4 and
  not the cohort size 6, and ``v4_candidates`` is 5 and not the cohort size
  7; ``<version>_candidates + len(<version>_without_candidate)`` is the
  cohort size;
* the cohort's assets and the excluded assets are the validated and excluded
  constituents of that version's universe manifest, in the manifest's own
  order and with the manifest's own reasons;
* the cohort index advances by one per completed cycle and the next cohort
  index is the cohort index plus one;
* the earlier cycles are preserved and still agree with their own published
  selection manifests;
* the snapshot id is **recomputed** from the stored evidence with the rule
  that belongs to the current version -- the sha256 of the stored raw
  market-cap response for the v2, v4 and v5 cycles, the canonical
  ``compute_snapshot_id`` over the stored snapshot manifest for the v3 cycle;
* the blocking dependency names the **latest** of the open confirmatory
  gates, re-derived from the confirmatory protocols and from the candidate
  freeze of the version that has no protocol yet;
* no confirmatory window is exposed: every data manifest still records
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.continuous_universe import compute_snapshot_id  # noqa: E402

STATE_RELATIVE = "research_state/continuous_universe_state.json"
V1_SPEC_RELATIVE = "configs/research_v1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"

#: The pair suffix the campaign uses for a constituent (``SHIB`` -> ``SHIBUSDT``).
PAIR_SUFFIX = "USDT"


@dataclass(frozen=True)
class Cycle:
    """One published selection cycle of the continuous universe."""

    version: str
    selection_relative: str
    universe_relative: str
    data_relative: str
    cohort_index: int
    #: The rule that re-derives the cycle's snapshot id from the stored evidence.
    snapshot_rule: str
    #: The artifact the snapshot rule reads.
    snapshot_evidence_relative: str
    #: The instant at which the version's confirmatory window can first end.
    gate_relative: str
    gate_pointer: Tuple[str, ...]


CYCLES: Tuple[Cycle, ...] = (
    Cycle(
        version="v2",
        selection_relative="research/v2_selected_configurations_manifest.json",
        universe_relative="research/universe_manifest_v2.json",
        data_relative="research/data_manifest_v2.json",
        cohort_index=2,
        snapshot_rule="raw_response_sha256",
        snapshot_evidence_relative="research/v2_evidence/raw_market_cap_response.json",
        gate_relative="configs/research_v2_confirmatory_protocol.json",
        gate_pointer=("window_definition", "earliest_possible_end_utc"),
    ),
    Cycle(
        version="v3",
        selection_relative="research/v3_selected_configurations_manifest.json",
        universe_relative="research/universe_manifest_v3.json",
        data_relative="research/data_manifest_v3.json",
        cohort_index=3,
        snapshot_rule="canonical_snapshot_manifest",
        snapshot_evidence_relative="",
        gate_relative="configs/research_v3_confirmatory_protocol.json",
        gate_pointer=("window_definition", "earliest_possible_end_utc"),
    ),
    Cycle(
        version="v4",
        selection_relative="research/v4_selected_configurations_manifest.json",
        universe_relative="research/universe_manifest_v4.json",
        data_relative="research/data_manifest_v4.json",
        cohort_index=4,
        snapshot_rule="raw_response_sha256",
        snapshot_evidence_relative="research/v4_evidence/raw_market_cap_response.json",
        gate_relative="configs/research_v4_candidate_freeze.json",
        gate_pointer=("confirmatory_window", "earliest_possible_end_utc"),
    ),
    Cycle(
        version="v5",
        selection_relative="research/v5_selected_configurations_manifest.json",
        universe_relative="research/universe_manifest_v5.json",
        data_relative="research/data_manifest_v5.json",
        cohort_index=5,
        snapshot_rule="raw_response_sha256",
        snapshot_evidence_relative="research/v5_evidence/raw_market_cap_response.json",
        gate_relative="configs/research_v5_candidate_freeze.json",
        gate_pointer=("confirmatory_window", "earliest_possible_end_utc"),
    ),
)


def _load(relative: str) -> Dict[str, Any]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _state() -> Dict[str, Any]:
    return _load(STATE_RELATIVE)


def _dig(document: Dict[str, Any], pointer: Tuple[str, ...]) -> Any:
    current: Any = document
    for key in pointer:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _pairs(cycle: Cycle) -> Tuple[List[str], List[Dict[str, str]]]:
    """The validated and the excluded constituents of a cycle's universe.

    The v2 and v3 manifests name a constituent with ``symbol`` and the v4 and
    v5 manifests with ``binance_pair``; both are accepted, and the manifest's
    own order is preserved.
    """
    universe = _load(cycle.universe_relative)
    validated: List[str] = []
    excluded: List[Dict[str, str]] = []
    for entry in universe.get("eligible_assets", []):
        symbol = str(entry.get("binance_pair") or f"{entry.get('symbol')}{PAIR_SUFFIX}")
        is_validated = (
            entry.get("validated") is True
            and entry.get("exclusion_reason") is None
        )
        if is_validated:
            validated.append(symbol)
        else:
            excluded.append({
                "symbol": symbol,
                "exclusion_reason": str(entry.get("exclusion_reason")),
            })
    return validated, excluded


def _canonical_snapshot_id() -> str:
    """The id of the unique self-consistent snapshot directory.

    A snapshot directory is named by the canonical snapshot id computed from
    its own manifest with the v1 specification hash and the authorized code
    hash, so the id is re-derived from the repository and not read out of the
    state file.  Exactly one directory satisfies the rule; more than one or
    none is a failure of the repository, not of the state.
    """
    specification_hash = _load(V1_SPEC_RELATIVE).get("specification_hash")
    code_hash = _load(AUTHORIZATION_RELATIVE).get("code_hash")
    consistent: List[str] = []
    root = REPO_ROOT / "research" / "universe_snapshots"
    for directory in sorted(root.iterdir()):
        manifest_path = directory / "universe_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if compute_snapshot_id(manifest, specification_hash, code_hash) == directory.name:
            consistent.append(directory.name)
    if len(consistent) != 1:
        raise AssertionError(
            f"expected exactly one self-consistent snapshot directory, found {consistent}"
        )
    return consistent[0]


def _snapshot_id(cycle: Cycle) -> str:
    """The cycle's snapshot id, re-derived from the stored evidence."""
    if cycle.snapshot_rule == "raw_response_sha256":
        return hashlib.sha256(
            (REPO_ROOT / cycle.snapshot_evidence_relative).read_bytes()
        ).hexdigest()
    if cycle.snapshot_rule == "canonical_snapshot_manifest":
        return _canonical_snapshot_id()
    raise ValueError(f"unknown snapshot rule {cycle.snapshot_rule!r}")


def _current_cycle(state: Dict[str, Any]) -> Optional[Cycle]:
    """The cycle whose published run id is the state's current cycle id."""
    cycle_id = state.get("current_cycle_id")
    for cycle in CYCLES:
        selection = _load(cycle.selection_relative)
        if selection.get("run_identity", {}).get("run_id") == cycle_id:
            return cycle
    return None


def _exposure_failures(cycles: Tuple[Cycle, ...],
                       overrides: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Every way in which a confirmatory window could be exposed.

    ``overrides`` replaces the data manifest of a version, so that a tamper
    control can feed a mutated **copy** to the same checks.
    """
    failures: List[str] = []
    for cycle in cycles:
        data = (overrides or {}).get(cycle.version) or _load(cycle.data_relative)
        window = data.get("confirmatory_window") or {}
        if window.get("holdout_exposed_count") != 0:
            failures.append(f"the {cycle.version} confirmatory window records an exposure")
        if window.get("confirmatory_window_status") != "NOT_STARTED":
            failures.append(f"the {cycle.version} confirmatory window is not NOT_STARTED")
    return failures


def _state_failures(state: Dict[str, Any]) -> List[str]:
    """Every way in which ``state`` disagrees with the hash-bound artifacts."""
    failures: List[str] = []

    # -- the schema itself -------------------------------------------------
    if state.get("schema_version") != 1:
        failures.append(f"schema_version is {state.get('schema_version')!r}, expected 1")

    # -- the current cycle -------------------------------------------------
    cycle = _current_cycle(state)
    if cycle is None:
        published = [
            _load(item.selection_relative).get("run_identity", {}).get("run_id")
            for item in CYCLES
        ]
        failures.append(
            f"current_cycle_id is {state.get('current_cycle_id')!r}, which is not a "
            f"published selection cycle {published}"
        )
        return failures

    selection = _load(cycle.selection_relative)
    cohort = state.get("current_cohort") or {}
    validated, excluded = _pairs(cycle)

    if state.get(f"{cycle.version}_selection_outcome") != selection.get("outcome"):
        failures.append(
            f"{cycle.version}_selection_outcome does not match the {cycle.version} "
            "selection manifest"
        )

    # -- the candidate split ------------------------------------------------
    with_candidate = list(selection.get("assets_with_candidate", []))
    without_candidate = list(selection.get("assets_without_candidate", []))
    if state.get(f"{cycle.version}_candidates") != len(with_candidate):
        failures.append(
            f"{cycle.version}_candidates is {state.get(f'{cycle.version}_candidates')!r}, "
            f"{len(with_candidate)} constituents have a selected configuration"
        )
    if state.get(f"{cycle.version}_candidates_with_candidate") != with_candidate:
        failures.append(
            f"{cycle.version}_candidates_with_candidate does not match the selection manifest"
        )
    if state.get(f"{cycle.version}_without_candidate") != without_candidate:
        failures.append(
            f"{cycle.version}_without_candidate does not match the selection manifest"
        )
    if state.get(f"{cycle.version}_candidates") != len(
            state.get(f"{cycle.version}_candidates_with_candidate") or []):
        failures.append(
            f"{cycle.version}_candidates and {cycle.version}_candidates_with_candidate disagree"
        )

    # -- the cohort ---------------------------------------------------------
    assets = list(cohort.get("assets") or [])
    if assets != validated:
        failures.append(f"current_cohort.assets is not the validated {cycle.version} cohort")
    if state.get(f"{cycle.version}_candidates", 0) + len(
            state.get(f"{cycle.version}_without_candidate") or []) != len(assets):
        failures.append(
            "the candidate split and the cohort size disagree: "
            f"{state.get(f'{cycle.version}_candidates')} + "
            f"{len(state.get(f'{cycle.version}_without_candidate') or [])} != {len(assets)}"
        )
    if cohort.get("completed") is not True:
        failures.append("current_cohort is not marked completed")
    if cohort.get("cohort_index") != cycle.cohort_index:
        failures.append(
            f"current_cohort.cohort_index is {cohort.get('cohort_index')!r}, the "
            f"{cycle.version} cycle is cohort {cycle.cohort_index}"
        )
    if not isinstance(cohort.get("cohort_index"), int):
        failures.append("current_cohort.cohort_index is not an integer")
    elif state.get("next_cohort_index") != cohort.get("cohort_index") + 1:
        failures.append("next_cohort_index is not the cohort index plus one")
    if cohort.get("excluded") != excluded:
        failures.append(
            f"current_cohort.excluded does not match the {cycle.version} universe manifest"
        )
    universe = _load(cycle.universe_relative)
    summary = universe.get("validation_summary") or {}
    if summary.get("validated_count") != len(validated):
        failures.append(
            f"the {cycle.version} universe manifest's validated_count disagrees with its "
            "own assets"
        )

    # -- the preserved history of the earlier cycles ------------------------
    for item in CYCLES:
        if item.version == cycle.version:
            continue
        earlier = _load(item.selection_relative)
        if state.get(f"{item.version}_selection_outcome") != earlier.get("outcome"):
            failures.append(
                f"{item.version}_selection_outcome does not match the {item.version} "
                "selection manifest"
            )
        if state.get(f"{item.version}_candidates") != len(
                earlier.get("assets_with_candidate", [])):
            failures.append(
                f"{item.version}_candidates does not match the {item.version} selection "
                "manifest"
            )
        if state.get(f"{item.version}_without_candidate") != list(
                earlier.get("assets_without_candidate", [])):
            failures.append(
                f"{item.version}_without_candidate does not match the {item.version} "
                "selection manifest"
            )

    # -- the completed cycle and snapshot ids ------------------------------
    completed_cycles = list(state.get("completed_cycle_ids") or [])
    for item in CYCLES:
        run_id = _load(item.selection_relative).get("run_identity", {}).get("run_id")
        if run_id not in completed_cycles:
            failures.append(f"the completed cycle id {run_id!r} is not recorded")
    completed_snapshots = list(state.get("completed_snapshot_ids") or [])
    snapshot_id = (state.get("current_snapshot") or {}).get("snapshot_id")
    if not snapshot_id:
        failures.append("current_snapshot.snapshot_id is missing")
    else:
        if snapshot_id not in completed_snapshots:
            failures.append("the current snapshot id is not in completed_snapshot_ids")
        recomputed = _snapshot_id(cycle)
        if recomputed != snapshot_id:
            failures.append(
                f"the snapshot id does not recompute: {recomputed!r} != {snapshot_id!r}"
            )
    for item in CYCLES:
        if item.version == cycle.version or item.snapshot_rule != "raw_response_sha256":
            continue
        evidence = hashlib.sha256(
            (REPO_ROOT / item.snapshot_evidence_relative).read_bytes()
        ).hexdigest()
        if evidence not in completed_snapshots:
            failures.append(
                f"the {item.version} snapshot id (the sha256 of the stored raw "
                "market-cap response) is not recorded"
            )

    # -- the blocking dependency -------------------------------------------
    gates: List[Tuple[str, str]] = []
    for item in CYCLES:
        gate = _dig(_load(item.gate_relative), item.gate_pointer)
        if gate:
            gates.append((item.version, str(gate)))
    if not gates:
        failures.append("no confirmatory gate could be re-derived")
    else:
        latest_version, latest_gate = max(gates, key=lambda item: item[1])
        blocking = str(state.get("blocking_dependency") or "")
        if latest_gate not in blocking:
            failures.append(
                f"blocking_dependency does not name the {latest_version} confirmatory "
                f"window's earliest end {latest_gate!r}"
            )
        for version, gate in gates:
            if gate != latest_gate and gate in blocking:
                failures.append(
                    f"blocking_dependency names the earlier {version} confirmatory window"
                )

    # -- the confirmatory windows are unexposed ----------------------------
    failures.extend(_exposure_failures(CYCLES))

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


def test_the_current_cycle_is_the_latest_published_cycle() -> None:
    state = _state()
    cycle = _current_cycle(state)
    assert cycle is not None
    assert cycle is CYCLES[-1]


def test_the_candidate_count_is_the_number_of_constituents_with_a_candidate() -> None:
    state = _state()
    cycle = _current_cycle(state)
    selection = _load(cycle.selection_relative)
    with_candidate = selection["assets_with_candidate"]
    assert state[f"{cycle.version}_candidates"] == len(with_candidate)
    assert state[f"{cycle.version}_candidates"] != len(state["current_cohort"]["assets"])


def test_the_candidate_split_covers_the_cohort_exactly_once() -> None:
    state = _state()
    cycle = _current_cycle(state)
    cohort = set(state["current_cohort"]["assets"])
    with_candidate = set(state[f"{cycle.version}_candidates_with_candidate"])
    without_candidate = set(state[f"{cycle.version}_without_candidate"])
    assert with_candidate & without_candidate == set()
    assert with_candidate | without_candidate == cohort


def test_the_cohort_is_the_validated_constituents_of_the_current_universe() -> None:
    state = _state()
    cycle = _current_cycle(state)
    validated, excluded = _pairs(cycle)
    assert state["current_cohort"]["assets"] == validated
    assert state["current_cohort"]["excluded"] == excluded


def test_the_earlier_cycles_are_preserved_and_agree_with_their_manifests() -> None:
    state = _state()
    for item in CYCLES[:-1]:
        selection = _load(item.selection_relative)
        assert state[f"{item.version}_selection_outcome"] == selection["outcome"]
        assert state[f"{item.version}_candidates"] == len(selection["assets_with_candidate"])
        assert (state[f"{item.version}_without_candidate"]
                == selection["assets_without_candidate"])


def test_the_snapshot_id_is_recomputed_from_the_stored_evidence() -> None:
    state = _state()
    cycle = _current_cycle(state)
    assert _snapshot_id(cycle) == state["current_snapshot"]["snapshot_id"]


def test_the_blocking_dependency_names_the_later_confirmatory_gate() -> None:
    state = _state()
    gates = [
        str(_dig(_load(item.gate_relative), item.gate_pointer)) for item in CYCLES
    ]
    latest = max(gate for gate in gates if gate)
    assert latest in state["blocking_dependency"]
    for gate in gates:
        if gate != latest:
            assert gate not in state["blocking_dependency"]


def test_no_confirmatory_window_is_exposed() -> None:
    for item in CYCLES:
        window = _load(item.data_relative)["confirmatory_window"]
        assert window["holdout_exposed_count"] == 0
        assert window["confirmatory_window_status"] == "NOT_STARTED"


def test_the_checks_detect_a_wrong_candidate_count() -> None:
    state = copy.deepcopy(_state())
    cycle = _current_cycle(state)
    state[f"{cycle.version}_candidates"] = len(state["current_cohort"]["assets"])
    failures = _state_failures(state)
    assert any(f"{cycle.version}_candidates" in failure for failure in failures), failures


def test_the_checks_detect_a_widened_candidate_split() -> None:
    state = copy.deepcopy(_state())
    cycle = _current_cycle(state)
    without = state[f"{cycle.version}_without_candidate"]
    state[f"{cycle.version}_without_candidate"] = without + ["AAVEUSDT"]
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
    state["current_cohort"]["excluded"][0]["exclusion_reason"] = "insufficient_hourly_history"
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


def test_the_checks_detect_a_cohort_index_that_does_not_advance() -> None:
    state = copy.deepcopy(_state())
    state["current_cohort"]["cohort_index"] = state["current_cohort"]["cohort_index"] - 1
    failures = _state_failures(state)
    assert any("cohort_index" in failure for failure in failures), failures


def test_the_checks_detect_an_exposed_confirmatory_window() -> None:
    exposed = copy.deepcopy(_load(CYCLES[-1].data_relative))
    exposed["confirmatory_window"]["holdout_exposed_count"] = 1
    failures = _exposure_failures(CYCLES, {CYCLES[-1].version: exposed})
    assert any("exposure" in failure for failure in failures), failures
    started = copy.deepcopy(_load(CYCLES[0].data_relative))
    started["confirmatory_window"]["confirmatory_window_status"] = "EXPOSED"
    failures = _exposure_failures(CYCLES, {CYCLES[0].version: started})
    assert any("NOT_STARTED" in failure for failure in failures), failures

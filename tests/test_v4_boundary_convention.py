"""Tests for the v4 development-data boundary convention.

Defect record (repaired in the session that added this module). The v4 chain
stated the development-data boundary in **two different conventions**:

* the candidate freeze, the execution protocol and the v4 data manifest stated
  it *exclusively* -- "no development candle closes at or after the cutoff" --
  which forbids the candle that closes exactly at the boundary;
* the selection authorization, the execution path
  (``src/v4_campaign/data.py``), the delivered datasets and the frozen v2 and v3
  candidate freezes state it *inclusively* -- a candle that closes at or before
  the boundary is development data, and only a candle that closes after it is
  forbidden.

Read literally, the exclusive statements forbade the last candle of every
delivered v4 dataset (each of them ends with the candle that closes exactly at
the preregistered cutoff, 2026-10-20T13:00:00Z). The inclusive convention is
the correct one: that candle covers the hour [12:00Z, 13:00Z) and therefore
contains no instant inside the open v3 confirmatory window, which opens at
13:00:00Z. The exclusive convention was also impossible to satisfy, because the
datasets must hold at least 26,280 closed hourly candles.

These tests pin the convention: every artifact that states the rule states it
in the same inclusive way, the data implements it, the execution path enforces
it, and the verifier refuses an artifact that states it exclusively.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

HOUR_MS = 3_600_000

FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
EXECUTION_RELATIVE = "configs/research_v4_execution.json"
AUTHORIZATION_RELATIVE = "configs/research_v4_selection_authorization_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

#: Phrasings that state the boundary exclusively.
EXCLUSIVE_MARKERS = (
    "closes at or after",
    "at or after the cutoff",
    "at or after that instant",
)

#: Phrasings that state the boundary inclusively.
INCLUSIVE_MARKERS = (
    "at or before",
    "closes exactly at",
    "closes after",
    "after that instant",
)

EXCLUSIVE_RULE = (
    "no development candle closes at or after the preregistered development cutoff"
)


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v4_selection_authorization_1",
    "scripts/verify_v4_selection_authorization_1.py",
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads."""
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {
        Path("research/results_shards"),
        Path("research/campaign_cycles"),
        Path("research/shards_v2"),
        Path("research/shards_v3"),
        Path("research/shards_v4"),
    }
    copy_relative = {Path(HASHED_SET_ROOT), Path(EXECUTION_PATH_ROOT)}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in skip_relative:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if relative in copy_relative or any(
                root_path in relative.parents for root_path in copy_relative
            ):
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def _rule_texts(root: Path = REPO_ROOT) -> Dict[str, str]:
    """Every v4 statement of the development-data boundary rule."""
    freeze = _load(root / FREEZE_RELATIVE)
    execution = _load(root / EXECUTION_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    data = _load(root / DATA_MANIFEST_RELATIVE)
    return {
        "the candidate freeze (development_data_rule)": freeze["data_boundary"][
            "development_data_rule"
        ],
        "the candidate freeze (development_cutoff_rule)": freeze["data_boundary"][
            "development_cutoff_rule"
        ],
        "the execution protocol": execution["candidate_freeze_and_confirmatory_window"][
            "development_data_boundary_rule"
        ],
        "the selection authorization": authorization["authorized_run"]["data_boundary"][
            "candles_before_utc_rule"
        ],
        "the data manifest": data["confirmatory_window"]["note"],
    }


# --------------------------------------------------------------------------
# the convention itself
# --------------------------------------------------------------------------


def test_every_artifact_states_the_inclusive_boundary_convention() -> None:
    texts = _rule_texts()
    assert len(texts) == 5
    for label, text in texts.items():
        assert isinstance(text, str) and text, label
        for marker in EXCLUSIVE_MARKERS:
            assert marker not in text, f"{label} states the boundary exclusively: {marker!r}"
        assert any(marker in text for marker in INCLUSIVE_MARKERS), label


def test_the_frozen_v2_and_v3_freezes_state_the_same_convention() -> None:
    for relative in (
        "configs/research_v2_candidate_freeze.json",
        "configs/research_v3_candidate_freeze.json",
    ):
        rule = _load(REPO_ROOT / relative)["data_boundary"]["development_data_rule"]
        assert "at or before" in rule, relative
        for marker in EXCLUSIVE_MARKERS:
            assert marker not in rule, f"{relative}: {marker!r}"


def test_every_validated_dataset_ends_with_the_candle_that_closes_at_the_boundary() -> None:
    data = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    cutoff = _load(REPO_ROOT / SPEC_V4_RELATIVE)["holdout"]["development_cutoff_utc"]
    assert cutoff == "2026-10-20T13:00:00Z"
    cutoff_ms = _parse_utc_ms(cutoff)
    validated = [
        (pair, entry)
        for pair, entry in (data.get("assets") or {}).items()
        if entry.get("validated") is True
    ]
    assert validated
    for pair, entry in validated:
        assert int(entry["last_candle_timestamp"]) + HOUR_MS == cutoff_ms, pair


def test_the_three_artifacts_agree_on_the_effective_boundary() -> None:
    freeze = _load(REPO_ROOT / FREEZE_RELATIVE)
    execution = _load(REPO_ROOT / EXECUTION_RELATIVE)
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    effective = freeze["data_boundary"]["effective_data_boundary_utc"]
    assert effective == freeze["data_boundary"]["development_cutoff_utc"]
    assert execution["candidate_freeze_and_confirmatory_window"][
        "development_data_boundary_utc"
    ] == effective
    assert execution["candidate_freeze_and_confirmatory_window"][
        "development_cutoff_utc"
    ] == effective
    assert authorization["authorized_run"]["data_boundary"]["candles_before_utc"] == effective


def test_the_execution_path_accepts_the_boundary_candle_and_refuses_one_past_it() -> None:
    from v4_campaign.data import load_development_candles
    from v4_campaign.errors import ConfirmatoryWindowViolation

    data = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    pair = next(
        key for key, entry in (data.get("assets") or {}).items() if entry.get("validated") is True
    )
    cutoff_ms = _parse_utc_ms(
        _load(REPO_ROOT / SPEC_V4_RELATIVE)["holdout"]["development_cutoff_utc"]
    )

    candles, summary = load_development_candles(REPO_ROOT, pair, data, cutoff_ms)
    assert candles
    assert summary["last_candle_close_ms"] == cutoff_ms
    assert summary["confirmatory_candles_read"] == 0

    with pytest.raises(ConfirmatoryWindowViolation):
        load_development_candles(REPO_ROOT, pair, data, cutoff_ms - HOUR_MS)


# --------------------------------------------------------------------------
# the tamper controls
# --------------------------------------------------------------------------


def test_the_verifier_detects_an_exclusive_rule_in_the_candidate_freeze(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    freeze = _load(REPO_ROOT / FREEZE_RELATIVE)
    freeze["data_boundary"]["development_cutoff_rule"] = EXCLUSIVE_RULE
    freeze["manifest_hash"] = verifier.compute_manifest_hash(freeze, ("manifest_hash",))
    _replace(root, FREEZE_RELATIVE, freeze)
    failures = _failures(root)
    assert any(
        "the candidate freeze states the development-data boundary exclusively" in failure
        for failure in failures
    ), failures


def test_the_verifier_detects_an_exclusive_rule_in_the_execution_protocol(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    execution = _load(REPO_ROOT / EXECUTION_RELATIVE)
    execution["candidate_freeze_and_confirmatory_window"][
        "development_data_boundary_rule"
    ] = EXCLUSIVE_RULE
    execution["manifest_hash"] = verifier.compute_manifest_hash(execution, ("manifest_hash",))
    _replace(root, EXECUTION_RELATIVE, execution)
    failures = _failures(root)
    assert any(
        "the execution protocol states the development-data boundary exclusively" in failure
        for failure in failures
    ), failures


def test_the_verifier_detects_an_exclusive_rule_in_the_authorization(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    authorization = _load(REPO_ROOT / AUTHORIZATION_RELATIVE)
    authorization["authorized_run"]["data_boundary"]["candles_before_utc_rule"] = EXCLUSIVE_RULE
    authorization["manifest_hash"] = verifier.compute_manifest_hash(
        authorization, ("manifest_hash",)
    )
    _replace(root, AUTHORIZATION_RELATIVE, authorization)
    failures = _failures(root)
    assert any(
        "the selection authorization states the development-data boundary exclusively" in failure
        for failure in failures
    ), failures


def test_the_verifier_detects_an_exclusive_rule_in_the_data_manifest(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    data["confirmatory_window"]["note"] = EXCLUSIVE_RULE
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    data["manifest_hash"] = verifier.compute_manifest_hash(data, excluded)
    data["snapshot_identity"]["data_manifest_hash"] = data["manifest_hash"]
    _replace(root, DATA_MANIFEST_RELATIVE, data)
    failures = _failures(root)
    assert any(
        "the data manifest states the development-data boundary exclusively" in failure
        for failure in failures
    ), failures


def test_the_verifier_detects_a_dataset_that_stops_before_the_boundary(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(REPO_ROOT / DATA_MANIFEST_RELATIVE)
    pair = next(
        key for key, entry in (data.get("assets") or {}).items() if entry.get("validated") is True
    )
    data["assets"][pair]["last_candle_timestamp"] = (
        int(data["assets"][pair]["last_candle_timestamp"]) - HOUR_MS
    )
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    data["manifest_hash"] = verifier.compute_manifest_hash(data, excluded)
    data["snapshot_identity"]["data_manifest_hash"] = data["manifest_hash"]
    _replace(root, DATA_MANIFEST_RELATIVE, data)
    failures = _failures(root)
    assert any(
        "does not end with the candle that closes exactly at the authorized data boundary"
        in failure
        for failure in failures
    ), failures

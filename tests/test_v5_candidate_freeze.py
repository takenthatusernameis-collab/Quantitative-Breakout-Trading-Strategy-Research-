"""Tests for the v5 candidate freeze and its verifier.

``configs/research_v5_candidate_freeze.json`` freezes the v5 candidate set, the
v5 data boundary and the v5 confirmatory window before any v5 evaluation runs.
The rules these tests pin are:

* the freeze is self-hashing and is **reproduced byte for byte** by its
  producer, so the frozen artifact is not a hand-written document;
* the frozen candidate set is exactly the v5 universe manifest's eligible
  assets, with the validation outcome and the exclusion reason of each, and the
  validated subset is exactly the validated constituents;
* the **batch rule** holds: every frozen candidate is strictly below the floor
  recomputed from the v4 universe manifest, and no frozen candidate is an
  asset of the v1, the v2, the v3 or the v4 universe;
* the **data boundary** holds: the development cutoff is the earliest open
  confirmatory window's start, the inclusive convention is stated, and the
  membership rule is the rule the published amendment owns;
* the **confirmatory window is a new window**: it opens after the freeze, it
  needs 2,160 closed hourly candles, it is single-use, it is not any of the
  v1-v4 windows, and the v5 candidate set is disjoint from every earlier
  candidate set;
* the ``supersedes`` chain names the v4 freeze with its recomputed identities;
* the exposure counter starts at 0, the freeze authorizes nothing and no v5 run
  artifact exists.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

FREEZE_PATH = REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
SPEC_PATH = REPO_ROOT / "configs" / "research_v5.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v5.json"
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v5_specification_amendment_1.json"
V4_FREEZE_PATH = REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v5_candidate_freeze", "scripts/verify_v5_candidate_freeze.py")
producer = _load_module("build_v5_candidate_freeze", "scripts/build_v5_candidate_freeze.py")
rules = _load_module("v5_universe_rules", "scripts/v5_universe_rules.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap even though the v5 chain
    carries ~50 MB of candle datasets. The tamper controls replace single
    files, and ``_replace`` unlinks the symlink before writing.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if target.is_symlink() or target.exists():
                target.unlink()
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


def _tamper(root: Path, mutate, relative: str = "configs/research_v5_candidate_freeze.json",
            rehash: bool = True) -> Path:
    document = _load(REPO_ROOT / relative)
    mutate(document)
    if rehash:
        document["manifest_hash"] = verifier.compute_manifest_hash(document, ("manifest_hash",))
    _replace(root, relative, document)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_the_freeze_is_self_hashing() -> None:
    freeze = _load(FREEZE_PATH)
    assert verifier.compute_manifest_hash(freeze, ("manifest_hash",)) == freeze["manifest_hash"]


def test_the_freeze_is_reproduced_byte_for_byte_by_its_producer() -> None:
    freeze = _load(FREEZE_PATH)
    rebuilt = producer.build(REPO_ROOT, freeze["candidate_freeze_utc"])
    assert rebuilt == freeze
    rendered = json.dumps(rebuilt, indent=2) + "\n"
    assert rendered == FREEZE_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v5_candidate_freeze.json"
    target.unlink()
    assert producer.main(["--repo-root", str(root), "--freeze-utc", "2026-10-21T12:14:36Z"]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root), "--freeze-utc", "2026-10-21T12:14:36Z"]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_frozen_candidate_set_is_the_v5_eligible_assets() -> None:
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_PATH)
    assert [entry["binance_pair"] for entry in freeze["candidates"]] == [
        entry["binance_pair"] for entry in universe["eligible_assets"]
    ]
    assert len(freeze["candidates"]) == 20
    for entry in freeze["candidates"]:
        if entry["validated"] is True:
            assert entry["exclusion_reason"] is None
        else:
            assert entry["exclusion_reason"]


def test_the_frozen_validated_set_is_the_validated_v5_universe() -> None:
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_PATH)
    frozen = sorted(
        entry["binance_pair"] for entry in freeze["candidates"] if entry.get("validated") is True
    )
    validated = sorted(
        entry["binance_pair"]
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    assert frozen == validated
    assert len(frozen) == 7


def test_every_frozen_candidate_is_strictly_below_the_v4_floor() -> None:
    freeze = _load(FREEZE_PATH)
    v4 = _load(REPO_ROOT / "research" / "universe_manifest_v4.json")
    floor_symbol, floor_market_cap = rules.recompute_floor(v4)
    assert floor_symbol == "AKE"
    assert floor_market_cap == 739186726
    for entry in freeze["candidates"]:
        assert int(entry["market_cap_usd"]) < floor_market_cap, entry["binance_pair"]


def test_no_frozen_candidate_is_an_asset_of_v1_to_v4() -> None:
    freeze = _load(FREEZE_PATH)
    prior = [_load(REPO_ROOT / relative) for relative in rules.PRIOR_UNIVERSE_RELATIVES]
    symbols, identifiers = rules.prior_universe_assets(*prior)
    for entry in freeze["candidates"]:
        marker = str(entry["binance_pair"])
        if marker.endswith("USDT"):
            marker = marker[:-4]
        assert marker.upper() not in symbols, entry["binance_pair"]
        assert str(entry["coingecko_id"]) not in identifiers, entry["binance_pair"]


def test_the_frozen_development_cutoff_is_the_earliest_open_window_start() -> None:
    freeze = _load(FREEZE_PATH)
    spec = _load(SPEC_PATH)
    assert freeze["data_boundary"]["development_cutoff_utc"] == "2026-10-19T22:00:00Z"
    assert freeze["data_boundary"]["development_cutoff_utc"] == spec["holdout"][
        "development_cutoff_utc"
    ]
    assert "closes exactly at" in freeze["data_boundary"]["development_cutoff_rule"]


def test_the_frozen_membership_rule_is_the_amendment_rule() -> None:
    freeze = _load(FREEZE_PATH)
    amendment = _load(AMENDMENT_PATH)
    assert freeze["data_boundary"]["confirmatory_window_membership_rule"] == (
        amendment["corrected_rule"]["rule"]
    )
    assert freeze["data_boundary"]["confirmatory_window_membership_amendment_path"] == (
        "configs/research_v5_specification_amendment_1.json"
    )
    assert freeze["data_boundary"]["confirmatory_window_membership_amendment_hash"] == (
        amendment["manifest_hash"]
    )


def test_the_confirmatory_window_is_a_new_window() -> None:
    freeze = _load(FREEZE_PATH)
    window = freeze["confirmatory_window"]
    assert window["opens_utc"] == "2026-10-21T13:00:00Z"
    assert window["min_hours"] == 2160
    assert window["earliest_possible_end_utc"] == "2027-01-19T13:00:00Z"
    assert window["single_use"] is True
    for version, relative in (
        ("v2", "configs/research_v2_candidate_freeze.json"),
        ("v3", "configs/research_v3_candidate_freeze.json"),
        ("v4", "configs/research_v4_candidate_freeze.json"),
    ):
        prior = _load(REPO_ROOT / relative)
        prior_pairs = {
            entry["binance_pair"]
            for entry in (prior.get("candidates") or [])
            if entry.get("validated") is True
        }
        frozen_pairs = {
            entry["binance_pair"]
            for entry in freeze["candidates"]
            if entry.get("validated") is True
        }
        assert not (prior_pairs & frozen_pairs), version


def test_the_supersedes_chain_names_the_v4_freeze() -> None:
    freeze = _load(FREEZE_PATH)
    v4 = _load(V4_FREEZE_PATH)
    assert freeze["supersedes"]["v4_candidate_freeze_path"] == (
        "configs/research_v4_candidate_freeze.json"
    )
    assert freeze["supersedes"]["v4_candidate_freeze_hash"] == v4["manifest_hash"]
    assert freeze["supersedes"]["v1_v2_v3_v4_artifacts_are_immutable"] is True


def test_the_exposure_counter_starts_at_zero() -> None:
    freeze = _load(FREEZE_PATH)
    spec = _load(SPEC_PATH)
    data = _load(DATA_PATH)
    assert spec["holdout"]["v5_holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"
    for key in (
        "v1_holdout_reuse",
        "v2_confirmatory_window_reuse",
        "v3_confirmatory_window_reuse",
        "v4_confirmatory_window_reuse",
    ):
        assert freeze["data_boundary"][key] == "forbidden"


def test_the_freeze_authorizes_nothing() -> None:
    freeze = _load(FREEZE_PATH)
    for key, value in freeze.items():
        if "authoriz" in str(key).lower():
            assert value is not True, key
    assert "authorizes nothing" in freeze["specification_purpose"]


# --------------------------------------------------------------------------
# the tamper controls
# --------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_candidate_that_is_not_in_the_universe_manifest(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["candidates"].append(
            {
                "binance_pair": "ZZZUSDT",
                "coingecko_id": "zzz",
                "exclusion_reason": None,
                "market_cap_rank": 500,
                "market_cap_usd": 1,
                "symbol": "ZZZ",
                "validated": True,
            }
        ),
    )
    failures = _failures(root)
    assert any("not the v5 universe" in failure for failure in failures), failures


def test_the_verifier_detects_a_widened_validated_set(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        for entry in document["candidates"]:
            if entry.get("validated") is not True:
                entry["validated"] = True
                entry["exclusion_reason"] = None
                break

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not the validated v5 universe" in failure for failure in failures), failures


def test_the_verifier_detects_a_candidate_above_the_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["candidates"][0]["market_cap_usd"] = 739186726

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not strictly below the v4 floor" in failure for failure in failures), failures


def test_the_verifier_detects_a_stale_specification_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"specification_hash": "0" * 64}))
    failures = _failures(root)
    assert any("not bound to the v5 specification" in failure for failure in failures), failures


def test_the_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"manifest_hash": "0" * 64}), rehash=False)
    failures = _failures(root)
    assert any("manifest_hash mismatch" in failure for failure in failures), failures


def test_the_verifier_detects_a_window_that_is_not_a_new_window(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["confirmatory_window"]["opens_utc"] = "2026-10-21T01:00:00Z"
        document["data_boundary"]["v5_confirmatory_window_start_utc"] = "2026-10-21T01:00:00Z"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any(
        "reuses the v4 confirmatory window" in failure
        or "first hour boundary strictly after the freeze instant" in failure
        for failure in failures
    ), failures


def test_the_verifier_detects_a_wrong_window_end(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["confirmatory_window"]["earliest_possible_end_utc"] = "2027-01-19T01:00:00Z"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any(
        "different earliest ends" in failure or "recomputed" in failure for failure in failures
    ), failures


def test_the_verifier_detects_a_membership_rule_that_contradicts_the_amendment(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["data_boundary"]["confirmatory_window_membership_rule"] = (
            "a candle is inside a confirmatory window when its close falls in that window's "
            "time range, regardless of which asset the candle belongs to"
        )

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not the rule the published amendment owns" in failure for failure in failures), failures


def test_the_verifier_detects_a_supersedes_chain_that_names_an_older_artifact(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["supersedes"]["v4_candidate_freeze_path"] = (
            "configs/research_v3_candidate_freeze.json"
        )

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not supersede the v4 candidate freeze" in failure for failure in failures), failures


def test_the_verifier_detects_a_freeze_that_claims_an_authorization(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"execution_authorized": True}))
    failures = _failures(root)
    assert any("claims an authorization" in failure for failure in failures), failures


def test_the_verifier_detects_a_missing_amendment(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "configs" / "research_v5_specification_amendment_1.json").unlink()
    failures = _failures(root)
    assert any("amendment" in failure for failure in failures), failures


def test_the_verifier_detects_a_tampered_amendment(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    path = root / "configs" / "research_v5_specification_amendment_1.json"
    document = _load(path)
    document["corrected_rule"]["interval_start_inclusive"] = True
    _replace(root, "configs/research_v5_specification_amendment_1.json", document)
    failures = _failures(root)
    assert any("interval_start_inclusive" in failure for failure in failures), failures


def test_the_verifier_detects_a_v5_run_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "ledger_v5.json").write_text("{}\n", encoding="utf-8")
    failures = _failures(root)
    assert any("v5 run artifact" in failure for failure in failures), failures

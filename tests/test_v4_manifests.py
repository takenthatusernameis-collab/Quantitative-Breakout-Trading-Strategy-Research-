"""Tests for the v4 universe and data manifests and their verifier.

The v4 chain was repaired in the session that delivered this module: the
candidate batch had been re-derived with the v2 floor and the v1/v2 identity
rule, so the v4 batch was the v3 batch again, and the development datasets
reached past the preregistered development cutoff into the open v3
confirmatory window. These tests pin the three rules that were violated, so
that the defect cannot come back silently:

* the **floor rule**: every member of the batch is strictly below the floor
  recomputed from the v3 universe manifest, which is the source the v4
  specification names;
* the **identity rule**: no member of the batch is an asset of the v1, the v2
  or the v3 universe;
* the **development cutoff**: no validated dataset closes a candle after the
  preregistered development cutoff -- the candle that closes exactly at the
  cutoff is development data -- so no v4 development candle closes inside the
  open v3 confirmatory window.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HASHED_SET_ROOT = Path("src/breakout_research")
EXECUTION_PATH_ROOT = Path("src/v4_campaign")

UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v4.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v4.json"
SPEC_PATH = REPO_ROOT / "configs" / "research_v4.json"
V3_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v3.json"
V3_DATA_PATH = REPO_ROOT / "research" / "data_manifest_v3.json"
AMENDMENT_2_PATH = REPO_ROOT / "configs" / "research_v4_exclusion_amendment_2.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_research_v4_manifests", "scripts/verify_research_v4_manifests.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    copy_relative = {HASHED_SET_ROOT, EXECUTION_PATH_ROOT, Path("research/data")}
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


def _rehash(document: Dict[str, Any], excluded: Any = ("manifest_hash",)) -> None:
    document["manifest_hash"] = verifier.compute_manifest_hash(document, excluded)


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]


def test_every_batch_member_is_strictly_below_the_v3_floor() -> None:
    universe = _load(UNIVERSE_PATH)
    v3 = _load(V3_UNIVERSE_PATH)
    floor = min(int(entry["market_cap_usd"]) for entry in v3["eligible_assets"])
    assert floor == 1468004153
    for entry in universe["eligible_assets"]:
        assert int(entry["market_cap_usd"]) < floor, entry["binance_pair"]


def test_no_batch_member_is_an_asset_of_v1_v2_or_v3() -> None:
    universe = _load(UNIVERSE_PATH)
    prior: Dict[str, str] = {}
    for version, relative in (
        ("v1", "research/universe_manifest.json"),
        ("v2", "research/universe_manifest_v2.json"),
        ("v3", "research/universe_manifest_v3.json"),
    ):
        for entry in _load(REPO_ROOT / relative)["eligible_assets"]:
            prior[str(entry["symbol"]).upper()] = version
    for entry in universe["eligible_assets"]:
        assert str(entry["symbol"]).upper() not in prior, entry["binance_pair"]


def test_the_v4_cohort_is_not_the_v3_cohort() -> None:
    universe = _load(UNIVERSE_PATH)
    v3 = _load(V3_UNIVERSE_PATH)
    v4_validated = {
        entry["binance_pair"] for entry in universe["eligible_assets"]
        if entry.get("validated") is True
    }
    v3_validated = {
        entry["binance_pair"] for entry in v3["eligible_assets"]
        if entry.get("validated") is True
    }
    assert v4_validated
    assert not v4_validated & v3_validated


def test_the_supersedes_chain_names_the_v3_artifacts() -> None:
    universe = _load(UNIVERSE_PATH)
    data = _load(DATA_PATH)
    v3 = _load(V3_UNIVERSE_PATH)
    assert universe["supersedes"]["universe_manifest_path"] == "research/universe_manifest_v3.json"
    assert universe["supersedes"]["universe_manifest_hash"] == v3["manifest_hash"]
    assert data["supersedes"]["data_manifest_path"] == "research/data_manifest_v3.json"


def test_the_effective_amendment_takes_the_floor_and_the_identity_rule_from_v3() -> None:
    amendment = _load(AMENDMENT_2_PATH)
    assert amendment["floor"]["source_universe_version"] == "v3"
    assert amendment["floor"]["floor_market_cap_usd"] == 1468004153
    assert amendment["prior_universe"]["v3_manifest_path"] == "research/universe_manifest_v3.json"
    assert "v3" in json.dumps(amendment["prior_universe"]["identity_rules"]).lower() or (
        "v3" in amendment["prior_universe"]["rule"]
    )
    assert amendment["derived_candidate_batch"]["count"] == 20


def test_the_effective_amendment_is_the_highest_numbered_one() -> None:
    amendments = sorted(REPO_ROOT.glob("configs/research_v4_exclusion_amendment_*.json"))
    numbers = [int(path.stem.rsplit("_", 1)[-1]) for path in amendments]
    assert numbers == sorted(numbers)
    assert amendments[-1] == AMENDMENT_2_PATH


def test_no_validated_dataset_closes_a_candle_after_the_cutoff() -> None:
    data = _load(DATA_PATH)
    spec = _load(SPEC_PATH)
    cutoff = spec["holdout"]["development_cutoff_utc"]
    assert cutoff == "2026-10-20T13:00:00Z"
    cutoff_ms = int(
        __import__("datetime").datetime.fromisoformat(cutoff.replace("Z", "+00:00")).timestamp()
        * 1000
    )
    for pair, entry in data["assets"].items():
        if entry.get("validated") is not True:
            continue
        assert int(entry["last_candle_timestamp"]) + 3_600_000 <= cutoff_ms, pair


def test_the_data_window_is_bound_to_the_cutoff_not_to_the_snapshot() -> None:
    data = _load(DATA_PATH)
    assert data["window_policy"]["bound_to"] == "holdout.development_cutoff_utc"
    assert data["window_policy"]["development_cutoff_utc"] == "2026-10-20T13:00:00Z"


# --------------------------------------------------------------------------
# the tamper controls
# --------------------------------------------------------------------------


def test_the_verifier_detects_a_member_above_the_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["eligible_assets"][0]["market_cap_usd"] = 999999999999
    _rehash(universe)
    _replace(root, "research/universe_manifest_v4.json", universe)
    failures = _failures(root)
    assert any("not strictly below the v3 floor" in failure for failure in failures)


def test_the_verifier_detects_a_member_of_a_prior_universe(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    v3 = _load(V3_UNIVERSE_PATH)
    prior = next(entry for entry in v3["eligible_assets"] if entry.get("validated") is True)
    universe["eligible_assets"][0]["symbol"] = prior["symbol"]
    universe["eligible_assets"][0]["coingecko_id"] = prior["coingecko_id"]
    _rehash(universe)
    _replace(root, "research/universe_manifest_v4.json", universe)
    failures = _failures(root)
    assert any("already an asset of the" in failure for failure in failures)


def test_the_verifier_detects_a_supersedes_chain_that_names_an_older_version(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["supersedes"]["universe_manifest_path"] = "research/universe_manifest_v2.json"
    _rehash(universe)
    _replace(root, "research/universe_manifest_v4.json", universe)
    failures = _failures(root)
    assert any("does not supersede the v3 universe manifest" in failure for failure in failures)


def test_the_verifier_detects_a_dataset_that_reaches_past_the_cutoff(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    data = _load(DATA_PATH)
    pair = next(
        key for key, entry in data["assets"].items() if entry.get("validated") is True
    )
    data["assets"][pair]["last_candle_timestamp"] = 1792533600000
    excluded = tuple(data["hashing"]["manifest_hash_excluded_keys"])
    _rehash(data, excluded)
    _replace(root, "research/data_manifest_v4.json", data)
    failures = _failures(root)
    assert any("development cutoff" in failure for failure in failures)


def test_the_verifier_detects_a_batch_that_is_not_the_re_derived_one(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    universe = _load(UNIVERSE_PATH)
    universe["eligible_assets"] = universe["eligible_assets"][:-1]
    _rehash(universe)
    _replace(root, "research/universe_manifest_v4.json", universe)
    failures = _failures(root)
    assert any("re-derived candidate batch" in failure for failure in failures)


# --------------------------------------------------------------------------
# the state-adaptive v4 execution state
# --------------------------------------------------------------------------


def test_the_execution_state_is_the_authorized_one() -> None:
    """After the authorized run the v4 execution artifacts are the authorized ones."""
    ledger = _load(REPO_ROOT / "research" / "ledger_v4.json")
    authorization = _load(REPO_ROOT / "configs" / "research_v4_selection_authorization_1.json")
    run = authorization["authorized_run"]
    assert ledger["status"] == "COMPLETED"
    assert ledger["authorization_manifest_hash"] == authorization["manifest_hash"]
    assert ledger["run_id"] == run["run_id"]
    assert ledger["campaign_id"] == run["campaign_id"]
    assert ledger["holdout_exposed_count"] == 0
    assert verifier.v4_execution_state_failures(REPO_ROOT) == []


def test_the_verifier_detects_an_execution_artifact_without_the_authorization(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    (root / "configs" / "research_v4_selection_authorization_1.json").unlink()
    failures = _failures(root)
    assert any(
        "without the v4 selection authorization" in failure for failure in failures
    )


def test_the_verifier_detects_a_ledger_that_is_not_bound_to_the_authorization(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _load(REPO_ROOT / "research" / "ledger_v4.json")
    ledger["authorization_manifest_hash"] = "0" * 64
    _replace(root, "research/ledger_v4.json", ledger)
    failures = _failures(root)
    assert any("not bound to the v4 selection authorization" in failure for failure in failures)


def test_the_verifier_detects_an_incomplete_run(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _load(REPO_ROOT / "research" / "ledger_v4.json")
    ledger["status"] = "INTERRUPTED"
    _replace(root, "research/ledger_v4.json", ledger)
    failures = _failures(root)
    assert any("not 'COMPLETED'" in failure for failure in failures)


def test_the_verifier_detects_a_confirmatory_exposure_in_the_ledger(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)
    ledger = _load(REPO_ROOT / "research" / "ledger_v4.json")
    ledger["holdout_exposed_count"] = 1
    _replace(root, "research/ledger_v4.json", ledger)
    failures = _failures(root)
    assert any("records a confirmatory exposure" in failure for failure in failures)

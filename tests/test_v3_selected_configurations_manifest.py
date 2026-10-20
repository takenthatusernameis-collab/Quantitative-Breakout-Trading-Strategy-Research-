"""Deterministic tests for the published v3 selected-configurations manifest.

Every expectation is recomputed from the repository: the selection itself is
re-derived from the verified result shards under the preregistered v1 rule, the
digests are recomputed from the bytes on disk, and the tamper tests rebuild the
artifact in a mirrored tree and prove that the verifier refuses it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} is not present in this checkout")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The producer is loaded first and registered under the name the verifier imports,
# so that both share one recomputation cache and the expensive re-derivation runs
# once per session instead of once per module.
producer = _load_module(
    "publish_v3_selected_configurations",
    "scripts/publish_v3_selected_configurations.py",
)
verifier = _load_module(
    "verify_v3_selected_configurations_manifest",
    "scripts/verify_v3_selected_configurations_manifest.py",
)

MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v3.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
SELECTION_AUTH_RELATIVE = "configs/research_v3_selection_authorization_1.json"
EXECUTION_AMENDMENT_2_RELATIVE = "configs/research_v3_execution_amendment_2.json"
UNIVERSE_V3_RELATIVE = "research/universe_manifest_v3.json"
DATA_V3_RELATIVE = "research/data_manifest_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"

MIRROR_FILES = (
    MANIFEST_RELATIVE,
    LEDGER_RELATIVE,
    "research/results_manifest_v3.json",
    FREEZE_RELATIVE,
    FREEZE_AMENDMENT_1_RELATIVE,
    FREEZE_AMENDMENT_2_RELATIVE,
    "configs/research_v3_data_manifest_amendment_1.json",
    "configs/research_v3_execution_amendment_1.json",
    EXECUTION_AMENDMENT_2_RELATIVE,
    SELECTION_AUTH_RELATIVE,
    UNIVERSE_V3_RELATIVE,
    DATA_V3_RELATIVE,
    SPEC_V1_RELATIVE,
    "configs/research_v3.json",
    "research/config_manifest.json",
    "research_state/checkpoint_v3.json",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/v2_selected_configurations_manifest.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

MIRROR_DIRECTORIES = (
    "research/shards_v3/v3-campaign",
    "research/shards_v2/v2-campaign",
    "research/data/candles_v3",
)


def _load(relative: str) -> Dict[str, Any]:
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A tree of symlinks to the artifacts the verifier reads.

    Files are symlinked, so a test may replace one without writing to the working
    tree; the directories that carry the shards and the candle datasets are
    mirrored the same way.
    """
    root = tmp_path / "repo"
    for relative in MIRROR_FILES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
    for relative in MIRROR_DIRECTORIES:
        source = REPO_ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if item.is_file():
                (target / item.name).symlink_to(item)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


@pytest.fixture(scope="module")
def recomputed() -> Dict[str, Any]:
    return verifier.recompute_selection(REPO_ROOT)


def test_the_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_manifest_hash_recomputes_from_the_document():
    manifest = _load(MANIFEST_RELATIVE)
    excluded = tuple(manifest["manifest_hash_excluded_keys"])
    assert manifest["manifest_hash"] == verifier.compute_manifest_hash(manifest, excluded)


def test_the_published_selection_is_reproduced_from_the_shards(recomputed):
    """The published winners are re-derived from the shards, not copied from them."""
    manifest = _load(MANIFEST_RELATIVE)
    selections = manifest["selections"]
    assert set(selections) == set(recomputed["per_asset"])
    for asset, entry in recomputed["per_asset"].items():
        published = selections[asset]
        assert published["config_id"] == entry["config_id"], asset
        assert published["status"] == entry["status"], asset
        assert published["economic_status"] == entry["economic_status"], asset
    assert manifest["assets_with_candidate"] == recomputed["assets_with_candidate"]
    assert manifest["assets_without_candidate"] == recomputed["assets_without_candidate"]
    assert manifest["derived_from"]["records_read"] == recomputed["records_read"]


def test_the_recomputation_consumes_every_validation_unit(recomputed):
    ledger = _load(LEDGER_RELATIVE)
    assert recomputed["records_read"] == ledger["counts"]["records_written"]
    assert recomputed["records_read"] == ledger["counts"]["execution_units"]
    assert ledger["holdout_exposed_count"] == 0


def test_the_selection_covers_exactly_the_frozen_candidate_set():
    manifest = _load(MANIFEST_RELATIVE)
    freeze_amendment_1 = _load(FREEZE_AMENDMENT_1_RELATIVE)
    freeze_amendment_2 = _load(FREEZE_AMENDMENT_2_RELATIVE)
    universe = _load(UNIVERSE_V3_RELATIVE)
    frozen = [
        str(member["binance_pair"])
        for member in freeze_amendment_1["validated_candidate_set"]["members"]
    ]
    rebound = [
        str(pair) for pair in freeze_amendment_2["frozen_candidate_set"]["binance_pairs"]
    ]
    assert sorted(frozen) == sorted(rebound)
    validated = sorted(
        str(entry["binance_pair"])
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    assert sorted(frozen) == validated
    assert sorted(manifest["selections"]) == sorted(frozen)
    assert manifest["scope"]["frozen_candidate_set"]["count"] == len(frozen)


def test_the_excluded_assets_stay_excluded_with_their_reasons():
    manifest = _load(MANIFEST_RELATIVE)
    universe = _load(UNIVERSE_V3_RELATIVE)
    excluded = {
        str(entry["binance_pair"]): str(entry["exclusion_reason"])
        for entry in universe["eligible_assets"]
        if not (entry.get("validated") is True and entry.get("exclusion_reason") is None)
    }
    assert len(excluded) == 14
    assert set(excluded.values()) == {
        "insufficient_hourly_history", "binance_spot_unavailable",
    }
    assert manifest["scope"]["frozen_candidate_set"]["excluded_after_validation"] == excluded
    for symbol in excluded:
        assert symbol not in manifest["selections"]


def test_the_assets_without_a_candidate_are_reported_with_a_reason():
    manifest = _load(MANIFEST_RELATIVE)
    assert manifest["outcome"] == "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
    assert manifest["assets_without_candidate_reported"] is True
    assert manifest["assets_without_candidate"] == ["AAVEUSDT", "QNTUSDT"]
    for asset in manifest["assets_without_candidate"]:
        entry = manifest["selections"][asset]
        assert entry["selected"] is False
        assert entry["config_id"] is None
        assert entry["reason"]
    assert sorted(manifest["assets_with_candidate"]) == [
        "ICPUSDT", "PEPEUSDT", "SHIBUSDT", "WLDUSDT",
    ]


def test_the_benchmark_rule_is_bound_and_the_dataset_is_hash_verified():
    manifest = _load(MANIFEST_RELATIVE)
    benchmark = manifest["benchmark"]
    dataset = REPO_ROOT / benchmark["dataset_path"]
    assert dataset.exists()
    assert verifier.sha256_file(dataset) == benchmark["content_hash"]
    assert benchmark["btc_configurations_dropped"] is False
    assert benchmark["symbol"] == "BTCUSDT"


def test_the_manifest_authorizes_nothing():
    manifest = _load(MANIFEST_RELATIVE)
    data_manifest = _load(DATA_V3_RELATIVE)
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0
    for key in ("selection_run", "second_run", "confirmatory_evaluation", "candle_fetch"):
        assert manifest["authorizes"][key] is False
    assert manifest["exposure"]["confirmatory_candles_read"] == 0
    assert manifest["exposure"]["holdout_exposed_count"] == 0


def test_the_prior_lines_are_uncontaminated():
    assert verifier.prior_line_contamination_failures(REPO_ROOT) == []


def test_the_amendment_authorizes_the_published_path():
    manifest = _load(MANIFEST_RELATIVE)
    amendment = _load(EXECUTION_AMENDMENT_2_RELATIVE)
    paths = amendment["v3_result_layout_amendment"]["paths"]
    assert paths["selected_configurations_manifest_path"] == MANIFEST_RELATIVE
    assert paths["selected_configurations_manifest_hash"] == manifest["manifest_hash"]


def test_the_mirrored_tree_verifies_cleanly(tmp_path):
    """The control: a mirror without any tamper must not produce a failure."""
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_published_artifact_is_reproducible_from_the_producer():
    """The producer re-derives the artifact from the shards; it reproduces it byte for byte."""
    built = producer.build(REPO_ROOT)
    assert built == _load(MANIFEST_RELATIVE)
    assert built["manifest_hash"] == verifier.compute_manifest_hash(
        built, tuple(built["manifest_hash_excluded_keys"]))


def test_the_producer_fails_loudly_when_the_selection_cannot_be_re_derived(monkeypatch):
    """No fallback copy: a failed re-derivation aborts the producer."""
    def boom(*args, **kwargs):
        raise RuntimeError("simulated selection failure")

    producer._RECOMPUTATION_CACHE.clear()
    monkeypatch.setattr(producer, "select_candidates", boom)
    with pytest.raises(RuntimeError):
        producer.build(REPO_ROOT)
    producer._RECOMPUTATION_CACHE.clear()


def test_the_verifier_detects_a_tampered_manifest_hash(tmp_path):
    root = _mirror_repo(tmp_path)
    manifest = _load(MANIFEST_RELATIVE)
    manifest["manifest_hash"] = "0" * 64
    _replace(root, MANIFEST_RELATIVE, manifest)
    assert _failures(root)


def test_the_verifier_detects_a_selected_configuration_the_shards_do_not_support(tmp_path):
    root = _mirror_repo(tmp_path)
    manifest = _load(MANIFEST_RELATIVE)
    other = next(
        entry["config_id"] for asset, entry in manifest["selections"].items()
        if entry["selected"] and asset != "ICPUSDT")
    manifest["selections"]["ICPUSDT"]["config_id"] = other
    manifest["manifest_hash"] = verifier.compute_manifest_hash(
        manifest, tuple(manifest["manifest_hash_excluded_keys"]))
    _replace(root, MANIFEST_RELATIVE, manifest)
    failures = _failures(root)
    assert any("ICPUSDT" in failure for failure in failures)


def test_the_verifier_detects_a_selection_that_the_shards_do_not_support(tmp_path):
    """A manifest and a ledger that agree with each other but not with the shards are refused."""
    root = _mirror_repo(tmp_path)
    manifest = _load(MANIFEST_RELATIVE)
    ledger = _load(LEDGER_RELATIVE)
    other = next(
        entry["config_id"] for asset, entry in manifest["selections"].items()
        if entry["selected"] and asset != "ICPUSDT")
    manifest["selections"]["ICPUSDT"]["config_id"] = other
    ledger["selection"]["per_asset"]["ICPUSDT"]["config_id"] = other
    manifest["manifest_hash"] = verifier.compute_manifest_hash(
        manifest, tuple(manifest["manifest_hash_excluded_keys"]))
    _replace(root, MANIFEST_RELATIVE, manifest)
    _replace(root, LEDGER_RELATIVE, ledger)
    failures = _failures(root)
    assert any("ICPUSDT" in failure for failure in failures)


def test_the_verifier_detects_a_widened_scope(tmp_path):
    root = _mirror_repo(tmp_path)
    manifest = _load(MANIFEST_RELATIVE)
    scope = manifest["scope"]["frozen_candidate_set"]
    scope["binance_pairs"] = sorted(list(scope["binance_pairs"]) + ["TAOUSDT"])
    scope["count"] = len(scope["binance_pairs"])
    manifest["manifest_hash"] = verifier.compute_manifest_hash(
        manifest, tuple(manifest["manifest_hash_excluded_keys"]))
    _replace(root, MANIFEST_RELATIVE, manifest)
    failures = _failures(root)
    assert any("frozen candidate set" in failure or "exclusion" in failure for failure in failures)


def test_the_verifier_detects_a_self_reporting_exposure(tmp_path):
    root = _mirror_repo(tmp_path)
    data_manifest = _load(DATA_V3_RELATIVE)
    data_manifest["confirmatory_window"]["confirmatory_window_status"] = "READ"
    data_manifest["confirmatory_window"]["holdout_exposed_count"] = 1
    _replace(root, DATA_V3_RELATIVE, data_manifest)
    failures = _failures(root)
    assert any("unexposed" in failure or "exposure" in failure for failure in failures)


def test_the_verifier_detects_a_changed_v1_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    _replace(root, "research/candidate_manifest.json", {"changed": True})
    failures = _failures(root)
    assert any("candidate_manifest.json" in failure for failure in failures)


def test_the_verifier_detects_an_unbound_amendment(tmp_path):
    root = _mirror_repo(tmp_path)
    amendment = _load(EXECUTION_AMENDMENT_2_RELATIVE)
    amendment["v3_result_layout_amendment"]["paths"][
        "selected_configurations_manifest_hash"] = "0" * 64
    _replace(root, EXECUTION_AMENDMENT_2_RELATIVE, amendment)
    failures = _failures(root)
    assert any("does not bind this manifest" in failure for failure in failures)


def test_the_verifier_detects_a_missing_manifest(tmp_path):
    root = _mirror_repo(tmp_path)
    (root / MANIFEST_RELATIVE).unlink()
    failures = _failures(root)
    assert failures == [f"missing artifact: {MANIFEST_RELATIVE}"]

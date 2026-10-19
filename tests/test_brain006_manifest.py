"""Cross-validation of the BRAIN-006 candidate manifests against the ledger.

These tests compare the production selector (``src/breakout_research``) with
the independent read-only re-derivation
(``research/campaign_cycles/<cycle>/candidate_selection.json``) and with the
immutable v1 manifest, so a divergence between the two implementations is a
failing test rather than a silent difference in a research artifact.
"""
import json
from pathlib import Path

import pytest

from breakout_research.baselines import baseline_for_asset
from breakout_research.candidate_freeze import _legacy_profit_factor_selector
from breakout_research.config import load_research_spec
from breakout_research.selection import iter_shard_records, select_candidates

REPO_ROOT = Path(__file__).resolve().parent.parent
CYCLE_ID = "0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d"
CAMPAIGN_ID = "577e87e2dc37b496b4d0c9e1a2eeecc9a777f01698591fc395dddb12f45708cb"
CYCLE_ROOT = REPO_ROOT / "research" / "campaign_cycles" / CYCLE_ID
SHARD_ROOT = CYCLE_ROOT / "results_shards" / CAMPAIGN_ID
ANALYSIS_ARTIFACT = CYCLE_ROOT / "candidate_selection.json"
BASELINE_ARTIFACT = REPO_ROOT / "research" / "baselines" / f"{CAMPAIGN_ID}.json"
V1_MANIFEST = REPO_ROOT / "research" / "candidate_manifest.json"
V2_MANIFEST = REPO_ROOT / "research" / "candidate_manifest_v2.json"

V1_MANIFEST_HASH = "9ea6b1c3439c6087650aca549373642e0afe8460e0eee76f520cc1ac2bd30597"


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_manifest_is_untouched():
    manifest = _require(V1_MANIFEST)
    assert manifest["manifest_hash"] == V1_MANIFEST_HASH
    assert manifest["code_hash"] == "382e314141d4826e29ae1c00e720aa3320a2f71fe00723ff07dfa025b79abfb8"
    assert manifest["frozen"] is True
    assert len(manifest["candidates"]) == 18


def test_published_manifest_reproduces_the_independent_analysis_artifact():
    analysis = _require(ANALYSIS_ARTIFACT)
    published = _require(V2_MANIFEST)
    summary = published["selection_summary"]
    assert set(summary) == set(analysis["assets"])
    for asset, reference in analysis["assets"].items():
        assert summary[asset]["selection_status"] == reference["selection_status"], asset
        assert summary[asset]["selected_config_id"] == reference["selected_config_id"], asset
    counts = {}
    for payload in summary.values():
        counts[payload["selection_status"]] = counts.get(payload["selection_status"], 0) + 1
    assert counts == {"CANDIDATE_SELECTED": 14, "INSUFFICIENT_EVIDENCE": 1, "NO_CANDIDATE": 3}


def test_published_manifest_records_the_holdout_disposition():
    published = _require(V2_MANIFEST)
    assert published["holdout_exposure"] == "EXPOSED_OR_UNKNOWN"
    assert published["holdout_reuse"] == "forbidden"
    assert published["candidate_status"] == "CANDIDATE_PENDING_HOLDOUT"
    assert published["rule"] == "preregistered_v1"
    assert published["supersedes"]["manifest_hash"] == V1_MANIFEST_HASH
    for asset, payload in published["candidates"].items():
        assert payload["economic_status"] == "CANDIDATE_PENDING_HOLDOUT", asset
        assert payload["gates"] is not None, asset
        assert payload["neighbor_analysis"] is not None, asset


def test_conforming_rule_does_not_reproduce_the_v1_profit_factor_manifest():
    published = _require(V2_MANIFEST)
    v1 = _require(V1_MANIFEST)
    matching = [asset for asset, payload in published["candidates"].items()
                if payload["superseded_config_id"] == payload["config_id"]]
    # Only ADAUSDT's frozen v1 candidate is also the preregistered winner.
    assert matching == ["ADAUSDT"]
    changed = sum(1 for asset, payload in published["candidates"].items()
                  if payload["superseded_config_id"] != payload["config_id"])
    assert changed == 13
    assert len(published["candidates"]) == 14
    assert len(v1["candidates"]) == 18


def test_conforming_selector_reproduces_the_published_manifest():
    baseline_artifact = _require(BASELINE_ARTIFACT)
    published = _require(V2_MANIFEST)
    spec = load_research_spec(str(REPO_ROOT / "configs" / "research_v1.json"))
    baselines = {asset: baseline_for_asset(baseline_artifact, asset)
                 for asset in baseline_artifact["assets"]}
    selection = select_candidates(iter_shard_records(SHARD_ROOT), spec, baselines)
    assert len(selection) == 18
    for asset, payload in selection.items():
        reference = published["selection_summary"][asset]
        assert payload["status"] == reference["selection_status"], asset
        assert payload["config_id"] == reference["selected_config_id"], asset
    for asset, payload in published["candidates"].items():
        gates = payload["gates"]
        assert set(gates) == {
            "min_trades_total", "min_trades_per_fold", "min_folds_with_min_trades",
            "positive_net_return_baseline", "positive_net_return_2x_costs",
            "positive_folds_required", "median_sharpe_gt_zero", "median_sharpe_gt_buyhold"}
        assert all(gate["pass"] is True for gate in gates.values()), asset


def test_legacy_profit_factor_selector_reproduces_the_v1_manifest():
    v1 = _require(V1_MANIFEST)
    legacy = _legacy_profit_factor_selector(iter_shard_records(SHARD_ROOT))
    assert {asset: entry["config_id"] for asset, entry in legacy.items()} == {
        asset: entry["config_id"] for asset, entry in v1["candidates"].items()}

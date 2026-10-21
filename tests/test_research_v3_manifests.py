"""Tests for the v3 universe and data manifests.

The v3 manifests (``research/universe_manifest_v3.json`` and
``research/data_manifest_v3.json``) are the evidence of the BRAIN-012 P2/P3
prerequisites: they record which constituents the frozen eligibility rules
accepted, which candidates they excluded and why, and the hash-verified
datasets that back the accepted constituents. These tests prove that

* both manifest hashes recompute from their own bodies;
* the market-cap snapshot is the in-window retrieval the specification pins and
  is never re-retrieved;
* the candidate batch is re-derivable from the stored snapshot with the
  published rules, so the membership is not a hand-written list;
* every constituent is either validated with a hash-verified dataset of exactly
  26,280 closed hourly candles, or excluded with a reason from the frozen
  vocabulary;
* the v2 confirmatory window and the v1 holdout are untouched, and the v3
  execution state follows the selection authorization rather than the manifests.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_V3 = REPO_ROOT / "research" / "universe_manifest_v3.json"
DATA_V3 = REPO_ROOT / "research" / "data_manifest_v3.json"
SPEC_V3 = REPO_ROOT / "configs" / "research_v3.json"
AMENDMENT = REPO_ROOT / "configs" / "research_v3_exclusion_amendment_1.json"

VALIDATED_PAIRS = (
    "AAVEUSDT",
    "ICPUSDT",
    "PEPEUSDT",
    "QNTUSDT",
    "SHIBUSDT",
    "WLDUSDT",
)

MIN_CANDLES = 26280
HOUR_MS = 3600 * 1000

#: The v1 evidence, which a v3 expansion may not touch.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_research_v3_manifests", REPO_ROOT / "scripts" / "verify_research_v3_manifests.py"
)
validation = _load_module(
    "v3_constituent_validation", REPO_ROOT / "scripts" / "v3_constituent_validation.py"
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_manifest_hashes_recompute_from_their_bodies():
    universe = _load(UNIVERSE_V3)
    data = _load(DATA_V3)
    assert universe["manifest_hash"] == verifier.compute_manifest_hash(
        universe, tuple(universe["hashing"]["manifest_hash_excluded_keys"])
    )
    assert data["manifest_hash"] == verifier.compute_manifest_hash(
        data, tuple(data["hashing"]["manifest_hash_excluded_keys"])
    )


def test_a_tampered_manifest_changes_its_hash():
    universe = _load(UNIVERSE_V3)
    tampered = json.loads(json.dumps(universe))
    tampered["eligible_assets"][0]["validated"] = not tampered["eligible_assets"][0]["validated"]
    assert verifier.compute_manifest_hash(
        tampered, tuple(universe["hashing"]["manifest_hash_excluded_keys"])
    ) != universe["manifest_hash"]


def test_the_snapshot_is_the_in_window_retrieval_and_is_not_re_retrieved():
    universe = _load(UNIVERSE_V3)
    spec = _load(SPEC_V3)
    source = universe["market_cap_source"]
    raw = REPO_ROOT / source["raw_response_path"]
    assert _sha256_file(raw) == source["raw_response_hash"]
    retrieved = validation.parse_iso_utc(source["retrieval_timestamp_utc"])
    window = spec["universe"]["snapshot_retrieval"]
    assert validation.parse_iso_utc(window["not_before_utc"]) <= retrieved
    assert retrieved <= validation.parse_iso_utc(window["deadline_utc"])
    assert source["endpoint"] == spec["universe"]["endpoint"]


def test_the_candidate_batch_is_re_derivable_from_the_stored_snapshot():
    spec = _load(SPEC_V3)
    amendment = _load(AMENDMENT)
    universe = _load(UNIVERSE_V3)
    v1_universe = _load(REPO_ROOT / "research" / "universe_manifest.json")
    v2_universe = _load(REPO_ROOT / "research" / "universe_manifest_v2.json")
    markets = json.loads(
        (REPO_ROOT / universe["market_cap_source"]["raw_response_path"]).read_text(encoding="utf-8")
    )
    batch, rule_excluded = validation.derive_batch(spec, amendment, markets, v1_universe, v2_universe)
    derived = [entry["binance_pair"] for entry in batch]
    manifest_pairs = [
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        for asset in universe["eligible_assets"]
    ]
    assert derived == manifest_pairs
    assert len(rule_excluded) == len(universe["excluded_assets"])
    assert all(
        asset["market_cap_usd"] < spec["universe"]["expansion_scope"]["prior_universe_floor"][
            "floor_market_cap_usd"]
        for asset in universe["eligible_assets"]
    )


def test_the_validated_constituents_are_exactly_the_expected_six():
    universe = _load(UNIVERSE_V3)
    validated = sorted(
        asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        for asset in universe["eligible_assets"]
        if asset.get("validated")
    )
    assert validated == sorted(VALIDATED_PAIRS)
    summary = universe["validation_summary"]
    assert summary["candidate_count"] == 20
    assert summary["validated_count"] == 6
    assert summary["excluded_after_validation_count"] == 14


def test_every_excluded_candidate_records_a_frozen_reason():
    universe = _load(UNIVERSE_V3)
    data = _load(DATA_V3)
    allowed = {
        "binance_spot_unavailable",
        "coverage_gap",
        "insufficient_hourly_history",
        "candle_validation_failed",
    }
    excluded = [asset for asset in universe["eligible_assets"] if not asset.get("validated")]
    assert len(excluded) == 14
    for asset in excluded:
        pair = asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        assert asset["exclusion_reason"] in allowed, pair
        assert (data["validation_results"][pair]["exclusion_reason"]
                == asset["exclusion_reason"]), pair


def test_every_validated_constituent_has_a_hash_verified_dataset():
    universe = _load(UNIVERSE_V3)
    data = _load(DATA_V3)
    for asset in universe["eligible_assets"]:
        if not asset.get("validated"):
            continue
        pair = asset.get("binance_pair") or f"{asset.get('symbol')}USDT"
        record = data["assets"][pair]
        path = REPO_ROOT / record["dataset_path"]
        assert path.exists(), pair
        content = path.read_text(encoding="utf-8")
        assert hashlib.sha256(content.encode("utf-8")).hexdigest() == record["content_hash"], pair
        assert data["content_hashes"][pair] == record["content_hash"], pair
        rows = content.strip().splitlines()
        assert len(rows) - 1 == MIN_CANDLES, pair
        timestamps = [int(row.split(",")[0]) for row in rows[1:]]
        assert all(timestamp % HOUR_MS == 0 for timestamp in timestamps), pair
        assert len(set(timestamps)) == len(timestamps), pair
        assert timestamps == sorted(timestamps), pair


def test_the_data_manifest_records_verified_provenance():
    data = _load(DATA_V3)
    assert data["candles_verified"] is True
    assert data["provenance_ok"] is True
    assert data["data_source"]["interval"] == "1h"
    assert data["data_source"]["provider"] == "binance"
    assert data["window_policy"]["candle_count"] == MIN_CANDLES
    assert data["window_policy"]["closed_candles_only"] is True
    assert data["window_policy"]["bound_to"] == "market_cap_source_retrieval_timestamp_utc"


def test_the_confirmatory_window_is_unexposed():
    data = _load(DATA_V3)
    window = data["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0
    assert window["v1_holdout_reuse"] == "forbidden"


def test_the_v3_execution_state_is_consistent_with_the_authorization():
    """The v3 execution state follows the authorization, not the manifests.

    The rule "nothing has run under v3" was **replaced, not deleted**. It was
    true while the v3 selection authorization did not exist and it is false by
    design once the authorized run has been performed. The replacement is
    state-adaptive and never weaker than the state it replaces:

    * while the authorization does not exist, no v3 execution artifact may
      exist -- the manifests authorize nothing;
    * once it exists, the authorized run has been performed: the v3 execution
      artifacts exist, and the ledger of the run is bound to the authorization's
      manifest hash and reports the outcome for every frozen candidate.
    """
    authorization_path = (
        REPO_ROOT / "configs" / "research_v3_selection_authorization_1.json"
    )
    artifacts = (
        "research/shards_v3",
        "research/ledger_v3.json",
        "research/results_manifest_v3.json",
        "research/results_v3.jsonl",
        "research_state/checkpoint_v3.json",
    )
    if not authorization_path.exists():
        for relative in artifacts:
            assert not (REPO_ROOT / relative).exists(), relative
        return

    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    pairs = list(authorization["authorized_run"]["scope"]["binance_pairs"])
    for relative in artifacts[:3] + artifacts[4:]:
        assert (REPO_ROOT / relative).exists(), relative
    # The result stream is a gitignored projection of the shards; it need not
    # be materialized on a fresh checkout.
    stream_path = REPO_ROOT / "research/results_v3.jsonl"
    if stream_path.exists():
        assert stream_path.is_file()
    ledger = json.loads((REPO_ROOT / "research" / "ledger_v3.json").read_text(encoding="utf-8"))
    assert ledger["authorization_manifest_hash"] == authorization["manifest_hash"]
    assert ledger["status"] == "COMPLETED"
    assert ledger["holdout_exposed_count"] == 0
    selection = ledger["selection"]
    assert selection["assets_evaluated"] == len(pairs)
    assert sorted(selection["per_asset"]) == sorted(pairs)


def test_the_code_hash_is_the_authorized_value_of_record():
    universe = _load(UNIVERSE_V3)
    data = _load(DATA_V3)
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert universe["code_hash"] == authorization["code_hash"]
    assert data["code_hash"] == authorization["code_hash"]
    assert universe["canonical_source_digest"] == data["canonical_source_digest"]


def test_the_v1_evidence_is_untouched():
    for relative, digest in V1_ARTIFACT_SHA256.items():
        path = REPO_ROOT / relative
        if not path.exists():
            pytest.skip(f"{relative} is not present in this checkout")
        assert _sha256_file(path) == digest, relative


def test_the_v2_universe_manifest_is_untouched():
    spec = _load(SPEC_V3)
    v2 = _load(REPO_ROOT / "research" / "universe_manifest_v2.json")
    recorded = spec["universe"]["expansion_scope"]["prior_universe_floor"]["source_manifest_hash"]
    assert v2["manifest_hash"] == recorded

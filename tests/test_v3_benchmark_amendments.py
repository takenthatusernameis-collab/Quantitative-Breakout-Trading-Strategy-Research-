"""Tests for the v3 benchmark amendment cascade.

BRAIN-013 publishes the BTCUSDT benchmark entry and re-binds the data-manifest
identity of the frozen v3 scope by a three-step versioned cascade:

* ``configs/research_v3_data_manifest_amendment_1.json`` -- publishes the
  benchmark entry and the *effective* data-manifest identity;
* ``configs/research_v3_candidate_freeze_amendment_2.json`` -- re-binds the
  identity inside the frozen candidate set;
* ``configs/research_v3_execution_amendment_1.json`` -- re-binds the identity
  inside the execution protocol and records the benchmark rule.

These tests prove that

* every amendment recomputes its own manifest hash and is produced
  deterministically by its builder;
* the effective data-manifest identity recomputes from the base manifest plus
  the published entry, and the two downstream amendments bind exactly that
  identity;
* the base artifacts are **not** edited in place: their bytes still hash to
  the digests the cascade records;
* the cascade authorizes nothing: no run, no grid, no confirmatory read;
* the read-only verifiers agree with the repository.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_AMENDMENT = REPO_ROOT / "configs" / "research_v3_data_manifest_amendment_1.json"
FREEZE_AMENDMENT_2 = (
    REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_2.json"
)
EXECUTION_AMENDMENT_1 = REPO_ROOT / "configs" / "research_v3_execution_amendment_1.json"
DATA_MANIFEST = REPO_ROOT / "research" / "data_manifest_v3.json"
EXECUTION_PROTOCOL = REPO_ROOT / "configs" / "research_v3_execution.json"
FREEZE = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1 = (
    REPO_ROOT / "configs" / "research_v3_candidate_freeze_amendment_1.json"
)
AUTHORIZATION = REPO_ROOT / "configs" / "research_v3_selection_authorization_1.json"

V1_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = _load_module(
    "v3_benchmark_amendment_common", REPO_ROOT / "scripts" / "v3_benchmark_amendment_common.py"
)


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _manifest_hash(document: dict, excluded_keys) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "path",
    [DATA_AMENDMENT, FREEZE_AMENDMENT_2, EXECUTION_AMENDMENT_1],
    ids=["data_amendment_1", "freeze_amendment_2", "execution_amendment_1"],
)
def test_amendment_recomputes_its_own_manifest_hash(path):
    document = _load(path)
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    assert excluded, "an amendment must declare its excluded keys"
    assert _manifest_hash(document, excluded) == document["manifest_hash"]


@pytest.mark.parametrize(
    ("builder_name", "artifact_path"),
    [
        ("build_v3_data_manifest_amendment_1", DATA_AMENDMENT),
        ("build_v3_candidate_freeze_amendment_2", FREEZE_AMENDMENT_2),
        ("build_v3_execution_amendment_1", EXECUTION_AMENDMENT_1),
    ],
    ids=["data_amendment_1", "freeze_amendment_2", "execution_amendment_1"],
)
def test_amendment_is_reproduced_deterministically_by_its_builder(builder_name, artifact_path):
    builder = _load_module(builder_name, REPO_ROOT / "scripts" / f"{builder_name}.py")
    rebuilt = builder.build(REPO_ROOT)
    assert rebuilt == _load(artifact_path)


def test_effective_data_manifest_identity_recomputes_and_is_bound_downstream():
    amendment = _load(DATA_AMENDMENT)
    base = _load(DATA_MANIFEST)
    entry = (amendment["benchmark_asset"] or {}).get("entry")
    assert isinstance(entry, dict)

    body = json.loads(json.dumps(base))
    body.pop("manifest_hash", None)
    body.get("snapshot_identity", {}).pop("data_manifest_hash", None)
    body.setdefault("assets", {})["BTCUSDT"] = entry
    body.setdefault("content_hashes", {})["BTCUSDT"] = entry["content_hash"]
    body["benchmark_asset"] = {
        "symbol": "BTCUSDT",
        "role": "trend_filter_and_benchmark",
        "included_in_universe": True,
        "is_candidate": False,
        "content_hash": entry["content_hash"],
        "dataset_path": entry["dataset_path"],
        "first_candle_timestamp": entry["first_candle_timestamp"],
        "last_candle_timestamp": entry["last_candle_timestamp"],
        "observed_candle_count": entry["observed_candle_count"],
        "source": "configs/research_v3_data_manifest_amendment_1.json",
        "alignment_rule": (
            "the benchmark series and the asset series are aligned by UTC candle close: "
            "both are sliced to the same fold window before the frozen engine is called, "
            "and no observation is forward-filled"
        ),
    }
    recomputed = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    effective = amendment["effective_data_manifest"]["effective_data_manifest_hash"]
    assert recomputed == effective
    assert amendment["effective_data_manifest"]["base_manifest_hash"] == base["manifest_hash"]

    freeze_amendment = _load(FREEZE_AMENDMENT_2)
    assert freeze_amendment["rebound_identity"]["effective_data_manifest_hash"] == effective
    assert freeze_amendment["rebound_identity"]["base_data_manifest_hash"] == base["manifest_hash"]

    execution_amendment = _load(EXECUTION_AMENDMENT_1)
    assert execution_amendment["evaluation_scope"]["data_manifest_hash"] == effective


def test_base_artifacts_are_not_edited_in_place():
    data_amendment = _load(DATA_AMENDMENT)
    problem = data_amendment["problem"]
    assert _sha256_file(DATA_MANIFEST) == problem["affected_artifact_sha256"]

    execution_amendment = _load(EXECUTION_AMENDMENT_1)
    problem = execution_amendment["problem"]
    assert _sha256_file(EXECUTION_PROTOCOL) == problem["affected_artifact_sha256"]

    freeze_amendment = _load(FREEZE_AMENDMENT_2)
    problem = freeze_amendment["problem"]
    assert _sha256_file(FREEZE) == problem["affected_artifact_sha256"]

    # The frozen candidate set and its first amendment are untouched as well.
    assert _load(FREEZE)["manifest_hash"] == freeze_amendment["problem"][
        "affected_artifact_manifest_hash"
    ]
    assert _load(FREEZE_AMENDMENT_1)["manifest_hash"] == "1f0f3d6535d2e7b16fce093177f8d7ca1048bc8597c8df1b0835208b29b54e55"


def test_freeze_amendment_2_rebinds_the_identity_without_changing_the_candidate_set():
    freeze_amendment = _load(FREEZE_AMENDMENT_2)
    amendment_1 = _load(FREEZE_AMENDMENT_1)
    pairs = sorted(
        str(member["binance_pair"])
        for member in (amendment_1["validated_candidate_set"] or {}).get("members") or []
    )
    assert sorted(freeze_amendment["frozen_candidate_set"]["binance_pairs"]) == pairs
    assert freeze_amendment["frozen_candidate_set"]["count"] == len(pairs) == 6
    assert "BTCUSDT" not in pairs, "the benchmark is not a candidate"


def test_cascade_authorizes_nothing():
    freeze_amendment = _load(FREEZE_AMENDMENT_2)
    execution_amendment = _load(EXECUTION_AMENDMENT_1)
    for document in (freeze_amendment, execution_amendment):
        authorization = document["execution_authorization"]
        assert authorization["execution_authorized"] is False
        assert authorization["grid_run_authorized"] is False
        assert authorization["selection_authorization_present"] is False
    # The cascade is not the selection authorization: the selection
    # authorization is a separate, versioned artifact. While it does not exist
    # no v3 run is authorized; once it exists it must be the hash-bound
    # artifact that permits exactly one bounded selection run over the frozen
    # candidate set. The state-adaptive rule replaced -- and is stronger than
    # -- the former "the authorization must not exist" check.
    assert common.selection_authorization_failures(REPO_ROOT) == []


def test_v1_anchors_are_untouched():
    for relative in V1_ANCHORS:
        path = REPO_ROOT / relative
        assert path.exists()
    # The v1 anchors are bound by digest in the cascade; the data-manifest
    # amendment records them and the verifiers check them.
    data_amendment = _load(DATA_AMENDMENT)
    anchors = (data_amendment.get("related_artifacts") or {}).get("v1_anchors") or {}
    assert anchors
    for relative, digest in anchors.items():
        assert _sha256_file(REPO_ROOT / relative) == digest


@pytest.mark.parametrize(
    "verifier_name",
    [
        "verify_v3_data_manifest_amendment_1",
        "verify_v3_candidate_freeze_amendment_2",
        "verify_v3_execution_amendment_1",
    ],
)
def test_read_only_verifiers_agree_with_the_repository(verifier_name):
    verifier = _load_module(verifier_name, REPO_ROOT / "scripts" / f"{verifier_name}.py")
    report = verifier.verify(REPO_ROOT)
    assert report["ok"] is True, report.get("failures")
    assert report.get("failures") == []

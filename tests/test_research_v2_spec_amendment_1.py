from __future__ import annotations

import json
import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_amendment():
    return json.loads((REPO_ROOT / "configs/research_v2_spec_amendment_1.json").read_text())


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _manifest_hash(doc):
    excluded = tuple(doc.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    body = {k: v for k, v in doc.items() if k not in excluded}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def test_manifest_hash_recomputes():
    doc = _load_amendment()
    assert _manifest_hash(doc) == doc["manifest_hash"]


def test_design_only_no_execution():
    doc = _load_amendment()
    assert doc["amendment_status"] == "PREREGISTERED_AMENDMENT_DESIGN_ONLY"
    assert doc["artifact"] == "v2_spec_amendment"


def test_p2_p3_delivered_by_reference():
    doc = _load_amendment()
    rec = doc["reconciliation"]
    assert rec["p2_status_recorded"] == "DELIVERED"
    assert rec["p3_status_recorded"] == "DELIVERED"
    universe = json.loads((REPO_ROOT / "research/universe_manifest_v2.json").read_text())
    data = json.loads((REPO_ROOT / "research/data_manifest_v2.json").read_text())
    freeze = json.loads((REPO_ROOT / "configs/research_v2_candidate_freeze.json").read_text())
    assert rec["p2_manifest_hash"] == universe["manifest_hash"]
    assert rec["p3_manifest_hash"] == data["manifest_hash"]
    assert rec["candidate_freeze_hash"] == freeze["manifest_hash"]


def test_immutable_spec_not_edited_by_amendment():
    doc = _load_amendment()
    rec = doc["reconciliation"]
    spec = json.loads((REPO_ROOT / "configs/research_v2.json").read_text())
    assert rec["specification_hash"] == spec["specification_hash"]
    assert "immutable" in rec["note"].lower()


def test_portability_decision_referenced():
    doc = _load_amendment()
    assert doc["portability_decision"]["reference"] == "configs/research_v2_code_hash_portability_decision.json"


def test_no_v2_execution_artifacts():
    for rel in ["research/shards_v2", "research/ledger_v2.json", "research/results_manifest_v2.json",
                "research/results_v2.jsonl", "research_state/checkpoint_v2.json"]:
        assert not (REPO_ROOT / rel).exists()

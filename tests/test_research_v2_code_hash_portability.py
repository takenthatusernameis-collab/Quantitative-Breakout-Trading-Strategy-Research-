import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "configs" / "research_v2_code_hash_portability.json"
VERIFIER = REPO_ROOT / "scripts" / "verify_research_v2_code_hash_portability.py"
V1_AUTH = REPO_ROOT / "research_state" / "campaign_authorization.json"
EXEC_AMEND = REPO_ROOT / "configs" / "research_v2_execution_amendment_1.json"

AUTHORIZED = "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"


def canonicalize_manifest(obj):
    m = json.loads(json.dumps(obj))
    m.pop("manifest_hash", None)
    return json.dumps(m, sort_keys=True).encode()


def test_artifact_exists_and_manifest_hash_recomputes():
    with open(ARTIFACT) as f:
        art = json.load(f)
    mh = art["manifest_hash"]
    assert mh == hashlib.sha256(canonicalize_manifest(art)).hexdigest()


def test_decision_keeps_authorized_digest_and_uses_canonical_verification():
    with open(ARTIFACT) as f:
        art = json.load(f)
    assert art["decision"]["chosen_approach"] == "keep_authorized_digest_use_canonical_verification"
    assert art["digests"]["authorized_code_hash"] == AUTHORIZED


def test_forbids_editing_src_or_rotating_digest():
    with open(ARTIFACT) as f:
        art = json.load(f)
    c = art["constraints"]
    assert c["src_must_not_be_modified"] is True
    assert c["v1_campaign_authorization_must_remain_untouched"] is True
    assert c["v2_identity_tuples_must_remain_unchanged"] is True


def test_v1_campaign_authorization_unchanged():
    with open(V1_AUTH) as f:
        va = json.load(f)
    assert va["authorized"] is True
    assert va["code_hash"] == AUTHORIZED


def test_exec_amendment_reflects_correct_rule():
    with open(EXEC_AMEND) as f:
        ea = json.load(f)
    chc = ea["code_hash_constraint"]
    assert chc["authorized_code_hash"] == AUTHORIZED
    outside = set(chc["paths_correctly_classified_as_outside_hashed_set"])
    assert "scripts/" in outside
    assert "src/v2_campaign/" in outside
    assert "canonical_source_digest" in chc


def test_verifier_passes():
    res = subprocess.run([sys.executable, str(VERIFIER)], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["ok"] is True

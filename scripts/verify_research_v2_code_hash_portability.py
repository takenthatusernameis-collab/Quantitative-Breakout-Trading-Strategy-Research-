#!/usr/bin/env python3
import json
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "configs" / "research_v2_code_hash_portability.json"
V1_AUTH = REPO_ROOT / "research_state" / "campaign_authorization.json"
EXEC_AMEND = REPO_ROOT / "configs" / "research_v2_execution_amendment_1.json"

REQUIRED_KEYS = ["version", "id", "created_at_utc", "decision", "digests", "constraints", "manifest_hash"]
AUTHORIZED = "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"


def canonicalize_manifest(obj):
    m = json.loads(json.dumps(obj))
    m.pop("manifest_hash", None)
    return json.dumps(m, sort_keys=True).encode()


def main():
    failures = []
    try:
        with open(ARTIFACT) as f:
            art = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "failures": [f"cannot_read_artifact:{e}"]}))
        sys.exit(1)
    for k in REQUIRED_KEYS:
        if k not in art:
            failures.append(f"missing_key:{k}")
    if art.get("id") != "research_v2_code_hash_portability":
        failures.append("bad_id")
    if art.get("decision", {}).get("chosen_approach") != "keep_authorized_digest_use_canonical_verification":
        failures.append("bad_chosen_approach")
    if art.get("digests", {}).get("authorized_code_hash") != AUTHORIZED:
        failures.append("bad_authorized_code_hash")
    if art.get("constraints", {}).get("src_must_not_be_modified") is not True:
        failures.append("src_must_not_be_modified_false")
    if art.get("constraints", {}).get("v1_campaign_authorization_must_remain_untouched") is not True:
        failures.append("v1_auth_constraint_false")
    if art.get("constraints", {}).get("v2_identity_tuples_must_remain_unchanged") is not True:
        failures.append("v2_identity_constraint_false")
    # manifest hash
    mh = art.get("manifest_hash")
    if mh != hashlib.sha256(canonicalize_manifest(art)).hexdigest():
        failures.append("manifest_hash_mismatch")
    # v1 auth untouched
    try:
        with open(V1_AUTH) as f:
            va = json.load(f)
        if va.get("code_hash") != AUTHORIZED or va.get("authorized") is not True:
            failures.append("v1_auth_changed")
    except Exception as e:
        failures.append(f"cannot_read_v1_auth:{e}")
    # exec amend has correct constraint
    try:
        with open(EXEC_AMEND) as f:
            ea = json.load(f)
        chc = ea.get("code_hash_constraint", {})
        if chc.get("authorized_code_hash") != AUTHORIZED:
            failures.append("amendment_authorized_code_hash_mismatch")
        outside = set(chc.get("paths_correctly_classified_as_outside_hashed_set", []))
        if "scripts/" not in outside or "src/v2_campaign/" not in outside:
            failures.append("amendment_outside_paths_mismatch")
        if "canonical_source_digest" not in chc:
            failures.append("amendment_missing_canonical_source_digest")
    except Exception as e:
        failures.append(f"cannot_read_exec_amend:{e}")
    if failures:
        print(json.dumps({"ok": False, "failures": failures}))
        sys.exit(1)
    print(json.dumps({"ok": True, "failures": []}))
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v3 execution amendment 2.

The amendment is immutable and hash-bound.  It adds one path to the v3 result layout --
the published selected-configurations manifest -- and it authorizes nothing else.  The
verifier recomputes every expectation from the repository: the self-hash, the digest of
the amended protocol, the digests of every artifact the amendment names, the digest of
the published manifest, and the digests of the v1 artifacts that the v3 line may not
touch.  It never writes to the repository and never contacts a provider.

Exit status is 0 when every check passes and 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

AMENDMENT_RELATIVE = "configs/research_v3_execution_amendment_2.json"
PROTOCOL_RELATIVE = "configs/research_v3_execution.json"
SPEC_V3_RELATIVE = "configs/research_v3.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_1_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"
FREEZE_AMENDMENT_2_RELATIVE = "configs/research_v3_candidate_freeze_amendment_2.json"
UNIVERSE_V3_RELATIVE = "research/universe_manifest_v3.json"
DATA_V3_RELATIVE = "research/data_manifest_v3.json"
DATA_AMENDMENT_1_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
EXECUTION_AMENDMENT_1_RELATIVE = "configs/research_v3_execution_amendment_1.json"
SELECTION_AUTH_RELATIVE = "configs/research_v3_selection_authorization_1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
LEDGER_V3_RELATIVE = "research/ledger_v3.json"
MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"

#: The v1 artifacts, byte-anchored.  The v3 line may not change any of them.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The manifest paths the amendment may never authorize.
FORBIDDEN_MANIFEST_PATHS = (
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

#: The rules the amendment's authorization rules must state.
REQUIRED_RULES = (
    "no second run",
    "no confirmatory-window evaluation",
    "no candle fetch",
    "re-derivable",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in set(excluded_keys)}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Verify the preregistered v3 execution amendment 2."""
    failures: List[str] = []
    root = Path(repo_root)

    required = [
        root / AMENDMENT_RELATIVE,
        root / PROTOCOL_RELATIVE,
        root / SPEC_V3_RELATIVE,
        root / SPEC_V1_RELATIVE,
        root / FREEZE_RELATIVE,
        root / FREEZE_AMENDMENT_1_RELATIVE,
        root / FREEZE_AMENDMENT_2_RELATIVE,
        root / UNIVERSE_V3_RELATIVE,
        root / DATA_V3_RELATIVE,
        root / DATA_AMENDMENT_1_RELATIVE,
        root / EXECUTION_AMENDMENT_1_RELATIVE,
        root / SELECTION_AUTH_RELATIVE,
        root / AUTHORIZATION_RELATIVE,
        root / LEDGER_V3_RELATIVE,
        root / MANIFEST_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {"ok": False, "failures": [f"missing artifact: {path.relative_to(root)}"]}

    amendment = _load(root / AMENDMENT_RELATIVE)
    protocol = _load(root / PROTOCOL_RELATIVE)
    manifest = _load(root / MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_V3_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)

    # 1. The document is self-hashing.
    excluded = tuple((amendment.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        return {"ok": False, "failures": ["the amendment declares no manifest_hash_excluded_keys"]}
    if amendment.get("manifest_hash") != compute_manifest_hash(amendment, excluded):
        failures.append("1: manifest_hash does not recompute from the document")

    # 2. The amended protocol is untouched.
    amends = amendment.get("amends") or {}
    if amends.get("file") != PROTOCOL_RELATIVE:
        failures.append("2: the amendment does not amend the v3 execution protocol")
    if amends.get("file_sha256") != sha256_file(root / PROTOCOL_RELATIVE):
        failures.append("2: the v3 execution protocol changed")
    if amends.get("protocol_specification_hash") != protocol.get("specification_hash"):
        failures.append("2: the recorded protocol specification hash differs from the protocol")

    # 3. Every artifact the amendment names is unchanged.
    for name, reference in sorted((amendment.get("references") or {}).items()):
        relative = reference.get("file")
        if not relative:
            failures.append(f"3: the reference {name} names no file")
            continue
        path = root / relative
        if not path.exists():
            failures.append(f"3: the referenced artifact {relative} is missing")
            continue
        document = _load(path)
        for key in ("manifest_hash", "specification_hash"):
            recorded = reference.get(key)
            if recorded is None:
                continue
            observed = document.get(key)
            if observed != recorded:
                failures.append(f"3: the reference {name} records a {key} that the file does not carry")
        if reference.get("code_hash") is not None:
            if reference["code_hash"] != document.get("code_hash"):
                failures.append("3: the reference to the v1 campaign authorization records "
                                "another code hash")
        if reference.get("run_id") is not None:
            if reference["run_id"] != document.get("run_id"):
                failures.append("3: the reference to the v3 ledger records another run id")

    # 4. The authorized path is the published manifest's path.
    layout = amendment.get("v3_result_layout_amendment") or {}
    paths = layout.get("paths") or {}
    published_path = paths.get("selected_configurations_manifest_path")
    if published_path in FORBIDDEN_MANIFEST_PATHS:
        failures.append("4: the amendment authorizes a v1 candidate manifest path")
    if published_path != MANIFEST_RELATIVE:
        failures.append("4: the amendment does not authorize the published manifest path")
    protocol_layout = protocol.get("v3_result_layout") or {}
    for key in ("shard_directory", "ledger_path", "results_manifest_path"):
        if paths.get(key) != protocol_layout.get(key):
            failures.append(f"4: the amendment changes the v3 result layout path {key}")
    if layout.get("campaign_id") != protocol_layout.get("campaign_id"):
        failures.append("4: the amendment changes the v3 campaign id")
    if layout.get("writes_into_v1_forbidden") is not True:
        failures.append("4: the amendment does not forbid writes into the v1 artifacts")
    if layout.get("writes_into_v2_forbidden") is not True:
        failures.append("4: the amendment does not forbid writes into the v2 artifacts")

    # 5. The amendment binds the published manifest.
    manifest_excluded = tuple(manifest.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    if manifest.get("manifest_hash") != compute_manifest_hash(manifest, manifest_excluded):
        failures.append("5: the published manifest does not recompute its own hash")
    if paths.get("selected_configurations_manifest_hash") != manifest.get("manifest_hash"):
        failures.append("5: the amendment does not bind the published manifest's hash")

    # 6. The amendment authorizes nothing beyond the publication.
    rules = " ".join(str(rule) for rule in layout.get("authorization_rules") or []).lower()
    for required_rule in REQUIRED_RULES:
        if required_rule not in rules:
            failures.append(f"6: the authorization rules do not state '{required_rule}'")
    if amendment.get("amendment_status") != "PREREGISTERED_AMENDMENT_DESIGN_ONLY":
        failures.append("6: the amendment does not declare itself a design-only amendment")
    for key in ("execution_authorized", "grid_run_authorized", "evaluation_authorized"):
        if amendment.get(key) is not None:
            failures.append(f"6: the amendment claims the authorization flag {key}")

    # 7. The run that produced the published manifest is the completed, bounded run.
    if ledger.get("status") != "COMPLETED":
        failures.append("7: the v3 selection run is not completed")
    if ledger.get("campaign_id") != layout.get("campaign_id"):
        failures.append("7: the ledger and the amendment disagree on the campaign id")
    if ledger.get("holdout_exposed_count") != 0:
        failures.append("7: the v3 ledger records a holdout exposure")
    if manifest.get("exposure", {}).get("holdout_exposed_count") != 0:
        failures.append("7: the published manifest records a holdout exposure")

    # 8. The v1 artifacts and the authorized code hash are unchanged.
    for relative, expected in V1_ARTIFACT_SHA256.items():
        observed = sha256_file(root / relative)
        if observed is None:
            failures.append(f"8: the v1 artifact {relative} is missing")
        elif observed != expected:
            failures.append(f"8: the v1 artifact {relative} changed")
    if authorization.get("code_hash") != "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2":
        failures.append("8: the authorized v1 code hash changed")
    if authorization.get("authorized") is not True:
        failures.append("8: the v1 campaign authorization is not authorized")

    return {"ok": len(failures) == 0, "failures": failures}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT),
                        help="the repository to verify (default: the repository of this script)")
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 spec amendment 1.

``configs/research_v2_spec_amendment_1.json`` records that BRAIN-008 §6
prerequisites P2 and P3 are delivered by reference without editing
``configs/research_v2.json``. The verifier never writes to the repository,
never contacts a provider and never reads a candle. It checks:

* the manifest hash recomputes from the canonical content of the document;
* the amendment is design-only and authorizes nothing;
* P2 and P3 are referenced by their delivered manifest hashes;
* the immutable spec file is unchanged;
* the portability decision is referenced and self-consistent;
* no **confirmatory** execution artifact exists and the v1 artifacts are
  byte-identical.

The amendment records a *status*; it never triggers a run.  The v2 selection
run is a separate, separately authorized step that **has** been executed, so
the absence of a v2 selection artifact is not a property of this amendment and
is not checked here.  What must hold is that the amendment created no
confirmatory execution artifact and that the confirmatory window was never
exposed: the v2 selection ledger and checkpoint must both record
``holdout_exposed_count == 0``.

Exit status is 0 when every check passes and 1 otherwise.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AMENDMENT_RELATIVE = "configs/research_v2_spec_amendment_1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
PORTABILITY_DECISION_RELATIVE = "configs/research_v2_code_hash_portability_decision.json"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The paths a confirmatory evaluation writes.  None of them may exist while
#: the confirmatory window has not been evaluated.
CONFIRMATORY_EXECUTION_ARTIFACTS = (
    "research/shards_v2_confirmatory",
    "research/ledger_v2_confirmatory.json",
    "research/results_manifest_v2_confirmatory.json",
    "research/results_v2_confirmatory.jsonl",
    "research_state/checkpoint_v2_confirmatory.json",
    "research/confirmatory_window_v2",
)

#: The v2 selection artifacts, which must record that the confirmatory window
#: was never exposed.
SELECTION_EXPOSURE_ARTIFACTS = (
    "research/ledger_v2.json",
    "research_state/checkpoint_v2.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    return sha256_bytes(canonical(body).encode("utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    amendment_path = repo_root / AMENDMENT_RELATIVE

    required = (
        amendment_path,
        repo_root / SPEC_V2_RELATIVE,
        repo_root / UNIVERSE_V2_RELATIVE,
        repo_root / DATA_V2_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / PORTABILITY_DECISION_RELATIVE,
    )
    for path in required:
        if not path.exists():
            return {"ok": False, "failures": [f"missing artifact: {path.relative_to(repo_root)}"]}

    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    spec_v2 = json.loads((repo_root / SPEC_V2_RELATIVE).read_text(encoding="utf-8"))
    universe_v2 = json.loads((repo_root / UNIVERSE_V2_RELATIVE).read_text(encoding="utf-8"))
    data_v2 = json.loads((repo_root / DATA_V2_RELATIVE).read_text(encoding="utf-8"))
    freeze = json.loads((repo_root / FREEZE_RELATIVE).read_text(encoding="utf-8"))
    portability = json.loads((repo_root / PORTABILITY_DECISION_RELATIVE).read_text(encoding="utf-8"))

    # 1. Self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. Design-only
    if amendment.get("amendment_status") != "PREREGISTERED_AMENDMENT_DESIGN_ONLY":
        failures.append("amendment not marked as design-only")
    if amendment.get("artifact") != "v2_spec_amendment":
        failures.append("wrong artifact type")

    # 3. P2/P3 recorded as delivered by reference
    reconciliation = amendment.get("reconciliation") or {}
    if reconciliation.get("p2_status_recorded") != "DELIVERED":
        failures.append("P2 not recorded as DELIVERED")
    if reconciliation.get("p3_status_recorded") != "DELIVERED":
        failures.append("P3 not recorded as DELIVERED")
    if reconciliation.get("p2_manifest_hash") != universe_v2.get("manifest_hash"):
        failures.append("P2 manifest hash mismatch")
    if reconciliation.get("p3_manifest_hash") != data_v2.get("manifest_hash"):
        failures.append("P3 manifest hash mismatch")
    if reconciliation.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("candidate freeze hash mismatch")
    if reconciliation.get("specification_hash") != spec_v2.get("specification_hash"):
        failures.append("spec v2 hash mismatch")
    if reconciliation.get("configs_research_v2") != SPEC_V2_RELATIVE:
        failures.append("does not reference configs/research_v2.json")
    if "immutable" not in str(reconciliation.get("note") or "").lower():
        failures.append("note must state configs/research_v2.json is immutable")

    # 4. Portability decision referenced and self-consistent
    portability_ref = amendment.get("portability_decision") or {}
    if portability_ref.get("reference") != PORTABILITY_DECISION_RELATIVE:
        failures.append("does not reference portability decision")
    portability_excluded = tuple(
        portability.get("hashing", {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    portability_recomputed = compute_manifest_hash(portability, portability_excluded)
    if portability.get("manifest_hash") != portability_recomputed:
        failures.append(
            "the referenced portability decision does not self-hash: declared "
            f"{portability.get('manifest_hash')}, recomputed {portability_recomputed}"
        )

    # 5. No confirmatory execution artifact exists
    for rel in CONFIRMATORY_EXECUTION_ARTIFACTS:
        if (repo_root / rel).exists():
            failures.append(f"confirmatory execution artifact exists: {rel}")

    # 6. The confirmatory window was never exposed
    for rel in SELECTION_EXPOSURE_ARTIFACTS:
        target = repo_root / rel
        if not target.exists():
            failures.append(f"v2 selection artifact missing: {rel}")
            continue
        document = json.loads(target.read_text(encoding="utf-8"))
        if document.get("holdout_exposed_count") != 0:
            failures.append(
                f"{rel} records holdout_exposed_count "
                f"{document.get('holdout_exposed_count')!r}, expected 0"
            )

    # 7. V1 artifacts unchanged
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"v1 artifact missing: {relative}")
            continue
        if sha256_file(target) != digest:
            failures.append(f"v1 artifact changed: {relative}")

    return {"ok": len(failures) == 0, "failures": failures}


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

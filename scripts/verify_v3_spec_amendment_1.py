#!/usr/bin/env python3
"""Read-only, offline verification of the v3 specification amendment 1.

The amendment corrects one stale reference of the immutable v3 specification
(``universe.eligibility_validation.data_integrity.data_manifest`` still names
the v2 data manifest) and records the delivered prerequisite status by
reference. This verifier checks that

* the amendment is self-hashing and its manifest hash recomputes;
* the immutable specification is byte-unchanged and still records the stale
  value, so the correction is not silently duplicated in the frozen file;
* the corrected value names the v3 data manifest and binds its current digest;
* the amendment binds the current v3 manifests, the candidate freeze and the
  freeze amendment by digest;
* the amendment authorizes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AMENDMENT_RELATIVE = "configs/research_v3_spec_amendment_1.json"
SPEC_RELATIVE = "configs/research_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
DATA_RELATIVE = "research/data_manifest_v3.json"
FREEZE_RELATIVE = "configs/research_v3_candidate_freeze.json"
FREEZE_AMENDMENT_RELATIVE = "configs/research_v3_candidate_freeze_amendment_1.json"

STALE_FIELD = "universe.eligibility_validation.data_integrity.data_manifest"


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


def compute_manifest_hash(document: Dict[str, Any],
                          excluded_keys: Tuple[str, ...] = ("manifest_hash",)) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    for relative in (AMENDMENT_RELATIVE, SPEC_RELATIVE, UNIVERSE_RELATIVE, DATA_RELATIVE,
                     FREEZE_RELATIVE, FREEZE_AMENDMENT_RELATIVE):
        if not (repo_root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    amendment = read_json(repo_root / AMENDMENT_RELATIVE)
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = read_json(repo_root / UNIVERSE_RELATIVE)
    data = read_json(repo_root / DATA_RELATIVE)
    freeze = read_json(repo_root / FREEZE_RELATIVE)
    freeze_amendment = read_json(repo_root / FREEZE_AMENDMENT_RELATIVE)

    # 1. the amendment is self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if amendment.get("manifest_hash") != compute_manifest_hash(amendment, excluded):
        failures.append("the spec amendment's manifest hash does not recompute from its body")

    # 2. the immutable specification is untouched and still holds the stale value
    recorded_spec = (amendment.get("immutable_specification") or {})
    if recorded_spec.get("specification_hash") != spec.get("specification_hash"):
        failures.append("the amendment binds another specification")
    if recorded_spec.get("file_sha256") != sha256_file(repo_root / SPEC_RELATIVE):
        failures.append("the amendment records a stale specification digest")
    integrity = (spec["universe"]["eligibility_validation"].get("data_integrity") or {})
    corrections = amendment.get("corrections") or []
    if len(corrections) != 1:
        failures.append("the amendment does not record exactly one correction")
    else:
        correction = corrections[0]
        if correction.get("path") != STALE_FIELD:
            failures.append("the amendment corrects an unexpected field")
        if correction.get("recorded_value") != integrity.get("data_manifest"):
            failures.append("the amendment's recorded value is not the one the specification holds")
        if correction.get("effective_value") != DATA_RELATIVE:
            failures.append("the correction does not name the v3 data manifest")
        evidence = correction.get("evidence") or {}
        if evidence.get("manifest_hash") != data.get("manifest_hash"):
            failures.append("the correction does not bind the current v3 data manifest")
        if evidence.get("file_sha256") != sha256_file(repo_root / DATA_RELATIVE):
            failures.append("the correction records a stale data manifest digest")

    # 3. the amendment binds the current artifacts
    binding = amendment.get("binding") or {}
    for key, relative, manifest in (
        ("universe_manifest", UNIVERSE_RELATIVE, universe),
        ("data_manifest", DATA_RELATIVE, data),
        ("candidate_freeze", FREEZE_RELATIVE, freeze),
        ("candidate_freeze_amendment", FREEZE_AMENDMENT_RELATIVE, freeze_amendment),
    ):
        block = binding.get(key) or {}
        if block.get("manifest_hash") != manifest.get("manifest_hash"):
            failures.append(f"the amendment does not bind the current {key}")
        if block.get("file_sha256") != sha256_file(repo_root / relative):
            failures.append(f"the amendment records a stale {key} digest")

    # 4. the prerequisite reconciliation
    reconciliation = amendment.get("reconciliation") or {}
    for pid in ("P2", "P3", "P4"):
        if reconciliation.get(pid, {}).get("status_recorded") != "DELIVERED":
            failures.append(f"the amendment does not record {pid} as delivered")
    for pid in ("P5", "P6"):
        if reconciliation.get(pid, {}).get("status_recorded") != "OUTSTANDING":
            failures.append(f"the amendment does not record {pid} as outstanding")

    # 5. the amendment authorizes nothing
    authorization = amendment.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        failures.append("the amendment does not withhold the execution authorization")
    if authorization.get("grid_run_authorized") is not False:
        failures.append("the amendment does not withhold the grid-run authorization")

    return {
        "ok": not failures,
        "failures": failures,
        "manifest_hash": amendment.get("manifest_hash"),
        "corrected_field": STALE_FIELD,
        "effective_value": DATA_RELATIVE,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

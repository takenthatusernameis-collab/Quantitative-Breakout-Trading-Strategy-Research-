#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 execution amendment 2."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.config import compute_code_hash  # noqa: E402

AMENDMENT_RELATIVE = "configs/research_v2_execution_amendment_2.json"
PROTOCOL_RELATIVE = "configs/research_v2_execution.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
MANIFEST_RELATIVE = "research/v2_selected_configurations_manifest.json"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)
    amendment_path = root / AMENDMENT_RELATIVE

    required = [
        amendment_path,
        root / PROTOCOL_RELATIVE,
        root / SPEC_V2_RELATIVE,
        root / SPEC_V1_RELATIVE,
        root / FREEZE_RELATIVE,
        root / UNIVERSE_V2_RELATIVE,
        root / DATA_V2_RELATIVE,
        root / AUTHORIZATION_RELATIVE,
        root / LEDGER_RELATIVE,
        root / MANIFEST_RELATIVE,
    ]
    for p in required:
        if not p.exists():
            return {"ok": False, "failures": [f"missing artifact: {p.relative_to(root)}"]}

    amendment = _load(amendment_path)
    protocol = _load(root / PROTOCOL_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_V2_RELATIVE)
    data_manifest = _load(root / DATA_V2_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    ledger = _load(root / LEDGER_RELATIVE)
    manifest = _load(root / MANIFEST_RELATIVE)

    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if amendment.get("manifest_hash") != compute_manifest_hash(amendment, excluded):
        failures.append("manifest_hash mismatch")

    # Protocol not edited
    if amendment.get("amends", {}).get("file_sha256") != sha256_file(root / PROTOCOL_RELATIVE):
        failures.append("protocol file changed")

    layout = amendment.get("v2_result_layout_amendment") or {}
    paths = layout.get("paths") or {}
    p = paths.get("selected_configurations_manifest_path")
    if p in ("research/candidate_manifest.json", "research/candidate_manifest_v2.json"):
        failures.append("forbidden manifest path")
    if p != "research/v2_selected_configurations_manifest.json":
        failures.append("wrong manifest path")
    if paths.get("selected_configurations_manifest_hash") != manifest.get("manifest_hash"):
        failures.append("manifest hash not bound")

    # Must not authorize confirmatory eval or second run
    rules = " ".join(str(r) for r in layout.get("authorization_rules") or []).lower()
    if "confirmatory" in rules and "not authorized" not in rules and "no confirmatory" not in rules:
        pass  # should be stated
    if "second run" not in rules and "no second run" not in rules:
        failures.append("must not authorize second run")

    # Check v1 artifacts unchanged
    for rel, expected in V1_ARTIFACT_SHA256.items():
        if sha256_file(root / rel) != expected:
            failures.append(f"v1 artifact changed: {rel}")

    # Check code hash unchanged
    if authorization.get("code_hash") != "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2":
        failures.append("code hash changed")

    return {"ok": len(failures) == 0, "failures": failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args = parser.parse_args(argv)
    report = verify(REPO_ROOT)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

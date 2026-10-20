#!/usr/bin/env python3
"""Read-only, offline verification of the v2 selected-configurations manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402
from breakout_research.config import compute_code_hash  # noqa: E402

MANIFEST_RELATIVE = "research/v2_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
SELECTION_AUTH_RELATIVE = "configs/research_v2_selection_authorization_1.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SHARDS_DIR = REPO_ROOT / "research" / "shards_v2" / "v2-campaign"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: tuple) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_shard_records(shard_dir: Path):
    for shard_path in sorted(shard_dir.glob("*.jsonl")):
        with shard_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    required = [
        root / MANIFEST_RELATIVE,
        root / LEDGER_RELATIVE,
        root / FREEZE_RELATIVE,
        root / SELECTION_AUTH_RELATIVE,
        root / UNIVERSE_V2_RELATIVE,
        root / DATA_V2_RELATIVE,
        root / SPEC_V1_RELATIVE,
        root / SPEC_V2_RELATIVE,
    ]
    for p in required:
        if not p.exists():
            return {"ok": False, "failures": [f"missing artifact: {p.relative_to(root)}"]}

    manifest = _load(root / MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    universe = _load(root / UNIVERSE_V2_RELATIVE)
    data_manifest = _load(root / DATA_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)

    excluded = tuple(manifest.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    declared = manifest.get("manifest_hash")
    recomputed = compute_manifest_hash(manifest, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch")

    # Check run identity matches
    run_id = manifest.get("run_identity") or {}
    if run_id.get("run_id") != ledger["run_id"]:
        failures.append("run_id mismatch with ledger")
    if run_id.get("campaign_id") != ledger["campaign_id"]:
        failures.append("campaign_id mismatch")
    if run_id.get("authorization_manifest_hash") != selection_auth["manifest_hash"]:
        failures.append("authorization_manifest_hash mismatch")

    # Check all assets covered
    frozen_pairs = list(freeze["frozen_candidate_set"]["binance_pairs"])
    if set(manifest.get("selections", {}).keys()) != set(frozen_pairs):
        failures.append("selections do not cover all frozen assets")
    if len(manifest.get("selections", {})) != 18:
        failures.append("selections count wrong")

    # Compare with ledger exactly
    ledger_sel = ledger.get("selection", {})
    for asset in frozen_pairs:
        msel = manifest["selections"].get(asset, {})
        lsel = ledger_sel["per_asset"].get(asset, {})
        if msel.get("config_id") != lsel.get("config_id"):
            failures.append(f"config_id mismatch for {asset}")
        if msel.get("status") != lsel.get("status"):
            failures.append(f"status mismatch for {asset}")
        if msel.get("economic_status") != lsel.get("economic_status"):
            failures.append(f"economic_status mismatch for {asset}")

    if manifest.get("assets_with_candidate") != ledger_sel.get("assets_with_candidate"):
        failures.append("assets_with_candidate mismatch")
    if manifest.get("assets_without_candidate") != ledger_sel.get("assets_without_candidate"):
        failures.append("assets_without_candidate mismatch")
    if manifest.get("outcome") != ledger_sel.get("outcome"):
        failures.append("outcome mismatch")

    # Verify records from shards
    code_hash = compute_code_hash()
    spec_hash = sha256_bytes(canonical(spec_v1))
    data_hash = data_manifest.get("manifest_hash") or sha256_bytes(canonical(data_manifest))
    count = 0
    for record in iter_shard_records(SHARDS_DIR):
        recomputed_eid = compute_experiment_id(
            record.get("specification_hash") or spec_hash,
            record.get("code_hash") or code_hash,
            record.get("data_hash") or data_hash,
            record["asset"],
            record["config_id"],
            int(record["fold_index"]),
            int(record["start_time"]),
            int(record["end_time"]),
            bool(record.get("is_holdout", False)),
            float(record["cost_multiplier"]),
            record.get("schema_version", "result-shard-v1"),
        )
        if recomputed_eid != record.get("experiment_id"):
            failures.append("experiment_id verification failed")
            break
        if record.get("is_holdout"):
            failures.append("holdout record found")
            break
        count += 1
    if count != 497664:
        failures.append(f"wrong record count {count}")
    if count != int(ledger["counts"]["records_written"]):
        failures.append("record count doesn't match ledger")

    return {"ok": len(failures) == 0, "failures": failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args = parser.parse_args(argv)
    report = verify(REPO_ROOT)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

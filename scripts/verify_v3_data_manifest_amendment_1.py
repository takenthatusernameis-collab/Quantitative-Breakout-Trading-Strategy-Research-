#!/usr/bin/env python3
"""Read-only, offline verification of the v3 data-manifest amendment 1.

The verifier recomputes every expectation from the repository: the benchmark
entry from the retrieved dataset, the alignment from the dataset files, the
effective data-manifest identity from the base manifest plus the published
entry, and the deviation counts from the completed v2 run's own evidence. It
never trusts a digest that is copied out of the artifact it is checking.

The rule that checks the selection authorization is state-adaptive and is never
weaker than the state it replaces. The cascade authorizes nothing by itself and
the selection authorization is a separate, versioned artifact: while it does
not exist, no v3 run is authorized; once it exists, it must be the hash-bound
artifact that permits exactly one bounded selection run over the frozen
candidate set, with the published benchmark dataset, the effective
data-manifest identity and the deviation disclosure bound into it. The former
"a v3 selection authorization exists" check was replaced -- not deleted -- by
that stronger check.

Exit status: 0 when the amendment is consistent with the repository, 1
otherwise.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from v3_benchmark_amendment_common import selection_authorization_failures  # noqa: E402

AMENDMENT_RELATIVE = "configs/research_v3_data_manifest_amendment_1.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v3.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v3.json"
SPEC_RELATIVE = "configs/research_v3.json"
EVIDENCE_RELATIVE = "research/v3_evidence/benchmark_retrieval.json"
RAW_RESPONSE_RELATIVE = "research/v3_evidence/benchmark_raw_klines.json"
DEVIATION_RELATIVE = "research/v3_evidence/v1_v2_btc_alignment_deviation.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
CONFIG_MANIFEST_RELATIVE = "research/config_manifest.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
AUTHORIZATION_RELATIVE = "configs/research_v3_selection_authorization_1.json"

V1_ANCHORS = (
    "configs/research_v1.json",
    "research/universe_manifest.json",
    "research/data_manifest.json",
    "research/candidate_manifest.json",
    "research/candidate_manifest_v2.json",
)

V3_EXECUTION_PATHS = (
    "research/shards_v3",
    "research/ledger_v3.json",
    "research/results_manifest_v3.json",
    "research/results_v3.jsonl",
    "research_state/checkpoint_v3.json",
    "research/v3_selected_configurations_manifest.json",
)

BENCHMARK_SYMBOL = "BTCUSDT"
MIN_CANDLES = 26280


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dataset_window(repo_root: Path, dataset_path: str) -> Optional[Dict[str, Any]]:
    """The window of a canonical hourly CSV, recomputed from the file."""
    path = Path(repo_root) / dataset_path
    if not path.exists():
        return None
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    if len(rows) < 2:
        return None
    body = rows[1:]
    return {
        "first_candle_timestamp": int(body[0].split(",")[0]),
        "last_candle_timestamp": int(body[-1].split(",")[0]),
        "observed_candle_count": len(body),
        "file_sha256": sha256_file(path),
    }


def effective_data_manifest_hash(base: Dict[str, Any], entry: Dict[str, Any],
                                  source: str) -> str:
    """The effective data-manifest identity, recomputed independently.

    The base manifest keeps its own hashing rule (the self-hash is taken over
    the body with ``manifest_hash`` and ``snapshot_identity.data_manifest_hash``
    removed); the effective view is the base body plus the published benchmark
    entry, and it is hashed by the same rule.
    """
    body = copy.deepcopy(base)
    body.pop("manifest_hash", None)
    snapshot = body.get("snapshot_identity")
    if isinstance(snapshot, dict):
        snapshot.pop("data_manifest_hash", None)
    body.setdefault("assets", {})[BENCHMARK_SYMBOL] = copy.deepcopy(entry)
    body.setdefault("content_hashes", {})[BENCHMARK_SYMBOL] = entry["content_hash"]
    body["benchmark_asset"] = {
        "symbol": BENCHMARK_SYMBOL,
        "role": "trend_filter_and_benchmark",
        "included_in_universe": True,
        "is_candidate": False,
        "content_hash": entry["content_hash"],
        "dataset_path": entry["dataset_path"],
        "first_candle_timestamp": entry["first_candle_timestamp"],
        "last_candle_timestamp": entry["last_candle_timestamp"],
        "observed_candle_count": entry["observed_candle_count"],
        "source": source,
        "alignment_rule": (
            "the benchmark series and the asset series are aligned by UTC candle close: "
            "both are sliced to the same fold window before the frozen engine is called, "
            "and no observation is forward-filled"
        ),
    }
    return compute_manifest_hash(body, ("manifest_hash", "snapshot_identity.data_manifest_hash"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    root = Path(repo_root)

    for relative in (AMENDMENT_RELATIVE, DATA_MANIFEST_RELATIVE, UNIVERSE_RELATIVE,
                     SPEC_RELATIVE, EVIDENCE_RELATIVE, RAW_RESPONSE_RELATIVE,
                     DEVIATION_RELATIVE, LEDGER_RELATIVE, CONFIG_MANIFEST_RELATIVE,
                     SPEC_V1_RELATIVE):
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    amendment = read_json(root / AMENDMENT_RELATIVE)
    base = read_json(root / DATA_MANIFEST_RELATIVE)
    universe = read_json(root / UNIVERSE_RELATIVE)
    evidence = read_json(root / EVIDENCE_RELATIVE)
    deviation = read_json(root / DEVIATION_RELATIVE)
    ledger = read_json(root / LEDGER_RELATIVE)
    config_manifest = read_json(root / CONFIG_MANIFEST_RELATIVE)
    spec_v1 = read_json(root / SPEC_V1_RELATIVE)

    # 1. the amendment is self-hashing
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. the base data manifest is byte-unchanged and still carries its own hash
    problem = amendment.get("problem") or {}
    if problem.get("affected_artifact_manifest_hash") != base.get("manifest_hash"):
        failures.append("the amendment does not record the base manifest's current manifest_hash")
    if problem.get("affected_artifact_sha256") != sha256_file(root / DATA_MANIFEST_RELATIVE):
        failures.append("the recorded sha256 of the base data manifest does not match the file")

    # 3. the benchmark entry is recomputed from the dataset file itself
    benchmark = amendment.get("benchmark_asset") or {}
    entry = benchmark.get("entry") or {}
    dataset_path = str(benchmark.get("dataset_path") or "")
    if not dataset_path:
        failures.append("the amendment records no benchmark dataset path")
        return {"ok": False, "failures": failures}
    window = dataset_window(root, dataset_path)
    if window is None:
        failures.append("the benchmark dataset does not exist or is not a canonical hourly CSV")
        return {"ok": False, "failures": failures}
    if window["file_sha256"] != benchmark.get("content_hash"):
        failures.append("the benchmark content hash does not match the dataset file")
    if window["observed_candle_count"] != MIN_CANDLES:
        failures.append(f"the benchmark dataset does not hold exactly {MIN_CANDLES} candles")
    for key in ("first_candle_timestamp", "last_candle_timestamp", "observed_candle_count"):
        if benchmark.get(key) != window[key]:
            failures.append(f"the recorded benchmark {key} differs from the dataset file")
        if entry.get(key) != window[key]:
            failures.append(f"the published benchmark entry {key} differs from the dataset file")
    if entry.get("content_hash") != benchmark.get("content_hash"):
        failures.append("the published benchmark entry and the benchmark block disagree")

    # 4. the retrieval evidence is the evidence of the recorded retrieval
    retrieval = amendment.get("retrieval_evidence") or {}
    if retrieval.get("evidence_sha256") != sha256_file(root / EVIDENCE_RELATIVE):
        failures.append("the recorded sha256 of the retrieval evidence does not match the file")
    if retrieval.get("raw_response_sha256") != sha256_file(root / RAW_RESPONSE_RELATIVE):
        failures.append("the recorded sha256 of the raw response does not match the file")
    if retrieval.get("retrieval_timestamp_utc") != evidence.get("retrieval_timestamp_utc"):
        failures.append("the recorded retrieval timestamp differs from the evidence")
    statuses = dict(evidence.get("http_status_of_each_probed_host") or {})
    if not statuses:
        failures.append("the retrieval evidence records no probed host status")
    if dict(retrieval.get("http_status_of_each_probed_host") or {}) != statuses:
        failures.append("the recorded host statuses differ from the evidence")
    if int(retrieval.get("raw_response_row_count") or 0) != MIN_CANDLES:
        failures.append("the raw response does not hold exactly 26,280 rows")

    # 5. the effective data-manifest identity recomputes from the base plus the entry
    effective = amendment.get("effective_data_manifest") or {}
    recomputed_effective = effective_data_manifest_hash(base, entry, AMENDMENT_RELATIVE)
    if effective.get("effective_data_manifest_hash") != recomputed_effective:
        failures.append(
            "the effective data-manifest identity does not recompute: recorded "
            f"{effective.get('effective_data_manifest_hash')}, recomputed {recomputed_effective}"
        )
    if effective.get("base_manifest_hash") != base.get("manifest_hash"):
        failures.append("the effective identity is not bound to the base manifest")

    # 6. the alignment is recomputed from the dataset files
    assets = base.get("assets") or {}
    evaluated = sorted(
        symbol for symbol in assets if (base.get("content_hashes") or {}).get(symbol)
    )
    alignment = (amendment.get("alignment_rule") or {}).get("index_alignment") or {}
    if sorted(alignment.get("evaluated_assets") or []) != evaluated:
        failures.append("the recorded evaluated assets differ from the base data manifest")
    for symbol in evaluated:
        asset_window = dataset_window(root, str((assets[symbol] or {}).get("dataset_path") or ""))
        if asset_window is None:
            failures.append(f"{symbol}: the dataset does not exist")
            continue
        if (asset_window["first_candle_timestamp"] != window["first_candle_timestamp"]
                or asset_window["last_candle_timestamp"] != window["last_candle_timestamp"]
                or asset_window["observed_candle_count"] != window["observed_candle_count"]):
            failures.append(f"{symbol}: the dataset is not index-aligned with the benchmark")
    if alignment.get("index_aligned") is not True:
        failures.append("the amendment does not record an index-aligned benchmark")
    if list(alignment.get("misaligned_assets") or []):
        failures.append("the amendment records misaligned assets")

    # 7. the universe declares the same benchmark
    declared_benchmark = (universe.get("benchmark_asset") or {}).get("symbol")
    if declared_benchmark != BENCHMARK_SYMBOL:
        failures.append("the v3 universe does not declare BTCUSDT as its benchmark")
    if benchmark.get("is_candidate") is not False:
        failures.append("the benchmark is not recorded as a non-candidate")

    # 8. the deviation counts recompute from the completed v2 run
    configurations = config_manifest.get("configurations") or []
    btc_configurations = [
        configuration for configuration in configurations
        if str(configuration.get("trend_filter")) == "btc_ema_168"
    ]
    scope = (ledger.get("scope") or {}).get("binance_pairs") or []
    expected_affected = (
        len(scope) * len(btc_configurations)
        * len(spec_v1["folds"]["window_fractions"]) * len(spec_v1["costs"]["scenarios"])
    )
    total_records = int((ledger.get("counts") or {}).get("execution_units") or 0)
    disclosure = amendment.get("deviation_disclosure") or {}
    if int(disclosure.get("records_with_btc_filter") or -1) != expected_affected:
        failures.append(
            "the disclosed number of BTC-filter records does not recompute from the ledger, "
            f"the configuration manifest and the frozen fold rule: {expected_affected}"
        )
    if int(disclosure.get("total_v2_records") or -1) != total_records:
        failures.append("the disclosed total of v2 records differs from the ledger")
    if (deviation.get("counts") or {}).get("records_with_btc_filter") != expected_affected:
        failures.append("the deviation evidence does not record the recomputed count")
    if disclosure.get("evidence_sha256") != sha256_file(root / DEVIATION_RELATIVE):
        failures.append("the recorded sha256 of the deviation evidence does not match the file")
    if sorted(disclosure.get("misaligned_validation_folds") or []) != [0, 1, 2, 3]:
        failures.append("the disclosure does not record that every validation fold was misaligned")

    # 9. the v1 evidence is byte-identical
    anchors = (amendment.get("related_artifacts") or {}).get("v1_anchors") or {}
    for relative in V1_ANCHORS:
        if anchors.get(relative) != sha256_file(root / relative):
            failures.append(f"the v1 anchor for {relative} does not match the file")

    # 10. the amendment authorizes nothing
    authorization = amendment.get("execution_authorization") or {}
    if authorization.get("execution_authorized") is not False:
        failures.append("execution_authorization.execution_authorized is not false")
    if authorization.get("grid_run_authorized") is not False:
        failures.append("execution_authorization.grid_run_authorized is not false")
    failures.extend(selection_authorization_failures(root))

    # 11. nothing has run under v3
    for relative in V3_EXECUTION_PATHS:
        if (root / relative).exists():
            failures.append(f"a v3 execution artifact exists: {relative}")
    window_block = base.get("confirmatory_window") or {}
    if window_block.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v3 confirmatory window is not NOT_STARTED")
    if int(window_block.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v3 confirmatory window records a non-zero holdout exposure")

    return {
        "ok": not failures,
        "failures": failures,
        "manifest_hash": declared,
        "effective_data_manifest_hash": effective.get("effective_data_manifest_hash"),
        "benchmark_content_hash": benchmark.get("content_hash"),
        "index_aligned_assets": evaluated,
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

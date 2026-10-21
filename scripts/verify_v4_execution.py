#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v4 execution protocol.

``configs/research_v4_execution.json`` records the v4 execution protocol -- the
benchmark rule of BRAIN-013, the code-hash constraint, the evaluation scope
bound to the frozen v4 candidate set, and the execution authorization (which
authorizes nothing). The verifier never writes to the repository, never contacts
a provider, never reads a candle and never runs a grid. It checks:

1. the manifest hash recomputes from the canonical content of the document with
   the hash key removed;
2. the evaluation scope is exactly the frozen candidate set, and the frozen set
   is the set of validated constituents of the v4 universe manifest;
3. the data-manifest identity matches the identity the freeze binds;
4. the code-hash constraint places the v4 execution path outside the hashed set
   and records the authorized v1 code hash as the value of record;
5. the benchmark rule is bound: the dataset, its recomputed content hash, the
   alignment rule, the fail-closed list and the "no configuration is dropped"
   rule;
6. the execution authorization authorizes nothing (execution_authorized is
   false, selection_authorization_present is false);
7. the deviation disclosure records that v4 has no prior deviation to disclose;

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

PROTOCOL_RELATIVE = "configs/research_v4_execution.json"
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_RELATIVE = "research/universe_manifest_v4.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

#: The alignment rule the execution path requires.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called, so that the engine's index pairing equals "
    "the UTC-candle-close alignment of docs/research_protocol.md:101"
)

#: Benchmark dataset referenced from v3 data (immutable, outside the v4 manifest).
BENCHMARK_DATASET_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"
BENCHMARK_CONTENT_HASH = "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"


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


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(root: Path) -> str:
    """The portable identity of the ``*.py`` tree under ``root``.

    This is the ``canonical_source_digest_v1`` rule of BRAIN-009: a sha256
    over the POSIX relative path and the content digest of every ``*.py`` file
    under the root, in ascending path order.
    """
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    repo_root = Path(repo_root)

    required = [
        repo_root / PROTOCOL_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / UNIVERSE_RELATIVE,
        repo_root / DATA_MANIFEST_RELATIVE,
        repo_root / SPEC_V4_RELATIVE,
    ]
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    protocol = _load(repo_root / PROTOCOL_RELATIVE)
    freeze = _load(repo_root / FREEZE_RELATIVE)
    universe = _load(repo_root / UNIVERSE_RELATIVE)
    data_manifest = _load(repo_root / DATA_MANIFEST_RELATIVE)
    spec_v4 = _load(repo_root / SPEC_V4_RELATIVE)

    # 1. The protocol is self-hashing.
    excluded = tuple(protocol.get("hashing", {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    declared_hash = protocol.get("manifest_hash")
    recomputed_hash = compute_manifest_hash(protocol, excluded)
    if declared_hash != recomputed_hash:
        failures.append(
            f"manifest_hash mismatch: declared {declared_hash}, recomputed {recomputed_hash}"
        )

    # 2. The evaluation scope is the frozen candidate set.
    members = freeze.get("candidates") or []
    binance_pairs = sorted(
        str(m.get("binance_pair"))
        for m in members
        if m.get("validated") is True
    )
    if not binance_pairs:
        failures.append("the frozen v4 candidate set is empty")
    evaluation = protocol.get("evaluation_scope") or {}
    if list(evaluation.get("constituents") or []) != binance_pairs:
        failures.append("the evaluated scope is not the frozen candidate set")
    if evaluation.get("count") != len(binance_pairs):
        failures.append("the evaluated scope count differs from the frozen count")
    if evaluation.get("data_manifest_hash") != freeze.get("data_manifest_hash"):
        failures.append("the evaluation scope is not bound to the freeze data-manifest hash")
    if evaluation.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("the evaluation scope is not bound to the freeze manifest hash")
    if evaluation.get("universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("the evaluation scope is not bound to the v4 universe manifest")
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(binance_pairs) != validated:
        failures.append("the frozen candidate set is not the validated v4 universe")
    if evaluation.get("widening_by_reranking_forbidden") is not True:
        failures.append("the protocol does not forbid widening the candidate set")
    if evaluation.get("excluded_assets_stay_excluded") is not True:
        failures.append("the protocol does not keep excluded assets excluded")

    # 3. The data-manifest identity matches.
    data_excluded = tuple((data_manifest.get("hashing") or {}).get(
        "manifest_hash_excluded_keys") or ("manifest_hash",))
    data_manifest_hash = compute_manifest_hash(data_manifest, data_excluded)
    if data_manifest_hash != data_manifest.get("manifest_hash"):
        failures.append("the v4 data manifest does not recompute its manifest_hash")
    if evaluation.get("data_manifest_hash") != data_manifest_hash:
        failures.append(
            "the evaluation scope data-manifest hash does not match the v4 data manifest"
        )

    # 4. The code-hash constraint.
    constraint = protocol.get("code_hash_constraint") or {}
    if constraint.get("authorized_code_hash") != (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    ):
        failures.append("the code-hash constraint does not record the authorized v1 code hash")
    if constraint.get("v4_execution_must_live_outside_hashed_set") is not True:
        failures.append("the code-hash constraint does not require v4 outside the hashed set")
    if constraint.get("v4_execution_root") != EXECUTION_PATH_ROOT:
        failures.append("the code-hash constraint does not name the v4 execution root")
    if constraint.get("edit_under_src_breakout_research_forbidden_without_reauthorization") is not True:
        failures.append("the code-hash constraint does not forbid edits under src/breakout_research")

    execution_path_digest = canonical_source_digest(repo_root / EXECUTION_PATH_ROOT)
    hashed_set_digest = canonical_source_digest(repo_root / HASHED_SET_ROOT)
    environment_facts = [
        f"v4 execution path canonical digest: {execution_path_digest}",
        f"hashed source set canonical digest: {hashed_set_digest}",
        "the checkout-dependent ordered digest compute_code_hash() is never used as an identity",
    ]

    # 5. The benchmark rule is bound.
    benchmark = protocol.get("benchmark_rule") or {}
    dataset_path = str(benchmark.get("dataset_path") or "")
    if not dataset_path:
        failures.append("the protocol names no benchmark dataset")
    else:
        dataset = repo_root / dataset_path
        if not dataset.exists():
            failures.append(f"the benchmark dataset {dataset_path} does not exist")
        else:
            live_hash = sha256_file(dataset)
            if benchmark.get("content_hash") != live_hash:
                failures.append(
                    "the benchmark content hash does not match the dataset: "
                    f"{benchmark.get('content_hash')} != {live_hash}"
                )
    if benchmark.get("content_hash") != BENCHMARK_CONTENT_HASH:
        failures.append("the benchmark content hash does not match the recorded hash")
    if benchmark.get("alignment") != ALIGNMENT_RULE:
        failures.append("the protocol does not bind the benchmark alignment rule")
    if benchmark.get("no_forward_fill") is not True:
        failures.append("the protocol does not forbid forward-filling the benchmark")
    if not benchmark.get("fail_closed"):
        failures.append("the protocol records no fail-closed condition")
    if "576" not in str(benchmark.get("grid_rule") or ""):
        failures.append("the protocol does not record the unchanged grid rule")
    if benchmark.get("symbol") != "BTCUSDT":
        failures.append("the benchmark symbol is not BTCUSDT")

    # 6. The execution authorization authorizes nothing.
    auth = protocol.get("execution_authorization") or {}
    if auth.get("execution_authorized") is not False:
        failures.append("the protocol claims an execution authorization; it authorizes none")
    if auth.get("selection_authorization_present") is not False:
        failures.append("the protocol claims a selection authorization; none exists")

    # 7. The deviation disclosure records that v4 has no prior deviation.
    disclosure = protocol.get("deviation_disclosure") or {}
    if disclosure.get("not_applicable") is not True:
        failures.append("the deviation disclosure does not record v4 as not applicable")
    if disclosure.get("records_with_btc_filter") != 0:
        failures.append("the deviation disclosure records a non-zero affected-record count")

    return {
        "ok": not failures,
        "protocol_path": PROTOCOL_RELATIVE,
        "manifest_hash": declared_hash,
        "recomputed_manifest_hash": recomputed_hash,
        "authorized_candidates": len(binance_pairs),
        "data_manifest_hash": data_manifest_hash,
        "hashed_set_digest": hashed_set_digest,
        "execution_path_digest": execution_path_digest,
        "environment_facts": environment_facts,
        "failures": failures,
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

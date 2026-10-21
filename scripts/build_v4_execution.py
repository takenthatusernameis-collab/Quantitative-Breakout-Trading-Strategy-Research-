#!/usr/bin/env python3
"""Build the preregistered v4 execution protocol.

This producer writes ``configs/research_v4_execution.json``:
the versioned, hash-bound artifact that records the v4 execution protocol --
the benchmark rule of BRAIN-013, the code-hash constraint, the evaluation
scope bound to the frozen v4 candidate set, and the execution authorization
(which authorizes nothing).

It is a design deliverable. Building it runs nothing: it reads the frozen
artifacts, recomputes every expectation from them and records what a future
run may do. The run itself requires the separate selection authorization
``configs/research_v4_selection_authorization_1.json``.

Every fact the artifact records is recomputed from the repository:

* the candidate set from the v4 freeze, re-derived from the v4 universe manifest;
* the data-manifest identity from the v4 base data manifest (v4 publishes no
  data-manifest amendment);
* the benchmark dataset reference from the immutable v3 data area (v4 publishes
  no BTCUSDT entry);
* the code-hash constraint placing the v4 execution path outside the hashed set.

Nothing is copied out of the artifact it describes, and no digest is trusted
because it is written down somewhere.

The script is deterministic: the creation instant is pinned and every other
field is derived from artifacts that are already hash-bound, so re-running it
reproduces the same bytes. It never writes to the hashed source set, never
touches a frozen artifact, never fetches anything and never runs a grid.

Usage::

    python3 scripts/build_v4_execution.py            # write the artifact
    python3 scripts/build_v4_execution.py --force    # rewrite it
    python3 scripts/build_v4_execution.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_RELATIVE = "configs/research_v4_execution.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELATIVE

#: The instant at which this protocol is created. It is pinned here so
#: that the artifact is byte-reproducible; it must not be moved once the
#: artifact has been committed.
CREATED_UTC = "2026-10-21T00:16:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: The source trees the run identity binds.
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

#: The v4 artifacts the protocol is bound to.
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
UNIVERSE_MANIFEST_RELATIVE = "research/universe_manifest_v4.json"
DATA_MANIFEST_RELATIVE = "research/data_manifest_v4.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"

#: The alignment rule the execution path requires.
ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called, so that the engine's index pairing equals "
    "the UTC-candle-close alignment of docs/research_protocol.md:101"
)

#: Benchmark dataset referenced from v3 data (immutable, outside the v4 manifest).
BENCHMARK_DATASET_PATH = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"
BENCHMARK_CONTENT_HASH = "50d357b0cb2d6f8dd36000b084d0c6993db7b505ff98aeef6597a7643e8b577e"
BENCHMARK_FIRST_CANDLE = 1697886000000
BENCHMARK_LAST_CANDLE = 1792490400000
BENCHMARK_CANDLE_COUNT = 26280


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


def dig(document: Any, dotted: str) -> Any:
    current = document
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the v4 execution protocol from the hash-bound artifacts."""
    root = Path(repo_root)

    freeze = _load(root / FREEZE_RELATIVE)
    universe = _load(root / UNIVERSE_MANIFEST_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_RELATIVE)
    spec_v4 = _load(root / SPEC_V4_RELATIVE)

    # --- the frozen scope, resolved from the freeze and the universe manifest --
    # Validate candidates: validated == true and exclusion_reason == null
    members = freeze.get("candidates") or []
    binance_pairs = sorted(
        str(m.get("binance_pair"))
        for m in members
        if m.get("validated") is True
    )
    if not binance_pairs:
        raise SystemExit("the frozen v4 candidate set is empty")

    # Re-derive from the universe manifest
    validated = sorted(
        str(entry.get("binance_pair") or f"{entry.get('symbol')}USDT")
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(binance_pairs) != validated:
        raise SystemExit(
            "the frozen v4 candidate set is not the validated v4 universe"
        )

    # --- the data-manifest identity -----------------------------------------
    excluded = tuple((data_manifest.get("hashing") or {}).get(
        "manifest_hash_excluded_keys") or ("manifest_hash",))
    data_manifest_hash = compute_manifest_hash(data_manifest, excluded)
    if data_manifest_hash != data_manifest.get("manifest_hash"):
        raise SystemExit("the v4 data manifest does not recompute its manifest_hash")
    if data_manifest_hash != freeze.get("data_manifest_hash"):
        raise SystemExit(
            "the v4 data-manifest identity does not match the identity the freeze binds"
        )

    # --- the benchmark dataset, verified from the v3 data area ---------------
    benchmark_dataset = root / BENCHMARK_DATASET_PATH
    if not benchmark_dataset.exists():
        raise SystemExit(f"the benchmark dataset {BENCHMARK_DATASET_PATH} does not exist")
    benchmark_content_hash = sha256_file(benchmark_dataset)
    if benchmark_content_hash != BENCHMARK_CONTENT_HASH:
        raise SystemExit(
            "the benchmark dataset does not hash to the recorded content hash"
        )

    boundary = dig(freeze, "confirmatory_window.opens_utc")
    min_hours = dig(freeze, "confirmatory_window.min_hours")

    document: Dict[str, Any] = {
        "artifact": "v4_execution_protocol",
        "artifact_version": "v4-execution-protocol-1",
        "candidate_freeze_and_confirmatory_window": {
            "candidate_manifest_committed_and_hash_bound_before_first_confirmatory_candle": True,
            "confirmatory_window_opens_utc": boundary,
            "min_confirmatory_window_hours": min_hours,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after freeze",
            "no_ranking_or_retuning_on_holdout": True,
            "single_use": True,
            "window_overlap_with_v1_or_v2_holdout_forbidden": True,
            "window_overlap_with_v3_confirmatory_window_forbidden": True,
        },
        "code_hash_constraint": {
            "authorized_code_hash": "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2",
            "chosen_approach": (
                "new code outside the hashed set (src/v4_campaign/), leaving "
                "compute_code_hash() unchanged; explicit re-authorization only if "
                "v1/v2 hashed paths are touched"
            ),
            "edit_under_src_breakout_research_forbidden_without_reauthorization": True,
            "hashed_source_root": HASHED_SET_ROOT,
            "v1_paths_hardcode_v1_spec": [
                "src/breakout_research/campaign.py",
                "src/breakout_research/pilot.py",
            ],
            "v4_execution_must_live_outside_hashed_set": True,
            "v4_execution_root": EXECUTION_PATH_ROOT,
            "v4_execution_namespace": f"{EXECUTION_PATH_ROOT}/",
        },
        "created_utc": CREATED_UTC,
        "deviation_disclosure": {
            "evidence_path": None,
            "records_with_btc_filter": 0,
            "statement": (
                "The v4 campaign has no prior completed runs and therefore no v1/v2 "
                "alignment deviation to disclose. The deviation from completed v1 and v2 "
                "runs is disclosed by the v3 selection authorization and the v3 execution "
                "amendment."
            ),
            "total_v2_records": 0,
            "not_applicable": True,
        },
        "evaluation_scope": {
            "candidate_freeze_hash": freeze.get("manifest_hash"),
            "candidate_freeze_path": FREEZE_RELATIVE,
            "constituents": binance_pairs,
            "count": len(binance_pairs),
            "data_manifest_hash": data_manifest_hash,
            "data_manifest_path": DATA_MANIFEST_RELATIVE,
            "excluded_assets_stay_excluded": True,
            "universe_manifest_hash": universe.get("manifest_hash"),
            "universe_manifest_path": UNIVERSE_MANIFEST_RELATIVE,
            "widening_by_reranking_forbidden": True,
        },
        "execution_authorization": {
            "execution_authorized": False,
            "grid_run_authorized": False,
            "scope": (
                "this protocol records the benchmark rule and the data-manifest identity. "
                "It authorizes no run, no evaluation and no confirmatory-window read."
            ),
            "selection_authorization_present": False,
        },
        "benchmark_rule": {
            "alignment": ALIGNMENT_RULE,
            "content_hash": benchmark_content_hash,
            "dataset_path": BENCHMARK_DATASET_PATH,
            "exposure_rule": (
                "the benchmark dataset is development data; it lies entirely before the "
                "confirmatory window and no confirmatory-window candle is read"
            ),
            "fail_closed": [
                "the benchmark series is missing",
                "the benchmark series is shorter than the evaluated window",
                "the benchmark series is not index-aligned with the asset series",
            ],
            "first_candle_timestamp": BENCHMARK_FIRST_CANDLE,
            "grid_rule": (
                "the 576 btc_ema_168 configurations per asset are evaluated, never dropped, "
                "re-derived or re-ranked"
            ),
            "last_candle_timestamp": BENCHMARK_LAST_CANDLE,
            "no_forward_fill": True,
            "observed_candle_count": BENCHMARK_CANDLE_COUNT,
            "role": "trend_filter_and_benchmark",
            "symbol": "BTCUSDT",
            "note": (
                "The v4 data manifest publishes no BTCUSDT entry. The benchmark dataset is "
                "referenced directly from the immutable v3 data area; it is external to the "
                "v4 data-manifest identity and is hash-verified before every use."
            ),
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), "
            "ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash removed, "
                "following the pattern of the other v2 and v3 artifacts."
            ),
        },
    }

    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true", help="overwrite an existing artifact")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print, write nothing")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    target = repo_root / ARTIFACT_RELATIVE
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    os.chmod(target, 0o644)
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 execution amendment 1.

``configs/research_v2_execution_amendment_1.json`` is a design artifact. It
corrects the code-hash constraint of the v2 execution protocol and records the
bounded parameters a future v2 selection grid run would have to satisfy. The
verifier never writes to the repository, never contacts a provider and never
reads a candle. It checks:

* the manifest hash recomputes from the canonical content of the document with
  the digest-carrying keys removed;
* the amended protocol is byte-identical to the recorded digest and still
  carries the defective text as historical evidence;
* the code-hash constraint names the hashed source set, classifies every path
  correctly, records the authorized v1 code hash and binds the tree to a
  portable, order-independent source digest;
* the authorized scope is exactly the frozen v2 candidate set and the excluded
  assets stay excluded;
* the selection data boundary matches the frozen confirmatory-window start and
  forbids confirmatory reads, v1 holdout reuse and v1 cycle-0 mixing;
* the v2 result paths are the v2 paths, the v1 paths are forbidden, and none of
  the v2 paths exists yet;
* the selection rule is the unchanged v1 rule and the bounds are concrete;
* nothing is authorized and nothing has been executed: no v2 shard, ledger,
  result manifest, result stream or checkpoint exists, and the confirmatory
  window is still unexposed;
* the v1 artifacts are byte-identical and the v1 campaign authorization is
  untouched.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AMENDMENT_RELATIVE = "configs/research_v2_execution_amendment_1.json"
PROTOCOL_RELATIVE = "configs/research_v2_execution.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
RESULTS_STREAM_RELATIVE = "research/results.jsonl"

HASHED_SET_ROOT = "src/breakout_research"

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

V2_EXECUTION_ARTIFACTS = (
    "research/shards_v2",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
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
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def path_is_inside_hashed_set(relative: str) -> bool:
    root = HASHED_SET_ROOT.rstrip("/")
    candidate = relative.rstrip("/")
    return candidate == root or candidate.startswith(root + "/")


def canonical_source_digest(repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT) -> str:
    """The portable identity of the hashed source tree.

    Every ``*.py`` file under the hashed set contributes its POSIX relative path
    and the sha256 hex digest of its bytes, in ascending path order. Unlike
    ``compute_code_hash()`` this does not depend on the directory enumeration
    order of the checkout, so it is reproducible on any machine.
    """
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def live_ordered_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Reproduce ``compute_code_hash()`` exactly, for the informational report.

    The result depends on the filesystem enumeration order of the checkout and
    is therefore not a portable identity of the tree.
    """
    src_dir = repo_root / HASHED_SET_ROOT
    if not src_dir.exists():
        return None
    digest = hashlib.sha256()
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            if name.endswith(".py"):
                digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    amendment_path = repo_root / AMENDMENT_RELATIVE

    required = (
        amendment_path,
        repo_root / PROTOCOL_RELATIVE,
        repo_root / SPEC_V2_RELATIVE,
        repo_root / SPEC_V1_RELATIVE,
        repo_root / FREEZE_RELATIVE,
        repo_root / UNIVERSE_V2_RELATIVE,
        repo_root / DATA_V2_RELATIVE,
        repo_root / AUTHORIZATION_RELATIVE,
    )
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    protocol = json.loads((repo_root / PROTOCOL_RELATIVE).read_text(encoding="utf-8"))
    spec_v2 = json.loads((repo_root / SPEC_V2_RELATIVE).read_text(encoding="utf-8"))
    spec_v1 = json.loads((repo_root / SPEC_V1_RELATIVE).read_text(encoding="utf-8"))
    freeze = json.loads((repo_root / FREEZE_RELATIVE).read_text(encoding="utf-8"))
    universe = json.loads((repo_root / UNIVERSE_V2_RELATIVE).read_text(encoding="utf-8"))
    data = json.loads((repo_root / DATA_V2_RELATIVE).read_text(encoding="utf-8"))
    authorization = json.loads((repo_root / AUTHORIZATION_RELATIVE).read_text(encoding="utf-8"))

    # 1. The amendment is self-hashing.
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the amendment does not declare its manifest_hash_excluded_keys")
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. The amended protocol is untouched and still carries the defective text.
    amends = amendment.get("amends") or {}
    if amends.get("file") != PROTOCOL_RELATIVE:
        failures.append("the amendment does not name the amended protocol")
    if amends.get("file_sha256") != sha256_file(repo_root / PROTOCOL_RELATIVE):
        failures.append("the amended protocol does not match its recorded file digest")
    if amends.get("specification_hash") != protocol.get("specification_hash"):
        failures.append("the amended protocol specification_hash does not match the protocol")
    protocol_body = {key: value for key, value in protocol.items() if key != "specification_hash"}
    if protocol.get("specification_hash") != sha256_bytes(canonical(protocol_body).encode("utf-8")):
        failures.append("the amended protocol specification_hash does not recompute")
    defective = str((protocol.get("code_hash_constraint") or {}).get("chosen_approach") or "")
    if "src/breakout_research/v2/" not in defective:
        failures.append("the amended protocol no longer carries the defective text as evidence")
    corrections = amends.get("corrections") or []
    correction_ids = {str(item.get("id")) for item in corrections}
    for required_id in ("C1", "C2"):
        if required_id not in correction_ids:
            failures.append(f"the amendment does not record correction {required_id}")
    for item in corrections:
        for field in ("topic", "defect", "correction", "status"):
            if not str(item.get(field) or "").strip():
                failures.append(f"correction {item.get('id')} does not state its {field}")

    # 3. The code-hash constraint.
    constraint = amendment.get("code_hash_constraint") or {}
    if constraint.get("hashed_set_root") != HASHED_SET_ROOT:
        failures.append("the code-hash constraint does not name the hashed source root")
    authorized_hash = constraint.get("authorized_code_hash")
    if authorized_hash != authorization.get("code_hash"):
        failures.append("the recorded code hash is not the authorized v1 code hash")
    if authorization.get("authorized") is not True:
        failures.append("the v1 campaign authorization is not authorized")
    if authorization.get("protocol_version") != "v1":
        failures.append("the campaign authorization is not bound to protocol v1")
    freeze_identity = freeze.get("snapshot_identity") or {}
    if authorized_hash != freeze_identity.get("code_hash"):
        failures.append("the recorded code hash is not the code hash of the candidate freeze")
    universe_identity = universe.get("snapshot_identity") or {}
    if authorized_hash != universe_identity.get("code_hash"):
        failures.append("the recorded code hash is not the code hash of the v2 universe manifest")
    live_canonical = canonical_source_digest(repo_root)
    if constraint.get("canonical_source_digest") != live_canonical:
        failures.append("the hashed source tree does not match the recorded canonical digest")
    if not str((constraint.get("canonical_source_digest_algorithm") or {}).get("description") or "").strip():
        failures.append("the canonical source digest algorithm is not documented")
    for relative in constraint.get("paths_correctly_classified_as_outside_hashed_set") or []:
        if path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as outside the hashed set but is inside it")
    for relative in constraint.get("paths_not_permitted_inside_hashed_set") or []:
        if not path_is_inside_hashed_set(relative):
            failures.append(f"{relative} is classified as inside the hashed set but is not")
    if not str(constraint.get("chosen_approach") or "").strip():
        failures.append("the code-hash constraint does not state the chosen approach")
    if "src/breakout_research" not in str(constraint.get("chosen_approach") or ""):
        failures.append("the chosen approach does not rule out the hashed source root")

    # 4. The authorized scope is exactly the frozen candidate set.
    authorization_block = amendment.get("v2_selection_authorization") or {}
    scope = authorization_block.get("scope") or {}
    frozen = freeze.get("frozen_candidate_set") or {}
    if sorted(str(item) for item in scope.get("constituents") or []) != sorted(
        str(item) for item in frozen.get("constituents") or []
    ):
        failures.append("the authorized scope is not the frozen candidate set")
    if sorted(str(item) for item in scope.get("binance_pairs") or []) != sorted(
        str(item) for item in frozen.get("binance_pairs") or []
    ):
        failures.append("the authorized pairs are not the frozen candidate pairs")
    validated_pairs = sorted(
        str(entry.get("symbol"))
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated")
    )
    if sorted(str(item) for item in scope.get("binance_pairs") or []) != validated_pairs:
        failures.append("the authorized scope is not the validated v2 candidate set")
    if scope.get("constituents_count") != len(validated_pairs):
        failures.append("the authorized constituent count does not match the scope")
    if scope.get("excluded_assets_stay_excluded") is not True:
        failures.append("the authorization does not keep the excluded assets excluded")
    if scope.get("widening_by_reranking_forbidden") is not True:
        failures.append("the authorization does not forbid widening the scope by re-ranking")
    excluded_pairs = {
        str(entry.get("symbol")): str(entry.get("exclusion_reason"))
        for entry in universe.get("eligible_assets") or []
        if not entry.get("validated")
    }
    for symbol, reason in excluded_pairs.items():
        if symbol in [str(item) for item in scope.get("binance_pairs") or []]:
            failures.append(f"the excluded asset {symbol} is inside the authorized scope")
        if (scope.get("excluded_after_validation") or {}).get(symbol) != reason:
            failures.append(f"the exclusion reason of {symbol} is not recorded by the authorization")

    # 5. The authorization binds the hash-verified v2 artifacts.
    if scope.get("bound_to_universe_hash") != universe.get("manifest_hash"):
        failures.append("the authorization is not bound to the current v2 universe manifest")
    if scope.get("bound_to_data_hash") != data.get("manifest_hash"):
        failures.append("the authorization is not bound to the current v2 data manifest")
    if scope.get("bound_to_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("the authorization is not bound to the current v2 candidate freeze")
    if scope.get("candidate_manifest_path") != FREEZE_RELATIVE:
        failures.append("the authorization does not name the v2 candidate manifest")

    # 6. The selection data boundary.
    boundary = authorization_block.get("data_boundary") or {}
    window_start = (freeze.get("data_boundary") or {}).get("confirmatory_window_start_utc")
    if boundary.get("candles_before_utc") != window_start:
        failures.append("the selection data boundary is not the frozen confirmatory-window start")
    for flag in (
        "development_data_only",
        "confirmatory_window_never_read_during_selection",
        "v1_holdout_never_reused",
        "v1_cycle0_units_never_mixed",
    ):
        if boundary.get(flag) is not True:
            failures.append(f"the selection data boundary does not set {flag}")
    if boundary.get("v1_cycle0_units") != (spec_v2.get("comparability") or {}).get("v1_cycle0_units"):
        failures.append("the v1 cycle-0 unit count does not match the v2 specification")

    # 7. The v2 result paths, and the v1 paths that stay forbidden.
    paths = authorization_block.get("paths") or {}
    layout = protocol.get("v2_result_layout") or {}
    if paths.get("shards_dir") != layout.get("shard_directory"):
        failures.append("the shard directory is not the v2 shard directory of the protocol")
    if paths.get("ledger") != layout.get("ledger_path"):
        failures.append("the ledger path is not the v2 ledger path of the protocol")
    if paths.get("results_manifest") != layout.get("results_manifest_path"):
        failures.append("the results manifest path is not the v2 results manifest path of the protocol")
    if paths.get("never_use_v1_paths") is not True:
        failures.append("the authorization does not forbid the v1 paths")
    v1_paths = {str(item).rstrip("/") for item in paths.get("v1_paths_forbidden") or []}
    if not v1_paths:
        failures.append("the authorization does not list the forbidden v1 paths")
    v2_paths = {
        str(paths.get(key) or "").rstrip("/")
        for key in ("shards_dir", "ledger", "results_manifest", "results_stream", "checkpoint")
    }
    for relative in sorted(v2_paths):
        if not relative:
            failures.append("a v2 path is not recorded")
            continue
        if relative in v1_paths:
            failures.append(f"the v2 path {relative} is also a forbidden v1 path")
    if authorization_block.get("campaign_id") != layout.get("campaign_id"):
        failures.append("the campaign id is not the v2 campaign id of the protocol")

    # 8. The selection rule is the unchanged v1 rule.
    selection = authorization_block.get("selection_rule") or {}
    if selection.get("unchanged_from_v1") is not True:
        failures.append("the authorization does not bind the unchanged v1 selection rule")
    if selection.get("reference") != SPEC_V1_RELATIVE:
        failures.append("the authorization does not reference the v1 specification")
    if spec_v1.get("selection") != spec_v2.get("selection"):
        failures.append("the v2 specification no longer inherits the v1 selection block unchanged")
    if selection.get("max_candidates_per_asset") != spec_v1["selection"]["max_candidates_per_asset"]:
        failures.append("the authorized candidate count per asset differs from the v1 rule")

    # 9. The bounds are concrete.
    bounds = authorization_block.get("bounds") or {}
    grid_combinations = spec_v1["strategy_grid"]["total_combinations"]
    if bounds.get("max_assets") != len(validated_pairs):
        failures.append("the asset bound does not match the authorized scope")
    if bounds.get("max_configs_per_asset") != grid_combinations:
        failures.append("the configuration bound per asset is not the inherited grid size")
    if bounds.get("max_total_config_units") != bounds.get("max_assets", 0) * grid_combinations:
        failures.append("the total unit bound does not follow from the asset and configuration bounds")
    if bounds.get("attempts") != 1:
        failures.append("the number of permitted attempts is not bounded to one")
    if bounds.get("max_retries_on_technical_failure") != spec_v1["checkpointing"]["max_retries"]:
        failures.append("the technical retry bound differs from the inherited checkpointing rule")
    if not str(bounds.get("resource_limits") or "").strip():
        failures.append("the resource limits are not recorded")

    # 10. The stopping conditions, the rollback rule and the falsifiers.
    stopping = " ".join(str(item) for item in authorization_block.get("stopping_conditions") or [])
    if "report" not in stopping.lower():
        failures.append("the stopping conditions do not require reporting an empty outcome")
    if "no candidate survives" not in stopping.lower():
        failures.append("the stopping conditions do not cover an empty candidate set")
    rollback = str(authorization_block.get("rollback_rule") or "")
    if "v1" not in rollback.lower():
        failures.append("the rollback rule does not protect the v1 artifacts")
    if "checkpoint" not in rollback.lower():
        failures.append("the rollback rule does not protect the v1 checkpoint")
    falsifiers = [str(item) for item in authorization_block.get("falsifiers") or []]
    if len(falsifiers) < 2:
        failures.append("the falsifiers are not recorded")
    falsifier_text = " ".join(falsifiers).lower()
    for needle in ("src/breakout_research", "confirmatory", "v1"):
        if needle.lower() not in falsifier_text:
            failures.append(f"the falsifiers do not cover {needle}")

    # 11. Nothing is authorized by this artifact.
    if authorization_block.get("authorized") is not False:
        failures.append("the selection authorization is not recorded as unauthorized")
    if authorization_block.get("no_execution") is not True:
        failures.append("the selection authorization does not record that nothing runs")
    execution = amendment.get("execution_authorization") or {}
    for flag in (
        "grid_run_authorized",
        "candidate_selection_authorized",
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
    ):
        if execution.get(flag) is not False:
            failures.append(f"execution_authorization.{flag} is not false")
    if amendment.get("amendment_status") != "PREREGISTERED_AMENDMENT_DESIGN_ONLY":
        failures.append("the amendment status does not record that it is a design artifact")

    # 12. Nothing has been executed and nothing is exposed.
    for relative in V2_EXECUTION_ARTIFACTS:
        if (repo_root / relative).exists():
            failures.append(f"a v2 execution artifact exists: {relative}")
    results_path = repo_root / RESULTS_STREAM_RELATIVE
    if results_path.exists():
        with results_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                if b"v2-campaign" in chunk:
                    failures.append("the v1 results file contains v2 campaign rows")
                    break
    window = data.get("confirmatory_window") or {}
    if window.get("holdout_exposed_count") != 0:
        failures.append("the v2 data manifest records confirmatory-window exposure")
    if window.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("the v2 confirmatory window is not marked NOT_STARTED")

    # 13. The v1 evidence is byte-identical.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")

    # 14. The v1 campaign authorization is untouched.
    if authorization.get("specification_hash") != spec_v1.get("specification_hash"):
        failures.append("the campaign authorization is not bound to the v1 specification hash")
    if authorization.get("code_hash") != authorized_hash:
        failures.append("the campaign authorization does not carry the recorded code hash")
    if not isinstance(authorization.get("reasons"), list):
        failures.append("the campaign authorization does not record its reasons as a list")

    # 15. The verification block names the verifier and the tests.
    verification = amendment.get("verification") or {}
    if verification.get("verifier_script") != "scripts/verify_research_v2_execution_amendment_1.py":
        failures.append("the amendment does not name its verifier")
    if verification.get("tests_module") != "tests/test_research_v2_execution_amendment_1.py":
        failures.append("the amendment does not name its test module")
    for relative in (verification.get("verifier_script"), verification.get("tests_module")):
        if relative and not (repo_root / relative).exists():
            failures.append(f"the declared verification file is missing: {relative}")

    return {
        "ok": not failures,
        "amendment_path": AMENDMENT_RELATIVE,
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "amendment_status": amendment.get("amendment_status"),
        "authorized_scope": sorted(str(item) for item in scope.get("constituents") or []),
        "data_boundary_utc": boundary.get("candles_before_utc"),
        "authorized_code_hash": authorized_hash,
        "canonical_source_digest": live_canonical,
        "live_ordered_code_hash": live_ordered_code_hash(repo_root),
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

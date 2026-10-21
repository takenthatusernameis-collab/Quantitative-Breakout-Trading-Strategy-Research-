"""Tests for the preregistered v4 execution protocol.

``configs/research_v4_execution.json`` records the v4 execution protocol -- the
benchmark rule of BRAIN-013, the code-hash constraint, the evaluation scope
bound to the frozen v4 candidate set, and the execution authorization (which
authorizes nothing). The tests prove that

* the protocol is self-hashing and reproduced byte for byte by its producer;
* the evaluation scope is exactly the frozen candidate set, which is the set of
  validated constituents of the v4 universe manifest;
* the data-manifest identity matches the identity the freeze binds;
* the code-hash constraint places the v4 execution path outside the hashed set
  and records the authorized v1 code hash as the value of record;
* the benchmark rule is bound: the dataset, its recomputed content hash, the
  alignment rule, the fail-closed list and the "no configuration is dropped"
  rule;
* the execution authorization authorizes nothing;
* the deviation disclosure records that v4 has no prior deviation to disclose;
* **the verifier is not vacuous**: tampering with the protocol, with the scope,
  with the data-manifest identity, with the code-hash constraint, with the
  benchmark rule, with the execution authorization or with the deviation
  disclosure is detected.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v4_execution.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v4_candidate_freeze.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v4.json"
DATA_MANIFEST_PATH = REPO_ROOT / "research" / "data_manifest_v4.json"
SPEC_V4_PATH = REPO_ROOT / "configs" / "research_v4.json"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v4_campaign"

ALIGNMENT_RULE = (
    "the asset series and the benchmark series are sliced to the same fold window "
    "before the frozen engine is called, so that the engine's index pairing equals "
    "the UTC-candle-close alignment of docs/research_protocol.md:101"
)


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_v4_execution", "scripts/verify_v4_execution.py"
)
producer = _load_module(
    "build_v4_execution", "scripts/build_v4_execution.py"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads."""
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    copy_relative = {Path(HASHED_SET_ROOT), Path(EXECUTION_PATH_ROOT)}
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if relative in copy_relative or any(
                root_path in relative.parents for root_path in copy_relative
            ):
                shutil.copyfile(source, target)
            else:
                target.symlink_to(source)
    return root


def _replace(root: Path, relative: str, payload: Any) -> None:
    target = root / relative
    if target.is_symlink() or target.exists():
        target.unlink()
    if isinstance(payload, str):
        target.write_text(payload, encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tamper(
    root: Path,
    mutate: Callable[[Dict[str, Any]], None],
    rehash: bool = True,
) -> Path:
    protocol = _load(PROTOCOL_PATH)
    mutate(protocol)
    if rehash:
        protocol["manifest_hash"] = verifier.compute_manifest_hash(
            protocol, ("manifest_hash",)
        )
    _replace(root, "configs/research_v4_execution.json", protocol)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_the_protocol_is_self_hashing() -> None:
    protocol = _load(PROTOCOL_PATH)
    recomputed = verifier.compute_manifest_hash(protocol, ("manifest_hash",))
    assert recomputed == protocol["manifest_hash"]


def test_the_protocol_is_reproduced_byte_for_byte_by_its_producer() -> None:
    rebuilt = producer.build(REPO_ROOT)
    on_disk = _load(PROTOCOL_PATH)
    assert rebuilt == on_disk
    rendered = json.dumps(rebuilt, indent=2, ensure_ascii=False) + "\n"
    assert rendered == PROTOCOL_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / "configs" / "research_v4_execution.json"
    target.unlink()
    assert producer.main(["--repo-root", str(root)]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_evaluation_scope_is_the_frozen_candidate_set() -> None:
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    scope = protocol["evaluation_scope"]
    pairs = sorted(
        str(member["binance_pair"])
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    )
    assert sorted(scope["constituents"]) == pairs
    assert scope["count"] == len(pairs)
    assert len(pairs) > 0
    assert scope["candidate_freeze_hash"] == freeze["manifest_hash"]
    assert scope["data_manifest_hash"] == freeze["data_manifest_hash"]
    assert scope["universe_manifest_hash"] == _load(UNIVERSE_PATH)["manifest_hash"]
    assert scope["widening_by_reranking_forbidden"] is True


def test_the_frozen_candidate_set_is_the_validated_v4_universe() -> None:
    universe = _load(UNIVERSE_PATH)
    validated = sorted(
        str(entry["binance_pair"])
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    protocol = _load(PROTOCOL_PATH)
    assert sorted(protocol["evaluation_scope"]["constituents"]) == validated
    assert len(validated) > 0
    assert "BTCUSDT" not in validated


def test_the_data_manifest_identity_matches_the_freeze() -> None:
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    data_manifest = _load(DATA_MANIFEST_PATH)
    scope = protocol["evaluation_scope"]
    assert scope["data_manifest_hash"] == freeze["data_manifest_hash"]
    assert scope["data_manifest_hash"] == data_manifest["manifest_hash"]


def test_the_code_hash_constraint_places_v4_outside_the_hashed_set() -> None:
    protocol = _load(PROTOCOL_PATH)
    constraint = protocol["code_hash_constraint"]
    assert constraint["authorized_code_hash"] == (
        "2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2"
    )
    assert constraint["v4_execution_must_live_outside_hashed_set"] is True
    assert constraint["v4_execution_root"] == "src/v4_campaign"
    assert constraint["edit_under_src_breakout_research_forbidden_without_reauthorization"] is True


def test_the_benchmark_rule_is_bound() -> None:
    protocol = _load(PROTOCOL_PATH)
    benchmark = protocol["benchmark_rule"]
    dataset = REPO_ROOT / benchmark["dataset_path"]
    assert dataset.exists()
    assert benchmark["content_hash"] == _sha256_file(dataset)
    assert benchmark["alignment"] == ALIGNMENT_RULE
    assert benchmark["no_forward_fill"] is True
    assert benchmark["fail_closed"]
    assert "576" in benchmark["grid_rule"]
    assert benchmark["symbol"] == "BTCUSDT"


def test_the_benchmark_is_external_to_the_v4_manifest() -> None:
    protocol = _load(PROTOCOL_PATH)
    benchmark = protocol["benchmark_rule"]
    assert "external to the v4 data-manifest identity" in benchmark["note"]


def test_the_execution_authorization_authorizes_nothing() -> None:
    protocol = _load(PROTOCOL_PATH)
    auth = protocol["execution_authorization"]
    assert auth["execution_authorized"] is False
    assert auth["selection_authorization_present"] is False


def test_the_deviation_disclosure_records_not_applicable() -> None:
    protocol = _load(PROTOCOL_PATH)
    disclosure = protocol["deviation_disclosure"]
    assert disclosure["not_applicable"] is True
    assert disclosure["records_with_btc_filter"] == 0


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"manifest_hash": "0" * 64}), rehash=False)
    failures = _failures(root)
    assert failures
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_a_widened_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["evaluation_scope"]["constituents"].append("ZZZUSDT"),
    )
    failures = _failures(root)
    assert any("not the frozen candidate set" in failure for failure in failures)


def test_verifier_detects_a_data_manifest_identity_mismatch(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["evaluation_scope"].update(
            {"data_manifest_hash": "1" * 64}
        ),
    )
    failures = _failures(root)
    assert any("data-manifest hash" in failure for failure in failures)


def test_verifier_detects_a_code_hash_constraint_violation(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["code_hash_constraint"].update(
            {"v4_execution_root": "src/breakout_research"}
        ),
    )
    failures = _failures(root)
    assert any("v4 execution root" in failure for failure in failures)


def test_verifier_detects_a_benchmark_hash_mismatch(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["benchmark_rule"].update(
            {"content_hash": "3" * 64}
        ),
    )
    failures = _failures(root)
    assert any("benchmark content hash does not match" in failure for failure in failures)


def test_verifier_detects_a_dropped_alignment_rule(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["benchmark_rule"].update(
            {"alignment": "the engine pairs the series by index"}
        ),
    )
    failures = _failures(root)
    assert any("does not bind the benchmark alignment rule" in failure for failure in failures)


def test_verifier_detects_an_execution_authorization_claim(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda document: document["execution_authorization"].update(
            {"execution_authorized": True}
        ),
    )
    failures = _failures(root)
    assert any("claims an execution authorization" in failure for failure in failures)

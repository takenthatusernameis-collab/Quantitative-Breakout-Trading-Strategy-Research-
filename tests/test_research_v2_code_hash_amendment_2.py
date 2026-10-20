"""Tests for the preregistered v2 code-hash amendment 2 (the RL1 location correction).

``configs/research_v2_code_hash_amendment_2.json`` corrects the recorded
**location** of residual limitation ``RL1`` in the frozen
``configs/research_v2_code_hash_amendment_1.json`` without editing that
artifact. The tests prove that

* the amendment is self-hashing and reproducible from its producer;
* the corrected artifact is byte-identical and still records the original
  (defective) location, so the correction is carried by reference and not by an
  edit;
* the code-hash comparison sites are **recomputed from the source tree** and are
  exactly the sites the amendment records -- the amendment can neither omit a
  site nor invent one, which is the very defect of the original record;
* every recorded evidence step still exists verbatim in the source, and the
  corrected location is exactly the set of files that hold a live-vs-recorded
  site;
* the correction changes no behaviour: the limitation, its consequence, the
  gate, the authorized value of record and the hashed set are untouched;
* the verifier is not vacuous: tampering with the amendment, with the corrected
  artifact, with the source tree or with the recorded evidence is detected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_2.json"
CORRECTED_ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_code_hash_amendment_1.json"

HASHED_SET_ROOT = "src/breakout_research"


def _load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_research_v2_code_hash_amendment_2",
    "scripts/verify_research_v2_code_hash_amendment_2.py",
)
producer = _load_module(
    "build_v2_code_hash_amendment_2", "scripts/build_v2_code_hash_amendment_2.py"
)


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        pytest.skip(f"{path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of symlinks to the parts of the repository the verifier reads.

    The hashed source tree is copied for real, so a test may modify it without
    ever writing to the working tree. The large result directories are skipped:
    the verifier never reads them.
    """
    root = tmp_path / "repo"
    skip_dirs = {".git", "__pycache__", ".pytest_cache"}
    skip_relative = {
        Path("research/results_shards"),
        Path("research/campaign_cycles"),
        Path("research/shards_v2"),
    }
    hashed = Path(HASHED_SET_ROOT)
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        if relative in skip_relative:
            dirs[:] = []
            continue
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            source = Path(current) / name
            target = root / relative / name
            if relative == hashed or hashed in relative.parents:
                # The hashed set is copied for real, recursively: a symlink would
                # let a test write through it into the working tree.
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


def _tamper(root: Path, mutate: Callable[[Dict[str, Any]], None]) -> Path:
    amendment = _load(AMENDMENT_PATH)
    mutate(amendment)
    _replace(root, "configs/research_v2_code_hash_amendment_2.json", amendment)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


def test_verifier_reports_no_failures():
    report = verifier.verify(REPO_ROOT)
    assert report["failures"] == []
    assert report["ok"] is True


def test_manifest_hash_recomputes_from_the_document():
    amendment = _load(AMENDMENT_PATH)
    excluded = tuple(amendment["hashing"]["manifest_hash_excluded_keys"])
    assert amendment["manifest_hash"] == verifier.compute_manifest_hash(amendment, excluded)


def test_amendment_is_reproducible_from_the_producer():
    built = producer.build(REPO_ROOT)
    recorded = _load(AMENDMENT_PATH)
    assert built["manifest_hash"] == recorded["manifest_hash"]
    assert built == recorded


def test_the_corrected_artifact_is_byte_identical_and_still_records_the_old_location():
    amendment = _load(AMENDMENT_PATH)
    corrected = _load(CORRECTED_ARTIFACT_PATH)
    correction = amendment["correction"]
    assert verifier.sha256_file(CORRECTED_ARTIFACT_PATH) == correction["target_file_sha256"]
    assert corrected["manifest_hash"] == correction["target_manifest_hash"]
    rl1 = next(
        item for item in corrected["residual_limitations"] if item["id"] == "RL1"
    )
    assert rl1["location"] == correction["recorded_location"]
    assert rl1["location"] != correction["corrected_location"]
    assert correction["target_artifact_edited"] is False


def test_the_correction_changes_no_behaviour():
    amendment = _load(AMENDMENT_PATH)
    correction = amendment["correction"]
    assert correction["behaviour_change"] is False
    assert correction["limitation_text_changed"] is False
    assert correction["consequence_text_changed"] is False
    assert amendment["amendment_status"] == "PREREGISTERED_CODE_HASH_AMENDMENT_2_DESIGN_ONLY"


def test_the_recorded_sites_are_exactly_the_sites_the_source_contains():
    scanned = verifier.scan_code_hash_comparison_sites(REPO_ROOT)
    recorded = _load(AMENDMENT_PATH)["code_hash_comparison_sites"]["sites"]
    assert [(site["path"], site["line"], site["comparison"]) for site in scanned] == [
        (site["path"], site["line"], site["comparison"]) for site in recorded
    ]
    assert len(scanned) == 5


def test_the_correction_names_the_site_the_prior_correction_omitted():
    amendment = _load(AMENDMENT_PATH)
    prior = amendment["correction"]["decision_record_correction"]
    assert prior["is_complete"] is False
    assert "backtest/shards.py" in prior["omission"]
    corrected = amendment["correction"]["corrected_location"]
    assert "src/breakout_research/backtest/shards.py" in corrected
    assert "pilot_gate_validator.py" not in corrected


def test_every_recorded_evidence_step_matches_the_source():
    amendment = _load(AMENDMENT_PATH)
    for site in amendment["code_hash_comparison_sites"]["sites"]:
        steps = list(site["live_digest_chain"])
        for chain in site["recorded_value_chains"]:
            steps.extend(chain)
        assert steps, f"{site['path']}:{site['line']} records no evidence"
        for step in steps:
            resolved = verifier._resolve_step(REPO_ROOT, step)
            assert resolved is not None
            assert resolved == {
                key: step.get(key) for key in ("path", "anchor", "span", "line", "text")
            }


def test_the_live_chain_starts_with_the_live_digest_and_the_recorded_chain_with_a_read():
    amendment = _load(AMENDMENT_PATH)
    for site in amendment["code_hash_comparison_sites"]["sites"]:
        if site["live_digest_chain"]:
            first = site["live_digest_chain"][0]
            assert "compute_code_hash(" in first["text"]
        for chain in site["recorded_value_chains"]:
            assert any(
                marker in chain[0]["text"]
                for marker in verifier.PERSISTED_READ_MARKERS
            )


def test_the_corrected_location_is_exactly_the_live_vs_recorded_files():
    amendment = _load(AMENDMENT_PATH)
    block = amendment["code_hash_comparison_sites"]
    sites = block["sites"]
    live_files = sorted(
        {site["path"] for site in sites if site["classification"] == "LIVE_VS_RECORDED"}
    )
    excluded_files = sorted(
        {site["path"] for site in sites if site["classification"] == "RECORDED_VS_RECORDED"}
    )
    assert sorted(block["corrected_location_files"]) == live_files
    assert sorted(block["excluded_location_files"]) == excluded_files
    assert live_files == [
        "src/breakout_research/backtest/shards.py",
        "src/breakout_research/campaign.py",
    ]
    assert excluded_files == ["src/breakout_research/pilot_gate_validator.py"]
    assert (
        amendment["correction"]["corrected_location"]
        == verifier.corrected_location_string(sites)
    )


def test_the_pilot_gate_validator_sites_are_recorded_as_recorded_vs_recorded():
    amendment = _load(AMENDMENT_PATH)
    sites = amendment["code_hash_comparison_sites"]["sites"]
    validator_sites = [
        site for site in sites if site["path"].endswith("pilot_gate_validator.py")
    ]
    assert len(validator_sites) == 2
    for site in validator_sites:
        assert site["classification"] == "RECORDED_VS_RECORDED"
        assert site["live_digest_chain"] == []


def test_the_hashed_set_is_identified_by_the_canonical_digest():
    amendment = _load(AMENDMENT_PATH)
    constraint = amendment["code_hash_constraint"]
    assert constraint["canonical_source_digest"] == verifier.canonical_source_digest(REPO_ROOT)
    assert constraint["authorized_code_hash_status"] == "RETAINED_AS_VALUE_OF_RECORD"
    assert constraint["authorized_code_hash"] == json.loads(
        (REPO_ROOT / "research_state" / "campaign_authorization.json").read_text(
            encoding="utf-8"
        )
    )["code_hash"]


def test_an_ordered_digest_mismatch_is_not_a_verifier_failure():
    report = verifier.verify(REPO_ROOT)
    assert report["ok"] is True
    assert report["ordered_code_hash_matches_authorized"] in (True, False)
    assert report["environment_facts"] == [] or all(
        "environment fact" in fact for fact in report["environment_facts"]
    )


def test_the_preflight_exists_and_implements_the_compatibility_check():
    amendment = _load(AMENDMENT_PATH)
    preflight = amendment["preflight"]
    path = REPO_ROOT / preflight["path"]
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "canonical_source_digest" in source
    assert amendment["code_hash_constraint"]["authorized_code_hash"] in source


def test_the_amendment_authorizes_nothing():
    amendment = _load(AMENDMENT_PATH)
    for flag, value in amendment["execution_authorization"].items():
        if flag == "statement":
            continue
        assert value is False


def test_v1_artifacts_are_unchanged():
    for relative, digest in verifier.V1_ARTIFACT_SHA256.items():
        target = REPO_ROOT / relative
        assert target.exists()
        assert verifier.sha256_file(target) == digest


def test_the_confirmatory_window_is_untouched():
    data_manifest = _load(REPO_ROOT / "research" / "data_manifest_v2.json")
    window = data_manifest["confirmatory_window"]
    assert window["confirmatory_window_status"] == "NOT_STARTED"
    assert window["holdout_exposed_count"] == 0
    checkpoint = _load(REPO_ROOT / "research_state" / "checkpoint_v2.json")
    assert checkpoint["holdout_exposed_count"] == 0


def test_verifier_detects_a_tampered_manifest_hash(tmp_path):
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda doc: doc.update({"manifest_hash": "0" * 64}))
    failures = _failures(root)
    assert any("manifest_hash mismatch" in failure for failure in failures)


def test_verifier_detects_an_edited_corrected_artifact(tmp_path):
    root = _mirror_repo(tmp_path)
    corrected = _load(CORRECTED_ARTIFACT_PATH)
    corrected["residual_limitations"][0]["location"] = "src/breakout_research/campaign.py"
    _replace(root, "configs/research_v2_code_hash_amendment_1.json", corrected)
    failures = _failures(root)
    assert any("does not match its recorded sha256" in failure for failure in failures)


def test_verifier_detects_a_removed_comparison_site(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        sites = document["code_hash_comparison_sites"]["sites"]
        sites.pop()
        document["code_hash_comparison_sites"]["total_sites"] = len(sites)

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("do not match the source" in failure for failure in failures)


def test_verifier_detects_an_invented_comparison_site(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        sites = document["code_hash_comparison_sites"]["sites"]
        invented = dict(sites[0])
        invented["line"] = 9999
        invented["comparison"] = "invented != code_hash"
        sites.append(invented)

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("do not match the source" in failure for failure in failures)


def test_verifier_detects_a_mislabelled_classification(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        for site in document["code_hash_comparison_sites"]["sites"]:
            if site["classification"] == "LIVE_VS_RECORDED":
                site["classification"] = "RECORDED_VS_RECORDED"
                break

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not match the live-vs-recorded sites" in failure for failure in failures)


def test_verifier_detects_evidence_that_does_not_match_the_source(tmp_path):
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        site = document["code_hash_comparison_sites"]["sites"][0]
        site["live_digest_chain"][0]["text"] = "code_hash = compute_code_hash()  # tampered"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not match the source" in failure for failure in failures)


def test_verifier_detects_a_source_edit_that_invalidates_the_evidence(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "backtest" / "shards.py"
    source = target.read_text(encoding="utf-8")
    target.write_text(
        source.replace(
            "        self.code_hash = code_hash",
            "        self.code_hash = code_hash  # tampered",
        ),
        encoding="utf-8",
    )
    failures = _failures(root)
    assert any("matches the source" in failure for failure in failures)
    assert any("canonical digest" in failure for failure in failures)


def test_verifier_detects_a_new_comparison_site_in_the_source(tmp_path):
    root = _mirror_repo(tmp_path)
    target = root / HASHED_SET_ROOT / "campaign.py"
    source = target.read_text(encoding="utf-8")
    target.write_text(
        source.replace(
            "        self.code_hash = compute_code_hash()",
            "        self.code_hash = compute_code_hash()\n"
            "        if self.code_hash != stored_code:\n"
            "            raise RuntimeError('injected comparison')\n",
            1,
        ),
        encoding="utf-8",
    )
    failures = _failures(root)
    assert any("do not match the source" in failure for failure in failures)


def test_verifier_detects_a_self_authorizing_amendment(tmp_path):
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda doc: doc["execution_authorization"].update({"grid_run_authorized": True}))
    failures = _failures(root)
    assert any("grid_run_authorized is not false" in failure for failure in failures)


def test_verifier_detects_a_widened_corrected_location(tmp_path):
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda doc: doc["correction"].update(
            {"corrected_location": doc["correction"]["corrected_location"] + " and more"}
        ),
    )
    failures = _failures(root)
    assert any("does not match the live-vs-recorded sites" in failure for failure in failures)


def test_verifier_detects_a_claim_that_the_prior_correction_was_complete(tmp_path):
    root = _mirror_repo(tmp_path)
    _tamper(
        root,
        lambda doc: doc["correction"]["decision_record_correction"].update(
            {"is_complete": True}
        ),
    )
    failures = _failures(root)
    assert any("prior correction was incomplete" in failure for failure in failures)

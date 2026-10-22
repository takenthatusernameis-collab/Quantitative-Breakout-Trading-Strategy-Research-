"""Tests for the v6 execution protocol, its verifier and its producer.

The v6 execution protocol is the artifact that says how a future v6 grid run
may be authorized and bounded. It is published *complete* -- the v5 chain
needed two amendments to add the bindings the first publication lacked, and
the v6 publication carries them from the start. The rules these tests pin are:

* the **evaluation scope** is exactly the frozen candidate set, which is the
  validated subset of the frozen 20-name band, and it is bound to the freeze
  and to the two manifests by their recomputed identities;
* the **benchmark rule** is bound: the dataset, its recomputed content hash,
  its recomputed candle count and bounds, the alignment rule, the fail-closed
  list and the "no configuration is dropped" rule -- and the v3 and v4 chains'
  benchmark dataset, whose candles close inside the open v2 confirmatory
  window, is refused;
* the **inherited rules** are the v1 rules: the digest of the inherited blocks
  is recomputed from ``configs/research_v1.json``, the grid still enumerates
  2,304 combinations and the single confirmatory criterion is the unchanged v1
  selection rule;
* the **code-hash constraint** places the v6 execution path outside the hashed
  set and records the authorized code hash and the canonical tree digest, both
  recomputed;
* the **evaluation authorization** authorizes nothing;
* the **confirmatory-window binding** names the freeze's identity, the window
  bounds and the evaluation gate, which is the later of the four recomputed
  earlier gates and the v6 window's own earliest end;
* the **supersedes chain** names the v5 execution protocol and its two
  amendments with their recomputed identities.

The tamper controls mutate a copy of the repository and assert that the
verifier refuses the mutated tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent

PROTOCOL_PATH = REPO_ROOT / "configs" / "research_v6_execution.json"
FREEZE_PATH = REPO_ROOT / "configs" / "research_v6_candidate_freeze.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v6.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v6.json"
V3_BENCHMARK_RELATIVE = "research/data/candles_v3/BTCUSDT_1h_50d357b0cb2d6f8d.csv"

PROTOCOL_RELATIVE = "configs/research_v6_execution.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module("verify_v6_execution", "scripts/verify_v6_execution.py")
producer = _load_module("build_v6_execution", "scripts/build_v6_execution.py")
rules = _load_module("v6_universe_rules", "scripts/v6_universe_rules.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap. The large trees the v6
    execution verifier never reads are skipped;
    ``test_the_mirror_of_the_untouched_repository_passes`` is the guard that
    keeps the optimization honest.
    """
    root = tmp_path / "repo"
    skip_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "campaign_cycles",
        "results_shards",
        "shards_v2",
        "shards_v3",
        "shards_v4",
        "shards_v5",
        "strategies",
        "baselines",
        "candles",
        "candles_v2",
        "candles_v3",
        "candles_v4",
        "candles_v5",
    }
    skip_files = {
        "results.jsonl",
        "results_v2.jsonl",
        "results_v3.jsonl",
        "results_v4.jsonl",
        "results_v5.jsonl",
        "results_manifest.json",
        "results_manifest.legacy_707f.json",
        "results_manifest_v2.json",
        "results_manifest_v3.json",
        "results_manifest_v4.json",
        "results_manifest_v5.json",
    }
    for current, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        relative = Path(current).relative_to(REPO_ROOT)
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in skip_files:
                continue
            source = Path(current) / name
            target = root / relative / name
            if target.is_symlink() or target.exists():
                target.unlink()
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
    mutate,
    relative: str = PROTOCOL_RELATIVE,
    rehash: bool = True,
) -> Path:
    document = _load(REPO_ROOT / relative)
    mutate(document)
    if rehash:
        document["manifest_hash"] = verifier.compute_manifest_hash(document, ("manifest_hash",))
    _replace(root, relative, document)
    return root


def _failures(root: Path) -> List[str]:
    return verifier.verify(root)["failures"]


# --------------------------------------------------------------------------
# the rules themselves
# --------------------------------------------------------------------------


def test_the_verifier_passes_on_the_repository() -> None:
    report = verifier.verify(REPO_ROOT)
    assert report["ok"], report["failures"]
    assert report["failures"] == []


def test_the_protocol_is_self_hashing() -> None:
    protocol = _load(PROTOCOL_PATH)
    assert verifier.compute_manifest_hash(protocol, ("manifest_hash",)) == protocol["manifest_hash"]


def test_the_protocol_is_reproduced_byte_for_byte_by_its_producer() -> None:
    protocol = _load(PROTOCOL_PATH)
    rebuilt = producer.build(REPO_ROOT)
    assert rebuilt == protocol
    assert json.dumps(rebuilt, indent=2) + "\n" == PROTOCOL_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / PROTOCOL_RELATIVE
    target.unlink()
    assert producer.main(["--repo-root", str(root)]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root)]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_evaluated_scope_is_the_frozen_candidate_set() -> None:
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    universe = _load(UNIVERSE_PATH)
    scope = protocol["evaluation_scope"]
    frozen = [
        entry["binance_pair"] for entry in freeze["candidates"] if entry.get("validated") is True
    ]
    validated = sorted(
        entry["binance_pair"]
        for entry in universe["eligible_assets"]
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    assert list(scope["constituents"]) == frozen
    assert sorted(scope["constituents"]) == validated
    assert scope["count"] == len(frozen) == 7
    assert scope["candidate_freeze_hash"] == freeze["manifest_hash"]
    assert scope["universe_manifest_hash"] == universe["manifest_hash"]
    assert scope["data_manifest_hash"] == _load(DATA_PATH)["manifest_hash"]


def test_the_benchmark_is_bound_by_its_recomputed_content_hash() -> None:
    protocol = _load(PROTOCOL_PATH)
    benchmark = protocol["benchmark_rule"]
    dataset = REPO_ROOT / benchmark["dataset_path"]
    assert dataset.exists()
    assert verifier.sha256_file(dataset) == benchmark["content_hash"]
    bounds = verifier._dataset_bounds(dataset)
    assert benchmark["observed_candle_count"] == bounds["observed_candle_count"]
    assert benchmark["first_candle_timestamp"] == bounds["first_candle_timestamp"]
    assert benchmark["last_candle_timestamp"] == bounds["last_candle_timestamp"]
    assert benchmark["alignment"] == verifier.ALIGNMENT_RULE
    assert benchmark["no_forward_fill"] is True
    assert benchmark["fail_closed"]
    assert "576" in benchmark["grid_rule"]


def test_the_v3_and_v4_benchmark_is_refused_and_its_overrun_is_recorded() -> None:
    protocol = _load(PROTOCOL_PATH)
    benchmark = protocol["benchmark_rule"]
    assert benchmark["dataset_path"] != V3_BENCHMARK_RELATIVE
    dataset = REPO_ROOT / V3_BENCHMARK_RELATIVE
    assert dataset.exists()
    cutoff = "2026-10-19T22:00:00Z"
    cutoff_ms = int(verifier._parse_iso(cutoff).timestamp() * 1000)
    after = verifier._candles_after_cutoff(dataset, cutoff_ms)
    assert after == 13
    assert str(after) in benchmark["note"]


def test_the_inherited_rules_are_the_unchanged_v1_rules() -> None:
    protocol = _load(PROTOCOL_PATH)
    spec_v1 = _load(REPO_ROOT / "configs" / "research_v1.json")
    inherited = protocol["inherited_rules"]
    assert tuple(inherited["blocks"]) == verifier.INHERITED_V1_BLOCKS
    digest = verifier.sha256_bytes(
        verifier.canonical(
            {block: spec_v1.get(block) for block in verifier.INHERITED_V1_BLOCKS}
        ).encode("utf-8")
    )
    assert inherited["blocks_digest"] == digest
    assert inherited["v1_specification_hash"] == spec_v1["specification_hash"]
    assert inherited["grid_total_combinations"] == 2304
    criterion = inherited["single_confirmatory_criterion"]
    assert "unchanged v1 selection rule" in criterion
    assert "never re-tuned" in criterion


def test_the_code_hash_constraint_keeps_the_execution_path_outside_the_hashed_set() -> None:
    protocol = _load(PROTOCOL_PATH)
    constraint = protocol["code_hash_constraint"]
    authorization = _load(REPO_ROOT / "research_state" / "campaign_authorization.json")
    assert constraint["authorized_code_hash"] == authorization["code_hash"]
    assert constraint["canonical_hashed_set_digest"] == rules.canonical_source_digest(REPO_ROOT)
    assert constraint["hashed_source_root"] == "src/breakout_research"
    assert constraint["v6_execution_root"] == "src/v6_campaign"
    assert not constraint["v6_execution_root"].startswith("src/breakout_research/")
    assert constraint["v6_execution_must_live_outside_hashed_set"] is True
    assert constraint["edit_under_src_breakout_research_forbidden_without_reauthorization"] is True


def test_the_protocol_authorizes_nothing() -> None:
    protocol = _load(PROTOCOL_PATH)
    authorization = protocol["execution_authorization"]
    for flag in (
        "execution_authorized",
        "grid_run_authorized",
        "candle_fetch_authorized",
        "confirmatory_evaluation_authorized",
        "second_run_authorized",
    ):
        assert authorization[flag] is False, flag
    for flag in (
        "execution_authorized",
        "campaign_authorized",
        "selection_authorized",
        "confirmatory_authorized",
    ):
        assert protocol["authorization"][flag] is False, flag
    assert authorization["selection_authorization_present"] is False


def test_the_evaluation_gate_is_the_later_of_the_five_gates() -> None:
    protocol = _load(PROTOCOL_PATH)
    freeze = _load(FREEZE_PATH)
    ends = []
    for version, relative, key in verifier.GATE_OWNERS:
        owner = _load(REPO_ROOT / relative)
        ends.append(verifier._window_bounds(owner, key)["earliest_possible_end_utc"])
    ends.append(freeze["confirmatory_window"]["earliest_possible_end_utc"])
    window = protocol["candidate_freeze_and_confirmatory_window"]
    assert window["evaluation_may_not_start_before_utc"] == max(ends)
    assert window["confirmatory_window_opens_utc"] == freeze["confirmatory_window"]["opens_utc"]
    assert window["min_confirmatory_window_hours"] == freeze["confirmatory_window"]["min_hours"]
    assert window["single_use"] is True
    assert window["no_ranking_or_retuning_on_holdout"] is True


def test_the_supersedes_chain_names_the_v5_execution_artifacts() -> None:
    protocol = _load(PROTOCOL_PATH)
    chain = protocol["supersedes"]["superseded_artifacts"]
    for relative in verifier.V5_EXECUTION_RELATIVES:
        key = Path(relative).stem
        document = _load(REPO_ROOT / relative)
        recomputed = verifier.compute_manifest_hash(document, ("manifest_hash",))
        assert chain[key]["path"] == relative
        assert chain[key]["manifest_hash"] == recomputed
        assert chain[key]["sha256"] == verifier.sha256_file(REPO_ROOT / relative)
    assert protocol["supersedes"]["v1_v2_v3_v4_v5_artifacts_are_immutable"] is True


def test_the_result_layout_does_not_collide_with_a_frozen_path() -> None:
    protocol = _load(PROTOCOL_PATH)
    layout = protocol["v6_result_layout"]
    paths = [str(value) for value in layout.values() if isinstance(value, str)]
    for foreign in verifier.FROZEN_RESULT_PATHS:
        assert foreign not in paths, foreign
    for relative in verifier.V6_EXECUTION_PATHS:
        assert not (REPO_ROOT / relative).exists(), relative


# --------------------------------------------------------------------------
# tamper controls
# --------------------------------------------------------------------------


def test_the_mirror_of_the_untouched_repository_passes(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    assert _failures(root) == []


def test_the_verifier_detects_a_tampered_manifest_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    _tamper(root, lambda document: document.update({"manifest_hash": "0" * 64}), rehash=False)
    assert any("manifest_hash mismatch" in failure for failure in _failures(root))


def test_the_verifier_detects_a_widened_evaluation_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["constituents"].append("BTCUSDT")
        document["evaluation_scope"]["count"] = 8

    _tamper(root, mutate)
    assert any("not the frozen candidate set" in failure for failure in _failures(root))


def test_the_verifier_detects_a_narrowed_evaluation_scope(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["constituents"].pop()
        document["evaluation_scope"]["count"] = 6

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not the frozen candidate set" in failure for failure in failures)


def test_the_verifier_detects_a_stale_freeze_binding(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["evaluation_scope"]["candidate_freeze_hash"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not bound to the freeze manifest hash" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_benchmark_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["benchmark_rule"]["content_hash"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("benchmark content hash does not match" in failure for failure in failures)


def test_the_verifier_detects_the_v3_benchmark_dataset(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["benchmark_rule"]["dataset_path"] = V3_BENCHMARK_RELATIVE
        document["benchmark_rule"]["content_hash"] = verifier.sha256_file(
            REPO_ROOT / V3_BENCHMARK_RELATIVE
        )

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("reuses the v3 and v4 chains' benchmark dataset" in failure for failure in failures)


def test_the_verifier_detects_a_wrong_inherited_rules_digest(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["inherited_rules"]["blocks_digest"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("inherited rules digest does not recompute" in failure for failure in failures)


def test_the_verifier_detects_a_stale_authorized_code_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["code_hash_constraint"]["authorized_code_hash"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("authorized code hash of record" in failure for failure in failures)


def test_the_verifier_detects_an_execution_path_inside_the_hashed_set(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["code_hash_constraint"]["v6_execution_root"] = "src/breakout_research/v6"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("inside the hashed source set" in failure for failure in failures)


def test_the_verifier_detects_a_self_authorizing_protocol(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["execution_authorization"]["execution_authorized"] = True

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("does not record execution_authorized as false" in failure for failure in failures)


def test_the_verifier_detects_an_evaluation_gate_that_is_too_early(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["candidate_freeze_and_confirmatory_window"][
            "evaluation_may_not_start_before_utc"
        ] = "2026-10-22T02:00:00Z"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("effective v6 evaluation start" in failure for failure in failures)


def test_the_verifier_detects_a_supersedes_chain_that_names_an_older_artifact(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["supersedes"]["superseded_artifacts"]["research_v5_execution"][
            "manifest_hash"
        ] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("names another manifest hash" in failure for failure in failures)


def test_the_verifier_detects_a_result_layout_that_collides_with_a_frozen_path(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["v6_result_layout"]["ledger_path"] = "research/ledger_v5.json"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("collides with the frozen path" in failure for failure in failures)


def test_the_verifier_detects_a_v6_run_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "ledger_v6.json").write_text("{}", encoding="utf-8")
    failures = _failures(root)
    assert any("the v6 run artifact" in failure for failure in failures)

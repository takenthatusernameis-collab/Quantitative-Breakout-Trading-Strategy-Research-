"""Tests for the v6 candidate freeze and its read-only verifier.

The v6 candidate freeze is the first freeze of the chain that binds a
**band** rather than a plain candidate list: the band is 20 names taken in
strictly descending market-capitalization order below the recomputed v5 floor,
and the validated subset is a *consequence* of the band, never its definition.
The rules these tests pin are therefore:

* the **band-width rule**: the band holds exactly ``top_n`` names in strictly
  descending market-capitalization order, it is re-derived from the raw
  snapshot bytes, and it is never widened;
* the **floor rule**: every band member is strictly below the floor recomputed
  from ``research/universe_manifest_v5.json``, the source the v6 specification
  names;
* the **identity rule**: no band member is an asset of the v1, the v2, the v3,
  the v4 or the v5 universe, on the Binance base symbol or the CoinGecko id;
* the **validation rule**: the outcome of every band member is re-derived from
  the validation evidence, and a member excluded for a *history* reason keeps
  its verified Binance spot pair -- excluding it does not un-verify the pair;
* the **development boundary**: the cutoff is the earliest open
  confirmatory-window start, the development window holds exactly 26,280 closed
  hourly candles and ends with the candle that closes exactly at the cutoff;
* the **window rule**: the v6 confirmatory window is a new, single-use window
  that opens at the first hour boundary after the freeze, and the evaluation
  gate is the later of the four recomputed earlier gates and the v6 window's
  own earliest end;
* the **authorizes-nothing rule**: the freeze starts the exposure counter at
  0, authorizes nothing, and no v6 run artifact exists.

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

FREEZE_PATH = REPO_ROOT / "configs" / "research_v6_candidate_freeze.json"
SPEC_PATH = REPO_ROOT / "configs" / "research_v6.json"
UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v6.json"
DATA_PATH = REPO_ROOT / "research" / "data_manifest_v6.json"
V5_FREEZE_PATH = REPO_ROOT / "configs" / "research_v5_candidate_freeze.json"
V5_UNIVERSE_PATH = REPO_ROOT / "research" / "universe_manifest_v5.json"

FREEZE_RELATIVE = "configs/research_v6_candidate_freeze.json"


def _load_module(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_module(
    "verify_research_v6_candidate_freeze", "scripts/verify_research_v6_candidate_freeze.py"
)
producer = _load_module("build_v6_candidate_freeze", "scripts/build_v6_candidate_freeze.py")
rules = _load_module("v6_universe_rules", "scripts/v6_universe_rules.py")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mirror_repo(tmp_path: Path) -> Path:
    """A temporary tree of the parts of the repository the verifier reads.

    Every file is symlinked, so the mirror is cheap even though the chain
    carries ~50 MB of candle datasets. The tamper controls replace single
    files, and ``_replace`` unlinks the symlink before writing.

    The large trees the v6 candidate freeze verifier never reads -- the result
    shards, the campaign cycles and the earlier candle datasets -- are skipped,
    so the mirror is a few megabytes of links instead of a walk over ~2.5 GB.
    ``test_the_mirror_of_the_untouched_repository_passes`` is the guard: if the
    verifier ever starts reading a skipped tree, that test fails with a
    "missing artifact" report instead of the tamper control going vacuous.
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
    relative: str = FREEZE_RELATIVE,
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


def test_the_freeze_is_self_hashing() -> None:
    freeze = _load(FREEZE_PATH)
    assert verifier.compute_manifest_hash(freeze, ("manifest_hash",)) == freeze["manifest_hash"]


def test_the_freeze_is_reproduced_byte_for_byte_by_its_producer() -> None:
    freeze = _load(FREEZE_PATH)
    rebuilt = producer.build(REPO_ROOT, freeze["candidate_freeze_utc"])
    assert rebuilt == freeze
    rendered = json.dumps(rebuilt, indent=2) + "\n"
    assert rendered == FREEZE_PATH.read_text(encoding="utf-8")


def test_the_producer_refuses_to_overwrite_the_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    target = root / FREEZE_RELATIVE
    target.unlink()
    assert producer.main(["--repo-root", str(root), "--freeze-utc", "2026-10-22T01:28:36Z"]) == 0
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert producer.main(["--repo-root", str(root), "--freeze-utc", "2026-10-22T01:28:36Z"]) == 1
    assert target.read_text(encoding="utf-8") == written


def test_the_band_is_twenty_names_in_descending_market_cap_order() -> None:
    freeze = _load(FREEZE_PATH)
    members = freeze["band"]["members"]
    assert len(members) == 20
    assert freeze["band"]["band_width"] == 20
    caps = [int(entry["market_cap_usd"]) for entry in members]
    assert caps == sorted(caps, reverse=True)
    assert len(set(caps)) == len(caps)
    assert [entry["rank"] for entry in members] == list(range(1, 21))


def test_the_band_is_re_derived_from_the_raw_snapshot_bytes() -> None:
    freeze = _load(FREEZE_PATH)
    spec = _load(SPEC_PATH)
    markets = json.loads(
        (REPO_ROOT / "research" / "v6_evidence" / "raw_market_cap_response.json").read_text(
            encoding="utf-8"
        )
    )
    prior = [_load(REPO_ROOT / relative) for relative in rules.PRIOR_UNIVERSE_RELATIVES]
    exclusion_rules = rules.load_exclusion_rules(REPO_ROOT)
    derived, _excluded, _records = rules.derive_batch(spec, markets, prior, exclusion_rules)
    assert [entry["binance_pair"] for entry in derived] == [
        entry["binance_pair"] for entry in freeze["band"]["members"]
    ]


def test_the_validated_set_is_a_consequence_of_the_band() -> None:
    freeze = _load(FREEZE_PATH)
    members = freeze["band"]["members"]
    validated = [entry for entry in members if entry["validated"] is True]
    assert [entry["binance_pair"] for entry in freeze["candidates"]] == [
        entry["binance_pair"] for entry in validated
    ]
    assert freeze["candidate_set"]["count"] == len(validated)
    assert freeze["band"]["validated_count"] == len(validated)
    assert freeze["band"]["excluded_member_count"] == len(members) - len(validated)
    assert freeze["candidate_set"]["members"] == [
        entry["binance_pair"] for entry in validated
    ]


def test_every_band_member_is_strictly_below_the_v5_floor() -> None:
    freeze = _load(FREEZE_PATH)
    floor_symbol, floor_market_cap = rules.recompute_floor(_load(V5_UNIVERSE_PATH))
    assert floor_symbol == "YLDS"
    assert floor_market_cap == 498236520
    assert freeze["floor"]["floor_market_cap_usd"] == floor_market_cap
    for entry in freeze["band"]["members"]:
        assert int(entry["market_cap_usd"]) < floor_market_cap, entry["binance_pair"]


def test_no_band_member_is_an_asset_of_v1_to_v5() -> None:
    freeze = _load(FREEZE_PATH)
    prior = [_load(REPO_ROOT / relative) for relative in rules.PRIOR_UNIVERSE_RELATIVES]
    symbols, identifiers = rules.prior_universe_assets(*prior)
    assert len(symbols) == 83
    assert len(identifiers) == 83
    for entry in freeze["band"]["members"]:
        marker = entry["binance_pair"][:-4]
        assert marker.upper() not in symbols, entry["binance_pair"]
        assert str(entry["coingecko_id"]) not in identifiers, entry["binance_pair"]


def test_every_band_members_validation_outcome_is_the_re_derived_one() -> None:
    freeze = _load(FREEZE_PATH)
    spec = _load(SPEC_PATH)
    spot = _load(REPO_ROOT / "research" / "v6_evidence" / "binance_spot_verification.json")
    candles = _load(REPO_ROOT / "research" / "v6_evidence" / "candle_verification.json")
    min_candles = int(spec["universe"]["min_candles"])
    for entry in freeze["band"]["members"]:
        outcome = verifier.band_member_outcome(
            entry["binance_pair"], spot, candles, min_candles
        )
        assert entry["validated"] is outcome["validated"], entry["binance_pair"]
        assert entry["exclusion_reason"] == outcome["exclusion_reason"], entry["binance_pair"]
        assert entry["binance_spot_verified"] is outcome["binance_spot_verified"], (
            entry["binance_pair"]
        )
        assert entry["candle_history_verified"] is outcome["candle_history_verified"], (
            entry["binance_pair"]
        )
        assert entry["observed_candles"] == outcome["observed_candles"], entry["binance_pair"]


def test_a_history_exclusion_keeps_its_verified_binance_spot_pair() -> None:
    """A short-history exclusion is not a spot exclusion.

    The v6 band holds four members that are tradeable on Binance spot and
    excluded for a short history. Recording them as *not* spot-verified would
    be a false statement about the evidence; the verifier therefore compares
    the recorded flag with the re-derived one instead of demanding ``False``
    for every excluded member.
    """
    freeze = _load(FREEZE_PATH)
    short_history = [
        entry
        for entry in freeze["band"]["members"]
        if entry["exclusion_reason"] == "insufficient_hourly_history"
    ]
    assert short_history, "the band is expected to hold short-history exclusions"
    for entry in short_history:
        assert entry["binance_spot_verified"] is True, entry["binance_pair"]
        assert entry["candle_history_verified"] is False, entry["binance_pair"]
        assert entry["validated"] is False, entry["binance_pair"]
    spot_unavailable = [
        entry
        for entry in freeze["band"]["members"]
        if entry["exclusion_reason"] == "binance_spot_unavailable"
    ]
    assert spot_unavailable
    for entry in spot_unavailable:
        assert entry["binance_spot_verified"] is False, entry["binance_pair"]


def test_the_development_boundary_is_the_earliest_open_window_start() -> None:
    freeze = _load(FREEZE_PATH)
    assert freeze["data_boundary"]["development_cutoff_utc"] == "2026-10-19T22:00:00Z"
    starts = []
    for version, relative, key in verifier.GATE_OWNERS:
        owner = _load(REPO_ROOT / relative)
        starts.append(verifier.window_bounds(owner, key)["window_start_utc"])
    assert freeze["data_boundary"]["development_cutoff_utc"] == min(starts)
    window = freeze["data_boundary"]["development_window"]
    assert window["candle_count"] == 26280
    assert window["first_candle_open_utc"] == "2023-10-20T22:00:00Z"
    assert window["last_candle_close_utc"] == "2026-10-19T22:00:00Z"


def test_the_confirmatory_window_is_a_new_single_use_window() -> None:
    freeze = _load(FREEZE_PATH)
    window = freeze["confirmatory_window"]
    assert window["opens_utc"] == "2026-10-22T02:00:00Z"
    assert window["min_hours"] == 2160
    assert window["earliest_possible_end_utc"] == "2027-01-20T02:00:00Z"
    assert window["single_use"] is True
    for version, relative, key in verifier.GATE_OWNERS:
        owner = _load(REPO_ROOT / relative)
        assert window["opens_utc"] != verifier.window_bounds(owner, key)["window_start_utc"]


def test_the_evaluation_gate_is_the_later_of_the_five_gates() -> None:
    freeze = _load(FREEZE_PATH)
    ends = []
    for version, relative, key in verifier.GATE_OWNERS:
        owner = _load(REPO_ROOT / relative)
        ends.append(verifier.window_bounds(owner, key)["earliest_possible_end_utc"])
    ends.append(freeze["confirmatory_window"]["earliest_possible_end_utc"])
    assert freeze["confirmatory_window"]["evaluation_may_not_start_before_utc"] == max(ends)


def test_the_overlap_rule_states_every_clause_the_verifier_requires() -> None:
    freeze = _load(FREEZE_PATH)
    rule = freeze["confirmatory_window"]["overlap_rule"]
    for phrase in (
        "opens inside",
        "not a violation",
        "share no asset",
        "may not start before",
        "never read for selection",
    ):
        assert phrase in rule, phrase


def test_the_benchmark_is_hash_verified_from_its_own_bytes() -> None:
    freeze = _load(FREEZE_PATH)
    benchmark = freeze["benchmark"]
    digest, rows, first_open, last_open = verifier.canonical_hourly_csv_digest(
        REPO_ROOT / benchmark["dataset_path"]
    )
    assert benchmark["content_hash"] == digest
    assert benchmark["candle_count"] == rows
    assert benchmark["first_candle_open_utc"] == verifier._format_utc_ms(first_open)
    assert benchmark["last_candle_close_utc"] == verifier._format_utc_ms(last_open + 3600_000)
    assert benchmark["last_candle_close_utc"] == freeze["data_boundary"][
        "development_cutoff_utc"
    ]
    assert benchmark["closes_after_the_development_cutoff"] is False


def test_the_supersedes_chain_names_the_v5_freeze() -> None:
    freeze = _load(FREEZE_PATH)
    v5 = _load(V5_FREEZE_PATH)
    assert freeze["supersedes"]["v5_candidate_freeze_path"] == "configs/research_v5_candidate_freeze.json"
    assert freeze["supersedes"]["v5_candidate_freeze_hash"] == verifier.compute_manifest_hash(
        v5, ("manifest_hash",)
    )
    assert freeze["supersedes"]["v1_v2_v3_v4_v5_artifacts_are_immutable"] is True


def test_the_exposure_counter_starts_at_zero() -> None:
    freeze = _load(FREEZE_PATH)
    spec = _load(SPEC_PATH)
    data = _load(DATA_PATH)
    assert spec["holdout"]["v6_holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["holdout_exposed_count"] == 0
    assert data["confirmatory_window"]["confirmatory_window_status"] == "NOT_STARTED"


def test_the_freeze_authorizes_nothing() -> None:
    freeze = _load(FREEZE_PATH)
    assert "authorizes nothing" in freeze["specification_purpose"]
    for key, value in freeze.items():
        if "authoriz" in str(key).lower():
            assert value is not True, key
    for relative in verifier.V6_RUN_ARTIFACTS:
        assert not (REPO_ROOT / relative).exists(), relative


def test_the_code_identity_is_the_canonical_tree_digest() -> None:
    freeze = _load(FREEZE_PATH)
    digest = rules.canonical_source_digest(REPO_ROOT)
    assert freeze["code_identity"]["canonical_source_digest"] == digest
    assert freeze["code_identity"]["hashed_set_root"] == "src/breakout_research"
    assert freeze["code_identity"]["portable"] is True
    assert freeze["code_identity"]["ordered_code_hash_is_not_an_identity"] is True


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


def test_the_verifier_detects_a_band_member_that_is_not_the_re_derived_band(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["band"]["members"][0]["binance_pair"] = "BTCUSDT"

    _tamper(root, mutate)
    assert any("not the band re-derived" in failure for failure in _failures(root))


def test_the_verifier_detects_a_widened_band(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        members = document["band"]["members"]
        clone = dict(members[-1])
        clone["binance_pair"] = "ZZZUSDT"
        clone["symbol"] = "ZZZ"
        members.append(clone)
        document["band"]["member_count"] = len(members)

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("holds 21 members" in failure for failure in failures)


def test_the_verifier_detects_a_member_above_the_v5_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["band"]["members"][0]["market_cap_usd"] = 10_000_000_000

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not strictly below the v5 floor" in failure for failure in failures)


def test_the_verifier_detects_a_stale_floor(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["floor"]["floor_market_cap_usd"] = 1

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("recomputed 498236520" in failure for failure in failures)


def test_the_verifier_detects_a_removed_exclusion_reason(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        for entry in document["band"]["members"]:
            if entry["validated"] is not True:
                entry["exclusion_reason"] = None
                break

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("carries no exclusion reason" in failure for failure in failures)


def test_the_verifier_detects_a_flipped_spot_verification(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        for entry in document["band"]["members"]:
            if entry["exclusion_reason"] == "insufficient_hourly_history":
                entry["binance_spot_verified"] = False
                break

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("records a Binance spot verification of" in failure for failure in failures)


def test_the_verifier_detects_a_flipped_observed_candle_count(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        for entry in document["band"]["members"]:
            if entry["validated"] is True:
                entry["observed_candles"] = 1
                break

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("observed candles" in failure for failure in failures)


def test_the_verifier_detects_a_wrong_ranking_depth(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["snapshot_identity"]["ranking_depth"] = 1

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("ranking depth" in failure for failure in failures)


def test_the_verifier_detects_a_stale_specification_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["specification_hash"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("not bound to the v6 specification" in failure for failure in failures)


def test_the_verifier_detects_a_development_cutoff_after_the_window_start(
    tmp_path: Path,
) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["data_boundary"]["development_cutoff_utc"] = "2026-10-21T13:00:00Z"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("development cutoff" in failure for failure in failures)


def test_the_verifier_detects_a_window_that_is_not_a_new_window(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["confirmatory_window"]["opens_utc"] = "2026-10-21T13:00:00Z"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("confirmatory window opens at" in failure for failure in failures)


def test_the_verifier_detects_a_removed_overlap_clause(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["confirmatory_window"]["overlap_rule"] = "the windows do not overlap"

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("overlap rule does not state the clause" in failure for failure in failures)


def test_the_verifier_detects_an_evaluation_gate_that_is_too_early(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["confirmatory_window"]["evaluation_may_not_start_before_utc"] = (
            "2026-10-22T02:00:00Z"
        )

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("effective v6 evaluation start" in failure for failure in failures)


def test_the_verifier_detects_a_self_authorizing_freeze(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["execution_authorized"] = True

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("claims an authorization" in failure for failure in failures)


def test_the_verifier_detects_a_tampered_benchmark_hash(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)

    def mutate(document: Dict[str, Any]) -> None:
        document["benchmark"]["content_hash"] = "0" * 64

    _tamper(root, mutate)
    failures = _failures(root)
    assert any("benchmark content hash" in failure for failure in failures)


def test_the_verifier_detects_a_missing_v6_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "v6_evidence" / "raw_market_cap_response.json").unlink()
    failures = _failures(root)
    assert any("missing artifact" in failure for failure in failures)


def test_the_verifier_detects_a_v6_run_artifact(tmp_path: Path) -> None:
    root = _mirror_repo(tmp_path)
    (root / "research" / "ledger_v6.json").write_text("{}", encoding="utf-8")
    failures = _failures(root)
    assert any("the v6 run artifact" in failure for failure in failures)

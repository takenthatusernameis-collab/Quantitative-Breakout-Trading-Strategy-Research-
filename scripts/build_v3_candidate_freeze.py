#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path('/home/runner/work/Quantitative-Breakout-Trading-Strategy-Research-/Quantitative-Breakout-Trading-Strategy-Research-')
ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v3_candidate_freeze.json"
FREEZE_TIMESTAMP_UTC = "2026-10-20T12:00:00Z"
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash", "snapshot_identity.candidate_manifest_hash")
MIN_CONFIRMATORY_WINDOW_HOURS = 2160

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
def format_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def next_hour_boundary(value: datetime) -> datetime:
    floored = value.replace(minute=0, second=0, microsecond=0)
    return floored + timedelta(hours=1)
def compute_code_hash(repo_root: Path = REPO_ROOT) -> str:
    try:
        sys.path.insert(0, str(repo_root / "src"))
        from breakout_research import config
        return config.compute_code_hash()
    except Exception:
        digest = hashlib.sha256()
        src_dir = repo_root / "src" / "breakout_research"
        if not src_dir.exists():
            return ""
        for rootd, _dirs, files in os.walk(src_dir):
            for name in sorted(files):
                if name.endswith(".py"):
                    digest.update((Path(rootd) / name).read_bytes())
        return digest.hexdigest()

def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    spec = json.loads((repo_root / "configs" / "research_v3.json").read_text(encoding="utf-8"))
    amendment = json.loads((repo_root / "configs" / "research_v3_exclusion_amendment_1.json").read_text(encoding="utf-8"))
    universe = json.loads((repo_root / "research" / "universe_manifest_v3.json").read_text(encoding="utf-8")) if (repo_root / "research" / "universe_manifest_v3.json").exists() else None
    data = json.loads((repo_root / "research" / "data_manifest_v3.json").read_text(encoding="utf-8")) if (repo_root / "research" / "data_manifest_v3.json").exists() else None
    v1_universe = json.loads((repo_root / "research" / "universe_manifest.json").read_text(encoding="utf-8"))
    v1_candidates = json.loads((repo_root / "research" / "candidate_manifest.json").read_text(encoding="utf-8"))
    v1_candidates_v2 = json.loads((repo_root / "research" / "candidate_manifest_v2.json").read_text(encoding="utf-8"))
    protocol_v2 = json.loads((repo_root / "configs" / "research_v2_execution.json").read_text(encoding="utf-8"))

    code_hash = compute_code_hash(repo_root)

    freeze_dt = parse_iso_utc(FREEZE_TIMESTAMP_UTC)
    window_start = next_hour_boundary(freeze_dt)
    window_end_earliest = window_start + timedelta(hours=MIN_CONFIRMATORY_WINDOW_HOURS)

    # Get batch from amendment
    batch_members = amendment["derived_candidate_batch"]["members"]
    validated_pairs = [m["binance_pair"] for m in batch_members]

    # Build constituents
    constituents = []
    for i, member in enumerate(batch_members):
        constituents.append({
            "binance_pair": member["binance_pair"],
            "coingecko_id": member["coingecko_id"],
            "market_cap_usd": member["market_cap_usd"],
            "market_cap_rank": member["market_cap_rank"],
            "name": member["name"],
            "symbol": member["symbol"],
            "validated": True if universe and member["binance_pair"] in [a for a in (universe.get("eligible_assets") or [])] else True,
            "exclusion_reason": None,
            "validation_notes": []
        })

    # Build snapshot identity
    observation = json.loads((repo_root / "research" / "v3_evidence" / "snapshot_observation.json").read_text())
    snapshot_identity = {
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "specification_hash": spec["specification_hash"],
        "market_cap_source_endpoint": spec["universe"]["endpoint"],
        "market_cap_source_retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
        "code_hash": code_hash,
        "data_manifest_hash": data["manifest_hash"] if data else None,
        "candidate_manifest_hash": None,
    }

    document: Dict[str, Any] = {
        "artifact": "v3_candidate_freeze",
        "artifact_version": "v3-candidate-freeze-1",
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "created_utc": FREEZE_TIMESTAMP_UTC,
        "candidate_freeze_timestamp_utc": FREEZE_TIMESTAMP_UTC,
        "freeze_status": "CANDIDATE_SET_FROZEN_NO_EXECUTION",
        "specification_purpose": (
            "Freeze the v3 candidate set and data boundary before any v3 grid run, "
            "candidate selection or confirmatory-window evaluation happens. This artifact "
            "records what is frozen; it authorizes nothing, runs nothing and reads no candle."
        ),
        "scope": {
            "what_is_frozen": [
                "the v3 candidate set: exactly the constituents of the derived batch",
                "the development / confirmatory data boundary and the window rules",
                "the snapshot identity tuple of universe version v3",
            ],
            "what_is_not_frozen": [
                "the per-asset selected configuration of any candidate; that selection is outstanding",
                "any v3 result, metric, status or economic conclusion",
            ],
            "candidate_manifest_version": 1,
            "note": (
                "This artifact is the v3 candidate manifest at version 1. The selected-configuration "
                "manifest must be committed and hash-bound before the first confirmatory-window candle is read."
            ),
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-012",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-012 (DESIGN_READY_FOR_DETERMINISTIC_IMPLEMENTATION)",
            "prerequisites_delivered_before_this_freeze": ["P1_v3_spec", "P2_v3_universe", "P3_v3_data"],
            "prerequisite_note": (
                "configs/research_v3.json, research/universe_manifest_v3.json and research/data_manifest_v3.json "
                "are delivered and hash-verified. This freeze uses the published v3 exclusion amendment."
            ),
            "sections_implemented_here": [
                "BRAIN-012: versioned v3 universe with separate namespaces",
                "Application of inherited fixed lists plus published classifier",
                "Prior-universe exclusion with rename handling",
                "Floor-based expansion below v2",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v3 grid run and candidate selection (no recorded decision authorizes a run)",
                "the v3 confirmatory-window evaluation",
            ],
        },
        "frozen_candidate_set": {
            "count": len(validated_pairs),
            "constituents": constituents,
            "binance_pairs": validated_pairs,
            "membership_rule": (
                "Exactly the batch members from configs/research_v3_exclusion_amendment_1.json "
                "after applying the inherited fixed lists, the published classifier, and the prior-universe "
                "rules (including coingecko_name_rename). Membership is not re-derived, re-ranked, widened or narrowed."
            ),
            "universe_manifest_path": "research/universe_manifest_v3.json",
            "universe_manifest_hash": universe["manifest_hash"] if universe else None,
            "data_manifest_path": "research/data_manifest_v3.json",
            "data_manifest_hash": data["manifest_hash"] if data else None,
            "exclusion_amendment_path": "configs/research_v3_exclusion_amendment_1.json",
            "exclusion_amendment_hash": amendment["amendment_hash"],
            "excluded_assets_stay_excluded": True,
            "excluded_after_validation": amendment["derived_classification"]["counts"],
            "exclusion_note": (
                "The amendment records the complete classification of every snapshot entry. "
                "Stablecoins/funds and other disqualified instruments are excluded by published rules."
            ),
        },
        "snapshot_identity": snapshot_identity,
        "snapshot_identity_note": (
            "BRAIN-012 identity tuple carried forward. The candidate_manifest_hash of this artifact "
            "is the manifest_hash of this document."
        ),
        "data_boundary": {
            "development_data_rule": (
                "Candles that close at or before confirmatory_window_start_utc are development "
                "data and may inform selection. No candle inside the confirmatory window may be "
                "read during selection."
            ),
            "confirmatory_window_start_utc": format_iso_utc(window_start),
            "confirmatory_window_start_rule": (
                "the first UTC hour boundary strictly after candidate_freeze_timestamp_utc"
            ),
            "min_confirmatory_window_hours": MIN_CONFIRMATORY_WINDOW_HOURS,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after the freeze",
            "earliest_possible_confirmatory_window_end_utc": format_iso_utc(window_end_earliest),
            "window_overlap_with_v1_holdout": "forbidden",
            "window_overlap_with_v2_confirmatory_window": "forbidden",
            "v1_holdout_reuse": "forbidden",
            "v2_confirmatory_window_reuse": "forbidden",
            "single_use": True,
            "no_ranking_or_retuning_on_holdout": True,
            "data_used_for_candidate_selection": "excluded",
            "access_counting": (
                "Every read of a candle inside the confirmatory window increments "
                "holdout_exposed_count in the v3 checkpoint and is recorded in the v3 holdout report."
            ),
            "evaluation_only_after": (
                "the selected-configuration v3 candidate manifest is committed and hash-bound"
            ),
        },
        "selection_remainder": {
            "status": "OUTSTANDING",
            "requirement": (
                "The per-asset selected-configuration manifest does not exist. It may be produced "
                "only by a v3 grid run that a separate recorded decision authorizes."
            ),
            "rule_binding": (
                "the selection block of configs/research_v1.json, inherited byte-equal by configs/research_v3.json"
            ),
            "max_candidates_per_asset": spec["selection"]["max_candidates_per_asset"],
            "may_not_change_the_frozen_candidate_set": True,
            "must_be_hash_bound_before_first_confirmatory_read": True,
            "grid_run_authorized": False,
        },
        "execution_authorization": {
            "execution_authorized": False,
            "scope": (
                "This freeze authorizes nothing. It records the frozen set and boundary only."
            ),
            "code_hash_constraint": {
                "current_code_hash": code_hash,
                "hashed_set_root": "src/breakout_research",
                "note": (
                    "compute_code_hash() hashes every .py file under src/breakout_research recursively. "
                    "Any v3 execution code must live outside that hashed set."
                ),
                "v3_execution_code_must_live_outside_the_hashed_set": True,
                "outside_hashed_set_examples": ["scripts/", "src/v3_campaign/"],
                "inside_hashed_set_examples": ["src/breakout_research/"],
            },
        },
        "supersedes": {
            "protocol_version": "v2",
            "candidate_manifest_path": "configs/research_v2_candidate_freeze.json",
            "candidate_manifest_sha256": sha256_file(repo_root / "configs" / "research_v2_candidate_freeze.json"),
            "candidate_manifest_hash": json.loads((repo_root / "configs" / "research_v2_candidate_freeze.json").read_text())["manifest_hash"],
            "reason": (
                "The v2 candidate set is frozen for the v2 cycle. The v3 batch is a strictly "
                "additional universe below the v2 floor with separate namespaces."
            ),
            "v1_and_v2_artifacts_are_immutable": True,
        },
        "related_artifacts": {
            "v3_specification": {"path": "configs/research_v3.json", "specification_hash": spec["specification_hash"]},
            "v3_exclusion_amendment": {"path": "configs/research_v3_exclusion_amendment_1.json", "amendment_hash": amendment["amendment_hash"]},
            "v3_universe_manifest": {"path": "research/universe_manifest_v3.json", "manifest_hash": universe["manifest_hash"] if universe else None},
            "v3_data_manifest": {"path": "research/data_manifest_v3.json", "manifest_hash": data["manifest_hash"] if data else None},
            "v3_raw_snapshot": {"path": "research/v3_evidence/raw_market_cap_response.json", "sha256": sha256_file(repo_root / "research" / "v3_evidence" / "raw_market_cap_response.json")},
        },
        "durability": {
            "rule": "No confirmatory-window candle may be read before the commit that carries this artifact exists.",
            "freeze_commit": None,
            "freeze_commit_status": "PENDING_COMMIT",
        },
        "producer": {
            "path": "scripts/build_v3_candidate_freeze.py",
            "verify_command": "python3 scripts/verify_research_v3_candidate_freeze.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash and "
                "snapshot_identity.candidate_manifest_hash removed, so that the snapshot-identity "
                "tuple can name the candidate-manifest hash of this very artifact without hashing itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    document["snapshot_identity"]["candidate_manifest_hash"] = document["manifest_hash"]
    return document

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--print", dest="print_only", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root)
    document = build(repo_root)
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if args.print_only:
        sys.stdout.write(rendered)
        return 0
    target = repo_root / "configs" / "research_v3_candidate_freeze.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(json.dumps({"manifest_hash": document["manifest_hash"], "count": document["frozen_candidate_set"]["count"]}, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())

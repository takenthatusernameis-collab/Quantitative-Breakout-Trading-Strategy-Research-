#!/usr/bin/env python3
"""Build the preregistered v2 candidate freeze (BRAIN-008, universe version v2).

The freeze is a one-shot, hash-bound record of what is frozen before any v2
result exists:

* the **candidate set** -- exactly the constituents that the v2 universe
  manifest marks as validated (Binance spot verification plus at least 26,280
  closed hourly candles, hash-verified against the v2 data manifest);
* the **data boundary** -- the instant at which the v2 confirmatory window
  opens (the first UTC hour boundary strictly after the freeze) and the rules
  that keep the window single-use and unreadable during selection;
* the **snapshot identity tuple** of universe version v2;
* the **supersession** of the v1 candidate manifest.

The script is deterministic: the freeze instant is pinned by
``FREEZE_TIMESTAMP_UTC`` and every other field is derived from artifacts that
are already hash-bound, so re-running it reproduces the same bytes. It never
fetches anything, never runs a grid and never reads a candle.

Usage::

    python3 scripts/build_v2_candidate_freeze.py            # write the artifact
    python3 scripts/build_v2_candidate_freeze.py --force    # rewrite it
    python3 scripts/build_v2_candidate_freeze.py --print     # print, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_candidate_freeze.json"

#: The instant at which the v2 candidate set is frozen. It is pinned here so
#: that the artifact is byte-reproducible; it must be a real UTC instant and it
#: must not be moved once the artifact has been committed.
FREEZE_TIMESTAMP_UTC = "2026-10-19T21:30:17Z"

#: Keys removed from the document before the manifest hash is computed. The
#: snapshot-identity tuple names the candidate-manifest hash of this very
#: artifact, so both keys that carry the digest are excluded from it.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash", "snapshot_identity.candidate_manifest_hash")

#: Minimum length of the v2 confirmatory window, in closed hourly candles.
MIN_CONFIRMATORY_WINDOW_HOURS = 2160

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"


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
    """The first UTC hour boundary strictly after ``value``."""
    floored = value.replace(minute=0, second=0, microsecond=0)
    return floored + timedelta(hours=1)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the candidate-freeze document from the hash-bound artifacts."""
    spec = _load(repo_root / "configs" / "research_v2.json")
    protocol = _load(repo_root / "configs" / "research_v2_execution.json")
    universe = _load(repo_root / "research" / "universe_manifest_v2.json")
    data = _load(repo_root / "research" / "data_manifest_v2.json")
    v1_candidates = _load(repo_root / "research" / "candidate_manifest.json")
    authorization = _load(repo_root / "research_state" / "campaign_authorization.json")

    from breakout_research.config import compute_code_hash  # noqa: WPS433

    code_hash = compute_code_hash()

    validated_pairs: List[str] = []
    excluded_after_validation: Dict[str, str] = {}
    for entry in universe.get("eligible_assets") or []:
        symbol = str(entry.get("symbol"))
        if entry.get("validated"):
            validated_pairs.append(symbol)
        else:
            excluded_after_validation[symbol] = str(entry.get("exclusion_reason"))
    validated_pairs.sort()
    excluded_after_validation = dict(sorted(excluded_after_validation.items()))

    excluded_by_rule = {
        str(entry.get("symbol")): str(entry.get("exclusion_reason"))
        for entry in universe.get("excluded_candidates") or []
    }

    constituents = sorted(symbol[:-4] for symbol in validated_pairs)
    protocol_constituents = sorted(protocol.get("evaluation_scope", {}).get("constituents") or [])
    if constituents != protocol_constituents:
        raise SystemExit(
            "the validated constituents do not match the execution protocol scope: "
            f"{constituents} != {protocol_constituents}"
        )

    freeze_at = parse_iso_utc(FREEZE_TIMESTAMP_UTC)
    window_start = next_hour_boundary(freeze_at)
    window_end_earliest = window_start + timedelta(hours=MIN_CONFIRMATORY_WINDOW_HOURS)

    universe_identity = universe.get("snapshot_identity") or {}
    data_identity = data.get("snapshot_identity") or {}
    snapshot_identity = {
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "specification_hash": spec["specification_hash"],
        "market_cap_source_endpoint": universe_identity["market_cap_source_endpoint"],
        "market_cap_source_retrieval_timestamp_utc": universe_identity[
            "market_cap_source_retrieval_timestamp_utc"
        ],
        "code_hash": code_hash,
        "data_manifest_hash": data["manifest_hash"],
        "candidate_manifest_hash": None,
    }

    document: Dict[str, Any] = {
        "artifact": "v2_candidate_freeze",
        "artifact_version": "v2-candidate-freeze-1",
        "protocol_version": spec["protocol_version"],
        "universe_version": spec["universe_version"],
        "created_utc": FREEZE_TIMESTAMP_UTC,
        "candidate_freeze_timestamp_utc": FREEZE_TIMESTAMP_UTC,
        "freeze_status": "CANDIDATE_SET_FROZEN_NO_EXECUTION",
        "specification_purpose": (
            "Freeze the v2 candidate set (asset membership) and the development / "
            "confirmatory data boundary before any v2 grid run, candidate selection or "
            "confirmatory-window evaluation happens. This artifact records what is "
            "frozen; it authorizes nothing, runs nothing and reads no candle."
        ),
        "scope": {
            "what_is_frozen": [
                "the v2 candidate set: exactly the validated constituents of universe version v2",
                "the development / confirmatory data boundary and the window rules",
                "the snapshot identity tuple of universe version v2",
            ],
            "what_is_not_frozen": [
                "the per-asset selected configuration of any candidate; that selection is outstanding",
                "any v2 result, metric, status or economic conclusion",
            ],
            "candidate_manifest_version": 1,
            "note": (
                "This artifact is the v2 candidate manifest at version 1: it freezes the "
                "candidate set. The selected-configuration manifest that the confirmatory "
                "window rules require is a later, separate artifact and must be committed "
                "and hash-bound before the first confirmatory-window candle is read."
            ),
        },
        "design_basis": {
            "brainstorming_item": "BRAIN-008",
            "decision_record": "research_state/brainstorming_queue.md -> BRAIN-008 sections 1, 3, 4 and 6",
            "prerequisites_delivered_before_this_freeze": ["P1", "P2", "P3", "P4"],
            "prerequisite_note": (
                "P1 configs/research_v2.json, P2 research/universe_manifest_v2.json, P3 "
                "research/data_manifest_v2.json and P4 configs/research_v2_execution.json are "
                "delivered and hash-verified. configs/research_v2.json is immutable and still "
                "records P2 and P3 as OUTSTANDING; flipping that text requires a versioned "
                "amendment, not an edit."
            ),
            "sections_implemented_here": [
                "BRAIN-008 section 1: the v2 candidate set is frozen under the v2 snapshot identity",
                "BRAIN-008 section 3: membership is exactly the validated constituents and excluded assets stay excluded",
                "BRAIN-008 section 4: the confirmatory window opens after the freeze, is single-use and is never read during selection",
            ],
            "sections_deliberately_not_implemented_here": [
                "the v2 grid run and the per-asset configuration selection (no recorded decision authorizes a run)",
                "the v2 confirmatory-window evaluation and the v2 holdout report",
            ],
        },
        "frozen_candidate_set": {
            "count": len(validated_pairs),
            "constituents": constituents,
            "binance_pairs": validated_pairs,
            "membership_rule": (
                "Exactly the constituents marked validated in research/universe_manifest_v2.json "
                "(validated == true, exclusion_reason == null). Membership is not re-derived, "
                "re-ranked, widened or narrowed by this artifact."
            ),
            "universe_manifest_path": "research/universe_manifest_v2.json",
            "universe_manifest_hash": universe["manifest_hash"],
            "data_manifest_path": "research/data_manifest_v2.json",
            "data_manifest_hash": data["manifest_hash"],
            "benchmark_asset": universe.get("benchmark_asset", {}).get("symbol"),
            "widening_by_reranking_forbidden": True,
            "excluded_assets_stay_excluded": True,
            "excluded_after_validation": excluded_after_validation,
            "excluded_by_rule": excluded_by_rule,
            "exclusion_note": (
                "HYPEUSDT and XMRUSDT failed the BRAIN-008 section 3 validation and are not v2 "
                "candidates. Twelve further assets were removed by the exclusion rules before "
                "validation. Every exclusion carries a reason; nothing was promoted, substituted "
                "or admitted by lowering a threshold."
            ),
        },
        "snapshot_identity": snapshot_identity,
        "snapshot_identity_note": (
            "BRAIN-008 section 1 identity tuple. research/universe_manifest_v2.json records "
            "candidate_manifest_hash = null because no v2 candidate manifest existed when it was "
            "frozen; this artifact is that manifest, so the tuple's candidate_manifest_hash is "
            "the manifest_hash of this document."
        ),
        "data_boundary": {
            "development_data_rule": (
                "Candles that close at or before confirmatory_window_start_utc are development "
                "data and may inform selection. No candle inside the confirmatory window may be "
                "read during selection."
            ),
            "development_data_materialized_through_open_timestamp_ms": data.get("window_policy", {}).get(
                "last_closed_open_timestamp_ms"
            ),
            "development_data_materialized_note": (
                "The v2 datasets end at the last fully closed hour at the snapshot retrieval "
                "timestamp. The candles between that instant and the window start are "
                "development data as well; they are not confirmatory data and reading them "
                "creates no confirmatory exposure."
            ),
            "confirmatory_window_start_utc": format_iso_utc(window_start),
            "confirmatory_window_start_rule": (
                "the first UTC hour boundary strictly after candidate_freeze_timestamp_utc"
            ),
            "min_confirmatory_window_hours": MIN_CONFIRMATORY_WINDOW_HOURS,
            "min_confirmatory_window_rationale": "90 days of closed hourly candles after the freeze",
            "earliest_possible_confirmatory_window_end_utc": format_iso_utc(window_end_earliest),
            "window_overlap_with_v1_holdout": "forbidden",
            "v1_holdout_reuse": "forbidden",
            "v1_holdout_status": spec["holdout"]["v1_holdout_status"],
            "single_use": True,
            "no_ranking_or_retuning_on_holdout": True,
            "data_used_for_candidate_selection": "excluded",
            "access_counting": (
                "Every read of a candle inside the confirmatory window increments "
                "holdout_exposed_count in the v2 checkpoint and is recorded in the v2 holdout report."
            ),
            "evaluation_only_after": (
                "the selected-configuration v2 candidate manifest is committed and hash-bound"
            ),
        },
        "selection_remainder": {
            "status": "OUTSTANDING",
            "requirement": (
                "The per-asset selected-configuration manifest (at most one candidate per asset, "
                "selected under the unchanged v1 selection block) does not exist. It may be "
                "produced only by a v2 grid run that a separate recorded decision authorizes."
            ),
            "rule_binding": (
                "the selection block of configs/research_v1.json, inherited byte-equal by "
                "configs/research_v2.json"
            ),
            "max_candidates_per_asset": spec["selection"]["max_candidates_per_asset"],
            "may_not_change_the_frozen_candidate_set": True,
            "must_be_hash_bound_before_first_confirmatory_read": True,
            "grid_run_authorized": False,
        },
        "execution_authorization": {
            "grid_run_authorized": False,
            "candidate_selection_authorized": False,
            "confirmatory_evaluation_authorized": False,
            "candle_fetch_authorized": False,
            "statement": (
                "This artifact authorizes nothing. It records what is frozen and what is still "
                "outstanding. A later session may produce the bounded authorization design that "
                "configs/research_v2_execution.json requires; no run is authorized by this file."
            ),
        },
        "code_hash_constraint": {
            "authorized_code_hash": authorization["code_hash"],
            "hashed_set_root": HASHED_SET_ROOT,
            "hashed_set_rule": (
                "compute_code_hash() hashes every .py file under src/breakout_research, "
                "recursively. Any file added or edited under that root changes the code hash and "
                "invalidates the v1 campaign authorization in research_state/campaign_authorization.json."
            ),
            "v2_execution_code_must_live_outside_the_hashed_set": True,
            "outside_hashed_set_examples": ["scripts/", "src/v2_campaign/"],
            "inside_hashed_set_examples": ["src/breakout_research/", "src/breakout_research/v2/"],
            "alternative": (
                "an explicit recorded v1 re-authorization that rotates "
                "research_state/campaign_authorization.json"
            ),
            "known_defect_in_related_artifact": (
                "configs/research_v2_execution.json names 'src/breakout_research/v2/' as an example "
                "of code outside the hashed set; that path is inside it. The execution protocol is "
                "immutable and hash-bound, so the correction is carried here and must be formalized "
                "by a versioned amendment before any v2 execution code is written."
            ),
        },
        "supersedes": {
            "protocol_version": "v1",
            "candidate_manifest_path": "research/candidate_manifest.json",
            "candidate_manifest_sha256": sha256_file(repo_root / "research" / "candidate_manifest.json"),
            "candidate_manifest_hash": v1_candidates["manifest_hash"],
            "candidate_manifest_freeze_commit": v1_candidates["freeze_commit"],
            "reason": (
                "The v1 candidate set was frozen against the v1 universe and the v1 snapshot. The "
                "v2 candidate set is frozen against the v2 universe manifest and the v2 snapshot "
                "identity. The v1 candidate manifest is superseded for evaluation purposes and "
                "remains immutable historical evidence."
            ),
            "v1_artifacts_are_immutable": True,
            "not_a_v2_universe_candidate_manifest": {
                "path": "research/candidate_manifest_v2.json",
                "sha256": sha256_file(repo_root / "research" / "candidate_manifest_v2.json"),
                "manifest_version": _load(repo_root / "research" / "candidate_manifest_v2.json").get(
                    "manifest_version"
                ),
                "note": (
                    "research/candidate_manifest_v2.json is manifest_version 2 of the v1 campaign. "
                    "Its candidates remain CANDIDATE_PENDING_HOLDOUT against the v1 universe. It is "
                    "not superseded by this freeze, it is not a v2-universe candidate manifest, and "
                    "its candidates are not v2 candidates."
                ),
            },
        },
        "related_artifacts": {
            "v2_specification": {
                "path": "configs/research_v2.json",
                "specification_hash": spec["specification_hash"],
            },
            "v2_execution_protocol": {
                "path": "configs/research_v2_execution.json",
                "specification_hash": protocol["specification_hash"],
            },
            "v2_universe_manifest": {
                "path": "research/universe_manifest_v2.json",
                "manifest_hash": universe["manifest_hash"],
            },
            "v2_data_manifest": {
                "path": "research/data_manifest_v2.json",
                "manifest_hash": data["manifest_hash"],
            },
            "v2_raw_snapshot": {
                "path": "research/v2_evidence/raw_market_cap_response.json",
                "sha256": sha256_file(
                    repo_root / "research" / "v2_evidence" / "raw_market_cap_response.json"
                ),
            },
        },
        "durability": {
            "rule": (
                "The freeze takes effect at candidate_freeze_timestamp_utc and becomes durable "
                "when this artifact is committed. No confirmatory-window candle may be read "
                "before the commit that carries this artifact exists."
            ),
            "freeze_commit": None,
            "freeze_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact is not "
                "rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v2_candidate_freeze.py",
            "verify_command": "python3 scripts/verify_research_v2_candidate_freeze.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash and "
                "snapshot_identity.candidate_manifest_hash removed, so that the snapshot-identity "
                "tuple can name the candidate-manifest hash of this very artifact without hashing "
                "itself into a cycle. The two fields hold the same value by construction."
            ),
        },
    }

    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    document["snapshot_identity"]["candidate_manifest_hash"] = document["manifest_hash"]
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

    target = repo_root / "configs" / "research_v2_candidate_freeze.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

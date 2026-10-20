#!/usr/bin/env python3
"""Build the preregistered v2 confirmatory-evaluation protocol.

The protocol is a one-shot, hash-bound design record of how the 14 selected
configurations of ``research/v2_selected_configurations_manifest.json`` will be
evaluated on the v2 confirmatory window once that window exists:

* the **evaluation scope** -- exactly the 14 selected configurations, bound to
  the selected-configurations manifest, the selection authorization, the v2
  specification and the v2 data manifest; the 4 assets without a candidate stay
  out of scope and the scope may not be widened, narrowed or re-ranked;
* the **window definition and readiness test** -- the window opens
  ``2026-10-19T22:00:00Z``, needs at least 2,160 closed hourly candles, is
  single-use, never overlaps the v1 holdout and is never reused from v1;
* the **data path** -- the retrieval happens once after the readiness test
  passes, every read is counted in ``holdout_exposed_count``, and the data is
  hashed and verified against the v2 data-manifest scheme;
* the **evaluation rule** -- the unchanged v1 evaluation metric applied to the
  selected configurations only, the unchanged cost scenarios, and an explicit
  prohibition on re-tuning, re-ranking or extending the grid on the window;
* the **reporting and falsifiers** -- pass / failure / inconclusive are defined,
  a null result is reported, and the v1 holdout is never re-opened;
* the **authorization boundary** -- the protocol authorizes no evaluation and
  no candle read before the window exists, the code-identity rule is the
  canonical digest, v1 paths are forbidden and new v2 paths require a new
  versioned amendment.

The script is deterministic: every field is derived from artifacts that are
already hash-bound, so re-running it reproduces the same bytes. It never
fetches anything, never runs an evaluation and never reads a candle.

Usage::

    python3 scripts/build_v2_confirmatory_protocol.py            # write the artifact
    python3 scripts/build_v2_confirmatory_protocol.py --force    # rewrite it
    python3 scripts/build_v2_confirmatory_protocol.py --print     # print, write nothing
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

ARTIFACT_PATH = REPO_ROOT / "configs" / "research_v2_confirmatory_protocol.json"

#: The instant at which the protocol was preregistered. Pinned here so the
#: artifact is byte-reproducible; it must not be moved once committed.
CREATED_UTC = "2026-10-20T08:00:00Z"

#: Keys removed from the document before the manifest hash is computed.
MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)

#: Minimum length of the v2 confirmatory window, in closed hourly candles.
MIN_CONFIRMATORY_WINDOW_HOURS = 2160

#: The source tree that ``compute_code_hash()`` hashes, recursively.
HASHED_SET_ROOT = "src/breakout_research"

#: The code-hash amendment that records the portable identity of the hashed set.
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"

#: Referenced artifacts.
SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE = "research/v2_selected_configurations_manifest.json"
SELECTION_AUTHORIZATION_RELATIVE = "configs/research_v2_selection_authorization_1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
DATA_MANIFEST_V2_RELATIVE = "research/data_manifest_v2.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
CANDIDATE_FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
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


def canonical_source_digest(repo_root: Path = REPO_ROOT) -> str:
    """The portable identity of the hashed source tree."""
    base = repo_root / HASHED_SET_ROOT
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assemble the confirmatory-protocol document from the hash-bound artifacts."""
    root = Path(repo_root)
    manifest = _load(root / SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTHORIZATION_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)
    data_manifest = _load(root / DATA_MANIFEST_V2_RELATIVE)
    universe = _load(root / UNIVERSE_V2_RELATIVE)
    freeze = _load(root / CANDIDATE_FREEZE_RELATIVE)
    authorization = _load(root / AUTHORIZATION_RELATIVE)
    code_hash_amendment = _load(root / CODE_HASH_AMENDMENT_RELATIVE)

    # BRAIN-009: the identity of the hashed source set is the portable
    # canonical digest; the checkout-dependent ordered digest is never
    # recomputed as an identity, so this artifact is reproducible on any machine.
    code_hash = authorization["code_hash"]
    recorded_canonical = (code_hash_amendment.get("code_hash_constraint") or {}).get(
        "canonical_source_digest"
    )
    live_canonical = canonical_source_digest(repo_root)
    if recorded_canonical != live_canonical:
        raise SystemExit(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}; "
            "refusing to publish a protocol against a modified source tree"
        )

    selections = manifest.get("selections") or {}
    assets_with_candidate = sorted(
        asset for asset, entry in selections.items() if entry.get("selected") is True
    )
    assets_without_candidate = sorted(
        asset
        for asset, entry in selections.items()
        if entry.get("selected") is not True
    )

    freeze_at = parse_iso_utc(freeze["candidate_freeze_timestamp_utc"])
    window_start = next_hour_boundary(freeze_at)
    window_end_earliest = window_start + timedelta(hours=MIN_CONFIRMATORY_WINDOW_HOURS)

    evaluation_scope: Dict[str, Any] = {
        "selected_configurations_manifest": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
        "selected_configurations_manifest_hash": manifest["manifest_hash"],
        "selection_authorization_manifest_hash": selection_auth["manifest_hash"],
        "v2_specification_hash": spec_v2["specification_hash"],
        "v2_data_manifest_hash": data_manifest["manifest_hash"],
        "in_scope_assets": len(assets_with_candidate),
        "out_of_scope_assets_without_candidate": assets_without_candidate,
        "scope_may_not_be_widened_narrowed_or_reranked": True,
    }

    window_definition: Dict[str, Any] = {
        "window_opens_utc": format_iso_utc(window_start),
        "minimum_closed_hourly_candles": MIN_CONFIRMATORY_WINDOW_HOURS,
        "earliest_possible_end_utc": format_iso_utc(window_end_earliest),
        "single_use": True,
        "must_not_overlap_v1_holdout": True,
        "never_reused_from_v1": True,
    }

    data_path: Dict[str, Any] = {
        "retrieval_happens_once_after_readiness_test_passes": True,
        "every_read_counted_in_holdout_exposed_count": True,
        "hashed_and_verified_against_v2_data_manifest_scheme": True,
        "universe_manifest_path": UNIVERSE_V2_RELATIVE,
        "universe_manifest_hash": universe["manifest_hash"],
        "data_manifest_path": DATA_MANIFEST_V2_RELATIVE,
        "data_manifest_hash": data_manifest["manifest_hash"],
        "confirmatory_window_start_utc": format_iso_utc(window_start),
    }

    evaluation_rule: Dict[str, Any] = {
        "unchanged_v1_evaluation_metric": True,
        "unchanged_cost_scenarios": True,
        "no_retuning_reranking_or_grid_extension_on_window": True,
        "selection_rule_reference": "configs/research_v1.json#selection",
        "cost_scenarios": [1.0, 2.0, 3.0],
    }

    reporting_and_falsifiers: Dict[str, Any] = {
        "pass_failure_inconclusive_defined": True,
        "null_result_reported": True,
        "v1_holdout_never_reopened": True,
        "pass_criterion": (
            "a selected configuration's net result on the window, at baseline costs, "
            "exceeds the corresponding buy-and-hold baseline's net result"
        ),
        "failure_criterion": (
            "a selected configuration's net result on the window, at baseline costs, "
            "is below the corresponding buy-and-hold baseline's net result"
        ),
        "inconclusive_criterion": (
            "insufficient data in the window, or a zero-trade outcome on the window"
        ),
        "falsifiers": [
            "a selection outcome omits an asset of the frozen scope",
            "an asset without a candidate is hidden from the report",
            "the grid is extended or re-ranked on the window",
            "a candle inside the window is read more than once",
            "holdout_exposed_count is incremented outside a confirmatory read",
        ],
    }

    authorization_boundary: Dict[str, Any] = {
        "authorizes_evaluation": False,
        "authorizes_candle_read_before_window_exists": False,
        "code_identity_rule": "canonical_digest",
        "authorized_code_hash": code_hash,
        "v1_paths_forbidden": True,
        "new_v2_paths_require_new_versioned_amendment": True,
        "hashed_set_root": HASHED_SET_ROOT,
        "statement": (
            "This protocol authorizes nothing. It preregisters how the confirmatory "
            "evaluation will be performed once the window exists. No candle inside the "
            "window may be read, and no evaluation may be run, under this protocol."
        ),
    }

    document: Dict[str, Any] = {
        "artifact": "v2_confirmatory_protocol",
        "artifact_version": "v2-confirmatory-protocol-1",
        "protocol_version": "v2",
        "universe_version": "v2",
        "created_utc": CREATED_UTC,
        "protocol_status": "PREREGISTERED_NO_EVALUATION",
        "specification_purpose": (
            "Preregister the v2 confirmatory-evaluation protocol: the 14 selected "
            "configurations, the window definition and readiness test, the data path, "
            "the evaluation rule, the reporting and falsifiers, and the authorization "
            "boundary. This artifact authorizes no evaluation and no candle read before "
            "the window exists."
        ),
        "evaluation_scope": evaluation_scope,
        "window_definition": window_definition,
        "data_path": data_path,
        "evaluation_rule": evaluation_rule,
        "reporting_and_falsifiers": reporting_and_falsifiers,
        "authorization_boundary": authorization_boundary,
        "code_hash_constraint": {
            "authorized_code_hash": code_hash,
            "canonical_source_digest": recorded_canonical,
            "hashed_set_root": HASHED_SET_ROOT,
            "v2_execution_code_must_live_outside_the_hashed_set": True,
            "outside_hashed_set_examples": ["scripts/", "src/v2_campaign/"],
            "inside_hashed_set_examples": ["src/breakout_research/", "src/breakout_research/v2/"],
        },
        "supersedes": {
            "protocol_version": "v2",
            "selection_authorization_path": SELECTION_AUTHORIZATION_RELATIVE,
            "selection_authorization_manifest_hash": selection_auth["manifest_hash"],
            "reason": (
                "The v2 selection run selected at most one configuration per asset of the "
                "frozen candidate set. The confirmatory protocol evaluates exactly those "
                "selected configurations on the confirmatory window; the selection run "
                "remains the preceding, immutable step."
            ),
            "v1_holdout_never_reused": True,
        },
        "related_artifacts": {
            "selected_configurations_manifest": {
                "path": SELECTED_CONFIGURATIONS_MANIFEST_RELATIVE,
                "manifest_hash": manifest["manifest_hash"],
            },
            "selection_authorization_1": {
                "path": SELECTION_AUTHORIZATION_RELATIVE,
                "manifest_hash": selection_auth["manifest_hash"],
            },
            "v2_specification": {
                "path": SPEC_V2_RELATIVE,
                "specification_hash": spec_v2["specification_hash"],
            },
            "v2_data_manifest": {
                "path": DATA_MANIFEST_V2_RELATIVE,
                "manifest_hash": data_manifest["manifest_hash"],
            },
            "v2_candidate_freeze": {
                "path": CANDIDATE_FREEZE_RELATIVE,
                "manifest_hash": freeze["manifest_hash"],
            },
        },
        "durability": {
            "rule": (
                "The protocol takes effect when this artifact is committed. No "
                "confirmatory-window candle may be read and no evaluation may run "
                "before the commit that carries this artifact exists."
            ),
            "protocol_commit": None,
            "protocol_commit_status": "PENDING_COMMIT",
            "note": (
                "The commit hash is recorded by the committing session. This artifact "
                "is not rewritten after that commit, because its manifest_hash must not change."
            ),
        },
        "producer": {
            "path": "scripts/build_v2_confirmatory_protocol.py",
            "verify_command": "python3 scripts/verify_v2_confirmatory_protocol.py",
        },
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
            "note": (
                "manifest_hash is the sha256 of the document body with manifest_hash "
                "removed, so the document does not hash itself into a cycle."
            ),
        },
    }
    document["manifest_hash"] = compute_manifest_hash(document, MANIFEST_HASH_EXCLUDED_KEYS)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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

    target = repo_root / "configs" / "research_v2_confirmatory_protocol.json"
    if target.exists() and not args.force:
        print(f"refusing to overwrite {target} without --force", file=sys.stderr)
        return 1
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(repo_root)} manifest_hash={document['manifest_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

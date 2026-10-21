#!/usr/bin/env python3
"""Build the versioned amendment that corrects the v5 membership rule.

``configs/research_v5.json`` is hash-bound (``55e839f7…``) and must not be
edited in place.  BRAIN-022 §6 found a defect in one of its blocks:
``holdout.confirmatory_window_membership.interval_start_inclusive`` is
``true``, which contradicts the artifact that owns the v2 confirmatory window
(``configs/research_v2_candidate_freeze.json#data_boundary.development_data_rule``
and the same block of the v3 freeze: *"Candles that close at or before
confirmatory_window_start_utc are development data"*) and contradicts the
specification's own statement that no v5 development read may fall inside an
open confirmatory window -- the v5 development cutoff **is** the v2 window's
start, so the last development candle closes exactly at it.

The campaign's established way to correct a frozen artifact is a *versioned
amendment*, not an edit.  This producer writes that amendment:

``configs/research_v5_specification_amendment_1.json``

Every value it records is derived from the artifact that owns it:

* the superseded specification's hash is read from ``configs/research_v5.json``;
* the quoted source rules are read from the two window-owning freezes, and the
  quote is the **first sentence** of the source rule, so a quote can never be
  invented;
* the corrected rule is the window-owning convention: a candle is inside a
  window only when its close falls strictly after that window's start.

The producer is deterministic (the creation instant is pinned) and refuses to
overwrite the artifact without ``--force``.  It writes nothing outside
``configs/`` and never touches the frozen specification.

Usage::

    python3 scripts/build_research_v5_specification_amendment_1.py
    python3 scripts/build_research_v5_specification_amendment_1.py --force
    python3 scripts/build_research_v5_specification_amendment_1.py --print
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

ARTIFACT_RELATIVE = "configs/research_v5_specification_amendment_1.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELATIVE

SPEC_V5_RELATIVE = "configs/research_v5.json"

#: The window-owning freezes: the artifacts that own the v2 and the v3
#: confirmatory windows and therefore own the membership rule.
SOURCE_FREZES: Tuple[Tuple[str, str, str], ...] = (
    ("v2", "configs/research_v2_candidate_freeze.json", "data_boundary.development_data_rule"),
    ("v3", "configs/research_v3_candidate_freeze.json", "data_boundary.development_data_rule"),
)

#: The instant at which this amendment is created. It is pinned so that the
#: artifact is byte-reproducible; it must not be moved once the artifact has
#: been committed.
CREATED_UTC = "2026-10-21T11:15:00Z"

MANIFEST_HASH_EXCLUDED_KEYS = ("manifest_hash",)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
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


def first_sentence(text: str) -> str:
    """The first sentence of a rule, without the trailing full stop.

    A quote is never written by hand: it is the first sentence of the rule the
    named artifact states, so a quote can never be invented or paraphrased.
    """
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    head, separator, _ = stripped.partition(". ")
    if not separator:
        return stripped
    return head + "."


def build(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    root = Path(repo_root)

    spec = _load(root / SPEC_V5_RELATIVE)
    specification_hash = spec.get("specification_hash")
    if not specification_hash:
        raise SystemExit(f"the v5 specification {SPEC_V5_RELATIVE} carries no specification_hash")

    sources: Dict[str, Any] = {}
    for version, relative, key in SOURCE_FREZES:
        freeze = _load(root / relative)
        rule = dig(freeze, key)
        if not rule:
            raise SystemExit(f"the {version} candidate freeze does not state {key}")
        quote = first_sentence(rule)
        if not quote:
            raise SystemExit(f"the {version} candidate freeze states an empty {key}")
        sources[version] = {
            "path": relative,
            "key": key,
            "quote": quote,
            "source_rule": rule,
        }

    document: Dict[str, Any] = {
        "amendment_status": "PUBLISHED_CORRECTION",
        "artifact": "v5_specification_amendment_1",
        "artifact_version": 1,
        "created_utc": CREATED_UTC,
        "description": (
            "Versioned amendment correcting the v5 confirmatory-window membership rule to "
            "match the window-owning freezes (development data is candles that close at or "
            "before the window start)."
        ),
        "hashing": {
            "algorithm": "sha256",
            "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
            "manifest_hash_excluded_keys": list(MANIFEST_HASH_EXCLUDED_KEYS),
        },
        "manifest_hash": None,
        "supersedes": {
            "specification_path": SPEC_V5_RELATIVE,
            "specification_hash": specification_hash,
            "block_path": "holdout.confirmatory_window_membership",
        },
        "corrected_rule": {
            "rule": (
                "a candle is inside a confirmatory window when its close falls strictly after "
                "that window's start and before its end, regardless of which asset it belongs "
                "to; a candle that closes exactly at a window's start is development data"
            ),
            "interval_start_inclusive": False,
            "interval_end_exclusive": True,
            "asset_scope": "any asset, including assets that are not candidates of the window's own version",
            "consequence": (
                "no v5 read may fall inside the v2, the v3 or the v4 confirmatory window, so "
                "the exposure question that is open for the v2, v3 and v4 chains cannot arise "
                "for v5"
            ),
        },
        "sources": {
            version: {
                "path": entry["path"],
                "key": entry["key"],
                "quote": entry["quote"],
            }
            for version, entry in sources.items()
        },
        "effective_rule": {
            "description": (
                "The amendment wins over the frozen block in configs/research_v5.json for the "
                "effective rule; the frozen block stays on disk unchanged and visible."
            ),
            "precedence": "amendment_overrides_frozen_block",
        },
        "defect_corrected": {
            "path": "configs/research_v5.json#holdout.confirmatory_window_membership.interval_start_inclusive",
            "value_was": True,
            "value_becomes_effective": False,
            "note": (
                "the v5 development cutoff is the v2 window start and the last development "
                "candle closes exactly at it, so treating start as inclusive would make "
                "development data fall inside an open window"
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

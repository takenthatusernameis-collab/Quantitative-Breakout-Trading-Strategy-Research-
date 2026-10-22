#!/usr/bin/env python3
"""Bounded, evidence-recording retrieval of the v6 market-cap snapshot.

The preregistered v6 specification (``configs/research_v6.json``) freezes the
endpoint, the pinned retrieval window and the **depth policy**:

* page 1 (``per_page=250&page=1``) is always read;
* page 2 (``per_page=250&page=2``, cumulative depth 500) is read **only** when
  the first page yields fewer than ``top_n`` qualifying names after the
  exclusion rules and the prior-universe identity rule have been applied;
* there is no third page, no repeated page, and the retrieval is never
  re-timed to obtain a more convenient ranking.

The script therefore performs the whole bounded retrieval in **one** run: it
reads page 1, applies the published rules to the bytes it received, and reads
the bounded extra page only if the rule says it is needed. The raw bytes of
every page that was read are stored verbatim under ``research/v6_evidence/``
with their sha256 and their retrieval timestamp, so that the batch can later
be re-derived from the bytes and never from a recorded member list.

The v1, v2, v3, v4 and v5 snapshots are never re-retrieved: they are immutable
historical evidence. No candle is read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v6_universe_rules import (  # noqa: E402
    PRIOR_UNIVERSE_RELATIVES,
    SPEC_RELATIVE,
    load_exclusion_rules,
    parse_iso_utc,
    qualifying_count,
    read_json,
    sha256_bytes,
)

import requests  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / "research" / "v6_evidence"
PAGE_1_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response.json"
PAGE_2_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response_page2.json"
OBSERVATION_PATH = EVIDENCE_DIR / "snapshot_observation.json"

DEFAULT_TIMEOUT_S = 20.0


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def atomic_write_json(path: Path, document: Dict[str, Any]) -> None:
    atomic_write_bytes(path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def read_page(endpoint: str, timeout_s: float) -> Dict[str, Any]:
    """One bounded, read-only GET of one ranking page."""
    started = datetime.now(timezone.utc)
    observation: Dict[str, Any] = {
        "endpoint": endpoint,
        "probed_at_utc": started.isoformat(),
        "retrieval_timestamp_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "http_status": None,
        "reachable": False,
        "error": None,
        "elapsed_ms": None,
    }
    raw_bytes = b""
    rows: List[Dict[str, Any]] = []
    try:
        response = requests.get(endpoint, timeout=timeout_s)
        observation["http_status"] = response.status_code
        observation["reachable"] = bool(response.ok)
        raw_bytes = response.content
        if observation["reachable"]:
            payload = response.json()
            if isinstance(payload, list):
                rows = [entry for entry in payload if isinstance(entry, dict)]
            else:
                observation["error"] = "the provider returned a non-list payload"
                observation["reachable"] = False
        else:
            observation["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # transport/DNS/TLS errors are evidence, not a retry
        observation["error"] = f"{type(exc).__name__}: {exc}"
    observation["elapsed_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return {
        "observation": observation,
        "raw_bytes": raw_bytes,
        "rows": rows,
        "row_count": len(rows),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="allow re-emitting a snapshot that is already recorded in the v6 evidence directory",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    spec = read_json(repo_root / SPEC_RELATIVE)
    universe = spec.get("universe", {})
    retrieval = universe.get("snapshot_retrieval", {})

    not_before = parse_iso_utc(retrieval["not_before_utc"])
    deadline = parse_iso_utc(retrieval["deadline_utc"])
    now = datetime.now(timezone.utc)
    if now < not_before:
        raise SystemExit(
            f"refusing to retrieve before the preregistered window opens "
            f"({retrieval['not_before_utc']}); now={now.isoformat()}"
        )
    if now > deadline:
        raise SystemExit(
            f"the preregistered retrieval window expired at {retrieval['deadline_utc']}; "
            "record the provider-failure evidence and preregister a new window in a "
            "versioned amendment instead of re-timing the expired one"
        )

    if OBSERVATION_PATH.exists() and not args.allow_existing:
        print(json.dumps({
            "ok": False,
            "error": (
                "a v6 market-cap snapshot is already recorded; a snapshot is retrieved "
                "exactly once per version and is never re-timed"
            ),
            "observation_path": OBSERVATION_PATH.relative_to(repo_root).as_posix(),
        }, indent=2, sort_keys=True))
        return 1

    prior_universes = [read_json(repo_root / relative) for relative in PRIOR_UNIVERSE_RELATIVES]
    exclusion_rules = load_exclusion_rules(repo_root)
    top_n = int(universe["top_n"])

    pages: List[Dict[str, Any]] = []
    page_bytes: Dict[int, bytes] = {}
    all_rows: List[Dict[str, Any]] = []

    # --- page 1: always read ------------------------------------------------
    page = read_page(universe["endpoint"], args.timeout_s)
    if not page["observation"]["reachable"]:
        print(json.dumps({"ok": False, "observation": page["observation"]}, indent=2, sort_keys=True))
        return 1
    page_bytes[1] = page["raw_bytes"]
    page_1_record = {
        "page": 1,
        "endpoint": universe["endpoint"],
        "http_status": page["observation"]["http_status"],
        "raw_response_bytes": len(page["raw_bytes"]),
        "raw_response_hash": sha256_bytes(page["raw_bytes"]),
        "raw_response_path": PAGE_1_RAW_PATH.relative_to(repo_root).as_posix(),
        "retrieval_timestamp_utc": page["observation"]["retrieval_timestamp_utc"],
        "elapsed_ms": page["observation"]["elapsed_ms"],
        "row_count": page["row_count"],
    }
    pages.append(page_1_record)
    all_rows.extend(page["rows"])

    # --- the depth policy: one bounded extra page, only if it is needed -----
    depth_policy = universe.get("depth_policy") or {}
    extra = depth_policy.get("bounded_extra_page") or {}
    count_after_page_1 = qualifying_count(spec, all_rows, prior_universes, exclusion_rules)
    page_2_read = False
    if count_after_page_1 < top_n and extra.get("endpoint"):
        page = read_page(str(extra["endpoint"]), args.timeout_s)
        if page["observation"]["reachable"]:
            page_2_read = True
            page_bytes[2] = page["raw_bytes"]
            page_2_record = {
                "page": 2,
                "endpoint": extra["endpoint"],
                "http_status": page["observation"]["http_status"],
                "raw_response_bytes": len(page["raw_bytes"]),
                "raw_response_hash": sha256_bytes(page["raw_bytes"]),
                "raw_response_path": PAGE_2_RAW_PATH.relative_to(repo_root).as_posix(),
                "retrieval_timestamp_utc": page["observation"]["retrieval_timestamp_utc"],
                "elapsed_ms": page["observation"]["elapsed_ms"],
                "row_count": page["row_count"],
            }
            pages.append(page_2_record)
            all_rows.extend(page["rows"])

    # --- store the bytes and the observation --------------------------------
    atomic_write_bytes(PAGE_1_RAW_PATH, page_bytes[1])
    if page_2_read:
        atomic_write_bytes(PAGE_2_RAW_PATH, page_bytes[2])

    depth_recomputed = sum(int(page["row_count"]) for page in pages)
    observation: Dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": universe["endpoint"],
        "pages": pages,
        "page_2_read": page_2_read,
        "page_2_reason": (
            None if not page_2_read else
            f"page 1 yielded only {count_after_page_1} qualifying names, fewer than top_n={top_n}"
        ),
        "policy": (
            "exactly one read-only GET of the frozen endpoint, plus at most one bounded extra "
            "page when the first page yields fewer than top_n qualifying names; the raw bytes "
            "are stored verbatim and hashed; the snapshot is never re-retrieved or re-timed"
        ),
        "protocol_version": spec["protocol_version"],
        "provider": universe.get("source", "unknown"),
        "qualifying_after_page_1": count_after_page_1,
        "ranking_depth_recomputed_from_bytes": depth_recomputed,
        "ranking_depth_recorded_by_the_specification": int(universe.get("ranking_depth") or 0),
        "retrieval_policy": retrieval.get("retrieval_policy"),
        "retrieval_timestamp_utc": pages[0]["retrieval_timestamp_utc"],
        "retrieval_window": {
            "not_before_utc": retrieval["not_before_utc"],
            "deadline_utc": retrieval["deadline_utc"],
            "retrieved_at_utc": pages[0]["retrieval_timestamp_utc"],
        },
        "specification_hash": spec["specification_hash"],
        "total_rows": len(all_rows),
        "universe_version": spec["universe_version"],
    }
    atomic_write_json(OBSERVATION_PATH, observation)

    print(json.dumps({
        "ok": True,
        "page_2_read": page_2_read,
        "pages": pages,
        "qualifying_after_page_1": count_after_page_1,
        "ranking_depth_recomputed_from_bytes": depth_recomputed,
        "total_rows": len(all_rows),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

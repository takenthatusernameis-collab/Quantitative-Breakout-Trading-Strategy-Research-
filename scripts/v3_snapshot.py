#!/usr/bin/env python3
"""Bounded, evidence-recording retrieval of the v3 market-cap snapshot.

This script performs exactly ONE read-only GET of the endpoint frozen in
``configs/research_v3.json`` -> ``universe.endpoint`` inside the preregistered
retrieval window (``not_before_utc`` .. ``deadline_utc``). It stores the raw
response bytes, their sha256 and the retrieval timestamp under
``research/v3_evidence/`` so that the v3 universe manifest can be bound to the
bytes that were actually received.

The window is fixed by the specification and must not be delayed, repeated or
re-timed to obtain a more convenient ranking. The script therefore refuses to
run outside the window and refuses to reuse a snapshot hash that is already
recorded in the v3 evidence directory (that would be a re-timed snapshot).

The v1 and v2 snapshots are never re-retrieved here: they are immutable
historical evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent

SPEC_PATH = REPO_ROOT / "configs" / "research_v3.json"
EVIDENCE_DIR = REPO_ROOT / "research" / "v3_evidence"
SNAPSHOT_RAW_PATH = EVIDENCE_DIR / "raw_market_cap_response.json"
SNAPSHOT_OBSERVATION_PATH = EVIDENCE_DIR / "snapshot_observation.json"

DEFAULT_TIMEOUT_S = 20.0


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    atomic_write_bytes(
        path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def fetch_snapshot(spec: Dict[str, Any], timeout_s: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Perform the single bounded retrieval and return the observation."""
    universe = spec.get("universe", {})
    endpoint = universe.get("endpoint")
    if not endpoint:
        raise SystemExit("the v3 spec has no universe.endpoint")

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
            "re-preregister a new window in a versioned amendment instead of re-timing"
        )

    started = datetime.now(timezone.utc)
    observation: Dict[str, Any] = {
        "endpoint": endpoint,
        "provider": universe.get("source", "unknown"),
        "probed_at_utc": started.isoformat(),
        "retrieval_timestamp_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "http_status": None,
        "reachable": False,
        "error": None,
        "elapsed_ms": None,
    }
    raw_bytes: bytes = b""
    markets: List[Dict[str, Any]] = []
    try:
        response = requests.get(endpoint, timeout=timeout_s)
        observation["http_status"] = response.status_code
        observation["reachable"] = bool(response.ok)
        raw_bytes = response.content
        if observation["reachable"]:
            payload = response.json()
            if isinstance(payload, list):
                markets = [entry for entry in payload if isinstance(entry, dict)]
            else:
                observation["error"] = "the provider returned a non-list payload"
                observation["reachable"] = False
        else:
            observation["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # transport/DNS/TLS errors are evidence, not a retry
        observation["error"] = f"{type(exc).__name__}: {exc}"
    observation["elapsed_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    digest = sha256_bytes(raw_bytes) if raw_bytes else ""
    return {
        "observation": observation,
        "raw_response_bytes_payload": raw_bytes,
        "raw_response_hash": digest,
        "raw_response_bytes": len(raw_bytes),
        "markets": markets,
        "window": {
            "not_before_utc": retrieval["not_before_utc"],
            "deadline_utc": retrieval["deadline_utc"],
            "retrieved_at_utc": observation["retrieval_timestamp_utc"],
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="allow re-emitting a hash that is already recorded in the v3 evidence directory",
    )
    parser.add_argument(
        "--print", dest="print_only", action="store_true", help="print the result, store nothing"
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    spec = json.loads((repo_root / "configs" / "research_v3.json").read_text(encoding="utf-8"))
    result = fetch_snapshot(spec, timeout_s=args.timeout_s)
    observation = result["observation"]

    existing_hash = ""
    raw_path = repo_root / "research" / "v3_evidence" / "raw_market_cap_response.json"
    if raw_path.exists():
        existing_hash = sha256_bytes(raw_path.read_bytes())
    if existing_hash and not args.allow_existing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        "a v3 market-cap snapshot is already recorded; a snapshot is retrieved "
                        "exactly once per version and is never re-timed"
                    ),
                    "recorded_raw_response_hash": existing_hash,
                    "this_raw_response_hash": result["raw_response_hash"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    if args.print_only:
        printable = {key: value for key, value in result.items()
                     if key != "raw_response_bytes_payload"}
        print(json.dumps(printable, indent=2, sort_keys=True))
        return 0 if observation["reachable"] else 1

    if not observation["reachable"]:
        print(json.dumps({"ok": False, "observation": observation}, indent=2, sort_keys=True))
        return 1

    atomic_write_bytes(raw_path, result["raw_response_bytes_payload"])
    observation["raw_response_hash"] = result["raw_response_hash"]
    observation["raw_response_bytes"] = result["raw_response_bytes"]
    observation["raw_response_path"] = raw_path.relative_to(repo_root).as_posix()
    observation["retrieval_window"] = result["window"]
    observation["protocol_version"] = spec["protocol_version"]
    observation["universe_version"] = spec["universe_version"]
    observation["specification_hash"] = spec["specification_hash"]
    observation["policy"] = (
        "exactly one read-only GET of the frozen endpoint inside the pinned window; the raw "
        "bytes are stored verbatim and hashed; the snapshot is never re-retrieved or re-timed"
    )
    atomic_write_json(repo_root / "research" / "v3_evidence" / "snapshot_observation.json", observation)

    print(
        json.dumps(
            {
                "ok": True,
                "raw_response_hash": result["raw_response_hash"],
                "raw_response_bytes": result["raw_response_bytes"],
                "markets": len(result["markets"]),
                "retrieval_timestamp_utc": observation["retrieval_timestamp_utc"],
                "raw_response_path": observation["raw_response_path"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _raw_bytes_of(result: Dict[str, Any]) -> bytes:
    """The exact bytes that were received from the provider."""
    return result["raw_response_bytes_payload"]


if __name__ == "__main__":
    sys.exit(main())

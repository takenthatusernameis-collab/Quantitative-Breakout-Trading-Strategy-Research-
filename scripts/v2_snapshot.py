#!/usr/bin/env python3
"""Bounded, evidence-recording retrieval of the v2 market-cap snapshot.

This script performs exactly ONE read-only GET of the endpoint frozen in
``configs/research_v2.json`` -> ``universe.endpoint`` inside the preregistered
retrieval window (``not_before_utc`` .. ``deadline_utc``). It writes nothing
to the repository: the raw response, its sha256, the retrieval timestamp and
the provider observation are printed as JSON so the caller can record them in
``research/universe_manifest_v2.json``.

The window is fixed by the specification and must not be delayed, repeated or
re-timed to obtain a more convenient ranking. The script therefore refuses to
run outside the window and refuses to reuse a snapshot hash already recorded
in the manifests (that would be a re-timed snapshot).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "configs" / "research_v2.json"
UNIVERSE_MANIFEST_V2_PATH = REPO_ROOT / "research" / "universe_manifest_v2.json"
DATA_MANIFEST_V2_PATH = REPO_ROOT / "research" / "data_manifest_v2.json"

DEFAULT_TIMEOUT_S = 15.0


def _parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _existing_snapshot_hash() -> str:
    """Return the raw_response_hash already recorded in the v2 manifests, or ''."""
    for path in (UNIVERSE_MANIFEST_V2_PATH, DATA_MANIFEST_V2_PATH):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source = payload.get("market_cap_source") or {}
        digest = source.get("raw_response_hash")
        if isinstance(digest, str) and digest:
            return digest
    return ""


def fetch_snapshot(spec: Dict[str, Any], timeout_s: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    universe = spec.get("universe", {})
    endpoint = universe.get("endpoint")
    if not endpoint:
        raise SystemExit("v2 spec has no universe.endpoint")

    retrieval = universe.get("snapshot_retrieval", {})
    not_before = _parse_iso_utc(retrieval["not_before_utc"])
    deadline = _parse_iso_utc(retrieval["deadline_utc"])
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
                observation["error"] = "provider returned a non-list payload"
                observation["reachable"] = False
        else:
            observation["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # transport/DNS/TLS errors are evidence, not a retry
        observation["error"] = f"{type(exc).__name__}: {exc}"
    observation["elapsed_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    digest = _sha256_bytes(raw_bytes) if raw_bytes else ""
    return {
        "observation": observation,
        "raw_response_hash": digest,
        "raw_response_bytes": len(raw_bytes),
        "markets": markets,
        "window": {
            "not_before_utc": retrieval["not_before_utc"],
            "deadline_utc": retrieval["deadline_utc"],
            "retrieved_at_utc": observation["retrieval_timestamp_utc"],
        },
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--allow-existing", action="store_true",
                        help="allow re-emitting a hash already recorded in the v2 manifests")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    spec = json.loads((repo_root / "configs" / "research_v2.json").read_text(encoding="utf-8"))
    result = fetch_snapshot(spec, timeout_s=args.timeout_s)
    result["observation"]["repo_root"] = str(repo_root)

    existing = _existing_snapshot_hash()
    if existing and not args.allow_existing and existing == result["raw_response_hash"]:
        print(json.dumps({
            "ok": True,
            "duplicate": True,
            "raw_response_hash": result["raw_response_hash"],
            "note": "the recorded snapshot hash matches this retrieval; not re-timed",
        }, indent=2, sort_keys=True))
        return 0

    if existing and not args.allow_existing:
        print(json.dumps({
            "ok": False,
            "error": (
                "the recorded snapshot hash differs from this retrieval; the previous "
                "snapshot was observed before these rules were frozen and must not be "
                "reused or re-timed"
            ),
            "recorded_raw_response_hash": existing,
            "this_raw_response_hash": result["raw_response_hash"],
        }, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["observation"]["reachable"] else 1


if __name__ == "__main__":
    sys.exit(main())
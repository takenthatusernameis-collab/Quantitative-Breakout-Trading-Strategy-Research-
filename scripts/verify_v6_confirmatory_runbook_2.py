#!/usr/bin/env python3
"""Read-only verifier for the versioned v6 confirmatory runbook 2."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def artifact_hash(document):
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body = dict(document)
    for key in excluded:
        parts = str(key).split(".")
        target = body
        for part in parts[:-1]:
            target = target.get(part) if isinstance(target.get(part), dict) else None
            if target is None:
                break
        if target is not None:
            target.pop(parts[-1], None)
    return digest(canonical(body))


def tree_hash(base):
    state = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        state.update(relative.encode("utf-8") + b"\n")
        state.update(digest((base / relative).read_bytes()).encode("ascii") + b"\n")
    return state.hexdigest()


def verify():
    p = ROOT / "configs/research_v6_confirmatory_runbook_2.json"
    old = ROOT / "configs/research_v6_confirmatory_runbook_1.json"
    protocol = json.loads((ROOT / "configs/research_v6_confirmatory_protocol.json").read_text())
    runbook = json.loads(p.read_text())
    previous = json.loads(old.read_text())
    selected = json.loads((ROOT / "research/v6_selected_configurations_manifest.json").read_text())
    authorization = json.loads((ROOT / "configs/research_v6_selection_authorization_2.json").read_text())
    fails = []
    if runbook.get("manifest_hash") != artifact_hash(runbook):
        fails.append("runbook 2 self-hash mismatch")
    if runbook.get("supersedes", {}).get("manifest_hash") != previous.get("manifest_hash"):
        fails.append("runbook 2 does not bind runbook 1")
    if runbook.get("supersedes", {}).get("sha256") != digest(old.read_bytes()):
        fails.append("runbook 1 file digest is stale")
    for name, item in (("protocol", protocol), ("selected manifest", selected), ("selection authorization", authorization)):
        if item.get("manifest_hash") != artifact_hash(item):
            fails.append(name + " self-hash mismatch")
    window = runbook.get("applies_to") or {}
    start = datetime.fromisoformat(window["window_start_utc"].replace("Z", "+00:00"))
    final_close = start + timedelta(hours=2160)
    exclusive_end = final_close + timedelta(hours=1)
    if window.get("evaluation_start_utc") != final_close.isoformat(timespec="milliseconds").replace("+00:00", "Z"):
        fails.append("evaluation start does not equal the 2,160th close")
    if window.get("window_end_utc") != exclusive_end.isoformat(timespec="milliseconds").replace("+00:00", "Z"):
        fails.append("exclusive end does not follow the 2,160th close")
    if window.get("minimum_closed_hourly_candles") != 2160:
        fails.append("minimum hourly sample differs from 2,160")
    binding = runbook.get("binding_identities") or {}
    if binding.get("confirmatory_protocol", {}).get("manifest_hash") != protocol.get("manifest_hash"):
        fails.append("protocol binding mismatch")
    if binding.get("selected_configurations_manifest", {}).get("manifest_hash") != selected.get("manifest_hash"):
        fails.append("selected manifest binding mismatch")
    if binding.get("selection_authorization_2", {}).get("manifest_hash") != authorization.get("manifest_hash"):
        fails.append("selection authorization binding mismatch")
    current_digest = tree_hash(ROOT / "src/v6_confirmatory")
    if binding.get("code_identity", {}).get("execution_path_digest") != current_digest:
        fails.append("confirmatory source digest mismatch")
    return {
        "ok": not fails,
        "failures": fails,
        "window_start_utc": window.get("window_start_utc"),
        "evaluation_start_utc": window.get("evaluation_start_utc"),
        "exclusive_close_end_utc": window.get("window_end_utc"),
        "minimum_closed_hourly_candles": window.get("minimum_closed_hourly_candles"),
        "confirmatory_candles_opened": False,
        "provider_requests": 0,
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 2)

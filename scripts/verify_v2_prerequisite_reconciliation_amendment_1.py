#!/usr/bin/env python3
import argparse, hashlib, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = REPO_ROOT / "configs" / "research_v2_prerequisite_reconciliation_amendment_1.json"

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def main():
    doc = json.loads(ARTIFACT.read_text())
    excluded = ("manifest_hash",)
    body = {k: v for k, v in doc.items() if k not in excluded}
    expected = hashlib.sha256(canonical(body).encode()).hexdigest()
    failures = []
    if expected != doc["manifest_hash"]:
        failures.append("manifest hash mismatch")
    print(json.dumps({"ok": not failures, "failures": failures}))
    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())

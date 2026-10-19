#!/usr/bin/env python3
"""Re-run the limited pilot and re-derive the campaign authorization.

Any change under ``src/breakout_research/`` rotates ``compute_code_hash()`` and
therefore invalidates ``research_state/campaign_authorization.json``: no
campaign execution may be trusted under the old hash afterwards (BRAIN-006
decision record, section 6).

The script has two phases, because the authorization must not claim a remote
persistence that has not happened yet:

* ``--phase pilot`` re-runs the limited pilot (top eligible asset, 24
  configurations, fold 0, baseline costs) against the frozen, hash-verified
  candle cache, writes ``research_state/pilot_evidence.json`` and
  ``reports/pilot_report.md`` bound to the current code hash, and rotates the
  code hash of ``research_state/checkpoint.json`` **without** touching its
  counters.  The pilot ledger and checkpoint are written to an isolated
  directory so that the live result ledger and the live checkpoint counters
  are not overwritten.  ``remote_persistence_verified`` is ``false`` in this
  phase.
* ``--phase authorize`` requires the pilot evidence to be committed and
  present on ``origin/main``; it then re-asserts ``remote_persistence_verified``
  and re-derives ``research_state/campaign_authorization.json`` through the
  independent validator.

Usage:
    PYTHONPATH=src python3 scripts/run_pilot_and_authorize.py --phase pilot
    PYTHONPATH=src python3 scripts/run_pilot_and_authorize.py --phase authorize
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.config import compute_code_hash  # noqa: E402
from breakout_research.pilot import PilotRunner  # noqa: E402
from breakout_research.pilot_gate_validator import authorize_campaign  # noqa: E402

CHECKPOINT_PATH = REPO_ROOT / "research_state" / "checkpoint.json"
EVIDENCE_PATH = REPO_ROOT / "research_state" / "pilot_evidence.json"
AUTHORIZATION_PATH = REPO_ROOT / "research_state" / "campaign_authorization.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT), check=True,
                          capture_output=True, text=True).stdout.strip()


def rotate_checkpoint_code_hash(code_hash: str) -> Dict[str, Any]:
    """Bind the live checkpoint to the current code hash, preserving its counters.

    The counters of the checkpoint are the record of the completed campaign and
    are never rewritten here; only the code hash (and its timestamp) rotate,
    because a checkpoint bound to a different code version is rejected by the
    campaign's stale-checkpoint guard.
    """
    with CHECKPOINT_PATH.open(encoding="utf-8") as handle:
        state = json.load(handle)
    previous = state.get("code_hash")
    state["code_hash"] = code_hash
    state["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    with CHECKPOINT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"previous_code_hash": previous, "code_hash": code_hash,
            "completed_records": state.get("completed_records"),
            "last_verified_record": state.get("last_verified_record")}


def run_pilot() -> Dict[str, Any]:
    code_hash = compute_code_hash()
    with tempfile.TemporaryDirectory() as workdir:
        work = Path(workdir)
        runner = PilotRunner(
            ledger_path=str(work / "pilot_results.jsonl"),
            checkpoint_path=str(work / "pilot_checkpoint.json"),
            evidence_path=str(EVIDENCE_PATH),
            report_path=str(REPO_ROOT / "reports" / "pilot_report.md"),
            remote_persistence_verified=False,
        )
        evidence = runner.run()
    if evidence["code_hash"] != code_hash:
        raise SystemExit("pilot evidence was not bound to the current code hash")
    rotation = rotate_checkpoint_code_hash(code_hash)
    return {"pilot": {
        "assets_tested": evidence["assets_tested"],
        "configs_tested": evidence["configs_tested"],
        "total_results": evidence["total_results"],
        "code_hash": evidence["code_hash"],
    }, "checkpoint": rotation}


def authorize() -> Dict[str, Any]:
    with EVIDENCE_PATH.open(encoding="utf-8") as handle:
        evidence = json.load(handle)
    code_hash = compute_code_hash()
    if evidence.get("code_hash") != code_hash:
        raise SystemExit(
            f"pilot evidence is bound to {evidence.get('code_hash')} but the code hash is {code_hash}; "
            "re-run the pilot first")
    head = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "origin", "main").split()[0] if _git("ls-remote", "origin", "main") else ""
    if remote != head:
        raise SystemExit(
            f"the pilot evidence is not on origin/main yet (local HEAD {head}, remote main {remote}); "
            "commit and push before authorizing")
    evidence["evidence"]["pilot_run_results"]["remote_persistence_verified"] = True
    with EVIDENCE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(evidence, handle, indent=2)
        handle.write("\n")
    artifact = authorize_campaign(str(EVIDENCE_PATH), str(AUTHORIZATION_PATH))
    return {"authorized": artifact["authorized"], "reasons": artifact["reasons"],
            "code_hash": artifact["code_hash"], "head": head, "remote_main": remote}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", choices=("pilot", "authorize"), required=True)
    args = parser.parse_args(argv)
    if args.phase == "pilot":
        result = run_pilot()
    else:
        result = authorize()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

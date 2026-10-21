"""The state of the v5 selection run, as the repository shows it.

The rule the v5 verifiers enforced before the run was a **preregistration** rule:
*no v5 run artifact may exist while the chain has not run*.  The single authorized
run has now run, so that rule no longer describes the world; the rule that does is
the post-run one:

* the v5 run artifacts, when they exist, are the outputs of the **authorized** run:
  the ledger names the authorized run id, campaign id and authorization identity;
* the run is in one of its three legal states -- not started, running (an
  interrupted run is resumed, never restarted) or completed -- and never in a
  fourth one;
* **no exposure occurred**: the ledger and the checkpoint both carry
  ``holdout_exposed_count == 0``;
* the shard directory holds the v5 campaign and no other;
* a **completed** run's record count agrees between the ledger and the results
  manifest.

The check is read-only and offline.  It reports the failures of the post-run
invariant; it never repairs anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

#: The five output paths of the v5 selection run.
V5_RUN_ARTIFACTS = (
    "research/shards_v5",
    "research/ledger_v5.json",
    "research/results_manifest_v5.json",
    "research/results_v5.jsonl",
    "research_state/checkpoint_v5.json",
)

LEDGER_RELATIVE = "research/ledger_v5.json"
RESULTS_MANIFEST_RELATIVE = "research/results_manifest_v5.json"
CHECKPOINT_RELATIVE = "research_state/checkpoint_v5.json"
SHARDS_RELATIVE = "research/shards_v5"
AUTHORIZATION_RELATIVE = "configs/research_v5_selection_authorization_1.json"

#: The three legal states of the single authorized run.
LEGAL_RUN_STATES = ("RUNNING", "INTERRUPTED", "COMPLETED")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def v5_run_artifacts_present(root: Path) -> List[str]:
    """The v5 run artifacts that exist in the repository."""
    return [relative for relative in V5_RUN_ARTIFACTS if (Path(root) / relative).exists()]


def v5_run_state_failures(root: Path) -> List[str]:
    """The failures of the post-run invariant of the v5 selection run.

    An empty list means the repository is consistent: either the chain has not run
    (no run artifact exists), or the artifacts that exist are the authorized run's
    outputs and no exposure occurred.
    """
    root = Path(root)
    failures: List[str] = []
    if not v5_run_artifacts_present(root):
        return failures

    ledger_path = root / LEDGER_RELATIVE
    if not ledger_path.exists():
        return [
            "a v5 run artifact exists, but the v5 ledger does not: the run artifacts "
            "are not the outputs of a recorded run"
        ]
    try:
        ledger = _load(ledger_path)
    except (OSError, ValueError) as exc:
        return [f"the v5 ledger is unreadable: {exc}"]

    authorization_path = root / AUTHORIZATION_RELATIVE
    if not authorization_path.exists():
        failures.append("the v5 ledger exists, but the v5 selection authorization does not")
        return failures
    authorization = _load(authorization_path)
    authorized_run = authorization.get("authorized_run") or {}

    if ledger.get("run_id") != authorized_run.get("run_id"):
        failures.append("the v5 ledger names another run than the authorized one")
    if ledger.get("campaign_id") != authorized_run.get("campaign_id"):
        failures.append("the v5 ledger names another campaign than the authorized one")
    if ledger.get("authorization_manifest_hash") != authorization.get("manifest_hash"):
        failures.append("the v5 ledger names another authorization than the authorized one")
    if ledger.get("status") not in LEGAL_RUN_STATES:
        failures.append(
            f"the v5 ledger records the run in the illegal state {ledger.get('status')!r}")
    if int(ledger.get("holdout_exposed_count") or 0) != 0:
        failures.append("the v5 ledger records a holdout exposure")

    shards_path = root / SHARDS_RELATIVE
    if shards_path.is_dir():
        campaigns = sorted(item.name for item in shards_path.iterdir() if item.is_dir())
        if campaigns != ["v5-campaign"]:
            failures.append(f"the research/shards_v5 directory holds {campaigns}")

    checkpoint_path = root / CHECKPOINT_RELATIVE
    if checkpoint_path.exists():
        checkpoint = _load(checkpoint_path)
        if int(checkpoint.get("holdout_exposed_count") or 0) != 0:
            failures.append("the v5 checkpoint records a holdout exposure")
        code_identity = ((ledger.get("code_identity") or {}).get("run_code_identity"))
        if code_identity and checkpoint.get("code_hash") != code_identity:
            failures.append("the v5 checkpoint was written by another code identity")

    results_manifest_path = root / RESULTS_MANIFEST_RELATIVE
    if results_manifest_path.exists():
        results_manifest = _load(results_manifest_path)
        if results_manifest.get("campaign_id") != ledger.get("campaign_id"):
            failures.append("the v5 results manifest names another campaign")
        code_identity = ((ledger.get("code_identity") or {}).get("run_code_identity"))
        if code_identity and results_manifest.get("code_hash") != code_identity:
            failures.append("the v5 results manifest was written by another code identity")
        if ledger.get("status") == "COMPLETED":
            written = int((ledger.get("counts") or {}).get("records_written") or 0)
            if int(results_manifest.get("total_records") or 0) != written:
                failures.append(
                    "the v5 results manifest and the ledger disagree on the record count")

    return failures

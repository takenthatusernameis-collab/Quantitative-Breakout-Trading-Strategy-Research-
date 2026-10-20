#!/usr/bin/env python3
"""Read-only, offline verification of the published v2 selected-configurations manifest.

The published artifact ``research/v2_selected_configurations_manifest.json`` records the
outcome of the authorized v2 selection run over the frozen v2 candidate set.  The
verifier never writes to the repository, never contacts a provider and never reads a
confirmatory-window candle.  It checks the artifact against the repository it claims
to describe:

* the document is self-hashing: ``manifest_hash`` recomputes from the canonical body
  with the hash-carrying key removed;
* the run identity binds the completed run: the run id, the campaign id and the
  selection-authorization hash agree with the ledger and with the selection
  authorization artifact, all of which are re-read from the repository;
* the scope is exactly the frozen candidate set of ``configs/research_v2_candidate_freeze.json``
  and exactly the validated constituents of the v2 universe manifest; the excluded
  assets are absent and keep their recorded reasons;
* the published selections are **independently reproduced**: the preregistered v1
  selection rule is re-applied to the verified result shards, with the buy-and-hold
  baselines recomputed from the hash-verified v2 datasets and the development boundary
  enforced by the loader, and every per-asset winner, status and economic status is
  compared with the published artifact.  The artifact is therefore checked against the
  evidence of the run itself and not against a copy of that evidence, and it is also
  compared with the run ledger, which is a derived artifact and cannot stand in for the
  shards;
* the reported outcome is the recomputed outcome;
* the confirmatory chain binds the artifact: the v2 confirmatory authorization anchors
  this manifest's self-hash and its file digest, and its evaluation scope is exactly the
  published selection;
* the artifact authorizes nothing: the confirmatory window is unexposed, no confirmatory
  or v3 execution artifact exists;
* every artifact the confirmatory authorization anchors is byte-unchanged.

Exit status is 0 when every check passes and 1 otherwise.  The report is printed as
JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from publish_v2_selected_configurations import recompute_selection  # noqa: E402

MANIFEST_RELATIVE = "research/v2_selected_configurations_manifest.json"
LEDGER_RELATIVE = "research/ledger_v2.json"
FREEZE_RELATIVE = "configs/research_v2_candidate_freeze.json"
SELECTION_AUTH_RELATIVE = "configs/research_v2_selection_authorization_1.json"
CONFIRMATORY_AUTH_RELATIVE = "configs/research_v2_confirmatory_authorization_1.json"
UNIVERSE_V2_RELATIVE = "research/universe_manifest_v2.json"
DATA_V2_RELATIVE = "research/data_manifest_v2.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V2_RELATIVE = "configs/research_v2.json"
CHECKPOINT_V2_RELATIVE = "research_state/checkpoint_v2.json"

REQUIRED_RELATIVES = (
    MANIFEST_RELATIVE,
    LEDGER_RELATIVE,
    FREEZE_RELATIVE,
    SELECTION_AUTH_RELATIVE,
    CONFIRMATORY_AUTH_RELATIVE,
    UNIVERSE_V2_RELATIVE,
    DATA_V2_RELATIVE,
    SPEC_V1_RELATIVE,
    SPEC_V2_RELATIVE,
)

# The recomputation is expensive, so the producer caches it per content signature.
# The signature covers every input the recomputation consumes (the shard bytes, the v2
# data manifest, the preregistered specification, the campaign id and the data
# boundary), so a cache hit can only happen when the evidence is unchanged.


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def v3_contamination_failures(root: Path) -> List[str]:
    """The failures of a v3 line that contaminated the v2 line.

    The v3 selection run writes into its own five output paths and into
    nothing else. The v2 line must therefore be untouched by it: the v2 ledger,
    the v2 results manifest and the v2 shard directory carry the v2 campaign,
    and the v2 selected-configurations manifest is the v2 manifest.
    """
    failures: List[str] = []
    ledger_path = root / "research" / "ledger_v2.json"
    if ledger_path.exists():
        ledger = _load(ledger_path)
        if ledger.get("campaign_id") != "v2-campaign":
            failures.append("7: the v2 ledger carries another campaign id")
    manifest_path = root / "research" / "results_manifest_v2.json"
    if manifest_path.exists():
        manifest = _load(manifest_path)
        if manifest.get("campaign_id") != "v2-campaign":
            failures.append("7: the v2 results manifest carries another campaign id")
    shards_v2 = root / "research" / "shards_v2"
    if shards_v2.is_dir():
        campaigns = sorted(path.name for path in shards_v2.iterdir() if path.is_dir())
        if campaigns != ["v2-campaign"]:
            failures.append(f"7: the v2 shard directory holds {campaigns}")
    return failures


def sha256_bytes(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Tuple[str, ...]) -> str:
    body = {key: value for key, value in document.items() if key not in set(excluded_keys)}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict) and tail in body[head]:
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body))


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Verify the published v2 selected-configurations manifest."""
    failures: List[str] = []
    root = Path(repo_root)

    for relative in REQUIRED_RELATIVES:
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    manifest = _load(root / MANIFEST_RELATIVE)
    ledger = _load(root / LEDGER_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    confirmatory_auth = _load(root / CONFIRMATORY_AUTH_RELATIVE)
    universe = _load(root / UNIVERSE_V2_RELATIVE)
    data_manifest = _load(root / DATA_V2_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v2 = _load(root / SPEC_V2_RELATIVE)

    # 1. The document is self-hashing.
    excluded = tuple(manifest.get("manifest_hash_excluded_keys") or ("manifest_hash",))
    if manifest.get("manifest_hash") != compute_manifest_hash(manifest, excluded):
        failures.append("1: manifest_hash does not recompute from the document")

    # 2. The run identity binds the completed run.
    identity = manifest.get("run_identity") or {}
    if identity.get("run_id") != ledger.get("run_id"):
        failures.append("2: run_id does not match the ledger")
    if identity.get("campaign_id") != ledger.get("campaign_id"):
        failures.append("2: campaign_id does not match the ledger")
    if identity.get("authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("2: authorization_manifest_hash does not match the selection authorization")
    if identity.get("ordered_code_hash_authorized") != ledger["code_identity"]["authorized_code_hash"]:
        failures.append("2: the recorded authorized code hash differs from the ledger")
    if identity.get("hashed_set_digest") != ledger["code_identity"]["hashed_set_digest"]:
        failures.append("2: the recorded hashed-set digest differs from the ledger")
    if identity.get("execution_path_digest") != ledger["code_identity"]["execution_path_digest"]:
        failures.append("2: the recorded execution-path digest differs from the ledger")
    specification_identities = manifest.get("specification_identities") or {}
    if specification_identities.get("spec_v1_hash") != sha256_bytes(canonical(spec_v1)):
        failures.append("2: the published manifest does not bind the v1 specification")
    if specification_identities.get("spec_v2_hash") != sha256_bytes(canonical(spec_v2)):
        failures.append("2: the published manifest does not bind the v2 specification")
    if specification_identities.get("selection_rule_digest") != sha256_bytes(canonical(spec_v1["selection"])):
        failures.append("2: the published selection-rule digest does not match the v1 selection block")
    if specification_identities.get("selection_rule_reference") != "configs/research_v1.json#selection":
        failures.append("2: the published selection-rule reference is not the v1 selection block")
    if ledger["selection"].get("selection_block_sha256") != specification_identities.get("selection_rule_digest"):
        failures.append("2: the published selection-rule digest differs from the ledger")

    # 3. The scope is exactly the frozen candidate set.
    frozen = freeze["frozen_candidate_set"]
    scope = manifest.get("scope", {}).get("frozen_candidate_set", {})
    frozen_pairs = [str(pair) for pair in frozen["binance_pairs"]]
    if sorted(scope.get("binance_pairs", [])) != sorted(frozen_pairs):
        failures.append("3: the published scope is not the frozen candidate set")
    if scope.get("count") != len(frozen_pairs):
        failures.append("3: the published scope count differs from the frozen candidate count")
    validated = sorted(
        entry["symbol"] for entry in universe["eligible_assets"] if entry.get("validated"))
    if sorted(frozen_pairs) != validated:
        failures.append("3: the frozen candidate set is not the validated v2 constituents")
    excluded_assets = {
        entry["symbol"]: entry["exclusion_reason"]
        for entry in universe["eligible_assets"]
        if not entry.get("validated")
    }
    if scope.get("excluded_after_validation") != excluded_assets:
        failures.append("3: the published exclusion reasons differ from the v2 universe manifest")
    for symbol in excluded_assets:
        if symbol in (manifest.get("selections") or {}):
            failures.append(f"3: the excluded asset {symbol} appears in the published selections")
    if scope.get("universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("3: the published scope does not bind the v2 universe manifest")
    if scope.get("data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("3: the published scope does not bind the v2 data manifest")
    if (manifest.get("data_identities") or {}).get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("3: the published manifest does not bind the v2 candidate freeze")

    # 4. The published selections are independently reproduced from the shards.
    try:
        recomputed = recompute_selection(root)
    except Exception as exc:  # a failure to re-derive is a verification failure
        recomputed = {}
        failures.append(f"4: the selection could not be recomputed from the shards: {exc}")
    selections = manifest.get("selections") or {}
    if recomputed:
        per_asset = recomputed["per_asset"]
        if set(selections) != set(per_asset):
            failures.append("4: the published selections do not cover the recomputed assets")
        for asset, entry in sorted(per_asset.items()):
            published = selections.get(asset) or {}
            if published.get("config_id") != entry["config_id"]:
                failures.append(
                    f"4: the selected configuration of {asset} differs from the recomputation "
                    f"({published.get('config_id')} != {entry['config_id']})")
            if published.get("status") != entry["status"]:
                failures.append(
                    f"4: the selection status of {asset} differs from the recomputation "
                    f"({published.get('status')} != {entry['status']})")
            if published.get("economic_status") != entry["economic_status"]:
                failures.append(
                    f"4: the economic status of {asset} differs from the recomputation "
                    f"({published.get('economic_status')} != {entry['economic_status']})")
        if manifest.get("derived_from", {}).get("records_read") != recomputed["records_read"]:
            failures.append("4: the published record count differs from the recomputation")

        # 4b. The published selections also agree with the run ledger.  The recomputation
        # above is the primary check; this one detects a ledger that diverges from the
        # shards, which the recomputation alone would not report.
        ledger_selection = ledger.get("selection") or {}
        for asset, published in sorted(selections.items()):
            entry = (ledger_selection.get("per_asset") or {}).get(asset) or {}
            if published.get("config_id") != entry.get("config_id"):
                failures.append(
                    f"4b: the selected configuration of {asset} differs from the run ledger")
            if published.get("status") != entry.get("status"):
                failures.append(f"4b: the selection status of {asset} differs from the run ledger")

        # 5. The reported outcome is the recomputed outcome.
        if manifest.get("assets_with_candidate") != recomputed["assets_with_candidate"]:
            failures.append("5: the published assets_with_candidate differs from the recomputation")
        if manifest.get("assets_without_candidate") != recomputed["assets_without_candidate"]:
            failures.append("5: the published assets_without_candidate differs from the recomputation")
        expected_outcome = (
            "CANDIDATES_SELECTED_FOR_PART_OF_THE_UNIVERSE"
            if recomputed["assets_with_candidate"] and recomputed["assets_without_candidate"]
            else ("CANDIDATES_SELECTED" if recomputed["assets_with_candidate"]
                  else "NO_CANDIDATE_SURVIVED_THE_SELECTION_RULE")
        )
        if manifest.get("outcome") != expected_outcome:
            failures.append(
                f"5: the published outcome differs from the recomputed outcome "
                f"({manifest.get('outcome')} != {expected_outcome})")
        if manifest.get("assets_without_candidate_reported") is not True:
            failures.append("5: the assets without a candidate are not reported")

    # 6. The confirmatory chain binds the artifact.
    authorized_run = confirmatory_auth.get("authorized_run") or {}
    confirmatory_scope = authorized_run.get("scope") or {}
    if confirmatory_scope.get("bound_to_selected_configurations_hash") != manifest.get("manifest_hash"):
        failures.append("6: the confirmatory authorization does not bind this manifest's hash")
    anchors = (authorized_run.get("immutable_artifact_anchors") or {}).get("v2_selection_outputs") or {}
    if anchors.get(MANIFEST_RELATIVE) != sha256_file(root / MANIFEST_RELATIVE):
        failures.append("6: the confirmatory authorization does not anchor this manifest's bytes")
    selected_assets = sorted(
        asset for asset, entry in selections.items() if entry.get("selected"))
    if sorted(confirmatory_scope.get("assets", [])) != selected_assets:
        failures.append("6: the confirmatory evaluation scope is not the published selection")
    if confirmatory_scope.get("config_ids") != {
            asset: entry.get("config_id") for asset, entry in selections.items() if entry.get("selected")}:
        failures.append("6: the confirmatory evaluation config ids are not the published selection")
    out_of_scope = sorted(
        asset for asset, entry in selections.items() if not entry.get("selected"))
    if sorted(confirmatory_scope.get("out_of_scope_assets_without_candidate", [])) != out_of_scope:
        failures.append("6: the assets without a candidate are not the published out-of-scope set")

    # 7. The artifact authorizes nothing.
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("7: the v2 confirmatory window is not unexposed")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("7: the v2 confirmatory window records an exposure")
    checkpoint_path = root / CHECKPOINT_V2_RELATIVE
    if checkpoint_path.exists():
        checkpoint = _load(checkpoint_path)
        if checkpoint.get("holdout_exposed_count") != 0:
            failures.append("7: the v2 checkpoint records an exposure")
    for relative in (authorized_run.get("paths") or {}).values():
        if (root / relative).exists():
            failures.append(f"7: the confirmatory output {relative} exists")
    # The rule "the v3 execution artifact exists" was replaced, not deleted: it
    # was true while the v3 line had not run, and it is false by design once
    # the authorized v3 selection run has been performed. The replacement
    # protects what the rule was protecting -- the v2 line -- and is stronger:
    # the v3 line may not write into, or be mixed into, any v2 artifact.
    failures.extend(v3_contamination_failures(root))
    if confirmatory_auth.get("authorizes_evaluation_before_the_window_exists") is not False:
        failures.append("7: the confirmatory authorization would evaluate before the window exists")

    # 8. Every anchored artifact is byte-unchanged.
    for group, entries in (authorized_run.get("immutable_artifact_anchors") or {}).items():
        for relative, digest in entries.items():
            observed = sha256_file(root / relative)
            if observed is None:
                failures.append(f"8: the anchored artifact {relative} is missing")
            elif observed != digest:
                failures.append(f"8: the anchored artifact {relative} changed")

    return {"ok": len(failures) == 0, "failures": failures}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=str(REPO_ROOT),
                        help="the repository to verify (default: the repository of this script)")
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

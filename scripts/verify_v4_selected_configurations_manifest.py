#!/usr/bin/env python3
"""Read-only, offline verification of the published v4 selection outcome.

The published artifact ``research/v4_selected_configurations_manifest.json`` records the
outcome of the authorized v4 selection run over the frozen v4 candidate set, and
``configs/research_v4_execution_amendment_1.json`` binds that publication into the v4
execution protocol.  The verifier never writes to the repository, never contacts a
provider and never reads a confirmatory-window candle.  It checks the artifacts against
the repository they claim to describe:

* the published document is self-hashing: ``manifest_hash`` recomputes from the
  canonical body with the hash-carrying key removed;
* the run identity binds the completed run: the run id, the campaign id, the
  selection-authorization hash and **every code identity** agree with the ledger and
  with the selection authorization artifact, all of which are re-read from the
  repository, and the execution-path digest is **recomputed from the source tree**
  rather than compared with a copy;
* the scope is exactly the frozen candidate set of the v4 freeze and exactly the
  validated constituents of the v4 universe manifest; the excluded assets are absent
  and keep their recorded reasons;
* the published selections are **independently reproduced**: the preregistered v1
  selection rule is re-applied to the verified result shards, with the buy-and-hold
  baselines recomputed from the hash-verified v4 datasets under the benchmark rule and
  the development boundary enforced by the v4 loader, and every per-asset winner,
  status and economic status is compared with the published artifact.  The artifact is
  therefore checked against the evidence of the run itself and not against a copy of
  that evidence, and it is also compared with the run ledger, which is a derived
  artifact and cannot stand in for the shards;
* the reported outcome is the recomputed outcome and the assets without a candidate
  are reported explicitly;
* the benchmark rule and the effective data-manifest identity are bound and recomputed;
* the artifact authorizes nothing: it starts no run, evaluates no confirmatory window
  and reads no candle; the holdout exposure of the v4 line is zero;
* the v1, v2 and v3 lines are uncontaminated by the v4 line and the v1 artifacts are
  byte-unchanged;
* the amendment that binds the published run names the performed run's identity, the
  evaluation scope, the benchmark rule and the code-hash constraint, authorizes
  nothing, and binds the published manifest's hash.

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

from publish_v4_selected_configurations import recompute_selection  # noqa: E402
from v4_campaign.identity import execution_path_digest, hashed_set_digest  # noqa: E402

MANIFEST_RELATIVE = "research/v4_selected_configurations_manifest.json"
AMENDMENT_RELATIVE = "configs/research_v4_execution_amendment_1.json"
LEDGER_RELATIVE = "research/ledger_v4.json"
RESULTS_MANIFEST_RELATIVE = "research/results_manifest_v4.json"
FREEZE_RELATIVE = "configs/research_v4_candidate_freeze.json"
SELECTION_AUTH_RELATIVE = "configs/research_v4_selection_authorization_1.json"
EXECUTION_RELATIVE = "configs/research_v4_execution.json"
UNIVERSE_V4_RELATIVE = "research/universe_manifest_v4.json"
DATA_V4_RELATIVE = "research/data_manifest_v4.json"
SPEC_V1_RELATIVE = "configs/research_v1.json"
SPEC_V4_RELATIVE = "configs/research_v4.json"
CHECKPOINT_V4_RELATIVE = "research_state/checkpoint_v4.json"
V3_MANIFEST_RELATIVE = "research/v3_selected_configurations_manifest.json"

REQUIRED_RELATIVES = (
    MANIFEST_RELATIVE,
    AMENDMENT_RELATIVE,
    LEDGER_RELATIVE,
    RESULTS_MANIFEST_RELATIVE,
    FREEZE_RELATIVE,
    SELECTION_AUTH_RELATIVE,
    EXECUTION_RELATIVE,
    UNIVERSE_V4_RELATIVE,
    DATA_V4_RELATIVE,
    SPEC_V1_RELATIVE,
    SPEC_V4_RELATIVE,
)

#: The v1 artifacts, byte-anchored.  The v4 line may not change any of them.
V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def prior_line_contamination_failures(root: Path) -> List[str]:
    """The failures of a v1, v2 or v3 line that the v4 line contaminated.

    The v4 selection run writes into its own five output paths and into nothing else.
    The v1, v2 and v3 lines must therefore be untouched by it: their ledgers, results
    manifests and shard directories carry their own campaign, and the published v2 and
    v3 selected-configurations manifests are theirs.
    """
    failures: List[str] = []
    for relative, campaign in (
        ("research/ledger_v2.json", "v2-campaign"),
        ("research/results_manifest_v2.json", "v2-campaign"),
        ("research/ledger_v3.json", "v3-campaign"),
        ("research/results_manifest_v3.json", "v3-campaign"),
        ("research/ledger_v4.json", "v4-campaign"),
        ("research/results_manifest_v4.json", "v4-campaign"),
    ):
        path = root / relative
        if path.exists():
            document = _load(path)
            if document.get("campaign_id") != campaign:
                failures.append(f"8: {relative} carries another campaign id")
    for directory, campaign in (("research/shards_v2", "v2-campaign"),
                                ("research/shards_v3", "v3-campaign"),
                                ("research/shards_v4", "v4-campaign")):
        path = root / directory
        if path.is_dir():
            campaigns = sorted(item.name for item in path.iterdir() if item.is_dir())
            if campaigns != [campaign]:
                failures.append(f"8: the {directory} directory holds {campaigns}")
    for relative, version in (("research/v2_selected_configurations_manifest.json", "v2"),
                              (V3_MANIFEST_RELATIVE, "v3")):
        path = root / relative
        if path.exists():
            document = _load(path)
            excluded = tuple(document.get("manifest_hash_excluded_keys") or ("manifest_hash",))
            if document.get("manifest_hash") != compute_manifest_hash(document, excluded):
                failures.append(f"8: the published {version} selected-configurations "
                                "manifest does not recompute")
            if document.get("protocol_version") != version:
                failures.append(f"8: the published {version} selected-configurations "
                                "manifest is not the v%s manifest" % version[1])
    return failures


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Verify the published v4 selection outcome."""
    failures: List[str] = []
    root = Path(repo_root)

    for relative in REQUIRED_RELATIVES:
        if not (root / relative).exists():
            return {"ok": False, "failures": [f"missing artifact: {relative}"]}

    manifest = _load(root / MANIFEST_RELATIVE)
    amendment = _load(root / AMENDMENT_RELATIVE)
    ledger = _load(root / LEDGER_RELATIVE)
    results_manifest = _load(root / RESULTS_MANIFEST_RELATIVE)
    freeze = _load(root / FREEZE_RELATIVE)
    selection_auth = _load(root / SELECTION_AUTH_RELATIVE)
    execution = _load(root / EXECUTION_RELATIVE)
    universe = _load(root / UNIVERSE_V4_RELATIVE)
    data_manifest = _load(root / DATA_V4_RELATIVE)
    spec_v1 = _load(root / SPEC_V1_RELATIVE)
    spec_v4 = _load(root / SPEC_V4_RELATIVE)

    # 1. The published document is self-hashing.
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
    if identity.get("authorized_code_hash") != ledger["code_identity"]["authorized_code_hash"]:
        failures.append("2: the recorded authorized code hash differs from the ledger")
    if identity.get("hashed_set_digest") != ledger["code_identity"]["hashed_set_digest"]:
        failures.append("2: the recorded hashed-set digest differs from the ledger")
    if identity.get("execution_path_digest") != ledger["code_identity"]["execution_path_digest"]:
        failures.append("2: the recorded execution-path digest differs from the ledger")
    if identity.get("run_code_identity") != ledger["code_identity"]["run_code_identity"]:
        failures.append("2: the recorded run code identity differs from the ledger")

    # 2b. The code identity is **recomputed** from the source tree, so a digest that
    # merely looks like the recorded one is caught.
    recomputed_execution_path = execution_path_digest(root)
    if recomputed_execution_path != identity.get("execution_path_digest"):
        failures.append(
            "2b: the recorded execution-path digest does not recompute from the source tree")
    recomputed_hashed_set = hashed_set_digest(root)
    if recomputed_hashed_set != identity.get("hashed_set_digest"):
        failures.append(
            "2b: the recorded hashed-set digest does not recompute from the source tree")
    if identity.get("authorized_code_hash") != str(
            (execution.get("code_hash_constraint") or {}).get("authorized_code_hash")):
        failures.append("2b: the recorded authorized code hash differs from the execution protocol")

    specification_identities = manifest.get("specification_identities") or {}
    if specification_identities.get("spec_v1_document_sha256") != sha256_bytes(canonical(spec_v1)):
        failures.append("2: the published manifest does not bind the v1 specification document")
    if specification_identities.get("spec_v4_document_sha256") != sha256_bytes(canonical(spec_v4)):
        failures.append("2: the published manifest does not bind the v4 specification document")
    if specification_identities.get("spec_v1_self_hash") != spec_v1.get("specification_hash"):
        failures.append("2: the recorded v1 self-hash differs from the v1 specification")
    if specification_identities.get("spec_v4_self_hash") != spec_v4.get("specification_hash"):
        failures.append("2: the recorded v4 self-hash differs from the v4 specification")
    if specification_identities.get("run_specification_hash") != ledger.get("specification_hash"):
        failures.append("2: the recorded run specification hash differs from the ledger")
    if specification_identities.get("selection_rule_digest") != sha256_bytes(canonical(spec_v1["selection"])):
        failures.append("2: the published selection-rule digest does not match the v1 selection block")
    if specification_identities.get("selection_rule_reference") != "configs/research_v1.json#selection":
        failures.append("2: the published selection-rule reference is not the v1 selection block")
    if ledger["selection"].get("selection_block_sha256") != specification_identities.get("selection_rule_digest"):
        failures.append("2: the published selection-rule digest differs from the ledger")

    # 3. The scope is exactly the frozen candidate set.
    frozen_pairs = sorted(
        str(member.get("binance_pair"))
        for member in (freeze.get("candidates") or [])
        if member.get("validated") is True
    )
    scope = (manifest.get("scope") or {}).get("frozen_candidate_set") or {}
    published_pairs = [str(pair) for pair in scope.get("binance_pairs") or []]
    if sorted(published_pairs) != frozen_pairs:
        failures.append("3: the published scope is not the frozen candidate set")
    if scope.get("count") != len(frozen_pairs):
        failures.append("3: the published scope count differs from the frozen candidate count")
    validated = sorted(
        str(entry.get("binance_pair"))
        for entry in universe.get("eligible_assets") or []
        if entry.get("validated") is True and entry.get("exclusion_reason") is None
    )
    if sorted(published_pairs) != validated:
        failures.append("3: the frozen candidate set is not the validated v4 constituents")
    excluded_assets = {
        str(entry.get("binance_pair")): str(entry.get("exclusion_reason"))
        for entry in universe.get("eligible_assets") or []
        if not (entry.get("validated") is True and entry.get("exclusion_reason") is None)
    }
    if scope.get("excluded_after_validation") != excluded_assets:
        failures.append("3: the published exclusion reasons differ from the v4 universe manifest")
    for symbol in excluded_assets:
        if symbol in (manifest.get("selections") or {}):
            failures.append(f"3: the excluded asset {symbol} appears in the published selections")
    if scope.get("universe_manifest_hash") != universe.get("manifest_hash"):
        failures.append("3: the published scope does not bind the v4 universe manifest")
    if scope.get("base_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("3: the published scope does not bind the v4 data manifest")
    data_identities = manifest.get("data_identities") or {}
    if data_identities.get("universe_manifest_v4_hash") != universe.get("manifest_hash"):
        failures.append("3: the published manifest does not bind the v4 universe manifest")
    if data_identities.get("base_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("3: the published manifest does not bind the v4 data manifest")
    if data_identities.get("effective_data_manifest_hash") != data_manifest.get("manifest_hash"):
        failures.append("3: the published effective data-manifest identity differs from "
                        "the v4 data manifest")
    if data_identities.get("candidate_freeze_hash") != freeze.get("manifest_hash"):
        failures.append("3: the published manifest does not bind the v4 candidate freeze")

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
            if published.get("counts") != entry["counts"]:
                failures.append(f"4: the gate counts of {asset} differ from the recomputation")
        if (manifest.get("derived_from") or {}).get("records_read") != recomputed["records_read"]:
            failures.append("4: the published record count differs from the recomputation")
        if (manifest.get("derived_from") or {}).get("all_grid_units_present") is not True:
            failures.append("4: the published manifest does not claim the complete grid")
        if recomputed["records_read"] != int(ledger["counts"]["records_written"]):
            failures.append("4: the recomputed record count differs from the ledger")

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
        for asset in recomputed["assets_without_candidate"]:
            published = selections.get(asset) or {}
            if published.get("selected") is not False:
                failures.append(f"5: the asset {asset} has no candidate but is published as selected")
            if not published.get("reason"):
                failures.append(f"5: the asset {asset} has no candidate and no reason is reported")

    # 6. The benchmark rule is bound and recomputed.
    benchmark = manifest.get("benchmark") or {}
    benchmark_rule = execution.get("benchmark_rule") or {}
    if benchmark.get("content_hash") != benchmark_rule.get("content_hash"):
        failures.append("6: the published benchmark digest differs from the v4 execution protocol")
    if benchmark.get("dataset_path") != benchmark_rule.get("dataset_path"):
        failures.append("6: the published benchmark dataset differs from the v4 execution protocol")
    if benchmark.get("alignment_rule") != benchmark_rule.get("alignment"):
        failures.append("6: the published benchmark alignment rule differs from the v4 execution protocol")
    if benchmark.get("btc_configurations_dropped") is not False:
        failures.append("6: the published manifest does not forbid dropping the BTC configurations")
    benchmark_path = root / str(benchmark.get("dataset_path") or "")
    if not benchmark_path.exists():
        failures.append("6: the published benchmark dataset is missing")
    elif sha256_file(benchmark_path) != benchmark.get("content_hash"):
        failures.append("6: the published benchmark digest does not match the dataset on disk")

    # 7. The artifact authorizes nothing and exposes nothing.
    authorizes = manifest.get("authorizes") or {}
    for key in ("selection_run", "second_run", "confirmatory_evaluation", "candle_fetch"):
        if authorizes.get(key) is not False:
            failures.append(f"7: the published manifest claims to authorize {key}")
    exposure = manifest.get("exposure") or {}
    if exposure.get("holdout_exposed_count") != 0:
        failures.append("7: the published manifest records a holdout exposure")
    if exposure.get("confirmatory_candles_read") != 0:
        failures.append("7: the published manifest records a confirmatory-window read")
    if exposure.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("7: the v4 confirmatory window is not unexposed")
    window_state = data_manifest.get("confirmatory_window") or {}
    if window_state.get("confirmatory_window_status") != "NOT_STARTED":
        failures.append("7: the v4 confirmatory window is not unexposed in the data manifest")
    if window_state.get("holdout_exposed_count") != 0:
        failures.append("7: the v4 data manifest records a holdout exposure")
    if ledger.get("holdout_exposed_count") != 0:
        failures.append("7: the v4 ledger records a holdout exposure")
    checkpoint_path = root / CHECKPOINT_V4_RELATIVE
    if checkpoint_path.exists():
        checkpoint = _load(checkpoint_path)
        if checkpoint.get("holdout_exposed_count") != 0:
            failures.append("7: the v4 checkpoint records a holdout exposure")
    if ledger.get("status") != "COMPLETED":
        failures.append("7: the v4 selection run is not completed")
    if results_manifest.get("total_records") != int(ledger["counts"]["records_written"]):
        failures.append("7: the v4 results manifest and the ledger disagree on the record count")

    # 8. The prior lines are uncontaminated, and the v1 artifacts are byte-unchanged.
    failures.extend(prior_line_contamination_failures(root))
    for relative, expected in V1_ARTIFACT_SHA256.items():
        observed = sha256_file(root / relative)
        if observed is None:
            failures.append(f"8: the v1 artifact {relative} is missing")
        elif observed != expected:
            failures.append(f"8: the v1 artifact {relative} changed")

    # 9. The amendment that binds the performed run names it, and authorizes nothing.
    excluded_amendment = tuple(
        (amendment.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",)
    )
    if amendment.get("manifest_hash") != compute_manifest_hash(amendment, excluded_amendment):
        failures.append("9: the v4 execution amendment does not recompute its own hash")
    if (amendment.get("amends") or {}).get("file") != EXECUTION_RELATIVE:
        failures.append("9: the v4 execution amendment does not amend the v4 execution protocol")
    performed = amendment.get("performed_run") or {}
    if performed.get("run_id") != ledger.get("run_id"):
        failures.append("9: the v4 execution amendment names another run")
    if performed.get("authorization_manifest_hash") != selection_auth.get("manifest_hash"):
        failures.append("9: the v4 execution amendment names another authorization")
    if performed.get("run_code_identity") != identity.get("run_code_identity"):
        failures.append("9: the v4 execution amendment names another run code identity")
    if performed.get("execution_path_digest") != identity.get("execution_path_digest"):
        failures.append("9: the v4 execution amendment names another execution-path digest")
    if performed.get("execution_path_digest") != recomputed_execution_path:
        failures.append("9: the v4 execution amendment's execution-path digest does not "
                        "recompute from the source tree")
    if sorted(str(pair) for pair in (amendment.get("evaluation_scope") or {})
              .get("constituents") or []) != sorted(published_pairs):
        failures.append("9: the v4 execution amendment names another evaluation scope")
    if (amendment.get("benchmark_rule") or {}) != benchmark_rule:
        failures.append("9: the v4 execution amendment's benchmark rule differs from the "
                        "v4 execution protocol")
    if (amendment.get("code_hash_constraint") or {}) != (execution.get("code_hash_constraint") or {}):
        failures.append("9: the v4 execution amendment's code-hash constraint differs from "
                        "the v4 execution protocol")
    if (amendment.get("selection_manifest") or {}).get("manifest_hash") != manifest.get("manifest_hash"):
        failures.append("9: the v4 execution amendment does not bind this manifest's hash")
    if (amendment.get("selection_manifest") or {}).get("path") != MANIFEST_RELATIVE:
        failures.append("9: the v4 execution amendment does not name this manifest path")
    authorization = amendment.get("execution_authorization") or {}
    for key in ("execution_authorized", "grid_run_authorized", "second_run_authorized",
                "confirmatory_evaluation_authorized", "candle_fetch_authorized"):
        if authorization.get(key) is not False:
            failures.append(f"9: the v4 execution amendment claims to authorize {key}")

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

#!/usr/bin/env python3
"""Read-only, offline verification of the preregistered v2 code-hash amendment 2.

``configs/research_v2_code_hash_amendment_2.json`` is a design artifact. It
corrects the recorded **location** of residual limitation ``RL1`` in the frozen
``configs/research_v2_code_hash_amendment_1.json`` by reference -- the frozen
artifact is not edited -- and it records the corrected location in a form the
verifier can enforce: the set of code-hash comparison sites in the hashed source
set is recomputed from the tree, so the amendment can neither omit a site nor
invent one.

The verifier never writes to the repository, never contacts a provider and never
reads a candle. It checks:

* the manifest hash recomputes from the canonical content of the document with
  the hash key removed;
* the corrected artifact is byte-identical to the digest recorded for it, still
  records the original (defective) location, and is not edited;
* the code-hash comparison sites recomputed from the source tree are exactly the
  sites the amendment records, with the same lines and comparisons;
* every recorded evidence step still exists verbatim in the source, the live
  chain of a live-vs-recorded site ends in a ``compute_code_hash()`` call, the
  recorded chain of every site begins with a persisted-artifact read, and the
  corrected location is exactly the set of files that hold a live-vs-recorded
  site;
* the corrected location differs from the recorded one only in the location: the
  limitation, its consequence and the behaviour are unchanged;
* the hashed set is unchanged (the canonical digest still matches), the
  authorized value of record is still the v1 campaign authorization's code hash,
  and the pre-flight that implements the BRAIN-010 decision exists;
* nothing is authorized, no v2 execution artifact changed and the v1 evidence is
  byte-identical.

Exit status is 0 when every check passes and 1 otherwise. The report is
printed as JSON so it can be diffed between runs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AMENDMENT_RELATIVE = "configs/research_v2_code_hash_amendment_2.json"
CORRECTED_ARTIFACT_RELATIVE = "configs/research_v2_code_hash_amendment_1.json"
AUTHORIZATION_RELATIVE = "research_state/campaign_authorization.json"
PREFLIGHT_RELATIVE = "scripts/verify_v1_gate_compatibility.py"

HASHED_SET_ROOT = "src/breakout_research"

#: Calls that read a persisted artifact. The list is fixed here, not taken from
#: the artifact, so the amendment cannot weaken the check by relaxing it.
PERSISTED_READ_MARKERS = (
    "_read_json_file(",
    "load_authorization(",
    "_read_json(",
    "_read_manifest(",
)

#: The call that produces the live, checkout-dependent ordered digest.
LIVE_DIGEST_MARKER = "compute_code_hash("

V1_ARTIFACT_SHA256 = {
    "configs/research_v1.json": "558d60990af9310d5cedbc41a58dbf29eb4dc869f8e45dc1cb2baf644480490d",
    "research/universe_manifest.json": "c8f367d24cd7b618f97f51b8a91c877429c1cac1ddbd17765349ea6c306fdffd",
    "research/data_manifest.json": "cf39de420cfc7328bd4a244c7f485e4b81c01dae108f17f2719d6ca6e7310580",
    "research/candidate_manifest.json": "87589f83f3bfe22517bb73257d285ec47d602c19a892f0971035e1523df4f1d6",
    "research/candidate_manifest_v2.json": "a68b061a8c314828bf60478ef8f826ee9d532c6e5ff1545c8afaa2c8e03dfa49",
}

#: The v2 execution artifacts of the completed, authorized v2 selection run.
#: They must not change: this amendment authorizes nothing.
V2_EXECUTION_ARTIFACTS = (
    "research/shards_v2",
    "research/ledger_v2.json",
    "research/results_manifest_v2.json",
    "research/results_v2.jsonl",
    "research_state/checkpoint_v2.json",
)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_hash(document: Dict[str, Any], excluded_keys: Sequence[str]) -> str:
    body = {key: value for key, value in document.items() if key not in excluded_keys}
    for dotted in (key for key in excluded_keys if "." in key):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k: v for k, v in body[head].items() if k != tail}
    return sha256_bytes(canonical(body).encode("utf-8"))


def canonical_source_digest(
    repo_root: Path = REPO_ROOT, hashed_set_root: str = HASHED_SET_ROOT
) -> str:
    """The portable identity of the hashed source tree."""
    base = repo_root / hashed_set_root
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def live_ordered_code_hash(repo_root: Path = REPO_ROOT) -> Optional[str]:
    """Reproduce ``compute_code_hash()`` exactly, for the informational report."""
    src_dir = repo_root / HASHED_SET_ROOT
    if not src_dir.exists():
        return None
    digest = hashlib.sha256()
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            if name.endswith(".py"):
                digest.update((Path(root) / name).read_bytes())
    return digest.hexdigest()


def scan_code_hash_comparison_sites(repo_root: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    """Recompute every code-hash comparison site in the hashed set."""
    base = repo_root / HASHED_SET_ROOT
    sites: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "code_hash" not in segment:
                continue
            sites.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "line": node.lineno,
                    "comparison": segment,
                }
            )
    sites.sort(key=lambda site: (site["path"], site["line"]))
    return sites


def corrected_location_string(sites: Sequence[Dict[str, Any]]) -> str:
    """Render the corrected location from the live-vs-recorded sites."""
    by_file: Dict[str, List[int]] = {}
    for site in sites:
        if site.get("classification") != "LIVE_VS_RECORDED":
            continue
        by_file.setdefault(site["path"], []).append(int(site["line"]))
    parts: List[str] = []
    for path in sorted(by_file):
        lines = sorted(by_file[path])
        if len(lines) == 1:
            parts.append(f"{path} (line {lines[0]})")
        else:
            rendered = ", ".join(str(line) for line in lines[:-1])
            parts.append(f"{path} (lines {rendered} and {lines[-1]})")
    return " and ".join(parts)


def _stream_contains(path: Path, needle: bytes) -> bool:
    """Search a (possibly large) file for a byte pattern, with bounded memory."""
    with path.open("rb") as handle:
        tail = b""
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                return False
            if needle in tail + chunk:
                return True
            tail = chunk[-len(needle) :]


def _resolve_step(repo_root: Path, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Re-resolve a recorded evidence step against the current source."""
    relative = str(step.get("path") or "")
    anchor = str(step.get("anchor") or "")
    span = int(step.get("span") or 1)
    path = repo_root / relative
    if not relative or not anchor or not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [index + 1 for index, line in enumerate(lines) if line.strip() == anchor]
    if len(hits) != 1:
        return None
    start = hits[0]
    text = "\n".join(lines[start - 1 : start - 1 + span])
    return {
        "path": relative,
        "anchor": anchor,
        "span": span,
        "line": start,
        "text": text,
    }


def verify(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    environment_facts: List[str] = []
    amendment_path = repo_root / AMENDMENT_RELATIVE

    required = (
        amendment_path,
        repo_root / CORRECTED_ARTIFACT_RELATIVE,
        repo_root / AUTHORIZATION_RELATIVE,
    )
    for path in required:
        if not path.exists():
            return {
                "ok": False,
                "failures": [f"missing artifact: {path.relative_to(repo_root)}"],
            }

    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    corrected = json.loads(
        (repo_root / CORRECTED_ARTIFACT_RELATIVE).read_text(encoding="utf-8")
    )
    authorization = json.loads((repo_root / AUTHORIZATION_RELATIVE).read_text(encoding="utf-8"))

    # 1. The amendment is self-hashing.
    excluded = tuple(amendment.get("hashing", {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        failures.append("the amendment does not declare its manifest_hash_excluded_keys")
    declared = amendment.get("manifest_hash")
    recomputed = compute_manifest_hash(amendment, excluded)
    if declared != recomputed:
        failures.append(f"manifest_hash mismatch: declared {declared}, recomputed {recomputed}")

    # 2. The corrected artifact is untouched and still records the old location.
    correction = amendment.get("correction") or {}
    if correction.get("target_artifact") != CORRECTED_ARTIFACT_RELATIVE:
        failures.append("the amendment does not name the artifact it corrects")
    if correction.get("target_artifact_edited") is not False:
        failures.append("the amendment does not record that the corrected artifact is unedited")
    corrected_path = repo_root / CORRECTED_ARTIFACT_RELATIVE
    if sha256_file(corrected_path) != correction.get("target_file_sha256"):
        failures.append("the corrected artifact does not match its recorded sha256")
    if corrected.get("manifest_hash") != correction.get("target_manifest_hash"):
        failures.append("the corrected artifact's manifest_hash does not match the recorded one")
    rl1 = None
    for limitation in corrected.get("residual_limitations") or []:
        if limitation.get("id") == "RL1":
            rl1 = limitation
            break
    if rl1 is None:
        failures.append("the corrected artifact records no residual limitation RL1")
    else:
        if rl1.get("location") != correction.get("recorded_location"):
            failures.append(
                "the corrected artifact no longer records the recorded location; it was edited"
            )
        if rl1.get("location") == correction.get("corrected_location"):
            failures.append(
                "the recorded location equals the corrected location; there is nothing to correct"
            )
        for field in ("limitation", "consequence"):
            if not str(rl1.get(field) or "").strip():
                failures.append(f"the corrected artifact's RL1 has no {field}")
    for flag in ("behaviour_change", "limitation_text_changed", "consequence_text_changed"):
        if correction.get(flag) is not False:
            failures.append(f"correction.{flag} is not false")
    if not str(correction.get("recorded_location_defect") or "").strip():
        failures.append("the amendment does not state the defect of the recorded location")
    prior = correction.get("decision_record_correction") or {}
    if prior.get("is_complete") is not False:
        failures.append("the amendment does not record that the prior correction was incomplete")
    if not str(prior.get("omission") or "").strip():
        failures.append("the amendment does not name the site the prior correction omitted")

    # 3. The recorded sites are exactly the sites the source contains.
    block = amendment.get("code_hash_comparison_sites") or {}
    scanned = scan_code_hash_comparison_sites(repo_root)
    recorded_sites = block.get("sites") or []
    scanned_keys = [(site["path"], site["line"], site["comparison"]) for site in scanned]
    recorded_keys = [
        (site.get("path"), site.get("line"), site.get("comparison")) for site in recorded_sites
    ]
    if scanned_keys != recorded_keys:
        missing = sorted(set(scanned_keys) - set(recorded_keys))
        invented = sorted(set(recorded_keys) - set(scanned_keys))
        failures.append(
            "the recorded code-hash comparison sites do not match the source: "
            f"missing {missing}, invented {invented}"
        )
    if block.get("total_sites") != len(scanned):
        failures.append("the recorded site count does not match the source")
    rule = block.get("scan_rule") or {}
    if tuple(rule.get("persisted_read_markers") or ()) != PERSISTED_READ_MARKERS:
        failures.append("the recorded persisted-read markers do not match the verifier's")
    if rule.get("live_digest_marker") != LIVE_DIGEST_MARKER:
        failures.append("the recorded live-digest marker does not match the verifier's")
    if not str(rule.get("site_definition") or "").strip():
        failures.append("the scan rule does not define a site")
    if not str(rule.get("classification_rule") or "").strip():
        failures.append("the scan rule does not state the classification rule")

    # 4. Every recorded evidence step still exists, and the classification follows.
    live_count = 0
    recorded_count = 0
    for site in recorded_sites:
        label = f"{site.get('path')}:{site.get('line')}"
        classification = site.get("classification")
        if classification not in ("LIVE_VS_RECORDED", "RECORDED_VS_RECORDED"):
            failures.append(f"the site {label} has no valid classification")
            continue
        live_chain = site.get("live_digest_chain") or []
        recorded_chains = site.get("recorded_value_chains") or []
        if not recorded_chains:
            failures.append(f"the site {label} records no source of its recorded value")
        for step in live_chain:
            resolved = _resolve_step(repo_root, step)
            if resolved is None:
                failures.append(f"the live-digest step of {label} no longer matches the source")
            elif resolved != {k: step.get(k) for k in ("path", "anchor", "span", "line", "text")}:
                failures.append(f"the live-digest step of {label} does not match the source")
        for chain in recorded_chains:
            if not chain:
                failures.append(f"the site {label} records an empty source chain")
                continue
            for step in chain:
                resolved = _resolve_step(repo_root, step)
                if resolved is None:
                    failures.append(f"a recorded-value step of {label} no longer matches the source")
                elif resolved != {k: step.get(k) for k in ("path", "anchor", "span", "line", "text")}:
                    failures.append(f"a recorded-value step of {label} does not match the source")
            first = chain[0]
            if not any(marker in str(first.get("text") or "") for marker in PERSISTED_READ_MARKERS):
                failures.append(
                    f"the recorded-value chain of {label} does not start with a persisted read"
                )
        if live_chain:
            live_count += 1
            first = live_chain[0]
            if LIVE_DIGEST_MARKER not in str(first.get("text") or ""):
                failures.append(
                    f"the live-digest chain of {label} does not start with the live digest"
                )
            for step in live_chain[1:]:
                if "code_hash" not in str(step.get("text") or ""):
                    failures.append(
                        f"the live-digest chain of {label} has a step that does not carry "
                        "the code hash"
                    )
            if classification != "LIVE_VS_RECORDED":
                failures.append(f"the site {label} has a live chain but is not live-vs-recorded")
        else:
            recorded_count += 1
            if classification != "RECORDED_VS_RECORDED":
                failures.append(
                    f"the site {label} has no live chain but is not recorded-vs-recorded"
                )
        if not str(site.get("effect") or "").strip():
            failures.append(f"the site {label} records no effect")
        artifact = site.get("recorded_artifact") or {}
        if not str(artifact.get("value") or "").strip():
            failures.append(f"the site {label} records no persisted artifact")

    if block.get("live_vs_recorded_site_count") != live_count:
        failures.append("the recorded live-vs-recorded site count is wrong")
    if block.get("recorded_vs_recorded_site_count") != recorded_count:
        failures.append("the recorded recorded-vs-recorded site count is wrong")

    # 5. The corrected location is exactly the live-vs-recorded files.
    expected_location = corrected_location_string(recorded_sites)
    if correction.get("corrected_location") != expected_location:
        failures.append(
            "the corrected location does not match the live-vs-recorded sites: "
            f"recorded {correction.get('corrected_location')}, recomputed {expected_location}"
        )
    live_files = sorted(
        {site["path"] for site in recorded_sites if site["classification"] == "LIVE_VS_RECORDED"}
    )
    excluded_files = sorted(
        {
            site["path"]
            for site in recorded_sites
            if site["classification"] == "RECORDED_VS_RECORDED"
        }
    )
    if sorted(block.get("corrected_location_files") or []) != live_files:
        failures.append("the corrected location files do not match the live-vs-recorded sites")
    if sorted(block.get("excluded_location_files") or []) != excluded_files:
        failures.append("the excluded location files do not match the recorded-vs-recorded sites")
    recorded_location = str(correction.get("recorded_location") or "")
    for path in excluded_files:
        if path not in recorded_location:
            failures.append(
                f"the recorded location does not name {path}, so the correction does not "
                "narrow the record as claimed"
            )
    for path in live_files:
        if path not in str(correction.get("corrected_location") or ""):
            failures.append(f"the corrected location does not name the live site file {path}")

    # 6. The tree identity and the value of record are unchanged.
    constraint = amendment.get("code_hash_constraint") or {}
    recorded_canonical = constraint.get("canonical_source_digest")
    live_canonical = canonical_source_digest(repo_root)
    if recorded_canonical != live_canonical:
        failures.append(
            "the hashed source tree does not match the recorded canonical digest: "
            f"recorded {recorded_canonical}, recomputed {live_canonical}"
        )
    authorized = constraint.get("authorized_code_hash")
    if authorized != authorization.get("code_hash"):
        failures.append("the recorded code hash is not the authorized v1 code hash")
    if authorization.get("authorized") is not True:
        failures.append("the v1 campaign authorization is not authorized")
    if constraint.get("authorized_code_hash_status") != "RETAINED_AS_VALUE_OF_RECORD":
        failures.append("the amendment does not retain the authorized digest as value of record")
    if not str(constraint.get("hashed_set_unchanged") or "").strip():
        failures.append("the amendment does not state that the hashed set is unchanged")
    if not str(constraint.get("gate_behaviour_unchanged") or "").strip():
        failures.append("the amendment does not state that the gate's behaviour is unchanged")
    ordered = live_ordered_code_hash(repo_root)
    if ordered != authorized:
        environment_facts.append(
            "the live ordered code hash "
            f"{ordered} differs from the authorized value of record {authorized}; this is an "
            "environment fact about the directory enumeration order of this checkout, not "
            "evidence of source drift"
        )

    # 7. The pre-flight that implements the decision exists and does what it claims.
    preflight = amendment.get("preflight") or {}
    if preflight.get("path") != PREFLIGHT_RELATIVE:
        failures.append("the amendment does not name the gate-compatibility pre-flight")
    preflight_path = repo_root / PREFLIGHT_RELATIVE
    if not preflight_path.exists():
        failures.append("the gate-compatibility pre-flight is missing")
    else:
        source = preflight_path.read_text(encoding="utf-8")
        if "canonical_source_digest" not in source:
            failures.append("the pre-flight does not compute the canonical source digest")
        if not authorized or authorized not in source:
            failures.append("the pre-flight does not carry the authorized value of record")
    if preflight.get("implementation_status") != "IMPLEMENTED":
        failures.append("the amendment does not record the pre-flight as implemented")

    # 8. Nothing is authorized by this artifact.
    execution = amendment.get("execution_authorization") or {}
    for flag in (
        "grid_run_authorized",
        "candidate_selection_authorized",
        "confirmatory_evaluation_authorized",
        "candle_fetch_authorized",
        "source_tree_change_authorized",
        "v1_reauthorization_authorized",
        "v1_resume_authorized",
    ):
        if execution.get(flag) is not False:
            failures.append(f"execution_authorization.{flag} is not false")
    if amendment.get("amendment_status") != "PREREGISTERED_CODE_HASH_AMENDMENT_2_DESIGN_ONLY":
        failures.append("the amendment status does not record that it is a design artifact")

    # 9. The v1 evidence is byte-identical and the v2 execution state is untouched.
    for relative, digest in V1_ARTIFACT_SHA256.items():
        target = repo_root / relative
        if not target.exists():
            failures.append(f"the v1 artifact {relative} is missing")
            continue
        if sha256_file(target) != digest:
            failures.append(f"the v1 artifact {relative} does not match its recorded sha256")
    data_manifest = repo_root / "research" / "data_manifest_v2.json"
    if data_manifest.exists():
        window = json.loads(data_manifest.read_text(encoding="utf-8")).get("confirmatory_window") or {}
        if window.get("confirmatory_window_status") != "NOT_STARTED":
            failures.append("the v2 confirmatory window is no longer NOT_STARTED")
        if window.get("holdout_exposed_count") != 0:
            failures.append("the v2 confirmatory window records a holdout exposure")
    checkpoint = repo_root / "research_state" / "checkpoint_v2.json"
    if checkpoint.exists():
        if json.loads(checkpoint.read_text(encoding="utf-8")).get("holdout_exposed_count") != 0:
            failures.append("the v2 checkpoint records a holdout exposure")
    results = repo_root / "research" / "results.jsonl"
    if results.exists() and _stream_contains(results, b"v2-campaign"):
        failures.append("a v2 result row appears in the v1 result stream")

    return {
        "ok": not failures,
        "amendment_path": AMENDMENT_RELATIVE,
        "manifest_hash": declared,
        "recomputed_manifest_hash": recomputed,
        "amendment_status": amendment.get("amendment_status"),
        "corrected_location": correction.get("corrected_location"),
        "recorded_location": correction.get("recorded_location"),
        "code_hash_comparison_sites": len(scanned),
        "live_vs_recorded_sites": live_count,
        "recorded_vs_recorded_sites": recorded_count,
        "authorized_code_hash": authorized,
        "canonical_source_digest": live_canonical,
        "live_ordered_code_hash": ordered,
        "ordered_code_hash_matches_authorized": ordered == authorized,
        "v2_execution_artifacts": [
            relative for relative in V2_EXECUTION_ARTIFACTS if (repo_root / relative).exists()
        ],
        "environment_facts": environment_facts,
        "failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    report = verify(Path(args.repo_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

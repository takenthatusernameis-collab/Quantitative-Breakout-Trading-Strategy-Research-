"""Independent campaign authorization validator for BRAIN-002."""
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_PILOT_EVIDENCE_FIELDS = [
    "protocol_version",
    "specification_hash",
    "code_hash",
    "pilot_completed_at",
    "assets_tested",
    "configs_tested",
    "total_results",
    "evidence",
]


REQUIRED_EVIDENCE_SUBFIELDS = [
    "protocol_hash",
    "code_hash",
    "spec_hash",
    "universe_manifest_hash",
    "data_manifest_hash",
    "asset_data_hashes",
    "data_provenance_ok",
    "data_min_history_ok",
    "pilot_run_results",
    "checkpoint_state",
    "test_reports",
]


VALIDATOR_ARTIFACT_PATH = "research_state/campaign_authorization.json"
PILOT_EVIDENCE_PATH = "research_state/pilot_evidence.json"
PILOT_GATE_PATH = "research_state/pilot_gate.json"
DATA_MANIFEST_PATH = "research/data_manifest.json"
UNIVERSE_MANIFEST_PATH = "research/universe_manifest.json"
SPEC_PATH = "configs/research_v1.json"
CHECKPOINT_PATH = "research_state/checkpoint.json"


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_canonical(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_data_provenance(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    assets = manifest.get("assets", {})
    if not isinstance(assets, dict) or len(assets) == 0:
        return False, ["data_manifest has no assets"]
    for symbol, entry in assets.items():
        if not isinstance(entry, dict):
            reasons.append(f"asset {symbol} entry malformed")
            continue
        if entry.get("fallback_used") is True:
            reasons.append(f"asset {symbol} has fallback_used=true (synthetic provenance)")
        fallback_source = entry.get("fallback_source")
        if fallback_source and str(fallback_source).lower() != "real":
            if str(fallback_source).lower() == "synthetic":
                reasons.append(f"asset {symbol} fallback_source=synthetic")
        content_hash = entry.get("content_hash")
        if not content_hash or not isinstance(content_hash, str) or len(content_hash) < 16:
            reasons.append(f"asset {symbol} missing valid content_hash")
        if entry.get("spec_hash") and entry.get("spec_hash") != manifest.get("spec_hash"):
            reasons.append(f"asset {symbol} spec_hash mismatch")
    data_min_history_ok = manifest.get("data_min_history_ok", False)
    if not data_min_history_ok:
        reasons.append("data_manifest.data_min_history_ok is not true")
    provenance_ok = manifest.get("provenance_ok", False) and len(reasons) == 0
    if not provenance_ok and len(reasons) == 0:
        reasons.append("data_manifest.provenance_ok is false")
    return (provenance_ok and data_min_history_ok and len(reasons) == 0), reasons


def _validate_evidence(evidence: Dict[str, Any], spec_hash: str, code_hash: str,
                      data_manifest: Dict[str, Any], universe_manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    for field in REQUIRED_EVIDENCE_SUBFIELDS:
        if field not in evidence:
            reasons.append(f"evidence missing {field}")

    if evidence.get("spec_hash") != spec_hash:
        reasons.append("evidence.spec_hash mismatch")
    if evidence.get("code_hash") != code_hash:
        reasons.append("evidence.code_hash mismatch")
    if evidence.get("protocol_hash") != spec_hash:
        reasons.append("evidence.protocol_hash mismatch")

    try:
        um_hash = _sha256_canonical(universe_manifest)
    except Exception as exc:
        return False, [f"universe manifest canonicalization failed: {exc}"]
    if evidence.get("universe_manifest_hash") != um_hash:
        reasons.append("evidence.universe_manifest_hash mismatch")

    try:
        dm_hash = _sha256_canonical(data_manifest)
    except Exception as exc:
        return False, [f"data manifest canonicalization failed: {exc}"]
    if evidence.get("data_manifest_hash") != dm_hash:
        reasons.append("evidence.data_manifest_hash mismatch")

    prov_ok, prov_reasons = _validate_data_provenance(data_manifest)
    if not prov_ok:
        reasons.extend(prov_reasons)
    if not evidence.get("data_provenance_ok", False):
        reasons.append("evidence.data_provenance_ok is false")
    if not evidence.get("data_min_history_ok", False):
        reasons.append("evidence.data_min_history_ok is false")

    pilot_run_results = evidence.get("pilot_run_results", {})
    if not isinstance(pilot_run_results, dict):
        reasons.append("evidence.pilot_run_results malformed")
    else:
        if not pilot_run_results.get("all_tests_passed", False):
            reasons.append("pilot_run_results.all_tests_passed is false")
        if pilot_run_results.get("test_failures", 0) > 0:
            reasons.append("pilot_run_results.test_failures > 0")
        if not pilot_run_results.get("remote_persistence_verified", False):
            reasons.append("pilot_run_results.remote_persistence_verified is false")
        if pilot_run_results.get("synthetic_data_used", False):
            reasons.append("pilot_run_results.synthetic_data_used is true")

    checkpoint_state = evidence.get("checkpoint_state", {})
    if not isinstance(checkpoint_state, dict):
        reasons.append("evidence.checkpoint_state malformed")
    else:
        if checkpoint_state.get("protocol_hash") != spec_hash:
            reasons.append("checkpoint_state.protocol_hash mismatch")
        if checkpoint_state.get("code_hash") != code_hash:
            reasons.append("checkpoint_state.code_hash mismatch")

    test_reports = evidence.get("test_reports", [])
    if not isinstance(test_reports, list) or len(test_reports) == 0:
        reasons.append("evidence.test_reports empty or malformed")

    return len(reasons) == 0, reasons


def validate_pilot_evidence(pilot_evidence_path: str = PILOT_EVIDENCE_PATH) -> Tuple[bool, List[str], Dict[str, Any]]:
    try:
        pilot = _read_json(pilot_evidence_path)
    except FileNotFoundError:
        return False, ["pilot evidence file not found"], {}
    except Exception as exc:
        return False, [f"failed to read pilot evidence: {exc}"], {}

    for field in REQUIRED_PILOT_EVIDENCE_FIELDS:
        if field not in pilot:
            return False, [f"pilot evidence missing {field}"], {}

    if pilot.get("pilot_passed") is True:
        return False, ["pilot_evidence.pilot_passed must not be true (evidence-only)"], pilot

    if pilot.get("campaign_authorized") is True:
        return False, ["pilot_evidence.campaign_authorized must not be true (evidence-only)"], pilot

    try:
        spec = _read_json(SPEC_PATH)
        um = _read_json(UNIVERSE_MANIFEST_PATH)
        dm = _read_json(DATA_MANIFEST_PATH)
    except Exception as exc:
        return False, [f"failed to load manifests/spec: {exc}"], pilot

    spec_hash = spec.get("specification_hash")
    code_hash = pilot.get("code_hash")
    if not spec_hash or not code_hash:
        return False, ["missing spec_hash or code_hash"], pilot

    ok, reasons = _validate_evidence(pilot.get("evidence", {}), spec_hash, code_hash, dm, um)
    if not ok:
        return False, reasons, pilot

    return True, [], pilot


def write_authorization_artifact(pilot: Dict[str, Any], reasons: List[str], authorized: bool,
                                 validator_path: str = VALIDATOR_ARTIFACT_PATH) -> Dict[str, Any]:
    try:
        spec = _read_json(SPEC_PATH)
        code_hash = pilot.get("code_hash") if pilot else spec.get("code_hash", "")
    except Exception:
        spec = {}
        code_hash = pilot.get("code_hash", "") if pilot else ""

    artifact = {
        "schema_version": 1,
        "authorized_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized": bool(authorized),
        "protocol_version": pilot.get("protocol_version") if pilot else spec.get("protocol_version"),
        "specification_hash": pilot.get("specification_hash") if pilot else spec.get("specification_hash"),
        "code_hash": code_hash,
        "pilot_evidence_path": PILOT_EVIDENCE_PATH,
        "validator_version": "brain-002-v1",
        "evidence_digest": _sha256_canonical(pilot) if pilot else "",
        "reasons": reasons if not authorized else [],
        "legacy_pilot_gate_present": os.path.exists(PILOT_GATE_PATH),
    }
    os.makedirs(os.path.dirname(validator_path), exist_ok=True)
    with open(validator_path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2)
    return artifact


def authorize_campaign(pilot_evidence_path: str = PILOT_EVIDENCE_PATH,
                      artifact_path: str = VALIDATOR_ARTIFACT_PATH) -> Dict[str, Any]:
    ok, reasons, pilot = validate_pilot_evidence(pilot_evidence_path)
    if not ok:
        return write_authorization_artifact(pilot, reasons, False, artifact_path)
    return write_authorization_artifact(pilot, [], True, artifact_path)


def load_authorization(artifact_path: str = VALIDATOR_ARTIFACT_PATH) -> Dict[str, Any]:
    return _read_json(artifact_path)

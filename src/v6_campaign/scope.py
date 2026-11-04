"""Fail-closed authorization and frozen-scope checks for v6 selection."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from .errors import ScopeError
from .identity import code_identity_document, run_code_identity

V6_SELECTION_AUTHORIZATION = "configs/research_v6_selection_authorization_1.json"
V6_BINDING_AMENDMENT = "configs/research_v6_selection_execution_binding_1.json"
FROZEN_PATHS = (
 "research/shards","research/shards_v2","research/shards_v3","research/shards_v4","research/shards_v5",
 "research/ledger.json","research/ledger_v2.json","research/ledger_v3.json","research/ledger_v4.json","research/ledger_v5.json",
 "research/results_manifest.json","research/results_manifest_v2.json","research/results_manifest_v3.json","research/results_manifest_v4.json","research/results_manifest_v5.json",
 "research/results.jsonl","research/results_v2.jsonl","research/results_v3.jsonl","research/results_v4.jsonl","research/results_v5.jsonl",
 "research_state/checkpoint.json","research_state/checkpoint_v2.json","research_state/checkpoint_v3.json","research_state/checkpoint_v4.json","research_state/checkpoint_v5.json",
)
# The v6 runner imports this name from the v5 package contract; it aliases the
# expanded v1-v5 denylist above and never includes v6 result paths.
FORBIDDEN_PATHS = FROZEN_PATHS

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def manifest_digest(document: Dict[str, Any]) -> str:
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys")
                     or (document.get("hashing") or {}).get("excluded_keys")
                     or ("manifest_hash",))
    body = {k:v for k,v in document.items() if k not in excluded}
    for dotted in (k for k in excluded if "." in k):
        head, _, tail = dotted.partition(".")
        if isinstance(body.get(head), dict):
            body[head] = {k:v for k,v in body[head].items() if k != tail}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()

def load_json(path: Path) -> Dict[str, Any]:
    value=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ScopeError(f"{path} must be a JSON object")
    return value

def dig(document: Any, dotted: str) -> Any:
    value=document
    for key in dotted.split("."):
        if not isinstance(value,dict) or key not in value: return None
        value=value[key]
    return value

def authorization_output_paths(authorization: Dict[str, Any]) -> Dict[str, str]:
    return {k:str(v) for k,v in (authorization.get("authorized_run",{}).get("paths") or {}).items()
            if k in {"shards_dir","ledger","results_manifest","results_stream","checkpoint"}}

def assert_no_forbidden_output(paths: Dict[str, str]) -> None:
    for name,path in paths.items():
        p=Path(path)
        for banned in FROZEN_PATHS:
            if p == Path(banned) or Path(banned) in p.parents:
                raise ScopeError(f"v6 output {name} points to frozen artifact {banned}")

def _require(condition: bool, message: str) -> None:
    if not condition: raise ScopeError(message)

def validate_v6_scope(repo_root: Path) -> Dict[str, Any]:
    root=Path(repo_root)
    paths={
      "spec_v1":"configs/research_v1.json","spec_v6":"configs/research_v6.json",
      "freeze":"configs/research_v6_candidate_freeze.json","universe":"research/universe_manifest_v6.json",
      "data":"research/data_manifest_v6.json","execution":"configs/research_v6_execution.json",
      "selection_authorization":V6_SELECTION_AUTHORIZATION,"binding":V6_BINDING_AMENDMENT,
      "config":"research/config_manifest.json",
    }
    docs={key:load_json(root/rel) for key,rel in paths.items()}
    v1,v6,freeze,universe,data,execution,auth,binding,config=(docs[k] for k in
        ("spec_v1","spec_v6","freeze","universe","data","execution","selection_authorization","binding","config"))
    _require(v6.get("specification_hash")==hashlib.sha256(canonical({k:v for k,v in v6.items() if k!="specification_hash"}).encode("utf-8")).hexdigest(),
             "v6 specification hash does not recompute")
    for name,doc in (("candidate freeze",freeze),("v6 universe manifest",universe),("v6 data manifest",data),("selection authorization",auth),("execution binding",binding)):
        _require(doc.get("manifest_hash")==manifest_digest(doc),f"{name} manifest_hash does not recompute")
    _require(freeze.get("specification_hash")==v6.get("specification_hash"),"freeze is not bound to the v6 specification")
    _require(freeze.get("universe_manifest_hash")==universe.get("manifest_hash"),"freeze is not bound to the v6 universe manifest")
    _require(freeze.get("data_manifest_hash")==data.get("manifest_hash"),"freeze is not bound to the v6 data manifest")
    candidates=[str(x.get("binance_pair")) for x in freeze.get("candidates",[]) if x.get("validated") is True]
    eligible=[str(x.get("binance_pair") or f"{x.get('symbol')}USDT") for x in universe.get("eligible_assets",[]) if x.get("validated") is True and x.get("exclusion_reason") is None]
    _require(candidates and candidates==eligible,"frozen candidate order/set differs from validated v6 universe")
    auth_run=auth.get("authorized_run") or {}
    _require(auth_run.get("authorized") is True and auth_run.get("max_runs")==1,"original selection authorization does not authorize exactly one run")
    _require(auth.get("manifest_hash")==binding.get("amends",{}).get("manifest_hash"),"binding amendment names another selection authorization manifest hash")
    _require(binding.get("amends",{}).get("path")==V6_SELECTION_AUTHORIZATION,"binding amendment does not name the frozen selection authorization")
    _require(binding.get("amends",{}).get("sha256")==sha256_file(root/V6_SELECTION_AUTHORIZATION),"binding amendment names another authorization file digest")
    _require(binding.get("binding_status")=="IMPLEMENTATION_BOUND_NOT_RUN","execution binding is not marked as implementation-only")
    import sys
    sys.path.insert(0, str(root))
    from scripts.v6_universe_rules import (
        resolve_effective_v6_execution_protocol,
        verify_effective_v6_selection_authorization,
        verify_v6_historical_execution_authorization,
    )
    try:
        effective_execution = resolve_effective_v6_execution_protocol(root)
        verify_v6_historical_execution_authorization(root)
        effective_auth = verify_effective_v6_selection_authorization(root, effective_execution)
    except Exception as exc:
        raise ScopeError(f"effective v6 authorization chain failed closed: {exc}") from exc
    _require(effective_auth.get("selection_authorization_manifest_hash")==auth.get("manifest_hash"),
             "effective execution amendment does not resolve to the frozen selection authorization")
    identity=code_identity_document(root)
    live_identity=identity
    recorded=binding.get("code_identity") or {}
    _require(recorded.get("algorithm")==live_identity["algorithm"],"binding uses another source digest algorithm")
    _require(recorded.get("hashed_set_digest")==live_identity["hashed_set_digest"],"frozen engine source digest changed")
    _require(recorded.get("execution_path_digest")==live_identity["execution_path_digest"],"v6 execution path digest changed")
    _require(recorded.get("run_code_identity")==live_identity["run_code_identity"],"composite v6 run identity does not recompute")
    _require(binding.get("execution_path",{}).get("entry_point")=="src/v6_campaign/runner.py:run_selection","binding names another selection entry point")
    _require(binding.get("execution_path",{}).get("outside_hashed_set") is True,"v6 package is not bound outside hashed engine")
    _require(binding.get("execution_path",{}).get("canonical_source_digest")==live_identity["execution_path_digest"],
             "execution path digest in the binding does not match its code identity")
    binding_scope = binding.get("scope_binding") or {}
    for field, expected in (
        ("candidate_freeze_hash", freeze.get("manifest_hash")),
        ("universe_manifest_hash", universe.get("manifest_hash")),
        ("data_manifest_hash", data.get("manifest_hash")),
        ("selection_rule_sha256", rule_hash if "rule_hash" in locals() else hashlib.sha256(canonical(v1.get("selection") or {}).encode("utf-8")).hexdigest()),
        ("development_boundary_utc", spec_cutoff if "spec_cutoff" in locals() else str(v6.get("holdout",{}).get("development_cutoff_utc"))),
    ):
        _require(binding_scope.get(field)==expected, f"execution binding has a stale {field}")
    _require(binding_scope.get("candidate_pairs")==candidates, "execution binding has another candidate list")
    modules = sorted(p.relative_to(root / "src/v6_campaign").as_posix()
                     for p in (root / "src/v6_campaign").rglob("*.py"))
    _require(binding.get("execution_path",{}).get("modules")==modules,
             "binding module inventory differs from the live v6 execution package")
    binding_authority = binding.get("authority") or {}
    _require(binding_authority.get("max_runs")==1, "implementation binding changes the one-run budget")
    for flag in ("confirmatory_evaluation_authorized","candle_fetch_authorized","second_v6_selection_run_authorized","amendment_of_a_frozen_artifact_authorized","holdout_reads_authorized"):
        _require(binding_authority.get(flag) is False,
                 f"implementation binding improperly grants {flag}")
    _require(binding_authority.get("single_selection_run_authority_source")==V6_SELECTION_AUTHORIZATION,
             "implementation binding does not retain the original single-run authorization as sole authority")
    not_auth=auth.get("not_authorized") or {}
    for flag in ("confirmatory_evaluation_authorized","candle_fetch_authorized","v1_reauthorization_authorized","second_v6_selection_run_authorized","amendment_of_a_frozen_artifact_authorized"):
        _require(not_auth.get(flag) is False,f"the original authorization no longer keeps {flag} false")
    rule=v1.get("selection") or {}
    rule_hash=hashlib.sha256(canonical(rule).encode("utf-8")).hexdigest()
    _require(auth_run.get("selection_rule",{}).get("selection_block_sha256")==rule_hash,"selection rule differs from unchanged v1")
    spec_cutoff=str(v6.get("holdout",{}).get("development_cutoff_utc"))
    boundary=auth_run.get("data_boundary") or {}
    _require(boundary.get("candles_before_utc")==spec_cutoff,"authorization development boundary differs from v6 specification")
    _require(freeze.get("data_boundary",{}).get("development_cutoff_utc")==spec_cutoff,"freeze development boundary differs from v6 specification")
    _require(auth_run.get("scope",{}).get("binance_pairs")==candidates,"selection auth scope is not the frozen candidate list")
    _require(auth_run.get("scope",{}).get("bound_to_data_hash")==data.get("manifest_hash"),"selection auth is not bound to the v6 data manifest")
    _require(auth_run.get("scope",{}).get("bound_to_universe_hash")==universe.get("manifest_hash"),"selection auth is not bound to the v6 universe manifest")
    _require(auth_run.get("bounds",{}).get("max_assets")==len(candidates),"selection asset bound differs from frozen scope")
    _require(auth_run.get("bounds",{}).get("max_configs_per_asset")==int(config.get("total_configurations",0)),"authorized config bound differs from config manifest")
    _require(auth_run.get("bounds",{}).get("max_total_config_units")==len(candidates)*int(config.get("total_configurations",0)),"authorized total config bound differs from frozen grid")
    _require(auth_run.get("paths",{}).get("shards_dir")=="research/shards_v6","selection outputs not isolated to v6 shards")
    expected_paths = {
      "shards_dir":"research/shards_v6","ledger":"research/ledger_v6.json",
      "results_manifest":"research/results_manifest_v6.json",
      "results_stream":"research/results_v6.jsonl","checkpoint":"research_state/checkpoint_v6.json"
    }
    for name, expected in expected_paths.items():
        _require(auth_run.get("paths",{}).get(name)==expected,
                 f"v6 authorized {name} path is not the isolated v6 namespace")
    output_paths=authorization_output_paths(auth)
    assert_no_forbidden_output(output_paths)
    code_ident={
      "algorithm":live_identity["algorithm"],
      "portable":True,
      "hashed_set_root":"src/breakout_research",
      "hashed_set_digest":live_identity["hashed_set_digest"],
      "execution_path_root":"src/v6_campaign",
      "execution_path_digest":live_identity["execution_path_digest"],
      "run_code_identity":live_identity["run_code_identity"],
      "authorized_code_hash":auth_run.get("code_identity",{}).get("authorized_code_hash"),
    }
    return {
      **docs,
      "scope":{"binance_pairs":candidates,"count":len(candidates),"excluded_after_validation":{},"confirmatory_window_start_utc":freeze["confirmatory_window"]["opens_utc"],"effective_data_boundary_utc":spec_cutoff,"development_cutoff_utc":spec_cutoff},
      "bounds":dict(auth_run["bounds"]),
      "run_id":str(auth_run["run_id"]),"campaign_id":str(auth_run["campaign_id"]),"run_phase":str(auth_run["run_phase"]),
      "code_identity":code_ident,"selection_rule":rule,"selection_rule_digest":rule_hash,
      "authorization_manifest_hash":auth["manifest_hash"],
      "paths":output_paths,
    }

__all__=["FORBIDDEN_PATHS","FROZEN_PATHS","assert_no_forbidden_output","authorization_output_paths","dig","load_json",
         "manifest_digest","sha256_file","validate_v6_scope"]

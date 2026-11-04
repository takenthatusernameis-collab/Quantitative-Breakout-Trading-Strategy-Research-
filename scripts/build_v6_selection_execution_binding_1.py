#!/usr/bin/env python3
"""Build the implementation-only binding for the v6 selection execution package.

This is a versioned addendum. It does not modify the frozen v6 selection
authorization, the execution protocol, its first amendment, or the hashed v1
engine. It binds the new isolated src/v6_campaign tree to the one selection
run already authorized by configs/research_v6_selection_authorization_1.json.
It grants no new run, confirmatory, fetch, or holdout-read authority.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from typing import Any, Dict
ROOT=Path(__file__).resolve().parent.parent
AUTH_REL="configs/research_v6_selection_authorization_1.json"
OUT_REL="configs/research_v6_selection_execution_binding_1.json"
CREATED_UTC="2026-11-04T16:00:00Z"
def canonical(value: Any) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def compute_manifest_hash(document: Dict[str,Any]) -> str:
    excluded=tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ("manifest_hash",))
    body={k:v for k,v in document.items() if k not in excluded}
    for dotted in (k for k in excluded if "." in k):
        head,_,tail=dotted.partition(".")
        if isinstance(body.get(head),dict): body[head]={k:v for k,v in body[head].items() if k!=tail}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
def build(repo_root: Path=ROOT) -> Dict[str,Any]:
    root=Path(repo_root)
    sys.path.insert(0,str(root/"src"))
    from v6_campaign.identity import code_identity_document
    auth=json.loads((root/AUTH_REL).read_text(encoding="utf-8"))
    if auth.get("manifest_hash")!=compute_manifest_hash(auth):
        raise SystemExit("the frozen v6 selection authorization does not recompute")
    run=auth.get("authorized_run") or {}
    if run.get("authorized") is not True or run.get("max_runs")!=1:
        raise SystemExit("the frozen v6 authorization does not permit exactly one selection run")
    package=root/"src/v6_campaign"
    if not package.is_dir() or not (package/"runner.py").is_file():
        raise SystemExit("the v6 selection execution package or entry point is missing")
    identity=code_identity_document(root)
    if identity["hashed_set_digest"] != (run.get("code_identity") or {}).get("hashed_set_digest"):
        raise SystemExit("the frozen v1 engine digest changed; no binding may be built")
    if identity["execution_path_digest"] is None:
        raise SystemExit("the v6 execution package contains no Python source files")
    modules=sorted(p.relative_to(package).as_posix() for p in package.rglob("*.py"))
    if "runner.py" not in modules or "scope.py" not in modules or "data.py" not in modules:
        raise SystemExit("the v6 selection package is incomplete")
    document={
      "artifact":"v6_selection_execution_binding",
      "artifact_version":"v6-selection-execution-binding-1",
      "protocol_version":"v6",
      "created_utc":CREATED_UTC,
      "binding_status":"IMPLEMENTATION_BOUND_NOT_RUN",
      "engineering_scope":{
        "basis":"explicit user instruction on 2026-11-04 to remove engineering bottlenecks on main",
        "purpose":"bind the isolated v6 selection execution implementation to the already-published one-run authorization",
        "hashed_v1_engine_modified":False,
        "frozen_v1_v5_artifacts_modified":False,
        "no_campaign_started":True,
        "no_market_data_read_by_builder":True,
        "no_provider_contact":True
      },
      "amends":{
        "path":AUTH_REL,
        "manifest_hash":auth["manifest_hash"],
        "sha256":sha256_file(root/AUTH_REL),
        "scope":"execution package identity only; the original authorization remains the sole authority for one bounded selection run"
      },
      "execution_path":{
        "package":"src/v6_campaign",
        "entry_point":"src/v6_campaign/runner.py:run_selection",
        "modules":modules,
        "outside_hashed_set":True,
        "hashed_set_root":"src/breakout_research",
        "canonical_source_digest":identity["execution_path_digest"],
        "engine_reused_unchanged":True
      },
      "code_identity":identity,
      "scope_binding":{
        "candidate_freeze_hash":run["scope"]["bound_to_freeze_hash"],
        "universe_manifest_hash":run["scope"]["bound_to_universe_hash"],
        "data_manifest_hash":run["scope"]["bound_to_data_hash"],
        "candidate_pairs":list(run["scope"]["binance_pairs"]),
        "selection_rule_sha256":run["selection_rule"]["selection_block_sha256"],
        "development_boundary_utc":run["data_boundary"]["candles_before_utc"]
      },
      "authority":{
        "single_selection_run_authority_source":AUTH_REL,
        "single_selection_run_authority_manifest_hash":auth["manifest_hash"],
        "max_runs":1,
        "confirmatory_evaluation_authorized":False,
        "candle_fetch_authorized":False,
        "second_v6_selection_run_authorized":False,
        "amendment_of_a_frozen_artifact_authorized":False,
        "holdout_reads_authorized":False
      },
      "hashing":{
        "algorithm":"sha256",
        "canonicalization":"json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)",
        "manifest_hash_excluded_keys":["manifest_hash"]
      }
    }
    document["manifest_hash"]=compute_manifest_hash(document)
    return document
def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",default=str(ROOT))
    parser.add_argument("--print",action="store_true",dest="print_only")
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args(argv)
    document=build(Path(args.repo_root))
    target=Path(args.repo_root)/OUT_REL
    rendered=json.dumps(document,indent=2,ensure_ascii=False)+"\n"
    if args.print_only:
        print(rendered,end="")
        return 0
    if args.check:
        if not target.is_file():
            print(f"missing binding artifact: {OUT_REL}")
            return 1
        existing=json.loads(target.read_text(encoding="utf-8"))
        if existing!=document:
            print("the committed binding does not match the live execution package")
            return 1
        print(f"verified {OUT_REL}: {document['manifest_hash']}")
        return 0
    if target.exists():
        print(f"refusing to overwrite {OUT_REL}; use --check or review a new versioned amendment")
        return 1
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(rendered,encoding="utf-8")
    print(f"wrote {OUT_REL}: {document['manifest_hash']}")
    return 0
if __name__=="__main__":
    raise SystemExit(main())

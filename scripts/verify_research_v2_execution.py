#!/usr/bin/env python3
import argparse, hashlib, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
def canonical(o): return json.dumps(o, sort_keys=True, separators=(",",":"), ensure_ascii=False)
def compute_hash(spec):
    body={k:v for k,v in spec.items() if k!="specification_hash"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()
def verify(repo_root=REPO_ROOT):
    failures=[]
    p=repo_root/"configs"/"research_v2_execution.json"
    spec=json.loads(p.read_text())
    if spec.get("specification_hash")!=compute_hash(spec): failures.append("hash mismatch")
    if spec.get("evaluation_scope",{}).get("count")!=18: failures.append("scope count")
    if not spec.get("selection_data_boundary",{}).get("v1_cycle0_units_mixed_forbidden"): failures.append("boundary")
    if spec.get("code_hash_constraint",{}).get("authorized_code_hash")!="2efd3b18fe3f42f42fbd97cce5825d2cfccc6e463a56c1fb8d25d891ab9c35b2": failures.append("code hash")
    return {"ok":not failures,"failures":failures}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",default=str(REPO_ROOT)); a=ap.parse_args()
    r=verify(Path(a.repo_root)); print(json.dumps(r,indent=2,sort_keys=True)); sys.exit(0 if r["ok"] else 1)
if __name__=="__main__": main()
EOF
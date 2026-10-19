#!/usr/bin/env python3
import json, hashlib, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(rel):
    with open(os.path.join(ROOT, rel)) as f: return json.load(f)
def canonical(o): return json.dumps(o, sort_keys=True, separators=(',',':'))
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def compute_hash(doc, excluded):
    body={k:v for k,v in doc.items() if k not in excluded}
    return sha256_bytes(canonical(body).encode())
def main():
    failures=[]
    amend=load('configs/research_v2_execution_amendment_1.json')
    excluded=tuple(amend.get('hashing',{}).get('manifest_hash_excluded_keys',[])) or ('manifest_hash',)
    recomputed=compute_hash(amend, excluded)
    if amend.get('manifest_hash')!=recomputed: failures.append(f"manifest_hash mismatch {amend.get('manifest_hash')} vs {recomputed}")
    if amend.get('amends',{}).get('file_hash')!='aa902aa935cfb71cce72bd643bb9685333860ec5470b02b12282c0f1659d67e6': failures.append('protocol hash reference wrong')
    if not amend.get('v2_selection_authorization',{}).get('no_execution', False): failures.append('no_execution must be true')
    if amend.get('v2_selection_authorization',{}).get('authorized', None) is not False: failures.append('authorized must be false (design only)')
    print(json.dumps({"ok": not failures, "failures": failures, "manifest_hash": amend.get('manifest_hash')}, indent=2))
    sys.exit(0 if not failures else 1)
if __name__=='__main__': main()
EOF
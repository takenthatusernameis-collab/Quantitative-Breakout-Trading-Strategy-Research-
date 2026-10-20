#!/usr/bin/env python3
import json, os, sys, hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def load(p):
    with open(p) as f: return json.load(f)

def canon_sha(obj, exclude=None):
    exclude = set(exclude or [])
    body = {k:v for k,v in obj.items() if k not in exclude}
    s = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(s).hexdigest()

def main():
    failures=[]
    try:
        dec = load(REPO/'configs/research_v2_code_hash_portability_decision.json')
    except Exception as e:
        print(json.dumps({'ok':False,'failures':[f'load_decision:{e}']}))
        sys.exit(1)
    # self-hash
    if dec.get('manifest_hash') != canon_sha(dec, dec.get('hashing',{}).get('manifest_hash_excluded_keys',[])):
        failures.append('self_hash_mismatch')
    # refs
    try:
        auth = load(REPO/'research_state/campaign_authorization.json')
        if auth.get('code_hash') != dec['references']['campaign_authorization']['code_hash']:
            failures.append('auth_code_hash_mismatch')
        if auth.get('authorized') is not True:
            failures.append('auth_not_authorized')
    except Exception as e:
        failures.append(f'auth:{e}')
    try:
        am1 = load(REPO/'configs/research_v2_execution_amendment_1.json')
        if am1.get('manifest_hash') != dec['references']['amendment_1']['manifest_hash']:
            failures.append('am1_hash_mismatch')
        if am1.get('code_hash_constraint',{}).get('canonical_source_digest') != dec['references']['amendment_1']['canonical_source_digest']:
            failures.append('canonical_digest_mismatch')
    except Exception as e:
        failures.append(f'am1:{e}')
    # decision semantics
    if dec.get('decision',{}).get('choice','').strip() != 'B. Keep the authorized code hash unchanged. Treat compute_code_hash() as order-dependent in value but treat the tree identity as portable via canonical_source_digest. Any verification that claims \'source modified\' must require both (a) the live ordered hash equals the authorized hash OR the canonical digest equals the recorded canonical digest AND (b) the set of files and their content digests match the canonical form. Do not change src/breakout_research/.':
        failures.append('decision_choice_mismatch')
    # no src changes implied
    if dec.get('implementation_rules',{}).get('forbidden') != ["Editing src/breakout_research/ to fix enumeration order","Recomputing or rewriting the authorized code hash in campaign_authorization.json without a recorded v1 re-authorization decision"]:
        failures.append('forbidden_mismatch')
    res = {'ok': len(failures)==0, 'failures': failures}
    print(json.dumps(res))
    sys.exit(0 if res['ok'] else 1)

if __name__=='__main__':
    main()

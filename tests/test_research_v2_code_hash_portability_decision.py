import json, os, hashlib
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
DEC_PATH = REPO/'configs/research_v2_code_hash_portability_decision.json'

def load(p):
    with open(p) as f: return json.load(f)

def canon_sha(obj, exclude=None):
    exclude = set(exclude or [])
    body = {k:v for k,v in obj.items() if k not in exclude}
    s = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(s).hexdigest()

def test_manifest_hash_recomputes():
    d = load(DEC_PATH)
    assert d['manifest_hash'] == canon_sha(d, d['hashing']['manifest_hash_excluded_keys'])

def test_decision_choice_b_preserves_binding():
    d = load(DEC_PATH)
    assert 'authorized code hash unchanged' in d['decision']['choice']
    assert 'canonical_source_digest' in d['decision']['choice']

def test_forbidden_rules():
    d = load(DEC_PATH)
    forbidden = d['implementation_rules']['forbidden']
    forbidden_s = " ".join(forbidden)
    assert "Editing src/breakout_research/ to fix enumeration order" in forbidden_s
    assert "Recomputing or rewriting the authorized code hash" in forbidden_s

def test_canonical_digest_matches_amendment():
    d = load(DEC_PATH)
    am1 = load(REPO/'configs/research_v2_execution_amendment_1.json')
    assert d['references']['amendment_1']['canonical_source_digest'] == am1['code_hash_constraint']['canonical_source_digest']
    assert d['references']['amendment_1']['manifest_hash'] == am1['manifest_hash']

def test_authorized_hash_unchanged():
    d = load(DEC_PATH)
    auth = load(REPO/'research_state/campaign_authorization.json')
    assert d['references']['campaign_authorization']['code_hash'] == auth['code_hash']
    assert auth['authorized'] is True

def test_no_execution_or_src_changes_stated():
    d = load(DEC_PATH)
    assert d['acceptance']['constraints']['no_src_changes'] is True
    assert d['acceptance']['constraints']['no_execution'] is True
    assert d['acceptance']['constraints']['design_only'] is True

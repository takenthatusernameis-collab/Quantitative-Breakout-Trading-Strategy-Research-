"""Math utilities."""
import hashlib
from typing import List, Dict, Any
import json


def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*args) -> str:
    h = hashlib.sha256()
    for a in args:
        if isinstance(a, dict):
            h.update(json.dumps(a, sort_keys=True).encode())
        else:
            h.update(str(a).encode())
    return h.hexdigest()[:16]

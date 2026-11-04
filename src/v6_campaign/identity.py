"""Portable source-tree identities for v6, outside the frozen v1 engine tree."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict

ALGORITHM = "canonical_source_digest_v1"
HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v6_campaign"

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical_source_digest(root: Path) -> str:
    base = Path(root)
    digest = hashlib.sha256()
    if base.is_dir():
        for relative in sorted(p.relative_to(base).as_posix() for p in base.rglob("*.py")):
            digest.update(relative.encode("utf-8") + b"\n")
            digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()

def hashed_set_digest(repo_root: Path) -> str:
    return canonical_source_digest(Path(repo_root) / HASHED_SET_ROOT)

def execution_path_digest(repo_root: Path) -> str:
    return canonical_source_digest(Path(repo_root) / EXECUTION_PATH_ROOT)

def run_code_identity(hashed_digest: str, execution_digest: str) -> str:
    return sha256_bytes(canonical({
        "algorithm": ALGORITHM,
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_digest,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_digest,
    }).encode("utf-8"))

def code_identity_document(repo_root: Path) -> Dict[str, Any]:
    hashed = hashed_set_digest(repo_root)
    execution = execution_path_digest(repo_root)
    return {
        "algorithm": ALGORITHM,
        "portable": True,
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution,
        "run_code_identity": run_code_identity(hashed, execution),
    }

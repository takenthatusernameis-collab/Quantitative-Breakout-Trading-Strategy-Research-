"""Portable source-tree identities for the v2 campaign.

The v1 campaign binds itself to ``compute_code_hash()``, which is not portable:
it sorts the files inside each directory but visits the directories in
filesystem enumeration order, so the same git-clean tree yields a different
digest on a machine whose directory order differs. BRAIN-009 therefore
established ``canonical_source_digest_v1`` as the portable identity of a source
tree: a sha256 over the POSIX relative path and the content digest of every
``*.py`` file under a root, in ascending path order.

This module applies that rule to two roots:

* the hashed set ``src/breakout_research`` -- the v1 engine that produces the
  results, whose canonical digest is recorded by
  ``configs/research_v2_code_hash_amendment_1.json``;
* the v2 execution path ``src/v2_campaign`` -- this package.

The identity of a v2 run is the composite of both digests, so that an
experiment ID is bound to the engine *and* to the path that drives it, and is
reproducible on any checkout.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

CANONICAL_DIGEST_ALGORITHM = "canonical_source_digest_v1"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v2_campaign"

_ALGORITHM_DESCRIPTION = (
    "sha256 over the concatenation, for every *.py file under the root in "
    "ascending POSIX relative-path order, of the relative path, a newline, the "
    "sha256 hex digest of the file bytes, and a newline."
)


def canonical(obj: Any) -> str:
    """Canonical JSON serialization used for every digest in this package."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_source_digest(root: Path) -> str:
    """The portable identity of the ``*.py`` tree under ``root``.

    The digest does not depend on the directory enumeration order of the
    checkout, so it is reproducible on any machine.
    """
    base = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(path.relative_to(base).as_posix() for path in base.rglob("*.py")):
        digest.update(relative.encode("utf-8") + b"\n")
        digest.update(sha256_bytes((base / relative).read_bytes()).encode("ascii") + b"\n")
    return digest.hexdigest()


def hashed_set_digest(repo_root: Path) -> str:
    """Canonical digest of the hashed source set ``src/breakout_research``."""
    return canonical_source_digest(Path(repo_root) / HASHED_SET_ROOT)


def execution_path_digest(repo_root: Path) -> str:
    """Canonical digest of the v2 execution path ``src/v2_campaign``."""
    return canonical_source_digest(Path(repo_root) / EXECUTION_PATH_ROOT)


def run_code_identity(hashed_set: str, execution_path: str) -> str:
    """Composite, portable identity of one v2 run.

    It binds the v1 engine that produces the results and the v2 execution path
    that drives it, under the canonical digest rule of BRAIN-009.
    """
    payload = {
        "algorithm": CANONICAL_DIGEST_ALGORITHM,
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
    }
    return sha256_bytes(canonical(payload).encode("utf-8"))


def code_identity_document(repo_root: Path) -> Dict[str, Any]:
    """The code identity of the v2 run, as recorded by the authorization."""
    hashed_set = hashed_set_digest(repo_root)
    execution_path = execution_path_digest(repo_root)
    return {
        "algorithm": CANONICAL_DIGEST_ALGORITHM,
        "algorithm_description": _ALGORITHM_DESCRIPTION,
        "portable": True,
        "hashed_set_root": HASHED_SET_ROOT,
        "hashed_set_digest": hashed_set,
        "execution_path_root": EXECUTION_PATH_ROOT,
        "execution_path_digest": execution_path,
        "run_code_identity": run_code_identity(hashed_set, execution_path),
        "note": (
            "The identity of a v2 run is the composite of the canonical digest of the "
            "hashed v1 engine and the canonical digest of the v2 execution path. The "
            "checkout-dependent ordered digest compute_code_hash() is reported by the "
            "verifiers as an environment fact and is never used as an identity."
        ),
    }

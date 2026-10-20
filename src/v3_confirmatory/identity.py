"""Portable source-tree identities for the v3 confirmatory evaluation.

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
* the v3 confirmatory execution path ``src/v3_confirmatory`` -- this package.

The identity of a confirmatory run is the composite of both digests, so that an
experiment ID is bound to the engine *and* to the path that drives it, and is
reproducible on any checkout.

The rule is implemented here rather than imported from ``v3_campaign`` on
purpose: the confirmatory path must stay independent of the v3 selection path,
whose canonical digest is bound by the selection authorization.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .errors import AuthorizationError

CANONICAL_DIGEST_ALGORITHM = "canonical_source_digest_v1"

HASHED_SET_ROOT = "src/breakout_research"
EXECUTION_PATH_ROOT = "src/v3_confirmatory"

#: The versioned amendment that may rotate the execution-path digest after the
#: authorization was frozen. It is the only artifact that may carry a digest
#: other than the one the authorization records. It does not exist yet: the
#: v3 confirmatory path is delivered in the same session that freezes the
#: authorization that binds it, so no rotation is needed.
CODE_HASH_AMENDMENT_RELATIVE = "configs/research_v3_confirmatory_code_hash_amendment_1.json"

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
    """Canonical digest of the confirmatory execution path ``src/v3_confirmatory``."""
    return canonical_source_digest(Path(repo_root) / EXECUTION_PATH_ROOT)


def run_code_identity(hashed_set: str, execution_path: str) -> str:
    """Composite, portable identity of one confirmatory run.

    It binds the v1 engine that produces the results and the confirmatory
    execution path that drives it, under the canonical digest rule of BRAIN-009.
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
    """The code identity of the confirmatory run, as recorded by the authorization."""
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
            "The identity of a confirmatory run is the composite of the canonical digest of "
            "the hashed v1 engine and the canonical digest of the confirmatory execution "
            "path. The checkout-dependent ordered digest compute_code_hash() is reported by "
            "the verifiers as an environment fact and is never used as an identity."
        ),
    }


def manifest_hash(document: Dict[str, Any], excluded_keys: Iterable[str]) -> str:
    """The self-hash of a hash-bound artifact.

    The digest is taken over the canonical JSON of the document body with the
    excluded keys removed, so that a document never hashes itself into a cycle.
    """
    excluded = tuple(excluded_keys)
    body = {key: value for key, value in document.items() if key not in excluded}
    return sha256_bytes(canonical(body).encode("utf-8"))


def code_hash_amendment_path(repo_root: Path) -> Path:
    """The path of the versioned code-hash amendment of the confirmatory path."""
    return Path(repo_root) / CODE_HASH_AMENDMENT_RELATIVE


def load_code_hash_amendment(repo_root: Path) -> Optional[Dict[str, Any]]:
    """Load the code-hash amendment, if it exists.

    Returns ``None`` when the amendment does not exist. Raises when it exists
    but does not verify: an amendment that cannot be verified authorises
    nothing.
    """
    path = code_hash_amendment_path(repo_root)
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    excluded = tuple((document.get("hashing") or {}).get("manifest_hash_excluded_keys") or ())
    if not excluded:
        raise AuthorizationError(
            "the code-hash amendment does not declare its manifest_hash_excluded_keys"
        )
    if document.get("manifest_hash") != manifest_hash(document, excluded):
        raise AuthorizationError(
            "the code-hash amendment manifest hash does not recompute; it authorises nothing"
        )
    return document


def resolve_code_identity(repo_root: Path, recorded: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the effective code identity of the confirmatory run.

    ``recorded`` is the code identity the authorization froze. It is honoured
    when the tree is still the tree the authorization froze. When the execution
    path was corrected afterwards, only a *versioned* code-hash amendment may
    rotate the recorded digest, and only when the amendment hash-verifies and
    binds this very tree: the amended digest must equal the live digest, the
    amendment's previous digest must equal the recorded one, and the hashed
    set must be unchanged.

    The result is the identity the run is bound to. It always carries the live
    digests, so an artifact that records it describes the code that actually
    ran.
    """
    root = Path(repo_root)
    live_hashed_set = hashed_set_digest(root)
    live_execution_path = execution_path_digest(root)
    live_composite = run_code_identity(live_hashed_set, live_execution_path)

    recorded_hashed_set = (recorded or {}).get("hashed_set_digest")
    recorded_execution_path = (recorded or {}).get("execution_path_digest")
    recorded_composite = (recorded or {}).get("run_code_identity")

    if recorded_hashed_set != live_hashed_set:
        raise AuthorizationError(
            "the authorized hashed-set digest does not match the current source tree; "
            "the hashed set may never change"
        )

    rotation_applied = False
    amendment_manifest_hash: Optional[str] = None
    superseded_execution_path: Optional[str] = None

    if recorded_execution_path == live_execution_path:
        if recorded_composite != live_composite:
            raise AuthorizationError(
                "the recorded run code identity is not the composite of the two live digests"
            )
    else:
        amendment = load_code_hash_amendment(root)
        if amendment is None:
            raise AuthorizationError(
                "the authorized execution-path digest does not match the current execution "
                "path and no versioned code-hash amendment authorises the rotation"
            )
        rotation = amendment.get("code_hash_rotation") or {}
        if rotation.get("previous_execution_path_digest") != recorded_execution_path:
            raise AuthorizationError(
                "the code-hash amendment does not rotate the digest the authorization records"
            )
        if rotation.get("execution_path_digest") != live_execution_path:
            raise AuthorizationError(
                "the code-hash amendment does not bind the current execution path"
            )
        if rotation.get("hashed_set_digest") != live_hashed_set:
            raise AuthorizationError(
                "the code-hash amendment records a different hashed-set digest"
            )
        if rotation.get("run_code_identity") != live_composite:
            raise AuthorizationError(
                "the code-hash amendment does not record the composite identity of the "
                "current tree"
            )
        rotation_applied = True
        amendment_manifest_hash = str(amendment.get("manifest_hash"))
        superseded_execution_path = str(recorded_execution_path)

    effective = dict(recorded or {})
    effective.update(
        {
            "algorithm": CANONICAL_DIGEST_ALGORITHM,
            "hashed_set_root": HASHED_SET_ROOT,
            "hashed_set_digest": live_hashed_set,
            "execution_path_root": EXECUTION_PATH_ROOT,
            "execution_path_digest": live_execution_path,
            "run_code_identity": live_composite,
            "rotation_applied": rotation_applied,
            "code_hash_amendment_manifest_hash": amendment_manifest_hash,
            "superseded_execution_path_digest": superseded_execution_path,
            "note": (
                "The identity of a confirmatory run is the composite of the canonical digest of "
                "the hashed v1 engine and the canonical digest of the confirmatory execution "
                "path. The checkout-dependent ordered digest compute_code_hash() is reported by "
                "the verifiers as an environment fact and is never used as an identity. When a "
                "versioned code-hash amendment rotates the execution-path digest, the effective "
                "digest is the amended one and the amendment is named here."
            ),
        }
    )
    return effective


__all__ = [
    "CANONICAL_DIGEST_ALGORITHM",
    "CODE_HASH_AMENDMENT_RELATIVE",
    "EXECUTION_PATH_ROOT",
    "HASHED_SET_ROOT",
    "canonical",
    "canonical_source_digest",
    "code_hash_amendment_path",
    "code_identity_document",
    "execution_path_digest",
    "hashed_set_digest",
    "load_code_hash_amendment",
    "manifest_hash",
    "resolve_code_identity",
    "run_code_identity",
    "sha256_bytes",
]

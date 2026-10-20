"""Helpers for the identity of the hashed source set.

``compute_code_hash()`` (``src/breakout_research/config.py``) hashes the files of
each directory in sorted order but visits the directories in filesystem
enumeration order, so the same git-clean tree yields a different digest on a
machine whose directory order differs.  BRAIN-009 therefore established the
canonical digest as the portable identity of the tree and ruled that a live
ordered-digest mismatch alone is **not** evidence of source drift.

These helpers let a test assert something stronger and checkout-independent than
the rejected equality between the live ordered digest and the authorized value
of record:

* the live ordered digest must still identify *this* tree under the checkout's
  own enumeration order, and
* the authorized digest must still be one of the digests that this tree
  produces.

A real edit of the tree changes every one of those digests, so real drift is
still detected -- the check is neither weaker nor vacuous.
"""

from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


def _blocks(root: Path) -> Tuple[List[Path], List[Tuple[str, List[Path]]]]:
    """The top-level files and the directory blocks of the tree under ``root``.

    A block is a directory that holds at least one ``*.py`` file; a directory
    without one (for example ``__pycache__``) contributes nothing to the digest
    and is therefore not a block.
    """
    base = Path(root)
    top = sorted(base.glob("*.py"))
    blocks: List[Tuple[str, List[Path]]] = []
    for candidate in sorted(path for path in base.iterdir() if path.is_dir()):
        files = sorted(candidate.glob("*.py"))
        if files:
            blocks.append((candidate.name, files))
    return top, blocks


def ordered_digest_for_order(root: Path, order: Sequence[str]) -> str:
    """The digest ``compute_code_hash()`` returns for the given block order.

    The replica is faithful to ``compute_code_hash()``: the files of the root
    directory come first, in sorted order, then the files of each directory
    block, in sorted order, in the given order of the blocks.
    """
    base = Path(root)
    top, blocks = _blocks(base)
    by_name = dict(blocks)
    hasher = hashlib.sha256()
    for path in top:
        hasher.update(path.read_bytes())
    for name in order:
        for path in by_name[name]:
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def ordered_digest_variants(root: Path) -> Dict[str, Tuple[str, ...]]:
    """Every digest ``compute_code_hash()`` can return for the tree under ``root``.

    The map is digest -> the order of the directory blocks that produces it.  The
    number of entries is the number of permutations of the blocks (120 for the
    hashed set ``src/breakout_research``, whose blocks are ``backtest``, ``data``,
    ``indicators``, ``signals`` and ``utils``).
    """
    _top, blocks = _blocks(Path(root))
    variants: Dict[str, Tuple[str, ...]] = {}
    for permutation in itertools.permutations(range(len(blocks))):
        order = tuple(blocks[index][0] for index in permutation)
        digest = ordered_digest_for_order(root, order)
        variants.setdefault(digest, order)
    return variants


def live_enumeration_order(root: Path) -> Tuple[str, ...]:
    """The order in which ``os.walk`` visits the directory blocks of ``root``.

    This is the order that the checkout happens to use; it is an environment
    fact, never an identity.
    """
    base = Path(root)
    order: List[str] = []
    for current, _dirs, files in os.walk(base):
        relative = Path(current).relative_to(base)
        if relative == Path("."):
            continue
        if any(name.endswith(".py") for name in files):
            order.append(relative.as_posix())
    return tuple(order)

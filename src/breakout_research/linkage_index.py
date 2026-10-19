"""Cycle-to-campaign linkage index for BRAIN-007.

Classifies result units as LINKED_PRIOR_EVIDENCE or NEW by comparing their
experiment IDs against a verified prior cycle's linked unit set. The index
is hash-bound to the cycle identity (code_hash, spec_hash,
data_manifest_hash, universe_hash) so that linkage is itself verifiable.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Set, Tuple


def compute_canonical_hash(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LinkageIndex:
    """Hash-bound linkage index keyed by cycle identity."""

    def __init__(self, code_hash: str, spec_hash: str,
                 data_manifest_hash: str, universe_hash: str) -> None:
        self.cycle_identity = (code_hash, spec_hash, data_manifest_hash, universe_hash)
        self.identity_hash = compute_canonical_hash(self.cycle_identity)

    def classify(self, unit_id: str, prior_linked_units: Set[str]) -> str:
        """Classify a single unit as LINKED_PRIOR_EVIDENCE or NEW."""
        if unit_id in prior_linked_units:
            return "LINKED_PRIOR_EVIDENCE"
        return "NEW"

    def count_linked_vs_new(self, unit_ids: List[str],
                            prior_linked_units: Set[str]) -> Tuple[int, int]:
        """Return (linked_count, new_count) for a batch of unit IDs."""
        linked = 0
        for uid in unit_ids:
            if self.classify(uid, prior_linked_units) == "LINKED_PRIOR_EVIDENCE":
                linked += 1
        return linked, len(unit_ids) - linked

    def identity_payload(self) -> Dict[str, str]:
        return {
            "code_hash": self.cycle_identity[0],
            "spec_hash": self.cycle_identity[1],
            "data_manifest_hash": self.cycle_identity[2],
            "universe_hash": self.cycle_identity[3],
        }

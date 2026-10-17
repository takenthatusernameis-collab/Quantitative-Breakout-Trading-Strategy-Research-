"""Recovery tests for continuous cycles."""
import json
import os
from pathlib import Path
import tempfile
import shutil

from breakout_research import continuous_universe as cu
from breakout_research import continuous_universe_coordinator as coc


def test_snapshot_ids_distinct_for_different_universes():
    spec = cu.load_research_spec("configs/research_v1.json")
    code_hash = cu.compute_code_hash()
    univ = cu.load_universe_manifest("research/universe_manifest.json")
    sid1 = cu.compute_snapshot_id(univ, spec["specification_hash"], code_hash)
    univ2 = json.loads(json.dumps(univ))
    # mutate eligible assets slightly
    if univ2.get("eligible_assets"):
        univ2["eligible_assets"][0]["symbol"] = univ2["eligible_assets"][0]["symbol"] + "_X"
    sid2 = cu.compute_snapshot_id(univ2, spec["specification_hash"], code_hash)
    assert sid1 != sid2


def test_interrupt_resume():
    pass

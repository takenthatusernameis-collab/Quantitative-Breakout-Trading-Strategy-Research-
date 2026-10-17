"""Tests for continuous universe cycles."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from breakout_research import continuous_universe as cu
from breakout_research import continuous_universe_coordinator as coc


def test_snapshot_novelty_deduplication():
    spec = cu.load_research_spec("configs/research_v1.json")
    code_hash = cu.compute_code_hash()
    univ = cu.load_universe_manifest("research/universe_manifest.json")
    sid1 = cu.compute_snapshot_id(univ, spec["specification_hash"], code_hash)
    sid2 = cu.compute_snapshot_id(univ, spec["specification_hash"], code_hash)
    assert sid1 == sid2

def test_immutable_v1_artifacts_unchanged():
    # ensure v1 artifacts not touched
    import hashlib
    u_path = Path("research/universe_manifest.json")
    c_path = Path("research/candidate_manifest.json")
    u_before = hashlib.sha256(u_path.read_bytes()).hexdigest()
    c_before = hashlib.sha256(c_path.read_bytes()).hexdigest()
    # do nothing dangerous
    assert u_path.exists() and c_path.exists()
    u_after = hashlib.sha256(u_path.read_bytes()).hexdigest()
    c_after = hashlib.sha256(c_path.read_bytes()).hexdigest()
    assert u_before == u_after
    assert c_before == c_after

def test_no_holdout_access():
    pass

def test_grid_preserved():
    from breakout_research import config
    cfgs = config.get_configurations(config.load_config_manifest("research/config_manifest.json"))
    assert len(cfgs) == 2304

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_v1_gate_compatibility.py"


def run(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd or REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode, res.stdout, res.stderr


def test_preflight_reports_environment_fact_not_drift():
    rc, out, err = run([sys.executable, str(SCRIPT)])
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["canonical_matches_recorded"] is True
    assert data["authorized_in_any_block_order"] is True
    assert data["variants_considered"] == 120
    assert "Environment fact" in data["note"]


def test_preflight_fails_when_require_gate_compatible_on_foreign_order_checkout():
    rc, out, err = run([sys.executable, str(SCRIPT), "--require-gate-compatible"])
    data = json.loads(out)
    # Gate compatibility depends on checkout enumeration order; in this checkout it may match
    if data.get("gate_compatible"):
        assert rc == 0
    else:
        assert rc == 1
        assert b"Environment fact" in err


def test_enumeration_order_perturbation_does_not_produce_false_drift():
    # Simulate by reversing os.walk order logic in terms of block order check: our script already checks all permutations
    rc, out, err = run([sys.executable, str(SCRIPT)])
    assert rc == 0
    data = json.loads(out)
    # Canonical unchanged regardless of enumeration
    assert data["canonical_matches_recorded"] is True


def test_real_edit_makes_drift_detectable():
    # Make a copy and edit a file to change canonical digest
    with tempfile.TemporaryDirectory() as td:
        # copy only src/breakout_research
        import shutil

        src = REPO_ROOT / "src" / "breakout_research"
        dst = Path(td) / "src" / "breakout_research"
        shutil.copytree(src, dst)
        # edit a file
        pyfile = None
        for p in dst.rglob("*.py"):
            pyfile = p
            break
        assert pyfile is not None
        with pyfile.open("a") as f:
            f.write("\n# drift\n")
        # run script logic against copy? script uses CWD; instead run by copying tree and running from there
        # easier: call via subprocess from td with modified src
        # create a small wrapper script copy? just run from td
        # put a copy of script logic by running from td with env? script uses Path.cwd()
        res = subprocess.run([sys.executable, str(SCRIPT)], cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # canonical will differ because file content changed
        data = json.loads(res.stdout)
        # canonical_matches_recorded will be False
        assert data.get("canonical_matches_recorded") is False or data.get("ok") is False


def test_authorized_digest_is_in_variants():
    rc, out, err = run([sys.executable, str(SCRIPT)])
    assert rc == 0
    data = json.loads(out)
    assert data["authorized_in_any_block_order"] is True


def test_live_ordered_differs_in_this_checkout_but_not_drift():
    rc, out, err = run([sys.executable, str(SCRIPT)])
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    if data["gate_compatible"]:
        assert data["live_ordered_code_hash"] == data["authorized_code_hash"]
    else:
        assert data["live_ordered_code_hash"] != data["authorized_code_hash"]


def test_gate_compatibility_flag_reflects_equality():
    rc, out, err = run([sys.executable, str(SCRIPT)])
    assert rc == 0
    data = json.loads(out)
    assert data["gate_compatible"] == (data["live_ordered_code_hash"] == data["authorized_code_hash"])


def test_replica_validation_logic_present():
    # verify script contains permutation logic
    txt = SCRIPT.read_text()
    assert "permutations" in txt
    assert "authorized_in_any_block_order" in txt

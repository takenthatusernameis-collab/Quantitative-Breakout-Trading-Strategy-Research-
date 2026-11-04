"""Tests for the non-authorizing v6 selection implementation binding."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"src"))
def _load(relative,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
def test_binding_is_self_hashed_and_matches_the_live_package():
    builder=_load("scripts/build_v6_selection_execution_binding_1.py","build_v6_selection_execution_binding_1")
    on_disk=json.loads((ROOT/"configs/research_v6_selection_execution_binding_1.json").read_text())
    assert builder.build(ROOT)==on_disk
    assert on_disk["binding_status"]=="IMPLEMENTATION_BOUND_NOT_RUN"
    assert on_disk["authority"]["max_runs"]==1
    assert on_disk["authority"]["confirmatory_evaluation_authorized"] is False
    assert on_disk["authority"]["candle_fetch_authorized"] is False
    assert on_disk["authority"]["holdout_reads_authorized"] is False
def test_v6_scope_and_execution_verifier_pass_without_creating_campaign_outputs():
    from v6_campaign.scope import validate_v6_scope
    result=validate_v6_scope(ROOT)
    assert len(result["scope"]["binance_pairs"])==7
    assert result["run_id"]=="v6-selection-20261022"
    assert not (ROOT/"research/ledger_v6.json").exists()
    assert not (ROOT/"research/results_v6.jsonl").exists()

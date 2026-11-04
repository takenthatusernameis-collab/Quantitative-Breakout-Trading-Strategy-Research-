"""Focused v6 selection-engine safety and readiness tests (no campaign execution)."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"src"))
from v6_campaign.data import load_development_candles
from v6_campaign.errors import ConfirmatoryWindowViolation
from breakout_research.config import TrendFilter
from v6_campaign.identity import canonical_source_digest
from v6_campaign.runner import build_plan, default_workspace
from v6_campaign.units import fold_bounds, validation_folds

def test_v6_plan_recomputes_the_frozen_7_asset_grid_without_starting_a_run():
    plan=build_plan(default_workspace(ROOT))
    assert [x["symbol"] for x in plan.assets]==[
        "FETUSDT","SEIUSDT","PENDLEUSDT","XTZUSDT","LDOUSDT","SUNUSDT","GNOUSDT"
    ]
    assert len(plan.configs)==2304
    assert sum(1 for c in plan.configs if c.trend_filter == TrendFilter.BTC_EMA_168)==576
    assert plan.counts["config_units"]==16128
    assert plan.counts["execution_units"]==193536
    assert plan.effective_data_boundary_utc=="2026-10-19T22:00:00Z"
    assert plan.code_identity["execution_path_digest"]==canonical_source_digest(ROOT/"src/v6_campaign")
    assert not (ROOT/"research/ledger_v6.json").exists()

def test_development_dataset_declared_past_cutoff_is_refused_before_open(monkeypatch,tmp_path):
    import v6_campaign.data as data
    called={"loader":False}
    def forbidden(*args,**kwargs):
        called["loader"]=True
        raise AssertionError("candle loader must not be called")
    monkeypatch.setattr(data,"load_verified_candles",forbidden)
    manifest={"assets":{"ABCUSDT":{
        "validated":True,"interval":"1h","hash_algorithm":"sha256-canonical-hourly-csv-v1",
        "gaps":[],"rejected_rows":0,"last_candle_timestamp":3_600_000,
        "dataset_path":"never-opened.csv"
    }}}
    with pytest.raises(ConfirmatoryWindowViolation):
        data.load_development_candles(tmp_path,"ABCUSDT",manifest,3_600_000)
    assert called["loader"] is False

def test_validation_fold_enumerator_never_returns_holdout_position_fold():
    candles=[type("C",(),{"timestamp":i*3_600_000})() for i in range(100)]
    bounds=fold_bounds(candles,{"development_fraction":0.8,"window_fractions":[0.1,0.2,0.3,0.4]})
    assert bounds[-1][3] is True
    assert all(not row[3] for row in validation_folds(bounds))
    assert len(validation_folds(bounds))==4

def test_importing_v6_campaign_has_no_execution_side_effects():
    import v6_campaign.runner
    assert not (ROOT/"research/ledger_v6.json").exists()
    assert not (ROOT/"research/shards_v6").exists()

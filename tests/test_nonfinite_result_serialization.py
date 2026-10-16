"""Strict JSON regression tests for backtest metrics and result shards."""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

from breakout_research.backtest.backtester import _compute_metrics
from breakout_research.backtest.shards import ShardWriter, serialize_record


def _reject_nonstandard_json_constant(value: str):
    raise ValueError(f"Non-standard JSON constant: {value}")


def _strict_loads(text: str):
    return json.loads(text, parse_constant=_reject_nonstandard_json_constant)


def test_profit_factor_without_losses_is_null_with_explicit_status() -> None:
    trade = SimpleNamespace(net_pnl=50.0)
    metrics = _compute_metrics(
        equity_curve=[10_000.0, 10_050.0],
        timestamps=[0, 86_400_000],
        trades=[trade],
        initial_capital=10_000.0,
        total_fees=0.0,
        total_slippage=0.0,
        total_turnover=0.0,
    )

    assert metrics["profit_factor"] is None
    assert metrics["profit_factor_status"] == "no_losses"


def test_profit_factor_with_no_trades_is_marked_not_applicable() -> None:
    metrics = _compute_metrics(
        equity_curve=[10_000.0],
        timestamps=[0],
        trades=[],
        initial_capital=10_000.0,
        total_fees=0.0,
        total_slippage=0.0,
        total_turnover=0.0,
    )

    assert metrics["profit_factor"] is None
    assert metrics["profit_factor_status"] == "no_trades"


def test_serializer_normalizes_all_non_finite_values_and_emits_strict_json() -> None:
    source = {
        "experiment_id": "strict-json-case",
        "profit_factor": math.inf,
        "profit_factor_status": "no_losses",
        "avg_loss": 0.0,
        "trade_count": 3,
        "daily_sharpe": math.nan,
        "annualized_return": -math.inf,
    }
    serialized = serialize_record(source)
    result = _strict_loads(serialized)

    assert result["profit_factor"] is None
    assert result["profit_factor_status"] == "no_losses"
    assert result["daily_sharpe"] is None
    assert result["annualized_return"] is None
    assert result["non_finite_fields"] == [
        "annualized_return", "daily_sharpe", "profit_factor"
    ]
    assert "Infinity" not in serialized and "NaN" not in serialized
    assert source["profit_factor"] == math.inf
    assert math.isnan(source["daily_sharpe"])


def test_shard_writer_emits_strict_json_lines(tmp_path: Path) -> None:
    writer = ShardWriter(
        campaign_id="strict-json-campaign",
        shard_root=str(tmp_path / "results_shards"),
        max_shard_bytes=4096,
    )
    writer.append({
        "experiment_id": "row-1",
        "profit_factor": math.inf,
        "profit_factor_status": "no_losses",
        "avg_loss": 0.0,
        "trade_count": 1,
    })
    info = writer.flush()[0]
    rows = Path(info["path"]).read_text(encoding="utf-8").splitlines()

    assert len(rows) == 1
    result = _strict_loads(rows[0])
    assert result["profit_factor"] is None
    assert result["profit_factor_status"] == "no_losses"
    assert result["non_finite_fields"] == ["profit_factor"]
    assert info["bytes"] == Path(info["path"]).stat().st_size

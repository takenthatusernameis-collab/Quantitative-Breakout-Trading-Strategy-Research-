"""Configuration and data structures for breakout research."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import json
import hashlib
from datetime import datetime


class EntryRule(str, Enum):
    CLASSIC_HIGH_BREAKOUT = "classic_high_breakout"
    CLOSE_BREAKOUT = "close_breakout"


class ConfirmationMode(str, Enum):
    ONE_CLOSE = "one_close"
    TWO_CLOSE = "two_close"


class TrendFilter(str, Enum):
    NONE = "none"
    ASSET_EMA_168 = "asset_ema_168"
    ASSET_EMA_24_168 = "asset_ema_24_168"
    BTC_EMA_168 = "btc_ema_168"


class ExitType(str, Enum):
    CHANNEL_12 = "channel_12"
    CHANNEL_24 = "channel_24"
    CHANNEL_48 = "channel_48"
    ATR_TRAIL_1_5 = "atr_trail_1.5"
    ATR_TRAIL_2_5 = "atr_trail_2.5"
    ATR_TRAIL_4_0 = "atr_trail_4.0"


class ExperimentStatus(str, Enum):
    COMPLETED = "COMPLETED"
    ZERO_TRADE_COMPLETED = "ZERO_TRADE_COMPLETED"
    EXCLUDED = "EXCLUDED"
    INVALID_DATA = "INVALID_DATA"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PILOT_RUNNING = "PILOT_RUNNING"
    PILOT_PASS = "PILOT_PASS"
    CAMPAIGN_RUNNING = "CAMPAIGN_RUNNING"
    CAMPAIGN_PARTIAL = "CAMPAIGN_PARTIAL"
    CAMPAIGN_COMPLETE = "CAMPAIGN_COMPLETE"
    INVALIDATED = "INVALIDATED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


class EconomicConclusion(str, Enum):
    NO_CANDIDATE = "NO_CANDIDATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CANDIDATE_PENDING_HOLDOUT = "CANDIDATE_PENDING_HOLDOUT"
    REJECTED_ON_HOLDOUT = "REJECTED_ON_HOLDOUT"
    PROVISIONAL_HISTORICAL_SURVIVAL = "PROVISIONAL_HISTORICAL_SURVIVAL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class StrategyConfig:
    config_id: str
    entry_rule: EntryRule
    entry_lookback: int
    buffer_atr_multiple: float
    confirmation: ConfirmationMode
    trend_filter: TrendFilter
    exit: ExitType
    content_hash: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'StrategyConfig':
        return cls(
            config_id=d['config_id'],
            entry_rule=EntryRule(d['entry_rule']),
            entry_lookback=d['entry_lookback'],
            buffer_atr_multiple=d['buffer_atr_multiple'],
            confirmation=ConfirmationMode(d['confirmation']),
            trend_filter=TrendFilter(d['trend_filter']),
            exit=ExitType(d['exit']),
            content_hash=d['content_hash']
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'config_id': self.config_id,
            'entry_rule': self.entry_rule.value,
            'entry_lookback': self.entry_lookback,
            'buffer_atr_multiple': self.buffer_atr_multiple,
            'confirmation': self.confirmation.value,
            'trend_filter': self.trend_filter.value,
            'exit': self.exit.value,
            'content_hash': self.content_hash
        }


@dataclass
class CostScenario:
    multiplier: float
    taker_fee_bps: float
    slippage_bps: float

    @classmethod
    def baseline(cls) -> 'CostScenario':
        return cls(multiplier=1.0, taker_fee_bps=10.0, slippage_bps=5.0)

    def scaled(self, multiplier: float) -> 'CostScenario':
        return CostScenario(
            multiplier=multiplier,
            taker_fee_bps=self.taker_fee_bps * multiplier,
            slippage_bps=self.slippage_bps * multiplier
        )


@dataclass
class Candle:
    timestamp: int  # UTC open timestamp in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    def validate(self) -> bool:
        return (
            self.high >= self.low and
            self.high >= self.open and
            self.high >= self.close and
            self.low <= self.open and
            self.low <= self.close and
            self.open > 0 and
            self.high > 0 and
            self.low > 0 and
            self.close > 0 and
            self.volume >= 0
        )


@dataclass
class Trade:
    entry_time: int
    entry_price: float
    exit_time: Optional[int]
    exit_price: Optional[float]
    quantity: float
    entry_fee: float
    exit_fee: float
    entry_slippage: float
    exit_slippage: float
    gross_pnl: float
    net_pnl: float
    exit_reason: str
    max_favorable_excursion: float
    max_adverse_excursion: float


@dataclass
class FoldResult:
    fold_index: int
    start_time: int
    end_time: int
    config_id: str
    asset: str
    cost_multiplier: float
    status: ExperimentStatus
    reason: Optional[str]
    trade_count: int
    gross_total_return: float
    net_total_return: float
    annualized_return: float
    daily_sharpe: Optional[float]
    max_drawdown: float
    exposure: float
    turnover: float
    win_rate: Optional[float]
    avg_win: Optional[float]
    avg_loss: Optional[float]
    profit_factor: Optional[float]
    fee_drag: float
    slippage_drag: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    timestamps: List[int] = field(default_factory=list)


@dataclass
class AssetResult:
    asset: str
    rank: int
    config_id: str
    fold_results: List[FoldResult]
    holdout_result: Optional[FoldResult]
    candidate_selected: bool
    selection_rank: Optional[int]
    economic_conclusion: EconomicConclusion


@dataclass
class CheckpointState:
    protocol_hash: str
    code_hash: str
    current_asset_index: int
    current_config_index: int
    current_fold_index: int
    current_cost_index: int
    completed_records: int
    last_verified_record: int
    next_unit: Dict[str, Any]
    timestamp_utc: str
    pilot_completed: bool = False
    pilot_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'protocol_hash': self.protocol_hash,
            'code_hash': self.code_hash,
            'current_asset_index': self.current_asset_index,
            'current_config_index': self.current_config_index,
            'current_fold_index': self.current_fold_index,
            'current_cost_index': self.current_cost_index,
            'completed_records': self.completed_records,
            'last_verified_record': self.last_verified_record,
            'next_unit': self.next_unit,
            'timestamp_utc': self.timestamp_utc,
            'pilot_completed': self.pilot_completed,
            'pilot_passed': self.pilot_passed
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CheckpointState':
        return cls(
            protocol_hash=d['protocol_hash'],
            code_hash=d['code_hash'],
            current_asset_index=d['current_asset_index'],
            current_config_index=d['current_config_index'],
            current_fold_index=d['current_fold_index'],
            current_cost_index=d['current_cost_index'],
            completed_records=d['completed_records'],
            last_verified_record=d['last_verified_record'],
            next_unit=d['next_unit'],
            timestamp_utc=d['timestamp_utc'],
            pilot_completed=d.get('pilot_completed', False),
            pilot_passed=d.get('pilot_passed', False)
        )


def compute_code_hash() -> str:
    """Compute hash of all source files in src/breakout_research."""
    import os
    src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src', 'breakout_research')
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(src_dir):
        for f in sorted(files):
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'rb') as fp:
                    hasher.update(fp.read())
    return hasher.hexdigest()


def load_research_spec() -> Dict[str, Any]:
    with open('configs/research_v1.json', 'r') as f:
        return json.load(f)


def load_universe_manifest() -> Dict[str, Any]:
    with open('research/universe_manifest.json', 'r') as f:
        return json.load(f)


def load_config_manifest() -> Dict[str, Any]:
    with open('research/config_manifest.json', 'r') as f:
        return json.load(f)


def load_data_manifest() -> Dict[str, Any]:
    with open('research/data_manifest.json', 'r') as f:
        return json.load(f)


def get_eligible_assets(universe: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [a for a in universe['eligible_assets'] if a.get('binance_spot_verified', False)]


def get_configurations(config_manifest: Dict[str, Any]) -> List[StrategyConfig]:
    return [StrategyConfig.from_dict(c) for c in config_manifest['configurations']]
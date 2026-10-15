"""Local data cache for offline operation/testing."""
import os
import json
from typing import List, Tuple, Optional
from datetime import datetime, timezone
from ..config import Candle


def generate_synthetic_candles(symbol: str, count: int = 3000, start_price: float = 50000) -> List[Candle]:
    """Generate synthetic candle data for testing."""
    candles = []
    base_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    price = start_price
    for i in range(count):
        timestamp = base_time + i * 3600000
        # Random walk
        import random
        random.seed(i + hash(symbol))
        change = random.uniform(-0.01, 0.015)
        price = price * (1 + change)
        open_p = price
        close_p = price * (1 + random.uniform(-0.001, 0.001))
        high_p = max(open_p, close_p) * (1 + random.uniform(0, 0.005))
        low_p = min(open_p, close_p) * (1 - random.uniform(0, 0.005))
        volume = random.uniform(100, 10000)
        candles.append(Candle(timestamp, open_p, high_p, low_p, close_p, volume))
    return candles

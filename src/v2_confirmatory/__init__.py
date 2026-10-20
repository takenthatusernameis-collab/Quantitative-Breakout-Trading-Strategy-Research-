"""v2 confirmatory evaluation execution path.

This package lives outside the hashed set (src/breakout_research) and outside the
v2 selection path (src/v2_campaign). It is the implementation of BRAIN-011.
Nothing in this package reads a confirmatory-window candle: the readiness probe
is implemented but never executed in this session.
"""

from __future__ import annotations

from .errors import ConfirmatoryError

__all__ = ["ConfirmatoryError"]
__version__ = "0.1.0"

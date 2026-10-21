"""Error types of the v4 execution path.

Every error raised by this package is a subclass of :class:`V4CampaignError`,
so that a caller can distinguish a boundary violation (which must abort and
roll back) from an ordinary bug.
"""

from __future__ import annotations


class V4CampaignError(RuntimeError):
    """Base class of every failure of the v4 execution path."""


class ScopeError(V4CampaignError):
    """The frozen scope, the authorization or the selection rule does not match."""


class ConfirmatoryWindowViolation(V4CampaignError):
    """A candle inside the v4 confirmatory window would have been read."""


class BoundsError(V4CampaignError):
    """The run would exceed a bound recorded by the authorization."""


class AttemptBudgetError(V4CampaignError):
    """The bounded run has already consumed its single authorized attempt."""


class DataVerificationError(V4CampaignError):
    """A dataset is missing, unverifiable or inconsistent with its manifest."""


class BenchmarkAlignmentError(V4CampaignError):
    """The benchmark series is missing, too short or not index-aligned.

    The error is raised **before** the frozen engine is called, so that a
    misaligned benchmark can never reach a result.
    """

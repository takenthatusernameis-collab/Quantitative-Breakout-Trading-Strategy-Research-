"""Error types of the v2 execution path.

Every error raised by this package is a subclass of :class:`V2CampaignError`,
so that a caller can distinguish a boundary violation (which must abort and
roll back) from an ordinary bug.
"""

from __future__ import annotations


class V2CampaignError(RuntimeError):
    """Base class of every failure of the v2 execution path."""


class ScopeError(V2CampaignError):
    """The frozen scope, the authorization or the selection rule does not match."""


class ConfirmatoryWindowViolation(V2CampaignError):
    """A candle inside the v2 confirmatory window would have been read."""


class BoundsError(V2CampaignError):
    """The run would exceed a bound recorded by the authorization."""


class AttemptBudgetError(V2CampaignError):
    """The bounded run has already consumed its single authorized attempt."""


class DataVerificationError(V2CampaignError):
    """A dataset is missing, unverifiable or inconsistent with its manifest."""

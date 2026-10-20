"""Errors of the v2 confirmatory evaluation path.

Every error of this package is a :class:`ConfirmatoryError`, so that a caller
can distinguish a boundary violation of the confirmatory evaluation (which
rolls back and releases the authorized attempt) from an ordinary technical
failure (which keeps the verified state so that the run can be resumed).
"""

from __future__ import annotations


class ConfirmatoryError(RuntimeError):
    """Base class of every confirmatory-evaluation error."""


class ScopeError(ConfirmatoryError):
    """The evaluation scope is not the frozen one, or was widened or narrowed."""


class BoundsError(ConfirmatoryError):
    """The run would exceed the bounds the authorization records."""


class AuthorizationError(ConfirmatoryError):
    """The authorization does not permit this run, or does not match the tree."""


class WindowNotReadyError(ConfirmatoryError):
    """The confirmatory window does not yet hold the required closed candles."""


class WindowExposureError(ConfirmatoryError):
    """The single-use rule of the confirmatory window would be violated."""


class AttemptBudgetError(ConfirmatoryError):
    """The authorized attempt has already been consumed."""


class DataVerificationError(ConfirmatoryError):
    """The window data does not verify against what was recorded."""


__all__ = [
    "AttemptBudgetError",
    "AuthorizationError",
    "BoundsError",
    "ConfirmatoryError",
    "DataVerificationError",
    "ScopeError",
    "WindowExposureError",
    "WindowNotReadyError",
]

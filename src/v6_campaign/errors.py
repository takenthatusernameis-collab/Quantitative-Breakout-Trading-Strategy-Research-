"""Typed failures of the isolated v6 selection execution path."""
from __future__ import annotations

class V6CampaignError(RuntimeError):
    """Base class for fail-closed v6 selection failures."""

class ScopeError(V6CampaignError):
    """Frozen scope, manifest, authorization or source identity mismatch."""

class ConfirmatoryWindowViolation(V6CampaignError):
    """A protected candle would be read by the selection campaign."""

class BoundsError(V6CampaignError):
    """The authorized selection bounds would be exceeded."""

class AttemptBudgetError(V6CampaignError):
    """The single authorized logical run has already completed or exhausted retries."""

class DataVerificationError(V6CampaignError):
    """A published development dataset is missing or does not verify."""

class BenchmarkAlignmentError(V6CampaignError):
    """The BTC benchmark does not cover the evaluated asset timestamps."""

"""Auth tests for continuous cycles."""
from breakout_research import continuous_universe as cu
from breakout_research import continuous_universe_coordinator as coc
from breakout_research.pilot_gate_validator import load_authorization, authorize_campaign, VALIDATOR_ARTIFACT_PATH
import json
from pathlib import Path


def test_per_cycle_auth_rejects_stale():
    # ensure current auth is valid
    auth = load_authorization(VALIDATOR_ARTIFACT_PATH)
    assert auth.get("authorized") is True

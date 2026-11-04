from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from v6_confirmatory.errors import AuthorizationError
from v6_confirmatory.provider import fetch_window_rows


class NeverCalledSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("network must not be called without explicit authorization")


def _hash(document: dict) -> str:
    body = dict(document)
    body.pop("manifest_hash", None)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_provider_refuses_missing_authorization_before_network(tmp_path: Path) -> None:
    session = NeverCalledSession()
    with pytest.raises(AuthorizationError):
        fetch_window_rows(
            "FETUSDT",
            1792634400000,
            1792803600000,
            repo_root=tmp_path,
            session=session,
        )
    assert session.calls == 0


def test_provider_refuses_draft_authorization_before_network(tmp_path: Path) -> None:
    auth_path = tmp_path / "configs" / "research_v6_confirmatory_authorization_1.json"
    auth_path.parent.mkdir(parents=True)
    document = {
        "authorized_run": {
            "authorized": False,
            "provider_access_authorized": False,
            "data_scope_assets": ["FETUSDT", "BTCUSDT"],
            "window": {
                "window_start_utc": "2026-10-22T02:00:00Z",
                "exclusive_close_end_utc": "2027-01-20T03:00:00Z",
                "minimum_closed_hourly_candles": 2160,
                "membership_rule": "strict_close_time_after_start_and_before_exclusive_end",
            },
        },
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash"]},
        "manifest_hash": "",
    }
    document["manifest_hash"] = _hash(document)
    auth_path.write_text(json.dumps(document), encoding="utf-8")
    session = NeverCalledSession()
    with pytest.raises(AuthorizationError):
        fetch_window_rows(
            "FETUSDT",
            1792634400000,
            1800414000000,
            repo_root=tmp_path,
            session=session,
        )
    assert session.calls == 0

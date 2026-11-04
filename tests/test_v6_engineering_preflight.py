from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "v6_engineering_preflight.py"
SPEC = importlib.util.spec_from_file_location("v6_engineering_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_spec_hashing_uses_specification_excluded_key() -> None:
    document = {
        "value": 7,
        "specification_hash": "placeholder",
        "hashing": {"excluded_keys": ["specification_hash"]},
    }
    expected = MODULE.sha256_bytes(MODULE.canonical({"value": 7}))
    assert MODULE.self_hash(document) == expected


def test_strict_close_membership_requires_exclusive_bound_one_hour_after_last_close() -> None:
    from datetime import timedelta

    start = MODULE.parse_utc("2026-10-22T02:00:00Z")
    minimum = 2160
    last_close = start + timedelta(hours=minimum)
    exclusive_end = last_close + timedelta(hours=1)

    old_end = start + timedelta(hours=minimum)
    eligible_old = sum(
        1 for k in range(1, minimum + 1)
        if start + timedelta(hours=k) < old_end
    )
    eligible_new = sum(
        1 for k in range(1, minimum + 1)
        if start + timedelta(hours=k) < exclusive_end
    )
    assert eligible_old == 2159
    assert eligible_new == 2160
    assert last_close.isoformat().replace("+00:00", "Z") == "2027-01-20T02:00:00Z"
    assert exclusive_end.isoformat().replace("+00:00", "Z") == "2027-01-20T03:00:00Z"

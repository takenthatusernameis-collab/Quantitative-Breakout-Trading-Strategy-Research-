"""Tests for the offline v6 readiness-preflight primitives."""
import hashlib
import json
from pathlib import Path

from scripts.v6_readiness_preflight import manifest_digest, source_tree_digest


def test_manifest_digest_uses_declared_exclusions_and_nested_keys():
    document = {
        "a": 1,
        "manifest_hash": "ignored",
        "snapshot_identity": {"data_manifest_hash": "cycle", "other": "kept"},
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash", "snapshot_identity.data_manifest_hash"]},
    }
    body = {
        "a": 1,
        "snapshot_identity": {"other": "kept"},
        "hashing": {"manifest_hash_excluded_keys": ["manifest_hash", "snapshot_identity.data_manifest_hash"]},
    }
    expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert manifest_digest(document) == expected


def test_source_tree_digest_is_order_independent_and_content_sensitive(tmp_path: Path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "b.py").write_text("B = 2\n", encoding="utf-8")
    (root / "a.py").write_text("A = 1\n", encoding="utf-8")
    first = source_tree_digest(root)
    assert first is not None
    (root / "a.py").write_text("A = 3\n", encoding="utf-8")
    assert source_tree_digest(root) != first


def test_source_tree_digest_returns_none_for_missing_or_empty_tree(tmp_path: Path):
    assert source_tree_digest(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert source_tree_digest(empty) is None

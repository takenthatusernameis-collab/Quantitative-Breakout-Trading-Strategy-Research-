#!/usr/bin/env python3
"""Build the v3 universe and data manifests (BRAIN-012 P2 and P3).

This is the CLI entry point of the v3 constituent validation; the implementation
lives in ``scripts/v3_constituent_validation.py``, which applies the frozen
v3 specification and the published v3 exclusion amendment to real provider
data and writes ``research/universe_manifest_v3.json`` and
``research/data_manifest_v3.json``.

Usage::

    python3 scripts/build_v3_manifests.py --help
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v3_constituent_validation import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the v4 universe and data manifests (BRAIN-013 P2 and P3)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v4_constituent_validation import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

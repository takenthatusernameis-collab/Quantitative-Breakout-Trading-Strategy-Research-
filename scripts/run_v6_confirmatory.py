#!/usr/bin/env python3
"""Explicit entry point for the single v6 confirmatory run.

No network request or execution occurs unless --run is supplied. A separate
hash-bound confirmatory authorization and a passed metadata preflight are
required by the runner/provider.
"""
from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v6_confirmatory.runner import default_workspace, run_confirmatory  # noqa: E402
from v6_confirmatory.provider import fetch_window_rows  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="perform the separately authorized single-use evaluation")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        print("\nNo requests were made and no evaluation was started.")
        return 0

    workspace = default_workspace(ROOT)
    fetch = partial(fetch_window_rows, repo_root=ROOT)
    result = run_confirmatory(workspace, fetch_rows=fetch)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

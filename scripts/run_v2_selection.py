#!/usr/bin/env python3
"""Perform the single authorized v2 selection run.

The run is authorized by ``configs/research_v2_selection_authorization_1.json``
and consumes its single logical attempt. It is **resumable**: an interrupted
process leaves the verified shards in place and the next process continues the
same logical run from them. A completed run is never re-run.

The script is a thin wrapper around ``v2_campaign.runner.run_selection``. It
adds a progress line (read from the checkpoint the run writes) and it prints
the resulting ledger document as JSON. It never touches a v1 path, never reads
a confirmatory-window candle and never contacts a provider.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from v2_campaign import runner  # noqa: E402


def _progress_printer(workspace: runner.Workspace, interval: float, stop: threading.Event) -> None:
    """Print the progress the run records in its checkpoint."""
    while not stop.wait(interval):
        try:
            checkpoint = json.loads(Path(workspace.checkpoint).read_text(encoding="utf-8"))
            shard_count = sum(
                1 for path in Path(workspace.shards_dir).rglob("shard_*.jsonl")
            )
            print(
                "progress: completed_records=%s shards=%s asset=%s config=%s fold=%s cost=%s"
                % (
                    checkpoint.get("completed_records"),
                    shard_count,
                    checkpoint.get("current_asset_index"),
                    checkpoint.get("current_config_index"),
                    checkpoint.get("current_fold_index"),
                    checkpoint.get("current_cost_index"),
                ),
                flush=True,
            )
        except Exception:  # pragma: no cover - progress must never break the run
            continue


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--progress-interval", type=float, default=60.0)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    workspace = runner.default_workspace(repo_root)

    stop = threading.Event()
    printer = threading.Thread(
        target=_progress_printer,
        args=(workspace, args.progress_interval, stop),
        daemon=True,
    )
    printer.start()
    started = time.perf_counter()
    try:
        document = runner.run_selection(workspace)
    except Exception as exc:
        stop.set()
        print(json.dumps({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}))
        raise
    finally:
        stop.set()
    elapsed = time.perf_counter() - started
    document = dict(document)
    document["wall_clock_seconds"] = round(elapsed, 3)
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

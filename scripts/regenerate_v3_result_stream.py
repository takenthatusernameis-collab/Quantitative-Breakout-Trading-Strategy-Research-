#!/usr/bin/env python3
"""Regenerate the v3 result stream from the verified shards.

The shards under ``research/shards_v3/`` are the authoritative record set of
the v3 selection run. The single-file result stream
``research/results_v3.jsonl`` is a *projection* of them, exactly as the v2
line records in ``configs/research_v2_selection_authorization_1.json``
(residual limitation RL2): at the size of the authorized run it exceeds the
per-file push limit, so it is not committed, and it is rebuilt from the shards
on demand. The file is listed in ``.gitignore`` for that reason; a checkout
that does not have it is missing a projection, not a run.

The projection is written in shard order, one record per line, exactly as the
run wrote it. Every record is re-verified while it is written: an experiment id
that does not recompute from its own content aborts the regeneration, so a
corrupted or hand-edited shard can never become the stream.

The stream is written atomically: the projection is built in a temporary file
next to the target and renamed into place only after it is complete.

Exit status is 0 when the stream was rebuilt and 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from breakout_research.backtest.shards import compute_experiment_id  # noqa: E402

SHARDS_RELATIVE = "research/shards_v3"
STREAM_RELATIVE = "research/results_v3.jsonl"


def _shard_paths(shard_root: Path, campaign_id: str) -> List[Path]:
    directory = shard_root / campaign_id
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.name.startswith("shard_") and path.name.endswith(".jsonl")
    )


def regenerate(
    repo_root: Path = REPO_ROOT, campaign_id: str = "v3-campaign"
) -> Dict[str, Any]:
    shard_root = repo_root / SHARDS_RELATIVE
    target = repo_root / STREAM_RELATIVE
    paths = _shard_paths(shard_root, campaign_id)
    if not paths:
        return {"ok": False, "failures": ["the campaign has no shard to project from"]}

    temporary = target.with_suffix(target.suffix + ".tmp")
    rows = 0
    hasher = hashlib.sha256()
    failures: List[str] = []
    with temporary.open("wb") as handle:
        for path in paths:
            with path.open("rb") as source:
                for line_number, raw in enumerate(source, start=1):
                    if not raw.strip():
                        continue
                    record = json.loads(raw)
                    recomputed = compute_experiment_id(
                        spec_hash=record.get("specification_hash", ""),
                        code_hash=record.get("code_hash", ""),
                        data_hash=record.get("data_hash", ""),
                        asset=record.get("asset", ""),
                        config_id=record.get("config_id", ""),
                        fold_index=record.get("fold_index", 0),
                        start_time=record.get("start_time", 0),
                        end_time=record.get("end_time", 0),
                        is_holdout=record.get("is_holdout", False),
                        cost_multiplier=record.get("cost_multiplier", 0.0),
                    )
                    if recomputed != record.get("experiment_id"):
                        failures.append(
                            f"{path.name} line {line_number}: the experiment id does not recompute"
                        )
                        break
                    handle.write(raw)
                    hasher.update(raw)
                    rows += 1
            if failures:
                break
        handle.flush()
        os.fsync(handle.fileno())
    if failures:
        temporary.unlink(missing_ok=True)
        return {"ok": False, "failures": failures}
    os.replace(temporary, target)
    return {
        "ok": True,
        "failures": [],
        "path": str(target),
        "rows": rows,
        "shards": len(paths),
        "bytes": target.stat().st_size,
        "sha256": hasher.hexdigest(),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--campaign-id", default="v3-campaign")
    args = parser.parse_args(argv)
    report = regenerate(Path(args.repo_root).resolve(), args.campaign_id)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

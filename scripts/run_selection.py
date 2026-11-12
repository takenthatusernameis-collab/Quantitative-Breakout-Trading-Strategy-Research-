#!/usr/bin/env python3
"""Run preregistered selection on validation units only.

This script loads validation records from the old campaign shards
and runs the preregistered selection, verifying that holdout records
raise HoldoutRecordError.
"""

import json
from pathlib import Path

from src.breakout_research.selection import select_candidates, HoldoutRecordError
from src.breakout_research.config import load_research_spec
from src.breakout_research.baselines import baseline_for_asset, VARIANT_BASELINE


SHARD_ROOT = "research/results_shards"
OLD_CAMPAIGN_ID = "41f0dc8d48674ef33cbe7e636fb476bab981286a3cc11dfb158f5f89bc6607c1"


def iter_shard_records(shard_root: Path):
    """Yield every record of a shard set in deterministic shard order."""
    for path in sorted(Path(shard_root).glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def main():
    spec = load_research_spec()
    selection_spec = spec["selection"]

    # Load baseline artifact
    baseline_artifact_path = "research/baselines/577e87e2dc37b496b4d0c9e1a2eeecc9a777f01698591fc395dddb12f45708cb.json"
    with open(baseline_artifact_path, "r", encoding="utf-8") as f:
        baseline_artifact = json.load(f)

    baselines = {}
    for asset in baseline_artifact.get("assets", {}):
        baselines[asset] = baseline_for_asset(baseline_artifact, asset)

    print(f"Loaded baselines for {len(baselines)} assets")

    # Load validation records from old campaign shards
    shard_dir = Path(SHARD_ROOT) / OLD_CAMPAIGN_ID
    records = list(iter_shard_records(shard_dir))
    print(f"Loaded {len(records)} records from old campaign shards")

    # Filter to validation records only (no holdout)
    validation_records = [r for r in records if not r.get("is_holdout", False)]
    holdout_records = [r for r in records if r.get("is_holdout", False)]
    print(f"Validation records: {len(validation_records)}")
    print(f"Holdout records in old shards: {len(holdout_records)}")

    # Run selection on validation records only
    print("\nRunning preregistered selection on validation records...")
    selection = select_candidates(validation_records, {"selection": selection_spec}, baselines)

    print("\n=== SELECTION RESULTS ===")
    for asset, result in sorted(selection.items()):
        print(f"  {asset}: {result['status']} - config_id={result.get('config_id')}")
        if result.get('gates'):
            for gate_name, gate_info in result['gates'].items():
                pass_status = gate_info.get('pass')
                if pass_status is None:
                    status_str = gate_info.get('status', 'UNKNOWN')
                else:
                    status_str = 'PASS' if pass_status else 'FAIL'
                print(f"    {gate_name}: {status_str}")

    # Verify that adding a holdout record raises HoldoutRecordError
    print("\n=== TESTING HOLDOUT RECORD REJECTION ===")
    if holdout_records:
        test_record = holdout_records[0]
        print(f"Testing with holdout record: {test_record['asset']} {test_record['config_id']} fold={test_record['fold_index']}")
        try:
            select_candidates(validation_records + [test_record], {"selection": selection_spec}, baselines)
            print("ERROR: Should have raised HoldoutRecordError!")
        except HoldoutRecordError as e:
            print(f"SUCCESS: HoldoutRecordError raised as expected: {e}")
        except Exception as e:
            print(f"ERROR: Wrong exception type: {type(e).__name__}: {e}")

    # Also test with validation + all holdout records
    print("\nTesting with all holdout records...")
    try:
        select_candidates(validation_records + holdout_records, {"selection": selection_spec}, baselines)
        print("ERROR: Should have raised HoldoutRecordError!")
    except HoldoutRecordError as e:
        print(f"SUCCESS: HoldoutRecordError raised as expected: {e}")
    except Exception as e:
        print(f"ERROR: Wrong exception type: {type(e).__name__}: {e}")

    print("\nSelection test complete.")


if __name__ == "__main__":
    main()
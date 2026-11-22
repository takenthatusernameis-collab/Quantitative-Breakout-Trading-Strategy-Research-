#!/usr/bin/env python
"""Run holdout-enabled campaign over frozen v2 candidates with cohort limits."""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, 'src')

from breakout_research.campaign import CampaignRunner
from breakout_research.candidate_freeze import (
    load_candidate_manifest,
    CANDIDATE_MANIFEST_V2_PATH,
    candidate_config_ids,
)

def main():
    # Load v2 candidate manifest
    manifest = load_candidate_manifest(CANDIDATE_MANIFEST_V2_PATH)
    candidate_ids = candidate_config_ids(manifest)

    print(f"Loaded v2 candidate manifest:")
    print(f"  Campaign ID: {manifest['campaign_id']}")
    print(f"  Candidate status: {manifest['candidate_status']}")
    print(f"  Frozen candidates: {len(candidate_ids)}")
    print(f"  Candidate configs: {sorted(candidate_ids)[:5]}...")

    # Create campaign runner
    runner = CampaignRunner()

    # Get v2 candidate assets
    v2_assets = set(manifest['candidates'].keys())
    print(f"\nV2 candidate assets: {sorted(v2_assets)}")

    # Filter runner assets to only v2 candidates
    v2_runner_assets = [
        asset for asset in runner.assets
        if asset['symbol'] in v2_assets
    ]
    print(f"Assets to process: {len(v2_runner_assets)}")

    # Run holdout-enabled campaign with cohort limits
    print("\nStarting holdout-enabled campaign...")
    result = runner.run(
        holdout_enabled=True,
        max_assets=len(v2_runner_assets),  # Use all v2 assets
        max_configs=100,  # Limit configs to first 100 for cohort
        max_folds=5,  # All 5 folds including holdout
        max_costs=3,  # All 3 cost scenarios
        assets_override=v2_runner_assets,
    )

    print(f"\nCampaign result:")
    print(f"  Status: {result['status']}")
    print(f"  Records processed: {result.get('records_processed', 'N/A')}")
    print(f"  Holdout records: {result.get('holdout_records', 'N/A')}")

    # Save result
    output_path = Path('research/holdout_campaign_result.json')
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nResult saved to: {output_path}")

if __name__ == '__main__':
    main()
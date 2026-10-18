"""Resume cohort-0 cycle with corrected eligible-asset set (excl. insufficient-history assets)."""
import json
import sys
from pathlib import Path

CYCLE_ID = "0f52f6c9d8fd2ab5b6cd2f232226ae71045e5a0d95e6a1b9cd4525a55e10b05d"
CYCLE_DIR = Path(f"research/campaign_cycles/{CYCLE_ID}")
MANIFEST_PATH = str(CYCLE_DIR / "results_manifest.json")
SHARD_ROOT = str(CYCLE_DIR / "results_shards")

from breakout_research.config import load_universe_manifest, get_eligible_assets
from breakout_research.campaign import run_campaign

universe = load_universe_manifest("research/universe_manifest.json")
all_eligible = get_eligible_assets(universe)
# Exclude assets with a recorded exclusion_reason (insufficient history, etc.)
# without changing source code (preserves code hash / authorization binding).
eligible = [a for a in all_eligible if not a.get("exclusion_reason")]
print(f"All eligible ({len(all_eligible)}):", [a["symbol"] for a in all_eligible])
print(f"Processing ({len(eligible)}):", [a["symbol"] for a in eligible])

result = run_campaign(
    holdout_enabled=False,
    manifest_path=MANIFEST_PATH,
    shard_root=SHARD_ROOT,
    assets_override=eligible,
)
print(json.dumps(result, indent=2))

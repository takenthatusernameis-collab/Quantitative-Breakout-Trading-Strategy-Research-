#!/usr/bin/env python3
"""Verify the frozen v6 selection plan; execute only with an explicit --execute."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"src"))
def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",default=str(ROOT))
    parser.add_argument("--execute",action="store_true",
        help="consume the one existing v6 selection authorization and start/resume its bounded campaign")
    args=parser.parse_args(argv)
    from v6_campaign.runner import build_plan, default_workspace, run_selection
    plan=build_plan(default_workspace(Path(args.repo_root)))
    if not args.execute:
        print(json.dumps({
            "status":"PREFLIGHT_ONLY","run_started":False,
            "run_id":plan.run_id,"campaign_id":plan.campaign_id,
            "assets":[x["symbol"] for x in plan.assets],
            "configuration_count":len(plan.configs),
            "planned_config_units":plan.counts["config_units"],
            "planned_execution_units":plan.counts["execution_units"],
            "confirmatory_window_reads":0,
            "development_boundary_utc":plan.effective_data_boundary_utc,
            "earliest_confirmatory_evaluation_utc":"2027-01-20T02:00:00Z",
        },indent=2,sort_keys=True))
        return 0
    result=run_selection(default_workspace(Path(args.repo_root)))
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

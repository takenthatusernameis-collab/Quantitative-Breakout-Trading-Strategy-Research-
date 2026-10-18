import sys
sys.path.insert(0, 'src')

from breakout_research.continuous_universe_coordinator import ContinuousCycleCoordinator

c = ContinuousCycleCoordinator()
res = c.run_cycle(holdout_enabled=False)
print(res['state'])

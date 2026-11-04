"""v6 selection execution path.

This package reuses the frozen v1 engine without modifying src/breakout_research.
It reads development-only data through the v6 manifests and uses a separate
v6 output namespace. Importing this package never starts a run.
"""
__all__ = ["benchmark", "data", "errors", "identity", "runner", "scope", "units"]

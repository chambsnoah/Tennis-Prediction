"""
Enhanced Tennis Match Simulation Package

This package contains the enhanced match simulation engine that integrates
AI predictions and dynamic state management for realistic tennis simulations.
"""

from typing import List

# Lazy export map: name -> (module, attr)
_EXPORTS = {
    "EnhancedMatchEngine": (".enhanced_match_engine", "EnhancedMatchEngine"),
    "MatchState": (".enhanced_match_engine", "MatchState"),
    "PointOutcome": (".enhanced_match_engine", "PointOutcome"),
    "MatchStatistics": (".enhanced_match_engine", "MatchStatistics"),
}

__all__: List[str] = [
    "EnhancedMatchEngine",
    "MatchState",
    "PointOutcome", 
    "MatchStatistics",
]


# PEP 562: Lazy attribute access for re-exports
def __getattr__(name: str):
    try:
        from importlib import import_module
        mod_name, attr = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(mod_name, __package__)
    value = getattr(module, attr)
    globals()[name] = value  # cache after first access
    return value


def __dir__():
    return sorted(__all__)
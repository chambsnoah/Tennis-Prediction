"""
Tennis API Data Models.

This package contains data classes and models for representing tennis statistics,
tournament information, and match data retrieved from various tennis APIs.
"""

from importlib import import_module
from typing import List

# Explicit imports to satisfy linters while keeping lazy loading for performance
from .player_stats import PlayerStats, SurfaceStats, ServeStatistics, ReturnStatistics
from .enhanced_player import PlayerEnhanced, PhysicalCondition, MentalState, ContextualFactors
from .ai_player import PlayerAI, MLModel, PerformanceContext
from .tournament_data import TournamentDraw, Match
from .match_data import MatchResult, HeadToHeadRecord

# Lazy export map: name -> (module, attr)
_EXPORTS = {
    "PlayerStats": (".player_stats", "PlayerStats"),
    "SurfaceStats": (".player_stats", "SurfaceStats"),
    "ServeStatistics": (".player_stats", "ServeStatistics"),
    "ReturnStatistics": (".player_stats", "ReturnStatistics"),
    "PlayerEnhanced": (".enhanced_player", "PlayerEnhanced"),
    "PhysicalCondition": (".enhanced_player", "PhysicalCondition"),
    "MentalState": (".enhanced_player", "MentalState"),
    "ContextualFactors": (".enhanced_player", "ContextualFactors"),
    "PlayerAI": (".ai_player", "PlayerAI"),
    "MLModel": (".ai_player", "MLModel"),
    "PerformanceContext": (".ai_player", "PerformanceContext"),
    "TournamentDraw": (".tournament_data", "TournamentDraw"),
    "Match": (".tournament_data", "Match"),
    "MatchResult": (".match_data", "MatchResult"),
    "HeadToHeadRecord": (".match_data", "HeadToHeadRecord"),
}

__all__: List[str] = [
    "PlayerStats",
    "SurfaceStats", 
    "ServeStatistics",
    "ReturnStatistics",
    "PlayerEnhanced",
    "PhysicalCondition",
    "MentalState",
    "ContextualFactors",
    "PlayerAI",
    "MLModel",
    "PerformanceContext",
    "TournamentDraw",
    "Match",
    "MatchResult",
    "HeadToHeadRecord",
]


# PEP 562: Lazy attribute access for re-exports
def __getattr__(name: str):
    try:
        mod_name, attr = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(mod_name, __package__)
    value = getattr(module, attr)
    globals()[name] = value  # cache after first access
    return value


def __dir__():
    return sorted(__all__)
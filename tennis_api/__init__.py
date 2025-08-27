"""
Tennis API Integration Module

This module provides real-time tennis data integration capabilities for the Tennis Prediction System.
It includes API clients for multiple tennis data sources, caching mechanisms, and data models.

Components:
- models: Data structures for tennis statistics and tournament information
- clients: API client implementations for different tennis data providers
- cache: Caching and rate limiting functionality
- extractors: API-based data extraction replacing static file processing
- config: Configuration management for API credentials and settings
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import CacheManager, RateLimiter
    from .clients import TennisAPIClient
    from .models import MatchResult, PlayerStats, SurfaceStats, TournamentDraw

# Export map for lazy loading
_EXPORTS = {
    "PlayerStats": "tennis_api.models",
    "TournamentDraw": "tennis_api.models",
    "MatchResult": "tennis_api.models",
    "SurfaceStats": "tennis_api.models",
    "TennisAPIClient": "tennis_api.clients",
    "CacheManager": "tennis_api.cache",
    "RateLimiter": "tennis_api.cache",
}

# Dynamic version detection
try:
    from importlib.metadata import version
    __version__ = version("tennis-api")
except ImportError:
    try:
        import pkg_resources
        __version__ = pkg_resources.get_distribution("tennis-api").version
    except Exception:
        __version__ = "0.0.0"
except Exception:
    __version__ = "0.0.0"

# Explicit exports for static analysis
__all__ = (
    "PlayerStats",
    "TournamentDraw", 
    "MatchResult",
    "SurfaceStats",
    "TennisAPIClient",
    "CacheManager",
    "RateLimiter",
)


def __getattr__(name: str):
    """Lazy import implementation following PEP 562."""
    if name in _EXPORTS:
        module_name = _EXPORTS[name]
        module = importlib.import_module(module_name)
        attr = getattr(module, name)
        # Cache the imported attribute on this module
        globals()[name] = attr
        return attr
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Return sorted list of available attributes for IDE support."""
    return sorted(__all__)
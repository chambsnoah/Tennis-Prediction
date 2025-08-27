"""
Tennis API Data Extractors

This package contains extractors that replace static file-based data extraction
with real-time API-based data extraction for tournaments and player information.
Usage: from tennis_api.extractors import APIPlayerExtractor, APITournamentExtractor
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_extractor import APIPlayerExtractor
    from ..integration import APITournamentExtractor

__all__ = (
    "APIPlayerExtractor",
    "APITournamentExtractor",
)


def __getattr__(name: str):
    """Lazy loading of extractor classes"""
    if name == "APIPlayerExtractor":
        from .api_extractor import APIPlayerExtractor
        globals()["APIPlayerExtractor"] = APIPlayerExtractor
        return APIPlayerExtractor
    elif name == "APITournamentExtractor":
        from ..integration import APITournamentExtractor
        globals()["APITournamentExtractor"] = APITournamentExtractor
        return APITournamentExtractor
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Support for introspection"""
    return list(__all__)
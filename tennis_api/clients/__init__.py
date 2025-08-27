"""
Tennis API Clients

API client implementations for tennis data providers with unified interface and error handling.
Usage: from tennis_api.clients import TennisAPIClient
"""

from typing import TYPE_CHECKING

# For static type checkers, import everything explicitly
if TYPE_CHECKING:
    from .base_client import BaseAPIClient
    from .tennis_api_client import TennisAPIClient

# PEP 562 lazy loading to avoid import-time side effects and circular imports
__all__ = (
    "BaseAPIClient",
    "TennisAPIClient"
)


def __getattr__(name: str):
    """Lazy import implementation for public API objects."""
    if name == "BaseAPIClient":
        from .base_client import BaseAPIClient
        globals()["BaseAPIClient"] = BaseAPIClient
        return BaseAPIClient
    elif name == "TennisAPIClient":
        from .tennis_api_client import TennisAPIClient
        globals()["TennisAPIClient"] = TennisAPIClient
        return TennisAPIClient
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Return the list of publicly available names."""
    return __all__
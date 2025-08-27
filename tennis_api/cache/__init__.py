"""
Tennis API caching and rate limiting utilities.

Provides intelligent caching with TTL and rate limiting across multiple API providers.
"""

from typing import TYPE_CHECKING

# For static type checkers, import everything explicitly
if TYPE_CHECKING:
    from .cache_manager import CacheManager
    from .rate_limiter import RateLimiter

# PEP 562 lazy loading to avoid import-time side effects and circular imports
__all__ = (
    "CacheManager",
    "RateLimiter",
)


def __getattr__(name: str):
    """Lazy import implementation for public API objects."""
    if name == "CacheManager":
        from .cache_manager import CacheManager
        globals()["CacheManager"] = CacheManager
        return CacheManager
    elif name == "RateLimiter":
        from .rate_limiter import RateLimiter
        globals()["RateLimiter"] = RateLimiter
        return RateLimiter
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Return the list of publicly available names."""
    return __all__
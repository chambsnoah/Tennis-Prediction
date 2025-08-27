"""
Tennis API Configuration

Configuration management for tennis API integration including credentials, endpoints, and rate-limiting configuration.
"""

from typing import TYPE_CHECKING

# For static type checkers, import everything explicitly
if TYPE_CHECKING:
    from .api_config import APIConfig, get_api_config
    from .test_config import TestConfig

# PEP 562 lazy loading to avoid import-time side effects and circular imports
__all__ = (
    "APIConfig",
    "get_api_config",
    "TestConfig",
)


def __getattr__(name: str):
    """Lazy import implementation for public API objects."""
    if name == "APIConfig":
        from .api_config import APIConfig
        globals()["APIConfig"] = APIConfig
        return APIConfig
    elif name == "get_api_config":
        from .api_config import get_api_config
        globals()["get_api_config"] = get_api_config
        return get_api_config
    elif name == "TestConfig":
        from .test_config import TestConfig
        globals()["TestConfig"] = TestConfig
        return TestConfig
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    """Return the list of publicly available names."""
    return __all__
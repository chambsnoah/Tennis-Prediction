"""
HTTP Adapters Package

Provides abstraction layers for HTTP operations, isolating direct usage
of HTTP libraries behind unified interfaces.
"""

from .http_adapter import (
    HTTPResponse,
    HTTPAdapter,
    AsyncHTTPAdapter,
    RequestsAdapter,
    AiohttpAdapter,
    UnifiedHTTPClient,
    get,
    get_async,
    post,
    post_async,
)

__all__ = [
    'HTTPResponse',
    'HTTPAdapter',
    'AsyncHTTPAdapter', 
    'RequestsAdapter',
    'AiohttpAdapter',
    'UnifiedHTTPClient',
    'get',
    'get_async',
    'post', 
    'post_async',
]
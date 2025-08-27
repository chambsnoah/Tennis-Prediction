"""
HTTP Adapter Abstraction

Provides unified interface for HTTP operations with both synchronous and 
asynchronous implementations. Isolates direct usage of requests and aiohttp
libraries behind a common interface.

This module documents why both HTTP libraries are required:
- requests: For synchronous operations needed by sync wrapper methods and integration with existing sync code
- aiohttp: For asynchronous operations providing better performance and concurrent request handling
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any

import aiohttp
import requests


class HTTPResponse:
    """Unified response object for both sync and async HTTP operations"""
    
    def __init__(self, status_code: int, headers: Dict[str, str], content: bytes, text: str):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.text = text
        self._json_data = None
    
    def json(self) -> Dict[str, Any]:
        """Parse response as JSON"""
        if self._json_data is None:
            self._json_data = json.loads(self.text)
        return self._json_data
    
    @property
    def ok(self) -> bool:
        """Check if response status indicates success"""
        return 200 <= self.status_code < 300


class HTTPAdapter(ABC):
    """Abstract base class for HTTP adapters"""
    
    @abstractmethod
    def request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Make HTTP request and return unified response"""
        pass
    
    @abstractmethod
    def close(self):
        """Close any open connections"""
        pass


class AsyncHTTPAdapter(ABC):
    """Abstract base class for async HTTP adapters"""
    
    @abstractmethod
    async def request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Make async HTTP request and return unified response"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close any open connections"""
        pass


class RequestsAdapter(HTTPAdapter):
    """Synchronous HTTP adapter using requests library"""
    
    def __init__(self, timeout: int = 30, headers: Optional[Dict[str, str]] = None):
        self.session: Optional[requests.Session] = requests.Session()
        self.timeout = timeout
        if headers and self.session:
            self.session.headers.update(headers)
    
    def request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Make synchronous HTTP request using requests"""
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        if self.session is None:
            raise RuntimeError("Session is closed")
        
        response = self.session.request(method, url, **kwargs)
        
        return HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
            text=response.text
        )
    
    def close(self):
        """Close requests session"""
        if self.session:
            self.session.close()
            self.session = None


class AiohttpAdapter(AsyncHTTPAdapter):
    """Asynchronous HTTP adapter using aiohttp library"""
    
    def __init__(self, timeout: int = 30, headers: Optional[Dict[str, str]] = None):
        self._session = None
        self.timeout = timeout
        self.headers = headers or {}
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout_obj = aiohttp.ClientTimeout(total=self.timeout)  # type: ignore
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout_obj,
                headers=self.headers
            )
        return self._session
    
    async def request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Make asynchronous HTTP request using aiohttp"""
        session = await self._get_session()
        
        # Convert requests-style kwargs to aiohttp format
        aiohttp_kwargs = {}
        if 'params' in kwargs:
            aiohttp_kwargs['params'] = kwargs['params']
        if 'json' in kwargs:
            aiohttp_kwargs['json'] = kwargs['json']
        if 'data' in kwargs:
            aiohttp_kwargs['data'] = kwargs['data']
        if 'headers' in kwargs:
            aiohttp_kwargs['headers'] = kwargs['headers']
        
        # Handle timeout
        timeout = kwargs.get('timeout', self.timeout)
        if timeout:
            aiohttp_kwargs['timeout'] = aiohttp.ClientTimeout(total=timeout)  # type: ignore
        
        async with session.request(method, url, **aiohttp_kwargs) as response:
            content = await response.read()
            text = await response.text()
            
            return HTTPResponse(
                status_code=response.status,
                headers=dict(response.headers),
                content=content,
                text=text
            )
    
    async def close(self):
        """Close aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


class UnifiedHTTPClient:
    """
    Unified HTTP client that provides both sync and async interfaces
    
    This class demonstrates the need for both requests and aiohttp:
    - Sync methods use requests for compatibility with existing synchronous code
    - Async methods use aiohttp for better performance in concurrent scenarios
    """
    
    def __init__(self, timeout: int = 30, headers: Optional[Dict[str, str]] = None):
        self.sync_adapter = RequestsAdapter(timeout, headers)
        self.async_adapter = AiohttpAdapter(timeout, headers)
    
    def get(self, url: str, **kwargs) -> HTTPResponse:
        """Synchronous GET request"""
        return self.sync_adapter.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> HTTPResponse:
        """Synchronous POST request"""
        return self.sync_adapter.request('POST', url, **kwargs)
    
    def request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Synchronous HTTP request"""
        return self.sync_adapter.request(method, url, **kwargs)
    
    async def get_async(self, url: str, **kwargs) -> HTTPResponse:
        """Asynchronous GET request"""
        return await self.async_adapter.request('GET', url, **kwargs)
    
    async def post_async(self, url: str, **kwargs) -> HTTPResponse:
        """Asynchronous POST request"""
        return await self.async_adapter.request('POST', url, **kwargs)
    
    async def request_async(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Asynchronous HTTP request"""
        return await self.async_adapter.request(method, url, **kwargs)
    
    def close(self):
        """Close all connections"""
        self.sync_adapter.close()
    
    async def close_async(self):
        """Close all async connections"""
        await self.async_adapter.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_async()


# Convenience functions for quick usage
def get(url: str, **kwargs) -> HTTPResponse:
    """Quick synchronous GET request"""
    with UnifiedHTTPClient() as client:
        return client.get(url, **kwargs)


async def get_async(url: str, **kwargs) -> HTTPResponse:
    """Quick asynchronous GET request"""
    async with UnifiedHTTPClient() as client:
        return await client.get_async(url, **kwargs)


def post(url: str, **kwargs) -> HTTPResponse:
    """Quick synchronous POST request"""
    with UnifiedHTTPClient() as client:
        return client.post(url, **kwargs)


async def post_async(url: str, **kwargs) -> HTTPResponse:
    """Quick asynchronous POST request"""
    async with UnifiedHTTPClient() as client:
        return await client.post_async(url, **kwargs)
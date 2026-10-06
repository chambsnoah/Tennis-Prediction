"""Regressions for offline execution and cache-free test collection."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tennis_api.cache.cache_manager import CacheManager
from tennis_api.cache.rate_limiter import RateLimiter
from tennis_api.clients.tennis_api_client import TennisAPIClient
from tennis_api.config.test_config import TestConfig


def test_imports_do_not_create_cache_or_load_credentials(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = (
        "import importlib, pathlib; "
        "from tennis_api import TennisAPIClient; "
        "from tennis_api.cache import CacheManager, RateLimiter; "
        "importlib.import_module('tennis_api.tests.test_basic_functionality'); "
        "assert not list(pathlib.Path.cwd().iterdir())"
    )
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, check=True)


def test_explicit_client_storage_does_not_create_default_cache(tmp_path):
    cache = CacheManager(str(tmp_path / "storage" / "responses"))
    limiter = RateLimiter(state_file=str(tmp_path / "storage" / "quotas.json"))
    client = TennisAPIClient(
        TestConfig.get_mock_config(), cache_manager=cache, rate_limiter=limiter
    )
    try:
        assert client.cache_manager is cache
        assert client.rate_limiter is limiter
        assert not (tmp_path / "cache").exists()
        assert limiter.acquire("rapidapi_tennis_live")
        limiter._save_state()
        assert limiter.state_file.exists()
    finally:
        client.close()


def test_default_tests_have_no_real_credentials():
    assert "RAPID_API_APPLICATION_KEY" not in os.environ
    assert "ENABLE_LIVE_API_TESTS" not in os.environ


def test_unmocked_network_is_rejected():
    with pytest.raises(AssertionError, match="Network access is disabled"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="Network access is disabled"):
            connection.connect(("127.0.0.1", 443))

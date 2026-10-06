"""Offline client wiring and explicitly opted-in live endpoint checks."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tennis_api.cache.cache_manager import CacheManager
from tennis_api.cache.rate_limiter import RateLimiter
from tennis_api.clients.tennis_api_client import TennisAPIClient
from tennis_api.config.api_config import get_api_config
from tennis_api.config.test_config import TestConfig
from tennis_api.tests.test_framework import run_api_tests


def test_basic_functionality(tmp_path):
    config = TestConfig.get_mock_config()
    cache = CacheManager(cache_dir=str(tmp_path / "cache"))
    limiter = RateLimiter(state_file=str(tmp_path / "rate_limiter_state.json"))
    with TennisAPIClient(config, cache_manager=cache, rate_limiter=limiter) as client:
        assert client.clients
        assert client.cache_manager is cache
        assert client.rate_limiter is limiter
        assert client.cache_manager.get_cache_size()["total_files"] == 0
        assert isinstance(client.rate_limiter.get_usage_stats(), dict)
        for subclient in client.clients.values():
            assert subclient.cache_manager is cache
            assert subclient.rate_limiter is limiter


def test_offline_framework():
    report = run_api_tests(use_live_apis=False, max_live_requests=0)
    assert report["summary"]["total_tests"] > 0
    assert report["summary"]["failed"] == 0, report["errors"]
    assert report["summary"]["all_passed"] is True


@pytest.mark.live
def test_with_minimal_api_calls(tmp_path):
    """Requires --live and an environment credential; makes two endpoint calls."""
    if not os.environ.get("RAPID_API_APPLICATION_KEY"):
        pytest.skip("RAPID_API_APPLICATION_KEY is required for live API testing")

    config = get_api_config()
    for endpoint in config.get_all_configs().values():
        endpoint.max_retries = 0
        endpoint.timeout = 10

    cache = CacheManager(cache_dir=str(tmp_path / "cache"))
    limits = {
        endpoint.name: {
            f"requests_per_{period}": getattr(endpoint.rate_limit, f"per_{period}")
            for period in ("minute", "hour", "day", "month")
        }
        for endpoint in config.get_all_configs().values()
    }
    limiter = RateLimiter(limits_config=limits, state_file=str(tmp_path / "rate_limiter_state.json"))
    with TennisAPIClient(config, cache_manager=cache, rate_limiter=limiter) as client:
        # High-level methods can fall back across providers or synthesize model
        # defaults. Validate uncached endpoint payloads, not those defaults.
        response = client.clients["rankings"].get_data_sync(
            "current_rankings", tour="atp", use_cache=False, priority="high"
        )
        assert isinstance(response, dict)
        rankings = response.get("rankings") or response.get("players")
        assert isinstance(rankings, list) and rankings, "Missing live rankings"
        assert isinstance(rankings[0], dict)
        assert rankings[0].get("name"), "Missing ranked player name"
        assert int(rankings[0].get("ranking", rankings[0].get("rank", 0))) > 0

        response = client.clients["live"].get_data_sync(
            "player_search", params={"name": "Novak Djokovic"},
            use_cache=False, priority="high",
        )
        assert isinstance(response, dict)
        players = response.get("players")
        assert isinstance(players, list) and players, "Missing live player search results"
        assert any(player.get("id") and player.get("name") for player in players)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "pytest", *(args or [str(Path(__file__).resolve())])],
        cwd=root,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())

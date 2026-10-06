"""Offline basic checks with explicit, disposable working state."""

from tennis_api.cache.cache_manager import CacheManager
from tennis_api.cache.rate_limiter import RateLimiter
from tennis_api.clients.base_client import APIException
from tennis_api.config.test_config import TestConfig


def test_rate_limiter_acquisition_and_usage(tmp_path):
    state_file = tmp_path / "rate_limiter_state.json"
    with RateLimiter(state_file=str(state_file)) as limiter:
        availability = limiter.check_availability("rapidapi_tennis_live", "normal")
        assert availability["available"] is True
        assert limiter.acquire("rapidapi_tennis_live", "normal") is True

        stats = limiter.get_usage_stats("rapidapi_tennis_live")
        assert stats["current_usage"]["minute"] == 1
    assert state_file.is_file()


def test_cache_round_trip(tmp_path):
    cache = CacheManager(cache_dir=str(tmp_path / "cache"))
    data = {"name": "Test Player", "ranking": 1}
    cache.set("player", data, "player_stats")

    assert cache.get("player", "player_stats") == data
    assert cache.invalidate("player", "player_stats") is True
    assert cache.get("player", "player_stats") is None


def test_mock_configuration():
    config = TestConfig.get_mock_config()
    assert config.rapid_api_key == "mock_test_key_12345"
    assert config.tennis_live_api is not None
    assert config.tennis_live_api.headers["X-RapidAPI-Key"] == config.rapid_api_key


def test_api_exception_preserves_response_details():
    error = APIException("Request failed", status_code=503, response_data={"error": "unavailable"})
    assert str(error) == "Request failed"
    assert error.status_code == 503
    assert error.response_data == {"error": "unavailable"}

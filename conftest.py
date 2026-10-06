"""Offline, independent test state; live provider contracts are opt-in."""

import random
import socket

import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Run live provider contracts")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip = pytest.mark.skip(reason="Live provider contracts require --live")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_test_state(tmp_path, monkeypatch, request):
    monkeypatch.chdir(tmp_path)
    # Relative caches/config files must never touch the checkout or real user state.
    monkeypatch.setenv("TENNIS_DATA_ROOT", str(tmp_path))
    state = random.getstate()
    if not request.node.get_closest_marker("live"):
        monkeypatch.delenv("RAPID_API_APPLICATION_KEY", raising=False)
        monkeypatch.delenv("ENABLE_LIVE_API_TESTS", raising=False)
        monkeypatch.setenv("ENABLE_MOCK_MODE", "true")

        def deny_network(*args, **kwargs):
            raise AssertionError("Network access is disabled; mock the transport or use --live")

        monkeypatch.setattr(socket.socket, "connect", deny_network)
        monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
        monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    try:
        yield
    finally:
        random.setstate(state)

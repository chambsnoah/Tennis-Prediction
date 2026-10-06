"""Regression coverage for honest runner statuses and framework reporting."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tennis_api.clients.base_client import APIException, BaseAPIClient
from tennis_api.tests import test_api_integration as integration_module
from tennis_api.tests import test_framework as framework_module
from tennis_api.tests.test_framework import APITestFramework, run_api_tests


ROOT = Path(__file__).resolve().parents[1]
RUNNERS = [
    "scripts/run_full_tests.py",
    "scripts/run_official_tests.py",
    "scripts/final_verification.py",
    "scripts/test_integration_fix.py",
]


@pytest.mark.parametrize("runner", RUNNERS)
@pytest.mark.parametrize(
    ("extra_args", "expected_code", "expected_output"),
    [
        ([], 1, "1 failed"),
        (["-k", "test_skip"], 0, "1 skipped"),
        (["-k", "missing_test"], 5, "2 deselected"),
        (["--not-a-pytest-option"], 4, "unrecognized arguments"),
    ],
)
def test_runners_forward_args_and_exact_pytest_status(
    tmp_path, runner, extra_args, expected_code, expected_output
):
    test_file = tmp_path / "test_synthetic.py"
    test_file.write_text(
        "import pytest\n"
        "def test_failure():\n"
        "    assert False, 'synthetic regression failure'\n"
        "def test_skip():\n"
        "    pytest.skip('synthetic skip alongside failure')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [sys.executable, str(ROOT / runner), str(test_file), "-q", *extra_args],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == expected_code, result.stdout + result.stderr
    assert expected_output in result.stdout + result.stderr


@pytest.fixture
def framework():
    instance = APITestFramework(use_live_apis=False, max_live_requests=0)
    try:
        yield instance
    finally:
        instance.cleanup()


@pytest.mark.parametrize("error", [AssertionError("failure"), TimeoutError("deadline"), APIException("API failure")])
def test_framework_counts_failures_even_above_old_threshold(framework, error):
    for index in range(9):
        framework._run_test(f"Passing test {index}", lambda: None)

    def fail():
        raise error

    framework._run_test("Failing test", fail)
    report = framework._generate_test_report()

    assert report["summary"]["total_tests"] == 10
    assert report["summary"]["passed"] == 9
    assert report["summary"]["failed"] == 1
    assert report["summary"]["skipped"] == 0
    assert report["summary"]["success_rate"] == 90
    assert report["summary"]["all_passed"] is False
    assert report["errors"] == [f"Failing test: {error}"]
    assert not any("ready for production" in item.lower() for item in report["recommendations"])


@pytest.mark.parametrize("raises", [False, True])
def test_framework_counts_elapsed_deadline_as_failure(framework, monkeypatch, raises):
    times = iter([0.0, 31.0])

    def test_function():
        if raises:
            raise AssertionError("Slow failure")

    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(framework_module.time, "monotonic", lambda: next(times))
        framework._run_test("Slow test", test_function, timeout_seconds=30)
    assert framework.test_results["total_tests"] == 1
    assert framework.test_results["failed_tests"] == 1
    assert framework.test_results["passed_tests"] == 0
    assert framework.test_results["skipped_tests"] == 0
    assert len(framework.test_results["errors"]) == 1


def test_framework_counts_category_errors(framework, monkeypatch):
    def fail_category():
        raise RuntimeError("Category failed before its tests")

    monkeypatch.setattr(framework, "_test_configuration", fail_category)
    for name in ["_test_data_models", "_test_cache_system", "_test_rate_limiter", "_test_mock_apis"]:
        monkeypatch.setattr(framework, name, lambda: None)

    report = framework.run_all_tests()
    assert report["summary"]["total_tests"] == 1
    assert report["summary"]["failed"] == 1
    assert report["summary"]["all_passed"] is False
    assert report["errors"] == ["Configuration Tests: Category failed before its tests"]


def test_framework_live_errors_fail_and_consume_attempt_budget(framework, monkeypatch):
    framework.use_live_apis = True
    framework.max_live_requests = 1
    framework.live_client = framework.mock_client

    def fail_rankings(*args, **kwargs):
        raise APIException("Live endpoint failed")

    monkeypatch.setattr(framework.live_client, "get_rankings_sync", fail_rankings)
    framework._test_live_apis()
    report = framework._generate_test_report()

    assert report["summary"]["failed"] == 1
    assert report["summary"]["skipped"] == 1
    assert report["summary"]["passed"] == 0
    assert report["summary"]["live_requests_made"] == 1
    assert report["summary"]["all_passed"] is False
    assert report["errors"] == ["Live Rankings: Live endpoint failed"]


def test_live_pytest_check_skips_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("RAPID_API_APPLICATION_KEY", raising=False)
    with pytest.raises(pytest.skip.Exception, match="RAPID_API_APPLICATION_KEY is required"):
        integration_module.test_with_minimal_api_calls(tmp_path)


def test_live_pytest_check_does_not_swallow_endpoint_errors(tmp_path, monkeypatch, capsys):
    credential = "synthetic-credential-not-a-secret"
    monkeypatch.setenv("RAPID_API_APPLICATION_KEY", credential)
    monkeypatch.setattr(integration_module, "get_api_config", integration_module.TestConfig.get_mock_config)

    with pytest.raises(APIException, match="Mock endpoint"):
        integration_module.test_with_minimal_api_calls(tmp_path)

    output = capsys.readouterr()
    assert credential not in output.out + output.err


def test_live_contract_reaches_both_transports_with_real_config_names(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPID_API_APPLICATION_KEY", "synthetic-credential-not-a-secret")
    calls = []

    def response(client, method, url, params=None):
        calls.append((client.config.name, method, url, params))
        if "rankings" in url:
            return {"players": [{"name": "Synthetic Player", "ranking": 1}]}
        return {"name": "Synthetic Player", "players": [{"name": "Synthetic Player", "id": "1"}]}

    monkeypatch.setattr(BaseAPIClient, "_make_request_sync", response)
    integration_module.test_with_minimal_api_calls(tmp_path)
    assert [call[0] for call in calls] == ["Tennis Rankings API", "Tennis Live API"]
    assert [call[1] for call in calls] == ["GET", "GET"]


@pytest.mark.parametrize("failure_phase", ["sync", "async"])
def test_cleanup_attempts_every_client_after_failure(framework, failure_phase):
    framework.mock_client.close()
    calls = []

    def client(name):
        def close():
            calls.append((name, "sync"))
            if name == "live" and failure_phase == "sync":
                raise RuntimeError("sync close failed")

        async def close_async():
            calls.append((name, "async"))
            if name == "live" and failure_phase == "async":
                raise RuntimeError("async close failed")

        return SimpleNamespace(close=close, close_async=close_async)

    framework.live_client = client("live")
    framework.mock_client = client("mock")
    with pytest.raises(ExceptionGroup, match="cleanup failed") as error:
        framework.cleanup()
    assert len(error.value.exceptions) == 1
    assert calls == [("live", "sync"), ("mock", "sync"), ("live", "async"), ("mock", "async")]
    assert not framework.work_dir.exists()


def test_original_execution_error_survives_cleanup_error(monkeypatch):
    def fail_run():
        raise ValueError("original execution failure")

    def fail_cleanup():
        raise RuntimeError("additional cleanup error")

    instance = SimpleNamespace(run_all_tests=fail_run, cleanup=fail_cleanup)
    monkeypatch.setattr(framework_module, "APITestFramework", lambda *args: instance)
    with pytest.raises(ValueError, match="original execution failure") as error:
        run_api_tests()
    assert "additional cleanup error" in " ".join(error.value.__notes__)


@pytest.mark.asyncio
async def test_cancellation_closes_remaining_clients_and_removes_state(framework):
    framework.mock_client.close()
    started = asyncio.Event()
    calls = []

    async def interrupted_close():
        started.set()
        await asyncio.Event().wait()

    async def remaining_close():
        calls.append("remaining async close")

    framework.live_client = SimpleNamespace(close=lambda: None, close_async=interrupted_close)
    framework.mock_client = SimpleNamespace(close=lambda: None, close_async=remaining_close)
    task = framework.cleanup()
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["remaining async close"]
    assert not framework.work_dir.exists()


def test_framework_state_is_temporary_and_cleanup_is_idempotent(framework):
    original_cwd = Path.cwd()
    work_dir = framework.work_dir
    assert work_dir.is_dir()
    assert framework.mock_client.cache_manager.cache_dir.is_relative_to(work_dir)
    assert framework.mock_client.rate_limiter.state_file.is_relative_to(work_dir)
    framework._test_cache_manager()
    framework._test_cache_ttl()
    framework._test_rate_limiter_basic()
    for _ in range(5):
        assert framework.mock_client.rate_limiter.acquire("rapidapi_tennis_live") is True
    assert list(work_dir.rglob("*.json"))
    assert not (original_cwd / "cache").exists()

    framework.cleanup()
    framework.cleanup()
    assert not work_dir.exists()
    assert Path.cwd() == original_cwd


def test_run_api_tests_does_not_save_report_and_cleans_up(monkeypatch):
    work_dirs = []
    original_run = APITestFramework.run_all_tests

    def run_and_capture(instance):
        work_dirs.append(instance.work_dir)
        return original_run(instance)

    def unexpected_report_save(*args, **kwargs):
        pytest.fail("Reports must only be saved when explicitly requested")

    monkeypatch.setattr(APITestFramework, "run_all_tests", run_and_capture)
    monkeypatch.setattr(APITestFramework, "save_report", unexpected_report_save)
    report = run_api_tests(use_live_apis=False, max_live_requests=0)

    assert report["summary"]["all_passed"] is True
    assert work_dirs and all(not path.exists() for path in work_dirs)
    assert not Path("tennis_api_test_report.json").exists()


def test_run_api_tests_cleans_up_when_execution_raises(monkeypatch):
    work_dirs = []

    def fail_run(instance):
        work_dirs.append(instance.work_dir)
        raise RuntimeError("Unexpected framework failure")

    monkeypatch.setattr(APITestFramework, "run_all_tests", fail_run)
    with pytest.raises(RuntimeError, match="Unexpected framework failure"):
        run_api_tests(use_live_apis=False, max_live_requests=0)

    assert work_dirs and all(not path.exists() for path in work_dirs)

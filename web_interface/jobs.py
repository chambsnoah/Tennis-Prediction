"""Bounded local jobs: each runs a registered typed function in a fresh worker process.

This is not command-line orchestration: no argv, shell or stdout parsing. The
job is a registered ``module:function`` called with a typed payload, and the
typed result comes back over a private pipe. A worker process is used so a job
can be stopped at its deadline and given its own resource limits:

* concurrency: at most ``max_concurrent`` jobs; further requests are refused
  with ``busy`` (429) instead of queueing without bound;
* time: a wall-clock deadline after which the worker is terminated
  (``job_timeout``), plus an ``RLIMIT_CPU`` backstop;
* memory: ``RLIMIT_AS`` where the platform enforces it (Linux; macOS refuses to
  lower it, which ``JobRunner.enforced`` reports);
* size: payloads and results are bounded; numeric libraries run single-threaded.

Workers always use the ``spawn`` start method, so they never inherit server
state. A failed job returns only a safe reason code; unexpected exceptions are
logged by type name only, never with their message or traceback.
"""

from __future__ import annotations

import logging
import math
import multiprocessing
import os
import pickle
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from importlib import import_module
from multiprocessing.connection import Connection
from typing import Any

from web_interface.errors import ServiceError, safe_code

LOG = logging.getLogger("web_interface.jobs")
_THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")


@dataclass(frozen=True)
class JobLimits:
    max_concurrent: int = 2
    timeout_seconds: int = 120
    memory_bytes: int = 4 * 1024 ** 3
    max_payload_bytes: int = 16 * 1024 ** 2
    max_result_bytes: int = 8 * 1024 ** 2

    def __post_init__(self) -> None:
        bounds = {"max_concurrent": (1, 16), "timeout_seconds": (1, 3600),
                  "memory_bytes": (256 * 1024 ** 2, 64 * 1024 ** 3),
                  "max_payload_bytes": (1024, 256 * 1024 ** 2),
                  "max_result_bytes": (1024, 256 * 1024 ** 2)}
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid job limit: " + name)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _set_limit(name: str, value: int) -> bool:
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return False
    kind = getattr(resource, name, None)
    if kind is None:
        return False
    try:
        _, hard = resource.getrlimit(kind)
        if hard != resource.RLIM_INFINITY:
            value = min(value, hard)
        resource.setrlimit(kind, (value, value))
        return resource.getrlimit(kind)[0] == value
    except (ValueError, OSError):
        return False


def apply_limits(limits: JobLimits) -> dict[str, bool]:
    """Apply worker limits in the current process; returns which ones took effect."""
    for name in _THREAD_ENV:
        os.environ[name] = "1"
    return {
        "cpu": _set_limit("RLIMIT_CPU", math.ceil(limits.timeout_seconds) + 2),
        "memory": _set_limit("RLIMIT_AS", limits.memory_bytes),
    }


def _worker(target: str, payload: bytes, conn: Connection, limits: JobLimits) -> None:
    try:
        try:
            apply_limits(limits)
            module, _, name = target.partition(":")
            function = getattr(import_module(module), name)
            message = pickle.dumps(("ok", function(pickle.loads(payload))),
                                   protocol=pickle.HIGHEST_PROTOCOL)
            if len(message) > limits.max_result_bytes:
                message = pickle.dumps(("error", "result_too_large", 507))
        except ServiceError as error:
            message = pickle.dumps(("error", error.code, error.status))
        except MemoryError:
            message = pickle.dumps(("error", "job_resource_limit", 503))
        except BaseException as error:  # noqa: BLE001 - redact everything else
            LOG.error("Job %s failed with %s", target, type(error).__name__)
            message = pickle.dumps(("error", "internal_error", 500))
        conn.send_bytes(message)
    finally:
        conn.close()


def _probe(limits: JobLimits) -> dict[str, bool]:
    return apply_limits(limits)


class JobRunner:
    """Run registered job targets with bounded concurrency, time, memory and size."""

    def __init__(self, limits: JobLimits, targets: Iterable[str]) -> None:
        self.limits = limits
        self.targets = frozenset(targets)
        if any(t.count(":") != 1 for t in self.targets):
            raise ValueError("Job targets are 'module:function'")
        self._slots = threading.BoundedSemaphore(limits.max_concurrent)
        self._context = multiprocessing.get_context("spawn")
        self._enforced: dict[str, bool] | None = None

    @property
    def enforced(self) -> dict[str, bool]:
        """Which OS limits a worker on this platform actually gets."""
        if self._enforced is None:
            with self._context.Pool(1) as pool:
                self._enforced = dict(pool.apply(_probe, (self.limits,)))
        return dict(self._enforced)

    def run(self, target: str, payload: object) -> Any:
        if target not in self.targets:
            raise ValueError("Unregistered job target")
        data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        if len(data) > self.limits.max_payload_bytes:
            raise ServiceError("payload_too_large", 413)
        if not self._slots.acquire(blocking=False):
            raise ServiceError("busy", 429)
        process = None
        try:
            receiver, sender = self._context.Pipe(duplex=False)
            try:
                process = self._context.Process(
                    target=_worker, args=(target, data, sender, self.limits), daemon=True)
                process.start()
                sender.close()
                if not receiver.poll(self.limits.timeout_seconds):
                    raise ServiceError("job_timeout", 504)
                message = receiver.recv_bytes(self.limits.max_result_bytes + 4096)
            except EOFError:
                # The worker died without answering (for example a CPU or memory limit).
                raise ServiceError("job_resource_limit", 503) from None
            except OSError:
                raise ServiceError("result_too_large", 507) from None
            finally:
                sender.close()
                receiver.close()
        finally:
            if process is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                    if process.is_alive():
                        process.kill()
                process.join()
            self._slots.release()
        status, *rest = pickle.loads(message)
        if status == "ok":
            return rest[0]
        code, http_status = rest
        raise ServiceError(safe_code(code, "internal_error"), int(http_status))

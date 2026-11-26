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


def probe_limits(limits: JobLimits) -> dict[str, bool]:
    """Job target: report which limits a worker on this platform actually gets."""
    return apply_limits(limits)


PROBE = "web_interface.jobs:probe_limits"


def _worker(target: str, inbox: Connection, conn: Connection, limits: JobLimits) -> None:
    # The payload and both pipes come only from the parent JobRunner that spawned
    # this process; none is reachable by a request, so unpickling is trusted.
    try:
        try:
            apply_limits(limits)
            payload = inbox.recv_bytes(limits.max_payload_bytes)
            inbox.close()
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


class JobRunner:
    """Run registered job targets with bounded concurrency, time, memory and size.

    Payloads are pickled by this runner and results by its own workers; both
    travel over a private pipe created here, so pickle is used only between
    trusted processes, never on request bytes.
    """

    def __init__(self, limits: JobLimits, targets: Iterable[str]) -> None:
        self.limits = limits
        self.targets = frozenset(targets) | {PROBE}
        if any(t.count(":") != 1 for t in self.targets):
            raise ValueError("Job targets are 'module:function'")
        self._slots = threading.BoundedSemaphore(limits.max_concurrent)
        self._context = multiprocessing.get_context("spawn")
        self._probe_lock = threading.Lock()
        self._enforced: dict[str, bool] | None = None

    @property
    def enforced(self) -> dict[str, bool | None]:
        """Which OS limits a worker gets; ``None`` while no job slot is free to probe.

        The probe is an ordinary job, so it uses the same slots and limits, and
        concurrent callers share one probe.
        """
        with self._probe_lock:
            if self._enforced is None:
                try:
                    self._enforced = dict(self.run(PROBE, self.limits))
                except ServiceError:
                    return {"cpu": None, "memory": None}
            return dict(self._enforced)

    def run(self, target: str, payload: object) -> Any:
        if target not in self.targets:
            raise ValueError("Unregistered job target")
        if not self._slots.acquire(blocking=False):
            raise ServiceError("busy", 429)
        try:
            # Serialize only once admitted, so a refused request builds no payload buffer.
            data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
            if len(data) > self.limits.max_payload_bytes:
                raise ServiceError("payload_too_large", 413)
            message = self._execute(target, data)
        finally:
            self._slots.release()
        status, *rest = pickle.loads(message)
        if status == "ok":
            return rest[0]
        code, http_status = rest
        raise ServiceError(safe_code(code, "internal_error"), int(http_status))

    def _execute(self, target: str, data: bytes) -> bytes:
        receiver, sender = self._context.Pipe(duplex=False)
        # The payload travels on its own pipe after start(), so start() only writes
        # a small bootstrap and the deadline below also covers the payload transfer.
        inbox, outbox = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=_worker, args=(target, inbox, sender, self.limits), daemon=True)
        expired = threading.Event()

        def expire() -> None:
            # One deadline covers the whole job, including a partly sent result:
            # killing the worker closes its end, so a blocked read ends with EOF.
            expired.set()
            process.kill()

        timer = threading.Timer(self.limits.timeout_seconds, expire)
        started = False
        try:
            try:
                process.start()
            except OSError:
                raise ServiceError("job_start_failed", 503) from None
            started = True
            timer.start()
            sender.close()
            inbox.close()
            try:
                outbox.send_bytes(data)
            except OSError:
                # The worker died (or was killed at the deadline) before reading it.
                if expired.is_set():
                    raise ServiceError("job_timeout", 504) from None
                raise ServiceError("job_resource_limit", 503) from None
            finally:
                outbox.close()
            try:
                if not receiver.poll(self.limits.timeout_seconds):
                    raise ServiceError("job_timeout", 504)
                message = receiver.recv_bytes(self.limits.max_result_bytes + 4096)
            except EOFError:
                if expired.is_set():
                    raise ServiceError("job_timeout", 504) from None
                # The worker died without answering (for example a CPU or memory limit).
                raise ServiceError("job_resource_limit", 503) from None
            except OSError:
                # Killed at the deadline mid-frame, or a frame longer than the result limit.
                if expired.is_set():
                    raise ServiceError("job_timeout", 504) from None
                raise ServiceError("result_too_large", 507) from None
            # A complete result that arrived is kept even if the deadline fired meanwhile.
            return message
        finally:
            timer.cancel()
            for end in (sender, receiver, inbox, outbox):
                end.close()
            if started:
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                    if process.is_alive():
                        process.kill()
                process.join()

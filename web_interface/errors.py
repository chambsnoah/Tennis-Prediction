"""Safe service errors: a fixed reason code and HTTP status, never source text."""

from __future__ import annotations

import re

_CODE = re.compile(r"[A-Za-z0-9_:]{1,80}")


class ServiceError(Exception):
    """An expected refusal with a safe, stable reason code.

    The code is the whole message. Callers never attach file paths, player or
    participant labels, environment values or upstream exception text.
    """

    def __init__(self, code: str, status: int = 422) -> None:
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise ValueError("Service error codes are short identifiers")
        if not 400 <= status <= 599:
            raise ValueError("Service errors use an HTTP error status")
        super().__init__(code)
        self.code = code
        self.status = status


def safe_code(value: object, default: str) -> str:
    """Return ``value`` when it is already a safe identifier, else ``default``."""
    return value if isinstance(value, str) and _CODE.fullmatch(value) else default

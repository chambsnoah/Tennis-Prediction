"""Deterministic configuration for the single-user local app.

Limits are fixed in code; the environment only selects local directories, the
port and an optional manifest digest. The host is always loopback and the
Werkzeug debugger is never enabled. Public or multi-user hosting is out of scope.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from tennis_pool.workbooks import WorkbookLimits
from web_interface.jobs import JobLimits

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, kw_only=True)
class LocalAppConfig:
    HOST: ClassVar[str] = "127.0.0.1"

    data_root: Path = REPOSITORY_ROOT
    pool_root: Path | None = None
    port: int = 5000
    jobs: JobLimits = field(default_factory=JobLimits)
    workbook_limits: WorkbookLimits = field(default_factory=WorkbookLimits)
    max_json_bytes: int = 1024 * 1024
    max_match_simulations: int = 20_000
    max_tournament_simulations: int = 20_000
    max_withdrawal_patterns: int = 64
    max_artifact_bytes: int = 256 * 1024 * 1024
    default_seed: int = 2026
    provider_loaders: tuple[tuple[str, str], ...] = ()
    manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        for root in (self.data_root, self.pool_root):
            if root is not None and (not isinstance(root, Path) or not root.is_absolute()):
                raise ValueError("Configured roots must be absolute paths")
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ValueError("Port must be an unprivileged TCP port")
        for name in ("max_json_bytes", "max_match_simulations", "max_tournament_simulations",
                     "max_withdrawal_patterns", "max_artifact_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError("Invalid limit: " + name)
        if type(self.default_seed) is not int or not 0 <= self.default_seed < 2 ** 63:
            raise ValueError("Invalid default seed")
        if self.manifest_sha256 is not None and not _DIGEST.fullmatch(self.manifest_sha256):
            raise ValueError("Manifest digest must be a lowercase SHA-256")

    @property
    def max_upload_bytes(self) -> int:
        return self.workbook_limits.file_bytes

    @classmethod
    def from_env(cls, environ: Mapping[str, str], **overrides: object) -> LocalAppConfig:
        """Read only TENNIS_DATA_ROOT, TENNIS_POOL_ROOT, TENNIS_PORT and the manifest pin."""
        values: dict[str, object] = {}
        if environ.get("TENNIS_DATA_ROOT"):
            values["data_root"] = Path(environ["TENNIS_DATA_ROOT"]).expanduser().resolve()
        if environ.get("TENNIS_POOL_ROOT"):
            values["pool_root"] = Path(environ["TENNIS_POOL_ROOT"]).expanduser().resolve()
        if environ.get("TENNIS_PORT"):
            if not environ["TENNIS_PORT"].isdigit():
                raise ValueError("TENNIS_PORT must be a number")
            values["port"] = int(environ["TENNIS_PORT"])
        if environ.get("TENNIS_ARTIFACT_MANIFEST_SHA256"):
            values["manifest_sha256"] = environ["TENNIS_ARTIFACT_MANIFEST_SHA256"]
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)  # type: ignore[arg-type]

    def limits(self) -> dict[str, object]:
        """Effective limits for the status route; no paths or environment values."""
        return {
            "host": self.HOST,
            "port": self.port,
            "jobs": self.jobs.to_dict(),
            "max_upload_bytes": self.max_upload_bytes,
            "max_json_bytes": self.max_json_bytes,
            "max_match_simulations": self.max_match_simulations,
            "max_tournament_simulations": self.max_tournament_simulations,
            "max_withdrawal_patterns": self.max_withdrawal_patterns,
            "default_seed": self.default_seed,
        }

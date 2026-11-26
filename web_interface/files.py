"""Bounded reads below a configured root, without following request-controlled paths.

Every path component must be a plain file name, so ``..``, separators and
absolute paths never reach the filesystem. Components are opened one at a time
relative to the previous directory with ``O_NOFOLLOW``, so a symlink anywhere
below the root is refused instead of followed. Trusted inputs (registries,
events, artifacts) must also be owned by the running user and not writable by
group or others, at every level from the root down.
"""

from __future__ import annotations

import errno
import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path

from web_interface.errors import ServiceError

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_READ = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_UNSAFE = {errno.ELOOP, errno.ENOTDIR, errno.EMLINK}


def _check_trusted(info: os.stat_result) -> None:
    getuid = getattr(os, "getuid", None)
    if (getuid is not None and info.st_uid != getuid()) or info.st_mode & 0o022:
        raise ServiceError("untrusted_file_permissions", 403)


def read_bounded(
    root: Path, parts: Sequence[str], limit: int, *, trusted: bool,
    missing: str, too_large: str,
) -> bytes:
    """Read at most ``limit`` bytes of ``root/parts...`` or raise a ServiceError."""
    if not parts or any(not isinstance(p, str) or not NAME.fullmatch(p) for p in parts):
        raise ServiceError("unsafe_path", 400)
    fds: list[int] = []
    try:
        try:
            fds.append(os.open(root, _READ | os.O_DIRECTORY))
            if trusted:
                _check_trusted(os.fstat(fds[-1]))
            for part in parts[:-1]:
                fds.append(os.open(part, _READ | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1]))
                if trusted:
                    _check_trusted(os.fstat(fds[-1]))
            # O_NONBLOCK keeps a planted FIFO from blocking the open itself.
            fds.append(os.open(parts[-1], _READ | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fds[-1]))
        except OSError as error:
            code, status = (("unsafe_path", 400) if error.errno in _UNSAFE
                            else (missing, 404))
            raise ServiceError(code, status) from None
        info = os.fstat(fds[-1])
        if not stat.S_ISREG(info.st_mode):
            raise ServiceError("unsafe_path", 400)
        if trusted:
            _check_trusted(info)
        if info.st_size > limit:
            raise ServiceError(too_large, 413)
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(fds[-1], min(remaining, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise ServiceError(too_large, 413)
        return data
    finally:
        for fd in reversed(fds):
            os.close(fd)


def list_directories(root: Path, parts: Sequence[str] = ()) -> list[str]:
    """Names of plain (non-symlink) subdirectories, or an empty list."""
    if any(not NAME.fullmatch(p) for p in parts):
        return []
    try:
        directory = root.joinpath(*parts)
        if any(root.joinpath(*parts[:i + 1]).is_symlink() for i in range(len(parts))):
            return []
        with os.scandir(directory) as entries:
            return sorted(e.name for e in entries
                          if NAME.fullmatch(e.name) and e.is_dir(follow_symlinks=False))
    except OSError:
        return []


def has_file(root: Path, parts: Sequence[str]) -> bool:
    """Whether ``root/parts`` is a regular file reached without symlinks."""
    if not parts or any(not NAME.fullmatch(p) for p in parts):
        return False
    path = root
    try:
        for part in parts:
            path = path / part
            if path.is_symlink():
                return False
        return path.is_file()
    except OSError:
        return False

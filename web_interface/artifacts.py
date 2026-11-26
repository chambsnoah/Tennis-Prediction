"""Trusted prediction artifacts: pinned SHA-256 digests in an operator-owned manifest.

The trust root is a local directory the operator owns (not group/world
writable) holding ``manifest.json`` and the artifact files beside it. A request
names an artifact; it never supplies a path. The bytes are read once, bounded,
hashed and compared with the pinned digest, and loaders deserialize from those
verified bytes only, so the file cannot be swapped between check and use.
Optionally the manifest's own digest is pinned in the app configuration.

No calibrated provider exists yet, so no loader is registered by default and
prediction routes refuse with ``no_provider_loader``. Loaders are configured in
code (``LocalAppConfig.provider_loaders``), never by a request or environment
variable. Pickle-based legacy artifacts are not loadable through this boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from tennis_api.models.canonical import MatchProbabilityProvider
from web_interface.errors import ServiceError
from web_interface.files import NAME, read_bounded

MANIFEST = "manifest.json"
MANIFEST_BYTES = 256 * 1024
_ARTIFACT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_KIND = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LOADER = re.compile(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    file: str
    sha256: str
    kind: str
    size: int


@dataclass(frozen=True)
class VerifiedArtifact:
    """Artifact bytes whose digest matched the manifest when read."""

    name: str
    kind: str
    sha256: str
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not hmac.compare_digest(sha256(self.data), self.sha256):
            raise ServiceError("artifact_digest_mismatch", 409)


def _spec(entry: object, max_bytes: int) -> ArtifactSpec:
    keys = {"name", "file", "sha256", "kind", "bytes"}
    if not isinstance(entry, dict) or set(entry) != keys:
        raise ServiceError("invalid_artifact_manifest", 503)
    name, file, digest, kind, size = (entry[k] for k in ("name", "file", "sha256", "kind", "bytes"))
    if not (isinstance(name, str) and _ARTIFACT.fullmatch(name)
            and isinstance(file, str) and NAME.fullmatch(file) and file != MANIFEST
            and isinstance(digest, str) and _DIGEST.fullmatch(digest)
            and isinstance(kind, str) and _KIND.fullmatch(kind)
            and type(size) is int and 0 < size <= max_bytes):
        raise ServiceError("invalid_artifact_manifest", 503)
    return ArtifactSpec(name=name, file=file, sha256=digest, kind=kind, size=size)


class ArtifactStore:
    """Named, digest-pinned artifacts under one trusted directory."""

    def __init__(self, directory: Path | None, specs: Mapping[str, ArtifactSpec],
                 loaders: Mapping[str, str]) -> None:
        for kind, loader in loaders.items():
            if not _KIND.fullmatch(kind) or not _LOADER.fullmatch(loader):
                raise ValueError("Provider loaders map a kind to 'module:function'")
        self.directory = directory
        self._specs = dict(specs)
        self._loaders = dict(loaders)

    @classmethod
    def empty(cls, loaders: Mapping[str, str] | None = None) -> ArtifactStore:
        return cls(None, {}, loaders or {})

    @classmethod
    def from_directory(cls, directory: Path, *, loaders: Mapping[str, str],
                       manifest_sha256: str | None, max_bytes: int) -> ArtifactStore:
        data = read_bounded(directory, [MANIFEST], MANIFEST_BYTES, trusted=True,
                            missing="artifact_manifest_missing",
                            too_large="invalid_artifact_manifest")
        if manifest_sha256 is not None and not hmac.compare_digest(sha256(data), manifest_sha256):
            raise ServiceError("artifact_manifest_digest_mismatch", 503)
        try:
            manifest = json.loads(data)
        except ValueError:
            raise ServiceError("invalid_artifact_manifest", 503) from None
        if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "artifacts"}
                or manifest["schema_version"] != 1 or not isinstance(manifest["artifacts"], list)):
            raise ServiceError("invalid_artifact_manifest", 503)
        specs: dict[str, ArtifactSpec] = {}
        for entry in manifest["artifacts"]:
            spec = _spec(entry, max_bytes)
            if spec.name in specs:
                raise ServiceError("invalid_artifact_manifest", 503)
            specs[spec.name] = spec
        return cls(directory, specs, loaders)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def load(self, name: object) -> tuple[VerifiedArtifact, str]:
        """Verified bytes and the configured loader for a named artifact."""
        spec = self._specs.get(name) if isinstance(name, str) else None
        if spec is None or self.directory is None:
            raise ServiceError("unknown_artifact", 404)
        loader = self._loaders.get(spec.kind)
        if loader is None:
            raise ServiceError("no_provider_loader", 503)
        data = read_bounded(self.directory, [spec.file], spec.size, trusted=True,
                            missing="artifact_missing", too_large="artifact_digest_mismatch")
        if len(data) != spec.size:
            raise ServiceError("artifact_digest_mismatch", 409)
        return VerifiedArtifact(name=spec.name, kind=spec.kind, sha256=spec.sha256, data=data), loader


def load_provider(artifact: VerifiedArtifact, loader: str) -> MatchProbabilityProvider:
    """Deserialize a provider from already verified bytes (run inside a job)."""
    if not _LOADER.fullmatch(loader):
        raise ServiceError("no_provider_loader", 503)
    # Re-check in the worker: the bytes crossed a process boundary.
    VerifiedArtifact(name=artifact.name, kind=artifact.kind, sha256=artifact.sha256,
                     data=artifact.data)
    module, _, attribute = loader.partition(":")
    provider: object = getattr(importlib.import_module(module), attribute)(artifact)
    if not callable(getattr(provider, "predict", None)):
        raise ServiceError("invalid_provider", 500)
    return cast(MatchProbabilityProvider, provider)

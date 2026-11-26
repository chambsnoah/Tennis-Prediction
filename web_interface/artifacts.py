"""Trusted prediction artifacts: pinned SHA-256 digests in an operator-owned manifest.

The trust root is the operator's pool directory (owned by the running user,
not group/world writable) with a real ``artifacts/`` subdirectory holding
``manifest.json`` and the artifact files. Every open below the pool directory
refuses symlinks, so the artifacts cannot resolve elsewhere. A request names an
artifact; it never supplies a path. Optionally the manifest's own digest is
pinned in the app configuration.

The server only resolves a name to an ``ArtifactRef``. The bounded job worker
reads the bytes once (bounded by the pinned size), hashes them, compares the
pinned digest, and the loader deserializes those same verified bytes, so the
file cannot be swapped between check and use and no artifact buffer is held by
the server or by a request that is refused as ``busy``.

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

DIRECTORY = "artifacts"
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
class ArtifactRef:
    """What a job needs to read and verify one artifact itself."""

    root: str
    spec: ArtifactSpec
    loader: str

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def sha256(self) -> str:
        return self.spec.sha256


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
    """Named, digest-pinned artifacts in ``<pool root>/artifacts``."""

    def __init__(self, root: Path | None, specs: Mapping[str, ArtifactSpec],
                 loaders: Mapping[str, str]) -> None:
        for kind, loader in loaders.items():
            if not _KIND.fullmatch(kind) or not _LOADER.fullmatch(loader):
                raise ValueError("Provider loaders map a kind to 'module:function'")
        self.root = root
        self._specs = dict(specs)
        self._loaders = dict(loaders)

    @classmethod
    def empty(cls, loaders: Mapping[str, str] | None = None) -> ArtifactStore:
        return cls(None, {}, loaders or {})

    @classmethod
    def from_pool_root(cls, root: Path, *, loaders: Mapping[str, str],
                       manifest_sha256: str | None, max_bytes: int) -> ArtifactStore:
        data = read_bounded(root, [DIRECTORY, MANIFEST], MANIFEST_BYTES, trusted=True,
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
        return cls(root, specs, loaders)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def resolve(self, name: object) -> ArtifactRef:
        """A reference to a named artifact with a configured loader; reads nothing."""
        spec = self._specs.get(name) if isinstance(name, str) else None
        if spec is None or self.root is None:
            raise ServiceError("unknown_artifact", 404)
        loader = self._loaders.get(spec.kind)
        if loader is None:
            raise ServiceError("no_provider_loader", 503)
        return ArtifactRef(root=str(self.root), spec=spec, loader=loader)

    def load(self, name: object) -> VerifiedArtifact:
        return read_artifact(self.resolve(name))


def read_artifact(ref: ArtifactRef) -> VerifiedArtifact:
    """Read once, bounded by the pinned size, and verify the pinned digest."""
    spec = ref.spec
    data = read_bounded(Path(ref.root), [DIRECTORY, spec.file], spec.size, trusted=True,
                        missing="artifact_missing", too_large="artifact_digest_mismatch")
    if len(data) != spec.size:
        raise ServiceError("artifact_digest_mismatch", 409)
    return VerifiedArtifact(name=spec.name, kind=spec.kind, sha256=spec.sha256, data=data)


def load_provider(ref: ArtifactRef) -> MatchProbabilityProvider:
    """Verify and deserialize a provider (run inside a bounded job worker)."""
    if not _LOADER.fullmatch(ref.loader):
        raise ServiceError("no_provider_loader", 503)
    artifact = read_artifact(ref)
    module, _, attribute = ref.loader.partition(":")
    try:
        factory = getattr(importlib.import_module(module), attribute)
    except (ImportError, AttributeError):
        # A mistyped loader in code configuration, not a request problem.
        raise ServiceError("no_provider_loader", 503) from None
    provider: object = factory(artifact)
    if not callable(getattr(provider, "predict", None)):
        raise ServiceError("invalid_provider", 500)
    return cast(MatchProbabilityProvider, provider)

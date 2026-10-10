"""Reviewed identities at the source-adapter -> canonical-record boundary.

Names are never generated IDs. Adapters must resolve before emitting canonical
records; unresolved input raises instead of silently entering training. Registry
revisions are immutable snapshots, not approval to fetch or publish source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import unicodedata

from .canonical import Contract, Player, PlayerId, Provenance, Tour


def _normalized(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.casefold())
    return " ".join(
        "".join(
            char if char.isalnum() else " "
            for char in text
            if not unicodedata.combining(char)
        ).split()
    )


class IdentityResolutionError(ValueError):
    """Adapters quarantine the source row with this reason and candidate IDs."""

    def __init__(self, reason: str, candidates: tuple[PlayerId, ...] = ()) -> None:
        self.reason = reason
        self.candidates = candidates
        # Do not expose source names or participant data in exception messages.
        super().__init__(f"Identity requires review: {reason}")


@dataclass(frozen=True, kw_only=True)
class _ReviewedIdentity(Contract):
    source: str
    player_id: PlayerId
    tour: Tour
    reviewed_by: str
    reviewed_at: datetime
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.source != self.source.strip():
            raise ValueError("Source must not contain surrounding whitespace")
        if self.source != self.provenance.source:
            raise ValueError("Review evidence must identify the mapping source")
        if self.reviewed_at < self.provenance.available_at:
            raise ValueError("Review cannot precede evidence availability")


@dataclass(frozen=True, kw_only=True)
class ProviderMapping(_ReviewedIdentity):
    external_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.external_id != self.external_id.strip():
            raise ValueError("Provider IDs must not contain surrounding whitespace")


@dataclass(frozen=True, kw_only=True)
class ReviewedAlias(_ReviewedIdentity):
    name: str


@dataclass(frozen=True, kw_only=True)
class IdentityRegistry(Contract):
    revision: str
    players: tuple[Player, ...]
    provider_mappings: tuple[ProviderMapping, ...] = ()
    aliases: tuple[ReviewedAlias, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        players = {item.player_id: item for item in self.players}
        if len(players) != len(self.players):
            raise ValueError("Duplicate player IDs")
        for item in (*self.provider_mappings, *self.aliases):
            if item.player_id not in players:
                raise ValueError("Mapping references an unknown player")
            if item.tour != players[item.player_id].tour:
                raise ValueError("Mapping tour differs from canonical player")
        keys = [
            (item.source, item.tour, item.external_id)
            for item in self.provider_mappings
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate or colliding provider IDs")
        alias_keys = [
            (item.source, item.tour, item.name, item.player_id) for item in self.aliases
        ]
        if len(set(alias_keys)) != len(alias_keys):
            raise ValueError("Duplicate reviewed aliases")
        object.__setattr__(
            self, "players", tuple(sorted(self.players, key=lambda p: p.player_id))
        )
        object.__setattr__(
            self,
            "provider_mappings",
            tuple(
                sorted(
                    self.provider_mappings,
                    key=lambda p: (p.source, p.tour.value, p.external_id),
                )
            ),
        )
        object.__setattr__(
            self,
            "aliases",
            tuple(
                sorted(
                    self.aliases,
                    key=lambda a: (a.source, a.tour.value, a.name, a.player_id),
                )
            ),
        )

    @property
    def digest(self) -> str:
        """Content identity including revision, review evidence and schema versions."""
        data = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def candidates(self, *, name: str, tour: Tour) -> tuple[PlayerId, ...]:
        """Accent/case/surname matches are hints, never automatic resolutions."""
        if not isinstance(name, str) or not isinstance(tour, Tour):
            raise IdentityResolutionError("invalid_query")
        key = _normalized(name)
        if not key:
            return ()
        labels = [
            (item.player_id, item.tour, item.display_name) for item in self.players
        ]
        labels.extend((item.player_id, item.tour, item.name) for item in self.aliases)
        return tuple(
            sorted(
                {
                    player_id
                    for player_id, label_tour, label in labels
                    if label_tour == tour
                    and (
                        _normalized(label) == key
                        or _normalized(label).split()[-1:] == [key]
                    )
                }
            )
        )

    def resolve(
        self,
        *,
        source: str,
        tour: Tour,
        external_id: str | None = None,
        name: str | None = None,
    ) -> PlayerId:
        """Use an exact reviewed key; never fall back from an unknown provider ID.

        A provider ID is authoritative unless the supplied name has a conflicting
        reviewed alias in that same source/tour. Unreviewed labels cannot establish
        or override an identity. Persist this registry's revision/digest with exports.
        """
        if (
            not isinstance(source, str)
            or not source.strip()
            or source != source.strip()
            or not isinstance(tour, Tour)
            or (external_id is None and name is None)
            or any(
                value is not None and (not isinstance(value, str) or not value.strip())
                for value in (external_id, name)
            )
        ):
            raise IdentityResolutionError("invalid_query")
        aliases = {
            item.player_id
            for item in self.aliases
            if (item.source, item.tour, item.name) == (source, tour, name)
        }
        if external_id is not None:
            matches = {
                item.player_id
                for item in self.provider_mappings
                if (item.source, item.tour, item.external_id)
                == (source, tour, external_id)
            }
        else:
            matches = aliases
        if len(matches) == 1:
            if external_id is not None and aliases and aliases != matches:
                raise IdentityResolutionError(
                    "conflicting_identity", tuple(sorted(aliases | matches))
                )
            return next(iter(matches))
        candidates = self.candidates(name=name, tour=tour) if name is not None else ()
        if external_id is not None:
            raise IdentityResolutionError("unknown_provider_id", candidates)
        if matches:
            candidates = tuple(sorted(matches))
        reason = "ambiguous_name" if len(candidates) > 1 else "unreviewed_name"
        raise IdentityResolutionError(reason, candidates)

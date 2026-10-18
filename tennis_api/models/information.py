"""Local, cited information records. Reporting only: never apply model deltas."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from fractions import Fraction
import hashlib
import json
import re
from typing import Any, Mapping

from .canonical import Contract, EventId, PlayerId, Provenance, Tour
from .identity import IdentityRegistry


def _utc_provenance(value: Provenance) -> Provenance:
    observed = value.observed_at
    return replace(
        value,
        observed_at=observed.astimezone(timezone.utc)
        if isinstance(observed, datetime)
        else observed,
        available_at=value.available_at.astimezone(timezone.utc),
        ingested_at=value.ingested_at.astimezone(timezone.utc),
    )


class InformationKind(str, Enum):
    MARKET_ADJUSTMENT = "market_adjustment"
    ANALYST_OPINION = "analyst_opinion"
    VERIFIED_WITHDRAWAL = "verified_withdrawal"
    INJURY_RISK = "injury_risk"


class AdjustmentUnit(str, Enum):
    """Signed changes to match-win probability, not multipliers or predictions."""

    PROBABILITY_POINTS = "probability_points"
    PERCENTAGE_POINTS = "percentage_points"


@dataclass(frozen=True, kw_only=True)
class MarketAdjustment(Contract):
    value: float
    unit: AdjustmentUnit
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        limit = 1 if self.unit == AdjustmentUnit.PROBABILITY_POINTS else 100
        if not -limit <= self.value <= limit:
            raise ValueError("Adjustment outside declared probability units")
        object.__setattr__(self, "value", float(self.value) or 0.0)
        object.__setattr__(self, "provenance", _utc_provenance(self.provenance))


@dataclass(frozen=True, kw_only=True)
class AnalystOpinion(Contract):
    text: str


@dataclass(frozen=True, kw_only=True)
class VerifiedWithdrawal(Contract):
    withdrawn: bool


@dataclass(frozen=True, kw_only=True)
class InjuryRisk(Contract):
    probability: float

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.probability <= 1:
            raise ValueError("Injury probability must lie in [0, 1]")
        object.__setattr__(self, "probability", float(self.probability) or 0.0)


def _digest_lineage(digest: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Lineage requires a SHA-256 digest")


@dataclass(frozen=True, kw_only=True)
class Observation(Contract):
    player_id: PlayerId
    event_id: EventId
    tour: Tour
    record_version: int
    provenance: Provenance
    citation: str
    certainty: float
    effective_at: datetime
    expires_at: datetime
    payload: MarketAdjustment | AnalystOpinion | VerifiedWithdrawal | InjuryRisk
    registry_revision: str
    registry_digest: str
    historical_snapshot: Provenance | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "provenance", _utc_provenance(self.provenance))
        object.__setattr__(
            self, "effective_at", self.effective_at.astimezone(timezone.utc)
        )
        object.__setattr__(self, "expires_at", self.expires_at.astimezone(timezone.utc))
        if self.historical_snapshot is not None:
            object.__setattr__(
                self, "historical_snapshot", _utc_provenance(self.historical_snapshot)
            )
        _digest_lineage(self.registry_digest)
        if (
            type(self.provenance.observed_at) is not datetime
            or self.provenance.source_record_id is None
            or self.record_version < 1
            or not 0 <= self.certainty <= 1
            or self.effective_at >= self.expires_at
            or self.provenance.observed_at >= self.expires_at
        ):
            raise ValueError("Invalid observation timing, certainty or record identity")
        if isinstance(self.payload, MarketAdjustment) and (
            self.payload.provenance.source_record_id is None
            or type(self.payload.provenance.observed_at) is not datetime
            or self.payload.provenance.available_at > self.provenance.available_at
            or self.payload.provenance.ingested_at > self.provenance.ingested_at
        ):
            raise ValueError(
                "Adjustment provenance must be cited and known with the observation"
            )
        archive = self.historical_snapshot
        if archive is not None and (
            archive.source_record_id is None
            or type(archive.observed_at) is not datetime
            or archive.observed_at < self.provenance.available_at
            or archive.ingested_at > self.provenance.ingested_at
        ):
            raise ValueError(
                "Historical snapshot must evidence this record's availability"
            )
        object.__setattr__(self, "certainty", float(self.certainty) or 0.0)

    @property
    def kind(self) -> InformationKind:
        if isinstance(self.payload, MarketAdjustment):
            return InformationKind.MARKET_ADJUSTMENT
        if isinstance(self.payload, AnalystOpinion):
            return InformationKind.ANALYST_OPINION
        if isinstance(self.payload, VerifiedWithdrawal):
            return InformationKind.VERIFIED_WITHDRAWAL
        return InformationKind.INJURY_RISK

    @classmethod
    def import_local(
        cls,
        data: Mapping[str, Any],
        *,
        registry: IdentityRegistry,
        external_id: str | None = None,
        name: str | None = None,
    ) -> Observation:
        """Decode local JSON without trusting caller-supplied canonical identity."""
        if {"player_id", "registry_revision", "registry_digest"} & data.keys():
            raise ValueError("Local imports must resolve identity through the registry")
        raw_provenance = data.get("provenance")
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("Local imports require source provenance")
        provenance = Provenance.from_dict(raw_provenance)
        player_id = registry.resolve(
            source=provenance.source,
            tour=Tour(data.get("tour")),
            external_id=external_id,
            name=name,
        )
        return cls.from_dict(
            dict(
                data,
                player_id=player_id,
                registry_revision=registry.revision,
                registry_digest=registry.digest,
            )
        )


def _digest(record: Contract) -> str:
    data = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _key(item: Observation) -> tuple[str, str, int]:
    return (
        item.provenance.source,
        item.provenance.source_record_id or "",
        item.record_version,
    )


def _ordered(observations: tuple[Observation, ...]) -> tuple[Observation, ...]:
    unique: dict[tuple[str, str, int], Observation] = {}
    players: dict[PlayerId, Tour] = {}
    events: dict[EventId, Tour] = {}
    for item in observations:
        if _key(item) in unique and unique[_key(item)] != item:
            raise ValueError("Conflicting copies of the same source record/version")
        unique[_key(item)] = item
        if players.setdefault(item.player_id, item.tour) != item.tour:
            raise ValueError("Player identity cannot cross tours")
        if events.setdefault(item.event_id, item.tour) != item.tour:
            raise ValueError("Event identity cannot cross tours")
    ordered = tuple(unique[key] for key in sorted(unique))
    for previous, current in zip(ordered, ordered[1:]):
        if _key(previous)[:2] != _key(current)[:2]:
            continue
        if (
            (previous.player_id, previous.event_id, previous.tour, previous.kind)
            != (current.player_id, current.event_id, current.tour, current.kind)
            or previous.provenance.available_at > current.provenance.available_at
        ):
            raise ValueError(
                "Record revisions must preserve scope and source availability order"
            )
    return ordered


class InformationStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    PENDING = "pending"


class RefreshStatus(str, Enum):
    BLOCKED_NO_APPROVED_PROVIDER = "blocked_no_approved_provider"


class SnapshotMode(str, Enum):
    LOCALLY_KNOWN = "locally_known"
    HISTORICAL_RECONSTRUCTION = "historical_reconstruction"


def _visible(item: Observation, cutoff: datetime, mode: SnapshotMode) -> bool:
    if item.provenance.available_at >= cutoff:
        return False
    if mode == SnapshotMode.LOCALLY_KNOWN:
        return item.provenance.ingested_at < cutoff
    return (
        item.historical_snapshot is not None
        and item.historical_snapshot.available_at < cutoff
    )


@dataclass(frozen=True, kw_only=True)
class InformationState(Contract):
    player_id: PlayerId
    kind: InformationKind
    active: tuple[Observation, ...]
    stale: tuple[Observation, ...]
    pending: tuple[Observation, ...]

    @property
    def missing(self) -> bool:
        """No current information is not a zero estimate or a negative withdrawal."""
        return not self.active

    @property
    def status(self) -> InformationStatus:
        values: set[str] = set()
        for item in self.active:
            payload = item.payload
            if isinstance(payload, MarketAdjustment):
                # Compare declared decimal values without binary unit-conversion noise.
                value = Fraction(str(payload.value))
                if payload.unit == AdjustmentUnit.PERCENTAGE_POINTS:
                    value /= 100
                values.add(str(value))
            else:
                values.add(json.dumps(payload.to_dict(), sort_keys=True))
        if len(values) > 1:
            return InformationStatus.CONFLICTING
        if self.active:
            return InformationStatus.ACTIVE
        if self.stale:
            return InformationStatus.STALE
        return InformationStatus.PENDING if self.pending else InformationStatus.MISSING


@dataclass(frozen=True, kw_only=True)
class InformationSnapshot(Contract):
    collection_revision: str
    collection_digest: str
    cutoff: datetime
    event_id: EventId
    tour: Tour
    player_ids: tuple[PlayerId, ...]
    observations: tuple[Observation, ...]
    mode: SnapshotMode = SnapshotMode.LOCALLY_KNOWN
    refresh_status: RefreshStatus = RefreshStatus.BLOCKED_NO_APPROVED_PROVIDER

    def __post_init__(self) -> None:
        super().__post_init__()
        _digest_lineage(self.collection_digest)
        if not self.player_ids or len(set(self.player_ids)) != len(self.player_ids):
            raise ValueError("Snapshot requires a unique, nonempty player roster")
        ordered = _ordered(self.observations)
        if len({_key(item)[:2] for item in ordered}) != len(ordered):
            raise ValueError(
                "Snapshot must select one visible revision per source record"
            )
        for item in ordered:
            if (
                item.event_id != self.event_id
                or item.tour != self.tour
                or item.player_id not in self.player_ids
                or not _visible(item, self.cutoff, self.mode)
            ):
                raise ValueError(
                    "Snapshot observation outside scope or knowledge cutoff"
                )
        object.__setattr__(self, "player_ids", tuple(sorted(self.player_ids)))
        object.__setattr__(self, "observations", ordered)
        object.__setattr__(self, "cutoff", self.cutoff.astimezone(timezone.utc))

    @property
    def digest(self) -> str:
        return _digest(self)

    def state(self, player_id: PlayerId, kind: InformationKind) -> InformationState:
        if player_id not in self.player_ids or not isinstance(kind, InformationKind):
            raise ValueError("Information state requires a scoped player and kind")
        items = tuple(
            item
            for item in self.observations
            if item.player_id == player_id and item.kind == kind
        )
        return InformationState(
            player_id=player_id,
            kind=kind,
            active=tuple(
                item
                for item in items
                if item.effective_at <= self.cutoff < item.expires_at
            ),
            stale=tuple(item for item in items if item.expires_at <= self.cutoff),
            pending=tuple(item for item in items if self.cutoff < item.effective_at),
        )

    @property
    def states(self) -> tuple[InformationState, ...]:
        return tuple(
            self.state(player, kind)
            for player in self.player_ids
            for kind in InformationKind
        )


@dataclass(frozen=True, kw_only=True)
class InformationCollection(Contract):
    revision: str
    observations: tuple[Observation, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "observations", _ordered(self.observations))

    @property
    def digest(self) -> str:
        return _digest(self)

    def extend(
        self, *, revision: str, observations: tuple[Observation, ...]
    ) -> InformationCollection:
        if revision == self.revision:
            raise ValueError("An extended collection requires a new revision")
        return replace(
            self, revision=revision, observations=self.observations + observations
        )

    def as_of(
        self,
        *,
        cutoff: datetime,
        event_id: EventId,
        tour: Tour,
        player_ids: tuple[PlayerId, ...],
        mode: SnapshotMode = SnapshotMode.LOCALLY_KNOWN,
    ) -> InformationSnapshot:
        snapshot = InformationSnapshot(
            collection_revision=self.revision,
            collection_digest=self.digest,
            cutoff=cutoff,
            event_id=event_id,
            tour=tour,
            player_ids=player_ids,
            observations=(),
            mode=mode,
        )
        latest: dict[tuple[str, str], Observation] = {}
        for item in self.observations:
            if (
                item.event_id == event_id
                and item.tour == tour
                and item.player_id in player_ids
                and _visible(item, cutoff, mode)
            ):
                latest[_key(item)[:2]] = item
        return replace(snapshot, observations=tuple(latest.values()))

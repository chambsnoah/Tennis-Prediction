"""Versioned, provider-neutral contracts for the new ATP pipeline.

Adapters resolve opaque IDs before constructing these records; display names are
never join keys. Unknown measurements are None, not estimates. Pool state is not
part of PredictionContext. Existing provider/legacy models are intentionally not
converted here, because their defaults cannot establish measurement provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import date, datetime, time, timezone
from enum import Enum
import hashlib
import json
import math
import re
from types import UnionType
from typing import (
    Any,
    Mapping,
    NewType,
    Protocol,
    Self,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


PlayerId = NewType("PlayerId", str)
EventId = NewType("EventId", str)
MatchId = NewType("MatchId", str)
SCHEMA_VERSION = 1


class Surface(str, Enum):
    HARD = "hard"
    CLAY = "clay"
    GRASS = "grass"
    CARPET = "carpet"
    UNKNOWN = "unknown"


class Tour(str, Enum):
    ATP = "atp"
    WTA = "wta"


class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    RETIRED = "retired"
    WALKOVER = "walkover"
    WITHDRAWN = "withdrawn"
    CANCELLED = "cancelled"


class EntryKind(str, Enum):
    PLAYER = "player"
    QUALIFIER = "qualifier"
    LUCKY_LOSER = "lucky_loser"
    REPLACEMENT = "replacement"
    BYE = "bye"


def _value(value: Any, annotation: Any, *, wire: bool) -> Any:
    """Validate constructors and decode JSON using the same closed field types."""
    origin = get_origin(annotation)
    if origin in (UnionType, Union):
        for option in get_args(annotation):
            try:
                return _value(value, option, wire=wire)
            except (TypeError, ValueError):
                pass
        raise ValueError(f"Invalid value for {annotation}")
    if annotation is type(None):
        if value is not None:
            raise ValueError("Expected null")
        return None
    if annotation in (PlayerId, EventId, MatchId):
        if not isinstance(value, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]*:[A-Za-z0-9._-]+", value
        ):
            raise ValueError("IDs must be opaque namespace:value identifiers")
        return value
    if origin is tuple:
        if not isinstance(value, (list, tuple) if wire else tuple):
            raise ValueError("Expected an immutable tuple (JSON array on the wire)")
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_value(item, args[0], wire=wire) for item in value)
        if len(value) != len(args):
            raise ValueError("Wrong tuple length")
        return tuple(_value(item, typ, wire=wire) for item, typ in zip(value, args))
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if not wire:
            if not isinstance(value, annotation):
                raise ValueError(f"Expected {annotation.__name__}")
            return value
        if not isinstance(value, Mapping):
            raise ValueError("Expected a JSON object")
        names = {field.name for field in fields(annotation)}
        if set(value) - names:
            raise ValueError(
                f"Unknown {annotation.__name__} fields: {sorted(set(value) - names)}"
            )
        if (
            type(value.get("schema_version")) is not int
            or value["schema_version"] != SCHEMA_VERSION
        ):
            raise ValueError("Missing or unsupported schema_version")
        hints = get_type_hints(annotation)
        return annotation(
            **{key: _value(item, hints[key], wire=True) for key, item in value.items()}
        )
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if wire:
            return annotation(value)
        if not isinstance(value, annotation):
            raise ValueError(f"Expected {annotation.__name__}")
        return value
    if annotation in (datetime, date):
        if wire and isinstance(value, str):
            value = annotation.fromisoformat(value)
        if type(value) is not annotation:
            raise ValueError(f"Expected {annotation.__name__}")
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Timestamps must include a timezone")
        return value
    if annotation is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Expected a finite number")
        return float(value)
    if type(value) is not annotation:
        raise ValueError(f"Expected {annotation.__name__}")
    if annotation is str and not value.strip():
        raise ValueError("Strings must not be blank")
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Contract):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True, kw_only=True)
class Contract:
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name, annotation in get_type_hints(type(self)).items():
            _value(getattr(self, name), annotation, wire=False)
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported schema_version")

    def to_dict(self) -> dict[str, Any]:
        return dict(_json_value(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        result: Self = _value(data, cls, wire=True)
        return result


@dataclass(frozen=True, kw_only=True)
class Provenance(Contract):
    source: str
    source_version: str
    source_record_id: str | None
    observed_at: datetime | date | None
    available_at: datetime
    ingested_at: datetime

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.available_at > self.ingested_at:
            raise ValueError("Availability cannot follow ingestion")
        if (
            isinstance(self.observed_at, datetime)
            and self.observed_at > self.available_at
        ):
            raise ValueError("Observation cannot follow availability")
        if (
            type(self.observed_at) is date
            and self.observed_at > self.available_at.date()
        ):
            raise ValueError("Observation date cannot follow availability")

    def require_available(self, cutoff: datetime) -> None:
        _value(cutoff, datetime, wire=False)
        if self.available_at >= cutoff:
            raise ValueError("Information was not available before prediction cutoff")


@dataclass(frozen=True, kw_only=True)
class Player(Contract):
    player_id: PlayerId
    display_name: str
    tour: Tour
    provenance: Provenance


@dataclass(frozen=True, kw_only=True)
class Event(Contract):
    event_id: EventId
    name: str
    tour: Tour
    start_date: date
    end_date: date
    surface: Surface
    best_of: int
    round_count: int
    level: str
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            self.end_date < self.start_date
            or self.best_of not in (3, 5)
            or self.round_count < 1
        ):
            raise ValueError("Invalid event dates, format or round count")


@dataclass(frozen=True, kw_only=True)
class MatchScore(Contract):
    """Games and optional tiebreak points are always in player1/player2 order."""

    sets: tuple[tuple[int, int], ...]
    tiebreak_points: tuple[tuple[int, int] | None, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if any(min(pair) < 0 for pair in self.sets):
            raise ValueError("Games cannot be negative")
        if self.tiebreak_points and len(self.tiebreak_points) != len(self.sets):
            raise ValueError("Tiebreak points must align with sets")
        if any(pair is not None and min(pair) < 0 for pair in self.tiebreak_points):
            raise ValueError("Tiebreak points cannot be negative")
        for games, points in zip(self.sets, self.tiebreak_points):
            if points is None:
                continue
            if games not in ((7, 6), (6, 7), (6, 6), (13, 12), (12, 13), (12, 12)):
                raise ValueError("Tiebreak points require a tiebreak set")
            if games[0] != games[1] and (
                max(points) < 7
                or abs(points[0] - points[1]) < 2
                or (
                    max(points) not in (7, 10)
                    and abs(points[0] - points[1]) != 2
                )
                or (games[0] > games[1]) != (points[0] > points[1])
            ):
                raise ValueError("Tiebreak points contradict completed set")


@dataclass(frozen=True, kw_only=True)
class Match(Contract):
    """Winners are canonical player IDs, never names or positional integers.

    A withdrawal is pre-play availability information, not a played loss. An
    adjudicated walkover has a winner but no played score. None score means the
    source did not supply it; incomplete retirement scores remain representable.
    """

    match_id: MatchId
    event_id: EventId
    tour: Tour
    player1_id: PlayerId
    player2_id: PlayerId
    surface: Surface
    best_of: int
    round_number: int
    occurred_at: datetime | date | None
    status: MatchStatus
    winner_id: PlayerId | None
    score: MatchScore | None
    provenance: Provenance
    withdrawn_player_id: PlayerId | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            self.player1_id == self.player2_id
            or self.best_of not in (3, 5)
            or self.round_number < 1
        ):
            raise ValueError("Invalid players, format or round")
        decided = self.status in (
            MatchStatus.COMPLETED,
            MatchStatus.RETIRED,
            MatchStatus.WALKOVER,
        )
        if decided != (self.winner_id is not None):
            raise ValueError("Only decided matches must have a winner")
        if self.winner_id is not None and self.winner_id not in (
            self.player1_id,
            self.player2_id,
        ):
            raise ValueError("Winner must be one of the match players")
        if self.withdrawn_player_id is not None and (
            self.status not in (MatchStatus.WITHDRAWN, MatchStatus.WALKOVER)
            or self.withdrawn_player_id not in (self.player1_id, self.player2_id)
            or self.withdrawn_player_id == self.winner_id
        ):
            raise ValueError("Withdrawal must identify an unplayed, non-winning entrant")
        if (
            self.status
            in (MatchStatus.WALKOVER, MatchStatus.WITHDRAWN, MatchStatus.SCHEDULED)
            and self.score is not None
        ):
            raise ValueError("Unplayed matches cannot have a played score")
        if self.score is not None and len(self.score.sets) > self.best_of:
            raise ValueError("Too many sets for match format")
        if self.status is MatchStatus.COMPLETED and self.score is not None:
            counts = [0, 0]
            for a, b in self.score.sets:
                if not (
                    (max(a, b) >= 6 and abs(a - b) == 2)
                    or (max(a, b) == 7 and min(a, b) == 6)
                    or (
                        max(a, b) == 13
                        and min(a, b) == 12
                        and counts[0] == counts[1] == self.best_of // 2
                    )
                    or (max(a, b) == 6 and min(a, b) <= 4)
                ):
                    raise ValueError("Completed match has an incomplete set")
                if max(counts) == self.best_of // 2 + 1:
                    raise ValueError("Sets played after the match was decided")
                counts[0 if a > b else 1] += 1
            index = 0 if self.winner_id == self.player1_id else 1
            if counts[index] != self.best_of // 2 + 1:
                raise ValueError("Score contradicts winner or format")

    def swapped(self) -> Self:
        score = self.score
        if score is not None:
            score = replace(
                score,
                sets=tuple((b, a) for a, b in score.sets),
                tiebreak_points=tuple(
                    None if pair is None else (pair[1], pair[0])
                    for pair in score.tiebreak_points
                ),
            )
        return replace(
            self, player1_id=self.player2_id, player2_id=self.player1_id, score=score
        )


@dataclass(frozen=True, kw_only=True)
class RankingSnapshot(Contract):
    player_id: PlayerId
    tour: Tour
    ranking_date: date
    rank: int | None
    points: int | None
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        if (self.rank is not None and self.rank < 1) or (
            self.points is not None and self.points < 0
        ):
            raise ValueError("Invalid ranking or ranking points")
        if self.ranking_date > self.provenance.available_at.date():
            raise ValueError("Ranking cannot be available before its effective date")


@dataclass(frozen=True, kw_only=True)
class PlayerMatchStats(Contract):
    """Measured counts only. Missing denominators/measurements remain None."""

    match_id: MatchId
    player_id: PlayerId
    provenance: Provenance
    aces: int | None = None
    double_faults: int | None = None
    service_points: int | None = None
    first_serves_in: int | None = None
    first_serve_points_won: int | None = None
    second_serve_points_won: int | None = None
    return_points: int | None = None
    return_points_won: int | None = None
    break_points_faced: int | None = None
    break_points_saved: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        counts = (
            self.aces,
            self.double_faults,
            self.service_points,
            self.first_serves_in,
            self.first_serve_points_won,
            self.second_serve_points_won,
            self.return_points,
            self.return_points_won,
            self.break_points_faced,
            self.break_points_saved,
        )
        if any(count is not None and count < 0 for count in counts):
            raise ValueError("Statistics cannot be negative")
        if (
            self.aces is not None
            and self.first_serve_points_won is not None
            and self.second_serve_points_won is not None
            and self.aces > self.first_serve_points_won + self.second_serve_points_won
        ):
            raise ValueError("Aces exceed known service points won")
        for numerator, denominator in (
            (self.aces, self.service_points),
            (self.first_serves_in, self.service_points),
            (self.first_serve_points_won, self.first_serves_in),
            (self.return_points_won, self.return_points),
            (self.break_points_saved, self.break_points_faced),
            (self.double_faults, self.service_points),
        ):
            if (
                numerator is not None
                and denominator is not None
                and numerator > denominator
            ):
                raise ValueError("Statistic exceeds its denominator")
        if self.service_points is not None and self.first_serves_in is not None:
            for count in (self.second_serve_points_won, self.double_faults):
                if (
                    count is not None
                    and count > self.service_points - self.first_serves_in
                ):
                    raise ValueError("Statistic exceeds second-serve opportunities")
            if (
                self.second_serve_points_won is not None
                and self.double_faults is not None
            ):
                if (
                    self.second_serve_points_won + self.double_faults
                    > self.service_points - self.first_serves_in
                ):
                    raise ValueError("Second-serve outcomes exceed opportunities")


@dataclass(frozen=True, kw_only=True)
class DrawSlot(Contract):
    position: int
    kind: EntryKind
    player_id: PlayerId | None
    seed: int | None = None
    replaced_player_id: PlayerId | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.position < 1 or (self.seed is not None and self.seed < 1):
            raise ValueError("Invalid draw position or seed")
        if self.kind is EntryKind.BYE:
            if any(
                value is not None
                for value in (self.player_id, self.seed, self.replaced_player_id)
            ):
                raise ValueError("Byes have no player, seed or replacement")
        elif (
            self.kind not in (EntryKind.QUALIFIER, EntryKind.LUCKY_LOSER)
            and self.player_id is None
        ):
            raise ValueError("Resolved entrant requires a player ID")
        if self.player_id is None and self.seed is not None:
            raise ValueError("Unresolved entrants cannot be seeded")
        if self.replaced_player_id is not None:
            if (
                self.kind is not EntryKind.REPLACEMENT
                or self.replaced_player_id == self.player_id
            ):
                raise ValueError("Replacement must identify a different former entrant")


@dataclass(frozen=True, kw_only=True)
class Draw(Contract):
    event: Event
    slots: tuple[DrawSlot, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        super().__post_init__()
        size = len(self.slots)
        if size < 2 or size & (size - 1) or size != 2**self.event.round_count:
            raise ValueError("Draw slots must match the event's power-of-two bracket")
        if tuple(slot.position for slot in self.slots) != tuple(range(1, size + 1)):
            raise ValueError("Draw slots must be complete and in bracket order")
        players = [slot.player_id for slot in self.slots if slot.player_id is not None]
        seeds = [slot.seed for slot in self.slots if slot.seed is not None]
        if len(set(players)) != len(players) or len(set(seeds)) != len(seeds):
            raise ValueError("Duplicate player IDs or seeds in draw")
        entrants = sum(slot.kind is not EntryKind.BYE for slot in self.slots)
        if any(seed > entrants for seed in seeds):
            raise ValueError("Seed exceeds field size")
        if any(
            a.kind is EntryKind.BYE and b.kind is EntryKind.BYE
            for a, b in zip(self.slots[::2], self.slots[1::2])
        ):
            raise ValueError("Both sides of a first-round match cannot be byes")


def _before(value: datetime | date | None, cutoff: datetime) -> bool:
    if value is None:
        return False
    if type(value) is date:
        # Date-only results become eligible after the entire UTC day, not midnight.
        value = datetime.combine(value, time.max, tzinfo=timezone.utc)
    return value < cutoff


@dataclass(frozen=True, kw_only=True)
class PredictionContext(Contract):
    """Pre-match tennis inputs only; no arbitrary feature or pool-state dictionary.

    Source adapters -> these records -> as-of features -> probability provider ->
    simulation -> pool objectives -> presentation. History must exclude the
    target result, cross-tour records and information published at/after cutoff.
    """

    event: Event
    player1_id: PlayerId
    player2_id: PlayerId
    round_number: int
    cutoff: datetime
    target_match_id: MatchId | None = None
    rankings: tuple[RankingSnapshot, ...] = ()
    history: tuple[Match, ...] = ()
    statistics: tuple[PlayerMatchStats, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            self.player1_id == self.player2_id
            or not 1 <= self.round_number <= self.event.round_count
        ):
            raise ValueError("Invalid prediction players or round")
        self.event.provenance.require_available(self.cutoff)
        ids = (self.player1_id, self.player2_id)
        if len({ranking.player_id for ranking in self.rankings}) != len(self.rankings):
            raise ValueError("Use at most one as-of ranking per player")
        for ranking in self.rankings:
            ranking.provenance.require_available(self.cutoff)
            if ranking.player_id not in ids or ranking.tour is not self.event.tour:
                raise ValueError("Ranking belongs to another player or tour")
        matches = {match.match_id: match for match in self.history}
        if len(matches) != len(self.history):
            raise ValueError("Duplicate historical match IDs")
        for match in self.history:
            match.provenance.require_available(self.cutoff)
            if match.match_id == self.target_match_id or not _before(
                match.occurred_at, self.cutoff
            ):
                raise ValueError(
                    "Target, unknown-time or future results are not history"
                )
            if match.tour is not self.event.tour or match.winner_id is None:
                raise ValueError(
                    "History must contain decided matches from the same tour"
                )
        if len({(stats.match_id, stats.player_id) for stats in self.statistics}) != len(
            self.statistics
        ):
            raise ValueError("Duplicate player-match statistics")
        for stats in self.statistics:
            stats.provenance.require_available(self.cutoff)
            historical_match = matches.get(stats.match_id)
            if historical_match is None or stats.player_id not in (
                historical_match.player1_id,
                historical_match.player2_id,
            ):
                raise ValueError(
                    "Statistics must reference a player in historical matches"
                )
            if historical_match.status is MatchStatus.WALKOVER:
                raise ValueError("Walkovers cannot supply played statistics")

    def swapped(self) -> Self:
        return replace(self, player1_id=self.player2_id, player2_id=self.player1_id)

    @property
    def digest(self) -> str:
        """Bind a response to all request inputs, independent of target orientation."""
        payload = self.to_dict()
        payload["player1_id"], payload["player2_id"] = sorted(
            (self.player1_id, self.player2_id)
        )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, kw_only=True)
class Coverage(Contract):
    observed: tuple[str, ...]
    missing: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if len(set(self.observed + self.missing)) != len(self.observed + self.missing):
            raise ValueError("Coverage fields must be unique and disjoint")


@dataclass(frozen=True, kw_only=True)
class MatchProbability(Contract):
    """Probability that player1 wins; player2 probability is its complement.

    None calibration_version explicitly means uncalibrated. Availability risk
    inclusion must be declared so simulation does not count it twice. No detailed
    score or serve-point forecast is implied by a match-win probability.
    """

    player1_id: PlayerId
    player2_id: PlayerId
    player1_win_probability: float
    model_version: str
    calibration_version: str | None
    cutoff: datetime
    context_digest: str
    coverage: Coverage
    warnings: tuple[str, ...]
    includes_availability_risk: bool

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            self.player1_id == self.player2_id
            or not 0 <= self.player1_win_probability <= 1
        ):
            raise ValueError("Invalid probability or player orientation")
        if not re.fullmatch(r"[0-9a-f]{64}", self.context_digest):
            raise ValueError("Expected a SHA-256 context digest")

    def swapped(self) -> Self:
        return replace(
            self,
            player1_id=self.player2_id,
            player2_id=self.player1_id,
            player1_win_probability=1 - self.player1_win_probability,
        )

    def require_context(self, context: PredictionContext) -> None:
        if (self.player1_id, self.player2_id, self.cutoff, self.context_digest) != (
            context.player1_id,
            context.player2_id,
            context.cutoff,
            context.digest,
        ):
            raise ValueError(
                "Probability orientation/cutoff/context does not match request"
            )


class MatchProbabilityProvider(Protocol):
    """Return P(player1 wins) at context.cutoff, or raise an explicit error.

    predict(context.swapped()) must complement predict(context), preserving
    lineage, coverage and warnings (within numerical tolerance). Providers must
    not read present-day state or pool ownership/quotas/scores, silently substitute
    another model, or fabricate missing measurements. Callers validate responses
    with require_context before using them in neutral tournament simulation.
    """

    def predict(self, context: PredictionContext) -> MatchProbability: ...

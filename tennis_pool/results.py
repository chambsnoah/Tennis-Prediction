"""Gated 2026 scoring from a complete canonical bracket, never inferred losses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path

from tennis_api.models.canonical import (
    Contract, Draw, EntryKind, EventId, Match, MatchStatus, PlayerId,
    RankingSnapshot, Tour,
)
from tennis_pool.rules import DEPENDENCIES, require_resolved
from tennis_pool.scoring import atp_points, band, bonus_points


@dataclass(frozen=True, kw_only=True)
class PlayerScore(Contract):
    player_id: PlayerId
    lost_in_round: int | None
    beaten_by: PlayerId | None
    played_wins: tuple[PlayerId, ...]
    atp: int
    bonus: int
    withdrew_before_participation: bool

    @property
    def total(self) -> int:
        return self.atp + self.bonus


@dataclass(frozen=True, kw_only=True)
class TournamentScore(Contract):
    event_id: EventId
    kind: str
    players: tuple[PlayerScore, ...]
    input_digest: str
    rule_register_version: str
    rules_source_version: str
    rules_source_sha256: str
    scoring_decisions: tuple[tuple[str, str, str], ...]


def score_tournament(
    draw: Draw,
    matches: tuple[Match, ...],
    rankings: tuple[RankingSnapshot, ...],
    kind: str,
    *,
    allow_provisional: bool = False,
    register_path: str | Path | None = None,
) -> TournamentScore:
    """Score a finished GS/M7/M6 event with explicit first-day ranking evidence.

    Byes advance without participation or bonus. Walkovers require the withdrawn
    entrant's identity, advance without bonus, and close replacement eligibility.
    A first-participation withdrawal scores zero; later withdrawals retain the
    terminal award and earned bonuses. Started retirements are played matches.
    Unadjudicated withdrawals, missing finals and unresolved entrants fail closed.
    Rankings must be snapshots applicable/available by the first event day;
    callers are responsible for supplying the official first-day snapshot.
    """
    register = require_resolved(
        "scoring", register_path, allow_provisional=allow_provisional,
    )
    # New decisions need an implementation review, not just a changed status.
    decision_digest = hashlib.sha256(json.dumps({
        key: register["decisions"][key]["decision"] for key in DEPENDENCIES["scoring"]
    }, sort_keys=True).encode()).hexdigest()
    if (register["register_version"] != "2026-provisional-2"
            or decision_digest != "d949f25064e47fde1b44ff74fab20fa7b84e520701a1c2454b9aa31a73ea8b8b"):
        raise ValueError("Unsupported scoring rule version; implementation review required")
    event = draw.event
    formats = {"gs": (7, 5, 128, 32), "m7": (7, 3, 96, 32), "m6": (6, 3, 56, 16)}
    if kind not in formats or event.tour is not Tour.ATP:
        raise ValueError("Unsupported ATP pool scoring format")
    rounds, best_of, field_size, seed_limit = formats[kind]
    entries = {s.player_id: s for s in draw.slots if s.player_id is not None}
    if (event.round_count != rounds or event.best_of != best_of
            or len(entries) != field_size
            or any(s.kind is not EntryKind.BYE and s.player_id is None for s in draw.slots)):
        raise ValueError("Unresolved entrants or inconsistent pool draw format")
    for slot in entries.values():
        band(slot.seed)
        if slot.seed is not None and slot.seed > seed_limit:
            raise ValueError("Event seed exceeds format limit")

    ranks: dict[PlayerId, int | None] = {}
    for snapshot in rankings:
        if (snapshot.player_id not in entries or snapshot.player_id in ranks
                or snapshot.tour is not event.tour
                or snapshot.ranking_date > event.start_date
                or snapshot.provenance.available_at.date() > event.start_date):
            raise ValueError("Invalid or post-start first-day ranking evidence")
        ranks[snapshot.player_id] = snapshot.rank

    indexed: dict[tuple[int, frozenset[PlayerId]], Match] = {}
    match_ids = set()
    for match in matches:
        key = (match.round_number, frozenset((match.player1_id, match.player2_id)))
        occurred = match.occurred_at
        occurred_date = occurred.date() if isinstance(occurred, datetime) else occurred
        if (match.match_id in match_ids or key in indexed
                or match.event_id != event.event_id or match.tour is not event.tour
                or match.surface is not event.surface or match.best_of != event.best_of
                or not 1 <= match.round_number <= rounds
                or match.player1_id not in entries or match.player2_id not in entries
                or (occurred_date is not None
                    and not event.start_date <= occurred_date <= event.end_date)
                or match.status not in (
                    MatchStatus.COMPLETED, MatchStatus.RETIRED, MatchStatus.WALKOVER,
                )):
            raise ValueError("Duplicate, undecided or incompatible match evidence")
        indexed[key] = match
        match_ids.add(match.match_id)

    wins: dict[PlayerId, list[PlayerId]] = {p: [] for p in entries}
    bonuses = dict.fromkeys(entries, 0)
    losses: dict[PlayerId, tuple[int, PlayerId, bool]] = {}
    participated: set[PlayerId] = set()
    active = [s.player_id for s in draw.slots]
    for rnd in range(1, rounds + 1):
        advancing: list[PlayerId | None] = []
        for p1, p2 in zip(active[::2], active[1::2]):
            if p1 is None or p2 is None:
                advancing.append(p1 or p2)
                continue
            record = indexed.pop((rnd, frozenset((p1, p2))), None)
            if record is None:
                raise ValueError("Incomplete bracket or impossible result progression")
            winner = record.winner_id
            assert winner is not None  # canonical decided-match invariant
            loser = p2 if winner == p1 else p1
            withdrew_before = False
            if record.status is MatchStatus.WALKOVER:
                if record.withdrawn_player_id != loser:
                    raise ValueError("Walkover requires explicit withdrawal identity")
                withdrew_before = loser not in participated
                participated.add(winner)
            else:
                participated.update((p1, p2))
                wins[winner].append(loser)
                bonuses[winner] += bonus_points(
                    entries[winner].seed, ranks.get(winner),
                    entries[loser].seed, ranks.get(loser), kind == "gs",
                )
            losses[loser] = (rnd, winner, withdrew_before)
            advancing.append(winner)
        active = advancing
    if indexed or len(active) != 1 or active[0] is None:
        raise ValueError("Extraneous matches or missing champion")

    players = []
    for player in entries:
        loss = losses.get(player)
        loss_round = loss[0] if loss else None
        withdrew_before = loss[2] if loss else False
        players.append(PlayerScore(
            player_id=player, lost_in_round=loss_round,
            beaten_by=loss[1] if loss else None, played_wins=tuple(wins[player]),
            atp=0 if withdrew_before else atp_points(loss_round, kind),
            bonus=bonuses[player], withdrew_before_participation=withdrew_before,
        ))
    payload = {
        "draw": draw.to_dict(),
        "matches": [m.to_dict() for m in sorted(matches, key=lambda m: m.match_id)],
        "rankings": [r.to_dict() for r in sorted(rankings, key=lambda r: r.player_id)],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return TournamentScore(
        event_id=event.event_id, kind=kind, players=tuple(players), input_digest=digest,
        rule_register_version=register["register_version"],
        rules_source_version=register["rules_source"]["version"],
        rules_source_sha256=register["rules_source"]["sha256"],
        scoring_decisions=tuple(
            (key, register["decisions"][key]["status"], register["decisions"][key]["decision"])
            for key in DEPENDENCIES["scoring"]
        ),
    )

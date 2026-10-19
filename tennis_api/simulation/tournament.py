"""Vectorized fixed-draw outcomes, independent of pool scoring and Elo.

Adapted from pool_optimizer/pool/simulate.py's round-wise array traversal.
Only the injected provider supplies match strength; no hidden hazard or format
adjustment is applied. Array entries are indices into player_ids, with -1 vacant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
import hashlib
import json

import numpy as np
from numpy.typing import NDArray

from tennis_api.models.canonical import (
    Draw,
    EntryKind,
    Match,
    MatchProbability,
    MatchProbabilityProvider,
    PlayerId,
    PlayerMatchStats,
    PredictionContext,
    RankingSnapshot,
)


class OutcomeKind(IntEnum):
    VACANT = 0
    UNCONTESTED = 1
    DECIDED = 2
    RETIRED = 3


@dataclass(frozen=True)
class ForcedRetirement:
    """Conditional scenario: retire during this round only if reached and played."""

    player_id: PlayerId
    round_number: int


@dataclass(frozen=True)
class RoundOutcomes:
    round_number: int
    player1: NDArray[np.int32]
    player2: NDArray[np.int32]
    winners: NDArray[np.int32]
    kinds: NDArray[np.int32]


@dataclass(frozen=True)
class TournamentSimulation:
    player_ids: tuple[PlayerId, ...]
    rounds: tuple[RoundOutcomes, ...]
    round_reach: NDArray[np.int32]
    champions: NDArray[np.int32]
    predictions: tuple[MatchProbability, ...]
    draw_digest: str
    rng_initial_state: str
    cutoff: datetime
    withdrawn: frozenset[PlayerId]
    retirements: tuple[ForcedRetirement, ...]
    simulator_version: str = "neutral-bracket-1"


def simulate_tournament(
    draw: Draw,
    provider: MatchProbabilityProvider,
    *,
    cutoff: datetime,
    simulations: int,
    rng: np.random.Generator,
    withdrawn: frozenset[PlayerId] = frozenset(),
    retirements: tuple[ForcedRetirement, ...] = (),
    rankings: tuple[RankingSnapshot, ...] = (),
    history: tuple[Match, ...] = (),
    statistics: tuple[PlayerMatchStats, ...] = (),
) -> TournamentSimulation:
    """Simulate a fixed bracket, vectorizing over independent tournament runs.

    round_reach is the last round entered (one-based), with round_count + 1
    denoting a champion. A bye advances without a played win. No result here is
    a canonical historical Match or a detailed score/retirement forecast.
    """
    if type(simulations) is not int or simulations < 1:
        raise ValueError("simulations must be a positive integer")
    if not isinstance(rng, np.random.Generator):
        raise ValueError("rng must be an independent numpy Generator")
    if not isinstance(withdrawn, frozenset) or not isinstance(retirements, tuple):
        raise ValueError("Availability scenarios must use immutable collections")
    draw.provenance.require_available(cutoff)
    draw.event.provenance.require_available(cutoff)
    if any(s.player_id is None and s.kind is not EntryKind.BYE for s in draw.slots):
        raise ValueError("Resolve all qualifier/lucky-loser entrants before simulation")
    player_ids = tuple(s.player_id for s in draw.slots if s.player_id is not None)
    indices = {player: i for i, player in enumerate(player_ids)}
    if not withdrawn <= indices.keys():
        raise ValueError("Withdrawn player is not in the draw")
    retirement_rounds = np.zeros(len(player_ids), dtype=np.int32)
    for retirement in retirements:
        if (
            retirement.player_id not in indices
            or retirement.player_id in withdrawn
            or type(retirement.round_number) is not int
            or not 1 <= retirement.round_number <= draw.event.round_count
        ):
            raise ValueError("Invalid retirement player or round")
        index = indices[retirement.player_id]
        if retirement_rounds[index]:
            raise ValueError("Duplicate retirement player")
        retirement_rounds[index] = retirement.round_number
    if len({r.player_id for r in rankings}) != len(rankings):
        raise ValueError("Duplicate ranking players")
    for ranking in rankings:
        ranking.provenance.require_available(cutoff)
        if ranking.player_id not in indices or ranking.tour is not draw.event.tour:
            raise ValueError("Ranking is not for this draw and tour")
    # Validate the shared history even when no contested match queries a provider.
    validation_ids = (player_ids[0], PlayerId(player_ids[0] + ".validation"))
    if len(player_ids) > 1:
        validation_ids = (player_ids[0], player_ids[1])
    PredictionContext(
        event=draw.event,
        player1_id=validation_ids[0],
        player2_id=validation_ids[1],
        round_number=1,
        cutoff=cutoff,
        history=history,
        statistics=statistics,
    )
    slots = np.array(
        [indices[s.player_id] if s.player_id is not None else -1 for s in draw.slots],
        dtype=np.int32,
    )
    for player in withdrawn:
        slots[slots == indices[player]] = -1
    current = np.tile(slots[:, None], (1, simulations))
    reach = np.zeros((len(player_ids), simulations), dtype=np.int32)
    initial_state = json.dumps(
        rng.bit_generator.state, sort_keys=True, default=lambda value: value.tolist()
    )
    rounds: list[RoundOutcomes] = []
    predictions: list[MatchProbability] = []
    for number in range(1, draw.event.round_count + 1):
        a, b = current[::2], current[1::2]
        for entrants in (a, b):
            row, sim = np.nonzero(entrants >= 0)
            reach[entrants[row, sim], sim] = number
        p = np.zeros(a.shape, dtype=np.float64)
        p[(a >= 0) & (b < 0)] = 1.0
        both = (a >= 0) & (b >= 0)
        retiring_a = both & (retirement_rounds[np.maximum(a, 0)] == number)
        retiring_b = both & (retirement_rounds[np.maximum(b, 0)] == number)
        if np.any(retiring_a & retiring_b):
            raise ValueError(
                "Both opponents retire: an explicit adjudication is required"
            )
        p[retiring_b] = 1.0
        modeled = both & ~retiring_a & ~retiring_b
        pairs = np.unique(np.stack((a[modeled], b[modeled]), axis=1), axis=0)
        for ia, ib in pairs:
            context = PredictionContext(
                event=draw.event,
                player1_id=player_ids[int(ia)],
                player2_id=player_ids[int(ib)],
                round_number=number,
                cutoff=cutoff,
                rankings=tuple(
                    r
                    for r in rankings
                    if r.player_id in (player_ids[int(ia)], player_ids[int(ib)])
                ),
                history=history,
                statistics=statistics,
            )
            prediction = provider.predict(context)
            prediction.require_context(context)
            if (withdrawn or retirements) and prediction.includes_availability_risk:
                raise ValueError(
                    "Explicit scenarios would double count provider availability risk"
                )
            predictions.append(prediction)
            p[(a == ia) & (b == ib)] = prediction.player1_win_probability
        winners = np.where(rng.random(a.shape) < p, a, b).astype(np.int32)
        kinds = np.full(a.shape, OutcomeKind.VACANT, dtype=np.int32)
        kinds[(a >= 0) | (b >= 0)] = OutcomeKind.UNCONTESTED
        kinds[both] = OutcomeKind.DECIDED
        kinds[retiring_a | retiring_b] = OutcomeKind.RETIRED
        rounds.append(RoundOutcomes(number, a.copy(), b.copy(), winners.copy(), kinds))
        current = winners
    champions = current[0].copy()
    real = champions >= 0
    reach[champions[real], np.nonzero(real)[0]] = draw.event.round_count + 1
    for outcome in rounds:
        for array in (outcome.player1, outcome.player2, outcome.winners, outcome.kinds):
            array.flags.writeable = False
    reach.flags.writeable = champions.flags.writeable = False
    digest = hashlib.sha256(
        json.dumps(draw.to_dict(), sort_keys=True).encode()
    ).hexdigest()
    return TournamentSimulation(
        player_ids,
        tuple(rounds),
        reach,
        champions,
        tuple(predictions),
        digest,
        initial_state,
        cutoff,
        withdrawn,
        retirements,
    )

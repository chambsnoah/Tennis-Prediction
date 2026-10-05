"""Pick-set optimizer: maximize P(finishing top-3 of the week).

Enumerates valid 5-pick sets for the user (respecting band quotas and the
5-uses-per-player cap), scores each against the simulated points matrix and
the simulated rival field, and ranks by P(top-3), tie-broken by expected
points.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product

import numpy as np

from .opponents import BAND_KEYS, FieldModel, band_of_seed
from .parsers import norm


@dataclass
class PickSet:
    players: tuple[int, ...]        # indices into the sim points matrix
    p_top3: float
    p_win: float
    ev: float
    q90: float


def rival_threshold(rival_scores: np.ndarray, k: int = 3) -> np.ndarray:
    """k-th highest rival score per sim: beat-or-tie this to be top-k."""
    part = np.partition(rival_scores, -k, axis=0)
    return part[-k, :]


def enumerate_sets(
    names: list[str],
    seeds: list[int | None],
    quota: dict[str, int],
    my_usage: dict[str, int],
    points: np.ndarray,
    top_nf: int = 10,
    top_band: int = 6,
    max_sets: int = 150000,
) -> list[tuple[int, ...]]:
    """Candidate 5-pick sets under the season quota bank.

    Band quotas are a SEASON budget, not one-per-tournament: taking two or
    three players from the same band in one week is legal if the bank allows
    it (weekly winners do this). Structures enumerated: every (a,b,c,d) with
    a<=quota['1-4'] etc. and a+b+c+d+nf = 5, nf <= 3. Candidate pools are
    pre-trimmed by simulated EV + upside to keep enumeration tractable."""
    ev = points.mean(axis=1)
    q95 = np.quantile(points, 0.95, axis=1)
    upside = ev + q95

    # qualifier / lucky-loser placeholders are not real, pickable players
    usable = [my_usage.get(norm(n), 0) < 5
              and not norm(n).startswith(("qualifier", "lucky loser"))
              for n in names]
    band_pool: dict[str, list[int]] = {k: [] for k in BAND_KEYS}
    nf_pool: list[int] = []
    for i, s in enumerate(seeds):
        if not usable[i]:
            continue
        b = band_of_seed(s)
        if b:
            band_pool[b].append(i)
        else:
            nf_pool.append(i)

    for k in band_pool:
        band_pool[k] = sorted(band_pool[k], key=lambda i: -upside[i])[:top_band]
    nf_pool = sorted(nf_pool, key=lambda i: -upside[i])[:top_nf]

    # up to 3 from one band (4 for 17-32 — it has the deep upset pool);
    # beyond that the combinatorics outrun the realized benefit
    caps = [min(quota.get(k, 0), len(band_pool[k]), 4 if k == "17-32" else 3)
            for k in BAND_KEYS]

    sets: set[tuple[int, ...]] = set()
    for counts in product(*(range(c + 1) for c in caps)):
        n_seeded = sum(counts)
        n_nf = 5 - n_seeded
        if not (0 <= n_nf <= min(3, len(nf_pool))):
            continue
        per_band = [
            list(combinations(band_pool[k], counts[j]))
            for j, k in enumerate(BAND_KEYS)
        ]
        for combo in product(*per_band):
            seeded = tuple(i for group in combo for i in group)
            for nfs in combinations(nf_pool, n_nf):
                sets.add(tuple(sorted(seeded + nfs)))
                if len(sets) > max_sets:
                    raise RuntimeError(
                        "candidate explosion: lower top_band/top_nf")
    return sorted(sets)


def filter_contrarian(
    candidate_sets: list[tuple[int, ...]],
    ownership: np.ndarray,
    low_own: float = 0.15,
    min_low: int = 2,
    max_total_own: float = 0.60,
) -> list[tuple[int, ...]]:
    """The contrarian sheet, set-level: at least `min_low` picks projected
    under `low_own` ownership AND total set ownership under `max_total_own`
    — leverage where it pays, while anchors stay free of the per-pick
    `low_own` condition. (An all-picks cap was tested and rejected: the
    actual variance-week winners paired one popular anchor — Shelton 46%,
    Fils 20-30% — with low-owned leverage picks.)

    `ownership` must be the model's RAW projection, the scale these
    thresholds were set and backtested on — never the hand-floored one
    (PLAYBOOK §6 floors correct the rival simulation; a 55%-floored anchor
    would otherwise eat the whole 60% budget). Excluding the anchor from the
    total instead was tested on 2026-10-05 and rejected: the filter then
    passed the main sheet itself and the mixed playbook fell from 4/11 to
    3/11 weeks in the money."""
    out = [
        s for s in candidate_sets
        if sum(1 for j in s if ownership[j] < low_own) >= min_low
        and sum(ownership[j] for j in s) <= max_total_own
    ]
    return out or candidate_sets


def evaluate(
    candidate_sets: list[tuple[int, ...]],
    points: np.ndarray,
    rival_scores: np.ndarray,
    top_n: int = 20,
    screen_sims: int = 5000,
) -> list[PickSet]:
    """Three-pass funnel: cheap moment-based proxy over everything, sim
    screening on a slice, full scoring for the survivors.

    Returns the candidates ranked by P(top-3) (tie-break: EV)."""
    ev_p = points.mean(axis=1)
    if len(candidate_sets) > 20000:
        q90 = np.quantile(points, 0.90, axis=1)
        proxy = ev_p + q90  # upside-tilted; cheap and monotone enough to trim
        mat = np.array(candidate_sets)
        scores = proxy[mat].sum(axis=1)
        keep = np.argsort(-scores)[:20000]
        candidate_sets = [candidate_sets[i] for i in keep]

    if len(candidate_sets) > 3000 and points.shape[1] > screen_sims:
        t3s = rival_threshold(rival_scores[:, :screen_sims], 3)
        scored = []
        for s in candidate_sets:
            my = points[list(s), :screen_sims].sum(axis=0)
            scored.append((float((my >= t3s).mean()), s))
        scored.sort(reverse=True)
        candidate_sets = [s for _, s in scored[: max(800, top_n * 40)]]

    t3 = rival_threshold(rival_scores, 3)
    t1 = rival_threshold(rival_scores, 1)
    results: list[PickSet] = []
    for s in candidate_sets:
        my = points[list(s), :].sum(axis=0)
        results.append(PickSet(
            players=s,
            p_top3=float((my >= t3).mean()),
            p_win=float((my >= t1).mean()),
            ev=float(my.mean()),
            q90=float(np.quantile(my, 0.90)),
        ))
    return sorted(results, key=lambda r: (-r.p_top3, -r.ev))[:top_n]

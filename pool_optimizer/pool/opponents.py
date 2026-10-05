"""Model of what the other poolers will pick.

For each rival we know exactly: remaining band quotas (Banques), how many
times they've used each player (ChoixSommaire, max 5), and their full pick
history (Choix). Sampling per rival:
  1. draw a band structure (e.g. 1/1/1/1/1 or 2/0/1/1/1) from that rival's
     own historical structure distribution, clipped to their remaining quota;
  2. fill each slot proportionally to (recency-weighted field popularity x
     personal affinity), sharpened so the simulated crowd concentrates on
     favorites the way the real one does.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from .parsers import ParticipantBank, norm

BAND_KEYS = ("1-4", "5-8", "9-16", "17-32")
CONCENTRATION = 1.35   # weight sharpening; calibrated vs actual weekly holdings


def band_of_seed(seed: int | None) -> str | None:
    if seed is None:
        return None
    for hi, key in ((4, "1-4"), (8, "5-8"), (16, "9-16"), (32, "17-32")):
        if seed <= hi:
            return key
    return None


def structure_of(picks: list[tuple[str, str]]) -> tuple[int, ...]:
    c = Counter(b.lstrip("#") for _, b in picks)
    return tuple(c.get(k, 0) for k in BAND_KEYS)  # NF implied by remainder


class FieldModel:
    def __init__(
        self,
        names: list[str],                      # players in the draw (sim order)
        seeds: list[int | None],
        atp_ranks: list[int],
        banks: dict[str, ParticipantBank],     # per rival
        usage: dict[str, dict[str, int]],      # rival -> player -> times used
        popularity: dict[str, float],          # player -> weighted pick count
        history: dict | None,                  # rival -> tournament -> picks
        me: str,
        is_gs: bool,
        elos: list[float] | None = None,       # rivals also chase current form
        last_event: bool = False,              # quota is use-it-or-lose-it
    ):
        self.rivals = [p for p in banks if p != me]
        self.n_players = len(names)
        idx = {norm(n): i for i, n in enumerate(names)}

        self.band_members: dict[str, list[int]] = {k: [] for k in BAND_KEYS}
        self.nf_members: list[int] = []
        for i, s in enumerate(seeds):
            b = band_of_seed(s)
            if b:
                self.band_members[b].append(i)
            else:
                self.nf_members.append(i)

        pop = np.array([popularity.get(norm(n), 0.0) + 0.3 for n in names])
        # rivals aren't purely backward-looking: they also chase whoever is
        # strong RIGHT NOW (market news, current form)
        if elos is not None:
            e = np.array(elos)
            strength_prior = np.exp((e - e.max()) / 120.0)
            pop = pop + 25.0 * strength_prior
        rank_prior = np.array([1.0 / (1.0 + r / 40.0) for r in atp_ranks])
        self.base_w = (pop * rank_prior) ** CONCENTRATION

        self.rival_weights = []
        self.rival_quota = []
        self.rival_structs = []
        for rv in self.rivals:
            u = usage.get(rv, {})
            used = np.zeros(self.n_players)
            for player, cnt in u.items():
                j = idx.get(norm(player))
                if j is not None:
                    used[j] = cnt
            w = self.base_w * (1.0 + 0.7 * used)     # affinity: repeat picks
            w[used >= 5] = 0.0                        # player burned out
            bank = banks[rv]
            quota = bank.gs_quota if is_gs else bank.masters_quota
            self.rival_weights.append(w)
            self.rival_quota.append(quota)
            # historical band structures for this rival (fallback: standard).
            # At the LAST event of a quota pool (US Open for Slams, Paris for
            # Masters) unspent tokens expire, so rational rivals pick their
            # remaining bank, not their habit.
            if last_event:
                forced, left = [], 5
                for key in BAND_KEYS:
                    take = min(quota.get(key, 0), left)
                    forced.append(take)
                    left -= take
                self.rival_structs.append([tuple(forced)])
            else:
                structs = []
                if history and rv in history:
                    for picks in history[rv].values():
                        if len(picks) == 5:
                            structs.append(structure_of(picks))
                self.rival_structs.append(structs or [(1, 1, 1, 1)])

    def apply_ownership_floor(self, floors: dict[str, float],
                              names: list[str], iters: int = 6) -> list[str]:
        """Raise selection weights of named players (for every rival) until
        projected ownership reaches the floor. Multiplicative fixed-point:
        others in the band lose share naturally. Returns a log."""
        idx = {norm(n): i for i, n in enumerate(names)}
        log, targets = [], {}
        for p, f in floors.items():
            key = norm(p)
            if key.startswith(("qualifier", "lucky loser")):
                log.append(f"WARNING: floor on placeholder '{p}' rejected")
            elif key not in idx:
                log.append(f"WARNING: floor on '{p}' ignored — not in this draw")
            else:
                targets[idx[key]] = float(f)
        if not targets:
            return log
        before = self.expected_ownership(np.random.default_rng(101), rounds=20)
        # reachable ceiling: share of rivals who can pick him at all (token in
        # his band and not maxed). A floor above it is clamped, not chased.
        band_of = {i: k for k, members in self.band_members.items() for i in members}
        for j in list(targets):
            b = band_of.get(j)
            able = sum(1 for w, q in zip(self.rival_weights, self.rival_quota)
                       if w[j] > 0 and (b is None or q.get(b, 0) > 0))
            ceil = 0.95 * able / max(len(self.rivals), 1)
            if targets[j] > ceil:
                log.append(f"WARNING: {names[j]} floor {targets[j]:.0%} > reachable "
                           f"{ceil:.0%} — clamped")
                targets[j] = ceil
        # floors in one band can't sum past that band's projected pick volume
        for b, members in self.band_members.items():
            fl = [j for j in targets if j in members]
            cap = 0.9 * sum(before[i] for i in members)
            tot = sum(targets[j] for j in fl)
            if fl and tot > cap:
                log.append(f"WARNING: {b} floors sum {tot:.0%} > band volume "
                           f"{cap:.0%} — scaled down")
                for j in fl:
                    targets[j] *= cap / tot
        for it in range(iters):
            own = self.expected_ownership(np.random.default_rng(101 + it), rounds=20)
            moved = False
            for j, f in targets.items():
                if own[j] < f * 0.97:
                    fac = min(8.0, (f / max(own[j], 0.01)) ** 1.3)
                    for w in self.rival_weights:
                        w[j] *= fac
                    moved = True
            if not moved:
                break
        after = self.expected_ownership(np.random.default_rng(199), rounds=20)
        for j, f in targets.items():
            tag = "" if after[j] >= 0.9 * f else "  WARNING: floor not reached"
            log.append(f"{names[j]}: {before[j]:.0%} -> {after[j]:.0%} (floor {f:.0%}){tag}")
        return log

    def sample_scores(
        self, points: np.ndarray, rng: np.random.Generator, block: int = 250
    ) -> np.ndarray:
        """Rival total scores per sim: (n_rivals, n_sims).

        Pick sets are resampled every `block` sims (a rival's picks are fixed
        for the week; which set they chose is our uncertainty)."""
        n_sims = points.shape[1]
        out = np.empty((len(self.rivals), n_sims), dtype=np.int32)
        for r_i in range(len(self.rivals)):
            for s0 in range(0, n_sims, block):
                s1 = min(s0 + block, n_sims)
                picks = self.sample_set(r_i, rng)
                out[r_i, s0:s1] = points[picks, s0:s1].sum(axis=0)
        return out

    def sample_set(self, r_i: int, rng: np.random.Generator) -> list[int]:
        w = self.rival_weights[r_i]
        quota = self.rival_quota[r_i]
        structs = self.rival_structs[r_i]
        want = list(structs[int(rng.integers(len(structs)))])
        # clip the desired structure to what the quota bank still allows
        for k, key in enumerate(BAND_KEYS):
            want[k] = min(want[k], quota.get(key, 0))

        picks: list[int] = []
        for k, key in enumerate(BAND_KEYS):
            for _ in range(want[k]):
                cand = [i for i in self.band_members[key]
                        if w[i] > 0 and i not in picks]
                if cand:
                    picks.append(self._draw(cand, w, rng))
        while len(picks) < 5:
            cand = [i for i in self.nf_members if w[i] > 0 and i not in picks]
            if not cand:  # degenerate: allow any remaining player
                cand = [i for i in range(self.n_players) if i not in picks]
            picks.append(self._draw(cand, w, rng))
        return picks

    def expected_ownership(self, rng: np.random.Generator, rounds: int = 60):
        """Fraction of rivals projected to hold each player."""
        counts = np.zeros(self.n_players)
        for _ in range(rounds):
            for r_i in range(len(self.rivals)):
                for j in self.sample_set(r_i, rng):
                    counts[j] += 1
        return counts / (rounds * len(self.rivals))

    @staticmethod
    def _draw(cand: list[int], w: np.ndarray, rng: np.random.Generator) -> int:
        cw = w[cand]
        tot = cw.sum()
        if tot <= 0:
            return int(rng.choice(cand))
        return int(rng.choice(cand, p=cw / tot))

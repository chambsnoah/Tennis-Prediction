"""Post-mortem of the model's best and worst back-tested weeks.

For each requested tournament:
  - the model's #1 recommended set with each player's ACTUAL result
  - the actual weekly podium (who won the money and with what)
  - the hindsight-optimal set under Noah's quota bank at the time
  - chaos metrics (how predictable was the week at all)
"""

import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings
warnings.filterwarnings("ignore")

from itertools import combinations, product

from pool.parsers import load_draw, load_pick_history, norm
from pool.results import score_tournament
from run_analysis import (
    ME, kind_of, run_pipeline, slice_history, usage_and_quota_from_history,
)
from tests.test_scoring import DATA, FILES

BAND_KEYS = ("1-4", "5-8", "9-16", "17-32")


def band_of(seed):
    if seed is None:
        return "NF"
    for hi, key in ((4, "1-4"), (8, "5-8"), (16, "9-16"), (32, "17-32")):
        if seed <= hi:
            return key
    return "NF"


def hindsight_best(outcomes, quota, my_usage):
    """Max actual points achievable under Noah's bank at that time."""
    by_band = {k: [] for k in list(BAND_KEYS) + ["NF"]}
    for name, o in outcomes.items():
        if my_usage.get(name, 0) >= 5:
            continue
        by_band[band_of(o.entry.seed)].append((o.result.total, name))
    for k in by_band:
        by_band[k].sort(reverse=True)

    caps = [min(quota.get(k, 0), 4, len(by_band[k])) for k in BAND_KEYS]
    best = (-1, None, None)
    for counts in product(*(range(c + 1) for c in caps)):
        n_nf = 5 - sum(counts)
        if not 0 <= n_nf <= len(by_band["NF"]):
            continue
        total, picks = 0, []
        for j, k in enumerate(BAND_KEYS):
            for pts, name in by_band[k][: counts[j]]:
                total += pts
                picks.append((name, k, pts))
        for pts, name in by_band["NF"][:n_nf]:
            total += pts
            picks.append((name, "NF", pts))
        if total > best[0]:
            struct = "/".join(map(str, counts)) + f"/{n_nf}"
            best = (total, picks, struct)
    return best


def chaos_metrics(outcomes, kind):
    """How predictable was the tournament?"""
    seeded = [(o.entry.seed, o.result.total) for o in outcomes.values()
              if o.entry.seed is not None]
    ranks = np.array([o.entry.atp_rank for o in outcomes.values()])
    pts = np.array([o.result.total for o in outcomes.values()])
    # spearman: correlation between rank order and points order
    r1 = np.argsort(np.argsort(ranks))
    r2 = np.argsort(np.argsort(-pts))
    rho = float(np.corrcoef(r1, r2)[0, 1])
    champ = next(o for o in outcomes.values() if o.lost_in_round is None)
    n_r = max(o.lost_in_round or 99 for o in outcomes.values()
              if o.lost_in_round)
    semi = [o for o in outcomes.values()
            if o.lost_in_round is None or o.lost_in_round >= n_r - 1]
    top8_in_sf = sum(1 for o in semi if (o.entry.seed or 99) <= 8)
    return rho, champ.entry.seed, top8_in_sf


def postmortem(tournament):
    fname = FILES[tournament]
    path = str(DATA / fname)
    draw = load_draw(path)
    kind = kind_of(tournament)
    history = load_pick_history(path)
    usage, banks = usage_and_quota_from_history(history, tournament)
    history_before = slice_history(history, tournament)

    names, points, rival_scores, ranked, model, field = run_pipeline(
        draw.entries, kind, tournament, 12000, exclude_event=tournament,
        usage=usage, banks=banks, history=history_before, quiet=True)

    outcomes = score_tournament(draw, kind)
    actual_pts = {n: o.result.total for n, o in outcomes.items()}
    actual_scores = {}
    for who, ts in history.items():
        picks = ts.get(tournament, [])
        if picks:
            actual_scores[who] = sum(actual_pts.get(norm(p), 0) for p, _ in picks)
    podium = sorted(actual_scores.items(), key=lambda kv: -kv[1])[:3]

    rho, champ_seed, top8_sf = chaos_metrics(outcomes, kind)
    print(f"\n{'='*74}\n{tournament.upper()}  "
          f"(rank-vs-points corr {rho:.2f} | champion seed "
          f"{champ_seed or 'unseeded'} | top-8 seeds in SF: {top8_sf}/4)")

    r = ranked[0]
    total = 0
    print("model #1 sheet (chosen on the eve, no hindsight):")
    for j in r.players:
        n = norm(names[j])
        o = outcomes.get(n)
        pts = o.result.total if o else 0
        total += pts
        seed = o.entry.seed if o else None
        lost = "CHAMPION" if o and o.lost_in_round is None else \
            f"out R{o.lost_in_round}" if o else "n/a"
        print(f"   {names[j]:22s} [{band_of(seed):5s}] "
              f"{o.result.atp if o else 0:3d} atp + {o.result.bonus if o else 0:3d} boni = "
              f"{pts:3d}   {lost}")
    week_rank = 1 + sum(v > total for v in actual_scores.values())
    print(f"   TOTAL {total}  -> weekly rank {week_rank}"
          f"  (model estimated P(top3) {r.p_top3:.0%})")

    print("actual podium:")
    for who, sc in podium:
        picks = history[who][tournament]
        det = ", ".join(f"{p} {actual_pts.get(norm(p), 0)}" for p, _ in picks)
        print(f"   {sc:4d} {who:24s} {det}")

    my_usage = {norm(p): c for p, c in usage[ME].items()}
    quota = banks[ME].gs_quota if kind == "gs" else banks[ME].masters_quota
    best_total, best_picks, struct = hindsight_best(outcomes, quota, my_usage)
    det = ", ".join(f"{outcomes[n].entry.name} {p}" for n, b, p in best_picks)
    print(f"hindsight-optimal under my bank ({struct}): {best_total} pts")
    print(f"   {det}")


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "Australie", "Wimbledon", "Monte Carlo",       # the wins
        "Montréal", "Cincinnati", "Rome",              # the flops
    ]
    for t in targets:
        postmortem(t)

"""Fit the rival field model's herding parameters to the pool's REAL
ownership, week by week.

Each completed week is rebuilt as of its eve (same path as backtests: that
week's rankings, only earlier results, banks/usage/history reconstructed
from earlier picks, no live overrides), then the FieldModel's projected
ownership is compared with the share of submitted sheets that actually
held each player. This calibrates a measurement model of the pool's
behaviour; it does not look at match results or pick-set outcomes.

  .venv/bin/python tests/ownership_fit.py            # grid + leave-one-week-out
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings
warnings.filterwarnings("ignore")

import numpy as np

import pool.opponents as OPP
from pool.parsers import GRAND_SLAMS, load_draw, load_pick_history, norm
from pool.strength import SEASON, build_model
from run_analysis import (DATA, ME, season_popularity, slice_history,
                          usage_and_quota_from_history)

LATEST = DATA / SEASON[-1][1]
# (concentration, strength weight, strength temperature in Elo)
GRID = [(c, w, t) for c in (0.8, 1.0, 1.35) for w in (25.0, 200.0, 600.0, 2000.0)
        for t in (30.0, 60.0, 120.0)]
CURRENT = (1.35, 25.0, 120.0)
ROUNDS = 12


def week_inputs():
    """Per completed week: FieldModel constructor args + actual ownership."""
    history = load_pick_history(str(LATEST))
    weeks = []
    for t, fname, _ in SEASON:
        held = [p for who, ts in history.items() for p, _ in ts.get(t, [])]
        n = sum(1 for ts in history.values() if ts.get(t))
        if not n:
            continue
        draw = load_draw(str(DATA / fname))
        players = [e for e in draw.entries if not e.is_bye]
        names = [e.name for e in players]
        model = build_model(DATA, target_surface="hard", upto=t)
        usage, banks = usage_and_quota_from_history(history, t)
        before = slice_history(history, t)
        actual = Counter(norm(p) for p in held)
        weeks.append(dict(
            t=t, names=names,
            args=(names, [e.seed for e in players], [e.atp_rank for e in players],
                  banks, usage, season_popularity(before), before, ME, t in GRAND_SLAMS),
            kw=dict(elos=[model.elo(x) for x in names],
                    last_event=t in ("US Open", "Paris")),
            actual=np.array([actual.get(norm(x), 0) / n for x in names])))
    return weeks


def projected(week, conc, weight, temp=120.0, seed=7):
    OPP.CONCENTRATION, OPP.STRENGTH_WEIGHT, OPP.STRENGTH_TEMP = conc, weight, temp
    field = OPP.FieldModel(*week["args"], **week["kw"])
    return field.expected_ownership(np.random.default_rng(seed), rounds=ROUNDS)


def main():
    weeks = week_inputs()
    print(f"{len(weeks)} weeks: {', '.join(w['t'] for w in weeks)}")
    combos = GRID
    # err[combo][week] = squared error of that week's projection; top5 likewise
    err, top5 = {}, {}
    for k in combos:
        err[k], top5[k] = [], []
        for w in weeks:
            p = projected(w, *k)
            err[k].append(float(((p - w["actual"]) ** 2).sum()))
            idx = np.argsort(-w["actual"])[:5]   # the names that decide sheets
            top5[k].append(float(np.abs(p[idx] - w["actual"][idx]).mean()))
        pass
    cur = CURRENT
    for k in sorted(combos, key=lambda k: np.mean(err[k]))[:6]:
        print(f"  {k}: SSE/week {np.mean(err[k]):.4f}, top-5 MAE {np.mean(top5[k]):.3f}")
    best = min(combos, key=lambda k: np.mean(err[k]))
    for lbl, k in (("current", cur), ("best", best)):
        print(f"{lbl:8s}{k}: SSE/week {np.mean(err[k]):.4f}, top-5 MAE {np.mean(top5[k]):.3f}")

    # leave-one-week-out: fit on 11 weeks, score the held-out one
    wins = 0
    for i, w in enumerate(weeks):
        fit = min(combos, key=lambda k: sum(e for j, e in enumerate(err[k]) if j != i))
        wins += err[fit][i] < err[cur][i]
        print(f"  held out {w['t']:14s} fit {fit}  SSE {err[fit][i]:.4f} vs current {err[cur][i]:.4f}")
    print(f"leave-one-out: fitted setting beat current on {wins}/{len(weeks)} held-out weeks")

    print("\nmost-owned players, projected (best) / projected (current) / actual:")
    for w in weeks[-4:]:
        pb, pc = projected(w, *best), projected(w, *cur)
        idx = np.argsort(-w["actual"])[:6]
        print(f"  {w['t']:14s} " + ", ".join(
            f"{w['names'][j]} {pb[j]:.0%}/{pc[j]:.0%}/{w['actual'][j]:.0%}" for j in idx))


if __name__ == "__main__":
    main()

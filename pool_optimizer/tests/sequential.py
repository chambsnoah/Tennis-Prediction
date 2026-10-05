"""True sequential season backtest: the model plays all 10 weeks in order,
consuming its OWN quota bank and player-usage counts (greedy weekly
optimization, exactly what a live season would have done)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings
warnings.filterwarnings("ignore")

from pool.parsers import GRAND_SLAMS, ParticipantBank, load_draw, load_pick_history, norm
from pool.results import score_tournament
from run_analysis import (
    ME, kind_of, run_pipeline, slice_history, usage_and_quota_from_history,
)
from tests.test_scoring import DATA, FILES
from pool.opponents import band_of_seed


import math

from pool.strength import EVENT_CLASS

GS_EVENTS = [t for t in FILES if t in GRAND_SLAMS]


def ration(remaining: dict, rem_events: int, rem_chalk: int,
           event_class: str) -> dict:
    """Season token budgeting: this week's allowed spend per band.

    Top bands (1-4/5-8) are only spendable at chalk events, so their fair
    share and their reservation are computed against remaining CHALK events
    (rem_chalk includes the current event when it is chalk). Lower bands
    spread over all remaining events, with variance events allowed +1."""
    out = {}
    for band, rem in remaining.items():
        if band in ("1-4", "5-8"):
            if event_class != "chalk":
                out[band] = 0
                continue
            spendable = max(rem_chalk, 1)
            base = math.ceil(rem / spendable)
            # up to fair share + 1, but always leave one per future chalk event
            cap = min(base + 1, rem - (spendable - 1))
        else:
            base = math.ceil(rem / max(rem_events, 1))
            cap = base + (1 if event_class != "chalk" else 0)
        out[band] = max(0, min(rem, cap))
    return out


def main(sims=10000, budgeted=True):
    gs = {"1-4": 4, "5-8": 4, "9-16": 4, "17-32": 4}
    ms = {"1-4": 9, "5-8": 9, "9-16": 9, "17-32": 7}
    my_usage: dict[str, int] = {}

    total = 0
    weekly_cash = 0
    cum_others = None
    rows = []
    for tournament, fname in FILES.items():
        path = str(DATA / fname)
        draw = load_draw(path)
        kind = kind_of(tournament)
        history = load_pick_history(path)
        usage, banks = usage_and_quota_from_history(history, tournament)
        # replace my state with the model's own trajectory; under the
        # budgeted policy the weekly optimizer only sees this week's ration
        gs_q, ms_q = dict(gs), dict(ms)
        if budgeted:
            done = list(FILES).index(tournament)
            future_all = list(FILES)[done:] + ["US Open", "Shanghai", "Paris"]
            gs_events = [t for t in future_all if t in GRAND_SLAMS]
            ms_events = [t for t in future_all if t not in GRAND_SLAMS]
            cls = EVENT_CLASS.get(tournament, "chalk")
            if tournament in GRAND_SLAMS:
                chalk_n = sum(1 for t in gs_events
                              if EVENT_CLASS.get(t, "chalk") == "chalk")
                gs_q = ration(gs, len(gs_events), chalk_n, cls)
            else:
                chalk_n = sum(1 for t in ms_events
                              if EVENT_CLASS.get(t, "chalk") == "chalk")
                ms_q = ration(ms, len(ms_events), chalk_n, cls)
        usage[ME] = dict(my_usage)
        banks[ME] = ParticipantBank(
            ME, gs_q, ms_q,
            [p for p, c in my_usage.items() if c >= 5])
        hb = slice_history(history, tournament)

        names, points, rival_scores, (ranked, ranked_contra), model, field = run_pipeline(
            draw.entries, kind, tournament, sims, exclude_event=tournament,
            usage=usage, banks=banks, history=hb, quiet=True)
        seeds = [e.seed for e in draw.entries if not e.is_bye]

        cls = EVENT_CLASS.get(tournament, "chalk")
        pick = ranked[0] if cls == "chalk" else ranked_contra[0]
        outcomes = score_tournament(draw, kind)
        actual_pts = {n: o.result.total for n, o in outcomes.items()}
        score = sum(actual_pts.get(norm(names[j]), 0) for j in pick.players)

        # consume the bank
        quota = gs if tournament in GRAND_SLAMS else ms
        picked = []
        for j in pick.players:
            b = band_of_seed(seeds[j])
            if b:
                quota[b] -= 1
                assert quota[b] >= 0, f"quota violation {b} at {tournament}"
            my_usage[norm(names[j])] = my_usage.get(norm(names[j]), 0) + 1
            assert my_usage[norm(names[j])] <= 5
            picked.append(f"{names[j]}{'[' + b + ']' if b else '[NF]'}")

        # weekly rank vs the real field
        field_scores = {}
        for who, ts in history.items():
            if who == ME:
                continue
            picks = ts.get(tournament, [])
            if picks:
                field_scores[who] = sum(
                    actual_pts.get(norm(p), 0) for p, _ in picks)
        rank = 1 + sum(1 for v in field_scores.values() if v > score)
        prize = {1: 70, 2: 35, 3: 20}.get(rank, 0)
        weekly_cash += prize
        total += score
        rows.append((tournament, score, rank, prize, picked))
        print(f"{tournament:15s} {score:3d} pts  weekly rank {rank:2d} "
              f"{'$' + str(prize) if prize else '':>4s}  {', '.join(picked)}")
        print(f"{'':15s} bank: GS {gs}  M {ms}")

    print(f"\nSEASON: {total} pts + 250 Excel bonus = {total + 250}")
    print(f"weekly cash: ${weekly_cash}")
    from pool.parsers import load_standings
    st = load_standings(str(DATA / FILES['Cincinnati']))
    finals = {w: st[w]["total"] for w in st if w != ME}
    r = 1 + sum(1 for v in finals.values() if v > total + 250)
    print(f"overall rank after Cincinnati: #{r} of 77 "
          f"(leader {max(finals.values())})")


if __name__ == "__main__":
    main()

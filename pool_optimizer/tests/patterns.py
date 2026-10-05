"""Test two hypotheses on the season's data:

1. Champion fatigue: does the previous event's champion/finalist
   underperform at the NEXT event (especially back-to-back weeks)?
2. Post-upset regression: after beating a much better-rated player, does
   the winner underperform Elo expectation in his NEXT match?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings
warnings.filterwarnings("ignore")

from pool.parsers import GRAND_SLAMS, load_draw, load_rankings, norm
from pool.results import match_log, score_tournament
from pool.strength import build_model, win_prob
from run_analysis import kind_of
from tests.test_scoring import DATA, FILES

# calendar gap in weeks between consecutive pool events (2026 dates)
GAPS = {  # event -> weeks since previous pool event
    "Indian Wells": 7, "Miami": 2, "Monte Carlo": 3, "Madrid": 2,
    "Rome": 2, "Roland-Garros": 3, "Wimbledon": 5, "Montréal": 5,
    "Cincinnati": 2,
}


def champion_fatigue():
    events = list(FILES.items())
    print("=== previous champion / finalist at the NEXT event ===")
    rows = []
    for k in range(1, len(events)):
        prev_t, prev_f = events[k - 1]
        cur_t, cur_f = events[k]
        prev_out = score_tournament(load_draw(str(DATA / prev_f)), kind_of(prev_t))
        cur_out = score_tournament(load_draw(str(DATA / cur_f)), kind_of(cur_t))
        n_rounds = max(o.lost_in_round or 0 for o in cur_out.values())
        n_prev = max(o.lost_in_round or 0 for o in prev_out.values())
        champ = next(o for o in prev_out.values() if o.lost_in_round is None)
        runner = next(o for o in prev_out.values() if o.lost_in_round == n_prev)
        for role, o in (("champ", champ), ("finalist", runner)):
            nxt = cur_out.get(norm(o.entry.name))
            if nxt is None:
                res = "skipped"
                rows.append((cur_t, role, o.entry.name, None, GAPS[cur_t]))
            else:
                lr = nxt.lost_in_round
                res = "WON" if lr is None else f"out R{lr}/{n_rounds}"
                rows.append((cur_t, role, o.entry.name, lr or 99, GAPS[cur_t]))
            print(f"  {prev_t:13s}->{cur_t:13s} {role:8s} "
                  f"{o.entry.name:18s} gap {GAPS[cur_t]}w  {res}")
    # back-to-back (gap<=2) vs rested
    for label, cond in (("gap<=2wk", lambda g: g <= 2), ("gap>2wk", lambda g: g > 2)):
        sub = [r for r in rows if r[3] is not None and cond(r[4])]
        early = sum(1 for r in sub if r[3] <= 3)
        print(f"  {label}: {len(sub)} appearances, "
              f"out by R3 in {early} ({early / max(len(sub), 1):.0%})")


def post_upset():
    print("\n=== next match after an upset win (Elo diff >= 100) ===")
    n_up = w_up = 0
    exp_up = 0.0
    n_norm = w_norm = 0
    exp_norm = 0.0
    for t, f in FILES.items():
        path = str(DATA / f)
        model = build_model(DATA, upto=t)   # eve-of-event ratings, no leakage
        draw = load_draw(path)
        log = sorted(match_log(draw))       # (round, winner, loser)
        # index matches by player and round
        by_round = {}
        for rnd, w, l in log:
            by_round.setdefault(w, {})[rnd] = ("W", l)
            by_round.setdefault(l, {})[rnd] = ("L", w)
        bo5 = t in GRAND_SLAMS
        for rnd, w, l in log:
            diff = model.elo(w) - model.elo(l)
            upset = diff <= -100.0
            # the winner's next match
            nxt = by_round.get(w, {}).get(rnd + 1)
            if nxt is None:
                continue
            res, opp = nxt
            p = win_prob(model.elo(w), model.elo(opp), bo5)
            if upset:
                n_up += 1
                w_up += (res == "W")
                exp_up += p
            else:
                n_norm += 1
                w_norm += (res == "W")
                exp_norm += p
    print(f"  after UPSET win:  {n_up} matches, won {w_up} "
          f"({w_up / n_up:.0%}) vs Elo-expected {exp_up / n_up:.0%}")
    print(f"  after normal win: {n_norm} matches, won {w_norm} "
          f"({w_norm / n_norm:.0%}) vs Elo-expected {exp_norm / n_norm:.0%}")


def deep_run_fatigue():
    """All matches played by someone who reached SF+ at the PREVIOUS event:
    actual vs Elo-expected win rate, split by rest weeks."""
    print("\n=== matches by previous-event deep runners (SF or better) ===")
    events = list(FILES.items())
    buckets = {"gap<=2wk": [0, 0, 0.0], "gap>2wk": [0, 0, 0.0]}
    for k in range(1, len(events)):
        prev_t, prev_f = events[k - 1]
        cur_t, cur_f = events[k]
        prev_out = score_tournament(load_draw(str(DATA / prev_f)), kind_of(prev_t))
        n_prev = max(o.lost_in_round or 0 for o in prev_out.values())
        deep = {n for n, o in prev_out.items()
                if o.lost_in_round is None or o.lost_in_round >= n_prev - 1}
        model = build_model(DATA, upto=cur_t)
        draw = load_draw(str(DATA / cur_f))
        bo5 = cur_t in GRAND_SLAMS
        key = "gap<=2wk" if GAPS[cur_t] <= 2 else "gap>2wk"
        for rnd, w, l in match_log(draw):
            for player, opp, won in ((w, l, 1), (l, w, 0)):
                if player in deep:
                    b = buckets[key]
                    b[0] += 1
                    b[1] += won
                    b[2] += win_prob(model.elo(player), model.elo(opp), bo5)
    for key, (n, w, exp) in buckets.items():
        if n:
            print(f"  {key}: {n} matches, won {w / n:.0%} "
                  f"vs Elo-expected {exp / n:.0%}  "
                  f"(edge {100 * (w / n - exp / n):+.0f} pp)")


if __name__ == "__main__":
    champion_fatigue()
    deep_run_fatigue()
    post_upset()

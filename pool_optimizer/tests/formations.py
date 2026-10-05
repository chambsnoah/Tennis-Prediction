"""What do winning pick sets actually look like?

For every completed tournament: score every participant's actual set, then
dissect the top-3 sets — band structure, crowd overlap of each pick, where
the points came from — and contrast with the median pooler.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pool.parsers import (
    GRAND_SLAMS, MASTERS_6R, load_draw, load_pick_history, norm,
)
from pool.results import score_tournament
from tests.test_scoring import FILES, DATA

ME = "Noah Chamberland"


def week(tournament, fname):
    path = str(DATA / fname)
    draw = load_draw(path)
    kind = "gs" if tournament in GRAND_SLAMS else (
        "m6" if tournament in MASTERS_6R else "m7")
    outcomes = score_tournament(draw, kind)
    pts = {n: o.result.total for n, o in outcomes.items()}
    champion = next(n for n, o in outcomes.items() if o.lost_in_round is None)

    history = load_pick_history(path)
    sets = {}
    for who, ts in history.items():
        picks = ts.get(tournament, [])
        if len(picks) == 5:
            sets[who] = picks

    # field popularity of each player this week
    held = Counter()
    for picks in sets.values():
        for p, _ in picks:
            held[norm(p)] += 1
    n_poolers = len(sets)

    scores = {
        who: sum(pts.get(norm(p), 0) for p, _ in picks)
        for who, picks in sets.items()
    }
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return draw, pts, sets, held, n_poolers, ranked, champion


def band_shape(picks):
    c = Counter(b.lstrip("#") for _, b in picks)
    return "/".join(str(c.get(k, 0)) for k in ("1-4", "5-8", "9-16", "17-32", "NF"))


def main():
    shape_counter = Counter()
    top3_shape_counter = Counter()
    winner_low_pop = []       # picks held by <15% of field among winners
    winner_top_player_share = []
    champion_held = 0

    for t, f in FILES.items():
        draw, pts, sets, held, n, ranked, champ = week(t, f)
        print(f"\n=== {t} ({n} poolers, champion: {champ}) ===")
        for who, score in ranked[:3]:
            picks = sets[who]
            shape = band_shape(picks)
            top3_shape_counter[shape] += 1
            detail = []
            for p, b in picks:
                pp = pts.get(norm(p), 0)
                pop = held[norm(p)] / n
                detail.append(f"{p}[{b}] {pp}pts {pop:.0%}held")
            best = max(pts.get(norm(p), 0) for p, _ in picks)
            share = best / score if score else 0
            print(f"  {score:4d} {who:24s} {shape}  " + " | ".join(detail))
            if who == ranked[0][0]:
                winner_top_player_share.append(share)
                winner_low_pop.append(
                    sum(1 for p, _ in picks if held[norm(p)] / n < 0.15))
                if any(norm(p) == champ for p, _ in picks):
                    champion_held += 1
        for who, picks in sets.items():
            shape_counter[band_shape(picks)] += 1
        me = scores_row = next(((w, s) for w, s in ranked if w == ME), None)
        if me:
            r = 1 + sum(1 for _, s in ranked if s > me[1])
            print(f"  (me: {me[1]} pts, rank {r}, shape {band_shape(sets[ME])})")

    print("\n=== structures overall (all poolers, all weeks) ===")
    for shape, cnt in shape_counter.most_common(8):
        print(f"  {shape}: {cnt}")
    print("=== structures among weekly top-3 ===")
    for shape, cnt in top3_shape_counter.most_common(10):
        print(f"  {shape}: {cnt}")
    print(f"\nweekly winners holding the actual champion: {champion_held}/10")
    print("winner's best-player share of set score:",
          ", ".join(f"{s:.0%}" for s in winner_top_player_share))
    print("winner's picks held by <15% of field:", winner_low_pop)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Pool pick optimizer CLI.

  analyze   data/"11 - US Open.xlsm" --tournament "US Open"
            full pipeline on a workbook whose Draw sheet is filled
  analyze   --draw-json data/shanghai_draw_2026.json --tournament Shanghai
            same, from the commissioner's draw PDF transcribed to JSON
            (--quota 1,1,1,2 caps this week's band spend, e.g. to reserve
            tokens for a later event)
  preview   --tournament "US Open"
            placeholder analysis before the draw is out (random draws
            with proper seed placement, entrants = current top rankings)
  backtest  --tournament Cincinnati
            rerun the pipeline as of the eve of a completed tournament and
            compare recommendations with what actually happened
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

from pool.opponents import FieldModel, band_of_seed
from pool.parsers import (
    GRAND_SLAMS, MASTERS_6R, DrawEntry, load_banques, load_draw,
    load_pick_history, load_player_usage, load_rankings, norm,
)
from pool.optimize import enumerate_sets, evaluate, filter_contrarian, rival_threshold
from pool.results import score_tournament
from pool.simulate import simulate
from pool.strength import SEASON, StrengthModel, build_model, load_withdrawals

DATA = Path(__file__).resolve().parent / "data"
REPORTS = Path(__file__).resolve().parent / "reports"
SUMMARY_XLSX = DATA / "ChoixTournois_2026.xlsx"
# per-event entry forms carry the up-to-date bank + usage for that event
EVENT_FORMS = {"Shanghai": DATA / "ChoixShanghai.xlsx"}
LATEST_EVENT = "US Open"  # most recent workbook WITH results in data/
ME = "Noah Chamberland"


def summary_file(tournament: str | None) -> Path:
    form = EVENT_FORMS.get(tournament)
    if form is not None and not form.exists():
        print(f"WARNING: {form.name} missing — falling back to the season "
              f"summary (stale usage/banks)", file=sys.stderr)
    return form if form is not None and form.exists() else SUMMARY_XLSX

# 32-seed anchor slots in a 128 draw (1-based), by seed group
SEED_SLOTS_128 = {
    (1,): [1], (2,): [128],
    (3, 4): [33, 96],
    (5, 6, 7, 8): [32, 64, 65, 97],
    (9, 10, 11, 12, 13, 14, 15, 16): [16, 17, 48, 49, 80, 81, 112, 113],
    tuple(range(17, 33)): [8, 9, 24, 25, 40, 41, 56, 57,
                           72, 73, 88, 89, 104, 105, 120, 121],
}


def kind_of(tournament: str) -> str:
    if tournament in GRAND_SLAMS:
        return "gs"
    return "m6" if tournament in MASTERS_6R else "m7"


def tournament_file(tournament: str) -> Path | None:
    for t, fname, _ in SEASON:
        if t == tournament:
            return DATA / fname
    return None


def placeholder_draw(rankings: dict[str, int], withdrawals: set[str],
                     rng: np.random.Generator, n_players: int = 128,
                     seed_order: list[str] | None = None) -> list[DrawEntry]:
    """Random draw with correct Slam seed placement. Entrants by ranking,
    unless a projected `seed_order` (top-32 names, in seed order) is given —
    rankings sheets go stale between events, seeds don't lie."""
    entrants = [(name, rank) for name, rank in
                sorted(rankings.items(), key=lambda kv: kv[1])
                if name not in withdrawals][:n_players]
    if seed_order:
        seeded_names = [norm(n) for n in seed_order[:32]]
        rest = [(n, r) for n, r in entrants if n not in seeded_names]
        entrants = [(norm(n), rankings.get(norm(n), 40)) for n in seed_order[:32]]
        entrants += rest[: n_players - 32]
    slots: list[DrawEntry | None] = [None] * n_players
    seeded, unseeded = entrants[:32], entrants[32:]
    for group, anchor_slots in SEED_SLOTS_128.items():
        anchors = list(anchor_slots)
        rng.shuffle(anchors)
        for seed_no, slot in zip(group, anchors):
            name, rank = entrants[seed_no - 1]
            slots[slot - 1] = DrawEntry(slot, name, rank, seed_no)
    open_slots = [i for i in range(n_players) if slots[i] is None]
    rng.shuffle(open_slots)
    for (name, rank), i in zip(unseeded, open_slots):
        slots[i] = DrawEntry(i + 1, name, rank, None)
    return slots


def slice_history(history, upto: str | None):
    """Drop tournaments from `upto` onward (no leakage in backtests)."""
    if upto is None:
        return history
    from pool.parsers import TOURNAMENTS
    keep = set(TOURNAMENTS[: TOURNAMENTS.index(upto)])
    return {
        who: {t: picks for t, picks in ts.items() if t in keep}
        for who, ts in history.items()
    }


def season_popularity(history) -> dict[str, float]:
    """Recency-weighted count of how often the field picked each player.
    Recency is anchored to the latest week PRESENT in the history (so a
    sliced backtest history weighs last week's picks like a live run would)."""
    from pool.parsers import TOURNAMENTS
    latest = max(
        (TOURNAMENTS.index(t)
         for ts in history.values() for t, picks in ts.items() if picks),
        default=0)
    pop: dict[str, float] = {}
    for tournaments in history.values():
        for t, picks in tournaments.items():
            age = latest - TOURNAMENTS.index(t)
            w = 0.5 ** (age / 4.0)
            for player, _ in picks:
                pop[norm(player)] = pop.get(norm(player), 0.0) + w
    return pop


def usage_and_quota_from_history(history, upto: str):
    """Reconstruct usage counts and remaining band quotas as of the eve of
    `upto` (exclusive), for back-testing."""
    from pool.parsers import TOURNAMENTS, ParticipantBank
    order = TOURNAMENTS[: TOURNAMENTS.index(upto)]
    usage: dict[str, dict[str, int]] = {}
    banks: dict[str, ParticipantBank] = {}
    for who, tournaments in history.items():
        u: dict[str, int] = {}
        gs = {b: 4 for b in ("1-4", "5-8", "9-16", "17-32")}
        ms = {"1-4": 9, "5-8": 9, "9-16": 9, "17-32": 7}
        for t in order:
            for player, band in tournaments.get(t, []):
                u[player] = u.get(player, 0) + 1
                key = band.lstrip("#")
                if key in gs:
                    if t in GRAND_SLAMS:
                        gs[key] -= 1
                    else:
                        ms[key] -= 1
        usage[who] = u
        banks[who] = ParticipantBank(who, gs, ms, [p for p, c in u.items() if c >= 5])
    return usage, banks


def run_pipeline(entries, kind, tournament, n_sims, exclude_event=None,
                 usage=None, banks=None, history=None, quiet=False,
                 quota_cap=None):
    """history, usage, banks must already be sliced to the eve of the
    tournament when back-testing (see cmd_backtest)."""
    # exclude_event: backtest mode — anchor on that event's own start-of-event
    # rankings, use only earlier events for form, ignore today's overrides
    anchor = None if exclude_event else {
        e.name: e.atp_rank for e in entries if not e.is_bye}
    model = build_model(DATA, target_surface="hard", upto=exclude_event,
                        anchor_ranks=anchor)

    from pool.strength import (EVENT_CLASS, UPSET_FACTOR, load_h2h,
                               load_injury_risk)
    uf = UPSET_FACTOR[EVENT_CLASS.get(tournament, "chalk")]
    # injury flags and h2h tilts describe TODAY's knowledge — never backtests
    inj = {} if exclude_event else load_injury_risk(DATA)
    h2h = [] if exclude_event else load_h2h(DATA)
    names, points = simulate(entries, model, kind, n_sims=n_sims,
                             upset_factor=uf, injury_risk=inj, h2h=h2h)
    seeds = [e.seed for e in entries if not e.is_bye]
    ranks = [e.atp_rank for e in entries if not e.is_bye]

    if history is None:
        latest = tournament_file(LATEST_EVENT)
        history = load_pick_history(str(latest))
    if usage is None:
        usage = load_player_usage(str(summary_file(tournament)))
    if banks is None:
        banks = load_banques(str(summary_file(tournament)))

    pop = season_popularity(history)
    last_event = tournament in ("US Open", "Paris")  # quota pool ends here
    field = FieldModel(names, seeds, ranks, banks, usage, pop, history,
                       ME, kind == "gs",
                       elos=[model.elo(n) for n in names],
                       last_event=last_event)
    # the contrarian filter's thresholds live on the RAW ownership scale
    # (see filter_contrarian), so project it before any floor is applied
    ownership = field.expected_ownership(np.random.default_rng(19), rounds=30)
    if not exclude_event:  # today's knowledge only — never in backtests
        from pool.strength import load_ownership_floor
        floors = load_ownership_floor(DATA)
        if floors:
            log = field.apply_ownership_floor(floors, names)
            if not quiet:
                for line in log:
                    print("ownership floor:", line)
    rng = np.random.default_rng(11)
    rival_scores = field.sample_scores(points, rng)

    my_bank = banks[ME]
    quota = dict(my_bank.gs_quota if kind == "gs" else my_bank.masters_quota)
    if quota_cap:
        for k, cap in quota_cap.items():
            quota[k] = min(quota.get(k, 0), cap)
        if not quiet:
            print(f"quota capped for this week: {quota}")
    my_usage = {norm(p): c for p, c in usage[ME].items()}
    sets = enumerate_sets(names, seeds, quota, my_usage, points)
    contra_sets = filter_contrarian(sets, ownership)
    if not quiet:
        print(f"{len(sets)} candidate pick sets ({len(contra_sets)} contrarian), "
              f"{points.shape[1]} sims, {len(field.rivals)} rivals")
    ranked = evaluate(sets, points, rival_scores)
    ranked_contra = evaluate(contra_sets, points, rival_scores)
    return names, points, rival_scores, (ranked, ranked_contra), model, field


def suggest_alternates(names, seeds, points, rival_scores, pick, usage_me):
    """Optimal alternate per pick. An alternate activates only if its primary
    withdraws BEFORE round 1 (rule 6) and must fit the same quota band, so
    the best alternate maximizes the SET's P(top-3) with that one player
    swapped out — computed on the full simulation, not just player EV."""
    t3 = rival_threshold(rival_scores, 3)
    base = list(pick.players)
    out = []
    for j in pick.players:
        b = band_of_seed(seeds[j])
        cands = [i for i in range(len(names))
                 if i not in pick.players and band_of_seed(seeds[i]) == b
                 and usage_me.get(norm(names[i]), 0) < 5
                 and not norm(names[i]).startswith(("qualifier", "lucky loser"))]
        best, best_p3 = None, -1.0
        rest = [k for k in base if k != j]
        rest_pts = points[rest, :].sum(axis=0)
        for i in cands:
            p3 = float(((rest_pts + points[i]) >= t3).mean())
            if p3 > best_p3:
                best, best_p3 = i, p3
        if best is not None:
            out.append(f"{names[j]:20s} -> {names[best]:20s} "
                       f"(set keeps P(top3) {best_p3:.1%})")
    return out


def describe_sets(names, seeds, points, rival_scores, ranked, usage_me,
                  top=12, field=None):
    t3 = rival_threshold(rival_scores, 3)
    own = None
    if field is not None:
        own = field.expected_ownership(np.random.default_rng(23), rounds=40)
    lines = []
    lines.append(f"median weekly threshold to reach top-3: {np.median(t3):.0f} pts\n")
    for i, r in enumerate(ranked[:top], 1):
        detail = []
        for j in r.players:
            seed = seeds[j]
            tag = f"#{seed}" if seed else "NF"
            ev_j = points[j].mean()
            used = usage_me.get(norm(names[j]), 0)
            extra = f", {own[j]:.0%} field" if own is not None else ""
            detail.append(f"{names[j]} ({tag}, ev {ev_j:.0f}, "
                          f"used {used}x{extra})")
        lines.append(
            f"{i:2}. P(top3)={r.p_top3:5.1%}  P(win)={r.p_win:5.1%}  "
            f"EV={r.ev:5.0f}  q90={r.q90:4.0f}\n     " + " | ".join(detail)
        )
    return "\n".join(lines)


def cmd_backtest(args):
    tournament = args.tournament
    path = tournament_file(tournament)
    draw = load_draw(str(path))
    kind = kind_of(tournament)
    entries = draw.entries

    history = load_pick_history(str(path))
    usage, banks = usage_and_quota_from_history(history, tournament)
    history_before = slice_history(history, tournament)

    names, points, rival_scores, (ranked, ranked_contra), model, field = run_pipeline(
        entries, kind, tournament, args.sims, exclude_event=tournament,
        usage=usage, banks=banks, history=history_before)

    seeds = [e.seed for e in entries if not e.is_bye]
    print(describe_sets(names, seeds, points, rival_scores, ranked,
                        {norm(p): c for p, c in usage[ME].items()},
                        field=field))

    # what actually happened
    outcomes = score_tournament(draw, kind)
    actual_pts = {n: o.result.total for n, o in outcomes.items()}
    actual_scores = {}
    for who, tournaments in history.items():
        picks = tournaments.get(tournament, [])
        if picks:
            actual_scores[who] = sum(actual_pts.get(norm(p), 0) for p, _ in picks)
    ordered = sorted(actual_scores.values(), reverse=True)
    print("\nACTUAL week: winner", ordered[0], "| 3rd place", ordered[2],
          "| median", ordered[len(ordered) // 2])
    # calibration: simulated field vs the real one
    t3 = rival_threshold(rival_scores, 3)
    print(f"model field:  simulated 3rd-place median {np.median(t3):.0f} "
          f"(p10 {np.quantile(t3, .1):.0f} / p90 {np.quantile(t3, .9):.0f}), "
          f"rival median {np.median(rival_scores):.0f}")
    # per-player EV sharpness
    ev = points.mean(axis=1)
    actual_vec = np.array([actual_pts.get(norm(n), 0) for n in names])
    played = actual_vec >= 0
    corr = np.corrcoef(ev[played], actual_vec[played])[0, 1]
    print(f"player EV vs actual points correlation: {corr:.2f}")
    print(f"my actual score: {actual_scores.get(ME)} "
          f"(rank {1 + sum(v > actual_scores.get(ME, 0) for v in actual_scores.values())})")
    for label, r in [("main #1", ranked[0]), ("contra #1", ranked_contra[0])]:
        s = sum(actual_pts.get(norm(names[j]), 0) for j in r.players)
        rank = 1 + sum(v > s for v in actual_scores.values())
        print(f"{label} set would have scored {s} -> actual rank {rank} "
              f"({', '.join(names[j] for j in r.players)})")


def cmd_rivals(args):
    """Quota-edge intelligence: what the poolers above me can still play."""
    banks = load_banques(str(summary_file(args.tournament)))
    usage = load_player_usage(str(summary_file(args.tournament)))
    st = None
    from pool.parsers import load_standings
    st = load_standings(str(tournament_file(LATEST_EVENT)))
    rows = sorted(st.items(), key=lambda kv: kv[1]["rank"])
    print("rk  pooler                    pts   GS bank    MS bank   "
          "17-32@SHA  Sinner  Alcaraz")
    for who, info in rows:
        if info["rank"] > (args.sims if args.sims < 100 else 30) and who != ME:
            continue
        b = banks.get(who)
        if not b:
            continue
        u = usage.get(who, {})
        gs = "/".join(str(b.gs_quota[k]) for k in ("1-4", "5-8", "9-16", "17-32"))
        ms = "/".join(str(b.masters_quota[k]) for k in ("1-4", "5-8", "9-16", "17-32"))
        tag = " <== me" if who == ME else ""
        print(f"{info['rank']:3d} {who:25s} {info['total']:4d}  {gs:9s}  {ms:9s}  "
              f"{b.masters_quota['17-32']:^9d}  {u.get('Sinner', 0)}x      "
              f"{u.get('Alcaraz', 0)}x{tag}")
    locked = sum(1 for b in banks.values() if b.masters_quota["17-32"] == 0)
    sinner5 = sum(1 for u in usage.values() if u.get("Sinner", 0) >= 5)
    print(f"\nrivals with ZERO Masters 17-32 tokens (band exists only at "
          f"Shanghai — Paris has 16 seeds): {locked}/77")
    print(f"poolers Sinner-locked (5 uses): {sinner5}/77; "
          f"one use left: {sum(1 for u in usage.values() if u.get('Sinner', 0) == 4)}/77")


def cmd_backtest_all(args):
    """Replay every completed tournament; report where the optimizer's top
    sets would have finished, plus field-model calibration per week."""
    from pool.parsers import TOURNAMENTS
    from tests.test_scoring import FILES
    summary = []
    for tournament, fname in FILES.items():
        path = DATA / fname
        draw = load_draw(str(path))
        kind = kind_of(tournament)
        history = load_pick_history(str(path))
        usage, banks = usage_and_quota_from_history(history, tournament)
        history_before = slice_history(history, tournament)
        names, points, rival_scores, (ranked, ranked_contra), model, field = run_pipeline(
            draw.entries, kind, tournament, args.sims,
            exclude_event=tournament, usage=usage, banks=banks,
            history=history_before, quiet=True)

        outcomes = score_tournament(draw, kind)
        actual_pts = {n: o.result.total for n, o in outcomes.items()}
        actual_scores = {}
        for who, ts in history.items():
            picks = ts.get(tournament, [])
            if picks:
                actual_scores[who] = sum(
                    actual_pts.get(norm(p), 0) for p, _ in picks)
        vals = sorted(actual_scores.values(), reverse=True)

        # calibration: predicted vs actual ownership correlation
        own_pred = field.expected_ownership(np.random.default_rng(2), rounds=30)
        idx = {norm(n): i for i, n in enumerate(names)}
        from collections import Counter
        held = Counter()
        for who, ts in history.items():
            for p, _ in ts.get(tournament, []):
                if norm(p) in idx:
                    held[idx[norm(p)]] += 1
        own_act = np.zeros(len(names))
        for i, c in held.items():
            own_act[i] = c / max(len(actual_scores), 1)
        mask = (own_pred > 0.01) | (own_act > 0.01)
        corr = float(np.corrcoef(own_pred[mask], own_act[mask])[0, 1])

        from pool.strength import EVENT_CLASS
        row = {"t": tournament, "corr": corr,
               "winner": vals[0], "third": vals[2],
               "me": actual_scores.get(ME, 0),
               "class": EVENT_CLASS.get(tournament, "chalk")}
        for lbl, r in [("main", ranked[0]), ("contra", ranked_contra[0])]:
            sc = sum(actual_pts.get(norm(names[j]), 0) for j in r.players)
            rk = 1 + sum(v > sc for v in actual_scores.values())
            row[lbl] = (sc, rk, [names[j] for j in r.players])
        summary.append(row)
        print(f"{tournament:15s} [{row['class']:8s}] 3rd-bar {row['third']:3d}  "
              f"me {row['me']:3d}  "
              f"MAIN {row['main'][0]:3d} (rank {row['main'][1]:2d})  "
              f"CONTRA {row['contra'][0]:3d} (rank {row['contra'][1]:2d})")
        print(f"{'':15s} main:   {', '.join(row['main'][2])}")
        print(f"{'':15s} contra: {', '.join(row['contra'][2])}")

    main_hits = sum(1 for r in summary if r["main"][1] <= 3)
    contra_hits = sum(1 for r in summary if r["contra"][1] <= 3)
    reco_hits = sum(1 for r in summary if
                    (r["contra"] if r["class"] == "variance" else r["main"])[1] <= 3)
    main_pts = sum(r["main"][0] for r in summary)
    contra_pts = sum(r["contra"][0] for r in summary)
    reco_pts = sum((r["contra"] if r["class"] == "variance" else r["main"])[0]
                   for r in summary)
    me_pts = sum(r["me"] for r in summary)
    print(f"\nMAIN sheet in the weekly money:   {main_hits}/{len(summary)}"
          f"   season points {main_pts}")
    print(f"CONTRA sheet in the weekly money: {contra_hits}/{len(summary)}"
          f"   season points {contra_pts}")
    print(f"MIXED playbook (main at chalk, contrarian at variance): "
          f"{reco_hits}/{len(summary)} in the money, season points {reco_pts}")
    print(f"my actual: 0/{len(summary)} in the money, season points {me_pts}")


def cmd_preview(args):
    tournament = args.tournament
    kind = kind_of(tournament)
    latest = tournament_file(LATEST_EVENT)
    rankings = load_rankings(str(latest))
    withdrawals = load_withdrawals(DATA)
    seed_order = None
    proj = DATA / "projected_seeds.json"
    if proj.exists():
        import json
        pj = json.loads(proj.read_text())
        if pj.get("tournament") == tournament:
            seed_order = pj["seed_order"]
            print(f"using projected seeds ({pj.get('source', 'manual')})")
    rng = np.random.default_rng(3)

    # draw uncertainty: several random draws, sims split across them
    n_draws = args.draws
    sims_per = max(500, args.sims // n_draws)
    all_ranked = {}
    all_contra = {}
    for d in range(n_draws):
        entries = placeholder_draw(rankings, withdrawals, rng,
                                   seed_order=seed_order)
        names, points, rival_scores, (ranked, ranked_contra), model, field = run_pipeline(
            entries, kind, tournament, sims_per, quiet=True)
        seeds = [e.seed for e in entries if not e.is_bye]
        for r in ranked:
            key = tuple(sorted(names[j] for j in r.players))
            cur = all_ranked.setdefault(key, [])
            cur.append(r.p_top3)
        for r in ranked_contra[:5]:
            key = tuple(sorted(names[j] for j in r.players))
            all_contra.setdefault(key, []).append(r.p_top3)
        if d == 0:
            first = (names, seeds, points, rival_scores, ranked, ranked_contra, field)
    print(f"preview across {n_draws} random draws x {sims_per} sims")
    print("== MAIN sheets (max P(top-3), ownership-aware) ==")
    best = sorted(all_ranked.items(), key=lambda kv: -np.mean(kv[1]))[:10]
    for i, (players, p3s) in enumerate(best, 1):
        print(f"{i:2}. mean P(top3)={np.mean(p3s):5.1%} "
              f"(seen in {len(p3s)}/{n_draws} draws)  {', '.join(players)}")
    print("== CONTRARIAN sheets (>=2 picks <15% owned, sheet <=60% on raw ownership) ==")
    bestc = sorted(all_contra.items(), key=lambda kv: -np.mean(kv[1]))[:10]
    for i, (players, p3s) in enumerate(bestc, 1):
        print(f"{i:2}. mean P(top3)={np.mean(p3s):5.1%} "
              f"(seen in {len(p3s)}/{n_draws} draws)  {', '.join(players)}")
    names, seeds, points, rival_scores, ranked, ranked_contra, field = first
    usage = load_player_usage(str(summary_file(tournament)))
    u = {norm(p): c for p, c in usage[ME].items()}
    print("\n--- draw sample #1: MAIN ---")
    print(describe_sets(names, seeds, points, rival_scores, ranked, u,
                        top=5, field=field))
    print("\n--- draw sample #1: CONTRARIAN ---")
    print(describe_sets(names, seeds, points, rival_scores, ranked_contra, u,
                        top=5, field=field))
    print("\nalternates for the sample MAIN sheet (pre-R1 withdrawal cover):")
    for line in suggest_alternates(names, seeds, points, rival_scores,
                                   ranked[0], u):
        print(f"   {line}")


def cmd_analyze(args):
    tournament = args.tournament
    kind = kind_of(tournament)
    if args.draw_json:
        entries = load_draw_json(args.draw_json)
    elif args.workbook:
        entries = load_draw(args.workbook).entries
    else:
        raise SystemExit("analyze needs a workbook or --draw-json")
    entries = apply_withdrawals(entries, load_withdrawals(DATA))
    cap = None
    if args.quota:
        vals = [int(x) for x in args.quota.split(",")]
        if len(vals) != 4:
            raise SystemExit("--quota needs 4 values: 1-4,5-8,9-16,17-32")
        cap = dict(zip(("1-4", "5-8", "9-16", "17-32"), vals))
    names, points, rival_scores, (ranked, ranked_contra), model, field = run_pipeline(
        entries, kind, tournament, args.sims, quota_cap=cap)
    seeds = [e.seed for e in entries if not e.is_bye]
    usage = load_player_usage(str(summary_file(tournament)))
    u = {norm(p): c for p, c in usage[ME].items()}
    print("=== MAIN sheet (max P(top-3), ownership-aware) ===")
    print(describe_sets(names, seeds, points, rival_scores, ranked, u,
                        top=6, field=field))
    print("\n=== CONTRARIAN sheet (>=2 picks <15% owned, sheet <=60% on raw ownership) ===")
    print(describe_sets(names, seeds, points, rival_scores, ranked_contra, u,
                        top=6, field=field))
    from pool.strength import EVENT_CLASS
    cls = EVENT_CLASS.get(tournament, "chalk")
    rec = "MAIN sheet" if cls == "chalk" else "CONTRARIAN sheet"
    print(f"\nplaybook recommendation: {tournament} is a {cls} event -> {rec}")
    for label, sheet in [("MAIN", ranked[0]), ("CONTRARIAN", ranked_contra[0])]:
        print(f"alternates to file for the {label} sheet "
              f"(same band, pre-R1 withdrawal only):")
        for line in suggest_alternates(names, seeds, points, rival_scores,
                                       sheet, u):
            print(f"   {line}")


def apply_withdrawals(entries: list[DrawEntry], withdrawn: set[str]) -> list[DrawEntry]:
    """Post-draw withdrawals: the slot goes to an unseeded lucky loser
    (rank ~110), so the bracket keeps its shape and the withdrawn player can
    never be simulated or recommended."""
    out, k = [], 0
    for e in entries:
        if not e.is_bye and norm(e.name) in withdrawn:
            k += 1
            print(f"withdrawn after the draw: {e.name} (slot {e.position}) "
                  f"-> Lucky Loser {k}", file=sys.stderr)
            out.append(DrawEntry(e.position, f"Lucky Loser {k}", 110, None))
        else:
            out.append(e)
    return out


def load_draw_json(path) -> list[DrawEntry]:
    """Slot list transcribed from a commissioner draw PDF:
    {"slots": [[position, name, atp_rank, seed_or_null], ...]} (BYEs incl.)."""
    import json
    from pool.parsers import BYE_RANK
    data = json.loads(Path(path).read_text())
    out = []
    for pos, name, rank, seed in data["slots"]:
        rank = BYE_RANK if norm(name) == "bye" else int(rank)
        out.append(DrawEntry(int(pos), name, rank, seed))
    if len(out) & (len(out) - 1):
        raise ValueError(f"draw size {len(out)} is not a power of two")
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("analyze", cmd_analyze), ("preview", cmd_preview),
                     ("backtest", cmd_backtest),
                     ("backtest-all", cmd_backtest_all),
                     ("rivals", cmd_rivals)]:
        p = sub.add_parser(name)
        p.add_argument("workbook", nargs="?")
        p.add_argument("--draw-json")
        p.add_argument("--quota", help="per-band cap this week, e.g. 1,1,1,2")
        p.add_argument("--tournament",
                       required=name not in ("backtest-all", "rivals"))
        p.add_argument("--sims", type=int, default=20000)
        p.add_argument("--draws", type=int, default=8)
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

"""Calibrate Elo overrides so simulated title probabilities match the
betting market. Writes the resulting deltas into data/form_overrides.json.

Usage: .venv/bin/python -m pool.calibrate
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from .parsers import norm

DATA = Path(__file__).resolve().parents[1] / "data"

# vig-normalized title probabilities — Paris 2026, post-draw (filled from the
# 2026-10-31 odds sweep; see data/research_paris.json for sources). Calibrated
# on the real bracket, so post-draw prices are matched directly.
TOURNAMENT = "Paris"
KIND = "m6"
DRAW_JSON = DATA / "paris_draw_2026.json"
MARKET: dict[str, float] = {
    "alcaraz": 0.27,
    "zverev": 0.192,
    "djokovic": 0.064,
    "medvedev": 0.052,
    "shelton": 0.052,
    "fils": 0.04,
    "jodar": 0.032,
    "fritz": 0.032,
    "de minaur": 0.022,
    "paul": 0.022,
    "tiafoe": 0.017,
    "cobolli": 0.014,
    "rune": 0.012,
    "ruud": 0.011,
    "davidovich fokina": 0.011,
}

# seed list; the live set is the UNION of this and whatever is already in
# form_overrides.json, so a withdrawal added later is never silently dropped
WITHDRAWALS = ["Sinner"]
EXTRA_DELTAS: dict[str, float] = {}


def simulate_title_probs(deltas: dict[str, float], n_draws: int, sims: int):
    from .strength import EVENT_CLASS, UPSET_FACTOR, build_model, load_h2h
    from .simulate import simulate
    from run_analysis import load_draw_json  # noqa: circular-safe at runtime

    overrides = dict(EXTRA_DELTAS)
    overrides.update(deltas)
    path = DATA / "form_overrides.json"
    # merge: calibrate owns _withdrawals and the MARKET/EXTRA player deltas;
    # everything else (_injury_risk, research deltas, _h2h) must survive.
    # Market players' research deltas are folded into the fit (the market
    # dominates for them), so the written value REPLACES the previous one.
    payload = json.loads(path.read_text()) if path.exists() else {}
    existing = payload.get("_withdrawals", [])
    merged = list(dict.fromkeys(list(existing) + WITHDRAWALS))
    payload["_withdrawals"] = merged
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    from .strength import load_injury_risk
    entries = load_draw_json(DRAW_JSON)
    model = build_model(DATA, target_surface="hard", anchor_ranks={
        e.name: e.atp_rank for e in entries if not e.is_bye})
    # calibrate under the SAME hazards, h2h and upset factor as live runs,
    # else market-priced injured players get double-penalized
    inj = load_injury_risk(DATA)
    h2h = load_h2h(DATA)
    uf = UPSET_FACTOR[EVENT_CLASS.get(TOURNAMENT, "chalk")]

    rng = np.random.default_rng(5)
    champs: Counter = Counter()
    total = 0
    for _ in range(n_draws):
        names, points, sim_champs = simulate(
            entries, model, KIND, n_sims=sims,
            seed=int(rng.integers(1e9)), return_champs=True,
            injury_risk=inj, h2h=h2h, upset_factor=uf)
        counts = np.bincount(sim_champs, minlength=len(names))
        for i, name in enumerate(names):
            champs[norm(name)] += int(counts[i])
        total += sims
    return {k: v / total for k, v in champs.items()}


def main():
    if not MARKET:
        raise SystemExit("MARKET is empty — fill it from the odds sweep first")
    path = DATA / "form_overrides.json"
    cur = json.loads(path.read_text()) if path.exists() else {}
    bad = [k for k in MARKET if k != norm(k)]
    if bad:  # probs are norm()-keyed; a raw key silently reads sim 0.000
        raise SystemExit(f"MARKET keys must be norm()'d (lowercase, no accents): {bad}")
    deltas = {k: float(cur.get(k, 0.0)) for k in MARKET}
    for it in range(6):
        probs = simulate_title_probs(deltas, n_draws=6, sims=3000)
        print(f"--- iteration {it} ---")
        worst = 0.0
        for player, target in MARKET.items():
            sim_p = max(probs.get(player, 0.0), 1e-4)
            adj = 120.0 * math.log(target / sim_p)
            adj = max(-80.0, min(80.0, adj))
            deltas[player] += adj
            worst = max(worst, abs(math.log(target / sim_p)))
            print(f"{player:20} sim {sim_p:6.3f} target {target:6.3f} "
                  f"delta {deltas[player]:+7.1f}")
        if worst < 0.12:
            break
    # final write happens inside simulate_title_probs on the last call
    simulate_title_probs(deltas, n_draws=1, sims=100)
    print("\nwrote", DATA / "form_overrides.json")


if __name__ == "__main__":
    main()

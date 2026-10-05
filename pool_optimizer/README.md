# ATP Pool Pick Optimizer

Pick recommender for the 2026 ATP tennis pool (13 Slam/Masters events, 5 picks
per event, 77 participants). Optimizes **P(finishing top-3 of the week)** —
the thing that pays — not raw expected points.

> **Not in this repo (kept private, see `.gitignore`):** the commissioner's
> workbooks under `data/` (`NN - <Event>.xlsm`, `ChoixTournois_2026.xlsx`,
> `Choix<Event>.xlsx`) hold every pooler's name and picks, and PLAYBOOK.md /
> INTEL.md hold named rival notes. The parsers, scoring tests and backtests
> need those workbooks in `data/` to run.

**→ PLAYBOOK.md (private) is the operating manual**: the strategy and its
evidence, the pre-tournament research ritual, the remaining US Open steps, and
the Shanghai/Paris checklists (what to archive, refresh and re-run per event).
This README covers the code; the playbook covers the process.

## How it works

1. **Parsers** ([pool/parsers.py](pool/parsers.py)) read the commissioner's
   workbooks: draws with results, rankings, everyone's picks, quota banks.
2. **Scoring engine** ([pool/scoring.py](pool/scoring.py)) implements the exact
   rules (ATP points + cumulative upset bonuses). Validated: reproduces all
   515 player-tournament scores from the 10 completed 2026 events exactly
   (`tests/test_scoring.py`).
3. **Strength model** ([pool/strength.py](pool/strength.py)): Elo anchored on
   current ATP rank, updated with 2026 season results (recency- and
   hard-court-weighted), then calibrated to betting-market title odds
   ([pool/calibrate.py](pool/calibrate.py)) and manual notes in
   `data/form_overrides.json` (injuries, withdrawals).
4. **Simulator** ([pool/simulate.py](pool/simulate.py)): Monte Carlo over the
   actual bracket, scoring every player per simulation with path-dependent
   bonuses (a dark horse crossing a top seed early is worth 50/win at a Slam).
5. **Opponent model** ([pool/opponents.py](pool/opponents.py)): samples what
   the 76 rivals will pick, using their exact remaining quotas, burned
   players, and revealed preferences. This is what turns "my points" into
   "probability I beat the field".
6. **Optimizer** ([pool/optimize.py](pool/optimize.py)): enumerates valid pick
   sets under my quota bank and ranks them by P(top-3).

## Usage

```bash
# before the draw is out: placeholder draws with proper seed placement
.venv/bin/python run_analysis.py preview --tournament "US Open" --sims 40000

# when the workbook with the real draw arrives (drop it in data/ first)
.venv/bin/python run_analysis.py analyze "data/11 - US Open.xlsm" --tournament "US Open"

# sanity: replay a completed tournament as of its eve
.venv/bin/python run_analysis.py backtest --tournament Cincinnati

# real draw from the commissioner's PDF (transcribed to JSON), capping this
# week's band spend so tokens are kept for a later event
.venv/bin/python run_analysis.py analyze --draw-json data/shanghai_draw_2026.json \
    --tournament Shanghai --quota 1,1,1,2

# merge research-agent JSON into the overrides, then recalibrate
.venv/bin/python -m pool.merge_research data/research_shanghai.json

# validate the scoring engine against all completed tournaments
.venv/bin/python tests/test_scoring.py

# recalibrate strengths to fresh betting odds (edit MARKET in the file first)
.venv/bin/python -m pool.calibrate
```

`data/form_overrides.json`: `_withdrawals` (list of names; in `analyze` a
withdrawn player's slot becomes a lucky loser), `_injury_risk`, `_h2h`,
`_ownership_floor` (hand-audited minimum field share), plus per-player Elo
deltas (`"name": +50`) or absolutes (`"name=": 1750`). None of it reaches
backtests. Setup: `python3 -m venv .venv && .venv/bin/pip install numpy openpyxl pypdf`.

## Strategy notes (why this beats template picking)

- Weekly money goes to top-3 of 77. Expected-points-maximizing chalk ties the
  crowd; you need the champion **plus** differentiation.
- Upset bonuses are cumulative and huge at Slams (unseeded beats top-4 seed =
  50/win), so an unseeded player whose path crosses giants early can outscore
  a quarterfinalist seed.
- The optimizer naturally penalizes picks the crowd holds (their runs raise
  the top-3 bar for everyone) and picks that collide early in the draw.
- Season quota: bands are use-it-or-lose-it per Slam group; player cap is
  5 uses. The tool reports the usage cost of each recommendation.

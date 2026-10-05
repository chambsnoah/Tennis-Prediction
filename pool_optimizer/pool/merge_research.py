"""Merge research-agent JSON deliverables into data/form_overrides.json.

Usage: .venv/bin/python -m pool.merge_research data/research_shanghai.json

The research file maps agent scope -> that agent's contract block
({"elo_delta", "injury_risk", "h2h", "withdrawals", "notes", ...}). Agents
own disjoint player scopes, so a player appearing in two scopes is a
contradiction to resolve by source quality (PLAYBOOK §7) — never averaged:
the merge refuses until the research file is fixed.

Market-priced players' research deltas are kept as the calibrator's
STARTING point; `python -m pool.calibrate` then fits them to the odds, so
re-run it after every merge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .parsers import norm

DATA = Path(__file__).resolve().parents[1] / "data"


def merge(research_path: Path, out_path: Path = DATA / "form_overrides.json"):
    research = json.loads(research_path.read_text())
    payload = json.loads(out_path.read_text()) if out_path.exists() else {}
    deltas: dict[str, tuple[float, str]] = {}
    injury = dict(payload.get("_injury_risk", {}))
    h2h = {(norm(a), norm(b)): (a, b, t) for a, b, t in payload.get("_h2h", [])}
    withdrawals = list(payload.get("_withdrawals", []))

    for scope, block in research.items():
        if scope.startswith("_"):
            continue
        for player, d in block.get("elo_delta", {}).items():
            key = norm(player)
            if key in deltas and deltas[key][0] != float(d):
                raise SystemExit(f"contradiction on {player}: {deltas[key][1]} says "
                                 f"{deltas[key][0]:+.0f}, {scope} says {d:+.0f}")
            deltas[key] = (float(d), scope)
        for player, h in block.get("injury_risk", {}).items():
            # a hazard flag is a risk floor: the more cautious reading wins
            cur = next((k for k in injury if norm(k) == norm(player)), player)
            injury[cur] = max(float(h), float(injury.get(cur, 0.0)))
        for a, b, t in block.get("h2h", []):
            pair, rev = (norm(a), norm(b)), (norm(b), norm(a))
            if rev in h2h:
                raise SystemExit(f"h2h {a}/{b} given in both directions")
            h2h[pair] = (a, b, float(t))
        for w in block.get("withdrawals", []):
            if norm(w) not in {norm(x) for x in withdrawals}:
                withdrawals.append(w)

    for key, (d, _) in deltas.items():
        payload[key] = d
    payload["_withdrawals"] = withdrawals
    payload["_injury_risk"] = {k: v for k, v in sorted(injury.items()) if v > 0}
    payload["_h2h"] = [list(v) for v in h2h.values()]
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"merged {len(deltas)} deltas, {len(payload['_injury_risk'])} hazards, "
          f"{len(payload['_h2h'])} h2h, {len(withdrawals)} withdrawals -> {out_path}")


if __name__ == "__main__":
    merge(Path(sys.argv[1]))

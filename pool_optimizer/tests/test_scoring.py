"""Validate the scoring engine against ground truth in the workbooks.

For every completed tournament: reconstruct each entrant's run from the Draw
sheet, score it, and compare with the (atp, bonus) the commissioner recorded
for every participant-player row.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pool.parsers import GRAND_SLAMS, MASTERS_6R, load_draw, load_pool_results, norm
from pool.results import score_tournament

DATA = Path(__file__).resolve().parents[1] / "data"

FILES = {
    "Australie": "01 - Australie.xlsm",
    "Indian Wells": "02 - Indian Wells.xlsm",
    "Miami": "03 - Miami.xlsm",
    "Monte Carlo": "04 - Monte Carlo.xlsm",
    "Madrid": "05 - Madrid.xlsm",
    "Rome": "06 - Rome.xlsm",
    "Roland-Garros": "07 - Roland-Garros.xlsm",
    "Wimbledon": "08 - Wimbledon.xlsm",
    "Montréal": "09 - Montréal.xlsm",
    "Cincinnati": "10 - Cincinnati.xlsm",
    "US Open": "11 - US Open.xlsm",
}


def validate(tournament: str, fname: str, verbose: bool = False):
    path = str(DATA / fname)
    draw = load_draw(path)
    kind = "gs" if tournament in GRAND_SLAMS else ("m6" if tournament in MASTERS_6R else "m7")
    outcomes = score_tournament(draw, kind)
    truth = load_pool_results(path, tournament)

    checked = mismatches = missing = 0
    seen_players = set()
    for participant, players in truth.items():
        for player, (atp, bonus, total) in players.items():
            key = norm(player)
            if key in seen_players:
                continue
            seen_players.add(key)
            if key not in outcomes:
                missing += 1
                if verbose:
                    print(f"  MISSING {tournament}: {player}")
                continue
            got = outcomes[key].result
            checked += 1
            if (got.atp, got.bonus) != (atp, bonus):
                mismatches += 1
                if verbose:
                    print(
                        f"  MISMATCH {tournament} {player}: "
                        f"engine atp={got.atp} bonus={got.bonus} "
                        f"truth atp={atp} bonus={bonus} "
                        f"(seed={outcomes[key].entry.seed} "
                        f"rank={outcomes[key].entry.atp_rank} "
                        f"lost_r={outcomes[key].lost_in_round})"
                    )
    return checked, mismatches, missing


def main():
    total_checked = total_bad = total_missing = 0
    for t, f in FILES.items():
        if not (DATA / f).exists():
            print(f"{t}: file not found, skipped")
            continue
        checked, bad, missing = validate(t, f, verbose=True)
        total_checked += checked
        total_bad += bad
        total_missing += missing
        status = "OK" if bad == 0 and missing == 0 else "FAIL"
        print(f"{t}: {checked} unique players checked, "
              f"{bad} mismatches, {missing} missing -> {status}")
    print(f"\nTOTAL: {total_checked} checked, {total_bad} mismatches, "
          f"{total_missing} missing")
    return 1 if (total_bad or total_missing) else 0


if __name__ == "__main__":
    sys.exit(main())

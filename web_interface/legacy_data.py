"""Legacy 2023/2024 tournament JSON, addressed by catalog ID rather than filesystem path.

A tournament ID is ``YYYY/slug`` with a fixed pattern; it is never joined onto
a path as given. Files are opened below the data root component by component
without following symlinks, size-bounded and schema-checked before use.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from web_interface.errors import ServiceError
from web_interface.files import has_file, list_directories, read_bounded

_YEAR = re.compile(r"20\d\d")
_SLUG = re.compile(r"[a-z0-9_]{1,64}")
PLAYER_FILE_BYTES = 1024 * 1024
BRACKET_FILE_BYTES = 256 * 1024
MAX_PLAYERS = 1024
_NAMES = (("wimby", "Wimbledon"), ("us", "US Open"), ("rg", "Roland Garros"),
          ("au", "Australian Open"))


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


@dataclass(frozen=True)
class PlayerRecord:
    name: str
    seed: int
    cost: float
    p_factor: float
    n_factor: float

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "seed": self.seed, "cost": self.cost,
                "p_factor": self.p_factor, "n_factor": self.n_factor}


def _number(value: object, default: float, low: float, high: float) -> float:
    if value is None:
        return default
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ServiceError("invalid_player_data", 422)
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= 100 or not value.isprintable():
        raise ServiceError("invalid_player_data", 422)
    return value


def gender(value: object) -> Gender:
    try:
        return Gender(value)
    except ValueError:
        raise ServiceError("invalid_gender", 422) from None


class LegacyCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _parts(self, tournament_id: object) -> tuple[str, str]:
        if isinstance(tournament_id, str) and tournament_id.count("/") == 1:
            year, slug = tournament_id.split("/")
            if _YEAR.fullmatch(year) and _SLUG.fullmatch(slug):
                return year, slug
        raise ServiceError("unknown_tournament", 404)

    def tournaments(self) -> list[dict[str, object]]:
        found = []
        for year in list_directories(self.root):
            if not _YEAR.fullmatch(year):
                continue
            for slug in list_directories(self.root, [year]):
                if not _SLUG.fullmatch(slug):
                    continue
                has = {g: has_file(self.root, [year, slug, f"players_{g.value}.json"])
                       for g in Gender}
                if not any(has.values()):
                    continue
                name = slug.replace(year, " " + year)
                for short, full in _NAMES:
                    name = name.replace(short, full)
                found.append({"id": f"{year}/{slug}", "name": name.title(),
                              "has_male": has[Gender.MALE], "has_female": has[Gender.FEMALE]})
        return found

    def _json(self, tournament_id: object, file: str, missing: str) -> object:
        year, slug = self._parts(tournament_id)
        data = read_bounded(self.root, [year, slug, file], PLAYER_FILE_BYTES, trusted=False,
                            missing=missing, too_large="data_file_too_large")
        try:
            return json.loads(data)
        except ValueError:
            raise ServiceError("invalid_player_data", 422) from None

    def players(self, tournament_id: object, sex: Gender) -> tuple[PlayerRecord, ...]:
        raw = self._json(tournament_id, f"players_{sex.value}.json", "players_file_not_found")
        if not isinstance(raw, dict) or len(raw) > MAX_PLAYERS:
            raise ServiceError("invalid_player_data", 422)
        records = []
        for name, data in raw.items():
            if not isinstance(data, dict):
                raise ServiceError("invalid_player_data", 422)
            seed = _number(data.get("seed"), 0, 0, 10_000)
            if seed != int(seed):
                raise ServiceError("invalid_player_data", 422)
            records.append(PlayerRecord(
                name=_name(name), seed=int(seed), cost=_number(data.get("cost"), 0, 0, 1e9),
                p_factor=_number(data.get("p_factor"), 0, -1, 1),
                n_factor=_number(data.get("n_factor"), 0, -1, 1)))
        return tuple(sorted(records, key=lambda r: r.seed))

    def points(self, tournament_id: object, sex: Gender) -> dict[str, float] | None:
        try:
            raw = self._json(tournament_id, f"player_points_{sex.value}.json", "points_missing")
        except ServiceError as error:
            if error.code == "points_missing":
                return None
            raise
        if not isinstance(raw, dict) or len(raw) > MAX_PLAYERS:
            raise ServiceError("invalid_player_data", 422)
        return {_name(k): _number(v, 0, 0, 1e9) for k, v in raw.items()}

    def bracket(self, tournament_id: object, sex: Gender) -> dict[str, object]:
        year, slug = self._parts(tournament_id)
        data = read_bounded(self.root, [year, slug, f"bracket_{sex.value}.txt"],
                            BRACKET_FILE_BYTES, trusted=False,
                            missing="bracket_file_not_found", too_large="data_file_too_large")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ServiceError("invalid_bracket_data", 422) from None
        matches = []
        for line in content.strip().split("\n"):
            # Simplified legacy display parsing, unchanged.
            if "Singles" in line and ("R1" in line or "Upcoming" in line):
                parts = line.split()
                if len(parts) >= 6:
                    matches.append({
                        "round": "R1",
                        "status": "Upcoming",
                        "player1": " ".join(parts[4:6]),
                        "player2": (" ".join(parts[-2:]) if len(parts) > 7
                                    else parts[-1] if len(parts) > 6 else ""),
                    })
        return {"bracket_text": content, "matches": matches[:32]}

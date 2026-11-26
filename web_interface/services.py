"""Typed local services behind the web app: direct calls, bounded jobs, safe errors.

``LocalServices`` validates untrusted request data into typed job records and
runs the heavy work (match simulation, legacy team optimization, workbook
preview, prediction, tournament scenarios and pool recommendations) through a
``JobRunner``. Requests name catalog entries (tournament IDs, configured pool
events, manifest artifacts); they never supply filesystem paths, rule-register
paths or provider code. Every refusal is a ``ServiceError`` reason code.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tennis_api.models.canonical import (
    Draw, Event, MatchProbability, PlayerId, PredictionContext, Provenance, RankingSnapshot,
)
from tennis_api.models.identity import IdentityRegistry
from tennis_pool.ledger import EntryState
from tennis_pool.workbooks import WorkbookImportError, WorkbookLimits, WorkbookPreview, preview_workbook
from web_interface.artifacts import ArtifactStore, VerifiedArtifact, load_provider
from web_interface.config import LocalAppConfig
from web_interface.errors import ServiceError, safe_code
from web_interface.files import read_bounded
from web_interface.jobs import JobRunner
from web_interface.legacy_data import Gender, LegacyCatalog, PlayerRecord, gender
from web_interface.match_simulator import SURFACE_ADJUSTMENTS, simulate_matches
from web_interface.team_optimizer import optimize_team

TARGETS = frozenset({
    "web_interface.services:match_simulation_job",
    "web_interface.services:team_optimization_job",
    "web_interface.services:workbook_preview_job",
    "web_interface.services:prediction_job",
    "web_interface.pool_jobs:scenario_job",
    "web_interface.pool_jobs:recommendation_job",
})
POOL_INPUT_BYTES = 8 * 1024 * 1024
WORKBOOK_FORMATS = ("GS128", "M7", "M6")
POOL_KINDS = ("gs", "m7", "m6")
MAX_WITHDRAWALS = 128
MAX_RANKINGS = 256
_POOL_EVENT = re.compile(r"[a-z0-9_]{1,64}")


# --- request parsing -----------------------------------------------------------


def _object(data: object, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ServiceError("invalid_json", 400)
    if set(data) - allowed:
        raise ServiceError("unknown_field", 400)
    return data


def _int(data: Mapping[str, Any], key: str, default: int | None, low: int, high: int) -> int:
    value = data.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ServiceError(f"invalid_{key}", 422)
    return value


def _choice(data: Mapping[str, Any], key: str, default: str | None, options: tuple[str, ...]) -> str:
    value = data.get(key, default)
    if value not in options:
        raise ServiceError(f"invalid_{key}", 422)
    return str(value)


def _bool(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if type(value) is not bool:
        raise ServiceError(f"invalid_{key}", 422)
    return value


def _contract(cls: Any, value: object, code: str) -> Any:
    if not isinstance(value, dict):
        raise ServiceError(code, 422)
    try:
        return cls.from_dict(value)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ServiceError(code, 422) from None


def _cutoff(value: object) -> datetime:
    try:
        cutoff = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        cutoff = None
    if cutoff is None or cutoff.tzinfo is None:
        raise ServiceError("invalid_cutoff", 422)
    return cutoff


# --- job records ---------------------------------------------------------------


@dataclass(frozen=True)
class MatchSimulationJob:
    player1: PlayerRecord
    player2: PlayerRecord
    sets_to_win: int
    simulations: int
    surface: str
    seed: int


@dataclass(frozen=True)
class TeamOptimizationJob:
    players: tuple[PlayerRecord, ...]
    points: tuple[tuple[str, float], ...] | None
    budget: int
    team_size: int
    seed: int


@dataclass(frozen=True)
class WorkbookPreviewJob:
    data: bytes = field(repr=False)
    suffix: str
    event: Event
    format: str
    registry: IdentityRegistry = field(repr=False)
    received_at: datetime
    limits: WorkbookLimits = field(default_factory=WorkbookLimits)


@dataclass(frozen=True)
class PredictionJob:
    artifact: VerifiedArtifact
    loader: str
    context: PredictionContext


@dataclass(frozen=True)
class ScenarioJob:
    artifact: VerifiedArtifact
    loader: str
    draw: Draw
    kind: str
    cutoff: datetime
    simulations: int
    seed: int
    allow_provisional: bool
    withdrawal_probabilities: tuple[tuple[PlayerId, float], ...]
    max_withdrawal_patterns: int
    rankings: tuple[RankingSnapshot, ...] = ()


@dataclass(frozen=True)
class RecommendationJob:
    scenarios: ScenarioJob
    event_id: str
    entry: EntryState | None


# --- job functions (run inside a bounded worker) ---------------------------------


def match_simulation_job(job: MatchSimulationJob) -> dict[str, object]:
    return simulate_matches(
        (job.player1.name, job.player1.p_factor, job.player1.n_factor),
        (job.player2.name, job.player2.p_factor, job.player2.n_factor),
        sets_to_win=job.sets_to_win, simulations=job.simulations, surface=job.surface,
        seed=job.seed)


def team_optimization_job(job: TeamOptimizationJob) -> dict[str, object]:
    return optimize_team(job.players, dict(job.points) if job.points else None,
                         budget=job.budget, team_size=job.team_size, seed=job.seed)


def preview_upload(job: WorkbookPreviewJob) -> WorkbookPreview:
    """Full preview (private season records included) for in-process callers."""
    if len(job.data) > job.limits.file_bytes:
        raise ServiceError("file_byte_limit", 413)
    digest = hashlib.sha256(job.data).hexdigest()
    provenance = Provenance(
        source="local_upload", source_version="sha256:" + digest, source_record_id=None,
        observed_at=None, available_at=job.received_at, ingested_at=job.received_at)
    with tempfile.TemporaryDirectory(prefix="tennis-upload-") as directory:
        path = Path(directory) / ("upload" + job.suffix)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(job.data)
        try:
            return preview_workbook(
                path, event=job.event, year=job.event.start_date.year, format=job.format,
                registry=job.registry, provenance=provenance, limits=job.limits)
        except WorkbookImportError as error:
            raise ServiceError(safe_code(str(error), "invalid_workbook_or_metadata"), 422) from None


def summarize_preview(preview: WorkbookPreview, upload_sha256: str) -> dict[str, object]:
    """What the browser may see: no participant labels, picks, banks or standings."""
    season = preview.season
    return {
        "upload_sha256": upload_sha256,
        "draw": preview.draw.to_dict(),
        "rankings": sum(r.rank is not None for r in preview.rankings),
        "sheets": [{"sheet": s.sheet, "records": s.records, "missing_values": s.missing_values,
                    "substitutions": s.substitutions} for s in preview.summaries],
        "missing_sheets": list(preview.missing_sheets),
        "unsupported_sheets": list(preview.unsupported_sheets),
        "warnings": list(preview.warnings),
        "registry_revision": preview.registry_revision,
        "registry_digest": preview.registry_digest,
        "private_season_records": {
            "picks": len(season.picks), "standings": len(season.standings),
            "banks": len(season.banks), "usage": len(season.usage),
            "substitutions": len(season.substitutions),
        },
    }


def workbook_preview_job(job: WorkbookPreviewJob) -> dict[str, object]:
    preview = preview_upload(job)
    return summarize_preview(preview, hashlib.sha256(job.data).hexdigest())


def prediction_job(job: PredictionJob) -> dict[str, object]:
    provider = load_provider(job.artifact, job.loader)
    try:
        result = provider.predict(job.context)
    except ServiceError:
        raise
    except (ValueError, TypeError, KeyError):
        raise ServiceError("prediction_refused", 422) from None
    if not isinstance(result, MatchProbability):
        raise ServiceError("invalid_provider_response", 502)
    try:
        result.require_context(job.context)
    except ValueError:
        raise ServiceError("provider_context_mismatch", 502) from None
    return {"prediction": result.to_dict(), "artifact": job.artifact.name,
            "artifact_sha256": job.artifact.sha256}


# --- configured pool inputs -------------------------------------------------------


@dataclass(frozen=True)
class PoolInputs:
    """Operator-reviewed records: the identity registry and canonical pool events."""

    registry: IdentityRegistry = field(repr=False)
    events: Mapping[str, Event] = field(repr=False)


def _trusted_json(root: Path, name: str) -> object:
    data = read_bounded(root, [name], POOL_INPUT_BYTES, trusted=True,
                        missing="pool_input_missing", too_large="pool_input_too_large")
    try:
        return json.loads(data)
    except ValueError:
        raise ServiceError("invalid_pool_input", 503) from None


def load_pool_inputs(root: Path) -> PoolInputs:
    """Read ``registry.json`` and ``events.json`` from the trusted pool directory."""
    registry = _trusted_json(root, "registry.json")
    events = _trusted_json(root, "events.json")
    if (not isinstance(events, dict) or set(events) != {"schema_version", "events"}
            or events["schema_version"] != 1 or not isinstance(events["events"], dict)):
        raise ServiceError("invalid_pool_input", 503)
    try:
        parsed = {key: Event.from_dict(value) for key, value in events["events"].items()
                  if _POOL_EVENT.fullmatch(key) and isinstance(value, dict)}
        if len(parsed) != len(events["events"]) or not isinstance(registry, dict):
            raise ValueError
        return PoolInputs(registry=IdentityRegistry.from_dict(registry), events=parsed)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ServiceError("invalid_pool_input", 503) from None


# --- the service facade --------------------------------------------------------------


class LocalServices:
    """Direct, validated service calls for one local user."""

    def __init__(self, config: LocalAppConfig, runner: JobRunner | None = None) -> None:
        self.config = config
        self.catalog = LegacyCatalog(config.data_root)
        self.runner = runner or JobRunner(config.jobs, TARGETS)
        self.pool: PoolInputs | None = None
        self.artifacts = ArtifactStore.empty(dict(config.provider_loaders))
        if config.pool_root is not None:
            self.pool = load_pool_inputs(config.pool_root)
            if (config.pool_root / "artifacts").is_dir():
                self.artifacts = ArtifactStore.from_directory(
                    config.pool_root / "artifacts", loaders=dict(config.provider_loaders),
                    manifest_sha256=config.manifest_sha256,
                    max_bytes=config.max_artifact_bytes)

    def status(self) -> dict[str, object]:
        return {
            "limits": self.config.limits(),
            "enforced_limits": self.runner.enforced,
            "pool_events": sorted(self.pool.events) if self.pool else [],
            "artifacts": list(self.artifacts.names()),
            "provider_kinds": sorted(k for k, _ in self.config.provider_loaders),
        }

    # Legacy tournament data -------------------------------------------------

    def tournaments(self) -> list[dict[str, object]]:
        return self.catalog.tournaments()

    def players(self, tournament_id: str, sex: object) -> list[dict[str, object]]:
        return [p.to_dict() for p in self.catalog.players(tournament_id, gender(sex))]

    def bracket(self, tournament_id: str, sex: object) -> dict[str, object]:
        return self.catalog.bracket(tournament_id, gender(sex))

    def _roster(self, data: Mapping[str, Any]) -> tuple[str, Gender, tuple[PlayerRecord, ...]]:
        sex = gender(data.get("gender"))
        tournament = data.get("tournament_path")
        return str(tournament), sex, self.catalog.players(tournament, sex)

    def simulate_match(self, data: object) -> dict[str, object]:
        request = _object(data, {"tournament_path", "gender", "player1_name", "player2_name",
                                 "sets_to_win", "num_simulations", "surface", "seed"})
        _, _, players = self._roster(request)
        by_name = {p.name: p for p in players}
        first, second = request.get("player1_name"), request.get("player2_name")
        if not isinstance(first, str) or not isinstance(second, str) or first == second:
            raise ServiceError("invalid_players", 422)
        if first not in by_name or second not in by_name:
            raise ServiceError("unknown_player", 404)
        job = MatchSimulationJob(
            player1=by_name[first], player2=by_name[second],
            sets_to_win=_int(request, "sets_to_win", 3, 2, 3),
            simulations=_int(request, "num_simulations", 500, 1, self.config.max_match_simulations),
            surface=_choice(request, "surface", "grass", tuple(SURFACE_ADJUSTMENTS)),
            seed=_int(request, "seed", self.config.default_seed, 0, 2 ** 63 - 1))
        result: dict[str, object] = self.runner.run(
            "web_interface.services:match_simulation_job", job)
        return result

    def optimize_team(self, data: object) -> dict[str, object]:
        request = _object(data, {"tournament_path", "gender", "budget", "team_size", "seed"})
        tournament, sex, players = self._roster(request)
        team_size = _int(request, "team_size", 8, 1, 32)
        if team_size > len(players):
            raise ServiceError("invalid_team_size", 422)
        points = self.catalog.points(tournament, sex)
        job = TeamOptimizationJob(
            players=players, points=tuple(sorted(points.items())) if points else None,
            budget=_int(request, "budget", 100_000, 1, 10 ** 9), team_size=team_size,
            seed=_int(request, "seed", self.config.default_seed, 0, 2 ** 63 - 1))
        result: dict[str, object] = self.runner.run(
            "web_interface.services:team_optimization_job", job)
        return result

    # Pool services ----------------------------------------------------------------

    def preview_workbook(self, data: bytes, params: Mapping[str, str],
                         now: datetime | None = None) -> dict[str, object]:
        if set(params) - {"event_id", "format", "suffix"}:
            raise ServiceError("unknown_field", 400)
        if self.pool is None:
            raise ServiceError("pool_inputs_not_configured", 503)
        event = self.pool.events.get(params.get("event_id", ""))
        if event is None:
            raise ServiceError("unknown_event", 404)
        if len(data) > self.config.workbook_limits.file_bytes:
            raise ServiceError("file_byte_limit", 413)
        job = WorkbookPreviewJob(
            data=data, suffix=_choice(params, "suffix", ".xlsx", (".xlsx", ".xlsm")),
            event=event, format=_choice(params, "format", None, WORKBOOK_FORMATS),
            registry=self.pool.registry, received_at=now or datetime.now(timezone.utc),
            limits=self.config.workbook_limits)
        result: dict[str, object] = self.runner.run(
            "web_interface.services:workbook_preview_job", job)
        return result

    def predict(self, data: object) -> dict[str, object]:
        request = _object(data, {"artifact", "context"})
        artifact, loader = self.artifacts.load(request.get("artifact"))
        context = _contract(PredictionContext, request.get("context"), "invalid_prediction_context")
        result: dict[str, object] = self.runner.run(
            "web_interface.services:prediction_job",
            PredictionJob(artifact=artifact, loader=loader, context=context))
        return result

    def _scenario_job(self, request: Mapping[str, Any]) -> ScenarioJob:
        artifact, loader = self.artifacts.load(request.get("artifact"))
        draw = _contract(Draw, request.get("draw"), "invalid_draw")
        withdrawals = request.get("withdrawal_probabilities", {})
        if not isinstance(withdrawals, dict) or len(withdrawals) > MAX_WITHDRAWALS:
            raise ServiceError("invalid_withdrawal_probabilities", 422)
        probabilities = []
        for player, probability in sorted(withdrawals.items()):
            if (not isinstance(probability, (int, float)) or isinstance(probability, bool)
                    or not math.isfinite(probability) or not 0 <= probability <= 1):
                raise ServiceError("invalid_withdrawal_probabilities", 422)
            probabilities.append((PlayerId(player), float(probability)))
        rankings = request.get("rankings", [])
        if not isinstance(rankings, list) or len(rankings) > MAX_RANKINGS:
            raise ServiceError("invalid_rankings", 422)
        return ScenarioJob(
            artifact=artifact, loader=loader, draw=draw,
            kind=_choice(request, "kind", None, POOL_KINDS),
            cutoff=_cutoff(request.get("cutoff")),
            simulations=_int(request, "simulations", 2000, 1,
                             self.config.max_tournament_simulations),
            seed=_int(request, "seed", self.config.default_seed, 0, 2 ** 63 - 1),
            allow_provisional=_bool(request, "allow_provisional"),
            withdrawal_probabilities=tuple(probabilities),
            max_withdrawal_patterns=self.config.max_withdrawal_patterns,
            rankings=tuple(_contract(RankingSnapshot, r, "invalid_rankings") for r in rankings))

    _SCENARIO_FIELDS = {"artifact", "draw", "kind", "cutoff", "simulations", "seed",
                        "allow_provisional", "withdrawal_probabilities", "rankings"}

    def simulate_tournament(self, data: object) -> dict[str, object]:
        request = _object(data, self._SCENARIO_FIELDS)
        result: dict[str, object] = self.runner.run(
            "web_interface.pool_jobs:scenario_job", self._scenario_job(request))
        return result

    def recommend(self, data: object) -> dict[str, object]:
        request = _object(data, self._SCENARIO_FIELDS | {"event_id", "entry"})
        event_id = request.get("event_id")
        if not isinstance(event_id, str) or not _POOL_EVENT.fullmatch(event_id):
            raise ServiceError("invalid_event_id", 422)
        entry = (None if request.get("entry") is None
                 else _contract(EntryState, request.get("entry"), "invalid_entry"))
        job = RecommendationJob(scenarios=self._scenario_job(request), event_id=event_id,
                                entry=entry)
        result: dict[str, object] = self.runner.run(
            "web_interface.pool_jobs:recommendation_job", job)
        return result


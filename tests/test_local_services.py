"""Local typed services and the loopback web app, with synthetic data built at runtime."""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import struct
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tennis_api.models.canonical import (
    Coverage, Draw, DrawSlot, EntryKind, Event, EventId, MatchProbability, Player, PlayerId,
    PredictionContext, Provenance, RankingSnapshot, Surface, Tour,
)
from dataclasses import replace

from tennis_api.models.identity import IdentityRegistry, ReviewedAlias
from tennis_pool.workbooks import WorkbookLimits
from web_interface import server
from web_interface.artifacts import ArtifactStore, VerifiedArtifact, load_provider
from web_interface.config import LocalAppConfig
from web_interface.errors import ServiceError
from web_interface.jobs import JobLimits, JobRunner
from web_interface.legacy_data import Gender, LegacyCatalog
from web_interface.services import TARGETS, LocalServices, MatchSimulationJob

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
CUTOFF = START + timedelta(hours=1)
SECRET = "synthetic-credential-sentinel-7f3a91"
LOADER = (("synthetic-table", "test_local_services:load_synthetic_provider"),)
TEST_TARGETS = TARGETS | {
    "test_local_services:sleep_job", "test_local_services:hold_job",
    "test_local_services:secret_failure_job", "test_local_services:partial_frame_job",
    "test_local_services:large_result_job", "test_local_services:echo_job",
}


# --- synthetic provider and job targets (imported by spawned workers) ----------


class SyntheticProvider:
    """Uncalibrated fixture: the lower player number wins 65% of matches."""

    def __init__(self, model_version: str, mismatch: bool = False) -> None:
        self.model_version = model_version
        self.mismatch = mismatch

    def predict(self, context):
        stronger = int(context.player1_id.split("p")[-1]) < int(context.player2_id.split("p")[-1])
        return MatchProbability(
            player1_id=context.player1_id, player2_id=context.player2_id,
            player1_win_probability=0.65 if stronger else 0.35,
            model_version=self.model_version, calibration_version=None, cutoff=context.cutoff,
            context_digest="0" * 64 if self.mismatch else context.digest,
            coverage=Coverage(observed=(), missing=("form",)),
            warnings=("synthetic uncalibrated probability",), includes_availability_risk=False)


def load_synthetic_provider(artifact: VerifiedArtifact) -> SyntheticProvider:
    data = json.loads(artifact.data)
    return SyntheticProvider(data["model_version"], data.get("mismatch", False))


def sleep_job(seconds):
    time.sleep(seconds)
    return seconds


def hold_job(marker):
    """Signal that this job holds its slot, then wait for release (bounded by the runner)."""
    Path(marker + ".started").touch()
    while not Path(marker + ".release").exists():
        time.sleep(0.01)
    return "held"


class PickleProbe:
    """Records whether a runner serialized it."""

    calls = 0

    def __reduce__(self):
        type(self).calls += 1
        return (PickleProbe, ())


def secret_failure_job(_):
    raise RuntimeError("upstream said key=" + os.environ.get("RAPID_API_APPLICATION_KEY", ""))


def partial_frame_job(_):
    """Send the header and a few bytes of a 1 MiB result frame, then stall."""
    import gc
    from multiprocessing.connection import Connection

    conn, = (o for o in gc.get_objects() if isinstance(o, Connection) and o.writable)
    os.write(conn.fileno(), struct.pack("!i", 1 << 20) + b"partial")
    time.sleep(60)


def large_result_job(size):
    return b"x" * size


def echo_job(value):
    return value


# --- fixtures -------------------------------------------------------------------


def evidence(source="synthetic"):
    return Provenance(source=source, source_version="fixture-v1", source_record_id="s",
                      observed_at=START, available_at=START, ingested_at=START)


def pid(number):
    return PlayerId(f"atp:p{number}")


def m6_draw():
    """64 slots, 56 entrants: seeds 1-8 have byes; player N is seeded N through 16."""
    event = Event(event_id=EventId("test:m6"), name="Synthetic M6", tour=Tour.ATP,
                  start_date=date(2026, 1, 2), end_date=date(2026, 1, 9), surface=Surface.HARD,
                  best_of=3, round_count=6, level="masters", provenance=evidence())
    slots, number = [], iter(range(1, 57))
    for position in range(1, 65):
        if position % 8 == 2:
            slots.append(DrawSlot(position=position, kind=EntryKind.BYE, player_id=None))
            continue
        player = next(number)
        slots.append(DrawSlot(position=position, kind=EntryKind.PLAYER, player_id=pid(player),
                              seed=player if player <= 16 else None))
    return Draw(event=event, slots=tuple(slots), provenance=evidence())


def rankings(draw):
    return [RankingSnapshot(player_id=s.player_id, tour=Tour.ATP, ranking_date=date(2026, 1, 1),
                            rank=int(s.player_id.split("p")[-1]), points=None,
                            provenance=evidence()).to_dict()
            for s in draw.slots if s.player_id is not None]


@pytest.fixture
def legacy_root(tmp_path):
    root = tmp_path / "data"
    tournament = root / "2024" / "wimby2024"
    tournament.mkdir(parents=True)
    (tournament / "players_male.json").write_text(json.dumps({
        "Synthetic Beta": {"seed": 2, "cost": 250}, "Synthetic Alpha": {"seed": 1},
        "Synthetic Gamma": {"seed": 3, "cost": 100, "p_factor": 0.01},
    }), encoding="utf-8")
    (tournament / "bracket_male.txt").write_text(
        "Singles R1 Upcoming Court Synthetic Alpha vs Synthetic Beta\n", encoding="utf-8")
    (root / "2024" / "empty").mkdir()
    return root


def write_artifacts(pool_root, artifacts):
    directory = pool_root / "artifacts"
    directory.mkdir(mode=0o700, exist_ok=True)
    entries = []
    for name, payload in artifacts.items():
        data = json.dumps(payload).encode()
        (directory / f"{name}.json").write_bytes(data)
        entries.append({"name": name, "file": f"{name}.json", "kind": "synthetic-table",
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    manifest = json.dumps({"schema_version": 1, "artifacts": entries}).encode()
    (directory / "manifest.json").write_bytes(manifest)
    return hashlib.sha256(manifest).hexdigest()


def synthetic_registry():
    players = tuple(Player(player_id=PlayerId(f"fixture:p{i}"), display_name=f"Player {i}",
                           tour=Tour.ATP, provenance=evidence("local_upload"))
                    for i in range(1, 130))
    return IdentityRegistry(
        revision="synthetic-review-1", players=players,
        aliases=tuple(ReviewedAlias(source="local_upload", player_id=p.player_id, tour=Tour.ATP,
                                    name=p.display_name, reviewed_by="fixture-reviewer",
                                    reviewed_at=START, provenance=evidence("local_upload"))
                      for p in players))


def slam_event():
    return Event(event_id=EventId("fixture:event"), name="Australie", tour=Tour.ATP,
                 start_date=date(2026, 1, 10), end_date=date(2026, 1, 20), surface=Surface.HARD,
                 best_of=5, round_count=7, level="grand_slam", provenance=evidence())


@pytest.fixture
def pool_root(tmp_path):
    root = tmp_path / "pool"
    root.mkdir(mode=0o700)
    (root / "registry.json").write_text(json.dumps(synthetic_registry().to_dict()))
    (root / "events.json").write_text(json.dumps(
        {"schema_version": 1, "events": {"australian_open": slam_event().to_dict(),
                                         "monte_carlo": m6_draw().event.to_dict()}}))
    write_artifacts(root, {"synthetic-v1": {"model_version": "synthetic-1"},
                           "mismatched": {"model_version": "bad", "mismatch": True}})
    return root


def make_config(legacy_root, pool_root=None, **kwargs):
    jobs = kwargs.pop("jobs", JobLimits(max_concurrent=2, timeout_seconds=60))
    return LocalAppConfig(data_root=legacy_root, pool_root=pool_root, jobs=jobs,
                          provider_loaders=LOADER, **kwargs)


@pytest.fixture
def services(legacy_root, pool_root):
    config = make_config(legacy_root, pool_root)
    return LocalServices(config, JobRunner(config.jobs, TEST_TARGETS))


@pytest.fixture
def client(services):
    app = server.create_app(services.config, services)
    with app.test_client() as test_client:
        yield test_client


def match_payload(**overrides):
    payload = {"tournament_path": "2024/wimby2024", "gender": "male",
               "player1_name": "Synthetic Alpha", "player2_name": "Synthetic Beta",
               "sets_to_win": 2, "num_simulations": 20}
    payload.update(overrides)
    return payload


def xlsx_bytes():
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Draw"
    ws.append(["Draw", "Player", "Rank", "Seed"])
    for position in range(1, 129):
        ws.append([position, f"Player {position}", position, position if position <= 32 else None])
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    return buffer.getvalue()


# --- legacy routes now call services directly --------------------------------------


def test_legacy_routes_list_players_and_bracket(client):
    assert client.get("/api/tournaments").get_json() == [
        {"id": "2024/wimby2024", "name": "Wimbledon 2024", "has_male": True, "has_female": False}]
    players = client.get("/api/players/2024/wimby2024/male").get_json()
    assert [p["name"] for p in players] == ["Synthetic Alpha", "Synthetic Beta", "Synthetic Gamma"]
    assert players[0] == {"name": "Synthetic Alpha", "seed": 1, "cost": 0, "p_factor": 0,
                          "n_factor": 0}
    assert client.get("/api/bracket/2024/wimby2024/male").get_json()["matches"] == [
        {"round": "R1", "status": "Upcoming", "player1": "Synthetic Alpha",
         "player2": "Synthetic Beta"}]


@pytest.mark.parametrize("url,code", [
    ("/api/players/2024/wimby2024/female", "players_file_not_found"),
    ("/api/bracket/2024/wimby2024/female", "bracket_file_not_found"),
    ("/api/players/2024/unknown/male", "players_file_not_found"),
    ("/api/players/2024/wimby2024/other", "invalid_gender"),
])
def test_missing_legacy_data_is_a_coded_404(client, url, code):
    response = client.get(url)
    assert response.get_json() == {"error": code}
    assert response.status_code in (404, 422)


def test_match_simulation_is_a_seeded_bounded_job_without_subprocess(client, monkeypatch):
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("no subprocess orchestration")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    first = client.post("/api/simulate-match", json=match_payload(seed=7))
    again = client.post("/api/simulate-match", json=match_payload(seed=7))
    assert first.status_code == 200, first.get_json()
    result = first.get_json()
    assert result == again.get_json()
    assert result["player1_wins"] + result["player2_wins"] == 20
    assert result["seed"] == 7
    assert result["win_estimate"]["validated"] is False
    assert result["detailed_forecast"]["status"] == "unavailable"
    team = client.post("/api/optimize-team", json={
        "tournament_path": "2024/wimby2024", "gender": "male", "team_size": 2, "budget": 300})
    assert team.status_code == 200, team.get_json()
    assert team.get_json()["total_cost"] <= 300
    assert len(team.get_json()["team_roster"]) == 2


# --- path traversal ------------------------------------------------------------------


@pytest.mark.parametrize("tournament", [
    "../2024/wimby2024", "2024/../wimby2024", "2024/wimby2024/..", "/etc/passwd",
    "2024/wimby2024/../../..", "2024\\wimby2024", "2024/WIMBY2024", "2024/wimby2024\x00",
    "1999/wimby2024", 5, None,
])
def test_tournament_ids_never_become_paths(services, tournament):
    with pytest.raises(ServiceError) as caught:
        services.catalog.players(tournament, Gender.MALE)
    assert caught.value.code == "unknown_tournament"
    with pytest.raises(ServiceError):
        services.simulate_match(match_payload(tournament_path=tournament))


@pytest.mark.parametrize("url", [
    "/api/players/2024/..%2f..%2fpool/male", "/api/players/2024/%2e%2e/male",
    "/api/players/..%2F/wimby2024/male", "/api/bracket/2024/wimby2024/..%2fmale",
    "/server.py", "/config.py", "/..%2fpyproject.toml", "/%2e%2e/pyproject.toml",
    "/api/players/2024/wimby2024/../../../etc/male",
])
def test_routes_refuse_traversal(client, url):
    # Werkzeug may first redirect to a normalized path; the target is still refused.
    response = client.get(url, follow_redirects=True)
    assert response.status_code in (404, 422), url
    assert set(response.get_json()) == {"error"}


def test_symlinks_below_the_root_are_refused(tmp_path, legacy_root):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "players_male.json").write_text(json.dumps({"Leak": {"seed": 1}}))
    (legacy_root / "2024" / "linked").symlink_to(outside, target_is_directory=True)
    linked_file = legacy_root / "2024" / "filelink"
    linked_file.mkdir()
    (linked_file / "players_male.json").symlink_to(outside / "players_male.json")
    catalog = LegacyCatalog(legacy_root)
    assert [t["id"] for t in catalog.tournaments()] == ["2024/wimby2024"]
    for tournament in ("2024/linked", "2024/filelink"):
        with pytest.raises(ServiceError) as caught:
            catalog.players(tournament, Gender.MALE)
        assert caught.value.code == "unsafe_path"


def test_oversize_and_malformed_legacy_files_are_refused(legacy_root):
    players = legacy_root / "2024" / "wimby2024" / "players_male.json"
    catalog = LegacyCatalog(legacy_root)
    players.write_text("{invalid")
    with pytest.raises(ServiceError, match="invalid_player_data"):
        catalog.players("2024/wimby2024", Gender.MALE)
    players.write_text(json.dumps({"A": {"seed": 1, "cost": float("nan")}}).replace("NaN", "1e999"))
    with pytest.raises(ServiceError, match="invalid_player_data"):
        catalog.players("2024/wimby2024", Gender.MALE)
    players.write_text(json.dumps({"A": {"seed": True}}))
    with pytest.raises(ServiceError, match="invalid_player_data"):
        catalog.players("2024/wimby2024", Gender.MALE)
    players.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ServiceError) as caught:
        catalog.players("2024/wimby2024", Gender.MALE)
    assert (caught.value.code, caught.value.status) == ("data_file_too_large", 413)


# --- invalid inputs and unbounded counts --------------------------------------------------


@pytest.mark.parametrize("overrides,code", [
    ({"num_simulations": 10 ** 9}, "invalid_num_simulations"),
    ({"num_simulations": 10 ** 100}, "invalid_num_simulations"),
    ({"num_simulations": 20_001}, "invalid_num_simulations"),
    ({"num_simulations": 0}, "invalid_num_simulations"),
    ({"num_simulations": -5}, "invalid_num_simulations"),
    ({"num_simulations": 1e3}, "invalid_num_simulations"),
    ({"num_simulations": "500"}, "invalid_num_simulations"),
    ({"num_simulations": True}, "invalid_num_simulations"),
    ({"sets_to_win": 5}, "invalid_sets_to_win"),
    ({"surface": "ice"}, "invalid_surface"),
    ({"seed": -1}, "invalid_seed"),
    ({"gender": "other"}, "invalid_gender"),
    ({"player2_name": "Synthetic Alpha"}, "invalid_players"),
    ({"player2_name": "Nobody"}, "unknown_player"),
    ({"player1_name": ["list"]}, "invalid_players"),
    ({"unexpected": 1}, "unknown_field"),
])
def test_invalid_match_requests_are_refused_with_codes(client, overrides, code):
    response = client.post("/api/simulate-match", json=match_payload(**overrides))
    assert response.status_code in (400, 404, 422)
    assert response.get_json() == {"error": code}


@pytest.mark.parametrize("body,content_type,status,code", [
    ("not json", "application/json", 400, "invalid_json"),
    ("[1, 2]", "application/json", 400, "invalid_json"),
    (json.dumps(match_payload()), "text/plain", 415, "json_required"),
    ("x" * (1024 * 1024 + 1), "application/json", 413, "payload_too_large"),
])
def test_request_bodies_are_typed_and_bounded(client, body, content_type, status, code):
    response = client.post("/api/simulate-match", data=body, content_type=content_type)
    assert (response.status_code, response.get_json()) == (status, {"error": code})


def test_team_and_tournament_sizes_are_bounded(client):
    response = client.post("/api/optimize-team", json={
        "tournament_path": "2024/wimby2024", "gender": "male", "team_size": 4})
    assert response.get_json() == {"error": "invalid_team_size"}
    response = client.post("/api/optimize-team", json={
        "tournament_path": "2024/wimby2024", "gender": "male", "budget": 10 ** 12, "team_size": 2})
    assert response.get_json() == {"error": "invalid_budget"}
    draw = m6_draw()
    for simulations in (20_001, 10 ** 12, 0):
        response = client.post("/api/pool/scenarios", json={
            "artifact": "synthetic-v1", "draw": draw.to_dict(), "kind": "m6",
            "cutoff": CUTOFF.isoformat(), "simulations": simulations})
        assert response.get_json() == {"error": "invalid_simulations"}


@pytest.mark.parametrize("change,code", [
    ({"draw": {"schema_version": 1}}, "invalid_draw"),
    ({"draw": "draw"}, "invalid_draw"),
    ({"cutoff": "2026-01-01T01:00:00"}, "invalid_cutoff"),
    ({"cutoff": "yesterday"}, "invalid_cutoff"),
    ({"kind": "atp500"}, "invalid_kind"),
    ({"withdrawal_probabilities": {"atp:p1": 1.5}}, "invalid_withdrawal_probabilities"),
    ({"withdrawal_probabilities": {"atp:p1": 10 ** 400}}, "invalid_withdrawal_probabilities"),
    ({"withdrawal_probabilities": {"atp:p999": 0.1}}, "invalid_withdrawal_probabilities"),
    ({"withdrawal_probabilities": {f"atp:p{i}": 0.1 for i in range(200)}},
     "invalid_withdrawal_probabilities"),
    ({"allow_provisional": "yes"}, "invalid_allow_provisional"),
    ({"artifact": "../manifest"}, "unknown_artifact"),
    ({"register_path": "/tmp/register.json"}, "unknown_field"),
])
def test_invalid_pool_requests_are_refused(client, change, code):
    payload = {"artifact": "synthetic-v1", "draw": m6_draw().to_dict(), "kind": "m6",
               "cutoff": CUTOFF.isoformat(), "simulations": 10}
    payload.update(change)
    response = client.post("/api/pool/scenarios", json=payload)
    assert response.get_json() == {"error": code}


# --- pool services: scenarios, recommendations, prediction, preview ------------------------


def test_pool_scenarios_and_recommendations_keep_strict_rule_gating(client):
    draw = m6_draw()
    payload = {"artifact": "synthetic-v1", "draw": draw.to_dict(), "kind": "m6",
               "cutoff": CUTOFF.isoformat(), "simulations": 40, "seed": 3,
               "rankings": rankings(draw)}
    strict = client.post("/api/pool/scenarios", json=payload)
    assert (strict.status_code, strict.get_json()) == (409, {"error": "rules_unresolved"})
    payload["allow_provisional"] = True
    first = client.post("/api/pool/scenarios", json=payload)
    assert first.status_code == 200, first.get_json()
    result = first.get_json()
    assert result == client.post("/api/pool/scenarios", json=payload).get_json()
    assert result["assumptions"]["seed"] == 3 and result["assumptions"]["simulations"] == 40
    assert result["artifact_sha256"] == hashlib.sha256(
        json.dumps({"model_version": "synthetic-1"}).encode()).hexdigest()
    assert len(result["players"]) == 56
    recommended = client.post("/api/pool/recommend", json={**payload, "event_id": "monte_carlo"})
    assert recommended.status_code == 200, recommended.get_json()
    body = recommended.get_json()
    assert body["scenario_digest"] == result["digest"]
    objectives = [r["objective"] for r in body["recommendations"]["recommendations"]]
    assert objectives == ["expected_points", "robust"]
    assert len(body["recommendations"]["skipped"]) == 2  # no rival field or payout supplied
    strict_recommend = client.post("/api/pool/recommend", json={
        **payload, "allow_provisional": False, "event_id": "monte_carlo"})
    assert strict_recommend.get_json() == {"error": "rules_unresolved"}
    assert "provisional" in {d["status"] for d in result["rules"]["decisions"]}
    for event_id, kind, code in (("atlantis", "m6", "unknown_event"),
                                 ("australian_open", "m6", "draw_event_mismatch"),
                                 ("monte_carlo", "m7", "kind_event_mismatch")):
        refused = client.post("/api/pool/recommend",
                              json={**payload, "event_id": event_id, "kind": kind})
        assert refused.get_json() == {"error": code}, event_id


def test_prediction_uses_only_verified_artifacts(client, pool_root):
    draw = m6_draw()
    context = PredictionContext(event=draw.event, player1_id=pid(1), player2_id=pid(9),
                                round_number=1, cutoff=CUTOFF)
    response = client.post("/api/predict", json={"artifact": "synthetic-v1",
                                                 "context": context.to_dict()})
    assert response.status_code == 200, response.get_json()
    prediction = MatchProbability.from_dict(response.get_json()["prediction"])
    prediction.require_context(context)
    assert prediction.calibration_version is None
    mismatch = client.post("/api/predict", json={"artifact": "mismatched",
                                                 "context": context.to_dict()})
    assert mismatch.get_json() == {"error": "provider_context_mismatch"}
    bad = client.post("/api/predict", json={"artifact": "synthetic-v1", "context": {"x": 1}})
    assert bad.get_json() == {"error": "invalid_prediction_context"}
    # Replacing the artifact bytes after the manifest pinned them is refused.
    (pool_root / "artifacts" / "synthetic-v1.json").write_text(
        json.dumps({"model_version": "synthetic-2"}))
    tampered = client.post("/api/predict", json={"artifact": "synthetic-v1",
                                                 "context": context.to_dict()})
    assert (tampered.status_code, tampered.get_json()) == (409, {"error": "artifact_digest_mismatch"})


def test_artifact_store_refuses_untrusted_locations_and_manifests(tmp_path):
    root = tmp_path / "pool"
    root.mkdir(mode=0o700)
    pin = write_artifacts(root, {"model": {"model_version": "synthetic-1"}})
    directory = root / "artifacts"
    loaders = dict(LOADER)

    def store(manifest_sha256=None):
        return ArtifactStore.from_pool_root(root, loaders=loaders,
                                            manifest_sha256=manifest_sha256, max_bytes=1024)

    reference = store(pin).resolve("model")
    assert reference.loader == LOADER[0][1] and reference.spec.size > 0
    artifact = store(pin).load("model")
    assert artifact.sha256 == reference.sha256 and "data" not in repr(artifact)
    assert isinstance(load_provider(reference), SyntheticProvider)
    with pytest.raises(ServiceError, match="no_provider_loader"):
        load_provider(replace(reference, loader="missing_module_xyz:load"))
    with pytest.raises(ServiceError, match="artifact_manifest_digest_mismatch"):
        store("0" * 64)
    with pytest.raises(ServiceError, match="unknown_artifact"):
        store().load("missing")
    with pytest.raises(ServiceError, match="no_provider_loader"):
        ArtifactStore.from_pool_root(root, loaders={}, manifest_sha256=None,
                                     max_bytes=1024).load("model")
    with pytest.raises(ServiceError, match="artifact_digest_mismatch"):
        VerifiedArtifact(name="model", kind="synthetic-table", sha256="0" * 64, data=b"{}")

    target = directory / "model.json"
    target.chmod(0o666)
    with pytest.raises(ServiceError, match="untrusted_file_permissions"):
        store().load("model")
    target.chmod(0o600)
    directory.chmod(0o777)
    with pytest.raises(ServiceError, match="untrusted_file_permissions"):
        store()
    directory.chmod(0o700)

    real = tmp_path / "elsewhere.json"
    real.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(real)
    with pytest.raises(ServiceError, match="unsafe_path"):
        store().load("model")

    # A symlinked artifacts folder is refused instead of followed out of the pool root.
    moved = tmp_path / "moved-artifacts"
    directory.rename(moved)
    directory.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ServiceError, match="unsafe_path"):
        store()
    directory.unlink()
    moved.rename(directory)

    manifest = json.loads((directory / "manifest.json").read_text())
    for bad in ("../model.json", "/etc/passwd", "sub/model.json", "manifest.json", ".hidden"):
        manifest["artifacts"][0]["file"] = bad
        (directory / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ServiceError, match="invalid_artifact_manifest"):
            store()


def test_workbook_upload_preview_is_bounded_and_returns_no_private_records(client, services):
    data = xlsx_bytes()
    url = "/api/workbooks/preview?event_id=australian_open&format=GS128"
    response = client.post(url, data=data, content_type="application/octet-stream")
    assert response.status_code == 200, response.get_json()
    summary = response.get_json()
    assert summary["upload_sha256"] == hashlib.sha256(data).hexdigest()
    assert len(Draw.from_dict(summary["draw"]).slots) == 128
    assert summary["private_season_records"] == {
        "picks": 0, "standings": 0, "banks": 0, "usage": 0, "substitutions": 0}
    oversize = client.post(url, data=b"\0" * (8 * 1024 * 1024 + 1),
                           content_type="application/octet-stream")
    assert (oversize.status_code, oversize.get_json()) == (413, {"error": "payload_too_large"})
    for query, code in (("event_id=atlantis&format=GS128", "unknown_event"),
                        ("event_id=australian_open&format=GS64", "invalid_format"),
                        ("event_id=australian_open&format=GS128&path=/etc", "unknown_field"),
                        ("event_id=australian_open&format=GS128&suffix=.exe", "invalid_suffix"),
                        ("event_id=australian_open&format=M7", "invalid_supplied_event_year_or_format")):
        refused = client.post("/api/workbooks/preview?" + query, data=data,
                              content_type="application/octet-stream")
        assert refused.get_json() == {"error": code}, query
    garbage = client.post(url, data=b"PK\x03\x04 not a workbook",
                          content_type="application/octet-stream")
    assert garbage.get_json()["error"] in ("invalid_workbook_or_metadata", "unsafe_xml")
    wrong_type = client.post(url, data=data, content_type="application/json")
    assert wrong_type.get_json() == {"error": "octet_stream_required"}

    small = make_config(services.config.data_root, services.config.pool_root,
                        workbook_limits=WorkbookLimits(file_bytes=1024, zip_bytes=4096))
    limited = LocalServices(small, services.runner)
    with pytest.raises(ServiceError) as caught:
        limited.preview_workbook(data, {"event_id": "australian_open", "format": "GS128"})
    assert (caught.value.code, caught.value.status) == ("file_byte_limit", 413)


def test_staged_upload_is_removed_even_when_the_job_times_out(services, monkeypatch):
    seen = []

    def timed_out(target, job):
        seen.append(Path(job.path))
        assert seen[-1].exists() and oct(seen[-1].stat().st_mode & 0o777) == "0o600"
        raise ServiceError("job_timeout", 504)

    monkeypatch.setattr(services.runner, "run", timed_out)
    with pytest.raises(ServiceError, match="job_timeout"):
        services.preview_workbook(xlsx_bytes(), {"event_id": "australian_open",
                                                 "format": "GS128"})
    assert seen and not seen[0].exists() and not seen[0].parent.exists()


# --- jobs: concurrency, time, size and determinism ---------------------------------------


def test_jobs_are_bounded_in_concurrency_and_time(tmp_path):
    runner = JobRunner(JobLimits(max_concurrent=1, timeout_seconds=60), TEST_TARGETS)
    marker = str(tmp_path / "hold")
    results = []
    worker = threading.Thread(
        target=lambda: results.append(runner.run("test_local_services:hold_job", marker)))
    worker.start()
    try:
        deadline = time.monotonic() + 30
        while not Path(marker + ".started").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert Path(marker + ".started").exists(), "the holding job never started"
        # The first job provably holds the only slot until it is released below.
        with pytest.raises(ServiceError) as busy:
            runner.run("test_local_services:echo_job", PickleProbe())
        assert (busy.value.code, busy.value.status) == ("busy", 429)
        assert PickleProbe.calls == 0  # refused before any serialization
        assert runner.enforced == {"cpu": None, "memory": None}  # no slot free to probe
    finally:
        Path(marker + ".release").touch()
        worker.join()
    assert results == ["held"]

    runner = JobRunner(JobLimits(max_concurrent=1, timeout_seconds=1), TEST_TARGETS)
    started = time.monotonic()
    with pytest.raises(ServiceError) as timeout:
        runner.run("test_local_services:sleep_job", 30)
    assert (timeout.value.code, timeout.value.status) == ("job_timeout", 504)
    assert time.monotonic() - started < 10
    assert runner.run("test_local_services:echo_job", 5) == 5  # the slot was released
    with pytest.raises(ValueError, match="Unregistered"):
        runner.run("os:system", "true")


def test_deadline_during_a_partial_result_is_a_timeout():
    runner = JobRunner(JobLimits(max_concurrent=1, timeout_seconds=1), TEST_TARGETS)
    started = time.monotonic()
    with pytest.raises(ServiceError) as caught:
        runner.run("test_local_services:partial_frame_job", None)
    assert (caught.value.code, caught.value.status) == ("job_timeout", 504)
    assert time.monotonic() - started < 10
    assert not multiprocessing.active_children()  # the stalled worker was reaped
    assert runner.run("test_local_services:echo_job", 3) == 3  # and its slot released


def test_job_payloads_and_results_are_bounded():
    runner = JobRunner(JobLimits(max_payload_bytes=4096, max_result_bytes=4096), TEST_TARGETS)
    with pytest.raises(ServiceError, match="payload_too_large"):
        runner.run("test_local_services:echo_job", b"x" * 10_000)
    with pytest.raises(ServiceError, match="result_too_large"):
        runner.run("test_local_services:large_result_job", 10_000)


def test_job_limits_and_configuration_are_deterministic(legacy_root):
    with pytest.raises(ValueError):
        JobLimits(max_concurrent=0)
    with pytest.raises(ValueError):
        JobLimits(timeout_seconds=10 ** 6)
    with pytest.raises(ValueError):
        LocalAppConfig(data_root=Path("relative"))
    environ = {"TENNIS_DATA_ROOT": str(legacy_root), "TENNIS_PORT": "5055",
               "RAPID_API_APPLICATION_KEY": SECRET, "TENNIS_MAX_SIMULATIONS": "999999999"}
    config = LocalAppConfig.from_env(environ)
    assert config == LocalAppConfig.from_env(environ)
    assert config.port == 5055 and config.max_match_simulations == 20_000
    assert SECRET not in json.dumps(config.limits())
    runner = JobRunner(config.jobs, TARGETS)
    enforced = runner.enforced
    assert enforced["cpu"] is True
    if sys.platform.startswith("linux"):
        assert enforced["memory"] is True
    job = MatchSimulationJob(*LegacyCatalog(legacy_root).players("2024/wimby2024", Gender.MALE)[:2],
                             sets_to_win=2, simulations=30, surface="clay", seed=11)
    target = "web_interface.services:match_simulation_job"
    assert runner.run(target, job) == runner.run(target, job)


# --- redaction and secrets ---------------------------------------------------------------


def test_internal_errors_are_redacted_and_never_log_secrets(client, services, monkeypatch, caplog,
                                                            capfd):
    monkeypatch.setenv("RAPID_API_APPLICATION_KEY", SECRET)

    def explode(*args, **kwargs):
        raise RuntimeError(f"failed reading /private/{SECRET}/players.json")

    monkeypatch.setattr(services, "tournaments", explode)
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/tournaments")
        with pytest.raises(ServiceError) as caught:
            services.runner.run("test_local_services:secret_failure_job", None)
    assert response.status_code == 500
    body = response.get_json()
    assert set(body) == {"error", "request_id"} and body["error"] == "internal_error"
    assert caught.value.code == "internal_error"
    captured = capfd.readouterr()
    for text in (response.get_data(as_text=True), caplog.text, captured.out, captured.err):
        assert SECRET not in text and "/private/" not in text
    assert "RuntimeError" in caplog.text + captured.err
    status = client.get("/api/status").get_data(as_text=True)
    assert SECRET not in status and str(services.config.data_root) not in status


# --- loopback-only app ----------------------------------------------------------------------


def test_app_rejects_foreign_hosts_and_cross_origin_posts(client):
    assert client.get("/api/tournaments", headers={"Host": "attacker.example"}).status_code == 400
    response = client.post("/api/simulate-match", json=match_payload(),
                           headers={"Origin": "http://attacker.example"})
    assert (response.status_code, response.get_json()) == (403, {"error": "cross_origin_request"})
    same = client.post("/api/simulate-match", json=match_payload(),
                       headers={"Origin": "http://127.0.0.1:5000"})
    assert same.status_code == 200


def test_one_command_starts_loopback_without_debugger(monkeypatch, legacy_root):
    calls = []
    monkeypatch.setattr("flask.Flask.run", lambda self, **kwargs: calls.append((self, kwargs)))
    monkeypatch.setenv("TENNIS_DATA_ROOT", str(legacy_root))
    monkeypatch.delenv("TENNIS_POOL_ROOT", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert server.main(["--port", "5123"]) == 0
    (app, kwargs), = calls
    assert kwargs == {"host": "127.0.0.1", "port": 5123, "debug": False, "use_reloader": False,
                      "use_debugger": False, "threaded": True}
    assert app.debug is False
    with pytest.raises(SystemExit):
        server.main(["--host", "0.0.0.0"])
    monkeypatch.setenv("TENNIS_POOL_ROOT", str(legacy_root / "missing"))
    assert server.main([]) == 2


# --- review regressions ----------------------------------------------------------------------


def test_unreadable_or_oversized_numbers_are_not_treated_as_missing(legacy_root, client):
    tournament = legacy_root / "2024" / "wimby2024"
    points = tournament / "player_points_male.json"
    points.write_text(json.dumps({"Synthetic Alpha": 10, "Synthetic Beta": 5}))
    points.chmod(0)
    try:
        if os.access(points, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        response = client.post("/api/optimize-team", json={
            "tournament_path": "2024/wimby2024", "gender": "male", "team_size": 2})
        assert (response.status_code, response.get_json()) == (503, {"error": "file_unreadable"})
    finally:
        points.chmod(0o644)
    (tournament / "players_male.json").write_text('{"A": {"seed": 1, "cost": 1' + "0" * 400 + "}}")
    response = client.get("/api/players/2024/wimby2024/male")
    assert (response.status_code, response.get_json()) == (422, {"error": "invalid_player_data"})


def test_legacy_team_search_keeps_size_budget_and_scored_players(legacy_root, client):
    tournament = legacy_root / "2024" / "wimby2024"
    (tournament / "players_male.json").write_text(json.dumps({
        "A": {"seed": 1, "cost": 10}, "B": {"seed": 2, "cost": 10},
        "C": {"seed": 3, "cost": 1}, "D": {"seed": 4, "cost": 1}}))
    request = {"tournament_path": "2024/wimby2024", "gender": "male"}
    for seed in range(5):
        team = client.post("/api/optimize-team", json={**request, "team_size": 3, "budget": 12,
                                                       "seed": seed}).get_json()
        assert len(team["team_roster"]) == 3 and team["total_cost"] <= 12
    too_small = client.post("/api/optimize-team", json={**request, "team_size": 2, "budget": 1})
    assert too_small.get_json() == {"error": "budget_too_small"}
    (tournament / "player_points_male.json").write_text(json.dumps({"A": 5, "Stale": 9}))
    stale = client.post("/api/optimize-team", json={**request, "team_size": 2, "budget": 100})
    assert stale.get_json() == {"error": "insufficient_scored_players"}


def test_method_errors_keep_allow_header(client):
    response = client.get("/api/simulate-match")
    assert response.status_code == 405
    assert response.get_json() == {"error": "method_not_allowed"}
    assert "POST" in response.headers["Allow"]


def test_explicit_port_wins_over_a_bad_environment_port(monkeypatch, legacy_root):
    calls = []
    monkeypatch.setattr("flask.Flask.run", lambda self, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("TENNIS_DATA_ROOT", str(legacy_root))
    monkeypatch.delenv("TENNIS_POOL_ROOT", raising=False)
    monkeypatch.setenv("TENNIS_PORT", "bad")
    assert server.main(["--port", "5050"]) == 0 and calls[-1]["port"] == 5050
    assert server.main([]) == 2

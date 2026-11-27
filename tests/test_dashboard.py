"""Pool dashboard routes over synthetic season inputs built at runtime (no real entries)."""

from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime, timedelta, timezone

import pytest

from tennis_api.models.canonical import Player, PlayerId, Provenance, Tour
from tennis_api.models.identity import IdentityRegistry
from tennis_pool.ledger import (
    Accepted, Band, EventPoints, EventTerms, LedgerRecord, Pair, SeasonLedger, Selection, Submitted,
)
from tennis_pool.rivals import KnownPick
from tennis_pool.rules import ProvisionalRulesWarning
from tennis_pool.season import FutureEvent, Prospect
from test_local_services import (  # noqa: F401 - fixtures are used by name
    TEST_TARGETS, legacy_root, m6_draw, make_config, pool_root, rankings,
)
from web_interface import server
from web_interface.dashboard import build_ledger, decision_baseline, entry_states, parse_season
from web_interface.errors import ServiceError
from web_interface.jobs import JobRunner
from web_interface.services import LocalServices

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = START + timedelta(hours=6)
DEADLINE = START + timedelta(hours=20)
OWN = "entry:own"
RIVALS = tuple(f"entry:r{i:02d}" for i in range(1, 40))


def at(hours):
    return START + timedelta(hours=hours)


def evidence(hours=0, key="synthetic"):
    return Provenance(source="synthetic", source_version="fixture-v1", source_record_id=key,
                      observed_at=at(hours), available_at=at(hours), ingested_at=at(hours))


def pid(number):
    return PlayerId(f"atp:p{number}")


def band(number):
    return (Band.TOP4 if number <= 4 else Band.TOP8 if number <= 8
            else Band.TOP16 if number <= 16 else Band.UNSEEDED)


def pair(primary, substitute=None):
    return Pair(primary=Selection(player_id=pid(primary), band=band(primary)),
                substitute=None if substitute is None
                else Selection(player_id=pid(substitute), band=band(substitute)))


CALENDAR = (
    EventTerms(event_id="indian_wells", deadline=at(2), provenance=evidence(0, "iw")),
    EventTerms(event_id="monte_carlo", deadline=DEADLINE, provenance=evidence(0, "mc")),
    EventTerms(event_id="madrid", deadline=at(24 * 40), provenance=evidence(0, "ma")),
)
SHEETS = {
    OWN: (pair(1, 2), pair(5), pair(9), pair(20), pair(21)),
    "entry:r01": (pair(2), pair(6), pair(10), pair(22), pair(23)),
    "entry:r02": (pair(1), pair(5), pair(11), pair(24), pair(25)),
}
POINTS = {OWN: 300, "entry:r01": 450, "entry:r02": 120}


def records():
    """Submitted, accepted and audited Indian Wells sheets for three entries."""
    out = []
    for entry, picks in SHEETS.items():
        out.append(LedgerRecord(
            record_id=f"sub-{entry}", entry_id=entry, event_id="indian_wells",
            effective_at=at(1), evidence=evidence(1, f"sub-{entry}"),
            payload=Submitted(picks=picks, submitted_at=at(1), excel=True)))
        out.append(LedgerRecord(
            record_id=f"acc-{entry}", entry_id=entry, event_id="indian_wells",
            effective_at=at(1.5), evidence=evidence(1.5, f"acc-{entry}"),
            payload=Accepted(submission_id=f"sub-{entry}", approved_by="fixture-commissioner")))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalRulesWarning)
        ledger = SeasonLedger.create(CALENDAR, allow_provisional=True).append(*out)
    digests = {s.entry_id: s.accounting_digest for s in ledger.replay(at(3)).events}
    for entry, points in POINTS.items():
        out.append(LedgerRecord(
            record_id=f"pts-{entry}", entry_id=entry, event_id="indian_wells",
            effective_at=at(3), evidence=evidence(3, f"pts-{entry}"),
            payload=EventPoints(points=points, accounting_digest=digests[entry])))
    return out


def prospects(event_id):
    return FutureEvent(event_id=event_id, available_at=at(0), prospects=tuple(
        Prospect(player_id=pid(i), entry_probability=0.9, rank=float(i),
                 mean_points=max(5.0, 120.0 - 4 * i)) for i in range(1, 57))).to_dict()


def season_document(**overrides):
    document = {
        "schema_version": 1, "entry_id": OWN, "entries": [OWN, *RIVALS],
        "events": [t.to_dict() for t in CALENDAR],
        "records": [r.to_dict() for r in records()],
        "known_picks": [KnownPick(entry_id="entry:r01", event_id="monte_carlo", pair=pair(3),
                                  provenance=evidence(4, "kp")).to_dict()],
        "future": [prospects("madrid")],
    }
    document.update(overrides)
    return document


def draw_registry():
    players = tuple(Player(player_id=pid(i), display_name=f"Synthetic {i}", tour=Tour.ATP,
                           provenance=evidence()) for i in range(1, 57))
    return IdentityRegistry(revision="synthetic-draw-review", players=players)


@pytest.fixture
def season_root(pool_root):
    (pool_root / "registry.json").write_text(json.dumps(draw_registry().to_dict()))
    (pool_root / "season.json").write_text(json.dumps(season_document()))
    return pool_root


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def services(legacy_root, season_root, clock):  # noqa: F811
    config = make_config(legacy_root, season_root)
    return LocalServices(config, JobRunner(config.jobs, TEST_TARGETS), clock=clock)


@pytest.fixture
def client(services):
    app = server.create_app(services.config, services)
    with app.test_client() as test_client:
        yield test_client


def decision_payload(**overrides):
    draw = m6_draw()
    payload = {"artifact": "synthetic-v1", "draw": draw.to_dict(), "event_id": "monte_carlo",
               "simulations": 120, "seed": 5, "rankings": rankings(draw),
               "allow_provisional": True}
    payload.update(overrides)
    return payload


def test_season_view_reports_banks_uses_standings_and_gaps(client):
    strict = client.post("/api/pool/season", json={"event_id": "monte_carlo"})
    assert (strict.status_code, strict.get_json()) == (409, {"error": "rules_unresolved"})
    response = client.post("/api/pool/season",
                           json={"event_id": "monte_carlo", "allow_provisional": True})
    assert response.status_code == 200, response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert body["mode"] == "decision" and body["deadline"] == DEADLINE.isoformat()
    own = body["own"]
    assert own["bank_kind"] == "masters" and own["season_points"] == 300
    # Indian Wells used one 1-4, one 5-8 and one 9-16 Masters token.
    assert [b["remaining"] for b in own["bank"]] == [8, 8, 8, 7]
    assert {u["player_id"]: u["remaining"] for u in own["usage"]}[pid(1)] == 4
    standings = body["standings"]
    assert [s["entry_id"] for s in standings[:3]] == ["entry:r01", OWN, "entry:r02"]
    assert standings[0]["gap"] == -150 and standings[2]["gap"] == 180
    assert len(standings) == 40 and standings[-1]["rank"] == 4  # tied entries share a rank
    assert [c["status"] for c in body["calendar"]] == ["past", "current", "upcoming"]
    assert body["calendar"][0]["accepted"] is True
    assert body["event"]["accepted"] is False
    assert body["names"] == {pid(n): f"Synthetic {n}" for n in (1, 5, 9, 20, 21)}  # unused substitute p2 has no use


def test_decision_explains_pairs_rivals_preservation_and_versions(client):
    response = client.post("/api/pool/decision", json=decision_payload(
        compare=[p.to_dict() for p in (pair(1, 2), pair(5), pair(9), pair(20), pair(21))]))
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["mode"] == "decision" and "guaranteed" in body["notice"]
    assert body["starts_at"] == "2026-01-02T00:00:00+00:00"
    recommendation = body["recommendation"]
    assert recommendation["objective"] == "expected_points"
    assert len(recommendation["best"]["pairs"]) == 5
    metrics = recommendation["best"]["metrics"]
    assert metrics["points_se"] > 0 and metrics["p_top3"] is not None
    assert metrics["expected_payout_cents"] is not None  # 40 participants: printed schedule
    assert all("tie_with_best" in c for c in recommendation["alternatives"])
    # Exact versus estimated rivals are kept apart.
    statuses = {r["entry_id"]: r["status"] for r in body["rivals"]["rivals"]}
    assert statuses["entry:r01"] == "partial" and statuses["entry:r02"] == "estimated"
    assert statuses["entry:r03"] == "no_history"
    owned = {o["player_id"]: o for o in body["rivals"]["ownership"]}
    assert owned[pid(3)]["known"] == 1
    # Preservation advice comes from season planning over the later event.
    plan = body["plan"]
    assert plan["chosen"] in {"greedy", "rationed", "horizon"}
    assert plan["use_costs"] and all("advice" in c for c in plan["use_costs"])
    assert plan["token_costs"] and plan["projections"][0]["rival_gaps"]
    versions = body["versions"]
    assert versions["artifact"] == "synthetic-v1" and len(versions["artifact_sha256"]) == 64
    assert versions["rules"]["register_version"]
    provider = body["provider"]
    assert provider["uncalibrated"] is True and provider["predictions"] > 0
    assert provider["missing_coverage"] == [{"value": "form", "count": provider["predictions"]}]
    assert any("news" in w for w in body["coverage_warnings"])
    compare = body["compare"]
    assert compare["legal"] is True and "expected_points_vs_best" in compare
    assert len(body["names"]) == 56 and body["names"][pid(1)] == "Synthetic 1"
    assert body["season"]["own"]["season_points"] == 300


def test_decision_is_refused_after_the_deadline_and_monitoring_remains(client, clock):
    clock.now = DEADLINE
    refused = client.post("/api/pool/decision", json=decision_payload())
    assert (refused.status_code, refused.get_json()) == (409, {"error": "deadline_passed"})
    legacy = client.post("/api/pool/recommend", json={
        **decision_payload(), "kind": "m6", "cutoff": NOW.isoformat()})
    assert legacy.get_json() == {"error": "deadline_passed"}
    season = client.post("/api/pool/season",
                         json={"event_id": "monte_carlo", "allow_provisional": True})
    assert season.status_code == 200 and season.get_json()["mode"] == "monitoring"


@pytest.mark.parametrize(("change", "code"), [
    ({"cutoff": (NOW + timedelta(minutes=1)).isoformat()}, "invalid_cutoff"),
    ({"cutoff": "2026-01-01T03:00:00"}, "invalid_cutoff"),
    ({"objective": "win_everything"}, "invalid_objective"),
    ({"season_objective": "glory"}, "invalid_season_objective"),
    ({"compare": [pair(1).to_dict()]}, "invalid_compare"),
    ({"compare": [{"primary": "atp:p1"}] * 5}, "invalid_compare"),
    ({"kind": "m7"}, "kind_event_mismatch"),
    ({"rankings": []}, "rankings_missing"),
    ({"event_id": "australian_open"}, "event_terms_missing"),
    ({"event_id": "atlantis"}, "unknown_event"),
    ({"register_path": "/tmp/register.json"}, "unknown_field"),
    ({"season_path": "/tmp/season.json"}, "unknown_field"),
    ({"allow_provisional": False}, "rules_unresolved"),
])
def test_invalid_decision_requests_are_refused_with_codes(client, change, code):
    response = client.post("/api/pool/decision", json=decision_payload(**change))
    assert response.get_json() == {"error": code}


def test_unavailable_objectives_and_missing_prospects_are_explicit(services, season_root):
    small = season_document(entries=[OWN, "entry:r01", "entry:r02"], future=[])
    (season_root / "season.json").write_text(json.dumps(small))
    with pytest.raises(ServiceError) as refused:
        services.decision(decision_payload(objective="expected_payout"))
    assert refused.value.code == "objective_unavailable"
    body = services.decision(decision_payload())
    assert body["plan"] is None
    assert any("Season planning skipped" in w for w in body["coverage_warnings"])
    assert any("payout schedule for 3" in w for w in body["coverage_warnings"])


@pytest.mark.parametrize("document", [
    {"schema_version": 2},
    {"schema_version": 1, "entry_id": "../x", "events": [], "records": []},
    {"schema_version": 1, "entry_id": OWN, "events": [], "records": []},
    {"schema_version": 1, "entry_id": OWN, "events": [{"event_id": "x"}], "records": []},
    {"schema_version": 1, "entry_id": OWN, "events": [], "records": [], "path": "/tmp"},
])
def test_season_inputs_are_validated(document):
    with pytest.raises(ServiceError) as refused:
        parse_season(document)
    assert refused.value.code == "invalid_season_input"


def test_season_errors_are_coded_and_private_data_is_never_logged(
        client, season_root, caplog):
    caplog.set_level(logging.DEBUG)
    (season_root / "season.json").unlink()
    missing = client.post("/api/pool/season",
                          json={"event_id": "monte_carlo", "allow_provisional": True})
    assert missing.get_json() == {"error": "season_input_missing"}
    broken = season_document()
    broken["records"].append({**broken["records"][1], "record_id": "acc-again"})
    (season_root / "season.json").write_text(json.dumps(broken))
    response = client.post("/api/pool/season",
                           json={"event_id": "monte_carlo", "allow_provisional": True})
    assert response.get_json() == {"error": "invalid_season_input"}
    assert "entry:" not in caplog.text and "atp:p" not in caplog.text


def test_locked_sheet_legality_is_checked_against_the_season_state(services):
    mismatched = (pair(1, 20), pair(5), pair(9), pair(22), pair(21))  # 1-4 primary, unseeded sub
    body = services.decision(decision_payload(compare=[p.to_dict() for p in mismatched]))
    compare = body["compare"]
    assert compare["legal"] is False and compare["problems"]
    assert compare["same_as_best"] is False


def test_dashboard_script_is_served_and_renders_without_html_injection(client):
    response = client.get("/dashboard.js")
    assert response.status_code == 200
    script = response.get_data(as_text=True)
    # Labels come from files and requests: render text only, keep private data in memory.
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "localStorage",
                      "sessionStorage", "eval("):
        assert forbidden not in script
    page = client.get("/").get_data(as_text=True)
    assert 'src="dashboard.js"' in page and 'id="pool-dashboard"' in page


def test_a_locked_sheet_with_a_player_out_of_the_draw_is_stale_not_fatal(services):
    gone = (pair(57), pair(5), pair(9), pair(20), pair(21))  # atp:p57 is not in the draw
    body = services.decision(decision_payload(compare=[p.to_dict() for p in gone]))
    assert len(body["recommendation"]["best"]["pairs"]) == 5
    compare = body["compare"]
    assert compare["scorable"] is False and compare["metrics"] is None
    assert compare["legal"] is False and compare["problems"]


def accepted_for_monte_carlo(picks):
    return [
        LedgerRecord(record_id="sub-own-mc", entry_id=OWN, event_id="monte_carlo",
                     effective_at=at(4), evidence=evidence(4, "sub-own-mc"),
                     payload=Submitted(picks=picks, submitted_at=at(4), excel=True)),
        LedgerRecord(record_id="acc-own-mc", entry_id=OWN, event_id="monte_carlo",
                     effective_at=at(4.5), evidence=evidence(4.5, "acc-own-mc"),
                     payload=Accepted(submission_id="sub-own-mc",
                                      approved_by="fixture-commissioner")),
    ]


def test_decisions_start_from_the_state_before_this_events_accepted_sheet(
        services, season_root):
    sheet = (pair(1, 2), pair(5), pair(9), pair(20), pair(21))
    document = season_document()
    document["records"] += [r.to_dict() for r in accepted_for_monte_carlo(sheet)]
    (season_root / "season.json").write_text(json.dumps(document))
    season = parse_season(document)
    ledger = build_ledger(season, True)
    before = entry_states(season, ledger.replay(at(3.9)))[OWN]
    snapshot = ledger.replay(NOW)
    after = entry_states(season, snapshot)[OWN]
    assert after.masters != before.masters and after.usage != before.usage
    assert after.qualifying_events == ("indian_wells", "monte_carlo")
    assert decision_baseline(after, snapshot, "monte_carlo") == before
    assert decision_baseline(after, snapshot, "madrid") == after
    # The accepted sheet itself stays legal when re-checked as a locked sheet.
    body = services.decision(decision_payload(compare=[p.to_dict() for p in sheet]))
    assert body["compare"]["legal"] is True
    assert body["season"]["event"]["accepted"] is True

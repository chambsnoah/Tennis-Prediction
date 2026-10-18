"""Synthetic behavioral tests at the observation/import/as-of public seams."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from tennis_api.models.canonical import EventId, Player, PlayerId, Provenance, Tour
from tennis_api.models.identity import (
    IdentityRegistry,
    IdentityResolutionError,
    ProviderMapping,
    ReviewedAlias,
)
from tennis_api.models.information import (
    AdjustmentUnit,
    AnalystOpinion,
    InjuryRisk,
    MarketAdjustment,
    Observation,
    VerifiedWithdrawal,
)


NOW = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
PLAYER = PlayerId("player:synthetic-1")
EVENT = EventId("event:synthetic-2026")


def evidence(**changes):
    return replace(
        Provenance(
            source="synthetic",
            source_version="source-r1",
            source_record_id="record-1",
            observed_at=NOW - timedelta(hours=3),
            available_at=NOW - timedelta(hours=2),
            ingested_at=NOW - timedelta(hours=1),
        ),
        **changes,
    )


def observation(**changes):
    return replace(
        Observation(
            player_id=PLAYER,
            event_id=EVENT,
            tour=Tour.ATP,
            record_version=1,
            provenance=evidence(),
            citation="synthetic://report/1",
            certainty=0.8,
            effective_at=NOW - timedelta(hours=2),
            expires_at=NOW + timedelta(days=1),
            payload=AnalystOpinion(text="Synthetic opinion, not a measurement"),
            registry_revision="registry-r1",
            registry_digest="a" * 64,
        ),
        **changes,
    )


@pytest.mark.parametrize(
    "payload",
    [
        AnalystOpinion(text="Uncertain form"),
        VerifiedWithdrawal(withdrawn=False),
        InjuryRisk(probability=0.25),
        MarketAdjustment(
            value=-2,
            unit=AdjustmentUnit.PERCENTAGE_POINTS,
            provenance=evidence(source_record_id="market-method"),
        ),
    ],
)
def test_validated_typed_observation_json_roundtrip(payload):
    item = observation(payload=payload)
    decoded = Observation.from_dict(json.loads(json.dumps(item.to_dict())))
    assert decoded == item
    assert decoded.to_dict() == item.to_dict()
    assert decoded.provenance.source_version == "source-r1"
    assert decoded.provenance.source_record_id == "record-1"
    assert decoded.citation == "synthetic://report/1"
    assert decoded.certainty == 0.8
    with pytest.raises(FrozenInstanceError):
        decoded.certainty = 1


@pytest.mark.parametrize(
    "change",
    [
        {"certainty": -0.1},
        {"certainty": 1.1},
        {"certainty": True},
        {"effective_at": NOW.replace(tzinfo=None)},
        {"expires_at": NOW.replace(tzinfo=None)},
        {"expires_at": NOW - timedelta(hours=2)},
        {"record_version": 0},
        {"registry_digest": "not-a-digest"},
        {"provenance": evidence(observed_at=None)},
        {"provenance": evidence(observed_at=NOW.date())},
        {"provenance": evidence(source_record_id=None)},
    ],
)
def test_observation_rejects_invalid_wire_data(change):
    data = observation().to_dict()
    for key, value in change.items():
        data[key] = value.to_dict() if isinstance(value, Provenance) else value
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    with pytest.raises(ValueError):
        Observation.from_dict(data)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "probability": 1.01},
        {"schema_version": 1, "probability": float("nan")},
        {"schema_version": 1, "withdrawn": 1},
        {"schema_version": 1, "text": " "},
        {
            "schema_version": 1,
            "value": 101,
            "unit": "percentage_points",
            "provenance": evidence().to_dict(),
        },
        {
            "schema_version": 1,
            "value": 0.1,
            "unit": "guess",
            "provenance": evidence().to_dict(),
        },
        {"schema_version": 1, "value": 0.1, "unit": "probability_points"},
        {"schema_version": 2, "withdrawn": True},
        {"schema_version": 1, "withdrawn": True, "delta": 0.1},
    ],
)
def test_payloads_fail_closed_on_wrong_kind_units_and_bounds(payload):
    data = observation().to_dict()
    data["payload"] = payload
    with pytest.raises(ValueError):
        Observation.from_dict(data)


def registry():
    return IdentityRegistry(
        revision="reviewed-r1",
        players=(
            Player(
                player_id=PLAYER,
                display_name="Alex Synthetic",
                tour=Tour.ATP,
                provenance=evidence(),
            ),
        ),
        provider_mappings=(
            ProviderMapping(
                source="synthetic",
                external_id="001",
                player_id=PLAYER,
                tour=Tour.ATP,
                reviewed_by="synthetic-reviewer",
                reviewed_at=NOW,
                provenance=evidence(),
            ),
        ),
        aliases=tuple(
            ReviewedAlias(
                source="synthetic",
                name=name,
                player_id=PLAYER,
                tour=Tour.ATP,
                reviewed_by="synthetic-reviewer",
                reviewed_at=NOW,
                provenance=evidence(),
            )
            for name in ("Alex Synthetic", "SYNTHETIC, Alex")
        ),
    )


def local_data():
    return {
        key: value
        for key, value in observation().to_dict().items()
        if key not in ("player_id", "registry_revision", "registry_digest")
    }


def test_local_import_resolves_reviewed_ids_and_aliases_with_registry_lineage():
    reviewed = registry()
    by_id = Observation.import_local(local_data(), registry=reviewed, external_id="001")
    by_alias = Observation.import_local(
        local_data(), registry=reviewed, name="SYNTHETIC, Alex"
    )
    assert by_id == by_alias
    assert by_id.player_id == PLAYER
    assert by_id.registry_revision == "reviewed-r1"
    assert by_id.registry_digest == reviewed.digest
    assert Observation.from_dict(by_id.to_dict()) == by_id
    with pytest.raises(IdentityResolutionError):
        Observation.import_local(local_data(), registry=reviewed, name="ALEX SYNTHETIC")
    with pytest.raises(IdentityResolutionError):
        Observation.import_local(
            local_data(), registry=reviewed, external_id="1", name="Alex Synthetic"
        )
    with pytest.raises(IdentityResolutionError):
        Observation.import_local(
            dict(local_data(), tour="wta"), registry=reviewed, external_id="001"
        )
    with pytest.raises(ValueError):
        Observation.import_local(
            dict(local_data(), player_id="player:forged"),
            registry=reviewed,
            external_id="001",
        )


def test_as_of_reports_conflicting_stale_missing_and_pending_without_applying_values():
    from tennis_api.models.information import (
        InformationCollection,
        InformationKind,
        InformationStatus,
    )

    active = observation(payload=VerifiedWithdrawal(withdrawn=True))
    conflicting = observation(
        payload=VerifiedWithdrawal(withdrawn=False),
        certainty=1,
        provenance=evidence(source="second-source", source_record_id="other"),
    )
    stale = observation(payload=InjuryRisk(probability=0.3), expires_at=NOW)
    pending = observation(
        payload=AnalystOpinion(text="Future effective opinion"),
        effective_at=NOW + timedelta(hours=1),
    )
    # Independent records, not different versions of one source record.
    stale = replace(stale, provenance=evidence(source_record_id="stale"))
    pending = replace(pending, provenance=evidence(source_record_id="pending"))
    collection = InformationCollection(
        revision="collection-r1", observations=(active, conflicting, stale, pending)
    )
    snapshot = collection.as_of(
        cutoff=NOW,
        event_id=EVENT,
        tour=Tour.ATP,
        player_ids=(PLAYER, PlayerId("player:missing")),
    )
    withdrawal = snapshot.state(PLAYER, InformationKind.VERIFIED_WITHDRAWAL)
    assert withdrawal.status == InformationStatus.CONFLICTING
    assert set(withdrawal.active) == {active, conflicting}
    injury = snapshot.state(PLAYER, InformationKind.INJURY_RISK)
    assert injury.status == InformationStatus.STALE
    assert injury.stale == (stale,)
    assert injury.missing is True
    opinion = snapshot.state(PLAYER, InformationKind.ANALYST_OPINION)
    assert opinion.status == InformationStatus.PENDING
    assert opinion.pending == (pending,)
    assert (
        snapshot.state(PLAYER, InformationKind.MARKET_ADJUSTMENT).status
        == InformationStatus.MISSING
    )
    assert len(snapshot.states) == 8
    assert all(state.missing for state in snapshot.states if state.player_id != PLAYER)
    assert snapshot.refresh_status == "blocked_no_approved_provider"
    assert snapshot.collection_digest == collection.digest
    assert (
        type(snapshot).from_dict(json.loads(json.dumps(snapshot.to_dict()))) == snapshot
    )
    assert type(snapshot).from_dict(snapshot.to_dict()).digest == snapshot.digest
    with pytest.raises(FrozenInstanceError):
        snapshot.cutoff = NOW + timedelta(days=1)
    with pytest.raises(ValueError):
        snapshot.state(PlayerId("player:outside-roster"), InformationKind.INJURY_RISK)


def test_as_of_strict_cutoffs_effective_boundaries_and_scoping():
    from tennis_api.models.information import (
        InformationCollection,
        InformationKind,
        InformationStatus,
    )

    item = observation(effective_at=NOW)
    collection = InformationCollection(revision="r1", observations=(item,))
    snapshot = collection.as_of(
        cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,)
    )
    assert (
        snapshot.state(PLAYER, InformationKind.ANALYST_OPINION).status
        == InformationStatus.ACTIVE
    )
    for excluded in (
        replace(item, provenance=evidence(available_at=NOW, ingested_at=NOW)),
        replace(item, provenance=evidence(ingested_at=NOW)),
        replace(item, event_id=EventId("event:other")),
        replace(item, tour=Tour.WTA),
        replace(item, player_id=PlayerId("player:other")),
    ):
        result = InformationCollection(
            revision="excluded", observations=(excluded,)
        ).as_of(cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,))
        assert result.observations == ()
        assert all(state.missing for state in result.states)
    with pytest.raises(ValueError):
        collection.as_of(
            cutoff=NOW.replace(tzinfo=None),
            event_id=EVENT,
            tour=Tour.ATP,
            player_ids=(PLAYER,),
        )
    with pytest.raises(ValueError):
        replace(
            snapshot,
            observations=(
                replace(
                    item,
                    expires_at=NOW + timedelta(hours=2),
                    provenance=evidence(ingested_at=NOW),
                ),
            ),
        )


def test_exact_imports_are_idempotent_conflicting_versions_rejected_and_history_retained():
    from tennis_api.models.information import InformationCollection, InformationKind

    original = observation()
    collection = InformationCollection(revision="r1", observations=(original, original))
    assert collection.observations == (original,)
    assert (
        InformationCollection(revision="r1", observations=(original,)).digest
        == collection.digest
    )
    with pytest.raises(ValueError):
        InformationCollection(
            revision="bad", observations=(original, replace(original, certainty=0.9))
        )
    newer = observation(
        record_version=2,
        payload=AnalystOpinion(text="Revised opinion"),
        provenance=evidence(
            source_version="source-r2",
            observed_at=NOW,
            available_at=NOW,
            ingested_at=NOW,
        ),
    )
    revised = collection.extend(revision="r2", observations=(newer,))
    assert len(collection.observations) == 1
    assert len(revised.observations) == 2
    assert revised.as_of(
        cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,)
    ).observations == (original,)
    later = revised.as_of(
        cutoff=NOW + timedelta(seconds=1),
        event_id=EVENT,
        tour=Tour.ATP,
        player_ids=(PLAYER,),
    )
    assert later.state(PLAYER, InformationKind.ANALYST_OPINION).active == (newer,)
    assert (
        revised.digest
        == InformationCollection(revision="r2", observations=(newer, original)).digest
    )
    assert (
        InformationCollection.from_dict(json.loads(json.dumps(revised.to_dict())))
        == revised
    )
    for incompatible in (
        replace(newer, event_id=EventId("event:other")),
        replace(newer, player_id=PlayerId("player:other")),
        replace(newer, payload=InjuryRisk(probability=0.4)),
        replace(
            newer,
            provenance=evidence(
                available_at=NOW - timedelta(hours=4),
                observed_at=NOW - timedelta(hours=5),
            ),
        ),
    ):
        with pytest.raises(ValueError):
            collection.extend(revision="bad", observations=(incompatible,))


def test_later_ingestion_requires_explicit_reconstruction_and_historical_snapshot_lineage():
    from tennis_api.models.information import InformationCollection, SnapshotMode

    imported_later = observation(
        provenance=evidence(ingested_at=NOW + timedelta(days=10))
    )
    archive = evidence(
        source="synthetic-archive",
        source_version="archive-r1",
        source_record_id="snapshot-123",
        observed_at=NOW - timedelta(minutes=90),
        available_at=NOW - timedelta(minutes=90),
        ingested_at=NOW + timedelta(days=10),
    )
    reconstructed = replace(imported_later, historical_snapshot=archive)
    args = dict(cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,))
    collection = InformationCollection(
        revision="archive-import", observations=(reconstructed,)
    )
    assert collection.as_of(**args).observations == ()
    snapshot = collection.as_of(**args, mode=SnapshotMode.HISTORICAL_RECONSTRUCTION)
    assert snapshot.observations == (reconstructed,)
    assert snapshot.mode == SnapshotMode.HISTORICAL_RECONSTRUCTION
    assert (
        snapshot.observations[0].historical_snapshot.source_record_id == "snapshot-123"
    )
    assert (
        type(snapshot).from_dict(json.loads(json.dumps(snapshot.to_dict()))) == snapshot
    )
    with pytest.raises(ValueError):
        replace(snapshot, mode=SnapshotMode.LOCALLY_KNOWN)
    # Backdating a claim without archived evidence never establishes historical knowledge.
    for excluded in (
        imported_later,
        replace(
            reconstructed,
            historical_snapshot=replace(archive, observed_at=NOW, available_at=NOW),
        ),
        replace(
            reconstructed,
            provenance=evidence(
                observed_at=NOW + timedelta(days=1),
                available_at=NOW + timedelta(days=1),
                ingested_at=NOW + timedelta(days=10),
            ),
            historical_snapshot=None,
            expires_at=NOW + timedelta(days=20),
        ),
    ):
        result = InformationCollection(
            revision="excluded", observations=(excluded,)
        ).as_of(**args, mode=SnapshotMode.HISTORICAL_RECONSTRUCTION)
        assert result.observations == ()
    for invalid in (
        replace(archive, source_record_id=None),
        replace(archive, observed_at=None),
        evidence(source_record_id="snapshot-before-news"),
    ):
        with pytest.raises(ValueError):
            replace(imported_later, historical_snapshot=invalid)


def test_adjustment_provenance_cannot_introduce_future_information():
    data = observation(
        payload=MarketAdjustment(
            value=0.1,
            unit=AdjustmentUnit.PROBABILITY_POINTS,
            provenance=evidence(),
        )
    ).to_dict()
    data["payload"]["provenance"] = evidence(
        observed_at=NOW, available_at=NOW, ingested_at=NOW
    ).to_dict()
    with pytest.raises(ValueError):
        Observation.from_dict(data)


def test_equivalent_numeric_reports_agree_without_aggregation_or_metadata_winners():
    from tennis_api.models.information import (
        InformationCollection,
        InformationKind,
        InformationStatus,
    )

    first = observation(payload=InjuryRisk(probability=0.0))
    second = observation(
        payload=InjuryRisk(probability=-0.0),
        certainty=1,
        provenance=evidence(source_record_id="second"),
    )
    adjustments = tuple(
        observation(
            payload=MarketAdjustment(value=value, unit=unit, provenance=evidence()),
            provenance=evidence(source_record_id=record_id),
        )
        for value, unit, record_id in (
            (-2, AdjustmentUnit.PERCENTAGE_POINTS, "market-1"),
            (-0.02, AdjustmentUnit.PROBABILITY_POINTS, "market-2"),
        )
    )
    snapshot = InformationCollection(
        revision="r1", observations=(first, second, *adjustments)
    ).as_of(cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,))
    assert (
        snapshot.state(PLAYER, InformationKind.INJURY_RISK).status
        == InformationStatus.ACTIVE
    )
    market = snapshot.state(PLAYER, InformationKind.MARKET_ADJUSTMENT)
    assert market.status == InformationStatus.ACTIVE
    assert len(market.active) == 2
    disagreement = replace(
        adjustments[1], payload=replace(adjustments[1].payload, value=0.02)
    )
    conflicting = InformationCollection(
        revision="r2", observations=(adjustments[0], disagreement)
    ).as_of(cutoff=NOW, event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,))
    assert (
        conflicting.state(PLAYER, InformationKind.MARKET_ADJUSTMENT).status
        == InformationStatus.CONFLICTING
    )


def test_digest_is_stable_for_equivalent_timezone_representations_and_duplicate_order():
    from tennis_api.models.information import InformationCollection

    item = observation()
    offset = timezone(timedelta(hours=5, minutes=30))
    equivalent = replace(
        item,
        effective_at=item.effective_at.astimezone(offset),
        expires_at=item.expires_at.astimezone(offset),
        provenance=replace(
            item.provenance,
            observed_at=item.provenance.observed_at.astimezone(offset),
            available_at=item.provenance.available_at.astimezone(offset),
            ingested_at=item.provenance.ingested_at.astimezone(offset),
        ),
    )
    first = InformationCollection(revision="r1", observations=(item, equivalent))
    second = InformationCollection(revision="r1", observations=(equivalent, item))
    assert first.to_dict() == second.to_dict()
    assert first.digest == second.digest
    args = dict(event_id=EVENT, tour=Tour.ATP, player_ids=(PLAYER,))
    assert (
        first.as_of(cutoff=NOW, **args).digest
        == second.as_of(cutoff=NOW.astimezone(offset), **args).digest
    )


def test_effective_range_uses_elapsed_time_across_daylight_saving_fold():
    zone = ZoneInfo("America/New_York")
    item = observation(
        effective_at=datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0),
        expires_at=datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1),
    )
    assert item.expires_at - item.effective_at == timedelta(minutes=30)
    assert Observation.from_dict(item.to_dict()) == item


@pytest.mark.parametrize("field", ["observed_at", "available_at", "ingested_at"])
def test_source_timestamps_require_timezones(field):
    data = observation().to_dict()
    data["provenance"][field] = "2026-01-10T09:00:00"
    with pytest.raises(ValueError):
        Observation.from_dict(data)

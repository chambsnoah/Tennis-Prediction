"""Synthetic identities, not real provider mappings or participant data."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from tennis_api.models.canonical import Player, PlayerId, Provenance, Tour
from tennis_api.models.identity import (
    IdentityRegistry,
    IdentityResolutionError,
    ProviderMapping,
    ReviewedAlias,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
P1 = PlayerId("canonical:p1")


def provenance(source="synthetic"):
    return Provenance(
        source=source,
        source_version="fixture-1",
        source_record_id=None,
        observed_at=NOW,
        available_at=NOW,
        ingested_at=NOW,
    )


def player(player_id=P1, name="Alex Example", tour=Tour.ATP):
    return Player(
        player_id=player_id, display_name=name, tour=tour, provenance=provenance()
    )


def mapping(source="live", external_id="001", player_id=P1, tour=Tour.ATP):
    return ProviderMapping(
        source=source,
        external_id=external_id,
        player_id=player_id,
        tour=tour,
        reviewed_by="fixture-reviewer",
        reviewed_at=NOW,
        provenance=provenance(source),
    )


def alias(name="Alex Example", source="workbook", player_id=P1, tour=Tour.ATP):
    return ReviewedAlias(
        source=source,
        name=name,
        player_id=player_id,
        tour=tour,
        reviewed_by="fixture-reviewer",
        reviewed_at=NOW,
        provenance=provenance(source),
    )


def test_reviewed_workbook_history_and_provider_resolve_same_identity():
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(),),
        provider_mappings=tuple(
            ProviderMapping(
                source=source,
                external_id=external_id,
                player_id=P1,
                tour=Tour.ATP,
                reviewed_by="fixture-reviewer",
                reviewed_at=NOW,
                provenance=provenance(source),
            )
            for source, external_id in (("history", "001"), ("live", "17"))
        ),
        aliases=(
            ReviewedAlias(
                source="workbook",
                name="EXAMPLE, Alex",
                player_id=P1,
                tour=Tour.ATP,
                reviewed_by="fixture-reviewer",
                reviewed_at=NOW,
                provenance=provenance("workbook"),
            ),
        ),
    )
    assert registry.resolve(source="history", tour=Tour.ATP, external_id="001") == P1
    assert registry.resolve(source="live", tour=Tour.ATP, external_id="17") == P1
    assert (
        registry.resolve(source="workbook", tour=Tour.ATP, name="EXAMPLE, Alex") == P1
    )


@pytest.mark.parametrize("name", ["Example", "ALEX EXAMPLE", "Alex Ex\u00e1mple"])
def test_normalized_names_only_offer_review_candidates(name):
    registry = IdentityRegistry(revision="review-1", players=(player(),))
    with pytest.raises(IdentityResolutionError) as error:
        registry.resolve(source="workbook", tour=Tour.ATP, name=name)
    assert error.value.reason == "unreviewed_name"
    assert error.value.candidates == (P1,)
    assert registry.candidates(name=name, tour=Tour.ATP) == (P1,)


def test_duplicate_surnames_are_ambiguous_and_never_joined():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, "Blair Example")),
    )
    with pytest.raises(IdentityResolutionError) as error:
        registry.resolve(source="workbook", tour=Tour.ATP, name="Example")
    assert error.value.reason == "ambiguous_name"
    assert error.value.candidates == (P1, p2)


def test_provider_id_collisions_fail_at_registry_construction():
    p2 = PlayerId("canonical:p2")
    with pytest.raises(ValueError, match="provider"):
        IdentityRegistry(
            revision="review-1",
            players=(player(), player(p2, "Blair Example")),
            provider_mappings=(mapping(), mapping(player_id=p2)),
        )


@pytest.mark.parametrize(
    "bad_mapping",
    [
        mapping(player_id=PlayerId("canonical:missing")),
        mapping(tour=Tour.WTA),
    ],
)
def test_mapping_requires_existing_player_in_same_tour(bad_mapping):
    with pytest.raises(ValueError, match="player|tour"):
        IdentityRegistry(
            revision="review-1",
            players=(player(),),
            provider_mappings=(bad_mapping,),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"reviewed_by": " "},
        {"reviewed_at": NOW - timedelta(days=1)},
        {"provenance": provenance("wrong-source")},
        {"source": " live "},
    ],
)
def test_review_evidence_is_required_and_validated(change):
    with pytest.raises(ValueError):
        replace(mapping(), **change)


def test_duplicate_canonical_players_fail_closed():
    with pytest.raises(ValueError, match="Duplicate player"):
        IdentityRegistry(revision="review-1", players=(player(), player()))


def test_registry_round_trip_and_digest_ignore_input_order():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, "Blair Other")),
        provider_mappings=(mapping(), mapping("history", "2", p2)),
        aliases=(alias(), alias("Former Name", player_id=p2)),
    )
    restored = IdentityRegistry.from_dict(json.loads(json.dumps(registry.to_dict())))
    reordered = replace(
        registry,
        players=registry.players[::-1],
        provider_mappings=registry.provider_mappings[::-1],
        aliases=registry.aliases[::-1],
    )
    assert restored == registry == reordered
    assert restored.digest == reordered.digest == registry.digest
    assert len(registry.digest) == 64
    assert replace(registry, revision="review-2").digest != registry.digest
    assert replace(registry, aliases=()).digest != registry.digest


@pytest.mark.parametrize("version", [None, 2, True])
def test_unknown_or_missing_schema_version_fails_closed(version):
    data = IdentityRegistry(revision="review-1", players=(player(),)).to_dict()
    data["schema_version"] = version
    with pytest.raises(ValueError):
        IdentityRegistry.from_dict(data)


def test_nested_review_version_and_unknown_fields_fail_closed():
    data = IdentityRegistry(
        revision="review-1",
        players=(player(),),
        aliases=(alias(),),
    ).to_dict()
    data["aliases"][0]["schema_version"] = 2
    with pytest.raises(ValueError):
        IdentityRegistry.from_dict(data)
    data["aliases"][0]["schema_version"] = 1
    data["aliases"][0]["approved"] = True
    with pytest.raises(ValueError):
        IdentityRegistry.from_dict(data)


def test_reviewed_renaming_retains_canonical_id_without_mutating_snapshot():
    old = IdentityRegistry(
        revision="review-1",
        players=(player(name="Former Name"),),
        aliases=(alias("Former Name"),),
    )
    new = replace(
        old,
        revision="review-2",
        players=(player(name="Current Name"),),
        aliases=(*old.aliases, alias("Current Name")),
    )
    for name in ("Former Name", "Current Name"):
        assert new.resolve(source="workbook", tour=Tour.ATP, name=name) == P1
    with pytest.raises(IdentityResolutionError):
        old.resolve(source="workbook", tour=Tour.ATP, name="Current Name")
    assert new.digest != old.digest


def test_unknown_provider_id_never_falls_back_to_reviewed_name():
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(),),
        aliases=(alias(),),
    )
    with pytest.raises(IdentityResolutionError) as error:
        registry.resolve(
            source="workbook", tour=Tour.ATP, external_id="unknown", name="Alex Example"
        )
    assert error.value.reason == "unknown_provider_id"
    assert error.value.candidates == (P1,)


def test_provider_id_scope_preserves_leading_zeros_and_tour():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, tour=Tour.WTA)),
        provider_mappings=(mapping(), mapping("history", "001", p2, Tour.WTA)),
    )
    assert registry.resolve(source="live", tour=Tour.ATP, external_id="001") == P1
    assert registry.resolve(source="history", tour=Tour.WTA, external_id="001") == p2
    for source, tour, external_id in (
        ("live", Tour.WTA, "001"),
        ("live", Tour.ATP, "1"),
    ):
        with pytest.raises(IdentityResolutionError):
            registry.resolve(source=source, tour=tour, external_id=external_id)


def test_exact_shared_alias_is_ambiguous():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, "Blair Example")),
        aliases=(alias("Example"), alias("Example", player_id=p2)),
    )
    with pytest.raises(IdentityResolutionError) as error:
        registry.resolve(source="workbook", tour=Tour.ATP, name="Example")
    assert error.value.reason == "ambiguous_name"
    assert error.value.candidates == (P1, p2)


def test_conflicting_provider_id_and_reviewed_name_block_resolution():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, "Blair Other")),
        provider_mappings=(mapping(),),
        aliases=(alias("Blair Other", source="live", player_id=p2),),
    )
    with pytest.raises(IdentityResolutionError, match="conflicting_identity"):
        registry.resolve(
            source="live", tour=Tour.ATP, external_id="001", name="Blair Other"
        )


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"name": ""},
        {"name": 123},
        {"external_id": ""},
        {"external_id": 1},
        {"source": " "},
        {"tour": "atp"},
    ],
)
def test_invalid_resolution_queries_fail_closed(query):
    registry = IdentityRegistry(revision="review-1", players=(player(),))
    with pytest.raises(IdentityResolutionError, match="invalid_query"):
        registry.resolve(**{"source": "live", "tour": Tour.ATP, **query})


def test_duplicate_alias_and_dangling_alias_fail_at_construction():
    for aliases in (
        (alias(), alias()),
        (alias(player_id=PlayerId("canonical:missing")),),
    ):
        with pytest.raises(ValueError):
            IdentityRegistry(revision="review-1", players=(player(),), aliases=aliases)


def test_same_provider_id_can_exist_in_distinct_sources():
    p2 = PlayerId("canonical:p2")
    registry = IdentityRegistry(
        revision="review-1",
        players=(player(), player(p2, "Blair Other")),
        provider_mappings=(mapping(), mapping("history", "001", p2)),
    )
    assert registry.resolve(source="live", tour=Tour.ATP, external_id="001") == P1
    assert registry.resolve(source="history", tour=Tour.ATP, external_id="001") == p2


def test_unknown_name_is_quarantined_without_exposing_input():
    registry = IdentityRegistry(revision="review-1", players=(player(),))
    with pytest.raises(IdentityResolutionError) as error:
        registry.resolve(source="workbook", tour=Tour.ATP, name="Unknown Person")
    assert error.value.reason == "unreviewed_name"
    assert error.value.candidates == ()
    assert "Unknown Person" not in str(error.value)

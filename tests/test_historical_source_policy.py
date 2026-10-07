"""Offline regressions for the source decision, not tests of downloaded data."""

import json
from datetime import date
from pathlib import Path

import pytest


POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/data/historical_source_policy.json"
)


@pytest.fixture
def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_unavailable_source_has_no_invented_version_or_license(policy):
    assert policy["schema_version"] == 1
    assert policy["policy_version"] == "2026-10-07.1"
    source = policy["source"]
    assert source["repository"] == "https://github.com/JeffSackmann/tennis_atp"
    assert source["selection"] == "provisional_candidate"
    assert source["access_status"] == "unavailable_http_404"
    assert source["revision"] is None
    assert source["terms_url"] is None
    assert source["license"] is None
    assert source["license_url"] is None
    assert source["terms_verified"] is False
    assert source["attribution"]["creator"] == "Jeff Sackmann"
    assert source["attribution"]["changes_must_be_indicated"] is True


@pytest.mark.parametrize("action", ["automated_ingestion", "publication", "paid_prize_pool_use"])
def test_unresolved_use_case_never_grants_permission(policy, action):
    permissions = policy["permissions"]
    assert permissions["status"] == "blocked_source_and_permission_review"
    assert permissions["approvals"] == []
    assert permissions["allowed_actions"][action] is False
    assert permissions["private_cache_is_not_permission"] is True
    assert permissions["confidential_evidence_location"] == "external_private_storage"


def test_coverage_is_a_plan_not_an_invented_measurement(policy):
    coverage = policy["coverage"]
    assert coverage["cohort"] == "ATP men's tour-level singles"
    assert coverage["planned_seasons"] == [2000, 2025]
    assert coverage["verified_match_count"] is None
    assert coverage["verified_statistics_coverage"] is None
    assert coverage["missing_statistics"] == "preserve_null_never_fabricate"
    assert coverage["date_precision"] == "event_date_not_exact_match_start"
    assert coverage["historical_availability"] == "not_proven_by_current_snapshot"
    assert coverage["excluded_match_files"] == ["qual_chall", "futures", "doubles"]


def test_frozen_season_partitions_are_exhaustive_ordered_and_disjoint(policy):
    splits = policy["evaluation"]
    assert splits["train_seasons"] == [2000, 2022]
    assert splits["validation_seasons"] == [2023, 2024]
    assert splits["holdout_seasons"] == [2025, 2025]
    assert splits["shadow_seasons"] == [2026, 2026]
    assert splits["shadow_predictions"] == "post_approval_pre_outcome_only"
    partitions = [
        set(range(start, end + 1))
        for start, end in (
            splits["train_seasons"], splits["validation_seasons"], splits["holdout_seasons"]
        )
    ]
    assert set.union(*partitions) == set(range(2000, 2026))
    assert all(left.isdisjoint(right) for i, left in enumerate(partitions) for right in partitions[i + 1:])
    assert splits["holdout_used_for_selection"] is False
    assert splits["split_key"] == "event_start_season"
    assert splits["ambiguous_boundary_records"] == "quarantine"
    assert date.fromisoformat(splits["frozen_on"]) == date(2026, 10, 7)


def test_retrieval_plan_requires_permission_and_reproducible_manifests(policy):
    retrieval = policy["retrieval"]
    assert retrieval["implemented"] is False
    assert retrieval["requires_permission_preflight"] is True
    assert retrieval["revision_strategy"] == "explicit_reviewed_commit_only"
    assert retrieval["match_file_template"] == "atp_matches_{season}.csv"
    assert retrieval["ranking_file_templates"] == ["atp_rankings_{decade}s.csv", "atp_rankings_current.csv"]
    assert set(retrieval["manifest_required_fields"]) == {
        "source_revision", "policy_version", "relative_path", "retrieved_at_utc",
        "sha256", "byte_count", "terms_reference", "permission_reference",
    }


def test_private_workbooks_are_not_approved_public_fixtures(policy):
    privacy = policy["workbook_privacy"]
    assert privacy["review_status"] == "not_reviewed"
    assert privacy["publication_allowed"] is False
    assert privacy["fixture_strategy"] == "generated_synthetic_only"
    assert set(privacy["excluded_from_public_artifacts"]) == {
        "participant_names", "contact_details", "selections", "quotas", "usage",
        "payments", "payouts", "hidden_sheets", "comments", "external_links",
        "document_metadata", "macros", "confidential_permission_evidence",
    }


@pytest.mark.parametrize("source_id", ["tennis_abstract_website", "official_atp", "commercial_api"])
def test_alternative_sources_are_not_silent_fallbacks(policy, source_id):
    alternative = next(item for item in policy["alternatives"] if item["id"] == source_id)
    assert alternative["status"] == "not_approved"
    assert alternative["automated_ingestion_allowed"] is False

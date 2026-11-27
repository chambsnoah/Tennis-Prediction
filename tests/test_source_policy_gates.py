"""Offline proofs that only verified evidence can unlock restricted source actions.

Every policy here is synthetic. Nothing is fetched, and the fixture revision and
evidence reference are placeholders, not real upstream or approval records.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tennis_api.source_policy import (
    RESTRICTED_ACTIONS,
    declared_actions_exceed_evidence,
    evaluate_gates,
    load_policy,
)

POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "docs/data/historical_source_policy.json"
)
AS_OF = date(2026, 11, 27)
SYNTHETIC_SHA = "ab" * 20
REPO = "https://github.com/JeffSackmann/tennis_atp"


@pytest.fixture
def committed() -> dict[str, Any]:
    return load_policy(POLICY_PATH)


def _verified(policy: dict[str, Any], actions: list[str]) -> dict[str, Any]:
    """A synthetic policy that satisfies every evidence requirement for actions."""
    verified = copy.deepcopy(policy)
    source = verified["source"]
    source.update(
        access_status="verified_at_pinned_revision",
        revision=SYNTHETIC_SHA,
        terms_verified=True,
        license="SYNTHETIC-LICENSE",
        license_url="https://example.invalid/license",
        readme_evidence={
            "url": f"{REPO}/blob/{SYNTHETIC_SHA}/README.md",
            "retrieved_on": "2026-11-20",
        },
        license_evidence={
            "url": f"{REPO}/blob/{SYNTHETIC_SHA}/LICENSE",
            "retrieved_on": "2026-11-20",
        },
    )
    verified["permissions"]["approvals"] = [
        {
            "grantor": "rights_holder",
            "actions": actions,
            "source_revision": SYNTHETIC_SHA,
            "evidence_reference": "restricted:synthetic-approval-001",
            "granted_on": "2026-11-21",
            "expires_on": "2027-11-21",
        }
    ]
    return verified


def _allowed(policy: dict[str, Any], as_of: date = AS_OF) -> set[str]:
    return {a for a, d in evaluate_gates(policy, as_of).items() if d.allowed}


def test_committed_policy_unlocks_nothing_and_declares_nothing_extra(committed):
    decisions = evaluate_gates(committed, AS_OF)
    assert set(decisions) == set(RESTRICTED_ACTIONS)
    assert not any(d.allowed for d in decisions.values())
    for decision in decisions.values():
        assert "source_access_not_verified" in decision.unmet
        assert "no_full_immutable_revision" in decision.unmet
        assert "no_valid_rights_holder_approval" in decision.unmet
    assert declared_actions_exceed_evidence(committed, AS_OF) == ()


def test_owner_selection_and_free_access_claims_cannot_unlock(committed):
    claimed = copy.deepcopy(committed)
    claimed["source"]["selection"] = "approved"
    claimed["source"]["selected_by"] = "rights_holder"
    claimed["source"]["cost"]["status"] = "free_for_anyone"
    claimed["permissions"]["status"] = "approved"
    claimed["permissions"]["allowed_actions"] = dict.fromkeys(RESTRICTED_ACTIONS, True)
    assert _allowed(claimed) == set()
    assert set(declared_actions_exceed_evidence(claimed, AS_OF)) == set(RESTRICTED_ACTIONS)


@pytest.mark.parametrize(
    "grantor", ["project_owner", "free_access_announcement", "commissioner", None]
)
def test_only_a_rights_holder_approval_counts(committed, grantor):
    policy = _verified(committed, list(RESTRICTED_ACTIONS))
    policy["permissions"]["approvals"][0]["grantor"] = grantor
    assert _allowed(policy) == set()


def test_full_evidence_unlocks_only_the_approved_action(committed):
    policy = _verified(committed, ["automated_ingestion"])
    assert _allowed(policy) == {"automated_ingestion"}
    policy["permissions"]["allowed_actions"]["publication"] = True
    assert declared_actions_exceed_evidence(policy, AS_OF) == ("publication",)


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("source", "access_status"), "unavailable_http_404", "source_access_not_verified"),
        (("source", "revision"), None, "no_full_immutable_revision"),
        (("source", "revision"), "master", "no_full_immutable_revision"),
        (("source", "revision"), SYNTHETIC_SHA[:12], "no_full_immutable_revision"),
        (("source", "revision"), SYNTHETIC_SHA.upper(), "no_full_immutable_revision"),
        (("source", "terms_verified"), "yes", "terms_not_verified"),
        (("source", "license"), None, "license_not_recorded"),
        (("source", "license_url"), "", "license_not_recorded"),
        (("source", "readme_evidence"), None, "readme_not_pinned"),
        (("source", "license_evidence"), {"url": f"{REPO}/blob/master/LICENSE",
                                          "retrieved_on": "2026-11-20"}, "license_not_pinned"),
    ],
)
def test_each_missing_source_proof_blocks_every_action(committed, path, value, reason):
    policy = _verified(committed, list(RESTRICTED_ACTIONS))
    policy[path[0]][path[1]] = value
    for decision in evaluate_gates(policy, AS_OF).values():
        assert not decision.allowed
        assert reason in decision.unmet


PINNED_README = f"{REPO}/blob/{SYNTHETIC_SHA}/README.md"


@pytest.mark.parametrize(
    "url",
    [
        f"{REPO}/blob/master/README.md?pin=/{SYNTHETIC_SHA}/",
        f"{REPO}/blob/master/README.md#/{SYNTHETIC_SHA}/",
        f"{PINNED_README}?ref=master",
        f"https://github.com/someone/fork/blob/{SYNTHETIC_SHA}/README.md",
        f"{REPO}/blob/{SYNTHETIC_SHA}/LICENSE",
        f"{REPO}/blob/{SYNTHETIC_SHA}/docs/README.md",
        f"{REPO}/blob/{SYNTHETIC_SHA}/README-old.txt",
        f"{REPO}/blob/{SYNTHETIC_SHA}/README.md.bak",
        f"{REPO}/tree/{SYNTHETIC_SHA}/README.md",
        f"http://github.com/JeffSackmann/tennis_atp/blob/{SYNTHETIC_SHA}/README.md",
        f"https://example.invalid/JeffSackmann/tennis_atp/{SYNTHETIC_SHA}/README.md",
        "https://[",
    ],
)
def test_readme_pin_must_be_the_revision_path_of_the_selected_repo(committed, url):
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["readme_evidence"]["url"] = url
    decision = evaluate_gates(policy, AS_OF)["automated_ingestion"]
    assert not decision.allowed
    assert "readme_not_pinned" in decision.unmet
    assert "license_not_pinned" not in decision.unmet


def test_malformed_urls_fail_closed_without_raising(committed):
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["license_evidence"]["url"] = "https://["
    policy["permissions"]["allowed_actions"]["automated_ingestion"] = True
    assert "license_not_pinned" in evaluate_gates(policy, AS_OF)["automated_ingestion"].unmet
    assert declared_actions_exceed_evidence(policy, AS_OF) == ("automated_ingestion",)


def test_raw_urls_at_the_revision_also_pin_evidence(committed):
    raw = f"https://raw.githubusercontent.com/JeffSackmann/tennis_atp/{SYNTHETIC_SHA}"
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["readme_evidence"]["url"] = f"{raw}/README.md"
    policy["source"]["license_evidence"]["url"] = f"{raw}/LICENSE"
    assert _allowed(policy) == {"automated_ingestion"}


@pytest.mark.parametrize("name", ["LICENSE-old.txt", "LICENSE.html", "COPYING.LESSER"])
def test_license_pin_needs_an_exact_license_file_name(committed, name):
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["license_evidence"]["url"] = f"{REPO}/blob/{SYNTHETIC_SHA}/{name}"
    unmet = evaluate_gates(policy, AS_OF)["automated_ingestion"].unmet
    assert "license_not_pinned" in unmet


@pytest.mark.parametrize("name", ["readme.md", "README", "README.rst"])
def test_common_readme_names_still_pin(committed, name):
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["readme_evidence"]["url"] = f"{REPO}/blob/{SYNTHETIC_SHA}/{name}"
    assert _allowed(policy) == {"automated_ingestion"}


@pytest.mark.parametrize(
    "repository", ["https://github.com/JeffSackmann/tennis_atp?x=1", "https://["]
)
def test_unparseable_repository_blocks_both_pins(committed, repository):
    policy = _verified(committed, ["automated_ingestion"])
    policy["source"]["repository"] = repository
    unmet = evaluate_gates(policy, AS_OF)["automated_ingestion"].unmet
    assert {"readme_not_pinned", "license_not_pinned"} <= set(unmet)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_revision", "cd" * 20),
        ("evidence_reference", "https://example.invalid/public-email"),
        ("evidence_reference", ""),
        ("evidence_reference", "restricted:"),
        ("evidence_reference", "restricted:   "),
        ("granted_on", "2026-12-01"),
        ("granted_on", None),
        ("expires_on", "2026-11-26"),
        ("expires_on", "not-a-date"),
        ("actions", "automated_ingestion"),
    ],
)
def test_approval_must_be_current_scoped_and_restricted(committed, field, value):
    policy = _verified(committed, ["automated_ingestion"])
    policy["permissions"]["approvals"][0][field] = value
    decision = evaluate_gates(policy, AS_OF)["automated_ingestion"]
    assert not decision.allowed
    assert decision.unmet == ("no_valid_rights_holder_approval",)


def test_open_ended_approval_is_allowed_only_from_its_grant_date(committed):
    policy = _verified(committed, ["publication"])
    policy["permissions"]["approvals"][0]["expires_on"] = None
    assert _allowed(policy, date(2026, 11, 21)) == {"publication"}
    assert _allowed(policy, date(2026, 11, 20)) == set()


@pytest.mark.parametrize("broken", [{}, {"source": []}, {"permissions": {"approvals": "all"}}])
def test_malformed_records_fail_closed(broken):
    assert _allowed(broken) == set()


def test_load_policy_rejects_non_object(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(path)

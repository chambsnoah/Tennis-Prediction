"""Synthetic rule-register tests; no private pool data or source-project imports."""

import json

import pytest

from tennis_pool.rules import (
    DEPENDENCIES,
    ProvisionalRulesWarning,
    UnresolvedRulesError,
    load_register,
    require_resolved,
)


@pytest.fixture
def register():
    return load_register()


def save_register(tmp_path, register):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(register), encoding="utf-8")
    return path


def confirm(register, key):
    register["register_version"] = "synthetic-test-v2"
    register["decisions"][key].update(
        status="confirmed",
        decision="Synthetic test decision, not a real commissioner confirmation.",
        confirmation={
            "source": "Synthetic fixture only",
            "source_version": "fixture-v1",
            "confirmed_by": "Synthetic commissioner",
            "confirmed_at": "2026-10-04T21:45:00Z",
        },
    )


def test_initial_register_has_no_fabricated_confirmations(register):
    assert len(register["decisions"]) == 17
    assert all(entry["status"] == "provisional" for entry in register["decisions"].values())
    assert all(entry["confirmation"] is None for entry in register["decisions"].values())
    assert all(entry["decision"] and entry["rationale"] for entry in register["decisions"].values())


@pytest.mark.parametrize("operation", DEPENDENCIES)
def test_each_initial_operation_is_blocked(operation):
    with pytest.raises(UnresolvedRulesError) as error:
        require_resolved(operation)
    assert tuple(error.value.blockers) == DEPENDENCIES[operation]
    assert error.value.operation == operation
    assert error.value.register_version == "2026-provisional-2"
    assert all(error.value.blockers.values())


@pytest.mark.parametrize("operation", DEPENDENCIES)
def test_opt_in_provisional_mode_accepts_and_discloses_assumptions(operation):
    with pytest.warns(ProvisionalRulesWarning, match="2026-provisional-2") as recorded:
        accepted = require_resolved(operation, allow_provisional=True)
    for key in DEPENDENCIES[operation]:
        assert key in str(recorded[0].message)
        assert accepted["decisions"][key]["status"] == "provisional"
        assert accepted["decisions"][key]["confirmation"] is None


def test_provisional_mode_still_blocks_unresolved_rules(register, tmp_path):
    register["decisions"]["walkovers"].update(
        status="unresolved", decision=None, confirmation=None,
    )
    with pytest.raises(UnresolvedRulesError) as error:
        require_resolved("scoring", save_register(tmp_path, register), allow_provisional=True)
    assert set(error.value.blockers) == {"walkovers"}


@pytest.mark.parametrize("field", ["decision", "rationale", "assumption_source", "confirmation"])
def test_provisional_mode_requires_honest_documented_assumptions(register, tmp_path, field):
    if field == "assumption_source":
        del register[field]
    elif field == "confirmation":
        register["decisions"]["ties_payouts"][field] = {"source": "Fabricated confirmation"}
    else:
        register["decisions"]["ties_payouts"][field] = ""
    with pytest.raises(ValueError):
        require_resolved("payout", save_register(tmp_path, register), allow_provisional=True)


def test_confirmed_operation_emits_no_provisional_warning(register, tmp_path, recwarn):
    confirm(register, "ties_payouts")
    require_resolved("payout", save_register(tmp_path, register), allow_provisional=True)
    assert not recwarn


def test_confirmation_only_unblocks_affected_operation(register, tmp_path):
    confirm(register, "ties_payouts")
    path = save_register(tmp_path, register)
    assert require_resolved("payout", path)["register_version"] == "synthetic-test-v2"
    with pytest.raises(UnresolvedRulesError):
        require_resolved("recommendation", path)


def test_scoring_does_not_require_payout_confirmation(register, tmp_path):
    for key in DEPENDENCIES["scoring"]:
        confirm(register, key)
    path = save_register(tmp_path, register)
    require_resolved("scoring", path)
    with pytest.raises(UnresolvedRulesError):
        require_resolved("payout", path)


def test_partial_confirmation_leaves_remaining_blockers(register, tmp_path):
    confirm(register, "walkovers")
    with pytest.raises(UnresolvedRulesError) as error:
        require_resolved("scoring", save_register(tmp_path, register))
    assert set(error.value.blockers) == {"mixed_bonus_order", "semifinal_points"}


def test_random_fallback_is_not_a_voluntary_roster_constraint():
    assert "random_fallback" in DEPENDENCIES["random_assignment"]
    assert "random_fallback" not in DEPENDENCIES["recommendation"]
    assert "random_accounting" in DEPENDENCIES["recommendation"]


@pytest.mark.parametrize("field", ["source", "source_version", "confirmed_by", "confirmed_at"])
def test_confirmations_require_each_provenance_field(register, tmp_path, field):
    confirm(register, "ties_payouts")
    del register["decisions"]["ties_payouts"]["confirmation"][field]
    with pytest.raises(ValueError, match="provenance"):
        require_resolved("payout", save_register(tmp_path, register))


@pytest.mark.parametrize("timestamp", ["not-a-date", "2026-10-04T21:45:00"])
def test_confirmation_timestamp_must_be_valid_and_zoned(register, tmp_path, timestamp):
    confirm(register, "ties_payouts")
    register["decisions"]["ties_payouts"]["confirmation"]["confirmed_at"] = timestamp
    with pytest.raises(ValueError):
        load_register(save_register(tmp_path, register))


@pytest.mark.parametrize("mutation", [
    "missing_decision", "unknown_decision", "unknown_status", "blank_question",
    "blank_reference", "blank_decision", "changed_source", "unsupported_schema",
    "missing_version", "unresolved_with_evidence",
])
def test_malformed_register_fails_closed(register, tmp_path, mutation):
    entry = register["decisions"]["ties_payouts"]
    if mutation == "missing_decision":
        del register["decisions"]["ties_payouts"]
    elif mutation == "unknown_decision":
        register["decisions"]["new_rule"] = dict(entry)
    elif mutation == "unknown_status":
        entry["status"] = "approved_by_agent"
    elif mutation == "blank_question":
        entry["question"] = " "
    elif mutation == "blank_reference":
        entry["reference"] = ""
    elif mutation == "blank_decision":
        confirm(register, "ties_payouts")
        entry["decision"] = ""
    elif mutation == "changed_source":
        register["rules_source"]["sha256"] = "0" * 64
    elif mutation == "unsupported_schema":
        register["schema_version"] = 2
    elif mutation == "missing_version":
        register["register_version"] = ""
    elif mutation == "unresolved_with_evidence":
        entry["status"] = "unresolved"
        entry["decision"] = "Unverified guess"
    with pytest.raises(ValueError):
        require_resolved("payout", save_register(tmp_path, register))


def test_unknown_operation_never_grants_approval():
    with pytest.raises(ValueError, match="Unknown rules operation"):
        require_resolved("voluntary_one_per_band")


def test_missing_register_never_grants_approval(tmp_path):
    with pytest.raises(FileNotFoundError):
        require_resolved("recommendation", tmp_path / "missing.json")

"""Fail-closed decision gates for future 2026 pool services.

Passing a gate only establishes recorded rule resolution, not roster legality
or that a scoring implementation correctly implements the decisions.
"""

import json
import warnings
from datetime import datetime
from pathlib import Path


SUBSTITUTION_DECISIONS = (
    "unused_substitutes", "activated_substitutes", "substitute_bands",
    "overlapping_picks", "duplicate_substitutes", "simultaneous_withdrawals",
    "replacement_eligibility", "substitute_withdrawal", "walkovers",
)
DEPENDENCIES = {
    "substitution": SUBSTITUTION_DECISIONS,
    "scoring": ("walkovers", "mixed_bonus_order", "semifinal_points"),
    "accounting": ("unused_substitutes", "activated_substitutes", "random_accounting"),
    "random_assignment": ("random_accounting", "random_fallback"),
    "submission": ("partial_submissions", "submission_bonus"),
    "payout": ("ties_payouts",),
    "event_mapping": ("canada_event",),
    "recommendation": SUBSTITUTION_DECISIONS + (
        "mixed_bonus_order", "semifinal_points", "random_accounting",
        "partial_submissions", "canada_event",
    ),
}
REGISTER_PATH = Path(__file__).with_name("rule_decisions_2026.json")


class UnresolvedRulesError(ValueError):
    """A requested operation depends on rules awaiting commissioner evidence."""

    def __init__(self, operation, blockers, register_version):
        self.operation = operation
        self.blockers = blockers
        self.register_version = register_version
        super().__init__(
            "{} blocked by unresolved rules ({}): {}".format(
                operation, register_version, ", ".join(blockers)
            )
        )


class ProvisionalRulesWarning(UserWarning):
    """An operation is proceeding with unconfirmed engineering assumptions."""


def load_register(path=None):
    """Read and validate the entire register, including confirmation provenance."""
    with Path(path or REGISTER_PATH).open(encoding="utf-8") as source:
        register = json.load(source)
    if not isinstance(register, dict) or register.get("schema_version") != 1:
        raise ValueError("Unsupported rule register schema")
    if not isinstance(register.get("register_version"), str) or not register["register_version"].strip():
        raise ValueError("Missing register version")
    rules_source = register.get("rules_source")
    if not isinstance(rules_source, dict) or not rules_source.get("version"):
        raise ValueError("Missing rules source version")
    if rules_source.get("sha256") != "d411c9e436bd64c9ecce679eee0a3027f47773404d76ecab2d1346939c938384":
        raise ValueError("Rules source changed; review the specification and gate dependencies")
    decisions = register.get("decisions")
    expected = {key for values in DEPENDENCIES.values() for key in values}
    if not isinstance(decisions, dict) or set(decisions) != expected:
        raise ValueError("Missing or unknown rule decisions; review gate dependencies")
    for key, entry in decisions.items():
        if not isinstance(entry, dict):
            raise ValueError("Invalid decision: " + key)
        for field in ("question", "reference"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError("Missing {}: {}".format(field, key))
        if entry.get("status") == "unresolved":
            if entry.get("decision") is not None or entry.get("confirmation") is not None:
                raise ValueError("Unresolved decision contains confirmation: " + key)
        elif entry.get("status") == "provisional":
            for field in ("decision", "rationale"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    raise ValueError("Missing provisional {}: {}".format(field, key))
            if entry.get("confirmation") is not None:
                raise ValueError("Provisional decision cannot claim confirmation: " + key)
            if not isinstance(register.get("assumption_source"), str) or not register["assumption_source"].strip():
                raise ValueError("Missing provisional assumption source")
        elif entry.get("status") == "confirmed":
            if not isinstance(entry.get("decision"), str) or not entry["decision"].strip():
                raise ValueError("Missing confirmed decision: " + key)
            evidence = entry.get("confirmation")
            fields = ("source", "source_version", "confirmed_by", "confirmed_at")
            if not isinstance(evidence, dict) or any(
                not isinstance(evidence.get(field), str) or not evidence[field].strip()
                for field in fields
            ):
                raise ValueError("Missing commissioner provenance: " + key)
            timestamp = datetime.fromisoformat(evidence["confirmed_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Confirmation timestamp requires timezone: " + key)
        else:
            raise ValueError("Unknown decision status: " + key)
    return register


def require_resolved(operation, path=None, *, allow_provisional=False):
    """Return the validated register or raise with affected IDs and questions.

    An explicit path permits a version-pinned local register. It does not
    authenticate evidence; commissioner confirmations still require review.
    Development callers may explicitly allow recorded provisional decisions;
    these emit a warning and remain labeled provisional in the returned register.
    """
    if operation not in DEPENDENCIES:
        raise ValueError("Unknown rules operation: " + str(operation))
    register = load_register(path)
    accepted_statuses = {"confirmed", "provisional"} if allow_provisional else {"confirmed"}
    blockers = {
        key: register["decisions"][key]["question"]
        for key in DEPENDENCIES[operation]
        if register["decisions"][key]["status"] not in accepted_statuses
    }
    if blockers:
        raise UnresolvedRulesError(operation, blockers, register["register_version"])
    provisional = [
        key for key in DEPENDENCIES[operation]
        if register["decisions"][key]["status"] == "provisional"
    ]
    if provisional:
        warnings.warn(
            "{} uses provisional rules ({}): {}".format(
                operation, register["register_version"], ", ".join(provisional)
            ),
            ProvisionalRulesWarning,
            stacklevel=2,
        )
    return register

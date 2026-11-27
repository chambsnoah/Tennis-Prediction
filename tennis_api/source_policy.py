"""Fail-closed evaluation of the historical source policy's permission gates.

The decision record lives in ``docs/data/historical_source_policy.json``. This
module derives which restricted actions that record's *evidence* supports; it
never reads the declared ``allowed_actions`` flags, an owner's source selection or
a free-access announcement as permission. It validates declarations only: it does
not contact the source, authenticate correspondence or retrieve any data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

RESTRICTED_ACTIONS = ("automated_ingestion", "publication", "paid_prize_pool_use")
_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_RIGHTS_HOLDER = "rights_holder"
_VERIFIED_ACCESS = "verified_at_pinned_revision"
_RESTRICTED_EVIDENCE_PREFIX = "restricted:"
_README_NAMES = ("README",)
_LICENSE_NAMES = ("LICENSE", "LICENCE", "COPYING")


@dataclass(frozen=True)
class GateDecision:
    """Whether one restricted action is supported, with every unmet requirement."""

    action: str
    allowed: bool
    unmet: tuple[str, ...]


def load_policy(path: Path) -> dict[str, Any]:
    """Read a policy record; the caller chooses the path, nothing is fetched."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("source policy must be a JSON object")
    return loaded


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _date(value: object) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _repository_path(repository: object) -> tuple[str, str] | None:
    """Owner and name of a ``https://github.com/<owner>/<name>`` repository."""
    text = _text(repository)
    if text is None:
        return None
    parts = urlsplit(text)
    segments = [s for s in parts.path.split("/") if s]
    if (
        parts.scheme != "https"
        or parts.netloc != "github.com"
        or parts.query
        or parts.fragment
        or len(segments) != 2
    ):
        return None
    return segments[0], segments[1]


def _pinned(
    evidence: object,
    repository: tuple[str, str] | None,
    revision: str,
    file_names: tuple[str, ...],
) -> bool:
    """README/license evidence must name the file at the reviewed revision.

    Only the URL path counts: ``github.com/<owner>/<name>/blob/<sha>/<file>`` or
    ``raw.githubusercontent.com/<owner>/<name>/<sha>/<file>``. A revision in the
    query or fragment, another repository, or a different file does not pin it.
    """
    if not isinstance(evidence, Mapping) or repository is None:
        return False
    url = _text(evidence.get("url"))
    if url is None or _date(evidence.get("retrieved_on")) is None:
        return False
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.query or parts.fragment:
        return False
    segments = parts.path.split("/")[1:]
    if parts.netloc == "github.com" and segments[2:3] == ["blob"]:
        segments = segments[:2] + segments[3:]
    elif parts.netloc != "raw.githubusercontent.com":
        return False
    return (
        len(segments) == 4
        and (segments[0], segments[1]) == repository
        and segments[2] == revision
        and segments[3].upper().startswith(file_names)
    )


def _source_unmet(source: Mapping[str, Any]) -> list[str]:
    unmet: list[str] = []
    repository = _repository_path(source.get("repository"))
    revision = _text(source.get("revision"))
    if source.get("access_status") != _VERIFIED_ACCESS:
        unmet.append("source_access_not_verified")
    if revision is None or _FULL_SHA.fullmatch(revision) is None:
        unmet.append("no_full_immutable_revision")
        revision = None
    if source.get("terms_verified") is not True:
        unmet.append("terms_not_verified")
    if _text(source.get("license")) is None or _text(source.get("license_url")) is None:
        unmet.append("license_not_recorded")
    if revision is None or not _pinned(
        source.get("readme_evidence"), repository, revision, _README_NAMES
    ):
        unmet.append("readme_not_pinned")
    if revision is None or not _pinned(
        source.get("license_evidence"), repository, revision, _LICENSE_NAMES
    ):
        unmet.append("license_not_pinned")
    return unmet


def _valid_approval(
    approval: object, action: str, revision: str | None, as_of: date
) -> bool:
    if not isinstance(approval, Mapping):
        return False
    actions = approval.get("actions")
    granted = _date(approval.get("granted_on"))
    expires_raw = approval.get("expires_on")
    expires = _date(expires_raw)
    evidence = _text(approval.get("evidence_reference"))
    return (
        approval.get("grantor") == _RIGHTS_HOLDER
        and isinstance(actions, list)
        and action in actions
        and revision is not None
        and approval.get("source_revision") == revision
        and evidence is not None
        and evidence.startswith(_RESTRICTED_EVIDENCE_PREFIX)
        and evidence[len(_RESTRICTED_EVIDENCE_PREFIX):].strip() != ""
        and granted is not None
        and granted <= as_of
        and (expires_raw is None or (expires is not None and as_of <= expires))
    )


def evaluate_gates(policy: Mapping[str, Any], as_of: date) -> dict[str, GateDecision]:
    """Derive restricted-action permissions from verified evidence only.

    Each action needs verified access at a full 40-character revision, verified
    terms with a recorded license, README and license evidence pinned to that
    revision, and an unexpired rights-holder approval naming the action and the
    revision, with its evidence held in restricted storage. Anything else,
    including selection, cost or declared flags, leaves the action blocked.
    """
    source = policy.get("source")
    permissions = policy.get("permissions")
    source = source if isinstance(source, Mapping) else {}
    approvals = permissions.get("approvals") if isinstance(permissions, Mapping) else None
    approvals = approvals if isinstance(approvals, list) else []
    source_unmet = _source_unmet(source)
    revision = _text(source.get("revision")) if not source_unmet else None
    decisions: dict[str, GateDecision] = {}
    for action in RESTRICTED_ACTIONS:
        unmet = list(source_unmet)
        if not any(_valid_approval(item, action, revision, as_of) for item in approvals):
            unmet.append("no_valid_rights_holder_approval")
        decisions[action] = GateDecision(action, not unmet, tuple(unmet))
    return decisions


def declared_actions_exceed_evidence(
    policy: Mapping[str, Any], as_of: date
) -> tuple[str, ...]:
    """Name declared ``allowed_actions`` that the evidence does not support."""
    permissions = policy.get("permissions")
    declared = permissions.get("allowed_actions") if isinstance(permissions, Mapping) else None
    declared = declared if isinstance(declared, Mapping) else {}
    decisions = evaluate_gates(policy, as_of)
    return tuple(
        action
        for action, value in declared.items()
        if value is not False
        and not (action in decisions and decisions[action].allowed and value is True)
    )

"""NumPy-backed pool jobs: tournament scenarios and recommendations from a trusted provider.

These run inside a bounded worker (``web_interface.jobs``). They always use the
bundled rule register (never a caller path) and pass ``allow_provisional``
through unchanged, so strict mode still blocks on provisional decisions.
Errors leave as safe reason codes only.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import numpy as np

from tennis_pool.optimizer import ScenarioSet, _gate, build_scenarios, recommend
from tennis_pool.rules import ProvisionalRulesWarning, UnresolvedRulesError
from web_interface.artifacts import load_provider
from web_interface.errors import ServiceError
from web_interface.services import RecommendationJob, ScenarioJob


@contextmanager
def _pool_errors() -> Iterator[None]:
    try:
        with warnings.catch_warnings():
            # Provisional rule use is recorded in the returned assumptions instead.
            warnings.simplefilter("ignore", ProvisionalRulesWarning)
            yield
    except ServiceError:
        raise
    except UnresolvedRulesError:
        raise ServiceError("rules_unresolved", 409) from None
    except (ValueError, TypeError, KeyError):
        # Pool validation messages can quote inputs; return a stable code instead.
        raise ServiceError("invalid_pool_request", 422) from None


def _scenarios(job: ScenarioJob) -> ScenarioSet:
    provider = load_provider(job.artifact)
    return build_scenarios(
        job.draw, provider, kind=job.kind, cutoff=job.cutoff, simulations=job.simulations,
        seed=job.seed, withdrawal_probabilities=dict(job.withdrawal_probabilities) or None,
        max_withdrawal_patterns=job.max_withdrawal_patterns, rankings=job.rankings,
        allow_provisional=job.allow_provisional, register_path=None)


def _rules(allow_provisional: bool) -> dict[str, object]:
    """The rule register version and decision statuses the scenarios were scored under."""
    version, decisions = _gate(allow_provisional, None)
    return {"register_version": version,
            "decisions": [{"key": key, "status": status, "decision": text}
                          for key, status, text in decisions]}


def _run(function: Callable[[], dict[str, object]]) -> dict[str, object]:
    with _pool_errors():
        return function()


def scenario_job(job: ScenarioJob) -> dict[str, object]:
    def run() -> dict[str, object]:
        scenarios = _scenarios(job)
        points = scenarios.points.astype(np.float64)
        return {
            "digest": scenarios.digest,
            # Provisional rule use is reported here instead of as a warning.
            "rules": _rules(job.allow_provisional),
            "artifact": job.artifact.name,
            "artifact_sha256": job.artifact.sha256,
            "assumptions": scenarios.assumptions.to_dict(),
            "players": [{
                "player_id": player,
                "seed": seed,
                "mean_points": float(points[i].mean()),
                "p90_points": float(np.quantile(points[i], 0.9)),
                "withdrawn_share": float(scenarios.withdrawn[i].mean()),
            } for i, (player, seed) in enumerate(zip(scenarios.player_ids, scenarios.seeds))],
        }
    return _run(run)


def recommendation_job(job: RecommendationJob) -> dict[str, object]:
    def run() -> dict[str, object]:
        scenarios = _scenarios(job.scenarios)
        result = recommend(scenarios, job.scenarios.draw, job.event_id, entry=job.entry,
                           allow_provisional=job.scenarios.allow_provisional,
                           register_path=None)
        return {"scenario_digest": scenarios.digest, "artifact": job.scenarios.artifact.name,
                "artifact_sha256": job.scenarios.artifact.sha256,
                "recommendations": result.to_dict()}
    return _run(run)

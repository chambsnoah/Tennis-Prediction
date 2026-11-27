"""NumPy-backed dashboard decision job: one event decision in its season context.

Runs inside a bounded worker. From the trusted season inputs it replays the
ledger at the information cutoff, builds shared scenarios from the verified
provider, models the rival field (known versus estimated picks), and then
either plans the event against the rest of the season (when prospects cover
every later event) or optimizes this event alone. A locked sheet, if given, is
checked for legality and scored on the same scenarios. Everything reuses the
merged pool modules; nothing here re-implements their logic.

Outputs are model-conditional estimates with their uncertainty, versions and
coverage, never guarantees. Errors leave as safe reason codes only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, time, timezone
from typing import Any

import numpy as np

from tennis_api.models.canonical import MatchProbability, MatchProbabilityProvider
from tennis_pool.ledger import EntryState, EventTerms
from tennis_pool.optimizer import (
    Objective, Recommendation, build_scenarios, evaluate, optimize,
)
from tennis_pool.payouts import PayoutConfig, payout_config
from tennis_pool.rivals import AppealSnapshot, KnownPick, RivalModel, model_rival_field
from tennis_pool.season import FutureEvent, SeasonObjective, SeasonPlan, plan_event
from tennis_pool.substitutions import validate_roster
from web_interface.artifacts import load_provider
from web_interface.dashboard import (
    SeasonInputs, build_ledger, decision_baseline, entry_states, mode, season_errors,
    season_summary,
)
from web_interface.errors import ServiceError
from web_interface.pool_jobs import _pool_errors, _rules
from web_interface.services import DecisionJob

PAYOUT_FIELDS = (40, 60, 80)
NOTICE = ("Model-conditional estimates from the configured provider, the stated "
          "assumptions and search limits. Tennis outcomes are uncertain; no sheet is "
          "guaranteed to score, place or win.")


class RecordingProvider:
    """Pass-through provider that tallies versions, coverage and warnings it returned."""

    def __init__(self, provider: MatchProbabilityProvider) -> None:
        self._provider = provider
        self.predictions = 0
        self.models: Counter[str] = Counter()
        self.calibrations: Counter[str] = Counter()
        self.missing: Counter[str] = Counter()
        self.warnings: Counter[str] = Counter()
        self.latest_cutoff: datetime | None = None

    def predict(self, context: Any) -> MatchProbability:
        result = self._provider.predict(context)
        if isinstance(result, MatchProbability):
            self.predictions += 1
            self.models[result.model_version] += 1
            self.calibrations[result.calibration_version or "uncalibrated"] += 1
            self.missing.update(result.coverage.missing)
            self.warnings.update(result.warnings)
            if self.latest_cutoff is None or result.cutoff > self.latest_cutoff:
                self.latest_cutoff = result.cutoff
        return result

    def summary(self) -> dict[str, object]:
        def table(counts: Counter[str]) -> list[dict[str, object]]:
            return [{"value": k, "count": n} for k, n in sorted(counts.items())]
        return {"predictions": self.predictions, "model_versions": table(self.models),
                "calibration_versions": table(self.calibrations),
                "uncalibrated": "uncalibrated" in self.calibrations,
                "missing_coverage": table(self.missing), "warnings": table(self.warnings),
                "latest_prediction_cutoff": (self.latest_cutoff.isoformat()
                                             if self.latest_cutoff else None)}


def _parse(cls: Any, items: tuple[Mapping[str, Any], ...]) -> list[Any]:
    try:
        return [cls.from_dict(item) for item in items]
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ServiceError("invalid_season_input", 503) from None


def _payout(participants: int, allow_provisional: bool) -> PayoutConfig | None:
    if participants not in PAYOUT_FIELDS:
        return None
    return payout_config(participants, allow_provisional=allow_provisional)


def _later(season: SeasonInputs, terms: EventTerms) -> tuple[str, ...]:
    return tuple(t.event_id for t in sorted(season.events, key=lambda t: t.deadline)
                 if t.deadline > terms.deadline)


def _plan_summary(plan: SeasonPlan) -> dict[str, object]:
    def projection(p: Any) -> dict[str, object]:
        data: dict[str, object] = p.to_dict()
        data.pop("recommendation")
        data["pairs"] = [pair.to_dict() for pair in p.recommendation.best.pairs]
        return data
    return {"objective": plan.objective.value, "chosen": plan.chosen.value,
            "projections": [projection(p) for p in plan.projections],
            "token_costs": [c.to_dict() for c in plan.token_costs],
            "use_costs": [c.to_dict() for c in plan.use_costs],
            "assumptions": plan.assumptions.to_dict()}


def _compare(job: DecisionJob, recommendation: Recommendation, entry: EntryState,
             scenarios: Any, rivals: RivalModel | None, payout: PayoutConfig | None,
             ) -> dict[str, object] | None:
    if job.compare is None:
        return None
    allow = job.scenarios.allow_provisional
    check = validate_roster(job.compare, job.scenarios.draw, job.event_id, entry,
                            allow_provisional=allow)
    problems = list(check.problems) + [
        problem for scenario in check.scenarios for problem in scenario.problems]
    simulated = set(scenarios.player_ids)
    if any(p.primary.player_id not in simulated
           or (p.substitute is not None and p.substitute.player_id not in simulated)
           for p in job.compare):
        # A player left the (revised) draw: keep the recommendation, report the sheet
        # as stale instead of scoring it.
        return {"pairs": [p.to_dict() for p in job.compare], "legal": False,
                "scorable": False, "problems": problems, "metrics": None,
                "same_as_best": False, "expected_points_vs_best": None,
                "robust_points_vs_best": None, "points_se": None}
    metrics = evaluate(scenarios, job.compare, rivals=rivals.field if rivals else None,
                       payout=payout if rivals else None,
                       robust_alpha=recommendation.search.limits.robust_alpha,
                       allow_provisional=allow)
    best = recommendation.best.metrics
    return {
        "pairs": [p.to_dict() for p in job.compare],
        "legal": check.legal,
        "scorable": True,
        "problems": problems,
        "metrics": metrics.to_dict(),
        "same_as_best": tuple(job.compare) == recommendation.best.pairs,
        "expected_points_vs_best": metrics.expected_points - best.expected_points,
        "robust_points_vs_best": metrics.robust_points - best.robust_points,
        # Paired differences on shared scenarios have no separate SE here; the
        # best policy's SE bounds the noise of either estimate.
        "points_se": best.points_se,
    }


def _coverage(job: DecisionJob, rivals: RivalModel | None, plan_note: str | None,
              payout: PayoutConfig | None, participants: int) -> list[str]:
    notes = []
    if not job.scenarios.withdrawal_probabilities:
        notes.append("No explicit withdrawal probabilities were supplied.")
    if rivals is None:
        notes.append("No rival entries in the season inputs: rank and payout objectives "
                     "are unavailable.")
    elif rivals.report.appeal_basis.startswith("scenario"):
        notes.append("No appeal snapshot: unknown rival picks chase the scenarios' mean "
                     "points.")
    if payout is None:
        notes.append(f"No printed payout schedule for {participants} participants: "
                     "payout objectives are unavailable.")
    if plan_note:
        notes.append(plan_note)
    notes.append("No news or injury observations feed these scenarios; only the draw, "
                 "rankings, withdrawal probabilities and the provider do.")
    return notes


def decision_job(job: DecisionJob) -> dict[str, object]:
    allow = job.scenarios.allow_provisional
    ledger = build_ledger(job.season, allow)
    terms = job.season.terms(job.event_id)
    cutoff = job.scenarios.cutoff
    if mode(terms, job.now) != "decision" or cutoff >= terms.deadline:
        raise ServiceError("deadline_passed", 409)
    with season_errors():
        snapshot = ledger.replay(cutoff)
        summary = season_summary(job.season, snapshot, job.event_id, job.now)
        # Decide from each entry's state before this event: an accepted sheet for it
        # is already charged by replay, and the chosen sheet must be charged once.
        states = {entry: decision_baseline(state, snapshot, job.event_id)
                  for entry, state in entry_states(job.season, snapshot).items()}
        known = [k for k in _parse(KnownPick, job.season.known_picks)
                 if k.event_id == job.event_id]
        appeal = next((a for a in _parse(AppealSnapshot, job.season.appeal)
                       if a.event_id == job.event_id), None)
        future = _parse(FutureEvent, job.season.future)
    own = states[job.season.entry_id]
    rival_states = tuple(states[e] for e in job.season.rival_ids)
    participants = len(job.season.entries)
    draw = job.scenarios.draw
    with _pool_errors():
        provider = RecordingProvider(load_provider(job.scenarios.artifact))
        scenarios = build_scenarios(
            draw, provider, kind=job.scenarios.kind, cutoff=cutoff,
            simulations=job.scenarios.simulations, seed=job.scenarios.seed,
            withdrawal_probabilities=dict(job.scenarios.withdrawal_probabilities) or None,
            max_withdrawal_patterns=job.scenarios.max_withdrawal_patterns,
            rankings=job.scenarios.rankings, allow_provisional=allow, register_path=None)
        # Play cannot start before the submission deadline, so the start is the later
        # of the draw's start date (00:00 UTC) and the deadline; the cutoff precedes both.
        starts_at = max(datetime.combine(draw.event.start_date, time(0), tzinfo=timezone.utc),
                        terms.deadline)
        rivals = None
        if job.season.rival_ids:
            rivals = model_rival_field(
                scenarios, ledger, draw, terms, starts_at=starts_at, cutoff=cutoff,
                rival_ids=job.season.rival_ids, seed=job.scenarios.seed, known_picks=known,
                appeal=appeal, allow_provisional=allow)
        payout = _payout(participants, allow)
        objective = Objective(job.objective)
        season_objective = SeasonObjective(job.season_objective)
        if objective in (Objective.P_TOP3, Objective.EXPECTED_PAYOUT) and rivals is None:
            raise ServiceError("objective_unavailable", 422)
        if objective is Objective.EXPECTED_PAYOUT and payout is None:
            raise ServiceError("objective_unavailable", 422)
        later = _later(job.season, terms)
        covered = {f.event_id for f in future}
        plan: SeasonPlan | None = None
        plan_note = None
        if set(later) <= covered:
            if season_objective is not SeasonObjective.EXPECTED_POINTS and not rival_states:
                raise ServiceError("objective_unavailable", 422)
            if season_objective is SeasonObjective.SEASON_PAYOUT and payout is None:
                raise ServiceError("objective_unavailable", 422)
            plan = plan_event(
                scenarios, draw, terms, cutoff=cutoff, entry=own, calendar=ledger.events,
                future=[f for f in future if f.event_id in later], seed=job.scenarios.seed,
                objective=season_objective, event_objective=objective,
                rivals=rivals.field if rivals else None,
                event_payout=payout if rivals else None, rival_states=rival_states,
                season_payout=payout if rival_states else None, allow_provisional=allow)
            recommendation = plan.recommendation
        else:
            plan_note = ("Season planning skipped: prospects are missing for "
                         f"{len(set(later) - covered)} later event(s), so no preservation "
                         "advice; this event is optimized alone.")
            recommendation = optimize(
                scenarios, draw, job.event_id, objective=objective, entry=own,
                rivals=rivals.field if rivals else None,
                payout=payout if rivals else None, allow_provisional=allow)
        compare = _compare(job, recommendation, own, scenarios, rivals, payout)
        rules = _rules(allow)
    return {
        "mode": "decision",
        "event_id": job.event_id,
        "deadline": terms.deadline.isoformat(),
        "cutoff": cutoff.isoformat(),
        "now": job.now.isoformat(),
        "starts_at": starts_at.isoformat(),
        "notice": NOTICE,
        "versions": {
            "artifact": job.scenarios.artifact.name,
            "artifact_sha256": job.scenarios.artifact.sha256,
            "scenario_digest": scenarios.digest,
            "scenarios": scenarios.assumptions.to_dict(),
            "rules": rules,
            "ledger_history_digest": snapshot.history_digest,
            "draw_provenance": draw.provenance.to_dict(),
            "ranking_snapshots": len(job.scenarios.rankings),
        },
        "provider": provider.summary(),
        "coverage_warnings": _coverage(job, rivals, plan_note, payout, participants),
        "season": summary,
        "rivals": rivals.report.to_dict() if rivals else None,
        "recommendation": recommendation.to_dict(),
        "plan": _plan_summary(plan) if plan else None,
        "compare": compare,
        "players": [{"player_id": p, "seed": s,
                     "mean_points": float(scenarios.points[i].mean()),
                     "p90_points": float(np.quantile(scenarios.points[i], 0.9)),
                     "withdrawn_share": float(scenarios.withdrawn[i].mean())}
                    for i, (p, s) in enumerate(zip(scenarios.player_ids, scenarios.seeds))],
    }


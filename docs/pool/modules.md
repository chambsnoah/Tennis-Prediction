# Pool Modules

Reference for the `tennis_pool` package. Rules and provisional decisions are in
[the 2026 rules specification](2026-rules.md).

## Canonical Pool Scoring

`tennis_pool.results.score_tournament(draw, matches, rankings, kind)` reconstructs
one complete canonical ATP bracket (`kind="gs"`, `"m7"` or `"m6"`). Supply the
fixed-order `Draw`, decided canonical `Match` records and official first-day
`RankingSnapshot` evidence. Missing needed rankings are errors, not default ranks.
Strict mode requires resolved scoring rules; explicitly opt into the recorded
development assumptions with `allow_provisional=True`. Unsupported rule versions
or changed scoring decisions require an implementation review and fail closed.

Results contain one terminal award plus cumulative played-win upset bonuses per
player, an input-evidence digest, PDF fingerprint/version, rule-register version
and the applied decision texts/statuses. Byes do not count as wins or participation;
walkovers advance without bonuses and need explicit withdrawal identity. A player
withdrawing before any played match or walkover advancement scores zero, including
after a bye. Later withdrawals retain earned terminal points and bonuses.
Retirements after play are played matches. Incomplete finals, unresolved entrants,
duplicate/incompatible matches and impossible progression are rejected. Raw
`WITHDRAWN` records need adjudication into a decided walkover before a complete
bracket can be scored; no replacement or season-ledger accounting is inferred.

The pure formulas live in `tennis_pool.scoring`; the legacy optimizer imports
them for compatibility, but its old name-based reconstruction/simulation is not
the gated canonical service and is not validated 2026 decision support.
Run synthetic scoring tests with
`uv run --locked python -m pytest tennis_pool/tests/test_pool_scoring.py`.

**Workbook parity remains unverified.** Exact scoring parity requires 564 player-event
comparisons, while the migrated optimizer README historically claimed 515.
Neither count is independently evidenced by an authorized corpus here. The
legacy diagnostic now fails on absent fixtures, inconsistent repeated observations,
component/total mismatches or a count other than 564; it is not canonical parity
proof. Only generated synthetic fixtures are published. Verifying parity requires
an authorized private audit and independently counted, versioned expected scores;
no source-data or workbook publication permission is granted by these tests.

## Season Ledger

`tennis_pool.ledger` is a local, append-only season ledger.
Open it with `SeasonLedger.create(event_terms)`, append evidence-bearing
`LedgerRecord` values with `append(...)`, and obtain immutable state with
`replay(cutoff)`. Both effective-time and information-availability cutoffs are
exclusive. `append` returns a new ledger; retain its history for later replay.
Explicit audited scores use `EventPoints(points=..., accounting_digest=...)`
with the matching replayed event state's `accounting_digest`. Changing the
accepted roster or accounting evidence requires corrected or cancelled scores;
old random-roster points cannot silently transfer to recovered voluntary picks.
Submitted choices, commissioner acceptance, activated selections and corrections
are distinct evidence; a workbook preview or export is not proof of acceptance.
Replay uses explicit information-availability and event cutoffs, preserves prior
history, and rejects conflicting duplicate records rather than silently rewriting
them. Separate Slam/Masters seed-band banks and the season-wide five-use limit
apply without an invented budget or one-player-per-band restriction.

Strict rule gates remain the default. Development must explicitly opt into
provisional accounting/submission decisions, and outputs retain rule provenance.
Unused substitutes consume nothing; approved activation transfers the original
selection's debit exactly once. This bookkeeping does not adjudicate withdrawal
eligibility or generate replacement scenarios; see Paired Substitutes below.
Random assignments remain event-prize-ineligible, and the seven-spreadsheet
250-point bonus is a once-only season award.

Only synthetic ledger and workbook reconciliation fixtures are published.
Real-workbook summary parity remains unverified pending an authorized private
audit; neither ingestion nor participant-data publication permission is implied.

## Paired Substitutes

`tennis_pool.substitutions` handles paired substitutes. Before the deadline,
`validate_roster(pairs, draw, event_id, entry_state)` checks five distinct
primaries, optional distinct same-band alternatives that are not also primaries,
and bands against the released draw's seeds. It then checks the event's remaining
Slam or Masters bank and the five-use cap under every activation combination.
Submit only when `legal` is true; problems name the failing player, band or scenario.

After withdrawals, `adjudicate(pairs, withdrawals, participation, as_of=...)`
decides each slot from one snapshot of evidence available before `as_of`. A
primary is replaced only if its official withdrawal precedes its first started
match or walkover advancement (a bye does not count), and only by its predeclared
substitute. There are no chains, no post-deadline picks and no replacement after a
loss. A substitute that withdraws before playing leaves the slot scoring zero.
Missing or conflicting timing evidence returns `BLOCKED` with the decision ID that
needs clarification. `activation_payload(...)` turns an unblocked result into the
ledger's `ApprovedActivation`, which transfers debits exactly once. Approval is
still a caller attestation. Strict mode blocks on the provisional register, and
changed substitution decisions require an implementation review.

## Pool Payouts

`tennis_pool.payouts` computes prize money. `payout_config(participants)` returns the
printed 2026 schedule for 40, 60 or 80 participants, in cents. Any other count,
or a commissioner adjustment, needs an explicit `ScheduleOverride` with its own
version, source and approval attestation. Season prizes refund the top five
$50 stakes, add the $25 sixth prize where the schedule has one, and split the
residual 57.5/27.5/10/5 percent, so they differ slightly from the rounded page 7
examples. Underfunded schedules are rejected.

`event_payouts(snapshot, event_id, config)` and `season_payouts(snapshot, config)`
pay from a ledger snapshot. Tied entries share the prizes of every position they
occupy, unpaid ones included, and leftover cents go to the lowest entry IDs.
Random-assigned entries are left out of event prizes but their points, like the
Excel bonus, count in the season standings. `outlook(samples, entry_id, config)`
reports expected payout separately from expected points and P(top-3) over
simulated scores, for event or season scope.

## Joint Roster Optimizer

`tennis_pool.optimizer` searches five primaries and their optional same-band
substitutes together. It needs the `simulation` extra (NumPy).

```python
from tennis_pool.optimizer import (
    Objective, build_scenarios, optimize, recommend, sample_rival_field,
)

scenarios = build_scenarios(
    draw, provider, kind="gs", cutoff=cutoff, simulations=10_000, seed=2026,
    withdrawal_probabilities={player_id: 0.04}, rankings=first_day_rankings,
    allow_provisional=True,
)
rivals = sample_rival_field(scenarios, projected_ownership, rivals=59, seed=7)
sheets = recommend(scenarios, draw, "australian_open", entry=entry_state,
                   rivals=rivals, payout=config, allow_provisional=True)
```

**Shared scenarios.** `build_scenarios` runs the tournament simulator and scores
every player with the pool tables and played-win bonuses, so one column is one
simulated tournament. Pre-match withdrawals are explicit, independent
probabilities for listed players only. Each distinct withdrawal pattern is
simulated again with that player removed: the opponent advances by walkover and
no lucky loser is drawn in. A policy scores its primary in each scenario, or its
substitute's result in that same scenario when the primary withdrew. Draw
correlations (two picks who meet early) and walkover effects therefore carry
into every objective. Marginal player values are never summed. Positive
withdrawal probabilities cannot be combined with a provider that already prices
availability risk. The draw must match the scoring kind's rounds, best-of, field
size and seed limit. Generated scenarios record the draw digest and are rejected
for any other draw. A `ScenarioSet` can also be built from caller arrays; it
keeps private read-only copies.

**Objectives.** `optimize(..., objective=...)` supports:

- `EXPECTED_POINTS`: mean points.
- `ROBUST`: the lower-tail mean (CVaR) of points over the worst
  `robust_alpha` share of scenarios, 20% by default.
- `P_TOP3`: the share of scenarios with fewer than three rivals strictly ahead.
- `EXPECTED_PAYOUT`: tie-shared event prize money, matching `payouts.outlook`.

The last two need ownership input: a `RivalField`, from the deadline-aware
`rivals.model_rival_field` (below), the simpler `sample_rival_field`, or the
caller. A rival field is bound to the
exact scenarios it was scored on through `ScenarioSet.digest`. Expected payout also needs a
`PayoutConfig` for exactly the rivals plus you. `recommend` returns every
objective it can and names the ones it skipped and why. `evaluate` scores a
policy of your own on the same scenarios.

**Search and disclosed limits.** `SearchLimits` sets the per-band pools (by
mean plus 90th-percentile points), the roster cap, the screening prefix, the
beam and the substitute passes. The search enumerates every bank-legal primary
roster in the pruned pool and screens them on a scenario prefix with greedy
covers. It then improves the substitutes of the beam on all scenarios: first
one slot at a time, then by re-choosing same-band slot pairs together. When the
whole policy space over every eligible player fits within `exhaustive_limit`,
it is also enumerated and the exhaustive optimum is returned. The heuristic's
in-sample gap is then measured, unless pruning left the heuristic no legal
roster, in which case the gap is reported as not measured. Without exhaustive
enumeration, expected points reports an upper bound from a relaxation, and the
other objectives report the gap as not measured. Too many rosters raise an error rather than being truncated silently.
On the synthetic small fixtures, default limits matched exhaustive search for
all four objectives. A 128-player draw with 10,000 scenarios takes roughly 5 to
20 seconds per objective.

**Legality.** Unused substitutes cost nothing, and every substitute shares its
primary's band. Primaries therefore fit the remaining Slam or Masters bank under
every activation combination. Players at five uses are excluded both as
primaries and as substitutes. Every returned policy is checked again with
`validate_roster`. Strict mode blocks on the provisional `recommendation`
decisions, and changed decision texts need an implementation review.

**Reporting.** Each `Recommendation` holds the best policy and up to five ranked
alternative primary rosters, with all metrics and standard errors. Under
exhaustive enumeration each roster carries its best substitutes. Otherwise it
carries the best assignment the heuristic found: every beam roster gets the
one-slot passes, but only the top `exchange_rosters` (20 by default, possibly
zero) also get the pairwise pass, and no pass changes three same-band slots at
once. An alternative ties the
best when its paired shortfall on the shared scenarios is within two standard
errors.
For P(top-3), any shortfall under 1.5 points also counts as a tie. Assumptions
record the objective definition, scenario seed and count, withdrawal model and
probabilities, ownership model, payout version, tie rule and rule decisions.
`Recommendation.to_dict()` round-trips. The scenario seed reproduces the
scenarios. Search limits, pruning counts and the gap basis are in `search`.

These are in-sample estimates that depend on the provider, the withdrawal and
ownership assumptions, and the search limits, not predictions of the winning
roster. `sample_rival_field` ignores rival substitutes and quotas, and a withdrawn
rival pick scores zero there; `model_rival_field` models both. The objectives cover one event only and do not value
quota or player uses saved for later events; Season Planning below does. The legacy web team optimizer still
uses annealing over a budget format. It is not 2026 decision support.

## Rival Selection Model

`tennis_pool.rivals` models what the other entries will pick, for the
optimizer's rank and payout objectives. It needs the `simulation` extra (NumPy).

```python
from tennis_pool.rivals import AppealSnapshot, KnownPick, model_rival_field

model = model_rival_field(
    scenarios, ledger, draw, event_terms, starts_at=first_match, cutoff=now,
    rival_ids=rival_entries, known_picks=revealed, appeal=favourites, seed=17,
    allow_provisional=True,
)
model.report.describe()      # known, partial, estimated and no-history rivals
sheets = recommend(scenarios, draw, event_id, entry=mine, rivals=model.field,
                   allow_provisional=True)
```

**What the analysis may see.** It runs before the deadline: a cutoff after the
submission deadline is rejected. Every `KnownPick` carries the time it became
legitimately known. A pick counts only if it was available strictly before both
the cutoff and the tournament start. Picks revealed at or after the start stay
hidden even when play starts before the cutoff. The report counts the picks
excluded for each reason. Banks, use counts and pick history come from one
`SeasonLedger.replay` at the same exclusive cut, and the draw, event terms and
appeal evidence must also predate it. An acceptance for this event that the
ledger already shows becomes a known sheet, and its debits are refunded so the
bank describes the state before the event. Known picks must name draw players
in their seed band, with same-band substitutes, within the rival's bank and
five-use cap.

**Unknown picks.** Each unknown sheet draws a band structure (picks per band)
from the rival's own accepted sheets for this bank kind. It is smoothed toward
the field's structures and toward every legal structure, and limited to the
remaining bank, the five-use cap and the known picks. At the last event of a
bank (US Open, Paris) rivals spend their expiring seeded tokens unless
`spend_expiring_bank=False`. Players are then drawn within each band in
proportion to `appeal^concentration x (1 + repeat_affinity x prior uses)`, a
current-strength signal plus mild loyalty, because the field follows current
strength more than pick history. Shared per-world noise moves the whole field
together, which captures herding and widens the ownership intervals. A rival's
substitutes come from the same band at its smoothed historical substitute rate.
A withdrawn rival primary hands its slot to its substitute in that scenario, as
for your own sheet. Without an `AppealSnapshot`, rivals chase the scenarios'
mean points, an ex-ante summary and never the column being scored.

**Keeping evidence apart.** Each rival is `KNOWN` (five primaries known),
`PARTIAL`, `ESTIMATED` (from its accepted history) or `NO_HISTORY`. Rivals
without history get broader personal noise, and a rival missing from the
ledger is flagged with a full bank assumed. `pick_certainty` is 1 for a known
sheet and falls as picks spread. Per-player ownership reports rivals known to
hold the player separately from the projected share and its interval across
worlds (80% by default). `RivalModelParameters` are unfitted priors and are
disclosed in every report.

**Randomness.** Selection draws come from children of a `SeedSequence` mixed
with a fixed tag, so the same integer seed never reuses a scenario stream. Each
scenario column picks its world from a separate stream. With an explicit
`AppealSnapshot`, changing tournament outcomes leaves every sampled sheet
unchanged. The scenario-mean fallback appeal is derived from the scenarios, so
it can change with them and gives no such guarantee. Each rival has its own
stream. The `RivalField` records `ScenarioSet.digest`, and the optimizer
rejects it on any other scenarios. `model.primaries`, `model.substitutes` and
`model.world_of_scenario` expose the read-only sampled sheets.

**Ownership evaluation.** `evaluate_ownership(ledger, cases, ...)` replays
past events walk-forward. Each `OwnershipCase` is projected at its own cutoff
with `project_ownership` inputs only, then scored against the primaries
accepted for that event as replayed at `outcome_cutoff`, after the deadline.
It reports rival-level Brier score, reliability bins, ownership MAE/RMSE over
relevant players, interval coverage and band-leader hits, per event and pooled.
Fully known rivals and known pairs are excluded from scoring, rivals without an
accepted sheet are counted as unscored, and known picks that the rival later
changed are counted. These metrics cover ownership only. No match results,
scenarios or player-performance quality enter them, so match-prediction quality
must be evaluated separately. Appeal snapshots used in backtests must be
pre-cutoff signals without overrides, head-to-head or injury flags. Tests use
synthetic entries only; no private pool history is published.

## Season Planning

`tennis_pool.season` plans each event as part of the season. It values the band
tokens and player uses a sheet spends against what they would be worth later.
It needs the `simulation` extra (NumPy).

```python
from tennis_pool.season import FutureEvent, Prospect, plan_event, replay_season

snapshot = ledger.replay(cutoff)
mine = next(e for e in snapshot.entries if e.entry_id == my_entry)
plan = plan_event(
    scenarios, draw, event_terms, cutoff=cutoff, entry=mine, calendar=ledger.events,
    future=later_events, seed=2026, rival_states=other_entries,
    season_payout=config, allow_provisional=True,
)
plan.recommendation          # the chosen policy's optimizer result
plan.token_costs, plan.use_costs
```

**Future events stay uncertain.** Each later event is a `FutureEvent` of
`Prospect` records: entry probability, a seeding rank and expected pool points
if the player enters. Every world samples who enters, seeds entrants by a noisy
rank (32 seeds, 16 at Monte Carlo and Paris) and draws gamma outcome noise
around the expected points. Participation and seeds become known only at that
event's own decision and outcomes never do. Players missing from the prospects
are worth zero. The calendar is the ledger's single deduplicated `events`
tuple. Its deadlines must be distinct, and `future` must cover every later
event in it exactly once. Prospects, the draw and every calendar entry's terms
must all be available before the cutoff, which must precede the deadline.

**Policies.** `GREEDY` optimizes the event on the whole remaining bank.
`RATIONED` caps each seeded band at `ration(bank, events_left)`: the remaining
tokens divided by the events left in that bank that seed the band, rounded up,
with everything spendable at the last one. When that share cannot fill a legal
sheet, the whole bank is allowed and the projection's `notes` say so.
`HORIZON` runs a backward dynamic
programme over every bank state of each bank (Slam, Masters) on planning
worlds. It picks this event's band structure to maximize expected points now
plus the expected value of the tokens left, and tokens expire after the last
event of their bank. The programme picks the best expected scorers within a
structure and ignores later use caps. All three policies hand their bank caps
to `optimizer.optimize`, which still chooses the exact primaries and
substitutes, and every sheet is checked again against the real entry state.

**Opportunity costs.** A forward simulation of the horizon policy on separate
evaluation worlds, with common random numbers, measures the later value of one
token or one player use. `TokenCost` compares the expected points the marginal
token of each band adds now with its value later. `UseCost` compares a
player's edge now (the plan's value with him minus without him, with the bands
re-chosen) with the later value of keeping one of his uses, and names the
events where that use would go. A use is preserved only when its later value
exceeds the edge now by more than two standard errors. On a tie the advice is
to spend it, since a player's uses can be stranded by injuries and skipped
events while band tokens cannot. Preservations are kept most valuable first and
dropped, with a note, when keeping them all would leave no legal sheet. A
player without whom no legal sheet exists has `edge_now=None` and is spent. A
token the sheet cannot do without is reported the same way. Costs start from
the same per-world charges as the projection, so a substitute that activates
is charged in those worlds and its cover value now is shown. Each cost carries
a plain-language explanation.

**Season objectives.** Each policy's projection pairs this event's scenario
columns with evaluation worlds and reports expected season points with a
standard error, the expected number of tokens left unused, and this event's
and later expected points. Given `rival_states` (the other entries' ledger
states at the same cutoff) it also reports P(season top 3), P(first), expected
season prize money from a `PayoutConfig` for every participant, and gaps to
named rivals (current gap, expected final gap and P(finishing ahead)). Without
`named_rivals`, the three entries just ahead are named. Rivals keep the
fair-share ration of their own bank and use caps and pick the best expected
scorers under lognormal choice noise, an unfitted prior. A rival with no legal
sheet submits nothing and scores zero. Their picks share each world's outcomes
with yours. When there are fewer scenario columns than evaluation worlds,
worlds sharing a column are treated as one independent draw in every standard
error (cluster-robust). Every legal sheet is assumed to be an Excel
submission, so the 250-point bonus is added in each world where an entry's
qualifying sheets reach seven; an event without a legal sheet does not count.
`SeasonObjective` selects expected points, expected season payout or P(top 3).
Policies within two paired standard errors (or 1.5 points of P(top 3)) tie, and
a tie goes to the policy spending fewer seeded tokens now.

**Sequential replay.** `replay_season(events, ledger=..., entry_id=...)` replays
`ReplayEvent` records in deadline order. Each policy decides from that event's
pre-cutoff inputs and its own ledger replayed at the cutoff. The replay then
appends the policy's own submission, acceptance, approved activations of
withdrawn primaries with substitutes and audited points, so later events see
the banks and uses that policy left. A substitute from an earlier sheet whose
outcome is not yet revealed at a cutoff has one use reserved there (listed in
`ReplayStep.reserved`, once per pending activation), so a late activation cannot break the five-use cap.
Outcomes must be revealed at or after the deadline and score every draw player
exactly once. Rival results must not include your own entry, and a payout
configuration must match its versioned derivation. Rival totals are the supplied
`rival_start` plus each event's `rival_points` (include their bonuses there).
Event and season prizes use the tie-sharing `split_prizes`. The comparison is
one realized season per policy. It must not be summed with independent weekly
backtests; use `plan_event` projections for expected differences.

**Repairs to the reference sequential script.** The old script appended a
hard-coded US Open, Shanghai and Paris to its workbook list, so the US Open
was counted twice once its workbook existed. It also ranked the season against
standings copied from a mid-season workbook while adding a later total and an
assumed bonus. Here the calendar comes from the ledger and the season total
comes from the policy's own ledger, bonus included. Banks also count activated
substitutes, ties share prizes, and each decision reads only pre-cutoff inputs.
Its chalk and variance event classes were not ported.

On a synthetic 13-event calendar the planner takes about four seconds per
event at default sizes (100 planning and 200 evaluation worlds). These are
model-conditional estimates. `PlanningParameters` (rank noise, outcome shape,
rival choice noise) are unfitted priors disclosed in every plan. Fitting them
and validating policies on real history needs the chronological backtesting
harness. Tests use synthetic entries only.

## Workbook Preview

`tennis_pool.workbooks.preview_workbook` is a read-only adapter for
authorized `.xlsx` / `.xlsm` input. Install the existing `excel` extra. Supply a
canonical ATP `Event`, its explicit `year`, a `format` (`GS128`, `M7`, or `M6`),
a reviewed `IdentityRegistry`, and workbook `Provenance`; filenames never infer
metadata or identities. Every player label requires an exact, source-scoped
reviewed alias. Registry revision/digest and source provenance accompany results.

```python
from tennis_pool.workbooks import preview_workbook

# event, registry and evidence are caller-supplied reviewed records.
preview = preview_workbook(
    authorized_event_path, event=event, year=2026, format="M7",
    registry=registry, provenance=evidence,
    # Optional separate season file; its provenance must also be supplied.
    season_path=authorized_season_path, season_provenance=season_evidence,
)
```

The frozen preview contains a canonical draw, player-ID ranking measurements,
sheet coverage summaries, and private local observations in `preview.season`:
pick history (including substitute slot labels), standings, remaining banks,
use counts and provided substitutions. These records retain participant labels
for local reconciliation but are excluded from default preview representations;
never publish or log them. Missing values remain `None`; workbook rankings
have no inferred effective date and are not canonical as-of ranking snapshots.
No ledger, season consumption, scoring or commit API is implemented.

Supported formats cover the four Slams (`GS128`: 128 slots/entrants, 32 seeds),
Indian Wells, Miami, Madrid, Rome, Canada, Cincinnati and Shanghai (`M7`: 128
slots, 96 entrants, 32 seeds), and Monte Carlo/Paris (`M6`: 64 slots, 56 entrants,
16 seeds). Use the legacy French event labels in `TOURNAMENTS`; explicit
Australian Open/French Open and Canadian Masters/Toronto/Montreal labels are
also accepted. Canada remains one event, not separate venue events. Only trailing,
empty-result bye padding at positions 65-128 can be removed from an M6 sheet;
other padding is rejected, never rebracketed heuristically.

Layouts follow the reference's positional sheets: `Draw` header in column A,
then position/player/rank/seed; `Rankings` rank/player; `Choix` participant blocks
with 13 player/band pairs from column C; `Classement` rows from row 5, totals in
Q; `Banques (Solde restant)` quotas from row 3 (full season or Masters-only);
`ChoixSommaire` participant headers in row 3 and player/use rows from row 5.
Recognized header labels and column order are validated. `Choix` rows labeled
`Substitut`/`Remplacant` are alternatives; an optional `Substitutions` sheet uses
exact headers `Participant, Event, Withdrawn, Replacement, Band`. Substitution
legality/activation is not inferred. Conflicting copies of a support sheet in
the event and season files fail rather than silently overwrite one another.

Check `missing_sheets`, `unsupported_sheets`, summary `missing_values`, and
`warnings` before using a preview. Absent support files/sheets, Masters-only Slam
quotas and missing formula caches are explicit; nothing is filled with zero or
a guessed rank. Both cached-value and formula views are read, without formula
evaluation; missing identity caches make the affected layout unsupported.
`WorkbookImportError` exposes only safe reason codes. Parser warnings are captured
and reduced to `workbook_parser_warning`, never emitted with source metadata.
`WorkbookLimits` defaults
to 8 MiB/file, 32 MiB expanded ZIP, 256 members, 10,000 rows/sheet, 128 columns,
and 300,000 actual/dense cells across worksheets per file, enforced before
openpyxl parsing. DTD/entities and malformed/duplicate ZIP or cell structures are
rejected. Workbooks always close; VBA is not retained/executed and external links
are not loaded. Worksheet relationships must target local `xl/worksheets/*.xml`
members so relocated payloads cannot bypass preflight. This is bounded data
parsing, not an untrusted-file sandbox.

Tests generate wholly synthetic workbooks at runtime. No real workbook has been
audited or compatibility-certified; unfamiliar headers/layouts remain explicit
limitations. Legacy `pool_optimizer/pool/parsers.py` is unchanged. This adapter
does not authorize private-data publication or unblock historical data
retrieval; the [historical source policy](../data/HISTORICAL_SOURCE_POLICY.md)
still applies.

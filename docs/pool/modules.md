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

The last two need ownership input: a `RivalField`, either from
`sample_rival_field` or supplied by the caller. A rival field is bound to the
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
it is also enumerated. The exhaustive optimum is then returned, along with the
heuristic's measured in-sample gap, even when pruning left the heuristic no roster. Otherwise expected points reports an upper
bound from a relaxation, and the other objectives report the gap as not
measured. Too many rosters raise an error rather than being truncated silently.
On the synthetic small fixtures, default limits matched exhaustive search for
all four objectives. A 128-player draw with 10,000 scenarios takes roughly 10 to
25 seconds per objective.

**Legality.** Unused substitutes cost nothing, and every substitute shares its
primary's band. Primaries therefore fit the remaining Slam or Masters bank under
every activation combination. Players at five uses are excluded both as
primaries and as substitutes. Every returned policy is checked again with
`validate_roster`. Strict mode blocks on the provisional `recommendation`
decisions, and changed decision texts need an implementation review.

**Reporting.** Each `Recommendation` holds the best policy and up to five ranked
alternative primary rosters, each with its best substitutes, with all metrics
and standard errors. An alternative ties the best
when its paired shortfall on the shared scenarios is within two standard errors.
For P(top-3), any shortfall under 1.5 points also counts as a tie. Assumptions
record the objective definition, scenario seed and count, withdrawal model and
probabilities, ownership model, payout version, tie rule and rule decisions.
`Recommendation.to_dict()` round-trips. The scenario seed reproduces the
scenarios. Search limits, pruning counts and the gap basis are in `search`.

These are in-sample estimates that depend on the provider, the withdrawal and
ownership assumptions, and the search limits, not predictions of the winning
roster. The rival model ignores rival substitutes and quotas, and a withdrawn
rival pick scores zero. The objectives cover one event only and do not value
quota or player uses saved for later events. The legacy web team optimizer still
uses annealing over a budget format. It is not 2026 decision support.

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

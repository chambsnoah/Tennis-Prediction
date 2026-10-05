# 2026 ATP Pool Rule Specification

Status: provisional specification v2, 2026-10-04, issue #4. **Not commissioner-confirmed.**
The published PDF supports the rules below; it does not resolve the decision
register. No commissioner response has been received or fabricated.
The user authorized best-guess interpretations on 2026-10-04. Development may
proceed with the explicit provisional decisions below without waiting for a
commissioner response. These assumptions may need revision for actual pool use.

## Sources and Authority

- Authoritative source: local `tennis/data/Règlements_2026 (1).pdf`, eight pages,
  SHA-256 `d411c9e436bd64c9ecce679eee0a3027f47773404d76ecab2d1346939c938384`.
- Implementation reference only: local `tennis/pool/scoring.py`, SHA-256
  `7c4d11c3bfe43e06a235555f8db0a70d997c87a0987de124b5389c1ff5a8907a`.
- Neither source project was modified. The PDF, participant records, private
  submissions, and workbooks are not copied into this repository.
- Page numbers below are PDF page numbers. Published rules, worked examples,
  implementation assumptions, and commissioner decisions are distinct evidence.

## Events and Selection

Rules 1-3, pages 1-2; scoring categories from rule 11, page 3:

| Event ID | Event | Bank | Scoring | Published seed count |
| --- | --- | --- | --- | --- |
| australian_open | Australian Open | Grand Slam | GS | 32 |
| indian_wells | Indian Wells | Masters | M7 | 32 |
| miami | Miami | Masters | M7 | 32 |
| monte_carlo | Monte Carlo | Masters | M6 | 16 |
| madrid | Madrid | Masters | M7 | 32 |
| rome | Rome | Masters | M7 | 32 |
| roland_garros | Roland-Garros | Grand Slam | GS | 32 |
| wimbledon | Wimbledon | Grand Slam | GS | 32 |
| canada | Canadian Masters | Masters | M7 | 32 |
| cincinnati | Cincinnati | Masters | M7 | 32 |
| us_open | US Open | Grand Slam | GS | 32 |
| shanghai | Shanghai | Masters | M7 | 32 |
| paris | Paris | Masters | M6 | 16 |

The PDF alternates between Toronto (rules 1, 2, 12) and Montreal (rules 11,
16). `canada` identifies one event, not two. Confirm venue/name and actual
event metadata before joining a schedule; no dates are inferred here.

Each voluntary submission selects five primary players after the men's main
draw is released and before the announced first-round deadline. The examples
of Friday/Monday timing are not fixed calendar rules. Store the actual deadline
with a timezone and source. The page 5 example allows a replacement after the
tournament begins when the primary's first match has not started.

| Seasonal bank | Seeds 1-4 | Seeds 5-8 | Seeds 9-16 | Seeds 17-32 | Unseeded |
| --- | ---: | ---: | ---: | ---: | --- |
| Four Grand Slams | 4 | 4 | 4 | 4 | Unlimited |
| Nine Masters | 9 | 9 | 9 | 7 | Unlimited |

These are separate season-long band banks, not per-event roster slots. There
is **no published one-per-band restriction on voluntary selections**. Multiple
players in the same band are not disallowed merely by their band. Rule 3 also
limits each ATP player to five tournaments across the entire season, including
unseeded players. Use event seeds, not ATP rankings, for seeded bank categories.
Accounting for withdrawals, substitutes, and random assignments uses the
provisional decisions below when provisional mode is enabled.
Do not use the four-band scoring grouping for the five-category selection banks.

## Substitutions and Eligibility

Rule 6, page 2, encourages but does not require five alternatives in addition to
the five primaries. The page 5 example pairs each alternative with a primary;
Fritz's pre-first-match withdrawal activates his paired substitute Musetti.
Five pairs are the representation for a complete substitute submission, not a
claim that substitutes are mandatory. Provisionally, partial alternatives are
allowed; primaries must still form a complete legal five-player roster.

A primary who withdraws before playing and has no supplied replacement scores
zero (rule 6), not the normal first-round-loss point. A supplied replacement
does not remove tournament-prize eligibility (rule 14, page 6). Retirement
after a match starts is not the pre-first-match withdrawal described by rule 6.

The example uses same-band pairs but does not establish a universal same-band
requirement. It does not establish quota refunds, substitute use accounting,
duplicate handling, or activation order. See the decision register; these are
not silently inferred from the example.

## Points

Rule 11, page 3: award one terminal-round value, **not** cumulative round points.
The prose incorrectly says a semifinal loss earns 140/70; the table and page 5
example give 90/45. Record this conflict rather than calling it confirmed.

| Terminal result | GS | M7 | M6 |
| --- | ---: | ---: | ---: |
| Champion | 200 | 100 | 100 |
| Final loss | 140 | 70 | 70 |
| Semifinal loss | 90 | 45 | 45 |
| Quarterfinal loss | 50 | 25 | 25 |
| Fourth-round loss | 30 | 15 | N/A |
| Third-round loss | 15 | 7 | 15 |
| Second-round loss | 7 | 4 | 7 |
| First-round loss | 1 | 1 | 1 |

For loss-round indexing from round 1, the sequences are GS
`[1, 7, 15, 30, 50, 90, 140]`, M7 `[1, 4, 7, 15, 25, 45, 70]`, and M6
`[1, 7, 15, 25, 45, 70]`; champion values are separate. Byes are not wins
against an opponent. Provisionally, walkovers advance terminal-round scoring
but do not earn upset bonuses; see the decisions below for withdrawal handling.

Rule 12, page 4: bonuses accumulate for each victory over a better player.

| Winner category | Defeated category | GS bonus | Masters bonus |
| --- | --- | ---: | ---: |
| Seed 1-4 | Better seed 1-4 | 20 | 10 |
| Seed 5-8 | Seed 1-4 | 30 | 15 |
| Seed 5-8 | Better seed 5-8 | 10 | 5 |
| Seed 9-16 | Seed 1-4 | 40 | 20 |
| Seed 9-16 | Seed 5-8 | 20 | 10 |
| Seed 9-16 | Better seed 9-16 | 10 | 5 |
| Other (seed 17-32 or unseeded) | Seed 1-4 | 50 | 25 |
| Other | Seed 5-8 | 30 | 15 |
| Other | Seed 9-16 | 20 | 10 |
| Other | Better Other | 10 | 5 |

Other victories have no listed bonus. Seed numbers order seeded players within
a band. Unseeded ranks use the ATP world ranking as of the tournament's first
day (footnote, page 4), not a later live ranking. Missing ranking data must not
be invented. Mixed seeded/unseeded ordering within Other is provisionally
seed-first, as recorded below.
The reference code's `atp_rank + 32` makes every seed outrank every unseeded
player; this is an implementation assumption, not commissioner evidence.

Published worked example (page 5): five totals `200, 120, 1, 15, 55`, comprising
321 terminal-round points and 70 bonus points, sum to **391**. This is an audit
fixture, not actual participant data or proof of all edge cases.

## Submissions and Random Assignments

Rules 4-5, page 2, and 16, pages 7-8:

- Spreadsheet attachment by email is encouraged; email text alone is accepted.
- At least seven spreadsheet submissions out of thirteen earn a single 250-point
  **season standings** bonus, not 250 points per tournament. Late/corrected
  attachment qualification follows the provisional submission decision below.
- Missed/late submissions receive random assignments for at most three events.
  From the fourth missed submission onward, no players are assigned.
- Random-assignment points count toward the season standings but not eligibility
  for that event's prize. This exclusion does not apply to supplied substitutes.
- Rule 8 requires remaining seeded banks to be communicated with the draw.
- Rules 7 and 9 describe auditable commissioner submission and disclosure of
  choices after tournament start; this does not authorize publishing private data.

Random assignment is a separate procedure, **not voluntary roster legality**:

| Draw | Initial random slots | Stated fallback when a seeded bank is unavailable |
| --- | --- | --- |
| 32 seeds | 1-4, 5-8, 9-16, 17-32, unseeded | Next lower band; 17-32 falls to unseeded |
| 16 seeds | 1-4, 5-8, 9-16, unseeded, unseeded | Next lower band; 9-16 falls to unseeded |

The PDF does not define recursive fallback when several banks are exhausted,
sampling order when fallback slots collide, duplicate exclusion, exhausted
five-use players, or the resulting bank/use debits. Development implementations
may follow the explicit provisional random-assignment decisions below.

## Ties and Payouts

Rules 13-15, pages 6-7:

- Entry stake is $50 per participant.
- At the illustrative 80-participant level, each event pays $70/$35/$20 to
  first/second/third. Tied participants share prizes, but tie spans and rounding
  are unspecified. Random-assigned entries are ineligible for event prizes.
- Season scores sum all thirteen events plus any earned submission bonus.
- Season top five recover $50 each. Sixth may receive $25 if participation
  permits. The residual is shared approximately 57.5%/27.5%/10%/5% by top four.
- The printed 80-person residual is `80*50 - 13*(70+35+20) - 5*50 - 25 = 2100`.
  Its percentages plus refunded stakes do not exactly match the rounded page 7
  season examples ($1260/$630/$260/$150/$50/$25). Do not treat examples as an
  exact payout algorithm.
- The commissioner may adjust prizes with participation. The actual season
  schedule, optional sixth prize, tie rules, and rounding require confirmation.

## Decision Register

`tennis_pool/rule_decisions_2026.json` is the versioned, machine-readable
question/evidence register. Version `2026-provisional-2` gives all 17 entries an
explicit `provisional` decision and rationale, with null commissioner evidence.
The original questions are retained for later verification, not as a development
blocker in provisional mode. No message has been sent automatically.

| ID | Question requiring an explicit decision | Affected behavior |
| --- | --- | --- |
| unused_substitutes | Do unactivated alternatives consume band banks or five-use counts, and when? | Recommendations/accounting |
| activated_substitutes | On activation, which of primary/substitute consumes uses/banks? Are original debits refunded and replacement limits checked? | Recommendations/accounting/substitution |
| substitute_bands | Must pairs share a seed band, including unseeded versus 17-32? | Recommendations/substitution |
| overlapping_picks | May an alternative already be a primary, or substitute for another primary? Is duplicate scoring ever permitted? | Recommendations/substitution |
| duplicate_substitutes | May two primaries name the same alternative; what happens if both withdraw? | Recommendations/substitution |
| simultaneous_withdrawals | Are activations atomic or ordered, and how are shared quota/use conflicts resolved? | Recommendations/substitution |
| replacement_eligibility | Is primary first-match start the cutoff (including byes)? May an alternative have already played? Which declaration/receipt timestamp controls? | Recommendations/substitution |
| substitute_withdrawal | What if the alternative also withdraws? Is a chain, later replacement, or zero score required? | Recommendations/substitution |
| walkovers | Do walkovers earn advancement points and/or bonuses, and do they affect first-match replacement eligibility? | Recommendations/scoring/substitution |
| mixed_bonus_order | Within Other, how is a seed 17-32 compared with an unseeded ATP rank? How are tied/missing ranks handled? | Recommendations/scoring |
| random_accounting | Do random players consume actual-band quotas and five uses? Can a player at five uses be sampled? | Recommendations/accounting/random allocation |
| random_fallback | How are cascading exhausted bands, collisions, duplicate samples, and sampling order handled? | Random allocation |
| partial_submissions | Are incomplete/invalid primary lists or partial substitute lists accepted, rejected, or randomly completed? | Recommendations/submissions |
| submission_bonus | Do late, corrected, or replacement spreadsheet attachments qualify toward seven submissions? | Submissions/season standings |
| ties_payouts | Which ranks are pooled in a tie, including season/eligibility boundaries? What schedule, rounding, and sixth prize apply? | Payouts |
| semifinal_points | Confirm the table/example's 90/45 semifinal points rather than rule 11 prose's 140/70. | Recommendations/scoring |
| canada_event | Confirm the Canadian event identity/venue for the Toronto/Montreal discrepancy. | Recommendations/event mapping |

## Provisional Interpretations

These are best guesses, not additional published rules. The JSON register is
the full decision text and rationale; this table summarizes the behavior.

| ID | Development assumption |
| --- | --- |
| unused_substitutes | No quota/use charge until activation; check potential activation legality. |
| activated_substitutes | Accepted primaries are charged. Valid replacement transfers the event's use/band debit from primary to substitute, atomically and exactly once. Without a valid replacement the primary keeps its debits and scores zero. |
| substitute_bands | Require same selection-bank category for each pair; unseeded differs from 17-32. Voluntary primaries need not be one per band. |
| overlapping_picks | Five distinct primaries; alternatives cannot also be primaries; no duplicate scoring. |
| duplicate_substitutes | Supplied alternatives must be distinct. |
| simultaneous_withdrawals | Evaluate pairs from one snapshot and apply valid transfers atomically; no slot-order priority. Invalid pairs stay zero-scoring primaries. Inconsistent aggregate accounting is an error. |
| replacement_eligibility | Alternative must be supplied before submission deadline. Official withdrawal must precede primary's first started match or walkover advancement; byes do not close eligibility. Predeclared alternatives may already have played and receive full event scores. Missing timestamp evidence blocks activation. |
| substitute_withdrawal | One paired replacement only, no chains or later picks. A substitute that also withdraws before participation is not activated; the original slot scores zero. A substitute that participated retains earned points. |
| walkovers | Advancement affects terminal-round points but earns no upset bonus. First walkover advancement closes primary replacement eligibility; a bye does not. |
| mixed_bonus_order | Within Other, seeds outrank unseeded players. Order seeds by seed number and unseeded players by first-day ATP rank. Equal ranks have no better-opponent bonus; needed missing ranks are data errors, not guessed values. |
| random_accounting | Same five-use cap; debit actual sampled band, not the intended slot. Unseeded players still consume a use. |
| random_fallback | Process strongest-to-weakest slots, uniform sampling without replacement, reserving quotas after each sample. Recursively descend existing categories when quota/candidates are exhausted. Explicit failure if five legal distinct players cannot be assigned. |
| partial_submissions | Allow zero to five valid paired alternatives, but require five legal distinct primaries. Reject invalid submissions for pre-deadline correction; no valid submission at deadline means missed-submission policy. |
| submission_bonus | Count each event once using its final accepted pre-deadline spreadsheet submission. Timely corrections qualify; late attachments/random assignments do not. Award 250 points once at seven events. |
| ties_payouts | Exclude event-prize-ineligible entries before ranking. Pool occupied-position prizes across ties. Use printed event schedules only at 40/60/80 participants; other counts need configuration. Season payouts use the residual formula and percentages, not rounded examples; sixth gets $25 in 60/80 schedules. Allocate rounding remainders in cents using stable anonymized IDs for exact ties. Reject underfunded schedules. |
| semifinal_points | Table/example prevail: 90 GS, 45 Masters. |
| canada_event | One `canada` event; Toronto/Montreal are aliases for accounting. Venue/dates come from event data. |

To confirm an entry, retain its question and PDF reference, set `status` to
`confirmed`, write a nonempty `decision`, and attach `confirmation` containing
`source`, `source_version`, `confirmed_by`, and ISO `confirmed_at`. The source
must identify an actual commissioner response or amendment, not this code or
an agent's interpretation. Increment `register_version` for changes and review
the diff. Keep evidence references redacted/local if the underlying message
contains private data. Corrected decisions require a new version; old versions
remain available in Git history.

## Fail-Closed Integration Contract

`tennis_pool.rules.require_resolved(operation)` is strict by default and raises
`UnresolvedRulesError` when required decisions are unresolved or provisional.
Development callers should use:

```python
from tennis_pool.rules import require_resolved

register = require_resolved("recommendation", allow_provisional=True)
```

This accepts validated provisional decisions, emits `ProvisionalRulesWarning`
with the assumption IDs/version, and returns their explicit decision text and
status. It never promotes them to confirmed. Still-unresolved decisions remain
blockers even in provisional mode. Unknown
operations, missing entries, malformed registers, and confirmations without
provenance fail rather than granting approval. Separate operation scopes avoid
blocking scoring solely because payout rules are pending.

Supported gates: `recommendation`, `substitution`, `scoring`, `accounting`,
`random_assignment`, `submission`, `payout`, and `event_mapping`. The initial
recommendation gate is deliberately conservative for complete seasonal
recommendations, including possible substitution outcomes and prior random
assignments. It is not a substitute for downstream legality validation or
implementation of confirmed decisions. A future narrower conditional
recommendation must establish that an unresolved case cannot affect it and
record that condition, rather than simply omit a gate.

No 2026 optimizer exists here yet. The web optimizer is a legacy budget workflow
and does not claim 2026 pool legality. Future 2026 entry points must invoke the
gate before scoring/optimization, expose blockers to callers, and pin the
register/PDF versions and affected provisional assumptions in outputs. Accepted
decisions authorize no silent code defaults: downstream implementations must explicitly implement
their recorded decisions. Recommendations remain conditional on information,
model assumptions, and search limits; they cannot promise realized winnings.

Run synthetic register/gate tests with `python -m pytest tennis_pool/tests -q`.
Commissioner confirmation is deferred and is not a blocker for provisional
development. The issue's original commissioner-confirmation criterion is not
claimed as satisfied. Source-workbook parity and full scoring/optimizer
implementation are not claimed by this foundation change.

# Historical ATP Source Policy

Initial review: **2026-10-07**. Source selection/access update: **2026-10-20**. Access re-check and gate record: **2026-11-27**, policy **2026-11-27.1**. Scope: [issue #9](https://github.com/chambsnoah/Tennis-Prediction/issues/9) and [#49](https://github.com/chambsnoah/Tennis-Prediction/issues/49); future ingestion: [#10](https://github.com/chambsnoah/Tennis-Prediction/issues/10).
This is source research and project policy, **not legal advice or permission approval**.
Machine-readable companion: [`historical_source_policy.json`](historical_source_policy.json). Both files carry the same policy version, and its `history` lists every version. `tennis_api.source_policy.evaluate_gates` derives restricted-action permission from that record's evidence alone; offline tests check that both files agree and that no selection or free-access claim unlocks a gate.

## Decision And Evidence Status

- The project owner selected **JeffSackmann/tennis_atp** for multi-year ATP singles on **2026-10-20**. This replaces the provisional candidate decision, not the access, verified version/license, quality review, or required use-case permission gates. Selecting a source is not rights-holder approval.
- **Exact latest commit SHA: unavailable; record `null`, not a fabricated pin.** GitHub repository metadata and commit endpoints returned HTTP 404 on 2026-10-20 and again on 2026-11-27 [S1].
- **Pinned upstream README and repository license: not verified; record `null`.** The README and license API endpoints and the raw `master`/`main` README and LICENSE URLs all returned HTTP 404 on 2026-11-27 [S1]. No immutable README or license URL can honestly be supplied yet.
- A 404 establishes only failed public access during review, not whether the repository was deleted, renamed, made private, or temporarily inaccessible [S1].
- Automated ingestion, paid-prize-pool decision support, and publication/redistribution **remain blocked**. Public accessibility, attribution, private operation, and this recommendation do not constitute approval.
- Issue #9 is not fully resolved: source access, exact revision, applicable license, and required permission remain external blockers. Do not unblock #10's real-data retrieval on this document alone.

## Selection And Access Update: 2026-10-20

The owner's instruction was "lets go with the jeff sackmann source, is it free?"
The same-day checks returned HTTP 404 for the repository metadata, latest-commit
list, and both `master` and `main` README URLs in S1. These failures do not
establish why access failed or verify a source revision or license. No dataset,
live provider API, or commissioner workbook was accessed.

S2 was accessible again and explicitly announces that the databases are "free
for anyone who wants to use them." That establishes a **2015 free-access
announcement**, not a verified current price, unrestricted license, or permission
for paid-prize-pool use. The machine-readable cost status records that limitation;
all three action gates remain false and the permission approval list stays empty.
S3-S5 were not re-reviewed in this update; their findings below retain the initial
review date. Historical partitions and the synthetic-only workbook policy are
unchanged.

## Access Re-check And Gate Status: 2026-11-27

Issue #49 repeated the read-only access check on **2026-11-27** (18:06 UTC). Only
metadata, commit-list, README and LICENSE endpoints were requested; no data file,
archive or clone was fetched. Every request returned **HTTP 404**:

- authenticated GitHub REST `repos/JeffSackmann/tennis_atp`, `.../commits?per_page=1`, `.../readme` and `.../license`;
- the same repository metadata request without authentication, and the repository web page;
- raw `README.md` and `LICENSE` on both `master` and `main` (HEAD requests).

The owner account `JeffSackmann` still resolves (HTTP 200). Its public repository
listing contains one repository, `tennis_MatchChartingProject`, a different
dataset. A GitHub rename would normally redirect the old API path; none did. The
cause remains unknown: the repository may have been deleted, made private or
moved elsewhere. Match Charting Project data, forks and mirrors are **not**
substitutes for the selected source and were not inspected.

Because no repository, README or license was reachable, the current terms, the
permitted-use scope, attribution wording, caching/retention and redistribution
rules remain **unverified**. The conditional CC BY-NC-SA 4.0 analysis below still
describes risks only; it does not establish the applicable license.

**Step for the project owner.** Permission for the paid-prize-pool use has to come
from the rights holder(s), and only the owner can ask for it. The request should
cover where the maintained dataset now lives and its current terms, plus whether
private decision support for a pool with entry fees and prizes is permitted. It
should also cover local caching/retention, model training, derived outputs and any
redistribution. Keep the correspondence in restricted storage outside this
repository. Record only an opaque `restricted:` evidence reference with grant
date, scope, source revision and expiry. Repository tooling has sent no request.
The policy records `rights_holder_request.status = "not_evidenced"`.

| Gate | Status on 2026-11-27 | Unblocks when |
| --- | --- | --- |
| `source_access_and_pinned_revision` | Blocked, external: HTTP 404 on both checks. | Upstream is reachable and a full 40-character commit SHA plus README/LICENSE URLs at that SHA are recorded. |
| `current_terms_and_license_scope` | Blocked by source access. | Terms are read at the pinned revision and recorded with their URL. |
| `rights_holder_permission` | Blocked, external: no request or approval evidenced. | A dated rights-holder approval names each action and the revision, with restricted evidence. |
| `coverage_quality_audit` | Not started; needs permission. | Ingestion is permitted; then measure seasons, events, fields, missing statistics and date semantics. |
| `evaluation_splits` | Preserved: 2000-2022 / 2023-2024 / 2025 / 2026 shadow. | Unchanged; any revision is predeclared before modeling. |
| `workbook_privacy_audit` | Not started; needs an authorized private audit. | Separately authorized; synthetic-only fixtures meanwhile. |
| `policy_consistency` | Complete: this Markdown and the JSON agree, enforced by tests. | Kept current on each policy version. |
| `real_data_ingestion_notice` | Blocked: #10 real-data retrieval may **not** proceed. | Every source and permission gate above is satisfied. |

Actions that need no source permission are permitted: synthetic-only fixture
development and read-only public access re-checks of metadata, README and LICENSE
endpoints. `automated_ingestion`, `publication` and `paid_prize_pool_use` stay
false; `evaluate_gates` reports the same.

## Five Primary Sources

All sources below were initially checked on **2026-10-07**; the updates above identify the S1/S2 rechecks on **2026-10-20** and the S1 recheck on **2026-11-27**. Only GitHub public metadata/README and first-party informational/terms pages were requested. No historical dataset, repository archive, live provider API, or workbook was downloaded.

| ID | Primary source and exact URL | Review result |
| --- | --- | --- |
| S1 | [GitHub repository](https://github.com/JeffSackmann/tennis_atp); [repository metadata](https://api.github.com/repos/JeffSackmann/tennis_atp); [latest commits, no branch assumed](https://api.github.com/repos/JeffSackmann/tennis_atp/commits?per_page=1); [master commit](https://api.github.com/repos/JeffSackmann/tennis_atp/commits/master) | All returned HTTP 404; latest SHA/default branch unavailable. |
| S1 | [Upstream master README](https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/README.md); [main README](https://raw.githubusercontent.com/JeffSackmann/tennis_atp/main/README.md) | Both HTTP 404; these are attempted mutable URLs, **not pins**. |
| S1 | [README endpoint](https://api.github.com/repos/JeffSackmann/tennis_atp/readme); [license endpoint](https://api.github.com/repos/JeffSackmann/tennis_atp/license); raw `LICENSE` on `master`/`main` | All HTTP 404 on 2026-11-27; no license file or terms reachable. |
| S2 | [Jeff Sackmann's release announcement, 2015-03-24](https://www.tennisabstract.com/blog/2015/03/24/free-atp-and-wta-results-and-stats-databases/) | Available; historical publisher description, not a current coverage audit or verified license notice. |
| S3 | [Creative Commons BY-NC-SA 4.0 International legal code](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en) | Available; exact **4.0 International** terms examined, conditionally, not established as the candidate's current license. |
| S4 | [Tennis Abstract homepage](https://www.tennisabstract.com/) | Available; player analysis, stats/ratings/report links and a separate "Tennis data at GitHub" link; no bulk-reuse authorization established. |
| S5 | [ATP Tour Terms and Conditions](https://www.atptour.com/en/terms-and-conditions) | Available; sections 3.A, 7, 12 and 14 are relevant to copying, retrieval, use, accuracy and availability. |

## Availability And Statistics Caveats

- S2 advertised tour-level results back to 1968, player age/handedness/country/rank, match statistics from 1991 onward, linked biography/rankings, and separate qualifying, Challenger, Futures/Satellite coverage. "Present" means the announcement's **2015** context, not verified 2026 coverage.
- Those claims motivate the candidate, but do not establish complete 2000-2025 files, row counts, singles-only contents, current schema, exact match timestamps, or serve/return field completeness. None was measured here; current README caveats could not be examined [S1, S2].
- Future #10 must measure dates, outcomes, scores, surfaces, rankings and available serve/return components per season/event/field. Do not promise advanced statistics for every match or infer zero from missing statistics.
- Derive return metrics only from validated opponent-service components when available; document denominators, missingness and transformations. Treat winners/unforced errors, shot-level charts and website ratings as separate, unapproved additions, not assumed candidate columns.
- Verify whether dates represent tournament starts or individual matches before constructing features. Preserve date precision and unknown timing; never invent match-start/end timestamps. Prefer prior-tournament cutoffs when same-event chronology or publication time is unproven.
- The JSON's observed `date_precision` is `null` until verified; its separate `feature_cutoff_policy` is a conservative project rule, not a claim about upstream date semantics.
- Revised historical snapshots do not prove what information was available before a past match. Record availability provenance; quarantine unclear cases rather than leak later rankings/statistics backward. S3 section 5 and S5 section 12 disclaim accuracy warranties, not substitute for validation.

## Conditional License And Use-Case Gate

The following is an examination of **CC BY-NC-SA 4.0 International**, not confirmation that it applies to the unavailable repository [S1, S3]. Do not silently substitute another version.

- Sections 1(k) and 2(a)(1): NonCommercial means "not primarily intended for or directed towards commercial advantage or monetary compensation"; reproduction, sharing and adaptation grants are NonCommercial only. The condition applies to private reproduction too, not just selling or redistributing files [S3].
- Section 3(a): when sharing, retain supplied creator/copyright/license/disclaimer notices and source link; identify modifications and retain prior modification indications; link the license. Do not imply endorsement (section 2(a)(6)) [S3].
- Section 3(b): shared Adapted Material requires a CC license with the same elements at 4.0 or later, or a BY-NC-SA-compatible license. Sections 2(a)(5)(C) and 3(b)(3) prohibit additional downstream restrictions/effective technological measures that restrict licensed rights [S3].
- Section 4 covers extraction/reuse of all or substantial database contents for NonCommercial purposes and applicable adapted-database/share obligations. This is not a blanket finding that every model or aggregate is Adapted Material [S3].
- Sections 1(i), 2(b), 5 and 8: the grant extends only to rights the licensor can license; privacy/publicity and other rights are not generally cleared, warranties are disclaimed, and lawful exceptions are not removed [S3]. Do not infer underlying third-party permissions.
- **Paid-prize-pool optimization is commercially uncertain**: an unpaid/local tool intended to improve monetary winnings may still be directed toward monetary compensation. The definition does not decide this specific case; neither "private", "research" nor lack of a subscription establishes NonCommercial use [S3; project risk assessment].
- Obtain documented clarification/permission from the appropriate rights holder(s) for this concrete decision-support use, including entry fees/prizes, users, monetization, caching, training and outputs; obtain qualified legal review where needed. No permission request or approval is evidenced by this research.
- Before enabling ingestion or publication, verify immutable source/license evidence and the applicable permission record. Store agreements/correspondence in restricted storage; public policy may carry an opaque evidence reference and approval scope/date/expiry, never confidential terms.

## Attribution, Caching And Alternatives

- Proposed attribution after verification: "ATP tennis data compiled by Jeff Sackmann, JeffSackmann/tennis_atp, commit <verified SHA>, <verified license URL>; accessed <UTC date>; modifications: <cleaning/derived fields>." Preserve supplied notices/disclaimer and transformation history [S3 section 3(a)]. Placeholders are not usable attribution evidence.
- After permission, prefer an access-controlled, immutable private raw cache outside git/public artifacts, with license/provenance retained. This is project risk control, **not a private-use exemption** from NonCommercial or contractual conditions [S3 section 2(a)(1)].
- Do not commit, mirror, package or publish raw/cleaned data, database extracts, model artifacts or data-derived reports until their rights treatment and intended distribution are reviewed. ShareAlike is conditional on sharing qualifying adapted material; private caching is not automatically redistribution [S3 sections 1(l), 3, 4].
- **Tennis Abstract website:** useful human-readable analysis and reference links, but distinct from a versioned GitHub release. S4 does not establish website scraping, bulk caching or redistribution permission. Do not transfer a repository license to its pages, ratings or Match Charting Project; no historical pages were scraped.
- **Official ATP sources:** S5 section 3.A allows one personal NonCommercial printed copy and restricts other copying/modification/distribution. Section 7 prohibits systematic retrieval without express prior written permission, and restricts commercial/gambling/wagering uses likewise. Section 14 permits content/service discontinuation. These are not an approved bulk-history fallback; seek a separately scoped data agreement rather than scraping.

## Planned Coverage And Frozen Evaluation

These are **proposed project boundaries**, not measured upstream coverage or existing datasets.

| Partition | Seasons | Policy |
| --- | --- | --- |
| Training | 2000-2022 | Time-respecting development/training only. |
| Validation | 2023-2024 | Model selection and calibration with pre-match information cutoffs. |
| Frozen holdout | 2025 | Freeze eligible cohort and snapshot/digest before model selection; never tune on its outcomes. |
| Shadow only | 2026 | Separate monitoring cohort; only post-approval predictions recorded before outcomes, not retrospective predictions of already played matches. |

Target scope is ATP tour-level singles, 2000-2025, with event inclusion rules explicit; qualifying/Challenger/Futures/doubles files are **excluded** (`excluded_match_files`), and adding any of them needs a new versioned policy decision. Measured coverage is **unknown**, including 2025 completeness. If approval/measurement reveals gaps, report them and predeclare any revised cohort before modeling; never replace the holdout opportunistically. Existing 2023/2024 prediction outputs are regression fixtures, not historical training truth (#10).
Assign whole events by event-start season to keep year-crossing tournaments in one partition; quarantine ambiguous boundary records. Exclude shadow predictions from development and frozen evaluation.

## Future #10 Retrieval And Privacy

- No retrieval now. Once gates are cleared, resolve an accessible approved source to a **full 40-character commit SHA**, fetch its README/license at that SHA, review changes, and use an explicit file allowlist at immutable URLs, never `master`/`main` during reproducible runs. A fork is not an automatic approved replacement or evidence of upstream's latest revision.
- Proposed manifest: source/revision, pinned URL/path, Git blob identifier, retrieved UTC time, byte length, SHA-256 of raw bytes, license URL/evidence digest, policy reference/version, permission evidence reference and scope/expiry. Keep observed file/header/schema/row counts, season/field missingness and temporal-precision audit separate from advertised/planned coverage.
- Cache verified bytes immutably; record deterministic transform/schema versions, selected files and resulting dataset digest. Quarantine duplicates, bad dates/scores/results, missing fields and drift with reasons. Preserve event-time precision and information-availability time; refresh only by an explicitly reviewed new manifest, never mutate a frozen holdout silently (#10).
- Commissioner workbook privacy is **not audited**: no workbook was opened. Do not commit original `.xlsm`, extracts, screenshots or "anonymized" copies containing real participants, contact details, picks, quotas, usage, payments, payouts, hidden sheets, comments, metadata, external links, VBA/macros or confidential permission evidence. Use wholly synthetic commissioner/participant IDs, picks and payments in independently constructed fixtures; inspect fixture metadata/macros/links before publication.
- Completion limits: source version/license and actual coverage remain unknown; no ingestion, provider request, permission approval, workbook audit or legal conclusion occurred. The coverage/quality audit and the private workbook audit stay blocked until permission and authorization clear. Fail closed until these blockers are resolved.

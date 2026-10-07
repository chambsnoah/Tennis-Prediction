# Historical ATP Source Policy

Review date: **2026-10-07**. Scope: [issue #9](https://github.com/chambsnoah/Tennis-Prediction/issues/9); future ingestion: [#10](https://github.com/chambsnoah/Tennis-Prediction/issues/10).
This is source research and project policy, **not legal advice or permission approval**.
Machine-readable companion: [`historical_source_policy.json`](historical_source_policy.json), maintained separately; it must preserve the unresolved evidence and blocked gates below.

## Decision And Evidence Status

- Provisionally select **JeffSackmann/tennis_atp** as the candidate for multi-year ATP singles, subject to restored access, verified version/license, quality review, and required use-case permission.
- **Exact latest commit SHA: unavailable; record `null`, not a fabricated pin.** GitHub repository metadata and commit endpoints returned HTTP 404 on the review date [S1].
- **Pinned upstream README and repository license: not verified; record `null`.** Raw README checks on both `master` and `main` returned HTTP 404 [S1]. No immutable README URL can honestly be supplied yet.
- A 404 establishes only failed public access during review, not whether the repository was deleted, renamed, made private, or temporarily inaccessible [S1].
- Automated ingestion, paid-prize-pool decision support, and publication/redistribution **remain blocked**. Public accessibility, attribution, private operation, and this recommendation do not constitute approval.
- Issue #9 is not fully resolved: source access, exact revision, applicable license, and required permission remain external blockers. Do not unblock #10's real-data retrieval on this document alone.

## Five Primary Sources

All sources below were checked on **2026-10-07**; only GitHub public metadata/README and first-party informational/terms pages were requested. No historical dataset, repository archive, live provider API, or workbook was downloaded.

| ID | Primary source and exact URL | Review result |
| --- | --- | --- |
| S1 | [GitHub repository](https://github.com/JeffSackmann/tennis_atp); [repository metadata](https://api.github.com/repos/JeffSackmann/tennis_atp); [latest commits, no branch assumed](https://api.github.com/repos/JeffSackmann/tennis_atp/commits?per_page=1); [master commit](https://api.github.com/repos/JeffSackmann/tennis_atp/commits/master) | All returned HTTP 404; latest SHA/default branch unavailable. |
| S1 | [Upstream master README](https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/README.md); [main README](https://raw.githubusercontent.com/JeffSackmann/tennis_atp/main/README.md) | Both HTTP 404; these are attempted mutable URLs, **not pins**. |
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

Target scope is ATP tour-level singles, 2000-2025, with event inclusion rules explicit; qualifying/Challenger/Futures/doubles require separate scope decisions. Measured coverage is **unknown**, including 2025 completeness. If approval/measurement reveals gaps, report them and predeclare any revised cohort before modeling; never replace the holdout opportunistically. Existing 2023/2024 prediction outputs are regression fixtures, not historical training truth (#10).
Assign whole events by event-start season to keep year-crossing tournaments in one partition; quarantine ambiguous boundary records. Exclude shadow predictions from development and frozen evaluation.

## Future #10 Retrieval And Privacy

- No retrieval now. Once gates are cleared, resolve an accessible approved source to a **full 40-character commit SHA**, fetch its README/license at that SHA, review changes, and use an explicit file allowlist at immutable URLs, never `master`/`main` during reproducible runs. A fork is not an automatic approved replacement or evidence of upstream's latest revision.
- Proposed manifest: source/revision, pinned URL/path, Git blob identifier, retrieved UTC time, byte length, SHA-256 of raw bytes, license URL/evidence digest, policy reference/version, permission evidence reference and scope/expiry. Keep observed file/header/schema/row counts, season/field missingness and temporal-precision audit separate from advertised/planned coverage.
- Cache verified bytes immutably; record deterministic transform/schema versions, selected files and resulting dataset digest. Quarantine duplicates, bad dates/scores/results, missing fields and drift with reasons. Preserve event-time precision and information-availability time; refresh only by an explicitly reviewed new manifest, never mutate a frozen holdout silently (#10).
- Commissioner workbook privacy is **not audited**: no workbook was opened. Do not commit original `.xlsm`, extracts, screenshots or "anonymized" copies containing real participants, picks, payments, contact details, hidden sheets, comments, metadata, external links or VBA secrets. Use wholly synthetic commissioner/participant IDs, picks and payments in independently constructed fixtures; inspect fixture metadata/macros/links before publication.
- Completion limits: source version/license and actual coverage remain unknown; no ingestion, provider request, permission approval, workbook audit or legal conclusion occurred. Fail closed until these blockers are resolved.

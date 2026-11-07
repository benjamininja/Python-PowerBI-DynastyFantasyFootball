# Source terms and licences are recorded per source, dated, and re-checked every six months

- Status: accepted. Decided in the owner planner chat of 2026-11-07, on [#417](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/417), [#416](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/416) and [#421](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/421).
- Date: 2026-11-07
- Extends: [ADR-0007](0007-machine-checked-source-manifest.md) (the source manifest gains a block and one advisory check). No decision is reversed.
- Scope:
  - the `terms` block on every source in `docs/sources.yml`
  - the advisory finding in `scripts/check_sources.py`
  - the terms table in `docs/SOURCES.md`
  - `CONTEXT.md` (Terms check)

## Context

- `docs/sources.yml` kept a terms verdict only as free text in `purpose` (PFF's rejection, for example). Nothing dated a check, said how it was made, or flagged one that had gone stale.
- WalterFootball (#417) and DraftSharks (#400) have no findable terms. DynastyProcess (#416) states only a GPL-3.0 code licence. Without a record, an unclear source reads the same as a cleared one.
- The owner asked that unclear terms be recorded as unresolved and re-checked every six months "on a programmatic basis so we aren't losing sight of whether we have affirmatively recorded."

## Decision

1. **We judge a source by the terms or licence of the place we read it from.** We do not inherit the terms of a site upstream of a public repository (owner, 2026-11-07, #416: "we don't inherit"). The upstream is recorded for transparency and is not a verdict.
2. **When we rebuild someone's method, we read its inputs ourselves,** so each input's own terms apply to us directly. A method built on PFF grades cannot be rebuilt, because PFF is rejected (#402).
3. **A repository with no licence is read for its method only.** We never copy its code or republish its output.
4. **Share-alike data (GPL-3.0, CC BY-SA) stays in its own published table,** carrying its licence and credit. Anything derived from share-alike data is also published share-alike, under that source's licence and with its credit (owner, 2026-11-07: "i'm fine shifting anything derivative to SA, no harm to use at this time"; to be revisited if it ever bites).
5. **A takedown request is honoured by setting the source to `rejected`.**
6. **Every source is re-checked at least every six months.** A source never checked, or past its next check, is an advisory finding. It is never a Gate failure.
7. **Every source in `docs/sources.yml` carries a `terms` block:**

   | Field | Meaning |
   |---|---|
   | `status` | `unresolved`, `permitted` or `rejected`. This is the terms verdict, separate from the manifest `status` (`live`, `planned`, `rejected`). |
   | `checked` | The date of the last check, or null if never checked. |
   | `next_check` | `checked` plus six months. Computed, never typed. |
   | `checked_in` | The ticket or comment that holds the evidence. |
   | `how` | A short list of what was done, for example "terms.php and termsofuse.php 404", "robots.txt allows all", "licence file read". |
   | `evidence` | The URLs read, each with a `web.archive.org` copy where one exists, because terms pages change without notice. |
   | `licence` | The SPDX id where one exists (`GPL-3.0-only`, `CC-BY-SA-4.0`), else `none` or `site terms`. |
   | `attribution` | The credit we must give, if any. |
   | `share_alike` | True or false. |
   | `upstream` | The sources this source takes its data from, if known. Transparency only, by decision 1. |
   | `access` | How we read the source: `public_get`, `api_key`, `owner_login`, `manual_file` or `none` (not read). `owner_login` means owner credentials are involved. |
   | `permission` | Whether written permission was asked for and given, with dates and a link. Null means never asked. This is the affirmative record. |

   A source never checked carries only `status`, `checked` and `access`. The rest become required once `checked` holds a date. `permitted` and `rejected` require a date, because a verdict with no check behind it is not a record.
8. **The re-check is a count, not a list.** `check_sources.py` prints one advisory line with the number of sources due. The daily run's summary and Discord carry the same one line and a link. They never carry one line per source.

## Starting values

| Source | Terms status | Evidence |
|---|---|---|
| WalterFootball | `unresolved`, checked 2026-11-07 | #417 |
| DraftSharks, each DraftSharks list entry, and DynastySharks (the hand-saved sheets, read from the same site) | `unresolved`, checked 2026-11-07 | #400, #414 |
| PFF | `rejected` | #402 |
| FantasyPros | `rejected` | #401, #415 |
| KeepTradeCut | `rejected` (terms last updated 2025-11-11 bar automated collection, use on any other website, redistribution and derivatives) | #423 |
| nflverse | `permitted` (CC BY 4.0 data, MIT nflreadpy) | #416 |
| Fantrax, each entry | `unresolved`, checked 2026-11-07 (read in a browser; the page shows no date). 8.6(c) allows published interfaces only (`fxea` is one, documented at https://www.fantrax.com/developer; `fxpa/req` is not), 8.6(a) bars non-public areas, 8.6(g) bars crawling and scraping, 8.7 bars showing its information on another website without authorization. The path to compliance is #428, with #429 as the fallback. | #421 (owner, Q13) |
| CollegeFootballData | `permitted` for derived outputs, checked 2026-11-07 (terms effective 2026-08-12). It allows publishing analyses, models and rankings and displaying reasonable portions; it bars redistributing raw API data as a dataset and scraping. The key is held only in a secret and never goes in a public repository. Credit is given anyway, though it is not required. A new `planned` entry, recorded for #422. | #421 (owner, Q13, confirmed Q20) |
| Every other source | `unresolved`, `checked: null` | none |

Researching the unchecked sources' terms is a later spike. This ADR records no verdict beyond the table.

## Alternatives considered

- **Inherit upstream terms.** Rejected by the owner: a site's terms are a contract with that site's users, and a public repository is a different place with its own licence.
- **Keep the verdict in `purpose` prose.** Rejected: it is undated, has no evidence and cannot be counted.
- **Store `next_check`.** Rejected: a typed date can disagree with `checked`. Computed, it cannot (the same reason ADR-0021 computes Run Tier).
- **Fail the Gate on a stale check.** Rejected: a stale record is not a broken pipeline, and it would block publishes over paperwork.
- **One advisory line per source.** Rejected: with most sources unchecked at the start, the output would bury the real warnings.

## Consequences

- An unclear source can no longer read as a cleared one: its block says `unresolved`, when it was last looked at, and what was done.
- Changing a source to `rejected` is a record change. Taking its values out of the published snapshot is a separate decision, made per source (#415, #423).
- Each check adds dated evidence; the six-month count keeps the unchecked sources visible until a spike works through them.
- Share-alike data may bind derived published tables. Deriving from it is a decision to take knowingly.

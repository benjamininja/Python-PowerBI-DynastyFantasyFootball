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

   *Amended by [the 2026-11-08 amendment](#amendment-2026-11-08-source-checks-a-citation-standard-and-a-dated-security-check-454) (#454): the re-check is once per season, before the rookie draft, in a month set on `CFG`. The advisory rule is unchanged.*
7. **Every source in `docs/sources.yml` carries a `terms` block:**

   | Field | Meaning |
   |---|---|
   | `status` | `unresolved`, `permitted` or `rejected`. This is the terms verdict, separate from the manifest `status` (`live`, `planned`, `rejected`). |
   | `checked` | The date of the last check, or null if never checked. |
   | `next_check` | `checked` plus six months. Computed, never typed. *Amended by #454: the 1st of the first check month after `checked` (see the 2026-11-08 amendment).* |
   | `checked_in` | The ticket or comment that holds the evidence. |
   | `how` | A short list of what was done, for example "terms.php and termsofuse.php 404", "robots.txt allows all", "licence file read". |
   | `evidence` | The URLs read, each with a `web.archive.org` copy where one exists, because terms pages change without notice. *Amended by #454: replaced by `documents`, `not_found` and `signals`. The old field stays valid until a block is re-cited.* |
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

## Amendment 2026-11-08: source checks, a citation standard and a dated security check (#454)

- Amends decisions 6 and 7 (the re-check cadence, `next_check` and `evidence`). It reverses nothing else.
- Designed in research [#453](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/453) (findings, with the owner's eight answers of 2026-11-08 that amend them) and scoped on [#454](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/454). The planner's rulings on the scoping briefs are the last word where they differ. This text lands first; the record shape and checker (A2), the fetch script (B1 to B5) and the re-cites (C1) follow in later PRs.

### Context

- The #424 candidate research left four inconsistencies: guessed 404 addresses recorded as evidence, `[s]` summaries standing where a quote was needed, a page drawn by JavaScript that was never seen, and no record of how a page was reached. The security run was a one-off.
- The `evidence` field, a list of url and archive pairs, carries three different things at once: the documents, the machine-readable signals and how we read them.
- A fetcher that follows robots.txt by discipline alone broke the rule twice in the #453 run. The rule has to be enforced in code.
- Counts against the manifest at the time of writing: 30 entries, 27 with a check date, all 27 on the old `evidence` field, 3 `evidence` rows that are guessed 404s (WalterFootball `terms.php` and `termsofuse.php`, DraftSharks `terms-of-use`).

### Decision

1. **A source check has three layers, each with its own fields and citation rule:** the **documents** (terms, API terms, licence, privacy), the machine-readable **signals** (robots.txt groups, Content-Signal and Content-Usage lines, TDMRep, `X-Robots-Tag`), and **the read** (who read it, by what method, whether verbatim).
2. **The citation standard has ten points:**
   1. The exact address, and how it was reached: the page, the link text, and a `place` from a fixed list: `footer`, `menu`, `sitemap`, `legal_hub`, `linked_from_doc`, `operator_domain`, `robots_txt`, `api_docs`, `owner_supplied`. `guess` is not on the list.
   2. Two dates: when it was read, and the page's own date (`page_date`). Null means none is shown. The page's exact wording ("Last updated", "Effective") stays in the quote.
   3. The page's words with section numbers. Each clause carries `verbatim: true` or `false`. A summary never decides. A `permitted` or `rejected` status may not rest on a `verbatim: false` clause.
   4. No terms found is a `not_found` entry: the places searched and the date. A guessed address is never evidence.
   5. Unread is recorded with a reason from a fixed list: `js_rendered`, `refused_status` (401, 403 or 429), `robots_blocks_agent`, `login`, `paywall`, `dns`, `tool_refused`, `rate_limited`. The owner reads those pages.
   6. Privacy is recorded as its own document, with its own `kind`, apart from terms.
   7. Who read it and how: `read_by` is `agent`, `owner` or `script`, and `method` is `http_get`, `browser_render` or `owner_paste`. The script's own reads record `read_by: script`, because it reads under `ETL_USER_AGENT`, not under a Claude token, and #429 may treat the two differently.
   8. A private capture of the document with its SHA-256 (decision 4).
   9. An archive copy (decision 5).
   10. The `operator`: the legal entity whose terms they are. One operator can serve several sites.
3. **Documents.** Terms and API terms are primary for the channel each names, and a licence is primary where present. Privacy governs what the site collects from us and almost never permits or bars reuse. A copyright line or "All Rights Reserved" is an ownership claim, not a licence: with no terms found, the status stays `unresolved`. An operator's terms are the site's terms.
4. **An owner paste counts as evidence of equal standing,** when it is captured verbatim with its URL and date and carries `read_by: owner`, `method: owner_paste` and a `capture_sha256`. The full text is the site's copyrighted text, and the repo and the snapshot are public. So the capture is private: a file in the gitignored `data/review/policies/` in the main checkout, named by read date and hash. The public record carries only the quotes and the hash (the owner's ruling, #453 answer 1). The captures move to Supabase only if the re-check ever runs on Actions.
5. **Wayback: the script looks up existing copies only** (the read-only availability API). It lists the deciding pages that have no copy, in a missing list file. The owner approves the saves in one explicit step, and only then does the script call Save Page Now, for that approved list. Nothing is saved without that step, and it is never part of a check (#453 answer 2).
6. **Season cadence replaces the six-month re-check** (decision 6 above; #453 answer 3).
   - One check per season, before the rookie draft, in a month set once on `CFG` (`source_check_month`, May by default).
   - `next_check` stays computed, never typed: the 1st of the first check month that starts after `checked`. A check on 2026-11-07 is next due 2027-05-01. A check on 2027-05-10 is next due 2028-05-01.
   - A source is due when today is past its `next_check`, so the advisory shows through the whole check month, before the draft.
   - The security check runs on the same date, and also before the first read of any new host. `security.checked` has its own next check by the same rule.
   - The re-check compares the capture hash and `page_date`, so a changed page flags itself even when its date did not move.
7. **The security check is a dated per-host block, made before anyone, person or script, reads a page on the host.**
   - **Safe Browsing** uses the keyless Transparency Report endpoint (`transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site=`), not a documented API. Three controls run first: the test pages `testsafebrowsing.appspot.com/s/malware.html`, `/s/phishing.html` and `/s/unwanted.html`, passed as the `site=` value and never fetched. All three must return `2`, or the run flags `controls_failed` and reports no verdict for any host.
   - A **shape check** follows: the `)]}'` prefix, a 10-element array, and `sb.ssr` as the first element. Any other shape is `controls_failed`.
   - The **code allowlist**: only `1` is clean. `2` is `sb_unsafe`. Any other code is `sb_no_verdict`, with the raw code kept. Google's scan time more than 30 days old is `sb_stale`.
   - We move to the documented v5 API only if the endpoint stops answering (#453 answer 4).
   - **DNS** (`resolves` or `nxdomain`; `nxdomain` is a flag and nothing more is read on that host), **TLS** (handshake only: `ok`, issuer, `notAfter`, version), **HSTS** (`max_age` and preload status; informational, never a flag) and **registration age** (RDAP: the IANA bootstrap names the server, and the registration event is the date).
   - **Flags** are computed: `young_domain` (registered under one year), `tls_expiring` (under 7 days left), `tls_failed` (a failed handshake, a hostname mismatch or an expired certificate; no request to that host follows), `sb_unsafe`, `sb_no_verdict`, `sb_stale`, `nxdomain`, `controls_failed`, and `age_unknown`.
   - RDAP that gives no answer, or no registration event, gives `registered: null` and `age_unknown`. The host is held like a `young_domain` until the owner confirms its security block (the planner's ruling, the stricter reading of #453 answer 6; the owner may loosen it).
   - The script never falls back to plain `http://`, for any host.
   - Every host is checked on its own before its first request. Apex and `www.` are two hosts, and one host's result never covers another. The record's `security.host` is the host the documents were read from. A redirecting host's check stays in the run's output file. This covers redirect hops and operator domains too.
   - HSTS is read from the `Strict-Transport-Security` header of the host's robots.txt response.
   - **Service hosts** are a fixed list in the script's code: `transparencyreport.google.com`, `data.iana.org`, the https RDAP base URL that IANA's bootstrap gives for the host's TLD (`rdap.verisign.com` for `.com`), `hstspreload.org`, `archive.org` and `web.archive.org`. Each passes robots and pacing like any host but has no security check of its own. A new service host needs a code change and a PR.
   - The owner confirms the block (`confirmed: {by, date}`) before a source moves past `planned`. That is the owner's confirmation, beside the technical control.
8. **`young_domain` and `age_unknown` hosts are not read at all, text or render,** until the owner confirms the host's security block. The script reads that confirmation only from `security.confirmed` in `docs/sources.yml` (#453 answer 6, the owner's Q9 answer of 2026-11-08). For such a host the first run writes only its security block to the output folder and reads nothing else. A later PR adds the host as a `planned` entry with the owner's `confirmed: {by, date}`. The next run reads the pages. After that, the normal rules apply.
9. **Reading rules (RFC 9309 and the owner's refusal rules).**
   - robots.txt is its own request, read before any other request to the host. A 2xx is parsed. 404 and 410, and any other 4xx except 401, 403 and 429, mean no rules.
   - **401 and 403 are a stop,** never retried, recorded with the code and the date. They are a refusal aimed at us, and a refusal is final.
   - **5xx and timeouts are a complete disallow.**
   - **429 on any read of a host, robots.txt included:** three plain tries of the same GET, waiting `Retry-After` if it is given, else 60 seconds, then 5 minutes. A `Retry-After` over 10 minutes is a stop at once: on robots.txt, a stop on the host; on a later read, the host's remaining reads are recorded `unread: rate_limited` with no deferred try. After three 429s the read gets one deferred plain try at the end of the run, after every other host is done. If that fails: on robots.txt, a stop; on a later read, `unread: rate_limited` for the host's remaining reads, which wait for next season. A retry is always a plain request, and a render is never a 429 retry (#453 answers 5 and the one added after it).
   - **After a robots.txt 429 clears,** the host's remaining reads go in segments: the essentials first (terms, privacy), then the optional reads (sitemap, `.well-known`, `llms.txt`), about 30 seconds apart.
   - The User-Agent is `ETL_USER_AGENT` (#458) on every request, and is never changed after a refusal. No cookies, logins, forms or POSTs.
   - A Claude or Anthropic agent stops on a disallow for its token. Until #429 rules, the gate stops on a disallow for our product token, for the `*` group, or for any Claude or Anthropic token (`ClaudeBot`, `Claude-User`, `Claude-SearchBot`, `anthropic-ai`, `Claude-Web`), and records which token stopped it, as `unread: robots_blocks_agent`. #429 may loosen this later (the owner's Q2 answer, 2026-11-08: "Stop until #429").
   - Parsing uses an RFC 9309 parser (Protego), never `urllib.robotparser`. Pacing: one host at a time, `Crawl-delay` honoured, otherwise at least 5 seconds between requests to one host.
   - The only paths requested without a link are `robots.txt`, `/sitemap.xml`, `/wp-sitemap.xml`, `/.well-known/tdmrep.json` and `/llms.txt`.
10. **JavaScript pages are rendered with Playwright:** the same User-Agent and gate, no cookies, logins or forms. A render is only for a page that answered 200 and drew nothing (under about 500 characters of visible text, or a body of only `Loading...`). Never after a 429, never for a young host before confirmation, and never past a 401, 403 or robots block, which stay a stop. Every request a rendered page makes passes the gate. A same-host request must pass robots. A request to another host is aborted unless that host has already passed its security check and robots, in this run or in the record. No check starts mid-render. If the page then draws nothing, the document is `unread: js_rendered`, for the owner (the owner's Q10 answer, 2026-11-08).
11. **When signals disagree, the stricter one governs what it names** (findings section 4):
    - the terms govern over a robots.txt that allows or is missing, because robots.txt is not a form of access authorization (RFC 9309 section 1);
    - a robots group that blocks an AI agent binds that agent. The terms decide for everyone else;
    - the more specific document governs its channel (API terms for the API), and the operative terms text beats marketing copy;
    - a specific robots group beats the `*` group for the agent it names. A Content-Signal under `*` does not reach an agent that has its own group. Both are recorded;
    - the privacy policy governs what the site collects. The terms govern reuse. Both are recorded;
    - an unknown Content-Signal key is recorded verbatim, and only the defined keys are interpreted (`search`, `ai-input`, `ai-train`; `train-ai`, `ai-use`, `search`). An unknown key counts as a reservation against AI use when the file also claims Art 4;
    - no terms, only a copyright line, is `not_found` and `unresolved`. No terms is not permission;
    - the AI vocabularies cover AI uses only, so for the pipeline the terms and the `Disallow` lines decide.
12. **The script writes facts and computed flags, never `status`, `permission`, `clauses` or `confirmed`.** The verdict stays a person's call, made from the verbatim clauses. Choosing and quoting clauses is a person's job. Its output is one file per host per run in the gitignored `REVIEW / "source_checks"` folder. Records reach `docs/sources.yml` only by a later PR, after the owner confirms. The script never writes `docs/sources.yml`.
13. **Robots-first is enforced in code.** A gate object's `allowed(url)` must pass before every request except the host's own robots.txt GET, and a request made before the host's robots result is known raises. The fetcher is the only network path in the script.

### Fields

`documents`, `not_found`, `signals` and `operator` join the `terms` block. `security` is a new block beside `terms` at the source level. `evidence` stays accepted until a block is re-cited (decision 15).

**`terms.documents[]`**, one per governing document:

| Field | Meaning |
|---|---|
| `kind` | `terms`, `api_terms`, `licence`, `privacy` or `copyright`. |
| `url` | The address, as text. |
| `reached_from` | `{page, place, link_text}`. `place` is one of the nine values in decision 2, point 1. |
| `read` | The date it was read. |
| `page_date` | The page's own date, or null. |
| `read_by` | `agent`, `owner` or `script`. |
| `method` | `http_get`, `browser_render` or `owner_paste`. |
| `unread` | Null, or one of `js_rendered`, `refused_status`, `robots_blocks_agent`, `login`, `paywall`, `dns`, `tool_refused`, `rate_limited`. |
| `archive` | An existing Wayback copy, or null. |
| `capture_sha256` | 64 hex characters, or null. The SHA-256 of exactly the bytes captured: the response body for `http_get`, the rendered HTML for `browser_render`. |
| `clauses[]` | `{section, topic, verbatim: bool, quote}`. |

**`terms.not_found[]`:** `{kind, looked, date, by}`. `looked` is a non-empty list of places from the place list.

**`terms.signals`:**

| Field | Meaning |
|---|---|
| `robots` | `{url, code: int, read: date, claude_groups: list, blocks_agent: bool, content_signal, content_usage, crawl_delay, sha256}`. |
| `tdmrep` | `{well_known, header, meta}`. |
| `x_robots_tag`, `meta_robots` | Text or null. |

**`terms.operator`:** text or null.

**`security`:**

| Field | Meaning |
|---|---|
| `checked` | The date of the check. |
| `host` | The host the documents were read from. |
| `controls` | `{malware, phishing, unwanted: int, shape_ok: bool}`. |
| `safe_browsing` | `{via: transparency_report, code: int, google_scan: date or null}`. |
| `dns` | `resolves` or `nxdomain`. |
| `tls` | `{ok, issuer, not_after, version}`. |
| `hsts` | `{max_age, preloaded}`. |
| `registered` | A date, or null. |
| `flags` | From `young_domain`, `age_unknown`, `tls_expiring`, `tls_failed`, `sb_unsafe`, `sb_no_verdict`, `sb_stale`, `nxdomain`, `controls_failed`. |
| `confirmed` | `{by, date or null}`. |

`security` is not in the required fields. It is needed for a `live` or `planned` source read over HTTP (access not `manual_file`), and `confirmed.date` is needed for `live`.

### Checker rules

14. **`check_sources.py` fails only on a shape error:**
    - a `place` or `unread` value off its list;
    - a `permitted` or `rejected` status on a new-shape block with no `terms`, `api_terms` or `licence` document whose clauses are all `verbatim: true`;
    - `read_by: owner` with `method: owner_paste` and no `capture_sha256`;
    - a `not_found` entry with no `looked` or no `date`;
    - a new-shape block with a check date and no `signals.robots.code`;
    - a block that holds both `evidence` and `documents`, so a half-migrated record cannot pass;
    - a malformed `security` block.
15. **Migration.** A block whose `checked` is a date and which has `evidence` and no `documents` or `not_found` stays valid. It is counted in one new advisory line, "re-cite due". The new-shape rules apply only to new-shape blocks. Removing `evidence` is a later ticket ([#464](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/464)), once the re-cite count is 0.
16. **Advisories stay counts, one line each (decision 8), and never a failure:** the terms-due line, the re-cite line, and a security line. The security line counts live and planned sources read over HTTP with no `security` block, a block past its next check, a block with flags, or a live source with no `confirmed.date`.

### Alternatives considered

- **Keep `evidence` flat.** Rejected: it let a guessed 404 stand as evidence and mixed documents, signals and the read.
- **Store the full terms text in the repo.** Rejected: it is the site's copyrighted text, and the repo and snapshot are public. A private capture with a public hash proves a quote without publishing the text.
- **Treat a 403 as "no rules".** Rejected: RFC 9309 would allow it, but a 403 on robots.txt is a refusal aimed at our client, and a refusal is final.
- **One Safe Browsing control.** Rejected: malware, phishing and unwanted software are separate lists, and one control proves only one list answers.
- **Let the script set the verdict.** Rejected: the verdict is a person's call, made from verbatim clauses. A tool's summary never decides it.
- **`urllib.robotparser`.** Rejected: on Python 3.12 it returned `False` for `/public/x` under `Disallow: /` with `Allow: /public/` (RFC 9309: allowed, longest match) and `True` for `/a.pdf` under `Disallow: /*.pdf$` (RFC 9309: disallowed).
- **The documented Safe Browsing API v5 now.** Rejected for now: it needs an account and a key, and is non-commercial only. It is the fallback if the keyless endpoint stops answering.
- **Keep the six-month re-check.** Rejected by the owner: one check per season, before the rookie draft, fits the use.

### Consequences

- DraftSharks and WalterFootball are re-cited, their guessed 404s moving to `not_found` (brief C1).
- Every `[s]` summary stays non-deciding.
- The season re-check gains hash comparison, so a changed page flags itself.
- One advisory line counts security flags, the same shape as the terms advisory (decision 8).
- The Terms check in `CONTEXT.md` now says once per season, and gains two terms, Security check and Policy capture.
- The checker and the record shape land in a later PR (A2), the script in five more (B1 to B5), so a source stays on the old `evidence` field until its re-cite. The re-cite line counts them.
- Out of this amendment, each its own ticket: the season run over the manifest ([#463](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/463)), the #424 candidates ([#462](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/462)) and the removal of `evidence` (#464).

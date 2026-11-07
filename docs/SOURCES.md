# SOURCES.md — external input manifest

Every place data **crosses into this repo from the outside world**: scraped
sites, third-party packages, the Fantrax league API, the Google Sheet, and
hand-maintained Excel. One row per external source.

**Scope — boundary only.** This file documents the *edge*. Internal lineage
(which notebook builds which table, and downstream joins) already lives in
[`.claude/memory/data-model.md`](../.claude/memory/data-model.md) (the `Source`
column) and the [`notebooks/README.md`](../notebooks/README.md) inventory — not
duplicated here. The **Feeds** column is the join between the two: it names the
ingesting notebook → table so a removed/renamed notebook shows up as drift
against this manifest.

**Secrets rule.** The `Auth` column records the *method* only — never a token,
password, email, API key, or `.env` value. Real credentials live in gitignored
`.env` files and (for Fantrax) the persistent Playwright profile, never in git.

**Anti-drift (machine-checked).** [`sources.yml`](sources.yml) is the SSOT; the
tables below are **generated** from it — do not hand-edit between the
`BEGIN/END GENERATED` markers. Edit `sources.yml`, then regenerate + validate:

```
.\run.ps1 scripts/check_sources.py --render   # rewrite the tables below
.\run.ps1 scripts/check_sources.py            # validate (schema + token-match + drift)
```

`scripts/check_sources.py` asserts each **live** source's `Feeds` notebook(s)
exist and still reference the source (token match in cell source), warns on
notebook hosts not registered here (reverse-drift), and `--check` fails if these
tables drift from the yaml. See [ADR-0007](adr/0007-machine-checked-source-manifest.md).

---

## Live sources (feed tables today)

<!-- BEGIN GENERATED sources-table:live — regen: python scripts/check_sources.py --render -->
| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |
|---|---|---|---|---|---|
| **Fantrax — getPlayerStats (Players grid)** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (method getPlayerStats; getDraftRanks retired 2026-07-31) | Full active-roster universe: FPts, FP/G, GP, ADP, %D, salary. Codes: `PROJECTION_0_23l_SEASON` (preseason), `SEASON_23l_YEAR_TO_DATE` (in-season / YTD), `SEASON_23l_BY_DATE` + ISO startDate/endDate (rebuild a missed week, `--rebuild-week`) | Fantrax account login, env-stored (FANTRAX_EMAIL/FANTRAX_PASSWORD); persistent Playwright profile (data/.pw_profile/) | `04a_fantrax_weekly_scrape.py` → `fact_fantrax_adp` | Weekly (Windows Task Scheduler) |
| **Fantrax — getPlayerStats (MINOR_FANTASY filters)** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (method getPlayerStats statusOrTeamFilter=MINOR_FANTASY_AVAILABLE\|TAKEN) | Minors eligibility (read-only): the site's own verdict on who is minors-eligible (GP<=19). 02d reads it for the `Minor` default when no Roster State row covers a move (ADR-0019). Roster Slots, salaries and contracts come from the public getTeamRosters entry below, not from here | Same Fantrax session as the Players-grid source (04v imports 04a's scraper; note: lean-import reuse means check_sources.py's host scan won't flag this file — keep this entry current by hand) | `04v_minor_contracts.py` → `fact_minor_eligibility` | Weekly (Windows Task Scheduler, after 04a) |
| **Fantrax — getDraftResults** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (methods getDraftResults + getFantasyLeagueInfo + getRefObject FantasyDraftPickType; one call per division) | Live-draft made-pick attribution: every slot of the startup draft board per division -> `startup_draft` events in the event-sourced ledger, the pick grid and the asset bridge (ADR-0003/0004) | Same Fantrax session as the Players-grid source (04w imports 04a's scraper: env-stored login + persistent Playwright profile) | `04w_fantrax_draft_results.py` → `(raw capture: data/raw/fantrax_draftresults_{season}_{divisionId}.json)`<br>`02d_fact_roster_transactions.py` → `fact_roster_transactions`<br>`02d_fact_roster_transactions.py` → `fact_draft_pick`<br>`02d_fact_roster_transactions.py` → `dim_roster_asset` | Live draft only — re-run between picks + on settle (never scheduled) |
| **Fantrax — getTransactionDetailsHistory** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (method getTransactionDetailsHistory; team=ALL, views TRADE + CLAIM_DROP, all pages) | Roster Moves log (trade legs, claims, drops) -> ledger `trade` / `trade_away` / `claim` / `drop` events + the per-asset trade log (players and picks). No public fxea equivalent exists | Same Fantrax session as the Players-grid source (04t imports 04a's scraper: env-stored login + persistent Playwright profile) | `04t_fantrax_transaction_history.py` → `(raw capture: data/raw/fantrax_txn_history_{season}.json)`<br>`02d_fact_roster_transactions.py` → `fact_roster_transactions`<br>`02d_fact_roster_transactions.py` → `fact_trade_log` | Manual run today (not in run_pipeline.py); ADR-0016 moves it to a full-season pull on every Change Poll trigger + the daily run |
| **Fantrax — public fxea API (getDraftPicks)** | https://www.fantrax.com/fxea/general/getDraftPicks?leagueId=v744203wmmvjqzv6 | Real per-pick ownership of every future rookie-draft pick (`futureDraftPicks`, incl. executed pick-for-pick trades) | None (public unauthenticated REST; plain requests, no Playwright session) | `04u_fantrax_public_api.py` → `fact_draft_pick_future` | Manual run (not in run_pipeline.py) |
| **Fantrax — public fxea API (getLeagueInfo)** | https://www.fantrax.com/fxea/general/getLeagueInfo?leagueId=v744203wmmvjqzv6 | The season's 17 Scoring Periods with their exact bounds (`scoringPeriods`, `playoffs`) and each team's division (`teamInfo`). Feeds the period dim, with the Update-Set state of each regular-season period, and the Division name per Conference (ADR-0016 amendment decisions 2, 12, 14). Errors come back as HTTP 200 with an `error` object; `etl_helpers.fantrax_public_get` checks the body | None (public unauthenticated REST; plain requests, no Playwright session) | `04p_fantrax_league_info.py` → `dim_scoring_period`<br>`04p_fantrax_league_info.py` → `dim_division` | Every pipeline run, all phases (`04p_league_info` step, fantrax_core Chain) |
| **Fantrax — public fxea API (getTeamRosters per period)** | https://www.fantrax.com/fxea/general/getTeamRosters?leagueId=v744203wmmvjqzv6&period=N | The Roster State of each regular-season Scoring Period: every player copy's Roster Slot (`status`), salary and contract, per team (ADR-0016 decision 3 and its amendment). A call with no period returns the current one and echoes its number. A past period returns its roster as it stood at that period's lineup lock; a FUTURE period returns the current roster under the future number, so 04r never asks past the current period. One call per period that has started and is not closed. The season comes from a getLeagueInfo call, so a league id carried into a new season cannot write under the old one | None (public unauthenticated REST; plain requests, no Playwright session) | `04r_fantrax_roster_state.py` → `fact_roster_state` | Every pipeline run, all phases (`04r_roster_state` step, fantrax_core Chain); nothing is read before Scoring Period 1 starts |
| **Fantrax — getLiveScoringStats + getStandings (per Scoring Period)** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (methods getLiveScoringStats {period, playerViewType:'2'} and getStandings {view:'SCHEDULE'}; plus the plain getStandings {view:'COMBINED'} per period, captured raw only) | Period Scoring and Matchups (ADR-0016 amendment decisions 1, 5, 9, 15). Live scoring with the bench view lists every rostered player with an entry, Starters under `ACTIVE` and Bench, IR and Minors under `BENCH`, each with points per stat; 04s sums them by Unit. The schedule view gives every week's matchups and Team Scores. A period loads once `allEventsFinished` is true. Live scoring echoes no period, and answers for a period that has not started with 28 teams and no entries. Errors come back as HTTP 200 with a `pageError`. The plain COMBINED standings ignore `period`: every reply is the current standings. It is saved raw and never loaded. No standings table is built (ADR-0016 amendment decision 11): rank is derived from `fact_matchup`, % Playoffs is dropped, and the reply's Salary Remaining is #97's to parse from the raw files | Same Fantrax session as the Players-grid source (04s imports 04a's scraper: env-stored login + persistent Playwright profile). `--from-raw` loads from the saved raw files with no browser and no login | `04s_fantrax_inseason_capture.py` → `fact_period_scoring`<br>`04s_fantrax_inseason_capture.py` → `fact_matchup` | Every INSEASON pipeline run (`04s_scoring` step, after `04r_roster_state`, fantrax_core Chain). Every regular-season period that has started and is not closed is captured and, once final, replaced whole |
| **Google Sheet — team manifest** | https://docs.google.com/spreadsheets/d/1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc (gid 178660131), read via export?format=csv | Owner/team roster manifest: team name, abbrev, manager emails, division, Team ID, Fantrax-TeamId | Published CSV export (link-readable, no creds) for read | `01c_dim_fantasy_teams_seed.ipynb` → `dim_fantasy_teams` | On league/owner change (manual rerun) |
| **nflverse (via nflreadpy)** | nflreadpy package (nflverse release data) | Canonical NFL player registry, combine / pro-day metrics, IDs (gsis_id), in-season snap counts and injury report | None (public package) | `01e_dim_nfl_players_seed.ipynb` → `dim_nfl_players`<br>`02a_fact_nfl_combine_pro_day_metrics.ipynb` → `fact_nfl_combine_pro_day_metrics`<br>`02g_nflverse_inseason.py` → `fact_nfl_snap_counts`<br>`02g_nflverse_inseason.py` → `fact_nfl_injuries`<br>`05a_startup_draft_board.py` → `(career-games lookup)` | Per pipeline run |
| **KeepTradeCut (KTC)** | https://keeptradecut.com (embedded-HTML / JSON scrape) | Dynasty trade value, tiers, trends, startup ADP/auction; rookie consensus | None (public scrape) | `03c_ktc_rankings.ipynb` → `fact_rookie_rankings`<br>`04b_ktc_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Per pipeline run |
| **FantasyPros** | https://www.fantasypros.com (scrape) + manual Excel for IDP/SF | Rookie PPR + Superflex consensus (scrape); dynasty SF/IDP best/worst/avg/stddev (manual) | None (scrape); manual file (Excel) | `03a_fantasypros_rankings.ipynb` → `fact_rookie_rankings`<br>`04x_manual_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Per pipeline run |
| **WalterFootball** | https://walterfootball.com (scrape) | Rookie positional rankings | None (public scrape) | `03b_walterfootball_rankings.ipynb` → `fact_rookie_rankings` | Per pipeline run |
| **DraftSharks** | https://www.draftsharks.com (scrape) | Rookie top-90 board | None (public scrape) | `03d_draftsharks_rankings.ipynb` → `fact_rookie_rankings` | Per pipeline run |
| **DynastySharks** | Manual extraction -> data/raw/DynastyRankings_2026_ManualExtraction.xlsx | Dynasty 1/3/5/10-yr fantasy-point projections + 3D value (SF/TEPP) | Manual file placement (no creds) | `04x_manual_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Manual (on refresh) |
| **Manual Excel — misc rankings** | data/raw/*.xlsx (RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP) | Supplemental rookie/dynasty expert ranks not available via scrape | Manual file placement (no creds) | `03x_manual_rankings.ipynb` → `fact_rookie_rankings` | Manual (on refresh) |
<!-- END GENERATED sources-table:live -->

## Planned sources (designed, not yet ingesting — ADR-0004 / ADR-0005 / ADR-0006)

<!-- BEGIN GENERATED sources-table:planned — regen: python scripts/check_sources.py --render -->
| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |
|---|---|---|---|---|---|
| **Fantrax — draftPicks.go** | Fantrax draftPicks.go page (league v744203wmmvjqzv6; per division — capture pending) | Pick-ownership SSOT per ADR-0006 (current + forward). Not captured; forward-pick ownership comes from the public fxea getDraftPicks (04u) today | Same Fantrax session as the Players-grid source (Fantrax login + Playwright profile) | — | TBD (capture pending) |
| **Fantrax — commissioner admin** | Fantrax commissioner pages (league v744203wmmvjqzv6) | Contract/cap reconciliation, manual corrections | Commissioner-account login (env-stored) | — | Ad hoc |
| **DraftSharks — preseason rankings** | https://www.draftsharks.com/rankings/{pos}/{format} (base /rankings/{format}; formats: non-PPR, half-ppr, ppr, te-premium and the superflex versions; positions QB RB WR TE K DEF DL LB DB IDP) | Redraft season-long ranks with floor/consensus/DS/ceiling projections, 3D Value and tiers, with IDP (DL LB DB) pages. For this league: IDP and superflex cross-check against the dynasty ranks. DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows are in the page HTML without login; the rest load by script after 'Loading remaining rows...' (call not seen in one GET). An Insider upsell banner shows; whether rows past 25 are gated is unconfirmed | — | Daily guess (page says updated in real time in the offseason) |
| **DraftSharks — best ball rankings** | https://www.draftsharks.com/best-ball-rankings/{pos} (positions QB RB WR TE FLEX; no format variants) | Best-ball ranks set to Underdog scoring, with Underdog ADP, projections and 3D Value. Low fit for this league (no best ball, no IDP); catalogued for completeness. DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows in the page HTML, remainder loaded by script (call not seen); Insider upsell banner shown | — | Daily guess |
| **DraftSharks — dynasty rankings** | https://www.draftsharks.com/dynasty-rankings/{pos}/{format} (rookies: /dynasty-rankings/{pos}/rookies/{format}; formats non-PPR, half-ppr, ppr, te-premium and superflex versions; positions QB RB WR TE K DL LB DB IDP) | Dynasty 1/3/5/10-yr projections, 3D Value+, ADP and DS Analysis, incl. IDP and rookie pages: the page the hand-saved DynastySharks sheets copy (04x). For this league: dynasty, IDP, rookies. The Close Day pull is #413. DraftSharks has no terms page found (#400), so terms are unresolved | None: first 25 rows in the page HTML; the rest from an htmx GET /dynasty-rankings/load-table (query pprSuperflexSlug, fantasyPosition, researchDepth, playerGroup, sort, selectedTeam, playerSearchTerm); one call returned 250 rows as HTML with no login (#400) | — | Close Day guess (weekly in season) |
| **DraftSharks — weekly rankings** | https://www.draftsharks.com/weekly-rankings/{pos\|format} and /weekly-rankings/{week}/{format} (positions QB RB WR TE IDP DEF FLEX; formats half-ppr, ppr, te-premium, superflex) | Per-week start/sit ranks with matchup, SOS and floor/consensus/ceiling projections, incl. IDP. For this league: in-season lineup help, no dynasty value. DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows in the page HTML, remainder loaded by script (call not seen); Insider upsell banner shown | — | Weekly in season (week selector shows weeks 9 to 18) |
| **DraftSharks — rest of season rankings** | https://www.draftsharks.com/ros-rankings/{pos}/{format} (bases /ros-rankings and /ros-rankings/{format}; formats non-PPR, half-ppr, ppr, te-premium, no superflex; positions QB RB WR TE K DEF DL LB DB IDP FLEX) | Rest-of-season ranks with projections, trend and injury risk, incl. IDP. For this league: in-season trade timing and contender/future stance checks. DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows in the page HTML, remainder loaded by script (call not seen); Insider upsell banner shown | — | Daily in season (page says updated daily in-season) |
| **DraftSharks — keeper rankings** | https://www.draftsharks.com/keeper-rankings/{pos} (positions QB RB WR TE FLEX, plus /keeper-rankings/superflex) | Keeper-value ranks with 1/3/5-yr projections and age; close to dynasty value for offense only (no IDP pages listed). DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows in the page HTML, remainder loaded by script (call not seen); Insider upsell banner shown | — | Weekly guess |
| **DraftSharks — auction values** | https://www.draftsharks.com/auction-values/{pos} (positions QB RB WR TE FLEX; no format variants) | Dollar values (DS Auction Value, Auction Market Value) on a fixed full-PPR, 200-dollar, standard-roster basis. For this league: an auction cross-check only; the league's cap and roster differ, so values need rescaling. DraftSharks has no terms page found (#400), so terms are unresolved | None seen: first 25 rows in the page HTML, remainder loaded by script (call not seen); Insider upsell banner shown | — | Weekly guess (preseason use) |
| **DraftSharks — ADP market indexes** | https://www.draftsharks.com/adp/{slug} (slugs: underdog, espn, yahoo, sleeper, ffpc, dynasty, dynasty/superflex, rookie, superflex, ppr, half-ppr, best-ball, qb, rb, wr, te) | Average draft position per market and format, with trend and age; the dynasty, superflex and rookie slugs are the useful ones for this league (market ADP beside expert ranks). DraftSharks has no terms page found (#400), so terms are unresolved | None seen: one GET shows only a template with no rows, so the table loads client-side by a call not seen; filters are league type, platform, position, league size; Insider upsell banner shown | — | Weekly guess (the dynasty page showed an older date than the ranking pages) |
| **DraftSharks — trade value charts** | https://www.draftsharks.com/trade-value-chart/{format} (variants ppr, half-ppr, superflex, ppr-superflex, dynasty, dynasty/ppr, dynasty/superflex, dynasty/ppr-superflex, dynasty-startup) | Player and pick trade values, dynasty and startup versions. For this league: a cross-check on the trade-bud valuation. DraftSharks has no terms page found (#400), so terms are unresolved | Not determined: one GET of the superflex dynasty page failed on size (over 10 MB), so how it is read and any gate are unknown | — | Weekly guess |
| **CollegeFootballData** | https://collegefootballdata.com (API) | College football stats for the rookie work in #422. Not ingested yet. Terms permit derived outputs (analyses, models, rankings) only; raw API data is never republished | API key held only in a secret; never committed, never in a public repository | — | TBD (#422) |
| **Google Sheet — manifest sync (write)** | Same sheet as the team manifest (write-back) | Sync Fantrax-owned fields back into the Sheet mirror (ADR-0005) | Sheets API OAuth / service account — owner-set-up; external write + PII gate | — | On owner-manifest change |
<!-- END GENERATED sources-table:planned -->

## Rejected sources (looked at, will not be ingested)

<!-- BEGIN GENERATED sources-table:rejected — regen: python scripts/check_sources.py --render -->
| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |
|---|---|---|---|---|---|
| **PFF (Pro Football Focus)** | https://www.pff.com (paid subscription; spike #402) | Rejected (owner, 2026-11-07): PFF terms 1.5(h) and 1.5(j) bar scrapers and automated browsers; personal non-commercial use only; the Pro API and CSV route is personal and non-public | None; not ingested | — | Never (rejected) |
<!-- END GENERATED sources-table:rejected -->

## Terms and licences (every source, re-checked every 6 months)

Each source's terms verdict, when it was last checked, and the ticket that holds
the evidence. `unresolved` means no clear terms were found or none were looked
for, and is never read as cleared. A source with no check date is counted as
due by `scripts/check_sources.py`, as is one past its next check; the count is
advisory and never fails a run. The full block (how it was checked, URLs read,
credit owed, share-alike, upstream, access, permission) is in
[`sources.yml`](sources.yml). See [ADR-0022](adr/0022-source-terms-and-licences.md).

<!-- BEGIN GENERATED sources-table:terms — regen: python scripts/check_sources.py --render -->
| Source | Manifest status | Terms | Checked | Next check | Licence | Access | Evidence |
|---|---|---|---|---|---|---|---|
| **Fantrax — getPlayerStats (Players grid)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Fantrax — getPlayerStats (MINOR_FANTASY filters)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Fantrax — getDraftResults** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Fantrax — getTransactionDetailsHistory** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Fantrax — public fxea API (getDraftPicks)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | public_get | #421 (issuecomment-6710339213) |
| **Fantrax — public fxea API (getLeagueInfo)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | public_get | #421 (issuecomment-6710339213) |
| **Fantrax — public fxea API (getTeamRosters per period)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | public_get | #421 (issuecomment-6710339213) |
| **Fantrax — getLiveScoringStats + getStandings (per Scoring Period)** | live | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Google Sheet — team manifest** | live | unresolved | never | — | — | public_get | — |
| **nflverse (via nflreadpy)** | live | permitted | 2026-11-07 | 2027-05-07 | CC-BY-4.0 | public_get | #416 (issuecomment-6709476183) |
| **KeepTradeCut (KTC)** | live | rejected | 2026-11-07 | 2027-05-07 | site terms | public_get | #423 |
| **FantasyPros** | live | rejected | 2026-11-07 | 2027-05-07 | site terms | public_get | #401, #415 |
| **WalterFootball** | live | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #417 (issuecomment-6709451916) |
| **DraftSharks** | live | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DynastySharks** | live | unresolved | never | — | — | manual_file | — |
| **Manual Excel — misc rankings** | live | unresolved | never | — | — | manual_file | — |
| **Fantrax — draftPicks.go** | planned | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **Fantrax — commissioner admin** | planned | unresolved | 2026-11-07 | 2027-05-07 | site terms | owner_login | #421 (issuecomment-6710339213) |
| **PFF (Pro Football Focus)** | rejected | rejected | 2026-11-07 | 2027-05-07 | site terms | none | #402 |
| **DraftSharks — preseason rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — best ball rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — dynasty rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — weekly rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — rest of season rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — keeper rankings** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — auction values** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — ADP market indexes** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **DraftSharks — trade value charts** | planned | unresolved | 2026-11-07 | 2027-05-07 | none | public_get | #400 |
| **CollegeFootballData** | planned | permitted | 2026-11-07 | 2027-05-07 | site terms | api_key | #421 (issuecomment-6710339213) |
| **Google Sheet — manifest sync (write)** | planned | unresolved | never | — | — | api_key | — |
<!-- END GENERATED sources-table:terms -->

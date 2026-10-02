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
| **Fantrax — getPlayerStats (MINOR_FANTASY filters) + getTeamRosterInfo** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (methods getPlayerStats statusOrTeamFilter=MINOR_FANTASY_AVAILABLE\|TAKEN; getTeamRosterInfo per team) | Minors system inputs (read-only): site's minors-eligibility verdict (GP<=19) + per-team squad placement (Active/Reserve/Minors). Placement drives roster_status and the cap exemption; Minors is not a contract type (ADR-0011) | Same Fantrax session as the Players-grid source (04v imports 04a's scraper; note: lean-import reuse means check_sources.py's host scan won't flag this file — keep this entry current by hand) | `04v_minor_contracts.py` → `fact_roster_placement`<br>`04v_minor_contracts.py` → `fact_minor_eligibility` | Weekly (Windows Task Scheduler, after 04a) |
| **Fantrax — getDraftResults** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (methods getDraftResults + getFantasyLeagueInfo + getRefObject FantasyDraftPickType; one call per division) | Live-draft made-pick attribution: every slot of the startup draft board per division -> `startup_draft` events in the event-sourced ledger, the pick grid and the asset bridge (ADR-0003/0004) | Same Fantrax session as the Players-grid source (04w imports 04a's scraper: env-stored login + persistent Playwright profile) | `04w_fantrax_draft_results.py` → `(raw capture: data/raw/fantrax_draftresults_{season}_{divisionId}.json)`<br>`02d_fact_roster_transactions.py` → `fact_roster_transactions`<br>`02d_fact_roster_transactions.py` → `fact_draft_pick`<br>`02d_fact_roster_transactions.py` → `dim_roster_asset` | Live draft only — re-run between picks + on settle (never scheduled) |
| **Fantrax — getTransactionDetailsHistory** | https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6 (method getTransactionDetailsHistory; team=ALL, views TRADE + CLAIM_DROP, all pages) | Roster Moves log (trade legs, claims, drops) -> ledger `trade` / `trade_away` / `claim` / `drop` events + the per-asset trade log (players and picks). No public fxea equivalent exists | Same Fantrax session as the Players-grid source (04t imports 04a's scraper: env-stored login + persistent Playwright profile) | `04t_fantrax_transaction_history.py` → `(raw capture: data/raw/fantrax_txn_history_{season}.json)`<br>`02d_fact_roster_transactions.py` → `fact_roster_transactions`<br>`02d_fact_roster_transactions.py` → `fact_trade_log` | Manual run today (not in run_pipeline.py); ADR-0016 moves it to a full-season pull on every Change Poll trigger + the daily run |
| **Fantrax — public fxea API (getDraftPicks + getTeamRosters)** | https://www.fantrax.com/fxea/general/{getDraftPicks,getTeamRosters}?leagueId=v744203wmmvjqzv6 | Real per-pick ownership of every future rookie-draft pick (`futureDraftPicks`, incl. executed pick-for-pick trades). getTeamRosters is a print-only reconciliation check against fact_roster_placement — never written (fact_fantasy_teams stays ledger-replay-only, ADR-0003) | None (public unauthenticated REST; plain requests, no Playwright session) | `04u_fantrax_public_api.py` → `fact_draft_pick_future` | Manual run (not in run_pipeline.py) |
| **Google Sheet — team manifest** | https://docs.google.com/spreadsheets/d/1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc (gid 178660131), read via export?format=csv | Owner/team roster manifest: team name, abbrev, manager emails, division, Team ID, Fantrax-TeamId | Published CSV export (link-readable, no creds) for read | `01c_dim_fantasy_teams_seed.ipynb` → `dim_fantasy_teams` | On league/owner change (manual rerun) |
| **nflverse (via nflreadpy)** | nflreadpy package (nflverse release data) | Canonical NFL player registry, combine / pro-day metrics, IDs (gsis_id) | None (public package) | `01e_dim_nfl_players_seed.ipynb` → `dim_nfl_players`<br>`02a_fact_nfl_combine_pro_day_metrics.ipynb` → `fact_nfl_combine_pro_day_metrics`<br>`05a_startup_draft_board.py` → `(career-games lookup)` | Per pipeline run |
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
| **Google Sheet — manifest sync (write)** | Same sheet as the team manifest (write-back) | Sync Fantrax-owned fields back into the Sheet mirror (ADR-0005) | Sheets API OAuth / service account — owner-set-up; external write + PII gate | — | On owner-manifest change |
<!-- END GENERATED sources-table:planned -->

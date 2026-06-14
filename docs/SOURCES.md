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

**Anti-drift (v1).** Hand-maintained. When a source's URL, auth, or consuming
notebook changes, update its row here in the same commit. A machine-readable
`sources.yml` + lint that checks each `Feeds` notebook still references its
source is a deferred enhancement (see [PLAN.md](../PLAN.md) → Deferred-Recommended),
not v1.

---

## Live sources (feed tables today)

| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |
|---|---|---|---|---|---|
| **Fantrax — `getDraftRanks`** | `https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6` (method `getDraftRanks`) | League-specific dynasty draft-ranking board + percent-drafted (cross-league demand) | Fantrax account login, env-stored (`FANTRAX_EMAIL`/`FANTRAX_PASSWORD`); persistent Playwright profile (`data/.pw_profile/`) | `04a_fantrax_weekly_scrape.py` → `fact_fantrax_adp` | Weekly (Windows Task Scheduler) |
| **Google Sheet — team manifest** | `https://docs.google.com/spreadsheets/d/1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc` (gid `178660131`), read via `export?format=csv` | Owner/team roster manifest: team name, abbrev, manager emails, division, `Team ID`, `Fantrax-TeamId` | Published CSV export (link-readable, no creds) for **read** | `01c_dim_fantasy_teams_seed.ipynb` → `dim_fantasy_teams` | On league/owner change (manual rerun) |
| **nflverse** (via `nflreadpy`) | `nflreadpy` package (nflverse release data) | Canonical NFL player registry, combine / pro-day metrics, IDs (`gsis_id`) | None (public package) | `01e_*` → `dim_nfl_players`; `02a_*` → `fact_nfl_combine_pro_day_metrics`; `05a` career-games lookup | Per pipeline run |
| **KeepTradeCut (KTC)** | `https://keeptradecut.com` (embedded-HTML / JSON scrape) | Dynasty trade value, tiers, trends, startup ADP/auction; rookie consensus | None (public scrape) | `03c_ktc_rankings.ipynb` → `fact_rookie_rankings`; `04b_ktc_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Per pipeline run |
| **FantasyPros** | `https://www.fantasypros.com` (scrape) + manual Excel for IDP/SF | Rookie PPR + Superflex consensus (scrape); dynasty SF/IDP best/worst/avg/stddev (manual) | None (scrape); manual file (Excel) | `03a_fantasypros_rankings.ipynb` → `fact_rookie_rankings`; `04x_manual_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Per pipeline run |
| **WalterFootball** | `https://walterfootball.com` (scrape) | Rookie positional rankings | None (public scrape) | `03b_walterfootball_rankings.ipynb` → `fact_rookie_rankings` | Per pipeline run |
| **DraftSharks** | `https://www.draftsharks.com` (scrape) | Rookie top-90 board | None (public scrape) | `03d_draftsharks_rankings.ipynb` → `fact_rookie_rankings` | Per pipeline run |
| **DynastySharks** | Manual extraction → `data/raw/DynastyRankings_2026_ManualExtraction.xlsx` | Dynasty 1/3/5/10-yr fantasy-point projections + 3D value (SF/TEPP) | Manual file placement (no creds) | `04x_manual_dynasty_rankings.ipynb` → `fact_dynasty_ranking_metrics` | Manual (on refresh) |
| **Manual Excel — misc rankings** | `data/raw/*.xlsx` (RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP) | Supplemental rookie/dynasty expert ranks not available via scrape | Manual file placement (no creds) | `03x_manual_rankings.ipynb` → `fact_rookie_rankings` | Manual (on refresh) |

## Planned sources (designed, not yet ingesting — ADR-0004 / ADR-0005)

| Source | URL / locator | Purpose | Auth | Feeds (notebook → table) | Cadence |
|---|---|---|---|---|---|
| **Fantrax — `getDraftResults` / `draftPicks.go`** | `https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6` (method TBD — **HAR-capture pending**) | Acquisition events (auction $, draft slots) + draft-pick inventory → event-sourced ledger | Same as `getDraftRanks` (Fantrax login + Playwright profile) | → `fact_roster_transactions` (ADR-0003/0004); `dim_draft_pick` | Between picks (live draft) + on settle |
| **Fantrax — commissioner admin** | Fantrax commissioner pages (league `v744203wmmvjqzv6`) | Contract/cap reconciliation, manual corrections | Commissioner-account login (env-stored) | → `fact_roster_transactions` reconciliation | Ad hoc |
| **Google Sheet — manifest sync (write)** | Same sheet as above | Sync Fantrax-owned fields back into the Sheet mirror (ADR-0005) | **Sheets API** OAuth / service account — owner-set-up; ⚠ external write + PII gate | `dim_fantasy_teams` sync writer (own stage) | On owner-manifest change |

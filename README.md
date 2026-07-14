# Python · Power BI · Dynasty Fantasy Football

ETL pipeline and Power BI reporting for a 28-team, dual-conference IDP dynasty fantasy football league. Python notebooks ingest NFL data from nflverse, Fantrax, and 10 expert ranking sources into a star-schema parquet data model that feeds a Power BI dashboard.

---

## League overview

| Setting | Value |
|---|---|
| Format | Dynasty · IDP |
| Teams | 28 (14 per conference) |
| Conferences | Riddell (A01–A14) · Wilson (B01–B14) |
| Salary cap | $300,000,000 per team |
| FA minimum | $2,000,000 |
| Draft year (active) | 2026 |

---

## Data model

Star schema stored as local Parquet files under `data/`. Migration path to potential Microsoft Fabric: swap `pd.read/write_parquet` for `spark.read.parquet` with `abfss://` paths — schema stays identical.

### Dimensions

| Table | Rows | Description |
|---|---|---|
| `dim_nfl_players` | 25,036 | Full nflverse player registry; primary FK for all fact tables (`gsis_id`) |
| `dim_rookie_prospect` | 468 | Current draft-class staging table; pre-signing proxy for `gsis_id` (`player_key`) |
| `dim_fantasy_teams` | 28 | League teams, conferences, cap metadata (seeded from Google Sheet) |
| `dim_contract` | 10 | Contract type definitions driving cap-hit % and dead money |
| `dim_nfl_teams` | 36 | NFL team metadata, colors, logos (nflverse) |
| `dim_position` | 39 | Raw → canonical position transformer (covers all source variants) |
| `dim_school` | 91 | Raw → canonical school + conference transformer |
| `dim_player_alias` | 53 | Persistent fuzzy-match decisions: variant name → `player_key` |
| `dim_fantrax_crosswalk` | 1,653 | Bridge: Fantrax `scorer_id` → `gsis_id` + `player_key` |

### Facts

| Table | Rows | Description |
|---|---|---|
| `fact_rookie_rankings` | 984 | Expert rookie rankings across 10 sources and 3 phases (pre-combine → post-draft) |
| `fact_fantrax_adp` | 1,653 | Weekly Fantrax ADP snapshot — 279 offense (ADP populated) + 1,374 IDP (salary, bye, FPts) |
| `fact_nfl_combine_pro_day_metrics` | 7,434 | Combine and pro-day athletic measurements, 2000–2026 |
| `fact_fantasy_teams` | — | Active rosters, salaries, dead cap (populated by draft notebook) |

---

## Notebook inventory

All ETL notebooks are `.ipynb` in `notebooks/`. All notebooks execute with CWD = project root so `data/` paths resolve correctly.

| Notebook | Output | Notes |
|---|---|---|
| `01a_dim_rookie_prospect` | `dim_position`, `dim_school`, `dim_rookie_prospect` | Seeds 319 base prospects from nflverse combine |
| `01b_dim_contract_seed` | `dim_contract` | 10 contract type rows |
| `01c_dim_fantasy_teams_seed` | `dim_fantasy_teams` | Reads from public Google Sheet |
| `01d_dim_nfl_teams_seed` | `dim_nfl_teams` | nflreadpy `load_teams()` |
| `01e_dim_nfl_players_seed` | `dim_nfl_players` | nflreadpy `load_players()`; `_COLMAP` maps nflverse → canonical names |
| `02a_fact_nfl_combine_pro_day_metrics` | `fact_nfl_combine_pro_day_metrics` | All seasons 2000–2026; `is_current_season` flag |
| `02c_fact_rookie_rankings_seed` | `fact_rookie_rankings` | Schema seed only. (`02b`, the old fact_fantasy_teams seed, is retired to `archive/` — 02e derives the fact from the ledger) |
| `03a_fantasypros_rankings` | `fact_rookie_rankings` ← FantasyPros PPR + Superflex | Scrapes embedded `ecrData` JSON |
| `03b_walterfootball_rankings` | `fact_rookie_rankings` ← WalterFootball | Positional ranks only (no global rank) |
| `03c_ktc_rankings` | `fact_rookie_rankings` ← KeepTradeCut | `KTC_Consensus` |
| `03d_draftsharks_rankings` | `fact_rookie_rankings` ← DraftSharks | Top-90 free tier |
| `03x_manual_rankings` | `fact_rookie_rankings` ← 5 manual sources | Reads `RookieRankings_2026_ManualExtraction.xlsx` |
| `03y_dim_player_alias` | `dim_player_alias` | Backfills from archived review decisions |
| `03z_apply_fuzzy_review` | `dim_rookie_prospect`, `dim_player_alias` | Applies `data/review/review_fuzzy_matches.csv` decisions |
| `04a_fantrax_weekly_scrape.py` | `fact_fantrax_adp` | **Scheduled script** (Task Scheduler). Playwright headless auth + Fantrax API |
| `04b_ktc_dynasty_rankings` | `fact_dynasty_rankings`, `fact_dynasty_ranking_metrics`, `dim_dynasty_crosswalk` | KTC dynasty value/ranks (embedded-HTML `playersArray`); two-layer model |
| `04z_fantrax_crosswalk` | `dim_fantrax_crosswalk` | Resolves Fantrax `scorer_id` → `gsis_id`/`player_key`; back-fills fact FKs |

---

## Expert ranking sources

984 rows across 10 sources covering the 2026 draft class:

| Source | Site | Phase | Method |
|---|---|---|---|
| FantasyPros PPR | FantasyPros | post_draft | Scraped (`ecrData` JSON) |
| FantasyPros Superflex | FantasyPros | post_draft | Scraped (`ecrData` JSON) |
| FantasyPros IDP | FantasyPros | post_draft | Manual (client-side render only) |
| WalterFootball | WalterFootball | post_draft | Scraped (`<b>` tags, positional only) |
| KeepTradeCut | KeepTradeCut | post_draft | Scraped |
| DraftSharks | DraftSharks | post_draft | Scraped (top-90 free tier) |
| DynastyLeagueFootball | DynastyLeagueFootball | pre_combine | Manual Excel |
| RotoBaller | RotoBaller | post_draft | Manual Excel |
| FantasyCalc | FantasyCalc | post_draft | Manual Excel |
| mystery_iono | mystery_iono | post_draft | Manual Excel |

Phase cascade: `pre_combine → post_combine → post_draft`. Each phase's composite average feeds the next as an additional source.

---

## Fantrax weekly scraper

`04a_fantrax_weekly_scrape.py` runs on Windows Task Scheduler (Thursdays ~06:00 CT). It uses Playwright persistent context for session reuse — log in once headfully, subsequent runs are fully headless.

**Key design notes:**
- HTTP 200 ≠ success — the Fantrax API returns `WARNING_NOT_LOGGED_IN` in the body. The scraper checks the body and retries after login.
- IDP players have null ADP (Fantrax global ADP is offense-only). They are included filtered by `teamShortName != "(N/A)"` to capture active-roster defenders with salary, bye, and in-season FPts/FP/G.
- `data/.pw_profile/` stores the Playwright session and is gitignored. Never commit it.
- Credentials live in `notebooks/.env` (`FANTRAX_EMAIL`, `FANTRAX_PASSWORD`) — also gitignored.

---

## Fuzzy player matching

Cross-source player matching uses `thefuzz.fuzz.token_sort_ratio`:

| Score | Action |
|---|---|
| ≥ 90 | Auto-link; recorded to `dim_player_alias` (`decision=auto`) |
| 70–89 | Written to `data/review/review_fuzzy_matches.csv` for manual review |
| < 70 | New prospect; added to `dim_rookie_prospect` |

`dim_player_alias` is a persistent decision table keyed on `(name_clean, position_raw)`. Once a name variant is resolved, it is never re-asked — and its ranking is attributed to the correct `player_key` at ingest. Archive convention: review files are renamed `*.applied_YYYYMMDD.csv` only when every `action` is filled.

---

## Setup

```bash
# Clone and create virtual environment
git clone https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball.git
cd Python-PowerBI-DynastyFantasyFootball
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install pandas pyarrow thefuzz nflreadpy requests beautifulsoup4 openpyxl playwright python-dotenv nbformat

# Install Playwright browser
playwright install chromium

# Fantrax credentials (for 04a_fantrax_weekly_scrape.py)
# Create notebooks/.env with:
#   FANTRAX_EMAIL=your@email.com
#   FANTRAX_PASSWORD=yourpassword

# Run notebooks in order (01a → 04z) with CWD = project root
# or open workspace/FantasyFootball-workspace.code-workspace in VS Code
```

---

## Power BI

`pbi/Mouserat2.pbix` connects to the parquet files in `data/`. Refresh after running the ETL notebooks.

---

## Tech stack

| Layer | Tools |
|---|---|
| ETL | Python · Jupyter · pandas · pyarrow |
| NFL data | nflreadpy (nflverse Python port) |
| Scraping | requests · BeautifulSoup4 · Playwright |
| Player matching | thefuzz (RapidFuzz) |
| Storage | Parquet (local → potential Fabric migration path) |
| Reporting | Power BI Desktop |
| Version control | Git · GitHub · GitHub CLI |

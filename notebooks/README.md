# `notebooks/`

ETL notebooks that build the Parquet tables in `../data/`. Numbered in run order.

> **Run convention:** execute every notebook with **CWD = repository root** (not `notebooks/`),
> so relative paths like `data/...` resolve. The shared module is imported via a small
> bootstrap that adds `notebooks/` to `sys.path` regardless of CWD.

## Shared module

- **`etl_helpers.py`** — single source of truth for `LeagueConfig`, `clean_player_name`,
  `generate_player_key`, `parse_height_to_inches`, `_make_session`, `_parse_rank_date`,
  `add_players_from_source`, `ingest_ranking_source`, `append_review`. The notebooks import
  from it rather than carrying copies.

## Notebooks

| # | Notebook | Output |
|---|---|---|
| 01 | `01_dim_rookie_prospect.ipynb` | `dim_position`, `dim_school`, `dim_rookie_prospect` |
| 02 | `02_dim_contract_seed.ipynb` | `dim_contract` |
| 03 | `03_dim_fantasy_teams_seed.ipynb` | `dim_fantasy_teams` (from Google Sheet) |
| 04 | `04_dim_nfl_teams_seed.ipynb` | `dim_nfl_teams` |
| 05 | `05_dim_nfl_players_seed.ipynb` | `dim_nfl_players` (maps nflverse names → canonical schema) |
| 06 | `06_fact_nfl_combine_pro_day_metrics.ipynb` | `fact_nfl_combine_pro_day_metrics` |
| 07 | `07_fact_fantasy_teams_seed.ipynb` | `fact_fantasy_teams` (schema seed) |
| 08 | `08_fact_rookie_rankings_seed.ipynb` | `fact_rookie_rankings` (schema seed) |
| 08a | `08a_fantasypros_rankings.ipynb` | FantasyPros PPR + Superflex (scraped) |
| 08b | `08b_walterfootball_rankings.ipynb` | WalterFootball positional ranks (scraped) |
| 08c | `08c_ktc_rankings.ipynb` | KeepTradeCut consensus (scraped) |
| 08d | `08d_draftsharks_rankings.ipynb` | DraftSharks top-90 (scraped) |
| 08e | `08e_manual_rankings.ipynb` | RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP (Excel) |
| 08y | `08y_dim_player_alias.ipynb` | `dim_player_alias` (backfill from archived reviews) |
| 08z | `08z_apply_fuzzy_review.ipynb` | Applies `data/review/review_fuzzy_matches.csv` decisions |
| 09 | `09_fantrax_weekly_scrape.py` | `fact_fantrax_adp` — **scheduled script** (Task Scheduler), Playwright |
| 09a | `09a_fantrax_crosswalk.ipynb` | `dim_fantrax_crosswalk`; back-fills fact FKs |

`09` is the one `.py` (a headless-browser scrape run by Windows Task Scheduler); everything else is `.ipynb`.

## Credentials (not in git)

- `.env` — Fantrax login for `09` (`FANTRAX_EMAIL`, `FANTRAX_PASSWORD`). Gitignored.

# `notebooks/`

ETL notebooks that build the Parquet tables in `../data/`. Numbered in run order.

## Numbering convention

`NN<letter>_name` — the **group prefix** is the project pattern; the **letter** is
order within the group (`x`/`y`/`z` reserved for late-stage / apply / resolver steps):

| Prefix | Domain |
|---|---|
| **01** | Core **dimension** tables (registries, transformers, seeds) |
| **02** | Core **fact** tables (combine metrics, schema seeds) |
| **03** | **Rookie-ranking** tables & processes (draft-class expert ranks → `fact_rookie_rankings`) |
| **04** | **Dynasty-ranking** tables & processes (whole-roster value/ranks → `fact_dynasty_ranking_metrics`, plus Fantrax) |

> **Run convention:** execute every notebook with **CWD = repository root** (not `notebooks/`),
> so relative paths like `data/...` resolve. The shared module is imported via a small
> bootstrap that adds `notebooks/` to `sys.path` regardless of CWD.

## Running the `.py` scripts

Launch the `.py` scripts (`04a`, `04w`, `02d`, `02e`, …) through the repo-root
launcher so they always use the project venv:

```powershell
.\run.ps1 notebooks\04w_fantrax_draft_results.py        # extra args pass through
```

`run.ps1` pins `.venv\Scripts\python.exe`. Don't use VS Code's "Run Python File"
or a bare `python x.py` — those pick the *selected* interpreter (usually anaconda
base), which lacks `playwright` and ships a broken `pyarrow`
(`Repetition level histogram size mismatch`). The repo has two venv folders
(`venv\` and `.venv\`); the launcher pins the correct one.

## Shared module

- **`etl_helpers.py`** — single source of truth for `LeagueConfig`, `clean_player_name`,
  `generate_player_key`, `parse_height_to_inches`, `_make_session`, `_parse_rank_date`,
  `add_players_from_source`, `ingest_ranking_source`, `append_review`. The notebooks import
  from it rather than carrying copies.

## Notebooks

| # | Notebook | Output |
|---|---|---|
| 01a | `01a_dim_rookie_prospect.ipynb` | `dim_position`, `dim_school`, `dim_rookie_prospect` |
| 01b | `01b_dim_contract_seed.ipynb` | `dim_contract` |
| 01c | `01c_dim_fantasy_teams_seed.ipynb` | `dim_fantasy_teams` (from Google Sheet) |
| 01d | `01d_dim_nfl_teams_seed.ipynb` | `dim_nfl_teams` |
| 01e | `01e_dim_nfl_players_seed.ipynb` | `dim_nfl_players` (maps nflverse names → canonical schema) |
| 01f | `01f_dim_season_seed.ipynb` | `dim_season` (calendar spine, current+2; ADR-0004) |
| 01g | `01g_dim_division_seed.ipynb` | `dim_division` (`(season_id, conference)` → division name; ADR-0005 read-side) |
| 02a | `02a_fact_nfl_combine_pro_day_metrics.ipynb` | `fact_nfl_combine_pro_day_metrics` |
| 02b | `02b_fact_fantasy_teams_seed.ipynb` | `fact_fantasy_teams` (schema seed) |
| 02c | `02c_fact_rookie_rankings_seed.ipynb` | `fact_rookie_rankings` (schema seed) |
| 03a | `03a_fantasypros_rankings.ipynb` | FantasyPros PPR + Superflex (scraped) |
| 03b | `03b_walterfootball_rankings.ipynb` | WalterFootball positional ranks (scraped) |
| 03c | `03c_ktc_rankings.ipynb` | KeepTradeCut consensus (scraped) |
| 03d | `03d_draftsharks_rankings.ipynb` | DraftSharks top-90 (scraped) |
| 03x | `03x_manual_rankings.ipynb` | RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP (Excel) |
| 03y | `03y_dim_player_alias.ipynb` | `dim_player_alias` (backfill from archived reviews) |
| 03z | `03z_apply_fuzzy_review.ipynb` | Applies `data/review/review_fuzzy_matches.csv` decisions |
| 04a | `04a_fantrax_weekly_scrape.py` | `fact_fantrax_adp` — **scheduled script** (Task Scheduler), Playwright |
| 04b | `04b_ktc_dynasty_rankings.ipynb` | `fact_dynasty_ranking_metrics` (overall/positional rank folded in as metric_keys) + `dim_dynasty_crosswalk` (KTC, embedded-HTML scrape) |
| 04c | `04c_dim_dynasty_metric.ipynb` | `dim_dynasty_metric` — curated index for `metric_key` (label/group/order/direction); matrix column axis |
| 04x | `04x_manual_dynasty_rankings.ipynb` | ↑ same dynasty tables ← DynastySharks (SF/TEPP) + FantasyPros (SF/IDP) from `data/raw/DynastyRankings_2026_ManualExtraction.xlsx` |
| 04z | `04z_fantrax_crosswalk.ipynb` | `dim_fantrax_crosswalk`; back-fills fact FKs |

`04a` is the one `.py` (a headless-browser scrape run by Windows Task Scheduler); everything else is `.ipynb`.

### Dynasty rankings (04) — single EAV fact

Dynasty sources expose **incompatible metric vocabularies** (KTC trade value/tiers/trends;
DynastySharks 1/3/5/10-yr projections; FantasyPros best/worst/avg/std-dev). The 2026-06-12
refactor (ADR-0002) collapsed the former two-layer backbone+companion model into **one
long EAV fact** — even rank is just another metric:
- `fact_dynasty_ranking_metrics` — **long EAV** (`metric_key → metric_num/metric_text`),
  grain `snapshot_date × source_name × source_player_id × format`. Overall/positional rank
  fold in as source-prefixed metric_keys (`ktc_overall_rank`, `fp_positional_rank`, …);
  new sources/metrics add rows, never columns. (The separate `fact_dynasty_rankings`
  ranking backbone is **retired**.)
- `dim_dynasty_crosswalk` — `(source, source_player_id) → gsis_id + player_key` (unified across sources).
- `dim_dynasty_metric` — curated index for `metric_key` (`metric_label`/`metric_group`/`metric_order`/`direction`); use as the matrix **column axis**, sort `metric_label` by `metric_order`. The 6 per-source rank rows are generated from `SOURCE_PREFIX` (one source list shared with `04b`/`04x`).

Formats are a dimension (`SF`, `TEPP`, `IDP`, …). Sources: KTC = `04b` (scrape),
DynastySharks + FantasyPros = `04x` (manual Excel). Identity is resolved by the
**shared** `etl_helpers.resolve_dynasty_crosswalk` (one matcher for all sources;
each source notebook upserts its own rows + passes nickname overrides).

## Credentials (not in git)

- `.env` — Fantrax login for `04a` (`FANTRAX_EMAIL`, `FANTRAX_PASSWORD`). Gitignored.

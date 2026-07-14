# `data/`

Star-schema tables as **local Parquet**, produced by the notebooks in `../notebooks/`.
Read with `pd.read_parquet`, written with `df.to_parquet(path, index=False)`.
Migration path to Microsoft Fabric: swap to `abfss://` + `spark.read.parquet` — schema is unchanged.

## Dimensions

| File | Key | Produced by | Notes |
|---|---|---|---|
| `dim_nfl_players.parquet` | `gsis_id` | 01e | Full nflverse registry; primary FK for all facts |
| `dim_rookie_prospect.parquet` | `player_key` | 01a, 03x, 03z | Current draft class; pre-signing proxy for `gsis_id` |
| `dim_fantasy_teams.parquet` | `team_key` | 01c | 28 league teams + conference/cap metadata |
| `dim_contract.parquet` | `contract_id` | 01b | Contract types driving cap-hit % and dead money |
| `dim_nfl_teams.parquet` | `team_abbr` | 01d | NFL team metadata |
| `dim_position.parquet` | `position_raw` | 01a | Raw → canonical position transformer (+ `side_of_ball`) |
| `dim_school.parquet` | `school_raw` | 01a | Raw → canonical school + conference transformer |
| `dim_player_alias.parquet` | `name_clean + position_raw` | 03y, 03z | Persistent fuzzy-match decisions (variant name → `player_key`) |
| `dim_fantrax_crosswalk.parquet` | `scorer_id` | 04z | Fantrax `scorer_id` → `gsis_id` + `player_key` |
| `dim_dynasty_crosswalk.parquet` | `source_uid` (= `source\|source_player_id`) | 04b, 04x | Unified dynasty-source id → `gsis_id` + `player_key`. `source_uid` is the single-column PBI relationship key (both dynasty facts carry it) |
| `dim_dynasty_metric.parquet` | `metric_key` | 04c | Index for `fact_dynasty_ranking_metrics.metric_key`: label/group/order/direction; matrix column axis (`metric_order` = flow) |
| `dim_season.parquet` | `season_id` | 01f | Calendar spine (ADR-0004): fantasy/NFL start-end dates + `relative_nfl_season_number` (0 = current, recomputed every run — never a frozen snapshot). Anchors phase-aware logic (04a week derivation, `scripts/run_pipeline.py` phase) and the Dead Money "current/next year" measures |
| `dim_division.parquet` | `season_id + conference` | 01g | Season-scoped conference → themed division name (Riddell/Wilson for 2026-2027). Read-side of ADR-0005; write-sync to the Sheet stays gated |
| `dim_draft_pick.parquet` | `pick_ref` | 02d (replay from 04w) | Startup-draft pick inventory + current owner (trades not modeled yet — `original_owner`/`current_owner` are the same until trade events exist). ETL-only: no PBI model value, feeds `dim_roster_asset`/the ledger |
| `dim_roster_asset.parquet` | `asset_id` | 02d (replay from 04w) | Polymorphic bridge (ADR-0004): one row per draftable asset — a player (`scorer_id`/`gsis_id`/`player_key`) or a pick (`pick_ref`). ETL-only: its value is resolving `asset_id` → identity in the ledger replay, not a model join |

## Facts

| File | Grain / key | Produced by | Notes |
|---|---|---|---|
| `fact_rookie_rankings.parquet` | `player_key + source_name + phase + draft_year` | 02c, 03a–03x | Expert rankings, 10 sources, phase cascade |
| `fact_fantrax_adp.parquet` | `scorer_id + season + week` | 04a, 04z | Fantrax projection board + season-actuals backfill (incl. GP) |
| `fact_dynasty_ranking_metrics.parquet` | `snapshot_date + source_name + source_player_id + format + metric_key` | 04b, 04x | **The** dynasty fact — long EAV; ranks fold in as source-prefixed metric_keys (the separate `fact_dynasty_rankings` backbone is retired, ADR-0002) |
| `fact_nfl_combine_pro_day_metrics.parquet` | `pfr_id + season` | 02a | Combine/pro-day metrics, all seasons |
| `fact_roster_transactions.parquet` | `team_key + asset_id + event_seq` | 02d (replay from 04w) | **The** roster ledger (ADR-0003) — event-sourced source of truth (`startup_draft`, `minor_assignment`, `minor_graduation`; last-event-wins per `(team_key, asset_id)` by `event_seq`). `fact_fantasy_teams` is a replay projection, never written independently. ETL-only: not surfaced in the PBI model directly — its value is producing 02e's projection |
| `fact_fantasy_teams.parquet` | `team_key + gsis_id` | 02e (ledger replay) | Current rosters, incl. `roster_status` (observed Active/Reserve/Minors squad placement, stamped from the latest `fact_roster_placement` snapshot; Minors = cap-exempt). `cap_hit`/`dead_money` are computed by consumers (capmath, DAX), not stored |
| `fact_roster_placement.parquet` | `team_id + scorer_id + season + week` | 04v | Weekly Fantrax roster-slot snapshot (Active/Reserve/Minors), replace-by-(season, week). Feeds `roster_status` above. ETL-only: no PBI model value, it's an input to 02e |
| `fact_minor_eligibility.parquet` | `scorer_id + season + week` | 04v | Weekly Yo-Yo Rule eligibility snapshot (Fantrax's own minors-eligibility verdict, rostered + FA). Durable history enables week-over-week "graduated while in the FA pool" detection. ETL-only: no PBI model value, it's an input to 04v's own worklist diff |

## Inputs (manual extractions, in `raw/`)

- `raw/RookieRankings_2026_ManualExtraction.xlsx` — manual rookie-ranking sheets, ingested by `03x` (one sheet per source).
- `raw/DynastyRankings_2026_ManualExtraction.xlsx` — manual dynasty-ranking sheets (DynastySharks SF-PPR/TE-prem, FantasyPros SF-PPR/IDP), ingested by `04x`.

> Note: `raw/` is gitignored, so these hand-curated inputs are **not tracked in git** —
> they rely on OneDrive for backup. Un-ignore them explicitly if you want them in the repo.

## Not in git (see `../.gitignore`)

- `.pw_profile/` — Playwright browser session for the Fantrax scraper. **Contains tokens; never commit.**
- `raw/` — verbatim API captures (Fantrax `04a`, KTC `04b`) + manual extraction xlsx (see Inputs).
- `review/` — fuzzy-match review CSVs (`review_*.csv`) and their `*.applied_YYYYMMDD.csv` archives.

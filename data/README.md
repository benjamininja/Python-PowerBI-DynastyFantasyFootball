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
| `dim_division.parquet` | `season_id + conference` | 04p (Fantrax public API) | Season-scoped conference → themed division name (Riddell/Wilson for 2026-2027), from public `getLeagueInfo.teamInfo` (ADR-0016 amendment decision 12). A run replaces its own season's rows |
| `dim_scoring_period.parquet` | `season_id + period` | 04p (Fantrax public API) | Every Scoring Period of the season (17) from public `getLeagueInfo.scoringPeriods`: exact bounds `start_at`/`end_at` (UTC), `start_date`/`end_date` (days on the league's Eastern clock; neighbouring periods share a day), `is_playoff` (13–17), and the Update-Set state `update_set_state` (open / closing / closed; null for playoff and future periods) with `closed_at`. The key every in-season fact carries |
| `dim_roster_asset.parquet` | `asset_id` | 02d (replay from 04w) | Polymorphic bridge (ADR-0004): one row per draftable asset — a player (`scorer_id`/`gsis_id`/`player_key`) or a pick (`pick_ref`). ETL-only: its value is resolving `asset_id` → identity in the ledger replay, not a model join |

## Facts

| File | Grain / key | Produced by | Notes |
|---|---|---|---|
| `fact_rookie_rankings.parquet` | `player_key + source_name + phase + draft_year` | 02c, 03a–03x | Expert rankings, 10 sources, phase cascade |
| `fact_fantrax_adp.parquet` | `scorer_id + season + week` | 04a, 04z | Fantrax projection board + season-actuals backfill (incl. GP) |
| `fact_dynasty_ranking_metrics.parquet` | `snapshot_date + source_name + source_player_id + format + metric_key` | 04b, 04x | **The** dynasty fact — long EAV; ranks fold in as source-prefixed metric_keys (the separate `fact_dynasty_rankings` backbone is retired, ADR-0002) |
| `fact_nfl_combine_pro_day_metrics.parquet` | `pfr_id + season` | 02a | Combine/pro-day metrics, all seasons |
| `fact_roster_transactions.parquet` | `transaction_id + scorer_id + team_key + event_type` | 02d (replay from 04w) | **The** roster ledger (ADR-0003) — event-sourced source of truth (`startup_draft`, `trade`/`trade_away`, `claim`/`drop`; last-event-wins per `(team_key, asset_id)` by `event_seq`). The key is stable across rebuilds (ADR-0016 decision 6): `transaction_id` is Fantrax's `txSetId` on a move and the slot's `pick_ref` on a draft pick; `event_seq` is sort order only. `period` is the Scoring Period the move takes effect in. `contract_source` says where the row's contract was read (`roster_state` / `preseason` / `default`; a `Minor` set by eligibility is `default`), or `no_stint` on a drop by a team the ledger never saw the copy join. `fact_fantasy_teams` is a replay projection, never written independently. ETL-only: not surfaced in the PBI model directly — its value is producing 02e's projection |
| `fact_fantasy_teams.parquet` | `team_key + gsis_id` | 02e (ledger replay) | Current rosters, incl. `roster_status` (the observed Roster Slot as Active/Reserve/Inj Res/Minors, stamped from the newest Scoring Period in `fact_roster_state`; Minors = cap-exempt; Inj Res charges, ADR-0011). `cap_hit`/`dead_money` are computed by consumers (capmath, DAX), not stored |
| `fact_roster_state.parquet` | `season_id + period + team_key + scorer_id` | 04r (Fantrax public API) | The Roster State of each regular-season Scoring Period from public `getTeamRosters?period=N`: `roster_slot` (Starter / Bench / IR / Minors), `salary`, `contract_id`, and `capture_date` (the day, on the league's Eastern clock, the period was last read). Replace-by-(season_id, period); every period that has started and is not closed is re-read each run. A period's roster is the roster at its lineup lock. Read by `02d` (each move's contract and salary), `02e` (`roster_status`) and `04e` (who is rostered). ETL-only today |
| `fact_period_scoring.parquet` | `season_id + period + team_key + scorer_id` | 04s (Fantrax, logged in) | Period Scoring: each rostered player's fantasy points per regular-season Scoring Period, per team. `fpts` as Fantrax serves it, split into `fpts_offense`, `fpts_defense` and `fpts_special_teams`; `is_starter` marks the players who count toward the Team Score. A rostered player with no live-scoring entry has no row. A period loads once its games are final and is replaced whole each run until it is closed. ETL-only today |
| `fact_matchup.parquet` | `season_id + period + team_key` | 04s (Fantrax, logged in) | Matchups: one row per team per Scoring Period (two mirrored rows per matchup) with `opponent_team_key`, `is_home`, `fpts_for`, `fpts_against`. Win, loss and tie are derived from the scores. Loaded periods only; the future schedule is not stored. ETL-only today |
| `fact_preseason_salary.parquet` | `season_id + team_key + scorer_id` | one-off copy (#117; `contract_id` added #96) | **Frozen.** The salary and contract of every player copy rostered in the 2026-07-18 preseason capture, copied once from the retired `fact_roster_placement` (`contract_id` is its `contract` column as committed in `995f663`). Keeps the terms of a pick or a claim that left its team before Scoring Period 1. `02d` reads the contract only for a stint no Roster State row shows, and a minors-eligible player is `Minor` whatever it says. No writer, no Chain |
| `fact_minor_eligibility.parquet` | `scorer_id + season + week` | 04v | Weekly Yo-Yo Rule eligibility snapshot (Fantrax's own minors-eligibility verdict, rostered + FA). Durable week-over-week history of the eligible population. ETL-only: no PBI model value |
| `fact_draft_pick.parquet` | `pick_ref` | 02d (replay from 04w) | Completed-draft pick inventory: `current_owner` (post-trade) + `original_owner` (inferred from round 1's own slot assignment, expanded via the snake rule — Fantrax's API carries no pre-trade allocation field), `draft_type` ("Startup"/"Rookie", derived from the batch's max round). Team-asset table, same shape as `fact_fantasy_teams` |
| `fact_draft_pick_future.parquet` | `pick_ref` | 04u (Fantrax public API) | Future (unslotted, pre-draft) pick ownership, incl. already-executed pick-for-pick trades; `is_slotted=False` throughout, `draft_type` always "Rookie" |

## Inputs (manual extractions, in `raw/`)

- `raw/RookieRankings_2026_ManualExtraction.xlsx` — manual rookie-ranking sheets, ingested by `03x` (one sheet per source).
- `raw/DynastyRankings_2026_ManualExtraction.xlsx` — manual dynasty-ranking sheets (DynastySharks SF-PPR/TE-prem, FantasyPros SF-PPR/IDP), ingested by `04x`.

> Note: `raw/` is gitignored, so these hand-curated inputs are **not tracked in git** —
> they rely on OneDrive for backup. Un-ignore them explicitly if you want them in the repo.

## Not in git (see `../.gitignore`)

- `.pw_profile/` — Playwright browser session for the Fantrax scraper. **Contains tokens; never commit.**
- `raw/` — verbatim API captures (Fantrax `04a`, KTC `04b`) + manual extraction xlsx (see Inputs).
- `review/` — fuzzy-match review CSVs (`review_*.csv`) and their `*.applied_YYYYMMDD.csv` archives.

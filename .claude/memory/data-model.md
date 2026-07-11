# Fantasy Football Data Model

## Storage Standard

All dimension and fact tables: **local Parquet** (`data/{table}.parquet`).
Human-review staging files only: CSV (e.g., `review_fuzzy_matches.csv`).
Migration path: swap `pd.read/write_parquet` for `spark.read.parquet` with `abfss://` paths when moving to Fabric. Schema stays identical.

## Player Registry Architecture — Critical Design Decisions

Two-table player system bridged by `pfr_id`:

### dim_nfl_players (central registry)
- **Key**: `gsis_id` (NFL-assigned, post-signing)
- **Role**: THE authoritative player registry for the fantasy league. Every rostered player must have a row here.
- **Source**: `nfl.load_players()` via nflreadpy
- **Rookies**: NOT present until they sign rookie contracts (~4–8 weeks post-draft, May–June)
- **Notebook**: `01e_dim_nfl_players_seed.ipynb`
- **Column mapping (critical)**: nflverse names ≠ canonical schema. 01e maps `desired → source` (NOT a name-only select, which silently nulls every column). Key: `team_abbr ← latest_team`, `entry_year ← rookie_season`, `draft_club ← draft_team`, `draft_number ← draft_pick`. Cross-ref IDs in this build: `pfr_id/pff_id/espn_id/esb_id/nfl_id/otc_id/smart_id` (no yahoo/sleeper/rotowire). Bug fixed 2026-05-29 — these were 100% null prior.

### dim_rookie_prospect (pre-draft staging)
- **Key**: `player_key` (MD5 hash of name+pos+school — interim, pre-gsis_id)
- **Role**: Current draft class only. Prospects graduate to `dim_nfl_players` post-signing.
- **Source**: nflverse combine (319 base) + expert ranking sources (expanded to 367+ by 2026-05-13)
- **`gsis_id`**: nullable at seed time; ETL populates via `pfr_id` join post-signing
- **Notebook**: `01a_dim_rookie_prospect.ipynb`
- **NOTE**: Was named `dim_player` — renamed to avoid ambiguity with `dim_nfl_players`

### Player FK Strategy in Fact Tables
- **Long-term FK**: `gsis_id` → `dim_nfl_players` (primary)
- **Interim FK**: `player_key` → `dim_rookie_prospect` (null once player signs)
- Both columns present in all fact tables during the pre-signing window

## Star Schema Tables

### Dimensions

| Table | Key | Source | Notes |
|---|---|---|---|
| `dim_nfl_players` | `gsis_id` | nflreadpy `load_players()` | Central player registry |
| `dim_rookie_prospect` | `player_key` | nflreadpy `load_combine()` + expert sources | Pre-draft staging |
| `dim_position` | `position_raw` | Hardcoded seed | Transformer: raw → canonical. Covers all FantasyPros + WalterFootball codes |
| `dim_school` | `school_raw` | Hardcoded seed | Transformer: raw → canonical + conference |
| `dim_contract` | `contract_id` | Hardcoded seed | 10 rows; 1st/2nd/.../FA |
| `dim_fantasy_teams` | `team_key` | Google Sheet | 28 teams; A01-A14 Riddell, B01-B14 Wilson. + `fantrax_team_id` (01c maps Sheet col `Fantrax-TeamId` → resolves teamId→team_key for the ledger, ADR-0004/0005). Sheet is Fantrax-synced mirror (ADR-0005) |
| `dim_nfl_teams` | `team_abbr` | nflreadpy `load_teams()` | NFL team metadata |
| `dim_fantrax_crosswalk` | `scorer_id` | notebook 04z | Bridge: Fantrax scorer_id → gsis_id + player_key |
| `dim_dynasty_crosswalk` | `source + source_player_id` | notebook 04b | Unified bridge: any dynasty source's id → gsis_id + player_key |
| `dim_dynasty_metric` | `metric_key` | notebook 04c | Index for fact_dynasty_ranking_metrics.metric_key: label/group/order/direction (matrix column axis) |
| `dim_player_alias` | `name_clean + position_raw` | notebook 03y | Persistent fuzzy-review decisions → player_key; stops repeat questions |
| `dim_roster_asset` | `asset_id` | notebook 02d (**BUILT 2026-06-14**) | **ADR-0004.** Polymorphic bridge: `asset_type` (player/prospect/pick) + nullable resolvers `gsis_id?`/`player_key?`/`pick_ref?` + **`scorer_id`** (the stable Fantrax natural key `asset_id` is minted on). `asset_id` = monotonic int, assigned at first sight, persisted, never re-derived; stable across Sign; Exercise mints a NEW asset + lineage. v1: 137, all `player` |
| `dim_draft_pick` | `(draft_season, divisionId, overall_slot)` slot key (`pick_ref` mirrors it) | notebook 02d ← `getDraftResults` (**BUILT 2026-06-14**) | **ADR-0004.** Pick grid (490 slots/division, made or not). `overall_slot = (round-1)*N + pick_in_round` (snake). Carries `current_owner`, `round`, `pick_in_round`, `is_made`. ⚠ **`original_owner` NULL** — getDraftResults' `teamId` is the *current* owner and **startup picks were traded**; original allocation needs `draftPicks.go` (not captured), which also lights up `pick_allocation`/`trade` (dormant v1) + forward years |
| `dim_season` | `season_id` (`"2026-2027"`) | notebook 01f (**BUILT 2026-06-14**) | **ADR-0004.** Calendar spine, self-extending anchor+2 horizon (**changed 2026-07-11**: floats off today's date via `_anchor_start_year`, not pinned to `CFG.draft_year` — re-running after crossing into a new fantasy season, Mar 1, auto-adds the next future row; history is never dropped, each run unions with existing `season_start_year`s). `season_start/end_year`, `season_fantasy_start_date` (Mar 1 start yr) / `_end_date` (last Feb day end yr), `season_nfl_start/end_date` (public sched, nullable), `theme`, **`relative_nfl_season_number`** (0 = anchor season containing today via the fantasy window, negative=past/positive=future, recomputed every run — feeds the dead-money design, see project-fantasy-football.md). Fantasy yr = Mar 1 → before Mar 1 |
| `dim_division` | `(season_id, conference)` | notebook 01g (**BUILT 2026-06-14**) | **ADR-0005 (read-side).** Transformer (dim_position pattern): `conference` stable `A`/`B` → `division_name` (seasonal label, `Riddell`/`Wilson` for 2026-2027). Season-scoped division naming; `dim_fantasy_teams.conference` resolves label by join (no downstream IF). Names **derived** from `dim_fantasy_teams.division` (Sheet truth via 01c), stamped current `season_id`; seeds known seasons only (v1 = 2026-2027, 2 rows). Sheet **write**-sync still gated |

### Facts

| Table | Key | Notes |
|---|---|---|
| `fact_nfl_combine_pro_day_metrics` | `pfr_id + season` | All seasons; `is_current_season` flag; both FKs present (notebook 02a) |
| `fact_fantasy_teams` | `team_key + gsis_id` | Current-roster state, **10-col schema** (`team_key`, `gsis_id`, `player_key`, `contract_id`, `contract_value`, `contract_year`, `dead_money`, `status`, `acquired_method`, `season` — trimmed from 12 cols 2026-07-11: `conference`/`cap_hit` removed, both 100% derivable via relationships, see below). **DERIVED** by `02e` (replay `fact_roster_transactions` → latest active contract per (team_key, asset_id), ADR-0003). `02e` no longer rolls cap up into `dim_fantasy_teams` either (changed 2026-07-11; see "dim_fantasy_teams Cap Columns" below). **BUILT 2026-06-14** (137 rows). |
| `fact_roster_transactions` | `season_id + event_type + team_key + asset_id + event_seq` | Event-sourced acquisition ledger = SSOT (ADR-0003 key amended by ADR-0004). **BUILT 2026-06-14** by `02d` (live-loop), 137 `startup_draft` rows (Riddell). `event_type` enum = **startup_draft** (snake draft — corrected from the ADRs' misnamed `startup_auction`; real auctions = FA/re-sign next offseason) / rookie_draft / fa_auction / fa_pickup / resign(+drop) / pick_allocation / trade — last two **dormant v1**. Each pick → Initial contract yr1 (`contract_id`=1st, cap_hit 0.50×), `contract_value` = Fantrax `salary` (as-of capture, via `dim_fantrax_crosswalk` scorer_id→gsis→adp). 18 cols incl. `event_seq`=overall pick#, `event_date`, `scorer_id`/`gsis_id` audit, `draft_round`/`pick_in_round`/`pick_overall`. Source `getDraftResults` via `04w` (**SW-served → HAR can't carry body**; fetch through authed ctx). Idempotent replace-by `(season_id, event_type)` |
| `fact_rookie_rankings` | `player_key + source + phase + draft_year` | Rookie-class expert ranks; pipeline 02c + 03a–03x |
| `fact_fantrax_adp` | `scorer_id + season + week` | Fantrax projection board + season-actuals; notebook 04a |
| `fact_dynasty_ranking_metrics` | `snapshot_date + source_name + source_player_id + format + metric_key` | **Single dynasty fact** (long/EAV): all source metrics + folded `*_overall/positional_rank` + `composite_adp`; carries `gsis_id`; notebooks 04b/04x/04y. `fact_dynasty_rankings` backbone **retired 2026-06-12**. |
| `fact_nfl_combine_pro_day` | **RETIRED** | Consolidated into `fact_nfl_combine_pro_day_metrics` |

### In-season (deferred — not yet built)
- `fact_nfl_player_stats` — key: `player_id + game_id`
- `fact_nfl_season_injuries` — key: `gsis_id + season + week`

## fact_rookie_rankings Pipeline (notebook 02c)

### Schema
```
player_key      -- interim FK -> dim_rookie_prospect (composite dedup key)
gsis_id         -- FK -> dim_nfl_players (null pre-signing)
source_name     -- expert source name (e.g. "FantasyPros_PPR", "RotoBaller")
source_site     -- parent site (e.g. "FantasyPros", "RotoBaller")
phase           -- pre_combine | post_combine | post_draft
draft_year
global_rank     -- null for WalterFootball (no cross-position board)
positional_rank -- rank within position page
grade           -- rank_ave for FantasyPros; Avg for DLF; global_rank for others; null for WalterFootball
capture_date    -- date ETL ran
rank_date       -- date ranking was published by source
```
Dedup key: `[player_key, source_name, phase, draft_year]` — keep="last" on re-run.

### Phase cascade
```
pre_combine composite  = avg(all expert pre_combine sources)
post_combine composite = avg(experts + pre_combine composite)
post_draft composite   = avg(experts + post_combine composite)
```
Stored with `source="composite"` and appropriate phase.

### Source-specific notes
- **FantasyPros PPR/Superflex** (03a, scraped): `grade = rank_ave`; `global_rank = rank_ecr`
- **FantasyPros IDP** (03x, manual): `dynasty-rookies-idp.php` raw HTML returns veteran draft board — defensive rookies render client-side only. Manually extracted to Excel.
- **WalterFootball** (03b, scraped): `grade = None`, `global_rank = None` — positional rank only. `_POS_NORM = {"3-4DE": "DE", "3-4OLB": "OLB"}`
- **KeepTradeCut** (03c), **DraftSharks** (03d): scraped
- **RotoBaller, mystery_iono, DynastyLeagueFootball, FantasyCalc** (03x, manual): from `RookieRankings_2026_ManualExtraction.xlsx`
- **DynastyLeagueFootball**: phase=`pre_combine` (Rank_Date 2025-12-31); `grade = Avg` (consensus across 6 named experts)

## fact_fantrax_adp Pipeline (notebook 04a)

Weekly Fantrax draft-board snapshot. League `v744203wmmvjqzv6`. Playwright headless scrape (`04a_fantrax_weekly_scrape.py` — a `.py` script, scheduled via Task Scheduler).

### Schema
```
scorer_id       -- Fantrax-native player id (composite key)
season          -- snapshot_season (e.g. 2026)
week            -- "PRE" or zero-padded "01".."18"
capture_date    -- date the scrape ran
player_name, position_raw, nfl_team
is_rookie       -- bool from scorer.rookie
overall_rank    -- Fantrax "Rk": rank by FPts across the whole pool (computed, see below)
adp             -- Average Draft Position (statsAll[4]); rank-on column
salary          -- cap salary (statsAll[1])
percent_drafted
fpts            -- total fantasy points (statsAll[2]); PHASE-AWARE (proj preseason / YTD in-season)
fpts_per_game   -- FP/G (statsAll[3]); same phase-aware semantics
games_played    -- GP; NULL on draft-ranks board rows, populated by the getPlayerStats backfill
age             -- integer age; board rows derive from dim_nfl_players.birth_date via gsis_id,
                --   getPlayerStats rows take Fantrax's Age column directly
gsis_id         -- FK -> dim_nfl_players (via crosswalk)
player_key      -- FK -> dim_rookie_prospect (via crosswalk)
```
Two snapshot TYPES share this table:
- **Projection board** (getDraftRanks, `board_to_frame`): weekly, ~1,655 rows, `week`=PRE/01..18, GP null.
- **Season-actuals backfill** (getPlayerStats, `backfill_player_stats` → `player_stats_to_frame`): completed seasons, e.g. **season=2025, week='YTD'** (~2,282 active-roster O+D players incl. real GP) as a counterpoint to projections. `gsis_id` ~28% null here until 04z re-runs (YTD population has scorer_ids not yet in the crosswalk).
NOTE: `score` was renamed to `fpts` (2026-06-06); `load_fact` migrates the legacy column on read.
Write semantics: **replace-by-`(season, week)`** — each run scrapes the whole board, so existing rows for the run's week are dropped before append (truly idempotent; no orphan rows when board composition shifts). `[scorer_id, season, week]` drop_duplicates is a safety net.

### Extract notes
- Endpoint `POST https://www.fantrax.com/fxpa/req?leagueId=...`, method `getDraftRanks`. **HTTP 200 ≠ success** — check body `pageError.code` for `WARNING_NOT_LOGGED_IN`.
- Response `responses[0].data.fullStats` = full ~8600 scorer universe. **Board = ~280 offense rows (non-null ADP, `statsAll[4]`) + ~1,374 active-roster IDP** = ~1,653 rows total. Fantrax global ADP is offense-only, so IDP have null ADP but are kept for salary/bye/Rk (filter `teamShortName != "(N/A)"`). `statsAll` order: `[bye, salary, fpts, fptsPerGame, adp, percentOwned]`.
- **Phase-aware timeframe** (`resolve_season_or_projection`): preseason runs request `PROJECTION_0_23l_SEASON` (season projection → real FPts/FP-G); once Week 1 completes, in-season runs request `SEASON_23l_YEAR_TO_DATE` (YTD actuals). statsAll[2]/[3] are 0 in offseason YTD — hence the projection split.
- **overall_rank** = Fantrax "Rk" reproduced by ranking the full ~8,600 pool by FPts (statsAll[2]) desc (validated against `getPlayerStats` `scorer.rank`). **age** is derived from `dim_nfl_players.birth_date` via the crosswalk gsis_id — a registry attribute, not a board field.
- **Games-played + per-stat splits** live ONLY on the Players grid: method `getPlayerStats`, `data={statusOrTeamFilter, pageNumber, maxResultsPerPage(≤500), positionOrGroup, miscDisplayType:"1", seasonOrProjection, timeframeTypeCode}`. **Now wired in** via `backfill_player_stats` (2026-06-06). Critical: the `ALL` position group returns only 12 overview cols (NO GP) — must pull `FOOTBALL_OFFENSE` (8 pages) + `FOOTBALL_DEFENSE` (10 pages), each 27 cols with GP at index 26, then union (dedup dual-eligibles, keep first). Parse columns by header `shortName` not fixed index (splits differ by group). `scorer.rank` is GLOBAL (matches getDraftRanks rank) → used directly as overall_rank. Completed-season codes in `YTD_SEASON_CODES` (2025→`SEASON_23j_YEAR_TO_DATE`, 2024→`SEASON_23h_YEAR_TO_DATE`). Run: `backfill_player_stats(CFG, season=2025, week="YTD")`.
- **IDP position set is derived from `dim_position`** (`side_of_ball == "Defense"`) via `_idp_positions(cfg)`, with a 12-code hardcoded fallback if the dim isn't seeded — so a new defensive code in `dim_position` is auto-picked-up (was a hardcoded `_IDP_POS` constant until 2026-05-30).
- Auth: persistent context `data/.pw_profile` + `.env` creds; probe→login→retry. Login form is Angular Material (`input[formcontrolname='email'|'password']`, submit via Enter); SPA never hits `networkidle`.
- Dual-eligible players (e.g. Travis Hunter `WR,DB`) appear twice with one `scorer_id` → deduped.
- **Identity FKs via `dim_fantrax_crosswalk` (04z)**: `scorer_id` → `gsis_id` (universal, `dim_nfl_players` covers ~100% incl. signed rookies) + `player_key` (rookies only). 04a joins the crosswalk during `board_to_frame` (`_load_crosswalk`); unresolved new scorer_ids stay null until 04z re-runs.

## dim_fantrax_crosswalk Pipeline (notebook 04z)

Bridge resolving Fantrax `scorer_id` to the player registries. Built from distinct `scorer_id`s in `fact_fantrax_adp`, then back-fills the fact's FK columns.

### Schema
```
scorer_id      -- PK (Fantrax-native id)
player_name, position_raw, nfl_team, is_rookie  -- carried for review/debug
gsis_id        -- FK -> dim_nfl_players (primary, ~100% coverage)
player_key     -- FK -> dim_rookie_prospect (rookies only)
match_method   -- exact | exact+disambig | fuzzy | manual | review | unmatched
match_score    -- 100 for exact/manual; token_sort_ratio for fuzzy
resolved_date
```

### Matching
1. `clean_player_name` → exact match vs `dim_nfl_players.display_name`.
2. If >1 candidate (16 of 279, e.g. Josh Allen QB vs LB): disambiguate by **position** (`position`/`position_group` vs Fantrax `pos_tokens`) → active status (`ACT`) → team / most recent `entry_year`. Position is the strongest signal.
3. No exact: `fuzz.token_sort_ratio` over all cleaned nfl names — auto ≥90, review 70–89, unmatched <90... <70.
4. `player_key`: exact cleaned-name vs `dim_rookie_prospect`.
5. Review/unmatched → `review_fantrax_crosswalk.csv` (archive `.applied_YYYYMMDD.csv` after fixing). Nickname vets (Cameron→Cam Skattebo, Chigoziem→Chig Okonkwo, Christopher→Chris Brooks) needed manual gsis_id. As of 2026-06-06 (post 2025-YTD backfill): 2,288 scorer_ids, ~98% gsis.

## Dynasty Rankings Pipeline (section 04 — single EAV fact)

Multi-source whole-roster dynasty value/ranks. Sources have **incompatible metric
vocabularies** (KTC value/tier/trend/crowd/market; DynastySharks 1/3/5/10-yr proj +
3D-value + analysis-text; FantasyPros best/worst/avg/std-dev), so everything is stored
long/EAV — new sources/metrics add ROWS, never columns.

**Refactored 2026-06-12 (via /grill-me): two-layer → single fact.** The old
`fact_dynasty_rankings` backbone is **retired**. `overall_rank`/`positional_rank` are
folded into the EAV as **source-prefixed** metric_keys (`ktc_/ds_/fp_overall_rank`,
`…_positional_rank`); player name/position/team/age now come from `dim_nfl_players` via a
gsis relationship, not duplicated on a fact. *Pending materialization:* user reruns
04b→04x→04y→04c and deletes the `Fact_DynastyRankings` table + its 4 relationships from
the PBI model — until that rerun the on-disk parquet still shows the OLD two-layer shape.

### fact_dynasty_ranking_metrics (the only dynasty fact, long/EAV)
```
snapshot_date  -- real DATE (was ISO text); manual cadence, time series   [key]
source_name    -- "KTC"|"DynastySharks"|"FantasyPros"|"Composite" [key, partition]
source_player_id, format ("SF"|"TEPP"|"IDP")                              [key]
metric_key     -- ONE source per key (FD: source lives in the dim)        [key]
source_uid     -- f"{source_name}|{source_player_id}" (crosswalk surrogate)
gsis_id        -- NEW: direct FK → dim_nfl_players (the fact's own player path)
metric_num / metric_text  -- numeric / text value
```
Every `metric_key` maps to exactly ONE source, so `dim_dynasty_metric.source_name` is the
sole attribution source-of-truth — the fact's `SourceName` column was **dropped from the
PBI model** (but `source_name` stays in the parquet: the partition load keys on it).
MetricNum/ranks default to **AVERAGE** (a summed rank is meaningless). The old
`MetricIndex` composite key + its hardcoded-date Power Query step are gone. Load =
replace-by-`(snapshot_date, source_name)`.

### composite_adp (notebook 04y — cross-source post-pass)
KTC `adp` (crowd Elo) and DS `adp` (projection model) measure different things on
incommensurable scales (KTC overall-pick ints; DS round.pick, ~0.13 rank-corr), so `adp`
was **split** into `ktc_adp` / `ds_adp`. 04y blends them: percentile-within-`(source,
format)` → mean → re-rank to 1..N = `composite_adp`, plus `sources_count` (1|2)
confidence. Written as a `source_name="Composite"` partition keyed by **gsis_id** (no
source row → relates to players via gsis only); single-source players keep their sole
percentile. KTC `adp`/`startup_adp` `0` = "no ADP recorded" sentinel → treated as missing
(else it false-ranks #1). Runs AFTER 04b+04x.

### dim_dynasty_crosswalk
`source_uid` (PK) + `(source, source_player_id)` → gsis_id + player_key + match_method/score.
One table for ALL dynasty sources (vs per-source `dim_fantrax_crosswalk`).

### Power BI relationships (why source_uid exists)
`source_player_id` is **NOT unique** across sources — 240 slugs (e.g. `alvin-kamara`)
appear under both DynastySharks and FantasyPros, so a single-column relationship on it
breaks (240 dup keys on the one-side → blanks/M2M, the "low match rate" symptom). PBI
relationships are single-column, and the grain is composite, so each fact + the
crosswalk carry **`source_uid` = `source_name|source_player_id`** (unique in the
crosswalk, 1381/1381). Model: `fact_*[source_uid] → dim_dynasty_crosswalk[source_uid]`
(many:1), then `dim_dynasty_crosswalk[gsis_id] → dim_nfl_players[gsis_id]`. Metrics
reach a gsis ~99.7% this way. **As of 2026-06-12 the metrics fact also carries `gsis_id`
directly** (its own active relationship to `dim_nfl_players`); the `source_uid`→crosswalk
path remains the ETL identity resolver. Players that don't resolve to a gsis drop out of
the model (the backbone no longer keeps them visible).

### Shared resolver (single source of truth)
**`etl_helpers.resolve_dynasty_crosswalk(identities, data_dir, overrides=None, ...)`**
— ONE matcher used by every section-04 source notebook (no per-notebook copies).
Mirrors 04z: exact clean-name vs `dim_nfl_players.display_name` → disambiguate
position/ACT/recency → fuzzy ≥90 (`review` 70–89, else `unmatched`); `overrides`
{source_player_id→gsis} → method `manual`; if no gsis but a `player_key` matches →
`rookie`. Each notebook builds identities, calls it, upserts its `source` rows.

### KTC (notebook 04b)
- `requests.get` the dynasty page; regex `var playersArray\s*=\s*(\[.*?\]);` → `json.loads` (full DB embedded in HTML, no browser).
- `superflexValues` → format `SF`; nested `superflexValues.tepp` → `TEPP`. Per-format: value, rank (→`ktc_overall_rank`), positionalRank (→`ktc_positional_rank`), overall_tier/positional_tier. Format-agnostic (trends/kept/traded/cut/`ktc_adp`/auction/liquidity) duplicated onto both formats. `oneQBValues` (1QB) skipped — SF league.
- `position=="RDP"` (rookie draft picks, 36) excluded — no player identity.
- Overrides: `533`→Gabe Davis, `1320`→Chig Okonkwo; Le'Veon Moss=rookie. gsis ~99.8%, 0 review. Raw → `data/raw/ktc_dynasty_{date}.json`. (Post-refactor: writes only the metrics fact; no backbone.)

### Manual sources (notebook 04x)
- `data/raw/DynastyRankings_2026_ManualExtraction.xlsx`, sheet → (source, format): DynastySharks SF/TEPP (metrics `ds_adp`, proj_1/3/5/10yr, ds_value, analysis-text), FantasyPros SF + IDP (best/worst/avg/stddev). Pos token `QB1`→QB+rank 1; source_player_id = name slug. Parse via `df.to_dict("records")` (itertuples mangles `1yr. Proj`/`AVG.` headers). Ranks fold in as `ds_/fp_overall_rank`+`…_positional_rank` (melt + `_RANK_PREFIX`); builds `backbone` only in-memory for the crosswalk, no longer writes it.
- Manual gsis ~99.5% after nickname overrides; ~2 review (Daylan Smothers, Mark Fletcher — not yet in any registry). Review CSV = projection of crosswalk unresolved rows, rebuilt each run.
- **metric_key vocab (post-refactor):** ranks `ktc_/ds_/fp_overall_rank`, `…_positional_rank`; KTC `value, overall/positional_tier, overall/positional_trend, overall/positional_7day_trend, kept, traded, cut, ktc_adp, avg_auction_pct, startup_adp, startup_avg_auction_pct, std_liquidity`; DS `ds_adp, proj_1yr/3yr/5yr/10yr, ds_value, analysis(text)`; FP `best, worst, avg, stddev`; Composite `composite_adp, sources_count`. Each key = one source (no shared keys after the `adp` split).

### dim_dynasty_metric (notebook 04c) — metric_key index
Curated transformer/seed (like dim_position) so PBI can use metrics as a **matrix
column axis**. Cols: `metric_key` (PK), `metric_label`, `metric_group` (Rank/Value/Tier/
Projection/Consensus/Market/Trend/Crowd/Notes — `Rank` added 2026-06-12, order 1–6),
`metric_order` (10s with gaps — controls column flow; set `metric_label` *Sort by column*
= `metric_order`), `value_type` (num/text), `direction` (up/down/neutral → conditional
formatting), and **`source_name`** (added 2026-06-12 — the one source that owns each key;
`Composite` for derived blends). 04c validates the seed covers every fact metric_key.

## Acquisition Ledger — `fact_roster_transactions` + derived `fact_fantasy_teams` (design 2026-06-13)

Event-sourced design (ADR-0003; build deferred to its own stage). The ledger is
SSOT; the roster fact is a projection.

- **`fact_roster_transactions`** (append-only event log): unified fact, one row
  per acquisition event, `event_type` discriminator (startup_auction /
  rookie_draft / fa_auction / fa_pickup / resign — resign = re-sign + franchise
  tag; add `drop` for dead-money realization). New event types add ROWS, not
  tables. `contract_value` ← Fantrax salary; `cap_hit` DERIVED by contract type
  (`dim_contract.cap_hit_pct` × value by `contract_year`, never stored twice);
  `dead_money` = guaranteed residual; Yo-Yo cap-exempt while `ml_games_left > 0`
  (see [[startup-draft-board-05a]]). gsis via `dim_fantrax_crosswalk`.
- **`fact_fantasy_teams`** = replay the ledger → latest active contract per
  rostered player. Derivable from startup data alone → enables running the
  scraper **live between picks** during the startup draft to refresh 05a
  availability (`startup_draft_board.xlsx`).
- **Source/load**: 04a-style Playwright + Fantrax `fxpa/req`
  (`getDraftResults`-type method), persistent `.pw_profile`, full snapshot →
  replace-by-`(season, event_type)`, idempotent. Reuse `etl_helpers`.
- v1 scope = startup auction (35 rounds); schema forward-compatible.

## Unified Asset Identity — `asset_id` / `dim_roster_asset` (design 2026-06-13, ADR-0004)

Resolved via `/grill-with-docs`. Bridges the three identity regimes the league
had grown into (`gsis_id` players · `player_key` prospects · nothing for picks).

- **`dim_roster_asset`** = thin polymorphic bridge: `asset_id` (PK, opaque
  surrogate) → `asset_type` (player/prospect/pick) + nullable `gsis_id?` /
  `player_key?` / `pick_ref?`. Generalizes the crosswalks one level up.
- **Stability:** `asset_id` permanent; resolver migrates underneath. **Sign**
  (prospect→player) = identity continuity (same asset_id, `gsis_id` fills in) —
  kills the dual-FK null-flip. **Exercise** (pick→player) = consumption: pick
  retired, NEW player asset_id minted, `rookie_draft` row links
  `spent_asset_id`(pick) → `asset_id`(player).
- **Ledger key** is now `season_id + event_type + team_key + asset_id +
  event_seq` (was `gsis_id`; ADR-0004 amends ADR-0003).
- **Picks event-sourced in the same ledger:** `pick_allocation` seeds initial
  ownership from the Fantrax `draftPicks.go` snapshot; `trade` defined but
  **dormant v1** (fresh startup, snapshot has no trade history). Pick horizon =
  current + ≥1 future `season_id` (current+2 during rookie-draft window = future
  confirm). `fact_fantasy_teams` derives pick inventory by replaying these.
- **`dim_draft_pick`** = pick commodity dim, parallel to `dim_nfl_players`.
  `pick_ref = (draft_season, round, original_owner)`, stable under trade;
  `overall_slot` nullable/late-resolving. `draft_season → season_id`.
- **`dim_season`** = calendar spine, PK `season_id` `"2026-2027"`; fantasy yr
  Mar 1 → before Mar 1; NFL dates from public schedule (nullable). New facts use
  `season_id`; `dim_draft_pick.draft_season` too.
- **Team identity:** resolve Fantrax `teamId → team_key` via a new
  `fantrax_team_id` column on `dim_fantasy_teams` (front-runs the owner-manifest
  task). Fact keys stay in league `team_key` space (A01–A14/B01–B14).
- **Valuation deferred:** KTC RDP pick values are a time-varying market estimate
  (≈0 in offseason, firms up weekly) → model later as snapshot-dated metric on
  the pick *class*, NOT a fixed `dim_draft_pick` attribute. v1 = inventory only.
- **Migration posture:** new facts only; existing `gsis_id`/`player_key`/
  `draft_year` FKs unchanged until a deliberate migration.

## Owner Manifest — Fantrax → Sheet sync (design 2026-06-13, ADR-0005)

`dim_fantasy_teams`' Google Sheet becomes a **field-scoped synced mirror** of
Fantrax (upstream SSOT for owner/team attributes). Resolved via `/grill-with-docs`.

- **Join on `Fantrax-TeamId`** (managers aren't unique — one email owns multiple
  teams). Inner; update matched rows only; never add/delete rows.
- **Locked (never written):** `Division`, `Team ID` (team_key), `Fantrax-TeamId` —
  owner-only. **Synced from Fantrax:** Team Name, Team Abbreviation, Manager Email,
  Other Manager Email.
- **Diff-only writes** (changed cells only, idempotent, print diff first); write
  range guarded to exclude locked columns. Unmatched either side → soft-fail +
  `data/review/` CSV (04z pattern).
- The Sheet is **both read (01c) and written (sync)** — it is the merge point of
  Fantrax-owned + owner-owned columns, not a pure mirror.
- ⚠ **Build-time gate:** external write to shared content → explicit owner
  go-ahead + Sheets-API auth (owner-set-up, no assistant credential entry);
  manager emails are PII → writes scoped to the 4 mutable columns.
- `01c` adds `Fantrax-TeamId → fantrax_team_id` to its `_COL_MAP` (the column
  exists on the Sheet now; the seed's stale printed column list predates it).

## dim_fantasy_teams Cap Columns

**Changed 2026-07-11**: `dim_fantasy_teams` only carries the two cap facts
that are true independent of the roster:

| Column | Formula |
|---|---|
| `original_cap` | `CFG.total_cap` — static |
| `reinvestment_cap` | In-season bonus cap charges |

Everything roster-derived (`active_roster_salary`, `cap_hits_current_yr` /
dead money, `remaining_cap_current_yr`, `remaining_cap_next_yr`) used to be
an ETL rollup `02e` wrote back into this table — that was a second,
ETL-frozen implementation of the same math already sitting live on
`fact_fantasy_teams`, and it went stale under any Power BI report filter
(fixed 2026-07-11). It's now computed on read, not cached: DAX measures in
`pbi/mouserat2/.../_Measures.tmdl` (`'Active Roster Salary'`, `'Dead
Money'`, `'Remaining Salary Cap'`) for Power BI, `discord_bot/capmath.py`
for the bot. One formula (`original_cap - (active_roster_salary +
dead_money + reinvestment_cap)`), implemented twice (DAX + pandas), not
cached a third time in the parquet.

## Transformer Tables

`dim_position` and `dim_school` normalize raw values across heterogeneous sources.
Every ETL notebook that touches position or school data must join these transformers.
Maintenance: add a row when a new raw value appears — never add if/else logic downstream.
All FantasyPros and WalterFootball position codes confirmed covered; no additions needed as of 2026-05-13.

## 02a_fact_nfl_combine_pro_day_metrics Schema (key columns)

```
pfr_id, season              -- composite key
gsis_id                     -- FK -> dim_nfl_players (null pre-signing)
player_key                  -- interim FK -> dim_rookie_prospect (null for historical)
is_current_season           -- bool: season == CFG.draft_year
player_name, pos, school, cfb_id
draft_team, draft_round, draft_ovr
metric_source               -- "combine"
height_inches, weight
forty_yard, ten_split, bench_press, vertical_jump, broad_jump, three_cone, shuttle
hand_size, arm_length, wingspan  -- optional nflverse cols
```

## Shared Module — `notebooks/etl_helpers.py` (single source of truth)

Imported by 01a, 02a, 03a–03x, 03z, 04b, 04x (NOT copied — consolidated 2026-05-30, ~1,500 dup lines removed). Exports `LeagueConfig`, `clean_player_name`, `generate_player_key`, `parse_height_to_inches`, `_make_session`, `_parse_rank_date`, `add_players_from_source`, `ingest_ranking_source`, `append_review`, `resolve_dynasty_crosswalk` (shared dynasty matcher), `load_replace_partition` / `upsert_dynasty_crosswalk` / `write_dynasty_review` (shared dynasty load/upsert/review, added 2026-06-06), `DEFAULT_HEADERS`.

- `parse_height_to_inches` — `6'2"`, `6-2`, `602`, numeric, None
- `clean_player_name` — strip periods, normalize NBSP/apostrophes, lowercase. **Keeps apostrophes + suffixes** (feeds the deterministic `generate_player_key` hash → must stay byte-stable).
- `clean_name_for_match` — aggressive normalizer for fuzzy cross-source **matching only**: additionally strips apostrophes + generational suffixes (jr/sr/ii..v). Shared by `resolve_dynasty_crosswalk` (04b/04x) and the Fantrax crosswalk (04z). (2026-06-14: consolidated — was duplicated verbatim in 04z's local def + `resolve_dynasty_crosswalk._clean`.)
- `generate_player_key` — MD5 12-char deterministic hash of name+pos+school
- `add_players_from_source` / `ingest_ranking_source` — canonical alias-aware matcher/ingester (consolidating these fixed the auto-match alias-drop bug that had silently affected 03a/03c/03d)

Config consolidation (swept 2026-06-14): 01b/01c/01d/01e/02b/03y/04z all import the shared `CFG` (no local `LeagueConfig` copy) — reference `CFG.initial_contract_years`, `CFG.fa_minimum_salary`, `CFG.team_sheet_csv_url`, `CFG.alias_name`, `CFG.path(CFG.fact_name)`, `CFG.fuzzy_*`, etc. **04a keeps its own `LeagueConfig` by design** — it is the lean-import SSOT for the Fantrax scraper cluster (04w does `fx.CFG = import 04a`), and 04w relies on 04a being safe to import without `etl_helpers`' heavy deps (requests/thefuzz) or `DATA`/`REVIEW` mkdir side-effects. Overlap is just 2 table-name strings + `data_dir` + a path-anchoring idiom; folding it in would break the lean→heavy boundary. All five `etl_helpers.LeagueConfig` table-name handles are live (`fact_name`/`crosswalk_name`/`nfl_players_name`/`rookie_prospect_name` via 04z+05a, `alias_name` via 03y).

## Fuzzy Match Workflow (notebook 02c)

1. `clean_player_name()` → exact match against `dim_rookie_prospect`
2. `thefuzz.fuzz.token_sort_ratio`:
   - ≥ 90 → auto-link
   - 70–89 → write to `review_fuzzy_matches.csv` for human review
   - < 70 → new prospect, add to `dim_rookie_prospect`
3. **Consult `dim_player_alias` first** (key `(name_clean, position_raw)`): already-decided → skip review entirely. Only genuinely-undecided names reach fuzzy.
4. User fills `action` column (`match` or `new`), runs `apply_review_decisions()` (03z) → appends decisions to `dim_player_alias`
5. Review file (in `data/review/`) archived as `review_fuzzy_matches.applied_YYYYMMDD.csv` — only when every `action` is filled
6. `ingest_ranking_source` folds alias into `name_to_key` so matched name-variants attribute their ranking to the resolved `player_key` (else silently dropped)

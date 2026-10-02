# nflreadpy in-season API surface

Research for #84 (child of map #71, nflverse in-season stats + injuries).
Probed 2026-09-26 (Sat, NFL Week 3 in progress) against the repo `.venv`.

## TL;DR

- **Version**: `nflreadpy 0.1.5` installed, and that is also the latest release
  (2025-11-19). `polars 1.42.1`, `pyarrow 24.0.0`. `requirements.txt` pins
  `nflreadpy>=0.1`, which is fine.
- **2026 data is live now** for all four loaders: stats and snaps through Week 3
  TNF, injuries through the Week 3 report.
- **`load_player_stats` takes no `stat_type` argument.** One wide 150-column
  frame holds offense, **IDP (`def_*`)**, kicking and punting together.
  `summary_level` ∈ `week | reg | post | reg+post`.
- **IDs**: stats `player_id`, injuries `gsis_id` and rosters `gsis_id` are all
  GSIS (`00-00xxxxx`). **Snap counts carry only `pfr_player_id`**, so they need a
  crosswalk.
- **A stats row does not mean a game played.** About 14% of skill/IDP players who
  took a snap in 2026 have no `load_player_stats` row. They played but recorded no
  stat. Snaps are the better GP source.

## Loader reference (as installed, 0.1.5)

Every loader returns a **Polars** DataFrame. `seasons=None` means the current
season, `True` means all seasons, and an int or list selects specific seasons.
`get_current_season()` returns 2026 and `get_current_week()` returns 3.

| Loader | Signature | 2026 rows / max week | Player ID | Natural key (verified unique) |
|---|---|---|---|---|
| `load_player_stats` | `(seasons, summary_level='week')` | 2,294 / wk 3 (1118, 1107, 69) | `player_id` (GSIS) | `player_id + game_id` (also `player_id + season + week`), 0 dups |
| `load_injuries` | `(seasons)`, 2009 to current | 733 / wk 3 (182, 251, 300) | `gsis_id` | `gsis_id + season + week`, 0 dups, 0 null ids |
| `load_schedules` | `(seasons=True)` | 272 games; 33 completed | `game_id` | `game_id` |
| `load_snap_counts` | `(seasons)`, 2012 onward | 3,086 / wk 3 (1492, 1502, 92) | `pfr_player_id` only | `pfr_player_id + game_id` |
| `load_rosters_weekly` | `(seasons)` | 8,036 / wk 3 | `gsis_id` (+ `pfr_id`, `sleeper_id`, `espn_id`, …) | `gsis_id + season + week` (4 null gsis) |

### `load_player_stats`

- **Columns (week level, 150)**: `player_id, player_name, player_display_name,
  position, position_group, headshot_url, season, week, season_type, game_id,
  team, opponent_team`, then passing, rushing, receiving, `special_teams_tds`,
  **`def_tackles_solo, def_tackles_with_assist, def_tackle_assists,
  def_tackles_for_loss(_yards), def_fumbles_forced, def_sacks(_yards),
  def_qb_hits, def_interceptions(_yards), def_pass_defended, def_tds,
  def_fumbles, def_safeties, def_*_blocks, def_2pt_*`**, `fumble_recovery_*`,
  returns, `fg_*`, `pat_*`, `pt_*`, `fantasy_points, fantasy_points_ppr`.
- **IDP is present.** 2026 rows by `position_group`: DB 489, LB 397, DL 389, WR
  313, RB 197, TE 158, SPEC 142, OL 128, QB 78.
- **`reg` / `post` / `reg+post`** drop `week`, `game_id` and `opponent_team`, and
  add `games` (count of that player's stat rows) and `recent_team`.
- **Gotcha: null-player rows.** Each week has one row with `player_id` = null
  (team-level remainder, all zeros). Filter `player_id.is_not_null()` before
  keying.
- **Gotcha: `fantasy_points` / `_ppr` use nflverse standard scoring**, not the
  league's IDP scoring. The map scopes Fantrax scoring reconciliation out.
- Internally the loader fetches release asset
  `nflverse-data/stats_player/stats_player_{week|reg|post|regpost}_{season}`.
  Source: installed package source (`nflreadpy.load_stats._load_stats`).

### `load_injuries`

- 16 columns: `season, season_type, game_type, team, week, gsis_id, position,
  full_name, first_name, last_name, report_primary_injury,
  report_secondary_injury, report_status, practice_primary_injury,
  practice_secondary_injury, practice_status`.
- `report_status` values are `Out`, `Doubtful`, `Questionable`, or **null**. Null
  means the player was listed on the practice report but carried no game-status
  designation (62% of 2026 rows). `practice_status` holds
  `Full / Limited / Did Not Participate` in long-form strings.
- **Only players on the NFL injury report appear.** Healthy players, IR, PUP and
  NFI are absent. IR and roster status come from `load_rosters_weekly.status`
  (`ACT, RES, INA, DEV, CUT, RET, EXE`) and `status_description_abbr` (e.g.
  `R01`).
- There is one row per week (the final report of that week), not one per
  practice day.
- The loader validates seasons in the range 2009 to `get_current_season()` and
  raises `ValueError` for any season outside it.

### `load_snap_counts`

- 16 columns: `game_id, pfr_game_id, season, game_type, week, player,
  pfr_player_id, position, team, opponent, offense_snaps, offense_pct,
  defense_snaps, defense_pct, st_snaps, st_pct`. The data comes from PFR.
- **No gsis_id.** Mapping `pfr_player_id` through `load_rosters_weekly.pfr_id`
  (or `load_ff_playerids.pfr_id`, same result) left **589 of 3,086 rows
  unmapped**. Almost all of them are OL/LS (T 157, OL 144, G 120, C 89, LS 55),
  plus 14 skill/IDP rows. Those positions are irrelevant to fantasy, so the gap
  is acceptable. Log the unmapped rows rather than failing.

### `load_schedules`

- `game_id, season, game_type, week, gameday, weekday, gametime, away_team,
  away_score, home_team, home_score, result, …` plus IDs (`gsis, pfr, espn`),
  betting lines and venue. The schedule is enough for a game or week dimension:
  `result` is not null once a game completes.

## Publish timing

From the nflverse data schedule page
(<https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html>):

| Dataset | Cadence (in season) | Observed 2026 asset `updated_at` (UTC) |
|---|---|---|
| Player stats | Nightly after each game day, plus extra runs on game days | `stats_player_week_2026` 2026-09-26 13:47 (Sat) |
| Injuries | Daily 07:00 UTC | `injuries_2026` 2026-09-26 12:11 |
| Snap counts | 00, 06, 12, 18 UTC daily | `snap_counts_2026` 2026-09-25 11:01 |
| Rosters | Daily 07:00 UTC | `roster_weekly_2026` 2026-09-26 12:13 |
| Schedules | Every 5 min | n/a |

(Observed timestamps come from
`gh api repos/nflverse/nflverse-data/releases/tags/<tag>`. The actual job runs
lag the nominal cron by several hours.)

**Practical implication**: a **Tuesday-morning (US) weekly run** sees every game
through Monday Night Football in stats and snaps. The injury feed changes daily
Wed–Sat as practice reports land, so an injury snapshot is only "the week's
status" once it is taken on Saturday or later. Otherwise the ETL just
re-replaces the current week's partition on each run, which the
replace-by-(season, week) pattern already handles.

## Polars to pandas

- `df.to_pandas()` needs `pyarrow`, which is already in `requirements.txt`. 05a
  already uses this pattern. Int32 columns come across as `int32` and strings
  as `object`. Integer columns that contain nulls become `float64`, and null
  strings become `None`. Stat columns are 0-filled, not null, but the
  injury text fields do contain nulls. Use `to_pandas(use_pyarrow_extension_array=True)` only if nullable ints
  matter.
- **Select and filter in Polars before `.to_pandas()`.** The frame is 150
  columns wide, and projecting down to about 8 columns first is cheap.
- Caching: the default `NFLREADPY_CACHE=memory` is fine for a scheduled script.
  Set `NFLREADPY_CACHE=filesystem` plus `NFLREADPY_CACHE_DIR` only for
  interactive iteration. `NFLREADPY_VERBOSE=False` silences download logs.
  Source: <https://nflreadpy.nflverse.com/api/configuration/>.

## Existing-code finding: 05a undercounts GP

`notebooks/05a_startup_draft_board.py::load_career_games` counts **stats rows**
per gsis_id as games played. For 2026 weeks 1–3, **356 of 2,497 mapped snap rows
(14%) have no stats row**: LB 70, TE 66, CB 48, S 37, WR 30, and so on. These are
special-teams-only players or players with 0 stats. Minors eligibility (GP ≤ 19)
is exactly the population of young depth players this undercounts, so any
nflverse GP cross-check should derive GP from **snap counts (any
offense, defense or ST snap > 0)**, not from stats rows. Fixing 05a is outside
this ticket's scope and belongs to a separate ticket.

## Recommended minimal column set

This follows the #85 direction: fantasy scoring is raw points, so per-player
stat detail stays minimal.

**Injuries (`fact_nfl_season_injuries`, key `gsis_id + season + week`)**, taken
straight from `load_injuries`:
`gsis_id, season, week, game_type, team, report_status,
report_primary_injury, practice_status`. Optionally add the IR state from
`load_rosters_weekly.status` (joined on `gsis_id + season + week`) so that
"Out" versus "on IR" is distinguishable.

**Weekly participation (`fact_nfl_player_stats` or a slimmer rename, key
`gsis_id + game_id`)**, built from snap counts mapped to gsis, left-joined to
stats:
`gsis_id, season, week, game_id, team, offense_snaps, defense_snaps, st_snaps`.
Here `played = (offense+defense+st snaps) > 0` is derivable, so do not store it.
GP = count of rows with `played` true. Offense and defense snap percentages are
optional, since they can be derived from team totals in DAX if ever needed.

**Optional: `fantasy_points_ppr`** from `load_player_stats`, useful only as a
sanity signal. It uses the wrong scoring for this IDP league, and scoring
reconciliation is out of scope. Leave it out unless #85 says otherwise.

**Do not carry**: the 140+ stat columns, `headshot_url`, names or positions
(these belong on `dim_nfl_players`), and schedule betting or venue columns.

**Key decision for #85**: the `player_id + game_id` key in data-model.md still
works (`player_id` is gsis). Renaming it to `gsis_id` matches the repo identity
rule. A `dim_nfl_game` is not needed for GP or injuries: `season + week` on
the facts is enough, and `load_schedules` can back one later if a
game-level view is ever wanted.

## Sources

- nflverse data schedule: <https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html>
- nflreadpy docs: <https://nflreadpy.nflverse.com/> · configuration: <https://nflreadpy.nflverse.com/api/configuration/>
- Data dictionaries (linked from the loader docstrings):
  <https://nflreadr.nflverse.com/articles/dictionary_player_stats.html>,
  <https://nflreadr.nflverse.com/articles/dictionary_injuries.html>,
  <https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html>,
  <https://nflreadr.nflverse.com/articles/dictionary_schedules.html>
- nflreadpy release: <https://github.com/nflverse/nflreadpy/releases> (v0.1.5 latest)
- Live probe: repo `.venv`, `load_*([2026])` calls on 2026-09-26.

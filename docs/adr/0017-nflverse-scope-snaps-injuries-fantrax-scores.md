# nflverse supplies only snaps and injuries; Fantrax supplies points and games played

- Status: accepted. Designed through HITL grilling on 2026-09-27 ([#85](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/85)); not yet built (→ [#86](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/86)).
- Date: 2026-09-27
- Scope:
  - the deferred "In-Season Tables" spec (`fact_nfl_player_stats`, `fact_nfl_season_injuries`)
  - the nflverse map (#71) and Period Scoring (#81)
  - `notebooks/05a` career games played

## Context

- The deferred spec planned a weekly `fact_nfl_player_stats`. `load_player_stats` returns one wide frame of about 150 columns (#84).
- The league scores raw fantasy points, and Fantrax is the scoring authority. Nothing reads per-stat columns.
- The owner wants, per player: games played, points per Scoring Period, year-to-date points, snaps by Unit, and points by Unit.
- Fantrax already covers the points side. Checked live on 2026-09-27:
  - `getLiveScoringStats {period, playerViewType:'2'}` returns Starters and Bench.
  - Each player has one `{scipId, sv, av, fpts}` per stat, and `fpts` is already weighted by position.
  - `scipId` is `<group>#<categoryId>#<pos>`, with `1010` = offense and `1020` = defense. Category names come from the public `getLeagueInfo` → `scoringCategorySettings`.
- Games played and year-to-date points come from `getPlayerStats` (04a).
- Snap counts per Unit exist only in nflverse.
- CONTEXT.md keys every in-season fact by (season, Scoring Period). NFL weeks and Scoring Periods don't map one-to-one.

## Decision

1. **No nflverse stats table.** `fact_nfl_player_stats` is dropped. Points, points by Unit and games played come from Fantrax, so the numbers always match what the league scored.
2. **Unit tagging.** Special Teams = Return Yards (`3218`) and Blocked Kicks (`256g`). Every other stat takes its Fantrax group. Period Scoring by Unit is modelled in #81.
3. **Two nflverse facts, current season only:**
   - `fact_nfl_snap_counts`, keyed `(gsis_id, game_id)`: NFL `season`, `week`, `team`, and offense/defense/special-teams snaps and pct. `pfr_player_id` maps to gsis through `load_rosters_weekly.pfr_id`. Unmapped rows (almost all OL/LS, who can't be rostered) are dropped, and the count is printed.
   - `fact_nfl_injuries`, keyed `(gsis_id, season, week)`: `game_type`, `team`, `report_status`, `report_primary_injury`, `practice_status`.
4. **Grain.** Both facts keep their native NFL grain and carry a stamped `period`. It comes from the game date, or for injuries the week's game date, checked against `getLeagueInfo.scoringPeriods`. Joins to Period Scoring use `(season, period, player)`.
5. **Lifecycle.** Each run replaces the current season. These facts are **not** Update-Sets: they have no freeze and no Drift, and nflverse corrections simply land. Fantrax Period Scoring keeps the Update-Set lifecycle (ADR-0015).
6. `05a` counts career games played as snaps > 0 from its own pull. The fact is not backfilled with earlier seasons.

## Consequences

- #86 builds the two facts and needs a `scoringPeriods` date lookup. It no longer builds a stats table.
- Points by Unit for free agents are not covered, because live scoring holds only rostered players. #79 confirms whether IR and Minors appear under BENCH.
- `mouserat_trade-bud`'s `injury_tolerance` gets a data source.
- Per-stat NFL detail (targets, yards, tackles outside league scoring) isn't stored. It can be re-pulled whenever a need appears.

## Alternatives considered

- **Keep the wide nflverse stats table.** Rejected: no consumer, and it duplicates Fantrax.
- **Score nflverse or Fantrax stat counts with our own copy of the rules.** Rejected: it re-implements position-weighted scoring that Fantrax already applies per stat.
- **Roll snaps up to the Scoring Period.** Rejected: it loses per-game detail, and playoff periods don't map one-to-one.
- **Treat these facts as Update-Sets.** Rejected: nflverse is external and can always be re-pulled. Freezing it only adds Drift noise.
- **Backfill career snaps.** Deferred by the owner: current season only.

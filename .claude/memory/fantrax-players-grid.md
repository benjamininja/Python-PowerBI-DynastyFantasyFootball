---
name: fantrax-players-grid
description: getDraftRanks is retired post-draft; the Players grid (getPlayerStats) is the live Fantrax universe source, and the old board truncated offense 3-5x
metadata:
  type: project
---

# Fantrax: the draft board is dead, the Players grid is live (2026-07-31)

`getDraftRanks` **stopped working the moment the startup draft completed** — it
now returns only *"The draft has already been completed, thus you can no longer
access this page"*. `notebooks/04a_fantrax_weekly_scrape.py::main_scrape` /
`extract_ranked_board` / `board_to_frame` are retained but **RETIRED**; the CLI
default is now `main_snapshot()`.

The live replacement is `getPlayerStats` (the Players grid) — a *different*
method, unaffected by the draft ending. `FantraxScraper.fetch_player_stats` and
`player_stats_to_frame` already existed and were already symmetric; Stage 0 was
a repoint, not new scraping code. `04a` gained `players_ref_url`,
`grid_timeframe`, `snapshot_player_stats()`, `main_snapshot()`,
`MIN_ACTIVE_BY_POS` and `check_universe()` (raises on a short pull).

## The asymmetry that made the old board unusable

`extract_ranked_board` filtered the two sides of the ball differently:

- offense survived only if `statsAll[4]` (Fantrax **global** ADP) was non-null —
  and that ADP is offense-only redraft demand, ~282 players league-wide;
- IDP survived on `teamShortName != '(N/A)'` — the full active-roster universe.

So `fact_fantrax_adp`'s 1,656 rows were 1,374 IDP + 282 offense. Measured
against the Players grid, active-roster only: QB 39 -> 118, RB 90 -> 209,
WR 116 -> 390, **TE 38 -> 206 (5.4x)**, IDP unchanged at 1.0x. Any
scarcity/replacement math built on the old board bakes in this artifact.

## Two partitions now live in `fact_fantrax_adp`

- `2026/PRE`, captured 2026-07-31, 2265 rows — Players grid, full universe,
  gsis 98.6% resolved. **`adp` and `percent_drafted` are all null**: the grid
  serves no ADP column.
- `2026/DRAFT`, captured 2026-06-09, 1656 rows — the final draft board,
  recovered from git and relabelled. It preserves the 283 ADP values, **the last
  that will ever exist for this league**.

Because of that, `discord_bot/adp.py` and `discord_bot/player.py` must select
the newest capture **that carries ADP**, not simply the newest capture — an
unconditional `capture_date.max()` sorts the whole board on an all-null column.
Both were patched; keep the pattern if a third consumer appears.

Related: [[trade-bud-valuation]], [[data-model]].

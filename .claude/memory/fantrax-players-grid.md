---
name: fantrax-players-grid
description: getDraftRanks is retired post-draft; the Players grid (getPlayerStats) is the live Fantrax universe source, and the old board truncated offense 3-5x; Rk is served per request timeframe (BY_DATE has none, so overall_rank is derived there)
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

## Rk depends on the request timeframe (2026-10-03)

`getPlayerStats` serves Fantrax's Rk in two places: `statsTable[].scorer.rank`
and a first header column (`shortName` `Rk`, key `rankOv`, index 0). **A
`BY_DATE` request gets neither.** The split is by timeframe, not by preseason
vs in-season.

| Raw capture (`data/raw/fantrax_playerstats_*`) | Built by | `seasonOrProjection` | Rk | Header cols | `statsTable` rows |
|---|---|---|---|---|---|
| `2025_YTD` | season-actuals backfill | `SEASON_23j_YEAR_TO_DATE` | yes | 27 (incl. `%D`, `ADP`) | 8,651 |
| `2026_wkPRE` | weekly snapshot, preseason | `PROJECTION_0_23l_SEASON` | yes | 26 | 8,633 |
| `2026_01`, `2026_02` | `--rebuild-week` | `SEASON_23l_BY_DATE` | **no** | 25 | 6,213 |

- **What 04a does**: `player_stats_to_frame` keeps `scorer.rank` when any row
  of the pull has one. Otherwise it ranks the whole pool (before the
  active-roster filter) by that pull's FPts via `_fpts_rank`: FPts > 0 only,
  ties in response order, zero-FPts null. The switch is all-or-nothing per
  pull, so one partition never mixes the two scales.
- **The derived rank is a stand-in, not Fantrax's Rk.** Against PRE's served
  rank it is exact for 98.5% of scored players (every miss inside a tied-FPts
  block, max difference 2). Against 2025 YTD it is exact for only 40%: tie
  blocks are larger, and a dual-eligible player has one Fantrax rank but
  different FPts on the offense and defense pages. Fantrax also ranks
  zero-FPts players in an alphabetical tail; the derived rank leaves them
  null.
- **Which partition holds which**: `2025/YTD` and `2026/PRE` = served.
  `2026/01` and `2026/02` = derived (857 and 1,078 of 1,956 rows; filled
  2026-10-03 by offline replay of the raw captures, PR #122). `2026/DRAFT` =
  the retired board's own computed rank (1,250 of 1,656).
- **Unconfirmed**: that the in-season `YEAR_TO_DATE` weekly pull still serves
  Rk. No weekly capture exists after week 02; check `scorer.rank` on the
  first one.
- **Fixtures**: `playerstats_page.json` is the `BY_DATE` shape (no rank);
  `playerstats_page_ranked.json` is the 2025 YTD shape (served rank, `Rk` at
  header index 0).
- **Briefing `fantrax-payload-analyst`**: say which request built each file
  (the table above). Without that, its first report on this bug blamed
  "in-season" for what was a `BY_DATE` effect.

Related: [[trade-bud-valuation]], [[data-model]].

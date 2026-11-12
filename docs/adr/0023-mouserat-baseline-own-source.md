# MouseRatPresents_Baseline is a source of our own: nflverse counts scored with Fantrax's rules

- Status: accepted. Decided in the owner grill [#432](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/432) (rounds 1 to 5, 2026-11-07 and 2026-11-08; design record issuecomment-6724713427), and confirmed by the owner there. Three further owner answers of 2026-11-09 are in decisions 3, 4, 10 and 11. Built in [#473](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/473).
- Date: 2026-11-08
- Amends: [ADR-0017](0017-nflverse-scope-snaps-injuries-fantrax-scores.md) (its 2026-11-08 amendment, below). No other decision is reversed.
- Scope:
  - `notebooks/04p_fantrax_league_info.py` and the rules table
  - the category-group table, the scored history, the player-season table and the baseline steps
  - `fact_dynasty_ranking_metrics`, `fact_rookie_rankings` and `dim_dynasty_metric` (a new source's rows)
  - trade-bud's fallback for players no board covers; the bot; Power BI
  - the yearly yardstick page under `docs/`
  - `docs/sources.yml` (nflverse, CollegeFootballData)
  - `CONTEXT.md` (Baseline, Scoring Category, Category Group, Yardstick)

## Context

- PFF, FantasyPros and KTC are rejected (#402, #415, #423). The league needs player values it may publish.
- An IDP score built from nflverse's defensive stats (CC BY 4.0) ranks as well as DraftSharks on the same players, and better at LB (#422). It has no rookies, no age curve and no view of a role change.
- No board covers most IDP. Trade-bud orders those players by Fantrax points, and the bot says it has no IDP source.
- The league's scoring lives in Fantrax. `getLeagueInfo.scoringSystem`, which 04p already fetches with no login, holds each category's points by position (for example solo tackles 3.5 for DL and less by default).
- ADR-0017 rejected scoring stat counts with our own copy of the rules, and stored no per-stat detail.

## Decision

1. **A source of our own.** `MouseRatPresents_Baseline` is a `source_name` in `fact_dynasty_ranking_metrics` and `fact_rookie_rankings`. Its metric keys are prefixed `mrp_`, and each belongs to it alone in `dim_dynasty_metric`. Its licence line is CC BY 4.0, credit to nflverse; the first build carries no share-alike data.
2. **Rules are read, never typed.** 04p writes `getLeagueInfo.scoringSystem` to a rules table on every run. The baseline scores nflverse counts with that table. A rule change flows through and rescores the stored counts.
3. **Fantrax stays the authority for league points.** A drift check compares our scored points with Fantrax's in the seasons both cover, against a bar fixed before it is measured (owner, 2026-11-09, "Looser bar"):
   - a compared player passes when the difference is at most 1 point plus 5% of Fantrax's figure;
   - the check fails when fewer than 90% of compared players pass in either season, or when any Fantrax position's summed points differ by more than 2%.

   Drift past the bar fails the baseline's step. The bar is measured against and never loosened.
4. **Scored history** is two tables (owner, 2026-11-09, "Second small table"):
   - one row per player, season and scoring category: the count and the points it earned, for the 15 most recent full seasons plus the current one, in Postgres and the snapshot. Only the league's scored categories are kept;
   - one row per player and season: games, position, the position's source and the rules season used. Every player and season in the first table has a row in this one.
5. **A transformer table assigns each category to one of seven groups:** Passing; Rushing; Receiving; Special teams; Defense, tackles; Defense, big plays; Other. A new category adds a row, not code.
6. **Position of record** is Fantrax's league position, with no override. A past player no longer in Fantrax takes nflverse's position through `dim_position`.
7. **Projection.** A weighted average of the last three seasons' points per game (the current season counted by its games), shrunk toward the position's average when games are few (a second-year player toward his rookie value), times our own age curve (the delta method, per position). Season weights and shrinkage are fit by back-test on the yardstick. The age curve stays, position by position, only if it beats no age adjustment there.
8. **Output per player:** projected points per game for each of the next three seasons, a positional rank on next season, and his share of last season's points by group. There is no blended single value.
9. **Rookies.** Draft pick and position first; combine tests and CollegeFootballData college production as secondary terms shrunk toward zero, kept only if they improve the fit on held-out past classes. A missing combine test counts as the position's average. Values compute once the draft is in nflverse's draft data. A drafted rookie gets a `post_draft` row in `fact_rookie_rankings` and a projection in `fact_dynasty_ranking_metrics` by `gsis_id`.
10. **CollegeFootballData is for derived outputs only.** Its raw data stays private in Postgres and never enters the snapshot. Its key lives only in a GitHub secret. The yearly pull runs in a scheduled workflow (owner, 2026-11-09, "Scheduled workflow"): see decision 11.
11. **Cadence.**
    - A Daily step recomputes only when nflverse's season stats have changed.
    - The age curve and the season weights refit once a year, after the final week.
    - The CollegeFootballData pull and the rookie refit run in a GitHub workflow on a daily schedule from 20 April to 31 May, also startable by hand. It checks whether the new class is in nflverse's draft data, runs once that year when it is (the pull, then the fit), and then idles. It writes only to Postgres; the fit reaches the snapshot through the Daily Run's export, and the workflow adds no merge path. Agents never start it.
12. **Readers.** Trade-bud's fallback for players no board covers uses the baseline's projected points. The bot and Power BI show it beside DraftSharks. Joining trade-bud's stance boards waits for its first yardstick result.
13. **The yardstick.** Lists dated before week 1 are judged against that season's Fantrax points per game by Fantrax position, over players with 8+ games: Spearman's rho within each position, and the hits of each list's top 12 and top 24. Next season now; three seasons once the data exists. A script writes the results each year to a dated page under `docs/`, merged by PR, and the README links the latest. The first page, after the 2026 final week, judges DraftSharks' 2026-07-31 list beside the baseline's 2026 back-test, built from data through 2025 and labelled as a back-test.

## Alternatives considered

- **A copy of the rules in config.** Rejected: hand-copied numbers drift from Fantrax and a rule change would not flow through.
- **Scored points per season only, no per-category counts.** Rejected in round 5: owners want points broken down by kind, and a rule change would need a re-pull.
- **Fantrax's own per-stat points.** Rejected as the base: live scoring holds only rostered players and the current season.
- **Blend the three seasons into one value.** Rejected: trade-bud, the bot and Power BI weight seasons their own way, and the yardstick tests each season.
- **A hand-shaped or published age curve.** Rejected: the delta method compares each player with himself, and the back-test decides whether it stays.
- **ffopportunity expected points, snap share, projections by group, joining the stance boards.** Deferred to later tickets, each added only if it improves the yardstick.

## Consequences

- New tables: the rules table, the category-group table, the scored history, the player-season table, and two yearly fit tables (the fit's figures and the age curve; the rookie fit shares the first).
- The history, player-season and fit tables sit in a new `baseline` Chain, so a drift failure holds only the baseline and not the `nflverse` Chain.
- `docs/sources.yml` gains a feed on the nflverse entry, and CollegeFootballData goes `live`.
- The owner stores a CollegeFootballData API key in a GitHub secret before the rookie build runs.
- The baseline publishes no value before its drift check passes on 2025 and 2026.
- The yardstick page is published every year, whatever it says about the baseline.
- The manager reports the yearly workflow's first run to the owner.

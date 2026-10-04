# Roster State is read from the snapshot; the ledger is provenance; cap math is computed once

- Status: accepted. Designed through HITL grilling on 2026-09-27 ([#82](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/82)); not yet built. **Amended 2026-10-03 ([#81](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/81))**: the in-season fact model, see [the amendment](#amendment-2026-10-03-in-season-fact-model-81).
- Date: 2026-09-27
- Amends:
  - [ADR-0003](0003-event-sourced-roster-transactions.md): the ledger stops being the source of *current rosters*. It stays the source of acquisition history. This ADR also closes ADR-0003's open "`dead_money` schedule by contract year".
  - [ADR-0006](0006-draft-pick-ownership-and-trades.md): Fantrax Roster Moves take a natural key instead of the surrogate monotonic `transaction_id`.
- Scope:
  - `notebooks/02d`, `02e`, `04t`, `04v`
  - `discord_bot/capmath.py` and `mouserat_trade-bud/backend/data_access.py`
  - the Change Poll (ADR-0015)
  - a new `fact_dead_money` and a per-team cap table

## Context

- Today `02e` builds current rosters by **replaying** the ledger: the last event per (team, asset) wins, and drops/trade-aways are removed. One missed or commissioner-reversed event silently corrupts a roster. The roster snapshot (`fact_roster_placement`, from `04v`) is used only to stamp a status, and mismatches are printed and ignored.
- Dead money never works. `02d` emits `drop` events but hardcodes `dead_money = 0`. `capmath.py` prices only `status == "Cut"` rows, and nothing ever sets "Cut".
- `event_seq` is renumbered on every full rebuild, so nothing can reference a move stably.
- trade-bud gets parity with the bot by putting `discord_bot/` on `sys.path` and monkeypatching `capmath.fetch_parquet`.
- Owner direction: **Power BI visuals are deprioritized** (the modeling concepts stay). **trade-bud and the Discord bot must agree** on cap math.

## Decision

1. **Three streams, each with its own source of truth.**
   - **Roster State** (players, Roster Slot, salary, contract) comes from the roster snapshot.
   - **Roster Moves** (claims, drops, trade legs with dates) come from the `04t` log. They feed provenance and Dead Money.
   - **Period Scoring** comes from the per-period roster plus live scoring (`04s`). Team attribution comes from the period roster, not the ledger. The grain is decided in #81. *Decided in the [2026-10-03 amendment](#amendment-2026-10-03-in-season-fact-model-81): `fact_period_scoring`, keyed `(season_id, period, team_key, scorer_id)`, with points by Unit.*
   - Replaying the ledger becomes a **reconciliation check**. Differences from the snapshot go to a `review_*` queue.
2. **Roster Slot** is Starter / Bench / IR / Minors, mapped from Fantrax `statusId` (Active → Starter, Reserve → Bench). The NFL injury designation is a separate player attribute.
3. **Snapshot source.** When the Change Poll detects a change, it persists the public `getTeamRosters` it just hashed. That needs no login. This holds **only if #79 confirms** the public payload carries all four slots plus salary and contract. Otherwise the source is the authed `getTeamRosterInfo`.
4. **History.** One current Roster State, overwritten on each change, plus one snapshot per Scoring Period that follows the Update-Set lifecycle (ADR-0015). A closed snapshot is frozen, and later differences raise Drift. *Amended 2026-10-03 (decisions 3–4 [below](#amendment-2026-10-03-in-season-fact-model-81)): the current Roster State is `fact_fantasy_teams`, kept all year; the per-period snapshots are `fact_roster_state`, regular-season periods only.*
5. **Dead Money is its own fact** (`fact_dead_money`), derived from drops. It has one row per guaranteed-contract drop × charged contract year, charged to the dropping team, with the drop date.
   - **Schedule: the rest of the contract, by year.** Each remaining guaranteed contract year charges its own `cap_hit_pct × contract_value` in its own season. A 1st-year drop costs .50 now and .40 next season. A 2nd-year drop costs .40. A 3rd-year drop costs 0.
   - The contract at the time of the drop is taken from the last Roster State before it.
   - If the same team re-claims the player, the Dead Money stands and the claim starts fresh terms. A commissioner-reversed drop disappears from the log, so it never produces Dead Money.
6. **Move identity** is the natural key `(txSetId, scorer_id, team_key, event_type)`. `event_seq` is a sort order only. Startup-draft rows keep their ADR-0004 key.
7. **Cadence.** Each run pulls the whole season from `04t` (the volume is small, and a full pull catches reversals), then runs `02d` and then Dead Money. This happens on **every debounced Change Poll trigger**, after the snapshot is saved, and again on the daily run. If spike #92 shows that frequent logins get challenged, fall back to the daily run only.
8. **Cap math is computed once, in the ETL.** The cap functions move out of `discord_bot/` into a shared module that the ETL calls. The ETL publishes:
   - `fact_fantasy_teams`: the snapshot rows plus `acquired_method` and date from the latest Roster Move into that team. *Per the [2026-10-03 amendment](#amendment-2026-10-03-in-season-fact-model-81), it is the current Roster State all year, and `roster_status` becomes `roster_slot`.*
   - a per-team × season cap table: current and next-year salary, Dead Money, and cap room.

   The bot and trade-bud read those numbers. trade-bud's what-if trades only add and subtract cap hits on the client. A rostered player with no matching move gets `acquired_method = 'unknown'` and a `review_*` row, never a guessed contract. DAX parity is not required.

## Alternatives considered

- **Keep ledger replay as the source of rosters.** Rejected: it is fragile to missed and reversed events, and the snapshot already exists. ADR-0003 rejected sourcing rosters from the roster page because no roster existed during the startup draft. That reason no longer applies in season.
- **Snapshot only, no ledger.** Rejected: it loses how and when players were acquired, and Dead Money.
- **Incremental (since-date) `04t` pull.** Rejected: it needs watermark state, and it cannot see a reversed transaction vanish.
- **Synthetic "Cut" rows in `fact_fantasy_teams`.** Rejected: it mixes rows derived from the ledger into a snapshot-truth table, and a dropped player can be on another roster within minutes.
- **Dead Money in the current season only**, or **the whole remainder charged at once.** Rejected in favour of the per-year schedule, which matches the league's current-year and next-year design.
- **A surrogate `transaction_id`** (ADR-0006). Rejected for Fantrax moves: it needs a persisted lookup and a rule for moves that vanish. `txSetId` is already stable.
- **A shared module computed live in each app.** Rejected: the math would still run in two places at runtime.

## Consequences

- `02e` becomes "snapshot + provenance + reconciliation", no longer a replay projection.
- `capmath.py`'s `remaining_cap_next_yr` must include next-season Dead Money. The trade-bud monkeypatch goes away.
- `04t` joins `run_pipeline.py` (build #93). The Change Poll now writes Roster State as well as triggering.
- #79 must confirm the public roster fields, including Roster Slot. #81 attributes Period Scoring from the period roster.
- **Build acceptance:**
  - Replay and snapshot differ by 0 rows on a quiet day.
  - A test 1st-year guaranteed drop yields two Dead Money rows (.50 and .40).
  - The bot and trade-bud show identical cap room from the published cap table.

## Amendment 2026-10-03: in-season fact model (#81)

- Amends decisions 1 (the Period Scoring grain), 4 (where current and per-period Roster State live) and 8 (`fact_fantasy_teams`).
- Designed through HITL grilling on 2026-10-03 ([#81](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/81)). Being built in stages: decisions 2, 12 and 14 are built (#117's first PR); decision 3's table is loaded but not yet read, and `fact_roster_placement` is not yet retired (#117's second PR); the rest are not yet.
- Scope:
  - new tables `dim_scoring_period`, `fact_roster_state`, `fact_period_scoring`, `fact_matchup`, `fact_standings`
  - `dim_division` (its source moves to Fantrax) and `fact_fantasy_teams.roster_status`
  - retires `fact_roster_placement`; touches `02d`, `02e`, `04s`, `04v`
  - `docs/data_model.yml` (entries land with the builds, because the registry check needs each table's parquet)

### Context

- #81 asked for the grain and naming of a matchup/score fact, a standings snapshot per period and a minimal player-week snapshot.
  - The owner's 2026-09-26 direction: raw points; few player contributions (Roster Slot, contract, week and year-to-date points, age); no per-stat breakdown.
  - [ADR-0017](0017-nflverse-scope-snaps-injuries-fantrax-scores.md) (2026-09-27) then asked for points by Unit.
- Verified from the payloads ([#79 findings](../research/inseason-schema-extraction.md), plus checks on 2026-10-03):
  - Public `getTeamRosters?period=N` carries slot, salary and contract on every row and returns real past periods. It has no age and no eligibility.
  - `getLiveScoringStats {period, playerViewType:'2'}` gives every rostered player's points under `ACTIVE` and `BENCH`, with per-stat `fpts`.
  - `allEventsFinished` was true for final periods 1 and 2, and false for period 3 in progress.
  - Skipping the `_1010`/`_1020` group-total keys, the Starters' points sum to `totalFpts` to 0.01 for all 28 teams in period 1.
  - The schedule has 12 regular-season weeks of 14 matchups. Every team plays once a week, never across Conferences. There is no matchup id and no playoff week.
  - Standings as of a period carry a league-wide rank plus W, L, T, Win%, Div, GB, Salary Remaining, FPtsF, FPtsA, Streak and % Playoffs.
  - `dim_nfl_players.birth_date` covers every rostered player with a `gsis_id`.

### Decision

1. **Points by Unit, not per stat.**
   - `fact_period_scoring` stores `fpts` (Fantrax's player total) and `fpts_offense`, `fpts_defense` and `fpts_special_teams`, summed from the per-stat `fpts` by Unit (ADR-0017 decision 2).
   - Per-stat values are not kept.
   - A Gate check requires the three Units to sum to `fpts`, to 0.01.
2. **`dim_scoring_period`**, keyed `(season_id, period)`, from public `getLeagueInfo.scoringPeriods`.
   - Columns: `start_date`, `end_date`, `is_playoff`, plus the Update-Set state (decision 14).
   - It lists all 17 periods. `is_playoff` marks every period after the last scheduled week.
   - Every in-season fact keys on `season_id` + `period`. #86 stamps nflverse rows from this dim.
   - *Built in #117 (`04p_fantrax_league_info.py`), with two more columns: `start_at` and `end_at`, the exact bounds Fantrax serves, stored in UTC. Periods turn over on a Thursday at 20:15 Eastern, so a period's `end_date` equals the next period's `start_date`; the dates are days on the Eastern clock and cannot place an instant in a period alone. `is_playoff` is true from `playoffs.firstPlayoffPeriod` on.*
3. **`fact_roster_state`**, keyed `(season_id, period, team_key, scorer_id)`, from public `getTeamRosters?period=N`.
   - Columns: `roster_slot` (Starter / Bench / IR / Minors), `salary`, `contract_id`.
   - One Roster State per regular-season Scoring Period (1–12).
   - It **retires `fact_roster_placement`**. `02d` reads it for asset minting and for the contract at the time of a move ([ADR-0019](0019-minor-is-a-pre-1st-contract-stage.md) decision 6). `04v` keeps only `fact_minor_eligibility`.
   - *Table built in #117 (`04r_fantrax_roster_state.py`), with one more column: `capture_date`, the day on the league's Eastern clock the period was last read. A period that has ended shows its final roster; the period in play shows the roster on that day, so a reader takes a period's day as the earlier of its `end_date` and its `capture_date` (owner's decision, 2026-10-03). Each run re-reads every period that has started and is not `closed`, and replaces it whole. Fantrax answers a request for a future period with the current roster under the future number, so a period is read only when the calendar and Fantrax both say it has started.*
   - *The preseason salaries are kept (owner's decision, 2026-10-03): `fact_preseason_salary`, keyed `(season_id, team_key, scorer_id)`, holds `salary` and `capture_date` from the one preseason capture, copied once from `fact_roster_placement`. Without it a draft pick or a claim that left its team before period 1 would lose its observed salary. It is frozen, has no writer, and is never read for a contract.*
   - *Not yet done: the retirement itself. `02d`, `02e` and `04e` still read `fact_roster_placement`; #117's last PR moves them.*
4. **The current Roster State is `fact_fantasy_teams`, all year** (decision 8).
   - The Change Poll and the daily run refresh it through the playoffs and the off-season.
   - While a regular-season period is open, its `fact_roster_state` rows mirror the current state. They freeze with the Update-Set.
5. **`fact_period_scoring`**, with the same key as `fact_roster_state`.
   - One row per rostered player with a live-scoring entry, Starters and non-starters alike.
   - A team's score is the sum of its Starter rows.
   - A player with no entry gets no row, not a zero.
6. **Players are identified by `scorer_id` only**, plus `team_key`. `gsis_id` and `player_key` come through `dim_fantrax_crosswalk`, and the #88 dirty-edge check covers orphans.
7. **Age is derived** from `dim_nfl_players.birth_date`, at whatever date a consumer needs. No age column.
8. **No year-to-date columns.**
   - A player's season points and games played come from 04a's YTD row in `fact_fantrax_adp`, which is unchanged.
   - A team's points to date are a sum of `fact_period_scoring`.
9. **`fact_matchup`**, keyed `(season_id, period, team_key)`, from Fantrax's schedule.
   - Columns: `opponent_team_key`, `is_home`, `fpts_for`, `fpts_against`. Each matchup is two mirrored rows.
   - Win, loss and tie are derived from the scores, not stored.
   - A Gate check requires every pair to mirror.
10. **The matchup Close check** (deferred by [ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88), decision 7) passes only if:
    - all 14 matchups are present;
    - each pair mirrors;
    - per team, schedule FPts = live-scoring `totalFpts` = the Starter sum in `fact_period_scoring`, to 0.01.
11. **`fact_standings`**, keyed `(season_id, period, team_key)`, holds only what can't be derived.
    - Columns: `rank` (Fantrax's order and tiebreaks), `playoff_odds`, `salary_remaining`.
    - Records, points, games back and streak are derived from `fact_matchup`.
    - A Review check compares `salary_remaining` with cap room in the cap table (#97).
12. **Division by join.**
    - Facts carry `team_key`. Conference comes from `dim_fantasy_teams`, and the Division name from `dim_division (season_id, conference)`.
    - `dim_division` is loaded from public `getLeagueInfo.teamInfo[].division` instead of the Sheet.
    - A Gate check requires each Fantrax division to map to exactly one Conference.
    - *Built in #117. The check runs in `04p`'s parser, before anything is written: a division in two Conferences, or two divisions in one, fails the step, which holds the Chain. `dim_fantasy_teams.division` is still read from the Sheet by `01c`.*
13. **Playoffs are out of scope.** Periods 13–17 get no Update-Set; no `fact_roster_state`, scoring, matchup or standings rows; and no follow-up ticket.
14. **The Update-Set state lives on `dim_scoring_period`.**
    - Columns: `update_set_state` (open | closing | closed; null for future and playoff periods) and `closed_at`.
    - It is published with the snapshot, so consumers can tell final numbers from provisional ones.
    - *Built in #117 (owner's decision, 2026-10-03): the build writes `open` and `closing` only. The transition to `closed` is coded and tested, but it needs the scoring Close checks, which arrive with #118 and #116; until then no period closes and `closed_at` is null. A period already `closed` stays closed.*
15. **Scoring loads once final.**
    - A period's scoring, matchup and standings rows first load when `allEventsFinished` is true, as its Update-Set enters closing.
    - They refresh through closing, so corrections land, and freeze at closed.
    - An open period has only `fact_roster_state` rows.
16. **`fact_fantasy_teams.roster_status` becomes `roster_slot`**, with Starter / Bench / IR / Minors, the same vocabulary as `fact_roster_state`.
    - It lands in [ADR-0018](0018-supabase-schema-and-rls.md)'s cutover pass (#110), with the capmath, `02e`, PBI `sourceColumn` and DAX cascade.
    - `Minors` is unchanged, so the cap exemption still holds.
17. **Built in two issues under #70.**
    - [#117](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/117) Roster State: decisions 2–4, 12, 14 and the `fact_roster_placement` retirement, with a `cap-ledger-auditor` review.
    - [#118](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/118) Scoring: decisions 1, 5, 9–11, 15, and `04s` sending `playerViewType:'2'`.
    - Wiring: #118 ← #117; #117 ← #113; #93 ← #117; #116 ← #118.

### Alternatives considered

- **Total points only,** or **every stat's `fpts` in a long table.** Rejected: the first drops ADR-0017's Unit split, and the second reverses the no-per-stat direction.
- **Period keys without a dim**, or reusing `season` + capture `week`. Rejected: #86 would need its own period lookup, and capture weeks are not Scoring Periods.
- **Rekeying `fact_roster_placement` in place,** or keeping it beside the new table. Rejected: the name doesn't match Roster State, and two slot sources would need reconciling.
- **Scoring as columns on `fact_roster_state`.** Rejected: two write paths (the poll and authed scoring) would share each row.
- **Starter rows only.** Rejected: non-starter points come free in the same call.
- **Copying `gsis_id` and `player_key` onto each row.** Rejected: closed periods would freeze stale ids.
- **Storing age**, either at period end or as Fantrax's integer. Rejected: a second copy of the dim, or an authed call per period.
- **A running `fpts_ytd`.** Rejected: it is ambiguous between player and team, and a correction would rewrite every later row.
- **One row per matchup (away/home).** Rejected: every per-team question would need an unpivot.
- **A matchup score derived from Starters,** or **a stored result**. Rejected: the first never records Fantrax's official score, and the second is derivable.
- **The full standings row with a reconcile check,** or **no standings table.** Rejected: the first keeps two truths for records, and the second loses Fantrax's order, its playoff odds and the cap cross-check.
- **Division from the Sheet,** or **stamped on each fact row.** Rejected: a manual mirror can lag, and stamping leaves mixed labels after a rename.
- **Deferring the playoff bracket to a capture ticket,** or **modelling playoffs on a guessed shape.** Not chosen: the owner leaves playoffs out entirely.
- **`fact_roster_state` continuing past period 12 as the current state.** Rejected: it would partly reverse leaving playoffs out, and ADR-0016 already gives `fact_fantasy_teams` that role.
- **A regular-season-only period dim.** Rejected: nflverse games in December would have no period.
- **Provisional rows for the open period.** Rejected: live scoring mid-period is badly incomplete, and the coverage Gate would need exceptions.
- **An `ops.update_set` table.** Rejected: consumers couldn't see whether a period is final.
- **Keeping `roster_status`.** Rejected: two vocabularies for one concept.
- **Zero-filling players with no entry.** Rejected: a bye week and a real 0 would look the same.
- **A new ADR.** Rejected by the owner, in favour of this amendment. **One build issue,** or **folding the work into #93/#116.** Rejected: it mixes cap-path changes with new scoring tables.

### Consequences

- `fact_roster_placement` stops being load-bearing: `02e` stamps slots from the current public roster, and `04v` no longer writes slots.
- `04s` must send `playerViewType:'2'` (the [#79 drift table](../research/inseason-schema-extraction.md#drift-against-existing-parsers)).
- The coverage Gate for Period Scoring ([ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88), decision 4) runs from period 1 to the last closed period, at most period 12.
- Playoff points are kept only by Fantrax, and in 04a's year-to-date totals.
- Registry entries and DDL arrive with builds #117 and #118.
- **Still open, harmless under decision 5:**
  - which instant the public per-period snapshot represents;
  - why 15 non-starters had no scoring entry in final period 1.

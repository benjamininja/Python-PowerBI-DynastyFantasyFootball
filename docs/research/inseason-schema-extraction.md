# In-season Fantrax payloads: shapes, IDs, and three open questions settled

Resolves #79 (child of map #70, "In-season Fantrax league flows").
Counted 2026-10-02 by the managing session, with scripts that print counts
and key names only. Sources:

- **Authed captures on disk** — `data/raw/fantrax_inseason_2026_p01..p03.json`
  and `_schedule.json`, written by `04s` on 2026-09-26 (periods 1 and 2
  final, period 3 in progress).
- **Public `fxea/general/getTeamRosters`** for `period=1` and `period=3`,
  fetched 2026-10-02 with no login (after period 3 ended).
- **Public `fxea/general/getLeagueInfo`**, fetched 2026-10-02.
- **One authed `getLiveScoringStats {period: 1, playerViewType: "2"}`**,
  fetched 2026-10-02 with the stored session (read-only, no login).

An earlier agent draft of this ticket reported totals that did not
reconcile (764 roster rows, a `2nd` contract, an IR "public-only" claim).
None of those hold; every number below was recounted from the payloads.

## Gist

1. **The public roster call carries everything Roster State needs.** All
   four Roster Slots, salary and contract are on every row, with no nulls,
   and it matches the authed roster call exactly.
2. **`period=N` returns real past periods in-season.** The preseason finding
   that it is ignored no longer applies.
3. **`playerViewType: "2"` puts Bench, IR and Minors players all under
   `BENCH`.** It is only complete once the period is final.
4. **A `Minor` contract now exists on about a third of roster rows.** It
   tracks minors eligibility, not placement. This contradicts the fact
   ADR-0011 was built on. *Reconciled in
   [ADR-0019](../adr/0019-minor-is-a-pre-1st-contract-stage.md): `Minor` is the
   pre-`1st` contract stage.*
5. **`04v` drops every IR player**, because it treats statusId `"3"` as an
   empty slot. *Fixed in `fix/04v-keep-ir-rows`: IR rows are kept as
   `"Inj Res"`.*

## 1. Public `getTeamRosters`: fields and agreement with the authed call

Row shape, identical on every row: `{id, position, status, salary,
contract: {name, smallId}}`. Nulls in `salary`, `contract`, `position`: 0.

| | Period 1 | Period 3 |
|---|---|---|
| Teams | 28 | 28 |
| Roster rows | 1,069 | 1,099 |
| Distinct player ids | 597 | 615 |
| `ACTIVE` (Starter) | 420 | 420 |
| `RESERVE` (Bench) | 463 | 471 |
| `INJURED_RESERVE` (IR) | 35 | 55 |
| `MINORS` (Minors) | 151 | 153 |

Rows exceed distinct players because each conference has its own player
pool, so one player can be rostered once per conference.

Compared with the authed `getTeamRosterInfo` captures, keyed on
`(teamId, scorerId)`:

| | Period 1 | Period 3 |
|---|---|---|
| Authed rows / public rows | 1,069 / 1,069 | 1,099 / 1,099 |
| In one source only | 0 | 0 |
| Same Roster Slot | 1,069 | 1,041 |
| Same contract | 1,069 | 1,099 |

- The public `id` is the authed `scorerId`, and the public status maps to
  the authed `statusId` as `ACTIVE`=1, `RESERVE`=2, `INJURED_RESERVE`=3,
  `MINORS`=9.
- The 58 slot differences in period 3 are timing: the authed capture was
  taken mid-period (2026-09-26) and the public fetch after the period ended.
  Membership was identical across the two.
- **Not established:** which instant within a period the public snapshot
  represents once the period is over (lock time, or end of period).

**Answer for ADR-0016 decision 3:** yes — the Change Poll can persist the
public call as Roster State with no login.

## 2. Past periods

Public period 1 against public period 3, both fetched 2026-10-02:

- 1,054 `(team, player)` pairs in both; 45 added; 15 removed.
- 228 of the 1,054 changed Roster Slot.
- 0 changed contract; 0 changed salary.

Public period 1 also equals the authed period 1 capture row for row
(section 1), so the past period is the real one, not the current roster
relabelled.

The comment at `02d_fact_roster_transactions.py:496-518` (probed
2026-07-26: "serves CURRENT state regardless of the parameter") was true in
preseason and is now out of date. Its own last paragraph asks for this
re-probe.

## 3. Live scoring: what `BENCH` holds

`getLiveScoringStats {period: 1, playerViewType: "2"}`, period 1 being
final:

| Roster Slot (authed period 1) | Rows | Under `ACTIVE` | Under `BENCH` | Absent |
|---|---|---|---|---|
| Starter (1) | 420 | 420 | 0 | 0 |
| Bench (2) | 463 | 0 | 455 | 8 |
| IR (3) | 35 | 0 | 33 | 2 |
| Minors (9) | 151 | 0 | 146 | 5 |

- Totals: `ACTIVE` 420, `BENCH` 634. No player is in both groups. No entry
  is off the roster.
- The 15 absent non-starters were not investigated. Likely they had no game
  in the period, but that is a guess.
- The default view (what `04s` sends today) returns `ACTIVE` only: 420
  entries for period 1, 419 for period 2.
- **A period in progress is incomplete.** Period 3 held 21 `ACTIVE` entries
  on 2026-09-26 and 310 `ACTIVE` + 464 `BENCH` on 2026-09-27, against 420
  Starters. Players appear as their games start. Period Scoring should be
  captured after the period is final. The payload has an `allEventsFinished`
  key that may serve as the signal; its values were not checked.
- Free agents are absent from this payload (ADR-0017 already notes this).

## 4. A `Minor` contract exists

Contract names across every roster row, both sources agreeing:

| Contract | 2026-07-18 (`fact_roster_placement`) | Period 1 | Period 3 |
|---|---|---|---|
| `1st` | 987 | 631 | 627 |
| `Minor` | 0 | 351 | 349 |
| `FA` | 5 | 87 | 123 |

`Minor` by Roster Slot, period 3: Starter 76, Bench 110, IR 25, Minors 138.
The Minors slot itself holds 138 `Minor`, 14 `FA` and 1 `1st`.

Against Fantrax's own `scorer.minorsEligible` flag (authed, period 1):

| | `Minor` | `FA` | `1st` |
|---|---|---|---|
| Eligible (385) | 349 | 30 | 6 |
| Not eligible (684) | 2 | 57 | 625 |

So `Minor` tracks eligibility closely, not placement: 349 of 351 `Minor`
rows are minors-eligible, and most of them are not in the Minors slot.
No contract changed between periods 1 and 3, so a `Minor` → other
transition has not been observed.

**Owner's reading (2026-10-02):** the other commissioner settled on the
more fluid design. `Minor` is the category for anyone inside the
minors-eligible window. The Minors space is where a team holds players and
cap, and players move up and down freely. This matches the counts above:
the contract follows eligibility, the slot is the lever. The owner noted
ADR-0011 may have been presented differently and is to be reconciled.

What this collides with:

- **ADR-0011** states "Zero `Minor` contracts exist" and decides "There is
  no Minor contract type". The first was true on 2026-07-18 and is false
  now; the second needs rewording, because `Minor` is now a contract value
  Fantrax reports. Its cap rule (only the Minors slot is exempt) is
  consistent with the owner's reading. The amendment is not written yet.
- **`dim_contract` has no `Minor` row** (10 rows: `1st`–`6th`, `Tag`, `X`,
  `FA`, `Pick`), so a contract key from Roster State finds no match on
  about 32% of rows.
- `02d` hard-codes `CONTRACT_ID = "1st"` for drafted players.
- `fact_roster_placement` and `fact_minor_eligibility` were last captured
  on 2026-07-18.

## Payload shapes (authed `04s` captures)

| Payload | Grain | Shape |
|---|---|---|
| `getStandings {view: SCHEDULE}` | week × matchup | `tableList[12]`, 14 rows each; header `Away, FPts, Home, FPts`; cell keys `content, id, leagueId, teamId` |
| `getStandings {view: COMBINED, period}` | team, current (`period` is ignored; see the 2026-10-04 notes) | `tableList[3]`: one 28-row table (`W, L, T, Win%, Div, GB, SR, FPtsF, FPtsA, Streak, % Playoffs`; `fixedCells` carry `teamId`) and two 14-row matchup tables |
| `getLiveScoringStats {period}` | team × player × stat | `statsPerTeam.allTeamsStats[teamId].{ACTIVE,BENCH}.statsMap[scorerId] = {object1: number, object2: [{scipId, sv, av, fpts}]}`; skip the `_1010` / `_1020` keys; team totals in `totalFpts` |
| `getTeamRosterInfo {teamId, period}` (no longer captured, #118) | team × player | `tables[2]` (offense, defense); header `Age, Opp, Sal, Con, FPts, Bye` + stat columns; row keys `statusId, posId, scorer{scorerId, minorsEligible, rookie, …}, cells`; `statusTotals[{id, name, total}]`; `draftPicksData` |

IDs:

- **`scorer_id`** — same value in authed `scorer.scorerId`, live-scoring
  `statsMap` keys and public `id`.
- **`teamId`** — same value in every payload, authed and public.
- **`matchupId`** — does not exist in any payload. A matchup is
  `(period, away teamId, home teamId)`.
- **`divisionId`** — absent from every authed payload. The only source is
  public `getLeagueInfo.teamInfo[teamId].division`.
- **Periods** — the authed schedule lists 12 weeks; public
  `getLeagueInfo.scoringPeriods` lists 17 with start and end dates.
- Two roster rows repeat across the offense and defense tables in period 1;
  dedupe on `(teamId, scorerId)`.

## Drift against existing parsers

| File | Line | Finding |
|---|---|---|
| `04v_minor_contracts.py` | 96, 284 | **Fixed** (`fix/04v-keep-ir-rows`). `EMPTY_SLOT_STATUS = "3"` skips every statusId `"3"` row. In-season `"3"` is IR with real players (35 in period 1, 50 in period 2). Empty slots are already caught by the missing `scorerId`. IR players would be dropped from `fact_roster_placement`. |
| `04v_minor_contracts.py` | 95 | **Fixed** (`fix/04v-keep-ir-rows`; `"3": "Inj Res"`, the live `statusTotals` name). `STATUS_TO_SECTION_FALLBACK` had no `"3"`. Low impact: the live `statusTotals` names override the fallback. |
| `04s_fantrax_inseason_capture.py` | 145 | **Fixed** (`feat/118-capture`, #118). Sent no `playerViewType`, so only Starters were captured. It now sends `"playerViewType": "2"`. Captures taken before the fix (2026-09-26) hold Starters only. |
| `02d_fact_roster_transactions.py` | 496–518 | Comment says the public `period` is ignored. Out of date (section 2). |
| `dim_contract` | — | No `Minor` row (section 4). |

`04a`, `04t` and `04w` parse other methods (`getPlayerStats`,
`getTransactionDetailsHistory`, `getDraftResults`); none of these payloads
pass through them.

## Still open

1. ~~Reconcile ADR-0011 with the `Minor` contract.~~ Done 2026-10-02:
   [ADR-0019](../adr/0019-minor-is-a-pre-1st-contract-stage.md) settles it,
   including the `dim_contract` row.
2. Which instant the public per-period snapshot represents.
3. Why 15 non-starters are missing from `BENCH` in a final period.
   *Harmless under #81: a player with no entry gets no scoring row.*
4. ~~Whether `allEventsFinished` reliably marks a final period.~~ Checked
   2026-10-03 for #81: it sits at `live_scoring.responses[0].data.allEventsFinished`,
   and it is `true` for final periods 1 and 2 and `false` for period 3 in progress.
   No other completion flag exists.

Also checked 2026-10-03 for #81, all from the authed captures:

- **Schedule:** 12 regular-season weeks, 14 matchups each. Every team plays
  once a week, never across Conferences. There are no playoff weeks.
- **Standings (COMBINED):** headers are in `tableList[0].header.cells[]`:
  W, L, T, Win%, Div, GB, Salary Remaining (`SR`), FPtsF, FPtsA, Streak and
  % Playoffs. The league-wide rank (1–28) is in `fixedCells`.
- **Live scoring:** `statsMap` keys `_1010` and `_1020` are offense and
  defense group totals. Skipping them, the Starters' `object1` sum equals
  `ACTIVE.totalFpts` to 0.01 for all 28 teams in period 1.

Answered by the 2026-10-04 capture (`04s --periods 1-5`, with the bench
view and the two probes; period 4 was in progress, period 5 not started):

- **Fantrax takes the by-period selection.** Both probes echo
  `timeframeType: BY_PERIOD` with the `timeStartType` and `period` asked for.
  - `FROM_SEASON_START` is the standings through period N: every team shows
    N games, and wins, points for and points against equal the schedule
    through week N for 28 of 28 teams (periods 1 to 3). Rank changes by
    period. For a period in progress or not started it equals the latest
    final period.
  - `PERIOD_ONLY` is that one period's results alone: 1 game per team, and
    0 for a period that is not final.
  - **`Salary Remaining` is the same in every reply and every period**, and
    **`% Playoffs` is blank in both by-period replies.** In the plain reply
    `% Playoffs` is filled for 14 of 28 teams. So rank has history; salary
    remaining and playoff odds are current values only.
  - Header keys: `win`, `loss`, `tie`, `winpc`, `div`, `gamesback`,
    `salaryRem`, `pointsFor`, `pointsAgainst`, `streak`, `playoffOdds`.
- **The bench view is complete for a final period.** `BENCH` holds Bench,
  IR and Minors. Entries (`ACTIVE` / `BENCH`): 420 / 634, 419 / 663 and
  420 / 670 in periods 1 to 3. No entry is off that period's Roster State
  and no player is in both groups. 9 to 15 rostered players a period have
  no entry, never a Starter. Both groups carry `totalFpts`, and each equals
  the sum of its entries.
- **A period that has not started is not an error.** Live scoring returns
  28 teams with no entries and `allEventsFinished: false`, with no
  `pageError`.
- **Points carry at most two decimals**, per stat and per player.
- **Schedule rows** are four cells: away team, away score, home team, home
  score. A team cell carries `teamId` and the team's name; a score cell
  carries the number only. An unplayed week shows `0`.

Checked 2026-10-04 for #118, from the same 2026-09-26 captures:

- **`getStandings {view: COMBINED, period}` ignores `period`.** The three
  captures (periods 1, 2 and 3, all taken on one day) are identical in every
  column. Every team shows 2 games played, and `FPtsF` equals the schedule
  points of weeks 1 to 3, period 3 in progress included. So the reply is the
  current standings, not the standings as of the period asked for. The two
  14-row tables are the week in play and the last final week.
- **The reply names a way to ask by period** (tested since; see the list
  above). `displayedSelections`
  echoes `timeframeType: YEAR_TO_DATE` and `timeStartType: PERIOD_ONLY`.
  `displayedLists` offers `timeframeTypes` `YEAR_TO_DATE` | `BY_PERIOD` and
  `timeStartTypes` `PERIOD_ONLY` | `FROM_SEASON_START`. `04s` now saves two
  probe replies per period, `BY_PERIOD` with each `timeStartType`. A probe
  counts only if its echo shows `BY_PERIOD`; an unchanged echo means Fantrax
  did not take the request key, and the question stays open.
- **Live scoring echoes no period** (`displayedSelections` is empty), so a
  reply cannot be checked against the period asked for.
- **Units:** every stat id (`scipId`) is `<group>#<category>#<pos>`. Group
  `1010` is Offense and `1020` is Defense. Categories `3218` (under both
  groups) and `256g` (under `1020`) are Special Teams. Per player the stat
  points sum to `object1` exactly, in periods 1 and 2.
- **Starters agree across sources.** In periods 1 and 2 the `ACTIVE` set
  equals `fact_roster_state`'s Starters for 28 of 28 teams, and each team's
  Starter sum equals `ACTIVE.totalFpts` and its schedule `FPts`.
- **Public `getLeagueInfo.matchups`** equals the authed schedule on all 12
  weeks, pairs and sides. Its playoff periods 15 to 17 are `TBD`.

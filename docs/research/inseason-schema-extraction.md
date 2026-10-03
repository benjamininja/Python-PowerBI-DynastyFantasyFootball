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
| `getStandings {view: COMBINED, period}` | team, as of period | `tableList[3]`: one 28-row table (`W, L, T, Win%, Div, GB, SR, FPtsF, FPtsA, Streak, % Playoffs`; `fixedCells` carry `teamId`) and two 14-row matchup tables |
| `getLiveScoringStats {period}` | team × player × stat | `statsPerTeam.allTeamsStats[teamId].{ACTIVE,BENCH}.statsMap[scorerId] = {object1: number, object2: [{scipId, sv, av, fpts}]}`; skip the `_1010` / `_1020` keys; team totals in `totalFpts` |
| `getTeamRosterInfo {teamId, period}` | team × player | `tables[2]` (offense, defense); header `Age, Opp, Sal, Con, FPts, Bye` + stat columns; row keys `statusId, posId, scorer{scorerId, minorsEligible, rookie, …}, cells`; `statusTotals[{id, name, total}]`; `draftPicksData` |

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
| `04s_fantrax_inseason_capture.py` | 145 | Sends no `playerViewType`, so only Starters are captured. Needs `"playerViewType": "2"`. |
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
4. Whether `allEventsFinished` reliably marks a final period.

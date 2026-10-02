# Fantrax public `fxea/general` API: what it exposes without auth

Resolves #80 (child of map #70, "In-season Fantrax league flows").
Probed 2026-09-26 with scoring period 3 in progress (weeks 1 and 2 final).
Every call was a read-only, unauthenticated GET to
`https://www.fantrax.com/fxea/general/<method>` for league `v744203wmmvjqzv6`,
spaced at least 2.5s apart, with no cookies and no writes.

## Gist

The public API gives the **league skeleton**: the full-season schedule of
matchups, the scoring and roster periods, team to division mapping, current
standings (W-L-T and points for), and **per-period roster lineups**, including
past periods. It gives **no scores at all**: no matchup scores, no per-period
team points, no player fantasy points, and no transactions. Matchups+scores,
player-week points and YTD fantasy points, and claims/drops/trades still need
authenticated `fxpa/req` capture.

## Sources for the method list

Fantrax has no public doc page or PDF for this API. Fantrax shares a
"Beta API" doc with users who ask for it, and the community bindings copy that
doc's method list:

- [pmurley/go-fantrax (pkg.go.dev)](https://pkg.go.dev/github.com/pmurley/go-fantrax):
  "current as of documentation provided from Fantrax in April 2025". It lists
  `getPlayerIds`, `getAdp`, `getLeagues`, `getLeagueInfo`, `getDraftPicks`,
  `getDraftResults`, `getTeamRosters` and `getStandings`.
- [meisnate12/FantraxAPI](https://github.com/meisnate12/FantraxAPI) /
  [docs](https://fantraxapi.kometa.wiki/): a Python wrapper. It mostly wraps
  the internal `fxpa/req` RPC, which needs a cookie for private endpoints. It
  is not `fxea`.
- `notebooks/04u_fantrax_public_api.py`: already uses `getDraftPicks` and
  `getTeamRosters`. It notes that six guesses at a trade-log method all failed.

## Method-by-method results

| Method | Params | Unauthed? | Grain | Key fields (shape only) |
|---|---|---|---|---|
| `getLeagueInfo` | `leagueId` | Yes (643 KB) | league | `matchups[period].matchupList[{home,away}{id,name,shortName}]`, `scoringPeriods[{number,startDate,endDate}]`, `rosterPeriods[...]`, `teamInfo{teamId:{id,name,division}}`, `playerInfo{division:{playerId:{eligiblePos,status: T/FA}}}`, `rosterInfo` (position maxActive, 33 total / 15 active / 18 reserve), `scoringSystem` (categories + points), `playoffs{lastRegularSeasonPeriod:12, firstPlayoffPeriod:13, numPlayoffTeams:10}`, `seasonYear`, `startDate`, `endDate` |
| `getStandings` | `leagueId` (`period` ignored, same bytes) | Yes (4 KB) | team, current only | list of 28 `{teamId, teamName, rank, points:"W-L-T", winPercentage, gamesBack, totalPointsFor}` |
| `getTeamRosters` | `leagueId`, `period` optional (defaults to current) | Yes (~120 KB) | team x player x **period** | `period`, `rosters{teamId:{teamName, salaryCap, rosterItems[{id, position, status, salary, contract{smallId,name}}]}}` |
| `getDraftPicks` | `leagueId` | Yes | pick | `futureDraftPicks[{year, round, originalOwnerTeamId, currentOwnerTeamId}]` (280), `currentDraftPicks[{round, pick, teamId}]` (5) |
| `getDraftResults` | `leagueId` | Yes (127 KB) | pick | `draftState`, `draftOrder{division:[teamId]}`, `draftPicks[{division, round, pick, pickInRound, teamId, playerId, time}]` (980) |
| `getPlayerIds` | `sport=NFL` | Yes (1.2 MB) | player | `{fantraxId:{fantraxId, name, position, team, rotowireId?, sportRadarId?, statsIncId?}}` (7,989 rows, including team defense rows) |
| `getAdp` | `sport=NFL`, optional `position/start/limit/order/showAllPositions` | Yes | player | `[{id, name, pos, ADP_PPR}]` |
| `getLeagues` | `userSecretId` (per user) | Returns `{}` without the secret | user | Out of scope: it needs a personal secret |

Undocumented guesses that all returned `{"error":{"code":"WARNING","message":"Unable to find method '...'"}}`
(HTTP 200): `getMatchups`, `getSchedule`, `getScores`, `getLiveScoring`,
`getTransactions`, `getLeagueTransactions`, `getLeagueHome`, `getPlayerStats`,
`getTeamStats`, `getScoringPeriodResults`. The documented list above looks
complete.

### Observations that matter for modelling

- **The schedule is complete and published up front.** There are 17 periods
  with 14 matchups each. Playoff periods 13 to 17 show `{"TBD": ...}` sides (42
  of them) until the bracket is set. Matchup entries have **only** `home` and
  `away` team refs. There is no score, winner or matchup id. The row key has to
  be synthesized as `(period, home_team_id, away_team_id)`.
- **Scoring period equals roster period** (the same numbers and dates, weekly,
  from Thursday night to Thursday night). Period 1 runs 2026-09-09 to 09-17.
- **`getTeamRosters?period=N` is historical.** Periods 1, 2 and 3 all differ.
  From period 1 to period 3, 45 roster slots were added, 15 were removed and
  203 statuses changed. A future period (4) returns a copy of the current
  roster with only `period` changed. `status` values are `ACTIVE`, `RESERVE`,
  `MINORS` and `INJURED_RESERVE`, which gives the lineup (active vs bench) per
  team, player and week. It also carries `salary`, `contract.name`
  (`1st`/`Minor`/`FA`) and `salaryCap`.
- **Standings are a current-state snapshot only.** They have no points
  against, no division and no per-period history. `points` is a W-L-T string.
  Weekly history would need a daily snapshot on our side.
- **No player fantasy points anywhere.** `getLeagueInfo.playerInfo` is only
  `{eligiblePos, status: T|FA}` per division pool.
- IDs line up with the authed side: `teamId` (16-char), player `id`
  (5-char Fantrax scorer id), and `division` names `Riddell`/`Wilson`. Note
  that `getDraftResults` pads the name with a trailing space (`"Riddell "`),
  and `playerInfo` keys do the same.
- Every error comes back as HTTP 200 with an `error` object, so a client must
  check for `error` in the body, not rely on `raise_for_status()` (04u's
  `fetch()` does not check today).

## Verdict: coverage of the map #70 in-season needs

| In-season need | Public `fxea` covers? | Source / gap |
|---|---|---|
| Schedule / matchup pairings | **Yes** | `getLeagueInfo.matchups`, the full season up front |
| Matchup **scores** (team points per period) | **No** | Needs authed `fxpa/req` (e.g. the league schedule/matchup scoring view) |
| Standings (W-L-T, PF, rank, GB) | **Partial** | `getStandings` is current only, with no PA and no division. Weekly history comes from a snapshot per run, or authed capture |
| Player-week lineup (active/bench/IR/minors) | **Yes** | `getTeamRosters?period=N`, backfillable for past periods |
| Player-week fantasy **points** | **No** | Needs authed capture (player stats / team roster stats view) |
| Fantasy points YTD | **No** | Needs authed capture |
| Roster status + contract/salary snapshot | **Yes** | `getTeamRosters` (`status`, `salary`, `contract`) |
| Transactions (claims/drops/trades) | **No** | No method exists. Adds and drops could be *inferred* from roster diffs between periods, but not their type (claim, FA or trade), timing, or counterparty. Authed transaction-history capture is still required (ADR-0003 ledger) |
| Team to division mapping | **Yes** | `getLeagueInfo.teamInfo` |
| Future pick ownership | **Yes** | `getDraftPicks` (already used in 04u) |

**Recommendation:** move schedule, standings snapshot, per-period lineups and
team/division refs onto the public API. It needs no auth, so it suits a
GitHub Actions schedule. Keep Playwright/`fxpa/req` only for **scores
(team and player points)** and **transactions**. Because standings history is
not queryable, a daily run should snapshot `getStandings` if weekly standings
history matters, or derive it from the authed matchup scores.

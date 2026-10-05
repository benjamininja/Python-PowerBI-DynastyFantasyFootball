# Dynasty Fantasy Football — Context

Shared language for the league's data model: how players, prospects, draft
picks, contracts, and transactions are named so the code, the docs, and the
owner mean the same thing.

## Language

### Assets & identity

**Roster Asset**:
Anything a team can own and trade as a unit — a signed NFL player, an unsigned
rookie prospect, or a draft pick. The unifying entity above the three identity
regimes the league had grown into.
_Avoid_: holding, property, piece

**asset_id**:
The one stable, permanent identifier for a Roster Asset. It does not change as
the underlying identity resolves underneath it (a prospect signing, a pick being
named); the resolver moves, the asset_id stays put.
_Avoid_: player_id, entity_id

**Draft Pick**:
A commoditized Roster Asset — player-like and tradeable, but with its own
attributes (draft season, round, original owner) and no person behind it until
it is Exercised.
_Avoid_: selection, slot (a "slot" is the position in draft order, not the asset)

**Original Owner**:
The team a Draft Pick was allocated to at its season's creation — one pick per
round per team. Deterministic and **identity-bearing**: it never changes, even
after the pick is traded, and together with (season, round) it identifies the
pick.
_Avoid_: drafting team, holder

**Current Owner**:
The team that holds a Draft Pick now, after any trades. Moves via Trade; **not**
part of the pick's identity. Equals the Original Owner until the pick is traded.
_Avoid_: original owner (that's the fixed allocation)

### Asset transitions

**Sign** (a.k.a. graduation):
An unsigned prospect becomes a signed NFL player. **Identity continuity** — the
same real-world person, so the same Roster Asset and the same asset_id; only the
underlying identity resolves.
_Avoid_: convert, promote

**Exercise**:
A Draft Pick is spent to acquire a player. **Consumption, not continuity** — the
pick is retired and a *new* player Roster Asset is born, linked to the pick by
lineage. Not the same asset.
_Avoid_: use, redeem, cash in

**Trade**:
An exchange that moves one or more Roster Assets between two teams. Recorded as
faithful, **multi-hop** history — every hand-change is its own Trade, not a
single net transfer from first owner to last.
_Avoid_: swap, deal

### Rosters & cap

**Roster State**:
Who is on each team right now: every player, their Roster Slot, salary and
contract, as the team's Fantrax roster shows it. Read directly, never rebuilt by
replaying Roster Moves. The current one is kept all year; one per regular-season
Scoring Period is kept alongside it. A Scoring Period's Roster State is the
roster as it stood when that period's lineups locked, not at the period's end.
_Avoid_: current roster derived from the ledger, lineup

**Roster Slot**:
Where a player sits on a team: **Starter**, **Bench**, **IR** or **Minors**.
Only Starters score. Fantrax calls Starter "Active" and Bench "Reserve"; those
words are not used here. Not the NFL injury designation (Questionable/Doubtful/
Out), which belongs to the player, not the slot. The Minors slot is not the
Minor contract: a Minor player can sit in any slot. Only the Minors slot takes
a player's salary off the cap.
_Avoid_: active, reserve, roster status, injury status

**Minors Eligibility**:
Whether a player is still inside the prospect window: career plus current
regular-season games played of 19 or fewer, as Fantrax computes it. A flag on
the player, league-wide, whether rostered or not. It lets a team use the
Minors slot but doesn't make them.
_Avoid_: Yo-Yo status, minor (that's the contract)

**Minor**:
The contract a player holds while minors-eligible, however they were acquired.
The stage before `1st`: off the 3-year clock, and dropping the player creates
no Dead Money. The player moves to `1st` in the Scoring Period after they pass
19 games, with the same salary, and that season is year 1.
_Avoid_: Minors (that's the slot), stash, minor-league contract

**Roster Move**:
One team gaining or losing one player — a claim, a drop, or one leg of a Trade.
The record of *how* and *when* a player arrived or left. Identified by the
Fantrax transaction it came from plus the player, team and kind of move. Each
takes effect in one Scoring Period, which Fantrax records: a move made after a
period's lineups lock takes effect in the next one.
_Avoid_: transaction (Fantrax groups several moves under one), event

**Stint**:
One unbroken stay of a player copy on a team. It starts with the Roster Move
that brings the copy in (a draft pick, a claim or a trade) and ends with the
next one that takes it out (a drop or a trade away). A re-claim by the same
team starts a new stint.
_Avoid_: tenure, ownership period

**Period Scoring**:
The points a player earned in a Scoring Period while on a team. The team is
whichever team had the player that period, not the one that has them now. It is
recorded for every rostered player, but only a Starter's points count toward the
Team Score. Fantrax scores each stat separately, so Period Scoring is broken down
by Unit; the individual stats are not kept.
_Avoid_: weekly stats, fantasy points (unqualified)

**Unit**:
The phase of play a stat, a point or a snap belongs to: **Offense**, **Defense**
or **Special Teams**. Scoring stats take Fantrax's offense/defense grouping,
except Return Yards and Blocked Kicks, which are Special Teams (the only special
teams stats the league scores). Snaps are counted per Unit by the NFL.
_Avoid_: side, phase, stat group

**Dead Money**:
Cap charged to a team for dropping a player on a guaranteed contract. It follows
the rest of the contract: each remaining guaranteed contract year charges its own
rate in its own season, to the dropping team, even if the player is later
re-claimed. Trades never create it.
_Avoid_: cut penalty, cap hit (that's a rostered player's charge)

### Results

**Team Score**:
A team's points for a Scoring Period: the sum of its Starters' Period Scoring.
It is Fantrax's matchup score, and it decides the Matchup.
_Avoid_: total points, team fpts

**Matchup**:
Two teams from the same Conference playing each other in one regular-season
Scoring Period. Every team has exactly one per period, and the higher Team Score
wins.
_Avoid_: game, fixture, head-to-head

**Standings**:
The teams in order as of a Scoring Period: by win percentage, then by points
for, both worked out from Matchups up to that period. The order runs across
both Conferences, 1 to 28. Nothing is stored. The rule gave Fantrax's own order
for every team in every period measured (periods 1 to 3 of 2026); no two teams
have yet tied on both, so Fantrax's deeper tiebreaks are unobserved. Fantrax's
playoff odds and its Salary Remaining are not part of Standings.
_Avoid_: table, leaderboard, power rankings

### Storage

**System of Record**:
The one store whose rows are the truth: Supabase Postgres (ADR-0014). Every
ETL write goes through the storage seam into it, and its constraints reject bad
rows at write time.
_Avoid_: master, source of truth (ambiguous with upstream sources like Fantrax)

**Published Snapshot**:
`data/*.parquet`, exported from the System of Record one Chain at a time, only
after that Chain commits and passes its Gate checks, then committed to git. The
only thing Power BI, the bot and trade-bud read, so they keep serving if the
database pauses.
_Avoid_: backup, mirror, cache

**Change Poll**:
A no-auth check that hashes each team's current-period roster on the public
Fantrax API and triggers the transaction ETL when a hash changes. It stands in
for the webhooks Fantrax doesn't offer.
_Avoid_: webhook, live sync

### Checks

**Chain**:
A group of pipeline steps whose tables publish together or not at all: the
Fantrax core, the rookie scrapes, the dynasty profile, nflverse. A failed Chain
keeps its last good tables; the others still publish.
_Avoid_: run (one run holds several Chains), job, group

**Gate check**:
A check that fails when the pipeline itself produced something broken or
incomplete: a step failed, a key repeats, a table collapsed, coverage is
missing, a column changed shape. It blocks its Chain from publishing.
_Avoid_: test, assertion, blocking review

**Review check**:
A check that fails when the data faithfully mirrors Fantrax but disagrees with
what the league expects, such as a contract that doesn't match Minors
Eligibility, or an unmapped key. It files a finding for a person and never
blocks a publish. A finding can wait out a grace period before it is raised.
_Avoid_: warning, error, Drift (Drift is one kind of Review finding)

**Close check**:
A check that must pass before an Update-Set goes from closing to closed: every
team's roster present, every Starter scored, team totals matching Fantrax.
Until it passes, the Update-Set stays closing.
_Avoid_: final check, freeze check

### Time

**Season** (`season_id`):
A league year that straddles two calendar years, written `"2026-2027"`. The
fantasy season runs Mar 1 of the start year through the last day of February of
the end year; the NFL season sits inside it.
_Avoid_: year, draft_year, bare calendar year

**Scoring Period** (`period`):
Fantrax's week: the unit every in-season fact is keyed and bounded by
(`season`, `period`). Same thing as Fantrax's roster period. Not the NFL week —
periods start mid-week and the playoffs (P13–17) need not map one-to-one.
Playoff periods are on the calendar but have no Update-Set.
_Avoid_: week, NFL week, gameweek

**Update-Set**:
The durable record of one Scoring Period. It moves through three states:
**open** (the period is in play; refreshed every run), **closing** (the period
has ended, judged on the league's Eastern clock; still refreshed so stat
corrections land) and **closed** (the following period has ended and its Close
checks pass; frozen). A closed Update-Set changes only by an explicit re-close.
Only regular-season periods have one. A period's Period Scoring and Matchups
are first recorded once its games are all final, which can be while it is still
open.
_Avoid_: weekly snapshot, week-closed data

**Drift**:
A difference between a closed Update-Set and what Fantrax reports now for that
period. Raised as an alert, never auto-applied, because history must not change
silently.
_Avoid_: correction (that's the normal change a closing period absorbs)

### Teams & divisions

**Conference**:
The stable half of the dual-conference league, identified `A` / `B`. Membership
and the `A`/`B` code do not change season to season.
_Avoid_: division (that's the seasonal label, below)

**Division**:
The **seasonal display name** of a Conference (`Riddell` / `Wilson` for
2026-2027) — themed and allowed to change between seasons. Resolved per season,
not a fixed team attribute, and taken from Fantrax.
_Avoid_: conference (that's the stable code), bracket, group

**Owner Manifest**:
The team/owner registry — names, abbreviations, manager contacts, and the
team_key ↔ Fantrax pairing. Fantrax is its upstream source of truth; the league
Google Sheet is a field-scoped synced mirror. Its manager contacts are Owner
PII.
_Avoid_: roster (that's players on a team), team list

**Owner PII**:
The link from a team to a real person: the person's human name, email and
Fantrax username. Kept in one protected table only; never in the Published
Snapshot, raw payload storage, docs or commits. Team names, abbreviations and
Fantrax team ids are public league identity, not Owner PII — even when a team
name contains a person's name.
_Avoid_: owner (that's the team, as in Original/Current Owner), user data

### Valuation & trade diagnostic

**Stance**:
A manager's strategic orientation (`contending`, `balanced`, `future`) that
selects valuation boards, age multiplier curves, and draft pick scalars in
`mouserat_trade-bud`.
_Avoid_: mode, phase, team state

**Position Ceiling**:
The positional scarcity multiplier derived per-conference from replacement-level
VOR (`ceiling = sqrt(max_fpts - replacement_fpts)` rescaled top = 100) to balance
offensive and IDP asset values without inflating overall rankings.
_Avoid_: position weight, tier multiplier

**Pick Stance Scalar**:
A stance-specific multiplier (`contending` 0.85, `balanced` 1.00, `future` 1.25)
applied to draft pick curves to reflect temporal team goals.
_Avoid_: pick tax, pick bump

**Commensuration**:
Mapping player and draft pick values onto one currency, so a mixed package can
be summed at all. A source that quotes both in the same native units (KTC's
`value`, DraftSharks' `ds_value`) is what makes it possible. **Built
2026-08-01 (#49)**: a pick's percentile within its source's covered player
pool maps onto our-scale player value at that same percentile (quantile
mapping), clamped at the anchoring pool's own max; players fold their
age tilt into the rank pre-ceiling instead of the finished value. Both are
now capped at 100 by construction. ADR-0013 decisions 4-5.
_Avoid_: dual scale, uncalibrated sum


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

### Time

**Season** (`season_id`):
A league year that straddles two calendar years, written `"2026-2027"`. The
fantasy season runs Mar 1 of the start year through the last day of February of
the end year; the NFL season sits inside it.
_Avoid_: year, draft_year, bare calendar year

### Teams & divisions

**Conference**:
The stable half of the dual-conference league, identified `A` / `B`. Membership
and the `A`/`B` code do not change season to season.
_Avoid_: division (that's the seasonal label, below)

**Division**:
The **seasonal display name** of a Conference (`Riddell` / `Wilson` for
2026-2027) — themed and allowed to change between seasons. Resolved per season,
not a fixed team attribute.
_Avoid_: conference (that's the stable code), bracket, group

**Owner Manifest**:
The team/owner registry — names, abbreviations, manager contacts, and the
team_key ↔ Fantrax pairing. Fantrax is its upstream source of truth; the league
Google Sheet is a field-scoped synced mirror.
_Avoid_: roster (that's players on a team), team list

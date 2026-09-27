# Roster State is read from the snapshot; the ledger is provenance; cap math is computed once

- Status: accepted. Designed through HITL grilling on 2026-09-27 ([#82](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/82)); not yet built.
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
   - **Period Scoring** comes from the per-period roster plus live scoring (`04s`). Team attribution comes from the period roster, not the ledger. The grain is decided in #81.
   - Replaying the ledger becomes a **reconciliation check**. Differences from the snapshot go to a `review_*` queue.
2. **Roster Slot** is Starter / Bench / IR / Minors, mapped from Fantrax `statusId` (Active → Starter, Reserve → Bench). The NFL injury designation is a separate player attribute.
3. **Snapshot source.** When the Change Poll detects a change, it persists the public `getTeamRosters` it just hashed. That needs no login. This holds **only if #79 confirms** the public payload carries all four slots plus salary and contract. Otherwise the source is the authed `getTeamRosterInfo`.
4. **History.** One current Roster State, overwritten on each change, plus one snapshot per Scoring Period that follows the Update-Set lifecycle (ADR-0015). A closed snapshot is frozen, and later differences raise Drift.
5. **Dead Money is its own fact** (`fact_dead_money`), derived from drops. It has one row per guaranteed-contract drop × charged contract year, charged to the dropping team, with the drop date.
   - **Schedule: the rest of the contract, by year.** Each remaining guaranteed contract year charges its own `cap_hit_pct × contract_value` in its own season. A 1st-year drop costs .50 now and .40 next season. A 2nd-year drop costs .40. A 3rd-year drop costs 0.
   - The contract at the time of the drop is taken from the last Roster State before it.
   - If the same team re-claims the player, the Dead Money stands and the claim starts fresh terms. A commissioner-reversed drop disappears from the log, so it never produces Dead Money.
6. **Move identity** is the natural key `(txSetId, scorer_id, team_key, event_type)`. `event_seq` is a sort order only. Startup-draft rows keep their ADR-0004 key.
7. **Cadence.** Each run pulls the whole season from `04t` (the volume is small, and a full pull catches reversals), then runs `02d` and then Dead Money. This happens on **every debounced Change Poll trigger**, after the snapshot is saved, and again on the daily run. If spike #92 shows that frequent logins get challenged, fall back to the daily run only.
8. **Cap math is computed once, in the ETL.** The cap functions move out of `discord_bot/` into a shared module that the ETL calls. The ETL publishes:
   - `fact_fantasy_teams`: the snapshot rows plus `acquired_method` and date from the latest Roster Move into that team.
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

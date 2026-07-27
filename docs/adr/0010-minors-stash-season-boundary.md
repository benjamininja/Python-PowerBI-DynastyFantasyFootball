# Minors stash durability: season-boundary FA gaps break contract protection

- Status: **SUPERSEDED** by
  [ADR-0011](0011-minors-is-placement-not-contract.md) (2026-07-26)
- Date: 2026-07-25

> **Superseded — do not implement or extend this.** This ADR defines stash
> durability for a **Minor contract type that does not exist**. The Minors
> system is placement + eligibility only: minors-eligible players hold ordinary
> contracts (generally `1st`), and nothing about the contract changes when a
> team places them in or out of the Minors squad. See ADR-0011.
>
> The "presently inert" note below was the right observation for the wrong
> reason — not "no Minor contracts *yet*", but no such thing at all. The
> `derive_minor_events()` logic this ADR describes remains in `02d` as inert
> dead code pending a cleanup pass; it has never emitted a row.
- Scope: `notebooks/02d_fact_roster_transactions.py` (`derive_minor_events`),
  `notebooks/04v_minor_contracts.py` (doc only), `fact_roster_transactions`
- **Corrects** the Yo-Yo Rule wording carried in `PLAN.md` and
  `.claude/memory/data-model.md`; builds on
  [ADR-0003](0003-event-sourced-roster-transactions.md)'s event-sourced ledger.

## Context

The Yo-Yo Rule as documented said: *"every player with career+current
regular-season GP ≤ 19 holds a **Minor** contract league-wide **(rostered or
FA)**"*. The commissioner confirmed that parenthetical is wrong. It conflates
two different things:

- **Eligibility** — GP ≤ 19. This genuinely is durable through free agency;
  Fantrax computes it itself and doesn't care whether the player is rostered.
- **Contract protection** — the Minor contract's benefits (Minors-squad
  eligibility, 0% drop penalty, and not burning years off the 3-year clock).
  This is *earned by a team stashing the player on its roster*, and was never
  meant to survive the player sitting in the free-agent pool across a season.

The rule had no ADR, which is how the two drifted into one sentence.

In code, the conflation lives in `derive_minor_events()`. It walks each roster
copy's `fact_roster_placement` snapshots grouped by `(team_key, scorer_id)`,
carrying a `prev` contract variable across the group. A copy that vanishes from
the snapshots (i.e. is in FA) and later reappears still holding Minor hits
`prev == MINOR_ID` and emits **nothing** — the stash silently continues across a
gap of any length or timing. That silent carry-through *is* the "(rostered or
FA)" bug in executable form.

## Decision

**Protection is granted by being stashed on a roster under contract.** Absence
from a snapshot period is time spent in free agency, and the *timing* of that
absence decides the outcome:

1. A **mid-season** FA gap does **not** break the stash. Teams churn the bottom
   of a roster constantly; that shouldn't cost a prospect their protection.
2. A gap spanning a **season boundary** **does** break it — the player either
   ended a season sitting in FA, or entered the next season's preseason auction
   undrafted. Either way no team was stashing them across the rollover.
3. Breaking a stash **never burns GP eligibility**. If the player is re-signed
   while still under 20 GP, they start a **fresh, independent** stash with no
   memory of the prior partial one.

**Implementation**: make `derive_minor_events`'s carry season-aware. Build the
global ordered snapshot grid from the placement table itself (placement only
holds rows for periods where a copy was *present*, so "was this copy absent?" is
only answerable against the full set of periods captured at all). Between a
copy's consecutive present-snapshots, if any global period was skipped **and**
the two snapshots belong to different seasons, reset `prev = None`. A fresh
`minor_assignment` then fires naturally on reappearance.

Season identity comes from the placement row's own `season` field, not from
`capture_date`: Fantrax labels each snapshot with the season it belongs to,
which is authoritative and sidesteps the edge case where a new season's `PRE`
snapshot is captured before the prior fantasy year's end date.

**No new event type.** A `minor_stash_break` event was considered and rejected:
the break has no independent contract consequence to record — its entire effect
is that the *next* assignment is fresh, which the reset already expresses.
Adding one would mean touching `02e`'s replay, its `TERMINAL` set, and the PBI
model for something that would carry no rows.

**`contract_year` stays 1** on both Minor events. Minor is a one-year rolling
term (`dim_contract.total_years == 1`), so this is already correct.

## Consequences

**This rule is prospectively correct and presently inert.** Two facts, both
confirmed by direct inspection at the time of writing, bound what it can do:

- **No player currently holds a `Minor` contract.** `fact_roster_placement`'s
  992 rows are 987 `1st` + 5 `FA`, zero `Minor` — even though 125 players sit in
  the Minors *squad section*. `derive_minor_events()` has therefore never
  emitted an event, and the ledger holds zero `minor_assignment`/
  `minor_graduation` rows.
- **The clock this rule pauses does not tick.** `contract_year` is written as
  the literal `1` at every writer in the repo; nothing advances it across a
  season. Building that rollover is a separate, larger piece of work that this
  rule merely presupposes.

Recording that inertness here is the point — so it reads as a known state rather
than a future surprise when someone finds this logic has never fired.

**The live cap-exemption path is unaffected.** Cap exemption follows Minors
*placement* (`roster_status == "Minors"`), not the Minor contract — see
`discord_bot/capmath.py` and the DAX `Active Roster Salary` measure. That is 125
real players today and neither reads nor cares about stash state.

**Validation is by construction, not by data.** With zero Minor contracts, one
placement snapshot, and one season, there is nothing real to test against. The
change was verified two ways: a synthetic replay of `derive_minor_events` over a
hand-built placement frame covering all four cases (continuous-across-boundary,
mid-season gap, boundary gap, ungapped graduation), asserting the emitted event
counts; and a real-data regression confirming `02d` → `02e` produce
byte-identical output (1094 ledger rows, 1027 active roster rows) — since no
Minor contract exists, a correct change *must* be a no-op on real data, and any
difference would have been a bug in the change.

**Agreement with the claim path, by coincidence rather than coupling.** The
CLAIM contract-inheritance logic added the same day independently enforces the
same boundary: a claim inherits only a contract held *this season in this
conference*, so a new-season re-claim falls back to `FA` rather than
resurrecting last season's terms. The two paths agree; neither needs to know
about the other.

## Alternatives considered

- **Ledger `drop`/`claim` events as the gap signal** instead of snapshot
  absence. Rejected as unnecessary: a drop-and-re-add falling entirely between
  two snapshots is by definition a mid-season gap, which doesn't break the stash
  anyway — so the finer resolution changes no outcome, at the cost of coupling
  this function to the transaction parser.
- **Docs-only correction, defer all code.** Rejected: the primitives (real
  `drop` events, `_season_id_for`) had just landed, and leaving
  `derive_minor_events` knowingly wrong is how the rule drifted the first time.
- **Build the `contract_year` rollover clock first.** Deferred to its own round;
  it is a prerequisite for the rule *mattering*, not for it being *correct*.

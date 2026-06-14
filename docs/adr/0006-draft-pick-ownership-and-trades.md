# Draft-pick ownership & trades: `draftPicks.go` + transaction history

- Status: accepted (design; build deferred — gated on two Fantrax captures)
- Date: 2026-06-14
- Scope: `dim_draft_pick`, `fact_roster_transactions`, `fact_fantasy_teams`,
  `dim_roster_asset`
- **Supersedes** the slot-keyed `dim_draft_pick` from [ADR-0004](0004-polymorphic-asset-id.md)'s
  Build amendment; **extends** ADR-0004's pick/`trade` design and
  [ADR-0003](0003-event-sourced-roster-transactions.md)'s ledger.

## Context

The ledger-v1 build (ADR-0003/0004, PR #15) shipped picks **slot-keyed** with
`original_owner` NULL and `pick_allocation`/`trade` **dormant** — because the only
captured source, `getDraftResults`, gives each slot's *current* owner but not the
pick's origin, and we had no trade history. The headline goals here —
`original_owner`, faithful `trade` events, and forward-year (2027/2028) pick
inventory — need sources we hadn't captured.

Two Fantrax pages supply them:
- **`draftPicks.go`** (`?season=…&viewType=TEAM&divisionId=…`, per-division) —
  the owner of every pick, current **and** forward, reflecting trades.
- **`transactions/history;view=TRADE`** (per-division) — a faithful, multi-hop
  trade log.

League facts that drive the design: the 2026 **startup** is a one-time 35-round
snake **draft** (not an auction); **rookie drafts thereafter are 5 rounds**;
allocation is deterministic (**one pick per round per team**); 28 teams across 2
divisions; `getDraftResults` is meaningful **only during a live draft**.

Settled via a `/grill-with-docs` session on 2026-06-14. Terms resolved into
[CONTEXT.md](../../CONTEXT.md): Original Owner, Current Owner, Trade.

## Decision

1. **Re-key `dim_draft_pick` to `(season, round, original_owner)`** — the glossary
   identity. `overall_slot` and `current_owner` demote to nullable attributes.
   Rationale: forward picks have **no slot** (draft order unset), so a slot key
   cannot represent them; `original_owner` is the trade-stable identity ADR-0004
   promised.

2. **Every pick is a first-class asset** (`asset_id` minted for all picks —
   ADR-0004 Option I). **`pick_allocation` stays dormant**: allocation is
   deterministic, so an allocation *event* carries no information the rule + team
   list don't already give. `dim_draft_pick` is **rule-seeded + trade-updated**,
   not allocation-event-sourced.

3. **`trade` goes live**, event-sourced from `transactions/history;view=TRADE`.
   Grain: **one row per asset leg** in `fact_roster_transactions`, `team_key` =
   receiving team, plus **`from_team_key`** and **`trade_id`** (legs in both
   directions share the `trade_id`). **All legs recorded** (picks *and* players);
   the player-leg **cap recompute** is deferred to the FA/roster-move build.

4. **Ownership SSOT**: `current_owner` is **stored from `draftPicks.go`** (the
   in-season ownership truth, reflecting trades); `original_owner` is
   **deterministic** from the pick's position + the base draft order; **trade-replay
   reconciles** against the stored `current_owner` at build time — a divergence
   (logged to `data/review/`) means a missed or mis-parsed `trade`.

5. **Provenance**: a surrogate **`transaction_id`** (monotonic, persisted, never
   re-derived — same pattern as `asset_id`) on the ledger.
   `fact_fantasy_teams.acquired_by` = FK → `transaction_id`;
   `fact_fantasy_teams.acquired_via` = denormalized `event_type`. Draft events
   carry **`via_asset_id`** → the consumed pick asset, materialising the Exercise
   lineage **on the event** (no separate `spent_asset_id` graph on
   `dim_roster_asset`). `acquired_by` points at the event behind the player's
   **current** contract (a drafted-then-traded player → the `trade` event).

6. **Sources & scope**: `draftPicks.go` = pick-ownership SSOT (current + forward);
   `getDraftResults`/04w = **live-draft made-pick attribution only**;
   `transactions/history;view=TRADE` = `trade` events. **`CLAIM_DROP` (→ `fa_pickup`/
   `drop`) is deferred** to the FA/roster-move build. **Capture-first**: capture
   both new sources, then build against the real wire shape (no schema-first
   guessing).

## Alternatives rejected

- **Keep `dim_draft_pick` slot-keyed** (ADR-0004 build amendment) — cannot
  represent forward picks (no slot) and breaks trade-stable identity. Re-keying
  restores glossary–code agreement.
- **`pick_allocation` as real events** (strict event-sourcing) — ceremonial rows
  carrying no information beyond the deterministic allocation rule.
- **Separate `fact_trades` table** — splits the SSOT, forces unions to answer
  "what did this team acquire," and contradicts ADR-0003's add-rows-not-tables
  principle.
- **Pure-derived `current_owner`** (replay as SSOT) — a single parse miss silently
  corrupts ownership with no cross-check, and demands a perfectly complete trade
  log. Fantrax-direct + replay-as-check is self-auditing.
- **`getDraftResults` as the in-season ownership source** — only valid during a
  live draft; `draftPicks.go` is the standing ownership SSOT.

## Consequences

- Re-keying migrates the built 2026 `dim_draft_pick` rows (490 × 2 divisions) from
  the slot key to `(season, round, original_owner)`; made-pick fact references
  re-point.
- ~1,260 pick assets minted (uniform Option I). The pick→player Exercise link
  lives on the draft event (`via_asset_id`), surfaced on the roster via
  `acquired_by`.
- `trade` events make pick ownership auditable. The build **asserts** every trade
  leg resolves to a minted `asset_id`, and that replay matches the stored
  `current_owner`.
- Build is **gated on two user-driven authed captures** (`draftPicks.go`,
  `transactions/history;view=TRADE`), both per-division, capture-first.
- Forward seeding = 28 teams × 5 rounds × {2027, 2028} = **280 picks** (plus the
  2026 startup grid already built).
- **Deferred to the FA/roster-move build**: player-trade cap effects and
  `CLAIM_DROP` (`fa_pickup`/`drop`).
- ADR-0004's Build-amendment slot-key note is **superseded** by Decision 1 here.

Open at build time (resolve on capture): the exact `draftPicks.go` /
`transactions/history` wire shape; whether `original_owner` reads off a
`draftPicks.go` label or is computed from position + base draft order; the base
draft-order source for that position→origin mapping.

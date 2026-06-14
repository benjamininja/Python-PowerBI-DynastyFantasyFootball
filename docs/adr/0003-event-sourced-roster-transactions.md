# Event-sourced `fact_roster_transactions`; `fact_fantasy_teams` is derived

- Status: accepted (design; build deferred)
- Date: 2026-06-13
- Scope: new `fact_roster_transactions`, `fact_fantasy_teams`, `dim_fantasy_teams`
- **Amended 2026-06-13 by [ADR-0004](0004-polymorphic-asset-id.md):** the ledger
  key changes `gsis_id → asset_id` (`season + event_type + team_key + asset_id +
  event_seq`) to admit draft picks and prospects as first-class assets;
  `event_type` gains `pick_allocation` (live) and `trade` (defined, dormant v1);
  `season → season_id` (new `dim_season`).

## Context

The league needs to track how every player was acquired and at what salary:
the startup auction (35 rounds), rookie drafts, free-agent auctions (FAAB),
free-agent pickups, and re-signs / franchise tags. `fact_fantasy_teams` exists
as a 12-column schema seed (02b) but is unpopulated. The owner wants to run this
**live during the startup draft** — re-deriving roster availability between picks
to drive the 05a `startup_draft_board.xlsx`.

Settled via a 5-question grill on 2026-06-13.

## Decision

Introduce **`fact_roster_transactions`** (renamed from the proposed
`fact_dead_money_drafts`) as an append-only, event-sourced acquisition ledger,
and make `fact_fantasy_teams` a **derived** current-state projection.

- **Unified fact + `event_type` discriminator**: `startup_auction | rookie_draft
  | fa_auction | fa_pickup | resign` (`resign` covers re-sign and franchise tag;
  add `drop` for dead-money realization). New event types add ROWS, not tables —
  mirrors the single-EAV-fact instinct.
- **Grain**: one row per acquisition event. Key: `season + event_type +
  team_key + gsis_id + event_seq` (pick number for drafts, txn date for FA).
- **SSOT**: the ledger is the source of truth for acquisition + salary.
  `fact_fantasy_teams` = replay the ledger → latest active contract per rostered
  player. Current rosters are derivable from startup data alone (no dependency on
  a pre-existing roster), which is what makes the live-draft availability view
  possible.
- **Salary / cap**: `contract_value` ← the salary Fantrax assigns;
  `cap_hit` is DERIVED by contract type (`dim_contract.cap_hit_pct` × value, by
  `contract_year`) and never stored twice; `dead_money` = guaranteed residual;
  Yo-Yo cap-exempt while `ml_games_left > 0`.
- **Source**: 04a-style Playwright + Fantrax `fxpa/req` (`getDraftResults`-type
  method), persistent `.pw_profile`; full snapshot each run → replace-by-
  `(season, event_type)`; idempotent so it is safe to re-run between picks.
  Reuse `etl_helpers` (CFG, `dim_fantrax_crosswalk` scorer_id→gsis_id,
  `load_replace_partition`).

## Alternatives rejected

- **Separate fact per event type** (startup/rookie/FA) — more tables and
  relationships, duplicated salary/contract logic, union work in Power BI.
- **Independent sourcing of `fact_fantasy_teams`** from the roster page — salary
  can diverge from draft history, and it cannot show live availability before a
  roster exists (during the draft itself).
- **Trust Fantrax for cap_hit too** — redundant with the contract-type
  derivation and risks Fantrax's cap model not matching league rules.

## Consequences

- `fact_fantasy_teams` becomes a derived projection, not a scrape target;
  "saturate it" now means *build the derivation*. It feeds `dim_fantasy_teams`
  cap rollups.
- Correctness depends on capturing every acquisition event in the ledger.
- v1 build scope = startup auction (35 rounds); the schema is forward-compatible
  for the other event types.
- Build is a future multi-step stage (own window) after Phase 0 + compact.
- Open at build time: finalize the `event_type` enum (incl. `drop`); the
  roster-page role under ledger-SSOT (recommendation: defer the roster scrape for
  v1 startup — there is no prior roster — and use it later for in-season
  status/IR reconciliation); the exact `dead_money` schedule by contract year;
  the 05a availability-join wiring.

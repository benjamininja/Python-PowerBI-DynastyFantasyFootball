# Event-sourced `fact_roster_transactions`; `fact_fantasy_teams` is derived

- Status: accepted — **BUILT + MERGED 2026-06-14 (PR #15)**; see the Build amendment below
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

## Build amendment (2026-06-14) — built reality

Built S1–S4 and merged to `main` (PR #15) against the live Riddell capture
(`.venv`). Where the build diverged from the design above:

- **`startup_auction` → `startup_draft`.** League reality (grill 2026-06-14): the
  league is at the **startup now, and it is a snake/linear DRAFT, not an auction** —
  players are acquired via picks, not bids. Auctions are the FA / re-sign mechanism
  next offseason (~2027). The `startup_auction` value in the enum above is
  **misnamed for v1**; the built event is `startup_draft`. The auction event types
  stay forward-defined for when FA arrives.
- **Grain key is the ADR-0004 form**, not this ADR's `gsis_id` key:
  `season_id + event_type + team_key + asset_id + event_seq` (`event_seq` =
  `overall_slot`). v1 built the **full** ADR-0004 polymorphic-asset machinery, not a
  `gsis_id`-keyed interim.
- **`contract_value` = the Fantrax `salary` field** (already captured in
  `fact_fantrax_adp.salary`, projection-based), joined by `scorer_id` from the
  latest snapshot (as-of the pick). Each made pick → an **Initial** contract, yr 1
  (`dim_contract` `"1st"`: `cap_hit_pct = 0.50`, guaranteed, 3-yr term); `cap_hit` =
  `0.50 × value`; `dead_money = 0` at acquisition. `getDraftResults` carries **no**
  salary on the pick, so the snapshot join is the source.
- **Source = `getDraftResults`**, fetched by new `notebooks/04w_fantrax_draft_results.py`
  (reuses 04a's `FantraxScraper`). The draft board is served by Fantrax's
  **service worker**, so a DevTools HAR records the response *size* but not the
  *body* — a HAR cannot deliver it; 04w fetches through the authed request context.
  `getDraftResults` returns **one division per call** (14 teams × 35 = 490 slots);
  04w loops both divisions (Riddell + Wilson), writing one raw file each, and 02d
  globs + dedups them on `(divisionId, round, pickNumber)`.
- **Built tables**: `01f`→`dim_season`; `02d` (one pass)→`dim_roster_asset` +
  `dim_draft_pick` + `fact_roster_transactions`; `02e`→derived `fact_fantasy_teams`
  + `dim_fantasy_teams` cap rollup; `05a` gained a non-destructive "Drafted By"
  availability column. Idempotent replace-by `(season_id, event_type)`.
- **Live-draft status**: Riddell is drafting (138/490 made as of 2026-06-14);
  Wilson has not started (0/490). The ledger scales to both divisions automatically
  as picks land — re-run `04w → 02d → 02e`.
- See [ADR-0004](0004-polymorphic-asset-id.md)'s Build amendment for the
  `asset_id` scheme and the slot-keyed `dim_draft_pick` / `original_owner`-deferred
  trade finding.

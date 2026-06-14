# Polymorphic `asset_id` + `dim_roster_asset` unifies players, prospects, and picks

- Status: accepted — **BUILT + MERGED 2026-06-14 (PR #15)**; see the Build amendment below
- Date: 2026-06-13
- Scope: `fact_roster_transactions`, `fact_fantasy_teams`, new `dim_roster_asset`,
  new `dim_draft_pick`, new `dim_season`
- Supersedes the `gsis_id`-in-key grain of [ADR-0003](0003-event-sourced-roster-transactions.md)

## Context

The league had grown into **three identity regimes** for things a team can own:

- `gsis_id` → `dim_nfl_players` (signed NFL players)
- `player_key` → `dim_rookie_prospect` (unsigned prospects; no `gsis_id` until they sign)
- *nothing* — draft picks, which have no person behind them at all

The existing "Player FK Strategy" carried **both** `gsis_id` and `player_key`
columns in every fact during the pre-signing window and COALESCEd downstream.
ADR-0003 then keyed `fact_roster_transactions` on `gsis_id`. Bringing draft
capital in (a team's tradeable picks) broke that key: a pick has no `gsis_id`,
and the owner's model is explicit — **a draft pick is a commoditized asset,
player-like but with its own dimensional attributes**. Settled via a
`/grill-with-docs` session on 2026-06-13.

## Decision

Introduce a **polymorphic `asset_id`** as the single, stable identity for any
**Roster Asset** (see [CONTEXT.md](../../CONTEXT.md)), resolved by a thin
**`dim_roster_asset`** bridge. This is the unifying layer over all three regimes.

- **`dim_roster_asset`** — one row per real-world asset. Columns:
  `asset_id` (PK, opaque surrogate), `asset_type` (`player | prospect | pick`),
  and nullable resolvers `gsis_id?`, `player_key?`, `pick_ref?`. It plays the
  role the crosswalks (`dim_fantrax_crosswalk`, `dim_dynasty_crosswalk`) play
  today, generalized one level up.
- **`asset_id` is permanent; the resolver migrates underneath it.** The
  surrogate is *not* derived from `gsis_id`/`player_key` (those move). Stability
  rules:
  - **Sign / graduation** (prospect → signed player) = **identity continuity**:
    same `asset_id`, the row's `gsis_id` fills in next to its `player_key`. This
    retires the null-flipping dual-FK dance in the new facts.
  - **Exercise** (pick spent → player) = **consumption, not continuity**: the
    pick asset is retired and a **new** player `asset_id` is born; the
    `rookie_draft` ledger row links them (`spent_asset_id` = pick, row
    `asset_id` = player).
- **Ledger key changes** from ADR-0003: `season + event_type + team_key +
  asset_id + event_seq` (was `gsis_id`).
- **`dim_draft_pick`** — descriptive dim for pick assets, parallel to
  `dim_nfl_players`. Natural key `pick_ref = (draft_season, round,
  original_owner)`; **stable under trade** (current owner moves via ledger
  events, `original_owner` never changes). `overall_slot`/`pick_no` is a
  late-resolving nullable attribute (unknown for future years, fills once draft
  order is set — same shape as `gsis_id` filling in at signing).
- **`dim_season`** — calendar spine. PK `season_id` string `"2026-2027"`;
  `season_start_year`, `season_end_year`, `season_fantasy_start_date`
  (Mar 1 of start year), `season_fantasy_end_date` (last day of Feb of end year),
  `season_nfl_start_date`/`season_nfl_end_date` (public schedule, nullable until
  known), `theme`. New facts key `season → season_id`; `dim_draft_pick.draft_season`
  → `season_id` too.
- **Scope discipline:** `dim_roster_asset`/`season_id` adoption is for the
  **new** facts only. Existing facts keep their `gsis_id`/`player_key`/`draft_year`
  FKs until a deliberate migration — no forced rewrite.

## Alternatives rejected

- **Separate `fact_draft_capital`** for picks — splits the SSOT, forces
  `fact_fantasy_teams` to union two facts to answer "what does this team own,"
  and loses the pick→player exercise link.
- **Pseudo-players in `dim_nfl_players`** (mint fake `gsis_id`s for picks) —
  pollutes the player registry; every player-identity join must filter them out.
  This is what KTC does in its flat `playersArray` (the 36 `RDP` rows); we have
  dimensions precisely to avoid it.
- **Keep the dual `gsis_id` + `player_key` FK columns and bolt on a third for
  picks** — three sparse, mostly-null FK columns per fact and COALESCE
  everywhere; the bridge dim is the altitude-correct fix.

## Consequences

- The dual-FK pre-signing dance disappears in the new facts: one stable
  `asset_id` holds across signing.
- Picks become first-class, event-sourced assets in the same ledger:
  `pick_allocation` seeds initial ownership from the Fantrax `draftPicks.go`
  snapshot; `trade` is defined in the `event_type` enum but **dormant in v1**
  (fresh startup, no trades; the `.go` snapshot has no trade history anyway).
- **Pick valuation deferred.** KTC RDP values are a *time-varying market
  estimate* (picks have ~no true value in the offseason; projections firm up
  weekly in-season), so they belong later as a snapshot-dated metric tied to the
  pick class, **not** a fixed `dim_draft_pick` attribute. v1 = inventory only.
- Open at build time: HAR-capture `draftPicks.go` for the underlying `fxpa/req`
  method + shape; add `fantrax_team_id` to `dim_fantasy_teams` (resolves Fantrax
  `teamId → team_key`; front-runs the owner-manifest task); confirm the
  current+2 pick horizon during the rookie-draft window; `dim_season` NFL date
  lookup; the `asset_id` surrogate scheme (sequence vs deterministic hash).

## Build amendment (2026-06-14) — built reality

Built + merged (PR #15) against the live Riddell capture. Resolutions of the
"open at build time" list, and the two design points reality changed:

- **v1 = FULL ADR-0004** (user decision): built `dim_roster_asset` +
  `dim_draft_pick` + `dim_season` + the `pick_allocation`/`trade` enum +
  polymorphic `asset_id` now, driven by live `startup_draft` events (ADR-0003's
  `startup_auction` is renamed — see that ADR's Build amendment).
- **`asset_id` = monotonic integer sequence** (resolves "sequence vs hash"):
  minted at first sight on the stable Fantrax `scorer_id`, persisted in
  `dim_roster_asset`, **never re-derived**. Known assets only refresh their
  `gsis_id`/`player_key` resolvers underneath the fixed `asset_id`.
- **`dim_draft_pick.pick_ref` was redefined to the SLOT, not the planned
  `(draft_season, round, original_owner)`.** ⚠ **Startup picks WERE traded** —
  `getDraftResults` gives each slot's **current** owner (some teams hold 2 picks
  in a round, others 0), and the pre-trade allocation lives only in Fantrax
  `draftPicks.go`, which is **not yet captured**. So the built natural key is the
  slot `pick_ref = (draft_season, divisionId, overall_slot)`, the dim records
  `current_owner`, and **`original_owner` is left NULL** until `draftPicks.go`
  lands. `pick_allocation` / `trade` events therefore stay **dormant in v1** (no
  source). The made-pick fact is unaffected — it records who actually drafted.
- **Team identity = the league Sheet's `Fantrax-TeamId` column** (ADR-0005 locked
  col; user added it 2026-06-14), ingested by `01c` →
  `dim_fantasy_teams.fantrax_team_id` (28/28, unique). `02d` joins
  `teamId → team_key` straight off it. The interim name-match heuristic
  (`01g_dim_fantrax_team_crosswalk`) was built and then **retired** — superseded by
  the Sheet (it had inferred the right mappings; re-running 01c also fixed drifted
  team names, e.g. A08's stale "Metallica").
- **Pick horizon = current + 2** (2026/2027/2028) confirmed; `dim_season` seeds 3
  rows. Forward-year picks (2027/2028) and the `original_owner` backfill both await
  the `draftPicks.go` capture.
- **Pick valuation** still deferred (v1 = inventory only) — unchanged.

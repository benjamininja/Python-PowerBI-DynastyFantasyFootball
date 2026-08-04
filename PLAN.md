# PLAN.md

Scratchpad for active/upcoming work. Expected to drift — completed items
collapse to one-liners once their durable signal lands in an ADR / MEMORY /
data-model. Blow-by-blow does NOT live here.

> **Runtime token-gating** (see [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)):
> loop is `grill/plan → (Phase 0 consolidate) → compact → execute stage →
> compact → … ↺`. Compact at **~125K–150K tokens**. PLAN.md = heartbeat;
> Memory/ADR/CONTEXT = real signal, batched into Phase 0.

## [x] CLOSED — trade-bud: wayfinder map #44 (2026-08-01)

**Tracker: [wayfinder map #44](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/44)** —
closed. All 5 ADR-0013 decisions built and doc-truthed; #49 (implementation)
and #50 (doc truth-up) both closed. Full design detail:
[ADR-0013](docs/adr/0013-trade-bud-valuation-model.md),
[trade-bud-valuation.md](.claude/memory/trade-bud-valuation.md).

Shipped via PR [#52](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/52),
squash-merged to `main` as `d51a47e` (2026-08-03). Stale branches
`trade-bud-static-pages` and `pages-deploy-fix` both deleted.

## [ ] ACTIVE — trade-bud: post-merge browser walkthrough (2026-08-03)

Ben started a live browser walkthrough of #52 (`http://127.0.0.1:8500/`,
static export rebuilt off merged `main`) and found two frontend-only issues,
both fixed — full detail in
[mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md)'s "Post-ADR-0013
UI fixes" section:

1. Salary display (asset list + basket line) was reading `cap_hit` (zeroed
   for minors-exempt players) instead of `contract_value` (true salary) —
   fixed, cap math untouched.
2. Cap cards (`True Cap`/`Trade Result Cap`) moved from "Build a Trade" up
   into the My Profile / Counterparty panels per Ben's ask.
3. Counterparty "No reliable data signal — ask the owner directly" helper
   panel removed — the low/medium/high confidence chips already convey it.
4. `onTeamChange` never cleared `state.give`/`state.receive` on a team swap —
   stale assets (e.g. traded-away players) lingered in the basket and their
   cap_hit kept counting against the newly-selected team. Fixed: switching
   `myTeam` clears `give`, switching `cpTeam` clears `receive`.

**Flagged, not fixed (Ben chose "leave as-is for now")**: 29 rostered rows
have both `gsis_id` and `player_key` null (`capmath.roster_with_cap_hit()`),
so they render as null-name/`-`-age assets in the trade UI. 12 are
`acquired_method="claim"` (free-agency adds, `contract_value=$2,000,000`
flat) — the FA-claim ETL path never resolves player identity via the
Fantrax scorerId→gsis_id crosswalk. The other 17 are `acquired_method=
"startup_draft"` with null `contract_value` — a separate, older identity gap.
Root-caused to upstream ETL (likely `02d_fact_roster_transactions.py`'s
claim-handling), not fixable in `mouserat_trade-bud/` alone — revisit as its
own scoped task.

### ➡ NEXT ACTION

Open, unresolved: Ben reports "minor league contracts are $0 again."
Checked all 3 layers (source data via `roster_with_cap_hit()`, exported
`_site/data/assets/*.json`, served `_site/index.html`) — all already correct
(non-zero `contract_value` for Minors players, Salary column reads
`contract_value` not `cap_hit`). Root cause NOT found — leading guess was a
stale browser build; `export_static.py` was rerun and the `:8500` server
restarted against the fresh `_site/` this session, so ask Ben to hard-refresh
and re-check before any more code changes. Full investigation trail in
[mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md).

Committed to branch `fix/trade-bud-swap-basket-reset`
(`mouserat_trade-bud/frontend/index.html`, 3 fixes this session:
helper-panel removal, `onTeamChange` basket-clear bug, plus the earlier
salary/cap-card fixes). `export_static.py` reran and the `:8500` server
restarted against the fresh `_site/`, so Ben's live tab now reflects all
three fixes after a hard refresh. Not yet pushed/PR'd — waiting on Ben's
walkthrough sign-off before `gh pr create` (feature-branch-to-main
convention, same as #52).

## [ ] Active — dead money (3-version design, user building in PBI Desktop)

Three versions, per the 2026-07-11 design:

- **Current year**: `Dim_Contract[CapHitPct]` (by `contract_id`) x salary **at
  time of separation** x `relative_nfl_season_number = 0`.
- **Next year**: same at `relative_nfl_season_number = 1`.
- **Total**: needs design; the contract-cycle rows in `Dim_Contract` are there.

Blockers, both real: `dim_season` isn't in the semantic model yet, so nothing
can reference `relative_nfl_season_number` (BUILT 2026-07-11 in `01f`); and
there is **no `drop` event** in `fact_roster_transactions` — trades incur no cap
hit, only drops do, so the event type has to exist first.

## [ ] Active — Minors, open user actions only

Design closed: [ADR-0011](docs/adr/0011-minors-is-placement-not-contract.md)
(supersedes ADR-0010) — **there is no Minor contract type**. Minors is
eligibility (GP ≤ 19, Fantrax-computed) + placement (the team's lever, and the
sole cap exemption). `04v` is read-only; it is the sole writer of
`fact_roster_placement`. Full build detail in
`.claude/memory/project-fantasy-football.md`.

**Open, user-owned:** site eligibility condition 20 → 19 (pending
co-commissioner OK); locate the Fantrax commissioner CSV-import tool and report
its exact columns (`--export-fa-csv` writes the 5,341-row candidate file);
`dim_nfl_players` career-GP column (nflverse) as a cross-check on Fantrax's
count.

## ➡ NEXT

Immediately-buildable queue outside the trade-bud work is **drained** —
remaining items are externally gated (Wilson draft finishing, ADR-0006
captures, Sheets-API auth). Optional small buildables: surface
`dim_division`/`dim_season` in the PBI semantic model (also unblocks the
dead-money measures); the singular/plural table rename
(`Dim_FantasyTeams`→`Dim_FantasyTeam` etc., spec in
`powerbi-semantic-model.md` "Pending").

## [ ] Active / gated

1. **Ledger → both divisions (Wilson).** Both ingested through `02d`/`02e`
   (935 picks: Riddell 485/490, Wilson 450/490). USER re-runs
   `04w → 02d → 02e` as the remaining picks land. 122 picks have a null
   `contract_value` — Fantrax's own payload is missing `salary` on those
   (draft-in-progress, not an identity failure) — recheck once Wilson finishes.
2. **Draft-pick ownership & trades → [ADR-0006](docs/adr/0006-draft-pick-ownership-and-trades.md)**
   (design RESOLVED 2026-06-14). Gated on two user-driven per-division authed
   captures: `draftPicks.go` (ownership SSOT, current + forward, reflects
   trades) and `transactions/history;view=TRADE` (faithful multi-hop trade
   log). Then re-key `dim_draft_pick` → `(season, round, original_owner)`,
   every pick an `asset_id`, `trade` LIVE (one row per leg), ledger gains
   `transaction_id`, `fact_fantasy_teams` gains `acquired_by`/`acquired_via`.
   Forward seed = 28×5×{2027,2028} = 280. `CLAIM_DROP` deferred.
3. **Externally gated**: ADR-0005 Sheet **write**-sync (Sheets-API auth + PII
   go-ahead); Railway deploy of the merged discord bot (`railway.json` +
   crash-loop guards in place; runs locally only).

## [ ] Deferred — user requested

- [ ] `git filter-repo` history-scrub follow-up for `notebooks/.env` /
  `data/.pw_profile` (2026-05-30 incident) — user-owned, low urgency.

## [ ] Deferred — future

- [ ] In-season tables: `fact_nfl_player_stats`, `fact_nfl_season_injuries`
  (nflreadpy weekly) — per data-model "In-Season Tables (deferred)".
- [ ] Fabric migration: `pd.read/write_parquet` → `spark.read.parquet` /
  `abfss://` once the dynasty model settles (schema already migration-neutral).
- [ ] Prep-for-AI / Fabric Data Agent config for the dynasty semantic model,
  after PBI model cleanup.
- [ ] Generalize composite ADP blending (`ADP_KEYS`) beyond 2 sources when a
  3rd lands.
- [ ] **Revisit table architecture: merge `dim_rookie_prospect` into
  `dim_nfl_players`.** Hypothesis: rookies graduate into NFL players, so one
  registry keyed on the persistent player ID removes the prospect→player
  handoff and the dual-registry/crosswalk seams. **Planning task** — grill the
  design first (identity collisions, pre-draft rows without `gsis_id`,
  downstream FKs, PBI impact).
- [x] ~~Delete stale branches `trade-bud-static-pages` / `pages-deploy-fix`~~ —
  both deleted 2026-08-01; verified zero unique files against `main` first.

## Shipped (one-liners; full detail in ADR / MEMORY / data-model)

- **Trade-bud v2 valuation model** ([ADR-0013](docs/adr/0013-trade-bud-valuation-model.md),
  all 5 decisions built): decisions 1–3 (2026-07-31, PRs #36/#43) — sqrt-VOR
  position ceiling `dim_position_ceiling` (04e), DraftSharks two-tree pull
  (04f), stance routing, future-stance age tilt, pick stance scalars.
  `player_blended_values` and `_FORMAT_BY_POSITION_GROUP` deleted. Decisions
  4-5 (2026-08-01, #49, uncommitted) — pick/player quantile-mapping
  commensuration (`pick_value.py`) and age-tilt-folded-into-rank so `future`
  can't exceed 100 (`data_access.player_values`); `tests/test_pick_commensuration.py`
  added (6 tests, both invariants x 3 stances).
- **Trade-bud → GitHub Pages, fully static** ([ADR-0012](docs/adr/0012-static-export-for-trade-bud.md),
  2026-07-28, PRs #34/#35): `export_static.py` precomputes every endpoint from
  committed parquet — no server, database, or secrets. Live at
  <https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/>.
- **Minors = placement, not contract** ([ADR-0011](docs/adr/0011-minors-is-placement-not-contract.md),
  2026-07-26, PR #33, supersedes ADR-0010): the `Minor` contract type is void;
  `04v`'s write-side `--apply` path and commissioner worklist deleted.
- **Critical-review epic, 6 slices** (2026-07-13, PRs #25→#29+F): A apply
  pacing + FA CSV export · B `scripts/run_pipeline.py` phase-aware orchestrator
  with the allowlisted direct-to-main data commit · C `roster_status` cap
  honesty (kept players charge FULL contract value — `CapHitPct` is
  dead-money-only; the old math was a 2x league-wide understatement) · D model
  cleanup (stored `dead_money` dropped, `DivisionKey` composite relationship) ·
  E 17 derivable duplicate columns dropped from the TMDL model · F docs
  completeness.
- **First subagent roster** ([ADR-0009](docs/adr/0009-first-subagent-roster.md),
  2026-07-12): `fantrax-payload-analyst` (context firewall for the 16–32MB
  `data/raw/` payloads) + `cap-ledger-auditor` (adversarial pre-merge audit).
- **Regression-testing standard** ([ADR-0008](docs/adr/0008-regression-testing-standard.md),
  2026-07-11): `.venv` pytest scoped to `tests/`; `test_etl_helpers.py`;
  bot offline smoke made pytest-discoverable; `check_sources.py` wired into
  pre-commit.
- **2026 startup draft ingest + $500M→$300M cap change** (2026-07-11, PR #17),
  incl. the `04z` crosswalk universe fix and the `Fact_FantasyTeams` cap
  consistency fix (CapHit/Conference derived live, never ETL-frozen).
- **Machine-checked source manifest** ([ADR-0007](docs/adr/0007-machine-checked-source-manifest.md),
  2026-06-14): `docs/sources.yml` SSOT → `SOURCES.md` generated;
  `check_sources.py` does schema + notebook-exists + live token-match +
  reverse-drift.
- **Ledger v1** (ADR-0003/0004; PRs #12/#13/#15): `01f`→`dim_season`,
  `02d`→`dim_roster_asset`/`dim_draft_pick`/`fact_roster_transactions`,
  `02e`→derived `fact_fantasy_teams` + cap rollup, `05a` "Drafted By".
- **`dim_division` read-side** (ADR-0005, 2026-06-14): `01g` →
  `(season_id, conference)→division_name` from Sheet truth. Write-sync gated.
- **Owner-manifest read-side** (ADR-0005): Sheet `Fantrax-TeamId` → `01c` →
  `dim_fantasy_teams.fantrax_team_id` (28/28); heuristic crosswalk retired.
- **Discord bot expansion** (2026-06-14): shared `delivery.py` + `render.py`;
  `/adp`, `/player`, `/cap`, `/roster` added; offline smoke harness asserts
  embed limits.
- **Dynasty single-EAV refactor** ([ADR-0002](docs/adr/0002-discord-rankings-position-group.md),
  PRs #9/#10) + `rankings.py` rewritten on `position_group`.
- **`run.ps1`** launcher pins `.venv` (2026-06-14). Notebooks run headless via
  `.venv\Scripts\python.exe -m nbconvert --to notebook --execute --inplace`
  (**not** `python -m jupyter nbconvert` — PATH dispatch trap).

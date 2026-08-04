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

## [x] CLOSED — trade-bud: post-merge browser walkthrough (2026-08-03 → 2026-08-04)

Live browser walkthrough of #52 found and fixed 4 frontend issues (salary
display, cap-card placement, helper-panel removal, `onTeamChange` basket-swap
bug) plus a header/subtitle copy simplification. The "$0 minors contract"
report was chased down to a stale served `_site/` build (source was already
correct) — fixed by rebuilding + restarting the `:8500` server, not a code
change. Shipped via PR [#53](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/53),
squash-merged to `main`. Live at
<https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/>.
Full detail: [mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md).

**Flagged, not fixed (Ben chose "leave as-is for now")**: 29 rostered rows
have both `gsis_id` and `player_key` null. 17 are an older `acquired_method=
"startup_draft"` gap, out of scope for now. The other 12 (`acquired_method=
"claim"`) are the subject of the new wayfinder map below.

## [x] CLOSED — trade-bud: FA-claim identity gap map charted + a 2nd live-test bug (2026-08-04)

1. **Wayfinder map [#55](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/55)
   charted on GitHub**, with 2 child tickets wired via native GitHub
   sub-issue + blocked-by relationships:
   [#56](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/56)
   (Task: rerun `04z`+`02d`, measure the real remaining gap) and
   [#57](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/57)
   (Grilling: how to extend `04z`'s match universe, blocked by #56).
   Destination: spec for closing the FA-claim identity-resolution gap
   (12-row null-identity subset). Key reframe: identity resolution isn't
   broken for claims — `04z_fantrax_crosswalk.ipynb`'s match universe just
   never includes `04t` claim/drop scorer_ids, so a claimed player never
   ADP-ranked/draft-boarded has no crosswalk row. 9 of 12 known-null rows
   are likely just stale output (crosswalk already resolved them,
   `dim_roster_asset` wasn't rebuilt since). Full detail in
   [mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md). #56 is the
   frontier's first takeable item.
2. **2nd live-test bug found post-PR #53, fixed and shipped**: stale
   Give/Receive totals after a team swap that empties both baskets —
   `evaluateTrade()`'s early-return branch (`index.html:691-695`) never
   reset the total/bar DOM, so old numbers lingered. Shipped via PR
   [#54](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/54).

## [ ] ACTIVE — wayfinder map #55: FA-claim identity gap, ticket #56 done (2026-08-04)

**Tracker: [wayfinder map #55](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/55).**
Task ticket [#56](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/56)
closed — reran `04z_fantrax_crosswalk.ipynb` then `02d_fact_roster_transactions.py`,
shipped via PR [#58](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/58)
(merged to `main`). **Result: 22 of 23 known-null rows were stale output,
now resolved** (crosswalk had already resolved them 2026-07-31;
`dim_roster_asset`/`fact_roster_transactions` just hadn't rebuilt since
2026-07-26). **1 true gap remains: scorer_id `04cc5`** — claim-only, zero
rows in `dim_fantrax_crosswalk`, confirming the map's hypothesized
mechanism (`04z`'s match universe never unions in `04t` claim/drop
scorer_ids).

### ➡ NEXT ACTION

Pick up [#57](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/57)
(Grilling: how should 04z's match universe be extended?) — narrowed scope,
now a single confirmed case instead of the original 12-row estimate.

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

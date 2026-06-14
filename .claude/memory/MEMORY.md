# Memory Index — Python-PowerBI-DynastyFantasyFootball (project)

> Project-local memory. Cross-project preferences, terminology, and working
> method live in root (`C:\Users\benha\.claude\`). Last consolidated:
> 2026-06-14.

## Active Files

- [Fantasy Football Project](project-fantasy-football.md) — notebooks 01 dim / 02 fact / 03 rookie-rank / 04 dynasty-rank; shared etl_helpers.py; PBIP + discord_bot layers; feature-branch→main PRs (noreply email); .env hygiene remediated
- [Data Model Architecture](data-model.md) — star schema; registries (dim_nfl_players/dim_rookie_prospect); rookie/fantrax/dynasty pipelines; dynasty = single EAV fact (2026-06-12: backbone retired, ranks→source-prefixed keys, composite_adp, gsis on fact, source in dim); crosswalk identity; acquisition ledger `fact_roster_transactions` + derived `fact_fantasy_teams` + `dim_roster_asset`/`dim_draft_pick`(slot-keyed)/`dim_season` (**BUILT 2026-06-14**, ADR-0003/0004); owner manifest Fantrax→Sheet sync `dim_division` (ADR-0005, write-sync deferred)
- [Domain glossary](../../CONTEXT.md) — repo-root `CONTEXT.md`: canonical terms (Roster Asset/asset_id, Draft Pick, Sign vs Exercise, Season, Conference vs Division, Owner Manifest). Grill-with-docs maintains it inline.
- [Source manifest](../../docs/SOURCES.md) — `docs/SOURCES.md`: external-input boundary (Fantrax, Google Sheet, nflverse, KTC/FantasyPros/WalterFootball/DraftSharks/DynastySharks, manual Excel) with locator · auth-method · Feeds (notebook→table) · cadence. Internal lineage stays in data-model `Source` col + README.
- [Power BI Semantic Model](powerbi-semantic-model.md) — PBIP/TMDL model + PBIR report at pbi/mouserat2/; Fact_/Dim_ PascalCase (sourceColumn stays snake); rename-cascade; dynasty measures (latest-snapshot/avg) + 2026-06-12 single-EAV refactor; Prep-for-AI gates
- [Startup draft board 05a](startup-draft-board-05a.md) — `notebooks/05a_startup_draft_board.py`; composite weights, Offense/Defense split, judgment-overlay CSV, Yo-Yo runway (games-played) semantics, IDP/crosswalk quirks

## Decisions (ADRs)

- `docs/adr/0001-token-gated-grill-execute-loop.md` — runtime token-gating loop (grill→compact→execute, ~35% Opus budget, deferred Phase-0). General method mirrored in root `token-gating-loop.md`.
- `docs/adr/0002-discord-rankings-position-group.md` — discord rankings groups by `dim_nfl_players.position_group` (offense QB/RB/WR/TE, IDP DL/LB/DB) + re-ranks 1..N per field. Do NOT revert to granular `position`. Stage A rewrite landed + verified 2026-06-13.
- `docs/adr/0003-event-sourced-roster-transactions.md` — `fact_roster_transactions` (was `fact_dead_money_drafts`): event-sourced acquisition ledger = SSOT; `fact_fantasy_teams` DERIVED by replay; live-draft → 05a board. Key amended by ADR-0004. **BUILT + MERGED 2026-06-14 (PR #15)** (grill corrected `startup_auction`→`startup_draft`: a snake draft, not an auction). **Build amendment landed 2026-06-14** (Status→BUILT; built reality recorded in the ADR).
- `docs/adr/0004-polymorphic-asset-id.md` — polymorphic `asset_id` + `dim_roster_asset` unify player/prospect/pick; Sign = same asset, Exercise = new asset + lineage; `dim_draft_pick`, `dim_season` (`season_id` `"2026-2027"`); `pick_allocation`/`trade` dormant v1; valuation deferred. Glossary → `CONTEXT.md`. **BUILT 2026-06-14** — but `dim_draft_pick` is **slot-keyed** (`original_owner` deferred to `draftPicks.go`: startup picks were traded), superseding the planned `pick_ref=(season,round,original_owner)`. **Build amendment landed 2026-06-14** (Status→BUILT; `asset_id`=monotonic int, slot-keyed pick + `original_owner` deferred, Sheet identity all recorded in the ADR).
- `docs/adr/0005-owner-manifest-fantrax-to-sheet-sync.md` — Fantrax = upstream SSOT, Google Sheet = field-scoped synced mirror; join on `Fantrax-TeamId`; locked cols (Division/Team ID/Fantrax-TeamId) vs synced (name/abbr/emails); diff-only writes. **Read-side BUILT 2026-06-14**: Sheet now carries `Fantrax-TeamId`, `01c` ingests → `dim_fantasy_teams.fantrax_team_id` (lit up the ledger join). **Still deferred**: the Sheet **write**-sync (external-write+PII gate) + new `dim_division` `(season_id,conference)→name`.

## Directional shift (2026-06-13)

- Project-specific memory moved out of root global into this repo's `.claude/memory/`. Root now holds only cross-project (preferences, token-gating loop). `CLAUDE.md` + `PLAN.md` generated at repo root; first ADR created.
- Migrated `startup-draft-board-05a.md` here from the harness skills-CWD store (`~/.claude/projects/C--Users-benha--claude-skills/memory/`); that store now redirects to root+project. Memory tier model + Phase 0 algorithm: root `memory-architecture.md`.

## Shipped (2026-06-14)

- **All design work through 2026-06-13 is now MERGED to `main`** (PRs #9 refactor+docs, #10 bot; #9 first). Feature branches deleted; repo flat on `main`. `PLAN.md` is the live status board.
- **Grill seams built**: 04c generates its 6 Rank rows from `etl.SOURCE_PREFIX` (`prefix.upper()` = display abbrev; ADR/grill "Option B"); 05a keys `METRIC_MAP` by `metric_key` alone (each key owns one source — "Option A"). Both verified behavior-preserving.
- **Docs destaled + authored**: `docs/SOURCES.md` (new), `notebooks/README.md` + the `discord-bot-github-fetch` skill's `references/data-model.md` rewritten to the single-EAV/`position_group` board; `CLAUDE.md` gained the token-gating "Execution loop" pointer. `.claude/settings.local.json` untracked + gitignored (per-developer local).
- **Still deferred — externally gated**: owner-manifest Sheet sync (needs Sheets-API auth + PII go-ahead); Railway deploy of the merged bot. Designs locked in ADR-0005.

## Ledger v1 — BUILT + MERGED 2026-06-14 (PRs #12/#13/#15 → `main`; Riddell, `.venv`)

- **`fact_roster_transactions` ledger** (ADR-0003/0004) shipped S1–S4: `01f`→dim_season,
  `02d` (live-loop)→dim_roster_asset + dim_draft_pick + the startup_draft fact, `02e`→
  derived fact_fantasy_teams + cap rollup; `05a` gained a "Drafted By" availability column;
  team identity via the Sheet's new `Fantrax-TeamId` (01c) — heuristic crosswalk retired.
  **Full detail in [project-fantasy-football.md](project-fantasy-football.md) + schemas in
  [data-model.md](data-model.md).**
- ➡ **Open** (also in PLAN.md): user re-runs 04w for the **Wilson** draft (identity already
  28/28) → 02d/02e; `draftPicks.go` for `original_owner`/trades/forward picks; ADR-0003/0004/
  0005 text amendments → next Phase 0.

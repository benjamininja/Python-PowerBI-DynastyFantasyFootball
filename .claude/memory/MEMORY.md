# Memory Index — Python-PowerBI-DynastyFantasyFootball (project)

> Project-local memory. Cross-project preferences, terminology, and working
> method live in root (`C:\Users\benha\.claude\`). Last consolidated:
> 2026-06-14.

## Active Files

- [Fantasy Football Project](project-fantasy-football.md) — notebooks 01 dim / 02 fact / 03 rookie-rank / 04 dynasty-rank; shared etl_helpers.py; PBIP + discord_bot layers; feature-branch→main PRs (noreply email); .env hygiene remediated
- [Data Model Architecture](data-model.md) — star schema; registries (dim_nfl_players/dim_rookie_prospect); rookie/fantrax/dynasty pipelines; dynasty = single EAV fact (2026-06-12: backbone retired, ranks→source-prefixed keys, composite_adp, gsis on fact, source in dim); crosswalk identity; acquisition ledger `fact_roster_transactions` + derived `fact_fantasy_teams` (2026-06-13, ADR-0003); unified `asset_id`/`dim_roster_asset` over player/prospect/pick + `dim_draft_pick` + `dim_season` (2026-06-13, ADR-0004); owner manifest Fantrax→Sheet sync + `dim_division` (2026-06-13, ADR-0005)
- [Domain glossary](../../CONTEXT.md) — repo-root `CONTEXT.md`: canonical terms (Roster Asset/asset_id, Draft Pick, Sign vs Exercise, Season, Conference vs Division, Owner Manifest). Grill-with-docs maintains it inline.
- [Source manifest](../../docs/SOURCES.md) — `docs/SOURCES.md`: external-input boundary (Fantrax, Google Sheet, nflverse, KTC/FantasyPros/WalterFootball/DraftSharks/DynastySharks, manual Excel) with locator · auth-method · Feeds (notebook→table) · cadence. Internal lineage stays in data-model `Source` col + README.
- [Power BI Semantic Model](powerbi-semantic-model.md) — PBIP/TMDL model + PBIR report at pbi/mouserat2/; Fact_/Dim_ PascalCase (sourceColumn stays snake); rename-cascade; dynasty measures (latest-snapshot/avg) + 2026-06-12 single-EAV refactor; Prep-for-AI gates
- [Startup draft board 05a](startup-draft-board-05a.md) — `notebooks/05a_startup_draft_board.py`; composite weights, Offense/Defense split, judgment-overlay CSV, Yo-Yo runway (games-played) semantics, IDP/crosswalk quirks

## Decisions (ADRs)

- `docs/adr/0001-token-gated-grill-execute-loop.md` — runtime token-gating loop (grill→compact→execute, ~35% Opus budget, deferred Phase-0). General method mirrored in root `token-gating-loop.md`.
- `docs/adr/0002-discord-rankings-position-group.md` — discord rankings groups by `dim_nfl_players.position_group` (offense QB/RB/WR/TE, IDP DL/LB/DB) + re-ranks 1..N per field. Do NOT revert to granular `position`. Stage A rewrite landed + verified 2026-06-13.
- `docs/adr/0003-event-sourced-roster-transactions.md` — NEW `fact_roster_transactions` (was `fact_dead_money_drafts`): event-sourced acquisition ledger = SSOT; `fact_fantasy_teams` DERIVED by replay; live-draft → 05a board. Key amended by ADR-0004. **Build STARTED 2026-06-14** (grill corrected `startup_auction`→`startup_draft`: the startup is a snake draft, not an auction).
- `docs/adr/0004-polymorphic-asset-id.md` — polymorphic `asset_id` + `dim_roster_asset` unify player/prospect/pick; ledger key `gsis_id→asset_id`; Sign = same asset, Exercise = new asset + lineage; `dim_draft_pick` (`pick_ref` stable under trade), `dim_season` (`season_id` `"2026-2027"`); picks event-sourced via `pick_allocation` (trade dormant v1); valuation deferred. Glossary → `CONTEXT.md`. Build deferred.
- `docs/adr/0005-owner-manifest-fantrax-to-sheet-sync.md` — Fantrax = upstream SSOT, Google Sheet = field-scoped synced mirror; join on `Fantrax-TeamId`; locked cols (Division/Team ID/Fantrax-TeamId) vs synced (name/abbr/emails); diff-only writes, soft-fail unmatched; Sheet both read(01c)+written(sync); `01c` maps `fantrax_team_id`; new `dim_division` `(season_id,conference)→name` (seasonal label, no downstream IF). External-write+PII gate at build. Build deferred.

## Directional shift (2026-06-13)

- Project-specific memory moved out of root global into this repo's `.claude/memory/`. Root now holds only cross-project (preferences, token-gating loop). `CLAUDE.md` + `PLAN.md` generated at repo root; first ADR created.
- Migrated `startup-draft-board-05a.md` here from the harness skills-CWD store (`~/.claude/projects/C--Users-benha--claude-skills/memory/`); that store now redirects to root+project. Memory tier model + Phase 0 algorithm: root `memory-architecture.md`.

## Shipped (2026-06-14)

- **All design work through 2026-06-13 is now MERGED to `main`** (PRs #9 refactor+docs, #10 bot; #9 first). Feature branches deleted; repo flat on `main`. `PLAN.md` is the live status board.
- **Grill seams built**: 04c generates its 6 Rank rows from `etl.SOURCE_PREFIX` (`prefix.upper()` = display abbrev; ADR/grill "Option B"); 05a keys `METRIC_MAP` by `metric_key` alone (each key owns one source — "Option A"). Both verified behavior-preserving.
- **Docs destaled + authored**: `docs/SOURCES.md` (new), `notebooks/README.md` + the `discord-bot-github-fetch` skill's `references/data-model.md` rewritten to the single-EAV/`position_group` board; `CLAUDE.md` gained the token-gating "Execution loop" pointer. `.claude/settings.local.json` untracked + gitignored (per-developer local).
- **Still deferred — externally gated**: owner-manifest Sheet sync (needs Sheets-API auth + PII go-ahead); Railway deploy of the merged bot. Designs locked in ADR-0005.

## Ledger v1 — BUILT + VERIFIED 2026-06-14 (Riddell capture, `.venv`)

- **`fact_roster_transactions` ledger** (ADR-0003/0004) shipped S1–S4. New files:
  `01f_dim_season_seed.ipynb` (dim_season),
  `02d_fact_roster_transactions.py` (live-loop parse →
  `dim_roster_asset` monotonic `asset_id` on `scorer_id` + `dim_draft_pick` slot grid
  + `fact_roster_transactions` startup_draft rows; contract `1st` yr1,
  `contract_value`=Fantrax salary, cap_hit 0.50×), `02e_fact_fantasy_teams_derive.py`
  (replay → 12-col `fact_fantasy_teams` + dim_fantasy_teams cap rollup). 05a got a
  non-destructive "Drafted By" availability column.
- **Team identity = Sheet `Fantrax-TeamId`** (ADR-0005 locked col, added to the Sheet
  2026-06-14). `01c` ingests it → `dim_fantasy_teams.fantrax_team_id` (28/28); 02d
  joins teamId→team_key off it. A name-match heuristic crosswalk was built then
  **retired** once the Sheet column landed (it had inferred the right mappings). 01c
  also refreshes drifted team names.
- **Findings**: 137/137 picks resolve to gsis_id+salary; **startup picks WERE traded**
  → getDraftResults `teamId`=current owner, so `dim_draft_pick` keyed on slot
  `(draft_season,divisionId,overall_slot)`, `original_owner` null (needs `draftPicks.go`).
  `pick_allocation`/`trade` dormant v1.
- ➡ **Open**: user re-runs 04w for Wilson draft capture (identity already 28/28; then 02d+02e);
  `draftPicks.go` for original_owner/forward picks; ADR-0003/0004 amendments → Phase 0.
- Pre-build PRs still open: #12 (`clean_name_for_match` DRY), #13 (plan + HAR doc).
  This build is **uncommitted** on `plan-ledger-v1-grill`. Detail → PLAN.md.

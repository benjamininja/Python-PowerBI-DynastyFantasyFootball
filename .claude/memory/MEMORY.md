# Memory Index — Python-PowerBI-DynastyFantasyFootball (project)

> Project-local memory. Cross-project preferences, terminology, and working
> method live in root (`C:\Users\benha\.claude\`). Last consolidated:
> 2026-06-13.

## Active Files

- [Fantasy Football Project](project-fantasy-football.md) — notebooks 01 dim / 02 fact / 03 rookie-rank / 04 dynasty-rank; shared etl_helpers.py; PBIP + discord_bot layers; feature-branch→main PRs (noreply email); .env hygiene remediated
- [Data Model Architecture](data-model.md) — star schema; registries (dim_nfl_players/dim_rookie_prospect); rookie/fantrax/dynasty pipelines; dynasty = single EAV fact (2026-06-12: backbone retired, ranks→source-prefixed keys, composite_adp, gsis on fact, source in dim); crosswalk identity; acquisition ledger `fact_roster_transactions` + derived `fact_fantasy_teams` (2026-06-13, ADR-0003); unified `asset_id`/`dim_roster_asset` over player/prospect/pick + `dim_draft_pick` + `dim_season` (2026-06-13, ADR-0004); owner manifest Fantrax→Sheet sync + `dim_division` (2026-06-13, ADR-0005)
- [Domain glossary](../../CONTEXT.md) — repo-root `CONTEXT.md`: canonical terms (Roster Asset/asset_id, Draft Pick, Sign vs Exercise, Season, Conference vs Division, Owner Manifest). Grill-with-docs maintains it inline.
- [Power BI Semantic Model](powerbi-semantic-model.md) — PBIP/TMDL model + PBIR report at pbi/mouserat2/; Fact_/Dim_ PascalCase (sourceColumn stays snake); rename-cascade; dynasty measures (latest-snapshot/avg) + 2026-06-12 single-EAV refactor; Prep-for-AI gates
- [Startup draft board 05a](startup-draft-board-05a.md) — `notebooks/05a_startup_draft_board.py`; composite weights, Offense/Defense split, judgment-overlay CSV, Yo-Yo runway (games-played) semantics, IDP/crosswalk quirks

## Decisions (ADRs)

- `docs/adr/0001-token-gated-grill-execute-loop.md` — runtime token-gating loop (grill→compact→execute, ~35% Opus budget, deferred Phase-0). General method mirrored in root `token-gating-loop.md`.
- `docs/adr/0002-discord-rankings-position-group.md` — discord rankings groups by `dim_nfl_players.position_group` (offense QB/RB/WR/TE, IDP DL/LB/DB) + re-ranks 1..N per field. Do NOT revert to granular `position`. Stage A rewrite landed + verified 2026-06-13.
- `docs/adr/0003-event-sourced-roster-transactions.md` — NEW `fact_roster_transactions` (was `fact_dead_money_drafts`): event-sourced acquisition ledger = SSOT; `fact_fantasy_teams` DERIVED by replay; live-draft → 05a board. Build deferred. Key amended by ADR-0004.
- `docs/adr/0004-polymorphic-asset-id.md` — polymorphic `asset_id` + `dim_roster_asset` unify player/prospect/pick; ledger key `gsis_id→asset_id`; Sign = same asset, Exercise = new asset + lineage; `dim_draft_pick` (`pick_ref` stable under trade), `dim_season` (`season_id` `"2026-2027"`); picks event-sourced via `pick_allocation` (trade dormant v1); valuation deferred. Glossary → `CONTEXT.md`. Build deferred.
- `docs/adr/0005-owner-manifest-fantrax-to-sheet-sync.md` — Fantrax = upstream SSOT, Google Sheet = field-scoped synced mirror; join on `Fantrax-TeamId`; locked cols (Division/Team ID/Fantrax-TeamId) vs synced (name/abbr/emails); diff-only writes, soft-fail unmatched; Sheet both read(01c)+written(sync); `01c` maps `fantrax_team_id`; new `dim_division` `(season_id,conference)→name` (seasonal label, no downstream IF). External-write+PII gate at build. Build deferred.

## Directional shift (2026-06-13)

- Project-specific memory moved out of root global into this repo's `.claude/memory/`. Root now holds only cross-project (preferences, token-gating loop). `CLAUDE.md` + `PLAN.md` generated at repo root; first ADR created.
- Migrated `startup-draft-board-05a.md` here from the harness skills-CWD store (`~/.claude/projects/C--Users-benha--claude-skills/memory/`); that store now redirects to root+project. Memory tier model + Phase 0 algorithm: root `memory-architecture.md`.

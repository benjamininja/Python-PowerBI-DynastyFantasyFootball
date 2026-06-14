# PLAN.md

Scratchpad for active/upcoming work. Expected to drift — completed items
collapse to one-liners once their durable signal lands in an ADR / MEMORY /
data-model. Blow-by-blow does NOT live here.

> **Runtime token-gating** (see [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)):
> loop is `grill/plan → (Phase 0 consolidate) → compact → execute stage →
> compact → … ↺`. Compact at **~35% window (Opus)**. PLAN.md = heartbeat;
> Memory/ADR/CONTEXT = real signal, batched into Phase 0.

## Working state (2026-06-14)
- Branch **`ledger-followups`** holds all uncommitted work; `main` = `origin/main`
  (clean — **never commit direct to main; feature branch → PR**). Committed on the
  branch: `run.ps1`, ADR-0003/4 build amendments, ledger parquet refresh.
  **Uncommitted on the branch** (grill output): ADR-0006 + `CONTEXT.md` terms +
  ADR-0007 + `sources.yml`/`check_sources.py`/`scripts/requirements.txt` +
  regenerated `SOURCES.md` + this PLAN + MEMORY index.
- Launch `.py` scripts via `.\run.ps1 <script.py>` (pins `.venv`; anaconda base
  lacks playwright + has broken pyarrow). Tooling deps (PyYAML) in
  `scripts/requirements.txt`, installed into `.venv`.

## ➡ NEXT
Immediately-buildable queue is **drained** — remaining work is externally gated
(Wilson draft, ADR-0006 captures, Sheets-API; see Active/gated). Optional small
buildables when ready: wire `check_sources.py` into a pre-commit hook (ADR-0007
deferred item); surface `dim_division` in the PBI semantic model (join
`Dim_FantasyTeams.conference`).

## [ ] Active / gated
1. **Ledger → both divisions (Wilson).** 04w capture proven for BOTH divisions
   this session; **Wilson draft not started (0/490)** — nothing to ingest there
   yet. Riddell at 138. `02d`/`02e` scale automatically once Wilson drafts; USER
   re-runs `04w → 02d → 02e` as Wilson picks land. Team identity already 28/28.
2. **Draft-pick ownership & trades build → [ADR-0006](docs/adr/0006-draft-pick-ownership-and-trades.md)**
   (design RESOLVED 2026-06-14 via `/grill-with-docs`). Gated on **two**
   user-driven per-division authed captures, then extend `02d`/`02e` + add
   04-series capture scripts:
   - **`draftPicks.go`** (`?season=…&viewType=TEAM&divisionId=…`) = pick-ownership
     SSOT (current + forward; reflects trades). Supersedes `getDraftResults` as the
     ownership source (04w = live-draft made-pick attribution only).
   - **`transactions/history;view=TRADE`** = faithful multi-hop trade log.
   - Re-key `dim_draft_pick` → `(season, round, original_owner)`; every pick an
     `asset_id` (Option I); `trade` LIVE (one row/leg, `from_team_key`+`trade_id`,
     all legs, player-leg cap deferred); `pick_allocation` dormant; ledger gains
     `transaction_id`; `fact_fantasy_teams` gains `acquired_by`/`acquired_via` +
     draft `via_asset_id`; `current_owner`←draftPicks.go, `original_owner`
     deterministic (position + base order), trade-replay = reconciliation check.
     Forward seed = 28×5×{2027,2028}=280. `CLAIM_DROP` (fa_pickup/drop) deferred.
3. **Externally gated** (need user auth / accounts):
   - ADR-0005 Sheet **write**-sync (Sheets-API auth + PII go-ahead). (The
     read-side `dim_division` is buildable now — see ➡ NEXT.)
   - Railway deploy of the merged discord bot (`railway.json` + crash-loop guards
     in place; runs locally only).

## [ ] Deferred - User Requested
- [ ] Additional Discord bot commands (`player`, `adp`) — v1 scoped to `rankings`.
- [ ] `git filter-repo` history-scrub follow-up for `notebooks/.env` /
  `data/.pw_profile` (2026-05-30 incident) — user-owned, low urgency.

## [ ] Deferred - Future
- [ ] In-season tables: `fact_nfl_player_stats`, `fact_nfl_season_injuries`
  (nflreadpy weekly) — per data-model "In-Season Tables (deferred)".
- [ ] Fabric migration: `pd.read/write_parquet` → `spark.read.parquet`/`abfss://`
  once the dynasty model settles (schema already migration-neutral).
- [ ] Prep-for-AI / Fabric Data Agent config for the dynasty semantic model
  (`semantic-modeling-prepforai`), after PBI model cleanup.
- [ ] Generalize composite ADP blending (`ADP_KEYS`) beyond 2 sources when a 3rd lands.

## Shipped (one-liners; full detail in ADR / MEMORY / data-model)
- **Dynasty single-EAV refactor** (ADR-0002) + Discord `rankings.py` rewrite
  (`position_group`, re-rank 1..N) + 04z gsis-collision soft-fail. PRs #9/#10.
- **Ledger v1** (ADR-0003/0004; PRs #12/#13/#15): `01f`→dim_season,
  `02d`→dim_roster_asset/dim_draft_pick/fact_roster_transactions,
  `02e`→derived fact_fantasy_teams + cap rollup, 05a "Drafted By". Riddell 138.
- **ADR-0003/0004 build amendments** + 02d docstring fix (Phase 0, 2026-06-14).
- **Grill seams**: 04c rank rows from `SOURCE_PREFIX` (Option B); 05a `METRIC_MAP`
  by `metric_key` (Option A). Both verified behavior-preserving.
- **Owner-manifest read-side** (ADR-0005): Sheet `Fantrax-TeamId` → `01c` →
  `dim_fantasy_teams.fantrax_team_id` (28/28); heuristic 01g retired.
- **`docs/SOURCES.md`** external-input boundary manifest (9 live + 3 planned rows).
- **Consolidations**: shared `clean_name_for_match` (04z); LeagueConfig sweep (04a
  standalone by design); `.claude/settings.local.json` untracked+ignored;
  CLAUDE.md token-gating pointer; notebooks/README + bot-skill data-model → EAV;
  PBI orphan `Fact_DynastyRankings` removed; dynasty pipeline rerun on regen parquet.
- **`run.ps1`** launcher pins `.venv` (2026-06-14).
- **Machine-checked source manifest** ([ADR-0007](docs/adr/0007-machine-checked-source-manifest.md),
  2026-06-14): `docs/sources.yml` SSOT → `SOURCES.md` tables generated;
  `scripts/check_sources.py` (`validate`/`--render`/`--check`) does schema +
  notebook-exists + token-match (live, hard-fail) + reverse-drift (WARN). 9 live
  sources validate clean.
- **`dim_division` read-side** (ADR-0005, 2026-06-14): `01g_dim_division_seed.ipynb`
  → `dim_division.parquet`, `(season_id, conference)→division_name` derived from
  the Sheet truth (v1 = 2026-2027: A→Riddell, B→Wilson). Sheet write-sync stays gated.

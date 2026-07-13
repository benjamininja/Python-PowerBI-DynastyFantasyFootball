# PLAN.md

Scratchpad for active/upcoming work. Expected to drift — completed items
collapse to one-liners once their durable signal lands in an ADR / MEMORY /
data-model. Blow-by-blow does NOT live here.

> **Runtime token-gating** (see [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)):
> loop is `grill/plan → (Phase 0 consolidate) → compact → execute stage →
> compact → … ↺`. Compact at **~35% window (Opus)**. PLAN.md = heartbeat;
> Memory/ADR/CONTEXT = real signal, batched into Phase 0.

## Working state (2026-07-12)

- The 2026-07-11 uncommitted slate below **landed on `main`** as PR #17
  ("2026 startup draft ingest, $300M cap change, cap-consistency fixes") —
  the branch-and-uncommitted framing is stale history now, kept for detail.
- **Subagent audit run (2026-07-12, uncommitted)**: first run of the
  `subagent-audit` skill (`skills-plugins-hooks-agents` PR #22) against
  this repo. Outcome: two read-only subagents defined in
  `.claude/agents/` — `fantrax-payload-analyst` (context firewall + typed
  schema/drift analysis for the 16–32MB `data/raw/` payloads) and
  `cap-ledger-auditor` (adversarial pre-merge audit of
  cap/contract/ledger logic, grounded in ADR-0003/0004/0006/0008) — plus
  [ADR-0009](docs/adr/0009-first-subagent-roster.md) recording the
  accepted and rejected-with-reason candidates. Awaiting "commit when
  asked".

## 2026-07-11 detail (landed as PR #17)
- Branch **`data-2026-draft-cap-update`**, off `main` (`b89671c`). Uncommitted:
  2026 startup-draft ingest (**both divisions live and ingested through
  `02d`/`02e`**: Riddell 485/490, Wilson 450/490, 935 total picks — re-run
  `04w → 02d → 02e` to refresh as picks finish), $500M→$300M cap change, `04z`
  crosswalk universe fix (draft-only scorer_ids), `requirements.txt`,
  `Fact_FantasyTeams`/`Dim_FantasyTeams` cap-consistency fix (`CapHit`/
  `Conference`/the old ETL rollup all removed as stored columns — derived live
  via relationships/measures instead), `discord_bot/capmath.py`,
  `dim_season.relative_nfl_season_number` + self-extending anchor+2 horizon
  (`01f`, floats off today's date, never drops history).
  Full detail: project-fantasy-football.md "Cap architecture", powerbi-semantic-model.md
  "No ETL-frozen rollups", data-model.md `dim_season` row.
- Launch `.py` scripts via `.\run.ps1 <script.py>` (pins `.venv`). Notebooks run
  headless via `.venv\Scripts\python.exe -m nbconvert --to notebook --execute
  --inplace <nb>.ipynb` (not `python -m jupyter nbconvert` — PATH dispatch trap).
  `requirements.txt` (repo root) is now the `.venv` dependency source of truth.
- **Not yet done, agreed scope**: singular/plural table rename (`Dim_FantasyTeams`
  →`Dim_FantasyTeam`, `Dim_NFLPlayers`→`Dim_NFLPlayer`, `Dim_NFLTeams`→
  `Dim_NFLTeam`) — spec in powerbi-semantic-model.md "Pending" section, agreed
  to land as its own commit on this same branch.
- **Nothing committed this session** — everything above is uncommitted working-tree
  state per standing "commit only when asked" rule.

## [ ] Active — dead money (3-version design, in progress in PBI Desktop by user)
User is building this live in `_Measures.tmdl` (`'Dead Money Active - Current
Year'`, `'Dead Money Cap Hit - Current Year'` already exist, WIP). Design as
described 2026-07-11: three versions —
- **`dim_season.relative_nfl_season_number` — BUILT 2026-07-11** (`01f`, ADR-0004
  calendar spine): 0 = the season whose `season_fantasy_start_date`/`_end_date`
  window contains today (anchor), negative = past, positive = future.
  Recomputed every `01f` run from the current date. Not yet wired into a PBI
  relationship (`dim_season` isn't in the semantic model yet) — needed before
  the dead-money measures below can actually reference it.
- **Current year**: `Dim_Contract[CapHitPct]` (looked up by `contract_id`) x
  the player's salary **at time of separation** x
  `relative_nfl_season_number = 0`.
- **Next year**: same, at `relative_nfl_season_number = 1`.
- **Total**: needs more design; the mechanics (contract cycle rows in
  `Dim_Contract`) are already there.
- Must track **when a player is actually dropped** — trades do NOT incur a cap
  hit/dead money, only drops do. No `drop` event exists in
  `fact_roster_transactions` yet (ADR-0003/0004 ledger only has `startup_draft`
  in v1) — this needs that event type built out first.
- Ties directly into the Minor League/draft-transition task below (drops are
  how a team moves a player to make Minor League room, or cuts for cap space).

## [ ] Active — Yo-Yo Rule contract automation (Minor ↔ 1st) — read-side built
**Design settled via grilling 2026-07-12; read-side BUILT same day**
(branch `yo-yo-minor-contracts`, uncommitted). Settled rule: every player with
career+current regular-season GP ≤ 19 holds a **Minor** contract league-wide
(rostered or FA); the 20th game graduates them to **1st**, and the 3-year clock
starts at the **graduation season** (Minor years don't burn contract years).
Cap exemption follows **Minors-squad placement** (team choice — salary charged
if kept active); the Minor *contract* grants squad eligibility + 0% drop
penalty. **Fantrax computes eligibility itself** (league setting "Career+
Current GP <=" — USER to fix site condition 20 → 19, both Offense + Individual
Defense rows); we read its verdict, never re-derive it.
- **Built — `notebooks/04v_minor_contracts.py`** (scraper cluster, imports 04a,
  runs after 04a on the weekly schedule): pulls `getPlayerStats` with
  `statusOrTeamFilter=MINOR_FANTASY_AVAILABLE|TAKEN` (site eligibility) +
  `getTeamRosterInfo` × 28 teams (placement: row `statusId` 1=Active/2=Reserve/
  9=Minors via `statusTotals`; contract = `Con` header) → writes
  `fact_roster_placement` (grain **team × scorer × season × week** — duplicate-
  player league, one copy per conference; replace-by-(season,week)) + worklist
  `data/review/review_contract_actions.csv`. Verified on live pulls 2026-07-12:
  991 placement rows (420 Active/469 Reserve/102 Minors), 5,513 eligible
  (union of both filter buckets — TAKEN alone misses rostered FA-contract
  copies), startup worklist = 202 rostered 1st→Minor + 5,311 FA→Minor.
- **Next (in order)**: (1) `--apply` mode — replay the worklist through
  Fantrax's commissioner contract-edit endpoint; **USER captures the request
  shape** (one manual contract edit with DevTools recording — request bodies
  survive the service-worker HAR gap). Opt-in flag, never unattended; explicit
  scoped exception to the no-write-side rule per grill sign-off. (2) `02d`
  ledger events `minor_assignment` (startup batch, dated at draft completion) +
  `minor_graduation` (payload: new contract_id, salary, graduation season);
  `02e` replay derives contract type, `contract_year` advancement keys off
  graduation season. (3) capmath/PBI: charge Active+Reserve salaries, exempt
  Minors placement (join `fact_roster_placement`). (4) `dim_nfl_players`
  career-GP column (nflverse) as a cross-check monitor vs Fantrax's count,
  reported early-season. Ties into the dead-money work above (a Minor drop is
  penalty-free by contract rule).

## ➡ NEXT
Immediately-buildable queue is **drained** — remaining work is externally gated
(Wilson draft finishing, ADR-0006 captures, Sheets-API; see Active/gated).
Optional small buildables when ready: surface `dim_division`/`dim_season` in
the PBI semantic model (join `Dim_FantasyTeams.conference`; `dim_season` also
needed before the dead-money measures can reference
`relative_nfl_season_number`, see Active above); the singular/plural table
rename (see Working state).

## [ ] Active / gated
1. **Ledger → both divisions (Wilson) — status 2026-07-11: near-complete, not
   done.** Both divisions ingested through `02d`/`02e` (935 picks total):
   Riddell 485/490, Wilson 450/490. USER re-runs `04w → 02d → 02e` as the
   remaining Wilson picks land. 122 picks currently have a null
   `contract_value` — Fantrax's own payload missing `salary` on those specific
   picks (draft-in-progress state, unrelated to identity resolution) — recheck
   once Wilson finishes.
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
- [ ] **Revisit table architecture: merge `dim_rookie_prospect` into `dim_nfl_players`.**
  Hypothesis (user): rookies graduate into NFL players, so one registry keyed on
  the recently-developed **persistent player ID** (confirm which during planning —
  `player_key` / `gsis_id` / asset lineage) removes the prospect→player handoff
  and the dual-registry/crosswalk seams. **Planning task** — grill the design
  before building (identity collisions, pre-draft rows without `gsis_id`, downstream
  FKs in rookie-ranking + dynasty + ledger tables, PBI model impact). **Work to be
  done on `pbi-dim-division-integration`.**

## Shipped (one-liners; full detail in ADR / MEMORY / data-model)
- **Discord bot expansion** (branch `discord-bot-expand`, 2026-06-14): extracted
  shared `delivery.py` (privacy routing + ShareView + `respond_with_embeds`) +
  `render.py` (embed pagination); rebuilt `rankings.py` on them; added 4 commands
  — `/adp` (Fantrax ADP + league-owner overlay), `/player` (curated card), `/cap`
  (conference cap standings via dim_division), `/roster` (team contracts +
  empty-state). Offline harness `tests/offline_smoke.py` asserts embed limits for
  all 5. No new deps; `github_fetch` unchanged.
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
- **Regression-testing standard** ([ADR-0008](docs/adr/0008-regression-testing-standard.md),
  2026-07-11): `pyproject.toml` scopes `.venv` pytest to `tests/`;
  `tests/test_etl_helpers.py` unit-tests the pure `etl_helpers.py` functions;
  `discord_bot/tests/offline_smoke.py` renamed to `test_offline_smoke.py`
  (pytest-discoverable, same assertions); `.pre-commit-config.yaml` wires
  `check_sources.py validate` (the ADR-0007 deferred item, now done). CI and
  Python lint/format logged as deliberately deferred, not built this pass.

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
  copies), startup worklist = 357 rostered copies 1st→Minor + 5,341 FA→Minor.
- **Pre-merge cap-ledger audit (2026-07-12) drove two fixes**: (1) contract is
  **per roster copy**, not per player (verified live: 3 post-draft FA signings
  hold 1st in one conference, FA in the other) → diff acts per (team, scorer);
  (2) players who graduate while sitting in the FA pool vanish from both pulls
  → new `fact_minor_eligibility` weekly snapshot + week-over-week vanish
  detection (flagged needs_verification). Unit tests
  `tests/test_04v_minor_contracts.py` (ADR-0008) pin both; `docs/sources.yml`
  gained the `fantrax_minor_contracts` entry (lean-import blind spot noted).
- **Ledger events BUILT 2026-07-12** (branch `yo-yo-ledger-events`, stacked on
  the 04v PR): `02d` derives `minor_assignment`/`minor_graduation` from
  **observed** per-copy contract transitions across `fact_roster_placement`
  snapshot history (event dated at the capture where the new state first
  appears — reflects what the site shows, not worklist intent). `event_seq =
  1000 + snapshot ordinal` so `02e`'s last-event-wins replay ranks flips after
  startup picks (max slot 490); `02e`'s `acquired_method` now comes from the
  copy's FIRST event (contract-state events must not masquerade as
  acquisitions). Rebuilt-from-history each run, replace-by-(season_id,
  event_type) → idempotent. Verified via simulated wk01/wk02 snapshots:
  assignments at cap_hit 0, graduation at 1st/50%, replay ordering correct.
  A copy vanishing while Minor = a **drop** — still out of scope until the
  drop event type exists (dead-money work above).
- **`--apply` mode BUILT 2026-07-13** (branch `yo-yo-apply-mode`). Endpoint
  captured via Playwright network listener replaying the user's recorded UI
  flow (flip-and-revert on A10): `confirmOrExecuteTeamRosterChanges`,
  TWO-PHASE (confirm:true then execute), whole-roster `fieldMap` keyed by
  scorer_id `{posId, stId, sal, csId}`. csId enum comes from the adminMode
  `getTeamRosterInfo` response's `miscData.contractChoices` (1st=0 … Minor=8,
  FA=9) — read live, never hardcoded; the Con cell carries `{'content','id'}`.
  Apply = per team: fresh adminMode pull → rebuild fieldMap verbatim → mutate
  ONLY target csIds → confirm → execute → re-pull verify. Flags: `--apply`,
  `--dry-run`, `--teams`, `--max-teams`; opt-in only, never scheduled.
  FA-copy actions are skipped (no roster fieldMap) — they **self-correct on
  signing** (copy lands on a roster → next weekly diff flips it). Dry-run
  verified on A10: 15 changes, csId 0→8, no failures.
- **Apply hardening (Slice A) BUILT 2026-07-13** (same branch): jittered
  pacing — `PULL_DELAY_S` (0.5–1.5s between read pulls) and
  `APPLY_TEAM_DELAY_S` (3–5s between teams during --apply; confirm/execute/
  verify within a team stay back-to-back, matching the UI's own timing).
  Startup apply = one sitting (~28 teams × 4 POSTs + delays, a few minutes).
  FA copies: `--export-fa-csv` writes `data/review/fa_contract_import.csv`
  (Player/Position/Team/Salary/Contract/FantraxID, 5,341 rows) for Fantrax's
  commissioner CSV-import tool — exact expected headers TBD until the user
  locates the tool in League Admin; iterate once against a real upload.
  Automation of the FA import deferred until a few monitored manual sessions.
- **Next**: (1) USER runs the startup apply (`.\run.ps1
  notebooks\04v_minor_contracts.py --apply` after eyeballing `--dry-run`;
  then re-run `04v → 02d → 02e` so the ledger picks up the observed flips).
  (2) capmath/PBI: charge Active+Reserve salaries, exempt Minors placement
  (Slice C of the approved orchestration/model plan; PBI half needs Desktop
  closed). (3) `dim_nfl_players` career-GP column (nflverse) as a cross-check
  monitor vs Fantrax's count. **USER actions open**: site eligibility
  condition 20 → 19 (pending co-commissioner confirmation); startup apply
  run; locate the commissioner contract CSV-import tool + report its columns.

## [ ] Active — pipeline orchestration + model normalization (approved plan, 6 slices)
Grill/plan session 2026-07-13 (plan file: `~/.claude/plans/
critically-review-our-graceful-nebula.md`). Slices: **A** apply pacing + FA
CSV export (landed on PR #25) → **B** orchestrator → **C** roster_status cap
honesty (02e → capmath → PBI, auditor gate) → **D** model cleanup (DeadMoney
drop, Dim_Season desc, Conference relationship, auditor gate) → **E** full PBI
normalization → **F** docs. One PR per slice.
- **Slice B BUILT 2026-07-13** (branch `pipeline-orchestrator`):
  `scripts/run_pipeline.py` — phase-aware (INSEASON/PRESEASON/OFFSEASON from
  04a week label + season calendar; February clamp edge fixed), dependency-
  ordered subprocess steps (`01f → 01e → 04a → 04z → backfill-gp (in-season)
  → 04v → 02d → 02e → 04b (offseason)`), review-queue surfacing, allowlisted
  `data/*.parquet` direct-to-main commit (pathspec-verified, change-detected,
  autostash rebase, main-branch-only guard), Discord webhook notify
  (`DISCORD_WEBHOOK_URL`, optional). `run_weekly.ps1` (Task Scheduler entry,
  console logs to `data/outputs/pipeline_runs/`),
  `scripts/register_scheduled_task.ps1` (reproducible task registration,
  Thu 06:00 default; daily reconciliation later = one-line trigger change).
  04a gained argparse `--backfill-gp` + `--season N` (always lands week="YTD" —
  a numeric week would clobber the board partition in load_fact). Exception
  codified in CONTRIBUTING.md + CLAUDE.md. NOT scheduled: 04w draft chain,
  03-group, review applies, `04v --apply`. Phase-2 guarded auto-apply
  designed, not built (state file + anomaly halt; see plan file).

## [ ] Active — pipeline orchestration + model normalization (approved plan, 6 slices)
Grill/plan session 2026-07-13 (plan file: `~/.claude/plans/
critically-review-our-graceful-nebula.md`). Slices: A apply pacing/FA CSV
(PR #25) → B orchestrator (PR #26) → **C cap honesty (this branch)** → D model
cleanup → E full PBI normalization → F docs. One PR per slice.
- **Slice C BUILT 2026-07-13** (branch `roster-status-cap-honesty`):
  `roster_status` (Active/Reserve/Minors) stamped by 02e from the latest
  `fact_roster_placement` snapshot on (team_key, scorer_id); Minors PLACEMENT
  = cap-exempt in capmath (cap_hit 0 + cap_exempt flag), 02e summary, and the
  DAX 'Active Roster Salary' / 'Remaining Salary Cap' measures
  (RosterStatus <> "Minors"; blank charges). New `Fact_FantasyTeams.
  RosterStatus` TMDL column.
- **Cap-ledger audit findings FIXED in the same slice**: (1) capmath/02e
  multiplied kept-player charges by `cap_hit_pct` — but CapHitPct is
  DEAD-MONEY-ONLY (the DAX measure's own comment); a kept player charges FULL
  contract_value. Was a 2x understatement league-wide and silently
  zero-charged Minor-CONTRACT players kept active (pct 0.0). Both now charge
  full value; placement is the only exemption lever. (2) New 02e reverse
  check surfaced **82 placement rows with no active ledger row** for that
  (team, scorer) — on-site trades/FA moves the ledger has no event types for
  yet; those copies' ledger rows stay null-status (charged, safe default).
  Ledger trade/FA event types remain the open gap (ties into dead-money
  drop-event work above). (3) Vacuous cap assert replaced with a real
  over-cap warning. Tests: `test_capmath_minors_exempt` pins full-value +
  placement-only exemption + null-charges.

## [ ] Active — pipeline orchestration + model normalization (approved plan, 6 slices)
Grill/plan session 2026-07-13 (plan file: `~/.claude/plans/
critically-review-our-graceful-nebula.md`). Slices: A apply pacing/FA CSV
(PR #25) → B orchestrator (PR #26) → **C cap honesty (this branch)** → D model
cleanup → E full PBI normalization → F docs. One PR per slice.
- **Slice C BUILT 2026-07-13** (branch `roster-status-cap-honesty`):
  `roster_status` (Active/Reserve/Minors) stamped by 02e from the latest
  `fact_roster_placement` snapshot on (team_key, scorer_id); Minors PLACEMENT
  = cap-exempt in capmath (cap_hit 0 + cap_exempt flag), 02e summary, and the
  DAX 'Active Roster Salary' / 'Remaining Salary Cap' measures
  (RosterStatus <> "Minors"; blank charges). New `Fact_FantasyTeams.
  RosterStatus` TMDL column.
- **Cap-ledger audit findings FIXED in the same slice**: (1) capmath/02e
  multiplied kept-player charges by `cap_hit_pct` — but CapHitPct is
  DEAD-MONEY-ONLY (the DAX measure's own comment); a kept player charges FULL
  contract_value. Was a 2x understatement league-wide and silently
  zero-charged Minor-CONTRACT players kept active (pct 0.0). Both now charge
  full value; placement is the only exemption lever. (2) New 02e reverse
  check surfaced **82 placement rows with no active ledger row** for that
  (team, scorer) — on-site trades/FA moves the ledger has no event types for
  yet; those copies' ledger rows stay null-status (charged, safe default).
  Ledger trade/FA event types remain the open gap (ties into dead-money
  drop-event work above). (3) Vacuous cap assert replaced with a real
  over-cap warning. Tests: `test_capmath_minors_exempt` pins full-value +
  placement-only exemption + null-charges.

- **Slice D BUILT 2026-07-13** (branch `model-cleanup-capcols`, stacked on C):
  stored `dead_money` DROPPED from fact_fantasy_teams (parquet + TMDL +
  cultures block) — computed by consumers instead (Cut + Guaranteed →
  contract_value × cap_hit_pct; capmath/02e-summary/DAX all agree, pinned by
  `test_capmath_dead_money_computed` incl. the X trap case). Dim_Season TMDL
  desc fixed (was Dim_School copy-paste) + column descs; Dim_Division descs.
  Conference→Dim_Division relationship re-keyed on hidden `DivisionKey`
  calculated columns (current-season|conference) — survives dim_division
  gaining future seasons. **Known limitation**: Dim_FantasyTeams has no
  season grain, so DivisionKey always resolves to TODAY's anchor season —
  a report sliced to a PAST season shows the current season's division
  names. Acceptable until multi-season division renames actually exist.
  02b retired to archive/ (02e supersedes); 01e verified writing its parquet
  (explorer concern was false); retired fact_dynasty_rankings removed from
  data/README.md.

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

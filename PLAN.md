# PLAN.md

Scratchpad for active/upcoming work. Update as decisions land or items
complete — this file is expected to drift, that's the point.

> **Runtime token-gating** (see [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)):
> loop is `grill/plan → (Phase 0 consolidate) → compact → execute stage →
> compact → … ↺`. Compact at **~35% window (Opus, model-relative)**. Step
> buckets: `cheap` <2K · `med` 2–10K · `heavy` 10K+. A **stage** = steps
> packed ≤ budget, run before one `⟂ COMPACT`. PLAN.md = heartbeat (every
> seam); Memory/ADR/CONTEXT = real signal only, batched into Phase 0.

## [ ] Active / Next Steps

### Stage A — execute · target ≤35%  ✅ landed + VERIFIED 2026-06-13
- [x] Discord `rankings.py` rewrite (Option A): reads
  `fact_dynasty_ranking_metrics.parquet` (EAV) + `dim_nfl_players.parquet`,
  filters to `{ktc,ds,fp}_positional_rank` for the format, joins on `gsis_id`,
  re-ranks 1..N per displayed group. Replaces read of deleted
  `fact_dynasty_rankings.parquet`. **Verified against regenerated parquet**
  (snapshot 2026-06-13): SF/TEPP/IDP boards build, source default + override,
  position filter, Composite/unknown-position/bad-format all error cleanly.
  Two refinements the live data forced:
  - **Grouping = `position_group`, not `position`.** Granular `position`
    fragments each source's single rank list (FantasyPros ranks DE/DT
    separately) across 11 IDP fields with duplicate #1s. `position_group`
    gives offense QB/RB/WR/TE + IDP DL/LB/DB; offense identical either way.
  - **Re-rank 1..N within each field** (user decision): source sub-position
    ranking disagrees with DL/LB/DB grouping → show a clean sequence; no-op
    for offense. `groupby("position").rank(method="first")`.            · **[med]** ✅
- [x] `04z_fantrax_crosswalk.ipynb` gsis collision (Option B): hard
  `RuntimeError` → soft-fail. Logs `[warn]`, writes colliding rows +
  `action` col to `data/review/review_fantrax_crosswalk_collisions.csv`,
  continues. Crosswalk still written.                   · **[med]** ✅

**Phase 0 — DONE 2026-06-13.** Crystallized: (a) Stage A rankings grouping →
ADR-0002 + data-model + MEMORY index; (b) new-table design → ADR-0003 +
data-model `fact_roster_transactions`/derived `fact_fantasy_teams` section +
MEMORY index. Root tier unchanged (all facts project-specific); harness store
already drained. **Next: COMPACT**, then either the build stage for the new
tables or the `05a`/`04c` grill seams.

### NEW fact tables — design RESOLVED via grill 2026-06-13 (build deferred to own stage)
Foundational design settled (5-Q grill). BUILD is a future multi-step stage AFTER
Phase 0 + compact — do not start now. Sources are Fantrax (league
`v744203wmmvjqzv6`), auth-gated. Full rationale → ADR (written in Phase 0 below).

**`fact_roster_transactions`** (NEW; renamed from `fact_dead_money_drafts`) —
event-sourced player acquisition/transaction ledger.
- Unified fact, `event_type` discriminator: `startup_auction | rookie_draft |
  fa_auction | fa_pickup | resign` (resign = re-sign + franchise tag; add `drop`
  for dead-money realization). New event types add ROWS, not tables.
- Grain: 1 row / acquisition event. Key `season + event_type + team_key +
  gsis_id + event_seq` (pick_no for drafts, txn_date for FA).
- **SSOT** for how / at-what-salary a player was acquired. `fact_fantasy_teams`
  is DERIVED from it (replay → latest active contract per player); derivable from
  startup data alone.
- `contract_value` ← Fantrax salary; `cap_hit` DERIVED by contract type
  (`dim_contract.cap_hit_pct` × value, by `contract_year`) — never stored twice;
  `dead_money` = guaranteed residual; Yo-Yo cap-exempt while `ml_games_left>0`.
- Source: 04a-style Playwright + Fantrax `fxpa/req` (`getDraftResults`-type
  method), persistent `.pw_profile`; full snapshot → replace-by-
  `(season, event_type)`; idempotent. Reuse `etl_helpers` (CFG, crosswalk via
  `dim_fantrax_crosswalk` scorer_id→gsis_id, `load_replace_partition`).
- **Live-draft use case:** run between picks during the startup draft → re-derive
  availability → refresh the 05a `startup_draft_board.xlsx`. v1 = startup auction
  (35 rounds); schema forward-compatible.

**Saturate `fact_fantasy_teams`** — now means BUILD THE DERIVATION (ledger →
current-roster state on the 12-col schema 02b already seeds), NOT an independent
scrape. Feeds `dim_fantasy_teams` cap rollups.

**Draft capital folded in (ADR-0004, grill 2026-06-13):** ledger key
`gsis_id → asset_id` (`season_id + event_type + team_key + asset_id +
event_seq`); new `dim_roster_asset` (player/prospect/pick bridge), `dim_draft_pick`,
`dim_season`. `event_type` += `pick_allocation` (live) + `trade` (dormant v1).
Picks seeded from Fantrax `draftPicks.go` snapshot; `fact_fantasy_teams` derives
pick inventory by replay. v1 = inventory only (valuation deferred).

#### GRILL 2026-06-14 — v1 scope RESOLVED (supersedes the open list above)
League reality correction: we are at the **STARTUP DRAFT now, and it is a snake/
linear DRAFT, not an auction** (auctions = FA/re-sign, next offseason). The ADRs'
`startup_auction` event is misnamed for v1 → **rename `startup_auction` →
`startup_draft`** (snake draft; players acquired via picks, not bids). Resolved:
- **v1 = FULL ADR-0004** (user decision): build the polymorphic-asset machinery
  now — `dim_roster_asset` + `dim_draft_pick` + `dim_season` + `pick_allocation`/
  `trade` enum + `asset_id` — with live `startup_draft` events as the driver.
- **Contract**: every startup pick gets an **Initial** contract, yr 1 →
  `dim_contract.contract_id="1st"` (`cap_hit_pct=0.50`, `guaranteed=True`,
  3-yr term). `contract_value` = the **Fantrax `salary` field** (already captured
  in `fact_fantrax_adp.salary`; projection-based by construction). `cap_hit` =
  0.50 × value (yr 1); dead money applies. Use the salary **as-of the pick**
  (locked) — HAR shape decides whether `getDraftResults` carries it or we join
  the nearest snapshot. No rookie-scale, no new projection math.
- **Pick horizon**: `dim_draft_pick` seeds **current + 2** (2026/2027/2028).
- **`asset_id` scheme**: **monotonic integer sequence**, assigned at first sight,
  persisted in `dim_roster_asset`, never re-derived (ADR-0004 forbids deriving
  from the migrating `gsis_id`/`player_key` resolvers).
- **Sequencing**: user captures HAR **first**; build parses against the real
  wire shape (no schema-first guessing).
- Identity joins already exist: player `scorerId → gsis_id/player_key` via
  `dim_fantrax_crosswalk` (04z); team `teamId → team_key` via
  `dim_fantasy_teams.fantrax_team_id` (added by 01c, ADR-0005).

**⛔ GATING PREREQUISITE — capture `getDraftResults` (UPDATED 2026-06-14).**
HAR delivered. It gave us the exact **request** but NOT the response body: the
draft board is served via Fantrax's **service worker**, so DevTools persists the
size (157 KB) but not the bytes — a HAR cannot carry it. **Pivot: capture via our
own authed scraper**, which is the real pipeline anyway.
- Request recovered: POST `fxpa/req?leagueId=v744203wmmvjqzv6`, `msgs =
  [getDraftResults{}, getFantasyLeagueInfo{}, getRefObject{FantasyDraftPickType}]`,
  `uiv 3`, `v 183.1.5` (04a's getDraftRanks was 182.4.8), refUrl `/draft-results`.
- **NEW `notebooks/04w_fantrax_draft_results.py`** (built 2026-06-14): reuses
  04a's `FantraxScraper` (persistent `.pw_profile`, server-verdict re-login),
  POSTs the bundle, writes `data/raw/fantrax_draftresults_{season}.json`.
- **✅ CAPTURED + DECODED 2026-06-14**: 04w ran (`.venv`, not anaconda — see env
  note). Real `getDraftResults` shape: `draftPicksOrdered` (round, pickNumber,
  teamId, **scorerId**, positionId, `type`→FantasyDraftPickType, divisionId,
  modifiedDate=epoch ms) + `scorers` (player detail, join scorerId→gsis via 04z) +
  `fantasyTeamsOrdered` (teamId→name) + `draftDirection` (snake ±1) + `positionMap`
  + FantasyDraftPickType ref. **NO salary on pick** → contract_value from
  `fact_fantrax_adp.salary` by scorerId (nearest snapshot = as-of pick), as planned.
  **Draft is LIVE/in-progress** (~137/490 picks made in Riddell).
- **Per-division finding**: getDraftResults returns ONE division (14 teams, 490=14×35).
  League = 2 divisions (Riddell `rhf63kfummvk3jnh` + Wilson `svxeyvvgmmvk3jnh`). 04w
  now loops divisions (passes `divisionId`, writes one raw file per division). ➡
  **USER: re-run 04w to capture BOTH** (verify Wilson switches; if `⚠ param ignored`
  → fall back to UI division-switch capture).
- **ENV (resolved 2026-06-14)**: build runs in **`.venv`** (has playwright + pandas
  + dotenv; **pyarrow installed this session** — reads all existing parquets, incl.
  `dim_position` which anaconda's pyarrow couldn't). Do NOT use anaconda base
  (no playwright; broken pyarrow "Repetition level histogram size mismatch").
- **Identity gap for S2/S3**: `dim_fantasy_teams` has **no `fantrax_team_id`** yet
  (cols: team_key/team_name/team_abbr/conference/division/manager_email). Need
  `teamId→team_key`: from draft `fantasyTeamsOrdered` (teamId+names) or Sheet
  `Fantrax-TeamId` (ADR-0005, 01c). Resolve as first step of S2.
- `draftPicks.go` (future-pick inventory for dim_draft_pick forward years) still
  not captured — getDraftResults covers the CURRENT startup picks; capture forward
  picks separately when seeding 2027/2028.

**Build stages — ✅ BUILT + VERIFIED + MERGED 2026-06-14** (PRs #12 matcher, #13 plan,
#15 build all merged to `main`; branches deleted; repo flat). Riddell capture, `.venv`:
- [x] **S1 `01f_dim_season_seed.ipynb`** → `dim_season` (3 rows: 2026-2027 +2;
  fantasy Mar 1→last Feb; NFL dates null; leap-year Feb correct).
- [x] **S2a — team identity via the Sheet (01c).** The league Sheet now carries the
  authoritative **`Fantrax-TeamId`** column (ADR-0005 locked col; user added it
  2026-06-14), so `01c_dim_fantasy_teams_seed.ipynb` ingests it →
  `dim_fantasy_teams.fantrax_team_id` (28/28, no nulls, unique). 02d joins
  `teamId→team_key` straight off it. The earlier name-match heuristic
  (`01g_dim_fantrax_team_crosswalk`) is **RETIRED** — superseded by the Sheet (it
  had correctly inferred `Big L`→A10, `Brantley Gilbert`→A08, now confirmed exact).
  Bonus: 01c also refreshed stale team names (A08 was a stale "Metallica" snapshot).
- [x] **S2b/c+S3 `02d_fact_roster_transactions.py`** (live-loop script) → one parse
  emits `dim_roster_asset` (137 assets; monotonic `asset_id` minted on stable
  `scorer_id`, persisted, never re-derived), `dim_draft_pick` (490 slots), and
  `fact_roster_transactions` (137 `startup_draft` rows; key
  `season_id+event_type+team_key+asset_id+event_seq`; contract `1st` yr1,
  `contract_value`=Fantrax salary, `cap_hit`=0.50×). Idempotent replace-by
  `(season_id,event_type)`. Globs+dedups all division files. **137/137 resolve to
  both gsis_id and salary.**
- [x] **S4 `02e_fact_fantasy_teams_derive.py`** → replay ledger → 12-col
  `fact_fantasy_teams` (137 active rows) + cap rollup into `dim_fantasy_teams`
  (active_roster_salary/remaining recomputed). 05a wired: non-destructive
  **"Drafted By"** column from `fact_fantasy_teams` (137 taken / 1519 available),
  guarded to run pre-draft.

**⚠ FINDING — startup picks WERE traded.** getDraftResults' slot `teamId` is the
**current** owner (some teams hold 2 picks/round, others 0). ADR-0004's
`pick_ref=(draft_season,round,original_owner)` needs the pre-trade allocation from
**`draftPicks.go`** (not captured) → `dim_draft_pick` is keyed on the slot
`(draft_season,divisionId,overall_slot)`, records `current_owner`, leaves
`original_owner` null. `pick_allocation`/`trade` events stay dormant v1 (no source).
The made-pick fact is unaffected (records who drafted).

**➡ FOLLOW-UPS (post-merge 2026-06-14, ordered):**
1. **USER: re-run 04w for the Wilson division** → then `02d` → `02e` (scales to 28
   teams / both divisions automatically). Identity already 28/28 (Sheet
   `Fantrax-TeamId`); only the Wilson *draft* capture is missing.
2. **Capture `draftPicks.go`** (separate `fxpa/req` method, not yet HAR'd) →
   backfill `dim_draft_pick.original_owner`, light up `pick_allocation`/`trade`
   events, seed 2027/2028 forward-year picks.
3. **Phase 0 — ADR-0003/0004 text amendments** (batched): `startup_auction`→
   `startup_draft` rename; v1-is-full-ADR-0004; `contract_value`=Fantrax salary;
   `dim_draft_pick` slot-keyed + `original_owner` deferred (the trade finding);
   team identity = Sheet `Fantrax-TeamId` via 01c (heuristic crosswalk retired).
4. Still externally gated: ADR-0005 Sheet **write**-sync (Sheets-API auth + PII
   go-ahead); Railway deploy of the merged discord bot.
- Env note: `.venv` is the full notebook env (`requests`/`rapidfuzz`/`thefuzz`/
  `pyarrow` added 2026-06-14); do NOT use anaconda base.

### NEW high-value tasks — ALL GRILLED 2026-06-13 (designs resolved; builds queued)
Decision trees cleared via `/grill-with-docs`. Builds are their own post-compact
stages. Architecturally significant.

1. [x] **Owner manifest sync → Google Sheet — design RESOLVED → ADR-0005.**
   Fantrax = upstream SSOT, Sheet = field-scoped synced mirror. Join on
   `Fantrax-TeamId` (managers not unique). **Locked (never written):** Division,
   Team ID, Fantrax-TeamId. **Synced:** Team Name, Team Abbreviation, Manager
   Email, Other Manager Email. Diff-only writes, soft-fail unmatched. `01c` maps
   `Fantrax-TeamId → fantrax_team_id` (lights up the ADR-0004 ledger join). New
   `dim_division` `(season_id, conference) → name`. ⚠ build: external-write + PII
   gate (explicit go-ahead + Sheets-API auth, owner-set-up). **Build = own stage.**
2. [x] **Ingest draft capital — design RESOLVED via `/grill-with-docs` 2026-06-13
   → ADR-0004.** Picks become first-class assets under a polymorphic `asset_id`
   (`dim_roster_asset` bridges player/prospect/pick); event-sourced in the SAME
   ledger via `pick_allocation`. New dims `dim_draft_pick` (`pick_ref` =
   (draft_season, round, original_owner), stable under trade) + `dim_season`
   (`season_id` `"2026-2027"`). Glossary → root `CONTEXT.md`. **Build folds into
   the `fact_roster_transactions` stage below** (no longer a standalone task).
3. [x] **Source/dependency manifest — ✅ BUILT 2026-06-13 → `docs/SOURCES.md`.**
   Hand-authored, **external-input boundary only** (internal lineage stays in
   data-model `Source` col + README inventory). Cols: Source · URL/locator ·
   Purpose · Auth · Feeds (notebook→table) · Cadence. 9 live rows (Fantrax
   getDraftRanks, Google Sheet, nflverse, KTC, FantasyPros, WalterFootball,
   DraftSharks, DynastySharks, manual Excel) + 3 planned (Fantrax
   getDraftResults/draftPicks.go, commissioner admin, Sheet write-sync). Secrets
   = auth **method** only (no tokens/emails/.env). Anti-drift via the `Feeds`
   column; no generator for v1. · **[med]** ✅

⟂ **COMPACT** — all four grills cleared (04c, 05a, manifest sync, SOURCES.md);
designs crystallized to ADR-0004/0005 + CONTEXT.md + data-model. Then build stages.

### Grill seam — `05a` `METRIC_MAP` keying · RESOLVED → Option A · ✅ BUILT + VERIFIED 2026-06-13
- [x] **Option A: key METRIC_MAP by `metric_key` alone** (dropped the redundant
  `(source, metric_key)` tuple — each key owns one source, data-model:241).
  `load_dynasty_metrics()` loop filters on `metric_key` only; source no longer
  threaded through. **Verified behavior-preserving**: all 13 mapped keys confirmed
  single-source in `fact_dynasty_ranking_metrics` (latest SF snapshot) → dropping
  the `source_name` filter cannot change results. **Rejected full B**: the board's
  subset-selection + display column names are 05a presentation, not registry
  concerns. Registry owns *what metrics are/where from*; 05a owns *which the board
  shows + what it calls them*.   · **[cheap-med]** ✅

### Grill seam — `04c` SEED rank rows · RESOLVED → Option B · ✅ BUILT + VERIFIED 2026-06-13
- [x] **Option B: generate the 6 rank rows from `SOURCE_PREFIX`** (× {overall,
  positional}); the prefix `.upper()` IS the display abbrev (ktc→KTC, ds→DS,
  fp→FP) so no second map needed (simpler than the grill sketch). 28 bespoke
  metric rows stay hand-typed. Makes `etl_helpers.py:544` (which already *claims*
  04c reads SOURCE_PREFIX) true. **Verified**: generated rows byte-identical to
  the prior hand-typed 6; notebook executes clean → 34 rows (6 gen + 28 bespoke),
  validation passes (all fact keys covered).   · **[cheap-med]** ✅

⟂ **COMPACT** — Stage (04c + 05a) landed + verified; SOURCES.md next (light) or
the two heavy stages (ledger / manifest sync, each external-gated).

### Off-thread (user-owned — don't budget against my window)
- [x] Rerun dynasty pipeline on `update-dynasty_metrics-refactor`: delete
  stale `fact_dynasty_rankings.parquet` + `fact_dynasty_ranking_metrics.parquet`,
  rerun `04b → 04x → 04y → 04c`, refresh PBI against regenerated parquet.
  Best done before the Discord rewrite is tested.        · **[user · off-thread]**
- [x] In `pbi/mouserat2`, remove orphaned `Fact_DynastyRankings` table, its 4
  relationships, and stale `cultures/en-US.tmdl` entries (2026-06-12
  refactor leftover).                                     · **[user · off-thread]**

### Cross-branch consistency — check-in · ✅ DONE 2026-06-14
- [x] Split the single uncommitted tree into two stream branches (grill
  2026-06-13): Stream A (refactor + all architecture docs/memory) →
  `update-dynasty_metrics-refactor`; Stream B (bot) → `harden-discord-bot`.
  Stray cleanup applied (probe deleted, `.pbix` restored, PBI `LocalDateTable_*`
  gitignored). Stale remote branches (add-dynasty-rankings,
  add-dim-school-abbr-report-page, dev) deleted; superseded GHD `dev` stash dropped.
- [x] PRs opened: **#9** `update-dynasty_metrics-refactor → main` (refactor +
  docs); **#10** `harden-discord-bot → main` (bot). ⚠ **Merge order: #9 first**
  (bot reads #9's EAV schema). Railway deploy still deferred. · **[cheap]** ✅

## [ ] Deferred - User Requested

- [ ] Deploy `discord_bot/` to Railway. Scaffolded per the
  `discord-bot-github-fetch` skill (`railway.json`, crash-loop guards in
  place) but currently runs locally only — deploy once the `rankings.py`
  rewrite above is done and verified against the new EAV schema.
- [ ] Additional Discord bot commands (`player`, `adp` lookups). v1 was
  intentionally scoped to `rankings` only — revisit once `rankings` is
  stable on the new schema.
- [ ] Close out the `git filter-repo` history-scrub follow-up for
  `notebooks/.env` / `data/.pw_profile` (2026-05-30 incident) — user-owned,
  low urgency, not yet fully verified closed.

## [ ] Deferred - Recommended

- [ ] **Revisit: machine-readable `sources.yml` + validation harness** (lower
  priority). Once `docs/SOURCES.md` (task #3) exists and proves useful, consider
  promoting it to a structured `sources.yml` with a lint that checks each
  `Feeds` notebook still references its source URL — rot-proof vs the hand-doc.
  Deferred per owner: door left open, not v1.            · [med]

- [x] Add the one-line token-gating pointer to `CLAUDE.md` (→
  [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)) — ✅ 2026-06-14
  ("Execution loop" bullet, committed in PR #9. The ADR's
  Consequences section already assumes it's there.            · [cheap]
- [x] `notebooks/README.md` 04b inventory row + "two-layer model" section
  updated to the single-EAV-fact design (ADR-0002, 2026-06-12 refactor):
  `fact_dynasty_rankings` backbone retired, ranks fold into
  `fact_dynasty_ranking_metrics` as source-prefixed metric_keys;
  `dim_dynasty_crosswalk` + `dim_dynasty_metric` retained. ✅ 2026-06-13
- [x] The `discord-bot-github-fetch` skill's `references/data-model.md`
  rewritten to the EAV + `position_group` board (ADR-0002), grounded in the
  shipped `discord_bot/rankings.py`: single `fact_dynasty_ranking_metrics`
  fact, `{ktc,ds,fp}_positional_rank` keys, identity join to `dim_nfl_players`
  on `gsis_id`, re-rank 1..N per group, `_PREFERRED_SOURCE` defaults. Retired
  `fact_dynasty_rankings`/`position_raw` references removed. ✅ 2026-06-13
  (Skill file, outside the repo: `~/.claude/skills/discord-bot-github-fetch/`.)
- [x] `04z`'s divergent `clean_player_name` copy consolidated ✅ 2026-06-14.
  Promoted the aggressive match-normalizer (strips periods/apostrophes/
  generational suffixes) to shared `etl_helpers.clean_name_for_match`; it was
  duplicated verbatim in 04z's local def AND `resolve_dynasty_crosswalk._clean`.
  Both now call the shared fn; 04z no longer shadows the gentle (hash-feeding)
  `clean_player_name`. Output verified byte-identical to the prior copies, so
  behavior-preserving for both Fantrax (04z) and dynasty (04b/04x) matching.
- [ ] Sweep `01b`-`01e`, `02b`, `03y`, `04a` for local `LeagueConfig`-style
  constants that duplicate what's now in `etl_helpers` (`CFG`,
  `SOURCE_PREFIX`, `ZERO_IS_MISSING`, `fold_ranks_long`) and consolidate.
- [x] `.claude/settings.local.json` resolved ✅ 2026-06-14 — untracked
  (`git rm --cached`, file kept on disk) + gitignored as per-developer local
  settings. Merged in PR #9.

## [ ] Deferred - Future

- [ ] In-season tables: `fact_nfl_player_stats`, `fact_nfl_season_injuries`
  (nflreadpy weekly stats/injuries) — per data-model.md "In-Season Tables
  (deferred)".
- [ ] Fabric migration: swap `pd.read/write_parquet` for
  `spark.read.parquet` / `abfss://` once the dynasty model has settled —
  schema is already designed to be migration-neutral.
- [ ] Prep-for-AI / Fabric Data Agent configuration for the dynasty
  semantic model (per the `semantic-modeling-prepforai` skill), once the
  dynasty refactor and PBI model cleanup are done.
- [ ] Generalize composite ADP blending (`ADP_KEYS`) beyond 2 sources if/
  when a 3rd ADP source is added.

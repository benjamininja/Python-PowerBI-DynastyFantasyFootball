# PLAN.md

Scratchpad for active/upcoming work. Expected to drift — completed items
collapse to one-liners once their durable signal lands in an ADR / MEMORY /
data-model. Blow-by-blow does NOT live here.

> **Runtime token-gating** (see [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md)):
> loop is `grill/plan → (Phase 0 consolidate) → compact → execute stage →
> compact → … ↺`. Compact at **~125K–150K tokens**. PLAN.md = heartbeat;
> Memory/ADR/CONTEXT = real signal, batched into Phase 0.

## [x] CLOSED — Owner-PII history scrub (final closeout, 2026-09-27)

Forward fix shipped in #95 (`scripts/check_pii.py` + `pii-scan` CI; 01c no
longer reads owner emails). This closes out the history side. Kit + local
backups live **outside the repo and outside OneDrive** (session reset prompt
has the path). Plan approved; user authorized rewrite + force-push.

- [x] **Hard gate**: every other session on this repo stopped + paused; no
  open PRs / Actions runs; everything worth keeping is pushed.
- [x] Run `scrub.sh`: bare clone → filter-repo → verify CLEAN → `main` tip
  tree identical → remote heads unmoved → force-push all branches + tags.
- [x] Re-verify against a fresh clone of GitHub (VERIFY: CLEAN, 8 branches;
  `main` tip tree unchanged).
- [x] Local reset: old clone → `*-OLD-DO-NOT-PUSH`; fresh clone; re-apply
  saved memory edits + untracked files; `.venv` + `pre-commit install`.
  Every session/worktree restarts on the fresh clone — **never push from an
  old clone**.
- [x] (ask) make `pii-scan` a required check on `main` — ruleset
  "main: require pii-scan", no bypass actors.
- [x] Remove the temporary scrub allow rules from `~/.claude/settings.json` —
  n/a, none found.
- [x] Old clone + kit work dir removed. User declined (risk accepted):
  GitHub Support sensitive-data request; moving owner columns off the
  link-shared Sheet.

## [ ] ACTIVE — Supabase + in-season ETL: 3 wayfinder maps (charted 2026-09-26)

Season is live; no in-season league data ingested yet, and storage is moving
parquet-in-git → Supabase. Decided (2026-09-26): 3 parallel maps joined by a
**storage seam** (`etl.read_table`/`write_table`, parquet backend first);
maps carry to *change landed*; `docs/reference/` (James's HoD baseball
Supabase stack) = pattern reference only, **kept out of git** (embeds keys).
User direction: **daily run, weekly update-set**, tested; minimal
player-week snapshot (roster status, contract, FPts YTD, age) — football is
raw points, not categories.

- [Map #69 — Supabase storage foundation](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/69):
  #72 role/ADR (grilling) · #73 platform facts (research) · #74 seam
  inventory (research) · #75 schema+RLS (grilling, ✅ ADR-0018) · #76 provision
  (HITL task, ← #72) · #77 build seam (task, ← #74; unblocks B/C writers).
- [Map #70 — In-season Fantrax league flows](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/70):
  #78 capture payloads (task) · #79 schema extraction (research, ← #78) ·
  #80 public fxea API (research) · #81 fact model (grilling, ✅ ADR-0016 amendment) ·
  #82 txn cadence (grilling, ✅ ADR-0016) · #83 sources.yml truth-up (task) · #87 daily
  run / weekly update-set (grilling, ✅ ADR-0015) · #88 test strategy
  (grilling, ✅ ADR-0008 amendment) · #92 Actions login spike (research; TOTP decided 2026-09-27) ·
  #93 cadence build (task, ← #92 #77 #75 #76 + #115; now also 04t orchestration
  + poll-writes-snapshot) · #96 `fact_dead_money` + stable move key (task,
  ADR-0016) · #97 shared cap module + published per-team cap table, 02e =
  snapshot + provenance (task, ← #96 #79) · #117 Roster State build (task,
  ← #113, ✅ PRs #127–#129) · #118 Scoring build (task, ← #117; PRs 1–2 of 3 ✅ #131, #132; PR 3 built) · #130 claim
  default contract (grilling, ADR-0019 d6; filed 2026-10-04).
- [Map #71 — nflverse in-season stats + injuries](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/71):
  #84 nflreadpy API (research) · #85 grain/scope (grilling, ✅ ADR-0017:
  snaps + injuries only; points/GP from Fantrax) · #86 build + schedule
  (task, ← #85 #77).

**Lanes.** Wave 1 (AFK, parallel) ✅: research #73 #74 #80 #84 (full
findings in [`docs/research/`](docs/research/); each issue carries a
summary + link), #78 capture (PR #89), #67 (PR #90). Wave 2 (HITL) ✅:
#72 → #87 → #82 → #85 (ADR-0014..0017). **Wave 3, in progress
(2026-10-02)**, run from the managing session
`dynastyFantasyFootball-central-builder`:

- AFK, fired 2026-10-02: #83 sources truth-up ✅ (PR #103). #79 schema
  extraction ✅ — recounted by the managing session after two unreliable
  agent reports; findings in
  [inseason-schema-extraction.md](docs/research/inseason-schema-extraction.md).
  Public rosters carry all four Roster Slots + salary + contract and
  backfill past periods; `playerViewType:'2'` BENCH holds Bench, IR and
  Minors. Next AFK: #68.
- **ADR-0011 reconciled ✅ 2026-10-02 →
  [ADR-0019](docs/adr/0019-minor-is-a-pre-1st-contract-stage.md)**: `Minor` is
  the pre-`1st` contract stage. Any eligible player holds it, however they
  were acquired. A drop costs 0% dead money, the contract is off the clock,
  and the player moves to `1st` mid-season the period after GP > 19, same
  salary.
  - Contracts are observed from Roster State, with a #88 drift check for
    mismatches.
  - `02d` takes each move's contract from the snapshot first, falling back
    to a default.
  - The Minors slot stays the only cap exemption.
  - Build: the `dim_contract` row + `02d` sourcing (#113) — **built
    2026-10-03**, merged as PR #124. The
    preseason snapshot is not read; 354 draft rows, 14 trades and 11 claims
    are `Minor`; cap totals unchanged. `02d` now runs behind `main()`.
    A move reads a snapshot only from inside the copy's stint and before
    the move day; eligibility counts the capture on either side of the move.
- **#88 grilled ✅ 2026-10-03 →
  [ADR-0008 amendment](docs/adr/0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88)**
  (amended in place, owner's choice).
  - Every publish is gated. Gate checks block their Chain; Review checks file
    to `ops.review_check` and never block.
  - The publish unit is a Chain, so one broken scraper no longer freezes
    rosters.
  - Close checks must pass before an Update-Set freezes.
  - Review findings: one open row each, auto-resolve, per-check grace (Minor
    drift = 1 period).
  - Drift sweep runs daily. Discord posts events plus a daily digest.
  - Fixtures are generated with a key allowlist. CI gets a required
    `tests.yml`, and `run_pipeline.py` gets `--check-only`.
  - Build (a), the foundation (also fixes the commit-on-failure bug at
    `run_pipeline.py:325`): #115 ✅ **merged 2026-10-03** (PR #120:
    `etl_checks.py`, per-Chain publish, `--check-only`, fixtures, `tests.yml`).
  - Build (b), the in-season checks (← #115, #93 and #118): #116.
- **#75 grilled ✅ 2026-10-02 →
  [ADR-0018](docs/adr/0018-supabase-schema-and-rls.md)**: schemas
  `football`/`shared`/`ops`; registry-generated migrations; PK = grain;
  deferred FKs on clean edges, dirty edges as checks; tight types through to
  the snapshot; RLS on with `etl_writer` + a read-only login; hashed
  `shared.owner` lookup for the PII check; `migrate.yml` on merge. Prereqs:
  the grain fixes, trade-log pick legs resolved to Original Owners,
  `division_id`.
- Code follow-ups from #79: `04s` sends `playerViewType:'2'` ✅ (PR #131).
  `04v` IR drop fixed ✅ (PR #106: IR kept as `"Inj Res"`, charges per
  ADR-0011).
- Research docs for #73 #74 #80 #84 landed in `docs/research/` ✅
  (2026-10-02); new research tickets (#79 onward) write there too.
- **#81 grilled ✅ 2026-10-03 →
  [ADR-0016 amendment](docs/adr/0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-03-in-season-fact-model-81)**
  (amended in place, owner's choice).
  - New tables:
    - `dim_scoring_period`: all 17 periods, plus the Update-Set state;
    - `fact_roster_state`: per period, P1–12; retires `fact_roster_placement`;
    - `fact_period_scoring`: points by Unit, every rostered player;
    - `fact_matchup`: one row per team;
    - `fact_standings`: rank, playoff odds and salary remaining only
      (not built: the owner's decision, 2026-10-04, in #118).
  - `fact_fantasy_teams` is the current Roster State all year; `roster_status`
    becomes `roster_slot` (#110).
  - Players by `scorer_id` only. Age is derived. No YTD columns. Division
    comes from Fantrax. Playoffs are out of scope.
  - Scoring loads once `allEventsFinished`. The matchup Close check is defined.
  - Builds: #117 Roster State (← #113), then #118 Scoring (← #117).
    #93 ← #117; #116 ← #118.
- Step-by-step handoff: [RESUME.md](.claude/memory/RESUME.md).
- Build, plan-gated: #113 ✅ PR #124 (it carries no `fact_*` parquet;
  Resolution and hand-on comments posted) → #125 ✅ PR #126 (draft picks and
  claims take their salary from the roster snapshot, then draft-time ADP;
  all 1,004 roster rows on Fantrax period 1 match; the ledger and roster
  are published, as of the 2026-07-24 transaction history) → #117 ✅ (grilled
  and planned 2026-10-03; three PRs; closed 2026-10-04). **PR 1 ✅ merged as PR #127
  (2026-10-03):** `04p` reads public
  `getLeagueInfo` on every run and writes `dim_scoring_period` (17 periods,
  exact bounds, Update-Set state `open` / `closing`) and `dim_division`
  (same two rows, now from Fantrax); `01g` is in `archive/`. **PR 2 ✅ merged as PR #128
  (2026-10-04):** `04r` reads
  public `getTeamRosters?period=N` on every run and writes
  `fact_roster_state` (periods 1–4 today, 4,360 rows; Roster Slot, salary,
  contract, `capture_date`), with coverage and contract Gates;
  `fact_preseason_salary` (992 rows, frozen) keeps the preseason salaries.
  Nothing read either table until PR 3. **PR 3 ✅ merged as PR #129
  (2026-10-04, `6a61da9`); it closed #117:** `fact_roster_placement` is
  retired. `04t` was recaptured (history to 2026-10-01). Decision 1 was
  re-ruled after its test: a period's public roster is the roster at its
  lineup lock, so a move reads Roster State by the Scoring Period it takes
  effect in (Fantrax's `week` stamp), not by day. Two more rulings came out
  of the audit: an in-season move with no readable period fails the step,
  and a trade or drop with no ledger terms is priced off the Roster State
  row it reads. The republished ledger and roster match Roster State period
  4 on all 1,100 copies, and charged salary matches Fantrax for 28 of 28
  teams. `pytest tests/` 359 pass. `04e` is edited but not rerun
  (`dim_position_ceiling` is unchanged; the owner decides when). Carried
  forward: the claim default (ADR-0019 decision 6, #130), dead money still 0, the
  roster still a ledger replay (#97). Detail
  in `.claude/memory/RESUME.md`
  → #118 (#115 ✅ PR #120): **grilled and planned 2026-10-04**, three PRs.
  PR 1 the `04s` capture change (bench view, standings probe, no roster
  calls), then the owner's capture; PR 2 `fact_period_scoring` (with
  `is_starter`) and `fact_matchup`; PR 3 standings per the probe, the Close
  checks, `closed` switched on, `04s` as a pipeline step. Found in the
  grill: `getStandings COMBINED` ignores `period` and serves the current
  standings, and the saved captures hold Starters only. A period's scoring
  loads once its games are final. **PR 1 ✅ merged as PR #131
  (2026-10-04, `6280c2e`):** `04s` asks for the bench view, saves two by-period
  standings probes beside the standings reply, makes no roster calls, and
  stamps `captured_at`; a period Fantrax rejects is reported and skipped.
  No table changed. `pytest tests/` 368 pass. **The owner's capture
  (2026-10-04, periods 1–5):** the bench view works, a period that has not
  started returns no entries, and Fantrax serves a past period's record and
  rank by period; Salary Remaining and % Playoffs are current-only. **PR 2
  ✅ merged as PR #132 (2026-10-04, `99d5753`):** `04s`
  loads `fact_period_scoring` (points by Unit, `is_starter`) and
  `fact_matchup` for every final period, `--from-raw` with no browser;
  Gates `unit_sum`, `starter_slot`, `mirror`; periods 1–3 loaded (3,226 and
  84 rows). `pytest tests/` 442 pass. **`fact_standings` grilled
  (2026-10-04): not built.** Rank is derived from `fact_matchup` (win %,
  then points for: it matches Fantrax for 28 of 28 teams in periods 1–3);
  Fantrax's Salary Remaining goes to #97 (it stays in the raw files; it
  equals cap minus non-Minors salary for 20 of 28 teams, the rest likely
  dead money); `% Playoffs` is dropped (one Conference only, no history);
  `04s` keeps the plain standings call only; Standings becomes a derived
  term in `CONTEXT.md`. **PR 3 built (2026-10-04, `feat/118-close`; it
  closes #118):** `04s` asks for the plain standings only; `04p` closes a
  period once the following period has ended and its Close checks pass on
  the stored tables (`etl_checks.close_errors`: Roster State covers 28
  teams, Matchups hold every team once and mirror, each Matchup score is
  the team's Starter sum); a coverage Gate on `fact_period_scoring`;
  `04s_scoring` is an INSEASON pipeline step after `04r_roster_state`.
  Periods 1 and 2 are `closed`. `pytest tests/` 468 pass. Left for #116:
  the alert, the Drift sweep, "every Starter has an entry", grace. Detail
  in `.claude/memory/RESUME.md`;
  #77 seam (← #74 ✅) → unblocks #86 and #93; #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; #76
  provisioning.

**Overdue, owner-run:** `fact_fantrax_adp` stops at `2026/02` (checked
2026-10-02) — the weekly pull planned for 2026-09-29 has not run, and week 4
is now due. It needs a live Fantrax session until #92 lands.

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

## [x] CLOSED — wayfinder map #55: FA-claim identity gap (2026-08-04)

**Tracker: [wayfinder map #55](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/55)** —
closed. #56 (rerun/measure) and #57 (grilled fix: union `04t` txn-history
scorer_ids into `04z`'s match universe via `_scorer_extras`) both closed.
Shipped via PR [#60](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/60),
squash-merged to `main` as `7336606`. Verified: `04cc5` → `gsis_id
00-0033897`/`exact`; `dim_roster_asset` null-identity rows 0 (was 1);
`pytest tests/` 33 passed. Full detail:
[mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md).

## [ ] ACTIVE — backlog triage from #55: #64/#61 closed, #62/#63 → grilled wayfinder maps (2026-08-04)

Four backlog issues filed from #55's deferred items, prioritized #64 → #62
→ #61 → #63.

- [x] [#64](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/64)
  closed — stale on filing, PR #58 (merged 2026-08-03, before #64 was
  opened) already fixed the 17-row gap. Verified 0 null-identity rows today.
- [x] [#61](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/61)
  closed — moot, `dim_season` confirms 2026 is the league's inaugural
  season, so there's no prior season for `04t` to backfill.
- [x] [#62](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/62)
  / [#63](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/63) —
  both grilled, design fully decided, and wired into their own wayfinder
  maps (see below). Original backlog issues closed, retrofitted as each
  map's grilling ticket.

**Wayfinder maps charted** (2026-08-04) — #65's task is built, #66's is
not:

- [Wayfinder Map: 04z crosswalk disambiguation hardening](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/65) —
  grilling ticket [#62](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/62)
  (closed), implementation ticket
  [Task #67](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/67)
  (✅ built, PR [#90](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/90),
  2026-09-26; map #65 has reached its destination and is still open on
  GitHub). `disambiguate()` gets an `nfl_team` tiebreak + an
  "ambiguous" flag routing genuinely-tied candidates to the review queue;
  `dim_player_alias` wired into `match_one` as a `player_key` fallback.
- [Wayfinder Map: trade-bud waiver-activity signal](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/66) —
  grilling ticket [#63](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/63)
  (closed), implementation ticket
  [Task #68](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/68)
  (open, unblocked). New `infer_waiver_activity(team_key)` in
  `profiles.py`, exact mirror of `infer_trade_activity`.

Full decision detail in
[mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md).

### ➡ NEXT ACTION

**Task #68 (waiver activity)** — open, unblocked, design fully decided
(see memory). Re-check the tier cut points against in-season claim/drop
counts when building; the grilled figures are preseason. #67 shipped
2026-09-26 via PR #90 (detail in
[mouserat-trade-bud.md](.claude/memory/mouserat-trade-bud.md)).

## [ ] Active — dead money (design settled 2026-09-27, ADR-0016; build pending)

Superseded the 2026-07-11 Power BI-first design. **Power BI visuals are
deprioritized**; trade-bud and the bot need parity. Per
[ADR-0016](docs/adr/0016-roster-state-from-snapshot-ledger-is-provenance.md):
`fact_dead_money` is derived from drops, and each remaining guaranteed contract
year charges its own `cap_hit_pct × contract_value` in its own season. The ETL
computes a per-team cap table that both apps read. The old "no `drop` event"
blocker is stale: `02d` emits drops, but `dead_money` is hardcoded 0 until the
build lands.

## [ ] Active — Minors, open user actions only

Design closed:
- [ADR-0011](docs/adr/0011-minors-is-placement-not-contract.md) (supersedes
  ADR-0010) still holds, except its headline: **placement** (the team's
  lever) is the only cap exemption. `04v` is read-only and is the only
  writer of `fact_roster_placement`.
- [ADR-0019](docs/adr/0019-minor-is-a-pre-1st-contract-stage.md)
  (2026-10-02) replaces that headline. **`Minor` is the contract** held
  while eligible (GP ≤ 19, Fantrax-computed): 0% dead money, off the clock,
  and `1st` the period after GP > 19. Full build detail in
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
4. **`fact_fantrax_adp.overall_rank` on rebuilt weeks** (2026-10-03). Fantrax
   serves no Rk on `BY_DATE` pulls, so `player_stats_to_frame` derives it
   (`_fpts_rank`; detail in data-model.md) — shipped via PR
   [#121](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/121).
   Wk 01–02 backfilled the same day by offline replay of their raw captures
   (PR [#122](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/122)):
   857 and 1,078 ranks, no other column changed. Still open, USER: confirm the in-season `YEAR_TO_DATE`
   weekly pull still serves Rk — check `scorer.rank` on the first wk 03+
   capture.

## [ ] Deferred — user requested

- [ ] `git filter-repo` history-scrub follow-up for `notebooks/.env` /
  `data/.pw_profile` (2026-05-30 incident) — user-owned, low urgency.

## [ ] Deferred — future

- [ ] In-season tables: `fact_nfl_snap_counts`, `fact_nfl_injuries`
  (nflreadpy, current season) — scope/grain per ADR-0017, build = #86.
  (`fact_nfl_player_stats` dropped.)
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
  2026-07-26, PR #33, supersedes ADR-0010; headline superseded by
  [ADR-0019](docs/adr/0019-minor-is-a-pre-1st-contract-stage.md) 2026-10-02): the `Minor` contract type is void;
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
  pre-commit. *Amended 2026-10-03 (#88): publish gate, Gate/Review/Close
  checks and CI. Designed, not built.*
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

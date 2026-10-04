# RESUME — Supabase + in-season ETL maps (updated 2026-10-03)

**Managing session**: `dynastyFantasyFootball-central-builder`. It fires the
AFK tickets as background sessions, reviews what they return, and posts to
GitHub; HITL grills happen in the managing session.

**Git state**: `main` = 3cdcabd (PR #106 04v IR fix), after the 2026-10-02
docs PRs #102 memory/PLAN reconcile, #103 sources truth-up, #104 research
docs, #105 #79 findings; then `main` = 2fa8e3e (PR #107 ADR-0018); then `main` = 1a70ce1 (PR #112 ADR-0019 Minor
reconcile); then `main` = 9458c9d (PR #114, #88 test strategy: ADR-0008
amended in place); then PR #119 (#81 fact model: ADR-0016 amended in
place); then `main` = e57034c (PR #120, #115 check-suite foundation); then
`main` = 3ac5fed (PRs #121–#123, the `overall_rank` fix); then `main` =
493a6d7 (PR #124, #113 `Minor` contract; 188 tests pass); then `main` =
376a842 (PR #126, #125 salary sourcing; 225 tests pass). Working branch:
`feat/117-league-info` (#117 PR 1, built, uncommitted; see below).
History was rewritten
on 2026-09-27 (owner-PII scrub) — every SHA recorded before that date is
dead. `pii-scan` is a required check on `main`. Commit/PR only when the user
asks. Stage explicit paths only. Untracked and not ours (leave alone):
`.agents/`, `GEMINI.md`, `.claude/worktrees/` (agent worktrees).

**Closed since the last RESUME** (all merged): #95 owner-PII forward fix,
#100 `fact_fantrax_adp` gap fill + in-season universe floors (new
`04a --rebuild-week NN --through-date`), #101 scrub closeout. The Fantrax
password found in public history was rotated 2026-09-27 and the history
scrub is done. Also merged 2026-10-03: PR #121 (`04a` derives `overall_rank`
when Fantrax serves no Rk), PR #122 (wk 01–02 rank backfill by offline
replay) and PR #123 (its Phase 0 consolidation); `main` = 3ac5fed.

**Overdue, user-owned — weekly Fantrax pull**: `fact_fantrax_adp` stops at
`2026/02` (checked 2026-10-02). The run planned for Tue 09-29 did not happen:
`.\run_weekly.ps1 --steps 04a_scrape,04z_crosswalk,04a_backfill_gp --no-commit`
→ `2026/03` + `2026/YTD` + gsis refresh. Week 4 is now also due. It needs a
live Fantrax session (see the auth note below) until #92 lands. On that first
wk 03+ capture, check that `scorer.rank` is served: the in-season
`YEAR_TO_DATE` pull has not been observed since #121, and if Fantrax omits Rk
there too the partition gets the derived rank (see
[fantrax-players-grid.md](fantrax-players-grid.md)).

**Research findings home** (done 2026-10-02): full findings for #73, #74,
#80 and #84 live in `docs/research/` on `main`; the issue Resolution
comments point there. New research tickets (#79 onward) land their findings
in `docs/research/` too.

**Environment gotchas found 2026-10-02**: the post-scrub re-clone had left
the repo `user.email` unset; it is now set repo-local to the noreply
address (owner's decision, 2026-10-02). Squash-merge commits on `main` are
authored by GitHub from the account's email setting, which local config
does not control — the owner turns on "Keep my email addresses private" in
GitHub.

**Working from an agent worktree (2026-10-03)**: a worktree under
`.claude/worktrees/` holds tracked files only, so it has no `.venv/` and no
`data/raw/`.
- Python / pytest: call the main checkout's interpreter with CWD = the
  worktree (`<main>\.venv\Scripts\python.exe -m pytest tests/`). `.\run.ps1`
  fails there.
- Fixtures: `scripts/make_fixtures.py --raw-dir <main>\data\raw`.
- Commits: `.pre-commit-config.yaml` hard-codes `./.venv`, so `git commit`
  fails in a bare worktree, and the main checkout is usually on another
  session's branch. Make a small ignored venv in the worktree instead:
  `<main>\.venv\Scripts\python.exe -m venv --without-pip .venv`, then one
  file `.venv\Lib\site-packages\main_checkout_venv.pth` holding the path
  `<main>\.venv\Lib\site-packages`. All hooks then run; no `--no-verify`.
- Do not junction `data\raw` or `.venv` into a worktree (agent's caution, not
  an owner rule): worktree cleanup deletes recursively and could follow the
  junction into the main checkout's untracked captures.
- `gh pr merge --delete-branch` run from the PR's branch leaves the worktree
  on `main`, which blocks `git checkout main` everywhere else. Follow it with
  `git checkout --detach`.

**Fantrax auth (2026-09-27)**: creds live in gitignored repo-root `.env`
(the only one; `notebooks/.env` no longer exists). The account now has **TOTP
2FA**, so automatic `_login()` stops at the code prompt. `data/.pw_profile` was
seeded by a manual visible-browser login (verified headless: PASS). When that
session expires, scheduled runs fail until someone logs in by hand again.
Login-check scripts are in the session scratchpad (not in repo). #92 has a
comment recommending `FANTRAX_TOTP_SECRET` + `pyotp` in `_login()`, which is a
plan-gated code change.

## #82 decisions (grilled 2026-09-27, closed; full text in ADR-0016)
1. Three streams: **Roster State** ← snapshot; **Roster Moves** ← 04t log
   (provenance, Dead Money); **Period Scoring** ← per-period roster + live
   scoring (04s). Replay = reconciliation check → `review_*`.
2. **Roster Slot** = Starter/Bench/IR/Minors (Active→Starter, Reserve→Bench).
3. Poll persists the public `getTeamRosters` (no login) if #79 confirms the fields.
4. Current Roster State + one snapshot per Scoring Period (Update-Set lifecycle).
5. `fact_dead_money` from drops; rest-of-contract by year (.50 + .40 for a
   1st-yr drop); re-claim doesn't cancel it.
6. Move key `(txSetId, scorer_id, team_key, event_type)`; supersedes ADR-0006 id.
7. 04t full-season → 02d → dead money on every poll trigger + daily; daily-only
   fallback if #92 shows login challenges.
8. Cap math computed once in ETL (shared module out of `discord_bot/`); bot and
   trade-bud read a published cap table. **Power BI visuals deprioritized.**

## #85 decisions (grilled 2026-09-27, closed; full text in ADR-0017)
1. No nflverse stats table. Points / per-period / by-Unit points / GP ← Fantrax
   (GP+YTD: 04a `getPlayerStats`; per-period+by-Unit: `getLiveScoringStats
   {period, playerViewType:'2'}` = ACTIVE+BENCH, per-stat `fpts` → #81).
2. **Unit** = Offense/Defense/Special Teams; ST = RtY 3218 + BK 256g.
3. nflverse: `fact_nfl_snap_counts` (gsis_id, game_id) + `fact_nfl_injuries`
   (gsis_id, season, week); current season, replaced each run (not
   Update-Sets); `period` stamped via `getLeagueInfo.scoringPeriods`.
4. Side finding → side session (see Git state).

## Maps (native sub-issues + blocked-by wired)
- **#69 Supabase storage**: #72 ✅ · #73 ✅ · #74 ✅ · #75 ✅ (ADR-0018) ·
  #76 provision (HITL) · #77 build seam (task, ←110) · #108 migrations
  (←76,109,110) · #109 pick legs · #110 grain fixes · #111 orphans (←108).
- **#70 In-season Fantrax**: #78 ✅ · #79 ✅ · #80 ✅ · #81 ✅ (ADR-0016
  amendment) · **#117** Roster State build (←113) · **#118** Scoring build
  (←117) · #82 ✅ · #83 ✅ · #87 ✅ · #88 test strategy
  ✅ (ADR-0008 amendment) · #92 Actions login spike (**TOTP decided**) · #93 cadence build
  (←92,77,75,76,115,117; now also 04t orchestration + poll-writes-snapshot) ·
  #115 checks foundation · #116 in-season checks (←115,93,118) ·
  **#96** `fact_dead_money` + stable move key (task) · **#97** shared cap
  module + cap table, 02e = snapshot+provenance (task, ←96,79).
- **#71 nflverse**: #84 ✅ · #85 ✅ (ADR-0017) · #86 build (←77; body rewritten).

## Next actions (compact handoff, 2026-10-03)

**ADR-0011 reconcile grilled ✅ 2026-10-02 (Q1–Q10)** →
[ADR-0019](../../docs/adr/0019-minor-is-a-pre-1st-contract-stage.md).
- `Minor` is the pre-`1st` contract stage, held by any eligible player
  however they were acquired.
- A Minor drop costs 0% dead money; the contract is off the clock with NULL
  years and is not cap-exempt.
- The player moves to `1st` mid-season, the period after GP > 19, with the
  same salary; that season is year 1.
- Contracts are observed from Roster State, plus a #88 drift check.
- `02d` takes each move's contract from the snapshot, falling back to a
  default.
- ADR-0011's headline only is superseded; the rest of it stands.
- Merged as PR #112.
- Build issue **#113** (under #70): the `01b` Minor row + `02d` contract
  sourcing + the `04v` header comment, with a `cap-ledger-auditor` review.
- Comments posted on #88 (drift-check spec) and #96 (Minor drops price 0).
- The owner kept the #77 ← #110 blocked-by link.

**#88 grilled ✅ 2026-10-03 (Q1–Q18)** →
[ADR-0008 amendment](../../docs/adr/0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88).
The owner chose to amend ADR-0008 in place rather than write a new ADR.
- Every publish is gated (daily, poll, weekly).
- **Gate checks** block their **Chain**: a step failure, a repeated grain key,
  a table shrinking >20%, missing coverage, or a schema that no longer matches
  the registry.
- **Review checks** file to `ops.review_check` and never block. Each finding
  keeps one open row and auto-resolves. Each check has its own grace (Minor
  drift = 1 Scoring Period).
- **Close checks** must pass before an Update-Set freezes.
- Dirty edges file one row per distinct orphan key, limited to what can be
  acted on.
- The Drift sweep runs daily over every closed period.
- Discord posts events plus a daily digest.
- Fixtures are generated by `scripts/make_fixtures.py` with a key allowlist.
- CI gets a required `tests.yml`; `run_pipeline.py` gets `--check-only`.
- ADR-0014 decision 3, ADR-0018 decision 11, ADR-0015 and ADR-0019 carry
  amend notes.
- CONTEXT gains Chain, Gate check, Review check and Close check.
- Build (a) **#115**, the foundation, can start now and fixes the
  commit-on-failure bug at `run_pipeline.py:325`.
- Build (b) **#116**, the in-season checks, is blocked by #115, #93 and #118
  (← #81 replaced by ← #118 on 2026-10-03).
- #93 is now blocked by #115 instead of #88.
- Merged as PR #114. #88 is closed with a Resolution, and map #70's
  "Decisions so far" has the #88 entry.
- #70's "Decisions so far" gap for #79 and ADR-0019 filled 2026-10-03.

**#81 grilled ✅ 2026-10-03 (Q1–Q18, plus Q12b/Q12c)** →
[ADR-0016 amendment](../../docs/adr/0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-03-in-season-fact-model-81).
The owner chose to amend ADR-0016 in place.
- Points are stored by Unit, not per stat.
- New tables:
  - `dim_scoring_period` (all 17 periods, `is_playoff`, Update-Set state);
  - `fact_roster_state` (per period, P1–12; retires `fact_roster_placement`);
  - `fact_period_scoring` (every rostered player with an entry; no zero-fill);
  - `fact_matchup` (one row per team, schedule FPts; W/L/T derived);
  - `fact_standings` (`rank`, `playoff_odds`, `salary_remaining` only).
- `fact_fantasy_teams` is the current Roster State all year; `roster_status`
  becomes `roster_slot` (a comment goes on #110).
- Players by `scorer_id` only. Age is derived from `birth_date`. No YTD
  columns. `dim_division` comes from public `getLeagueInfo`. Playoffs are out
  of scope (owner's choice; no ticket).
- Scoring, matchup and standings rows load once `allEventsFinished` is true.
- The matchup Close check is defined (ADR-0008 decision 7 carries a note).
- CONTEXT gains Team Score, Matchup and Standings; Period Scoring, Roster
  State, Update-Set, Scoring Period and Division are edited.
- Payload facts are recorded in the research doc ("Still open" item 4 is
  answered).
- Builds, both sub-issues of #70: **#117** Roster State (← #113,
  cap-ledger-auditor review), then **#118** Scoring (← #117; includes `04s`
  `playerViewType:'2'`). #93 ← #117; #116 ← #118, replacing ← #81.
- Done 2026-10-03 on the owner's go: blocked-by links wired and verified;
  comments on #110 (`roster_slot`), #97 (the `salary_remaining` check) and
  #86 (`dim_scoring_period`); map #70 "Decisions so far" has #81, #79 and
  ADR-0019; merged as PR #119; #81 closed with a Resolution.

**#117 grilled ✅ 2026-10-03 (Q1–Q8, every answer the recommended option).**
Nothing is built. The plan is in
`C:\Users\benha\.claude\plans\composed-juggling-rainbow.md`; **the owner
approved it 2026-10-03**, including its "My defaults" list (two new scripts
`04p_fantrax_league_info.py` and `04r_fantrax_roster_state.py`; `start_at` /
`end_at` on `dim_scoring_period`; `capture_date` on `fact_roster_state`; the
division Gate in the parser; the `Stint` glossary text). One PR per window,
compact between them, commit and PR only when asked.
1. **Period day.** A closing or closed period's Roster State counts as its
   `end_date`; the open period counts as the day it was captured. Test it on
   a real in-period claim once `04t` is rerun, and report.
2. **Stint start.** A draft pick and a claim read contract *and* salary off
   the first Roster State inside the stint they start, else the default.
   Amends ADR-0019 decision 6. The preseason capture is still never read for
   a contract.
3. **Preseason salaries.** A frozen `fact_preseason_salary`, keyed
   `(season_id, team_key, scorer_id)`, with `salary` and `capture_date`
   only, written once from today's `fact_roster_placement`. `02d` reads it
   for salary beside `fact_roster_state`.
4. **Update-Set state.** #117 writes `open` and `closing` only. The
   transition function is built and tested for all three states; `closed`
   waits for the scoring Close checks (#118, #116).
5. **`02e` slots.** Stamped from the newest period in `fact_roster_state`.
   `roster_status` keeps today's values (`Active` / `Reserve` / `Inj Res` /
   `Minors`) until #110. Flag the post-period-12 gap on #97.
6. **Draft tiers.** Both ADP tiers get a league-minimum floor; the
   any-season tier becomes "league minimum, with a warning".
7. **`04t`.** The owner reruns it before the window that repoints `02d`.
   The table-building PRs do not wait.
8. **Three PRs.** (1) `getLeagueInfo` capture, `dim_scoring_period`,
   `dim_division` from Fantrax, `01g` retired. (2) `fact_roster_state`,
   `fact_preseason_salary`, Gates, the pipeline step. (3) Retire
   `fact_roster_placement`: `02d` repoint, `02e` slots, `04v` cut down,
   other readers, republished ledger and roster, auditor. (3) closes #117.
- Payload facts probed 2026-10-03 (public, no login):
  - `getLeagueInfo.scoringPeriods` is a list of 17 `{number, startDate,
    endDate}` with Eastern-offset timestamps; periods turn over Thursdays
    at 20:15 ET. `playoffs.firstPlayoffPeriod` is `'13'`.
  - `teamInfo` is a dict of 28 `{id, name, division}`; one division name
    has a trailing space, so strip it.
  - `getTeamRosters` echoes `period`; with none it returns the current one
    (4 today). **A future period returns the current roster under the
    future number**, so never request past the current period.
  - `getLeagueInfo.matchups` lists 14 matchups for each of the 17 periods
    (useful to #118).
- Measured: salary and contract are identical on all 1,054 copies shared by
  periods 1 and 3. Dropping the preseason capture would un-price 14
  stint-starting rows (8 picks, 6 claims; 9 above the minimum).
- `04u` and `dim_division` are not in the scheduled pipeline today
  (`dim_division` has no `chain`). `04e` reads `fact_roster_placement` for
  who is rostered per Conference.

**#117 PR 1 BUILT 2026-10-03 on branch `feat/117-league-info` — not
committed, no PR yet (waits for the owner's go).** "Part of #117".
- `notebooks/04p_fantrax_league_info.py` (new, pipeline step
  `04p_league_info`, `fantrax_core`, group `regular_season`, after `01f`,
  all phases): one public `getLeagueInfo` call → `dim_scoring_period` and
  `dim_division`, both replace-by-`season_id`. Raw to
  `data/raw/fantrax_public_leagueinfo.json`.
- `etl_helpers.fantrax_public_get(method, league_id, expect=(), **params)`:
  raises on a non-200, an `error` body (Fantrax sends errors as HTTP 200),
  a non-JSON body, or a missing `expect` key. PR 2's `04r` uses it for
  `getTeamRosters`.
- `parse_scoring_periods(info, now, prior=None, checks_passed=frozenset())`
  and `update_set_state(start_at, end_at, next_end_at, now, is_playoff,
  prior=None, checks_pass=False)`. `checks_passed` is the seam for #118 /
  #116; #117 passes none, so no period closes. A closed period is carried
  forward from the published table, with its `closed_at`.
- `dim_scoring_period` columns: `season_id`, `period`, `start_date`,
  `end_date` (`datetime64[us]`, Eastern days), `start_at`, `end_at`
  (`datetime64[us, UTC]`), `is_playoff`, `update_set_state`, `closed_at`.
  Written: 17 rows, 12 regular season; period 4 `open`, 1–3 `closing`.
  Period 11 ends Wed 2026-11-25 19:59:59 ET (Thanksgiving week).
- `dim_division`: the Fantrax load is byte-identical to `main`, so the
  parquet is not in the diff. `01g` moved to `archive/` (`git mv`).
- Fixture `tests/fixtures/fantrax/league_info.json`: `seasonYear`, the two
  `playoffs` keys, four teams' `id` and `division`, and **all 17 periods**
  (the plan said four; the parser requires periods numbered 1..n).
- Verified: `pytest tests/` 269 pass (44 new); `check_data_model.py` (28
  tables) and `--check`; `check_sources.py` (14 sources) and `--check`;
  `--check-only` 142 checks, 0 Gate failures, 2 review findings
  (`grain_null_key`: dynasty 1,812, trade_log 125); `--dry-run` shows
  `01f → 04p → 01e → 04a …`; a second `04p` run is byte-identical;
  `check_pii.py` clean on all 24 changed files. Bot suite not run (no bot
  code or bot-read data changed).
- Changed files: `04p` (new), `etl_helpers.py`, `run_pipeline.py`,
  `make_fixtures.py`, `data_model.yml` + `DATA_MODEL.md`, `sources.yml` +
  `SOURCES.md`, `notebooks/README.md`, `data/README.md`, ADR-0005 and
  ADR-0016 amend notes, `docs/research/storage-seam-inventory.md`, three
  memory files, `PLAN.md`, this file, three test files, the fixture,
  `data/dim_scoring_period.parquet` (new).

**NEXT: commit and open the PR for PR 1 when the owner says so. Then, after
a compact, PR 2 (`feat/117-roster-state`):** `04r_fantrax_roster_state.py`,
`fact_roster_state`, `fact_preseason_salary`, the coverage and contract
Gates. PR 3 (`feat/117-retire-placement`) waits for the owner's `04t`
rerun; its window starts by checking the history runs past 2026-07-24. Then
#118, which is plan-gated: grill and plan first, in its own window. Read
the #117 issue and its hand-on comments (from #115, #113 and #125) before
building.
- Scratchpad for #117: `g117_facts.py` (table counts), `g117_probe.py` and
  `g117_probe2.py` (public payload shapes, keys and counts only).
- Owner calls still open from the #125 audit (see "Open after the audit"
  below; items 1–3 need the owner): the stale cap (rerun `04t`, owner's
  login), the `FA` contract on a re-priced claim, the lower draft tiers.
- The post-#125 RESUME and PLAN.md edits ride on the PR 1 branch.

**#125 DONE 2026-10-03 — merged as PR #126 (`376a842`), branch deleted; the
PR closed #125.** The ledger and roster on `main` are now the `02d` → `02e`
rerun, so a pipeline run may include `02d` and `02e` again.
Plan (approved): `C:\Users\benha\.claude\plans\composed-juggling-rainbow.md`.
Issue #125 is a sub-issue of map #70.
- Owner decisions, grilled 2026-10-03 (both the recommended option):
  1. A drafted player's salary comes from the roster snapshot first, then
     draft-time ADP.
  2. Claims too: one rule for both moves that start a stint.
- The rule as built (`02d`, "Salary sourcing" block): a draft pick or a
  claim takes `contract_value` from the first `fact_roster_placement`
  snapshot with `move day < capture day < the day the copy next left that
  team`. The `PRE` snapshot is read for salary (not for contracts). Else: a
  pick → `fact_fantrax_adp` of `season == CFG.draft_year`, latest capture on
  or before the pick, else the earliest after, else the latest of any
  season; a claim → inherited salary, else the league minimum. Trades and
  drops carry the copy's salary.
- My choices, not ruled on by the owner (flagged in the report):
  - a draft row's stint ends at the copy's first departure from the drafting
    team, whatever its date (draft `event_date` is a UTC date; transaction
    dates are local);
  - a claim's stint end is the first departure strictly after its timestamp;
  - `repriced()` scales the ledger's unread `cap_hit` by the share it had of
    the old salary;
  - a pick with no date reads the draft season's earliest capture.
- API changes: `build_startup_rows(made, team_lut, sid2aid, gsis_lut,
  draft_salaries, src, departs)` returns `(fact, tally, priced)`;
  `resolve_legs` returns a fifth value, `snapshot_priced`; `ContractSource`
  has `salaries`; `main()` parses the transaction legs before the draft rows.
- Measured on the rerun (`02d` → `02e`), against a baseline rerun of the
  pre-change code:
  - Ledger differs only in `contract_value` (44 rows: 36 draft, 8 claim, all
    upward, +$176.0M) and `cap_hit` (29 rows). Roster differs only in
    `contract_value` (44 rows). `contract_id` counts unchanged (354 draft, 14
    trade, 11 claim on `Minor`).
  - Draft salaries read off: 946 roster snapshot, 27 ADP on or before the
    pick, 2 ADP after the pick. Claims: 16 off the snapshot, 37 at the
    league minimum.
  - Against Fantrax period 1: all 1,004 active roster rows found there match
    (baseline 962: draft 902 of 938, claim 31 of 37, trade 29 of 29). Period
    3: all 993 match (baseline 952). The first commit and PR text said 1,006
    and 995: `p01_salary.csv` and `p03_salary.csv` hold one scorer twice on
    two teams, which inflated the join by 2. Dedupe on `(team_key,
    scorer_id)` before joining.
  - Cap totals vs baseline: 13 of 28 teams move, active roster salary
    +$170.7M, dead money 0. Vs `main`'s published roster: 23 teams move,
    +$276.6M. Lowest remaining cap is now $561K; no team is over.
  - `pytest tests/` 221 pass (33 new); bot suite 8 pass; `check_data_model.py
    --check`, `check_sources.py --check` pass; `--check-only` 137 checks, 0
    Gate failures.
- The commit carries: `02d`, `tests/test_02d_contract_sourcing.py`,
  `docs/data_model.yml`, `notebooks/README.md`,
  `.claude/memory/data-model.md`, `PLAN.md`, this file, and the two
  regenerated tables (`fact_roster_transactions`, `fact_fantasy_teams`).
  The other three `02d` outputs are identical to `main`.
- Scratchpad: `baseline125/` (pre-change rerun), `baseline_main/` (`main`'s
  tables), `vs_fantrax.py`, `cap125.py`, `issue_salary.md`.
- **`cap-ledger-auditor`, 2026-10-03: no defect.** It re-ran the table
  diff, the Fantrax comparison, the cap totals and the suites; all held.
  Fixed in the follow-up commit: ADR-0019 decision 6 and ADR-0003 notes that
  salary is sourced on its own, the `data_model.yml` wording, "roster
  snapshot" instead of "Roster State" in the salary comments, a "Known
  limits" comment, and tests (`TestRepriced`, the other Conference's copy).
  No code path changed, so the data was not rerun.
- **Open after the audit (not fixed; each needs the owner or a later
  ticket):**
  1. **The published cap is as of 2026-07-24.** The transaction history ends
     there. One team shows $561K of room; on Fantrax's period-1 roster it
     has about $23.5M. The gap is six claim rows that team no longer holds
     (two of them re-priced here). Fantrax period 1 also has 65 rostered
     players the ledger lacks. Fix: rerun `04t` (owner's login), then `02d`
     → `02e`. Until then per-team cap room can be off by $10M–$23M.
  2. **A re-priced claim keeps `FA`** (claims always default; `PRE` is unread
     for contracts). Fantrax shows `1st` on four of the eight. No cap effect
     today. A later cut would price 0 dead money under `FA` and about half
     the salary under `1st`. Needs an owner ruling; belongs with #117's
     "how a claim reads its own period" and #96.
  3. **The two lower draft tiers are weak.** The capture after the pick
     carries Fantrax's re-price ($2.0M where the roster says $2.6M–$4.7M on
     five players), and the any-season tier gives $800K for one player,
     below the league minimum. Today the snapshot prices all six. Auditor's
     proposal: floor at the league minimum and drop or NA-and-warn the
     any-season tier. That changes the approved rule, so it is the owner's.
  4. **#117 retires the `PRE` snapshot** (`fact_roster_state` starts at
     period 1). Picks and claims that left before period 1 then lose their
     snapshot salary. Keep the preseason salaries somewhere before
     `fact_roster_placement` goes.
  5. Latent, not in the data: a claim traded away before its first snapshot
     keeps the default; `snapshot_salary` is not bounded by season; a draft
     row's stint ends at any departure, even one dated before the pick
     (kept: it matches `02e`'s replay order).
  6. Tests still missing: a `main()` smoke test (already on #117), a
     published-ledger invariant (one salary per copy per Conference, none
     below the minimum; fits #116).
  7. "Stint" is not in `CONTEXT.md`. It is used in ADR-0019 and `02d`.
- **After-merge items DONE 2026-10-03 on the owner's go:** a Resolution on
  #125, and a hand-on note on #117 (re-point the salary index with the
  contract index, keep the preseason salaries, "first snapshot" against an
  open period, bound the lookup by season, `FA` on a re-priced claim, a
  claim traded before its first snapshot, the ledger's 2026-07-24 as-of).
  Nothing was posted on #96 or #97; the `FA`-vs-`1st` cut cost is raised in
  the #117 note only.
- Gotcha: `scripts/check_pii.py` raises on a path outside the repo. Copy a
  scratchpad draft into `workspace/` to scan it, then delete the copy. And
  do not pipe a check through `tail` in an `&&` chain: the pipe hides the
  failure.

**#113 DONE 2026-10-03 — merged as PR #124 (`493a6d7`), branch deleted; the
PR closed #113.**
Plan: `C:\Users\benha\.claude\plans\composed-juggling-rainbow.md`.

**After-merge items DONE 2026-10-03 on the owner's go:** a Resolution on
#113; comments on #117 (re-point the lookup, the claim's own period, `FA` on
eligible claims, claim pricing, `PRE` by label, season scope, `04v`'s two
dates, missing tests), #96 (`Minor` drops price zero) and #77 (`Int64`
columns). The #97 note (ledger `cap_hit` not recomputed on a relabel) is in
the #113 Resolution only; no comment on #97.
- Correction: `dim_contract` is not the only `Int64` table.
  `fact_rookie_rankings` has three `Int64` columns. The #77 comment says so;
  PR #124's body still has the old wording.

This RESUME edit and the matching PLAN.md lines are uncommitted on `main` —
fold both into the salary-sourcing branch (see NEXT above). The auditor fixes went in before
the PR. Owner answers, grilled 2026-10-03 (all four the
recommended option), and how each landed in `02d`:
- Item 2 → a move reads only snapshots captured **strictly before** its day.
- Item 3 → each copy remembers the day it joined the team (its stint); a
  move reads only snapshots from that day on. Rule in one line:
  `since <= captured < move day`. `resolve_legs` keeps a `stint_start` dict
  beside `copy_terms`. A draft pick and a claim start a stint, so both
  always default.
  - *Managing session's reading, not an owner answer:* a copy with no stint
    on record (the ledger never saw it join) reads any snapshot before the
    move day.
- Item 4 → `eligible_at` names the capture that lists the player: `next`
  (first on or after the move day), `previous` (the last one before it,
  when the next one dropped them) or `newest` (the move postdates every
  capture), else None. `sourcing_report` prints the two "decided by the
  earlier capture" counts apart: 8 after the newest capture, 0 graduates.
- Item 5 → `stale_capture`: the report warns with the count of moves that
  defaulted more than 8 days past the newest eligibility capture (0 today).
  Labels unchanged.
- Item 6 → `index_snapshots` drops blank contracts and null capture dates.
- `resolve_contract` returns a `Sourced` tuple (`contract_id`, `observed`,
  `after_newest`, `left_list`, `stale_capture`); the builders return
  `tally_sourcing`.
- Tests: `test_02d_contract_sourcing.py` 31 → 63. ADR-0019 decision 6 amend
  notes and the `data_model.yml` ledger note are in line.
- Re-run 2026-10-03: `pytest tests/` 188 pass; bot suite 8 pass; registry
  checks pass; `02d` → `02e` gives the same labels and the same diff against
  `baseline/` as before the fixes (counts below); `cap_totals.py` identical
  for 28 teams; `--check-only` 137 checks, 0 Gate failures. The two `fact_*`
  parquet are restored to `main` (they stay out of #113's commit).

*Second `cap-ledger-auditor` pass (on the fixes), 2026-10-03.* It found no
fault in the stint tracking, `eligible_at` or the tallies. Fixed from it: the
null-capture-date crash, the split count, `sourcing_report` extracted and
tested, two pinned edge cases (chained same-day trades; a trade with no
stint on record), the `dim_contract` read moved into a fixture. Left open,
to raise on the tickets named:
- #97: a relabelled leg keeps the inherited ledger `cap_hit` (a graduated
  `Minor` → `1st` keeps 0; an eligible claim keeps the 2.0M FA figure).
  Nothing reads the column.
- #117: `derive_week_label` returns `PRE` until 2026-09-14, so a `04v` run
  on 09-10..09-13 would be dropped as preseason and would overwrite the
  07-18 capture; the eligibility index is not season-scoped either, so an
  old list can stamp `Minor` over a `2nd` next season (the stale warning
  fires, the label stays); `04v` calls `date.today()` twice, so a run
  across midnight splits the two tables' dates.
- Not ticketed: draft `event_date` is a UTC date, so a pick made after about
  19:00 Central is dated a day late (pre-existing; no label changes today).

*`cap-ledger-auditor` review — returned 2026-10-03. The findings:*
1. The two `fact_*` parquet carry the stale-roster catch-up (see the next
   block). Its suggestion: leave both out of #113's commit.
2. `snapshot_contract` uses `captured <= day`. `04v` re-stamps a week's
   snapshot with today's date, so a same-day claim's label depends on run
   timing. Suggested: `captured < day`, plus a test.
3. The snapshot lookup has no continuity rule: a copy dropped and re-claimed
   after graduating reads an older `Minor` snapshot. Suggested: keep the
   acquisition date in `copy_terms` and ignore older snapshots.
4. `eligible_at` reads absence from a later capture as ineligible. A player
   who graduates between the move and that capture is mislabelled.
   Suggested: absent later but present in the latest earlier capture →
   eligible. `test_02d_contract_sourcing.py:99` pins today's behaviour.
5. The "else the latest capture" fallback is unbounded: with only the 07-18
   capture, every later move by a then-eligible player is stamped `Minor`.
   Suggested: warn when a move is ~8+ days past the newest capture.
6. A blank snapshot contract (`04v` emits `""`) becomes a dangling
   `contract_id`; `index_snapshots` filters only nulls. Suggested: filter
   blanks; file unknown ids as a Review finding.
- Not verified by the managing session yet: the `04v` claims in 2 and 6.
- It found nothing reading the ledger `cap_hit`, no cap effect from a stale
  `Minor` label, and restructure parity on the edge paths. It also noted
  `discord_bot/player.py:178` reads a `cap_hit` column `fact_fantasy_teams`
  dropped on 07-11 (pre-existing, renders blank).
- Follow-ups it listed for #117/#116/#77: the snapshot index is not
  season-scoped; `PRE` is excluded by label, not by date; `dim_contract` is
  the only `Int64` table (tell #77); missing tests (a `main()` smoke test,
  claim/drop legs through the snapshot branch, re-run determinism);
  `TestPublishedDimContract` reads `data/` at import time.

*Fantrax comparison — done (payload analyst, counts only, not re-verified):*
- Period 1 shows 352 `Minor` rows; our roster has 365; 347 agree on
  `(team_key, scorer_id)`. Period 3: 350 on Fantrax, 345 agree.
- No shared copy is `Minor` on Fantrax and something else on ours. Fantrax's
  other 5 `Minor` rows are copies not on our roster (moves after our
  transaction capture ends, 2026-07-24).
- Ours `Minor`, Fantrax not (period 1): 19. Six drafted players show `1st`
  (the analyst reads them as graduated; not verified). **Seven claimed
  players show `FA`.** Six copies are no longer on that team.
- **Flag for the owner / #117 / #116:** all 10 of our active `Minor` claims
  fail to match: 7 show `FA` on Fantrax, 3 are gone. So Fantrax has not put
  any checkable eligible claim on `Minor`, though ADR-0019 decision 5 says
  it should. No cap effect (`Minor` and `FA` both price zero). These are the
  "eligible player on `FA`" mismatches the drift check is meant to file;
  once #117 reads Roster State, the observed `FA` wins.
- The analyst's period-3 breakdown was approximate; only its headline counts
  are used above.
- Relayed to the owner 2026-10-03. PLAN.md already says #113 is built.

*Catch-up data PR — NOT landed; owner decision owed (2026-10-03):*
- The owner said "land the catch-up as its own data PR first". The managing
  session reran `02d` → `02e` on clean `main` (`3ac5fed`), which reproduced
  the saved baseline exactly, then stopped before committing. Nothing was
  pushed; the branch was deleted unpushed.
- Why: the committed `fact_fantasy_teams` is stale (published 2026-07-26),
  but the rerun is wrong in a new way. `02d` prices a draft row from the
  *latest* `fact_fantrax_adp` salary. Fantrax re-set 462 pool salaries to
  $2.0M between the 06-09 `DRAFT` capture and the 07-31 `PRE` capture; 30
  drafted players (all IDP) are among them. Fantrax's roster still charges
  the draft-time salary.
- Against Fantrax's period-1 roster salaries (`p01_salary.csv` in the
  scratchpad, payload analyst extract; period 3 agrees):
  - roster on `main`: 985 matched, 854 equal, 125 blank, 6 different;
  - rerun: 1,006 matched, 964 equal, 0 blank, 42 different (36 draft rows,
    6 claims; ours is $2.0M on 41 of them, −$165.1M in total).
- Simulated fix, draft rows only: price from the `DRAFT` capture, else the
  latest. 933 of 939 equal (today 903); the gap falls from −$124.7M to
  −$9.1M. The 6 left are players absent from the `DRAFT` capture.
- `main`'s ledger already holds the 30 at $2.0M (built 08-04). `main`'s
  roster does not, so the bot shows them right today. Any full pipeline run
  (`02d` → `02e`) would publish the wrong values straight to `main`.
- The 6 claim rows are a second, older gap: a no-history claim is priced at
  the $2.0M minimum, Fantrax charges more. They differ on `main` today too.
- By capmath, `main` → rerun moves 24 of 28 teams (−$16.7M … +$27.2M; league
  $6,429.2M → $6,535.1M). 127 rows gain a value, 29 gain an identity.
- **Owner decided 2026-10-03: #113 goes first with no fact data.** #113's
  PR carries code + `dim_contract.parquet` only. The two `fact_*` parquet in
  the working tree were restored to `main`'s versions. A follow-up PR (not
  ticketed yet; plan-gated) fixes draft pricing on #113's new seams with a
  test and publishes the ledger and roster once, checked against Fantrax
  salaries. Until then no pipeline run should include `02d`/`02e`.
- Both `04v` claims behind auditor items 2 and 6 were checked and hold:
  `04v` stamps `capture_date = today` and replaces a `(season, week)`
  partition; an empty contract cell is written as `""`.
- All #113 parity numbers below are against that rerun baseline, saved in
  the session scratchpad (`baseline/`), not against `HEAD`.
- Scratchpad: `catchup_numbers.py`, `catchup_roster.py`, `catchup_cap.py`,
  `replay_main/`, `main_fft/`, `wip113/` + `wip113.patch` (backup of the
  #113 work before the rebase).

*What was built:*
- `01b`: `Minor` row first in `_CONTRACT_DEFS`; years cast to nullable
  `Int64`; `cap_exempt` comment says it is descriptive only. 11 rows.
- `02d` step A: all I/O in `main()` behind `__main__`; pure
  `parse_draft_results`, `build_draft_picks`, `mint_assets(scorer_ids,
  existing, gsis_lut, pkey_lut)`, `build_startup_rows`, `rows_from_pages`,
  `parse_txn_rows` → `(trade_log, legs, stats)`, `sort_legs`, `fa_terms`,
  `resolve_legs`. Parity: all five tables identical to the baseline.
- `02d` step B: `ContractSource` (snaps, elig, years, pcts),
  `index_snapshots` (drops `week == "PRE"`), `index_eligibility`,
  `snapshot_contract`, `eligible_at`, `default_contract`,
  `resolve_contract` → `(contract_id, observed)`, `contract_year_of`,
  `unknown_contracts`. Constants `MINOR_CONTRACT_ID`, `DRAFT_CONTRACT_ID`
  (was `CONTRACT_ID`), `FA_CONTRACT_ID`, `PRESEASON_WEEK`.
- Fixtures: `draft_results.json` (Wilson, rounds 1–2, two traded slots in
  round 2) and `txn_history.json` (one trade with 2 player + 2 pick legs, a
  claim+drop pair, a lone claim, a lone drop). The trimmer drops `content`
  from team cells and swaps the pick owner hint for `(Team (X))`, because
  both hold fantasy team names; a test in `test_fixture_allowlist.py` holds
  a regenerated fixture to that.
- Tests: `tests/test_02d_contract_sourcing.py` (31), `test_fantrax_parsers.py`
  (`TestDraftResults`, `TestTxnHistory`), bot
  `test_capmath_minor_cut_costs_no_dead_money`.
- Registry/docs: `data_model.yml` (`Int64` years + notes), `Dim_Contract.tmdl`
  (11 rows, `CapExempt` description), `_Measures.tmdl:247` comment, `04v`
  header, `test_04v` wording, `run_pipeline.py` docstring, `sources.yml` +
  re-rendered `SOURCES.md`, ADR-0019 status + italic amend notes, READMEs,
  `data-model.md`, `project-fantasy-football.md` contract table.

*Measured:*
- 354 draft rows, 14 trades (28 rows) and 11 claims on `Minor`; 0 moves read
  a snapshot (only the `PRE` snapshot exists). Roster: 365 `Minor`.
- Ledger differs from the baseline only in `contract_id`, `contract_year`,
  `cap_hit`; roster only in `contract_id`, `contract_year`.
- `capmath.teams_with_cap` identical for all 28 teams.
- `pytest tests/` 152 pass; bot suite 8 pass (run in a throwaway venv built
  from `discord_bot/requirements.txt`: `.venv` has no `discord`, and there is
  no `.botvenv` on this machine); `run_pipeline.py --check-only` 0 Gate
  failures; `check_data_model.py` + `--check`, `check_sources.py` +
  `--check`, `check_pii.py` on every changed file all pass.

*Known wart, flagged to the auditor:* the ledger `cap_hit` column is
inconsistent on `Minor` rows (0 on draft rows, the league minimum on a
no-history claim, 0 carried onto a graduated `1st` leg). Nothing reads it;
#97 replaces it.

*After merge, on the owner's go:* #113 Resolution; comments on #117 (re-point
the lookup at `fact_roster_state` by period; how a claim reads its own
period) and #96 (`Minor` drops price zero through `dim_contract`).

The side session's `overall_rank` fix merged 2026-10-03 (PRs #121–#123).

**#115 DONE 2026-10-03**: merged as PR #120 (`e57034c`), #115 closed with a
Resolution, comments posted on #113/#117/#118. Still open: the owner makes
`tests`/`bot-tests` required checks; the `overall_rank` bug below is
unticketed (task chip offered). This RESUME edit and the PLAN.md "PR
pending" wording were folded into the #113 branch (PR #124). What landed:
- `notebooks/etl_checks.py` holds the Table Gates, coverage and
  `review_check.csv` filing. `docs/data_model.yml` gains `chain` and
  `required_keys` and registers `fact_trade_log`.
- `run_pipeline.py` adds per-Chain `plan_publish`, a `commit_data` that
  restores held Chains and stages explicit paths, and the `--check-only` and
  `--accept-shrink` flags.
- Fixtures: `scripts/make_fixtures.py` writes `tests/fixtures/fantrax/` (4
  fixtures, allowlist-pruned). There are 4 new test files, and
  `.github/workflows/tests.yml` runs `tests` and `bot-tests`.
- `--check-only` today: 0 Gate failures and 3 `grain_null_key` findings
  (29 / 1,812 / 125).
- Found while building: `fact_fantrax_adp.overall_rank` was 100% null for
  2026 wk01–02. **Fixed 2026-10-03** (PRs #121, #122). The cause was the
  `BY_DATE` request used by `--rebuild-week`, not in-season pulls in general;
  detail in [fantrax-players-grid.md](fantrax-players-grid.md).

Plan was `C:\Users\benha\.claude\plans\composed-juggling-rainbow.md`.
Owner decisions (planning window):
1. Parser tests only for parsers that exist (04a, 04u picks, 04s schedule
   helpers, 04v `rosters_to_frame`); `make_fixtures.py` extensible. 02d seam
   → #113, `getLeagueInfo` → #117, live scoring/standings → #118 (comments
   after merge).
2. Grain Gate over complete-key rows; null-key rows file one
   `grain_null_key` Review finding per table (ff_teams 29, dynasty 1,812,
   trade_log 125 today).
3. Pipeline stages only passing Chains' tables; the 10 manual-only tables go
   to `main` by PR.
4. nflverse Chain starts now with 01e.

**#75 grilled ✅ 2026-10-02** (Q1–Q17) →
[ADR-0018](../../docs/adr/0018-supabase-schema-and-rls.md), merged PR #107.
#75 closed with Resolution; map #69 "Decisions so far" updated; hand-off on
#77. New #69 children: **#108** registry-generated migrations +
`migrate.yml` + first migration (← #76 #109 #110) · **#109** trade-log pick
legs → Original Owner (`pick_ref`) + mint assets · **#110** grain fixes
(Composite, `fact_fantasy_teams` `scorer_id`, combine orphans,
`division_id`; also blocks #77 per seam-inventory §8 prereqs) · **#111**
post-cutover orphan resolution without manual queues (← #108).
Note: `grill-with-docs` is user-invoked only — ask the owner to type it.

Approved by the owner on 2026-10-02 — next in order:

1. ~~Reconcile ADR-0011 with the `Minor` contract~~ ✅ ADR-0019 (above).

Done 2026-10-02: research docs landed in `docs/research/`, issue links
repointed, `research/*` and `feat/78-inseason-capture` remote branches
removed; repo `user.email` set to the noreply address; **#79 closed** —
findings in `docs/research/inseason-schema-extraction.md`.

In flight:

- **04v IR fix merged ✅** (PR #106, 2026-10-02): IR rows are kept in
  `fact_roster_placement` as `"Inj Res"` (Fantrax's own `statusTotals`
  name) and charged per ADR-0011; cap totals unchanged. The first
  in-season 02e run may list IR players as placement orphans (ledger
  gaps surfaced, no cap effect).
- #83 done (PR #103). **#79 done 2026-10-02**: both agent reports
  were rejected (totals did not reconcile; the live-scoring file it cited
  was never saved), so the managing session recounted everything itself.
  Results, all in `docs/research/inseason-schema-extraction.md`:
  - Public `getTeamRosters` has all four Roster Slots + salary + contract,
    0 nulls, and equals the authed roster call row for row → the Change
    Poll can persist it with no login (ADR-0016 decision 3 confirmed).
  - `period=N` returns real past periods in-season (the 02d:496-518
    comment is preseason-only).
  - `playerViewType:'2'` puts Bench, IR and Minors under `BENCH`; only
    complete once the period is final.
  - No `matchupId` anywhere; `divisionId` only in public `getLeagueInfo`.
  - Code follow-ups, not ticketed yet: `04s` line 145 needs
    `playerViewType:'2'`; the 02d:496-518 comment; `dim_contract` has no
    `Minor` row.
- The Fantrax stored session was alive on 2026-10-02 (one read-only call
  succeeded), so the overdue weekly pull can run without a manual login.

After that:

- Build, plan-gated: #113 (built, auditor review + PR pending) → #117 →
  #118 (#115 ✅ PR #120); #77 storage seam
  (inventory doc in `docs/research/`), which unblocks #86 and #93. Then
  #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; run the
  overdue weekly pull; #76 provisioning. Map #65 can be closed on GitHub.
- AFK frontier: #92 spike (TOTP-first, see its comment), #68.
- Leftover to clean up: agent worktree under `.claude/worktrees/` with local
  branch `docs/83-sources-truth-up` (superseded by PR #103).

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

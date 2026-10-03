# RESUME — Supabase + in-season ETL maps (updated 2026-10-03)

**Managing session**: `dynastyFantasyFootball-central-builder`. It fires the
AFK tickets as background sessions, reviews what they return, and posts to
GitHub; HITL grills happen in the managing session.

**Git state**: `main` = 3cdcabd (PR #106 04v IR fix), after the 2026-10-02
docs PRs #102 memory/PLAN reconcile, #103 sources truth-up, #104 research
docs, #105 #79 findings; then `main` = 2fa8e3e (PR #107 ADR-0018); then `main` = 1a70ce1 (PR #112 ADR-0019 Minor
reconcile); then `main` = 9458c9d (PR #114, #88 test strategy: ADR-0008
amended in place); then PR #119 (#81 fact model: ADR-0016 amended in
place). History was rewritten
on 2026-09-27 (owner-PII scrub) — every SHA recorded before that date is
dead. `pii-scan` is a required check on `main`. Commit/PR only when the user
asks. Stage explicit paths only. Untracked and not ours (leave alone):
`.agents/`, `GEMINI.md`, `.claude/worktrees/` (agent worktrees).

**Closed since the last RESUME** (all merged): #95 owner-PII forward fix,
#100 `fact_fantrax_adp` gap fill + in-season universe floors (new
`04a --rebuild-week NN --through-date`), #101 scrub closeout. The Fantrax
password found in public history was rotated 2026-09-27 and the history
scrub is done. Also merged 2026-10-03: PR #121 (`04a` derives `overall_rank`
when Fantrax serves no Rk) and PR #122 (wk 01–02 rank backfill by offline
replay); `main` = 899be7a.

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

Next: builds, plan-gated — #113, then #117 → #118.

**#115 BUILT 2026-10-03** on `feat/115-check-suite` (PR pending the owner's
go; after merge: comments on #113/#117/#118, #115 Resolution + close, owner
makes `tests`/`bot-tests` required). What landed:
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

- Build, plan-gated: #113 → #117 → #118 (#115 built, PR pending); #77 storage seam
  (inventory doc in `docs/research/`), which unblocks #86 and #93. Then
  #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; run the
  overdue weekly pull; #76 provisioning. Map #65 can be closed on GitHub.
- AFK frontier: #92 spike (TOTP-first, see its comment), #68.
- Leftover to clean up: agent worktree under `.claude/worktrees/` with local
  branch `docs/83-sources-truth-up` (superseded by PR #103).

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

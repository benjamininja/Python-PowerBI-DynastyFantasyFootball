# RESUME — Supabase + in-season ETL maps (updated 2026-09-27, post-#85 grill)

**Git state**: `main` = 3f6c804 (PR #99 squash-merged, #85 done; local +
remote branch deleted). This RESUME edit is uncommitted on `main` — fold it
into the next docs branch.
Commit/PR only when the user asks. Stage explicit paths only.
Not mine (leave alone): `.claude/memory/MEMORY.md`, `mouserat-trade-bud.md`,
untracked `.agents/`, `GEMINI.md`, `.claude/worktrees/`.

**Side session (fact_fantrax_adp gap) — done 2026-09-27, uncommitted**:
root cause = pipeline never scheduled/run (no task, no workflow); the 2025 YTD
backfill never reached git. Filled: 2025/YTD (offline replay), 2026/01 + 02
(new `04a --rebuild-week NN --through-date` via BY_DATE; ADP/%D/Sal are
rebuild-day values). Also recalibrated `MIN_ACTIVE_BY_POS` to in-season floors
(old ones blocked every in-season pull). **Still to do**: Tue 09-29 (after MNF)
`.\run_weekly.ps1 --steps 04a_scrape,04z_crosswalk,04a_backfill_gp --no-commit`
→ 2026/03 + 2026/YTD + gsis refresh. Uncommitted: `04a_fantrax_weekly_scrape.py`,
`data/fact_fantrax_adp.parquet`, `data-model.md` — don't revert.

**Email-leak session** ("Remove leaked owner emails from public repo",
local_8a9a63f7…) shipped PR #95 (stop publishing owner PII + PII scan gate,
merged); session still open — verify what remains before touching its files. It
found a Fantrax password in public history (`notebooks/.env`, 66b79d8); the
user **rotated it 2026-09-27**, and the history scrub is still theirs to run.
01c still writes `manager_email*`. Don't touch 01c, `etl_helpers.py`,
`project-fantasy-football.md` until it lands.

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
- **#69 Supabase storage**: #72 ✅ · #73 ✅ · #74 ✅ · #75 schema+RLS (grill) ·
  #76 provision (HITL) · #77 build seam (task).
- **#70 In-season Fantrax**: #78 ✅ · #79 schema extraction (research; now also
  must confirm public roster fields incl. Roster Slot) · #80 ✅ · #81 fact model
  (grill, ←79) · #82 ✅ · #83 sources truth-up · #87 ✅ · #88 test strategy
  (grill) · #92 Actions login spike (**TOTP decided**) · #93 cadence build
  (←92,77,75,76,88; now also 04t orchestration + poll-writes-snapshot) ·
  **#96** `fact_dead_money` + stable move key (task) · **#97** shared cap
  module + cap table, 02e = snapshot+provenance (task, ←96,79).
- **#71 nflverse**: #84 ✅ · #85 ✅ (ADR-0017) · #86 build (←77; body rewritten).

## Next actions (no build work until the user says so)
1. **Next: `/grill-with-docs #88`** (test strategy). Owner re-enrolls the
   Fantrax authenticator to capture the TOTP setup key for #92.
2. HITL grill queue after #88: #81 (now has live-scoring input comment); #75 schema+RLS.
3. AFK frontier: #92 spike (now TOTP-first, see its comment), #79 (fantrax-payload-analyst; never read
   `data/raw/` in main context), #77 seam, #83, #68.

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

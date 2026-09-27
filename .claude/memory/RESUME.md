# RESUME — Supabase + in-season ETL maps (updated 2026-09-27, post-#82 grill)

**Git state**: branch `docs/82-roster-streams` (from `main` = 2179979, PR #94
merged). Uncommitted docs: `CONTEXT.md` (+Roster State, Roster Slot, Roster
Move, Period Scoring, Dead Money), new ADR-0016, amendment notes on ADR-0003 /
ADR-0006, `PLAN.md` (dead-money section rewritten; #82 ✅), this file.
Commit/PR only when the user asks. Stage explicit paths only.
Not mine (leave alone): `.claude/memory/MEMORY.md`, `mouserat-trade-bud.md`,
untracked `.agents/`, `GEMINI.md`, `.claude/worktrees/`.

**Email-leak session** ("Remove leaked owner emails from public repo",
local_8a9a63f7…) is still waiting at its plan gate; nothing written yet. It
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
- **#71 nflverse**: #84 ✅ · #85 grain (grill) · #86 build (←85,77).

## Next actions (no build work until the user says so)
1. User: commit/PR `docs/82-roster-streams` when ready (build tickets #96/#97
   created 2026-09-27; 04t orchestration folded into #93). Owner re-enrolls the
   Fantrax authenticator to capture the TOTP setup key for #92.
2. HITL grill queue: #85 → #88 → #81; #75 schema+RLS.
3. AFK frontier: #92 spike (now TOTP-first, see its comment), #79 (fantrax-payload-analyst; never read
   `data/raw/` in main context), #77 seam, #83, #68.

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

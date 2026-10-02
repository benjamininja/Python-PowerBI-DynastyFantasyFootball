# RESUME — Supabase + in-season ETL maps (updated 2026-10-02)

**Managing session**: `dynastyFantasyFootball-central-builder`. It fires the
AFK tickets as background sessions, reviews what they return, and posts to
GitHub; HITL grills happen in the managing session.

**Git state**: `main` = 65e1d4d (PR #101) plus the 2026-10-02 docs PRs
(#102 memory/PLAN reconcile, #103 sources truth-up). History was rewritten
on 2026-09-27 (owner-PII scrub) — every SHA recorded before that date is
dead. `pii-scan` is a required check on `main`. Commit/PR only when the user
asks. Stage explicit paths only. Untracked and not ours (leave alone):
`.agents/`, `GEMINI.md`, `.claude/worktrees/` (agent worktrees).

**Closed since the last RESUME** (all merged): #95 owner-PII forward fix,
#100 `fact_fantrax_adp` gap fill + in-season universe floors (new
`04a --rebuild-week NN --through-date`), #101 scrub closeout. The Fantrax
password found in public history was rotated 2026-09-27 and the history
scrub is done.

**Overdue, user-owned — weekly Fantrax pull**: `fact_fantrax_adp` stops at
`2026/02` (checked 2026-10-02). The run planned for Tue 09-29 did not happen:
`.\run_weekly.ps1 --steps 04a_scrape,04z_crosswalk,04a_backfill_gp --no-commit`
→ `2026/03` + `2026/YTD` + gsis refresh. Week 4 is now also due. It needs a
live Fantrax session (see the auth note below) until #92 lands.

**Research findings home** (done 2026-10-02): full findings for #73, #74,
#80 and #84 live in `docs/research/` on `main`; the issue Resolution
comments point there. New research tickets (#79 onward) land their findings
in `docs/research/` too.

**Environment gotchas found 2026-10-02**: the post-scrub re-clone had left
the repo `user.email` unset; it is now set repo-local to the noreply
address (owner's decision, 2026-10-02). Squash-merge commits on `main` are
authored by GitHub from the account's email setting, which local config
does not control — the owner turns on "Keep my email addresses private" in
GitHub. `.pre-commit-config.yaml` hard-codes `./.venv`, so commits fail
inside agent worktrees; commit from the main checkout instead.

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

## Next actions (compact handoff, 2026-10-02)

Approved by the owner on 2026-10-02 — do these in order:

1. **Settle #79** (see "In flight" below) — recount, verify the `Minor`
   contract claim, write the findings doc, post, close.
2. **Grill #75** (Supabase schema + RLS) with `grill-with-docs`, one
   question at a time. Inputs: the #75 body + its ADR-0015 scope comment,
   ADR-0014, ADR-0015, `docs/research/supabase-platform-facts.md`,
   `docs/reference/` (pattern reference only, kept out of git).

Done 2026-10-02: research docs landed in `docs/research/`, issue links
repointed, `research/*` and `feat/78-inseason-capture` remote branches
removed; repo `user.email` set to the noreply address.

In flight:

- **#79 schema extraction** (`fantrax-payload-analyst` background session).
  Its first report was **rejected** by the managing session — do not post
  it. Problems: 280 ACTIVE / 252 BENCH vs 310 / 464 from the 2026-09-27
  live call; a one-team sample used as proof; a contract named "Minor"
  reported, which conflicts with ADR-0011 and must be verified with counts;
  backfill "proof" was a quote from the #80 doc. It was sent back with an
  exact evidence list. **Its second report (2026-10-02) is still not
  postable**: its status counts sum to 764 while its contract-by-status
  counts and its own period-3 total are 1,099; it says IR players are
  public-only although the authed captures have statusId `"3"` rows; its
  BENCH coverage table uses the 764 base. Directionally it says yes to all
  three questions (public `getTeamRosters` has all four Roster Slots +
  salary + contract with 0 nulls; `period=N` returns distinct past periods,
  so the 02d:503-518 "period ignored" comment is preseason-only;
  `playerViewType:'2'` BENCH holds nearly all Reserve / IR / Minors).
  **Big claim to verify first**: a contract named `Minor` on ~138
  Minors-slot players plus ~190 others, which would contradict ADR-0011's
  "no Minor contract". The live responses are saved in the session
  scratchpad `issue79\` (`public_rosters_p1_response.json`,
  `public_rosters_p3_response.json`,
  `live_scoring_p3_playerviewtype2_response.json`,
  `public_league_info_response.json`, `inseason-schema-complete.md`); the
  scratchpad is session-scoped, so re-fetch the public ones if it is gone.
  Next step: the managing session recounts from those files with its own
  short script (print counts only, never dump the payload), then writes
  `docs/research/inseason-schema-extraction.md`, posts a Resolution comment
  on #79, closes it, and passes the answers to #81 / #93 / #96 / #97. If
  the `Minor` contract is real, ADR-0011 needs an amendment — raise it with
  the owner before #75 / #81 settle any contract columns. Likely
  follow-ups it surfaced: `04s` should send `playerViewType:'2'`; `04v`
  `STATUS_TO_SECTION_FALLBACK` lacks statusId `"3"` (IR).
- **#83** — done, PR #103.

After that:

- HITL grills: #88 test strategy, then #81 once #79 is settled.
- Build, plan-gated: #77 storage seam (inventory doc in `docs/research/`);
  unblocks #86 and #93. Then #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; run the
  overdue weekly pull; #76 provisioning. Map #65 can be closed on GitHub.
- AFK frontier: #92 spike (TOTP-first, see its comment), #68.
- Leftover to clean up: agent worktree under `.claude/worktrees/` with local
  branch `docs/83-sources-truth-up` (superseded by PR #103).

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

# RESUME — Supabase + in-season ETL maps (updated 2026-10-02)

**Managing session**: `dynastyFantasyFootball-central-builder`. It fires the
AFK tickets as background sessions, reviews what they return, and posts to
GitHub; HITL grills happen in the managing session.

**Git state**: `main` = 3cdcabd (PR #106 04v IR fix), after the 2026-10-02
docs PRs #102 memory/PLAN reconcile, #103 sources truth-up, #104 research
docs, #105 #79 findings. Branch `docs/75-schema-rls` carries ADR-0018 +
PLAN/RESUME/seam-inventory edits (PR pending owner go). History was rewritten
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
- **#69 Supabase storage**: #72 ✅ · #73 ✅ · #74 ✅ · #75 ✅ (ADR-0018) ·
  #76 provision (HITL) · #77 build seam (task).
- **#70 In-season Fantrax**: #78 ✅ · #79 ✅ · #80 ✅ · #81 fact model
  (grill) · #82 ✅ · #83 ✅ · #87 ✅ · #88 test strategy
  (grill) · #92 Actions login spike (**TOTP decided**) · #93 cadence build
  (←92,77,75,76,88; now also 04t orchestration + poll-writes-snapshot) ·
  **#96** `fact_dead_money` + stable move key (task) · **#97** shared cap
  module + cap table, 02e = snapshot+provenance (task, ←96,79).
- **#71 nflverse**: #84 ✅ · #85 ✅ (ADR-0017) · #86 build (←77; body rewritten).

## Next actions (compact handoff, 2026-10-02)

**#75 grilled ✅ 2026-10-02** (Q1–Q17) →
[ADR-0018](../../docs/adr/0018-supabase-schema-and-rls.md). Close-out still
to do, each on owner go: PR for branch `docs/75-schema-rls`; Resolution
comment + close #75; new #69 issues — (a) registry generator +
`migrate.yml` + first migration (←#76), (b) trade-log pick legs →
Original Owner (`pick_ref`), (c) grain fixes (Composite, `fact_fantasy_teams`
`scorer_id`, combine gsis orphans, `division_id`), (d) post-cutover
orphan-resolution approach (owner wants something better than manual
review queues); hand-off comment on #77 (tight types reach the snapshot).
Note: `grill-with-docs` is user-invoked only — ask the owner to type it.

Approved by the owner on 2026-10-02 — next in order:

1. **Reconcile ADR-0011 with the `Minor` contract** (not yet written; plan
   gate applies). Owner's reading, 2026-10-02: the other commissioner chose
   the fluid design — `Minor` is the category for anyone inside the
   minors-eligible window; the Minors space holds players and cap, moving
   up and down freely. Counts agree (349 of 351 `Minor` rows are eligible;
   only 138 sit in the Minors slot). To settle: reword ADR-0011, and how
   `dim_contract` represents `Minor` (it has no such row today).

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

- HITL grills: #88 test strategy, then #81 (unblocked by #79; needs the
  ADR-0011 reconcile first).
- Build, plan-gated: #77 storage seam (inventory doc in `docs/research/`);
  unblocks #86 and #93. Then #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; run the
  overdue weekly pull; #76 provisioning. Map #65 can be closed on GitHub.
- AFK frontier: #92 spike (TOTP-first, see its comment), #68.
- Leftover to clean up: agent worktree under `.claude/worktrees/` with local
  branch `docs/83-sources-truth-up` (superseded by PR #103).

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

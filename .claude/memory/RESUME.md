# RESUME — Supabase + in-season ETL maps (updated 2026-10-03)

**Managing session**: `dynastyFantasyFootball-central-builder`. It fires the
AFK tickets as background sessions, reviews what they return, and posts to
GitHub; HITL grills happen in the managing session.

**Git state**: `main` = 3cdcabd (PR #106 04v IR fix), after the 2026-10-02
docs PRs #102 memory/PLAN reconcile, #103 sources truth-up, #104 research
docs, #105 #79 findings; then `main` = 2fa8e3e (PR #107 ADR-0018); then `main` = 1a70ce1 (PR #112 ADR-0019 Minor
reconcile); then the #88 docs PR (ADR-0008 amended in place). History was rewritten
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
  #76 provision (HITL) · #77 build seam (task, ←110) · #108 migrations
  (←76,109,110) · #109 pick legs · #110 grain fixes · #111 orphans (←108).
- **#70 In-season Fantrax**: #78 ✅ · #79 ✅ · #80 ✅ · #81 fact model
  (grill) · #82 ✅ · #83 ✅ · #87 ✅ · #88 test strategy
  ✅ (ADR-0008 amendment) · #92 Actions login spike (**TOTP decided**) · #93 cadence build
  (←92,77,75,76 + #88 build (a); now also 04t orchestration + poll-writes-snapshot) ·
  **#96** `fact_dead_money` + stable move key (task) · **#97** shared cap
  module + cap table, 02e = snapshot+provenance (task, ←96,79).
- **#71 nflverse**: #84 ✅ · #85 ✅ (ADR-0017) · #86 build (←77; body rewritten).

## Next actions (compact handoff, 2026-10-02)

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
- Build (a), the foundation, can start now and fixes the
  commit-on-failure bug at `run_pipeline.py:325`.
- Build (b), the in-season checks, is blocked by (a), #81 and #93.
- #93 is now blocked by (a) instead of #88.

**On resume: start the #81 grill** (fact model). Ask the owner to type
`/grill-with-docs #81 fact model` (the skill is user-invoked only). Grill one
question at a time, recommended answer first, and plan-gate before any
write.

Read first:
- #81's body and comments;
- ADR-0016 decision 1 (Period Scoring);
- ADR-0017 decision 1 (per-period and by-Unit points);
- the #79 findings (`docs/research/inseason-schema-extraction.md`);
- `CONTEXT.md`: Period Scoring, Scoring Period, Update-Set, Unit.

Matchup grain is open in #81 (there is no `matchupId`), and so is the
matchup Close check the #88 amendment deferred to it.

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

- HITL grill: #81 (unblocked by #79, ADR-0019 and the #88 amendment).
- Build, plan-gated: #88 build (a) (can start now); #113; #77 storage seam
  (inventory doc in `docs/research/`), which unblocks #86 and #93. Then
  #96 → #97.
- Owner: re-enroll the Fantrax authenticator for the #92 TOTP key; run the
  overdue weekly pull; #76 provisioning. Map #65 can be closed on GitHub.
- AFK frontier: #92 spike (TOTP-first, see its comment), #68.
- Leftover to clean up: agent worktree under `.claude/worktrees/` with local
  branch `docs/83-sources-truth-up` (superseded by PR #103).

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

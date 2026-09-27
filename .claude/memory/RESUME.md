# RESUME — Supabase + in-season ETL maps (updated 2026-09-27, post-#87 grill)

**Git state**: **PR #94** open (`docs/87-run-cadence` → `main` = 08c5c80;
no CI checks on docs): `CONTEXT.md` (+Scoring Period, Update-Set, Drift,
Owner PII; Owner Manifest note), new ADR-0015, ADR-0014 amendment note,
`PLAN.md` map line, this file. User merges it (squash, `--delete-branch`),
then `git switch main && git pull`. Stage explicit paths only.
Not mine (leave alone): `.claude/memory/MEMORY.md`, `mouserat-trade-bud.md`,
untracked `.agents/`, `GEMINI.md`, `.claude/worktrees/`.

**Parallel session running**: task_5f6a95b6 "Remove leaked owner emails from
public repo" — 24 manager emails in saved outputs of tracked
`notebooks/01c_dim_fantasy_teams_seed.ipynb` (4 commits of history),
link-readable owner Google Sheet (ID at `etl_helpers.py:58`), 1 third-party
email in `.claude/memory/project-fantasy-football.md`. History rewrite is the
user's to run. Check its outcome before touching those files.

## #87 decisions (grilled 2026-09-27, closed; full text in ADR-0015 + map #70)
1. Week = Fantrax **Scoring Period**; facts keyed `(season, period)`.
2. **Update-Set** open → closing (day after end, America/New_York) → closed
   (next period ends); closed re-hashed → **Drift** alert; `--reclose Pnn`.
3. One daily trigger; step cadence `daily`|`on_close` (03a–03d, 04b on_close).
4. Host **GitHub Actions** (daily `17 11 * * *` UTC), gated on spike **#92**;
   home PC = test/fallback; Linux entrypoint shared; dead-man's switch;
   least-privilege writer role; Actions hardening; CI Owner PII check.
5. Change Poll on Actions: 10 min IN/PRESEASON, hourly OFFSEASON, one-poll
   debounce, 429 backoff, `concurrency: etl`; trigger → 04t→02d→02e→export.
6. Poll state → Supabase `change_poll_state`.
7. Discord event-only (fail, close, drift, poll-trigger); silence = success.
8. Review queues → Supabase `review_*` with `resolved_at`.
9. Raw payloads → private Storage `raw/`, gzip; 14 d dailies, closing pulls +
   failed runs kept; Owner PII stripped at capture.
10. **Owner PII** = human names, emails, Fantrax usernames → only
    `shared.owner`. Team names/abbrs/ids are public. Docs name people by role.
11. PC Thursday task unchanged until cutover (1-week parallel run).
12. Daily run re-enables its workflows via API (GitHub 60-day timer).

## Maps (native sub-issues + blocked-by wired)
- **#69 Supabase storage**: #72 ✅ · #73 ✅ · #74 ✅ · #75 schema+RLS (grill;
  ADR-0015 scope comment added) · #76 provision (HITL) · #77 build seam (task).
- **#70 In-season Fantrax**: #78 ✅ · #79 schema extraction (research) · #80 ✅
  · #81 fact model (grill, ←79) · #82 txn cadence (grill) · #83 sources truth-up
  · #87 ✅ · #88 test strategy (grill, now unblocked) · **#92** Actions login
  spike (research, new) · **#93** cadence build (task, ←92,77,75,76,88).
- **#71 nflverse**: #84 ✅ · #85 grain (grill) · #86 build (←85,77).

## Next actions (no build work until the user says so)
1. Confirm PR #94 merged; check task_5f6a95b6 (email leak) outcome/PR.
2. HITL grill queue: #82 → #85 → #88 → #81; #75 schema+RLS.
3. AFK frontier: #92 spike, #79 (fantrax-payload-analyst; never read
   `data/raw/` in main context; also check payloads for Owner PII fields),
   #77 seam, #83, #68. Close map #65 if its destination is reached.

Tests: `.venv/Scripts/python.exe -m pytest tests/`. Map-edit pattern: python
insert under `## Decisions so far\n\n`, `gh issue edit N --body-file`.

# RESUME — Supabase + in-season ETL: 3 wayfinder maps (updated 2026-09-26)

**Git state**: on branch `docs/wayfinder-supabase-inseason-maps` (pushed, **no PR —
hold until #72's ADR lands, then add ADR to this branch and PR**). Carries
`PLAN.md` ACTIVE section, this file, `.gitignore` += `docs/reference/`.
`main` = 6be523e (PRs #89 + #90 merged, remote + local branches deleted).
Uncommitted, not mine: `.claude/memory/MEMORY.md`, `mouserat-trade-bud.md`,
untracked `.agents/`, `GEMINI.md`, `.claude/worktrees/`.

## Decisions (user, 2026-09-26)
- 3 parallel maps joined by a **storage seam** (`etl.read_table`/
  `write_table`, parquet backend first, Supabase later).
- Maps carry to **change landed** (decision tickets → task tickets).
- `docs/reference/` = pattern reference only (reject name-keys, anon-write RLS);
  now gitignored. User will tell James about his anon-write RLS himself.
- **Daily run, weekly update-set, tested**; minimal player-week snapshot
  (roster status, contract, FPts YTD, age) — football = raw points.
- New ADR must supersede ADR-0012 "no database" + CLAUDE.md storage rule.

## Maps (GitHub, native sub-issues + blocked-by wired)
- **#69 Supabase storage foundation**: #72 role/ADR (grill) · #73 ✅ · #74 ✅ ·
  #75 schema+RLS (grill, ←72) · #76 provision (HITL, ←72) · #77 build seam
  (task, **unblocked**; prereq grain fixes listed in #69 fog).
- **#70 In-season Fantrax**: #78 ✅ · #79 schema extraction (research,
  **unblocked**) · #80 ✅ · #81 fact model (grill, ←79,87) · #82 txn cadence
  (grill) · #83 sources.yml truth-up (task; add 04s entry too) · #87 daily
  run/weekly update-set (grill) · #88 test strategy (grill, ←87).
- **#71 nflverse**: #84 ✅ · #85 grain (grill; minimal stats) · #86
  build+schedule (task, ←85,77).
All closed research gists are already folded into map **Decisions so far**.

## Landed this session
- PR #89: `notebooks/04s_fantrax_inseason_capture.py` (schedule once; per
  period standings COMBINED, `getLiveScoringStats {period}` (period
  REQUIRED), `getTeamRosterInfo {teamId, period}` ×28 incl. Age/Sal/Con/FPts +
  `draftPicksData`). Raw in `data/raw/fantrax_inseason_2026_{schedule,p01..p03}.json`.
  Also `04a CFG.api_version` 182.4.8 → 186.3.22 (old = STALE_CLIENT pageError;
  current version lives in Fantrax JS chunk `name:"fantrax",version:"…"`).
- PR #90: #67 04z disambiguate tiebreak. #67 closed. **Map #65 still open —
  check if destination reached and close.**
- Tests: run with `.venv/Scripts/python.exe -m pytest tests/` (33 pass);
  system python has no pytest.

## Next actions
1. **User runs `/grill-with-docs` on #72** (Supabase role: SoR vs mirror, parquet
   fate, free-tier pause/no-backup mitigation, ADR-0012 supersession). Output:
   new ADR → commit on docs branch → PR. Then user clears context.
2. HITL queue after: #87 (cadence) → #82 → #85 → #81.
3. AFK frontier: #79 (fantrax-payload-analyst on 04s raw files; never read
   `data/raw/` in main context), #77 seam build, #83 sources truth-up, #68.
4. Close map #65 if done.

Chart scripts (scratchpad, may be gone): `chart_maps.py`, `amend_b.py`.
Map-edit pattern: `gh issue view N --json body -q .body > f.md`, python
replace under `## Decisions so far\n\n`, `gh issue edit N --body-file f.md`.

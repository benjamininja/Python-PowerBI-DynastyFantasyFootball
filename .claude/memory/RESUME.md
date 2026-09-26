# RESUME — Supabase + in-season ETL: 3 wayfinder maps charted (2026-09-26)

**Files touched (uncommitted, docs-only)**: `PLAN.md` (new ACTIVE section at
top indexing the maps + lanes). Earlier uncommitted work still in tree:
Task #67 (`04z` + 3 parquet, verified, needs commit/PR), memory docs.
`docs/reference/` untracked — James's HoD *baseball* Supabase stack; embeds
admin passkey + anon key → **keep out of git** (recommend `.gitignore`; tell
James his anon key has write RLS). Not done yet — awaiting user OK.

## Decisions (user, 2026-09-26)
- 3 parallel maps joined by a **storage seam** (`etl.read_table`/
  `write_table`, parquet backend first, Supabase later).
- Maps carry to **change landed** (decision tickets → task tickets).
- `docs/reference/` = pattern reference only (reject name-keys, anon-write RLS).
- **Daily run, weekly update-set, tested**; minimal player-week snapshot
  (roster status, contract, FPts YTD, age) — football = raw points.
- New ADR must supersede ADR-0012 "no database" + CLAUDE.md storage rule.

## Maps (GitHub, native sub-issues + blocked-by wired)
- **#69 Supabase storage foundation**: #72 role/ADR (grill) · #73 platform
  facts (research) · #74 seam inventory (research) · #75 schema+RLS (grill,
  ←72,73) · #76 provision (HITL task, ←72) · #77 build seam (task, ←74).
- **#70 In-season Fantrax**: #78 capture payloads (task) · #79 schema
  extraction (research, ←78) · #80 public fxea API (research) · #81 fact
  model (grill, ←79,80,87) · #82 txn cadence (grill) · #83 sources.yml
  truth-up (task) · #87 daily run/weekly update-set (grill) · #88 test
  strategy (grill, ←87).
- **#71 nflverse stats+injuries**: #84 nflreadpy (research) · #85 grain
  (grill, ←84; minimal stats) · #86 build+schedule (task, ←85,77).

## Research done (all 4 closed, gists folded into map Decisions)
- #73 → #69: free tier no backups + 7-day pause; psycopg COPY via session pooler :5432; PBI service needs gateway.
- #74 → #69: seam = `read_table`/`table_exists`/`write_table(mode=replace|replace_partition|upsert)`; grain+dtype enforced from `data_model.yml`. Prereq grain fixes added as #69 fog. **#77 now unblocked.**
- #80 → #70: public fxea gives schedule/divisions/current standings/rosters+contract; NOT scores/FPts/txns → #78 authed capture essential. 04u error-in-200 fog.
- #84 → #71: nflreadpy 2026 live; gsis key; injuries + participation minimal; 05a GP bug fog.
Branches `research/*` pushed, no PRs.

## Next actions
1. (done) research folded in.
2. User's HITL queue: #72 (Supabase role) → #87 (cadence) → #82 → #85.
   Use `grilling`/`grill-with-docs`, one question at a time.
3. AFK frontier still unstarted: #78 capture, #83 sources truth-up, #77
   after #74, #68 waiver activity, #67 commit/PR (ask first).
4. Ask user re `.gitignore` for `docs/reference/`.

Chart scripts (reusable, scratchpad, may be gone): `chart_maps.py`,
`amend_b.py`. Wayfinder skill source:
`skills-plugins-hooks-agents/skills/wayfinder/SKILL.md`.

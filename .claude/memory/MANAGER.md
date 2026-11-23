# MANAGER — the builder manager's state

The dynasty builder manager's working copy of its state. It links to
the record on GitHub and does not replace it. **Only the newest state is
kept here.** Every earlier block is in this file's git history:
`git log -p -- .claude/memory/MANAGER.md` (trimmed 2026-11-22 on the
owner's button; the last long version is at commit `995f0cf`).

Read order at a start: the role file's list, then this file, then the
main checkout's `NEEDS-OWNER.md` (the one copy the owner's pane reads).

## Standing facts

- **Paths.** Repo root `C:\source\Github\Python-PowerBI-DynastyFantasyFootball`
  (since the tools #235 move; any OneDrive path is stale). Tools repo
  `C:\source\Github\skills-plugins-hooks-agents`. The dispatch script is
  in the session-dispatch plugin's `scripts/` folder.
- **session-dispatch** must be typed by Ben in each session before any
  dispatch, merge, resume or closeout.
- **Re-proof:** `.venv/Scripts/python.exe scripts/reproof.py <pr> <head>`
  after `git fetch origin`, run in the background. Post a summary on the
  PR with counts only: its review-finding lines hold row keys. Merge
  squash, pinned with `--match-head-commit`, then `git pull --ff-only`
  in the main checkout at once.
- **Dispatch from PowerShell without `2>&1`:** Windows PowerShell 5.1
  turns git's stderr into a stopping error, and the script fails after
  making the worktree. A re-run reuses the worktree.
- **Closeout:** `claude rm <id>` removes the worktree and the local
  branch. A squash-merged branch with more than one commit shows `+` in
  `git cherry`: check that the branch's files have no diff against main
  instead, and say so to Ben.
- **The Daily Run** is the `etl-daily` GitHub Actions workflow. Its log
  (`gh run view <id> --log`) holds each step's error tail, the same
  text the Discord summary posts.
- **The bot** runs on Ben's PC from `discord_bot`
  (`.\.botvenv\Scripts\python.exe bot.py`) in a terminal tab of the
  manager's session. A clear can close it: check and restart.
- **Ben's standing merge word, each when GREEN:** #616, #623, #597, #626.
  It never covers a parked Decision (an ADR amend, a DROP COLUMN).

## CURRENT STATE (2026-11-23 ~07:30Z, session `1a0538b1-047b-4ba3-8967-ff325369e7ab`, before a clear at Ben's word)

- **Heads.** origin/main and main checkout `61aa044`.
- **Merged since the last save:** #649 (#648) `b089d59`; #646 (#548
  brief 3, owner crosswalk and policies) `61aa044` at Ben's word, GREEN at
  re-proof (3426 passed), migrate on main SUCCESS. Builders b648 and b548
  closed out.
- **#646 live check:** every rule of the planner's ADR-0025 list holds
  (counts on #548). Use `has_table_privilege` / `has_column_privilege` /
  `has_function_privilege` per role: `information_schema` grant views
  show only what the querying role can see and came back empty.
- **Owner crosswalk load:** at Ben's word the loader ran and stopped (the
  tab's headers are Team Name, Team ID, Fantrax-TeamId, Roster, Discord;
  the data checks clean by counts: 30 rows, 28 teams). Ben chose the
  loader fix: #650 (low), dispatched as b650-ownerheaders (session
  `554a5d1b`). After it merges: re-run the loader to a scratchpad path at
  Ben's word and show him the full SQL.
- **In flight:**
  - PR #652 (b650, head `b76df2f`): builder reports 53 targeted tests
    passed; full suite held for the test line. b650 no longer shows in
    `claude agents`. Next: re-proof (reproof.py, full sha), read the
    diff, the code reviewer, then merge (dispatched ticket: no further
    word needed). Close out b650.
  - PR #651 (the manager's own, ADR-0025 text in GOAL-RUN.md and
    supabase-auditor.md, Ben-approved one-time): Ben said merge when
    green. Was waiting on one storage-pg run. Worktree
    `.claude/worktrees/adr25-text` (its `.venv` is a junction to the main
    checkout's); remove it after the merge.
- **Test line:** Tools-builder-manager plans PR 246's re-proof (up to 90
  min). Agreed: tools sends a start notice and waits for an OK if b650
  has reported green; otherwise dynasty holds b650's re-proof until the
  tools end notice.
- **Queue:** the Supabase sign-in check (Ben is configuring the Discord
  provider: Client ID and Secret from the Discord developer portal, the
  Supabase callback URL as a Discord redirect); the ADR-0025 text entry
  (closes when #651 merges).
- **Dispatch order after, each at Ben's go:** #633, #637, #639, #616 (ADR
  amend as a Decision first), #626, #597. #563 held; #595 last; #620
  waits on tools #231. #644 ticketed.
- **Peers:** planner session id `e0f49660-15b2-44b9-8430-e04f2e6b243b`
  (next: #548 after-deadline brief Q6, then brief 4). Tools queue id
  `55edaa09-855e-454f-991a-371eb4875402`.

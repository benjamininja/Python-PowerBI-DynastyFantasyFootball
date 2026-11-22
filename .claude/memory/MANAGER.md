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

## CURRENT STATE (2026-11-22 ~17:55Z, session `1a0538b1-047b-4ba3-8967-ff325369e7ab`, before a compact at Ben's word)

- **Heads.** origin/main and main checkout `c598e3e`.
- **Merged this session:** #625 (#615) `558a7ae`; #575 state `0916977`;
  #631 (2027 price list) `91f6640`, GREEN on `0916977`
  (pull/631#issuecomment-7082731183); #632 (planner CLAUDE.md) `c598e3e`
  on Ben's button. Closed out b615, b619 on Ben's button.
- **BLOCKER: the Claude CLI on this PC is signed out** (`claude auth
  status`: loggedIn false). b629-gsisremap (#629, session `31981061`)
  and b630-sheetssecret (#630, session `6058fd00`) stopped at turn one
  with Login expired, no work done. NEXT: Ben runs `claude auth login`;
  Claude checks status, then resumes each with `resume_plain.ps1` on its
  ticket (message: start the brief). No dispatch works until then.
- **#548 keep load:** prices done (162 of 162 FA copies priced, #554
  closed out of the queue). The loader ran on Ben's button and STOPPED:
  Wilson rows 2-9, 82-87 carry 2 old team names
  (issues/548#issuecomment-7083149108). Queued: Ben updates the 2 names;
  the planner may propose an alias path instead. Then re-run with
  `ETL_STORAGE=parquet` (the .env sets postgres) to the SQL path the
  queue entry names (the file must not exist),
  then the paste step for Ben.
- **When #629 and #630 have merged:** queue Ben's Action to start
  etl-daily by hand (Ben, planner's chat 16:28Z); close stale data PRs
  #603, #618, #627, #628 and later, each recorded on #629.
- **Dispatch order after:** #548 brief 3 (gid in, issuecomment-7082200751),
  #633 (memory trim, low), #623, #616 (ADR amend as a Decision first),
  #626, #597 (after #623). Each at Ben's go here. #563 held; #595 last;
  #620 waits on tools #231.
- **Test line:** with Tools-builder-manager for the #244 builder's full
  run (up to an hour); ask before the next dynasty full run.
- **Bot:** running in this session's terminal tab c3 (started 10:28 local).
- **Queue:** done entries #630 secret and the gid leave at this save.
- **Peers:** dff-central-planner `65cb1676-fc95-4abf-8174-422c03a5f64e`;
  Tools-builder-manager `55edaa09-855e-454f-991a-371eb4875402`;
  Tools-central-planner `019c4c0b-d63a-4262-9ee1-558f1408fd4f`;
  personal-assistant.

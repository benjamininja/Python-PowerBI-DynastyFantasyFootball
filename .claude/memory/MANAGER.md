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

## CURRENT STATE (2026-11-22 ~16:40Z, session `1a0538b1-047b-4ba3-8967-ff325369e7ab`)

- **Heads.** origin/main and main checkout `558a7ae` (#625 merged).
- **Merged:** PR #625 (#615) as `558a7ae`, pinned `dbc2505`, GREEN on
  base `5bd92f4` (pull/625#issuecomment-7081850303), CI green.
- **Closed out** on Ben's button "Close both": b615-handrunstore and
  b619-pathmove (issues/615#issuecomment-7081945663,
  issues/619#issuecomment-7081945980).
- **Running builders** (dispatched here on Ben's "Both now"):
  b629-gsisremap (#629, medium, session `31981061`), b630-sheetssecret
  (#630, low, session `6058fd00`). Both hold full suites until the
  manager's go.
- **PR #631** (2027 price list, #554): Claude ran the loader on Ben's
  buttons, with the FreeAgentResign 11-12 export and pulled-on
  2026-11-12 (Ben confirmed the date): 5070 rows written and exported.
  NEXT: re-prove when Tools-builder-manager gives a gap in the test
  line, merge, then the every-FA-copy-priced count, then
  `load_contract_choices.py` (#548) by Ben's button, then Ben's SQL paste.
- **#548:** Fill the Resign column done on Ben's button
  (issues/548#issuecomment-7082029081). Both #548 entries keyed to this
  session.
- **When #629 and #630 have both merged:** queue an Action for Ben to
  start etl-daily by hand (Ben's answer in the planner's chat,
  16:28Z), and close the stale data PRs #603, #618, #627, #628 and
  today's, each recorded on #629.
- **Dispatch order after:** #623 (low), #616 (high, ADR amend drafted
  as a Decision first), #626 (low), #597 (medium, after #623; DROP
  COLUMN parks). #563 held. #595 merges last, after a data PR stages
  the DLF delete (#589). #620 waits on tools #231.
- **Test line:** with Tools-builder-manager (#236, #238, #239, #242).
  Dynasty #631 is next, in a gap Tools offers.
- **Peers:** dff-central-planner `65cb1676-fc95-4abf-8174-422c03a5f64e`;
  Tools-builder-manager `55edaa09-855e-454f-991a-371eb4875402`;
  Tools-central-planner `019c4c0b-d63a-4262-9ee1-558f1408fd4f`;
  personal-assistant.

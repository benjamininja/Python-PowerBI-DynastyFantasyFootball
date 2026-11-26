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
- **Merge (since PRs #694 and #703):** one read of
  `gh pr view <n> --json mergeStateStatus,statusCheckRollup`. Every check
  SUCCESS with no conflict is Green. Post a short Green note on the PR,
  merge squash pinned with `--match-head-commit`, then `git pull
  --ff-only` and read CI on main's new commit. `scripts/reproof.py` is
  only for chasing a failure CI shows; its review-finding lines hold row
  keys, so post counts only.
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
- **The reset prompt** is a local file in the owner's profile, outside
  every repository, one per repo and role (tools #217). A new session
  told to read it, with none in its chat, looks there before it rebuilds
  from this file.
- **The queue is edited with the owner-queue command line** (add, remove,
  prune), never by hand for a whole entry. A pane Note is recorded on the
  entry's ticket word for word before the entry is removed.
- **A pane Note is not approval,** even when its words approve. Bring it
  to Ben by button in chat, then act. A tick is not approval of a merge
  either: an entry that asks for a merge is a Decision, so the pane
  writes an Answer, and it never offers the tick as a way to approve.
- **An owner's settings edit** is made by Ben in the main checkout. On
  his word the manager copies the file unchanged to a branch and a PR.
  After that PR merges, restore the main checkout's copy and pull at
  once: git refuses a pull over the same edit left uncommitted.


## CURRENT STATE (2026-11-26, seventeenth save, before a compact at Ben's word; session `9d28e196-d848-4cf7-a3d6-f97cbe859143`)

Done items left this block: their records are on GitHub (tools #272 read budget).

- **Heads.** origin/main and the main checkout at `405a6af` (PR #723). CI on main green at `405a6af` (tests, pii-scan).
- **Rules in force.** Session-rules 0.5.2 (tools PR #290, e3a342f; this session still runs the older load): until dynasty's table of checks is written and Ben sets the ruleset, **every PR, a builder's too, needs Ben's merge word** by button. GOAL-RUN.md's Who merges what disagrees; the planner proposes the new text on a ticket (record of the exchange: planner chat, 2026-11-26). Before a merge, read the last finished push run on main. Green is every CI check SUCCESS at the head, no conflict, one read; one reviewer per code PR (pr-code-reviewer, or supabase-auditor on its paths).
- **BLOCKER: background sign-in expired.** Since about 07:07 every background builder stops with Login expired, please run /login (authentication_failed). Queue Action: Sign Claude Code in again (Ben runs `claude auth login`). After Ben ticks it, SendMessage each builder below to resume (they are listed, so never resume_plain: that starts a copy, as happened once on #670, recorded on issues/670#issuecomment-7192517019).
- **Builders (all stopped on the sign-in, nothing committed):**
  - **b670-appviews** (#670, app read-path views; session `b03d5fd3-f725-45cf-ab22-e07ab78f85f3`), tier medium, from `17f695e`. Ben's go by button; planner's ready issues/670#issuecomment-7192060151.
  - **b644-reproofleak** (#644, reproof.py Temp leak; session `4b5df36a-b92f-4b2a-9fe6-85101a5cc2e8`), tier low, from `405a6af`. Ben's pane Answer (a), issues/644#issuecomment-7192528450. Re-proof extra: count reproof-* folders in Temp before and after the next re-proof and post both counts.
  - **b724-footballrows** (#724, 01c keeps the football league's rows, piece 1 of 3; session `5b69b66c-8a10-46c4-be32-d66653fc2829`), tier medium, from `405a6af`. Ben's go by button. After merge: read the next scheduled run (01c passes, team_manifest not held).
- **Waiting on Ben's word or a record:**
  - App chain HELD by the planner: #675, #663, #664, #665, #676, #682 until the planner restates them for Ben's rounds 1 and 2 (issues/721#issuecomment-7192805266 and -7192965729). Order: #724, then a planner PR amending ADR-0026 (app_admin, owner role, a league on every role row), then restated #675 after #670 and before #663.
  - #721 stop 1 (Fantrax login): PR #723 merged; Ben's hand login works (issues/721#issuecomment-7192653301). Next: read the next scheduled run's #723 flags and send them to the planner, who shapes the fix. b721 open questions (04t, 04v, 04w retry copies; stop after a first failed login) stay on #721.
  - #722 (tier low, after #717): dispatch on Ben's word. #719, #720: after the app chain.
  - #662, #700 close once a scheduled run shows the two load counts.
  - #713: note on the ticket the first later PR under pbi/, mouserat_trade-bud/, discord_bot/ or docs/site/.
- **Closed out this session:** b697 (PR #716), b715 (PR #717), b721 (PR #723). #697 and #715 closed. Stale worktree locks (process gone) were removed with git worktree unlock before the closeout script.
- **Peers:** dff-central-planner `536a467f-4989-475e-bcc0-c7a14917d52a`; Tools-builder-manager `3bac2fdb-b847-4732-b572-e582ae2af312`; Tools-central-planner `a09ca279-6faa-4a61-a313-10328ff9c39d`; personal-assistant `6f53e894`.
- **Bot:** bot.py runs in this session's terminal tab (discord bot). Check it after a clear.

## Queue entries raised

- Action: Sign Claude Code in again so the background builders can run (Session 9d28e196). Raised 2026-11-26.

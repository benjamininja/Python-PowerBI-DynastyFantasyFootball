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


## CURRENT STATE (2026-11-26, sixteenth save; session `9d28e196-d848-4cf7-a3d6-f97cbe859143`)

Done items left this block: their records are on GitHub (tools #272 read budget).

- **Heads.** origin/main and the main checkout at `17f695e` (PR #717). CI on main green at `642176d` (PR #716); `17f695e` was running at this save: **read it first.**
- **Rules.** Green is every CI check SUCCESS at the head with no conflict, on one read; read CI on main after each merge; one reviewer. The token merged #717 (a workflow PR) without fault this time.
- **Builders running:**
  - **b721-fantraxlogin** (#721 stop 1 only, the Fantrax login; session `64c6ee51-7d68-40f8-a8dd-a4d700fbaf22`), tier medium, profile none, from `17f695e`. Ben's go by button (issues/721#issuecomment-7191883106). Logs and code only. Next: its comment on #721, then a PR or a park.
- **Waiting on Ben's word or a record:**
  - The chain (#670, then #675 before #663, never side by side; #682; then #663, #664, #665; #676 after #675). #697 has merged. Before any dispatch: confirm Ben's go by pop-up in this chat, and ask the planner to recheck each ticket's body; the league-scope question (map #658) now bears on #675.
  - #721 stops 2 and 3 (the workbook holds other leagues on purpose, Ben's answer, issues/721#issuecomment-7191750945): the planner's league-scope button to Ben comes first.
  - #722 (tier low, follow-up to #717: tests.yml heavy jobs when scope fails, --no-renames): lands after #717, before the ruleset question; dispatch on Ben's word.
  - #719 and #720 (tier medium, #716 advisories): later, after the app chain, at Ben's go.
  - #662 and #700 close once the scheduled run's notice shows the two load counts; the 11-25 run loaded nothing (#721).
  - #713: note on the ticket the first later PR under pbi/, mouserat_trade-bud/, discord_bot/ or docs/site/.
  - #699 stays open for the planner.
- **Closed out this session:** b697 (PR #716, #697 closed), b715 (PR #717, #715 closed).
- **Peers:** dff-central-planner `536a467f-4989-475e-bcc0-c7a14917d52a`; Tools-builder-manager `3bac2fdb-b847-4732-b572-e582ae2af312`; Tools-central-planner `a09ca279-6faa-4a61-a313-10328ff9c39d`.
- **Bot:** bot.py runs in the terminal tab of this session (discord bot). Check it after a clear.

## Queue entries raised

- None open. The #662 App roles tab Action is done, and Action 2 was withdrawn by Ben's Decision to automate.

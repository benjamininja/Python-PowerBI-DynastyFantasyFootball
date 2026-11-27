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


## CURRENT STATE (2026-11-27, twenty-first save, before a clear at Ben's word; session `e5579518-3626-469b-b1d5-3095f10a1c6a`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-27 ~13:50 UTC, session `e5579518-3626-469b-b1d5-3095f10a1c6a`. After the clear Ben must type session-dispatch again before any dispatch, merge or closeout.
- **Heads.** origin/main at `2bfd70a` (PR #754). CI on main green through `24cfb9a`.
- **Rules in force.** Six required checks (#731). GOAL-RUN.md's closed list merges on Green alone; every other PR needs Ben's word by pop-up. Every dispatch needs Ben's go (the #746 no-go trial is parked with tools #300, which Ben kept whole; ask Ben again only after that text merges). Since PR #754 the planner writes and removes its own queue entries and tells the manager; builders' parks still go through the manager. Since PR #753 the managers' and builders' settings deny gh run rerun and the gh api pending_deployments and rerun patterns.
- **Ben's cut (2026-11-27, #746 issuecomment-7219555230):** finish what has an open PR, park everything not started. Parked with the backlog label, no dispatch until Ben lifts it: #620, #711, #749, #746. Power BI stays backlog (#624, #556, #567, #211, #399, #511, #512, PR #563). Active: #721 and #740 (Fantrax login in the scheduled run), #675 until a run prints the four access counts, the state PR #634 on Ben's merge word.

### Next
1. **Tonight's etl-daily run** (~20:00 UTC 2026-11-27; the 11-26 run failed). Read the access load counts for all four tables (#675, #662, #700 close on them), the SessionStillDead flag line (send to the planner; #740 closes on it), the logins count. Post counts only.
2. **First held migration after PR #745** (merged `585ada7`): its push job ends green, apply-held waits in environment migrate-held for Ben's Approve, re-runs the gate and applies. Read that run, then advisors (security and performance) by level. No held file is pending now.
3. **State PR #634**: on Ben's merge word when he asks for a check-in.
4. App chain after #675 (#663, #664, #665, #676, #682, #719, #720): only on the planner's ready and Ben's go; check against Ben's cut first.

### Waiting
- On Ben: nothing in the queue (empty at this save).
- On the planner: nothing open for the manager.

### In flight
- No builders running.
- Open PRs: #634 (state, CLEAN), #691 (old data PR, DIRTY), #595 (b589, parked), #563 (b556, Power BI backlog).

### Peers
dff-central-planner `823b0d8b-9a43-423c-82fe-429cfcd98aae`; Tools-builder-manager `fbd93714-8c8b-49c7-b434-7dee4a8488fd`; Tools-central-planner `4e27fb7c-445f-47d9-ad2b-919bca911066`; personal-assistant `5d72e933-3c89-4f59-8d43-6e6ac9884826`. After the clear, send the planner the new session id.

### Reads and checks due
- Tonight's etl-daily run (above).
- The first held migration's run (above).
- Bot: running in the terminal tab discord bot; check after the clear and restart if missing.

### Decided since the last merged state PR
- #724 closed on the 11-26 run (issuecomment-7217160100).
- #734, #737, #739, #738 (`d21758e`), #741 (`bcb365e`), #743 (`f834dbb`), #742 (`0d6284c`), #747 (`175dd7c`), #748 (`c0d1757`) merged on Ben's word; b736, b740, b675 closed out.
- #731 closed: ruleset at six, rules file on main.
- #744: PR #745 merged (`585ada7`) after the migrate-held environment was read right (reviewer benjamininja, admin bypass off, branch main); b744 closed out. PR #750 merged (`e7da865`).
- #751: dispatched on Ben's go, finished on his pop-up after the cut; PR #752 merged (`24cfb9a`); b751 closed out.
- #736 closed (done by PR #738).
- PR #753 (`c8a41a2`, deny rules) and PR #754 (`2bfd70a`, planner writes its own queue entries) merged on Ben's word.
- Ben's cut of the process work (#746 issuecomment-7219555230).

## Queue entries raised

- None open.

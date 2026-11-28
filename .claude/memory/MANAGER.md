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


## CURRENT STATE (2026-11-28, twenty-second save, before a compact at Ben's word; session `637314ca-f6ae-4049-a3ff-576bd1479cfe`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-28 ~14:40 UTC, session `637314ca-f6ae-4049-a3ff-576bd1479cfe`. Ben typed session-dispatch in this session (2026-11-28); a compact keeps it, a clear needs it again.
- **Heads.** origin/main at `f93449f` (the manual run's own data PR, after #762 `30ac3a9`). CI on main green through `a0fd038`.
- **Rules in force.** Six required checks (#731); GOAL-RUN.md's closed list merges on Green alone. **No-go trial live** (PR #762, GOAL-RUN.md section "Dispatch without the owner's go"): low and haiku tickets dispatch without Ben's go until 2026-12-12, unless `held` or `backlog`; every such dispatch is named in the next report and here. Medium and high keep Ben's go. Ben's cut (#746 issuecomment-7219555230) still parks the backlog-labelled tickets.
- **Ben's rulings of 2026-11-28** (planner's chat, recorded #429 issuecomment-7240199640): scheduled Fantrax sign-ins stop (#760), weekly hand load (#761); #520, #522, #523, #524 lifted to run in shadow, in that order, each with Ben's go.

### Next
1. **PR #764 (#520, b520-matchups)**: when the builder reports Green, one pr-code-reviewer (scripts/run_pipeline.py is touched, so the merge needs Ben's word), then merge in shadow. Not held (planner, #520 issuecomment-7240503830). The second of #764 and #765 to merge takes main in first (both touch the Chain lines near 04s_scoring).
2. **PR #765 (#760, b760-nologin)**: when Green, one pr-code-reviewer; it changes the workflow, so the planner's read and Ben's word before the merge. After it merges: close #758 as not planned; ask Ben's go for #761 (medium, hold lifted).
3. **--live for 04m**: its own one-line PR, opened after one scheduled run's shadow line shows every closed period matching; post the counts on #520 and ask Ben's merge word. Target merged before 2026-12-03 (period 12 ends on the first playoff day); if it cannot make it, tell the planner.
4. **After #520 merges**: ask Ben's go for #522, then #523 (read #554 first), then #524, one at a time.
5. **Scheduled runs**: read each for the access counts and the Fantrax lines; post counts only.
6. **State PR #634**: on Ben's merge word at a check-in.
7. **First held migration after PR #745**: read the run, then advisors security and performance. None pending.

### Waiting
- On Ben: nothing in the queue (empty at this save).
- On the planner: nothing open for the manager.

### In flight
- b760-nologin, session `36574c3d-63f7-423e-8d82-9ec43f280c5e`, #760, medium; PR #765 open, CI pending.
- b520-matchups, session `637f9486-e7d3-4de3-a879-dad1e6b7db7a`, #520, medium; PR #764 open, CI pending.
- Other open PRs: #634 (state, CLEAN), #595 (b589, parked), #563 (b556, Power BI backlog).

### Peers
dff-central-planner `0ef68551-3dad-4f09-b5af-b164a0307ae9`; Tools-builder-manager `ea58e038-9092-4552-9e4c-32bb3cdf8281`; Tools-central-planner `0a6ad927-943a-481d-99fc-f2cbfcda8498`; personal-assistant `5d72e933-3c89-4f59-8d43-6e6ac9884826`. SendMessage by name: pipe addresses go stale.

### Reads and checks due
- Tonight's scheduled etl-daily run (~20:00 UTC 2026-11-28): 04m's shadow line (#520) if #764 merged; Fantrax lines; access counts.
- Bot: running in the terminal tab discord bot.

### Decided since the last merged state PR
- #724 closed on the 11-26 run (issuecomment-7217160100).
- #734, #737, #739, #738 (`d21758e`), #741 (`bcb365e`), #743 (`f834dbb`), #742 (`0d6284c`), #747 (`175dd7c`), #748 (`c0d1757`) merged on Ben's word; b736, b740, b675 closed out.
- #731 closed: ruleset at six, rules file on main.
- #744: PR #745 merged (`585ada7`); b744 closed out. PR #750 merged (`e7da865`).
- #751: PR #752 merged (`24cfb9a`); b751 closed out. #736 closed (done by PR #738).
- PR #753 (`c8a41a2`) and PR #754 (`2bfd70a`) merged on Ben's word.
- Ben's cut of the process work (#746 issuecomment-7219555230).
- 2026-11-27 run read: #675 (issuecomment-7239458026), #700 (issuecomment-7239458778), #740 (issuecomment-7239459462) closed on its counts and flag line.
- PR #691 closed as superseded by #755, on Ben's word.
- #756: dispatched on Ben's go; PR #757 merged (`a0fd038`) on Green; b756 closed out; advisories to #758 (now overtaken by #760).
- #564: PR #759 merged (`a0aea0e`) on Ben's word (four gh issue denies).
- PR #762 merged (`30ac3a9`) on Ben's word: the no-go trial.
- #760 and #520 dispatched on Ben's go (2026-11-28).
- Ben's manual run 46151521462: 1 Fantrax login, error kind other (#721 issuecomment-7240358827).
- #520 period 9 offline comparison matched, 28 teams, run by the manager on Ben's word (#520 issuecomment-7240491709).

## Queue entries raised

- None open.

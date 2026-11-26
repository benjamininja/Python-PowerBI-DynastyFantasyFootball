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


## CURRENT STATE (2026-11-26, eighteenth save, before a clear at Ben's word; session `9d28e196-d848-4cf7-a3d6-f97cbe859143`)

Done items left this block: their records are on GitHub (tools #272 read budget).

- **Heads.** origin/main at `8faefbb` (PR #732). CI on main green through `6b40b82`; the runs for `6a78fe2` (docs) and `8faefbb` were in progress at the save.
- **Rules in force.** Session-rules as pulled (tools at 3bdba9c). Until dynasty's table of checks (#731) is set by Ben, **every PR, a builder's too, needs Ben's merge word** by pop-up (or his line in chat naming the PR). Before a merge, read the last finished push run on main. Green is every CI check SUCCESS at the head, no conflict, one read. One reviewer per code PR (pr-code-reviewer with mrp-dff-code-review at tier effort, or supabase-auditor on migrations, registry, generator, SUPABASE workflows). Owner-queue Options: write them as (a) text; (b) text, never a semicolon then a parenthesised key inside an option (tools #293: the pane joined both options into one Answer today; the manager re-asked by pop-up).
- **Builder running:**
  - **b675-leagueroles** (#675, tier high; session `3fbeb76a-d8f0-4fc6-9be4-b6e705a6fe85`), from `696d808`. Ben's go by pop-up. Two PRs. Ben answered its two Decisions (both option 1, record issues/675#issuecomment-7194660844); planner PR #733 (6a78fe2) amended ADR-0018 decisions 3, 10, 12 and ADR-0026 decision 2; load functions are shared.load_leagues and shared.load_teams. b675 was told to merge main and build PR 1. Reviewer: supabase-auditor. **At PR 1's merge queue an Action:** Ben dispatches migrate.yml for the held statements the plan comment names (two DROP CONSTRAINT, one UPDATE, one DROP FUNCTION). Tell the planner when each PR merges. #675 stays open until the scheduled run after PR 2 shows the access loads pass with counts for all four tables.
- **In flight at the save: #655 step 5** (background, this session): removing the 23 damaged-record worktrees that passed steps 1 to 3 plus b349-floats (Ben's pop-up answers: Remove all 23; b349-floats Discard and remove), then git worktree prune, then deleting each worktree-<name> branch only when its tip equals the merged PR head or is on main. Log: this session's scratchpad remove24.txt (lost on a clear). After a clear: count folders under .claude/worktrees, check git worktree list for zero-HEAD rows, check which worktree-b3xx/b4xx branches of the list remain (list and tips on issues/655#issuecomment-7194837863), finish what is missing the same way, then post counts on #655.
- **Waiting on a run or a record:**
  - #724: stays open until the next scheduled etl-daily run shows 01c_dim_fantasy_teams passing and team_manifest not held. From the same run read #723's Fantrax login flags and send them to the planner (#721 stop 1).
  - #662, #700 close once a scheduled run's notice shows the two load counts.
  - #713 (closed): when the first PR changing only pbi/, mouserat_trade-bud/, discord_bot/ or docs/site/ comes, note on #713 that storage-pg skipped.
  - #731 (dynasty table of checks): the planner puts the ruleset button to Ben; the rules-file text then comes into GOAL-RUN.md by the manager's PR.
  - App chain after #675: #663, #664, #665, #676, #682 (renamed words only), then #719, #720. Dispatch only on the planner's ready and Ben's go.
- **Merged and closed out today (records on the PRs):** #725, #726 (#644 closed; Temp count 13 to 14, new folder only pytest.log), #727 (#724 open for run proof), #728 (#670 closed; auditor finding 1 ruled (a) by the planner, ADR line PR #730), #729, #730, #733 (planner), #732 (#722 closed). Builders b644, b724, b670, b722 closed out. Closed on the planner's notes: #695, #688, #581, #713, #699.
- **#655 backlog:** 83 worktree folders at the start of the day. Backlog run removed 44 (matches the prediction); the 8 with scratch files discarded and removed on Ben's word; counts on #655 (issuecomment-7193866528, -7194700497). Left by rule: metadata-principles (commits after #246), 3 scratchpad worktrees outside .claude/worktrees, state (#634), b556-caphit (#563). Branch claude/jolly-jepsen-6a8774 remains (no commit of its own, harmless).
- **Peers:** dff-central-planner `536a467f-4989-475e-bcc0-c7a14917d52a`; Tools-builder-manager `3bac2fdb-b847-4732-b572-e582ae2af312`; Tools-central-planner `a09ca279-6faa-4a61-a313-10328ff9c39d`; personal-assistant `6f53e894`. New subagents available: supabase-look (dynasty, #653), supabase-router (tools #249).
- **Bot:** bot.py in the terminal tab discord bot. Check it after a clear.

## Queue entries raised

- None open (the queue was empty at the save).

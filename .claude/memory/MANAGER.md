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


## CURRENT STATE (2026-11-28, twenty-sixth save, before a CLEAR at Ben's word; session `10ea8a98-91e0-445b-bef3-77cb005def21`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-28 ~19:40 UTC by session `10ea8a98-91e0-445b-bef3-77cb005def21`, before a clear. The next session has a new id: Ben must invoke session-dispatch again before any dispatch, merge or closeout.
- **Heads.** origin/main at `8aaaf1b` (#777), after #776 `ce67c6c` and #775 `6a00ab1`. Data PR #778 (etl-daily) merged 4 parquet files.
- **Rules in force.**
  - Six required checks. GOAL-RUN.md's closed list merges on Green alone; a ledger change also needs cap-ledger-auditor clean.
  - No-go trial to 2026-12-12 for low and haiku tickets that are not held or backlog. **Dispatched under it: #773 (b773-keepids). It went right:** merged on Green, closed out, review clean with 4 advisories.
- **Ben's rulings of 2026-11-28 (this session):**
  - Delete the Fantrax secrets, spike copies too (#760).
  - #473's brief 4 bar is Ben's 2026-11-09 bar.
  - Declare the category_id FK (merged as ADR-0018, #776).
  - The 2025 comparison is printed only (#473 issuecomment-7244229278).
  - Chase the TE cause rather than write at 3% (#473 issuecomment-7244312913).

### Next
1. **#473 brief 4 (b473-history, session `24575614-f591-4e0c-a050-0086adf40baa`, medium, this session's dispatch; branch worktree-b473-history, head `ef4b9f1`, part 2 uncommitted in its worktree).** Parked.
   - The manager ran 02i at ef4b9f1 from a temp worktree with junctions to `.venv` and `data/raw`. The junctions were removed first and the worktree is gone.
   - TE cause found (#473 issuecomment-7244388593):
     - 70 of TE's +100.5 points are tackles, FF and FR that ours score and Fantrax scores 0;
     - 16.5 is TE receptions at 1.485 per unit against 1.5 (slot pay);
     - offensive players' tackles score 0 at Fantrax;
     - IDP solo tackle counts are lower in ours;
     - BK is unmapped.
   - Sent to the planner. Await its ruling, then relay the next brief to b473-history: SendMessage while it is listed, else resume_plain.ps1.
   - Any rerun needing data/raw is the manager's, by the same junction method (rmdir the junctions before `git worktree remove`).
   - Brief 4's PR will touch docs/data_model.yml, so supabase-auditor reviews it and it needs Ben's word.
2. **--live for 04m (#520).** Tonight's scheduled etl-daily (run 46178434728) succeeded:
   - 04m `[shadow]` periods 1 to 10 all matched, and `fantrax logins: 0` (#520 issuecomment-7244325722);
   - the condition is met;
   - asked the planner for a tier and a brief for the one-line --live PR;
   - dispatch on receipt (Ben's go, unless the trial applies); the planner reads; it merges on Ben's word, target before 2026-12-03;
   - check the --live advisories (#764 issuecomment-7240955453).
3. **PR #777's four advisories** (F1 to F4, #777 issuecomment-7244237445): the planner disposes of them after the tier review Ben asked for through the personal-assistant (32 tickets).
4. **#522**, then **#523**, then **#524**, each on Ben's go. #522's brief gets the one-figure-per-scorer rule from the planner.
5. **State PR #634** shows CLEAN now; ask Ben's merge word at a check-in.

### Waiting
- On Ben: the queue entry "Delete the Fantrax sign-in secrets" (#760). His hand step. Its Session line names this session: re-key it after the clear.
- On the planner: the #473 ruling on the TE cause; the #520 --live brief; the #777 advisories.

### In flight
- b473-history (above), parked.
- Open PRs: #634 (state, CLEAN), #595 (b589, parked), #563 (b556, Power BI backlog).

### Peers
dff-central-planner `36235893-7875-4548-9384-a950ad72d75d`; Tools-builder-manager `0e714f8a-9e39-453b-aa53-f3f91e9431ec`; Tools-central-planner `ad27c4f7-ccae-4f9d-aab0-2be31444a3f3`; personal-assistant (now `9892259d-36fe-4e53-a301-2cfcac1df068`). SendMessage by name.

### Reads and checks due
- Saturday mornings: after Ben's export, run `.venv/Scripts/python.exe scripts/load_fantrax_history.py` and post counts on #770. #773 is merged, so a loader run between a fill and `--apply` is now safe.
- Advisor baseline: security INFO 5, WARN 1; performance unindexed FK 42, unused index 1, WARN 4 and 2. #776 was a doc only, so no check was due.
- Before a local full test run, ask Tools-builder-manager for the machine line.
- Tools PR #336 merged: session-rules' text on compact and clear changed (the start line is a committed constant, no reset prompt file). This session still keeps the local reset prompt, until the planner says the role file carries the new start line.

### Decided since the last merged state PR
- Earlier items (to the twenty-fifth save) are on their tickets; see this file's git history.
- PR #776 merged (`ce67c6c`) on Ben's word: ADR-0018 decision 6 gains category_id.
- PR #777 merged (`8aaaf1b`) on Green, under the closed list and the trial. Re-proof is #777 issuecomment-7244237445. b773-keepids is closed out.
- Planner rulings on #473:
  - the second rows are correct, one per Conference (issuecomment-7244107877);
  - where rows disagree, the higher counts (issuecomment-7244163995).
- etl-daily 2026-11-28 succeeded; counts are on #520 and #764.

## Queue entries raised

- None open.

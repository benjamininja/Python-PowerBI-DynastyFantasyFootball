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


## CURRENT STATE (2026-11-28, twenty-fourth save, before a clear at Ben's word; session `637314ca-f6ae-4049-a3ff-576bd1479cfe`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-28 ~16:00 UTC, session `637314ca-f6ae-4049-a3ff-576bd1479cfe`. A clear follows: the next session must ask Ben to type session-dispatch before any dispatch, merge or closeout, and send the planner its new session id.
- **Heads.** origin/main at `cdeecef` (#771), after #768 `6a4bf2c`, #767 `aff9797`, #764 `098c61a`, #766 `822b3d8`, #765 `a6e223d`.
- **Rules in force.** Six required checks; GOAL-RUN.md's closed list merges on Green alone (a ledger change also needs cap-ledger-auditor with nothing open). No-go trial live to 2026-12-12 for low and haiku tickets that are not held or backlog (none dispatched under it yet). Ben's cut (#746 issuecomment-7219555230) parks the backlog-labelled tickets. Session-rules 0.6.5: message another session only when it must act or decide; links, not record text; no reply to a report that asks nothing.
- **Ben's rulings of 2026-11-28:** no script signs in to Fantrax, whoever starts it (#760 issuecomment-7240898743). Ben exports on Saturday mornings, the manager runs the shadow load (allow rule merged in #771; the command is `.venv/Scripts/python.exe scripts/load_fantrax_history.py`, no argument). #520, #522, #523, #524 run in shadow, in order, each on Ben's go. #473 brief 3 map: First Downs = passing + rushing + receiving (#473 issuecomment-7241656476), with season validation right after (brief 4).

### Next
1. **PR #769 (#473 brief 3, b473-categories, session `0bf6ab28-b8f0-4f92-ab48-9f24fa3492d2`)**: the builder is changing the First Downs seed row to (b). On its Green report: one pr-code-reviewer at effort high. It adds a migration and a parquet, so the merge needs Ben's word; after the merge, watch migrate push and apply-held, then advisors (baseline below). Then ask Ben's go for **brief 4**, naming the planner's refresh #473 issuecomment-7241693871 in the brief. Then #522 (refreshed, #522 issuecomment-7241074047).
2. **#770 (b770-teamxwalk, session `6ded5526-20d0-427a-92dc-a168674fb494`)**: the plan was read and taken (#770 issuecomment-7241736975); the builder is building one PR. Its Green report gives the two exact commands (seed and --apply). Queue Ben one Action: the whole managers.settings.json allow block to replace, with those two exact commands, no wildcard. Until it is in, re-proof runs neither. Review: the table is private (schema ops); pick pr-code-reviewer unless the PR touches 02d (then cap-ledger-auditor). After the merge and Ben's list, run the shadow load and post counts on #770.
3. **--live for 04m (#520)**: a one-line PR after one scheduled run's `[shadow]` lines show every closed period matching. Post counts on #520; the planner reads it; Ben's word. Target merged before 2026-12-03, else tell the planner. Check the two --live advisories (#764 issuecomment-7240955453).
4. **#523** (read #554 first), then **#524**, each on Ben's go, after #522.
5. **State PR #634**: shows BLOCKED at this save; read why before asking Ben's merge word.

### Waiting
- On Ben: queue entry "Delete the Fantrax sign-in secrets" (#760). He asked whether manual runs need them; answered no (no workflow reads them since #765; PC runs use the local .env). Recommended: delete, the fantrax-spike copies too.
- On the planner: nothing open.

### In flight
- b473-categories, session `0bf6ab28-b8f0-4f92-ab48-9f24fa3492d2`, #473 brief 3, medium; PR #769.
- b770-teamxwalk, session `6ded5526-20d0-427a-92dc-a168674fb494`, #770, medium; building.
- Other open PRs: #634 (state), #595 (b589, parked), #563 (b556, Power BI backlog).

### Peers
dff-central-planner `0ef68551-3dad-4f09-b5af-b164a0307ae9`; Tools-builder-manager `ea58e038-9092-4552-9e4c-32bb3cdf8281`; Tools-central-planner `0a6ad927-943a-481d-99fc-f2cbfcda8498`; personal-assistant `5d72e933-3c89-4f59-8d43-6e6ac9884826`. SendMessage by name.

### Reads and checks due
- Tonight's scheduled etl-daily (~20:00 UTC 2026-11-28): the first run with no Fantrax login (#765) and 04m's `[shadow]` lines (#764); access counts. The last two etl-daily runs (scheduled 11-27, manual 11-28 13:49Z) ended failure, both from the old Fantrax login path (#756, #757); tonight should not. Counts only on GitHub.
- Saturday mornings: after Ben's export, run the shadow load and post counts on #761 (or #770 once it lands).
- Advisor baseline (after #675): security INFO 5, WARN 1; performance unindexed FK 42, unused index 1, WARN 4 and 2.
- Bot: running in the terminal tab discord bot.

### Decided since the last merged state PR
- Earlier items (to the twenty-second save) are on their tickets; see this file's git history.
- PR #765 merged (`a6e223d`) on Ben's word after a clean review and the planner's read; b760 closed out; #758 closed not planned.
- PR #766 merged (`822b3d8`) on Ben's word (DATA-USE promise 3).
- PR #764 merged (`098c61a`) on Ben's word after a review round (F1, F2 fixed and accepted); b520 closed out.
- PR #767 merged (`aff9797`) on Ben's word: the oneshot profile, Ben's edit copied unchanged.
- PR #768 merged (`6a4bf2c`) on Green after a cap-ledger-auditor round (F1, F2 fixed and accepted); b761 closed out; #761 closed.
- PR #771 merged (`cdeecef`) on Ben's word: the shadow-load allow rule.
- Ben's first shadow load (#761 issuecomment-7241521946): unknown_team 124; ledger gone 90, trade log gone 66; --write would refuse. #770 filed and dispatched for it.
- Dispatched on Ben's go: #761, #473 brief 3, #770.
- Dispatch note: never pipe dispatch.ps1 through 2>&1 in PowerShell 5.1; git's progress line on stderr stops the script after the worktree is made. A python heredoc needs a script file or </dev/null.

## Queue entries raised

- None open.

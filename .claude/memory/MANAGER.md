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


## CURRENT STATE (2026-11-27, twentieth save, before a compact at Ben's word; session `e5579518-3626-469b-b1d5-3095f10a1c6a`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-27 ~13:20 UTC, session `e5579518-3626-469b-b1d5-3095f10a1c6a`. session-dispatch is loaded (a compact keeps it).
- **Heads.** origin/main at `c0d1757` (PR #748). CI on main green through `0d6284c`. #675 PR 2's held file applied by Ben's run 46000465740 (SUCCESS); advisors posted (#675 issuecomment-7218567649).
- **Rules in force.** The #731 ruleset requires six checks, and GOAL-RUN.md (PR #743) holds the closed list that merges on Green alone (`notebooks/`, `scripts/` except four, `tests/`, `discord_bot/`, and every required check for its paths ran, not skipped); every other PR keeps Ben's word by pop-up. One reviewer per PR. Before each merge read main's last finished run. A migration PR whose base is older than main's newest migration takes a merge of main first. Every dispatch still needs Ben's go (the #746 low/haiku no-go trial waits for its rule text).

### Next
1. **PR #745** (#744, b744-approvegate, session `43b9c590-831f-45aa-a77c-f2d5ad1ea309`, medium): head `cbf5019`, CLEAN. Audit round 2 posted, no blocking (PR #745 issuecomment-7219076264). Waiting: the planner's read at cbf5019, and Ben's setup (queue entry). Then Ben's merge word by pop-up, merge pinned, closeout b744. The first held migration after the merge is the real proof: read its run.
2. **Tonight's etl-daily run** (~20:00 UTC 2026-11-27): first with six required checks (#738) and the Fantrax flag line (#741). Read the access load counts for all four tables (#675, #662, #700 close on them), the SessionStillDead flag line (send to the planner for #740 and #721 stop 1; #740 closes on it), the logins count.
3. **#746 dispatch trial**: low and haiku dispatch with no go for two weeks, once its rule text merges. The go line is in the session-dispatch skill (Before a dispatch); the planner decides skill or GOAL-RUN override. Keep the count here: no-go dispatches 0; parked or went wrong 0.
3a. **Planner PR #750** (head `10c2218`, branch docs/planner-role-sweep-lines, the planner's role file, two lines from #746): needs Ben's merge word by pop-up, asked together with #745's. After the merge, tell the planner (its worktree to remove).
3b. **#749** (medium, find out first: deadline rows and keep choices into the scheduled run or retire the hand load): after #675 closes, dispatch on Ben's go.
3c. The #746 go-word trial waits for the Tools planner's skill text; then the manager's own GOAL-RUN.md PR adds dynasty's dated line (low and haiku, two weeks from the merge day, count here), on Ben's word.
3d. **Power BI is backlog** (Ben via the personal-assistant, 2026-11-27): #624, #556, #567, #211, #399, #511, #512 and PR #563 are not dispatched or merged until Ben lifts it.
4. App chain after #675: #663, #664, #665, #676, #682, then #719, #720. Dispatch only on the planner's ready and Ben's go. #682 waits for a run with all four access counts.
5. Follow-up named by b744 (for the planner to ticket): comments still say the owner's dispatch in scripts/migration_gate.py, scripts/generate_migrations.py:39, docs/data_model.yml:70.
6. Housekeeping: the local branch of merged PR #747 (docs/744-goalrun-applyheld) is still there; its delete was refused by the guardrail hook (gh timed out). Retry the plain branch delete, branch named literally.

### Waiting
- On Ben: queue entry "One-time setup: the migrate-held approval environment (#744)" (Session e5579518-3626-469b-b1d5-3095f10a1c6a). Coming: merge word for #745.
- On the planner: one more read of #745 at cbf5019; the #746 trial rule text.

### In flight
- b744-approvegate `43b9c590` (#744): PR #745 at `cbf5019`, idle, waiting.
- Open PRs not ours: #691 (old data PR), #634 (state), #595 (b589, parked), #563 (b556, parked; both need main merged in for the checks job).

### Peers
dff-central-planner `823b0d8b-9a43-423c-82fe-429cfcd98aae`; Tools-builder-manager `fbd93714-8c8b-49c7-b434-7dee4a8488fd` (running tools reproof.py 197, about 70 min from ~13:10Z; both tools checkouts at 1259c38 with the machine-wide lock); Tools-central-planner `4e27fb7c-445f-47d9-ad2b-919bca911066`; personal-assistant `5d72e933-3c89-4f59-8d43-6e6ac9884826`.

### Reads and checks due
- Tonight's etl-daily run (above).
- After #745 merges: the first held migration's run (apply-held waits, Ben approves, it applies).
- Closeout list at this save: merged and still there 1; no commit of its own 1; unknown 0; open PR 2; locked 1; no readable HEAD 0; refused for another reason 1; outside the folder 3.
- Bot: running in the terminal tab discord bot.

### Decided since the last merged state PR
- #724 closed on the 11-26 run (issuecomment-7217160100).
- #734, #737, #739 merged on Ben's word (earlier today).
- #738 (`d21758e`), #741 (`bcb365e`), #743 (`f834dbb`), #742 (`0d6284c`), #747 (`175dd7c`), #748 (`c0d1757`) merged on Ben's pop-up word; b736, b740, b675 closed out.
- #731 closed: ruleset at six, rules file on main (#731 comments).
- #744 dispatched on Ben's go (b744); the planner ruled #745 items 2 and 4 (PR #745 issuecomment-7218881282).
- #746: Ben chose a two-week trial of low/haiku dispatch without a go; not in force until its rule text merges (#746 issuecomment-7219028189).

## Queue entries raised

- "One-time setup: the migrate-held approval environment (#744)", open.

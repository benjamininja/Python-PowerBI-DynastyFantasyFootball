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


## CURRENT STATE (2026-11-28, twenty-fifth save, before a compact at Ben's word; session `10ea8a98-91e0-445b-bef3-77cb005def21`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-28 ~18:45 UTC, session `10ea8a98-91e0-445b-bef3-77cb005def21`. Ben invoked session-dispatch in this session (armed). A compact keeps the id.
- **Heads.** origin/main at `6a00ab1` (#775), after #772 `62ac24f`, #769 `11c638f`, #774 `f2a7d63`, #771 `cdeecef`.
- **Rules in force.** Six required checks; GOAL-RUN.md's closed list merges on Green alone (a ledger change also needs cap-ledger-auditor clean). No-go trial to 2026-12-12 for low and haiku tickets not held or backlog (none dispatched under it yet). A PR on two auditor lists: the planner names the one reviewer (ruling for #772, #772 issuecomment-7243254560); a rules-file line is owed by the planner to Ben.
- **Ben's rulings of 2026-11-28 (this session):** delete the Fantrax secrets, spike copies too (#760 issuecomment-7243287016); brief 4 drift failure: investigate both causes first, read-only (#473, latest manager comment); the brief 4 bar is Ben's 2026-11-09 bar, 1 point plus 5%, 90%, 2% (planner, #473 issuecomment-7243906914).

### Next
1. **#473 brief 4 (b473-history, session `24575614-f591-4e0c-a050-0086adf40baa`, medium, this session's dispatch)**: drift check failed (#473 issuecomment-7243916310). Ben: investigate both first; the planner set it medium for b473-history (questions #473 issuecomment-7243994213). Planner ruled neither (#473 issuecomment-7244034527): Profile none, the counts go into 02i's own drift report, run under its existing rule; sent to b473-history by message (still listed, rule already loaded). Await its report. It had parked before any count: its dispatch cannot run analysis code (#473 issuecomment-7244016630). Sent to the planner: (a) Profile: probe or (b) a committed read-only scripts/diagnose_scored_history.py with Ben's exact rule; then re-dispatch at medium on branch worktree-b473-history, same worktree. Earlier sent the go with the bar ruling (Ben's 2026-11-09 bar, #473 issuecomment-7243906914) and Ben's choice to declare the category_id FK (#473 issuecomment-7243986718). Part 2 uncommitted in its worktree; part 1 pushed at ba20b81. On its report: read its findings on #473; a fix or a rerun is the planner's next brief. The planner opens a one-line ADR-0018 decision 6 PR for the FK after its compact: ask Ben's merge word when its number arrives.
2. **#773 (tier low, filed by the planner)**: the loader stops rebuilding Ben's team-name list on every run. Dispatch now that #772 merged; under the no-go trial if the planner's ticket names files and proof and it is not held, else on Ben's go. Read the ticket first.
3. **--live for 04m (#520)**: one-line PR after one scheduled run's `[shadow]` lines show every closed period matching. Counts on #520; planner reads; Ben's word. Target before 2026-12-03, else tell the planner. Check the --live advisories (#764 issuecomment-7240955453).
4. **#522**, then **#523** (read #554, now closed, first), then **#524**, each on Ben's go.
5. **State PR #634**: was BLOCKED at the last save; read why before asking Ben's merge word.

### Waiting
- On Ben: queue entry "Delete the Fantrax sign-in secrets" (#760), Session line re-keyed to this session. Ben answered delete; his hand step is open.
- On the planner: the ADR-0018 decision 6 PR for the category_id FK (after its compact).

### In flight
- b473-history, session `24575614-f591-4e0c-a050-0086adf40baa`, #473 brief 4, medium; investigating via 02i's drift report on the planner's ruling; no PR yet.
- Open PRs: #634 (state), #595 (b589, parked, DIRTY), #563 (b556, Power BI backlog, BLOCKED).

### Peers
dff-central-planner `36235893-7875-4548-9384-a950ad72d75d`; Tools-builder-manager `0e714f8a-9e39-453b-aa53-f3f91e9431ec`; Tools-central-planner `ad27c4f7-ccae-4f9d-aab0-2be31444a3f3`; personal-assistant `061c1d24-09c1-4c01-8d89-ff693eb974d9`. SendMessage by name.

### Reads and checks due
- Tonight's scheduled etl-daily (~20:00 UTC 2026-11-28): first run with no Fantrax login (#765) and 04m's `[shadow]` lines (#764). Post counts only. The last two runs failed on the old login path.
- Saturday mornings: after Ben's export, run `.venv/Scripts/python.exe scripts/load_fantrax_history.py` and post counts on #770. Expect 0 names on the owner's list and no unapplied guess (Ben's list applied: crosswalk 35 rows). Do not run the loader between a fill and `--apply` until #773 lands.
- Advisor baseline (after #772): security INFO 5, WARN 1; performance unindexed FK 42, unused index 1, WARN 4 and 2.
- Tools-builder-manager holds the machine test line for its PR #326 (~80 min from ~18:20 UTC); ask it before any local full run.

### Decided since the last merged state PR
- Ben by button in the planner's chat: declare the category_id FK (#473 issuecomment-7243986718).
- Earlier items (to the twenty-fourth save) are on their tickets; see this file's git history.
- PR #774 merged (`f2a7d63`) on Ben's word: manager allow rules for load_team_names.py.
- PR #769 merged (`11c638f`) on Ben's word after a clean supabase-auditor review (3 advisories); migrate push success, advisors equal baseline (#473 issuecomment-7243525593); b473-categories closed out.
- PR #772 merged (`62ac24f`) on Ben's word after a supabase-auditor round (F1 fixed at bf6ca56, accepted on re-check, closed); planner read no breach; migrate push success, advisors equal baseline; b770-teamxwalk resumed on Ben's word for F1, then closed out. Seed 33 rows; shadow load unknown_team 17 (was 124), ledger gone 13 (was 90), trade log gone 0 (was 66) (#770 issuecomment-7243792330). Ben's list applied, crosswalk 35 rows.
- PR #775 merged (`6a00ab1`) on Ben's word: builder allow rules for 02i, fit_baseline, 04g, yardstick_report.
- #554 closed on the planner's read.
- Dispatched on Ben's go: #473 brief 4 (b473-history). Resumed on Ben's word: b770 (F1). Resumed as this session's own: b473-history (to load the new rule).
- Settings-copy note: a `cd` into a settings worktree moves the session's directory; use `gh pr create` from the repo root with `--head`, never `cd`.

## Queue entries raised

- None open.

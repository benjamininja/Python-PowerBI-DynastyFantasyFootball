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


## CURRENT STATE (2026-11-27, nineteenth save, before a compact at Ben's word; session `e5579518-3626-469b-b1d5-3095f10a1c6a`)

Done items left this block: their records are on GitHub.

- **Saved:** 2026-11-27 ~12:00 UTC, session `e5579518-3626-469b-b1d5-3095f10a1c6a`. session-dispatch is loaded (Ben typed it this session; a compact keeps it).
- **Heads.** origin/main at `f94787c` (PR #739). CI on main green at `a5fa34c`. Migrate push on `7130221` stopped at the held file by design. Ben's dispatch run 45992249898 applied it: SUCCESS.
- **Rules in force.** Until #731's ruleset is set by Ben, **every PR needs Ben's merge word** by pop-up. Green = every CI check SUCCESS at the head, no conflict, one read; plus migration order for a migration PR; one reviewer per code PR (pr-code-reviewer with mrp-dff-code-review at tier effort, or supabase-auditor on migrations, registry, generator or SUPABASE workflows). Before a merge, read the last push run on main. A relayed go from the planner is confirmed by pop-up here.

### Next
1. **PR #738** (#736, b736-sixchecks, session `970e6fa1-fd38-4a66-93f8-96a99f2da9db`): reported green at `b0444c3`; the manager's read at the save: CLEAN, every check SUCCESS or skipped. To do: start pr-code-reviewer (packet, mrp-dff-code-review, low effort), post the re-proof, ask Ben's merge word by pop-up (it changes the data PR's merge script), merge pinned, tell the planner (the #731 ruleset step waits on it), closeout b736. b736 flagged that the Required checks table in CONTRIBUTING.md (from line 46) still lists three checks: that's for the #731 rules-file step, tell the planner.
2. **#675 PR 2** (b675-leagueroles, session `3fbeb76a-d8f0-4fc6-9be4-b6e705a6fe85`, resumed on Ben's word): building the league table and team list loads (shared.load_leagues, shared.load_teams). At green: supabase-auditor, migration order, Ben's word, merge, a migrate Action if held, post-schema-change check, then closeout b675 (Ben's word given). #675 stays open until a scheduled run shows the access loads pass with counts for all four tables.
3. **#740** (b740-loginflags, session `52653931-4ec2-4ce7-aab2-911bac344db2`, tier low, dispatched on Ben's go, confirmed by pop-up): the Fantrax login flags go into the SessionStillDead message. At green: reviewer, Ben's word, merge, tell the planner (it reads the next run's flag line).
4. **Next scheduled etl-daily run** (~20:00 UTC 2026-11-27): read the access load (the App roles tab now says app_admin, per Ben by pop-up, record #675 issuecomment-7217401577). #662 and #700 close once a run's notice shows the two load counts.
5. **#731**: Ben accepted the table and the closed list (#731 issuecomment-7217186617). After #738 merges, the planner puts the ruleset button to Ben; then the manager's PR puts #731's rules text (with its corrected line) into GOAL-RUN.md, on Ben's word.
6. App chain after #675: #663, #664, #665, #676, #682, then #719, #720. Dispatch only on the planner's ready and Ben's go.

### Waiting
- On Ben: nothing in the queue (empty). Coming: merge words for #738, #675 PR 2 and #740's PR.
- On builders: b736 (done, waiting for the merge), b675 and b740 building.

### In flight
- b736-sixchecks `970e6fa1` (#736): PR #738 at `b0444c3`, waiting for re-proof.
- b675-leagueroles `3fbeb76a` (#675 PR 2): building.
- b740-loginflags `52653931` (#740): building.
- Open PRs not ours: #691 (old data PR), #634 (state), #595 (b589, parked), #563 (b556, parked).

### Peers
dff-central-planner `823b0d8b-9a43-423c-82fe-429cfcd98aae`; Tools-builder-manager `fbd93714-8c8b-49c7-b434-7dee4a8488fd`; Tools-central-planner `4e27fb7c-445f-47d9-ad2b-919bca911066`; personal-assistant `5d72e933-3c89-4f59-8d43-6e6ac9884826`. Tools-builder-manager holds the machine test line for tools PR #196's reproof (the dynasty side said clear; wait for its end notice before any local full run).

### Reads and checks due
- Tonight's etl-daily run: access loads, #723/#740 flag line, Fantrax logins count.
- Closeout list at this save: merged and still there 2; no commit of its own 0; unknown 0; open PR 2; locked 1; no readable HEAD 0; refused for another reason 2; outside the folder 3.
- Bot: running in the terminal tab discord bot.

### Decided since the last merged state PR
- #724 closed on the 11-26 run (issuecomment-7217160100).
- #734 merged at `7130221` on Ben's word; auditor finding 1 ruled no breach by the planner (PR #734 issuecomment-7217217148); the post-schema-change check is clean (#675 issuecomment-7217393524).
- #737 (`8944837`) and #739 (`f94787c`) merged on Ben's word.
- #736 and #740 dispatched on Ben's go; b675 resumed for PR 2 on Ben's word, closeout after PR 2 approved.

## Queue entries raised

- None open (the migrate Action for #734 was raised and closed today; the queue is empty).

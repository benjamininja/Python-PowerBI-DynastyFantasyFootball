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


## CURRENT STATE (2026-11-25, fifteenth save, before a clear at Ben's word; session `4ff97ebc-bfd4-4723-997c-406160d975ba`)

Done items left this block: their records are on GitHub (tools #272 read budget).

- **Heads.** origin/main and the main checkout at `2ad12bd` (PR #714). CI on main green through `428a877`; `2ad12bd` tests was running at this save: **read it first.**
- **Rules.** Green is every CI check SUCCESS at the head with no conflict, on one read; no local full run, no re-proof of a merged tree; read CI on main after each merge; one reviewer, no advisory rounds. The tools planner reports a shared CI-gate rule merged (tools #187, PR #288): read session-rules and GOAL-RUN.md fresh before the first merge.
- **GitHub fault.** All afternoon GitHub gave 500/502 and GraphQL errors on some writes. When `gh` fails, `gh api` REST often works (`gh api repos/<o>/<r>/issues/<n>/comments -F body=@file`). The token's merge of a PR that edits a workflow file failed every time (#709, #714); Ben merged both on the web. Pattern sent to the tools planner for tools #204.
- **Builders running:**
  - **b697-gsishold** (#697, PR #716, session `1e16794b-d836-4076-9300-548fd4f191f9`). Green by its report at `2a7e9a7`. Ben's word: merge when green (issues/697#issuecomment-7167922906). The one review is posted, no blocking finding (pull/716#issuecomment-7168622017); advisories F1 to F5 are the planner's to raise. Next: one CI read, merge pinned. Ben may veto one choice in the PR body: a passing Chain whose table cannot be put back is held, never published on the new id.
  - **b715-validate** (#715, session `aa8bccb1-3928-4ed4-9c83-0494d72f518a`), tier low, from `2ad12bd`. Ben's go confirmed by button. Before merge: the planner reads the PR; the supabase-auditor is the one reviewer. No merge word yet.
- **Waiting on Ben's word or a record:**
  - The chain (#670, then #675 before #663, never side by side; #682; then #663, #664, #665; #676 after #675): Ben's go is "dispatch the chain after #697 merges". Before each dispatch, ask the planner to recheck that ticket's body (they lean on unmerged #670, #675, #682).
  - #662 and #700 close once the scheduled run's notice shows the two load counts (Ben's word, issues/662#issuecomment-7167238773).
  - #713: note on the ticket the first later PR under pbi/, mouserat_trade-bud/, discord_bot/ or docs/site/ (the skip's first reading).
  - #699 stays open for the planner: index on 38 foreign-key child columns (a migration and a design decision); advisory F1, no lock_timeout on the fixture TRUNCATE.
  - Closeout words for b697 and b715 after their merges: ask by pop-up.
- **Closed out this session:** b597, b688, b662, b686, b695, b581, b639, b700, b699, b713.
- **Peers:** dff-central-planner `9bcc0c9c-574c-4ebb-b4f4-18edc03af9aa`; Tools-builder-manager `dabbbcd0-2b97-445e-a2d9-4502691fb617`; Tools-central-planner `2c14b7ab-3b12-4984-ae56-5c6526f96566`.
- **Bot:** bot.py in a terminal tab of this session. Check it after a clear.

## Queue entries raised

- None open. The #662 App roles tab Action is done, and Action 2 was withdrawn by Ben's Decision to automate.

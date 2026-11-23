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
- **Re-proof:** `.venv/Scripts/python.exe scripts/reproof.py <pr> <head>`
  after `git fetch origin`, run in the background. Post a summary on the
  PR with counts only: its review-finding lines hold row keys. Merge
  squash, pinned with `--match-head-commit`, then `git pull --ff-only`
  in the main checkout at once.
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
  to Ben by button in chat, then act.

## CURRENT STATE (2026-11-23, second save; session `f38b1eac-6b97-4859-8aea-e68610d98e1c`, before a clear at Ben's word)

- **Heads.** origin/main and main checkout `828db84`.
- **Merged this session:**
  - PR #652 (#650, b650) as `d4e7847`, pinned to `b76df2f`. GREEN on
    base `61aa044`, 3428 passed (pull/652#issuecomment-7102542315); code
    review, no findings (pull/652#issuecomment-7102458222).
  - PR #651 (the manager's own: ADR-0025 text in GOAL-RUN.md and
    supabase-auditor.md) as `828db84`, on Ben's buttons "Manager edits
    both" (a one-time exception) and "Merge now"
    (issues/548#issuecomment-7102719077). Its branch and worktree are
    removed.
- **Closed out:** b650-ownerheaders, on Ben's button
  (issues/650#issuecomment-7102718573).
- **Sign-in check done:** Discord is the only provider; Ben's ruling by
  button: Confirm email on (issues/548#issuecomment-7102523231).
- **NEXT, first: the owner-crosswalk load (#548).** Ben chose "Run it
  now" by button, then asked for this clear prep before the run started.
  **It has not been run.** At Ben's word in the new session: run
  `scripts/load_owner_crosswalk.py --out <a new file outside every
  repository>`, show Ben the file's full SQL in chat and in a queue
  Action, Ben runs it in the Supabase SQL editor, verify by count only
  (rows 30, teams 28), Ben deletes the file.
- **Running builders:** none of this manager's.
- **The bot is down** at this save (no `bot.py` process). Restart it at
  the next start.
- **Test line:** dynasty's end notice went to Tools-builder-manager, who
  may be running tools PR 246's re-proof (up to 90 minutes). Ask for the
  line before a full re-proof.
- **From the planner, not started:**
  - The Supabase consultant line for GOAL-RUN.md (tools #247): a queue
    Action. On Ben's approval the manager adds it in its own PR.
  - Whether to prove by a live test that a builder's subagent cannot
    reach supabase-dynasty (tools #247): a queue Decision.
  - #655 item 1, the manager's: prune the merged and abandoned worktrees
    (13 merged, 25 detached, 5 folders git does not know, each checked
    for unpushed work first). Another session's builder is closed out
    only on Ben's direct word, per builder.
  - PR #653 (draft, the supabase-look agent) is the planner's. It merges
    after tools PR #249, on Ben's word.
  - #644: `reproof.py` leaves its temp folder behind; this session's run
    left one more.
- **Open PRs:** #653 (draft, planner), #634 (the state batch; the
  planner merges it after Ben's approval), #595 (last, after a data PR
  stages the DLF delete, #589), #563 (held).
- **Dispatch order, each at Ben's go:** #633, #637, #639 (medium), #616
  (ADR amend as a Decision first), #626, #597. #620 waits on tools #231.
  Memory is tight: about two builders at a time.
- **Peers:** dff-central-planner session
  `e0f49660-15b2-44b9-8430-e04f2e6b243b`; Tools-builder-manager queue id
  `55edaa09-855e-454f-991a-371eb4875402`. After the clear, send both the
  new session id.

## Queue entries raised

- "Approve the Supabase consultant line for GOAL-RUN.md" (Action):
  Session `f38b1eac-6b97-4859-8aea-e68610d98e1c`.
- "Decide how to prove a builder's subagent cannot reach
  supabase-dynasty" (Decision): Session
  `f38b1eac-6b97-4859-8aea-e68610d98e1c`.
- "Decide whether the published after-deadline choices table carries
  locked_value" (Decision, the planner's): Session
  `e0f49660-15b2-44b9-8430-e04f2e6b243b`.

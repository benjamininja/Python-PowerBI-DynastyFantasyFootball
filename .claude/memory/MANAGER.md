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
  to Ben by button in chat, then act. A tick is not approval of a merge
  either: an entry that asks for a merge is a Decision, so the pane
  writes an Answer, and it never offers the tick as a way to approve.
- **An owner's settings edit** is made by Ben in the main checkout. On
  his word the manager copies the file unchanged to a branch and a PR.
  After that PR merges, restore the main checkout's copy and pull at
  once: git refuses a pull over the same edit left uncommitted.

## CURRENT STATE (2026-11-24, tenth save, before a compact; session `695f05fc-6dff-445b-a9fd-af605c6997d9`)

- **Heads.** origin/main and main checkout `43d053c` (PR #668). The
  main checkout is clean.
- **session-dispatch** was typed by Ben in session `695f05fc`. A
  compact keeps the session; a clear makes a new one and Ben types it
  again.
- **Ben's words in this session, all recorded:** closeout of b626-creds
  once PR #659 is merged (issues/626#issuecomment-7132525378); closeout
  of b616-manualpublish once it has stopped and all its PRs are merged
  (issues/616#issuecomment-7132525971); next dispatch #597
  (issues/597#issuecomment-7132526468); and, typed in chat, "merge #659
  when green, then dispatch #597".
- **#626, PR #659** (builder **b626-creds**, Tier low, session
  `7daad6fd-715d-4117-9ed2-49ffa75f0e58`, branch `worktree-b626-creds`),
  head `389ca8dc4735d290509a23818b8e9ac7cadd6ca9`. Code review round
  closed: F1 fixed, re-check accepted, nothing open
  (pull/659#issuecomment-7132571868). Re-proof GREEN at this head on
  base `f8b4584` (pull/659#issuecomment-7132684294), but main has moved
  to `43d053c`. **Next:** when Tools-builder-manager's end notice for
  tools PR #253 arrives (dynasty has the line next, agreed): send a
  start notice, `git fetch origin`, re-run `reproof.py 659 <head>` in
  the background, send the end notice, post the counts, read CI once
  (every check SUCCESS), merge squash pinned, `git pull --ff-only`,
  then close out b626-creds (git cherry or no-diff check, the interim
  link check, `claude rm 7daad6fd`), record on #626.
- **#597: dry run done and matches** (name `b597-teamabbr`, medium, no
  profile, 59 deny rules). The brief is in the session scratchpad and
  is rebuilt from the ticket if lost: ticket body plus the planner's
  check and the cut in two (steps 1 and 2 only, no `pbi/`), full suite
  held, the DROP COLUMN parks as a Decision, supabase-auditor at
  re-proof. **Next:** after #659 is merged, run the dispatch with
  `-Apply` (10-minute timeout), record the start on #597.
- **#616, PR #669** (builder **b616-manualpublish**, Tier high, session
  `38d02387-31bf-4bca-b945-9f78e851f66f`, branch
  `worktree-b616-manualpublish`), head `e0eb103` at its report. Built
  on Ben's pane Answer (a) (issues/616#issuecomment-7132412282). The
  builder reports it green and waits. A first-round code review (full,
  high) is running, and the planner is asked for its read (it amends
  ADR-0008, CONTRIBUTING.md and CLAUDE.md). **Next:** post the findings
  on the PR, run the one round if any (builder woken with
  `resume_plain.ps1`), ask for the test line, re-prove, post counts,
  merge pinned on Ben's standing merge word for #616 when GREEN and the
  planner says no breach, then close out. Its live proof (#554's
  price-list publish) is Ben's own command.
- **Tools #247: done.** PR #668 merged as `43d053c` on Ben's pane
  Answer (a); both deny lines are on main (lines 75 and 76); worktree
  and branch removed; entry removed
  (tools issues/247#issuecomment-7133028058).
- **#654 is closed.** Planner PRs #660 and #667 are merged; the hold on
  the auditor step of #661 is lifted.
- **Dispatch order after #597,** each on Ben's go by button: #661, #662
  (same files, in that order), then #670 (after both merge), then
  brief 4 of #548 and the after-deadline copy (outside 2026-12-03 to
  2027-01-07), #663, #664, #665 (restated by the planner first); and
  #633, #637, #639, #644; #592 held; #620 waits on tools #242; #563
  held; #595 last. About two builders at a time. Tell the planner when
  #661's PR opens. #661 and #662 need the supabase-auditor and the
  After a schema change lands check.
- **Test line:** Tools-builder-manager holds it for tools PR #253
  (started 13:21Z, about 59 minutes); dynasty is next for PR #659;
  tools PR #255 follows dynasty's end notice. PR #669's re-proof needs
  the line too: ask again.
- **The bot is up** (checked 2026-11-24).
- **Worktree removal, interim check** (issues/655#issuecomment-7104025813):
  no link inside (`Get-ChildItem -Recurse -Force -Attributes
  ReparsePoint` prints nothing), `git status --porcelain` prints
  nothing, remove, confirm the folder is gone and `git worktree list`
  no longer shows it; a removal that stops part way is reported on
  #655, nothing forced.
- **#655 item 1, the rest:** merged and detached worktrees only at
  Ben's direct word per builder; 24 worktrees have a damaged git record
  (issues/655#issuecomment-7104537108).
- **Open PRs:** #669 (b616-manualpublish), #659 (b626-creds), #653
  (draft, planner), #634 (the state batch), #595 (last), #563 (held).
- **Peers:** dff-central-planner queue id
  `cff0e612-f08d-401c-9bb6-2a60446c1492`; Tools-builder-manager
  `5074d20f-d5f6-4edf-b1b1-e18d5f31db19`; Tools-central-planner
  `2f55ae6a-00e1-46b6-9f89-e3d2d939e0de`. Builders are woken with
  `resume_plain.ps1` (SendMessage does not list them); their messages
  arrive by name.

## Queue entries raised

- None open. The queue is empty.

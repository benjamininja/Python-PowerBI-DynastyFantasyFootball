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

## CURRENT STATE (2026-11-23, fourth save; session `aa75bef2-1167-49fd-995a-bdee72226d36`, the session after the clear)

- **Heads.** origin/main and main checkout `828db84`. The main checkout
  holds one uncommitted change, the owner's own: the deny line in
  `.claude/builders.settings.json` (the same edit as PR #657).
- **session-dispatch** was typed by Ben at this session's start.
- **Owner-crosswalk load (#548): done and verified.** Ben ran the SQL;
  the count read rows 30, teams 28, 0 duplicate pairs
  (issues/548#issuecomment-7103174921). The entry is removed. Ben was
  given the command that deletes the SQL file.
- **PR #656 (the manager's own): the Supabase consultant line in
  GOAL-RUN.md,** branch `docs/goal-run-consultant-line`, head `af80bbb`.
  Ben's word by button: "Merge when green (Recommended)"
  (tools issues/247#issuecomment-7103340781). At this save one
  storage-pg run was still in progress; every other check passed.
  **Next:** read the checks once, squash-merge pinned to the head only
  if every check passed, pull, remove its branch and worktree.
- **Tools #247, the builder reach: closed by a deny rule.** First live
  test: 10 supabase-dynasty tool names offered to a builder and its
  subagent. Ben chose the deny rule and "Ben edits, manager carries";
  Ben added `mcp__supabase-dynasty` to the builders settings. Second
  live test: 0 names offered to either
  (tools issues/247#issuecomment-7103503667). Both test builders are
  closed out. **PR #657** (branch `chore/builders-deny-supabase-dynasty`,
  head `3273a30`) carries Ben's edit unchanged; its merge is the queue
  Decision "Decide whether PR #657, the supabase-dynasty deny rule,
  merges". After that merge the main checkout's copy must be restored
  and pulled at once, as the Decision's first option says. Left with
  the planner: whether to deny the unauthenticated Supabase plugin
  server's two sign-in tools too.
- **Running builders:** none of this manager's.
- **#655 item 1, first part done.** The five folders git did not know
  held no unpushed work and are removed with their four local branches,
  on Ben's button "Folders and branches (Recommended)"
  (issues/655#issuecomment-7102915409 and -7103035127). Their cause:
  .git pointers that named the repository's pre-move location. Still
  open: the merged and the detached worktrees git lists, each on Ben's
  direct word per builder.
- **The bot is up,** restarted in a terminal tab of this session.
- **Test line:** Tools-builder-manager held it for tools PR 246's
  re-proof at this session's start. Ask before a full re-proof.
- **From the planner, not started:**
  - PR #653 (draft, the supabase-look agent) is the planner's. It merges
    after tools PR #249, on Ben's word.
  - #644: `reproof.py` leaves its temp folder behind.
- **Open PRs:** #656 (the manager's, merges when green), #657 (the
  owner's deny rule, waits on Ben's Decision), #653 (draft,
  planner), #634 (the state batch; the planner merges it after Ben's
  approval), #595 (last, after a data PR stages the DLF delete, #589),
  #563 (held).
- **Dispatch order, each at Ben's go.** The planner's order, sent
  2026-11-23: #616, #626, #597, #633, #637, #639, #644; #592 held; #620
  waits on tools #242; #604 and #590 at Ben's go. The last manager
  session had #633, #637, #639 first: ask Ben which leads. #616's ADR
  amend goes to Ben as a Decision first. Memory is tight: about two
  builders at a time.
- **Peers:** dff-central-planner queue id
  `986a10cc-2c8b-4d55-9600-5cc9306c91be`; Tools-builder-manager queue id
  `55edaa09-855e-454f-991a-371eb4875402`; Tools-central-planner queue id
  `6b47c44d-e4cb-43be-8d0a-51ec2776881b`. All were sent this session's
  id.

## Queue entries raised

- "Decide whether PR #657, the supabase-dynasty deny rule, merges"
  (Decision): Session `aa75bef2-1167-49fd-995a-bdee72226d36`.
- "Decide whether the published after-deadline choices table carries
  locked_value" (Decision, the planner's): Session
  `986a10cc-2c8b-4d55-9600-5cc9306c91be`.

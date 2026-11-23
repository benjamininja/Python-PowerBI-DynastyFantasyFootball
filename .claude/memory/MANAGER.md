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

## CURRENT STATE (2026-11-23, seventh save, two builders dispatched; session `aa75bef2-1167-49fd-995a-bdee72226d36`)

- **Heads.** origin/main and main checkout `6721d97`. The main checkout
  holds no uncommitted change.
- **session-dispatch** was typed by Ben again after the compact.
- **Owner-crosswalk load (#548): done and verified.** Ben ran the SQL;
  the count read rows 30, teams 28, 0 duplicate pairs
  (issues/548#issuecomment-7103174921). Ben was given the command that
  deletes the SQL file.
- **PR #656 merged** as `97dbebb`: the Supabase consultant line is on
  main (tools issues/247#issuecomment-7103677619).
- **Tools #247, the builder reach: closed by a deny rule, on main.**
  First live test: 10 supabase-dynasty tool names offered to a builder
  and its subagent. Ben added `mcp__supabase-dynasty` to the builders
  settings; second live test: 0 names offered to either
  (tools issues/247#issuecomment-7103503667). **PR #657 merged** as
  `6721d97`, pinned to `3273a30`, on Ben's pane Answer (a); every check
  SUCCESS on one read. The main checkout was restored and pulled at
  once; the file has the same blob hash as Ben's edit. Its worktree and
  branch are removed (tools issues/247#issuecomment-7104068971).
  **Open:** the planner's second line
  (tools issues/247#issuecomment-7103639275), the owner line
  `"mcp__plugin_supabase_supabase",` after line 75, is queued as an
  Action. After Ben's tick: ask Ben by button whether the manager
  carries the file unchanged to a PR; the merge is then a Decision;
  after that merge, restore the main copy and pull at once.
- **Worktree removal, interim check** (issues/655#issuecomment-7104025813,
  until tools #250's script is merged and pulled): list every junction
  or link inside (`Get-ChildItem -Recurse -Force -Attributes
  ReparsePoint`) and remove the link itself, never its target;
  `git status --porcelain` prints nothing; remove; confirm the folder
  is gone and `git worktree list` no longer shows it. A removal that
  stops part way is reported on #655 and nothing is forced. On Windows
  the remove follows a junction, and a file held open makes it stop
  part way (tools issues/250#issuecomment-7103861254).
- **The planner's locked_value Decision is ruled by the planner** (option
  (a), ADR-0025 decision 10 point 1; issues/548#issuecomment-7103631284);
  its entry is removed (issues/548#issuecomment-7103677049).
- **#654 grill answered** (the planner's; last record
  issues/654#issuecomment-7103974431): a foundations brief comes before
  brief 4 of #548; football launches first, baseball second (#658,
  owner-led). No brief posted, no dispatch asked.
- **Running builders, both dispatched by this session on 2026-11-23**
  on Ben's button answer "Planner's order" (to "Which order should the
  next dispatch follow?"):
  - **b616-manualpublish** (#616, Tier high, Profile none), session
    `38d02387-31bf-4bca-b945-9f78e851f66f`, branch
    `worktree-b616-manualpublish` (issues/616#issuecomment-7104311819).
    Part 1: it drafts the ADR or CONTRIBUTING amend, posts it on #616
    and sends the manager a ready Decision; it builds nothing until
    Ben's answer is relayed. Part 1 is done: the draft and plan are at
    issues/616#issuecomment-7104356290 and the Decision is queued
    (issues/616#issuecomment-7104376591). **Next:** on Ben's pane
    Answer, relay the question and the answer word for word to the
    builder, record it on #616, then remove the entry.
  - **b626-creds** (#626, Tier low, Profile none), session
    `7daad6fd-715d-4117-9ed2-49ffa75f0e58`, branch
    `worktree-b626-creds` (issues/626#issuecomment-7104312553).
    **Next:** when it reports its PR ready, ask Tools-builder-manager
    for the test line, re-prove, run the code review round, merge on
    Ben's standing merge word for #626 when GREEN.
  - Both briefs hold the full suite: builders run their own test files
    only. Ben's standing merge word covers #616 and #626 when GREEN,
    never a parked Decision.
- **#655 item 1, first part done.** The five folders git did not know
  held no unpushed work and are removed with their four local branches,
  on Ben's button "Folders and branches (Recommended)"
  (issues/655#issuecomment-7102915409 and -7103035127). Their cause:
  .git pointers that named the repository's pre-move location. Still
  open: the merged and the detached worktrees git lists, each on Ben's
  direct word per builder.
- **The bot is up,** restarted in a terminal tab of this session.
- **Test line:** with Tools-builder-manager, which runs its waiting
  re-proofs (tools PRs 236, 238, 239, 242) and sends a start and an end
  notice for each. Dynasty said it does not need the line now. Ask
  before a full re-proof.
- **From the planner, not started:**
  - **The #654 batch, held until planner PR #660 merges** (ADR-0026,
    docs only; it waits on Ben's approval in the planner's chat). Ben
    confirmed the grill (issues/654#issuecomment-7104535169). All Tier
    medium, Profile none, in this order: #661, then #662 (same files),
    then brief 4 of #548 restated whole (issues/548#issuecomment-7104491120),
    then the after-deadline copy (issues/548#issuecomment-7104493151),
    then #663, #664, #665 (the planner restates these three against
    merged code first). Brief 4 and the copy land outside 2026-12-03
    to 2027-01-07. #661 and #662 change schema, grants and a generator
    rule: the supabase-auditor and the After a schema change lands
    check apply; the planner sends replacement GOAL-RUN lines when
    #661's PR opens. Each still needs Ben's go.
  - #655: 24 worktrees have a damaged git record
    (issues/655#issuecomment-7104537108). The planner's worktree on
    branch `docs/adr-0026-app-roles` is in use: never offer it for
    removal.
  - PR #653 (draft, the supabase-look agent) is the planner's. It merges
    after tools PR #249, on Ben's word.
  - #644: `reproof.py` leaves its temp folder behind.
- **Open PRs:** #653 (draft,
  planner), #634 (the state batch; the planner merges it after Ben's
  approval), #595 (last, after a data PR stages the DLF delete, #589),
  #563 (held).
- **Dispatch order: the planner's, chosen by Ben by button on
  2026-11-23** ("Planner's order"): #616, #626 (both running), then
  #597, #633, #637, #639, #644 as a slot frees; #592 held; #620 waits
  on tools #242; #604 and #590 at Ben's go. Memory is tight: about two
  builders at a time. Each ticket needs its tier on the ticket and a
  dry run first.
- **Peers:** dff-central-planner queue id
  `986a10cc-2c8b-4d55-9600-5cc9306c91be`; Tools-builder-manager queue id
  `55edaa09-855e-454f-991a-371eb4875402`; Tools-central-planner queue id
  `6b47c44d-e4cb-43be-8d0a-51ec2776881b`. All were sent this session's
  id.

## Queue entries raised

- Action: "Add the Supabase plugin server deny rule to the builders
  settings file" (tools #247), raised 2026-11-23, open.
- Decision: "Decide whether a manual-only table may reach main by the
  pipeline's own data PR, on Ben's command (#616)", raised 2026-11-23
  for builder b616-manualpublish, open.

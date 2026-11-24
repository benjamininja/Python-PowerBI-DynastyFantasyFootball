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

## CURRENT STATE (2026-11-24, eleventh save, before a clear at Ben's word; session `695f05fc-6dff-445b-a9fd-af605c6997d9`)

- **Heads.** origin/main and main checkout `1eda32b` (PR #672). The
  main checkout is clean (only `.agents/` and `GEMINI.md` untracked).
- **session-dispatch** was typed by Ben in session `695f05fc`. After
  the clear Ben types it again before any dispatch, merge or closeout,
  and gives the closeout word per builder again.
- **Merged this session:** PR #659 (#626) `ea9876a`; PR #668 `43d053c`;
  PR #669 (#616) `1b1fc23`; PR #672 (#671) `1eda32b`. **Closed out:**
  b626-creds, b616-manualpublish, b671-dropwarn. **Closed:** #654,
  #658, #674 (and #616, #626, #671 by their PRs).
- **PR #685 (#661, builder b661-choicehist, session
  `59eeebaa-541a-48e6-a59f-96f0871eee19`, branch
  `worktree-b661-choicehist`), head
  `2acffd56d598aabe576870d63c71f33fd5270856`.** Code review: no
  blocking, F1 and F2 advisory (pull/685#issuecomment-7135947201).
  supabase-auditor: no blocking, two advisories
  (issuecomment-7135889854). Planner: no breach
  (issuecomment-7135882049). Ben: "merge #685 when green"
  (issues/661#issuecomment-7135951371). **Next:** ask the test line,
  re-prove, post counts, one CI read, merge pinned, pull; then queue an
  owner Action to dispatch `migrate.yml` for the held drops file
  (`final_at DROP DEFAULT`); run the planner's check lines
  (issues/661#issuecomment-7135889563); then dispatch #662 (brief
  ready, see Do first). Closeout of b661 needs Ben's word.
- **PR #684 (#597, builder b597-teamabbr, session
  `4a1fed88-8d24-4502-83c3-25eaf5bf18b3`, branch
  `worktree-b597-teamabbr`), head moving (was `24ccfdf`).** Ben re-ran
  01c on the branch (Note recorded, issuecomment-7136034918); the
  builder was woken to commit the table and read CI. Ben: "merge #684
  when green" (issues/597#issuecomment-7135711716); DROP COLUMN
  Decision answered (a) apply after merge
  (issuecomment-7135625750). **Next:** on the builder's report, code
  review (medium, full, high) and supabase-auditor, re-prove (it covers
  the trade-tool export and bot suite), merge pinned, then give Ben the
  `migrate.yml` dispatch step and run the After a schema change lands
  check; then dispatch #686 (Ben's go, issues/686#issuecomment-7135826055).
- **Dispatch chain on Ben's go, each after the one before merges:**
  #661 (PR #685) then #662 (go: issuecomment-7134054704) then #670
  (go: issuecomment-7134103462) then #682 = brief 4 of #548 (go:
  issuecomment-7135826055 on #548 and issues/682#issuecomment-7134177639;
  merge outside 2026-12-03 to 2027-01-07) then #663 then #664 then
  #665 (each needs the planner's restated brief first). Separately:
  #684 then #686. Backlog, no go yet: #683 (F3 of #669), #687 (F1 of
  #685), #675 and #676 (map #658, planner restates first), #633, #637,
  #639, #644; #592 held; #620 waits on tools #242; #563 held; #595 last.
- **Owed to the planner:** one line when #662's PR opens and when
  #670's PR opens; #682's owner Actions 2 to 4 are queued when its PR
  opens (Action 1 is done).
- **Test line:** tools runs PR #255 then #210; dynasty asks again for
  #685 then #684, with start and end notices.
- **Bot:** restarted 2026-11-24 in a terminal tab of this app.
- **Worktree removal, interim check** (issues/655#issuecomment-7104025813)
  as before; #655 item 1 and the 24 damaged-record worktrees unchanged.
- **Open PRs:** #685, #684, #653 (draft, planner), #634 (state batch),
  #595, #563.
- **Peers:** dff-central-planner `125a6d6d-88c4-406a-8ea8-220374432d42`
  (new after its clear); Tools-builder-manager
  `e7026592-a1b4-4ccd-afea-61d5cf451e9f`; Tools-central-planner
  `2f55ae6a-00e1-46b6-9f89-e3d2d939e0de`. Builders answer by name
  through SendMessage while running; a stopped one is woken with
  `resume_plain.ps1`.

## Queue entries raised

- None open. The queue is empty.

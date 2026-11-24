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

## CURRENT STATE (2026-11-24, ninth save; session `695f05fc-6dff-445b-a9fd-af605c6997d9`)

- **Heads.** origin/main and main checkout `f8b4584` (PR #660, ADR-0026,
  merged by the planner). The main checkout holds one uncommitted
  change: Ben's own line in `.claude/builders.settings.json` (below).
- **session-dispatch** was typed by Ben in session `695f05fc`. A later
  clear makes a new session: Ben types it again.
- **Ben's closeout words, by button on 2026-11-24, both recorded:**
  b626-creds once PR #659 is merged (issues/626#issuecomment-7132525378);
  b616-manualpublish once it has stopped and all its PRs are merged
  (issues/616#issuecomment-7132525971). After another clear these are
  asked again.
- **#616: Ben's pane Answer is (a)** (widen the exception, run on Ben's
  PC, no new workflow). Recorded word for word at
  issues/616#issuecomment-7132412282, relayed word for word, entry
  removed. Builder **b616-manualpublish** (Tier high, Profile none,
  session `38d02387-31bf-4bca-b945-9f78e851f66f`, branch
  `worktree-b616-manualpublish`) is resumed and builds under its plan
  (issues/616#issuecomment-7104356290). Under (a) the supabase-auditor
  joins only if a PR touches a path on its list.
- **#626, PR #659** (builder **b626-creds**, Tier low, session
  `7daad6fd-715d-4117-9ed2-49ffa75f0e58`, branch `worktree-b626-creds`).
  Code review, first round: one finding, F1, advisory class but a real
  regression (the second-factor secret is read with `os.getenv` only;
  pull/659#issuecomment-7132489194). The planner's read: fix in this PR,
  done condition amended to the three Fantrax names
  (pull/659#issuecomment-7132497362). The builder is resumed to fix F1
  and answer once on the PR. **Next:** on its report, start a fresh
  reviewer for the re-check (packet with F1, the answer and the new
  head), record the round as one table comment, ask the tools manager
  for the test line, re-prove the new head, post counts, merge pinned on
  Ben's standing merge word for #626 when GREEN, pull, close out.
  A re-proof of the old head `9a3a07e` was started at the free line
  (base `f8b4584`); its result does not cover the new head. An end
  notice to Tools-builder-manager is owed when it prints its RESULT.
- **Tools #247, second deny line.** Ben made the edit and ticked the
  Action (tools issues/247#issuecomment-7132441776). On Ben's button
  (Carry it now) the file is carried unchanged to **PR #668** (branch
  `chore/builders-deny-supabase-plugin`, same blob hash as Ben's copy;
  tools issues/247#issuecomment-7132524777). The merge is queued as a
  Decision. **Next:** on Ben's pane Answer, merge pinned when every
  check passed on one read, then `git restore` the main copy and pull
  at once, check both lines, remove the branch and its worktree, record
  on tools #247, remove the entry.
- **#654 is closed** at the planner's ask (resolution
  issues/654#issuecomment-7132410402).
- **Next dispatch: #597** (Tier medium, Profile none) when b626-creds's
  slot frees, on Ben's button of 2026-11-24
  (issues/597#issuecomment-7132526468). Dry run first. Then, each on
  Ben's go by button: #661, #662 (same files, in that order; both now
  carry Profile: none), #633, #637, #639, #644; #592 held; #620 waits
  on tools #242; #563 held; #595 last. About two builders at a time.
- **The #654 batch** (all medium): #661 and #662 are ready; brief 4 of
  #548 waits for the planner's ruling on the page's read path and, with
  the after-deadline copy, lands outside 2026-12-03 to 2027-01-07; #663,
  #664 and #665 are restated by the planner first. #661 and #662 need
  the supabase-auditor and the After a schema change lands check. Tell
  the planner when #661's PR opens (it then sends GOAL-RUN lines). Hold
  the auditor step of #661's re-proof until planner PR #667 is on main.
- **Test line:** dynasty holds it for the re-proof of PR #659 (start
  notice sent). Tools' next full run is tools PR #253, after dynasty's
  end notice.
- **The bot is up** (checked 2026-11-24).
- **Worktree removal, interim check** (issues/655#issuecomment-7104025813,
  until tools #250's script is merged and pulled): list every junction
  or link inside (`Get-ChildItem -Recurse -Force -Attributes
  ReparsePoint`) and remove the link itself, never its target;
  `git status --porcelain` prints nothing; remove; confirm the folder
  is gone and `git worktree list` no longer shows it. A removal that
  stops part way is reported on #655 and nothing is forced.
- **#655 item 1, the rest:** merged and detached worktrees only at
  Ben's direct word per builder; 24 worktrees have a damaged git record
  (issues/655#issuecomment-7104537108).
- **Open PRs:** #668 (manager, settings line), #667 (planner, auditor
  basis), #659 (b626-creds), #653 (draft, planner), #634 (the state
  batch), #595 (last), #563 (held).
- **Peers:** dff-central-planner queue id
  `cff0e612-f08d-401c-9bb6-2a60446c1492`; Tools-builder-manager
  `5074d20f-d5f6-4edf-b1b1-e18d5f31db19`; Tools-central-planner
  `2f55ae6a-00e1-46b6-9f89-e3d2d939e0de`. All were sent this session's
  id. Builders are reached with `resume_plain.ps1` (SendMessage does
  not list them).

## Queue entries raised

- Decision: "Decide whether the manager merges PR #668, the second
  builders deny line (tools #247)", raised 2026-11-24, Session
  `695f05fc-6dff-445b-a9fd-af605c6997d9`, open.
